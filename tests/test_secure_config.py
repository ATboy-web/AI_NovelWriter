"""
SecureConfig 单元测试
测试API密钥加密存储功能
"""

import sys
import tempfile
import shutil
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
        with open(secure_config.config_file, 'r') as f:
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
        """测试向后兼容性（未加密的旧配置）"""
        import json
        
        # 模拟旧的未加密配置
        config_dir.mkdir(parents=True, exist_ok=True)
        old_config = {
            "api_provider": "openai",
            "api_key": "sk-old-plain-key",  # 未加密
            "model": "gpt-3.5-turbo"
        }
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(old_config, indent=2))
        
        # 加载配置，应该能读取旧的未加密密钥
        config = SecureConfig(config_dir)
        assert config.get_api_key() == "sk-old-plain-key"
    
    def test_get_nonexistent_key(self, secure_config):
        """测试获取不存在的键"""
        assert secure_config.get("nonexistent") is None
        assert secure_config.get("nonexistent", "default") == "default"


class TestSecureConfigEdgeCases:
    """边界条件测试"""
    
    def test_corrupted_key_file(self, tmp_path):
        """测试损坏的密钥文件"""
        config_dir = tmp_path / ".ai_novel_writer"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # 写入损坏的密钥文件
        key_file = config_dir / ".config_key"
        key_file.write_bytes(b"corrupted-key-data")
        
        # 应该抛出异常或处理错误
        with pytest.raises(Exception):
            SecureConfig(config_dir)
    
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
