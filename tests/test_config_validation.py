"""`app/config.py` 的校验与读取降级（第 2 档：静默失效）。

## 为什么这个模块的值出问题，用户查不出来

配置错**不会报错**，只会"改了没反应"：

| 故障 | 用户看到 |
|---|---|
| 布尔串写错（`"ture"`） | 思考开关拧了没动，模型一直不思考 |
| 数值越界没拦 | 温度填 3 → 请求被服务端拒；或永远只出 1 个 token |
| 扁平键没镜像 | 旧代码读顶层键拿到旧值，新旧两套读法打架 |
| 敏感字段没走加密层 | 密钥明文躺在 config.json 里 |

所以这里的判据都是"**非法输入必须当场失败**"，而不是"能存进去"。
"""

from __future__ import annotations

import json

import pytest

from app.config import (
    _AI_PROFILE_FIELD_SET,
    AI_PROFILE_DEFAULTS,
    AI_PROFILE_FIELDS,
    PROFILE_FIELD_RANGES,
    PROFILES_SECTION,
    AppConfig,
    _coerce_profile_field,
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def cfg(home):
    return AppConfig()


class TestCoerceThinkingEnabled:
    """思考开关是布尔值，但用户/配置文件会给出各种写法。"""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_passes_through(self, value):
        assert _coerce_profile_field("thinking_enabled", value) is value

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1", True),
            ("true", True),
            ("TRUE", True),
            (" yes ", True),
            ("on", True),
            ("启用", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("off", False),
            ("禁用", False),
            ("", False),
        ],
    )
    def test_string_forms(self, value, expected):
        assert _coerce_profile_field("thinking_enabled", value) is expected

    @pytest.mark.parametrize(("value", "expected"), [(1, True), (0, False)])
    def test_int_forms(self, value, expected):
        """`1`/`0` 来自 JSON 或 Tk 的 IntVar —— 必须当布尔用。"""
        assert _coerce_profile_field("thinking_enabled", value) is expected

    @pytest.mark.parametrize("value", ["ture", "maybe", 2.5, [], {}])
    def test_invalid_raises(self, value):
        """拼错的布尔串必须当场失败 —— 静默当成 False 会让"开了却不思考"无法排查。"""
        with pytest.raises(ValueError):
            _coerce_profile_field("thinking_enabled", value)


class TestCoerceStringFields:
    @pytest.mark.parametrize("key", ["balance_url", "balance_total_path", "balance_currency_path"])
    def test_balance_none_becomes_empty(self, key):
        assert _coerce_profile_field(key, None) == ""

    @pytest.mark.parametrize("key", ["balance_url", "balance_total_path", "balance_currency_path"])
    def test_balance_rejects_non_string(self, key):
        with pytest.raises(ValueError):
            _coerce_profile_field(key, 123)

    def test_balance_is_stripped(self):
        assert _coerce_profile_field("balance_url", "  https://x  ") == "https://x"

    def test_reasoning_effort_normalized(self):
        assert _coerce_profile_field("reasoning_effort", " HIGH ") == "high"

    @pytest.mark.parametrize("value", ["", "   ", None, 3])
    def test_reasoning_effort_rejects_empty(self, value):
        with pytest.raises(ValueError):
            _coerce_profile_field("reasoning_effort", value)

    def test_model_none_becomes_empty(self):
        assert _coerce_profile_field("model", None) == ""

    def test_model_rejects_non_string(self):
        with pytest.raises(ValueError):
            _coerce_profile_field("model", 42)

    def test_api_provider_none_falls_back_to_default(self):
        """provider 为空时不能留空串 —— 空 provider 会让请求无处可发。"""
        assert _coerce_profile_field("api_provider", None) == AI_PROFILE_DEFAULTS["api_provider"]

    def test_api_provider_empty_falls_back_to_default(self):
        assert _coerce_profile_field("api_provider", "   ") == AI_PROFILE_DEFAULTS["api_provider"]

    def test_api_provider_rejects_non_string(self):
        with pytest.raises(ValueError):
            _coerce_profile_field("api_provider", ["deepseek"])


class TestCoerceNumericFields:
    def test_int_fields_are_truncated(self):
        assert _coerce_profile_field("max_tokens", "4096.9") == 4096
        assert isinstance(_coerce_profile_field("max_tokens", "4096.9"), int)

    def test_float_fields_stay_float(self):
        assert _coerce_profile_field("temperature", "0.7") == 0.7

    @pytest.mark.parametrize("value", [True, False, None])
    def test_bool_and_none_rejected(self, value):
        """`True` 会被 `float()` 悄悄变成 1.0 —— 必须显式拦掉。"""
        with pytest.raises(ValueError):
            _coerce_profile_field("temperature", value)

    def test_non_numeric_rejected(self):
        with pytest.raises(ValueError):
            _coerce_profile_field("temperature", "热一点")

    @pytest.mark.parametrize("key", list(PROFILE_FIELD_RANGES))
    def test_range_enforced(self, key):
        low, high = PROFILE_FIELD_RANGES[key]
        with pytest.raises(ValueError):
            _coerce_profile_field(key, high + 1)
        with pytest.raises(ValueError):
            _coerce_profile_field(key, low - 1)


class TestTypedGetters:
    """`get_float/int/bool` 是"配置里存了脏值也别让界面崩"的兜底。"""

    def test_float_falls_back(self, cfg):
        cfg.config["x"] = "不是数字"
        assert cfg.get_float("x", 1.5) == 1.5
        cfg.config["x"] = "2.5"
        assert cfg.get_float("x") == 2.5

    def test_int_falls_back(self, cfg):
        cfg.config["y"] = "abc"
        assert cfg.get_int("y", 7) == 7
        cfg.config["y"] = "12.9"
        assert cfg.get_int("y") == 12

    @pytest.mark.parametrize(("value", "expected"), [(True, True), (0, False), (2, True), (0.0, False)])
    def test_bool_accepts_native_types(self, cfg, value, expected):
        cfg.config["z"] = value
        assert cfg.get_bool("z") is expected

    @pytest.mark.parametrize(("value", "expected"), [("true", True), (" YES ", True), ("on", True), ("1", True)])
    def test_bool_accepts_true_strings(self, cfg, value, expected):
        cfg.config["z"] = value
        assert cfg.get_bool("z") is expected

    @pytest.mark.parametrize("value", ["false", "0", "no", "随便什么"])
    def test_bool_rejects_unrecognized(self, cfg, value):
        cfg.config["z"] = value
        assert cfg.get_bool("z", default=False) is False

    def test_bool_returns_default_for_objects(self, cfg):
        """`MagicMock` 之类会被 `bool()` 判真 —— 必须回落到默认值。"""

        class Weird:
            pass

        cfg.config["z"] = Weird()
        assert cfg.get_bool("z", default=False) is False


class TestProfileReadPaths:
    def test_profile_value_wins_over_flat_key(self, cfg):
        """Profile 值优先于顶层扁平键。

        ⚠️ 顺带记录一个事实：`_active_profile_dict()` 会给**全部** 14 个字段
        `setdefault` 默认值，所以 `get()` 里"prof 没有就回落到顶层键"那一支
        （config.py 的 `if key in self.config`）实际上不可达 ——
        `_AI_PROFILE_FIELD_SET` 与 `AI_PROFILE_DEFAULTS` 的键集完全相同。
        这里断言的是**用户真正感受到的优先级**：改了 Profile 就生效。
        """
        cfg.set("temperature", 0.42)
        cfg.config["temperature"] = 0.99  # 模拟顶层的陈旧值

        assert cfg.get("temperature") == 0.42, "顶层陈旧值盖住了 Profile 里的新值"

    def test_profile_field_falls_back_to_defaults(self, cfg):
        cfg.config.pop("temperature", None)
        cfg._active_profile_dict().pop("temperature", None)

        assert cfg.get("temperature") == AI_PROFILE_DEFAULTS["temperature"]

    def test_unknown_key_returns_default(self, cfg):
        assert cfg.get("完全不存在的键", "兜底") == "兜底"


class TestSensitiveFields:
    def test_sensitive_field_goes_through_secure_layer(self, cfg):
        """敏感字段（密钥类）必须交给加密层，而不是写进明文 config。"""

        class FakeSecure:
            def __init__(self):
                self.store = {}

            def get(self, key):
                return self.store.get(key)

            def set(self, key, value):
                self.store[key] = value

            def _encrypt(self, value):
                # 落盘前会调它加密；替身直接返回原值（不影响本用例的判据）
                return value

        fake = FakeSecure()
        cfg._secure_config = fake

        cfg.set("secret_key", "p@ss")

        assert fake.store["secret_key"] == "p@ss"

    def test_sensitive_field_without_secure_layer_still_readable(self, cfg):
        """没有加密层时（例如首次启动）也要能读回刚写的值。"""
        cfg._secure_config = None

        cfg.set("secret_key", "p@ss")

        assert cfg.get("secret_key") == "p@ss"


class TestMigrationPersist:
    def test_noop_when_nothing_pending(self, cfg):
        cfg._migration_backup_pending = False

        assert cfg.ensure_profiles_persisted() is False

    def test_writes_when_pending(self, cfg, home):
        cfg._migration_backup_pending = True

        assert cfg.ensure_profiles_persisted() is True
        raw = json.loads((home / ".ai_novel_writer" / "config.json").read_text(encoding="utf-8"))
        assert raw, "落盘文件是空的"
        assert cfg._migration_backup_pending is False, "落盘后没清标记，启动时会反复备份"


class TestProfileStructureValidation:
    """`_profiles_are_current` 是"该不该重建多档案结构"的判据。

    ❗ 它收的是 **`ai` 段的 section**，不是整个 config —— 传错会让判据恒为 False
    （本次就踩了：传整个 config 时 `section.get("profiles")` 拿不到，直接判不合格，
    于是每次启动都重建一遍结构）。

    判错的后果两个方向都难受：
    - 该重建却没重建 ⇒ 老配置一直补默认值，用户改动被默认值盖住；
    - 不该重建却重建 ⇒ 用户在旧结构里存的东西被冲掉。
    """

    def test_section_is_normalized(self, cfg):
        """构造后 `ai` 段就应处于当前 schema 且字段齐全。

        （实测构造时就已归一化 —— 早先以为它是"首次访问才建"是错的。）
        """
        from app.config import PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is True

    def test_missing_default_profile(self, cfg):
        from app.config import DEFAULT_PROFILE_NAME, PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)
        cfg.config[PROFILES_SECTION]["profiles"].pop(DEFAULT_PROFILE_NAME, None)

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is False

    def test_active_profile_not_in_profiles(self, cfg):
        from app.config import PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)
        cfg.config[PROFILES_SECTION]["active_profile"] = "压根不存在"

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is False

    def test_profile_not_dict(self, cfg):
        from app.config import DEFAULT_PROFILE_NAME, PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)
        cfg.config[PROFILES_SECTION]["profiles"][DEFAULT_PROFILE_NAME] = "字符串"

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is False

    def test_profile_missing_fields(self, cfg):
        from app.config import DEFAULT_PROFILE_NAME, PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)
        cfg.config[PROFILES_SECTION]["profiles"][DEFAULT_PROFILE_NAME] = {"model": "x"}

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is False

    def test_wrong_schema_version(self, cfg):
        from app.config import PROFILES_SECTION

        cfg._normalize_profiles(cfg.config)
        cfg.config[PROFILES_SECTION]["schema_version"] = 0

        assert cfg._profiles_are_current(cfg.config[PROFILES_SECTION]) is False

    def test_normalize_is_idempotent(self, cfg):
        """已经合格的结构再归一化应返回 False（否则每次启动都写一次盘）。"""
        cfg._normalize_profiles(cfg.config)

        assert cfg._normalize_profiles(cfg.config) is False


class TestCreateProfileEdges:
    def test_duplicate_name_rejected(self, cfg):
        cfg.create_profile("work")

        with pytest.raises(ValueError):
            cfg.create_profile("work")

    def test_copy_from_missing_source(self, cfg):
        with pytest.raises(ValueError):
            cfg.create_profile("copy", copy_from="不存在")

    def test_copy_from_copies_values(self, cfg):
        cfg.create_profile("工作")
        cfg.switch_profile("工作")
        cfg.set("temperature", 0.3)

        cfg.create_profile("工作副本", copy_from="工作")

        cfg.switch_profile("工作副本")
        assert cfg.get("temperature") == 0.3


class TestProfileFieldInvariant:
    """删除"回落到扁平键"之后必须成立的前提。

    2026-11-28 删掉了 `get()` 里两行不可达代码（详见 `config.py` 模块文档）：
    `if key in prof` 恒为真，所以后面的"回落到顶层扁平键"永远走不到。

    **删除的安全前提是**：任何 Profile 字典都含全部 14 个字段。
    一旦有人改坏 `_active_profile_dict()` 的 setdefault 循环，
    `get()` 会静默返回默认值而不是用户设的值 —— 那种 bug 极难查。
    这组用例就是把这个前提钉住。
    """

    def test_field_sets_are_derived_from_the_same_tuple(self):
        """两个集合同源派生 ⇒ 结构上不可能出现"在字段集里但无默认值"的键。"""
        assert set(_AI_PROFILE_FIELD_SET) == set(AI_PROFILE_FIELDS)
        assert set(AI_PROFILE_DEFAULTS) == set(AI_PROFILE_FIELDS)

    @pytest.mark.parametrize(
        ("label", "raw"),
        [
            ("全新", {}),
            ("v2 扁平键", {"temperature": 0.42, "model": "m"}),
            ("段非 dict", {PROFILES_SECTION: "字符串"}),
            ("profiles 为空", {PROFILES_SECTION: {"profiles": {}}}),
            ("default 被删", {PROFILES_SECTION: {"profiles": {"work": {"model": "x"}}}}),
            ("default 非 dict", {PROFILES_SECTION: {"profiles": {"default": "字符串"}}}),
            ("字段缺失", {PROFILES_SECTION: {"profiles": {"default": {"model": "x"}}}}),
            (
                "active 指向不存在",
                {PROFILES_SECTION: {"profiles": {"default": {"model": "x"}}, "active_profile": "幽灵"}},
            ),
        ],
    )
    def test_every_profile_carries_all_fields(self, cfg, label, raw):
        """8 种畸形结构下都必须补齐全部字段 —— 否则 `get()` 的简化不再安全。"""
        cfg.config = raw

        prof = cfg._active_profile_dict()

        missing = set(AI_PROFILE_DEFAULTS) - set(prof)
        assert not missing, f"{label} 下缺字段：{sorted(missing)}"

    def test_stale_flat_key_never_leaks_through(self, cfg):
        """扁平键里的陈旧值不能盖住 Profile 里的新值（删除前也不会，删除后更不能）。"""
        cfg.set("temperature", 0.42)
        cfg.config["temperature"] = 0.99

        assert cfg.get("temperature") == 0.42
