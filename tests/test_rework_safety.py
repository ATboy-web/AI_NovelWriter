"""`app/rework.py` 的容错与归档（第 1 档：章节回炉，可能覆盖原稿）。

## 这个模块最怕什么

回炉 = **替换用户已经写好的章节**。所以它的安全边界不是"能跑通"，而是：

| 判据 | 坏了会怎样 |
|---|---|
| 队列文件损坏**不覆盖** | 一次读取失败把整份回炉队列清零 |
| 原文快照在**入炉时**做（不是重写后） | 重写失败时原文已改，**回滚无门** |
| 归档版本号"已有最大 + 1" | 嵌套覆盖，历史版本互相吃掉 |
| 归档用原子写 | 写出半截 = "可回滚"变成假的（回滚得到断章） |
| 不允许入炉时抛 `ReworkError` | 静默把人送进队列，后面全乱 |

用例按这些边界组织，而不是按函数顺序。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.rework as rework_mod
from app.rework import (
    QUEUE_FILE,
    ReworkError,
    ReworkRecord,
    ReworkStore,
    _blocker_evidence,
    _read_chapter,
    scan,
)


@pytest.fixture
def novel(tmp_path):
    """最小作品目录：一章正文 + 一本空队列。"""
    base = tmp_path / "book"
    chapters = base / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "chapter_0001.txt").write_text("第一章正文。" * 60, encoding="utf-8")
    (chapters / "chapter_0002.txt").write_text("短。", encoding="utf-8")
    return base


@pytest.fixture
def store(novel):
    return ReworkStore(novel_dir=novel)


class TestReadChapter:
    def test_reads_existing(self, novel):
        assert _read_chapter(novel, 1).startswith("第一章正文")

    def test_missing_returns_empty(self, novel):
        assert _read_chapter(novel, 99) == ""

    def test_unreadable_returns_empty(self, novel, monkeypatch):
        """读不出来只记日志返回空串 —— 回炉面板不该因为一章坏而打不开。"""
        real = Path.read_text

        def boom(self, *a, **kw):
            if "chapter_0001" in str(self):
                raise OSError("文件被占用")
            return real(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", boom)
        assert _read_chapter(novel, 1) == ""


class TestQueuePersistence:
    def test_missing_queue_is_empty(self, store):
        store.load()

        assert store.all() == []

    def test_corrupt_queue_is_not_overwritten(self, store, novel):
        """🔴 队列损坏时只记日志、按空队列继续，**绝不覆盖原文件**。"""
        queue = novel / "rework" / QUEUE_FILE
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text("{ 坏掉的队列", encoding="utf-8")

        store.load()

        assert queue.read_text(encoding="utf-8") == "{ 坏掉的队列", "损坏的队列被覆盖了（证据没了）"

    def test_non_dict_items_are_skipped(self, store, novel):
        queue = novel / "rework" / QUEUE_FILE
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text(
            json.dumps({"records": ["不是字典", {"chapter": 0}, {"chapter": 3, "reason_code": "low_score"}]}),
            encoding="utf-8",
        )

        store.load()

        assert [r.chapter for r in store.all()] == [3], "非法条目或章号 0 被收进了队列"

    def test_save_roundtrip(self, store):
        store.enqueue(1, reason_code="low_score")

        fresh = ReworkStore(novel_dir=store.novel_dir)
        fresh.load()

        assert [r.chapter for r in fresh.all()] == [1]

    def test_save_failure_returns_false(self, store, novel, monkeypatch):
        """落盘失败返回 False 而不是抛 —— 面板要能提示"没存上"。"""

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(rework_mod, "atomic_write_json", boom)

        assert store.save() is False

    def test_store_without_base_dir_is_safe(self):
        """没有作品目录时所有落盘点都要返回空/False，不能崩。"""
        bare = ReworkStore(novel_dir=None)

        assert bare.queue_path is None
        assert bare.archive_dir is None
        assert bare.save() is False
        assert bare.list_versions(1) == []
        assert bare.archive_chapter(1) is None


class TestArchive:
    """🔴 归档是**原文的唯一副本** —— 它坏了就没有回滚可言。"""

    def test_archive_creates_v1(self, novel, store):
        rel = store.archive_chapter(1, "入炉：分数偏低")

        path = Path(novel) / rel
        assert path.exists()
        assert path.read_text(encoding="utf-8").startswith("第一章正文")
        meta = json.loads((path.parent / "v1.meta.json").read_text(encoding="utf-8"))
        assert meta["chapter"] == 1
        assert "分数偏低" in meta["note"]

    def test_versions_increment_without_overwrite(self, novel, store):
        store.archive_chapter(1, "第一次")
        store.archive_chapter(1, "第二次")

        rows = store.list_versions(1)

        assert [r["version"] for r in rows] == [1, 2]
        assert (Path(novel) / rows[0]["path"]).read_text(encoding="utf-8").startswith("第一章正文")

    def test_empty_chapter_is_not_archived(self, novel, store):
        (novel / "chapters" / "chapter_0003.txt").write_text("   \n\n", encoding="utf-8")

        assert store.archive_chapter(3) is None

    def test_archive_failure_returns_none(self, novel, store, monkeypatch):
        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(rework_mod, "atomic_write_text", boom)

        assert store.archive_chapter(1) is None

    def test_list_versions_skips_bad_names_and_meta(self, novel, store):
        folder = Path(novel) / "rework" / "archive" / "ch0071"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "v1.txt").write_text("一", encoding="utf-8")
        (folder / "v1.meta.json").write_text("{ 坏", encoding="utf-8")
        (folder / "junk.txt").write_text("无关文件", encoding="utf-8")

        rows = store.list_versions(71)

        assert len(rows) == 1, "非法文件名被当成版本了"
        assert rows[0]["version"] == 1

    def test_read_version_missing_returns_empty(self, novel, store):
        assert store.read_version(1, 99) == ""

    def test_read_version_unreadable_returns_empty(self, novel, store, monkeypatch):
        store.archive_chapter(1, "x")
        real = Path.read_text

        def boom(self, *a, **kw):
            if "v1.txt" in str(self):
                raise OSError("占用")
            return real(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", boom)
        assert store.read_version(1, 1) == ""


class TestEnqueueGuards:
    def test_empty_chapter_is_refused(self, novel, store):
        """空章节不能入炉。

        ⚠️ `can_enqueue` **不判质量**（不数字数）—— 它只回答"有没有可回炉的东西"。
        字数门槛在 `scan(min_hanzi=...)` 里。这条区分很重要：
        把字数检查塞进 `can_enqueue` 会让"手动送一章短章回炉"这种合理操作被拦掉。
        """
        (novel / "chapters" / "chapter_0009.txt").write_text("   " + chr(10) * 2 + " ", encoding="utf-8")
        ok, why = store.can_enqueue(9)

        assert ok is False
        assert why

    def test_enqueue_raises_when_refused(self, novel, store):
        (novel / "chapters" / "chapter_0009.txt").write_text("", encoding="utf-8")

        with pytest.raises(ReworkError):
            store.enqueue(9, reason_code="low_score")

    def test_force_allows_already_queued_chapter(self, novel, store):
        """`force` 的用途是"已在队列里也重来一次"，不是绕过空正文检查。"""
        store.enqueue(1, reason_code="low_score")
        again = store.enqueue(1, reason_code="manual", force=True)

        assert isinstance(again, ReworkRecord)
        assert again.chapter == 1

    def test_archive_happens_at_enqueue_time(self, novel, store):
        """🔴 原文快照必须在**入炉时**做 —— 等重写完再存就晚了。"""
        store.enqueue(1, reason_code="low_score")

        rows = store.list_versions(1)
        assert rows, "入炉时没有留存原文快照 —— 重写失败将无法回滚"


class TestRecordShape:
    def test_roundtrip_through_dict(self):
        record = ReworkRecord(chapter=7, reason_code="low_score", reason_text="测试")
        restored = ReworkRecord.from_dict(record.as_dict())

        assert restored.chapter == 7
        assert restored.reason_code == "low_score"

    def test_from_dict_ignores_unknown_keys(self):
        """旧版本队列里多出来的字段不能把加载搞崩。"""
        restored = ReworkRecord.from_dict({"chapter": 5, "完全没见过的字段": 1})

        assert restored.chapter == 5


class TestBlockerEvidence:
    def test_returns_none_for_clean_text(self):
        assert _blocker_evidence("他推开门，走了出去。") is None

    def test_scan_failure_does_not_raise(self, monkeypatch):
        """质检失败时跳过该章 —— 扫描是"发现候选"，不该把自己变成故障源。"""

        def boom(*_a, **_kw):
            raise RuntimeError("预设损坏")

        monkeypatch.setattr(rework_mod, "_load_presets_for_scan", boom, raising=False)

        # 直接让内部 import 失败：把模块函数打成抛异常
        import app.writing_presets as wp

        monkeypatch.setattr(wp, "qc_report", boom)

        assert _blocker_evidence("任意正文") is None


class TestScan:
    def test_skips_non_chapter_files(self, novel):
        (novel / "chapters" / "notes.txt").write_text("无关", encoding="utf-8")

        rows = scan(novel, min_hanzi=1)  # 不抛即通过

        assert all(r["chapter"] >= 1 for r in rows)

    def test_skips_short_chapters(self, novel):
        rows = scan(novel, min_hanzi=50)

        assert all(r["chapter"] != 2 for r in rows), "过短章节被当成候选了"

    def test_respects_limit(self, novel):
        rows = scan(novel, min_hanzi=1, limit=1)

        assert len(rows) <= 1
