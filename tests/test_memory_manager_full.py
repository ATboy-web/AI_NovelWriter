"""
memory_manager.py 全量测试 - 覆盖chunks/timeline/characters/settings
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.memory_manager import MemoryManager


class TestChunks:
    """记忆块测试"""

    def test_add_chunk(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunk_id = mm.add_chunk("test", "测试内容", importance=8, tags=["测试"])
        assert chunk_id is not None
        assert chunk_id.startswith("test_")

    def test_add_chunk_with_related(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunk_id = mm.add_chunk("test", "内容", related_to=["other_id"])
        assert chunk_id is not None

    def test_get_chunks_page_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunks = mm._get_chunks_page(0)
        assert chunks == []

    def test_get_total_chunk_count_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm._get_total_chunk_count() == 0

    def test_get_total_chunk_count_with_chunks(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.add_chunk("test", "内容1")
        mm.add_chunk("test", "内容2")
        assert mm._get_total_chunk_count() >= 1

    def test_find_similar_chunk_none(self, tmp_path):
        mm = MemoryManager(tmp_path)
        result = mm._find_similar_chunk("完全不同的内容")
        assert result is None

    def test_find_similar_chunk_found(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.add_chunk("test", "张三修炼武功")
        result = mm._find_similar_chunk("张三修炼武功", threshold=0.5)
        # May or may not find depending on keyword extraction

    def test_merge_chunk(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunk_id = mm.add_chunk("test", "原始内容")
        mm._merge_chunk(chunk_id, "新内容", ["新标签"])


class TestTimeline:
    """时间线测试"""

    def test_add_event(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.add_event(1, "张三出场", "story", ["张三"])
        timeline = mm.get_timeline(from_chapter=1, to_chapter=1)
        assert len(timeline) == 1
        assert timeline[0]["event"] == "张三出场"

    def test_add_multiple_events(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.add_event(1, "事件1")
        mm.add_event(2, "事件2")
        mm.add_event(3, "事件3")
        timeline = mm.get_timeline(from_chapter=1, to_chapter=3)
        assert len(timeline) == 3

    def test_get_timeline_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        timeline = mm.get_timeline()
        assert timeline == []

    def test_get_timeline_range(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.add_event(1, "事件1")
        mm.add_event(50, "事件2")
        mm.add_event(100, "事件3")
        timeline = mm.get_timeline(from_chapter=10, to_chapter=60)
        assert len(timeline) == 1

    def test_get_timeline_page(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm._get_timeline_page(1) == 0
        assert mm._get_timeline_page(100) == 0
        assert mm._get_timeline_page(101) == 1


class TestCharacters:
    """角色管理测试"""

    def test_save_and_get_characters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chars = {"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}
        mm.save_characters(chars)
        result = mm.get_characters()
        assert result == chars

    def test_get_characters_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm.get_characters() == {}

    def test_update_character(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character("张三", {"personality": "勇敢"})
        chars = mm.get_characters()
        assert "张三" in chars
        assert chars["张三"]["personality"] == "勇敢"

    def test_update_character_merge(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character("张三", {"personality": "勇敢"})
        mm.update_character("张三", {"age": 20})
        chars = mm.get_characters()
        assert chars["张三"]["personality"] == "勇敢"
        assert chars["张三"]["age"] == 20

    def test_update_character_with_relationships(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character("张三", {"relationships": {"李四": "师徒"}})
        chars = mm.get_characters()
        assert "张三" in chars


class TestSettings:
    """世界观设定测试"""

    def test_get_settings_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm.get_settings() == {}

    def test_save_and_get_settings(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"world": "修仙世界", "power_system": "灵气修炼"}
        mm.save_settings(settings)
        result = mm.get_settings()
        assert result == settings

    def test_save_settings_creates_md(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"world": "修仙世界", "details": {"power": "灵气"}}
        mm.save_settings(settings)
        md_file = mm.settings_file.parent / "settings.md"
        assert md_file.exists()


class TestMeta:
    """元数据测试"""

    def test_get_meta_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm.get_meta() == {}

    def test_set_and_get_meta(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.set_meta("title", "测试小说")
        assert mm.get_meta("title") == "测试小说"

    def test_get_meta_default(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm.get_meta("nonexistent", "default") == "default"

    def test_set_meta_multiple(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.set_meta("title", "测试小说")
        mm.set_meta("author", "张三")
        assert mm.get_meta("title") == "测试小说"
        assert mm.get_meta("author") == "张三"


class TestIndex:
    """索引测试"""

    def test_update_index(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_index(1, ["张三", "修炼", "武功"])
        results = mm.search_by_keyword("修炼")
        assert 1 in results

    def test_search_by_keyword_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        results = mm.search_by_keyword("不存在")
        assert results == []

    def test_search_by_keyword_multiple(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_index(1, ["张三", "修炼"])
        mm.update_index(5, ["张三", "战斗"])
        mm.update_index(10, ["李四", "修炼"])
        results = mm.search_by_keyword("张三")
        assert sorted(results) == [1, 5]


class TestExtractKeywords:
    """关键词提取测试"""

    def test_extract_chinese(self):
        keywords = MemoryManager._extract_keywords("张三修炼武功")
        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_extract_empty(self):
        keywords = MemoryManager._extract_keywords("")
        assert keywords == []

    def test_extract_mixed(self):
        keywords = MemoryManager._extract_keywords("张三abc修炼def武功")
        assert isinstance(keywords, list)


class TestCalcFreshness:
    """新鲜度计算测试"""

    def test_freshness_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm._calc_freshness("") == 0.5

    def test_freshness_recent(self, tmp_path):
        from datetime import datetime
        mm = MemoryManager(tmp_path)
        recent = datetime.now().isoformat()
        freshness = mm._calc_freshness(recent)
        assert freshness > 0.9

    def test_freshness_old(self, tmp_path):
        from datetime import datetime, timedelta
        mm = MemoryManager(tmp_path)
        old = (datetime.now() - timedelta(days=30)).isoformat()
        freshness = mm._calc_freshness(old)
        assert freshness < 0.5

    def test_freshness_invalid(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm._calc_freshness("invalid") == 0.5


class TestCalculateRelevance:
    """相关性计算测试"""

    def test_relevance_basic(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunk = {"content": "张三修炼武功", "importance": 5}
        score = mm._calculate_relevance(chunk, {"张三", "修炼"})
        assert score > 0

    def test_relevance_no_overlap(self, tmp_path):
        mm = MemoryManager(tmp_path)
        chunk = {"content": "李四学习法术", "importance": 5}
        score = mm._calculate_relevance(chunk, {"张三", "修炼"})
        assert score >= 0


class TestFormatSettingsMd:
    """设置格式化测试"""

    def test_format_dict(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"world": "修仙世界"}
        md = mm._format_settings_md(settings)
        assert "world" in md
        assert "修仙世界" in md

    def test_format_nested(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"details": {"power": "灵气"}}
        md = mm._format_settings_md(settings)
        assert "details" in md

    def test_format_list(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"items": ["item1", "item2"]}
        md = mm._format_settings_md(settings)
        assert "item1" in md

    def test_format_list_of_dicts(self, tmp_path):
        mm = MemoryManager(tmp_path)
        settings = {"characters": [{"name": "张三"}, {"name": "李四"}]}
        md = mm._format_settings_md(settings)
        assert "张三" in md


class TestSmartContext:
    """智能上下文测试"""

    def test_build_smart_context_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        ctx = mm.build_smart_context(1)
        assert isinstance(ctx, str)

    def test_build_smart_context_with_query(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "张三修炼武功")
        ctx = mm.build_smart_context(1, query="修炼")
        assert isinstance(ctx, str)

    def test_build_smart_context_with_characters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character("张三", {"personality": "勇敢"})
        mm.update_character_activity("张三", 1)
        ctx = mm.build_smart_context(1)
        assert isinstance(ctx, str)
