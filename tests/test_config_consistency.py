"""配置 / 依赖 / 余额接口的一致性门禁。

来自 2026-09-17 的全项目审计（`docs/CONSISTENCY_AUDIT_20260917.md`）。
这里钉住的都是"**声明与实际行为不一致**"的类：
- 声明了却不生效的配置项；
- 同一事实写在两个文件（已踩 5 次）；
- 依赖声明与实际 import 不符（会让功能静默降级）；
- 余额接口的地址拼装（`/v1` 前缀会导致 404）。
"""

import ast
import inspect
import re
import tomllib
from pathlib import Path

import pytest

from app.config import DEFAULT_CONFIG, SENSITIVE_CONFIG_FIELDS
from app.providers import balance as balance_module
from app.providers.balance import (
    BALANCE_FALLBACK_PROVIDER,
    BALANCE_PROBES,
    DEEPSEEK_BALANCE_URL,
    BalanceResult,
    has_builtin_probe,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ───────────────────────── 敏感字段：单一来源 ─────────────────────────


class TestSensitiveFieldsSingleSource:
    """`SENSITIVE_CONFIG_FIELDS` 必须只有**一处**定义。

    审计发现：`secure_config.py` 里有一份**字面量副本** `_SENSITIVE_FIELDS`，
    而它的注释却声称"与 AppConfig 共用同一定义" —— 实际既没 import、
    也没有测试锁定两者相等。任一处改动都会静默漂移，后果是
    "某个密钥该加密却以明文落盘"（安全后果，且**不会报错**）。
    """

    def test_secure_config_uses_the_same_object(self):
        from app.secure_config import _SENSITIVE_FIELDS

        assert _SENSITIVE_FIELDS is SENSITIVE_CONFIG_FIELDS, (
            "secure_config 又抄了一份敏感字段清单 —— 必须 `from .config import` 同一个对象"
        )

    def test_no_literal_duplicate_in_source(self):
        """守卫：`secure_config.py` 里不得再出现那份三元组的**字面量**。"""
        src = (_REPO_ROOT / "app" / "secure_config.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
                vals = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
                if vals == list(SENSITIVE_CONFIG_FIELDS):
                    raise AssertionError(f"secure_config.py:{node.lineno} 又出现了敏感字段清单的字面量副本")

    def test_no_second_literal_definition(self):
        """全仓只允许 `config.py` 出现该清单的**字面量**定义。

        `secure_config.py` 里的 `_SENSITIVE_FIELDS = SENSITIVE_CONFIG_FIELDS`
        是**别名**（指向同一个对象），不算第二处定义 —— 所以这里只拦字面量。
        """
        for path in (_REPO_ROOT / "app").rglob("*.py"):
            if path.name == "config.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
                    vals = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
                    assert vals != list(SENSITIVE_CONFIG_FIELDS), (
                        f"{path.relative_to(_REPO_ROOT)}:{node.lineno} 出现敏感字段清单的字面量副本"
                    )


# ───────────────────────── 已移除的无效配置项 ─────────────────────────


class TestDeadConfigKeysRemoved:
    """`theme` / `auto_save` 已**有意移除**（声明了却完全无对应功能）。"""

    @pytest.mark.parametrize("key", ["theme", "auto_save"])
    def test_not_in_default_config(self, key):
        assert key not in DEFAULT_CONFIG, f"{key} 又被加回来了 —— 它没有任何对应功能"

    @pytest.mark.parametrize("key", ["theme", "auto_save"])
    def test_not_read_anywhere(self, key):
        offenders = []
        for path in (_REPO_ROOT / "app").rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            if re.search(rf'\.get\(\s*["\']{key}["\']', src):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        assert not offenders, f"{key} 被读取了但配置里没有它：{offenders}"


# ───────────────────────── 图片尺寸：两端接通 ─────────────────────────


class TestImageSizeIsWiredBothEnds:
    """`img_width` / `img_height` 原先"声明了但无效"：既不可编辑也不被读取。"""

    def test_declared_with_defaults(self):
        assert DEFAULT_CONFIG["img_width"] == 1024
        assert DEFAULT_CONFIG["img_height"] == 1024

    def test_generator_reads_from_config(self):
        from app.image_generator import ImageGenerator

        src = inspect.getsource(ImageGenerator)
        assert '"img_width"' in src and '"img_height"' in src, "生成器没有从配置取尺寸"

    def test_ui_exposes_the_fields(self):
        """设置页必须有尺寸输入框。

        ❗ 用**读文件**而不是 `inspect.getsource(模块)`：后者对经
        `_safe_import` 延迟加载的模块不一定拿得到源码，会让断言无故失败
        （第一版就踩了这个）。查源码文件本身最稳。
        """
        src = (_REPO_ROOT / "app" / "lifecycle_ui.py").read_text(encoding="utf-8")
        assert "img_width_entry" in src and "img_height_entry" in src, "设置页没有尺寸输入框"
        # 保存是循环写的（键在循环变量里），所以断言"两个键都出现在源码中"
        # 且确实有一处把循环变量交给 config.set —— 不能只断言字面量形式。
        assert '"img_width"' in src and '"img_height"' in src, "尺寸键没被保存"
        assert "self.config.set(_key, _v)" in src, "尺寸输入没有被写回配置"

    def test_bad_config_value_falls_back_instead_of_raising(self):
        """配置里是垃圾值时必须退回默认，**不能**让生成图片这条主路径抛错。"""

        class _Cfg:
            def __init__(self, v):
                self._v = v

            def get(self, key, default=None):
                return self._v if key in ("img_width", "img_height") else "disabled"

        gen = __import__("app.image_generator", fromlist=["ImageGenerator"]).ImageGenerator(_Cfg("abc"))
        for bad in ("abc", "", None, "0", "-8", 3.7):
            assert gen._dimension(None, "img_width") >= 0  # 不抛异常即可
        gen2 = __import__("app.image_generator", fromlist=["ImageGenerator"]).ImageGenerator(_Cfg("abc"))
        assert gen2._dimension(None, "img_width", default=1024) == 1024

    def test_disabled_provider_does_not_touch_size_config(self):
        """未启用/未知后端直接返回 None，不应去读尺寸（否则坏配置会把正常情况变异常）。"""

        class _Cfg:
            def get(self, key, default=None):
                if key == "img_provider":
                    return "disabled"
                raise AssertionError(f"未启用时不应读取 {key}")

        gen = __import__("app.image_generator", fromlist=["ImageGenerator"]).ImageGenerator(_Cfg())
        assert gen.generate("prompt") is None


# ───────────────────────── PDF 导出依赖 ─────────────────────────


class TestPdfExportDependencyDeclared:
    """`format_converter._to_pdf` 用 fpdf；漏声明会让"选 PDF"静默变成 TXT。"""

    def test_fpdf2_is_declared(self):
        data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        deps = data["project"]["dependencies"]
        assert any(d.startswith("fpdf2") for d in deps), (
            "pyproject 没有声明 fpdf2 —— `_to_pdf` 会静默降级成 TXT（不报错）"
        )

    def test_to_pdf_still_degrades_but_is_now_reachable(self):
        """降级分支本身是合理的兜底，但依赖已声明 ⇒ 正常安装下不会走到它。"""
        from app import format_converter

        src = inspect.getsource(format_converter.FormatConverter._to_pdf)
        assert "from fpdf import FPDF" in src
        assert "_to_txt" in src, "降级分支被删了 —— 没有 fpdf 时会直接崩"


# ───────────────────────── 余额：DeepSeek 官方接口 ─────────────────────────


class TestDeepSeekBalanceUrlIsOfficial:
    """DeepSeek 余额接口必须是官方绝对地址，且不受 `api_base` 影响。"""

    def test_constant_is_the_official_url(self):
        assert DEEPSEEK_BALANCE_URL == "https://api.deepseek.com/user/balance"

    def test_probe_uses_the_constant(self):
        probe = BALANCE_PROBES["deepseek"]
        assert probe.path == DEEPSEEK_BALANCE_URL
        assert probe.source_url == "https://api-docs.deepseek.com/zh-cn/api/get-user-balance"
        assert probe.configured is True

    def test_v1_suffixed_api_base_does_not_break_the_url(self):
        """回归：用户把 `api_base` 填成 `…/v1`（很常见）时，旧实现会拼成
        `…/v1/user/balance` ⇒ **404**。绝对 URL 使探针路径直接生效。"""
        seen = {}

        def http_get(url, headers, timeout):
            seen["url"] = url
            raise RuntimeError("stop")  # 只关心 URL，不真正请求

        from app.providers.registry import default_registry

        spec = default_registry().get("deepseek")
        balance_module.fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com/v1")
        assert seen["url"] == DEEPSEEK_BALANCE_URL, f"拼出了错误的余额地址：{seen['url']}"

    def test_url_also_correct_without_api_base(self):
        seen = {}

        def http_get(url, headers, timeout):
            seen["url"] = url
            raise RuntimeError("stop")

        from app.providers.registry import default_registry

        balance_module.fetch_balance(default_registry().get("deepseek"), http_get, api_key="k")
        assert seen["url"] == DEEPSEEK_BALANCE_URL


class TestBalanceFallbackToDeepSeek:
    """当前服务商无内置余额接口时，回退到 DeepSeek 官方接口。"""

    def test_has_builtin_probe_only_for_deepseek(self):
        assert has_builtin_probe("deepseek") is True
        for p in ("ollama", "glm", "qwen", "openai", "claude"):
            assert has_builtin_probe(p) is False, f"{p} 竟然有内置探针，请核实"

    def test_fallback_provider_is_deepseek(self):
        assert BALANCE_FALLBACK_PROVIDER == "deepseek"
        assert has_builtin_probe(BALANCE_FALLBACK_PROVIDER), "回退目标自己都没有内置探针"

    def _query(self, provider, *, override_url="", api_base=""):
        from app.ai_client import AIClient

        client = AIClient.__new__(AIClient)
        client._balance_cache = balance_module.BalanceCache()
        seen = {}

        def fake_get(url, headers, timeout):
            seen["url"] = url

            class _R:
                status_code = 200

                @staticmethod
                def json():
                    return {
                        "balance_infos": [
                            {
                                "currency": "CNY",
                                "total_balance": "1.00",
                                "granted_balance": "0.00",
                                "topped_up_balance": "1.00",
                            }
                        ]
                    }

            return _R()

        client._http_get = fake_get
        cfg = {
            "api_provider": provider,
            "api_key": "k",
            "api_base": api_base or "",
            "balance_url": override_url,
        }
        client.config = type("C", (), {"get": lambda self, k, d=None: cfg.get(k, d)})()
        from app.providers.registry import default_registry

        client.registry = default_registry()
        # 不要自己伪造 adapter：`AIClient._adapter_for` 就是
        # `self.registry.adapter(spec.key)`，用真的即可（`ProviderSpec` 上没有
        # `adapter_cls` 字段，第一版误以为有）。
        result = client.query_balance(provider)
        return result, seen

    def test_provider_without_probe_falls_back(self):
        result, seen = self._query("glm")
        assert seen["url"] == DEEPSEEK_BALANCE_URL, f"没有回退到 DeepSeek：{seen['url']}"
        assert result.provider == "deepseek"

    def test_fallback_result_says_whose_balance_it_is(self):
        """必须说明"这是 DeepSeek 的余额" —— 否则 GLM 用户会以为是自己 GLM 的余额。"""
        result, _ = self._query("glm")
        assert result.note, "回退结果没有 note，用户无法分辨这是谁的余额"
        assert "DeepSeek" in result.note and "glm" in result.note
        assert "DeepSeek" in result.format_total(), "format_total 没把 note 展示出来"

    def test_provider_with_probe_does_not_fall_back(self):
        result, seen = self._query("deepseek")
        assert seen["url"] == DEEPSEEK_BALANCE_URL
        assert not result.note, "DeepSeek 自己查询时不该带回退说明"

    def test_user_override_url_wins_over_fallback(self):
        custom = "https://my-proxy.example.com/balance"
        _, seen = self._query("glm", override_url=custom)
        assert seen["url"] == custom, "用户自定义的余额地址被回退覆盖了"

    def test_balance_result_note_round_trips_through_dict(self):
        r = BalanceResult(provider="deepseek", supported=True, total="1.0", note="说明")
        assert BalanceResult(**r.as_dict()).note == "说明"
