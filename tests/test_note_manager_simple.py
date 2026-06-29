"""
笔记管理模块简化测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.note_manager import NoteManager


class TestNoteManagerSimple:
    """NoteManager 简化测试套件"""
    
    def test_class_exists(self):
        """测试类存在"""
        assert NoteManager is not None
    
    def test_init_parameters(self):
        """测试初始化参数"""
        # 测试类可以被实例化
        mock_config = MagicMock()
        mock_config.config_dir = Path("/tmp/test")
        
        # 不带小说目录
        manager = NoteManager(config=mock_config)
        assert manager is not None
    
    def test_has_sticky_note_methods(self):
        """测试便笺方法存在"""
        assert hasattr(NoteManager, 'get_sticky_notes')
        assert hasattr(NoteManager, 'save_sticky_notes')
        assert hasattr(NoteManager, 'add_sticky_note')
        assert hasattr(NoteManager, 'delete_sticky_note')
    
    def test_sticky_file_location(self):
        """测试便笺文件位置"""
        mock_config = MagicMock()
        mock_config.config_dir = Path("/tmp/test")
        
        manager = NoteManager(config=mock_config)
        assert manager.sticky_file == Path("/tmp/test/sticky_notes.json")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
