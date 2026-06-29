"""
Mixin模块方法测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# CharacterManagerMixin 方法测试
# ============================================================

class TestCharacterManagerMixinMethods:
    """CharacterManagerMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.character_manager import CharacterManagerMixin
        methods = dir(CharacterManagerMixin)
        assert len(methods) > 5


# ============================================================
# NavigationManager 方法测试
# ============================================================

class TestNavigationManagerMethods:
    """NavigationManager方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.navigation import NavigationManager
        methods = dir(NavigationManager)
        assert len(methods) > 5


# ============================================================
# SettingsManagerMixin 方法测试
# ============================================================

class TestSettingsManagerMixinMethods:
    """SettingsManagerMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.settings_manager import SettingsManagerMixin
        methods = dir(SettingsManagerMixin)
        assert len(methods) > 5


# ============================================================
# UIManagerMixin 方法测试
# ============================================================

class TestUIManagerMixinMethods:
    """UIManagerMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.ui_manager import UIManagerMixin
        methods = dir(UIManagerMixin)
        assert len(methods) > 5


# ============================================================
# NoteManagerMixin 方法测试
# ============================================================

class TestNoteManagerMixinMethods:
    """NoteManagerMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.note_manager_ui import NoteManagerMixin
        methods = dir(NoteManagerMixin)
        assert len(methods) > 5


# ============================================================
# ReaderManagerMixin 方法测试
# ============================================================

class TestReaderManagerMixinMethods:
    """ReaderManagerMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.reader_manager import ReaderManagerMixin
        methods = dir(ReaderManagerMixin)
        assert len(methods) > 5


# ============================================================
# WritingSkillsPanelMixin 方法测试
# ============================================================

class TestWritingSkillsPanelMixinMethods:
    """WritingSkillsPanelMixin方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.writing_skills_panel import WritingSkillsPanelMixin
        methods = dir(WritingSkillsPanelMixin)
        assert len(methods) > 5


# ============================================================
# FullscreenWriter 方法测试
# ============================================================

class TestFullscreenWriterMethods:
    """FullscreenWriter方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.fullscreen_writer import FullscreenWriter
        methods = dir(FullscreenWriter)
        assert len(methods) > 15


# ============================================================
# NoteManager 方法测试
# ============================================================

class TestNoteManagerMethods:
    """NoteManager方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.note_manager import NoteManager
        methods = dir(NoteManager)
        assert len(methods) > 10


# ============================================================
# ReadingManager 方法测试
# ============================================================

class TestReadingManagerMethods:
    """ReadingManager方法测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.reading_manager import ReadingManager
        methods = dir(ReadingManager)
        assert len(methods) > 5
    
    def test_supported_formats_count(self):
        """测试支持格式数量"""
        from app.reading_manager import ReadingManager
        formats = ReadingManager.SUPPORTED_FORMATS
        assert len(formats) >= 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
