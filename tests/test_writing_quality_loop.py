"""评审判据同源 / 评审落盘 / 一致性校验 / DNA 自动学 —— 四项建议的回归测试。

对应关系：

| 建议 | 用例类 |
|---|---|
| 1 统一写与评的标准 | `TestReviewCriteria` / `TestSlopGrading` |
| 2 评审落盘 + 趋势 | `TestReviewStore` |
| 3 失败不伪装 | `TestNoDisguise` |
| 4 长篇一致性 | `TestConsistency` |
| 5 DNA 自动学 | `TestLearnStyle` |
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.consistency import (
    AGE_TOLERANCE,
    ConsistencyIssue,
    check_chapter,
    check_character_properties,
    check_timeline_sanity,
    format_issues,
)
from app.review_store import (
    ReviewRecord,
    format_trend,
    list_reviews,
    load_review,
    normalize_review,
    save_review,
    score_trend,
    summarize_novel,
)
from app.style_dna import format_dna, learn_from_novel, learn_from_texts
from app.writing_presets import review_criteria
from app.writing_skills import classify_slop_issue, split_slop_issues

NL = chr(10)


# ====================================================================== 建议 1：统一标准


class TestReviewCriteria:
    def test_core_sections_present(self):
        text = review_criteria(budget=2000)
        assert "评审判据" in text
        assert "不得另立标准" in text
        assert "可扣分项" in text
        assert "不得扣分" in text
        assert "不得判定" in text

    def test_x_level_listed_as_no_deduction(self):
        """🔴 核心断言：X 级特征必须出现在「不得扣分」里。

        这是旧实现最严重的问题：`_reviewer_evaluate` 的手写清单会为这些特征扣分，
        而技能库实测它们**人类用得更多**。
        """
        text = review_criteria(budget=2000)
        assert "序数词小标题" in text
        assert "这意味着" in text
        assert "空转句引列表" in text
        assert "概括替代" in text

    def test_fingerprint_is_hint_only(self):
        text = review_criteria(budget=2000)
        assert "句长/段长方差" in text

    def test_budget_respected(self):
        for budget in (200, 400, 760):
            assert len(review_criteria(budget=budget)) <= budget

    def test_without_library_degrades_safely(self):
        """技能库不可用 ⇒ 明确写"请勿凭印象判定"，而不是给一份空清单让人自由发挥。"""
        text = review_criteria(rules=[], budget=900)
        assert "技能库未加载" in text

    def test_retired_rules_excluded(self):
        """已降级/已否决的规则不得出现在可扣分项里。"""

        class Rule:
            def __init__(self, title, level):
                self.title = title
                self.level = level

        rules = [
            Rule("1. 翻案腔", "A"),
            Rule("9. 段首零主语评论（降级：不再自动检测）", "B"),
            Rule("13. 高度同构三连", "A"),
        ]
        text = review_criteria(rules=rules, budget=2000)
        deduct_part = text.split("只提示")[0]
        assert "翻案腔" in deduct_part
        assert "段首零主语" not in text

    def test_unnumbered_sections_excluded(self):
        """`F 级单模型指纹的处置` 是章节标题，不是可执行规则。"""

        class Rule:
            title = "F 级单模型指纹的处置"
            level = "F"

        text = review_criteria(rules=[Rule()], budget=2000)
        assert "指纹的处置" not in text


class TestSlopGrading:
    def test_common_connectives_are_soft(self):
        """「然而/不过/但是」单独出现不算 AI 味 —— 这是扣分口径的关键修复。"""
        for word in ("然而", "不过", "但是", "虽然如此", "即便如此", "尽管如此"):
            issue = f"第3行: 过度使用过渡词 '{word}'"
            assert classify_slop_issue(issue) == "soft", word

    def test_summary_cliches_are_hard(self):
        for word in ("综上所述", "总而言之", "言归正传", "话说回来", "归根结底"):
            assert classify_slop_issue(f"第1行: 过度使用过渡词 '{word}'") == "hard", word

    def test_openings_endings_hard(self):
        assert classify_slop_issue("发现禁止开头: '在这个世界上'") == "hard"
        assert classify_slop_issue("发现禁止结尾: '故事，才刚刚开始'") == "hard"

    def test_adjective_cluster_hard(self):
        assert classify_slop_issue("发现形容词堆砌: '美丽动人可爱'") == "hard"

    def test_split_keeps_counts(self):
        issues = [
            "第1行: 过度使用过渡词 '然而'",
            "第2行: 过度使用过渡词 '综上所述'",
            "发现禁止开头: '众所周知'",
        ]
        hard, soft = split_slop_issues(issues)
        assert len(hard) == 2 and len(soft) == 1

    def test_unknown_transition_is_soft(self):
        """自定义规则里的未登记过渡词按 soft —— 宁可少扣，不可误扣。"""
        assert classify_slop_issue("第5行: 过度使用过渡词 '自定义词'") == "soft"

    def test_normal_novel_no_deduction(self):
        """一段含 3 个「但是/然而」的正常小说，不应产生任何可扣分项。"""
        from app.writing_skills import AntiSlopProcessor

        text = "但是他还是走了。" + NL + "然而雨没有停。" + NL + "不过他没有回头。"
        issues = AntiSlopProcessor().check_text(text)
        collected = [i for k, v in issues.items() if k != "suggestions" for i in v]
        hard, _soft = split_slop_issues(collected)
        assert hard == [], f"正常叙事不该被扣分，实际：{hard}"


# ====================================================================== 建议 2/3：落盘与不伪装


class TestReviewStore:
    @pytest.fixture()
    def novel(self, tmp_path: Path) -> Path:
        (tmp_path / "memory").mkdir()
        return tmp_path

    def test_save_and_load(self, novel: Path):
        record = normalize_review({"overall_score": 82, "issues": ["x"], "suggestions": ["y"]}, 1)
        assert save_review(novel, record) is True
        loaded = load_review(novel, 1)
        assert loaded is not None
        assert loaded.overall == 82.0
        assert loaded.issues == ["x"]

    def test_file_layout(self, novel: Path):
        save_review(novel, normalize_review({"overall_score": 70}, 7))
        assert (novel / "memory" / "reviews" / "chapter_007.json").is_file()

    def test_missing_returns_none(self, novel: Path):
        assert load_review(novel, 99) is None

    def test_corrupt_file_skipped(self, novel: Path):
        base = novel / "memory" / "reviews"
        base.mkdir(parents=True)
        (base / "chapter_002.json").write_text("{坏", encoding="utf-8")
        assert load_review(novel, 2) is None
        assert list_reviews(novel) == []

    def test_load_all_sorted(self, novel: Path):
        for chapter in (3, 1, 2):
            save_review(novel, normalize_review({"overall_score": 60 + chapter}, chapter))
        assert [r.chapter for r in list_reviews(novel)] == [1, 2, 3]

    def test_score_trend_keeps_failures(self, novel: Path):
        """失败的章节要留成缺口，不能静默跳过（否则曲线假平滑）。"""
        save_review(novel, normalize_review({"overall_score": 80}, 1))
        save_review(novel, normalize_review("不是 JSON", 2))
        save_review(novel, normalize_review({"overall_score": 85}, 3))
        trend = score_trend(novel)
        assert [row["chapter"] for row in trend] == [1, 2, 3]
        assert trend[1]["overall"] is None and trend[1]["ok"] is False

    def test_summary_trend_up(self, novel: Path):
        for chapter, score in ((1, 60), (2, 62), (3, 80), (4, 82)):
            save_review(novel, normalize_review({"overall_score": score}, chapter))
        summary = summarize_novel(novel)
        assert summary["trend"] == "up"
        assert summary["highest"]["overall"] == 82.0

    def test_summary_trend_down(self, novel: Path):
        for chapter, score in ((1, 85), (2, 84), (3, 62), (4, 60)):
            save_review(novel, normalize_review({"overall_score": score}, chapter))
        assert summarize_novel(novel)["trend"] == "down"

    def test_summary_flat_needs_four(self, novel: Path):
        save_review(novel, normalize_review({"overall_score": 80}, 1))
        assert summarize_novel(novel)["trend"] == "unknown"

    def test_summary_lists_failures(self, novel: Path):
        save_review(novel, normalize_review({"overall_score": 80}, 1))
        save_review(novel, normalize_review(None, 2))
        summary = summarize_novel(novel)
        assert summary["failed_chapters"] == [2]

    def test_rules_version_recorded(self, novel: Path):
        record = normalize_review({"overall_score": 80}, 1)
        assert record.rules_version
        save_review(novel, record)
        assert load_review(novel, 1).rules_version == record.rules_version

    def test_cross_version_detected(self, novel: Path):
        """换过判据就不能直接比 —— 报告要显式提示。"""
        first = normalize_review({"overall_score": 80}, 1)
        first.rules_version = "v1"
        second = normalize_review({"overall_score": 82}, 2)
        second.rules_version = "v2"
        save_review(novel, first)
        save_review(novel, second)
        summary = summarize_novel(novel)
        assert summary["comparable"] is False
        assert "不可直接比较" in format_trend(novel)

    def test_format_trend_empty(self, novel: Path):
        assert "还没有评审记录" in format_trend(novel)

    def test_without_novel_dir(self):
        assert save_review(None, normalize_review({"overall_score": 80}, 1)) is False
        assert load_review(None, 1) is None
        assert list_reviews(None) == []


class TestNoDisguise:
    """建议 3：失败必须留痕，不能伪装成及格分。"""

    def test_unparseable_returns_none(self):
        record = normalize_review("我不是 JSON", 5)
        assert record.overall is None
        assert record.ok is False
        assert "人工确认" in record.error

    def test_missing_score_returns_none(self):
        record = normalize_review({"issues": ["某问题"]}, 5)
        assert record.overall is None
        assert record.issues == ["某问题"], "失败时也要保留已有信息"

    def test_never_defaults_to_70(self):
        """回归守卫：旧实现回落 70 分，让失败看起来像及格。"""
        for payload in ("", None, {}, {"overall_score": "不知道"}, []):
            assert normalize_review(payload, 1).overall != 70

    def test_out_of_range_is_invalid(self):
        assert normalize_review({"overall_score": 999}, 1).overall is None
        assert normalize_review({"overall_score": -5}, 1).overall is None
        assert normalize_review({"overall_score": True}, 1).overall is None

    def test_valid_boundaries(self):
        assert normalize_review({"overall_score": 0}, 1).overall == 0.0
        assert normalize_review({"overall_score": 100}, 1).overall == 100.0

    def test_overall_score_alias(self):
        """`as_dict()` 要提供 `overall_score` 兼容别名（Editor 读这个名字）。"""
        record = normalize_review({"overall_score": 77}, 1)
        assert record.as_dict()["overall_score"] == record.as_dict()["overall"] == 77.0

    def test_explicit_error_preserved(self):
        record = normalize_review({"error": "AI 超时"}, 1)
        assert record.overall is None
        assert record.error == "AI 超时"

    def test_ok_requires_no_error(self):
        record = ReviewRecord(chapter=1, overall=80.0, error="有问题")
        assert record.ok is False


# ====================================================================== 建议 4：一致性


class TestConsistency:
    CHARS = {
        "林默": {"age": 24, "gender": "男", "faction": "正派"},
        "苏言": {"age": 18, "gender": "女", "faction": "中立"},
    }

    def test_age_conflict_detected(self):
        issues = check_character_properties("林默今年四十岁。", self.CHARS, chapter=3)
        assert len(issues) == 1
        assert issues[0].kind == "年龄"
        assert issues[0].severity == "high"
        assert "四十" in issues[0].evidence

    def test_age_within_tolerance_ignored(self):
        near = 24 + AGE_TOLERANCE
        assert check_character_properties(f"林默{near}岁。", self.CHARS) == []

    def test_age_attributive_ignored(self):
        """「看着四十岁的老人」里的岁数不是他的。"""
        assert check_character_properties("林默看着四十岁的老人。", self.CHARS) == []

    def test_chinese_numeral_parsed(self):
        issues = check_character_properties("林默已经六十岁了。", self.CHARS)
        assert issues and issues[0].claimed == "60 岁"

    def test_gender_conflict_detected(self):
        issues = check_character_properties("苏言是男性。", self.CHARS)
        assert issues and issues[0].kind == "性别"

    def test_gender_title_not_conflict(self):
        """「少女」是称谓不是属性 —— 实测这类造成过 118 条误报。"""
        assert check_character_properties("林默看着少女走远。", self.CHARS) == []

    def test_gender_needs_copula(self):
        assert check_character_properties("苏言看见那个男性走来。", self.CHARS) == []

    def test_multi_character_sentence_skipped(self):
        """同句有多个已知角色 ⇒ 属性词指向不确定，跳过。"""
        assert check_character_properties("林默和苏言说话，她是女性。", self.CHARS) == []

    def test_faction_conflict_is_low(self):
        issues = check_character_properties("林默投靠了反派。", self.CHARS)
        assert issues and issues[0].severity == "low"

    def test_faction_kill_is_not_membership(self):
        """「杀了反派」不是他的阵营。"""
        assert check_character_properties("林默杀了反派。", self.CHARS) == []

    def test_single_char_name_skipped(self):
        chars = {"王": {"age": 30}}
        assert check_character_properties("王三十岁。", chars) == []

    def test_issue_always_has_evidence(self):
        issues = check_character_properties("林默今年九十岁。", self.CHARS)
        assert all(i.evidence for i in issues), "没有原句的问题不许出现"

    def test_timeline_zero_chapter(self):
        issues = check_timeline_sanity([{"chapter": 0, "event": "某事"}])
        assert issues and issues[0].severity == "low"

    def test_timeline_duplicate(self):
        events = [{"chapter": 3, "event": "同一件事"}, {"chapter": 3, "event": "同一件事"}]
        assert len(check_timeline_sanity(events)) == 1

    def test_timeline_non_monotonic_allowed(self):
        """章节号回退是正常写法（插叙/回忆），不得报错。"""
        assert check_timeline_sanity([{"chapter": 5, "event": "甲"}, {"chapter": 3, "event": "乙"}]) == []

    def test_check_chapter_shape(self, tmp_path: Path):
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "characters.json").write_text(
            json.dumps({"林默": {"age": 24}}, ensure_ascii=False), encoding="utf-8"
        )
        result = check_chapter(tmp_path, 2, "林默今年五十岁。")
        assert result["ok"] is False
        assert result["summary"]["high"] == 1
        assert result["checked"]["characters"] is True
        # 设定一致性做不了，必须显式说明
        assert "未检查" in result["checked"]["settings"]

    def test_check_chapter_clean(self, tmp_path: Path):
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "characters.json").write_text(
            json.dumps({"林默": {"age": 24}}, ensure_ascii=False), encoding="utf-8"
        )
        result = check_chapter(tmp_path, 1, "林默二十四岁。")
        assert result["ok"] is True

    def test_format_issues_mentions_evidence(self):
        result = {
            "chapter": 1,
            "issues": [
                ConsistencyIssue(
                    kind="年龄", character="林默", claimed="40 岁", recorded="24 岁", evidence="林默四十岁。"
                ).as_dict()
            ],
            "summary": {"high": 1, "low": 0, "characters_checked": 1, "timeline_events": 0},
            "checked": {"settings": "未检查"},
        }
        text = format_issues(result)
        assert "林默" in text and "林默四十岁。" in text
        assert "未覆盖" in text

    def test_format_no_issues(self):
        result = {"chapter": 1, "issues": [], "summary": {"high": 0, "low": 0}, "checked": {}}
        assert "未发现" in format_issues(result)

    def test_missing_characters_file(self, tmp_path: Path):
        result = check_chapter(tmp_path, 1, "任意文本。")
        assert result["summary"]["characters_checked"] == 0
        assert result["ok"] is True


# ====================================================================== 建议 5：DNA 自动学


class TestLearnStyle:
    def _prose(self, n: int = 40) -> str:
        line = "他推开门，雨声一下子涌进来——那种声音像有人在远处敲铁皮。她想说点什么，却又停住了……"
        return NL.join(line for _ in range(n))

    def test_learns_person_and_marks(self):
        dna = learn_from_texts([self._prose()], name="测试")
        assert dna.person == "第三人称"
        assert "——" in dna.favorite_marks or "……" in dna.favorite_marks

    def test_learns_sentence_stats(self):
        dna = learn_from_texts([self._prose()])
        assert dna.sentence_mean > 0
        assert dna.sentence_cv >= 0

    def test_too_short_sample_warns(self):
        dna = learn_from_texts(["太短"])
        assert dna.warnings
        assert dna.sentence_mean == 0

    def test_mixed_person_leaves_blank(self):
        """人称不集中时不硬填 —— 否则会把混用写法误标成单一视角。"""
        text = NL.join(["我说了一句。", "你说了一句。", "他说了一句。"] * 30)
        dna = learn_from_texts([text])
        assert dna.person == ""
        assert any("人称不集中" in w for w in dna.warnings)

    def test_banned_words_not_invented(self):
        """禁词无法从正面文本反推 —— 学了就是编造。"""
        dna = learn_from_texts([self._prose()])
        assert dna.banned_words == ()

    def test_learn_from_novel(self, tmp_path: Path):
        (tmp_path / "chapters").mkdir()
        for index in range(3):
            (tmp_path / "chapters" / f"chapter_{index:04d}.txt").write_text(self._prose(10), encoding="utf-8")
        dna = learn_from_novel(tmp_path, max_chapters=10)
        assert dna is not None
        assert "自动学习" in dna.name
        assert "章成稿统计生成" in dna.notes

    def test_learn_from_novel_without_chapters(self, tmp_path: Path):
        assert learn_from_novel(tmp_path) is None
        assert learn_from_novel(None) is None

    def test_name_strips_timestamp(self, tmp_path: Path):
        novel = tmp_path / "某本书_1781862528"
        (novel / "chapters").mkdir(parents=True)
        (novel / "chapters" / "chapter_0001.txt").write_text(self._prose(10), encoding="utf-8")
        dna = learn_from_novel(novel)
        assert "1781862528" not in dna.name
        assert "某本书" in dna.name

    def test_format_dna_shows_warnings(self):
        dna = learn_from_texts(["太短"])
        text = format_dna(dna)
        assert "未能自动确定" in text

    def test_format_dna_none(self):
        assert "尚未配置" in format_dna(None)

    def test_learned_dna_injects(self):
        """学到的指纹要能直接进提示词（否则白学）。"""
        from app.style_dna import style_prompt

        dna = learn_from_texts([self._prose()])
        prompt = style_prompt(dna)
        assert "作者风格 DNA" in prompt
        assert "第三人称" in prompt
