"""
AI客户端模块单元测试
测试TokenStats、重试机制等核心功能
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


import httpx
import pytest

from app.ai_client import TokenStats, _is_transient_error


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


class TestIsTransientError:
    """M1: 判定「重试是否值得」的辅助函数。

    原 `retry_with_backoff` 装饰器无差别重试一切异常（含 400/401），
    已在第三轮修复中删除；保留其唯一有价值的语义（哪些错误值得重试）
    供 `_dispatch_with_retry` 复用，并在此固定为回归断言。
    """

    @staticmethod
    def _status_error(code: int) -> httpx.HTTPStatusError:
        req = httpx.Request("POST", "https://api.example.com/v1/chat")
        resp = httpx.Response(code, request=req)
        return httpx.HTTPStatusError("boom", request=req, response=resp)

    def test_timeout_is_transient(self):
        assert _is_transient_error(httpx.TimeoutException("t")) is True

    def test_connect_error_is_transient(self):
        assert _is_transient_error(httpx.ConnectError("c")) is True

    def test_429_and_5xx_are_transient(self):
        for code in (429, 500, 502, 503):
            assert _is_transient_error(self._status_error(code)) is True, code

    def test_client_errors_are_not_transient(self):
        for code in (400, 401, 403, 404, 422):
            assert _is_transient_error(self._status_error(code)) is False, code

    def test_plain_exception_is_not_transient(self):
        assert _is_transient_error(ValueError("x")) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
