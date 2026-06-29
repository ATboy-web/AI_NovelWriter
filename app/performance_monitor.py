"""
性能监控模块
记录应用性能指标：响应时间、错误率、吞吐量
"""

import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from functools import wraps
import json
from pathlib import Path


@dataclass
class RequestMetric:
    """请求指标"""
    path: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: float
    error: Optional[str] = None


@dataclass
class PerformanceStats:
    """性能统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: float = 0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0
    p50_duration_ms: float = 0
    p95_duration_ms: float = 0
    p99_duration_ms: float = 0
    error_rate: float = 0
    requests_per_second: float = 0


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 10000):
        self._lock = threading.Lock()
        self._max_history = max_history
        
        # 请求历史
        self._request_history: deque = deque(maxlen=max_history)
        
        # 按路径统计
        self._path_stats: Dict[str, List[float]] = defaultdict(list)
        
        # 错误统计
        self._error_counts: Dict[str, int] = defaultdict(int)
        
        # 时间窗口统计（最近1分钟）
        self._window_requests: deque = deque()
        self._window_duration_ms: float = 0
        
        # 启动时间
        self._start_time = time.time()
    
    def record_request(
        self,
        path: str,
        method: str,
        status_code: int,
        duration_ms: float,
        error: Optional[str] = None
    ):
        """记录请求指标"""
        now = time.time()
        
        metric = RequestMetric(
            path=path,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=now,
            error=error
        )
        
        with self._lock:
            # 添加到历史
            self._request_history.append(metric)
            
            # 更新路径统计
            self._path_stats[path].append(duration_ms)
            
            # 更新错误统计
            if status_code >= 400:
                error_key = f"{status_code}:{path}"
                self._error_counts[error_key] += 1
            
            # 更新时间窗口
            self._window_requests.append((now, duration_ms))
            self._window_duration_ms += duration_ms
            
            # 清理过期的窗口数据（超过1分钟）
            cutoff = now - 60
            while self._window_requests and self._window_requests[0][0] < cutoff:
                _, expired_duration = self._window_requests.popleft()
                self._window_duration_ms -= expired_duration
    
    def get_stats(self) -> PerformanceStats:
        """获取性能统计"""
        with self._lock:
            if not self._request_history:
                return PerformanceStats()
            
            # 计算基本统计
            total = len(self._request_history)
            successful = sum(1 for m in self._request_history if m.status_code < 400)
            failed = total - successful
            
            # 计算响应时间统计
            durations = sorted([m.duration_ms for m in self._request_history])
            total_duration = sum(durations)
            
            # 计算百分位数
            p50_idx = int(total * 0.5)
            p95_idx = int(total * 0.95)
            p99_idx = int(total * 0.99)
            
            # 计算时间窗口内的RPS
            window_count = len(self._window_requests)
            rps = window_count / 60 if window_count > 0 else 0
            
            return PerformanceStats(
                total_requests=total,
                successful_requests=successful,
                failed_requests=failed,
                total_duration_ms=total_duration,
                min_duration_ms=durations[0] if durations else 0,
                max_duration_ms=durations[-1] if durations else 0,
                p50_duration_ms=durations[p50_idx] if p50_idx < total else 0,
                p95_duration_ms=durations[p95_idx] if p95_idx < total else 0,
                p99_duration_ms=durations[p99_idx] if p99_idx < total else 0,
                error_rate=failed / total if total > 0 else 0,
                requests_per_second=rps
            )
    
    def get_path_stats(self) -> Dict[str, Dict]:
        """获取按路径分组的统计"""
        with self._lock:
            stats = {}
            for path, durations in self._path_stats.items():
                if not durations:
                    continue
                
                sorted_durations = sorted(durations)
                total = len(sorted_durations)
                
                stats[path] = {
                    "count": total,
                    "avg_ms": sum(sorted_durations) / total,
                    "min_ms": sorted_durations[0],
                    "max_ms": sorted_durations[-1],
                    "p50_ms": sorted_durations[int(total * 0.5)] if total > 0 else 0,
                    "p95_ms": sorted_durations[int(total * 0.95)] if total > 0 else 0
                }
            
            return stats
    
    def get_error_stats(self) -> Dict[str, int]:
        """获取错误统计"""
        with self._lock:
            return dict(self._error_counts)
    
    def get_slow_requests(self, threshold_ms: float = 1000) -> List[RequestMetric]:
        """获取慢请求"""
        with self._lock:
            return [m for m in self._request_history if m.duration_ms > threshold_ms]
    
    def get_uptime(self) -> float:
        """获取运行时间（秒）"""
        return time.time() - self._start_time
    
    def reset(self):
        """重置统计"""
        with self._lock:
            self._request_history.clear()
            self._path_stats.clear()
            self._error_counts.clear()
            self._window_requests.clear()
            self._window_duration_ms = 0
            self._start_time = time.time()
    
    def export_metrics(self) -> Dict:
        """导出指标（用于Prometheus）"""
        stats = self.get_stats()
        path_stats = self.get_path_stats()
        error_stats = self.get_error_stats()
        
        return {
            "timestamp": time.time(),
            "uptime_seconds": self.get_uptime(),
            "summary": {
                "total_requests": stats.total_requests,
                "successful_requests": stats.successful_requests,
                "failed_requests": stats.failed_requests,
                "error_rate": stats.error_rate,
                "requests_per_second": stats.requests_per_second,
                "response_time": {
                    "avg_ms": stats.total_duration_ms / stats.total_requests if stats.total_requests > 0 else 0,
                    "min_ms": stats.min_duration_ms,
                    "max_ms": stats.max_duration_ms,
                    "p50_ms": stats.p50_duration_ms,
                    "p95_ms": stats.p95_duration_ms,
                    "p99_ms": stats.p99_duration_ms
                }
            },
            "paths": path_stats,
            "errors": error_stats
        }
    
    def save_report(self, filepath: str):
        """保存性能报告"""
        report = self.export_metrics()
        
        # 确保目录存在
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


# 全局性能监控器实例
_performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    return _performance_monitor


def monitor_performance(func):
    """性能监控装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        error = None
        status_code = 200
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error = str(e)
            status_code = 500
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            
            # 获取函数信息
            path = f"{func.__module__}.{func.__qualname__}"
            method = "CALL"
            
            # 记录指标
            _performance_monitor.record_request(
                path=path,
                method=method,
                status_code=status_code,
                duration_ms=duration_ms,
                error=error
            )
    
    return wrapper


class PerformanceMiddleware:
    """性能监控中间件（用于Web框架）"""
    
    def __init__(self, app=None):
        self.app = app
        self.monitor = get_performance_monitor()
    
    def __call__(self, environ, start_response):
        """WSGI中间件"""
        start_time = time.time()
        
        def custom_start_response(status, headers, exc_info=None):
            # 计算响应时间
            duration_ms = (time.time() - start_time) * 1000
            
            # 获取状态码
            status_code = int(status.split()[0])
            
            # 记录指标
            self.monitor.record_request(
                path=environ.get('PATH_INFO', '/'),
                method=environ.get('REQUEST_METHOD', 'GET'),
                status_code=status_code,
                duration_ms=duration_ms
            )
            
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)


def create_prometheus_metrics() -> str:
    """创建Prometheus格式的指标"""
    monitor = get_performance_monitor()
    stats = monitor.get_stats()
    path_stats = monitor.get_path_stats()
    
    lines = []
    
    # 总请求数
    lines.append(f'# HELP http_requests_total Total number of HTTP requests')
    lines.append(f'# TYPE http_requests_total counter')
    lines.append(f'http_requests_total {stats.total_requests}')
    
    # 成功请求数
    lines.append(f'# HELP http_requests_successful Successful HTTP requests')
    lines.append(f'# TYPE http_requests_successful counter')
    lines.append(f'http_requests_successful {stats.successful_requests}')
    
    # 失败请求数
    lines.append(f'# HELP http_requests_failed Failed HTTP requests')
    lines.append(f'# TYPE http_requests_failed counter')
    lines.append(f'http_requests_failed {stats.failed_requests}')
    
    # 错误率
    lines.append(f'# HELP http_error_rate HTTP error rate')
    lines.append(f'# TYPE http_error_rate gauge')
    lines.append(f'http_error_rate {stats.error_rate}')
    
    # 每秒请求数
    lines.append(f'# HELP http_requests_per_second HTTP requests per second')
    lines.append(f'# TYPE http_requests_per_second gauge')
    lines.append(f'http_requests_per_second {stats.requests_per_second}')
    
    # 响应时间
    lines.append(f'# HELP http_response_time_ms HTTP response time in milliseconds')
    lines.append(f'# TYPE http_response_time_ms summary')
    lines.append(f'http_response_time_ms{{quantile="0.5"}} {stats.p50_duration_ms}')
    lines.append(f'http_response_time_ms{{quantile="0.95"}} {stats.p95_duration_ms}')
    lines.append(f'http_response_time_ms{{quantile="0.99"}} {stats.p99_duration_ms}')
    
    # 按路径统计
    for path, path_stat in path_stats.items():
        safe_path = path.replace('"', '\\"').replace('\n', '\\n')
        lines.append(f'http_path_requests{{path="{safe_path}"}} {path_stat["count"]}')
        lines.append(f'http_path_avg_ms{{path="{safe_path}"}} {path_stat["avg_ms"]}')
    
    return '\n'.join(lines)
