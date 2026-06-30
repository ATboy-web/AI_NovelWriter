"""
小说创作智能体额外测试2 - 覆盖更多方法
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# NovelAgent 额外方法测试2
# ============================================================

class TestNovelAgentExtra2:
    """NovelAgent额外方法测试2"""
    
    def test_has_compress_text(self):
        """测试有_compress_text方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_text')
    
    def test_has_compress_characters(self):
        """测试有_compress_characters方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_characters')
    
    def test_has_compress_settings(self):
        """测试有_compress_settings方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_settings')
    
    def test_has_compress_active_characters(self):
        """测试有_compress_active_characters方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_active_characters')
    
    def test_has_compress_recent_chapters(self):
        """测试有_compress_recent_chapters方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_recent_chapters')
    
    def test_has_generate_outline_batch(self):
        """测试有_generate_outline_batch方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_generate_outline_batch')
    
    def test_has_generate_outline_continuation(self):
        """测试有generate_outline_continuation方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_outline_continuation')
    
    def test_has_finalize_chapter(self):
        """测试有finalize_chapter方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'finalize_chapter')
    
    def test_has_update_character_progression(self):
        """测试有_update_character_progression方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_update_character_progression')
    
    def test_has_analyze_style(self):
        """测试有analyze_style方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'analyze_style')
    
    def test_has_generate_with_style(self):
        """测试有generate_with_style方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_with_style')
    
    def test_has_blend_styles(self):
        """测试有blend_styles方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'blend_styles')
    
    def test_has_extract_characters_from_raw(self):
        """测试有_extract_characters_from_raw方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_extract_characters_from_raw')
    
    def test_has_parse_json_response(self):
        """测试有_parse_json_response方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_parse_json_response')
    
    def test_has_generate_long_chapter(self):
        """测试有_generate_long_chapter方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_generate_long_chapter')
    
    def test_has_excessive_repetition(self):
        """测试有_has_excessive_repetition方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_has_excessive_repetition')
    
    def test_has_review_chapter(self):
        """测试有review_chapter方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'review_chapter')
    
    def test_has_generate_settings(self):
        """测试有generate_settings方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_settings')
    
    def test_has_generate_characters(self):
        """测试有generate_characters方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_characters')
    
    def test_has_generate_outline(self):
        """测试有generate_outline方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_outline')
    
    def test_has_plan_story_arcs(self):
        """测试有_plan_story_arcs方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_plan_story_arcs')
    
    def test_has_generate_with_collaboration(self):
        """测试有generate_with_collaboration方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_with_collaboration')
    
    def test_has_plot_designer_analyze(self):
        """测试有_plot_designer_analyze方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_plot_designer_analyze')
    
    def test_has_world_builder_build(self):
        """测试有_world_builder_build方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_world_builder_build')
    
    def test_has_writer_generate(self):
        """测试有_writer_generate方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_writer_generate')
    
    def test_has_reviewer_evaluate(self):
        """测试有_reviewer_evaluate方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_reviewer_evaluate')
    
    def test_has_writer_revise(self):
        """测试有_writer_revise方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_writer_revise')
    
    def test_has_build_context(self):
        """测试有_build_context方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_build_context')
    
    def test_has_record_conversation(self):
        """测试有_record_conversation方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_record_conversation')
    
    def test_has_knowledge_graph_context(self):
        """测试有_get_knowledge_graph_context方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_get_knowledge_graph_context')
    
    def test_has_anti_slop_check(self):
        """测试有_call_anti_slop_check方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_call_anti_slop_check')
    
    def test_has_register_tools(self):
        """测试有_register_tools方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_register_tools')
    
    def test_has_writing_style_prompt(self):
        """测试有_get_writing_style_prompt方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_get_writing_style_prompt')


# ============================================================
# NovelAgent 静态方法额外测试2
# ============================================================

class TestNovelAgentStaticMethodsExtra2:
    """NovelAgent静态方法额外测试2"""
    
    def test_parse_json_response_with_numbers(self):
        """测试解析数字JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{"count": 42}', {})
        assert result == {"count": 42}
    
    def test_parse_json_response_with_nested_list(self):
        """测试解析嵌套列表JSON"""
        from app.novel_agent import NovelAgent
        json_str = '{"items": [1, 2, 3]}'
        result = NovelAgent._parse_json_response(json_str, {})
        assert result == {"items": [1, 2, 3]}
    
    def test_parse_json_response_with_empty_dict(self):
        """测试解析空字典JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{}', {})
        assert result == {}
    
    def test_parse_json_response_with_empty_list(self):
        """测试解析空列表JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('[]', [], is_list=True)
        assert result == []
    
    def test_parse_json_response_with_boolean(self):
        """测试解析布尔值JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{"active": true}', {})
        assert result == {"active": True}
    
    def test_parse_json_response_with_null(self):
        """测试解析null值JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{"value": null}', {})
        assert result == {"value": None}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
