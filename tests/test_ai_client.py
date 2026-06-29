"""
AI客户端模块单元测试
测试TokenStats、重试机制等核心功能
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.ai_client import TokenStats, retry_with_backoff


class TestTokenStats:
    """TokenStats 测试套件"""
    
    @pytest.fixture
    def stats(self):
        return TokenStats()
    
    def test_initial_state(self, stats):
        """测试初始状态"""
        assert stats.total_tokens == 0
        assert stats.total_prompt_tokens == 0
        assert stats.total_completion_tokens == 0
        assert stats.request_count == 0
    
    def test_record_single(self, stats):
        """测试单次记录"""
        stats.record(100, 50)
        assert stats.total_prompt_tokens == 100
        assert stats.total_completion_tokens == 50
        assert stats.total_tokens == 150
        assert stats.request_count == 1
    
    def test_record_multiple(self, stats):
        """测试多次记录"""
        stats.record(100, 50)
        stats.record(200, 100)
        stats.record(300, 150)
        
        assert stats.total_prompt_tokens == 600
        assert stats.total_completion_tokens == 300
        assert stats.total_tokens == 900
        assert stats.request_count == 3
    
    def test_get_summary(self, stats):
        """测试获取摘要"""
        stats.record(100, 50)
        summary = stats.get_summary()
        
        assert summary["total_tokens"] == 150
        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 50
        assert summary["request_count"] == 1
    
    def test_get_display_small(self, stats):
        """测试小数字显示"""
        stats.record(100, 50)
        display = stats.get_display()
        assert "150 tokens" in display
        assert "1次调用" in display
    
    def test_get_display_kilo(self, stats):
        """测试K级别显示"""
        stats.record(5000, 5000)
        display = stats.get_display()
        assert "10.0K tokens" in display
    
    def test_get_display_mega(self, stats):
        """测试M级别显示"""
        stats.record(500000, 500000)
        display = stats.get_display()
        assert "1.0M tokens" in display
    
    def test_thread_safety(self, stats):
        """测试线程安全性"""
        import threading
        
        def record_tokens():
            for _ in range(100):
                stats.record(10, 5)
        
        threads = [threading.Thread(target=record_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert stats.total_tokens == 15000  # 100 * 10 * 15
        assert stats.request_count == 1000  # 100 * 10


class TestRetryWithBackoff:
    """重试机制测试套件"""
    
    def test_success_on_first_try(self):
        """测试第一次就成功"""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = success_func()
        assert result == "success"
        assert call_count == 1
    
    def test_success_after_retries(self):
        """测试重试后成功"""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        result = fail_then_succeed()
        assert result == "success"
        assert call_count == 3
    
    def test_failure_after_max_retries(self):
        """测试达到最大重试次数后失败"""
        call_count = 0
        
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fail")
        
        with pytest.raises(ValueError, match="Always fail"):
            always_fail()
        
        assert call_count == 3  # 初始调用 + 2次重试
    
    def test_exponential_delay(self):
        """测试指数退避延迟"""
        call_times = []
        
        @retry_with_backoff(max_retries=3, base_delay=0.1, max_delay=1)
        def record_time():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Not yet")
            return "success"
        
        record_time()
        
        # 验证延迟递增（允许一定误差）
        if len(call_times) >= 2:
            delay1 = call_times[1] - call_times[0]
            assert delay1 >= 0.09  # 约0.1秒
        
        if len(call_times) >= 3:
            delay2 = call_times[2] - call_times[1]
            assert delay2 >= 0.19  # 约0.2秒
    
    def test_max_delay_cap(self):
        """测试最大延迟上限"""
        call_times = []
        
        @retry_with_backoff(max_retries=5, base_delay=10, max_delay=0.1)
        def record_time():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Not yet")
            return "success"
        
        record_time()
        
        # 验证延迟不超过max_delay
        if len(call_times) >= 2:
            delay = call_times[1] - call_times[0]
            assert delay <= 0.15  # 约0.1秒，留一定误差


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
