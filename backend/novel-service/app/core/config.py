"""
小说生成服务配置文件
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List, Optional
import os
from loguru import logger

class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "小说生成服务"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=True, env="DEBUG")
    ENV: str = Field(default="development", env="APP_ENV")
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    WORKERS: int = 1
    
    @property
    def is_production(self) -> bool:
        return self.ENV == "production"
    
    # CORS配置 - 生产环境应限制来源
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:80"],
        env="CORS_ORIGINS"
    )
    
    # 数据库配置
    DATABASE_URL: str = Field(default="", env="DATABASE_URL")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
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

# 验证必要配置
def validate_settings():
    """验证配置有效性"""
    errors = []
    
    # 检查数据库配置
    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL未配置，请在.env文件中设置")
    
    # 生产环境安全检查
    if settings.is_production:
        if settings.CORS_ORIGINS == ["*"]:
            errors.append("生产环境CORS_ORIGINS不能为['*']，请配置具体域名")
    
    if errors:
        for error in errors:
            logger.error(f"配置错误: {error}")
        if settings.is_production:
            raise ValueError("配置验证失败，请检查环境变量")
    
    return errors

# 在模块加载时验证配置
validate_settings()