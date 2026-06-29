"""
性能监控模块测试
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.performance_monitor import (
    PerformanceMonitor,
    PerformanceStats,
    RequestMetric,
    monitor_performance,
    create_prometheus_metrics
)


class TestPerformanceMonitor:
    """PerformanceMonitor 测试套件"""
    
    @pytest.fixture
    def monitor(self):
        """创建新的监控器实例"""
        return PerformanceMonitor(max_history=100)
    
    def test_initial_state(self, monitor):
        """测试初始状态"""
        stats = monitor.get_stats()
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.error_rate == 0
    
    def test_record_request(self, monitor):
        """测试记录请求"""
        monitor.record_request(
            path="/api/test",
            method="GET",
            status_code=200,
            duration_ms=100.0
        )
        
        stats = monitor.get_stats()
        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.failed_requests == 0
    
    def test_record_error_request(self, monitor):
        """测试记录错误请求"""
        monitor.record_request(
            path="/api/test",
            method="POST",
            status_code=500,
            duration_ms=50.0,
            error="Internal Server Error"
        )
        
        stats = monitor.get_stats()
        assert stats.total_requests == 1
        assert stats.successful_requests == 0
        assert stats.failed_requests == 1
        assert stats.error_rate == 1.0
    
    def test_multiple_requests(self, monitor):
        """测试多个请求"""
        # 记录多个请求
        for i in range(10):
            monitor.record_request(
                path="/api/test",
                method="GET",
                status_code=200 if i < 8 else 500,
                duration_ms=100.0 + i * 10
            )
        
        stats = monitor.get_stats()
        assert stats.total_requests == 10
        assert stats.successful_requests == 8
        assert stats.failed_requests == 2
        assert stats.error_rate == 0.2
    
    def test_response_time_stats(self, monitor):
        """测试响应时间统计"""
        durations = [10, 20, 30, 40, 50, 100, 200, 300, 400, 1000]
        
        for duration in durations:
            monitor.record_request(
                path="/api/test",
                method="GET",
                status_code=200,
                duration_ms=duration
            )
        
        stats = monitor.get_stats()
        assert stats.min_duration_ms == 10
        assert stats.max_duration_ms == 1000
        # P50是第50百分位数，索引为5（10*0.5），对应值100
        assert stats.p50_duration_ms == 100
        assert stats.p95_duration_ms == 1000  # P95
    
    def test_path_stats(self, monitor):
        """测试按路径统计"""
        # 记录不同路径的请求
        monitor.record_request("/api/users", "GET", 200, 100)
        monitor.record_request("/api/users", "GET", 200, 150)
        monitor.record_request("/api/posts", "GET", 200, 200)
        monitor.record_request("/api/posts", "POST", 500, 50)
        
        path_stats = monitor.get_path_stats()
        
        assert "/api/users" in path_stats
        assert "/api/posts" in path_stats
        assert path_stats["/api/users"]["count"] == 2
        assert path_stats["/api/posts"]["count"] == 2
    
    def test_error_stats(self, monitor):
        """测试错误统计"""
        monitor.record_request("/api/test", "GET", 500, 100)
        monitor.record_request("/api/test", "GET", 500, 100)
        monitor.record_request("/api/other", "POST", 404, 50)
        
        error_stats = monitor.get_error_stats()
        
        assert "500:/api/test" in error_stats
        assert error_stats["500:/api/test"] == 2
        assert "404:/api/other" in error_stats
    
    def test_slow_requests(self, monitor):
        """测试慢请求检测"""
        # 记录一些请求
        monitor.record_request("/api/fast", "GET", 200, 100)
        monitor.record_request("/api/slow", "GET", 200, 2000)
        monitor.record_request("/api/medium", "GET", 200, 500)
        
        slow_requests = monitor.get_slow_requests(threshold_ms=1000)
        
        assert len(slow_requests) == 1
        assert slow_requests[0].path == "/api/slow"
    
    def test_max_history(self, monitor):
        """测试最大历史记录限制"""
        # 记录超过最大限制的请求
        for i in range(150):
            monitor.record_request(
                path=f"/api/test/{i}",
                method="GET",
                status_code=200,
                duration_ms=100
            )
        
        # 应该只保留最近100条
        assert len(monitor._request_history) == 100
    
    def test_reset(self, monitor):
        """测试重置"""
        monitor.record_request("/api/test", "GET", 200, 100)
        monitor.reset()
        
        stats = monitor.get_stats()
        assert stats.total_requests == 0
    
    def test_export_metrics(self, monitor):
        """测试导出指标"""
        monitor.record_request("/api/test", "GET", 200, 100)
        monitor.record_request("/api/test", "GET", 500, 200)
        
        metrics = monitor.export_metrics()
        
        assert "timestamp" in metrics
        assert "uptime_seconds" in metrics
        assert "summary" in metrics
        assert "paths" in metrics
        assert "errors" in metrics
        
        assert metrics["summary"]["total_requests"] == 2
        assert metrics["summary"]["error_rate"] == 0.5
    
    def test_uptime(self, monitor):
        """测试运行时间"""
        uptime = monitor.get_uptime()
        assert uptime >= 0
        assert uptime < 1  # 刚创建


class TestMonitorPerformanceDecorator:
    """性能监控装饰器测试"""
    
    def test_successful_function(self):
        """测试成功执行的函数"""
        @monitor_performance
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_failed_function(self):
        """测试失败的函数"""
        @monitor_performance
        def test_func():
            raise ValueError("test error")
        
        with pytest.raises(ValueError, match="test error"):
            test_func()
    
    def test_records_metrics(self):
        """测试记录指标"""
        monitor = PerformanceMonitor()
        
        @monitor_performance
        def test_func():
            time.sleep(0.01)
            return "done"
        
        # 替换全局监控器
        import app.performance_monitor as pm
        old_monitor = pm._performance_monitor
        pm._performance_monitor = monitor
        
        try:
            test_func()
            
            stats = monitor.get_stats()
            assert stats.total_requests == 1
            assert stats.successful_requests == 1
        finally:
            pm._performance_monitor = old_monitor


class TestPrometheusMetrics:
    """Prometheus指标测试"""
    
    def test_create_prometheus_metrics(self):
        """测试创建Prometheus指标"""
        monitor = PerformanceMonitor()
        monitor.record_request("/api/test", "GET", 200, 100)
        monitor.record_request("/api/test", "GET", 200, 200)
        
        # 替换全局监控器
        import app.performance_monitor as pm
        old_monitor = pm._performance_monitor
        pm._performance_monitor = monitor
        
        try:
            metrics = create_prometheus_metrics()
            
            assert "http_requests_total" in metrics
            assert "http_requests_successful" in metrics
            assert "http_requests_failed" in metrics
            assert "http_error_rate" in metrics
            assert "http_response_time_ms" in metrics
        finally:
            pm._performance_monitor = old_monitor


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
