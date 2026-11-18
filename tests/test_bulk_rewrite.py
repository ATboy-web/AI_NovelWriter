"""整书重写引擎：分块 / 字数校验 / 断点续跑 / 暂停取消 / 不覆盖原文。

## 测什么、为什么

这个功能会**批量调用模型并写上千个文件**，出错代价高。用例集中在：

1. **不覆盖原文** —— 输出到 `chapters_rewritten/`，`chapters/` 必须一字不动；
2. **断点续跑** —— 判据是「状态 + 内容指纹」双条件，原文改过就必须重做；
3. **字数比例校验** —— 比例异常（漏写/注水）要重试，不能直接落盘；
4. **取消/暂停** —— 检查点只在块之间，取消后已完成章不丢；
5. **前置检查** —— `check_ready` 不依赖 AI（dry-run 要能跑），`check_ai` 必须实测。

面板侧由 `test_panel_controls_mounted.py` 守控件挂载，本文件只测面板方法
在"无宿主"时不崩。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.async_runner import CancelToken
from app.bulk_rewrite import (
    OUTPUT_DIR,
    REWRITE_LOG,
    BulkRewriter,
    chunk_paragraphs,
    clean_output,
    split_paragraphs,
    split_title,
)

NL = chr(10)


# ====================================================================== 假 AI


class FakeAI:
    """按需返回：正常改写 / 字数不足 / 抛异常 / 空内容。"""

    def __init__(self, mode: str = "ok", ratio: float = 1.0):
        self.mode = mode
        self.ratio = ratio
        self.calls = 0
        self.prompts: list[str] = []

    def chat(self, messages, system: str = "", max_tokens: int = 0, **kwargs):
        self.calls += 1
        prompt = messages[0]["content"]
        self.prompts.append(prompt)

        if self.mode == "raise":
            raise RuntimeError("模拟网络错误")
        if self.mode == "empty":
            return ""

        # 从提示词里取出"待重写的原文"，然后在**同等长度**上做替换。
        # 必须同长度：引擎有 75%–135% 的字数校验，返回太短会被（正确地）判失败。
        marker = "## 待重写的原文"
        tail = prompt.split(marker, 1)[-1] if marker in prompt else "正文。"
        lines = tail.splitlines()
        source = NL.join(lines[1:]).strip() if len(lines) > 1 else tail.strip()
        if not source:
            return ""

        rewritten = source.replace("这是", "这乃是").replace("正文", "文本").replace("段落", "段落内容")
        if self.ratio >= 1.0:
            return rewritten
        keep = max(1, int(len(rewritten) * self.ratio))
        return rewritten[:keep]


@pytest.fixture()
def novel(tmp_path: Path) -> Path:
    (tmp_path / "chapters").mkdir()
    return tmp_path


def _write(novel: Path, chapter: int, title: str = "起点", paragraphs: int = 6) -> str:
    body = NL + NL.join(f"这是第{index}段正文，用来测试分块与改写是否保持段落对应关系。" for index in range(paragraphs))
    text = f"# 第{chapter}章 {title}{NL}{NL}{body}"
    (novel / "chapters" / f"chapter_{chapter:04d}.txt").write_text(text, encoding="utf-8")
    return text


# ====================================================================== 文本工具


class TestTextTools:
    def test_split_title(self):
        title, body = split_title("# 第1章 起点" + NL + NL + "正文。")
        assert title == "# 第1章 起点"
        assert body == "正文。"

    def test_split_without_heading(self):
        assert split_title("正文而已。") == ("", "正文而已。")

    def test_split_paragraphs_drops_blanks(self):
        assert split_paragraphs("甲" + NL + NL + NL + "乙") == ["甲", "乙"]

    def test_chunk_keeps_paragraphs_whole(self):
        """❗ 分块**不切断段落** —— 断在段落中间模型接不上。"""
        paragraphs = ["甲" * 500, "乙" * 500, "丙" * 500]
        chunks = chunk_paragraphs(paragraphs, target=600)
        assert [len(chunk) for chunk in chunks] == [1, 1, 1]
        assert all(isinstance(p, str) for chunk in chunks for p in chunk)

    def test_chunk_accumulates_small_paragraphs(self):
        paragraphs = ["段落" * 100] * 4
        chunks = chunk_paragraphs(paragraphs, target=1000)
        assert len(chunks) < 4

    def test_clean_output_strips_prefix(self):
        assert clean_output("以下是改写结果：" + NL + NL + "正文。") == "正文。"

    def test_clean_output_strips_fence(self):
        assert clean_output("```text" + NL + "正文。" + NL + "```") == "正文。"

    def test_clean_output_keeps_real_text(self):
        assert clean_output("正文第一段。" + NL + NL + "第二段。") == "正文第一段。" + NL + NL + "第二段。"

    def test_clean_output_empty(self):
        assert clean_output("") == ""
        assert clean_output(None) == ""


# ====================================================================== 前置检查


class TestReadiness:
    def test_ready_without_ai(self, novel: Path):
        """`check_ready` 不要求 AI —— dry-run 与"看规模"都不需要模型。"""
        _write(novel, 1)
        ok, why = BulkRewriter(novel, None).check_ready()
        assert ok is True, why

    def test_missing_chapters_dir(self, tmp_path: Path):
        ok, why = BulkRewriter(tmp_path, FakeAI()).check_ready()
        assert ok is False and "chapters" in why

    def test_empty_novel(self, novel: Path):
        ok, why = BulkRewriter(novel, FakeAI()).check_ready()
        assert ok is False and "没有章节" in why

    def test_no_novel_dir(self):
        ok, _why = BulkRewriter(None, FakeAI()).check_ready()
        assert ok is False

    def test_check_ai_success(self, novel: Path):
        _write(novel, 1)
        assert BulkRewriter(novel, FakeAI()).check_ai()[0] is True

    def test_check_ai_failure(self, novel: Path):
        _write(novel, 1)
        ok, why = BulkRewriter(novel, FakeAI(mode="raise")).check_ai()
        assert ok is False and "AI 调用失败" in why

    def test_check_ai_without_client(self, novel: Path):
        ok, why = BulkRewriter(novel, None).check_ai()
        assert ok is False and "没有可用的 AI" in why

    def test_run_without_ai_raises(self, novel: Path):
        """执行时必须明确报错，而不是跑到一半 AttributeError。"""
        from app.rework import ReworkError

        _write(novel, 1)
        with pytest.raises(ReworkError):
            BulkRewriter(novel, None).run()


# ====================================================================== 计划


class TestPlan:
    def test_counts(self, novel: Path):
        _write(novel, 1, paragraphs=6)
        _write(novel, 2, paragraphs=6)
        plan = BulkRewriter(novel, FakeAI()).plan()
        assert plan.chapters == 2
        assert plan.todo_chapters == 2
        assert plan.done_chapters == 0
        assert plan.hanzi > 0
        assert plan.chunks >= 2

    def test_estimated_text_readable(self, novel: Path):
        _write(novel, 1)
        plan = BulkRewriter(novel, FakeAI()).plan()
        assert "分钟" in plan.estimated_text or "小时" in plan.estimated_text

    def test_done_chapters_excluded(self, novel: Path):
        _write(novel, 1)
        rewriter = BulkRewriter(novel, FakeAI())
        rewriter.run()
        plan = BulkRewriter(novel, FakeAI()).plan()
        assert plan.done_chapters == 1
        assert plan.todo_chapters == 0


# ====================================================================== 执行


class TestRun:
    def test_writes_to_output_dir(self, novel: Path):
        _write(novel, 1)
        stats = BulkRewriter(novel, FakeAI()).run()
        assert stats.done == 1
        out = novel / OUTPUT_DIR / "chapter_0001.txt"
        assert out.is_file()
        assert out.read_text(encoding="utf-8").startswith("# 第1章")

    def test_original_untouched(self, novel: Path):
        """🔴 核心：原文一个字都不能变。"""
        original = _write(novel, 1)
        BulkRewriter(novel, FakeAI()).run()
        assert (novel / "chapters" / "chapter_0001.txt").read_text(encoding="utf-8") == original

    def test_log_written(self, novel: Path):
        _write(novel, 1)
        BulkRewriter(novel, FakeAI()).run()
        log = json.loads((novel / REWRITE_LOG).read_text(encoding="utf-8"))
        assert log["chapters"]["1"]["status"] == "done"
        assert log["chapters"]["1"]["fingerprint"]

    def test_failure_recorded(self, novel: Path):
        _write(novel, 1)
        stats = BulkRewriter(novel, FakeAI(mode="raise")).run()
        assert stats.failed == 1
        assert stats.failures
        log = json.loads((novel / REWRITE_LOG).read_text(encoding="utf-8"))
        assert log["chapters"]["1"]["status"] == "failed"

    def test_partial_success_continues(self, novel: Path):
        """一章失败不该中断整批 —— 其余章继续。"""
        _write(novel, 1)
        _write(novel, 2)

        class FlakyAI(FakeAI):
            """第 1 次调用必失败 —— 不靠 prompt 里的章节号判断（块内容里没有章号）。"""

            def chat(self, messages, **kwargs):
                # 前 3 次抛错 = 用尽引擎的重试次数（MAX_CHUNK_TRIES），该章才会记 failed
                if self.calls < 3:
                    self.calls += 1
                    raise RuntimeError("这一章失败")
                return super().chat(messages, **kwargs)

        stats = BulkRewriter(novel, FlakyAI()).run()
        assert stats.failed == 1
        assert stats.done == 1

    def test_no_paragraphs_fails(self, novel: Path):
        (novel / "chapters" / "chapter_0001.txt").write_text("# 第1章 空" + NL, encoding="utf-8")
        stats = BulkRewriter(novel, FakeAI()).run()
        assert stats.failed == 1


# ====================================================================== 字数校验


class TestRatioGuard:
    def test_short_output_retried(self, novel: Path):
        """输出只有原文 30% ⇒ 重试；三次都不达标 ⇒ 失败，不落盘。"""
        _write(novel, 1, paragraphs=20)
        ai = FakeAI(ratio=0.3)
        stats = BulkRewriter(novel, ai).run()
        assert stats.failed == 1
        assert ai.calls >= 3
        assert not list((novel / OUTPUT_DIR).glob("*.txt"))

    def test_retry_prompt_mentions_shortfall(self, novel: Path):
        _write(novel, 1, paragraphs=20)
        ai = FakeAI(ratio=0.3)
        BulkRewriter(novel, ai).run()
        assert any("篇幅" in prompt for prompt in ai.prompts[1:])


# ====================================================================== 断点续跑


class TestResume:
    def test_second_run_skips(self, novel: Path):
        _write(novel, 1)
        BulkRewriter(novel, FakeAI()).run()
        ai = FakeAI()
        stats = BulkRewriter(novel, ai).run()
        assert stats.skipped == 1
        assert stats.done == 0
        assert ai.calls == 0, "已完成的章不该再调用模型"

    def test_changed_source_is_redone(self, novel: Path):
        """🔴 判据是「状态 + 指纹」双条件：原文改过就必须重做。"""
        _write(novel, 1)
        BulkRewriter(novel, FakeAI()).run()
        # 指纹只覆盖正文（重写不改标题，所以改标题不算内容变更）—— 这里改正文
        (novel / "chapters" / "chapter_0001.txt").write_text(
            "# 第1章 起点" + NL + NL + "改写过的正文内容，与原来完全不同的一段话。" * 5, encoding="utf-8"
        )
        ai = FakeAI()
        stats = BulkRewriter(novel, ai).run()
        assert stats.done == 1
        assert ai.calls > 0

    def test_force_redoes(self, novel: Path):
        _write(novel, 1)
        BulkRewriter(novel, FakeAI()).run()
        stats = BulkRewriter(novel, FakeAI(), force=True).run()
        assert stats.done == 1

    def test_failed_chapters_listed(self, novel: Path):
        _write(novel, 1)
        rewriter = BulkRewriter(novel, FakeAI(mode="raise"))
        rewriter.run()
        assert rewriter.failed_chapters() == [1]

    def test_corrupt_log_tolerated(self, novel: Path):
        _write(novel, 1)
        (novel / REWRITE_LOG).write_text("{坏", encoding="utf-8")
        stats = BulkRewriter(novel, FakeAI()).run()
        assert stats.done == 1


# ====================================================================== 取消与暂停


class TestControl:
    def test_cancel_stops_early(self, novel: Path):
        for chapter in range(1, 6):
            _write(novel, chapter)
        rewriter = BulkRewriter(novel, FakeAI())
        token = CancelToken("测试取消")

        seen: list[int] = []

        def progress(update):
            seen.append(update.chapter)

        token.cancel("立刻取消")
        stats = rewriter.run(on_progress=progress, token=token)
        assert stats.done == 0

    def test_cancel_keeps_finished_chapters(self, novel: Path):
        """取消后已完成的章要留着（日志里有 done），下次不重做。"""
        _write(novel, 1)
        _write(novel, 2)
        rewriter = BulkRewriter(novel, FakeAI())
        token = CancelToken("测")

        def progress(update):
            # 等第一章真的落盘后再取消 —— 用 update.done 判断，
            # 而不是 chapter_index（后者在第一章开始前就已经是 1）
            if update.done >= 1:
                token.cancel("跑完第一章就停")

        stats = rewriter.run(on_progress=progress, token=token)
        assert stats.done >= 1
        log = json.loads((novel / REWRITE_LOG).read_text(encoding="utf-8"))
        assert log["chapters"]["1"]["status"] == "done"

    def test_pause_flag(self, novel: Path):
        rewriter = BulkRewriter(novel, FakeAI())
        assert rewriter.paused is False
        rewriter.pause()
        assert rewriter.paused is True
        rewriter.resume()
        assert rewriter.paused is False

    def test_progress_callback_receives_status(self, novel: Path):
        _write(novel, 1)
        updates: list[str] = []
        BulkRewriter(novel, FakeAI()).run(on_progress=lambda u: updates.append(u.status))
        assert "done" in updates

    def test_progress_callback_exception_tolerated(self, novel: Path):
        """回调抛异常不能中断重写（面板刷新出错不该毁掉任务）。"""
        _write(novel, 1)

        def boom(_update):
            raise RuntimeError("面板刷新炸了")

        stats = BulkRewriter(novel, FakeAI()).run(on_progress=boom)
        assert stats.done == 1


# ====================================================================== 面板


class TestPanelWiring:
    def test_panel_without_host(self):
        """未绑定宿主时面板方法不能崩。"""
        from app.panels.rework_panel import ReworkPanel

        panel = ReworkPanel()
        assert panel._bulk_ai_client() is not None or panel._bulk_ai_client() is None
        panel._bulk_ui(lambda: None)  # 无 root 时直接执行

    def test_idle_buttons_disabled(self):
        import tkinter as tk

        from app.panels.rework_panel import ReworkPanel

        root = tk.Tk()
        root.withdraw()
        try:
            panel = ReworkPanel()
            panel.build(root)
            assert str(panel._bulk_pause_btn.cget("state")) == "disabled"
            assert str(panel._bulk_cancel_btn.cget("state")) == "disabled"
            assert str(panel._bulk_start_btn.cget("state")) == "normal"
        finally:
            root.destroy()

    def test_panel_has_bulk_attrs(self):
        from app.panels.rework_panel import ReworkPanel

        panel = ReworkPanel()
        for name in ("_on_bulk_start", "_on_bulk_toggle_pause", "_on_bulk_cancel", "_on_bulk_progress"):
            assert callable(getattr(panel, name))
