"""
小说生成服务配置文件
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "小说生成服务"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    WORKERS: int = 1
    
    # CORS配置
    CORS_ORIGINS: List[str] = ["*"]
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_novel"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # AI服务配置
    AI_SERVICE_URL: str = "http://localhost:8001"
    AI_SERVICE_TIMEOUT: int = 30
    
    # 小说生成配置
    MAX_CHAPTERS: int = 50
    MAX_CHAPTER_LENGTH: int = 5000  # 字符数
    DEFAULT_CHAPTER_COUNT: int = 10
    
    # 缓存配置
    CACHE_TTL: int = 3600  # 1小时
    CACHE_MAX_SIZE: int = 1000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/novel-service.log"
    
    # 性能配置
    MAX_CONCURRENT_GENERATIONS: int = 5
    GENERATION_TIMEOUT: int = 300  # 5分钟
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# 创建全局设置实例
settings = Settings()

# 确保日志目录存在
os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)