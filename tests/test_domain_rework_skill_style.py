"""回炉判定 / 技能入口 / 风格命名的领域规则测试（全纯函数，不造目录）。

三个模块都是从大函数里抽出来的：`rework.scan`(81)、`skill_library.parse_skill`(74)、
`style_dna.learn_from_novel`(52)。抽出的共同理由是**里面的分支值得单独穷举**，
而不是"大函数必须变小"。
"""

from __future__ import annotations

import pytest

from app.domain.rework import (
    REASON_BAD_TITLE,
    REASON_LOW_SCORE,
    REASON_QC_BLOCKER,
    judge_low_score,
    judge_static,
    title_is_placeholder,
)
from app.domain.skill import ENTRY_NAMES, first_entry_name
from app.domain.style import MAX_DISPLAY_NAME, derive_display_name


def _split(text: str) -> tuple[str, str]:
    """最简标题切分：首行去掉 # 前缀。"""
    first = text.splitlines()[0] if text else ""
    return first.lstrip("#").strip(), text


class TestTitlePlaceholder:
    @pytest.mark.parametrize(
        "title",
        ["", "   ", "第3章", "第 3 章：", "章节标题", "Untitled", "标题（200字）"],
    )
    def test_placeholders(self, title):
        assert title_is_placeholder(title) is True

    @pytest.mark.parametrize("title", ["第3章 初入黑风岭", "雨夜断剑", "阴阳地之辱"])
    def test_real_titles(self, title):
        assert title_is_placeholder(title) is False


class TestJudgeStatic:
    def test_bad_title_wins_and_skips_qc(self):
        """标题是占位符时**不该再跑质检** —— 同一章只报一条。"""
        calls: list[str] = []

        def blocker(text):
            calls.append(text)
            return {"summary": "不该被调用"}

        hit = judge_static(3, "# 第3章\n正文", split_title=_split, blocker_evidence=blocker)
        assert hit["reason_code"] == REASON_BAD_TITLE
        assert calls == [], "标题硬伤已命中，却还跑了质检"

    def test_qc_blocker_reported_when_title_ok(self):
        hit = judge_static(
            5,
            "# 第5章 雨夜\n正文",
            split_title=_split,
            blocker_evidence=lambda t: {"summary": "破折号 3 次（1.20/千字）", "detectors": ["dash"]},
        )
        assert hit["reason_code"] == REASON_QC_BLOCKER
        assert "破折号" in hit["reason_text"]
        assert hit["evidence"]["detectors"] == ["dash"]

    def test_clean_chapter_returns_none(self):
        hit = judge_static(5, "# 第5章 雨夜\n正文", split_title=_split, blocker_evidence=lambda t: None)
        assert hit is None

    def test_evidence_is_copied_not_aliased(self):
        """`evidence` 必须是副本：调用方后续改原字典不该影响已入队的结果。"""
        info = {"summary": "x", "detectors": []}
        hit = judge_static(1, "# 第1章 a\n正文", split_title=_split, blocker_evidence=lambda t: info)
        info["summary"] = "改成别的"
        assert hit["evidence"]["summary"] == "x"


class TestJudgeLowScore:
    def test_below_threshold_hits(self):
        hit = judge_low_score(7, ok=True, overall=42.5, threshold=60, issues=["节奏慢", "重复"])
        assert hit["reason_code"] == REASON_LOW_SCORE
        assert "42.5" in hit["reason_text"]
        assert hit["evidence"]["issues"] == ["节奏慢", "重复"]

    def test_at_or_above_threshold_passes(self):
        assert judge_low_score(7, ok=True, overall=60, threshold=60) is None
        assert judge_low_score(7, ok=True, overall=80, threshold=60) is None

    def test_missing_review_is_not_low_score(self):
        """「没评审」≠「差」—— 把未评当差会让回炉队列被新章淹没。"""
        assert judge_low_score(7, ok=False, overall=None, threshold=60) is None
        assert judge_low_score(7, ok=True, overall=None, threshold=60) is None

    def test_issues_are_truncated_to_five(self):
        hit = judge_low_score(7, ok=True, overall=10, threshold=60, issues=[str(i) for i in range(10)])
        assert len(hit["evidence"]["issues"]) == 5


class TestFirstEntryName:
    def test_prefers_first_candidate(self):
        assert first_entry_name(ENTRY_NAMES, lambda n: n in {"SKILL.md", "skill.md"}) == "SKILL.md"

    def test_falls_through_to_later_candidate(self):
        assert first_entry_name(ENTRY_NAMES, lambda n: n == "Skill.md") == "Skill.md"

    def test_none_when_absent(self):
        assert first_entry_name(ENTRY_NAMES, lambda n: False) is None

    def test_does_not_probe_after_hit(self):
        seen: list[str] = []

        def is_file(name):
            seen.append(name)
            return name == "SKILL.md"

        first_entry_name(ENTRY_NAMES, is_file)
        assert seen == ["SKILL.md"], "命中后还在继续探测后续候选（无谓 IO）"

    def test_entry_names_order_is_capitalized_first(self):
        assert ENTRY_NAMES[0] == "SKILL.md"
        assert "SKILL.MD" in ENTRY_NAMES


class TestDeriveDisplayName:
    def test_strips_timestamp_suffix(self):
        assert derive_display_name("重生之岛_1781862528") == "重生之岛"

    def test_keeps_names_without_timestamp(self):
        assert derive_display_name("配种的强大之处") == "配种的强大之处"

    def test_short_suffix_is_kept(self):
        """`_12345`（5 位）不是时间戳，不该被吃 —— 否则会误伤正常书名。"""
        assert derive_display_name("帝国_12345") == "帝国_12345"

    def test_truncates_long_names(self):
        name = "很长的书名" * 10
        out = derive_display_name(name)
        assert len(out) == MAX_DISPLAY_NAME + 1
        assert out.endswith("…")

    def test_exactly_max_length_not_truncated(self):
        name = "字" * MAX_DISPLAY_NAME
        assert derive_display_name(name) == name

    @pytest.mark.parametrize("raw", ["", "   ", "_1781862528"])
    def test_empty_falls_back(self, raw):
        assert derive_display_name(raw) == "本书"

    def test_custom_fallback(self):
        assert derive_display_name("", fallback="未命名") == "未命名"
