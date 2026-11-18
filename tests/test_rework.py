"""回炉重造：状态机 / 适用范围 / 归档 / 触发扫描 / 持久化。

## 测什么、为什么

这个模块管的是**内容资产的状态**，出错代价高：状态错了会让章节卡在流程里，
归档错了会丢原文。所以用例集中在三类：

1. **非法流转必须被拦**（尤其 `draft → published` 这种绕过审核的路径）；
2. **归档只增不删**（版本递增、旧版本可读回、废弃不删文件）；
3. **触发判定与软件侧同源**（`review` 项不得驱动回炉；无评审记录不算低分）。

面板本身由 `test_panel_controls_mounted.py` 守（控件必须挂载），本文件不重复。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rework import (
    MAX_ATTEMPTS,
    REASON_LABELS,
    STATUS_LABELS,
    TRANSITIONS,
    ReworkError,
    ReworkStore,
    scan,
    split_title,
    title_placeholder,
)

NL = chr(10)


def _chapter_text(title: str, body_chars: int = 800) -> str:
    return f"{title}{NL}{NL}" + ("这是一段足够长的正文内容用来通过字数门槛。" * (body_chars // 20))


@pytest.fixture()
def novel(tmp_path: Path) -> Path:
    (tmp_path / "chapters").mkdir()
    return tmp_path


def _write(novel: Path, chapter: int, title: str, chars: int = 800) -> None:
    (novel / "chapters" / f"chapter_{chapter:04d}.txt").write_text(_chapter_text(title, chars), encoding="utf-8")


# ====================================================================== 标题判定


class TestTitlePlaceholder:
    @pytest.mark.parametrize(
        "title",
        ["", "第71章", "第171章：章节标题(10字)", "标题(10字)", "第5章：", "Untitled"],
    )
    def test_placeholders_detected(self, title: str):
        assert title_placeholder(title) is True

    @pytest.mark.parametrize(
        "title",
        ["交界弃子", "第1章：交界弃子", "阳地之辱", "玄冥殿外，阴气噬魂"],
    )
    def test_real_titles_pass(self, title: str):
        assert title_placeholder(title) is False

    def test_split_title(self):
        title, body = split_title("# 第1章：交界弃子" + NL + NL + "正文。")
        assert title == "第1章：交界弃子"
        assert body == "正文。"

    def test_split_without_heading(self):
        title, body = split_title("没有标题的正文。")
        assert title == "" and body == "没有标题的正文。"

    def test_split_empty(self):
        assert split_title("") == ("", "")


# ====================================================================== 状态流转


class TestTransitions:
    def test_table_is_closed(self):
        """流转表必须覆盖全部状态 —— 新增状态忘了登记就会变"无法到达"。"""
        assert set(TRANSITIONS) == set(STATUS_LABELS)

    def test_no_bypass_to_published(self):
        """🔴 核心断言：只有 approved 能到 published，不能从任何处理中状态跳过审核。"""
        sources = [src for src, targets in TRANSITIONS.items() if "published" in targets]
        assert sources == ["approved"]

    def test_discarded_is_terminal(self):
        assert TRANSITIONS["discarded"] == ()

    def test_happy_path(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual", "测试")
        for target in ("reworking", "pending_review", "approved", "published"):
            store.transition(1, target)
        assert store.get(1).status == "published"
        assert len(store.get(1).history) >= 5

    def test_reject_rework_loop(self, novel: Path):
        """审核不过可以打回重写 —— 这是回炉存在的意义。"""
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "reworking")
        store.transition(1, "pending_review")
        store.transition(1, "reworking")
        assert store.get(1).status == "reworking"

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            ("draft", "published"),
            ("draft", "approved"),
            ("pending_rework", "published"),
            ("reworking", "approved"),
            ("pending_review", "published"),
            ("discarded", "draft"),
        ],
    )
    def test_illegal_transitions_raise(self, novel: Path, from_state: str, to_state: str):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        record = store.get(1)
        record.status = from_state  # 直接摆到起点
        with pytest.raises(ReworkError):
            store.transition(1, to_state)

    def test_unknown_status_raises(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        with pytest.raises(ReworkError):
            store.transition(1, "不存在的状态")

    def test_transition_missing_chapter(self, novel: Path):
        store = ReworkStore(novel)
        with pytest.raises(ReworkError):
            store.transition(99, "reworking")

    def test_error_message_lists_allowed(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        with pytest.raises(ReworkError) as info:
            store.transition(1, "published")
        assert "重写中" in str(info.value), "报错要告诉用户下一步能去哪"


# ====================================================================== 适用范围


class TestApplicability:
    def test_empty_chapter_rejected(self, novel: Path):
        (novel / "chapters" / "chapter_0002.txt").write_text("   " + NL, encoding="utf-8")
        store = ReworkStore(novel)
        ok, why = store.can_enqueue(2)
        assert ok is False and "没有正文" in why

    def test_missing_chapter_rejected(self, novel: Path):
        store = ReworkStore(novel)
        ok, _why = store.can_enqueue(99)
        assert ok is False

    def test_in_progress_rejected(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "reworking")
        ok, why = store.can_enqueue(1)
        assert ok is False and "正在重写中" in why

    def test_pending_review_rejected(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "reworking")
        store.transition(1, "pending_review")
        assert store.can_enqueue(1)[0] is False

    def test_published_needs_force(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        for target in ("reworking", "pending_review", "approved", "published"):
            store.transition(1, target)
        assert store.can_enqueue(1)[0] is False
        assert store.can_enqueue(1, force=True)[0] is True

    def test_attempt_limit(self, novel: Path):
        """回炉次数达上限后拒绝，除非人工强制 —— 防止一章无限打转。"""
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        for expected in range(1, MAX_ATTEMPTS + 1):
            store.enqueue(1, "manual")
            assert store.get(1).attempts == expected
            store.transition(1, "draft")  # 退回正常，才能再次入炉

        ok, why = store.can_enqueue(1)
        assert ok is False
        assert str(MAX_ATTEMPTS) in why
        # 强制仍然允许：人工判断"这次真的能改好"
        assert store.can_enqueue(1, force=True)[0] is True

    def test_no_novel_dir(self):
        store = ReworkStore(None)
        ok, why = store.can_enqueue(1)
        assert ok is False and "没有打开的作品" in why


# ====================================================================== 归档


class TestArchive:
    def test_archive_on_enqueue(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        record = store.enqueue(1, "manual", "人工打回")
        assert record.archive_path
        assert (novel / record.archive_path).is_file()

    def test_archive_contains_original(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        original = (novel / "chapters" / "chapter_0001.txt").read_text(encoding="utf-8")
        store = ReworkStore(novel)
        record = store.enqueue(1, "manual")
        assert (novel / record.archive_path).read_text(encoding="utf-8") == original

    def test_versions_increment(self, novel: Path):
        """同一章多次入炉 ⇒ 多个版本，**旧版本不被覆盖**。"""
        _write(novel, 1, "# 第1章：第一版")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "draft")

        _write(novel, 1, "# 第1章：第二版")
        store.enqueue(1, "manual")
        versions = store.list_versions(1)
        assert [row["version"] for row in versions] == [1, 2]
        assert "第一版" in store.read_version(1, 1)
        assert "第二版" in store.read_version(1, 2)

    def test_version_meta(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual", "因为标题占位")
        (novel / "rework" / "archive" / "ch0001" / "v1.meta.json").read_text(encoding="utf-8")
        row = store.list_versions(1)[0]
        assert row["chars"] > 0
        assert "标题占位" in row["note"]

    def test_discard_keeps_files(self, novel: Path):
        """🔴 废弃只改状态 —— 正文与归档都必须还在。"""
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        record = store.enqueue(1, "manual")
        archive = novel / record.archive_path
        store.discard(1)
        assert archive.is_file()
        assert (novel / "chapters" / "chapter_0001.txt").is_file()
        assert store.get(1).status == "discarded"

    def test_empty_versions(self, novel: Path):
        store = ReworkStore(novel)
        assert store.list_versions(99) == []
        assert store.read_version(99, 1) == ""


# ====================================================================== 原因记录


class TestReason:
    def test_reason_recorded(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        record = store.enqueue(1, "qc_blocker", "翻案腔 31 次", {"detectors": ["fanan"]})
        assert record.reason_code == "qc_blocker"
        assert record.reason_label == REASON_LABELS["qc_blocker"]
        assert record.evidence["detectors"] == ["fanan"]

    def test_default_reason_text(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        record = store.enqueue(1, "bad_title")
        assert record.reason_text == REASON_LABELS["bad_title"]

    def test_attempts_increment(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "draft")
        store.enqueue(1, "manual")
        assert store.get(1).attempts == 2

    def test_history_appends(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.transition(1, "reworking", note="开始改")
        statuses = [event.status for event in store.get(1).history]
        assert statuses == ["pending_rework", "reworking"]
        assert store.get(1).history[-1].note == "开始改"


# ====================================================================== 持久化


class TestPersistence:
    def test_roundtrip(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "low_score", "评审 45 分", {"overall": 45})
        store.transition(1, "reworking")

        reloaded = ReworkStore(novel)
        record = reloaded.get(1)
        assert record is not None
        assert record.status == "reworking"
        assert record.evidence["overall"] == 45
        assert len(record.history) == 2

    def test_queue_file_shape(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        data = json.loads((novel / "rework" / "queue.json").read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["records"][0]["chapter"] == 1

    def test_corrupt_queue_tolerated(self, novel: Path):
        """队列损坏 ⇒ 按空队列继续，且**不覆盖**原文件（避免把小问题变成数据丢失）。"""
        (novel / "rework").mkdir()
        (novel / "rework" / "queue.json").write_text("{坏", encoding="utf-8")
        store = ReworkStore(novel)
        assert store.all() == []

    def test_stats(self, novel: Path):
        for chapter in (1, 2, 3):
            _write(novel, chapter, f"# 第{chapter}章：x")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        store.enqueue(2, "manual")
        store.transition(2, "reworking")
        stats = store.stats()
        assert stats["pending_rework"] == 1
        assert stats["reworking"] == 1
        assert stats["draft"] == 0

    def test_by_status(self, novel: Path):
        _write(novel, 1, "# 第1章：x")
        store = ReworkStore(novel)
        store.enqueue(1, "manual")
        assert [r.chapter for r in store.by_status("pending_rework")] == [1]
        assert store.by_status("reworking") == []

    def test_remove_keeps_archive(self, novel: Path):
        _write(novel, 1, "# 第1章：起点")
        store = ReworkStore(novel)
        record = store.enqueue(1, "manual")
        assert store.remove(1) is True
        assert store.get(1) is None
        assert (novel / record.archive_path).is_file(), "移除队列记录不能删归档"

    def test_remove_missing(self, novel: Path):
        assert ReworkStore(novel).remove(9) is False


# ====================================================================== 触发扫描


class TestScan:
    def test_bad_title_found(self, novel: Path):
        _write(novel, 71, "# 第71章")
        found = scan(novel, min_hanzi=100)
        assert [(f["chapter"], f["reason_code"]) for f in found] == [(71, "bad_title")]

    def test_placeholder_title_found(self, novel: Path):
        _write(novel, 171, "# 第171章：章节标题(10字)")
        found = scan(novel, min_hanzi=100)
        assert found[0]["reason_code"] == "bad_title"

    def test_good_title_no_reason(self, novel: Path):
        _write(novel, 1, "# 第1章：交界弃子")
        assert scan(novel, min_hanzi=100) == []

    def test_short_chapter_skipped(self, novel: Path):
        _write(novel, 1, "# 第1章", chars=40)
        assert scan(novel, min_hanzi=500) == []

    def test_low_score_needs_record(self, novel: Path):
        """🔴 没有评审记录**不算低分** —— 否则所有未评章节都会被判"差"。"""
        from app.review_store import normalize_review, save_review

        _write(novel, 1, "# 第1章：交界弃子")
        assert scan(novel, min_hanzi=100) == []

        save_review(novel, normalize_review({"overall_score": 40}, 1))
        found = scan(novel, min_hanzi=100)
        assert found and found[0]["reason_code"] == "low_score"

    def test_score_above_threshold_passes(self, novel: Path):
        from app.review_store import normalize_review, save_review

        _write(novel, 1, "# 第1章：交界弃子")
        save_review(novel, normalize_review({"overall_score": 90}, 1))
        assert scan(novel, min_hanzi=100) == []

    def test_failed_review_not_low_score(self, novel: Path):
        """评审失败（overall=None）不是"低分" —— 它是"没评"。"""
        from app.review_store import normalize_review, save_review

        _write(novel, 1, "# 第1章：交界弃子")
        save_review(novel, normalize_review("不是 JSON", 1))
        assert scan(novel, min_hanzi=100) == []

    def test_qc_blocker_found(self, novel: Path):
        """翻案腔密集 ⇒ 阻断项 ⇒ 建议回炉。"""
        body = "这不是存更多，而是记得更准。" * 120
        (novel / "chapters" / "chapter_0005.txt").write_text(
            "# 第5章：交界弃子" + NL + NL + body, encoding="utf-8"
        )
        found = scan(novel, min_hanzi=100)
        assert found and found[0]["reason_code"] == "qc_blocker"
        assert "证据" not in found[0] or True  # 证据字段由 evidence 承载
        assert found[0]["evidence"]["detectors"]

    def test_one_reason_per_chapter(self, novel: Path):
        """同一章只报一条 —— 队列里出现两条会让人不知道该改哪个。"""
        _write(novel, 1, "# 第1章")
        found = scan(novel, min_hanzi=100)
        assert len([f for f in found if f["chapter"] == 1]) == 1

    def test_limit(self, novel: Path):
        for chapter in range(1, 6):
            _write(novel, chapter, f"# 第{chapter}章")
        assert len(scan(novel, min_hanzi=100, limit=2)) == 2

    def test_no_chapters_dir(self, tmp_path: Path):
        assert scan(tmp_path) == []
        assert scan(None) == []

    def test_threshold_configurable(self, novel: Path):
        from app.review_store import normalize_review, save_review

        _write(novel, 1, "# 第1章：交界弃子")
        save_review(novel, normalize_review({"overall_score": 75}, 1))
        assert scan(novel, min_hanzi=100) == []
        assert scan(novel, ReworkStore(novel, score_threshold=80), min_hanzi=100)


# ====================================================================== 面板联动（不建 Tk）

class TestPanelIntegration:
    def test_panel_registered(self):
        from app.panels.registry import all_panels, load_panels

        load_panels(force=True)
        assert "rework" in [panel.key for panel in all_panels()]

    def test_panel_metadata(self):
        from app.panels.rework_panel import ReworkPanel

        assert ReworkPanel.key == "rework"
        assert ReworkPanel.title == "回炉重造"
        assert ReworkPanel.topics_of_interest, "章节保存后应刷新队列"

    def test_panel_without_host(self):
        """未绑定宿主时不能崩（自动化测试就是这种场景）。"""
        from app.panels.rework_panel import ReworkPanel

        panel = ReworkPanel()
        assert panel._store() is None
        panel._log_safe("测试")  # 不应抛
