"""
AI模型服务配置文件
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List, Optional
import os
import secrets
from loguru import logger

class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "AI模型服务"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENV: str = Field(default="development", env="APP_ENV")
    HOST: str = "0.0.0.0"
    PORT: int = 8001
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
    
    # 本地模型配置
    LOCAL_MODEL_PATH: str = "./models/local"
    LOCAL_MODEL_NAME: str = "qwen3.6"
    LOCAL_MODEL_CONTEXT_SIZE: int = 4096
    LOCAL_MODEL_GPU_LAYERS: int = 0  # 0表示使用CPU
    
    # OpenAI配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4"
    OPENAI_MAX_TOKENS: int = 4096
    
    # Claude配置
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_API_BASE: str = "https://api.anthropic.com"
    CLAUDE_DEFAULT_MODEL: str = "claude-3-sonnet-20240229"
    CLAUDE_MAX_TOKENS: int = 4096
    
    # 生成配置
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9
    DEFAULT_MAX_TOKENS: int = 1000
    
    # 缓存配置
    CACHE_TTL: int = 3600  # 1小时
    CACHE_MAX_SIZE: int = 1000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/ai-service.log"
    
    # 安全配置
    SECRET_KEY: str = Field(default="", env="SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v:
            # 开发环境自动生成临时密钥，生产环境必须配置
            import os
            if os.getenv("APP_ENV") == "production":
                raise ValueError("生产环境必须配置SECRET_KEY环境变量")
            logger.warning("SECRET_KEY未配置，使用临时密钥（仅限开发环境）")
            return secrets.token_urlsafe(32)
        return v
    
    # 性能配置
    MAX_CONCURRENT_REQUESTS: int = 10
    REQUEST_TIMEOUT: int = 30  # 秒
    
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
    
    # 检查本地模型路径
    if not os.path.exists(settings.LOCAL_MODEL_PATH):
        os.makedirs(settings.LOCAL_MODEL_PATH, exist_ok=True)
    
    # 检查数据库配置
    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL未配置，请在.env文件中设置")
    
    # 检查API密钥
    if not settings.OPENAI_API_KEY and not settings.CLAUDE_API_KEY:
        logger.warning("未配置云端API密钥，只能使用本地模型")
    
    # 生产环境安全检查
    if settings.is_production:
        if settings.CORS_ORIGINS == ["*"]:
            errors.append("生产环境CORS_ORIGINS不能为['*']，请配置具体域名")
    
    return errors

# 在模块加载时验证配置
validation_errors = validate_settings()
if validation_errors:
    for error in validation_errors:
        logger.error(f"配置错误: {error}")