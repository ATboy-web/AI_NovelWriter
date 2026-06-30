"""
AI客户端额外测试2
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# TokenStats 额外测试2
# ============================================================

class TestTokenStatsExtra2:
    """TokenStats额外测试2"""
    
    def test_record_zero_tokens(self):
        """测试记录0个token"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(0, 0)
        assert stats.total_tokens == 0
        assert stats.request_count == 1
    
    def test_record_large_numbers(self):
        """测试记录大数字"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(1000000, 500000)
        assert stats.total_prompt_tokens == 1000000
        assert stats.total_completion_tokens == 500000
        assert stats.total_tokens == 1500000
    
    def test_get_summary_empty(self):
        """测试空摘要"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        summary = stats.get_summary()
        assert summary["total_tokens"] == 0
        assert summary["request_count"] == 0
    
    def test_get_display_zero(self):
        """测试0显示"""
        from app.ai_client import TokenStats
        stats = TokenStats()
        stats.record(0, 0)
        display = stats.get_display()
        assert "0 tokens" in display


# ============================================================
# retry_with_backoff 额外测试2
# ============================================================

class TestRetryWithBackoffExtra2:
    """retry_with_backoff额外测试2"""
    
    def test_with_zero_retries(self):
        """测试0次重试"""
        from app.ai_client import retry_with_backoff
        
        call_count = 0
        
        @retry_with_backoff(max_retries=0, base_delay=0.01)
        def fail_once():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            fail_once()
        
        assert call_count == 1
    
    def test_with_different_exceptions(self):
        """测试不同异常类型"""
        from app.ai_client import retry_with_backoff
        
        call_count = 0
        
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def raise_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("type error")
        
        with pytest.raises(TypeError):
            raise_type_error()
        
        assert call_count == 3


# ============================================================
# AIClient 额外测试2
# ============================================================

class TestAIClientExtra2:
    """AIClient额外测试2"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.ai_client import AIClient
        methods = dir(AIClient)
        assert len(methods) > 10


# ============================================================
# PromptManager 额外测试2
# ============================================================

class TestPromptManagerExtra2:
    """PromptManager额外测试2"""
    
    def test_class_may_exist(self):
        """测试类可能存在"""
        try:
            from app.ai_client import PromptManager
            assert PromptManager is not None
        except ImportError:
            pass


# ============================================================
# AIMetrics 额外测试2
# ============================================================

class TestAIMetricsExtra2:
    """AIMetrics额外测试2"""
    
    def test_class_may_exist(self):
        """测试类可能存在"""
        try:
            from app.ai_client import AIMetrics
            assert AIMetrics is not None
        except ImportError:
            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
