"""
agent_orchestrator.py 全量测试 - 覆盖所有方法
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.agent_orchestrator import AgentOrchestrator, ContextOptimizer, PromptOptimizer


class TestAgentOrchestratorFull:
    """AgentOrchestrator 全量测试"""

    def test_init(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        assert ao.ai == ai_client
        assert ao.metrics == ai_client.metrics

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
        ao.shutdown(wait=True)

    def test_shutdown_no_wait(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        ao.shutdown(wait=False)

    def test_get_metrics(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.metrics.get_summary.return_value = {"total_tokens": 100}
        ao = AgentOrchestrator(ai_client)
        metrics = ao.get_metrics()
        assert metrics == {"total_tokens": 100}

    def test_run_parallel_empty(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([])
        assert results == []

    def test_run_parallel_single_task(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "result"
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([{"name": "task1", "prompt": "test"}])
        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == "result"

    def test_run_parallel_multiple_tasks(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "result"
        ao = AgentOrchestrator(ai_client)
        tasks = [{"name": f"task{i}", "prompt": f"test{i}"} for i in range(5)]
        results = ao.run_parallel(tasks)
        assert len(results) == 5

    def test_run_parallel_task_failure(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.side_effect = Exception("API error")
        ao = AgentOrchestrator(ai_client)
        results = ao.run_parallel([{"name": "task1", "prompt": "test"}])
        assert len(results) == 1
        assert results[0]["success"] is False
        assert "API error" in results[0]["error"]

    def test_run_parallel_mixed_results(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.side_effect = ["result1", Exception("error"), "result3"]
        ao = AgentOrchestrator(ai_client)
        tasks = [{"name": f"task{i}", "prompt": f"test{i}"} for i in range(3)]
        results = ao.run_parallel(tasks)
        assert len(results) == 3
        success_count = sum(1 for r in results if r["success"])
        assert success_count == 2

    def test_execute_task(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "task result"
        ao = AgentOrchestrator(ai_client)
        result = ao._execute_task({"system": "sys", "prompt": "test", "max_tokens": 1000})
        assert result == "task result"

    def test_execute_task_no_system(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "task result"
        ao = AgentOrchestrator(ai_client)
        result = ao._execute_task({"prompt": "test"})
        assert result == "task result"

    def test_execute_task_no_max_tokens(self):
        ai_client = MagicMock()
        ai_client.metrics = MagicMock()
        ai_client.chat.return_value = "task result"
        ao = AgentOrchestrator(ai_client)
        result = ao._execute_task({"prompt": "test"})
        assert result == "task result"


class TestContextOptimizerFull:
    """ContextOptimizer 全量测试"""

    def test_constants(self):
        assert ContextOptimizer.MAX_CONTEXT_CHARS == 8000
        assert "global_summary" in ContextOptimizer.COMPRESSION_RATIOS
        assert "volume_summary" in ContextOptimizer.COMPRESSION_RATIOS
        assert "characters" in ContextOptimizer.COMPRESSION_RATIOS
        assert "recent_chapters" in ContextOptimizer.COMPRESSION_RATIOS
        assert "rag_results" in ContextOptimizer.COMPRESSION_RATIOS
        assert "extra" in ContextOptimizer.COMPRESSION_RATIOS

    def test_compression_ratios_sum(self):
        total = sum(ContextOptimizer.COMPRESSION_RATIOS.values())
        assert abs(total - 1.0) < 0.01

    def test_optimize_basic(self):
        sections = {
            "global_summary": "全局摘要内容",
            "volume_summary": "卷摘要内容",
            "characters": "角色信息",
        }
        result = ContextOptimizer.optimize(sections)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_optimize_with_max_chars(self):
        sections = {"global_summary": "x" * 10000}
        result = ContextOptimizer.optimize(sections, max_chars=100)
        assert len(result) <= 150

    def test_optimize_empty_sections(self):
        result = ContextOptimizer.optimize({})
        assert result == ""

    def test_optimize_all_empty(self):
        sections = {"global_summary": "", "volume_summary": "", "characters": ""}
        result = ContextOptimizer.optimize(sections)
        assert result == ""

    def test_optimize_with_budget_exceeded(self):
        sections = {
            "global_summary": "x" * 5000,
            "volume_summary": "y" * 5000,
            "characters": "z" * 5000,
        }
        result = ContextOptimizer.optimize(sections, max_chars=100)
        assert len(result) <= 200

    def test_truncate_short_text(self):
        result = ContextOptimizer._truncate("短文本", 1000)
        assert result == "短文本"

    def test_truncate_long_text(self):
        result = ContextOptimizer._truncate("x" * 1000, 100)
        assert len(result) <= 150
        assert "已压缩" in result

    def test_truncate_with_paragraph_boundary(self):
        text = "段落1\n\n段落2\n\n段落3\n\n段落4\n\n段落5"
        result = ContextOptimizer._truncate(text, 20)
        assert "已压缩" in result

    def test_truncate_with_sentence_boundary(self):
        text = "句子1。句子2。句子3。句子4。句子5。"
        result = ContextOptimizer._truncate(text, 15)
        assert "已压缩" in result


class TestPromptOptimizerFull:
    """PromptOptimizer 全量测试"""

    def test_optimize_prompt_short(self):
        result = PromptOptimizer.optimize_prompt("基础提示词", "上下文内容", max_tokens=4000)
        assert "基础提示词" in result
        assert "上下文内容" in result

    def test_optimize_prompt_long_context(self):
        long_context = "x" * 10000
        result = PromptOptimizer.optimize_prompt("基础提示词", long_context, max_tokens=1000)
        assert "基础提示词" in result

    def test_optimize_prompt_with_max_tokens(self):
        result = PromptOptimizer.optimize_prompt("提示词", "上下文", max_tokens=100)
        assert isinstance(result, str)
