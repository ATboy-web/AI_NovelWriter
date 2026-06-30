"""
diagnostic_logger.py 深度测试 - 真正调用方法
"""

import sys
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.diagnostic_logger import DiagnosticLogger, get_logger


class TestDiagnosticLoggerDeep:
    """DiagnosticLogger 深度测试"""

    def test_init_creates_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        assert log_dir.exists()

    def test_log_writes_to_file(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "test_event", {"key": "value"})
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) > 0
        
        content = log_files[0].read_text(encoding="utf-8").strip()
        assert len(content) > 0

    def test_log_with_error(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        try:
            raise ValueError("test error")
        except ValueError as e:
            logger.log("ERROR", "test_error", error=e)
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) > 0

    def test_log_with_duration(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("PERF", "test_perf", duration_ms=123.45)
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) > 0

    def test_log_sequence_increments(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        initial = logger._sequence
        logger.log("TEST", "event1")
        logger.log("TEST", "event2")
        assert logger._sequence == initial + 2

    def test_session_id_format(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        parts = logger._session_id.split('-')
        assert len(parts) >= 3

    def test_log_json_lines_format(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "event1", {"a": 1})
        logger.log("TEST", "event2", {"b": 2})
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        lines = log_files[0].read_text(encoding="utf-8").strip().split('\n')
        
        for line in lines:
            data = json.loads(line)
            assert isinstance(data, dict)

    def test_log_contains_required_fields(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "test_event", {"key": "value"})
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        lines = log_files[0].read_text(encoding="utf-8").strip().split('\n')
        
        data = json.loads(lines[-1])
        assert "timestamp" in data or "ts" in data or "time" in data

    def test_log_multiple_categories(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        categories = ["API_CALL", "FUNC_ENTRY", "FUNC_EXIT", "ERROR", "SYSTEM", "CHAPTER"]
        for cat in categories:
            logger.log(cat, f"test_{cat}")
        
        assert logger._sequence >= len(categories)

    def test_thread_safety(self, tmp_path):
        import threading
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        initial = logger._sequence
        
        def log_worker(n):
            for i in range(10):
                logger.log("THREAD", f"event_{n}_{i}")
        
        threads = [threading.Thread(target=log_worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert logger._sequence == initial + 50

    def test_max_file_size_constant(self):
        assert DiagnosticLogger.MAX_FILE_SIZE == 5 * 1024 * 1024

    def test_max_backup_files_constant(self):
        assert DiagnosticLogger.MAX_BACKUP_FILES == 5

    def test_get_logger_singleton(self):
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2

    def test_log_with_none_data(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "test_event", None)
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) > 0

    def test_log_with_empty_data(self, tmp_path):
        logger = DiagnosticLogger(log_dir=tmp_path / "logs")
        logger.log("TEST", "test_event", {})
        
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) > 0
