"""
JWT认证中间件 - 提供API认证和授权功能
"""

import os
import secrets
import time
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("jwt库未安装，JWT认证功能不可用")


class JWTConfig:
    """JWT配置"""
    
    # 密钥从环境变量读取，禁止硬编码。未配置时生产环境将拒绝启动。
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    ALGORITHM = "HS256"
    
    # Token过期时间
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    # 不需要认证的路径
    PUBLIC_PATHS = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/health",
    ]
    
    # API Key认证的路径（可选）
    API_KEY_PATHS = [
        "/api/v1/generate",
        "/api/v1/models",
    ]


def _load_api_keys() -> Dict[str, Dict]:
    """从环境变量 API_KEYS 加载合法 API Key。

    格式：逗号分隔的 `key:level` 或裸 `key`（默认 level=basic）。
    例如：`API_KEYS=sk-abc123:premium,sk-def456`
    """
    raw = os.getenv("API_KEYS", "")
    result: Dict[str, Dict] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            key, level = item.split(":", 1)
        else:
            key, level = item, "basic"
        key = key.strip()
        if key:
            result[key] = {
                "user_id": f"apikey-{key[:8]}",
                "username": "apikey",
                "role": "user",
                "level": level.strip() or "basic",
            }
    return result


class JWTManager:
    """JWT管理器"""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
        if not self.config.SECRET_KEY:
            logger.warning("SECRET_KEY 未配置，JWT 签名密钥缺失。请在环境变量中设置 SECRET_KEY。")
    
    def _require_secret(self):
        """确保签名密钥已配置，否则拒绝签名/验签"""
        if not self.config.SECRET_KEY:
            raise RuntimeError("SECRET_KEY 未配置，无法进行 JWT 签名/验签")
    
    def create_access_token(
        self, 
        data: Dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问Token"""
        if not JWT_AVAILABLE:
            raise RuntimeError("jwt库未安装")
        self._require_secret()
        
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.config.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        return jwt.encode(
            to_encode, 
            self.config.SECRET_KEY, 
            algorithm=self.config.ALGORITHM
        )
    
    def create_refresh_token(self, data: Dict) -> str:
        """创建刷新Token"""
        if not JWT_AVAILABLE:
            raise RuntimeError("jwt库未安装")
        self._require_secret()
        
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(
            days=self.config.REFRESH_TOKEN_EXPIRE_DAYS
        )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        })
        
        return jwt.encode(
            to_encode, 
            self.config.SECRET_KEY, 
            algorithm=self.config.ALGORITHM
        )
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """验证Token"""
        if not JWT_AVAILABLE:
            raise RuntimeError("jwt库未安装")
        if not self.config.SECRET_KEY:
            return None
        
        try:
            payload = jwt.decode(
                token, 
                self.config.SECRET_KEY, 
                algorithms=[self.config.ALGORITHM]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效Token: {e}")
            return None


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件"""
    
    def __init__(self, app, config: Optional[JWTConfig] = None):
        super().__init__(app)
        self.config = config or JWTConfig()
        self.jwt_manager = JWTManager(self.config)
    
    def _is_public_path(self, path: str) -> bool:
        """检查是否为公开路径"""
        # 精确匹配
        if path in self.config.PUBLIC_PATHS:
            return True
        
        # 前缀匹配
        for public_path in self.config.PUBLIC_PATHS:
            if path.startswith(public_path):
                return True
        
        return False
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """提取Token"""
        # 从Authorization header提取
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # 从查询参数提取
        token = request.query_params.get("token")
        if token:
            return token
        
        # 从Cookie提取
        token = request.cookies.get("access_token")
        if token:
            return token
        
        return None
    
    def _extract_api_key(self, request: Request) -> Optional[str]:
        """提取API Key"""
        # 从header提取
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key
        
        # 从查询参数提取
        api_key = request.query_params.get("api_key")
        if api_key:
            return api_key
        
        return None
    
    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 检查是否为公开路径
        if self._is_public_path(request.url.path):
            return await call_next(request)
        
        # 提取Token
        token = self._extract_token(request)
        
        # 提取API Key
        api_key = self._extract_api_key(request)
        
        # 验证认证
        user_info = None
        
        if token:
            # 验证JWT Token
            payload = self.jwt_manager.verify_token(token)
            if payload:
                user_info = {
                    "user_id": payload.get("sub"),
                    "username": payload.get("username"),
                    "role": payload.get("role", "user"),
                    "level": payload.get("level", "free"),
                }
        
        if not user_info and api_key:
            # 验证API Key
            user_info = await self._verify_api_key(api_key)
        
        if not user_info:
            logger.warning(f"未认证访问: {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "需要认证，请提供有效的Token或API Key"
                }
            )
        
        # 将用户信息添加到请求状态
        request.state.user = user_info
        
        # 处理请求
        response = await call_next(request)
        
        # 添加认证相关头
        response.headers["X-User-Id"] = str(user_info.get("user_id", ""))
        
        return response
    
    async def _verify_api_key(self, api_key: str) -> Optional[Dict]:
        """验证API Key（从环境变量 API_KEYS 读取合法密钥）"""
        if not api_key:
            return None
        valid_api_keys = _load_api_keys()
        if not valid_api_keys:
            logger.warning("API_KEYS 未配置，API Key 认证不可用")
            return None
        return valid_api_keys.get(api_key)


class AuthDependencies:
    """认证依赖注入"""
    
    def __init__(self):
        self.jwt_manager = JWTManager()
    
    def get_current_user(self, request: Request) -> Dict:
        """获取当前用户"""
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="未认证"
            )
        return user
    
    def require_role(self, roles: List[str]):
        """要求特定角色"""
        def dependency(request: Request):
            user = self.get_current_user(request)
            if user.get("role") not in roles:
                raise HTTPException(
                    status_code=403,
                    detail="权限不足"
                )
            return user
        return dependency
    
    def require_level(self, levels: List[str]):
        """要求特定用户级别"""
        def dependency(request: Request):
            user = self.get_current_user(request)
            if user.get("level") not in levels:
                raise HTTPException(
                    status_code=403,
                    detail="用户级别不足"
                )
            return user
        return dependency


# 全局实例
auth_deps = AuthDependencies()
