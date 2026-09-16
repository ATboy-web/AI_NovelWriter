"""
P2-5 设置页重构 与 `AIClient.probe_connection` 单元测试。

覆盖三块：
1. 设置页的下拉/模型候选/能力说明**由注册表生成**（修 P5：不再手工维护第二份清单）；
2. 旧实现里的两处「配了不生效」被修掉（P11 重复温度控件、P9 max_tokens/temperature 硬编码）；
3. 「测试连接」的探测逻辑：成功 / 各种失败分支都要有**明确的文字结论**，
   不能抛异常、也不能把失败当成成功。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
# 同上：按顶层模块名导入，避免 `tests.x` 在不同 pytest 调用方式下不可见
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
import pytest
from _source_scan import code_only

import app.ai_client as ai_client_module
from app.ai_client import AIClient
from app.ai_settings_ui import (
    describe_capabilities,
    models_for_provider,
    provider_choices,
)
from app.providers import default_registry


class FakeConfig:
    """最小配置替身（`get(key, default)` 即可满足 AIClient 的读取面）。"""

    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def make_client(**values) -> AIClient:
    return AIClient(FakeConfig(**values))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or ""

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


# ===================================================================== 注册表驱动


class TestSettingsFromRegistry:
    """设置页内容必须来自注册表，避免与 ai_client 的清单漂移。"""

    def test_every_registry_provider_is_selectable(self):
        labels, key_of = provider_choices()
        keys = {key_of[label] for label in labels}
        expected = {spec.key for spec in default_registry().specs()}
        assert keys == expected, "设置页下拉必须覆盖注册表里的全部 provider"

    def test_previously_missing_providers_are_offered(self):
        """P5：v2 的下拉缺 kimi / mimo / glm / qwen，用户只能手填地址。"""
        _, key_of = provider_choices()
        keys = set(key_of.values())
        for key in ("kimi", "mimo", "glm", "qwen", "deepseek", "claude", "ollama"):
            assert key in keys, f"{key} 必须能在设置页选到"

    def test_labels_are_unique(self):
        labels, _ = provider_choices()
        assert len(labels) == len(set(labels))

    def test_models_come_from_registry(self):
        for spec in default_registry().specs():
            models = models_for_provider(spec.key)
            assert models, f"{spec.key} 至少要有一个模型候选"
            if spec.default_model:
                assert spec.default_model in models

    def test_unknown_provider_gets_placeholder(self):
        assert models_for_provider("does-not-exist") == ["custom-model"]

    def test_capability_summary_mentions_key_facts(self):
        deepseek = default_registry().get("deepseek")
        text = describe_capabilities(deepseek.supports.as_dict(), deepseek.note)
        assert "深度思考" in text
        assert "余额" in text
        assert deepseek.note in text

    def test_local_provider_summary_says_no_billing(self):
        ollama = default_registry().get("ollama")
        text = describe_capabilities(ollama.supports.as_dict())
        assert "无计费" in text


# ===================================================================== 配了要生效


class TestConfiguredValuesActuallyApply:
    """设置页能填的每一项都必须真的被读到 —— 否则就是「改了个寂寞」。"""

    def test_max_tokens_and_temperature_are_read_from_config(self, monkeypatch):
        captured = {}

        def fake_send(self, adapter, spec, base, request, api_key):
            captured["max_tokens"] = request.max_tokens
            captured["temperature"] = request.temperature
            return type("R", (), {
                "text": "ok", "reasoning": "", "finish_reason": "stop",
                "usage": type("U", (), {"total_tokens": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "cached_tokens": 0,
                                        "estimated": False})(),
            })()

        monkeypatch.setattr(AIClient, "_send", fake_send)
        client = make_client(api_provider="deepseek", api_key="sk-1234567890",
                             api_base="https://api.deepseek.com",
                             model="deepseek-v4-flash",
                             max_tokens=1234, temperature=0.35)
        client.chat([{"role": "user", "content": "hi"}])

        assert captured["max_tokens"] == 1234, "max_tokens 必须来自配置而不是硬编码 4096"
        assert captured["temperature"] == 0.35, "temperature 必须来自配置而不是硬编码 0.8"

    def test_explicit_kwargs_still_win(self, monkeypatch):
        captured = {}

        def fake_send(self, adapter, spec, base, request, api_key):
            captured["max_tokens"] = request.max_tokens
            return type("R", (), {
                "text": "ok", "reasoning": "", "finish_reason": "stop",
                "usage": type("U", (), {"total_tokens": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "cached_tokens": 0,
                                        "estimated": False})(),
            })()

        monkeypatch.setattr(AIClient, "_send", fake_send)
        client = make_client(api_provider="deepseek", api_key="sk-1234567890",
                             api_base="https://api.deepseek.com",
                             model="deepseek-v4-flash", max_tokens=1234)
        client.chat([{"role": "user", "content": "hi"}], max_tokens=77)
        assert captured["max_tokens"] == 77

    def test_timeouts_are_split_read_and_connect(self):
        """P10：连接阶段不该吃 600s 的读超时，否则界面会假死到超时。"""
        client = make_client(api_provider="deepseek", api_key="sk-1234567890",
                             api_base="https://api.deepseek.com",
                             model="deepseek-v4-flash",
                             timeout=120.0, connect_timeout=3.0)
        spec = default_registry().get("deepseek")
        assert client._timeout_for(spec) == 120.0
        assert client._connect_timeout_for(spec) == 3.0
        timeout = client._httpx_timeout(spec)
        assert timeout.connect == 3.0
        assert timeout.read == 120.0

    def test_timeout_falls_back_to_spec_declaration(self):
        client = make_client(api_provider="ollama", api_base="http://localhost:11434")
        spec = default_registry().get("ollama")
        assert client._timeout_for(spec) == spec.timeout
        assert client._connect_timeout_for(spec) == spec.connect_timeout


# ===================================================================== 探测


class TestProbeConnection:
    """`probe_connection` 必须给出可照做的结论，而不是抛栈。"""

    def _patch_post(self, monkeypatch, response=None, exc=None):
        def fake_post(url, json=None, headers=None, timeout=None):
            fake_post.calls.append({"url": url, "json": json,
                                    "headers": headers or {}, "timeout": timeout})
            if exc is not None:
                raise exc
            return response

        fake_post.calls = []
        monkeypatch.setattr(ai_client_module.httpx, "post", fake_post)
        return fake_post

    def test_success_reports_model_and_url(self, monkeypatch):
        post = self._patch_post(monkeypatch, FakeResponse(200, {
            "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 2},
        }))
        client = make_client(api_provider="deepseek", api_key="sk-1234567890")

        result = client.probe_connection(
            provider="deepseek",
            api_base="https://api.deepseek.com",
            api_key="sk-from-form",
            model="deepseek-v4-flash",
        )

        assert result["ok"] is True
        assert result["url"] == "https://api.deepseek.com/chat/completions"
        assert result["sample"] == "pong"
        # 用表单里刚填的密钥，而不是已保存的配置
        assert post.calls[0]["headers"]["Authorization"] == "Bearer sk-from-form"
        # 只花 1 个 token
        assert post.calls[0]["json"]["max_tokens"] == 1

    def test_missing_key_is_reported_without_any_request(self, monkeypatch):
        post = self._patch_post(monkeypatch, FakeResponse(200, {}))
        client = make_client(api_provider="deepseek")
        result = client.probe_connection(provider="deepseek",
                                         api_base="https://api.deepseek.com",
                                         api_key="")
        assert result["ok"] is False
        assert "未填写 API Key" in result["reason"]
        assert post.calls == [], "缺少密钥时不该浪费一次请求"

    def test_local_provider_needs_no_key(self, monkeypatch):
        self._patch_post(monkeypatch, FakeResponse(200, {
            "message": {"content": "pong"}, "done": True,
        }))
        client = make_client(api_provider="ollama")
        result = client.probe_connection(provider="ollama",
                                         api_base="http://localhost:11434",
                                         api_key="", model="qwen2.5:14b")
        assert result["ok"] is True

    @pytest.mark.parametrize("status,keyword", [
        (401, "API Key 无效"),
        (403, "权限"),
        (404, "/v1"),
        (429, "频繁"),
        (500, "服务端错误"),
    ])
    def test_http_errors_are_translated(self, monkeypatch, status, keyword):
        self._patch_post(monkeypatch, FakeResponse(status, {}, text="boom"))
        client = make_client(api_provider="deepseek", api_key="sk-1234567890")
        result = client.probe_connection(provider="deepseek",
                                         api_base="https://api.deepseek.com",
                                         api_key="sk-x")
        assert result["ok"] is False
        assert result["status"] == status
        assert keyword in result["reason"], result["reason"]

    def test_network_error_is_reported_not_raised(self, monkeypatch):
        self._patch_post(monkeypatch, exc=httpx.ConnectError("dns boom"))
        client = make_client(api_provider="deepseek", api_key="sk-1234567890")
        result = client.probe_connection(provider="deepseek",
                                         api_base="https://api.deepseek.com",
                                         api_key="sk-x")
        assert result["ok"] is False
        assert "无法连接" in result["reason"]
        assert "ConnectError" in result["reason"]

    def test_unparsable_body_is_reported(self, monkeypatch):
        self._patch_post(monkeypatch, FakeResponse(200, {"unexpected": "shape"}))
        client = make_client(api_provider="deepseek", api_key="sk-1234567890")
        result = client.probe_connection(provider="deepseek",
                                         api_base="https://api.deepseek.com",
                                         api_key="sk-x")
        # OpenAI 兼容解析器遇到空 choices 会显式失败 —— 探测要把这个失败说清楚
        assert result["ok"] is False
        assert result["reason"]

    def test_plaintext_http_is_rejected_before_sending(self, monkeypatch):
        post = self._patch_post(monkeypatch, FakeResponse(200, {}))
        client = make_client(api_provider="deepseek", api_key="sk-1234567890")
        result = client.probe_connection(provider="deepseek",
                                         api_base="http://api.deepseek.com",
                                         api_key="sk-x")
        assert result["ok"] is False
        assert "明文 HTTP" in result["reason"]
        assert post.calls == []


# ===================================================================== 源码守卫


class TestSettingsSourceGuards:
    """P5 / P11 的回归守卫（只扫真实代码，跳过注释与文档字符串）。"""

    def test_no_second_provider_list_in_settings(self):
        src = code_only("app/lifecycle_ui.py")
        assert "MODEL_PRESETS" not in src, "模型预设清单已收敛到注册表"
        assert "API_PRESETS" not in src, "API 地址预设清单已收敛到注册表"

    def test_settings_delegates_ai_tab(self):
        src = code_only("app/lifecycle_ui.py")
        assert "_build_ai_settings_tab" in src

    def test_single_temperature_control(self):
        """P11：旧实现有两个温度输入框绑到同一个变量，改上面那个读下面那个。"""
        src = code_only("app/ai_settings_ui.py")
        assert src.count("temperature") >= 1
        assert src.count("from_=0, to=2") == 1, "温度控件只应存在一个"

    def test_ai_settings_has_no_hardcoded_provider_branch(self):
        """能力判断必须走 spec.supports，而不是 `if provider == "..."`。"""
        src = code_only("app/ai_settings_ui.py")
        for name in ("claude", "deepseek", "openai", "ollama", "kimi", "mimo"):
            assert f'== "{name}"' not in src, f"不应按服务商名硬编码分支：{name}"
