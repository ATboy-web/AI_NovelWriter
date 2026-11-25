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


class TestStatusMachine:
    """回炉队列状态机（原在 ReworkStore 里，与读写混在一起）。"""

    def test_labels_cover_all_statuses(self):
        from app.domain.rework import REWORK_STATUSES, STATUS_LABELS

        assert set(STATUS_LABELS) == set(REWORK_STATUSES)
        assert len(REWORK_STATUSES) == len(set(REWORK_STATUSES))

    def test_transition_table_covers_every_status(self):
        """每个状态都必须在流转表里有一行；漏一行 ⇒ 该状态永远出不去。"""
        from app.domain.rework import REWORK_STATUSES, TRANSITIONS

        assert set(TRANSITIONS) == set(REWORK_STATUSES)

    def test_transition_targets_are_known_statuses(self):
        """流转表里的目标不能是拼错的状态名 —— 那会让用户卡在一个不存在的状态。"""
        from app.domain.rework import REWORK_STATUSES, TRANSITIONS

        for src, targets in TRANSITIONS.items():
            for dst in targets:
                assert dst in REWORK_STATUSES, f"{src} → {dst}：目标状态不存在"

    def test_no_self_transition(self):
        from app.domain.rework import TRANSITIONS

        for src, targets in TRANSITIONS.items():
            assert src not in targets, f"{src} 允许流转到自身（无意义且会刷 history）"

    def test_discarded_is_terminal(self):
        from app.domain.rework import TRANSITIONS

        assert TRANSITIONS["discarded"] == (), "废弃应是终点：要恢复就重新入炉（留痕）"

    def test_draft_cannot_jump_to_published(self):
        """刻意禁止：跳过大纲外的重写与审核。"""
        from app.domain.rework import validate_transition

        assert validate_transition("draft", "published") is not None

    def test_status_label_known_and_unknown(self):
        from app.domain.rework import status_label

        assert status_label("reworking") == "重写中"
        assert status_label("未来新状态") == "未来新状态", "未知状态应原样返回，不能让展示层崩"

    @pytest.mark.parametrize("target", ["pending_rework", "reworking", "approved", "published"])
    def test_valid_and_invalid_transitions_are_consistent(self, target):
        """凡在表里的目标都必须通过校验；表外的必须被拒。"""
        from app.domain.rework import TRANSITIONS, validate_transition

        for src, allowed in TRANSITIONS.items():
            if target in allowed:
                assert validate_transition(src, target) is None
            else:
                assert validate_transition(src, target) is not None

    def test_unknown_target_rejected(self):
        from app.domain.rework import validate_transition

        msg = validate_transition("draft", "不存在的状态")
        assert msg and "未知状态" in msg


class TestCheckEnqueue:
    def test_no_novel(self):
        from app.domain.rework import check_enqueue

        ok, why = check_enqueue(3, has_novel=False)
        assert ok is False and "没有打开的作品" in why

    def test_empty_chapter(self):
        from app.domain.rework import check_enqueue

        ok, why = check_enqueue(3, has_text=False)
        assert ok is False and "没有正文" in why

    def test_clean_chapter_allowed(self):
        from app.domain.rework import check_enqueue

        assert check_enqueue(3) == (True, "")

    @pytest.mark.parametrize("status", ["reworking", "pending_review"])
    def test_busy_statuses_rejected(self, status):
        from app.domain.rework import check_enqueue

        ok, why = check_enqueue(3, status=status)
        assert ok is False and "不能重复入炉" in why

    def test_published_requires_force(self):
        from app.domain.rework import check_enqueue

        assert check_enqueue(3, status="published")[0] is False
        assert check_enqueue(3, status="published", force=True)[0] is True

    def test_attempts_limit_requires_force(self):
        from app.domain.rework import MAX_ATTEMPTS, check_enqueue

        assert check_enqueue(3, status="pending_rework", attempts=MAX_ATTEMPTS)[0] is False
        assert check_enqueue(3, status="pending_rework", attempts=MAX_ATTEMPTS, force=True)[0] is True

    def test_below_limit_allowed(self):
        from app.domain.rework import MAX_ATTEMPTS, check_enqueue

        assert check_enqueue(3, status="pending_rework", attempts=MAX_ATTEMPTS - 1)[0] is True

    def test_no_record_means_allowed(self):
        from app.domain.rework import check_enqueue

        assert check_enqueue(3, status=None) == (True, "")
