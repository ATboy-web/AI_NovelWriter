"""
JWT认证中间件 - 提供API认证和授权功能

认证模型（S5 明确声明）
----------------------
本中间件支持两种凭据：

1. **静态 API Key**（推荐，也是本服务唯一开箱可用的方式）
   通过环境变量 ``API_KEYS`` 配置，客户端以 ``X-API-Key: <key>``（或
   ``?api_key=``）调用。
2. JWT Token —— 由 ``JWTManager`` 验签，但**本服务不提供签发端点**
   （全仓无 ``/login`` / ``/token`` 路由）。``create_access_token`` 仅用于
   单元测试与内部集成。

因此一体化部署请优先使用 ``API_KEYS``；只配置 ``SECRET_KEY`` 而不配
``API_KEYS`` 会得到一个"能验签但没有 token 可用"的服务。
"""

import hashlib
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException, Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("jwt库未安装，JWT认证功能不可用")


class JWTConfig:
    """JWT配置"""
    
    # 密钥从环境变量读取，禁止硬编码。未配置时生产环境将拒绝启动。
    #
    # 变量名兼容 SECRET_KEY / JWT_SECRET 两个名字：
    # .env.example、docker-compose.prod.yml、deploy.sh 历史上统一使用 JWT_SECRET，
    # 而代码只读取 SECRET_KEY，导致运维按文档配置的密钥被静默忽略、鉴权永远失败。
    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "")
    ALGORITHM = "HS256"
    
    # Token过期时间
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    # 不需要认证的路径（精确匹配）
    PUBLIC_PATHS = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/health",
    ]
    
    # 公开路径前缀（仅用于 Swagger/ReDoc 的静态子资源，如 /docs/oauth2-redirect）。
    #
    # ⚠️ 严禁把 "/" 放进本列表：任何路径都以 "/" 开头，
    #    前缀匹配 "/" 会让 _is_public_path() 恒为 True，等于彻底关闭鉴权
    #    （历史上 PUBLIC_PATHS 同时参与前缀匹配，正是该缺陷）。
    PUBLIC_PATH_PREFIXES = [
        "/docs",
        "/redoc",
        "/static",
        "/assets",
    ]
    
    # API Key认证的路径（可选）
    API_KEY_PATHS = [
        "/api/v1/generate",
        "/api/v1/models",
    ]
    
    def __init__(self, secret_key: Optional[str] = None):
        """初始化配置。

        Args:
            secret_key: 显式指定签名密钥。服务启动时应传入 Settings.SECRET_KEY，
                以便统一由配置层解析环境变量/别名并执行生产环境校验；
                不传则回退到直接读取环境变量。
        """
        if secret_key:
            self.SECRET_KEY = secret_key


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
            # S8: user_id 不能包含密钥本体。旧实现用 `f"apikey-{key[:8]}"`，
            # 而这个值会经 `X-User-Id` 响应头回给调用方（见 dispatch），
            # 使密钥前 8 位进入浏览器 / 代理 / 日志的可见范围，缩小暴力破解空间。
            # 改用密钥的短哈希：仍然稳定、可区分不同 key，但不可逆。
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
            result[key] = {
                "user_id": f"apikey-{digest}",
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
        
        # 启用鉴权但不存在任何凭据来源时，中间件无法认证任何调用方。
        # 此时必须显式失败（503 + 可操作提示），绝不能静默放行 —— 静默放行等于没有鉴权。
        #
        # S5 说明：本服务**只支持静态凭据**（环境变量 `API_KEYS` 里的 API Key），
        # 没有任何签发 JWT 的端点（全仓无 /login、/token 路由，
        # `JWTManager.create_access_token` 仅供单测与内部使用）。
        # 因此"只配 SECRET_KEY 不配 API_KEYS"仍会得到一个能验签却没有 token 可用的服务，
        # 下面的提示把 API Key 作为**首选**方案写出来，避免把运维逼向 ENABLE_AUTH=false。
        api_keys_configured = bool(_load_api_keys())
        self._credential_source_available = bool(self.config.SECRET_KEY or api_keys_configured)
        if not self._credential_source_available:
            logger.error(
                "ENABLE_AUTH 已启用，但既未配置 API_KEYS（推荐，客户端用 `X-API-Key` 直接调用），"
                "也未配置 SECRET_KEY / JWT_SECRET。本服务没有签发 JWT 的端点，"
                "只配 SECRET_KEY 无法获得可用凭据。所有非公开端点将返回 503。"
                "请配置 API_KEYS，或显式设置 ENABLE_AUTH=false 关闭鉴权。"
            )
        elif self.config.SECRET_KEY and not api_keys_configured:
            logger.warning(
                "已配置 SECRET_KEY 但未配置 API_KEYS：本服务没有签发 JWT 的端点，"
                "客户端需要一个由其它途径签发的 Token 才可用；"
                "一体化部署建议直接使用 API_KEYS + `X-API-Key`。"
            )
    
    def _is_public_path(self, path: str) -> bool:
        """检查是否为公开路径
        
        先精确匹配 PUBLIC_PATHS，再对 PUBLIC_PATH_PREFIXES 做前缀匹配。
        前缀匹配要求 path 恰好等于前缀或以「前缀 + /」开头，
        避免 /docs 误匹配 /docsomething、更避免 "/" 匹配全部路径。
        """
        # 精确匹配
        if path in self.config.PUBLIC_PATHS:
            return True
        
        # 前缀匹配（仅静态文档资源）
        for prefix in getattr(self.config, "PUBLIC_PATH_PREFIXES", []):
            if path == prefix or path.startswith(prefix + "/"):
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
        
        # 鉴权已启用却没有任何可用凭据来源 → 无法认证任何调用方，
        # 显式失败并给出可操作指引，而不是静默放行或返回令人困惑的 401。
        if not self._credential_source_available:
            logger.error(f"拒绝访问（鉴权未配置凭据）: {request.url.path}")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Auth Misconfigured",
                    "message": (
                        "认证已启用，但服务未配置任何可用凭据。"
                        "本服务当前只支持静态 API Key：请设置环境变量 "
                        "API_KEYS（客户端以 `X-API-Key: <key>` 调用），"
                        "或显式设置 ENABLE_AUTH=false 关闭鉴权。"
                        "（注意：本服务**没有**签发 JWT 的端点，"
                        "单独配置 SECRET_KEY 不产生可用凭据。）"
                    ),
                },
            )
        
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
