"""
SecureConfig 单元测试
测试API密钥加密存储功能
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.secure_config import SecureConfig


class TestSecureConfig:
    """SecureConfig 测试套件"""

    @pytest.fixture
    def config_dir(self, tmp_path):
        """创建临时配置目录"""
        return tmp_path / ".ai_novel_writer"

    @pytest.fixture
    def secure_config(self, config_dir):
        """创建SecureConfig实例"""
        return SecureConfig(config_dir)

    def test_init_creates_directory(self, config_dir):
        """测试初始化时创建配置目录"""
        assert not config_dir.exists()
        SecureConfig(config_dir)
        assert config_dir.exists()

    def test_init_creates_key_file(self, secure_config, config_dir):
        """测试初始化时创建加密密钥文件"""
        key_file = config_dir / ".config_key"
        assert key_file.exists()

    def test_default_config(self, secure_config):
        """测试默认配置"""
        config = secure_config.config
        assert "api_key" in config
        assert "api_provider" in config
        assert config["api_provider"] == "ollama"

    def test_set_and_get(self, secure_config):
        """测试设置和获取配置"""
        secure_config.set("test_key", "test_value")
        assert secure_config.get("test_key") == "test_value"

    def test_encrypt_decrypt_api_key(self, secure_config):
        """测试API密钥加密和解密"""
        test_key = "sk-1234567890abcdef"
        secure_config.set_api_key(test_key)

        # 读取原始文件，确认API密钥已加密
        import json

        # 显式 utf-8：不指定的话 Windows 上默认 GBK，配置里有中文/非 ASCII 就解析不了
        with open(secure_config.config_file, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        # 原始文件中的API密钥应该是加密的
        assert raw_config["api_key"] != test_key

        # 但通过get获取的应该是解密后的
        assert secure_config.get_api_key() == test_key

    def test_save_and_reload(self, config_dir):
        """测试保存后重新加载"""
        # 创建并保存配置
        config1 = SecureConfig(config_dir)
        config1.set_api_key("sk-test-key-123")
        config1.set("model", "gpt-4")

        # 重新加载
        config2 = SecureConfig(config_dir)
        assert config2.get_api_key() == "sk-test-key-123"
        assert config2.get("model") == "gpt-4"

    def test_empty_api_key(self, secure_config):
        """测试空API密钥"""
        secure_config.set_api_key("")
        assert secure_config.get_api_key() == ""

    def test_special_characters_in_api_key(self, secure_config):
        """测试特殊字符的API密钥"""
        special_key = "sk-!@#$%^&*()_+{}|:<>?[]\\;',./"
        secure_config.set_api_key(special_key)
        assert secure_config.get_api_key() == special_key

    def test_unicode_in_config(self, secure_config):
        """测试Unicode字符"""
        secure_config.set("app_name", "AI小说写作助手")
        assert secure_config.get("app_name") == "AI小说写作助手"

    def test_backward_compatibility(self, config_dir):
        """测试明文旧格式配置：敏感字段被安全清空（不再降级接受明文）"""
        import json

        # 模拟旧的未加密配置
        config_dir.mkdir(parents=True, exist_ok=True)
        old_config = {
            "api_provider": "openai",
            "api_key": "sk-old-plain-key",  # 未加密
            "model": "gpt-3.5-turbo",
        }
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(old_config, indent=2))

        # 加载配置：明文敏感字段不再被接受，安全清空
        config = SecureConfig(config_dir)
        assert config.get_api_key() == ""

    def test_get_nonexistent_key(self, secure_config):
        """测试获取不存在的键"""
        assert secure_config.get("nonexistent") is None
        assert secure_config.get("nonexistent", "default") == "default"


@pytest.mark.skipif(sys.platform != "win32", reason="该用例依赖 Windows DPAPI")
class TestSecureConfigEdgeCases:
    """边界条件测试"""

    def test_corrupted_key_file_is_rotated_not_fatal(self, tmp_path):
        """损坏/异账户的密钥文件 ⇒ **轮换**，不是让加密后端永久失效。

        ❗ 原用例断言 `pytest.raises(Exception)`，即"打不开就抛"。那个契约把所有
        打不开密钥的机器**永久锁死**：`CloudStorageManager._secure_config` 变成 `None`
        ⇒ 云盘凭据永远无法保存，且用户不知道"删掉密钥文件就能恢复"。
        本机实测就撞上了这一条（密钥来自另一账户）。

        新契约（本次改动）：
        1. 构造**成功**；
        2. 旧密钥文件被留档为 `.config_key.old-<时间戳>`（不覆盖、可取证）；
        3. `_load_failed` 置位 ⇒ `save()` 不会用默认值抹掉磁盘上的既有配置；
        4. 新密钥可用（能加解密）。
        """
        config_dir = tmp_path / ".ai_novel_writer"
        config_dir.mkdir(parents=True, exist_ok=True)
        key_file = config_dir / ".config_key"
        key_file.write_bytes(b"corrupted-key-data")

        secure = SecureConfig(config_dir)

        assert secure.fernet is not None, "轮换后加密引擎应可用"
        assert secure._load_failed is True, "必须置 _load_failed，否则保存时会抹掉既有配置"
        archived = list(config_dir.glob(".config_key.old-*"))
        assert archived, "旧密钥必须留档（以后能恢复账户时旧密文还有救）"
        assert archived[0].read_bytes() == b"corrupted-key-data", "留档的应是原始字节"
        assert key_file.read_bytes() != b"corrupted-key-data", "主密钥文件应已换成新密钥"

        # 新密钥真的能用
        cipher = secure._encrypt("PLAINTEXT")
        assert cipher != "PLAINTEXT"
        assert secure._decrypt(cipher) == "PLAINTEXT"

    def test_rotation_does_not_wipe_existing_config(self, tmp_path):
        """轮换之后 `save()` 不得把磁盘上既有配置洗成默认值。

        这是轮换最容易造成的**数据损失**：密钥换了、旧密文解不开，
        若保存逻辑把"解不开"当成"没有"，用户配置就被默认值覆盖了。
        """
        config_dir = tmp_path / ".ai_novel_writer"
        config_dir.mkdir(parents=True, exist_ok=True)

        first = SecureConfig(config_dir)
        first.set("safe_setting", "KEEP-ME")
        first.save()

        # 模拟密钥被外部破坏（换账户/换机器）
        (config_dir / ".config_key").write_bytes(b"corrupted-key-data")

        broken = SecureConfig(config_dir)
        assert broken._load_failed is True
        broken.set("another", "x")
        broken.save()

        import json

        raw = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert raw.get("safe_setting") == "KEEP-ME", "轮换后既有配置被抹掉了"

    def test_missing_config_file(self, tmp_path):
        """测试缺少配置文件"""
        config_dir = tmp_path / ".ai_novel_writer"
        config = SecureConfig(config_dir)

        # 应该返回默认配置
        assert config.get("api_provider") == "ollama"

    def test_invalid_json_in_config(self, tmp_path):
        """测试无效的JSON配置"""
        config_dir = tmp_path / ".ai_novel_writer"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.json"
        config_file.write_text("这不是有效的JSON{")

        # 应该返回默认配置
        config = SecureConfig(config_dir)
        assert config.get("api_provider") == "ollama"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
