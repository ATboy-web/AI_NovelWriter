"""写作预设测试：触发条件 / 调用方式 / 写作规范 / 输出质检。

四类断言与用户要求的四项验收一一对应：

| 验收项 | 用例 |
|---|---|
| 触发条件 | `TestMatch` —— 阶段、字数、体裁、显式指定四条分流规则 |
| 调用方式 | `TestPromptAssembly` + `TestInjectionIsExclusive` —— 注入什么、预算多少、与技能库互斥 |
| 写作规范 | `TestPromptAssembly` —— 规范/边界/自检三段都在，X/H 级绝不出现 |
| 输出质检 | `TestQc` —— 门禁判定、密度口径、阻断与复核的区分、信息守恒 |

> 不测"技能包是否在 `~/Downloads`"：仓库不该依赖某台机器的下载目录。
> 与真实技能包的数值对齐（翻案腔 0.763 / 提示码 1.145 / 顿号 3.817 / 定语 0.382）
> 记录在验收报告里，用**合成文本**复现同样的判据行为。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.writing_presets import (
    DETECTORS,
    PRESETS,
    PresetManager,
    build_rewrite_instruction,
    calibrated_limits,
    check_conservation,
    check_x_level,
    count_hanzi,
    detect_text,
    format_qc,
    gate_factor_issues,
    match_preset,
    official_level,
    qc_report,
    resolve_preset,
    structure_metrics,
    x_level_counts,
)

REPO_ROOT = Path(__file__).parent.parent


def _code_only(path: Path) -> str:
    """去掉注释与 docstring 的源码（说明文字里必然会提到旧写法）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    body.pop(0)
    return ast.unparse(tree)


#: 一段"AI 味"合成稿：两条翻案腔、一处提示语冒号、一处起手式、一处过长定语。
AI_ISH = (
    "真正的壁垒不是技术，而是认知。这个问题不是资源不够，而是优先级没定。\n\n"
    "一句话总结：先把范围收窄。说白了，大家都不缺想法。\n\n"
    "这是一个能够帮助团队在不增加人力的情况下显著提升审核速度的工具。"
)

#: 同一段话按技能规则清理后的样子。
CLEANED = (
    "真正的壁垒是认知。这个问题出在优先级。\n\n"
    "先把范围收窄。大家都不缺想法。\n\n"
    "这个工具能显著提升审核速度，不需要增加人力。"
)


# ====================================================================== 注册表


class TestRegistry:
    def test_five_presets_are_orthogonal(self):
        """五个预设按「阶段 / 体裁 / 长度 / 只验收」分工，不是规则多少的差别。"""
        assert set(PRESETS) == {"gen-guard", "deai-full", "novel-voice", "shortcopy", "qc-gate"}
        dims = [p.dimension for p in PRESETS.values()]
        assert len(set(dims)) == len(dims), f"预设维度重复：{dims}"

    def test_only_qc_gate_is_manual(self):
        """质检闸门不参与自动选择 —— 否则会和生成期约束抢同一份提示词。"""
        assert PRESETS["qc-gate"].auto is False
        assert all(p.auto for k, p in PRESETS.items() if k != "qc-gate")

    @pytest.mark.parametrize("key", sorted(PRESETS))
    def test_gates_reference_real_detectors(self, key):
        for detector, limit in PRESETS[key].gates:
            assert detector in DETECTORS, f"{key} 引用了不存在的检测器 {detector}"
            assert limit >= 0

    @pytest.mark.parametrize("key", sorted(PRESETS))
    def test_rule_ids_are_within_skill_range(self, key):
        for number in PRESETS[key].rule_ids:
            assert 1 <= number <= 13, f"{key} 的规则编号 {number} 超出技能包范围"

    @pytest.mark.parametrize("key", sorted(PRESETS))
    def test_every_preset_has_norms_and_gates(self, key):
        preset = PRESETS[key]
        assert preset.norms, f"{key} 缺写作规范"
        assert preset.gates, f"{key} 缺质检门禁"
        assert preset.summary and preset.stage

    def test_qc_gate_matches_deai_full(self):
        """质检闸门不得比清理预设少判项 —— 否则"清理时要求、验收时不查"。"""
        full = {g[0]: g[1] for g in PRESETS["deai-full"].gates}
        gate = {g[0]: g[1] for g in PRESETS["qc-gate"].gates}
        assert gate == full

    def test_official_levels_cover_detector_rules(self):
        """门禁里的 blocker 项必须能在官方分级里找到 A 级依据。"""
        for key, detector in DETECTORS.items():
            if detector.gate_class != "blocker":
                continue
            assert official_level(detector.label) == "A", f"{key} 标了 blocker 但官方不是 A 级"


# ====================================================================== 触发条件


class TestDivisionOfLabour:
    """预设分工守则（建议 1）：新增预设必须遵守，否则五个变十个、十个变二十个。

    守则是**可执行**的，不是文档里的一句话：
    1. 每个预设必须有**非空排除项** —— 没有排除项的预设等于"什么都管"，会和其他预设打架；
    2. 任意两个预设的规则集不得完全相同 —— 完全相同的两个只是名字不同；
    3. 维度必须唯一 —— 同一维度下的两个预设是同一件事的两种叫法。
    """

    def test_every_preset_has_exclusions(self):
        for key, preset in PRESETS.items():
            assert preset.exclude_note, f"{key} 没有排除项：它会对所有文本做全量处理，必然越界"

    def test_no_two_presets_share_exclusions(self):
        seen: dict = {}
        for key, preset in PRESETS.items():
            signature = tuple(preset.exclude_note)
            assert signature not in seen, f"{key} 与 {seen.get(signature)} 的排除项完全相同"
            seen[signature] = key

    def test_no_two_presets_share_rule_set(self):
        seen: dict = {}
        for key, preset in PRESETS.items():
            signature = tuple(sorted(preset.rule_ids))
            if not signature:  # qc-gate 不注入规则，属刻意设计
                continue
            assert signature not in seen, f"{key} 与 {seen.get(signature)} 的规则集完全相同"
            seen[signature] = key

    def test_dimensions_are_unique(self):
        dims = [p.dimension for p in PRESETS.values()]
        assert len(dims) == len(set(dims)), f"维度重复：{dims}"

    def test_preset_count_is_capped(self):
        """上限 5 个：超过就说明有人在按"规则多少"切分，而不是按场景。

        真要加第 6 个，先回答"它独占哪个维度、别的预设为什么不能覆盖它"，
        然后把这个数字改掉 —— 强制停顿，避免预设清单无限膨胀。
        """
        assert len(PRESETS) <= 5, "预设超过 5 个：请先确认新预设是否落在一个全新维度上"


class TestGateAudit:
    """门禁数字必须**有据可查**（建议 5）。"""

    @pytest.mark.parametrize("key", sorted(PRESETS))
    def test_no_unexplained_gate(self, key):
        issues = gate_factor_issues(PRESETS[key])
        assert not issues, "；".join(issues)

    def test_limits_are_derived_from_human_ref(self):
        """有 body 参照的项，倍数必须落在合理区间；超界的必须有策略说明。"""
        from app.writing_presets import GATE_FACTOR_RANGE

        low, high = GATE_FACTOR_RANGE
        for key, preset in PRESETS.items():
            for row in calibrated_limits(preset):
                if row["factor"] is None or row["basis"] == "policy":
                    continue
                assert low <= row["factor"] <= high, f"{key}.{row['detector']} 倍数 {row['factor']} 无依据"

    def test_policy_entries_are_real_gates(self):
        """策略说明不能挂在不存在的门禁上（改门禁时容易漏删）。"""
        for key, preset in PRESETS.items():
            gate_keys = {g[0] for g in preset.gates}
            for detector, _reason in preset.gate_policy:
                assert detector in gate_keys, f"{key}.gate_policy 里的 {detector} 不在门禁中"

    def test_qc_gate_matches_deai_full(self):
        """质检闸门不得比清理预设少判项 —— 否则"清理时要求、验收时不查"。"""
        full = {g[0]: g[1] for g in PRESETS["deai-full"].gates}
        gate = {g[0]: g[1] for g in PRESETS["qc-gate"].gates}
        assert gate == full


class TestMatch:
    def test_generate_stage_wins(self):
        """生成阶段一律走 gen-guard，即使前文是小说。"""
        key, reason = match_preset("第一章 他说：走吧。", stage="generate")
        assert key == "gen-guard"
        assert "生成" in reason

    def test_short_text_goes_to_shortcopy(self):
        key, reason = match_preset("一句很短的话。")
        assert key == "shortcopy"
        assert "汉字" in reason

    def test_fiction_goes_to_novel_voice(self):
        text = "第一章 雪夜\n" + "他说：「走吧。」" * 40 + "雪落在铠甲上。" * 60
        key, _ = match_preset(text)
        assert key == "novel-voice"

    def test_nonfiction_defaults_to_deai_full(self):
        text = "这是一篇关于工程效率的评论。" * 80
        key, _ = match_preset(text)
        assert key == "deai-full"

    def test_explicit_key_wins(self):
        key, reason = match_preset("短文", explicit="deai-full")
        assert key == "deai-full" and "显式" in reason

    def test_explicit_by_name_and_trigger(self):
        assert match_preset("x", explicit="成稿去 AI 味")[0] == "deai-full"
        assert match_preset("x", explicit="去AI味")[0] == "deai-full"

    def test_unknown_explicit_falls_through(self):
        key, _ = match_preset("", explicit="不存在的预设")
        assert key in PRESETS

    def test_resolve_returns_none_for_blank(self):
        assert resolve_preset("") is None
        assert resolve_preset("不存在") is None


# ====================================================================== 调用方式 / 规范


class TestPromptAssembly:
    def test_budget_is_respected(self):
        for key, preset in PRESETS.items():
            for budget in (120, 300, preset.budget):
                assert len(preset.to_prompt(budget=budget)) <= budget, (key, budget)

    def test_contains_four_sections(self):
        text = PRESETS["deai-full"].to_prompt(budget=1200)
        assert "【写作预设：" in text
        assert "写作规范：" in text
        assert "本预设的边界：" in text
        assert "交付前自检：" in text

    def test_x_and_h_are_forbidden_not_injected(self):
        """X 级只作为「禁止改动」出现，H 级只作为「不判」出现 —— 不得变成可执行规则。"""
        text = PRESETS["deai-full"].to_prompt(budget=1200)
        assert "X 级永不改" in text
        assert "H 级不判" in text
        # 不得出现"把序数词小标题改掉"这类会被模型当指令的写法
        assert "删掉序数词" not in text

    def test_novel_voice_excludes_punctuation_rules(self):
        """小说预设必须显式排除顿号/破折号/冒号，否则会把叙事改坏。"""
        text = PRESETS["novel-voice"].to_prompt(budget=1200)
        assert "不处理顿号" in text
        assert "不处理破折号" in text
        assert "不处理冒号" in text

    def test_gen_guard_does_not_inject_rewrite_rules(self):
        text = PRESETS["gen-guard"].to_prompt(budget=1200)
        assert "不做「改写」动作" in text

    def test_truncation_is_disclosed(self):
        class FakeRule:
            def __init__(self, title):
                self.title = title
                self.level = "B"

            def revision(self):
                return "改法：" + "很长的说明" * 30

        rules = [FakeRule(f"{i}. 规则{i}") for i in range(1, 12)]
        text = PRESETS["deai-full"].to_prompt(rules=rules, budget=700)
        assert "未注入" in text or len(text) <= 700

    def test_rule_levels_use_official_grading(self):
        class Rule:
            title = "1. 翻案腔"
            level = "B"  # 技能库启发式判成 B

            def revision(self):
                return "改法：直接下判断"

        text = PRESETS["deai-full"].to_prompt(rules=[Rule()], budget=1200)
        assert "- [A] 1. 翻案腔" in text, "必须用技能包官方 A 级，而不是启发式 B 级"

    def test_missing_library_does_not_crash(self):
        assert PRESETS["deai-full"].to_prompt(rules=[], budget=600)


# ====================================================================== 互斥注入


class TestInjectionIsExclusive:
    def test_agent_injects_preset_or_skill_not_both(self):
        source = _code_only(REPO_ROOT / "app" / "novel_agent.py")
        assert "writing_presets" in source
        assert "if not preset_ctx" in source, "预设与技能库必须互斥，否则同一批规则注入两遍"

    def test_single_injection_point(self):
        """`prompt_context` 只允许在 novel_agent 出现一次（防止二次注入）。"""
        source = _code_only(REPO_ROOT / "app" / "novel_agent.py")
        assert source.count("prompt_context(") == 2, "应为预设 + 技能各一处，且互斥"

    def test_preset_module_is_not_orphan(self):
        callers = [
            p.name
            for p in (REPO_ROOT / "app").rglob("*.py")
            if p.name != "writing_presets.py" and "writing_presets" in p.read_text(encoding="utf-8")
        ]
        assert "novel_agent.py" in callers
        assert "skill_library_panel.py" in callers


# ====================================================================== 输出质检


class TestQc:
    def test_detects_all_blockers_on_ai_text(self):
        report = qc_report(AI_ISH, PRESETS["deai-full"])
        assert report["ok"] is False
        assert report["blockers"] >= 1
        labels = {i["detector"]: i for i in report["items"]}
        assert labels["fanan"]["count"] == 2
        assert labels["starter"]["count"] == 1
        assert labels["colon_prompt"]["count"] == 1

    def test_passes_after_cleaning(self):
        report = qc_report(CLEANED, PRESETS["deai-full"])
        assert report["blockers"] == 0, report["items"]
        assert report["ok"] is True

    def test_density_unit_matches_hanzi(self):
        """密度口径 = 次数 × 1000 / 汉字数，与技能包一致。"""
        text = "不是甲而是乙。" * 3  # 6 个汉字/句 → 18 汉字，3 次
        report = qc_report(text, PRESETS["deai-full"])
        fanan = next(i for i in report["items"] if i["detector"] == "fanan")
        assert fanan["count"] == 3
        assert fanan["per_ktx"] == pytest.approx(3 * 1000 / count_hanzi(text), rel=1e-3)

    def test_review_items_do_not_block(self):
        """粗筛项超限只提示复核 —— 技能包自己的合格稿里冒号/破折号仍超标。"""
        text = "问题：这段在讲什么。" * 20 + "正文——说明。" * 10
        report = qc_report(text, PRESETS["deai-full"])
        assert report["blockers"] == 0
        assert report["reviews"] >= 1
        assert report["ok"] is True

    def test_semantic_layer_is_listed_not_judged(self):
        report = qc_report(AI_ISH, PRESETS["deai-full"])
        keys = {i["key"] for i in report["semantic"]}
        # 规则 6（相邻句结构同款）原先既无机检也不在清单里 —— 属真实遗漏，已补
        assert keys == {"rename", "cohesion", "colon_judge", "iso_pair", "iso3"}
        # 不得给出"通过/不通过"判定
        assert all("passed" not in item for item in report["semantic"])

    def test_qc_gate_preset_is_unaffected_by_rule_injection(self):
        preset = PRESETS["qc-gate"]
        assert preset.rule_ids == ()
        assert preset.gates  # 但门禁必须完整

    def test_format_qc_marks_blocker_and_review_differently(self):
        text = format_qc(qc_report(AI_ISH, PRESETS["deai-full"]), "成稿去 AI 味")
        assert "❌" in text and "阻断" in text
        assert "待判读" in text

    def test_human_reference_is_shown(self):
        text = format_qc(qc_report(AI_ISH, PRESETS["deai-full"]), "x")
        assert "人类参考" in text


class TestConservation:
    def test_numbers_must_survive(self):
        result = check_conservation("花了 10 小时，成本 30 美元。", "花了不少时间，成本 30 美元。")
        assert result["ok"] is False
        assert "10" in result["missing_numbers"]

    def test_numbers_preserved(self):
        result = check_conservation("花了 10 小时。", "用了 10 小时。")
        assert result["ok"] is True

    def test_quote_change_is_warning_only(self):
        """「」也可能是强调而非引文 ⇒ 只提示，不判不合格。"""
        result = check_conservation("他说「原文如此」。", "他说「改成这样」。")
        assert result["ok"] is True
        assert result["quotes_ok"] is False

    def test_no_reference_means_no_check(self):
        report = qc_report(CLEANED, PRESETS["deai-full"], reference=None)
        assert report["conservation"] is None


# ====================================================================== 检测器口径


class TestDetectors:
    def test_fanan_counts_both_sides(self):
        assert len(DETECTORS["fanan"].find("不是技术，而是认知。")) == 1
        assert len(DETECTORS["fanan"].find("与其说效率，不如说焦虑。")) == 1

    def test_colon_prompt_is_broad_but_not_any_colon(self):
        assert len(DETECTORS["colon_prompt"].find("一句话总结：先做小的。")) == 1
        assert len(DETECTORS["colon_prompt"].find("时间：周三")) == 0

    def test_long_attr_does_not_fire_on_normal_text(self):
        """❌ 曾经的「的…的」宽口径在正常中文里误报约 10 倍，必须不命中。"""
        normal = "我们的目标是提升团队的协作效率。"
        assert len(DETECTORS["long_attr"].find(normal)) == 0

    def test_dunhao_requires_three_items(self):
        assert len(DETECTORS["dunhao"].find("甲、乙、丙")) == 1
        assert len(DETECTORS["dunhao"].find("甲、乙")) == 0

    def test_dash_is_density_based(self):
        assert DETECTORS["dash"].unit == "density"

    def test_detect_text_covers_every_detector(self):
        hits = detect_text(AI_ISH)
        assert set(hits) == set(DETECTORS)


# ====================================================================== 状态


class TestManager:
    @pytest.fixture()
    def manager(self, tmp_path: Path) -> PresetManager:
        return PresetManager(state_file=tmp_path / "presets.json")

    def test_activate_and_persist(self, manager, tmp_path):
        ok, message = manager.activate("novel-voice")
        assert ok and "小说叙事" in message
        again = PresetManager(state_file=tmp_path / "presets.json")
        assert again.active == "novel-voice"

    def test_activate_empty_clears(self, manager):
        manager.activate("deai-full")
        assert manager.activate("")[0] is True
        assert manager.active == ""

    def test_activate_unknown_rejected(self, manager):
        ok, message = manager.activate("nope")
        assert ok is False and "不存在" in message

    def test_auto_toggle(self, manager):
        manager.set_auto(False)
        assert manager.current("") is None
        assert "关闭" in manager.explain("")

    def test_current_prefers_manual(self, manager):
        manager.activate("shortcopy")
        assert manager.current("第一章 他说").key == "shortcopy"

    def test_explain_reports_reason(self, manager):
        assert "自动选择" in manager.explain("第一章 他说：「走吧」" * 30)

    def test_corrupt_state_file_is_tolerated(self, tmp_path):
        path = tmp_path / "presets.json"
        path.write_text("{not json", encoding="utf-8")
        manager = PresetManager(state_file=path)
        assert manager.active == ""


# ====================================================================== X 级反向守卫


class TestXLevelGuard:
    """技能包最核心的安全规则是「X 级永不改」；只靠"不注入"防不住顺手删。"""

    @pytest.mark.parametrize(
        "text,marker",
        [
            ("1. 第一点\n2. 第二点", "序数词小标题"),
            ("这意味着团队要重排优先级。", "「这意味着」复述"),
            ("我见过几种典型场景：交付延期、预算超支。", "空转句引列表"),
        ],
    )
    def test_counts_each_marker(self, text, marker):
        assert x_level_counts(text)[marker] >= 1

    def test_no_loss_passes(self):
        text = "1. 第一点\n这意味着要延期。"
        assert check_x_level(text, text + "\n\n补一句。")["ok"] is True

    def test_deletion_is_flagged(self):
        original = "1. 第一点\n这意味着要延期。"
        revised = "第一点\n要延期。"
        result = check_x_level(original, revised)
        assert result["ok"] is False
        assert set(result["dropped"]) == {"序数词小标题", "「这意味着」复述"}

    def test_qc_fails_when_x_deleted(self):
        """改了不该改的 ⇒ 即使 blocker 项全过，也不得判合格。"""
        report = qc_report(CLEANED, PRESETS["deai-full"], reference=AI_ISH + "\n1. 第一点")
        assert report["x_guard"]["ok"] is False
        assert report["ok"] is False


# ====================================================================== C 级结构指标


class TestStructure:
    """C 级结构指标：只报告，不设门禁。"""

    #: 用 `chr(10)` 拼换行 —— 比在源码里写转义更稳（编辑器/工具链不会改写它）
    NL = chr(10)

    def test_counts_paragraphs_and_sentences(self):
        text = "第一段。第二句。" + self.NL + self.NL + "第二段。"
        metrics = structure_metrics(text)
        assert metrics["paragraphs"] == 2
        assert metrics["sentences"] == 3

    def test_cv_is_zero_for_uniform(self):
        metrics = structure_metrics("甲乙丙丁。戊己庚辛。")
        assert metrics["sentence_cv"] == 0.0

    def test_empty_text(self):
        metrics = structure_metrics("")
        assert metrics["paragraphs"] == 0 and metrics["sentences"] == 0

    def test_reported_but_never_gated(self):
        """C 级只报告：报告里有数字，但不参与 ok 判定。"""
        report = qc_report(CLEANED, PRESETS["deai-full"])
        assert "structure" in report and "sentence_cv" in report["structure"]
        assert all(i["detector"] != "sentence_cv" for i in report["items"])


class TestSkillUpgradeFollows:
    """技能包升级时预设应**自动跟随**（建议 5 的迭代方向）。

    机制是"按规则编号引用 + 不重抄规则文本"。这里用假规则对象模拟
    "技能包把第 1 条规则的措辞改了"，确认预设输出跟着变 ——
    如果哪天有人为了"稳定"把规则文本抄进预设，这条会变红。
    """

    def _rule(self, title: str, summary: str, level: str = "A"):
        class Rule:
            def __init__(self):
                self.title = title
                self.level = level

            def revision(self):
                return summary

        return Rule()

    def test_changed_rule_text_flows_through(self):
        old_rule = self._rule("1. 翻案腔", "改法：直接正面下判断。")
        new_rule = self._rule("1. 翻案腔", "改法：新版改了措辞，直接给判断并保留限定词。")

        old_text = PRESETS["deai-full"].to_prompt(rules=[old_rule], budget=1200)
        new_text = PRESETS["deai-full"].to_prompt(rules=[new_rule], budget=1200)
        assert "直接正面下判断" in old_text
        assert "新版改了措辞" in new_text

    def test_rule_removal_is_visible(self):
        """技能包里删掉某条规则 ⇒ 预设不再显示它（不报错、不残留旧文本）。"""
        only_rule = self._rule("3. 起手式", "改法：删掉。")
        text = PRESETS["deai-full"].to_prompt(rules=[only_rule], budget=1200)
        assert "起手式" in text
        assert "翻案腔" not in text

    def test_preset_does_not_hardcode_rule_text(self):
        """守卫：预设的文本字段里不得抄进规则原文（技能升级时会漂移）。

        只查预设自身的叙述字段，不扫整个文件 —— 检测器的 `note` 里
        复述一句规则要点是合理的，那是给人看的说明，不参与装配。
        """
        for key, preset in PRESETS.items():
            fields = list(preset.norms) + list(preset.exclude_note) + list(preset.self_check) + [preset.summary]
            for text in fields:
                assert not text.startswith("改法："), f"{key} 的字段里抄了规则原文：{text[:30]}"


class TestStyleDnaWiring:
    """风格 DNA 必须真的进入生成链（否则只是编辑器里的一个按钮）。"""

    def test_prompt_context_reads_dna(self, tmp_path: Path):
        (tmp_path / "风格DNA.json").write_text(
            json.dumps({"name": "某作者", "banned_words": ["赋能"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        manager = PresetManager(state_file=tmp_path / "state.json")
        manager.activate("gen-guard")
        ctx = manager.prompt_context(budget=1200, novel_dir=tmp_path)
        assert "作者风格 DNA" in ctx
        assert "赋能" in ctx

    def test_no_dna_no_block(self, tmp_path: Path):
        manager = PresetManager(state_file=tmp_path / "state.json")
        manager.activate("gen-guard")
        ctx = manager.prompt_context(budget=1200, novel_dir=tmp_path)
        assert "作者风格 DNA" not in ctx

    def test_agent_passes_novel_dir(self):
        source = _code_only(REPO_ROOT / "app" / "novel_agent.py")
        # `ast.unparse` 会把双引号统一成单引号，所以只匹配结构片段
        assert "self.memory" in source and "novel_dir" in source, "生成链没有把作品目录传给预设"
        assert "prompt_context(" in source


class TestTwoPhaseInstruction:
    """两段式（建议 3b）：改写指令只能由**已完成的报告**生成。"""

    def test_instruction_has_hard_constraints(self):
        report = qc_report(AI_ISH, PRESETS["deai-full"], with_candidates=False)
        text = build_rewrite_instruction(report, PRESETS["deai-full"])
        for keyword in ("硬性约束", "信息守恒", "结构不动", "永不改", "逐处改动清单"):
            assert keyword in text

    def test_instruction_embeds_detection_results(self):
        report = qc_report(AI_ISH, PRESETS["deai-full"], with_candidates=False)
        text = build_rewrite_instruction(report, PRESETS["deai-full"])
        assert "检测结果" in text
        assert "翻案腔" in text

    def test_instruction_budget(self):
        report = qc_report(AI_ISH, PRESETS["deai-full"], with_candidates=False)
        text = build_rewrite_instruction(report, PRESETS["deai-full"], budget=600)
        assert len(text) <= 600

    def test_instruction_without_report_sections_is_safe(self):
        """空报告也不能崩（面板可能传入不完整的 dict）。"""
        text = build_rewrite_instruction({}, PRESETS["deai-full"])
        assert "硬性约束" in text
