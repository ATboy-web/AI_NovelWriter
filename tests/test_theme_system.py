"""主题系统守卫（v3.4 UI 改版，2026-11-20）。

钉住五件事：
1. **数据完整**：三主题键集一致、hex 合法、别名一致、间距/字阶与桌面令牌同源；
2. **对比度**：每套主题的文字色在全部深色背景上 ≥4.5:1（沿用既有守卫口径），
   白字/金字在主色填充上可读；
3. **换肤行为**：调色板原地更新（别名链不断）、真实控件树即时改色、
   悬停引用/Text tag/Canvas 图元/Toplevel 全覆盖、遗留值回落、幂等；
4. **接线**：启动读配置、设置对话框有选择控件且取消回滚、配置落盘；
5. **跨端单一来源**：ThemeTokens.kt 与 app/theme_system.py 逐值一致，
   移动端令牌是状态驱动 getter（不是静态字面量），设置页有主题入口。
"""

import importlib.util
import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import _tk_harness
import _ui_metrics as M
import pytest

from app import theme_system as ts
from app.design_tokens import DesignTokens
from app.ui_style import UIStyle

REPO = Path(__file__).parent.parent
MOBILE_THEME_DIR = REPO / "mobile-app" / "novel-app" / "app" / "src" / "main" / "java" / "com" / "ainovelwriter"
KT_TOKENS = MOBILE_THEME_DIR / "ui" / "theme" / "ThemeTokens.kt"
KT_THEME = MOBILE_THEME_DIR / "ui" / "theme" / "Theme.kt"

BG_KEYS = ("bg_dark", "bg_medium", "bg_light", "bg_card", "bg_hover", "hover_light")
AA = 4.5  # WCAG AA 正文阈值（与 test_panel_ui_quality 同口径）


@pytest.fixture(autouse=True)
def _restore_default_palette():
    """每个用例后回到默认主题 —— 别的测试文件假设默认调色板。"""
    yield
    UIStyle.set_palette(ts.DEFAULT_THEME)


# ============================================================ 1. 数据完整


class TestDataGuards:
    def test_theme_registries_are_aligned(self):
        assert set(ts.THEMES) == set(ts.THEME_IDS)
        assert set(ts.STYLE_PARAMS) == set(ts.THEME_IDS)
        assert set(ts.THEME_META) == set(ts.THEME_IDS)
        assert ts.DEFAULT_THEME in ts.THEME_IDS

    def test_every_palette_has_exactly_the_ui_style_key_set(self):
        base = set(ts.THEMES[ts.DEFAULT_THEME])
        for tid, pal in ts.THEMES.items():
            assert set(pal) == base, f"{tid} 键集漂移：多 {set(pal) - base}，缺 {base - set(pal)}"

    def test_all_values_are_hex_colors(self):
        for tid, pal in ts.THEMES.items():
            for key, value in pal.items():
                assert isinstance(value, str) and re.fullmatch(r"#[0-9a-f]{6}", value), f"{tid}.{key}={value!r}"

    def test_structural_aliases_hold(self):
        for tid, pal in ts.THEMES.items():
            assert pal["bg_light"] == pal["bg_card"], tid
            assert pal["hover"] == pal["bg_hover"], tid

    def test_background_is_darker_than_text(self):
        # test_ui_style 的既有不变量（字符串序）对每套主题都必须成立
        for tid, pal in ts.THEMES.items():
            assert pal["bg_dark"] < pal["text_primary"], tid

    def test_semantic_fills_are_constant_across_themes(self):
        """设计决策：危险=红/成功=绿的识别不随主题漂移。"""
        keys = ("success", "success_bg", "warning", "warning_bg", "error", "error_bg", "info", "info_bg")
        ref = ts.THEMES[ts.DEFAULT_THEME]
        for tid, pal in ts.THEMES.items():
            for key in keys:
                assert pal[key] == ref[key], f"{tid}.{key} 语义填充色漂移"

    def test_spacing_scale_matches_ui_style(self):
        assert ts.SPACING_SCALE == UIStyle.SPACING

    def test_type_scale_desktop_matches_font_roles(self):
        for role, spec in ts.TYPE_SCALE.items():
            assert role in UIStyle.FONT_ROLES, role
            assert spec["desktop_px"] == UIStyle.FONT_ROLES[role][1], role
            assert spec["mobile_sp"] > 0

    def test_style_params_cover_component_density(self):
        required = {
            "primary_pad",
            "secondary_pad",
            "ghost_pad",
            "tab_pad",
            "entry_pad",
            "borderwidth",
            "tree_row_height",
        }
        for tid, params in ts.STYLE_PARAMS.items():
            assert required <= set(params), tid
            assert params["tree_row_height"] == 28, "行高是既有守卫钉住的值"

    def test_normalize_theme(self):
        for tid in ts.THEME_IDS:
            assert ts.normalize_theme(tid) == tid
        for legacy in ("light", "dark", "", None, 123, "赛博朋克"):
            assert ts.normalize_theme(legacy) == ts.DEFAULT_THEME

    def test_palette_swap_map_is_unambiguous(self):
        for a in ts.THEME_IDS:
            for b in ts.THEME_IDS:
                mapping = ts.palette_swap_map(ts.THEMES[a], ts.THEMES[b])
                # 每个旧值恰好映射到一个新值（别名同值不产生歧义）
                for key, old_value in ts.THEMES[a].items():
                    assert mapping[old_value.lower()] == ts.THEMES[b][key]


# ============================================================ 2. 对比度


class TestContrastPerTheme:
    @pytest.mark.parametrize("tid", ts.THEME_IDS)
    def test_text_colors_readable_on_every_background(self, tid):
        pal = ts.THEMES[tid]
        backgrounds = [pal[k] for k in BG_KEYS]
        text_keys = [k for k in pal if k.startswith("text") or k.endswith("_text")]
        bad = []
        for key in text_keys:
            worst = min(M.contrast_ratio(pal[key], bg) for bg in backgrounds)
            if worst < AA:
                bad.append(f"{key} worst={worst:.2f}")
        assert not bad, f"{tid}: {bad}"

    @pytest.mark.parametrize("tid", ts.THEME_IDS)
    def test_white_and_gold_readable_on_accent_fill(self, tid):
        # 白字：主按钮/选中页签；金字：shell_ui 的"未配置"徽标（#ffd700）
        accent = ts.THEMES[tid]["accent"]
        assert M.contrast_ratio("#ffffff", accent) >= AA, tid
        assert M.contrast_ratio("#ffd700", accent) >= AA, tid

    @pytest.mark.parametrize("tid", ts.THEME_IDS)
    def test_warning_text_variant_readable(self, tid):
        # v3.4.1：warning 填充色专用于白字按钮；深底文字一律走 warning_text 变体
        pal = ts.THEMES[tid]
        worst = min(M.contrast_ratio(pal["warning_text"], pal[k]) for k in BG_KEYS)
        assert worst >= AA, tid


class TestSemanticFillContrast:
    """v3.4.1 R2：语义填充色（含 hover/pressed）上的白字必须全部 ≥4.5:1。

    历史教训：#f59e0b/#ef4444/#3b82f6 本是深底文字色，被复用为按钮填充后
    白字只剩 2.15/3.76/3.68。填充色与文字色必须分离，且不得回退。
    """

    FILL_KEYS = ("success", "warning", "error", "info")

    def test_white_on_every_fill_meets_aa(self):
        for key in self.FILL_KEYS:
            fill = ts.THEMES[ts.DEFAULT_THEME][key]
            ratio = M.contrast_ratio("#ffffff", fill)
            assert ratio >= AA, f"{key}={fill} white={ratio:.2f}"

    def test_states_white_meets_aa_and_darken(self):
        for key, states in ts.SEMANTIC_STATES.items():
            base = ts.THEMES[ts.DEFAULT_THEME][key]
            ladder = [base, states["active"], states["pressed"]]
            for color in ladder:
                assert M.contrast_ratio("#ffffff", color) >= AA, f"{key} {color}"
            # 对纯黑对比度随明度单调增 ⇒ 用它断言「悬停/按下逐级加深」
            blacks = [M.contrast_ratio(c, "#000000") for c in ladder]
            assert blacks[0] > blacks[1] > blacks[2], f"{key} ladder={blacks}"

    def test_fills_and_states_do_not_alias_palette_keys(self):
        # 填充/状态色不得等于其它主题键的值，防止热切换按值映射时误伤
        fills = {ts.THEMES[ts.DEFAULT_THEME][k].lower() for k in self.FILL_KEYS}
        states = {c.lower() for st in ts.SEMANTIC_STATES.values() for c in st.values()}
        for tid in ts.THEME_IDS:
            for key, value in ts.THEMES[tid].items():
                if key in self.FILL_KEYS:
                    continue
                assert value.lower() not in fills | states, f"{tid}.{key}={value}"

    def test_mobile_warning_maps_to_text_variant(self):
        # 移动端 Warning 令牌唯一用途是深底图标着色 ⇒ 必须映射亮色文字变体
        assert ts.MOBILE_TOKEN_MAP["Warning"] == "warning_text"

    def test_default_colors_single_source(self):
        for key in self.FILL_KEYS:
            assert UIStyle.COLORS[key] == ts.THEMES[ts.DEFAULT_THEME][key]


# ============================================================ 3. 激活与换肤行为


class TestActivation:
    def test_set_palette_mutates_in_place(self):
        """字典对象同一性必须保持 —— 全仓 C = UIStyle.COLORS 别名依赖它。"""
        alias = UIStyle.COLORS
        for tid in ts.THEME_IDS:
            UIStyle.set_palette(tid)
            assert UIStyle.COLORS is alias
            assert alias["accent"] == ts.THEMES[tid]["accent"]
            assert UIStyle.ACTIVE_THEME == tid

    def test_design_tokens_refresh_propagates(self):
        for tid in ts.THEME_IDS:
            UIStyle.set_palette(tid)
            assert DesignTokens.COLORS["primary"] == UIStyle.COLORS["accent"]
            assert DesignTokens.BUTTON_PRIMARY["bg"] == UIStyle.COLORS["accent"]
            assert DesignTokens.BUTTON_SECONDARY["bg"] == UIStyle.COLORS["hover_light"]
            assert DesignTokens.CARD["bg"] == UIStyle.COLORS["bg_card"]

    def test_legacy_value_falls_back(self):
        assert UIStyle.set_palette("light") == ts.DEFAULT_THEME


@pytest.mark.skipif(not _tk_harness.tk_available(), reason="无可用 Tk 显示环境（Linux 无头 CI）")
class TestSwitchTk:
    """真实控件树换肤（类名含 Tk：CI 的 -k 'not Tk' 会剔除，本地全量跑）。"""

    @pytest.fixture
    def root(self):
        root = _tk_harness.create_root()  # 单一入口：重试 + 留痕，返回已 withdraw 的根
        yield root
        root.destroy()

    def _build_tree(self, root):
        from app.panels import ui_kit

        C = UIStyle.COLORS
        widgets = {}
        widgets["label"] = tk.Label(root, text="标题", bg=C["bg_dark"], fg=C["text_primary"])
        widgets["label"].pack()
        widgets["btn"] = ui_kit.button(root, "主操作", kind="primary")
        widgets["btn"].pack()
        legacy = tk.Button(root, text="旧按钮", bg=C["bg_medium"], fg=C["text_primary"])
        legacy.pack()
        ui_kit.add_hover(legacy, C["bg_medium"], C["hover"])
        widgets["legacy"] = legacy
        text = tk.Text(root, bg=C["bg_card"], fg=C["text_primary"])
        text.tag_configure("hl", foreground=C["accent_text"], background=C["bg_medium"])
        text.pack()
        widgets["text"] = text
        canvas = tk.Canvas(root, bg=C["bg_dark"], highlightthickness=0)
        widgets["item"] = canvas.create_rectangle(0, 0, 10, 10, fill=C["accent"], outline=C["border"])
        canvas.pack()
        widgets["canvas"] = canvas
        widgets["listbox"] = tk.Listbox(root, bg=C["bg_card"], selectbackground=C["accent"])
        widgets["listbox"].pack()
        top = tk.Toplevel(root)
        top.withdraw()
        widgets["top_label"] = tk.Label(top, text="弹窗", bg=C["bg_card"], fg=C["text_secondary"])
        widgets["top_label"].pack()
        widgets["ttk_btn"] = ttk.Button(root, text="ttk", style="Accent.TButton")
        widgets["ttk_btn"].pack()
        root.update_idletasks()
        return widgets

    def test_switch_recolors_whole_tree(self, root):
        from app.theme_switch import switch_theme

        UIStyle.apply_theme(root, theme="cyberpunk")
        w = self._build_tree(root)
        assert switch_theme(root, "wasteland") == "wasteland"
        pal = ts.THEMES["wasteland"]
        assert str(w["label"].cget("bg")).lower() == pal["bg_dark"]
        assert str(w["label"].cget("fg")).lower() == pal["text_primary"]
        assert str(w["btn"].cget("bg")).lower() == pal["accent"]
        assert str(w["legacy"].cget("bg")).lower() == pal["bg_medium"]
        assert w["legacy"]._ui_hover == (pal["bg_medium"], pal["hover"])
        assert str(w["text"].cget("bg")).lower() == pal["bg_card"]
        assert str(w["text"].tag_cget("hl", "foreground")).lower() == pal["accent_text"]
        assert str(w["canvas"].itemcget(w["item"], "fill")).lower() == pal["accent"]
        assert str(w["canvas"].itemcget(w["item"], "outline")).lower() == pal["border"]
        assert str(w["listbox"].cget("selectbackground")).lower() == pal["accent"]
        assert str(w["top_label"].cget("bg")).lower() == pal["bg_card"], "Toplevel 必须一起换"
        style = ttk.Style()
        assert str(style.lookup("Accent.TButton", "background")).lower() == pal["accent"]

    def test_roundtrip_and_idempotent(self, root):
        from app.theme_switch import switch_theme

        UIStyle.apply_theme(root, theme="cyberpunk")
        w = self._build_tree(root)
        for tid in ("wasteland", "mechapunk", "cyberpunk"):
            switch_theme(root, tid)
            assert str(w["label"].cget("bg")).lower() == ts.THEMES[tid]["bg_dark"]
        switch_theme(root, "cyberpunk")  # 幂等
        assert UIStyle.ACTIVE_THEME == "cyberpunk"

    def test_switch_persists_to_config(self, root, tmp_path, monkeypatch):
        from app.config import AppConfig
        from app.theme_switch import switch_theme

        UIStyle.apply_theme(root, theme="cyberpunk")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        config = AppConfig()
        switch_theme(root, "mechapunk", config=config)
        assert config.get("theme") == "mechapunk"
        # 预览（不传 config）不落盘
        switch_theme(root, "wasteland")
        assert config.get("theme") == "mechapunk"


# ============================================================ 4. 接线守卫


class TestWiringGuards:
    def test_startup_reads_theme_from_config(self):
        source = (REPO / "novel_app.py").read_text(encoding="utf-8")
        assert 'UIStyle.apply_theme(self.root, theme=self.config.get("theme"' in source

    def test_settings_dialog_has_theme_picker_with_rollback(self):
        source = (REPO / "app" / "lifecycle_ui.py").read_text(encoding="utf-8")
        assert "theme_combo" in source, "设置对话框缺主题选择控件"
        assert "switch_theme(self.root, tid)" in source, "选择后应即时预览"
        assert "revert_theme" in source, "取消/关窗必须回滚预览"
        assert 'self.config.set("theme"' in source, "保存时必须落盘"
        assert 'dialog.protocol("WM_DELETE_WINDOW", cancel_settings)' in source

    def test_config_default_theme_is_valid(self):
        from app.config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG["theme"] in ts.THEME_IDS

    def test_hover_uses_live_refs(self):
        source = (REPO / "app" / "panels" / "ui_kit.py").read_text(encoding="utf-8")
        assert "_ui_hover" in source
        assert "_kind_style(kind)" in source, "按钮配色必须是活引用而非常量快照"


# ============================================================ 5. 跨端单一来源


class TestCrossPlatformSync:
    def test_generated_tokens_match_python_authority(self):
        content = KT_TOKENS.read_text(encoding="utf-8")
        assert "DO NOT EDIT" in content
        for tid in ts.THEME_IDS:
            block = re.search(rf'"{tid}" to mapOf\((.*?)\n        \),', content, re.S)
            assert block, f"ThemeTokens.kt 缺主题 {tid}"
            pairs = dict(re.findall(r'"(\w+)" to (0x[0-9A-F]+L)', block.group(1)))
            for name, key in ts.MOBILE_TOKEN_MAP.items():
                expected = "0xFF" + ts.THEMES[tid][key].lstrip("#").upper() + "L"
                assert pairs.get(name) == expected, f"{tid}.{name}: {pairs.get(name)} != {expected}"

    def test_meta_and_scales_match(self):
        content = KT_TOKENS.read_text(encoding="utf-8")
        assert f'const val DEFAULT_THEME = "{ts.DEFAULT_THEME}"' in content
        for tid in ts.THEME_IDS:
            assert f'"{tid}" to "{ts.THEME_META[tid]["name_cn"]}"' in content
        for key, value in ts.SPACING_SCALE.items():
            assert f'"{key}" to {value},' in content
        for role, spec in ts.TYPE_SCALE.items():
            assert f'"{role}" to {spec["mobile_sp"]},' in content

    def test_regeneration_is_idempotent(self):
        spec = importlib.util.spec_from_file_location("sync_theme_tokens", REPO / "scripts" / "sync_theme_tokens.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.build() == KT_TOKENS.read_text(encoding="utf-8"), (
            "生成物与权威漂移：请运行 scripts/sync_theme_tokens.py"
        )

    def test_mobile_tokens_are_state_driven_getters(self):
        content = KT_THEME.read_text(encoding="utf-8")
        for name in ("Surface1", "Text1", "Primary500"):
            assert f"val {name}: Color get() = token(" in content, f"{name} 必须是状态驱动 getter"
            assert f"val {name} = Color(0x" not in content, f"{name} 不得是静态字面量"
        assert "fun applyThemeTokens(" in content
        assert "fun AINovelWriterTheme(themeId: String" in content

    def test_mobile_theme_wiring(self):
        repo_kt = (MOBILE_THEME_DIR / "data" / "SettingsRepository.kt").read_text(encoding="utf-8")
        assert 'stringPreferencesKey("theme")' in repo_kt
        assert "suspend fun saveTheme(" in repo_kt
        vm = (MOBILE_THEME_DIR / "viewmodel" / "MainViewModel.kt").read_text(encoding="utf-8")
        assert "val themeId: String" in vm
        assert "fun setTheme(" in vm
        settings = (MOBILE_THEME_DIR / "ui" / "screen" / "SettingsScreen.kt").read_text(encoding="utf-8")
        assert "界面主题" in settings
        assert "viewModel.setTheme(tid)" in settings
        main = (MOBILE_THEME_DIR / "MainActivity.kt").read_text(encoding="utf-8")
        assert "AINovelWriterTheme(themeId = state.themeId)" in main


# ============================================================ 6. 换肤遍历逻辑（无 Tk 依赖，CI 可跑）


class _FakeWidget:
    """鸭子类型替身：只实现遍历用到的 cget/configure/tag/children 接口。"""

    def __init__(self, children=(), **options):
        self._options = dict(options)
        self._tags = {}
        self._children = list(children)

    def winfo_children(self):
        return self._children

    def cget(self, option):
        if option not in self._options:
            raise tk.TclError(f"unknown option {option}")
        return self._options[option]

    def configure(self, **kw):
        self._options.update(kw)

    def tag_names(self):
        return list(self._tags)

    def tag_cget(self, tag, option):
        return self._tags.get(tag, {}).get(option, "")

    def tag_configure(self, tag, **kw):
        self._tags.setdefault(tag, {}).update(kw)


class TestRethemeLogic:
    """theme_switch 的映射/遍历逻辑不依赖显示环境 —— 用替身钉住行为。"""

    def test_swap_option_hits_and_misses(self):
        from app.theme_switch import _swap_option

        old, new = ts.THEMES["cyberpunk"], ts.THEMES["wasteland"]
        mapping = ts.palette_swap_map(old, new)
        widget = _FakeWidget(bg=old["bg_dark"], fg="#ffd700")
        assert _swap_option(widget, "bg", mapping) is True
        assert widget.cget("bg") == new["bg_dark"]
        # 语义常量不命中
        assert _swap_option(widget, "fg", mapping) is False
        assert widget.cget("fg") == "#ffd700"
        # 不存在的选项不抛异常
        assert _swap_option(widget, "troughcolor", mapping) is False

    def test_swap_tags(self):
        from app.theme_switch import _swap_tags

        old, new = ts.THEMES["cyberpunk"], ts.THEMES["mechapunk"]
        mapping = ts.palette_swap_map(old, new)
        widget = _FakeWidget()
        widget.tag_configure("odd", background=old["bg_card"])
        widget.tag_configure("hl", foreground=old["accent_text"])
        changed = _swap_tags(widget, mapping)
        assert changed == 2
        assert widget.tag_cget("odd", "background") == new["bg_card"]
        assert widget.tag_cget("hl", "foreground") == new["accent_text"]

    def test_swap_hover_refs_strings_and_callables(self):
        from app.theme_switch import _swap_hover_refs

        old, new = ts.THEMES["wasteland"], ts.THEMES["cyberpunk"]
        mapping = ts.palette_swap_map(old, new)
        widget = _FakeWidget()
        live = lambda: ts.THEMES[ts.DEFAULT_THEME]["hover"]  # noqa: E731
        widget._ui_hover = (old["bg_medium"], live)
        _swap_hover_refs(widget, mapping)
        assert widget._ui_hover[0] == new["bg_medium"]
        assert widget._ui_hover[1] is live, "callable 活引用不得被替换"

    def test_retheme_walks_children(self):
        from app.theme_switch import retheme_widgets

        old, new = ts.THEMES["cyberpunk"], ts.THEMES["wasteland"]
        child = _FakeWidget(bg=old["bg_card"], fg=old["text_primary"])
        root = _FakeWidget(children=[child], bg=old["bg_dark"])
        touched = retheme_widgets(root, old, new)
        assert touched == 2
        assert root.cget("bg") == new["bg_dark"]
        assert child.cget("bg") == new["bg_card"]
        assert child.cget("fg") == new["text_primary"]
