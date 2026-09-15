"""薄转发层 (P2-3)

实体实现已抽取到 backend/shared/middleware/auth.py。
本文件仅做再导出，保持既有 `from app.middleware.auth import ...` 调用不变。
"""
from shared.middleware.auth import *  # noqa: F401,F403
from shared.middleware.auth import (  # noqa: F401
    AuthMiddleware,
    JWTConfig,
    JWTManager,
    AuthDependencies,
)
