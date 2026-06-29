"""
AI诊断日志系统简化测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.diagnostic_logger import DiagnosticLogger, get_logger


class TestDiagnosticLoggerSimple:
    """DiagnosticLogger 简化测试套件"""
    
    def test_class_exists(self):
        """测试类存在"""
        assert DiagnosticLogger is not None
    
    def test_constants(self):
        """测试常量"""
        assert DiagnosticLogger.MAX_FILE_SIZE == 5 * 1024 * 1024  # 5MB
        assert DiagnosticLogger.MAX_BACKUP_FILES == 5
    
    def test_has_methods(self):
        """测试方法存在"""
        assert hasattr(DiagnosticLogger, 'log')
        assert hasattr(DiagnosticLogger, '_generate_session_id')
        assert hasattr(DiagnosticLogger, '_get_log_file')
    
    def test_get_logger(self):
        """测试get_logger函数"""
        logger = get_logger()
        assert isinstance(logger, DiagnosticLogger)
    
    def test_init_with_temp_dir(self, tmp_path):
        """测试带临时目录的初始化"""
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        
        assert logger.log_dir == log_dir
        assert logger.log_dir.exists()
        assert logger._session_id is not None
    
    def test_session_id_format(self, tmp_path):
        """测试会话ID格式"""
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        
        session_id = logger._session_id
        # 格式应该是 YYYYMMDD-HHMMSS-PID
        parts = session_id.split('-')
        assert len(parts) >= 3
    
    def test_log_method(self, tmp_path):
        """测试log方法"""
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        
        # 记录一条日志
        logger.log("TEST", "test_event", {"key": "value"})
        
        # 验证日志文件被创建
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) > 0
    
    def test_sequence_increments(self, tmp_path):
        """测试序列号递增"""
        log_dir = tmp_path / "logs"
        logger = DiagnosticLogger(log_dir=log_dir)
        
        initial = logger._sequence
        logger.log("TEST", "event1")
        logger.log("TEST", "event2")
        
        assert logger._sequence == initial + 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
