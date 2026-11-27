"""`memory_manager` 的剩余分支（第 1 档：丢稿 / 不可逆）。

## 为什么这些分支比别处更值得测

`memory_manager` 是所有**角色、设定、时间线、记忆块**的落盘层。它出错的方式是：

| 故障 | 用户看到 |
|---|---|
| 退出时没落盘 | 刚写的设定，重启后没了 |
| 用空索引覆盖已有索引 | 检索永久失效（写出去的书再也搜不到前文） |
| 损坏档案被直接覆盖 | 286 个角色变成 3 个，**不可恢复** |
| meta.json 损坏后整体重写 | 章数/主角名等元数据丢失 |

这些**都不会报错**：程序照常运行，只是数据悄悄少了一块。

## 组织方式

按"坏了会丢什么"分组，而不是按函数在文件里的顺序。
"""

from __future__ import annotations

import json
import weakref

import pytest

import app.memory_manager as mm_mod
from app.memory_manager import MemoryManager, _register_flush


@pytest.fixture
def mm(tmp_path):
    return MemoryManager(tmp_path)


class TestExitFlush:
    """退出前落盘 —— 这是"刚写的东西重启后还在不在"的最后一道。"""

    def test_register_flush_is_idempotent(self, monkeypatch):
        """多次注册只挂一个 atexit 钩子，且注册表是弱引用（不阻碍回收）。"""
        monkeypatch.setattr(mm_mod, "_atexit_registered", False)
        monkeypatch.setattr(mm_mod, "_flush_registry", weakref.WeakSet())
        registered: list = []
        monkeypatch.setattr(mm_mod.atexit, "register", lambda fn: registered.append(fn))

        class Dummy:
            def flush(self):
                pass

        # ❗ 必须是可弱引用的对象：`object()` 不能进 WeakSet（TypeError）
        a, b = Dummy(), Dummy()
        _register_flush(a)
        _register_flush(b)

        assert len(registered) == 1, "每个实例都挂一个 atexit 钩子会重复落盘"

    def test_flush_all_survives_one_failure(self, monkeypatch):
        """一个实例落盘失败不能连累其它实例 —— 否则一次异常丢掉全部未落盘数据。"""

        class Boom:
            def flush(self):
                raise RuntimeError("磁盘满")

        class Ok:
            def __init__(self):
                self.called = False

            def flush(self):
                self.called = True

        ok = Ok()
        monkeypatch.setattr(mm_mod, "_flush_registry", weakref.WeakSet([Boom(), ok]))
        # 弱引用集合里 Boom() 没有强引用会被立即回收，这里显式持有
        boom = Boom()
        monkeypatch.setattr(mm_mod, "_flush_registry", weakref.WeakSet([boom, ok]))
        mm_mod._flush_all_on_exit()

        assert ok.called, "一个实例失败导致其它实例没落盘"

    def test_flush_saves_index_and_scores(self, mm):
        mm._inverted_index = {"林风": ["1", "2"]}
        mm._scores_dirty = 1

        mm.flush()

        assert json.loads(mm.inverted_index_file.read_text(encoding="utf-8")) == {"林风": ["1", "2"]}
        assert mm._scores_dirty == 0, "落盘后没清脏标记，下次会重复写"

    def test_flush_skips_when_dir_removed(self, mm):
        """临时目录被清掉后不该再落盘（会抛 FileNotFoundError 吓用户一跳）。"""
        import shutil

        shutil.rmtree(mm.memory_dir)
        mm.flush()  # 不抛即通过

    def test_flush_failure_is_logged_not_raised(self, mm, monkeypatch):
        mm._inverted_index = {"a": ["1"]}

        def boom(*_a, **_kw):
            raise OSError("只读文件系统")

        monkeypatch.setattr(mm, "_save_inverted_index", boom)
        mm.flush()  # 不抛即通过 —— 退出路径抛异常会让进程带错误码退出


class TestCorruptCharacterArchive:
    """🔴 角色档案损坏时必须**先留档再谈修复** —— 直接覆盖等于删掉 286 个角色。"""

    def test_archives_with_timestamp(self, mm):
        mm.characters_file.write_text("{ 坏掉的 JSON", encoding="utf-8")

        dst = mm._archive_corrupt_characters()

        assert dst is not None and dst.exists()
        assert ".corrupt-" in dst.name
        assert dst.read_text(encoding="utf-8") == "{ 坏掉的 JSON"
        assert mm.characters_file.exists(), "留档是复制，原文件必须还在（人工恢复要用）"

    def test_repeated_archive_does_not_overwrite(self, mm):
        """同一秒内连续留档（拒绝写盘 + 用户重试）要各自独立成文件。"""
        mm.characters_file.write_text("{ 坏", encoding="utf-8")

        first = mm._archive_corrupt_characters()
        second = mm._archive_corrupt_characters()

        assert first != second
        assert first.exists() and second.exists()

    def test_missing_file_returns_none(self, mm):
        mm.characters_file.unlink(missing_ok=True)
        assert mm._archive_corrupt_characters() is None

    def test_copy_failure_returns_none(self, mm, monkeypatch):
        """留档失败只记日志返回 None —— 不能让"留档"本身把写盘流程带崩。"""
        mm.characters_file.write_text("{ 坏", encoding="utf-8")

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(mm_mod.shutil, "copy2", boom)
        assert mm._archive_corrupt_characters() is None


class TestInvertedIndexGuard:
    """🔴 倒排索引被空覆盖 ⇒ 检索**永久**失效（写出去的书再也搜不到前文）。"""

    def test_refuses_to_overwrite_nonempty_index_with_empty(self, mm):
        mm.inverted_index_file.write_text(json.dumps({"林风": ["1"]}), encoding="utf-8")
        mm._inverted_index = {}
        mm._inverted_index_load_failed = False

        mm._save_inverted_index()

        assert json.loads(mm.inverted_index_file.read_text(encoding="utf-8")) == {"林风": ["1"]}, "空索引覆盖了已有索引"

    def test_allows_write_when_load_failed(self, mm):
        """索引读坏过（`_inverted_index_load_failed`）⇒ 允许写入，否则永远修不好。"""
        mm.inverted_index_file.write_text(json.dumps({"旧": ["1"]}), encoding="utf-8")
        mm._inverted_index = {"新": ["2"]}
        mm._inverted_index_load_failed = True

        mm._save_inverted_index()

        assert json.loads(mm.inverted_index_file.read_text(encoding="utf-8")) == {"新": ["2"]}

    def test_allows_write_when_existing_is_empty(self, mm):
        mm.inverted_index_file.write_text("{}", encoding="utf-8")
        mm._inverted_index = {"林风": ["1"]}

        mm._save_inverted_index()

        assert json.loads(mm.inverted_index_file.read_text(encoding="utf-8")) == {"林风": ["1"]}

    def test_corrupt_index_sets_failure_flag(self, mm):
        """索引读坏不能只吞掉 —— 要置标记，否则后续写入会触发"拒绝覆盖"死锁。"""
        mm.inverted_index_file.write_text("{ 坏", encoding="utf-8")

        assert mm._load_inverted_index() == {}
        assert mm._inverted_index_load_failed is True

    def test_missing_index_is_not_a_failure(self, mm):
        mm.inverted_index_file.unlink(missing_ok=True)

        assert mm._load_inverted_index() == {}
        assert mm._inverted_index_load_failed is False, "全新作品不该被标记成'索引坏了'"


class TestMetaAndSettings:
    """元数据（章数/主角名）与世界观设定 —— 丢了这些，作品"性格"全变。"""

    def test_get_meta_missing_file(self, mm):
        assert mm.get_meta("chapter_count", default=20) == 20
        assert mm.get_meta() == {}

    def test_get_meta_corrupt_file(self, mm):
        (mm.novel_dir / "meta.json").write_text("{ 坏", encoding="utf-8")

        assert mm.get_meta("chapter_count", default=20) == 20

    def test_set_meta_rebuilds_corrupt_file(self, mm):
        """损坏的 meta.json 被重建而不是让写入失败 —— 否则用户永远改不了设置。"""
        (mm.novel_dir / "meta.json").write_text("{ 坏", encoding="utf-8")

        mm.set_meta("chapter_count", 12)

        assert json.loads((mm.novel_dir / "meta.json").read_text(encoding="utf-8")) == {"chapter_count": 12}

    def test_set_meta_preserves_other_keys(self, mm):
        mm.set_meta("protagonist", "林风")
        mm.set_meta("chapter_count", 30)

        assert mm.get_meta("protagonist") == "林风"

    def test_settings_missing(self, mm):
        assert mm.get_settings() == {}

    def test_save_settings_writes_both_versions(self, mm):
        mm.save_settings({"world": {"name": "青云界"}})

        assert json.loads(mm.settings_file.read_text(encoding="utf-8")) == {"world": {"name": "青云界"}}
        md = mm.settings_file.parent / "settings.md"
        assert md.exists() and "青云界" in md.read_text(encoding="utf-8")

    def test_save_settings_survives_md_failure(self, mm, monkeypatch):
        """Markdown 版是给人看的副本；它失败不能连累 JSON 主数据。"""

        def boom(*_a, **_kw):
            raise OSError("只读")

        monkeypatch.setattr(mm_mod, "atomic_write_text", boom)
        mm.save_settings({"world": {"name": "青云界"}})

        assert json.loads(mm.settings_file.read_text(encoding="utf-8"))["world"]["name"] == "青云界"


class TestChunkIndex:
    """记忆块索引 —— 它坏了，`add_chunk` 会把同一段记忆反复追加。"""

    def _write_page(self, mm, page: int, chunks: list):
        mm.chunks_dir.mkdir(parents=True, exist_ok=True)
        (mm.chunks_dir / f"page_{page:04d}.json").write_text(json.dumps(chunks), encoding="utf-8")

    def test_total_count_across_pages(self, mm):
        self._write_page(mm, 0, [{"id": "a"}, {"id": "b"}])
        self._write_page(mm, 1, [{"id": "c"}])

        assert mm._get_total_chunk_count() == 101, "分页计数按『页数×100 + 末页条数』"

    def test_total_count_no_pages(self, mm):
        assert mm._get_total_chunk_count() == 0

    def test_total_count_corrupt_last_page(self, mm):
        self._write_page(mm, 0, [{"id": "a"}])
        (mm.chunks_dir / "page_0001.json").write_text("{ 坏", encoding="utf-8")

        assert mm._get_total_chunk_count() == 0

    def test_get_chunks_page_missing_and_corrupt(self, mm):
        assert mm._get_chunks_page(0) == []
        self._write_page(mm, 0, [{"id": "a"}])
        (mm.chunks_dir / "page_0000.json").write_text("{ 坏", encoding="utf-8")

        assert mm._get_chunks_page(0) == []

    def test_index_maps_id_to_page(self, mm):
        self._write_page(mm, 0, [{"id": "a"}])
        self._write_page(mm, 2, [{"id": "z"}])

        mm._ensure_chunk_index()

        assert mm._chunk_page_index == {"a": 0, "z": 2}
        assert mm._chunk_index_built is True

    def test_index_is_built_once(self, mm):
        self._write_page(mm, 0, [{"id": "a"}])
        mm._ensure_chunk_index()
        self._write_page(mm, 5, [{"id": "later"}])

        mm._ensure_chunk_index()

        assert "later" not in mm._chunk_page_index, "索引被重复扫描（长跑会越来越慢）"

    def test_index_skips_bad_page_names_and_corrupt(self, mm):
        mm.chunks_dir.mkdir(parents=True, exist_ok=True)
        (mm.chunks_dir / "page_abcd.json").write_text("[]", encoding="utf-8")
        (mm.chunks_dir / "page_0001.json").write_text("{ 坏", encoding="utf-8")

        mm._ensure_chunk_index()  # 不抛即通过

        assert mm._chunk_index_built is True

    def test_merge_chunk_appends_and_tags(self, mm):
        self._write_page(mm, 0, [{"id": "c1", "content": "旧内容", "tags": ["甲"]}])

        mm._merge_chunk("c1", "新增的一段", new_tags=["乙"])

        saved = mm._get_chunks_page(0)[0]
        assert "新增的一段" in saved["content"]
        assert set(saved["tags"]) == {"甲", "乙"}
        assert "updated_at" in saved

    def test_merge_chunk_does_not_duplicate_content(self, mm):
        self._write_page(mm, 0, [{"id": "c1", "content": "旧内容"}])

        mm._merge_chunk("c1", "旧内容")

        assert mm._get_chunks_page(0)[0]["content"] == "旧内容", "同样的内容被追加了两次"

    def test_merge_chunk_falls_back_to_full_scan(self, mm):
        """索引里没有这个 id（例如索引建好后新加的块）⇒ 回退全量扫描，不能直接放弃。"""
        self._write_page(mm, 0, [{"id": "c1", "content": "旧"}])
        mm._ensure_chunk_index()  # 建立索引时还没有 c2
        self._write_page(mm, 0, [{"id": "c1", "content": "旧"}, {"id": "c2", "content": "另一个"}])

        mm._merge_chunk("c2", "补充")

        assert "补充" in mm._get_chunks_page(0)[1]["content"]


class TestTimelineAnnotation:
    """人工批注（地点/故事内时间）—— 写错就与事件对不上，面板还得重做。"""

    def _event(self, mm, chapter=3, event="他推开门", **extra):
        mm.add_event(chapter, event, "story", **extra)
        return f"timeline_{chapter // 100:03d}.json"

    def test_annotate_writes_fields(self, mm):
        self._event(mm)

        assert mm.annotate_event(3, "他推开门", location="山门", confidence=0.9) is True

        rows = mm.get_timeline()
        assert rows[0]["location"] == "山门"
        assert rows[0]["confidence"] == 0.9

    def test_annotate_without_valid_fields_returns_false(self, mm):
        self._event(mm)

        assert mm.annotate_event(3, "他推开门", bogus="x") is False, "非法字段被当成成功写入了"

    def test_annotate_missing_page_returns_false(self, mm):
        assert mm.annotate_event(999, "不存在") is False

    def test_annotate_missing_event_returns_false(self, mm):
        self._event(mm)

        assert mm.annotate_event(3, "根本没发生") is False

    def test_annotate_same_value_returns_false(self, mm):
        self._event(mm, location="山门")

        assert mm.annotate_event(3, "他推开门", location="山门") is False, "没改动却报成功"

    def test_annotate_corrupt_page_returns_false(self, mm):
        name = self._event(mm)
        (mm.timeline_dir / name).write_text("{ 坏", encoding="utf-8")

        assert mm.annotate_event(3, "他推开门", location="山门") is False

    def test_annotate_emits_event_with_record_type(self, mm):
        """广播载荷里的 `type` 必须是**事件自身**的类型，不能是批注字段的值。"""
        self._event(mm)
        seen: list = []

        class Sink:
            def publish(self, topic, payload):
                seen.append(payload)

        mm.set_event_sink(Sink())

        mm.annotate_event(3, "他推开门", location="山门", arc="第一卷")

        assert seen and seen[0]["type"] == "story", f"载荷 type 错了：{seen[0]['type']}"

    def test_get_timeline_range_filters(self, mm):
        mm.add_event(1, "开场")
        mm.add_event(5, "中场")
        mm.add_event(9, "收尾")

        assert [e["event"] for e in mm.get_timeline(from_chapter=5)] == ["中场", "收尾"]
        assert [e["event"] for e in mm.get_timeline(from_chapter=1, to_chapter=5)] == ["开场", "中场"]


class TestCharacterSaveGates:
    """🔴 硬不变式：「已有角色名不可删」。

    两道闸门都在 `save_characters`：
    1. 档案此前读坏过 ⇒ 非 force 时拒绝写入；
    2. 写空集合且主备都不可解析（`STATUS_CORRUPT`）⇒ 拒绝并留档。

    闸门 2 是最容易被"顺手简化"掉的：它要**先判断主备状态**才决定拦不拦 ——
    直接看 `existing` 是否为空会把"文件坏了读不出来的空"误判成"本来就没有角色"。
    """

    def test_empty_write_refused_when_archive_corrupt(self, mm):
        """主备都不可解析 + 写空集合 ⇒ 必须拒绝，并把损坏内容留档。"""
        mm.characters_file.write_text("{ 坏掉的角色档案", encoding="utf-8")
        mm.characters_file.with_name(mm.characters_file.name + ".bak").write_text("{ 也坏", encoding="utf-8")

        with pytest.raises(mm_mod.CharacterDataGuardError) as exc_info:
            mm.save_characters({}, allow_empty=False)

        assert "损坏" in str(exc_info.value)
        archives = list(mm.memory_dir.glob("characters.corrupt-*.json"))
        assert archives, "损坏档案没有被留档 —— 用户失去了人工恢复的可能"

    def test_empty_write_refused_when_existing_characters(self, mm):
        mm.save_characters({"林风": {"personality": "沉默"}})

        with pytest.raises(mm_mod.CharacterDataGuardError):
            mm.save_characters({}, allow_empty=False)

        assert "林风" in mm.get_characters(), "既有角色被清空了"

    def test_empty_write_allowed_with_explicit_flag(self, mm):
        """用户显式要求清空时才清空 —— 这是唯一的合法清空路径。"""
        mm.save_characters({"林风": {"personality": "沉默"}})

        mm.save_characters({}, allow_empty=True)

        assert mm.get_characters() == {}

    def test_force_overrides_corrupt_guard(self, mm):
        """`force=True` 时放行，但**必须先留档** —— 否则证据被彻底覆盖。"""
        mm.characters_file.write_text("{ 坏", encoding="utf-8")
        mm._characters_corrupt = True

        mm.save_characters({"新人": {"personality": "x"}}, force=True)

        assert list(mm.memory_dir.glob("characters.corrupt-*.json")), "force 写入前没留档"
        assert "新人" in mm.get_characters()

    def test_successful_save_clears_corrupt_flag(self, mm):
        mm._characters_corrupt = True
        mm.characters_file.write_text("{ 坏", encoding="utf-8")
        mm.characters_file.with_name(mm.characters_file.name + ".bak").write_text("{ 也坏", encoding="utf-8")

        mm.save_characters({"甲": {"personality": "x"}}, force=True)

        assert mm._characters_corrupt is False, "写成功后标记没清，下次还会拦住写入"


class TestHealthCheck:
    """健康检查是"该整理记忆了"的唯一提示来源。"""

    def test_reports_stale_chunks(self, mm):
        mm.chunks_dir.mkdir(parents=True, exist_ok=True)
        (mm.chunks_dir / "page_0000.json").write_text(
            json.dumps([{"id": "c1", "content": "旧记忆", "type": "event"}]), encoding="utf-8"
        )
        mm._scores = {"c1": {"created_at": "2000-01-01T00:00:00", "references": 0}}

        report = mm.health_check()

        assert report["stale_chunks"], "极旧的记忆块没有被识别为衰减"
        assert any("衰减" in r for r in report["recommendations"])

    def test_recommends_volume_summary(self, mm):
        """章数很多却没有卷摘要 ⇒ 建议生成（否则长文检索全靠倒排索引硬扛）。

        ⚠️ `total_chapters` 是**数章节文件**得来的，不是读 `meta.chapter_count` ——
        用元数据构造这条用例会永远绿（元数据与磁盘不一致时以磁盘为准是对的）。
        """
        mm.chapters_dir.mkdir(parents=True, exist_ok=True)
        for i in range(101):
            (mm.chapters_dir / f"chapter_{i:04d}.txt").write_text("正文", encoding="utf-8")

        report = mm.health_check()

        assert any("卷级摘要" in r for r in report["recommendations"])

    def test_no_recommendations_for_fresh_book(self, mm):
        report = mm.health_check()

        assert report["recommendations"] == []


class TestBuildSmartContext:
    def test_includes_active_characters_and_settings(self, mm):
        mm.save_characters({"林风": {"personality": "沉默寡言，心里压着旧事"}})
        mm.save_settings({"world": {"name": "青云界"}})

        text = mm.build_smart_context(1)

        assert "林风" in text
        assert "青云界" in text

    def test_falls_back_to_reference_order(self, mm):
        """没有任何活跃记录时，退化成"引用次数排序"的前 5 个 —— 不能空着。"""
        mm.save_characters({"甲": {"personality": "冷静"}, "乙": {"personality": "急躁"}})

        text = mm.build_smart_context(999)

        assert "甲" in text or "乙" in text

    def test_non_dict_character_info_is_rendered_as_text(self, mm):
        """旧存档里角色值可能是字符串 —— 不能因此崩掉整个上下文。"""
        mm.save_characters({"甲": "旧格式字符串"})

        text = mm.build_smart_context(1)

        assert "甲" in text


class TestCharacterReadFallbacks:
    """读角色档案的三条降级路径 —— 每一条都对应一次真实事故。"""

    def test_corrupt_sets_flag_and_returns_empty(self, mm):
        mm.characters_file.write_text("{ 坏", encoding="utf-8")
        mm.characters_file.with_name(mm.characters_file.name + ".bak").write_text("{ 也坏", encoding="utf-8")

        assert mm.get_characters() == {}
        assert mm._characters_corrupt is True, "读坏却没置标记，后续写盘会静默覆盖"

    def test_corrupt_with_raise_flag(self, mm):
        mm.characters_file.write_text("{ 坏", encoding="utf-8")
        mm.characters_file.with_name(mm.characters_file.name + ".bak").write_text("{ 也坏", encoding="utf-8")

        with pytest.raises(mm_mod.CharacterDataCorruptError):
            mm.get_characters(raise_on_corrupt=True)

    def test_backup_fallback_clears_flag_and_warns(self, mm):
        """主文件坏但 `.bak` 可用 ⇒ 回退成功，且必须把"档案坏了"的标记清掉。

        标记不清的后果：之后每次 `save_characters` 都会被闸门 1 拦住，
        用户改了角色却永远存不进去。
        """
        mm.characters_file.write_text("{ 坏", encoding="utf-8")
        mm.characters_file.with_name(mm.characters_file.name + ".bak").write_text(
            json.dumps({"林风": {"personality": "沉默"}}), encoding="utf-8"
        )
        mm._characters_corrupt = True

        chars = mm.get_characters()

        assert "林风" in chars
        assert mm._characters_corrupt is False

    def test_non_dict_root_returns_empty(self, mm):
        mm.characters_file.write_text("[]", encoding="utf-8")

        assert mm.get_characters() == {}


class TestUpdateCharacterMerge:
    def test_merges_into_existing_fields(self, mm):
        mm.save_characters({"林风": {"personality": "沉默", "age": 20}})

        mm.update_character("林风", {"age": 21})

        assert mm.get_characters()["林风"] == {"personality": "沉默", "age": 21}

    def test_replaces_when_existing_is_not_dict(self, mm):
        """旧存档里角色值是字符串时整条替换（不能 `dict.update(str)` 崩掉）。"""
        mm.save_characters({"林风": "旧格式"})

        mm.update_character("林风", {"personality": "沉默"})

        assert mm.get_characters()["林风"] == {"personality": "沉默"}


class TestTimelinePaging:
    def test_corrupt_page_is_skipped(self, mm):
        mm.add_event(1, "第一件事")
        mm.add_event(2, "第二件事")
        (mm.timeline_dir / "timeline_000.json").write_text("{ 坏", encoding="utf-8")

        assert mm.get_timeline() == [], "坏掉的分页应当被跳过（而不是抛异常）"

    def test_default_range_limits_to_200_chapters(self, mm):
        """`from_chapter>0` 且未给上界时只看 200 章内 —— 否则长书会全量加载。"""
        mm.add_event(1, "远古")
        mm.add_event(500, "很久以后")
        mm.add_event(520, "更后面")

        events = [e["event"] for e in mm.get_timeline(from_chapter=500)]

        assert "更后面" in events
        assert "远古" not in events


class TestGetDocumentContent:
    """检索命中后要靠它取回正文 —— 取不到就等于"搜到了但打不开"。"""

    def test_chapter_padded_fallback(self, mm):
        """`chapter_1` 与 `chapter_00001` 两种 id 都要能取到同一章。"""
        mm.chapters_dir.mkdir(parents=True, exist_ok=True)
        (mm.chapters_dir / "chapter_00001.txt").write_text("第一章正文", encoding="utf-8")

        assert mm._get_document_content("chapter_1") == "第一章正文"

    def test_chapter_bad_id_returns_empty(self, mm):
        """`chapter_abc` 这类脏 id 只记日志，不能抛异常（检索会带脏 id）。"""
        assert mm._get_document_content("chapter_abc") == ""

    def test_chapter_missing_returns_empty(self, mm):
        assert mm._get_document_content("chapter_999") == ""

    def test_volume_content(self, mm):
        mm.volumes_dir.mkdir(parents=True, exist_ok=True)
        (mm.volumes_dir / "volume_1.txt").write_text("第一卷摘要", encoding="utf-8")

        assert mm._get_document_content("volume_1") == "第一卷摘要"

    def test_arc_content_returns_summary_field(self, mm):
        mm.arcs_dir.mkdir(parents=True, exist_ok=True)
        (mm.arcs_dir / "arc_1.json").write_text(json.dumps({"summary": "弧线摘要"}), encoding="utf-8")

        assert mm._get_document_content("arc_1") == "弧线摘要"

    def test_unknown_prefix_returns_empty(self, mm):
        assert mm._get_document_content("nonsense_1") == ""
