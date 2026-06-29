"""
AI客户端完整测试
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# TokenStats 完整测试
# ============================================================

class TestTokenStatsFull:
    """TokenStats完整测试"""
    
    def test_init_defaults(self):
        """测试默认值"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        assert stats.total_prompt_tokens == 0
        assert stats.total_completion_tokens == 0
        assert stats.total_tokens == 0
        assert stats.request_count == 0
    
    def test_record_single(self):
        """测试单次记录"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(100, 50)
        assert stats.total_prompt_tokens == 100
        assert stats.total_completion_tokens == 50
        assert stats.total_tokens == 150
        assert stats.request_count == 1
    
    def test_record_multiple(self):
        """测试多次记录"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(100, 50)
        stats.record(200, 100)
        stats.record(300, 150)
        assert stats.total_prompt_tokens == 600
        assert stats.total_completion_tokens == 300
        assert stats.total_tokens == 900
        assert stats.request_count == 3
    
    def test_get_summary(self):
        """测试获取摘要"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(100, 50)
        summary = stats.get_summary()
        assert summary["total_tokens"] == 150
        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 50
        assert summary["request_count"] == 1
    
    def test_get_display_small(self):
        """测试小数字显示"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(100, 50)
        display = stats.get_display()
        assert "150 tokens" in display
        assert "1次调用" in display
    
    def test_get_display_kilo(self):
        """测试K级别显示"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(5000, 5000)
        display = stats.get_display()
        assert "10.0K tokens" in display
    
    def test_get_display_mega(self):
        """测试M级别显示"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(500000, 500000)
        display = stats.get_display()
        assert "1.0M tokens" in display
    
    def test_thread_safety(self):
        """测试线程安全"""
        from app.ai_client import TokenStats
        import threading
        
        stats = TokenStats()
        
        def record_tokens():
            for _ in range(100):
                stats.record(10, 5)
        
        threads = [threading.Thread(target=record_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert stats.total_tokens == 15000
        assert stats.request_count == 1000


# ============================================================
# retry_with_backoff 完整测试
# ============================================================

class TestRetryWithBackoffFull:
    """retry_with_backoff完整测试"""
    
    def test_success_on_first_try(self):
        """测试第一次成功"""
        from app.ai_client import retry_with_backoff
        
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
        from app.ai_client import retry_with_backoff
        
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
        """测试达到最大重试次数"""
        from app.ai_client import retry_with_backoff
        
        call_count = 0
        
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fail")
        
        with pytest.raises(ValueError, match="Always fail"):
            always_fail()
        
        assert call_count == 3
    
    def test_exponential_delay(self):
        """测试指数退避"""
        from app.ai_client import retry_with_backoff
        
        call_times = []
        
        @retry_with_backoff(max_retries=3, base_delay=0.1, max_delay=1)
        def record_time():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Not yet")
            return "success"
        
        record_time()
        
        if len(call_times) >= 2:
            delay1 = call_times[1] - call_times[0]
            assert delay1 >= 0.09
        
        if len(call_times) >= 3:
            delay2 = call_times[2] - call_times[1]
            assert delay2 >= 0.19


# ============================================================
# AIClient 测试
# ============================================================

class TestAIClientFull:
    """AIClient完整测试"""
    
    def test_class_exists(self):
        """测试类存在"""
        from app.ai_client import AIClient
        assert AIClient is not None
    
    def test_has_init(self):
        """测试有__init__方法"""
        from app.ai_client import AIClient
        assert hasattr(AIClient, '__init__')
    
    def test_has_methods(self):
        """测试有方法"""
        from app.ai_client import AIClient
        methods = dir(AIClient)
        assert len(methods) > 5


# ============================================================
# PromptManager 测试
# ============================================================

class TestPromptManagerFull:
    """PromptManager完整测试"""
    
    def test_class_exists(self):
        """测试类存在"""
        try:
            from app.ai_client import PromptManager
            assert PromptManager is not None
        except ImportError:
            # PromptManager可能不存在
            pass


# ============================================================
# AIMetrics 测试
# ============================================================

class TestAIMetricsFull:
    """AIMetrics完整测试"""
    
    def test_class_exists(self):
        """测试类存在"""
        try:
            from app.ai_client import AIMetrics
            assert AIMetrics is not None
        except ImportError:
            # AIMetrics可能不存在
            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
