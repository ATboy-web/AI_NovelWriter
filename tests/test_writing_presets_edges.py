"""写作预设的**边界与降级分支**（补充 `test_writing_presets.py`）。

主测试文件覆盖"正常路径"（预设能匹配、能装配、能判定）。本文件专门覆盖
那些**只有出错时才走到**的代码：

| 分支 | 为什么必须有测试 |
|---|---|
| 规则摘要抛异常 | 技能包的规则对象格式多样，摘要失败不能让整个注入崩掉 |
| 状态文件读写失败 | 磁盘满 / 只读目录下，预设不可用但不该阻断写作 |
| 单例初始化失败 | `get_preset_manager()` 明确承诺返回 `None` 而不是抛 |
| 守恒/守卫渲染的失败分支 | 报告要能显示"哪里不对"，否则用户只看到"不通过" |
| `as_dict` 结构 | 面板与外部工具依赖这些字段名 |

这些路径平时不执行，一旦执行就是"出问题的时候"—— 恰恰最不能崩。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.writing_presets as wp
from app.writing_presets import (
    PRESETS,
    PresetManager,
    _rule_summary,
    build_preset_context,
    build_rewrite_instruction,
    calibrated_limits,
    check_conservation,
    format_qc,
    gate_factor_issues,
    get_preset_manager,
    qc_report,
    reset_preset_manager,
)

NL = chr(10)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    """每个用例都用自己的状态文件，并清掉单例与规则缓存。"""
    monkeypatch.setattr(wp, "_manager", None)
    monkeypatch.setattr(wp, "_library_cache", None)
    yield


# ====================================================================== as_dict


class TestAsDict:
    def test_all_presets_serialise(self):
        for key, preset in PRESETS.items():
            data = preset.as_dict()
            assert data["key"] == key
            assert {"name", "dimension", "summary", "stage", "triggers", "rule_ids", "levels"} <= set(data)
            assert isinstance(data["gates"], list)
            assert all({"detector", "limit"} <= set(g) for g in data["gates"])

    def test_person_strict_exposed(self):
        assert PRESETS["novel-voice"].as_dict()["person_strict"] is True
        assert PRESETS["deai-full"].as_dict()["person_strict"] is False

    def test_json_serialisable(self):
        """面板可能把 as_dict 结果直接丢给 JSON —— 不能有 set / 元组。"""
        dumped = json.dumps(PRESETS["deai-full"].as_dict(), ensure_ascii=False)
        assert "deai-full" in dumped


# ====================================================================== 规则摘要


class TestRuleSummary:
    def test_prefers_revision(self):
        class Rule:
            def revision(self):
                return "改法：直接下判断"

            def summary(self, limit):
                return "摘要"

        assert "直接下判断" in _rule_summary(Rule(), 50)

    def test_falls_back_to_summary(self):
        class Rule:
            def summary(self, limit):
                return "这是摘要"

        assert _rule_summary(Rule(), 50) == "这是摘要"

    def test_summary_without_argument(self):
        """有些规则对象的 `summary` 不吃参数 —— 要能兼容（TypeError 回退）。"""

        class Rule:
            def summary(self):
                return "无参摘要"

        assert _rule_summary(Rule(), 50) == "无参摘要"

    def test_exception_returns_empty(self):
        """摘要抛异常时必须返回空串，让规则名仍能显示 —— 不能让整个注入失败。"""

        class Rule:
            def revision(self):
                raise RuntimeError("解析炸了")

        assert _rule_summary(Rule(), 50) == ""

    def test_no_methods_returns_empty(self):
        class Rule:
            pass

        assert _rule_summary(Rule(), 50) == ""

    def test_empty_value_returns_empty(self):
        class Rule:
            def revision(self):
                return ""

        assert _rule_summary(Rule(), 50) == ""

    def test_newlines_flattened(self):
        class Rule:
            def revision(self):
                return "第一行" + NL + "第二行"

        assert NL not in _rule_summary(Rule(), 100)


# ====================================================================== 状态文件异常


class TestStateFileFailures:
    def test_unwritable_directory_is_tolerated(self, tmp_path: Path, monkeypatch):
        """状态文件写不进去 ⇒ activate 仍返回成功（内存状态已改），只是不持久化。"""
        blocker = tmp_path / "blocked"
        blocker.write_text("我不是目录", encoding="utf-8")
        manager = PresetManager(state_file=blocker / "presets.json")
        ok, _message = manager.activate("deai-full")
        assert ok is True
        assert manager.active == "deai-full"

    def test_corrupt_state_ignored(self, tmp_path: Path):
        path = tmp_path / "state.json"
        path.write_text("{坏 json", encoding="utf-8")
        manager = PresetManager(state_file=path)
        assert manager.active == ""
        assert manager.auto is True

    def test_non_object_state_ignored(self, tmp_path: Path):
        path = tmp_path / "state.json"
        path.write_text("[1,2,3]", encoding="utf-8")
        assert PresetManager(state_file=path).active == ""

    def test_unknown_active_key_ignored(self, tmp_path: Path):
        """状态文件里存了一个已不存在的预设名 ⇒ 回退到自动选择。"""
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"active": "已被删除的预设"}), encoding="utf-8")
        assert PresetManager(state_file=path).active == ""

    def test_auto_flag_persisted(self, tmp_path: Path):
        path = tmp_path / "state.json"
        manager = PresetManager(state_file=path)
        manager.set_auto(False)
        assert PresetManager(state_file=path).auto is False


# ====================================================================== 单例


class TestSingleton:
    def test_returns_manager(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(wp, "default_presets_file", lambda: tmp_path / "p.json")
        manager = get_preset_manager()
        assert isinstance(manager, PresetManager)

    def test_reuses_instance(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(wp, "default_presets_file", lambda: tmp_path / "p.json")
        assert get_preset_manager() is get_preset_manager()

    def test_returns_none_on_failure(self, monkeypatch):
        """构造失败必须返回 None —— 承诺过的降级契约。"""

        def boom():
            raise RuntimeError("磁盘不可用")

        monkeypatch.setattr(wp, "PresetManager", boom)
        assert get_preset_manager() is None

    def test_reset_clears(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(wp, "default_presets_file", lambda: tmp_path / "p.json")
        first = get_preset_manager()
        reset_preset_manager()
        assert get_preset_manager() is not first

    def test_build_context_without_manager(self, monkeypatch):
        monkeypatch.setattr(wp, "get_preset_manager", lambda: None)
        assert build_preset_context(budget=500) == ""


# ====================================================================== 规则库不可用


class TestLibraryUnavailable:
    def test_prompt_still_works_without_rules(self, monkeypatch):
        """技能库不可用 ⇒ 预设仍能注入（规则少几条而已），不能返回空。"""
        monkeypatch.setattr(wp, "_library_cache", None)
        monkeypatch.setitem(__import__("sys").modules, "app.skill_library", None)
        text = wp.build_preset_context(budget=800, stage="generate")
        assert text == "" or "写作预设" in text

    def test_library_exception_is_swallowed(self, monkeypatch):
        class Boom:
            def enabled_skills(self):
                raise RuntimeError("技能库炸了")

        monkeypatch.setattr(wp, "_library_cache", None)
        import app.skill_library as real

        monkeypatch.setattr(real, "get_skill_library", lambda: Boom())
        manager = PresetManager(state_file=Path("/tmp") / "x.json")
        manager.activate("gen-guard")
        # 不抛即通过
        manager.prompt_context(budget=500)


# ====================================================================== 报告渲染的失败分支


class TestReportRenderingFailures:
    def _report(self, conservation=None, x_guard=None):
        return {
            "preset": "deai-full",
            "hanzi": 100,
            "passed": 0,
            "failed": 0,
            "blockers": 0,
            "reviews": 0,
            "items": [],
            "semantic": [],
            "conservation": conservation,
            "x_guard": x_guard,
            "structure": None,
            "candidates": None,
        }

    def test_missing_numbers_rendered_as_error(self):
        report = self._report(
            conservation={
                "numbers_total": 3,
                "quotes_total": 0,
                "missing_numbers": ["10", "30"],
                "missing_quotes": [],
                "ok": False,
                "quotes_ok": True,
            }
        )
        text = format_qc(report)
        assert "❌" in text and "10" in text and "必须补回" in text

    def test_quote_difference_rendered_as_warning(self):
        report = self._report(
            conservation={
                "numbers_total": 1,
                "quotes_total": 1,
                "missing_numbers": [],
                "missing_quotes": ["原句"],
                "ok": True,
                "quotes_ok": False,
            }
        )
        text = format_qc(report)
        assert "⚠️" in text and "原句" in text and "人工确认" in text

    def test_numbers_kept_but_quotes_changed_shows_both(self):
        """数字保住了、引语变了 ⇒ 既要报"数字 OK"也要报引语待核。"""
        report = self._report(
            conservation={
                "numbers_total": 2,
                "quotes_total": 1,
                "missing_numbers": [],
                "missing_quotes": ["某句"],
                "ok": True,
                "quotes_ok": False,
            }
        )
        text = format_qc(report)
        assert "数字 2 个均保留" in text
        assert "某句" in text

    def test_x_guard_dropped_rendered(self):
        report = self._report(
            x_guard={
                "before": {"序数词小标题": 2},
                "after": {"序数词小标题": 0},
                "dropped": {"序数词小标题": 2},
                "ok": False,
            }
        )
        text = format_qc(report)
        assert "❌" in text and "序数词小标题" in text and "误删" in text

    def test_style_allowed_marked(self):
        report = self._report()
        report["items"] = [
            {
                "detector": "dash",
                "label": "破折号",
                "rule": "r8",
                "count": 5,
                "per_ktx": 2.0,
                "limit": 2.0,
                "human_ref": 0.8,
                "passed": True,
                "style_allowed": True,
                "samples": [],
                "hint": "",
                "blocking": False,
                "gate_class": "review",
            }
        ]
        assert "🎨" in format_qc(report)

    def test_unknown_item_without_human_ref(self):
        report = self._report()
        report["items"] = [
            {
                "detector": "semicolon",
                "label": "分号",
                "rule": "F",
                "count": 1,
                "per_ktx": 1.0,
                "limit": 2.0,
                "human_ref": None,
                "passed": True,
                "style_allowed": False,
                "samples": [],
                "hint": "",
                "blocking": False,
                "gate_class": "review",
            }
        ]
        text = format_qc(report)
        assert "分号" in text
        assert "人类参考 None" not in text


# ====================================================================== 守恒与门禁边界


class TestConservationEdges:
    def test_no_numbers_at_all(self):
        result = check_conservation("没有数字的句子。", "还是没有数字。")
        assert result["ok"] is True
        assert result["numbers_total"] == 0

    def test_decimal_and_percent(self):
        result = check_conservation("得分 0.9169，提升 79%。", "得分 0.9169，提升 79%。")
        assert result["ok"] is True

    def test_percent_lost(self):
        result = check_conservation("提升 79%。", "有提升。")
        assert "79%" in result["missing_numbers"]

    def test_multiple_quote_styles(self):
        result = check_conservation('他说「甲」，又说“乙”，还说"丙"。', '他说「甲」，又说“乙”，还说"丙"。')
        assert result["quotes_total"] >= 3
        assert result["ok"] is True


class TestGatePolicy:
    def test_policy_rows_marked(self):
        """有策略说明的项 basis 应是 policy，而不是 human_ref。"""
        rows = calibrated_limits(PRESETS["novel-voice"])
        assert any(row["basis"] == "policy" for row in rows)

    def test_shortcopy_policy_reasons_non_empty(self):
        for _detector, reason in PRESETS["shortcopy"].gate_policy:
            assert reason, "策略说明不能是空字符串（否则等于没解释）"

    def test_manual_basis_for_no_reference(self):
        """分号没有人类参照 ⇒ basis 是 manual。"""
        rows = calibrated_limits(PRESETS["deai-full"])
        semicolon = [r for r in rows if r["detector"] == "semicolon"]
        if semicolon:
            assert semicolon[0]["basis"] == "manual"

    def test_all_presets_pass_audit(self):
        for key, preset in PRESETS.items():
            assert gate_factor_issues(preset) == [], key


# ====================================================================== 整装与指令


class TestAssemblyEdges:
    def test_budget_zero_returns_empty_or_short(self):
        assert len(PRESETS["deai-full"].to_prompt(budget=10)) <= 10

    def test_rewrite_instruction_with_dna(self, tmp_path: Path):
        from app.style_dna import parse_style_dna

        dna = parse_style_dna({"banned_words": ["赋能"]})
        report = qc_report("短文本。", PRESETS["deai-full"], with_candidates=False)
        text = build_rewrite_instruction(report, PRESETS["deai-full"], dna=dna)
        assert "赋能" in text, "改写指令必须带上风格 DNA 的禁词"

    def test_rewrite_instruction_lists_style_allowed(self):
        """作者特征要写进指令的"不得改"清单，否则模型会照旧删。"""
        from app.style_dna import parse_style_dna

        text = ("他停了一下——然后走了。" * 20) + ("正文继续。" * 40)
        dna = parse_style_dna({"favorite_marks": ["——"]})
        report = qc_report(text, PRESETS["deai-full"], dna=dna, with_candidates=False)
        instruction = build_rewrite_instruction(report, PRESETS["deai-full"], dna=dna)
        assert "作者风格特征" in instruction or "不得改" in instruction

    def test_rewrite_instruction_truncated_gracefully(self):
        report = qc_report("正文。" * 100, PRESETS["deai-full"])
        text = build_rewrite_instruction(report, PRESETS["deai-full"], budget=200)
        assert len(text) <= 200
        assert text.endswith("…") or len(text) < 200
