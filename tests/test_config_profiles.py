"""
v3 多 Profile 配置（P2-4）单元测试

覆盖三件事：
1. **迁移**：v2 的扁平配置如何升级到 `ai.profiles`，且幂等、可回滚、不泄露明文；
2. **兼容**：活跃 Profile 必须镜像到顶层扁平键，v2 的 `config.get("model")` 读法不变；
3. **隔离**：不同 Profile 的连接参数与密钥互不串台，密钥永不进入 Profile。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.config import (
    AI_PROFILE_FIELDS,
    AppConfig,
)
from app.secure_config import SecureConfig

# --------------------------------------------------------------------- 夹具


@pytest.fixture
def home(tmp_path, monkeypatch):
    """把 `Path.home()` 指到临时目录，避免碰到开发机上的真实配置。"""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def config_dir(home):
    return home / ".ai_novel_writer"


def _raw(config_dir) -> dict:
    return json.loads((config_dir / "config.json").read_text(encoding="utf-8"))


def _raw_text(config_dir) -> str:
    return (config_dir / "config.json").read_text(encoding="utf-8")


# ===================================================================== 迁移


class TestLegacyMigration:
    """v2 扁平配置 → v3 多 Profile。"""

    def test_legacy_flat_keys_become_default_profile(self, config_dir, home):
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "api_provider": "deepseek",
                    "api_base": "https://api.deepseek.com",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.5,
                    "theme": "dark",
                }
            ),
            encoding="utf-8",
        )

        cfg = AppConfig()

        assert cfg.active_profile == "default"
        assert cfg.profile_names() == ["default"]
        default = cfg.profiles()["default"]
        assert default["api_provider"] == "deepseek"
        assert default["model"] == "deepseek-v4-flash"
        assert default["temperature"] == 0.5
        # 缺项用默认值补齐，而不是留空
        assert default["thinking_enabled"] is True
        assert default["timeout"] == 600.0

    def test_flat_keys_are_kept_for_rollback(self, config_dir, home):
        """顶层扁平键不得删除 —— 换回旧版本程序也还能跑。"""
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "api_provider": "openai",
                    "model": "gpt-4o",
                }
            ),
            encoding="utf-8",
        )

        cfg = AppConfig()
        cfg.set("theme", "dark")  # 触发一次落盘

        data = _raw(config_dir)
        assert data["api_provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["theme"] == "dark"
        assert data["ai"]["schema_version"] == 2

    def test_migration_writes_one_backup_before_first_save(self, config_dir, home):
        config_dir.mkdir(parents=True, exist_ok=True)
        original = {"api_provider": "openai", "custom_key": "custom_value"}
        (config_dir / "config.json").write_text(json.dumps(original), encoding="utf-8")

        cfg = AppConfig()
        # 构造阶段保持只读：不应产生任何文件
        assert list(config_dir.glob("config.pre-v3-profiles-*.json")) == []

        cfg.set("theme", "dark")

        backups = list(config_dir.glob("config.pre-v3-profiles-*.json"))
        assert len(backups) == 1
        # 备份必须是**迁移前**的内容
        assert json.loads(backups[0].read_text(encoding="utf-8")) == original

        # 再次保存不重复留档
        cfg.set("theme", "light")
        assert len(list(config_dir.glob("config.pre-v3-profiles-*.json"))) == 1

    def test_migration_is_idempotent(self, config_dir, home):
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"api_provider": "ollama", "model": "qwen2.5:14b"}),
            encoding="utf-8",
        )

        first = AppConfig()
        first.set("theme", "dark")
        snapshot = _raw(config_dir)

        second = AppConfig()
        assert second.profiles() == first.profiles()
        # 结构已是最新 → 不再需要留档，也不该重写文件
        assert second._migration_backup_pending is False
        assert second.ensure_profiles_persisted() is False
        assert _raw(config_dir) == snapshot

    def test_partial_user_written_section_is_preserved(self, config_dir, home):
        """手写/半成品的 `ai` 段落要被补全，而不是被重建覆盖。"""
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"ai": {"profiles": {"manual": {"api_provider": "groq", "model": "llama-3.3-70b-versatile"}}}}),
            encoding="utf-8",
        )

        cfg = AppConfig()

        assert "manual" in cfg.profile_names()
        manual = cfg.profiles()["manual"]
        assert manual["api_provider"] == "groq"
        assert manual["model"] == "llama-3.3-70b-versatile"
        # 缺失字段被补齐为自洽值
        assert set(AI_PROFILE_FIELDS) <= set(manual)

    def test_garbage_on_disk_does_not_block_startup(self, config_dir, home):
        """磁盘上的历史脏值要降级，不能让程序打不开。"""
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "api_provider": "deepseek",
                    "temperature": "0.8",  # 字符串数字（旧版本可能这么写）
                    "timeout": None,  # 空值
                    "max_retries": 999,  # 超范围
                    "thinking_enabled": "yes",  # 宽松布尔
                }
            ),
            encoding="utf-8",
        )

        cfg = AppConfig()
        default = cfg.profiles()["default"]
        assert default["temperature"] == 0.8
        assert default["timeout"] == 600.0  # 非法 → 默认值
        assert default["max_retries"] == 3  # 超范围 → 默认值
        assert default["thinking_enabled"] is True


# ===================================================================== 兼容


class TestFlatKeyCompatibility:
    """活跃 Profile 必须镜像到顶层扁平键，v2 调用点零改动。"""

    def test_default_profile_visible_through_flat_get(self, home):
        cfg = AppConfig()
        assert cfg.get("model") == "qwen2.5:14b"
        assert cfg.get("api_provider") == "ollama"
        assert cfg.get("timeout") == 600.0

    def test_set_mirrors_into_flat_key(self, config_dir, home):
        cfg = AppConfig()
        cfg.set("model", "gpt-4o")

        assert cfg.get("model") == "gpt-4o"
        assert cfg.config["model"] == "gpt-4o"  # 兼容直接读字典的代码
        assert _raw(config_dir)["model"] == "gpt-4o"

    def test_switch_profile_moves_flat_keys(self, config_dir, home):
        cfg = AppConfig()
        cfg.set("api_provider", "deepseek")
        cfg.set("model", "deepseek-v4-flash")

        cfg.create_profile("local", activate=False)
        cfg.switch_profile("local")
        # 新 Profile 以默认值起手
        assert cfg.get("api_provider") == "ollama"
        assert cfg.get("model") == "qwen2.5:14b"

        cfg.switch_profile("default")
        assert cfg.get("api_provider") == "deepseek"
        assert cfg.get("model") == "deepseek-v4-flash"

    def test_profiles_are_isolated(self, config_dir, home):
        cfg = AppConfig()
        cfg.set("model", "deepseek-v4-flash")
        cfg.create_profile("work", activate=True)
        cfg.set("api_provider", "openai")
        cfg.set("model", "gpt-4o")

        cfg.switch_profile("default")
        assert cfg.get("model") == "deepseek-v4-flash"
        cfg.switch_profile("work")
        assert cfg.get("model") == "gpt-4o"
        assert cfg.get("api_provider") == "openai"


# ===================================================================== 密钥


class TestProfileSecrets:
    """密钥托管：不进 Profile、不明文落盘、不跨 Profile 串台。"""

    def test_profiles_never_contain_api_key(self, config_dir, home):
        cfg = AppConfig()
        cfg.set("api_key", "sk-default-secret")
        cfg.create_profile("work", activate=True)
        cfg.set("api_key", "sk-work-secret")

        data = _raw(config_dir)
        for name, prof in data["ai"]["profiles"].items():
            assert "api_key" not in prof, f"Profile {name} 里不允许出现 api_key"

        text = _raw_text(config_dir)
        assert "sk-default-secret" not in text
        assert "sk-work-secret" not in text

    def test_keys_are_encrypted_and_round_trip(self, config_dir, home):
        cfg = AppConfig()
        cfg.set("api_key", "sk-default-secret")
        cfg.create_profile("work", activate=True)
        cfg.set("api_key", "sk-work-secret")

        data = _raw(config_dir)
        assert data["api_key"].startswith("gAAAAA")
        assert data["ai_keys"]["work"].startswith("gAAAAA")

        reloaded = AppConfig()
        assert reloaded.active_profile == "work"
        assert reloaded.get("api_key") == "sk-work-secret"
        reloaded.switch_profile("default")
        assert reloaded.get("api_key") == "sk-default-secret"

    def test_profile_without_key_does_not_borrow_others(self, config_dir, home):
        """没有独立密钥的 Profile 必须返回空，而不是偷偷用别的 Profile 的密钥。

        否则用户会「切了 Profile 但钱花在老账号上」，且极难排查。
        """
        cfg = AppConfig()
        cfg.set("api_key", "sk-default-secret")
        cfg.create_profile("work", activate=True)

        assert cfg.get("api_key") == ""
        assert cfg.profile_has_key("work") is False
        assert cfg.profile_has_key("default") is True

    def test_delete_profile_drops_its_key(self, config_dir, home):
        cfg = AppConfig()
        cfg.create_profile("work", activate=True)
        cfg.set("api_key", "sk-work-secret")
        cfg.create_profile("temp", activate=True)

        cfg.delete_profile("work")
        assert "work" not in cfg.profile_names()
        assert "work" not in _raw(config_dir).get("ai_keys", {})
        assert SecureConfig(config_dir).get_ai_key("work") == ""

    def test_rename_profile_moves_its_key(self, config_dir, home):
        cfg = AppConfig()
        cfg.create_profile("work", activate=True)
        cfg.set("api_key", "sk-work-secret")

        cfg.rename_profile("work", "office")
        assert cfg.active_profile == "office"
        assert cfg.get("api_key") == "sk-work-secret"


# ===================================================================== 守卫


class TestProfileGuards:
    def test_cannot_delete_active_profile(self, home):
        cfg = AppConfig()
        cfg.create_profile("work", activate=True)
        with pytest.raises(ValueError, match="正在使用"):
            cfg.delete_profile("work")

    def test_cannot_delete_last_profile(self, home):
        cfg = AppConfig()
        with pytest.raises(ValueError, match="至少要保留"):
            cfg.delete_profile("default")

    def test_duplicate_name_is_rejected(self, home):
        cfg = AppConfig()
        cfg.create_profile("work")
        with pytest.raises(ValueError, match="已存在"):
            cfg.create_profile("work")

    def test_switch_to_unknown_profile_is_rejected(self, home):
        cfg = AppConfig()
        with pytest.raises(ValueError, match="不存在"):
            cfg.switch_profile("nope")

    @pytest.mark.parametrize("name", ["", "  ", "a/b", "a\\b", "a\nb", "x" * 41])
    def test_invalid_profile_names_are_rejected(self, home, name):
        cfg = AppConfig()
        with pytest.raises(ValueError):
            cfg.create_profile(name)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("temperature", 5.0),
            ("temperature", "warm"),
            ("max_tokens", 0),
            ("max_retries", -1),
            ("timeout", 1),
            ("reasoning_effort", ""),
        ],
    )
    def test_invalid_user_input_raises(self, home, field, value):
        """界面输入走快速失败，而不是静默夹到边界值。"""
        cfg = AppConfig()
        with pytest.raises(ValueError):
            cfg.set(field, value)

    def test_valid_coercions(self, home):
        cfg = AppConfig()
        cfg.set("temperature", "0.3")
        cfg.set("max_retries", 2.9)
        cfg.set("thinking_enabled", "false")
        assert cfg.get("temperature") == 0.3
        assert cfg.get("max_retries") == 2
        assert cfg.get("thinking_enabled") is False


# ===================================================================== 共写文件


class TestSharedConfigFileSafety:
    """AppConfig 与 SecureConfig 共写 `config.json` 的相互覆盖问题。"""

    def test_saving_api_key_does_not_revert_other_settings(self, config_dir, home):
        """回归：旧实现在改 API Key 时会把同会话改过的设置退回旧值。"""
        cfg = AppConfig()
        cfg.set("theme", "dark")
        cfg.set("model", "gpt-4o")

        cfg.set("api_key", "sk-secret")  # 这一路径会触发 SecureConfig 落盘

        data = _raw(config_dir)
        assert data["theme"] == "dark", "改 API Key 不得把主题退回旧值"
        assert data["ai"]["profiles"]["default"]["model"] == "gpt-4o"

    def test_appconfig_save_keeps_profile_keys(self, config_dir, home):
        """反向：AppConfig 落盘不得抹掉 SecureConfig 刚存的 Profile 密钥。"""
        cfg = AppConfig()
        cfg.create_profile("work", activate=True)
        cfg.set("api_key", "sk-work-secret")
        cfg.set("theme", "dark")  # AppConfig 全量落盘

        assert _raw(config_dir)["ai_keys"]["work"].startswith("gAAAAA")
        reloaded = AppConfig()
        assert reloaded.get("api_key") == "sk-work-secret"

    def test_secure_config_keeps_unknown_sections(self, config_dir, home):
        """SecureConfig 只回写自己负责的键，别的段落要原样保留。"""
        cfg = AppConfig()
        cfg.set("theme", "dark")

        sc = SecureConfig(config_dir)
        sc.set("api_key", "sk-secret")

        data = _raw(config_dir)
        assert data["theme"] == "dark"
        assert "ai" in data

    def test_secure_config_refuses_write_after_load_failure(self, config_dir, home):
        """读盘失败时必须拒绝写入，而不是用残缺内存覆盖唯一一份数据。"""
        config_dir.mkdir(parents=True, exist_ok=True)
        corrupt = config_dir / "config.json"
        corrupt.write_text("{不是 JSON", encoding="utf-8")

        sc = SecureConfig(config_dir)
        assert sc._load_failed is True
        assert sc.save() is False
        # 原文件必须原地不动（同时另存了一份 corrupt 留档）
        assert corrupt.read_text(encoding="utf-8") == "{不是 JSON"

    def test_no_plaintext_anywhere_in_legacy_file(self, config_dir, home):
        """老文件里的明文密钥不得被迁移进任何新结构。"""
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "api_provider": "openai",
                    "api_key": "sk-plaintext-legacy",
                    "model": "gpt-4o",
                }
            ),
            encoding="utf-8",
        )

        cfg = AppConfig()
        assert cfg.get("api_key") == ""

        cfg.set("theme", "dark")  # 触发落盘
        data = _raw(config_dir)
        assert "sk-plaintext-legacy" not in _raw_text(config_dir)
        assert data["api_key"] == ""
        for prof in data["ai"]["profiles"].values():
            assert "api_key" not in prof


# ===================================================================== 辅助


class TestMaskAndSnapshot:
    def test_api_key_masking(self):
        assert AppConfig.mask_api_key("") == ""
        assert AppConfig.mask_api_key("abc") == "***"
        masked = AppConfig.mask_api_key("sk-1234567890abcdef")
        assert masked.startswith("sk-1") and masked.endswith("cdef")
        assert "234567890abc" not in masked

    def test_profile_snapshot(self, home):
        cfg = AppConfig()
        cfg.set("model", "gpt-4o")
        snap = cfg.profile_snapshot("default")
        assert snap["name"] == "default"
        assert snap["is_active"] is True
        assert snap["model"] == "gpt-4o"
        assert snap["has_api_key"] is False
