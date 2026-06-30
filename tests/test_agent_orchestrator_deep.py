"""
agent_orchestrator.py 深度测试 - 真正调用方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.agent_orchestrator import AgentOrchestrator, ContextOptimizer


class TestAgentOrchestratorDeep:
    """AgentOrchestrator 深度测试"""

    def test_init(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        assert ao.ai == ai_client

    def test_init_with_log_callback(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        log_fn = MagicMock()
        ao = AgentOrchestrator(ai_client, log_callback=log_fn)
        assert ao.log == log_fn

    def test_shutdown(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        ao.shutdown(wait=False)

    def test_get_metrics(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.metrics.get_summary.return_value = {"total_tokens": 0}
        ao = AgentOrchestrator(ai_client)
        metrics = ao.get_metrics()
        assert "total_tokens" in metrics

    def test_run_parallel_empty(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([])
        assert results == []

    def test_run_parallel_single_task(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "test result"
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([{"name": "task1", "prompt": "test"}])
        assert len(results) == 1
        assert results[0]["success"] is True

    def test_run_parallel_multiple_tasks(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "result"
        ao = AgentOrchestrator(ai_client)
        tasks = [{"name": f"task{i}", "prompt": f"test{i}"} for i in range(3)]
        results = ao.run_parallel(tasks)
        assert len(results) == 3

    def test_run_parallel_task_failure(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.side_effect = Exception("API error")
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([{"name": "task1", "prompt": "test"}])
        assert len(results) == 1
        assert results[0]["success"] is False


class TestContextOptimizerDeep:
    """ContextOptimizer 深度测试"""

    def test_constants(self):
        assert ContextOptimizer.MAX_CONTEXT_CHARS == 8000
        assert "global_summary" in ContextOptimizer.COMPRESSION_RATIOS
        assert "volume_summary" in ContextOptimizer.COMPRESSION_RATIOS
        assert "characters" in ContextOptimizer.COMPRESSION_RATIOS
        assert "recent_chapters" in ContextOptimizer.COMPRESSION_RATIOS

    def test_compression_ratios_sum(self):
        total = sum(ContextOptimizer.COMPRESSION_RATIOS.values())
        assert total <= 1.0
