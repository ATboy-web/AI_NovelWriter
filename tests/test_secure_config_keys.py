"""`secure_config` 的多档案密钥与容错（第 4 档：密钥）。

## 为什么这些分支值得单独测

| 分支 | 坏了会怎样 |
|---|---|
| 解不开的密文在 `save()` 时**原样写回** | 一次启动失败把用户的所有密钥洗成空 |
| 根节点不是对象 ⇒ 留档 + 用默认配置 | 配置被静默清空，且没有证据可查 |
| 密钥轮换时保留旧密钥文件 | 账户恢复后旧密文再也解不开 |
| 改名/删除 Profile 时同步搬/删密钥 | 密钥留在旧名下：删了档案，密钥还在盘上 |

最后一条是"看起来删干净了、其实没删"的典型 —— 用户以为密钥已经没了。
"""

from __future__ import annotations

import json

import pytest

from app.secure_config import AI_KEYS_FIELD, DEFAULT_PROFILE_NAME, SecureConfig


@pytest.fixture
def cfg_dir(tmp_path):
    return tmp_path / ".ai_novel_writer"


@pytest.fixture
def sc(cfg_dir):
    return SecureConfig(cfg_dir)


class TestEmptyValues:
    def test_encrypt_empty_returns_empty(self, sc):
        assert sc._encrypt("") == ""

    def test_decrypt_empty_returns_empty(self, sc):
        assert sc._decrypt("") == ""

    def test_decrypt_rejects_plaintext(self, sc):
        """明文不再被接受（移除降级路径）—— 否则敏感数据会以明文留在磁盘上。"""
        assert sc._decrypt("sk-plain-text") == ""

    def test_roundtrip(self, sc):
        cipher = sc._encrypt("sk-123456")

        assert cipher.startswith("gAAAAA")
        assert sc._decrypt(cipher) == "sk-123456"


class TestCorruptConfig:
    def test_root_not_dict_is_archived_and_defaulted(self, sc, cfg_dir):
        """根节点是数组 ⇒ 留档 + 用默认配置 + 置 load_failed（拒绝用默认值覆盖磁盘）。"""
        sc.config_file.parent.mkdir(parents=True, exist_ok=True)
        sc.config_file.write_text("[]", encoding="utf-8")

        config = sc._load()

        assert isinstance(config, dict)
        assert sc._load_failed is True, "没有置 load_failed，下次保存会洗掉磁盘内容"
        assert list(cfg_dir.glob("*.corrupt-*")), "损坏配置没有被留档"

    def test_undecryptable_field_is_preserved_on_save(self, sc, cfg_dir):
        """解不开的密文必须原样写回，不能被空值覆盖。"""
        sc.config_file.parent.mkdir(parents=True, exist_ok=True)
        bogus = "gAAAAA这不是真密文"
        sc.config_file.write_text(json.dumps({"api_key": bogus}), encoding="utf-8")

        sc._load()
        sc.save()

        raw = json.loads(sc.config_file.read_text(encoding="utf-8"))
        assert raw["api_key"] == bogus, "解不开的密文被覆盖成空值（密钥永久丢失）"


class TestAiKeyProfiles:
    def test_delete_default_clears_api_key(self, sc):
        sc.set("api_key", "sk-default")

        sc.delete_ai_key(DEFAULT_PROFILE_NAME)

        assert sc.get_ai_key(DEFAULT_PROFILE_NAME) == ""

    def test_delete_unknown_profile_is_noop(self, sc):
        sc.set_ai_key("work", "sk-work")

        sc.delete_ai_key("根本不存在")

        assert sc.get_ai_key("work") == "sk-work"

    def test_delete_removes_key(self, sc):
        sc.set_ai_key("work", "sk-work")

        sc.delete_ai_key("work")

        assert sc.get_ai_key("work") == ""
        assert "work" not in sc.ai_key_profiles()

    def test_rename_to_same_name_is_noop(self, sc):
        sc.set_ai_key("work", "sk-work")

        sc.rename_ai_key("work", "work")

        assert sc.get_ai_key("work") == "sk-work"

    def test_rename_empty_target_falls_back_to_default(self, sc):
        """空目标名按**默认档案**处理（`str(new or DEFAULT_PROFILE_NAME)`）。

        这条不是"什么都不做"—— 它会把密钥搬到默认档案下、并从旧名下移除。
        之所以值得钉住：传空串时调用方多半以为"无效输入会被忽略"，
        实际结果是密钥换了位置。
        """
        sc.set_ai_key("work", "sk-work")

        sc.rename_ai_key("work", "")

        assert sc.get_ai_key(DEFAULT_PROFILE_NAME) == "sk-work"
        assert sc.get_ai_key("work") == ""

    def test_rename_default_moves_to_target(self, sc):
        """默认 Profile 改名：密钥搬到新名字下，默认置空。"""
        sc.set_ai_key(DEFAULT_PROFILE_NAME, "sk-default")

        sc.rename_ai_key(DEFAULT_PROFILE_NAME, "新名字")

        assert sc.get_ai_key("新名字") == "sk-default"
        assert sc.get_ai_key(DEFAULT_PROFILE_NAME) == ""

    def test_rename_unknown_is_noop(self, sc):
        sc.set_ai_key("work", "sk-work")

        sc.rename_ai_key("不存在", "新名字")

        assert sc.get_ai_key("work") == "sk-work"

    def test_rename_moves_undecryptable_ciphertext(self, sc):
        """解不开的密文也要跟着改名走 —— 否则改名后既解不开也删不掉。"""
        sc._undecryptable_ai_keys["旧名"] = "gAAAAA坏密文"
        sc.config[AI_KEYS_FIELD] = {"旧名": "gAAAAA坏密文"}

        sc.rename_ai_key("旧名", "新名")

        assert "新名" in sc._undecryptable_ai_keys
        assert "旧名" not in sc._undecryptable_ai_keys

    def test_ai_key_profiles_lists_only_non_empty(self, sc):
        sc.set_ai_key("work", "sk-work")
        sc.set_ai_key("empty", "")

        profiles = sc.ai_key_profiles()

        assert "work" in profiles
        assert "empty" not in profiles, "空密钥的档案被列成了有密钥"

    def test_ai_key_profiles_without_container(self, sc):
        sc.config.pop(AI_KEYS_FIELD, None)

        assert sc.ai_key_profiles() == []

    def test_has_ai_key(self, sc):
        assert sc.has_ai_key(DEFAULT_PROFILE_NAME) is False
        sc.set_ai_key(DEFAULT_PROFILE_NAME, "sk-x")
        assert sc.has_ai_key(DEFAULT_PROFILE_NAME) is True


class TestKeyProtectionFallbacks:
    def test_chmod_failure_is_ignored(self, sc, monkeypatch):
        """`chmod` 在 Windows/网络盘上可能失败 —— 只记日志，不阻断密钥落盘。"""
        import app.secure_config as mod

        def boom(*_a, **_kw):
            raise OSError("不支持")

        monkeypatch.setattr(mod.os, "chmod", boom)

        sc._chmod_key()  # 不抛即通过

    def test_rotate_key_keeps_old_file(self, sc, cfg_dir):
        """轮换必须保留旧密钥文件 —— 账户恢复后旧密文还有救。"""
        old = sc.key_file.read_bytes()

        sc._rotate_key(RuntimeError("解保护失败"))

        backups = list(cfg_dir.glob(".config_key.old-*"))
        assert backups, "旧密钥文件被直接覆盖，永久失去恢复可能"
        assert backups[0].read_bytes() == old
        assert sc._load_failed is True, "轮换后没置标记，下次 save 会洗掉磁盘内容"

    def test_rotate_overwrites_stale_backup(self, sc, cfg_dir):
        """同一秒内两次轮换产生的同名备份要能被覆盖，不能因存在而失败。"""
        import time

        stamp = time.strftime("%Y%m%d_%H%M%S")
        stale = cfg_dir / f".config_key.old-{stamp}"
        stale.write_bytes(b"stale")

        sc._rotate_key(RuntimeError("x"))

        assert stale.exists()
        assert stale.read_bytes() != b"stale", "同名旧备份没有被覆盖"
