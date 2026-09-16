"""面板 UI 质量门禁（v3 §2.5）。

把"界面好不好用"里**可测量**的部分写成断言，避免改一次退一次：

1. **对比度**：所有文字色在深色背景上 ≥4.5:1（改造前 `text_muted` 在卡片上只有 2.68）；
2. **组件**：`ui_kit` 的卡片/工具栏/状态栏/表格/空态能正常构建，且**只使用 4px 刻度**的间距；
3. **迁移润色**：`polish_legacy` 必须给按钮手型光标/点击高度、给输入框聚焦边框 ——
   且**只设控件支持的选项**（ttk 控件没有 `insertbackground`，直接设会抛错）；
4. **面板外壳**：原生面板必须带面包屑 + 刷新按钮 + 状态栏 + F5 快捷键；
5. **表格**：统一 `Panel.Treeview` 样式（28px 行高 + 斑马纹），不再出现 clam 默认灰。

需要 Tk 的用例在没有显示环境时自动跳过（`pytest.importorskip("tkinter")` + 构建失败即 skip）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import _ui_metrics as M  # noqa: E402

from app.ui_style import UIStyle  # noqa: E402

DARK_BACKGROUNDS = ["bg_dark", "bg_medium", "bg_light", "bg_card", "bg_hover"]

#: 可接受的间距取值：4px 刻度 + 1（徽标内衬）+ 0
ALLOWED_PADDING = set(UIStyle.SPACING.values()) | {0, 1}


# ====================================================================== 1. 对比度


class TestPaletteContrast:
    """调色板是所有面板的**共同根因** —— 它不达标，逐面板改也改不好。"""

    def test_every_text_color_passes_on_every_dark_background(self):
        colors = UIStyle.COLORS
        text_keys = [key for key in colors if key.startswith("text") or key.endswith("_text")]
        assert len(text_keys) >= 6, "文字色数量异常，检查 COLORS 是否被误改"
        problems = []
        for key in text_keys:
            for background in DARK_BACKGROUNDS:
                ratio = M.contrast_ratio(colors[key], colors[background])
                if ratio is None:
                    problems.append(f"{key} on {background}: 无法解析颜色")
                elif ratio < 4.5:
                    problems.append(f"{key}({colors[key]}) on {background}({colors[background]}) = {ratio} < 4.5")
        assert problems == [], "文字对比度不达标（会直接表现为'看不清'）：\n  " + "\n  ".join(problems)

    def test_semantic_text_variants_exist_for_each_base_color(self):
        """语义基色是**填充色**，深色背景上的文字必须用 `*_text` 变体。"""
        for name in ("accent", "success", "info", "error", "warning"):
            assert f"{name}_text" in UIStyle.COLORS, f"缺少 {name}_text（基色当文字用会看不清）"

    def test_no_source_uses_a_low_contrast_base_color_as_text(self):
        """源码级：`fg=C["<基色>"]` 在深色背景上不达标，必须用 `*_text`。"""
        colors = UIStyle.COLORS
        offenders = []
        for path in sorted((REPO_ROOT / "app").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                for base in ("accent", "success", "error", "info"):
                    worst = min(M.contrast_ratio(colors[base], colors[bg]) for bg in DARK_BACKGROUNDS)
                    if f'fg=C["{base}"]' in line and worst < 4.5:
                        offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{number} fg=C[{base!r}]")
        assert offenders == [], "这些位置把低对比基色当文字色用了：\n  " + "\n  ".join(offenders)


# ====================================================================== 2. 组件


@pytest.fixture()
def tk_root():
    """一个隐藏的根窗口；没有显示环境时跳过。"""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - 无显示环境
        pytest.skip(f"无可用显示环境：{exc}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


class TestUiKitComponents:
    def test_card_has_border_and_body(self, tk_root):
        from app.panels import ui_kit

        built = ui_kit.card(tk_root, "标题", "副标题")
        assert built["frame"].winfo_class() == "Frame"
        assert int(built["frame"].cget("highlightthickness")) == 1, "卡片必须有 1px 边框（Tk 无圆角，靠边框+留白）"
        # 标题在 body 内的 head 子框架里，所以要**递归**找 Label（直接子控件只有 Frame）
        labels = [w for w in M.walk(built["body"]) if w.winfo_class() == "Label"]
        texts = [str(label.cget("text")) for label in labels]
        assert "标题" in texts, f"卡片带 title 时应渲染标题，实际 {texts}"
        assert "副标题" in texts

    def test_toolbar_splits_left_and_right(self, tk_root):
        from app.panels import ui_kit

        bar = ui_kit.toolbar(tk_root)
        assert bar["left"] is not bar["right"]
        assert bar["bar"].winfo_class() == "Frame"

    def test_status_bar_reports_kinds_without_raising(self, tk_root):
        from app.panels import ui_kit

        status = ui_kit.StatusBar(tk_root)
        for kind in ("info", "ok", "warn", "error"):
            status.set("示例消息", kind)
        status.clear()
        assert status.frame.winfo_class() == "Frame"

    def test_empty_state_explains_next_step(self, tk_root):
        from app.panels import ui_kit

        frame = ui_kit.empty_state(
            tk_root, "暂无内容", "点下面的按钮开始", action_text="开始", action_command=lambda: None
        )
        texts = [str(w.cget("text")) for w in frame.winfo_children() if w.winfo_class() == "Label"]
        assert "暂无内容" in texts
        assert "点下面的按钮开始" in texts

    def test_pretty_tree_is_styled_and_sorted(self, tk_root):
        from tkinter import ttk

        from app.panels import ui_kit

        ui_kit.apply_widget_theme(tk_root)
        built = ui_kit.pretty_tree(tk_root, ("名称", "数量"), (120, 60))
        tree = built["tree"]
        assert str(tree.cget("style")) == "Panel.Treeview"
        assert int(ttk.Style().lookup("Panel.Treeview", "rowheight")) == ui_kit.TREE_ROW_HEIGHT
        assert tree.tag_configure("odd") and tree.tag_configure("even"), "必须有斑马纹标签"

        ui_kit.fill_tree(tree, [("a", ("甲", "3")), ("b", ("乙", "10")), ("c", ("丙", "1"))])
        assert len(tree.get_children("")) == 3
        built["sort_by"]("数量")
        order = [tree.set(item, "数量") for item in tree.get_children("")]
        assert order[0] in ("1", "3"), f"点击表头应按数值排序，实际 {order}"

    def test_scrollable_hides_scrollbar_when_content_fits(self, tk_root):
        from app.panels import ui_kit

        built = ui_kit.scrollable(tk_root)
        assert built["inner"].winfo_class() == "Frame"
        assert built["canvas"].winfo_class() == "Canvas"

    def test_kpi_row_renders_label_and_value(self, tk_root):
        from app.panels import ui_kit

        row = ui_kit.kpi_row(tk_root, [("事件", "12"), ("角色", "3")])
        cells = row.winfo_children()
        assert len(cells) == 2
        texts = [str(label.cget("text")) for cell in cells for label in cell.winfo_children()]
        assert "12" in texts and "事件" in texts

    def test_kit_uses_only_the_spacing_scale(self):
        """组件库自己必须守刻度，否则"统一间距"就成了空话。"""
        source = (REPO_ROOT / "app" / "panels" / "ui_kit.py").read_text(encoding="utf-8")
        found = {int(number) for number in re.findall(r"pad[xy]=(\d+)", source)}
        assert found <= ALLOWED_PADDING, f"ui_kit 里出现了非刻度间距：{sorted(found - ALLOWED_PADDING)}"

    def test_kit_colors_come_from_tokens(self):
        """组件库不得写字面颜色（否则改主题改不动）。"""
        source = (REPO_ROOT / "app" / "panels" / "ui_kit.py").read_text(encoding="utf-8")
        # 允许极少数"基色之外的固定值"（例如 hover 加深），但必须集中在 _KIND_STYLE / 显式常量里
        literals = re.findall(r'"#[0-9a-fA-F]{6}"', source)
        assert len(literals) <= 3, f"ui_kit 里的字面颜色过多：{literals}"


# ====================================================================== 3. 迁移润色


class TestPolishLegacy:
    def test_buttons_get_cursor_hover_and_hit_target(self, tk_root):
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        button = tk.Button(holder, text="运行", bg=UIStyle.COLORS["bg_medium"])
        touched = ui_kit.polish_legacy(holder)
        assert touched >= 1
        assert str(button.cget("cursor")) == "hand2"
        assert int(str(button.cget("pady")).split()[0]) >= ui_kit.SPACE["sm"]
        assert str(button.cget("relief")) == "flat"

    def test_ttk_widgets_are_not_given_unsupported_options(self, tk_root):
        """**回归点**：ttk.Entry / ttk.Combobox 没有 `insertbackground`，
        上一版直接 configure 会抛 `unknown option` 并中断整套润色。"""
        import tkinter as tk
        from tkinter import ttk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        entry = ttk.Entry(holder)
        combo = ttk.Combobox(holder, values=("a", "b"))
        entry.pack()
        combo.pack()
        # 不应抛异常
        ui_kit.polish_legacy(holder)
        assert entry.winfo_exists() and combo.winfo_exists()

    def test_text_and_labelframe_are_styled(self, tk_root):
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        text = tk.Text(holder, height=2)
        frame = tk.LabelFrame(holder, text="分区")
        ui_kit.polish_legacy(holder)
        assert str(text.cget("bg")) == UIStyle.COLORS["bg_card"]
        assert int(str(frame.cget("highlightthickness"))) == 1

    def test_layout_is_not_disturbed(self, tk_root):
        """只改外观：位置参数（pack/pady 的位置信息）不得被改动。"""
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        child = tk.Frame(holder)
        child.pack(side=tk.LEFT, fill=tk.X)
        before = child.pack_info()
        ui_kit.polish_legacy(holder)
        assert child.pack_info() == before


# ====================================================================== 4/5. 面板外壳与表格


class _StubApp:
    """给 `PanelHost` 用的最小宿主：只提供面板构建需要的东西（没有小说 → 空态）。"""

    def __init__(self, root):
        self.root = root
        self.current_novel_dir = None
        self.memory = None
        self.outline = []
        self.panel_host = None
        self.logs: list[str] = []

    def _log(self, message, *_args, **_kwargs):
        self.logs.append(str(message))

    def _load_novel(self, *_args, **_kwargs):
        raise AssertionError("本测试不应触发打开作品")

    def refresh(self):
        return None


def _build_host(root):
    from app.panels import PanelHost, registry

    root.update()
    app = _StubApp(root)
    container = __import__("tkinter").Frame(root)
    selector = __import__("tkinter").Frame(root)
    host = PanelHost(app, container=container, select_var=__import__("tkinter").StringVar(), selector_parent=selector)
    app.panel_host = host
    registry.load_panels()
    return host, app


NATIVE_KEYS = ("timeline", "biography", "lineage")


class TestPanelChrome:
    @pytest.mark.parametrize("key", NATIVE_KEYS)
    def test_native_panel_has_breadcrumb_refresh_and_status(self, tk_root, key):
        host, _app = _build_host(tk_root)
        assert host.select(key) is True, f"{key} 构建失败"
        root = tk_root
        root.update()
        panel = host.panel(key)
        content = getattr(panel, "_chrome_content", None)
        assert content is not None, "面板未套宿主外壳"
        import tkinter as tk

        crumb = content.master.winfo_children()[0]
        texts = [
            str(widget.cget("text"))
            for widget in M.walk(crumb)
            if isinstance(widget, (tk.Label, tk.Button)) and str(widget.cget("text") or "")
        ]
        assert any("刷新" in text for text in texts), f"{key} 缺少刷新入口"
        assert any("世界与世代" in text for text in texts), f"{key} 缺少分组面包屑"
        assert getattr(panel, "_status_bar", None) is not None, f"{key} 缺少状态栏"

    @pytest.mark.parametrize("key", NATIVE_KEYS)
    def test_native_panel_binds_refresh_shortcut(self, tk_root, key):
        host, _app = _build_host(tk_root)
        assert host.select(key) is True
        tk_root.update()
        content = getattr(host.panel(key), "_chrome_content", None)
        bindings = content.bind()
        assert "<F5>" in bindings or "<Key-F5>" in bindings, f"{key} 缺少 F5 刷新绑定"

    @pytest.mark.parametrize("key", NATIVE_KEYS)
    def test_native_panel_tables_use_shared_style(self, tk_root, key):
        from tkinter import ttk

        host, _app = _build_host(tk_root)
        assert host.select(key) is True
        tk_root.update()
        content = getattr(host.panel(key), "_chrome_content", None)
        trees = [w for w in M.walk(content) if isinstance(w, ttk.Treeview)]
        assert trees, f"{key} 没有表格？"
        for tree in trees:
            assert str(tree.cget("style")) == "Panel.Treeview", f"{key} 的表格未套统一风格"
            assert tree.tag_configure("odd") and tree.tag_configure("even"), f"{key} 的表格缺少斑马纹"

    @pytest.mark.parametrize("key", NATIVE_KEYS)
    def test_native_panel_passes_quality_metrics(self, tk_root, key):
        host, _app = _build_host(tk_root)
        assert host.select(key) is True
        tk_root.update()
        content = getattr(host.panel(key), "_chrome_content", None)
        report = M.audit(content, label=key)
        M.assert_quality(report, max_contrast=0, max_small=0, max_fonts=4)

    def test_unknown_panel_key_is_reported(self, tk_root):
        host, _app = _build_host(tk_root)
        assert host.select("definitely-not-a-panel") is False


# ====================================================================== 6. 截图实证的三个回归点


class TestRefreshDoesNotDuplicateChrome:
    """**回归（截图实证）**：`refresh()` 把 `is_built` 置 False 后 `select()` 会在
    **同一个 frame** 里重建外壳。旧实现不销毁旧控件，面包屑/内容区/状态栏就叠两份
    —— 打开/切换小说（`novel.opened` → `host.refresh()`）或按 F5 必现。"""

    def test_refresh_keeps_exactly_one_chrome(self, tk_root):
        host, _app = _build_host(tk_root)
        assert host.select("timeline") is True
        tk_root.update()
        frame = host._frames["timeline"]
        assert len(frame.winfo_children()) == 3, "首次构建：面包屑 + 内容区 + 状态栏"
        host.refresh()
        tk_root.update()
        assert len(frame.winfo_children()) == 3, "refresh 后外壳叠了不止一份"
        host.refresh()
        tk_root.update()
        assert len(frame.winfo_children()) == 3, "连续 refresh 仍应只有一份外壳"

    def test_switch_away_and_back_keeps_single_chrome(self, tk_root):
        host, _app = _build_host(tk_root)
        assert host.select("timeline") is True
        assert host.select("biography") is True
        assert host.select("timeline") is True
        tk_root.update()
        assert len(host._frames["timeline"].winfo_children()) == 3


class TestKpiRowUpdates:
    """**回归（截图实证）**：上一版靠"比对字体"找数值 Label，
    而 `cget("font")` 返回 Tcl 字体名（字符串），与 `UIStyle.font()` 元组**永不相等**
    —— KPI 卡片永远停在占位符"—"。现在由 `kpi_row` 直接交出数值 Label 列表。"""

    def test_kpi_row_exposes_value_labels(self, tk_root):
        from app.panels import ui_kit

        row = ui_kit.kpi_row(tk_root, [("事件", "—"), ("章节", "—")])
        labels = getattr(row, "value_labels", None)
        assert labels is not None and len(labels) == 2, "kpi_row 必须暴露 value_labels"
        labels[0].configure(text="42")
        assert str(row.value_labels[0].cget("text")) == "42"

    def test_timeline_kpi_updates_with_stats(self, tk_root):
        host, _app = _build_host(tk_root)
        assert host.select("timeline") is True
        tk_root.update()
        panel = host.panel("timeline")
        panel._update_kpi({"events": 7, "chapters": 3, "characters": 5, "world_lines": 1, "branch_dirs": 2})
        texts = [str(label.cget("text")) for label in panel._kpi.value_labels]
        assert texts == ["7", "3", "5", "1", "2"], f"KPI 数值未更新：{texts}"


class TestPolishLegacyDarkWidgets:
    """**回归（截图实证）**：v2 面板里不设颜色的 `tk.Listbox` 是暗色主题里的"米色斑"；
    `ttk.Combobox` 不指定 style 则退回 clam 默认浅色。"""

    def test_listbox_is_darkened(self, tk_root):
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        listbox = tk.Listbox(holder)  # v2 面板的典型写法：不设任何颜色
        ui_kit.polish_legacy(holder)
        assert str(listbox.cget("bg")) == UIStyle.COLORS["bg_card"]
        assert str(listbox.cget("fg")) == UIStyle.COLORS["text_primary"]
        assert str(listbox.cget("selectbackground")) == UIStyle.COLORS["accent"]

    def test_combobox_gets_dark_style(self, tk_root):
        import tkinter as tk
        from tkinter import ttk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        combo = ttk.Combobox(holder, values=("a", "b"))
        ui_kit.polish_legacy(holder)
        assert str(combo.cget("style")) == "Dark.TCombobox"

    def test_ttk_widgets_are_not_shadowed_by_tk_branches(self, tk_root):
        """**回归**：`ttk.Combobox` 继承自 `ttk.Entry` → `tk.Entry`，
        若 tk 分支排在 ttk 分支前面，下拉框会被"Entry 分支"截胡，永远轮不到换肤。"""
        import tkinter as tk
        from tkinter import ttk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        entry = ttk.Entry(holder)
        combo = ttk.Combobox(holder, values=("a",))
        tree = ttk.Treeview(holder, columns=("x",), show="headings")
        ui_kit.polish_legacy(holder)
        assert str(entry.cget("style")) == "Panel.TEntry"
        assert str(combo.cget("style")) == "Dark.TCombobox"
        assert str(tree.cget("style")) == "Panel.Treeview"

    def test_unstyled_frame_and_label_are_darkened(self, tk_root):
        """**回归（截图实证）**：v2 面板里没配色的 Frame/Label 是系统默认米色
        （`SystemButtonFace`），在暗色主题里是一条条米色横带/区块。"""
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)  # 自身也是默认色
        strip = tk.Frame(holder)  # 按钮行式的米色横带
        label = tk.Label(strip, text="类别：")
        ui_kit.polish_legacy(holder)
        assert str(strip.cget("bg")) == UIStyle.COLORS["bg_dark"]
        assert str(label.cget("bg")) == UIStyle.COLORS["bg_dark"]
        assert str(label.cget("fg")) == UIStyle.COLORS["text_primary"]

    def test_explicitly_colored_widgets_are_left_alone(self, tk_root):
        """换肤只动"没配色"的控件：显式配色的强调标签/容器不得被覆盖。"""
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root, bg="#123456")
        label = tk.Label(holder, text="成功", bg="#0f6e56", fg="#ffffff")
        half = tk.Label(holder, text="半配色", bg="#123456")  # bg 显式、fg 默认 → 不动
        ui_kit.polish_legacy(holder)
        assert str(holder.cget("bg")) == "#123456"
        assert str(label.cget("bg")) == "#0f6e56"
        assert str(label.cget("fg")) == "#ffffff"
        assert str(half.cget("bg")) == "#123456"

    def test_bare_ttk_widgets_get_dark_styles(self, tk_root):
        """**回归（截图实证）**：v2 面板的 ttk.Frame/Label/Button 不指定 style，
        退回 clam 默认浅色 —— 那就是截图里的一条条米色横带。"""
        import tkinter as tk
        from tkinter import ttk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        frame = ttk.Frame(holder)
        label = ttk.Label(holder, text="类别:")
        button = ttk.Button(holder, text="运行")
        styled = ttk.Button(holder, text="强调", style="Accent.TButton")
        ui_kit.polish_legacy(holder)
        assert str(frame.cget("style")) == "Dark.TFrame"
        assert str(label.cget("style")) == "Dark.TLabel"
        assert str(button.cget("style")) == "Secondary.TButton"
        assert str(styled.cget("style")) == "Accent.TButton", "显式指定的 style 不得被覆盖"

    def test_tk_scrollbar_is_darkened(self, tk_root):
        """ScrolledText 自带的滚动条是经典 tk 控件，默认米色。"""
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        bar = tk.Scrollbar(holder)
        ui_kit.polish_legacy(holder)
        assert str(bar.cget("bg")) == UIStyle.COLORS["bg_medium"]
        assert str(bar.cget("troughcolor")) == UIStyle.COLORS["bg_dark"]

    def test_polish_is_repeatable_after_rebuild(self, tk_root):
        """**回归（截图实证）**：迁移面板 `on_show()` 会重建内容 —— 新控件回到系统
        默认色，宿主会在 `on_show` 后重跑润色。润色必须可重复、且对新建控件生效。"""
        import tkinter as tk

        from app.panels import ui_kit

        holder = tk.Frame(tk_root)
        first = tk.Listbox(holder)
        ui_kit.polish_legacy(holder)
        assert str(first.cget("bg")) == UIStyle.COLORS["bg_card"]
        # 模拟 on_show 重建：旧控件销毁、新控件又是系统默认色
        first.destroy()
        second = tk.Listbox(holder)
        ui_kit.polish_legacy(holder)
        assert str(second.cget("bg")) == UIStyle.COLORS["bg_card"]
