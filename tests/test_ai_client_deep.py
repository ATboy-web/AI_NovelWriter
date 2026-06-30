"""
ai_client.py 深度测试 - 真正调用方法
"""

import sys
import time
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.ai_client import TokenStats, AIMetrics, PromptManager, retry_with_backoff


class TestTokenStatsDeep:
    """TokenStats 深度测试"""

    def test_init_defaults(self):
        s = TokenStats()
        assert s.total_prompt_tokens == 0
        assert s.total_completion_tokens == 0
        assert s.total_tokens == 0
        assert s.request_count == 0

    def test_record_single(self):
        s = TokenStats()
        s.record(100, 50)
        assert s.total_prompt_tokens == 100
        assert s.total_completion_tokens == 50
        assert s.total_tokens == 150
        assert s.request_count == 1

    def test_record_multiple(self):
        s = TokenStats()
        s.record(100, 50)
        s.record(200, 100)
        s.record(300, 150)
        assert s.total_tokens == 900
        assert s.request_count == 3

    def test_record_zero(self):
        s = TokenStats()
        s.record(0, 0)
        assert s.total_tokens == 0
        assert s.request_count == 1

    def test_record_large(self):
        s = TokenStats()
        s.record(1000000, 500000)
        assert s.total_tokens == 1500000

    def test_get_summary(self):
        s = TokenStats()
        s.record(100, 50)
        summary = s.get_summary()
        assert summary["total_tokens"] == 150
        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 50
        assert summary["request_count"] == 1

    def test_get_display_small(self):
        s = TokenStats()
        s.record(100, 50)
        display = s.get_display()
        assert "150 tokens" in display
        assert "1次调用" in display

    def test_get_display_kilo(self):
        s = TokenStats()
        s.record(5000, 5000)
        display = s.get_display()
        assert "10.0K tokens" in display

    def test_get_display_mega(self):
        s = TokenStats()
        s.record(500000, 500000)
        display = s.get_display()
        assert "1.0M tokens" in display

    def test_thread_safety(self):
        s = TokenStats()
        def record_many():
            for _ in range(100):
                s.record(10, 5)
        threads = [threading.Thread(target=record_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert s.total_tokens == 15000
        assert s.request_count == 1000


class TestAIMetricsDeep:
    """AIMetrics 深度测试"""

    def test_init(self):
        m = AIMetrics()
        assert m.total_requests == 0
        assert m.total_tokens == 0
        assert m.errors == 0

    def test_record(self):
        m = AIMetrics()
        m.record(100, 0.5, cost=0.01)
        assert m.total_requests == 1
        assert m.total_tokens == 100
        assert m.total_cost == 0.01

    def test_record_error(self):
        m = AIMetrics()
        m.record(0, 0.1, error=True)
        assert m.errors == 1

    def test_get_summary(self):
        m = AIMetrics()
        m.record(100, 0.5, cost=0.01)
        summary = m.get_summary()
        assert "requests" in summary
        assert "tokens" in summary
        assert "cost_usd" in summary
        assert "errors" in summary
        assert "error_rate" in summary
        assert "avg_latency" in summary

    def test_avg_latency(self):
        m = AIMetrics()
        m.record(100, 0.5)
        m.record(100, 1.5)
        assert abs(m.avg_latency - 1.0) < 0.01

    def test_latency_samples_limit(self):
        m = AIMetrics()
        for i in range(150):
            m.record(100, 0.1)
        assert len(m._latency_samples) <= 100


class TestPromptManagerDeep:
    """PromptManager 深度测试"""

    def test_novel_prompts_exist(self):
        assert hasattr(PromptManager, 'NOVEL_PROMPTS')
        assert isinstance(PromptManager.NOVEL_PROMPTS, dict)

    def test_writer_prompt(self):
        assert "writer" in PromptManager.NOVEL_PROMPTS
        assert "system" in PromptManager.NOVEL_PROMPTS["writer"]

    def test_get_prompt(self):
        if hasattr(PromptManager, 'get_prompt'):
            prompt = PromptManager.get_prompt("writer")
            assert isinstance(prompt, str)

    def test_get_system_prompt(self):
        if hasattr(PromptManager, 'get_system_prompt'):
            prompt = PromptManager.get_system_prompt("writer")
            assert isinstance(prompt, str)


class TestRetryWithBackoffDeep:
    """retry_with_backoff 深度测试"""

    def test_success_first_try(self):
        call_count = 0
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def success():
            nonlocal call_count
            call_count += 1
            return "ok"
        assert success() == "ok"
        assert call_count == 1

    def test_success_after_retries(self):
        call_count = 0
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"
        assert fail_then_succeed() == "ok"
        assert call_count == 3

    def test_failure_after_max_retries(self):
        call_count = 0
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")
        with pytest.raises(ValueError):
            always_fail()
        assert call_count == 3

    def test_zero_retries(self):
        call_count = 0
        @retry_with_backoff(max_retries=0, base_delay=0.01)
        def fail_once():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")
        with pytest.raises(ValueError):
            fail_once()
        assert call_count == 1

    def test_different_exceptions(self):
        @retry_with_backoff(max_retries=1, base_delay=0.01)
        def type_error():
            raise TypeError("type")
        with pytest.raises(TypeError):
            type_error()
