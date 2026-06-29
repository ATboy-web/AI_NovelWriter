"""
全屏写作器详细测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# FullscreenWriter 方法测试
# ============================================================

class TestFullscreenWriterMethods:
    """FullscreenWriter方法测试"""
    
    def test_has_init(self):
        """测试有__init__方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '__init__')
    
    def test_has_create_widgets(self):
        """测试有_create_widgets方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_create_widgets')
    
    def test_has_bind_events(self):
        """测试有_bind_events方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_bind_events')
    
    def test_has_show_context_menu(self):
        """测试有_show_context_menu方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_show_context_menu')
    
    def test_has_on_key_release(self):
        """测试有_on_key_release方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_on_key_release')
    
    def test_has_on_tab(self):
        """测试有_on_tab方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_on_tab')
    
    def test_has_trigger_ai_suggestion(self):
        """测试有_trigger_ai_suggestion方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_trigger_ai_suggestion')
    
    def test_has_show_suggestion(self):
        """测试有_show_suggestion方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_show_suggestion')
    
    def test_has_clear_suggestion(self):
        """测试有_clear_suggestion方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_clear_suggestion')
    
    def test_has_center_current_line(self):
        """测试有_center_current_line方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_center_current_line')
    
    def test_has_change_font_size(self):
        """测试有_change_font_size方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_change_font_size')
    
    def test_has_toggle_ai(self):
        """测试有_toggle_ai方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_toggle_ai')
    
    def test_has_toggle_typewriter(self):
        """测试有_toggle_typewriter方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_toggle_typewriter')
    
    def test_has_update_status(self):
        """测试有_update_status方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_update_status')
    
    def test_has_update_paper_position(self):
        """测试有_update_paper_position方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_update_paper_position')
    
    def test_has_ai_expand(self):
        """测试有_ai_expand方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_ai_expand')
    
    def test_has_ai_compress(self):
        """测试有_ai_compress方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_ai_compress')
    
    def test_has_ai_continue(self):
        """测试有_ai_continue方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_ai_continue')
    
    def test_has_ai_polish(self):
        """测试有_ai_polish方法"""
        from app.fullscreen_writer import FullscreenWriter
        assert hasattr(FullscreenWriter, '_ai_polish')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
