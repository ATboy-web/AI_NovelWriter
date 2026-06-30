"""
请求日志中间件 - 记录API请求和响应信息
"""

import time
import json
from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class RequestLoggerConfig:
    """请求日志配置"""
    
    # 是否记录请求体
    LOG_REQUEST_BODY = True
    
    # 是否记录响应体
    LOG_RESPONSE_BODY = False  # 默认关闭，避免日志过大
    
    # 最大记录的请求体大小（字节）
    MAX_BODY_SIZE = 10240  # 10KB
    
    # 不记录的路径
    EXCLUDED_PATHS = [
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]
    
    # 敏感字段（不记录）
    SENSITIVE_FIELDS = [
        "password",
        "token",
        "secret",
        "api_key",
        "authorization",
    ]


class RequestLogger(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    def __init__(self, app, config: Optional[RequestLoggerConfig] = None):
        super().__init__(app)
        self.config = config or RequestLoggerConfig()
    
    def _should_log(self, path: str) -> bool:
        """检查是否应该记录"""
        for excluded in self.config.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return False
        return True
    
    def _sanitize_body(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """清理敏感字段"""
        sanitized = {}
        for key, value in body.items():
            if key.lower() in self.config.SENSITIVE_FIELDS:
                sanitized[key] = "***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_body(value)
            else:
                sanitized[key] = value
        return sanitized
    
    async def _read_body(self, request: Request) -> Optional[Dict]:
        """读取请求体"""
        if not self.config.LOG_REQUEST_BODY:
            return None
        
        if request.method in ["GET", "DELETE"]:
            return None
        
        try:
            body = await request.body()
            if len(body) > self.config.MAX_BODY_SIZE:
                return {"_truncated": True, "_size": len(body)}
            
            if body:
                return json.loads(body)
        except Exception:
            pass
        
        return None
    
    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 检查是否应该记录
        if not self._should_log(request.url.path):
            return await call_next(request)
        
        # 记录开始时间
        start_time = time.time()
        
        # 获取客户端信息
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        # 读取请求体
        request_body = await self._read_body(request)
        
        # 构建请求日志
        request_log = {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) if request.query_params else None,
            "client_ip": client_ip,
            "user_agent": request.headers.get("User-Agent", ""),
        }
        
        if request_body:
            request_log["body"] = self._sanitize_body(request_body)
        
        # 记录用户信息
        user = getattr(request.state, "user", None)
        if user:
            request_log["user_id"] = user.get("user_id")
            request_log["user_level"] = user.get("level")
        
        logger.info(f"请求开始: {request.method} {request.url.path}", **request_log)
        
        # 处理请求
        try:
            response = await call_next(request)
            
            # 计算耗时
            duration = time.time() - start_time
            
            # 记录响应
            response_log = {
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            }
            
            # 记录限流信息
            rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
            if rate_limit_remaining:
                response_log["rate_limit_remaining"] = rate_limit_remaining
            
            if response.status_code >= 400:
                logger.warning(
                    f"请求失败: {request.method} {request.url.path}",
                    **response_log
                )
            else:
                logger.info(
                    f"请求完成: {request.method} {request.url.path}",
                    **response_log
                )
            
            return response
            
        except Exception as e:
            # 记录异常
            duration = time.time() - start_time
            logger.error(
                f"请求异常: {request.method} {request.url.path}",
                error=str(e),
                duration_ms=round(duration * 1000, 2)
            )
            raise


class PerformanceMonitor:
    """性能监控"""
    
    def __init__(self):
        self._metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0,
            "max_duration_ms": 0,
            "min_duration_ms": float("inf"),
        }
        self._endpoint_metrics = {}
    
    def record_request(
        self, 
        path: str, 
        method: str, 
        status_code: int, 
        duration_ms: float
    ):
        """记录请求指标"""
        self._metrics["total_requests"] += 1
        self._metrics["total_duration_ms"] += duration_ms
        
        if status_code < 400:
            self._metrics["successful_requests"] += 1
        else:
            self._metrics["failed_requests"] += 1
        
        self._metrics["max_duration_ms"] = max(
            self._metrics["max_duration_ms"], 
            duration_ms
        )
        self._metrics["min_duration_ms"] = min(
            self._metrics["min_duration_ms"], 
            duration_ms
        )
        
        # 端点级别指标
        endpoint_key = f"{method}:{path}"
        if endpoint_key not in self._endpoint_metrics:
            self._endpoint_metrics[endpoint_key] = {
                "count": 0,
                "total_duration_ms": 0,
                "errors": 0,
            }
        
        self._endpoint_metrics[endpoint_key]["count"] += 1
        self._endpoint_metrics[endpoint_key]["total_duration_ms"] += duration_ms
        
        if status_code >= 400:
            self._endpoint_metrics[endpoint_key]["errors"] += 1
    
    def get_metrics(self) -> Dict:
        """获取性能指标"""
        metrics = self._metrics.copy()
        
        if metrics["total_requests"] > 0:
            metrics["avg_duration_ms"] = round(
                metrics["total_duration_ms"] / metrics["total_requests"], 
                2
            )
            metrics["success_rate"] = round(
                metrics["successful_requests"] / metrics["total_requests"] * 100, 
                2
            )
        else:
            metrics["avg_duration_ms"] = 0
            metrics["success_rate"] = 0
        
        # 端点级别指标
        endpoint_metrics = {}
        for key, data in self._endpoint_metrics.items():
            if data["count"] > 0:
                endpoint_metrics[key] = {
                    "count": data["count"],
                    "avg_duration_ms": round(
                        data["total_duration_ms"] / data["count"], 
                        2
                    ),
                    "error_rate": round(
                        data["errors"] / data["count"] * 100, 
                        2
                    ),
                }
        
        metrics["endpoints"] = endpoint_metrics
        
        return metrics
    
    def reset(self):
        """重置指标"""
        self._metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0,
            "max_duration_ms": 0,
            "min_duration_ms": float("inf"),
        }
        self._endpoint_metrics = {}


# 全局性能监控实例
performance_monitor = PerformanceMonitor()
