"""`bulk_rewrite` 的展示层与失败清单。

## 为什么先补这一层（按故障类型）

整书重写是**唯一会批量覆盖存量章节**的功能，用户点"开始"前要看三行字决定信不信它：

| 文字 | 用户据它判断 |
|---|---|
| `BulkPlan.as_text` | "这次要跑多久、动多少字" —— **估错就等于骗人** |
| `BulkProgress.as_line` | "现在跑到哪了" —— 卡住时这是唯一线索 |
| `summary_text` | "哪些章失败了" —— 决定要不要"只重试失败项" |

这些是纯格式化，跑起来不花钱、不联网，但错一个字用户就会误判。
`failed_chapters()` 尤其关键：它决定"重试失败项"会不会**重跑已经成功的章节**
（那等于重复烧钱，且可能把好稿再改一遍）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.bulk_rewrite import BulkPlan, BulkProgress, BulkRewriter, BulkStats


class TestEstimatedText:
    """耗时预估必须在不同量级都**可读** —— 「11949 分钟」没人能直观理解。"""

    # 每块按 `SECONDS_PER_CHUNK=75` 秒估：95 块≈119 分钟，96 块正好 2 小时。
    @pytest.mark.parametrize(("chunks", "expect"), [(0, "0 分钟"), (1, "1 分钟"), (50, "62 分钟")])
    def test_short_runs_in_minutes(self, chunks, expect):
        assert expect in BulkPlan(chunks=chunks).estimated_text

    def test_hours_when_over_two_hours(self):
        """超过 2 小时换算成小时（不是"1260 分钟"）。"""
        text = BulkPlan(chunks=1000).estimated_text

        assert "21 小时" in text
        assert "分钟" not in text

    def test_days_when_over_two_days(self):
        """超过 48 小时换算成天 —— 1094 章的整书重写会落在这里。"""
        assert "2.0 天" in BulkPlan(chunks=2304).estimated_text

    def test_boundary_between_minutes_and_hours(self):
        """边界钉在 120 分钟：95 块仍按分钟，96 块换成小时。

        这是 off-by-one 最容易出事的地方 —— 差一块就从「约 119 分钟」
        变成「约 2 小时」，而两者读起来差别很大。
        """
        assert "分钟" in BulkPlan(chunks=95).estimated_text
        assert "小时" in BulkPlan(chunks=96).estimated_text

    def test_estimated_minutes_is_rounded(self):
        plan = BulkPlan(chunks=7)
        assert isinstance(plan.estimated_minutes, float)
        assert round(plan.estimated_minutes, 1) == plan.estimated_minutes


class TestPlanAsText:
    def test_mentions_counts_and_done(self):
        plan = BulkPlan(chapters=1094, chunks=3000, hanzi=1234567, todo_chapters=12, done_chapters=1082)
        text = plan.as_text()

        assert "1094 章" in text
        assert "1,234,567 汉字" in text, "大数字必须带千分位，否则数不清几位"
        assert "3000 块" in text
        assert "已完成 1082 章" in text
        assert "本次待处理 12 章" in text


class TestProgressLine:
    """进度行是"卡住时唯一的线索"，每个状态都要能说清自己在哪。"""

    def test_running_shows_chapter_and_chunk(self):
        line = BulkProgress(
            chapter=5, chapter_index=5, total_chapters=20, chunk_index=2, total_chunks=3, done=4, elapsed=90
        ).as_line()

        assert "第 5 章" in line
        assert "5/20" in line
        assert "第 2/3 块" in line
        assert "已完成 4 章" in line
        assert "1.5 分钟" in line

    def test_running_without_chunks_omits_chunk_part(self):
        line = BulkProgress(chapter=5, chapter_index=5, total_chapters=20, total_chunks=0).as_line()
        assert "块" not in line

    def test_paused_line(self):
        line = BulkProgress(status="paused", chapter_index=3, total_chapters=10).as_line()
        assert "已暂停" in line and "3/10" in line

    def test_done_line_counts_everything(self):
        line = BulkProgress(status="done", done=8, failed=1, skipped=1, elapsed=600).as_line()
        assert "完成 8 章" in line
        assert "失败 1" in line
        assert "跳过 1" in line
        assert "10.0 分钟" in line

    def test_cancelled_line(self):
        line = BulkProgress(status="cancelled", done=3, elapsed=120).as_line()
        assert "已取消" in line and "完成 3 章" in line


class TestPercent:
    def test_zero_total_returns_zero(self):
        """还没有章节时不能除零 —— 面板首屏就是这个状态。"""
        assert BulkProgress(total_chapters=0).percent == 0.0

    def test_normal(self):
        assert BulkProgress(chapter_index=5, total_chapters=10).percent == 50.0

    def test_capped_at_hundred(self):
        """越界时钳到 100 —— 进度条超过满格会画到控件外面。"""
        assert BulkProgress(chapter_index=12, total_chapters=10).percent == 100.0


class TestStatsText:
    def test_mentions_word_count_change_and_tokens(self):
        text = BulkStats(
            done=8, failed=1, skipped=1, hanzi_before=100000, hanzi_after=101500, calls=9, prompt_tokens=123456
        ).as_text()

        assert "完成 8" in text
        assert "100,000 → 101,500" in text
        assert "调用 9 次" in text
        assert "123,456" in text


class TestFailedChapters:
    """决定"只重试失败项"到底重跑哪些 —— 选错就要么漏跑、要么重复烧钱。"""

    @staticmethod
    def _rewriter(tmp_path: Path) -> BulkRewriter:
        (tmp_path / "chapters").mkdir(exist_ok=True)
        return BulkRewriter(tmp_path, ai_client=None)

    def test_reads_failed_and_cancelled_only(self, tmp_path):
        rw = self._rewriter(tmp_path)
        rw._log_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "chapters": {
                        "3": {"status": "done"},
                        "7": {"status": "failed"},
                        "9": {"status": "cancelled"},
                        "11": {"status": "done"},
                    },
                }
            ),
            encoding="utf-8",
        )

        assert rw.failed_chapters() == [7, 9], "成功章节被当成失败项重跑了"

    def test_sorted_numerically_not_lexically(self, tmp_path):
        """`"10" < "9"` 按字符串排序会把第 10 章排在第 9 章前面。"""
        rw = self._rewriter(tmp_path)
        rw._log_path.write_text(
            json.dumps({"chapters": {"9": {"status": "failed"}, "10": {"status": "failed"}}}),
            encoding="utf-8",
        )

        assert rw.failed_chapters() == [9, 10]

    def test_skips_malformed_entries(self, tmp_path):
        rw = self._rewriter(tmp_path)
        rw._log_path.write_text(
            json.dumps(
                {"chapters": {"not-a-number": {"status": "failed"}, "5": "不是字典", "6": {"status": "failed"}}}
            ),
            encoding="utf-8",
        )

        assert rw.failed_chapters() == [6]

    def test_missing_log_returns_empty(self, tmp_path):
        rw = self._rewriter(tmp_path)
        assert rw.failed_chapters() == []

    def test_corrupt_log_does_not_raise(self, tmp_path):
        """日志坏掉不能让"重试失败项"这个按钮直接崩。"""
        rw = self._rewriter(tmp_path)
        rw._log_path.write_text("{ 坏掉的 JSON", encoding="utf-8")

        assert rw.failed_chapters() == []


class TestSummaryText:
    @staticmethod
    def _rewriter(tmp_path: Path) -> BulkRewriter:
        (tmp_path / "chapters").mkdir(exist_ok=True)
        return BulkRewriter(tmp_path, ai_client=None, output_dir=tmp_path / "out")

    def test_starts_with_stats_line(self, tmp_path):
        rw = self._rewriter(tmp_path)
        rw.stats = BulkStats(done=2, failed=0)

        assert rw.summary_text().startswith("完成 2")

    def test_lists_failures(self, tmp_path):
        rw = self._rewriter(tmp_path)
        rw.stats = BulkStats(failed=1, failures=[{"chapter": 7, "error": "超时"}])

        text = rw.summary_text()
        assert "失败章节" in text
        assert "第7章" in text and "超时" in text

    def test_truncates_after_fifteen(self, tmp_path):
        """失败 100 章时不能把 100 行全铺出来 —— 面板会被撑爆。"""
        rw = self._rewriter(tmp_path)
        rw.stats = BulkStats(failed=20, failures=[{"chapter": i, "error": "err"} for i in range(1, 21)])

        text = rw.summary_text()
        assert text.count("第") <= 16
        assert "另有 5 章" in text, "截断后必须告诉用户还有多少没显示"

    def test_mentions_output_dir(self, tmp_path):
        rw = self._rewriter(tmp_path)

        assert "输出目录" in rw.summary_text()

    def test_no_failures_no_section(self, tmp_path):
        rw = self._rewriter(tmp_path)
        rw.stats = BulkStats(done=3)

        assert "失败章节" not in rw.summary_text()
