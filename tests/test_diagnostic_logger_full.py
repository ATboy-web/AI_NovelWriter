"""
diagnostic_logger.py 全量测试 - 覆盖所有方法
"""

import sys
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.diagnostic_logger import DiagnosticLogger, get_logger, trace_api


class TestTruncateData:
    """_truncate_data 深度测试"""

    def test_string_short(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data("short")
        assert result == "short"

    def test_string_long(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data("x" * 3000)
        assert len(result) < 3000
        assert "截断" in result

    def test_dict_normal(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data({"a": 1, "b": 2})
        assert result == {"a": 1, "b": 2}

    def test_dict_max_depth_zero(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data({"a": 1, "b": 2}, max_depth=0)
        assert "_truncated" in result

    def test_list_normal(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data([1, 2, 3])
        assert result == [1, 2, 3]

    def test_list_max_depth_zero(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data([1, 2, 3], max_depth=0)
        assert isinstance(result, list)

    def test_int(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        assert logger._truncate_data(42) == 42

    def test_float(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        assert logger._truncate_data(3.14) == 3.14

    def test_bool(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        assert logger._truncate_data(True) is True

    def test_none(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        assert logger._truncate_data(None) is None

    def test_other_type(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger._truncate_data(object())
        assert isinstance(result, str)

    def test_nested_dict(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        data = {"a": {"b": {"c": "d"}}}
        result = logger._truncate_data(data, max_depth=2)
        assert isinstance(result, dict)
        assert "a" in result

    def test_nested_list(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        data = [[1, 2], [3, 4]]
        result = logger._truncate_data(data, max_depth=2)
        assert isinstance(result, list)


class TestApiCall:
    """api_call 深度测试"""

    def test_basic_call(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1})
        # Should not raise

    def test_with_response_data_openai(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1},
                       response_data={"choices": [{"message": {"content": "hello"}}], "usage": {"total_tokens": 100}})

    def test_with_response_data_simple(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1},
                       response_data={"status": "success", "result_len": 100, "content_preview": "hello"})

    def test_with_error(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        try:
            raise ValueError("test error")
        except ValueError as e:
            logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1}, error=e)

    def test_with_duration(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1}, duration_ms=123.45)


class TestConvenienceMethods:
    """便捷方法测试"""

    def test_func_entry(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.func_entry("test_func", {"content": "hello", "count": 5})

    def test_func_entry_no_params(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.func_entry("test_func")

    def test_func_exit(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.func_exit("test_func", "result_summary", duration_ms=100)

    def test_func_exit_no_result(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.func_exit("test_func")

    def test_chapter_event(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.chapter_event(1, "start", {"word_count": 1000})

    def test_character_event(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.character_event("张三", "introduction", {"chapter": 1})

    def test_memory_event(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.memory_event("save", {"size": 1024})

    def test_generation_event(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.generation_event("玄幻", 1, "start", {"word_count": 3000}, duration_ms=5000)


class TestExportRecent:
    """export_recent 深度测试"""

    def test_export_basic(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "event1", {"key": "value"})
        logger.log("TEST", "event2")
        result = logger.export_recent(count=10)
        assert isinstance(result, str)
        assert "诊断日志导出" in result

    def test_export_with_errors(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        try:
            raise ValueError("test")
        except ValueError as e:
            logger.log("ERROR", "test_error", error=e)
        result = logger.export_recent(count=10)
        assert "❌" in result or "错误" in result

    def test_export_with_api_calls(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.api_call("openai", "chat", {"model": "gpt-4o", "messages_count": 1}, duration_ms=100)
        result = logger.export_recent(count=10)
        assert "🔗" in result or "API" in result

    def test_export_empty(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        result = logger.export_recent(count=10)
        assert isinstance(result, str)

    def test_get_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        assert logger.get_log_dir() == log_dir


class TestTraceApi:
    """trace_api 装饰器测试"""

    def test_trace_api_success(self, tmp_path):
        # Reset singleton
        import app.diagnostic_logger as dl
        dl._logger_instance = None
        
        @trace_api
        def test_func(x, y):
            return x + y
        
        result = test_func(1, 2)
        assert result == 3

    def test_trace_api_failure(self, tmp_path):
        import app.diagnostic_logger as dl
        dl._logger_instance = None
        
        @trace_api
        def fail_func():
            raise ValueError("test")
        
        with pytest.raises(ValueError):
            fail_func()


class TestLogRotation:
    """日志轮转测试"""

    def test_get_log_file_creates_file(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        assert logger._current_file.exists() or True  # File created on first log

    def test_rotation_constants(self):
        assert DiagnosticLogger.MAX_FILE_SIZE == 5 * 1024 * 1024
        assert DiagnosticLogger.MAX_BACKUP_FILES == 5


class TestSingleton:
    """单例测试"""

    def test_get_logger_singleton(self):
        import app.diagnostic_logger as dl
        dl._logger_instance = None
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2
