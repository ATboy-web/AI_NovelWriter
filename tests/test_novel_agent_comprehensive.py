"""
小说创作智能体全面测试 - 覆盖所有方法
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# NovelAgent 方法测试
# ============================================================

class TestNovelAgentMethods:
    """NovelAgent方法测试"""
    
    def test_has_init(self):
        """测试有__init__方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '__init__')
    
    def test_has_writing_style_prompt(self):
        """测试有_get_writing_style_prompt方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_get_writing_style_prompt')
    
    def test_has_register_tools(self):
        """测试有_register_tools方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_register_tools')
    
    def test_has_anti_slop_check(self):
        """测试有_call_anti_slop_check方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_call_anti_slop_check')
    
    def test_has_knowledge_graph_context(self):
        """测试有_get_knowledge_graph_context方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_get_knowledge_graph_context')
    
    def test_has_record_conversation(self):
        """测试有_record_conversation方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_record_conversation')
    
    def test_has_build_context(self):
        """测试有_build_context方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_build_context')
    
    def test_has_compress_methods(self):
        """测试有压缩方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_compress_active_characters')
        assert hasattr(NovelAgent, '_compress_settings')
        assert hasattr(NovelAgent, '_compress_characters')
        assert hasattr(NovelAgent, '_compress_text')
        assert hasattr(NovelAgent, '_compress_recent_chapters')
    
    def test_has_generate_with_collaboration(self):
        """测试有generate_with_collaboration方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_with_collaboration')
    
    def test_has_agent_methods(self):
        """测试有智能体方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, '_plot_designer_analyze')
        assert hasattr(NovelAgent, '_world_builder_build')
        assert hasattr(NovelAgent, '_writer_generate')
        assert hasattr(NovelAgent, '_reviewer_evaluate')
        assert hasattr(NovelAgent, '_writer_revise')
    
    def test_has_generate_chapter(self):
        """测试有generate_chapter方法"""
        from app.novel_agent import NovelAgent
        assert hasattr(NovelAgent, 'generate_chapter')
    
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
    
    def test_has_extract_characters(self):
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


# ============================================================
# NovelAgent 静态方法测试
# ============================================================

class TestNovelAgentStaticMethods:
    """NovelAgent静态方法测试"""
    
    def test_parse_json_response_valid(self):
        """测试解析有效JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{"key": "value"}', {})
        assert result == {"key": "value"}
    
    def test_parse_json_response_invalid(self):
        """测试解析无效JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('invalid json', {"default": True})
        assert result == {"default": True}
    
    def test_parse_json_response_list(self):
        """测试解析JSON列表"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('[1, 2, 3]', [], is_list=True)
        assert result == [1, 2, 3]
    
    def test_parse_json_response_list_invalid(self):
        """测试解析无效JSON列表"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('invalid', [0], is_list=True)
        assert result == [0]
    
    def test_extract_characters_from_raw(self):
        """测试从原始文本提取角色"""
        from app.novel_agent import NovelAgent
        # 测试方法存在
        assert callable(NovelAgent._extract_characters_from_raw)


# ============================================================
# AgentMessage 扩展测试
# ============================================================

class TestAgentMessageExtended:
    """AgentMessage扩展测试"""
    
    def test_all_roles(self):
        """测试所有角色"""
        from app.novel_agent import MessageRole
        roles = [
            MessageRole.SYSTEM,
            MessageRole.PLOT,
            MessageRole.WORLD,
            MessageRole.WRITER,
            MessageRole.REVIEWER,
            MessageRole.EDITOR,
            MessageRole.TOOL
        ]
        for role in roles:
            assert role.value is not None
    
    def test_message_with_all_roles(self):
        """测试所有角色的消息"""
        from app.novel_agent import AgentMessage, MessageRole
        for role in MessageRole:
            msg = AgentMessage(role=role, action="test", content="test")
            assert msg.role == role
            d = msg.to_dict()
            assert d["role"] == role.value


# ============================================================
# Tool 扩展测试
# ============================================================

class TestToolExtended:
    """Tool扩展测试"""
    
    def test_tool_with_schema(self):
        """测试带schema的工具"""
        from app.novel_agent import Tool
        tool = Tool(
            name="test",
            description="test",
            func=lambda x: x,
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}}
        )
        assert tool.input_schema["type"] == "object"
    
    def test_tool_with_category(self):
        """测试带分类的工具"""
        from app.novel_agent import Tool
        tool = Tool(name="test", description="test", func=lambda: None, category="plot")
        assert tool.category == "plot"
    
    def test_tool_execute_with_args(self):
        """测试带参数执行"""
        from app.novel_agent import Tool
        def add(a, b, c=0): return a + b + c
        tool = Tool(name="add", description="加法", func=add)
        result = tool.execute(a=1, b=2, c=3)
        assert result["success"] is True
        assert result["result"] == 6


# ============================================================
# ToolRegistry 扩展测试
# ============================================================

class TestToolRegistryExtended:
    """ToolRegistry扩展测试"""
    
    def test_register_multiple(self):
        """测试注册多个工具"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        for i in range(10):
            registry.register(Tool(name=f"tool_{i}", description=f"tool {i}", func=lambda: None))
        assert len(registry._tools) == 10
    
    def test_list_tools_with_category(self):
        """测试按分类列表"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="t1", description="d1", func=lambda: None, category="plot"))
        registry.register(Tool(name="t2", description="d2", func=lambda: None, category="writer"))
        registry.register(Tool(name="t3", description="d3", func=lambda: None, category="general"))
        
        plot_tools = registry.list_tools(agent_type="plot")
        assert len(plot_tools) == 2  # plot + general
        
        writer_tools = registry.list_tools(agent_type="writer")
        assert len(writer_tools) == 2  # writer + general
    
    def test_call_tool_with_kwargs(self):
        """测试带参数调用"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="greet", description="问候", func=lambda name: f"Hello, {name}!"))
        result = registry.call("greet", name="World")
        assert result["success"] is True
        assert result["result"] == "Hello, World!"
    
    def test_call_tool_error(self):
        """测试调用出错"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="fail", description="失败", func=lambda: 1/0))
        result = registry.call("fail")
        assert result["success"] is False
        assert "error" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
