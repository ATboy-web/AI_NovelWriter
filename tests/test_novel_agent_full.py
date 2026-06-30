"""
novel_agent.py 全量测试 - 覆盖compress/build_context/tools方法
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.novel_agent import (
    MessageRole, AgentMessage, Tool, ToolRegistry, NovelAgent
)


class TestCompressText:
    """_compress_text 深度测试"""

    def test_short_text(self):
        config = MagicMock()
        config.get.return_value = ""
        memory = MagicMock()
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._compress_text("短文本", 1000)
            assert result == "短文本"

    def test_long_text_keep_tail(self):
        config = MagicMock()
        config.get.return_value = ""
        memory = MagicMock()
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            text = "x" * 1000
            result = agent._compress_text(text, 100, keep_tail=True)
            assert len(result) <= 110  # Some tolerance
            assert "..." in result

    def test_long_text_no_tail(self):
        config = MagicMock()
        config.get.return_value = ""
        memory = MagicMock()
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            text = "x" * 1000
            result = agent._compress_text(text, 100, keep_tail=False)
            assert len(result) <= 110

    def test_very_small_budget(self):
        config = MagicMock()
        config.get.return_value = ""
        memory = MagicMock()
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            text = "x" * 1000
            result = agent._compress_text(text, 30)
            assert len(result) <= 35


class TestCompressSettings:
    """_compress_settings 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            settings = {"world": "修仙世界", "rules": "灵气修炼", "factions": "门派林立"}
            result = agent._compress_settings(settings, 200)
            assert "world" in result
            assert "修仙世界" in result

    def test_empty(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._compress_settings({}, 200)
            assert result == ""

    def test_budget_limit(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            settings = {"world": "x" * 1000, "rules": "y" * 1000}
            result = agent._compress_settings(settings, 50)
            assert isinstance(result, str)


class TestCompressCharacters:
    """_compress_characters 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {"张三": {"personality": "勇敢", "motivation": "复仇"}}
            result = agent._compress_characters(chars, 200)
            assert "张三" in result

    def test_string_info(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {"张三": "勇敢的少年"}
            result = agent._compress_characters(chars, 200)
            assert "张三" in result

    def test_budget_limit(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {f"角色{i}": {"personality": "x" * 100} for i in range(20)}
            result = agent._compress_characters(chars, 100)
            assert len(result) <= 120


class TestCompressActiveCharacters:
    """_compress_active_characters 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}
            result = agent._compress_active_characters(chars, ["张三"], 200)
            assert "张三" in result

    def test_string_info(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {"张三": "勇敢的少年"}
            result = agent._compress_active_characters(chars, ["张三"], 200)
            assert "张三" in result

    def test_budget_limit(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            chars = {f"角色{i}": {"personality": "x" * 100} for i in range(20)}
            result = agent._compress_active_characters(chars, [f"角色{i}" for i in range(20)], 50)
            assert len(result) <= 60


class TestRecordConversation:
    """_record_conversation 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent._log_lock = __import__('threading').Lock()
            agent._conversation_log = []
            agent._record_conversation("Writer", "generate", "测试内容")
            assert len(agent._conversation_log) == 1

    def test_all_agents(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent._log_lock = __import__('threading').Lock()
            agent._conversation_log = []
            for agent_name in ["PlotDesigner", "WorldBuilder", "Writer", "Reviewer", "Editor"]:
                agent._record_conversation(agent_name, "test", "内容")
            assert len(agent._conversation_log) == 5


class TestCallAntiSlopCheck:
    """_call_anti_slop_check 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.log = lambda msg: None
            result = agent._call_anti_slop_check("张三走进了房间。")
            assert isinstance(result, list)

    def test_with_issues(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.log = lambda msg: None
            result = agent._call_anti_slop_check("在这个世界上，然而不过但是。")
            assert isinstance(result, list)


class TestGetKnowledgeGraphContext:
    """_get_knowledge_graph_context 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._get_knowledge_graph_context()
            assert isinstance(result, str)

    def test_with_character(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._get_knowledge_graph_context("张三")
            assert isinstance(result, str)


class TestGetWritingStylePrompt:
    """_get_writing_style_prompt 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._get_writing_style_prompt()
            assert isinstance(result, str)


class TestRegisterTools:
    """_register_tools 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.tools = ToolRegistry()
            agent.memory = MagicMock()
            agent._call_anti_slop_check = lambda c: []
            agent._get_knowledge_graph_context = lambda c=None: ""
            agent._register_tools()
            tools = agent.tools.list_tools()
            assert len(tools) > 0


class TestBuildContext:
    """_build_context 深度测试"""

    def test_basic(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.config = MagicMock()
            agent.config.get.return_value = 10000
            agent.memory = MagicMock()
            agent.memory.get_global_summary.return_value = "全局摘要"
            agent.memory.get_current_volume_summary.return_value = "卷摘要"
            agent.memory.get_characters.return_value = {}
            agent.memory.get_active_characters.return_value = []
            agent.memory.get_recent_summaries.return_value = ""
            agent.memory.retrieve_relevant.return_value = []
            agent.log = lambda msg: None
            
            result = agent._build_context(1, extra_context="世界观设定")
            assert isinstance(result, str)

    def test_with_characters(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.config = MagicMock()
            agent.config.get.return_value = 10000
            agent.memory = MagicMock()
            agent.memory.get_global_summary.return_value = ""
            agent.memory.get_current_volume_summary.return_value = ""
            agent.memory.get_characters.return_value = {"张三": {"personality": "勇敢"}}
            agent.memory.get_active_characters.return_value = ["张三"]
            agent.memory.get_recent_summaries.return_value = ""
            agent.memory.retrieve_relevant.return_value = []
            agent.log = lambda msg: None
            
            result = agent._build_context(1)
            assert isinstance(result, str)

    def test_all_phases(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.config = MagicMock()
            agent.config.get.return_value = 10000
            agent.memory = MagicMock()
            agent.memory.get_global_summary.return_value = "全局"
            agent.memory.get_current_volume_summary.return_value = "卷"
            agent.memory.get_characters.return_value = {}
            agent.memory.get_active_characters.return_value = []
            agent.memory.get_recent_summaries.return_value = ""
            agent.memory.retrieve_relevant.return_value = []
            agent.log = lambda msg: None
            
            for phase in ["opening", "writing", "action", "dialogue", "ending"]:
                result = agent._build_context(1, writing_phase=phase)
                assert isinstance(result, str)

    def test_truncation(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            agent.config = MagicMock()
            agent.config.get.return_value = 100
            agent.memory = MagicMock()
            agent.memory.get_global_summary.return_value = "x" * 1000
            agent.memory.get_current_volume_summary.return_value = "y" * 1000
            agent.memory.get_characters.return_value = {}
            agent.memory.get_active_characters.return_value = []
            agent.memory.get_recent_summaries.return_value = "z" * 1000
            agent.memory.retrieve_relevant.return_value = []
            agent.log = lambda msg: None
            
            result = agent._build_context(1, max_chars=100)
            assert len(result) <= 120


class TestCompressRecentChapters:
    """_compress_recent_chapters 深度测试"""

    def test_single_chapter(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result = agent._compress_recent_chapters("单章内容", 100, 1)
            assert isinstance(result, str)

    def test_multiple_chapters(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            text = "第1章内容\n\n第2章内容\n\n第3章内容"
            result = agent._compress_recent_chapters(text, 50, 3)
            assert isinstance(result, str)


class TestHasExcessiveRepetition:
    """_has_excessive_repetition 深度测试"""

    def test_no_repetition(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            result, msg = agent._has_excessive_repetition("张三走进了房间。李四笑了笑。", 100)
            assert isinstance(result, bool)

    def test_with_repetition(self):
        with patch.object(NovelAgent, '__init__', lambda self, *a, **kw: None):
            agent = NovelAgent.__new__(NovelAgent)
            text = "张三修炼武功。" * 50
            result, msg = agent._has_excessive_repetition(text, 100)
            assert isinstance(result, bool)


class TestExtractCharactersFromRaw:
    """_extract_characters_from_raw 深度测试"""

    def test_basic(self):
        result = NovelAgent._extract_characters_from_raw("张三：勇敢的少年\n李四：聪明的少女")
        assert isinstance(result, dict)

    def test_empty(self):
        result = NovelAgent._extract_characters_from_raw("")
        assert isinstance(result, dict)


class TestNovelAgentInit:
    """NovelAgent 初始化测试"""

    def test_has_all_methods(self):
        methods = [
            'generate_chapter', 'generate_outline', 'generate_characters',
            'generate_settings', 'review_chapter', 'finalize_chapter',
            'analyze_style', 'generate_with_style', 'blend_styles',
            'generate_with_collaboration', 'generate_outline_continuation',
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
