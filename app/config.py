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
    """应用配置"""
    
    # 敏感字段列表 - 这些字段应该使用SecureConfig加密存储
    SENSITIVE_FIELDS = ['api_key', 'img_api_key', 'secret_key']
    
    def __init__(self):
        self.config_dir = Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.novels_dir = self.config_dir / "novels"
        self.novels_dir.mkdir(exist_ok=True)
        self.config = self._load()
        
        # 尝试加载SecureConfig用于敏感字段
        self._secure_config = None
        try:
            from .secure_config import SecureConfig
            self._secure_config = SecureConfig()
        except Exception:
            pass
    
    def _load(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default=None):
        # 如果有SecureConfig且是敏感字段，优先从SecureConfig获取
        if self._secure_config and key in self.SENSITIVE_FIELDS:
            value = self._secure_config.get(key)
            if value:
                return value
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        # 如果是敏感字段且有SecureConfig，使用SecureConfig加密存储
        if self._secure_config and key in self.SENSITIVE_FIELDS:
            self._secure_config.set(key, value)
        else:
            self.config[key] = value
        self.save()
