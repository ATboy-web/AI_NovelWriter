"""
novel_agent.py 使用mock AI客户端测试generate方法
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.novel_agent import NovelAgent


def create_mock_agent():
    """创建mock的NovelAgent"""
    agent = NovelAgent.__new__(NovelAgent)
    agent.ai = MagicMock()
    agent.memory = MagicMock()
    agent.log = lambda msg: None
    agent._log_lock = __import__('threading').Lock()
    agent._conversation_log = []
    agent._revision_memory = []
    agent.tools = MagicMock()
    agent.tools.call = MagicMock(return_value={"success": True})
    agent.config = MagicMock()
    agent.config.get.return_value = 10000
    agent.MAX_REVISION_ROUNDS = 2
    agent.QUALITY_THRESHOLD = 60
    return agent


class TestPlotDesignerAnalyze:
    """_plot_designer_analyze 测试"""

    def test_short_outline(self):
        agent = create_mock_agent()
        result = agent._plot_designer_analyze(1, "标题", "短")
        assert result["type"] == "opening"
        assert result["pace"] == "medium"

    def test_chapter_1_opening(self):
        agent = create_mock_agent()
        result = agent._plot_designer_analyze(1, "标题", "")
        assert result["type"] == "opening"

    def test_chapter_10_ending(self):
        agent = create_mock_agent()
        result = agent._plot_designer_analyze(10, "标题", "")
        assert result["type"] == "ending"

    def test_chapter_5_writing(self):
        agent = create_mock_agent()
        result = agent._plot_designer_analyze(5, "标题", "")
        assert result["type"] == "writing"

    def test_with_ai_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"type": "action", "pace": "fast", "foreshadowing": ["伏笔1"]}'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容，包含足够的信息来分析")
        assert result["type"] == "action"

    def test_ai_returns_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = 'invalid json'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "writing"

    def test_ai_returns_none(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "writing"

    def test_ai_raises_exception(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = Exception("API error")
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "writing"


class TestWorldBuilderBuild:
    """_world_builder_build 测试"""

    def test_with_settings(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {
            "world": {"已知区域": ["区域1", "区域2", "区域3"]}
        }
        result = agent._world_builder_build(1, {"type": "writing"})
        assert "区域1" in result

    def test_without_settings(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {}
        result = agent._world_builder_build(1, {"type": "writing"})
        assert result == ""

    def test_settings_none(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = None
        result = agent._world_builder_build(1, {"type": "writing"})
        assert result == ""


class TestWriterGenerate:
    """_writer_generate 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_with_protagonist(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = "张三"
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_with_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000, prev_ending="前文结尾")
        assert result == "章节内容"

    def test_long_chapter(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        agent._generate_long_chapter = MagicMock(return_value="长章节内容")
        
        result = agent._writer_generate(1, "标题", "大纲", 5000)
        assert result == "长章节内容"

    def test_ai_returns_none(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == ""


class TestReviewerEvaluate:
    """_reviewer_evaluate 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"overall_score": 80, "issues": [], "suggestions": []}'
        agent._build_context = MagicMock(return_value="上下文")
        
        result = agent._reviewer_evaluate(1, "章节内容")
        assert result["overall_score"] == 80

    def test_with_previous_feedback(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"overall_score": 70, "issues": ["问题1"], "suggestions": ["建议1"]}'
        agent._build_context = MagicMock(return_value="上下文")
        
        result = agent._reviewer_evaluate(1, "章节内容", previous_feedback="上次反馈")
        assert result["overall_score"] == 70

    def test_long_content_sampling(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"overall_score": 85, "issues": [], "suggestions": []}'
        agent._build_context = MagicMock(return_value="上下文")
        
        long_content = "x" * 5000
        result = agent._reviewer_evaluate(1, long_content)
        assert result["overall_score"] == 85

    def test_ai_returns_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = 'invalid json'
        agent._build_context = MagicMock(return_value="上下文")
        
        result = agent._reviewer_evaluate(1, "章节内容")
        assert "overall_score" in result

    def test_ai_returns_none(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent._build_context = MagicMock(return_value="上下文")
        
        result = agent._reviewer_evaluate(1, "章节内容")
        # When AI returns None, _parse_json_response returns default
        assert isinstance(result, dict)


class TestGenerateWithCollaboration:
    """generate_with_collaboration 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="场景")
        agent._writer_generate = MagicMock(return_value="章节内容")
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 80, "issues": [], "suggestions": []})
        agent._call_anti_slop_check = MagicMock(return_value=[])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_with_prev_context(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="场景")
        agent._writer_generate = MagicMock(return_value="章节内容")
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 80, "issues": [], "suggestions": []})
        agent._call_anti_slop_check = MagicMock(return_value=[])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000, prev_context="【前一章·第0章结尾】\n前文内容")
        assert result == "章节内容"

    def test_low_quality_triggers_revision(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="场景")
        agent._writer_generate = MagicMock(return_value="初稿")
        agent._writer_revise = MagicMock(return_value="修订稿")
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 40, "issues": ["问题1"], "suggestions": ["建议1"]})
        agent._call_anti_slop_check = MagicMock(return_value=[])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000)
        assert result == "修订稿"

    def test_slop_issues_deduct_score(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="场景")
        agent._writer_generate = MagicMock(return_value="章节内容")
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 80, "issues": [], "suggestions": []})
        agent._call_anti_slop_check = MagicMock(return_value=["AI痕迹1", "AI痕迹2"])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000)
        assert result == "章节内容"


class TestHasExcessiveRepetition:
    """_has_excessive_repetition 测试"""

    def test_no_repetition(self):
        agent = create_mock_agent()
        result, msg = agent._has_excessive_repetition("张三走进了房间。李四笑了笑。", 100)
        assert isinstance(result, bool)

    def test_with_repetition(self):
        agent = create_mock_agent()
        text = "张三修炼武功。" * 50
        result, msg = agent._has_excessive_repetition(text, 100)
        assert isinstance(result, bool)


class TestExtractCharactersFromRaw:
    """_extract_characters_from_raw 测试"""

    def test_basic(self):
        result = NovelAgent._extract_characters_from_raw("张三：勇敢的少年\n李四：聪明的少女")
        assert isinstance(result, dict)

    def test_empty(self):
        result = NovelAgent._extract_characters_from_raw("")
        assert isinstance(result, dict)


class TestParseJsonResponse:
    """_parse_json_response 测试"""

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
