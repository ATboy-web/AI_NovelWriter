"""
novel_agent.py 更多mock测试 - 覆盖generate方法
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch

from app.novel_agent import NovelAgent


def create_mock_agent():
    """创建mock的NovelAgent"""
    agent = NovelAgent.__new__(NovelAgent)
    agent.ai = MagicMock()
    agent.memory = MagicMock()
    agent.log = lambda msg: None
    agent._log_lock = __import__("threading").Lock()
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
        agent._has_excessive_repetition = MagicMock(
            side_effect=[
                (True, 500),  # First call: has repetition
                (False, 1000),  # Second call: no repetition
            ]
        )
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

        with patch("pathlib.Path.mkdir"):
            result = agent.generate_characters("玄幻", "测试小说", 2)
            assert isinstance(result, dict)

    def test_empty_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = Path("/tmp/test")

        with patch("pathlib.Path.mkdir"):
            result = agent.generate_characters("玄幻", "测试小说", 2)
            assert isinstance(result, dict)
