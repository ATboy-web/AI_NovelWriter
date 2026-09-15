"""薄转发层 (P2-3)

实体实现已抽取到 backend/shared/middleware/rate_limiter.py。
本文件仅做再导出，保持既有 `from app.middleware.rate_limiter import ...` 调用不变。
"""
from shared.middleware.rate_limiter import *  # noqa: F401,F403
from shared.middleware.rate_limiter import (  # noqa: F401
    DynamicRateLimiter,
    RateLimitConfig,
    RateLimitInfo,
)
