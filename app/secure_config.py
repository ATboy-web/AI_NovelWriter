"""
安全配置管理模块 - 加密存储敏感配置
"""

import json
import os
import base64
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class SecureConfig:
    """安全配置管理器 - 使用Fernet加密保护敏感数据"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.key_file = self.config_dir / ".config_key"
        self.fernet = self._init_encryption()
        self.config = self._load()
    
    def _init_encryption(self) -> Fernet:
        """初始化加密引擎"""
        if self.key_file.exists():
            # 读取已有的加密密钥
            key = self.key_file.read_bytes()
        else:
            # 生成新的加密密钥
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            # 设置文件权限（仅当前用户可读写）
            try:
                os.chmod(self.key_file, 0o600)
            except (OSError, AttributeError):
                # Windows上可能不支持chmod
                pass
        return Fernet(key)
    
    def _encrypt(self, value: str) -> str:
        """加密字符串"""
        if not value:
            return ""
        return self.fernet.encrypt(value.encode()).decode()
    
    def _decrypt(self, encrypted_value: str) -> str:
        """解密字符串"""
        if not encrypted_value:
            return ""
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            # 如果解密失败，检查是否是旧格式的未加密配置
            # Fernet token 格式: base64编码，以gAAAAA开头
            if encrypted_value.startswith('gAAAAA'):
                # 看起来是加密的但解密失败，返回空字符串
                logger.error(f"解密失败，密钥可能已损坏: {e}")
                return ""
            else:
                # 可能是旧格式的未加密配置，向后兼容
                logger.warning(f"检测到未加密的旧格式配置，建议重新保存以加密")
                return encrypted_value
    
    def _load(self) -> dict:
        """加载配置"""
        if not self.config_file.exists():
            return self._default_config()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 解密敏感字段
            sensitive_fields = ['api_key', 'img_api_key', 'secret_key']
            for field in sensitive_fields:
                if field in config and config[field]:
                    config[field] = self._decrypt(config[field])
            
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """默认配置"""
        return {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "qwen2.5:14b",
            "max_tokens": 4096,
            "temperature": 0.8,
            "context_window": 32000,
            "auto_save": True,
            "theme": "light",
            "adult_content": False,
            "edge_content": False,
            "img_provider": "comfyui",
            "img_api_base": "http://127.0.0.1:8188",
            "img_api_key": "",
            "img_model": "sd_xl_base_1.0.safetensors",
            "img_width": 1024,
            "img_height": 1024,
            "auto_detect_scene": True,
        }
    
    def save(self):
        """保存配置（加密敏感字段）"""
        config_to_save = self.config.copy()
        
        # 加密敏感字段
        sensitive_fields = ['api_key', 'img_api_key', 'secret_key']
        for field in sensitive_fields:
            if field in config_to_save and config_to_save[field]:
                config_to_save[field] = self._encrypt(config_to_save[field])
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
        # 设置文件权限（仅当前用户可读写）
        try:
            os.chmod(self.config_file, 0o600)
        except (OSError, AttributeError):
            pass
    
    def get(self, key: str, default=None):
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """设置配置值"""
        self.config[key] = value
        self.save()
    
    def get_api_key(self) -> str:
        """获取API密钥"""
        return self.get("api_key", "")
    
    def set_api_key(self, api_key: str):
        """设置API密钥"""
        self.set("api_key", api_key)


# 全局实例
_secure_config: Optional[SecureConfig] = None


def get_secure_config() -> SecureConfig:
    """获取安全配置管理器单例"""
    global _secure_config
    if _secure_config is None:
        _secure_config = SecureConfig()
    return _secure_config
