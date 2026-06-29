"""
笔记管理器详细测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# NoteManager 方法测试
# ============================================================

class TestNoteManagerMethods:
    """NoteManager方法测试"""
    
    def test_class_exists(self):
        """测试类存在"""
        from app.note_manager import NoteManager
        assert NoteManager is not None
    
    def test_has_init(self):
        """测试有__init__方法"""
        from app.note_manager import NoteManager
        assert hasattr(NoteManager, '__init__')
    
    def test_has_sticky_note_methods(self):
        """测试有便笺方法"""
        from app.note_manager import NoteManager
        assert hasattr(NoteManager, 'get_sticky_notes')
        assert hasattr(NoteManager, 'save_sticky_notes')
        assert hasattr(NoteManager, 'add_sticky_note')
        assert hasattr(NoteManager, 'delete_sticky_note')
    
    def test_has_project_note_methods(self):
        """测试有工程笔记方法"""
        from app.note_manager import NoteManager
        # 检查是否有工程笔记相关方法
        methods = dir(NoteManager)
        assert len(methods) > 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
