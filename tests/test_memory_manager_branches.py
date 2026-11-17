"""记忆管理器的检索、分块、角色持久化与健康检查。

## 为什么这些分支最该被覆盖

`memory_manager` 是"数据资产"最集中的地方：

- `save_characters()` 的两道闸门（**非空守卫** + **降级读后禁止盲写**）是为了
  防止一次误调用把整个角色库抹掉 —— 这类保护**只有出错时才执行**，
  不测就等于没有；
- `_find_similar_chunk` / `_merge_chunk` 决定"同一件事会不会被记两遍"；
- `health_check` 是用户排查问题的入口，它自己崩了最尴尬。

所以这里的用例集中在**保护的边界上**：什么情况下必须拒绝写、拒绝之后
原数据是否完好、以及拒绝时有没有留下可追溯的档案。

## 与既有测试的分工

`test_memory_manager*.py` 已覆盖摘要读写、上下文构建等主流程。
本文件只补"未覆盖的分支"，不重复主流程断言。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.memory_manager import CharacterDataCorruptError, CharacterDataGuardError, MemoryManager


@pytest.fixture()
def memory(tmp_path: Path) -> MemoryManager:
    return MemoryManager(novel_dir=tmp_path)


# ====================================================================== 分块（chunks）


class TestChunks:
    def test_add_and_count(self, memory: MemoryManager):
        memory.add_chunk("plot", "主角在雨夜离开了故乡。")
        assert memory._get_total_chunk_count() == 1

    def test_add_repeated_content_merges(self, memory: MemoryManager):
        """同一段内容重复添加 ⇒ 合并成一块（`references` 累加），不能重复记。"""
        first = memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把断剑。")
        second = memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把断剑。")
        assert first == second, "重复内容应合并到同一块"
        assert memory._get_total_chunk_count() == 1

    def test_similar_content_is_merged_not_duplicated(self, memory: MemoryManager):
        """只改一个字的两段内容必须合并，否则同一件事会被记两遍。"""
        memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把断剑。")
        memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把长枪。")
        assert memory._get_total_chunk_count() == 1

    def test_find_similar_threshold(self, memory: MemoryManager):
        memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把断剑。")
        assert memory._find_similar_chunk("主角在雨夜离开了故乡，带着一把断剑。") is not None
        assert memory._find_similar_chunk("完全不同的另一段内容，讲的是别的事。") is None

    def test_merge_appends_update_marker(self, memory: MemoryManager):
        """相似内容合并时，新内容以 [更新] 标记追加，不覆盖原文。

        `_merge_chunk` 不会增加 `references`（只有 `_increment_reference` 才动它）：
        合并是"补充信息"，不是"又一次被引用"。
        """
        content = "主角在雨夜离开了故乡，带着一把断剑。"
        memory.add_chunk("plot", content)
        memory.add_chunk("plot", content + "雨很大。", tags=["补充"])
        chunk = memory._find_similar_chunk(content)
        assert "[更新]" in chunk["content"], "合并后应保留原文并追加新内容"

    def test_merge_accumulates_tags(self, memory: MemoryManager):
        content = "主角在雨夜离开了故乡，带着一把断剑。"
        memory.add_chunk("plot", content, tags=["雨夜"])
        memory.add_chunk("plot", content, tags=["断剑"])
        chunk = memory._find_similar_chunk(content)
        assert {"雨夜", "断剑"} <= set(chunk["tags"])

    def test_paging(self, memory: MemoryManager):
        """分页存储：写入多条关键词不重叠的记忆，总数要累计。

        内容太像会被 `_find_similar_chunk` 判为重复并合并（相似度
        = 关键词交集 / min(两侧关键词数)，阈值 0.7）—— 这本身是正确行为，
        所以测试数据必须真正不同。
        """
        contents = [
            "林默在苍云城拜入剑宗，师父赐名青锋。",
            "苏言暗中联络商队，把药材运往北境。",
            "妖兽潮冲垮了落星谷的护山大阵。",
            "朝廷派钦差查办盐税舞弊案。",
            "古碑上浮现出失传已久的阵法图。",
        ]
        for text in contents:
            memory.add_chunk("plot", text)
        assert memory._get_total_chunk_count() == len(contents)
        assert len(memory._get_chunks_page(0)) == len(contents)

    def test_get_chunks_page_out_of_range(self, memory: MemoryManager):
        assert memory._get_chunks_page(99) == []

    def test_save_and_reload_page(self, memory: MemoryManager):
        memory._save_chunks_page(7, [{"id": "x", "content": "手工写入"}])
        assert memory._get_chunks_page(7)[0]["id"] == "x"


# ====================================================================== 检索相关度


class TestSearch:
    def test_extract_keywords_filters_stopwords(self):
        keywords = MemoryManager._extract_keywords("主角在雨夜离开了故乡，他带着一把断剑。")
        assert isinstance(keywords, list)
        # 常见虚词不该成为关键词
        assert "的" not in keywords and "了" not in keywords

    def test_extract_keywords_empty(self):
        assert MemoryManager._extract_keywords("") == []

    def test_calculate_relevance_rewards_overlap(self, memory: MemoryManager):
        chunk = {"content": "雨夜 断剑 故乡", "tags": ["雨夜"]}
        high = memory._calculate_relevance(chunk, {"雨夜", "断剑", "故乡"})
        low = memory._calculate_relevance(chunk, {"完全无关"})
        assert high > low

    def test_freshness_decays(self, memory: MemoryManager):
        from datetime import datetime, timedelta

        now = datetime.now().isoformat()
        old = (datetime.now() - timedelta(days=30)).isoformat()
        assert memory._calc_freshness(now) > memory._calc_freshness(old)

    def test_freshness_with_bad_timestamp(self, memory: MemoryManager):
        """时间戳坏了不能抛 —— 返回最低分即可。"""
        assert memory._calc_freshness("不是时间") >= 0

    def test_fallback_search_reads_chapter_summaries(self, memory: MemoryManager):
        """降级检索扫的是章节摘要（chapter_*.txt），不是记忆块。"""
        (memory.chapters_dir / "chapter_001.txt").write_text(
            "林默在雨夜离开故乡，带着断剑前往苍云城。", encoding="utf-8"
        )
        results = memory._fallback_search({"雨夜", "断剑"}, top_k=3)
        assert results
        assert results[0]["id"] == "chapter_001"

    def test_fallback_search_ranks_by_relevance(self, memory: MemoryManager):
        (memory.chapters_dir / "chapter_001.txt").write_text("雨夜 断剑 故乡", encoding="utf-8")
        (memory.chapters_dir / "chapter_002.txt").write_text("雨夜而已，别的不提。", encoding="utf-8")
        results = memory._fallback_search({"雨夜", "断剑", "故乡"}, top_k=5)
        assert results[0]["id"] == "chapter_001", "关键词命中的摘要应排在前面"

    def test_fallback_search_no_keywords_returns_baseline(self, memory: MemoryManager):
        """空关键词不是"返回空"：相关度是加权分，未命中关键词仍有新鲜度+重要性基础分。

        权重 keyword 0.40 / freshness 0.20 / importance 0.30 / ref 0.10，
        所以一篇新写的、importance=5 的摘要基础分 ≈ 0.2 + 0.15 = 0.35。
        记下这个语义，避免有人误以为"没关键词就不该有结果"而改坏排序。
        """
        (memory.chapters_dir / "chapter_001.txt").write_text("任意内容。", encoding="utf-8")
        results = memory._fallback_search(set(), top_k=3)
        assert results, "空关键词仍应返回基础分排序结果"
        assert results[0]["relevance"] > 0

    def test_keyword_match_raises_score(self, memory: MemoryManager):
        """命中关键词的分数必须高于未命中 —— 这是排序有效性的底线。"""
        (memory.chapters_dir / "chapter_001.txt").write_text("雨夜 断剑 故乡", encoding="utf-8")
        hit = memory._fallback_search({"雨夜", "断剑", "故乡"}, top_k=1)[0]["relevance"]
        miss = memory._fallback_search({"完全不相关的词"}, top_k=1)[0]["relevance"]
        assert hit > miss

    def test_fallback_search_empty_novel(self, memory: MemoryManager):
        assert memory._fallback_search({"雨夜"}, top_k=3) == []

    def test_get_document_content_unknown_id(self, memory: MemoryManager):
        assert memory._get_document_content("不存在") == ""


# ====================================================================== 时间线


class TestTimeline:
    def test_add_event_and_read(self, memory: MemoryManager):
        memory.add_event(1, "主角出场", event_type="story", characters_involved=["林默"])
        events = memory.get_timeline()
        assert any(e["event"] == "主角出场" for e in events)

    def test_new_optional_fields_stored(self, memory: MemoryManager):
        """v3 P4b 的 5 个可选字段必须真的落盘（时间线面板要显示"在哪、何时"）。"""
        memory.add_event(
            2,
            "雨夜相遇",
            location="苍云城",
            story_time="第三年春",
            arc="启程",
            source="manual",
            confidence="high",
        )
        event = memory.get_timeline()[0]
        assert event["location"] == "苍云城"
        assert event["story_time"] == "第三年春"
        assert event["arc"] == "启程"
        assert event["source"] == "manual"

    def test_timeline_range_filter(self, memory: MemoryManager):
        for chapter in (1, 2, 3):
            memory.add_event(chapter, f"第{chapter}章事件")
        selected = memory.get_timeline(from_chapter=2, to_chapter=2)
        assert all(e["chapter"] == 2 for e in selected)

    def test_annotate_existing_event(self, memory: MemoryManager):
        memory.add_event(1, "旧事件")
        assert memory.annotate_event(1, "旧事件", location="改为某地") is True
        assert memory.get_timeline()[0]["location"] == "改为某地"

    def test_annotate_missing_event(self, memory: MemoryManager):
        assert memory.annotate_event(1, "不存在的事件", location="x") is False


# ====================================================================== 角色持久化（核心不变式）


class TestCharacterPersistence:
    def test_save_and_read(self, memory: MemoryManager):
        memory.save_characters({"林默": {"role": "主角"}})
        assert memory.get_characters()["林默"]["role"] == "主角"

    def test_empty_overwrite_is_rejected(self, memory: MemoryManager):
        """🔴 核心守卫：磁盘上有角色时，空集合覆盖必须被拒绝。"""
        memory.save_characters({"林默": {"role": "主角"}})
        with pytest.raises(CharacterDataGuardError):
            memory.save_characters({})
        assert memory.get_characters()["林默"]["role"] == "主角", "原数据必须完好"

    def test_empty_overwrite_allowed_when_explicit(self, memory: MemoryManager):
        """显式 `allow_empty=True` = "我确实要清空"。"""
        memory.save_characters({"林默": {"role": "主角"}})
        memory.save_characters({}, allow_empty=True)
        assert memory.get_characters() == {}

    def test_first_save_empty_is_fine(self, memory: MemoryManager):
        """磁盘上本来就没有角色 ⇒ 写空不算"删除"。"""
        memory.save_characters({})
        assert memory.get_characters() == {}

    def test_corrupt_file_is_archived_before_overwrite(self, memory: MemoryManager):
        """文件损坏时必须先留档，再拒绝写入。"""
        memory.characters_file.write_text("{坏掉的 json", encoding="utf-8")
        memory.get_characters()  # 触发降级读，置位 corrupt 标记
        with pytest.raises((CharacterDataGuardError, CharacterDataCorruptError)):
            memory.save_characters({"新角色": {}})
        archived = list(memory.memory_dir.glob("characters.corrupt-*.json"))
        assert archived, "损坏文件必须留档"

    def test_force_skips_gate_but_still_archives(self, memory: MemoryManager):
        memory.characters_file.write_text("{坏掉的 json", encoding="utf-8")
        memory.get_characters()
        memory.save_characters({"新角色": {"role": "配角"}}, force=True)
        assert memory.get_characters()["新角色"]["role"] == "配角"
        assert list(memory.memory_dir.glob("characters.corrupt-*.json"))

    def test_mutate_characters_in_memory(self, memory: MemoryManager):
        memory.save_characters({"林默": {"role": "主角"}})
        memory.mutate_characters(lambda chars: chars.update({"苏言": {"role": "配角"}}) or chars)
        assert set(memory.get_characters()) == {"林默", "苏言"}

    def test_mutate_in_place(self, memory: MemoryManager):
        """mutator 返回 None 表示"就地改完了"，也要能保存。"""
        memory.save_characters({"林默": {"role": "主角"}})

        def mutator(chars):
            chars["林默"]["level"] = 10
            return None

        memory.mutate_characters(mutator)
        assert memory.get_characters()["林默"]["level"] == 10

    def test_update_character_merges_not_replaces(self, memory: MemoryManager):
        """更新角色是**合并**语义 —— 不能把原有字段冲掉。"""
        memory.save_characters({"林默": {"role": "主角", "age": 18}})
        memory.update_character("林默", {"level": 5})
        data = memory.get_characters()["林默"]
        assert data["role"] == "主角" and data["age"] == 18 and data["level"] == 5

    def test_update_character_records_relationship_event(self, memory: MemoryManager):
        memory.save_characters({"林默": {"role": "主角"}})
        memory.update_character("林默", {"relationships": {"苏言": "同门"}})
        events = memory.get_timeline()
        assert any("角色关系更新" in e["event"] for e in events)

    def test_get_characters_raise_on_corrupt(self, memory: MemoryManager):
        memory.characters_file.write_text("{坏", encoding="utf-8")
        with pytest.raises(CharacterDataCorruptError):
            memory.get_characters(raise_on_corrupt=True)


# ====================================================================== 评分


class TestScores:
    def test_update_and_reload(self, memory: MemoryManager):
        """评分先记在内存（P1-5 批量落盘），显式 `_save_scores()` 后才在磁盘上。

        这是刻意的设计：每召回一次就写一次盘，磁盘 IO 会把检索拖慢一个量级。
        """
        chunk_id = memory.add_chunk("plot", "一段值得记住的内容，主角在雨夜离开故乡。")
        memory._update_score(chunk_id, "chunk", importance=9)
        assert chunk_id in memory._scores
        memory._save_scores()
        assert chunk_id in memory._load_scores()

    def test_importance_recorded(self, memory: MemoryManager):
        chunk_id = memory.add_chunk("plot", "另一段内容，主角带着断剑。")
        memory._update_score(chunk_id, "chunk", importance=9)
        assert memory._scores[chunk_id]["importance"] == 9

    def test_importance_only_ratchets_up(self, memory: MemoryManager):
        """`_update_score` 取 max ⇒ 一次低重要性不会把既有的高分降下来。"""
        chunk_id = memory.add_chunk("plot", "再一段内容，讲的是盐税案。")
        memory._update_score(chunk_id, "chunk", importance=9)
        memory._update_score(chunk_id, "chunk", importance=2)
        assert memory._scores[chunk_id]["importance"] == 9

    def test_increment_reference(self, memory: MemoryManager):
        chunk_id = memory.add_chunk("plot", "第三段内容，讲的是妖兽潮。")
        memory._increment_reference(chunk_id)
        memory._increment_reference(chunk_id)
        assert memory._scores[chunk_id]["references"] == 2
        assert "last_referenced" in memory._scores[chunk_id]

    def test_increment_creates_entry_if_missing(self, memory: MemoryManager):
        memory._increment_reference("从未见过的_id")
        assert memory._scores["从未见过的_id"]["references"] == 1

    def test_batch_flush_at_threshold(self, memory: MemoryManager):
        """达到阈值自动落盘 —— 否则进程被杀会丢掉整批评分。"""
        for index in range(memory._scores_save_threshold + 1):
            memory._update_score(f"id_{index}", "chunk")
        assert memory.scores_file.exists()

    def test_save_scores_creates_file(self, memory: MemoryManager):
        memory._mark_scores_dirty()
        memory._save_scores()
        assert memory.scores_file.exists()

    def test_load_scores_on_missing_file(self, memory: MemoryManager):
        assert memory._load_scores() == {}

    def test_corrupt_scores_tolerated(self, memory: MemoryManager):
        memory.scores_file.write_text("{坏", encoding="utf-8")
        assert memory._load_scores() == {}


# ====================================================================== 设置与元信息


class TestSettings:
    def test_save_and_get(self, memory: MemoryManager):
        memory.save_settings({"genre": "玄幻", "pov": "第三人称"})
        settings = memory.get_settings()
        assert settings["genre"] == "玄幻"

    def test_missing_settings_returns_dict(self, memory: MemoryManager):
        assert isinstance(memory.get_settings(), dict)

    def test_meta_roundtrip(self, memory: MemoryManager):
        memory.set_meta("last_chapter", 12)
        assert memory.get_meta("last_chapter") == 12

    def test_meta_default(self, memory: MemoryManager):
        assert memory.get_meta("不存在", default="默认值") == "默认值"

    def test_get_all_meta(self, memory: MemoryManager):
        memory.set_meta("a", 1)
        meta = memory.get_meta()
        assert isinstance(meta, dict) and meta.get("a") == 1

    def test_format_settings_markdown(self, memory: MemoryManager):
        text = memory._format_settings_md({"世界观": "九州", "势力": ["甲", "乙"]})
        assert "世界观" in text and "九州" in text


# ====================================================================== 索引与上下文


class TestIndex:
    def test_update_and_search(self, memory: MemoryManager):
        memory.update_index(1, ["雨夜", "断剑"])
        assert memory.search_by_keyword("雨夜") == [1]

    def test_search_unknown_keyword(self, memory: MemoryManager):
        memory.update_index(1, ["雨夜"])
        assert memory.search_by_keyword("不存在") == []

    def test_index_accumulates(self, memory: MemoryManager):
        memory.update_index(1, ["雨夜"])
        memory.update_index(2, ["雨夜"])
        assert set(memory.search_by_keyword("雨夜")) == {1, 2}

    def test_load_index_on_missing_file(self, memory: MemoryManager):
        assert memory._load_index() == {}

    def test_build_smart_context(self, memory: MemoryManager):
        memory.add_chunk("plot", "主角在雨夜离开了故乡，带着一把断剑。")
        memory.add_event(1, "主角出场")
        context = memory.build_smart_context(chapter_num=2, query="雨夜 断剑")
        assert isinstance(context, str)

    def test_build_smart_context_without_data(self, memory: MemoryManager):
        """没有任何记忆时也要给出可用上下文（不能返回 None）。"""
        assert isinstance(memory.build_smart_context(chapter_num=1), str)


# ====================================================================== 健康检查


class TestHealthCheck:
    def test_reports_counters(self, memory: MemoryManager):
        """`health_check` 是统计报告，不是布尔体检：字段是 total_* 加三类清单。"""
        report = memory.health_check()
        assert {
            "total_chunks",
            "total_chapters",
            "total_volumes",
            "total_characters",
            "total_arcs",
            "stale_chunks",
            "orphan_chunks",
            "recommendations",
        } <= set(report)

    def test_counts_reflect_content(self, memory: MemoryManager):
        memory.save_characters({"林默": {}})
        memory.add_chunk("plot", "林默在苍云城拜入剑宗，师父赐名青锋。")
        report = memory.health_check()
        assert report["total_characters"] == 1
        assert report["total_chunks"] == 1

    def test_corrupt_characters_does_not_crash(self, memory: MemoryManager):
        """角色档案损坏时 health_check 仍要出报告（它正是用来排查这种问题的）。"""
        memory.characters_file.write_text("{坏", encoding="utf-8")
        report = memory.health_check()
        assert isinstance(report, dict)
        assert report["total_characters"] == 0
