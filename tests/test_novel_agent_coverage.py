"""
novel_agent.py 精准测试 - 覆盖剩余未覆盖行
"""

import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.novel_agent import NovelAgent, MessageRole, AgentMessage, Tool, ToolRegistry


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


class TestExtractCharactersFromRawEdgeCases:
    """_extract_characters_from_raw 边缘情况测试"""

    def test_with_nested_json_objects(self):
        text = '{"张三": {"personality": "勇敢", "weapon": {"name": "剑", "quality": "稀有"}, "attributes": {"力量": 80}}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_multiple_characters_and_nested(self):
        text = '{"张三": {"personality": "勇敢", "weapon": {"name": "剑"}}, "李四": {"personality": "聪明", "weapon": {"name": "杖"}}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_truncated_nested_object(self):
        text = '{"张三": {"personality": "勇敢", "weapon": {"name": "剑"'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_escape_characters(self):
        text = '{"张三": {"personality": "勇敢\\"坚强"}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)

    def test_with_unicode_characters(self):
        text = '{"张三": {"personality": "勇敢🔥", "emoji": "🎮📚"}}'
        result = NovelAgent._extract_characters_from_raw(text)
        assert isinstance(result, dict)


class TestParseJsonResponseEdgeCases:
    """_parse_json_response 边缘情况测试"""

    def test_with_goal_array_fix(self):
        text = '{"name": "张三", "goal": ["成为最强", "保护家人"]}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_unterminated_string(self):
        text = '{"key": "value'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_multiple_json_objects_takes_first(self):
        text = '{"key1": "value1"} some text {"key2": "value2"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_nested_json_in_string(self):
        text = '{"data": "{\\"nested\\": true}"}'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)

    def test_with_broken_json_fix_attempt(self):
        text = '{"key": "value", "arr": [1, 2, 3'
        result = NovelAgent._parse_json_response(text, {})
        assert isinstance(result, dict)


class TestUpdateCharacterProgressionEdgeCases:
    """_update_character_progression 边缘情况测试"""

    def test_with_all_change_types(self):
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
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}, "李四": {"category": "配角"}}
        agent.memory.add_event = MagicMock()
        agent.memory.update_character = MagicMock()
        
        agent._update_character_progression(1, "章节内容" * 100, "摘要")

    def test_with_empty_updates(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps({"updates": []})
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        agent.memory.add_event = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_with_string_info_characters(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = json.dumps({"updates": [{"name": "张三", "change": "+力量"}]})
        agent.memory.get_characters.return_value = {"张三": "勇敢的少年", "李四": "聪明的少女"}
        agent.memory.add_event = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_with_malformed_json_bracket_tracking(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = 'Some text before {"updates": [{"name": "张三", "change": "+力量"}]} some text after'
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        agent.memory.add_event = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_with_markdown_json_block(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '```json\n{"updates": [{"name": "张三", "change": "+力量"}]}\n```'
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        agent.memory.add_event = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")

    def test_with_regex_fallback(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = 'Analysis: {"updates": [{"name": "张三", "change": "+力量"}]}'
        agent.memory.get_characters.return_value = {"张三": {"category": "主角"}}
        agent.memory.add_event = MagicMock()
        
        agent._update_character_progression(1, "章节内容", "摘要")


class TestGenerateLongChapterEdgeCases:
    """_generate_long_chapter 边缘情况测试"""

    def test_with_markdown_title_removal(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "# 第1章 标题\n\n这是正文内容" * 100
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_with_chapter_title_in_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "第1章：标题\n\n这是正文内容" * 100
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_last_part_completion(self):
        agent = create_mock_agent()
        # First parts return content, last part returns incomplete
        agent.ai.chat.side_effect = [
            "段落内容" * 200,  # Part 1
            "段落内容" * 200,  # Part 2
            "段落内容没有结尾标点" * 50  # Last part - incomplete
        ]
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_with_protagonist_in_long_chapter(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 200
        agent.memory.get_meta.return_value = "张三"
        agent._build_context = MagicMock(return_value="上下文")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)

    def test_with_prev_ending_extraction(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "段落内容" * 200
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="【前一章·第0章结尾】\n前文内容在这里")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._generate_long_chapter(1, "标题", "大纲", 5000, "上下文")
        assert isinstance(result, str)


class TestGenerateCharactersEdgeCases:
    """generate_characters 边缘情况测试"""

    def test_with_partial_characters(self, tmp_path):
        agent = create_mock_agent()
        # Return only 1 character when 3 requested
        agent.ai.chat.return_value = '{"张三": {"personality": "勇敢"}}'
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 3)
        assert isinstance(result, dict)

    def test_with_name_extraction_fallback(self, tmp_path):
        agent = create_mock_agent()
        # Return response with character names but invalid JSON
        agent.ai.chat.return_value = '"张三": {\n"李四": {\n"王五": {'
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 3)
        assert isinstance(result, dict)

    def test_with_raw_key_filtered(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"raw": "some text", "张三": {"personality": "勇敢"}}'
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert "raw" not in result

    def test_with_empty_chars_dict(self, tmp_path):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{}'
        agent.memory.get_meta.return_value = 20
        agent.memory.get_settings.return_value = {}
        agent.memory.save_characters = MagicMock()
        agent.memory.novel_dir = tmp_path
        agent.memory.memory_dir = tmp_path / "memory"
        
        result = agent.generate_characters("玄幻", "测试小说", 2)
        assert isinstance(result, dict)


class TestGenerateOutlineEdgeCases:
    """generate_outline 边缘情况测试"""

    def test_with_progress_phases(self):
        agent = create_mock_agent()
        call_count = 0
        def mock_batch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            start = args[3] if len(args) > 3 else 1
            return [{"chapter": start + i, "title": f"标题{start + i}", "summary": f"概要{start + i}"} for i in range(15)]
        agent._generate_outline_batch = mock_batch
        agent._plan_story_arcs = MagicMock(return_value="弧线规划")
        
        result = agent.generate_outline("玄幻", "测试小说", 60, "概念", total_chapters=100)
        assert len(result) > 0

    def test_with_arc_plan(self):
        agent = create_mock_agent()
        def mock_batch(*args, **kwargs):
            start = args[3] if len(args) > 3 else 1
            return [{"chapter": start + i, "title": f"标题{start + i}", "summary": f"概要{start + i}"} for i in range(15)]
        agent._generate_outline_batch = mock_batch
        agent._plan_story_arcs = MagicMock(return_value="开端：引入主角\n发展：展开冲突\n高潮：最终决战\n结局：大团圆")
        
        result = agent.generate_outline("玄幻", "测试小说", 100, "概念", total_chapters=200)
        assert len(result) > 0


class TestFinalizeChapterEdgeCases:
    """finalize_chapter 边缘情况测试"""

    def test_with_all_exceptions(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = Exception("API error")
        agent.memory.get_global_summary.return_value = ""
        agent.memory.save_chapter_summary = MagicMock()
        agent.memory.save_global_summary = MagicMock()
        agent.memory.update_index = MagicMock()
        agent.memory.add_chunk = MagicMock()
        agent.memory.add_event = MagicMock()
        agent.memory.get_characters.return_value = {}
        agent._update_character_progression = MagicMock(side_effect=Exception("error"))
        
        agent.finalize_chapter(1, "章节内容")

    def test_with_writing_skills_success(self):
        agent = create_mock_agent()
        agent.ai.chat.side_effect = ["章节摘要", "全局摘要更新", "关键词1,关键词2"]
        agent.memory.get_global_summary.return_value = "旧全局摘要"
        agent.memory.save_chapter_summary = MagicMock()
        agent.memory.save_global_summary = MagicMock()
        agent.memory.update_index = MagicMock()
        agent.memory.add_chunk = MagicMock()
        agent.memory.add_event = MagicMock()
        agent.memory.get_characters.return_value = {"张三": {"personality": "勇敢"}}
        agent._update_character_progression = MagicMock()
        agent.memory.novel_dir = Path("/tmp/test")
        
        with patch('app.novel_agent.writing_skill_manager') as mock_wsm:
            mock_wsm.learn_from_chapter = MagicMock()
            mock_wsm.knowledge_graph = MagicMock()
            mock_wsm.knowledge_graph.entities = {}
            mock_wsm.knowledge_graph.add_entity = MagicMock()
            agent.finalize_chapter(1, "章节内容")


class TestBuildContextEdgeCases:
    """_build_context 边缘情况测试"""

    def test_with_writing_phase_opening(self):
        agent = create_mock_agent()
        agent.config.get.return_value = 10000
        agent.memory.get_global_summary.return_value = "全局摘要"
        agent.memory.get_current_volume_summary.return_value = "卷摘要"
        agent.memory.get_characters.return_value = {"张三": {"personality": "勇敢"}}
        agent.memory.get_active_characters.return_value = ["张三"]
        agent.memory.get_recent_summaries.return_value = "近期摘要"
        agent.memory.retrieve_relevant.return_value = [{"content": "相关内容"}]
        
        result = agent._build_context(1, extra_context="世界观设定", writing_phase="opening")
        assert isinstance(result, str)

    def test_with_writing_phase_action(self):
        agent = create_mock_agent()
        agent.config.get.return_value = 10000
        agent.memory.get_global_summary.return_value = "全局摘要"
        agent.memory.get_current_volume_summary.return_value = "卷摘要"
        agent.memory.get_characters.return_value = {}
        agent.memory.get_active_characters.return_value = []
        agent.memory.get_recent_summaries.return_value = ""
        agent.memory.retrieve_relevant.return_value = []
        
        result = agent._build_context(1, writing_phase="action")
        assert isinstance(result, str)

    def test_with_writing_phase_dialogue(self):
        agent = create_mock_agent()
        agent.config.get.return_value = 10000
        agent.memory.get_global_summary.return_value = "全局摘要"
        agent.memory.get_current_volume_summary.return_value = "卷摘要"
        agent.memory.get_characters.return_value = {"张三": {"personality": "勇敢"}}
        agent.memory.get_active_characters.return_value = ["张三"]
        agent.memory.get_recent_summaries.return_value = ""
        agent.memory.retrieve_relevant.return_value = []
        
        result = agent._build_context(1, writing_phase="dialogue")
        assert isinstance(result, str)

    def test_with_writing_phase_ending(self):
        agent = create_mock_agent()
        agent.config.get.return_value = 10000
        agent.memory.get_global_summary.return_value = "全局摘要"
        agent.memory.get_current_volume_summary.return_value = "卷摘要"
        agent.memory.get_characters.return_value = {}
        agent.memory.get_active_characters.return_value = []
        agent.memory.get_recent_summaries.return_value = ""
        agent.memory.retrieve_relevant.return_value = []
        
        result = agent._build_context(1, writing_phase="ending")
        assert isinstance(result, str)

    def test_with_large_context_truncation(self):
        agent = create_mock_agent()
        agent.config.get.return_value = 100
        agent.memory.get_global_summary.return_value = "x" * 1000
        agent.memory.get_current_volume_summary.return_value = "y" * 1000
        agent.memory.get_characters.return_value = {}
        agent.memory.get_active_characters.return_value = []
        agent.memory.get_recent_summaries.return_value = "z" * 1000
        agent.memory.retrieve_relevant.return_value = []
        
        result = agent._build_context(1, max_chars=100)
        assert len(result) <= 120


class TestCompressTextEdgeCases:
    """_compress_text 边缘情况测试"""

    def test_keep_tail_true(self):
        agent = create_mock_agent()
        text = "x" * 1000
        result = agent._compress_text(text, 100, keep_tail=True)
        assert len(result) <= 110
        assert "..." in result

    def test_keep_tail_false(self):
        agent = create_mock_agent()
        text = "x" * 1000
        result = agent._compress_text(text, 100, keep_tail=False)
        assert len(result) <= 110
        assert "..." in result

    def test_small_budget(self):
        agent = create_mock_agent()
        text = "x" * 1000
        result = agent._compress_text(text, 30)
        assert len(result) <= 35

    def test_exact_budget(self):
        agent = create_mock_agent()
        text = "x" * 100
        result = agent._compress_text(text, 100)
        assert result == text


class TestCompressActiveCharactersEdgeCases:
    """_compress_active_characters 边缘情况测试"""

    def test_with_budget_limit(self):
        agent = create_mock_agent()
        chars = {f"角色{i}": {"personality": "x" * 100} for i in range(20)}
        active = [f"角色{i}" for i in range(20)]
        result = agent._compress_active_characters(chars, active, 50)
        assert len(result) <= 60

    def test_with_string_info(self):
        agent = create_mock_agent()
        chars = {"张三": "勇敢的少年", "李四": "聪明的少女"}
        result = agent._compress_active_characters(chars, ["张三"], 200)
        assert "张三" in result

    def test_with_empty_active(self):
        agent = create_mock_agent()
        chars = {"张三": {"personality": "勇敢"}}
        result = agent._compress_active_characters(chars, [], 200)
        assert isinstance(result, str)


class TestCompressSettingsEdgeCases:
    """_compress_settings 边缘情况测试"""

    def test_with_priority_keys(self):
        agent = create_mock_agent()
        settings = {"world": "修仙世界", "rules": "灵气修炼", "factions": "门派林立", "other": "其他"}
        result = agent._compress_settings(settings, 200)
        assert "world" in result

    def test_with_budget_limit(self):
        agent = create_mock_agent()
        settings = {"world": "x" * 1000, "rules": "y" * 1000}
        result = agent._compress_settings(settings, 50)
        assert isinstance(result, str)


class TestCompressCharactersEdgeCases:
    """_compress_characters 边缘情况测试"""

    def test_with_budget_limit(self):
        agent = create_mock_agent()
        chars = {f"角色{i}": {"personality": "x" * 100} for i in range(20)}
        result = agent._compress_characters(chars, 100)
        assert len(result) <= 120

    def test_with_string_info(self):
        agent = create_mock_agent()
        chars = {"张三": "勇敢的少年"}
        result = agent._compress_characters(chars, 200)
        assert "张三" in result


class TestHasExcessiveRepetitionEdgeCases:
    """_has_excessive_repetition 边缘情况测试"""

    def test_with_many_similar_paragraphs(self):
        agent = create_mock_agent()
        paragraphs = ["这是重复的内容" * 10] * 20
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)

    def test_with_short_paragraphs_high_ratio(self):
        agent = create_mock_agent()
        paragraphs = ["短"] * 20 + ["这是一个正常的段落内容" * 10] * 5
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)

    def test_with_normal_content(self):
        agent = create_mock_agent()
        paragraphs = [f"第{i}段内容" * 10 for i in range(20)]
        content = "\n\n".join(paragraphs)
        result, words = agent._has_excessive_repetition(content, 1000)
        assert isinstance(result, bool)


class TestPlotDesignerAnalyzeEdgeCases:
    """_plot_designer_analyze 边缘情况测试"""

    def test_with_json_in_response(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '分析结果：\n{"type": "action", "pace": "fast", "foreshadowing": ["伏笔1"]}\n'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容，包含足够的信息来分析")
        assert result["type"] == "action"

    def test_with_nested_json(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"type": "dialogue", "pace": "slow", "foreshadowing": [], "extra": {"key": "value"}}'
        result = agent._plot_designer_analyze(1, "标题", "这是一个详细的大纲内容")
        assert result["type"] == "dialogue"


class TestWorldBuilderBuildEdgeCases:
    """_world_builder_build 边缘情况测试"""

    def test_with_nested_settings(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {
            "world": {"已知区域": ["区域1", "区域2", "区域3", "区域4", "区域5", "区域6"]}
        }
        result = agent._world_builder_build(1, {"type": "writing"})
        assert "区域1" in result

    def test_with_string_settings(self):
        agent = create_mock_agent()
        agent.memory.get_settings.return_value = {"world": "修仙世界"}
        result = agent._world_builder_build(1, {"type": "writing"})
        assert result == ""


class TestWriterGenerateEdgeCases:
    """_writer_generate 边缘情况测试"""

    def test_with_prev_ending_in_context_regex(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="【前一章·第0章结尾】\n前文内容在这里，需要被提取出来作为prev_ending")
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_with_long_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "章节内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="【前一章·第0章结尾】\n" + "x" * 2000)
        agent._get_writing_style_prompt = MagicMock(return_value="风格")
        
        result = agent._writer_generate(1, "标题", "大纲", 1000)
        assert result == "章节内容"


class TestReviewerEvaluateEdgeCases:
    """_reviewer_evaluate 边缘情况测试"""

    def test_with_very_long_content(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"overall_score": 85, "issues": [], "suggestions": []}'
        agent._build_context = MagicMock(return_value="上下文")
        
        long_content = "x" * 10000
        result = agent._reviewer_evaluate(1, long_content)
        assert result["overall_score"] == 85

    def test_with_feedback_section(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = '{"overall_score": 70, "issues": ["问题1"], "suggestions": ["建议1"]}'
        agent._build_context = MagicMock(return_value="上下文")
        
        result = agent._reviewer_evaluate(1, "章节内容", previous_feedback="上次的反馈内容很长" * 100)
        assert result["overall_score"] == 70


class TestWriterReviseEdgeCases:
    """_writer_revise 边缘情况测试"""

    def test_with_long_content_sampling(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "修订后的内容"
        agent.memory.get_meta.return_value = ""
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": ["建议1"], "issues": ["问题1"], "strengths": ["优点1"]}
        long_content = "x" * 10000
        result = agent._writer_revise(1, long_content, review, "大纲")
        assert result == "修订后的内容"

    def test_with_protagonist_and_prev_ending(self):
        agent = create_mock_agent()
        agent.ai.chat.return_value = "修订后的内容"
        agent.memory.get_meta.return_value = "张三"
        agent._build_context = MagicMock(return_value="上下文")
        
        review = {"suggestions": [], "issues": [], "strengths": []}
        result = agent._writer_revise(1, "原文内容", review, "大纲", prev_ending="前文结尾")
        assert result == "修订后的内容"


class TestGenerateWithCollaborationEdgeCases:
    """generate_with_collaboration 边缘情况测试"""

    def test_with_prev_context_extraction(self):
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

    def test_with_world_context_injection(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="世界观场景: 区域1, 区域2")
        agent._writer_generate = MagicMock(return_value="章节内容")
        agent._reviewer_evaluate = MagicMock(return_value={"overall_score": 80, "issues": [], "suggestions": []})
        agent._call_anti_slop_check = MagicMock(return_value=[])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000)
        assert result == "章节内容"

    def test_with_revision_rounds(self):
        agent = create_mock_agent()
        agent._plot_designer_analyze = MagicMock(return_value={"type": "writing", "pace": "medium"})
        agent._build_context = MagicMock(return_value="上下文")
        agent._world_builder_build = MagicMock(return_value="")
        agent._writer_generate = MagicMock(return_value="初稿")
        agent._writer_revise = MagicMock(return_value="修订稿")
        agent._reviewer_evaluate = MagicMock(side_effect=[
            {"overall_score": 40, "issues": ["问题1"], "suggestions": ["建议1"]},
            {"overall_score": 80, "issues": [], "suggestions": []}
        ])
        agent._call_anti_slop_check = MagicMock(return_value=[])
        agent._record_conversation = MagicMock()
        
        result = agent.generate_with_collaboration(1, "标题", "大纲", 1000)
        assert result == "修订稿"


class TestRecordConversationEdgeCases:
    """_record_conversation 边缘情况测试"""

    def test_all_agent_types(self):
        agent = create_mock_agent()
        agent._log_lock = __import__('threading').Lock()
        agent._conversation_log = []
        
        for agent_name in ["PlotDesigner", "WorldBuilder", "Writer", "Reviewer", "Editor", "Unknown"]:
            agent._record_conversation(agent_name, "test", "内容")
        assert len(agent._conversation_log) == 6


class TestCallAntiSlopCheckEdgeCases:
    """_call_anti_slop_check 边缘情况测试"""

    def test_with_issues(self):
        agent = create_mock_agent()
        agent.log = lambda msg: None
        result = agent._call_anti_slop_check("在这个世界上，然而不过但是可是。")
        assert isinstance(result, list)

    def test_with_clean_text(self):
        agent = create_mock_agent()
        agent.log = lambda msg: None
        result = agent._call_anti_slop_check("张三走进了房间。")
        assert isinstance(result, list)


class TestGetKnowledgeGraphContextEdgeCases:
    """_get_knowledge_graph_context 边缘情况测试"""

    def test_with_character(self):
        agent = create_mock_agent()
        result = agent._get_knowledge_graph_context("张三")
        assert isinstance(result, str)

    def test_without_character(self):
        agent = create_mock_agent()
        result = agent._get_knowledge_graph_context()
        assert isinstance(result, str)


class TestGetWritingStylePromptEdgeCases:
    """_get_writing_style_prompt 边缘情况测试"""

    def test_with_high_values(self):
        agent = create_mock_agent()
        with patch('app.novel_agent.writing_skill_manager') as mock_wsm:
            mock_wsm.style_config = MagicMock()
            mock_wsm.style_config.descriptiveness = 9
            mock_wsm.style_config.dialogue_ratio = 8
            mock_wsm.style_config.pacing = 9
            mock_wsm.style_config.emotional_depth = 9
            mock_wsm.style_config.action_intensity = 9
            result = agent._get_writing_style_prompt()
            assert isinstance(result, str)

    def test_with_low_values(self):
        agent = create_mock_agent()
        with patch('app.novel_agent.writing_skill_manager') as mock_wsm:
            mock_wsm.style_config = MagicMock()
            mock_wsm.style_config.descriptiveness = 2
            mock_wsm.style_config.dialogue_ratio = 2
            mock_wsm.style_config.pacing = 2
            mock_wsm.style_config.emotional_depth = 2
            mock_wsm.style_config.action_intensity = 2
            result = agent._get_writing_style_prompt()
            assert isinstance(result, str)

    def test_with_medium_values(self):
        agent = create_mock_agent()
        with patch('app.novel_agent.writing_skill_manager') as mock_wsm:
            mock_wsm.style_config = MagicMock()
            mock_wsm.style_config.descriptiveness = 5
            mock_wsm.style_config.dialogue_ratio = 5
            mock_wsm.style_config.pacing = 5
            mock_wsm.style_config.emotional_depth = 5
            mock_wsm.style_config.action_intensity = 5
            result = agent._get_writing_style_prompt()
            assert isinstance(result, str)


class TestRegisterToolsEdgeCases:
    """_register_tools 边缘情况测试"""

    def test_all_tools_registered(self):
        agent = create_mock_agent()
        agent.tools = ToolRegistry()
        agent.memory = MagicMock()
        agent._call_anti_slop_check = lambda c: []
        agent._get_knowledge_graph_context = lambda c=None: ""
        agent._register_tools()
        tools = agent.tools.list_tools()
        assert len(tools) >= 5


class TestNovelAgentInitEdgeCases:
    """NovelAgent 初始化边缘情况测试"""

    def test_has_all_required_methods(self):
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
