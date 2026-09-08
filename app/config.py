"""
配置管理模块 - 管理应用配置
"""

import json
from pathlib import Path

# 默认配置（单一定义，避免重复）
DEFAULT_CONFIG = {
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
    "img_model": "sd_xl_base_1.0.safetensors",
    "img_width": 1024,
    "img_height": 1024,
    "auto_detect_scene": True,
}


class AppConfig:
    """应用配置（敏感字段加密存储）"""
    
    # 敏感字段列表 - 这些字段使用加密存储
    SENSITIVE_FIELDS = ['api_key', 'img_api_key', 'secret_key']
    
    def __init__(self):
        self.config_dir = Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.novels_dir = self.config_dir / "novels"
        self.novels_dir.mkdir(exist_ok=True)
        
        # 先初始化安全配置（用于敏感字段加解密）
        self._secure_config = None
        try:
            from .secure_config import SecureConfig
            self._secure_config = SecureConfig()
        except Exception:
            self._secure_config = None
        
        self.config = self._load()
    
    def _load(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = DEFAULT_CONFIG.copy()
        
        # 解密敏感字段（M3 修复：单一加密数据源，读取时解密）
        if self._secure_config:
            for field in self.SENSITIVE_FIELDS:
                if field in config and config[field]:
                    decrypted = self._secure_config._decrypt(config[field])
                    if decrypted:
                        config[field] = decrypted
                    else:
                        # 无法解密的残留值（明文或损坏），清空
                        config[field] = ""
        return config
    
    def save(self):
        config_to_save = self.config.copy()
        
        # 加密敏感字段后再落盘（M3 修复：明文不写入 config.json）
        if self._secure_config:
            for field in self.SENSITIVE_FIELDS:
                if field in config_to_save and config_to_save[field]:
                    config_to_save[field] = self._secure_config._encrypt(config_to_save[field])
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default=None):
        if self._secure_config and key in self.SENSITIVE_FIELDS:
            value = self._secure_config.get(key)
            if value:
                return value
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        if self._secure_config and key in self.SENSITIVE_FIELDS:
            self._secure_config.set(key, value)
            # 同步内存中的值
            self.config[key] = value
        else:
            self.config[key] = value
        self.save()
