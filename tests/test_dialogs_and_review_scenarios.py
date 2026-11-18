"""补充场景：弹窗静默模式 + 评审归一化的失败语义。

## 为什么这两块值得补

**弹窗静默（`dialogs.set_silent`）**：全仓有 200+ 处 `dialogs.showinfo/showwarning`。
后台线程里弹模态框会**卡死主线程**（历史上被卡过 14 分钟），所以自动流程必须能静默。
静默一旦失效，表现是"软件卡住不动"，而日志里什么都没有 —— 最难排查的一类。

**评审归一化（`normalize_review`）**：AI 返回不是 JSON 时，旧实现回落成 70 分，
把"评审失败"伪装成"刚好及格"。这条错误直接决定「回炉重造」会不会把坏章当成好章，
必须有明确用例钉住。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import dialogs
from app.review_store import (
    DIMENSIONS,
    ReviewRecord,
    list_reviews,
    load_review,
    normalize_review,
    reviews_dir,
    save_review,
)

# ====================================================================== 弹窗静默


class TestDialogSilentMode:
    def test_silent_blocks_all_modal_helpers(self):
        """静默期间所有提示类调用都返回、不弹窗。"""
        dialogs.set_silent(True)
        try:
            assert dialogs.showinfo("t", "m") is None
            assert dialogs.showwarning("t", "m") is None
            assert dialogs.showerror("t", "m") is None
            assert dialogs.askyesno("t", "m") is False, "静默时确认类必须返回 False（不做破坏性动作）"
            assert dialogs.is_silent() is True
        finally:
            dialogs.set_silent(False)

    def test_silent_can_be_nested_or_restored(self):
        """静默是"可开可关"的开关，关掉后必须恢复。"""
        dialogs.set_silent(True)
        assert dialogs.is_silent() is True
        dialogs.set_silent(False)
        assert dialogs.is_silent() is False

    def test_show_text_silent_returns_immediately(self):
        """🔴  曾**完全不检查静默标志**：它建 Toplevel 后 ，
        在后台流程里会卡住主线程直到用户手动关闭（历史事故"卡 14 分钟"的形态）。
        静默时必须立刻返回。"""
        import time

        dialogs.set_silent(True)
        try:
            start = time.perf_counter()
            dialogs.show_text(None, "标题", "正文" * 5000)
            elapsed = time.perf_counter() - start
            assert elapsed < 1.0, f"静默下 show_text 阻塞了 {elapsed:.1f}s"
        finally:
            dialogs.set_silent(False)

    def test_ask_text_silent_returns_none(self):
        """静默下  等同"用户取消"（返回 None），不能阻塞。"""
        dialogs.set_silent(True)
        try:
            assert dialogs.ask_text(None, "标题", "提示") is None
        finally:
            dialogs.set_silent(False)

    def test_edit_items_silent_returns_none(self):
        """静默下  返回 None 而不是原列表 ——
        返回原列表会让调用方误以为用户确认保存了。"""
        dialogs.set_silent(True)
        try:
            assert dialogs.edit_items(None, "标题", ["a", "b"]) is None
        finally:
            dialogs.set_silent(False)

    def test_prepare_returns_none_when_silent(self):
        """公共入口也必须拦一道：否则将来新增的模态函数会再漏一次。"""
        dialogs.set_silent(True)
        try:
            assert dialogs._prepare(None, "标题") is None
        finally:
            dialogs.set_silent(False)

    def test_all_modal_functions_have_silent_guard(self):
        """守卫（防回退）：会开窗的函数必须都处理静默。

        判据用 AST 扫描而不是记忆清单 —— 新增函数自动纳入。
        """
        import ast
        import pathlib as _p

        src = (_p.Path(__file__).resolve().parent.parent / "app" / "dialogs.py").read_text(encoding="utf-8")
        offenders = []
        for node in ast.parse(src).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            body = ast.get_source_segment(src, node) or ""
            if "wait_window" not in body and "_prepare(" not in body:
                continue
            if "_silent" in body or "win is None" in body:
                continue
            offenders.append(node.name)
        assert not offenders, f"这些模态函数缺静默守卫（会卡死自动流程）：{offenders}"


# ====================================================================== 评审归一化


class TestNormalizeReviewFailureSemantics:
    """🔴 核心：拿不到合法分数 ⇒ overall=None + error，**绝不能回落成及格分**。"""

    @pytest.mark.parametrize(
        "raw",
        [None, "不是 JSON", [], 42, {"foo": "bar"}, {"overall_score": "很高"}],
        ids=["None", "str", "list", "int", "缺字段", "非数字"],
    )
    def test_invalid_payload_never_invents_score(self, raw):
        record = normalize_review(raw, chapter=3)
        assert record.overall is None, f"{raw!r} 被算成了 {record.overall} 分"
        assert record.error, "失败必须带原因，否则界面上看不出来"
        assert record.ok is False

    def test_valid_payload_keeps_score(self):
        first_dim = next(iter(DIMENSIONS))
        record = normalize_review({"overall_score": 88, first_dim: 90}, chapter=1)
        assert record.overall == 88
        assert record.dimensions[first_dim] == 90
        assert record.error == ""

    def test_string_score_is_coerced(self):
        record = normalize_review({"overall_score": "72.5"}, chapter=1)
        assert record.overall == 72.5

    def test_model_is_stringified(self):
        """调用方可能传 Mock/None —— 落盘时 JSON 不能炸。"""
        record = normalize_review({"overall_score": 60}, chapter=1, model=None)  # type: ignore[arg-type]
        assert isinstance(record.model, str)

    def test_rules_version_recorded(self):
        """判据版本要落盘：否则"分数变了"分不清是稿子变了还是判据变了。"""
        record = normalize_review({"overall_score": 60}, chapter=1)
        assert record.rules_version


class TestReviewPersistence:
    def test_roundtrip(self, tmp_path: Path):
        record = normalize_review({"overall_score": 77, "issues": ["对话偏平"]}, chapter=2)
        assert save_review(tmp_path, record) is True
        loaded = load_review(tmp_path, 2)
        assert loaded is not None
        assert loaded.overall == 77
        assert loaded.issues == ["对话偏平"]

    def test_missing_returns_none(self, tmp_path: Path):
        assert load_review(tmp_path, 99) is None

    def test_corrupt_record_is_skipped_not_raised(self, tmp_path: Path):
        base = reviews_dir(tmp_path)
        assert base is not None
        base.mkdir(parents=True, exist_ok=True)
        (base / "chapter_0001.json").write_text("{坏", encoding="utf-8")
        save_review(tmp_path, normalize_review({"overall_score": 80}, chapter=2))
        rows = list_reviews(tmp_path)
        assert [r.chapter for r in rows] == [2], "损坏记录应跳过，而不是让整批读取失败"

    def test_invalid_novel_dir_returns_empty(self):
        assert reviews_dir(None) is None
        assert list_reviews(None) == []
        assert load_review(None, 1) is None
        assert save_review(None, ReviewRecord(chapter=1)) is False

    def test_trend_direction(self, tmp_path: Path):
        """趋势查询是「回炉重造」判断"改完有没有变好"的依据。"""
        for chapter, score in ((1, 55), (2, 60), (3, 78)):
            save_review(tmp_path, normalize_review({"overall_score": score}, chapter))
        rows = list_reviews(tmp_path)
        scores = [r.overall for r in rows]
        assert scores == [55, 60, 78]
        assert scores[-1] > scores[0], "趋势应能看出上升"


# ====================================================================== 与回炉联动


class TestReviewDrivesRework:
    """评审分数 → 回炉触发。这条链错了，坏章就永远留在书里。"""

    def test_low_score_triggers_candidate(self, tmp_path: Path):
        from app.rework import scan

        (tmp_path / "chapters").mkdir()
        (tmp_path / "chapters" / "chapter_0001.txt").write_text(
            "# 第1章 正常标题" + chr(10) * 2 + "正常正文内容，没有明显句式问题。" * 100,
            encoding="utf-8",
        )
        save_review(tmp_path, normalize_review({"overall_score": 41}, chapter=1))
        found = scan(tmp_path, min_hanzi=100)
        assert [(f["chapter"], f["reason_code"]) for f in found] == [(1, "low_score")]

    def test_failed_review_is_not_low_score(self, tmp_path: Path):
        """评审失败（overall=None）不是"低分" —— 否则未评章节会被全部打回。"""
        from app.rework import scan

        (tmp_path / "chapters").mkdir()
        (tmp_path / "chapters" / "chapter_0001.txt").write_text(
            "# 第1章 正常标题" + chr(10) * 2 + "正常正文内容，没有明显句式问题。" * 100,
            encoding="utf-8",
        )
        save_review(tmp_path, normalize_review("不是 JSON", chapter=1))
        assert scan(tmp_path, min_hanzi=100) == []

    def test_high_score_not_flagged(self, tmp_path: Path):
        from app.rework import scan

        (tmp_path / "chapters").mkdir()
        (tmp_path / "chapters" / "chapter_0001.txt").write_text(
            "# 第1章 正常标题" + chr(10) * 2 + "正常正文内容，没有明显句式问题。" * 100,
            encoding="utf-8",
        )
        save_review(tmp_path, normalize_review({"overall_score": 92}, chapter=1))
        assert scan(tmp_path, min_hanzi=100) == []
