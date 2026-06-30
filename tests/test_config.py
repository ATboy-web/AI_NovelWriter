"""
AppConfig 单元测试
测试配置管理功能
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock
from app.config import AppConfig


class TestAppConfig:
    """AppConfig 测试套件"""
    
    @pytest.fixture
    def config_dir(self, tmp_path):
        """创建临时配置目录"""
        return tmp_path / ".ai_novel_writer"
    
    @pytest.fixture
    def app_config(self, config_dir, monkeypatch):
        """创建AppConfig实例，使用临时目录"""
        # Mock Path.home() 返回临时目录
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        return AppConfig()
    
    def test_init_creates_directory(self, config_dir, monkeypatch):
        """测试初始化时创建配置目录"""
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        assert not config_dir.exists()
        AppConfig()
        assert config_dir.exists()
    
    def test_init_creates_novels_directory(self, config_dir, monkeypatch):
        """测试初始化时创建小说目录"""
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        AppConfig()
        assert (config_dir / "novels").exists()
    
    def test_default_config(self, app_config):
        """测试默认配置"""
        assert app_config.get("api_provider") == "ollama"
        assert app_config.get("api_base") == "http://localhost:11434"
        assert app_config.get("model") == "qwen2.5:14b"
        assert app_config.get("max_tokens") == 4096
        assert app_config.get("temperature") == 0.8
        assert app_config.get("auto_save") is True
        assert app_config.get("theme") == "light"
        assert app_config.get("adult_content") is False
        assert app_config.get("edge_content") is False
    
    def test_get_existing_key(self, app_config):
        """测试获取已存在的键"""
        assert app_config.get("api_provider") == "ollama"
    
    def test_get_nonexistent_key(self, app_config):
        """测试获取不存在的键"""
        assert app_config.get("nonexistent") is None
    
    def test_get_with_default(self, app_config):
        """测试获取不存在的键时返回默认值"""
        assert app_config.get("nonexistent", "default") == "default"
    
    def test_set_and_get(self, app_config):
        """测试设置和获取配置"""
        app_config.set("api_key", "sk-test-key")
        assert app_config.get("api_key") == "sk-test-key"
    
    def test_set_overwrites(self, app_config):
        """测试设置覆盖"""
        app_config.set("model", "gpt-4")
        assert app_config.get("model") == "gpt-4"
        
        app_config.set("model", "gpt-3.5-turbo")
        assert app_config.get("model") == "gpt-3.5-turbo"
    
    def test_save_persists(self, config_dir, monkeypatch):
        """测试保存持久化"""
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        
        # 创建并保存配置（使用非敏感字段测试持久化）
        config1 = AppConfig()
        config1.set("model", "gpt-4-turbo")
        config1.set("temperature", 0.9)
        
        # 重新加载
        config2 = AppConfig()
        assert config2.get("model") == "gpt-4-turbo"
        assert config2.get("temperature") == 0.9
    
    def test_load_existing_config(self, config_dir, monkeypatch):
        """测试加载已存在的配置"""
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        
        # 创建配置文件
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        existing_config = {
            "api_provider": "openai",
            "api_key": "sk-existing-key",
            "model": "gpt-4"
        }
        config_file.write_text(json.dumps(existing_config, indent=2), encoding='utf-8')
        
        # 加载配置
        config = AppConfig()
        assert config.get("api_provider") == "openai"
        assert config.get("api_key") == "sk-existing-key"
        assert config.get("model") == "gpt-4"
    
    def test_load_preserves_extra_keys(self, config_dir, monkeypatch):
        """测试加载保留额外的键"""
        monkeypatch.setattr('pathlib.Path.home', lambda: config_dir.parent)
        
        # 创建配置文件，包含额外的键
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        existing_config = {
            "api_provider": "openai",
            "custom_key": "custom_value"
        }
        config_file.write_text(json.dumps(existing_config, indent=2), encoding='utf-8')
        
        # 加载配置
        config = AppConfig()
        assert config.get("custom_key") == "custom_value"
    
    def test_unicode_config(self, app_config):
        """测试Unicode配置"""
        app_config.set("app_name", "AI小说写作助手")
        assert app_config.get("app_name") == "AI小说写作助手"
    
    def test_complex_config(self, app_config):
        """测试复杂配置值"""
        app_config.set("nested", {"key": "value", "list": [1, 2, 3]})
        assert app_config.get("nested") == {"key": "value", "list": [1, 2, 3]}


class TestAppConfigEdgeCases:
    """边界条件测试"""
    
    def test_invalid_json_file(self, tmp_path, monkeypatch):
        """测试无效的JSON文件"""
        config_dir = tmp_path / ".ai_novel_writer"
        monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
        
        # 创建无效的JSON文件
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text("这不是有效的JSON{", encoding='utf-8')
        
        # 应该抛出异常
        with pytest.raises(json.JSONDecodeError):
            AppConfig()
    
    def test_read_only_config_file(self, tmp_path, monkeypatch):
        """测试只读配置文件"""
        config_dir = tmp_path / ".ai_novel_writer"
        monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
        
        # 创建配置文件
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"key": "value"}', encoding='utf-8')
        
        # 设置只读（Windows上可能不生效）
        try:
            config_file.chmod(0o444)
        except (OSError, AttributeError):
            pass
        
        # 加载配置应该成功
        config = AppConfig()
        assert config.get("key") == "value"
    
    def test_config_dir_is_file(self, tmp_path, monkeypatch):
        """测试配置目录是文件的情况"""
        config_dir = tmp_path / ".ai_novel_writer"
        monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
        
        # 创建一个文件而不是目录
        config_dir.write_text("这是文件", encoding='utf-8')
        
        # 应该抛出异常
        with pytest.raises(Exception):
            AppConfig()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
