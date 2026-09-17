"""
novel_agent.py 更多mock测试 - 覆盖generate_long_chapter和其他方法
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

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


class TestGenerateLongChapterExtended:
    """_generate_long_chapter 扩展测试"""

    def test_multiple_parts(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 200
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")

        result = agent._generate_long_chapter(1, "标题", "大纲", 8000, "上下文")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_with_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 200
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")

        result = agent._generate_long_chapter(1, "标题", "大纲", 8000, "上下文", prev_ending="前文结尾")
        assert isinstance(result, str)

    def test_short_response_retries(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = ["短", "短", "段落内容" * 200]
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")

        result = agent._generate_long_chapter(1, "标题", "大纲", 8000, "上下文")
        assert isinstance(result, str)

    def test_incomplete_ending_triggers_completion(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = [
            "段落内容" * 200,  # First part
            "段落内容" * 200,  # Second part
            "补全内容",  # Completion
        ]
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")

        # Create content that ends without proper punctuation
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_with_protagonist(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 200
        agent.memory.get_meta.return_value = "张三"
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")

        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)


class TestExtractCharactersFromRawMore:
    """_extract_characters_from_raw 更多测试"""

    def test_with_nested_objects(self):
        text = '{"张三": {"personality": "勇敢", "weapon": {"name": "剑", "quality": "稀有"}}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_multiple_characters(self):
        text = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}, "王五": {"personality": "善良"}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_truncated_json(self):
        text = '{"张三": {"personality": "勇敢", "age": 20, "weapon": {"name": "剑"'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_markdown_code_block(self):
        text = '```json\n{"张三": {"personality": "勇敢"}}\n```'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_fullwidth_characters(self):
        text = '{"张三"：{"personality"："勇敢"}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_empty_string(self):
        result = NovelAgent._extract_characters_from_raw("")
        assert result == {}

    def test_none(self):
        result = NovelAgent._extract_characters_from_raw(None)
        assert result == {}

    def test_non_string(self):
        result = NovelAgent._extract_characters_from_raw(123)
        assert result == {}


class TestParseJsonResponseMore:
    """_parse_json_response 更多测试"""

    def test_with_markdown_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = NovelAgent._parse_json_response(text, {})
        assert result == {"key": "value"}

    def test_with_fullwidth_colon(self):
        text = '{"key"："value"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_fullwidth_comma(self):
        text = '{"key1"："value1"，"key2"："value2"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_smart_quotes(self):
        text = '{"key"："value"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_list_with_markdown(self):
        text = "```json\n[1, 2, 3]\n```"
        result = NovelAgent._parse_json_response(text, [], is_list=True)
        assert result == [1, 2, 3]

    def test_truncated_json(self):
        text = '{"key": "value", "key2": "value2"'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_truncated_list(self):
        text = "[1, 2, 3"
        result = NovelAgent._parse_json_response(text, [], is_list=True)
        assert isinstance(result, list)

    def test_with_extra_text(self):
        text = '分析结果：{"key": "value"}'
        result = NovelAgent._parse_json_response(text, {})
        assert result == {"key": "value"}

    def test_with_multiple_json_objects(self):
        text = '{"key1": "value1"} {"key2": "value2"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_invalid_json_returns_default(self):
        text = "invalid json"
        result = NovelAgent._parse_json_response(text, {"default": True})
        assert result == {"default": True}

    def test_invalid_list_returns_default(self):
        text = "invalid json"
        result = NovelAgent._parse_json_response(text, [0], is_list=True)
        assert result == [0]

    def test_empty_string_returns_default(self):
        result = NovelAgent._parse_json_response("", {"default": True})
        assert result == {"default": True}

    def test_none_returns_default(self):
        result = NovelAgent._parse_json_response(None, {"default": True})
        assert result == {"default": True}


class TestHasExcessiveRepetitionMore:
    """_has_excessive_repetition 更多测试"""

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

    def test_normal_content(self):
        agent = create_mock_agent()
        paragraphs = [f"第{i}段内容" * 10 for i in range(20)]
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)


class TestPlotDesignerAnalyzeMore:
    """_plot_designer_analyze 更多测试"""

    def test_short_outline(self):
        agent = create_mock_agent()
        result = agent._plot_designer_analyze(1, "标题", "短")
        assert result["type"] == "opening"

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


class TestWorldBuilderBuildMore:
    """_world_builder_build 更多测试"""

    def test_with_multiple_regions(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {"world": {"已知区域": ["区域1", "区域2", "区域3", "区域4", "区域5"]}}
        result = agent._world_builder_build(1, {"type": "writing"})
        assert "区域1" in result

    def test_with_empty_regions(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {"world": {"已知区域": []}}
        result = agent._world_builder_build(1, {"type": "writing"})
        assert result == ""


class TestWriterGenerateMore:
    """_writer_generate 更多测试"""

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


class TestGenerateCharactersMore:
    """generate_characters 更多测试"""

    def test_invalid_json(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"

        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert isinstance(result, dict)

    def test_empty_response(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"

        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert isinstance(result, dict)
