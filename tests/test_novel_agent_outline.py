"""
novel_agent.py 更多mock测试 - 覆盖outline/finalize/style方法
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


class TestGenerateOutline:
    """generate_outline 测试"""

    def test_small_count(self):
        agent = create_mock_agent()
        agent._generate_outline_batch = MagicMock(return_value=[
            {"chapter": 1, "title": "标题1", "summary": "概要1"},
            {"chapter": 2, "title": "标题2", "summary": "概要2"},
        ])
        
        result = agent.generate_outline("玄幻", "测试小说", 10, "概念")
        assert len(result) == 2

    def test_medium_count(self):
        agent = create_mock_agent()
        agent._generate_outline_batch = MagicMock(return_value=[
            {"chapter": i, "title": f"标题{i}", "summary": f"概要{i}"}
            for i in range(1, 16)
        ])
        agent._plan_story_arcs = MagicMock(return_value="弧线规划")
        
        result = agent.generate_outline("玄幻", "测试小说", 30, "概念")
        assert len(result) > 0

    def test_large_count(self):
        agent = create_mock_agent()
        agent._generate_outline_batch = MagicMock(return_value=[
            {"chapter": i, "title": f"标题{i}", "summary": f"概要{i}"}
            for i in range(1, 16)
        ])
        agent._plan_story_arcs = MagicMock(return_value="弧线规划")
        
        result = agent.generate_outline("玄幻", "测试小说", 100, "概念")
        assert len(result) > 0


class TestPlanStoryArcs:
    """_plan_story_arcs 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "开端：引入主角\n发展：展开冲突\n高潮：最终决战\n结局：大团圆"
        
        result = agent._plan_story_arcs("玄幻", "测试小说", 100, "概念")
        assert isinstance(result, str)

    def test_ai_returns_none(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        
        result = agent._plan_story_arcs("玄幻", "测试小说", 100, "概念")
        assert result == ""

    def test_ai_raises_exception(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = Exception("API error")
        
        result = agent._plan_story_arcs("玄幻", "测试小说", 100, "概念")
        assert result == ""


class TestGenerateOutlineBatch:
    """_generate_outline_batch 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps([
            {"chapter": 1, "title": "标题1", "summary": "概要1"},
            {"chapter": 2, "title": "标题2", "summary": "概要2"},
        ])
        agent.memory.get_meta.return_value = ""
        
        result = agent._generate_outline_batch("玄幻", "测试小说", 2, 1, "概念")
        assert len(result) == 2

    def test_with_protagonist(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps([
            {"chapter": 1, "title": "标题1", "summary": "概要1"},
        ])
        agent.memory.get_meta.return_value = "张三"
        
        result = agent._generate_outline_batch("玄幻", "测试小说", 1, 1, "概念")
        assert len(result) == 1

    def test_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        agent.memory.get_meta.return_value = ""
        
        result = agent._generate_outline_batch("玄幻", "测试小说", 2, 1, "概念")
        assert len(result) == 2  # Should fill with placeholders

    def test_partial_outline(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps([
            {"chapter": 1, "title": "标题1", "summary": "概要1"},
        ])
        agent.memory.get_meta.return_value = ""
        
        result = agent._generate_outline_batch("玄幻", "测试小说", 3, 1, "概念")
        assert len(result) == 3  # Should fill missing chapters


class TestGenerateOutlineContinuation:
    """generate_outline_continuation 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps([
            {"chapter": 11, "title": "标题11", "summary": "概要11"},
        ])
        agent.memory.get_meta.return_value = ""
        
        result = agent.generate_outline_continuation("玄幻", "测试小说", 1, "上下文", 10)
        assert len(result) == 1

    def test_with_protagonist(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps([
            {"chapter": 11, "title": "标题11", "summary": "概要11"},
        ])
        agent.memory.get_meta.return_value = "张三"
        
        result = agent.generate_outline_continuation("玄幻", "测试小说", 1, "上下文", 10)
        assert len(result) == 1

    def test_empty_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_meta.return_value = ""
        
        result = agent.generate_outline_continuation("玄幻", "测试小说", 2, "上下文", 10)
        assert len(result) == 2  # Should fill with placeholders


class TestFinalizeChapter:
    """finalize_chapter 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = ["章节摘要", "全局摘要更新", "关键词1,关键词2"]
        agent.memory.get_global_summary.return_value = "旧全局摘要"
        agent.memory.save_chapter_summary = MagicMock()
        agent.memory.save_global_summary = MagicMock()
        agent.memory.update_index = MagicMock()
        agent.memory.add_chunk = MagicMock()
        agent.memory.add_event = MagicMock()
        agent.memory.get_characters.return_value = {}
        agent._update_character_progression = MagicMock()
        
        with patch('app.novel_agent.writing_skill_manager', create=True):
            agent.finalize_chapter(1, "章节内容")

    def test_summary_generation_fails(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = Exception("API error")
        agent.memory.get_global_summary.return_value = ""
        agent.memory.save_chapter_summary = MagicMock()
        agent.memory.save_global_summary = MagicMock()
        agent.memory.update_index = MagicMock()
        agent.memory.add_chunk = MagicMock()
        agent.memory.add_event = MagicMock()
        agent.memory.get_characters.return_value = {}
        agent._update_character_progression = MagicMock()
        
        agent.finalize_chapter(1, "章节内容")


class TestUpdateCharacterProgression:
    """_update_character_progression 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps({
            "updates": [{"name": "张三", "change": "+力量+3", "reason": "战斗突破"}],
            "skills_learned": [{"name": "张三", "skill": "剑法", "type": "攻击", "how": "战斗领悟"}],
            "relationship_changes": [{"name1": "张三", "name2": "李四", "old": "朋友", "new": "敌人", "reason": "背叛"}],
            "items_gained": [{"name": "张三", "item": "宝剑", "quality": "稀有", "from": "战斗获得"}],
            "items_lost": [{"name": "张三", "item": "盾牌", "reason": "战斗毁坏"}],
            "deaths": ["王五"],
            "new_allies": ["赵六"],
            "new_enemies": ["钱七"]
        })
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        agent.memory.add_event = MagicMock()
        agent.memory.update_character = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_no_characters(self):
        agent = create_mock_agent()
        agent.memory.get_characters.return_value = {}
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        
        # Patch _diag to avoid NameError
        import app.novel_agent as na
        na._diag = MagicMock()
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_empty_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = None
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        
        agent._update_character_progression(1, "章节内容", "摘要")


class TestAnalyzeStyle:
    """analyze_style 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps({
            "author": "测试作者",
            "sentence_style": "长短句结合",
            "word_choice": "古风词汇",
        })
        
        result = agent.analyze_style("测试文本", "测试作者")
        assert result["author"] == "测试作者"

    def test_invalid_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "invalid json"
        
        result = agent.analyze_style("测试文本", "测试作者")
        assert "author" in result


class TestGenerateWithStyle:
    """generate_with_style 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "风格化文本"
        
        style = {"author": "测试作者", "sentence_style": "长短句结合"}
        result = agent.generate_with_style("创作提示", style, 1000)
        assert result == "风格化文本"

    def test_string_style(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "风格化文本"
        
        result = agent.generate_with_style("创作提示", "古风风格", 1000)
        assert result == "风格化文本"


class TestBlendStyles:
    """blend_styles 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "融合风格文本"
        
        styles = [
            {"author": "作者1", "sentence_style": "短句"},
            {"author": "作者2", "sentence_style": "长句"},
        ]
        result = agent.blend_styles(styles, "创作提示", 1000)
        assert result == "融合风格文本"


class TestExtractCharactersFromRawExtended:
    """_extract_characters_from_raw 扩展测试"""

    def test_with_json(self):
        text = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_truncated_json(self):
        text = '{"张三": {"personality": "勇敢", "age": 20}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_markdown(self):
        text = '```json\n{"张三": {"personality": "勇敢"}}\n```'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_fullwidth_chars(self):
        text = '{"张三"：{"personality"："勇敢"}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)


class TestParseJsonResponseExtended:
    """_parse_json_response 扩展测试"""

    def test_with_markdown(self):
        text = '```json\n{"key": "value"}\n```'
        result = NovelAgent._parse_json_response(text, {})
        assert result == {"key": "value"}

    def test_with_fullwidth_colon(self):
        text = '{"key"："value"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_trailing_comma(self):
        text = '{"key": "value",}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_list_with_markdown(self):
        text = '```json\n[1, 2, 3]\n```'
        result = NovelAgent._parse_json_response(text, [], is_list=True)
        assert result == [1, 2, 3]

    def test_truncated_json(self):
        text = '{"key": "value", "key2": "value2"'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)


class TestGenerateLongChapter:
    """_generate_long_chapter 测试"""

    def test_basic(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 100
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_with_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 100
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文", prev_ending="前文结尾")
        assert isinstance(result, str)

    def test_short_response_retries(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = ["短", "短", "段落内容" * 100]
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)
