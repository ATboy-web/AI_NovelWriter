"""
小说创作智能体完整测试 - 覆盖所有方法
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# MessageRole 完整测试
# ============================================================

class TestMessageRoleFull:
    """MessageRole完整测试"""
    
    def test_system_role_value(self):
        """测试SYSTEM角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.SYSTEM.value == "system"
    
    def test_plot_role_value(self):
        """测试PLOT角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.PLOT.value == "plot_designer"
    
    def test_world_role_value(self):
        """测试WORLD角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.WORLD.value == "world_builder"
    
    def test_writer_role_value(self):
        """测试WRITER角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.WRITER.value == "writer"
    
    def test_reviewer_role_value(self):
        """测试REVIEWER角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.REVIEWER.value == "reviewer"
    
    def test_editor_role_value(self):
        """测试EDITOR角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.EDITOR.value == "editor"
    
    def test_tool_role_value(self):
        """测试TOOL角色值"""
        from app.novel_agent import MessageRole
        assert MessageRole.TOOL.value == "tool"
    
    def test_all_roles_count(self):
        """测试所有角色数量"""
        from app.novel_agent import MessageRole
        assert len(MessageRole) == 7


# ============================================================
# AgentMessage 完整测试
# ============================================================

class TestAgentMessageFull:
    """AgentMessage完整测试"""
    
    def test_init_with_defaults(self):
        """测试默认初始化"""
        from app.novel_agent import AgentMessage, MessageRole
        msg = AgentMessage(role=MessageRole.WRITER, action="test", content="test")
        assert msg.role == MessageRole.WRITER
        assert msg.action == "test"
        assert msg.content == "test"
        assert msg.metadata == {}
        assert msg.timestamp is not None
    
    def test_init_with_metadata(self):
        """测试带元数据初始化"""
        from app.novel_agent import AgentMessage, MessageRole
        msg = AgentMessage(
            role=MessageRole.WRITER,
            action="test",
            content="test",
            metadata={"key": "value"}
        )
        assert msg.metadata == {"key": "value"}
    
    def test_to_dict_basic(self):
        """测试基本字典转换"""
        from app.novel_agent import AgentMessage, MessageRole
        msg = AgentMessage(role=MessageRole.WRITER, action="test", content="test")
        d = msg.to_dict()
        assert d["role"] == "writer"
        assert d["action"] == "test"
        assert "test" in d["content"]
        assert "timestamp" in d
    
    def test_to_dict_content_truncation(self):
        """测试内容截断"""
        from app.novel_agent import AgentMessage, MessageRole
        long_content = "x" * 500
        msg = AgentMessage(role=MessageRole.WRITER, action="test", content=long_content)
        d = msg.to_dict()
        assert len(d["content"]) <= 300
    
    def test_to_dict_with_metadata(self):
        """测试带元数据字典转换"""
        from app.novel_agent import AgentMessage, MessageRole
        msg = AgentMessage(
            role=MessageRole.WRITER,
            action="test",
            content="test",
            metadata={"key": "value"}
        )
        d = msg.to_dict()
        assert d["metadata"] == {"key": "value"}
    
    def test_all_roles_to_dict(self):
        """测试所有角色字典转换"""
        from app.novel_agent import AgentMessage, MessageRole
        for role in MessageRole:
            msg = AgentMessage(role=role, action="test", content="test")
            d = msg.to_dict()
            assert d["role"] == role.value


# ============================================================
# Tool 完整测试
# ============================================================

class TestToolFull:
    """Tool完整测试"""
    
    def test_init_defaults(self):
        """测试默认初始化"""
        from app.novel_agent import Tool
        tool = Tool(name="test", description="test", func=lambda: None)
        assert tool.name == "test"
        assert tool.description == "test"
        assert tool.input_schema == {}
        assert tool.category == "general"
    
    def test_init_with_schema(self):
        """测试带schema初始化"""
        from app.novel_agent import Tool
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        tool = Tool(name="test", description="test", func=lambda: None, input_schema=schema)
        assert tool.input_schema == schema
    
    def test_init_with_category(self):
        """测试带分类初始化"""
        from app.novel_agent import Tool
        tool = Tool(name="test", description="test", func=lambda: None, category="plot")
        assert tool.category == "plot"
    
    def test_execute_success(self):
        """测试执行成功"""
        from app.novel_agent import Tool
        def add(a, b): return a + b
        tool = Tool(name="add", description="加法", func=add)
        result = tool.execute(a=1, b=2)
        assert result["success"] is True
        assert result["result"] == 3
        assert result["tool"] == "add"
    
    def test_execute_failure(self):
        """测试执行失败"""
        from app.novel_agent import Tool
        def fail(): raise ValueError("测试错误")
        tool = Tool(name="fail", description="失败", func=fail)
        result = tool.execute()
        assert result["success"] is False
        assert "测试错误" in result["error"]
        assert result["tool"] == "fail"
    
    def test_execute_with_kwargs(self):
        """测试带参数执行"""
        from app.novel_agent import Tool
        def greet(name, greeting="Hello"): return f"{greeting}, {name}!"
        tool = Tool(name="greet", description="问候", func=greet)
        result = tool.execute(name="World", greeting="Hi")
        assert result["success"] is True
        assert result["result"] == "Hi, World!"


# ============================================================
# ToolRegistry 完整测试
# ============================================================

class TestToolRegistryFull:
    """ToolRegistry完整测试"""
    
    def test_init_empty(self):
        """测试空初始化"""
        from app.novel_agent import ToolRegistry
        registry = ToolRegistry()
        assert registry._tools == {}
    
    def test_register_single(self):
        """测试注册单个工具"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        tool = Tool(name="test", description="test", func=lambda: None)
        result = registry.register(tool)
        assert result == registry
        assert "test" in registry._tools
    
    def test_register_multiple(self):
        """测试注册多个工具"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        for i in range(10):
            registry.register(Tool(name=f"tool_{i}", description=f"tool {i}", func=lambda: None))
        assert len(registry._tools) == 10
    
    def test_list_tools_empty(self):
        """测试空工具列表"""
        from app.novel_agent import ToolRegistry
        registry = ToolRegistry()
        tools = registry.list_tools()
        assert tools == []
    
    def test_list_tools_all(self):
        """测试所有工具列表"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="t1", description="d1", func=lambda: None))
        registry.register(Tool(name="t2", description="d2", func=lambda: None))
        tools = registry.list_tools()
        assert len(tools) == 2
    
    def test_list_tools_by_category(self):
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
    
    def test_call_existing_tool(self):
        """测试调用存在的工具"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="add", description="加法", func=lambda a, b: a + b))
        result = registry.call("add", a=1, b=2)
        assert result["success"] is True
        assert result["result"] == 3
    
    def test_call_nonexistent_tool(self):
        """测试调用不存在的工具"""
        from app.novel_agent import ToolRegistry
        registry = ToolRegistry()
        result = registry.call("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]
    
    def test_call_tool_with_error(self):
        """测试调用出错的工具"""
        from app.novel_agent import ToolRegistry, Tool
        registry = ToolRegistry()
        registry.register(Tool(name="fail", description="失败", func=lambda: 1/0))
        result = registry.call("fail")
        assert result["success"] is False
        assert "error" in result


# ============================================================
# NovelAgent 方法测试
# ============================================================

class TestNovelAgentMethodsFull:
    """NovelAgent方法完整测试"""
    
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

class TestNovelAgentStaticMethodsFull:
    """NovelAgent静态方法完整测试"""
    
    def test_parse_json_response_valid_dict(self):
        """测试解析有效字典JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('{"key": "value"}', {})
        assert result == {"key": "value"}
    
    def test_parse_json_response_invalid(self):
        """测试解析无效JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('invalid json', {"default": True})
        assert result == {"default": True}
    
    def test_parse_json_response_valid_list(self):
        """测试解析有效列表JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('[1, 2, 3]', [], is_list=True)
        assert result == [1, 2, 3]
    
    def test_parse_json_response_invalid_list(self):
        """测试解析无效列表JSON"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('invalid', [0], is_list=True)
        assert result == [0]
    
    def test_parse_json_response_empty_string(self):
        """测试解析空字符串"""
        from app.novel_agent import NovelAgent
        result = NovelAgent._parse_json_response('', {})
        assert result == {}
    
    def test_parse_json_response_nested(self):
        """测试解析嵌套JSON"""
        from app.novel_agent import NovelAgent
        json_str = '{"nested": {"key": "value"}}'
        result = NovelAgent._parse_json_response(json_str, {})
        assert result == {"nested": {"key": "value"}}
    
    def test_extract_characters_from_raw_callable(self):
        """测试_extract_characters_from_raw可调用"""
        from app.novel_agent import NovelAgent
        assert callable(NovelAgent._extract_characters_from_raw)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
