"""补充分支覆盖：容错路径（坏输入不该让程序崩，也不该静默吞掉有效数据）。

## 为什么单独一个文件

这里测的不是"主流程能跑通"，而是**输入不可信时**的分支：
模型返回的 JSON 坏掉、`characters` 写成字符串、归档目录里有人手工放了别的文件、
技能包正文里混用表格与列表。

这些分支在真实使用中都会遇到（模型输出尤其不可信），但正常路径的测试永远走不到。
"""

from __future__ import annotations

import pytest

from app.domain.rework import parse_archive_version
from app.domain.timeline import char_list_unique, parse_extraction_result


class TestParseExtractionTolerance:
    """模型输出不可信 —— 每种坏输入都该降级成"跳过这一条"。"""

    @pytest.mark.parametrize(
        "raw",
        [
            "没有 JSON",
            "[未完",
            "]先闭后开[",
            "{不是数组}",
            "[1, 2, 3]",
            "[]",
            "",
            None,
        ],
    )
    def test_bad_input_yields_empty_list(self, raw):
        assert parse_extraction_result(raw, 1) == []

    def test_string_characters_is_wrapped(self):
        """`characters: "林风"`（单值而非列表）应被当作一个角色，而不是逐字符拆开。"""
        raw = '[{"event": "他来了", "characters": "林风"}]'
        rows = parse_extraction_result(raw, 1)
        assert rows and rows[0]["characters"] == ["林风"]

    def test_blank_character_entries_dropped(self):
        raw = '[{"event": "事件", "characters": ["林风", "  ", ""]}]'
        rows = parse_extraction_result(raw, 1)
        assert rows[0]["characters"] == ["林风"]

    def test_known_characters_filters_others(self):
        """传了 `known_characters` 就只保留名单内的 —— 防止模型编造角色名。"""
        raw = '[{"event": "事件", "characters": ["林风", "编造的人"]}]'
        rows = parse_extraction_result(raw, 1, known_characters=["林风"])
        assert rows[0]["characters"] == ["林风"]

    def test_known_characters_empty_keeps_all(self):
        raw = '[{"event": "事件", "characters": ["甲", "乙"]}]'
        rows = parse_extraction_result(raw, 1, known_characters=[])
        assert rows[0]["characters"] == ["甲", "乙"]

    def test_event_empty_is_skipped(self):
        raw = '[{"event": ""}, {"event": "有内容"}]'
        rows = parse_extraction_result(raw, 1)
        assert len(rows) == 1 and rows[0]["event"] == "有内容"

    def test_confidence_is_lowercased(self):
        raw = '[{"event": "事件", "confidence": "HIGH"}]'
        rows = parse_extraction_result(raw, 1)
        assert rows[0].get("confidence") == "high"


class TestParseArchiveVersionBoundaries:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("v1.txt", 1),
            ("v12.txt", 12),
            ("V3.txt", None),  # 大写 V 不算（文件名由本程序生成，永远是 v）
            ("v0.txt", None),  # 0 不是合法版本
            ("v.txt", None),  # 没有数字
            ("v2-old.txt", None),  # 不是纯数字
            ("notes.txt", None),
            ("v3.md", None),  # 扩展名不对
            ("", None),
            (None, None),
        ],
    )
    def test_boundaries(self, filename, expected):
        assert parse_archive_version(filename) == expected


class TestCharListUnique:
    def test_non_string_entries_are_stringified_consistently(self):
        """列表中混入非字符串时不该崩；strip 后为空的丢弃。"""
        assert char_list_unique(["甲", " 甲 ", "乙"]) == ["甲", "乙"]

    def test_all_blank_yields_empty(self):
        assert char_list_unique(["", "  ", "\t"]) == []


class TestSkillRuleDerived:
    """`SkillRule` 的派生属性（原先只被间接执行，分支没被逐个走到）。"""

    def _rule(self, body: str, level: str = "A") -> object:
        from app.domain.skill import SkillRule

        return SkillRule(level=level, title="t", body=body)

    def test_level_label_known_and_unknown(self):
        assert self._rule("x", "A").level_label == "机械改"
        assert self._rule("x", "").level_label == "通用"
        assert self._rule("x", "未来级别").level_label == "通用"

    @pytest.mark.parametrize(("level", "injectable"), [("A", True), ("B", True), ("X", False), ("H", False)])
    def test_injectable_excludes_x_and_h(self, level, injectable):
        """X（已否决）与 H（人审）**永不注入提示词** —— 这是硬约束。"""
        assert self._rule("x", level).injectable is injectable

    def test_revision_prefers_block_containing_fix(self):
        rule = self._rule("这是前言。\n\n改法：把破折号换成逗号。\n\n这是结尾。")
        assert "破折号换成逗号" in rule.revision()

    def test_revision_falls_back_to_numbered_item(self):
        rule = self._rule("前言一句。\n\n**1.** 第一条原则内容。\n\n**2.** 第二条。")
        assert "第一条原则内容" in rule.revision()

    def test_revision_falls_back_to_first_block(self):
        rule = self._rule("只有一段没有改法没有编号的正文。")
        assert rule.revision() == "只有一段没有改法没有编号的正文。"

    def test_revision_empty_body(self):
        assert self._rule("").revision() == ""

    def test_summary_truncates_with_ellipsis(self):
        rule = self._rule("字" * 200)
        out = rule.summary(limit=20)
        assert len(out) <= 20 and out.endswith("…")

    def test_summary_short_body_unchanged(self):
        rule = self._rule("短正文")
        assert rule.summary() == "短正文"

    def test_items_from_markdown_table(self):
        body = "| 特征 | 说明 |\n| --- | --- |\n| 序数词小标题 | 一二三四 |\n| 复述 | 这意味着 |"
        items = self._rule(body).items()
        assert "序数词小标题" in items
        assert "特征" not in items, "表头不该被当成条目"
        assert "---" not in items, "分隔行不该被当成条目"

    def test_items_from_bullet_list(self):
        body = "- 第一条规则\n* 第二条规则\n1. 第三条规则"
        items = self._rule(body).items()
        assert len(items) == 3

    def test_items_strips_bold_and_takes_head_before_colon(self):
        body = "- **比喻贴切度**：说明很长的一段话"
        items = self._rule(body).items()
        assert items == ["比喻贴切度"]

    def test_items_skips_overlong_heads(self):
        """冒号前超过 24 字说明是整句话而不是条目名，不该当条目。"""
        body = "- " + "很长的一句话" * 6 + "：说明"
        assert self._rule(body).items() == []

    def test_items_deduplicates(self):
        body = "- 同一条\n- 同一条\n- 另一条"
        assert self._rule(body).items() == ["同一条", "另一条"]


class TestClassifySection:
    @pytest.mark.parametrize(
        ("title", "level", "expected"),
        [
            ("第一步：脚本检测", 3, "workflow"),
            ("1. 破折号滥用", 3, "rule"),
            ("改写规则（按优先级排序）", 2, "rule"),
            ("附录：版本说明", 2, "meta"),
            ("随便一个标题", 4, "meta"),
        ],
    )
    def test_kinds(self, title, level, expected):
        from app.domain.skill import classify_section

        assert classify_section(title, level) == expected


class TestOneLineHelper:
    """`_one_line` 把多行压成一行（`revision()` 依赖它）。"""

    def _one_line(self, text: str) -> str:
        from app.domain.skill import _one_line

        return _one_line(text)

    def test_drops_blank_lines(self):
        assert self._one_line("第一行\n\n  \n第二行") == "第一行 第二行"

    def test_strips_quote_markers(self):
        """技能包里常有 `> 原文引用` 的写法，注入前要去掉引用符号。"""
        assert self._one_line("> 被引用的句子") == "被引用的句子"

    def test_strips_bullet_markers(self):
        assert self._one_line("- 条目一\n* 条目二") == "条目一 条目二"

    def test_strips_bold_markers(self):
        assert self._one_line("**加粗的词**") == "加粗的词"

    def test_empty_text(self):
        assert self._one_line("") == ""


class TestItemsSeparatorRows:
    @pytest.mark.parametrize("row", ["| --- |", "| :-: |", "| :: |", "|  |"])
    def test_separator_and_blank_cells_are_skipped(self, row):
        from app.domain.skill import SkillRule

        body = "| 特征 | 说明 |\n" + row + "\n| 真条目 | x |"
        items = SkillRule(level="A", title="t", body=body).items()
        assert items == ["真条目"]


class TestTimelineJsonEdges:
    def test_malformed_json_inside_brackets(self):
        """有方括号但内容不是合法 JSON —— 走 JSONDecodeError 分支。"""
        from app.domain.timeline import parse_extraction_result

        assert parse_extraction_result("[{坏的}]", 1) == []

    def test_trailing_comma_not_repaired(self):
        """尾逗号 JSON 不被静默修复（本项目的容错口径：宁可少一条，不要猜）。"""
        from app.domain.timeline import parse_extraction_result

        assert parse_extraction_result('[{"event": "x"},]', 1) == []

    def test_json_embedded_in_prose_is_extracted(self):
        """模型常在 JSON 前后加解释文字 —— 只要方括号内是合法数组就应抽出来。"""
        from app.domain.timeline import parse_extraction_result

        raw = '好的，以下是结果：\n[{"event": "开篇事件"}]\n希望有帮助。'
        rows = parse_extraction_result(raw, 1)
        assert len(rows) == 1 and rows[0]["event"] == "开篇事件"


class TestLastBranches:
    def test_items_skips_blank_lines(self):
        from app.domain.skill import SkillRule

        body = "\n\n- 条目一\n\n- 条目二\n"
        assert SkillRule(level="A", title="t", body=body).items() == ["条目一", "条目二"]

    def test_classify_section_rewrite_parent_title(self):
        """`## 改写时注意` 这类父标题（不含"规则/原则"等词）也应判为 rule 容器。"""
        from app.domain.skill import classify_section

        assert classify_section("改写时注意", 2) == "rule"
        assert classify_section("去 AI 的要领", 2) == "rule"

    def test_parse_result_rejects_non_array_json(self, monkeypatch):
        """防御性分支：若 JSON 解析返回非数组（理论上以 `[` 开头不会），也必须返回 []。

        用 monkeypatch 造这个形状 —— 否则这条分支永远跑不到，
        将来真出问题时就没人知道它到底有没有生效。
        """
        import app.domain.timeline as mod

        monkeypatch.setattr(mod.json, "loads", lambda s: {"不是": "数组"})
        assert mod.parse_extraction_result('[{"event": "x"}]', 1) == []


class TestLineageTolerance:
    def test_unknown_kind_falls_back_to_novel(self):
        """meta 里写了未知 `kind`（手改或旧版本遗留）时归一到 novel，不炸。"""
        from app.domain.lineage import KIND_NOVEL, LineageRecord

        record = LineageRecord.from_meta({"lineage": {"kind": "外星分支"}})
        assert record is not None and record.kind == KIND_NOVEL

    def test_non_numeric_origin_chapter_becomes_zero(self):
        from app.domain.lineage import LineageRecord

        record = LineageRecord.from_meta({"lineage": {"origin_chapter": "第三章"}})
        assert record is not None and record.origin_chapter == 0

    def test_is_within_returns_false_when_resolve_fails(self, monkeypatch):
        """路径无法解析（权限/非法字符）时判 False —— 护栏必须 fail-closed。"""
        from pathlib import Path

        from app.domain.lineage import is_within

        def boom(self):
            raise OSError("path too long")

        monkeypatch.setattr(Path, "resolve", boom)
        assert is_within("/a", "/a/b") is False

    def test_describe_lists_unchecked_dimensions(self):
        from app.domain.lineage import InheritancePlan

        plan = InheritancePlan(inherited={"characters": True, "outline": False})
        plan.items = {
            "characters": {"copy": ["characters"], "missing": [], "skipped": False},
            "outline": {"copy": [], "missing": [], "skipped": True},
        }
        assert "不继承" in plan.describe()

    def test_as_int_passes_through_int(self):
        from app.domain.lineage import _as_int

        assert _as_int(42) == 42

    def test_as_int_truncates_float(self):
        """这种浮点（JSON 里可能出现）向下取整，不做四舍五入。"""
        from app.domain.lineage import _as_int

        assert _as_int(42.7) == 42

    def test_as_int_handles_absurdly_long_digits(self):
        """Python 3.11 起 `int()` 有位数上限，超长会抛 ValueError —— 必须降级为 None。"""
        from app.domain.lineage import _as_int

        assert _as_int("9" * 5000) is None

    def test_extract_plots_skips_short_lines(self):
        from app.domain.lineage import extract_unresolved_plots, unresolved_plot_keywords

        keyword = unresolved_plot_keywords()[0]
        assert extract_unresolved_plots(f"短{keyword}") == [], "过短的行不该被当成伏笔"

    def test_describe_plan_marks_skipped(self):
        from app.domain.lineage import InheritancePlan, describe_plan_items

        plan = InheritancePlan(inherited={"characters": False})
        plan.items = {"characters": {"copy": [], "missing": [], "skipped": True}}
        lines = list(describe_plan_items(plan))
        assert any("不继承" in line for line in lines)
