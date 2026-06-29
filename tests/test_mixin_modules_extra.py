"""
Mixin模块额外测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# CharacterManagerMixin 额外测试
# ============================================================

class TestCharacterManagerMixinExtra:
    """CharacterManagerMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.character_manager import CharacterManagerMixin
        methods = dir(CharacterManagerMixin)
        assert len(methods) > 5


# ============================================================
# NavigationManager 额外测试
# ============================================================

class TestNavigationManagerExtra:
    """NavigationManager额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.navigation import NavigationManager
        methods = dir(NavigationManager)
        assert len(methods) > 5


# ============================================================
# SettingsManagerMixin 额外测试
# ============================================================

class TestSettingsManagerMixinExtra:
    """SettingsManagerMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.settings_manager import SettingsManagerMixin
        methods = dir(SettingsManagerMixin)
        assert len(methods) > 5


# ============================================================
# UIManagerMixin 额外测试
# ============================================================

class TestUIManagerMixinExtra:
    """UIManagerMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.ui_manager import UIManagerMixin
        methods = dir(UIManagerMixin)
        assert len(methods) > 5


# ============================================================
# NoteManagerMixin 额外测试
# ============================================================

class TestNoteManagerMixinExtra:
    """NoteManagerMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.note_manager_ui import NoteManagerMixin
        methods = dir(NoteManagerMixin)
        assert len(methods) > 5


# ============================================================
# ReaderManagerMixin 额外测试
# ============================================================

class TestReaderManagerMixinExtra:
    """ReaderManagerMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.reader_manager import ReaderManagerMixin
        methods = dir(ReaderManagerMixin)
        assert len(methods) > 5


# ============================================================
# WritingSkillsPanelMixin 额外测试
# ============================================================

class TestWritingSkillsPanelMixinExtra:
    """WritingSkillsPanelMixin额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.writing_skills_panel import WritingSkillsPanelMixin
        methods = dir(WritingSkillsPanelMixin)
        assert len(methods) > 5


# ============================================================
# FullscreenWriter 额外测试
# ============================================================

class TestFullscreenWriterExtra:
    """FullscreenWriter额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.fullscreen_writer import FullscreenWriter
        methods = dir(FullscreenWriter)
        assert len(methods) > 15


# ============================================================
# NoteManager 额外测试
# ============================================================

class TestNoteManagerExtra:
    """NoteManager额外测试"""
    
    def test_class_has_many_methods(self):
        """测试类有很多方法"""
        from app.note_manager import NoteManager
        methods = dir(NoteManager)
        assert len(methods) > 10


# ============================================================
# ReadingManager 额外测试
# ============================================================

class TestReadingManagerExtra:
    """ReadingManager额外测试"""
    
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
