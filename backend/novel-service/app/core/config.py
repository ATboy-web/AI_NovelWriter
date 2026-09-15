"""
小说生成服务配置文件
"""

import os
import secrets
from typing import List

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


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
        # 兼容 APP_ENV / ENV / NODE_ENV 三种约定：
        # docker-compose.prod.yml 用 NODE_ENV=production（Node 惯例）注入，
        # 而原实现只认 APP_ENV/ENV，导致生产安全校验（SECRET_KEY 必填、
        # CORS 禁 "*"）在真实部署中从未生效。
        return self.ENV == "production" or os.getenv("NODE_ENV", "").lower() == "production"
    
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
    
    # 安全/认证配置
    SECRET_KEY: str = Field(default="", env="SECRET_KEY")
    ENABLE_AUTH: bool = Field(default=True, env="ENABLE_AUTH")
    API_KEYS: str = Field(default="", env="API_KEYS")
    
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """解析签名密钥，并在生产环境强制要求显式配置。

        与 ai-service 行为保持一致（原 novel-service 缺少该校验，
        导致生产环境可在无密钥状态下启动，鉴权必然失败）。
        """
        # 变量名兼容：.env.example / docker-compose.prod.yml / deploy.sh 均使用
        # JWT_SECRET，此处作为 SECRET_KEY 的别名回退。
        v = v or os.getenv("JWT_SECRET", "")
        if not v:
            if (
                os.getenv("APP_ENV", "").lower() == "production"
                or os.getenv("NODE_ENV", "").lower() == "production"
            ):
                raise ValueError("生产环境必须配置SECRET_KEY环境变量")
            logger.warning("SECRET_KEY未配置，使用临时密钥（仅限开发环境）")
            return secrets.token_urlsafe(32)
        return v
    
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
