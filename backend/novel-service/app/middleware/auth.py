"""
JWT认证中间件 - 提供API认证和授权功能
"""

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
    
    # 密钥（生产环境应从环境变量读取）
    SECRET_KEY = "your-secret-key-change-in-production"
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


class JWTManager:
    """JWT管理器"""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
    
    def create_access_token(
        self, 
        data: Dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问Token"""
        if not JWT_AVAILABLE:
            raise RuntimeError("jwt库未安装")
        
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
    
    def decode_token_without_verification(self, token: str) -> Optional[Dict]:
        """解码Token（不验证签名，用于调试）"""
        if not JWT_AVAILABLE:
            return None
        
        try:
            return jwt.decode(
                token, 
                options={"verify_signature": False}
            )
        except Exception:
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
        """验证API Key"""
        # TODO: 实现API Key验证逻辑
        # 这里只是示例，实际应该查询数据库
        valid_api_keys = {
            "test-api-key": {
                "user_id": "test-user",
                "username": "test",
                "role": "user",
                "level": "basic"
            }
        }
        
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
