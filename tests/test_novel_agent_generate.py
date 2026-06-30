"""
novel_agent.py 更多mock测试 - 覆盖generate方法
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


class TestWriterRevise:
    """_writer_revise 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "修订后的内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": ["建议1"], "issues": ["问题1"], "strengths": ["优点1"]}
        result = agent._writer_revise(1, "原文内容", review, "大纲")
        assert result == "修订后的内容"

    def test_with_protagonist(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "修订后的内容"
        agent.memory.get_meta.return_value = "张三"
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": ["建议1"], "issues": ["问题1"], "strengths": ["优点1"]}
        result = agent._writer_revise(1, "原文内容", review, "大纲")
        assert result == "修订后的内容"

    def test_with_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "修订后的内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": [], "issues": [], "strengths": []}
        result = agent._writer_revise(1, "原文内容", review, "大纲", prev_ending="前文结尾")
        assert result == "修订后的内容"

    def test_short_revision_returns_original(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "短"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": [], "issues": [], "strengths": []}
        result = agent._writer_revise(1, "原文内容很长" * 100, review, "大纲")
        assert result == "原文内容很长" * 100

    def test_ai_returns_none(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": [], "issues": [], "strengths": []}
        result = agent._writer_revise(1, "原文内容", review, "大纲")
        assert result == "原文内容"


class TestGenerateChapter:
    """generate_chapter 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.generate_with_collaboration = MagicMock(return_value="章节内容")
        agent._has_excessive_repetition = MagicMock(return_value=(False, 1000))
        
        result = agent.generate_chapter(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_empty_content(self):
        agent = create_mock_agent()
        agent.generate_with_collaboration = MagicMock(return_value="")
        agent._has_excessive_repetition = MagicMock(return_value=(False, 0))
        
        result = agent.generate_chapter(1, "标题", "大纲", 1000)
        assert "生成失败" in result

    def test_with_repetition_retry(self):
        agent = create_mock_agent()
        agent.generate_with_collaboration = MagicMock(return_value="章节内容")
        agent._has_excessive_repetition = MagicMock(side_effect=[
            (True, 500),  # First call: has repetition
            (False, 1000)  # Second call: no repetition
        ])
        agent.ai.chat.return_value = "修订后的内容"
        
        result = agent.generate_chapter(1, "标题", "大纲", 1000)
        assert result == "修订后的内容"


class TestReviewChapter:
    """review_chapter 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 80})
        
        result = agent.review_chapter(1, "章节内容")
        assert result["overall_score"] == 80


class TestGenerateSettings:
    """generate_settings 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"world": {"name": "测试世界"}, "rules": {}, "factions": {}}'
        agent.memory.save_settings = MagicMock()
        
        result = agent.generate_settings("玄幻", "测试小说", "测试概念")
        assert "world" in result

    def test_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        agent.memory.save_settings = MagicMock()
        
        result = agent.generate_settings("玄幻", "测试小说", "测试概念")
        assert "raw" in result

    def test_empty_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.save_settings = MagicMock()
        
        result = agent.generate_settings("玄幻", "测试小说", "测试概念")
        assert isinstance(result, dict)


class TestGenerateCharacters:
    """generate_characters 测试"""

    def test_basic(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}'
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert "张三" in result

    def test_with_protagonist(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}'
        agent.memory.get_meta.return_value = "张三"
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert "张三" in result

    def test_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = Path("/tmp/test")
        
        with patch('pathlib.Path.mkdir'):
            result = agent.generate_characters("玄幻", "测试小说", 2)
            assert isinstance(result, dict)

    def test_empty_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = Path("/tmp/test")
        
        with patch('pathlib.Path.mkdir'):
            result = agent.generate_characters("玄幻", "测试小说", 2)
            assert isinstance(result, dict)


class TestHasExcessiveRepetitionExtended:
    """_has_excessive_repetition 扩展测试"""

    def test_short_content(self):
        agent = create_mock_agent()
        result, words = agent._has_excessive_repetition("短", 1000)
        assert result is True

    def test_no_paragraphs(self):
        agent = create_mock_agent()
        result, words = agent._has_excessive_repetition("没有段落分隔的内容" * 100, 1000)
        assert isinstance(result, bool)

    def test_many_similar_paragraphs(self):
        agent = create_mock_agent()
        paragraphs = ["这是重复的内容" * 10] * 20
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)

    def test_short_paragraphs(self):
        agent = create_mock_agent()
        paragraphs = ["短"] * 20
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)


class TestPlotDesignerAnalyzeExtended:
    """_plot_designer_analyze 扩展测试"""

    def test_json_with_trailing_comma(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"type": "action", "pace": "fast", "foreshadowing": [],}'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "action"

    def test_json_with_extra_text(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '分析结果：{"type": "dialogue", "pace": "slow"}'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "dialogue"


class TestWorldBuilderBuildExtended:
    """_world_builder_build 扩展测试"""

    def test_with_multiple_regions(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {
            "world": {"已知区域": ["区域1", "区域2", "区域3", "区域4", "区域5"]}
        }
        result = agent._world_builder_build(1, {"type": "writing"})
        assert "区域1" in result

    def test_with_empty_regions(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {
            "world": {"已知区域": []}
        }
        result = agent._world_builder_build(1, {"type": "writing"})
        assert result == ""


class TestWriterGenerateExtended:
    """_writer_generate 扩展测试"""

    def test_with_context(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000, context="自定义上下文")
        assert result == "章节内容"

    def test_with_prev_ending_in_context(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="【前一章·第0章结尾】\n前文内容")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == "章节内容"
