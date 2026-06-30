"""
动态限流中间件 - 支持根据请求类型和用户级别动态调整限流策略
"""

import time
import asyncio
from typing import Dict, Optional, Tuple
from collections import defaultdict
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger


class RateLimitConfig:
    """限流配置"""
    
    # 默认限流规则 (requests, seconds)
    DEFAULT_RULES = {
        # 健康检查 - 宽松限制
        "health": (100, 60),
        # 普通API - 标准限制
        "default": (30, 60),
        # 生成类API - 根据字数动态调整
        "generate": (10, 60),
        # 大章节生成 - 更宽松限制
        "generate_long": (5, 60),
        # 模型管理 - 严格限制
        "model_manage": (20, 60),
    }
    
    # 章节字数阈值
    LONG_CHAPTER_THRESHOLD = 5000  # 5000字以上视为长章节
    VERY_LONG_CHAPTER_THRESHOLD = 10000  # 10000字以上视为超长章节
    
    # 用户级别乘数
    USER_LEVEL_MULTIPLIERS = {
        "free": 1.0,
        "basic": 2.0,
        "premium": 5.0,
        "unlimited": 100.0,  # 几乎无限制
    }


class RateLimitStore:
    """限流存储（内存实现，可扩展为Redis）"""
    
    def __init__(self):
        self._store: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        检查限流
        
        返回: (是否允许, 剩余请求数, 重置时间)
        """
        async with self._lock:
            now = time.time()
            window_start = now - window_seconds
            
            # 清理过期记录
            self._store[key] = [
                t for t in self._store[key] 
                if t > window_start
            ]
            
            current_count = len(self._store[key])
            
            if current_count >= max_requests:
                # 已达限制
                oldest = self._store[key][0] if self._store[key] else now
                reset_time = int(oldest + window_seconds - now)
                return False, 0, max(0, reset_time)
            
            # 允许请求
            self._store[key].append(now)
            remaining = max_requests - current_count - 1
            reset_time = window_seconds
            
            return True, remaining, reset_time
    
    async def get_usage(self, key: str, window_seconds: int) -> int:
        """获取当前使用量"""
        async with self._lock:
            now = time.time()
            window_start = now - window_seconds
            return len([
                t for t in self._store[key] 
                if t > window_start
            ])


class DynamicRateLimiter(BaseHTTPMiddleware):
    """动态限流中间件"""
    
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.store = RateLimitStore()
    
    def _get_endpoint_category(self, path: str, method: str) -> str:
        """根据路径和方法确定端点类别"""
        if "/health" in path:
            return "health"
        elif "/generate" in path:
            return "generate"
        elif "/models" in path and method in ["POST", "DELETE"]:
            return "model_manage"
        else:
            return "default"
    
    def _estimate_chapter_length(self, request_body: Optional[dict]) -> int:
        """估算章节长度"""
        if not request_body:
            return 0
        
        # 从请求体中提取max_tokens作为估算
        max_tokens = request_body.get("max_tokens", 0)
        
        # 中文大约1.5-2 tokens/字
        estimated_words = max_tokens / 1.5
        
        return int(estimated_words)
    
    def _get_dynamic_limits(
        self, 
        category: str, 
        estimated_words: int,
        user_level: str = "free"
    ) -> Tuple[int, int]:
        """
        获取动态限流参数
        
        返回: (最大请求数, 窗口秒数)
        """
        # 基础限制
        if category == "generate" and estimated_words > self.config.VERY_LONG_CHAPTER_THRESHOLD:
            # 超长章节（1万字以上）
            max_requests, window = 3, 60  # 每分钟3次
            logger.info(f"超长章节限流: {estimated_words}字, 限制{max_requests}/{window}s")
        elif category == "generate" and estimated_words > self.config.LONG_CHAPTER_THRESHOLD:
            # 长章节（5000字以上）
            max_requests, window = 5, 60  # 每分钟5次
            logger.info(f"长章节限流: {estimated_words}字, 限制{max_requests}/{window}s")
        else:
            # 使用默认限制
            max_requests, window = self.config.DEFAULT_RULES.get(
                category, 
                self.config.DEFAULT_RULES["default"]
            )
        
        # 应用用户级别乘数
        multiplier = self.config.USER_LEVEL_MULTIPLIERS.get(user_level, 1.0)
        max_requests = int(max_requests * multiplier)
        
        return max_requests, window
    
    def _get_user_level(self, request: Request) -> str:
        """从请求中获取用户级别"""
        # 从JWT token或header中获取
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # TODO: 解析JWT获取用户级别
            # 这里暂时从header获取
            return request.headers.get("X-User-Level", "free")
        return "free"
    
    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识"""
        # 优先使用用户ID，其次使用IP
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # TODO: 解析JWT获取用户ID
            user_id = request.headers.get("X-User-Id")
            if user_id:
                return f"user:{user_id}"
        
        # 使用IP地址
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        return f"ip:{client_ip}"
    
    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 跳过不需要限流的路径
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # 获取端点类别
        category = self._get_endpoint_category(request.url.path, request.method)
        
        # 健康检查不限流
        if category == "health":
            return await call_next(request)
        
        # 获取客户端标识
        client_id = self._get_client_id(request)
        
        # 获取用户级别
        user_level = self._get_user_level(request)
        
        # 估算章节长度（仅对生成类API）
        estimated_words = 0
        if category == "generate":
            try:
                # 读取请求体
                body = await request.body()
                if body:
                    import json
                    request_body = json.loads(body)
                    estimated_words = self._estimate_chapter_length(request_body)
            except Exception:
                pass
        
        # 获取动态限流参数
        max_requests, window = self._get_dynamic_limits(
            category, estimated_words, user_level
        )
        
        # 构建限流key
        rate_limit_key = f"{client_id}:{category}"
        
        # 检查限流
        allowed, remaining, reset_time = await self.store.check_rate_limit(
            rate_limit_key, max_requests, window
        )
        
        if not allowed:
            logger.warning(f"限流触发: {client_id}, 类别: {category}, 估算字数: {estimated_words}")
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"请求过于频繁，请在{reset_time}秒后重试",
                    "retry_after": reset_time,
                    "limit": max_requests,
                    "window": window,
                    "category": category,
                    "estimated_words": estimated_words
                },
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time)
                }
            )
        
        # 处理请求
        response = await call_next(request)
        
        # 添加限流头
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window)
        
        return response


class RateLimitInfo:
    """限流信息（用于依赖注入）"""
    
    def __init__(self, limiter: DynamicRateLimiter):
        self.limiter = limiter
    
    async def get_usage(self, client_id: str, category: str) -> int:
        """获取当前使用量"""
        key = f"{client_id}:{category}"
        return await self.limiter.store.get_usage(key, 60)
    
    async def get_limits(
        self, 
        category: str, 
        estimated_words: int = 0,
        user_level: str = "free"
    ) -> Dict:
        """获取限流配置"""
        max_requests, window = self.limiter._get_dynamic_limits(
            category, estimated_words, user_level
        )
        return {
            "max_requests": max_requests,
            "window": window,
            "category": category,
            "estimated_words": estimated_words,
            "user_level": user_level
        }
