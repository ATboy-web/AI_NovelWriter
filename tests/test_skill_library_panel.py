"""技能库面板测试：纯函数渲染 + 真实 Tk 构建。

分两层，理由与 `test_panel_controls_mounted.py` 相同：

- **纯函数层**（`skill_rows` / `skill_detail_lines` / `match_report` / `preview_text`）
  脱离 Tk 单测，覆盖"信息有没有被正确渲染"；
- **Tk 层**只验"面板建得起来、按钮被几何管理器接管"，不重复测渲染细节。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_skill_library import write_skill  # noqa: E402

from app.panels.skill_library_panel import (  # noqa: E402
    match_report,
    preview_text,
    skill_detail_lines,
    skill_rows,
)
from app.skill_library import MatchResult, parse_skill  # noqa: E402


def _info(skill_root: Path) -> dict:
    skill = parse_skill(skill_root)
    return skill.as_dict()


# ====================================================================== 表格行


class TestSkillRows:
    def test_basic_row(self, tmp_path: Path):
        rows = skill_rows([_info(write_skill(tmp_path / "s"))])
        assert len(rows) == 1
        iid, values = rows[0]
        assert iid == "demo-tone"
        assert values[0] == "demo-tone"
        assert values[3] == "未启用"

    def test_enabled_and_ref_marked(self, tmp_path: Path):
        info = _info(write_skill(tmp_path / "s"))
        info["enabled"] = True
        info["mode"] = "ref"
        _iid, values = skill_rows([info])[0]
        assert "已启用" in values[3] and "引用" in values[3]

    def test_long_scenario_truncated(self, tmp_path: Path):
        info = _info(write_skill(tmp_path / "s"))
        info["scenarios"] = ["这是一个非常非常长的场景描述用来测试截断是否生效"]
        _iid, values = skill_rows([info])[0]
        assert values[2].endswith("…") and len(values[2]) <= 18

    def test_missing_scenario(self, tmp_path: Path):
        info = _info(write_skill(tmp_path / "s"))
        info["scenarios"] = []
        _iid, values = skill_rows([info])[0]
        assert "未声明" in values[2]


# ====================================================================== 详情


class TestSkillDetail:
    def test_empty(self):
        assert skill_detail_lines({}) == []

    def test_contains_key_sections(self, tmp_path: Path):
        lines = dict(skill_detail_lines(_info(write_skill(tmp_path / "s"))))
        assert lines["键"] == "demo-tone"
        assert "适用场景" in lines
        assert "触发词" in lines
        assert "规则分级" in lines
        assert "调用参数" in lines
        assert "包含文件" in lines

    def test_blocked_rules_counted(self, tmp_path: Path):
        info = _info(write_skill(tmp_path / "s"))
        lines = dict(skill_detail_lines(info))
        blocked = sum(1 for r in info["rules"] if not r["injectable"])
        assert f"{blocked} 条 X/H 级永不注入" in lines["可注入"]

    def test_no_params_omits_line(self, tmp_path: Path):
        info = _info(write_skill(tmp_path / "s", scripts=False))
        info["params"] = []
        assert "调用参数" not in dict(skill_detail_lines(info))


# ====================================================================== 匹配报告


class TestMatchReport:
    def test_empty_explains_why(self):
        text = match_report([], {}, 120)
        assert "没有技能匹配" in text
        assert "120 字" in text

    def test_renders_score_and_reasons(self):
        text = match_report(
            [MatchResult(key="demo-tone", score=0.42, reasons=("去AI味",))], {"demo-tone": "去AI味"}, 300
        )
        assert "去AI味" in text
        assert "42%" in text
        assert "不会自动启用" in text

    def test_no_reason_fallback(self):
        text = match_report([MatchResult(key="k", score=0.2)], {"k": "K"}, 10)
        assert "无明确命中词" in text


# ====================================================================== 预览


class TestPreviewText:
    def test_includes_prompt_stats_and_examples(self, tmp_path: Path):
        skill = parse_skill(write_skill(tmp_path / "s"))
        text = preview_text({**skill.preview(max_chars=600), "ok": True})
        assert "将注入写作提示词的内容" in text
        assert "tokens" in text
        assert "❌" in text and "✅" in text

    def test_failure_message(self):
        assert "不存在" in preview_text({"ok": False, "message": "技能不存在：x"})

    def test_warnings_section(self, tmp_path: Path):
        skill = parse_skill(write_skill(tmp_path / "s"))
        text = preview_text({**skill.preview(), "ok": True, "warnings": ["测试警告"]})
        assert "解析提示" in text and "测试警告" in text


# ====================================================================== Tk


def _tk_ok() -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _tk_ok(), reason="无显示环境")
class TestPanelBuilds:
    def test_build_and_show_installed_skill(self, tmp_path: Path, monkeypatch):
        import tkinter as tk

        from app import skill_library as sl
        from app.panels.skill_library_panel import SkillLibraryPanel

        library = sl.SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")
        library.install(str(write_skill(tmp_path / "src")))
        monkeypatch.setattr(sl, "_library", library)

        root = tk.Tk()
        root.withdraw()
        try:
            panel = SkillLibraryPanel()
            panel.build(root)
            assert panel.is_built
            assert panel._tree.get_children(), "安装后技能表应有行"
            assert panel._tree.item(panel._tree.get_children()[0], "values")[0] == "demo-tone"

            panel._select("demo-tone")
            detail = panel._detail.get("1.0", tk.END)
            assert "适用场景" in detail and "规则分级" in detail
        finally:
            root.destroy()

    def test_apply_enables_and_previews(self, tmp_path: Path, monkeypatch):
        import tkinter as tk

        from app import skill_library as sl
        from app.panels.skill_library_panel import SkillLibraryPanel

        library = sl.SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")
        library.install(str(write_skill(tmp_path / "src")))
        monkeypatch.setattr(sl, "_library", library)
        captured: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "app.panels.skill_library_panel.dialogs.show_text",
            lambda _parent, title, text, **_kw: captured.append((title, text)),
        )

        root = tk.Tk()
        root.withdraw()
        try:
            panel = SkillLibraryPanel()
            panel.build(root)
            panel._select("demo-tone")
            panel._on_apply()
            # 一键应用 = 启用 + 立刻预览（否则用户不知道应用了什么）
            assert library.get("demo-tone").enabled is True
            assert captured and "注入预览" in captured[0][0]
            assert "将注入写作提示词的内容" in captured[0][1]
        finally:
            root.destroy()

    def test_match_without_text_explains(self, tmp_path: Path, monkeypatch):
        import tkinter as tk

        from app import skill_library as sl
        from app.panels.skill_library_panel import SkillLibraryPanel

        library = sl.SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")
        monkeypatch.setattr(sl, "_library", library)

        root = tk.Tk()
        root.withdraw()
        try:
            panel = SkillLibraryPanel()
            panel.build(root)
            panel._on_match()  # app=None ⇒ 没有正文
            assert "没有可匹配的正文" in panel._effect_line.cget("text")
        finally:
            root.destroy()
