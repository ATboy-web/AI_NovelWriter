"""
novel_agent.py 深度测试 - 真正调用静态方法和工具类
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.novel_agent import (
    MessageRole, AgentMessage, Tool, ToolRegistry, NovelAgent
)


class TestMessageRoleDeep:
    """MessageRole 深度测试"""

    def test_all_values(self):
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.PLOT.value == "plot_designer"
        assert MessageRole.WORLD.value == "world_builder"
        assert MessageRole.WRITER.value == "writer"
        assert MessageRole.REVIEWER.value == "reviewer"
        assert MessageRole.EDITOR.value == "editor"
        assert MessageRole.TOOL.value == "tool"

    def test_count(self):
        assert len(MessageRole) == 7


class TestAgentMessageDeep:
    """AgentMessage 深度测试"""

    def test_init_defaults(self):
        msg = AgentMessage(MessageRole.WRITER, "test", "content")
        assert msg.role == MessageRole.WRITER
        assert msg.action == "test"
        assert msg.content == "content"
        assert msg.metadata == {}
        assert msg.timestamp is not None

    def test_init_with_metadata(self):
        msg = AgentMessage(MessageRole.WRITER, "test", "content", {"key": "val"})
        assert msg.metadata == {"key": "val"}

    def test_to_dict(self):
        msg = AgentMessage(MessageRole.WRITER, "test", "content")
        d = msg.to_dict()
        assert d["role"] == "writer"
        assert d["action"] == "test"
        assert "content" in d
        assert "timestamp" in d

    def test_to_dict_truncates_content(self):
        msg = AgentMessage(MessageRole.WRITER, "test", "x" * 500)
        d = msg.to_dict()
        assert len(d["content"]) <= 300

    def test_all_roles_to_dict(self):
        for role in MessageRole:
            msg = AgentMessage(role, "test", "content")
            d = msg.to_dict()
            assert d["role"] == role.value


class TestToolDeep:
    """Tool 深度测试"""

    def test_init(self):
        tool = Tool("test", "desc", lambda: 42)
        assert tool.name == "test"
        assert tool.description == "desc"
        assert tool.input_schema == {}
        assert tool.category == "general"

    def test_init_with_schema(self):
        schema = {"type": "object"}
        tool = Tool("test", "desc", lambda: 42, input_schema=schema)
        assert tool.input_schema == schema

    def test_init_with_category(self):
        tool = Tool("test", "desc", lambda: 42, category="plot")
        assert tool.category == "plot"

    def test_execute_success(self):
        def add(a, b): return a + b
        tool = Tool("add", "加法", add)
        result = tool.execute(a=1, b=2)
        assert result["success"] is True
        assert result["result"] == 3
        assert result["tool"] == "add"

    def test_execute_failure(self):
        def fail(): raise ValueError("error")
        tool = Tool("fail", "失败", fail)
        result = tool.execute()
        assert result["success"] is False
        assert "error" in result
        assert result["tool"] == "fail"


class TestToolRegistryDeep:
    """ToolRegistry 深度测试"""

    def test_init(self):
        registry = ToolRegistry()
        assert registry._tools == {}

    def test_register(self):
        registry = ToolRegistry()
        tool = Tool("test", "desc", lambda: 42)
        result = registry.register(tool)
        assert result is registry  # chain
        assert "test" in registry._tools

    def test_register_multiple(self):
        registry = ToolRegistry()
        for i in range(10):
            registry.register(Tool(f"t{i}", f"d{i}", lambda: None))
        assert len(registry._tools) == 10

    def test_list_tools_empty(self):
        registry = ToolRegistry()
        assert registry.list_tools() == []

    def test_list_tools_all(self):
        registry = ToolRegistry()
        registry.register(Tool("t1", "d1", lambda: None))
        registry.register(Tool("t2", "d2", lambda: None))
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_list_tools_by_category(self):
        registry = ToolRegistry()
        registry.register(Tool("t1", "d1", lambda: None, category="plot"))
        registry.register(Tool("t2", "d2", lambda: None, category="writer"))
        registry.register(Tool("t3", "d3", lambda: None, category="general"))
        plot_tools = registry.list_tools(agent_type="plot")
        assert len(plot_tools) == 2  # plot + general

    def test_call_existing(self):
        registry = ToolRegistry()
        registry.register(Tool("add", "加法", lambda a, b: a + b))
        result = registry.call("add", a=1, b=2)
        assert result["success"] is True
        assert result["result"] == 3

    def test_call_nonexistent(self):
        registry = ToolRegistry()
        result = registry.call("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_call_error(self):
        registry = ToolRegistry()
        registry.register(Tool("fail", "失败", lambda: 1/0))
        result = registry.call("fail")
        assert result["success"] is False


class TestNovelAgentParseJson:
    """NovelAgent._parse_json_response 深度测试"""

    def test_valid_dict(self):
        result = NovelAgent._parse_json_response('{"key": "value"}', {})
        assert result == {"key": "value"}

    def test_invalid_returns_default(self):
        result = NovelAgent._parse_json_response("invalid", {"default": True})
        assert result == {"default": True}

    def test_valid_list(self):
        result = NovelAgent._parse_json_response('[1, 2, 3]', [], is_list=True)
        assert result == [1, 2, 3]

    def test_invalid_list_returns_default(self):
        result = NovelAgent._parse_json_response("invalid", [0], is_list=True)
        assert result == [0]

    def test_empty_string(self):
        result = NovelAgent._parse_json_response('', {})
        assert result == {}

    def test_nested(self):
        result = NovelAgent._parse_json_response('{"nested": {"key": "value"}}', {})
        assert result == {"nested": {"key": "value"}}

    def test_with_numbers(self):
        result = NovelAgent._parse_json_response('{"count": 42}', {})
        assert result == {"count": 42}

    def test_with_boolean(self):
        result = NovelAgent._parse_json_response('{"active": true}', {})
        assert result == {"active": True}

    def test_with_null(self):
        result = NovelAgent._parse_json_response('{"value": null}', {})
        assert result == {"value": None}

    def test_empty_dict(self):
        result = NovelAgent._parse_json_response('{}', {})
        assert result == {}

    def test_empty_list(self):
        result = NovelAgent._parse_json_response('[]', [], is_list=True)
        assert result == []


class TestNovelAgentInit:
    """NovelAgent 初始化测试"""

    def test_has_required_methods(self):
        methods = [
            'generate_chapter', 'generate_outline', 'generate_characters',
            'generate_settings', 'review_chapter', 'finalize_chapter',
            'analyze_style', 'generate_with_style', 'blend_styles',
            'generate_with_collaboration', 'generate_outline_continuation',
        ]
        for method in methods:
            assert hasattr(NovelAgent, method), f"缺少方法: {method}"

    def test_has_internal_methods(self):
        methods = [
            '_compress_text', '_compress_characters', '_compress_settings',
            '_compress_active_characters', '_compress_recent_chapters',
            '_build_context', '_record_conversation',
            '_plot_designer_analyze', '_world_builder_build',
            '_writer_generate', '_reviewer_evaluate', '_writer_revise',
            '_get_writing_style_prompt', '_register_tools',
            '_call_anti_slop_check', '_get_knowledge_graph_context',
            '_extract_characters_from_raw', '_parse_json_response',
            '_generate_long_chapter', '_has_excessive_repetition',
            '_plan_story_arcs', '_generate_outline_batch',
            '_update_character_progression',
        ]
        for method in methods:
            assert hasattr(NovelAgent, method), f"缺少方法: {method}"
