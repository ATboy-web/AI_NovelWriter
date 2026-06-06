"""
配置管理模块 - 管理应用配置
"""

import json
from pathlib import Path


class AppConfig:
    """应用配置"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.novels_dir = self.config_dir / "novels"
        self.novels_dir.mkdir(exist_ok=True)
        self.config = self._load()
    
    def _load(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "api_provider": "ollama",  # openai / claude / deepseek / ollama / custom
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "qwen2.5:14b",
            "max_tokens": 4096,
            "temperature": 0.8,
            "context_window": 32000,  # 上下文窗口大小（字符数）
            "auto_save": True,
            "theme": "light",
            # 文生图配置
            "img_provider": "comfyui",  # comfyui / sdapi / disabled
            "img_api_base": "http://127.0.0.1:8188",
            "img_model": "sd_xl_base_1.0.safetensors",
            "img_width": 1024,
            "img_height": 1024,
            "auto_detect_scene": True,  # 自动检测名场面
        }
    
    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        self.config[key] = value
        self.save()
