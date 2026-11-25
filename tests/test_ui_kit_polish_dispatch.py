"""`polish_legacy` 的分发表测试（假控件，无需显示环境）。

## 这个文件存在的意义

重构前 `polish_legacy` 是一条 18 路 `isinstance` 链：假控件过不了类型检查，
于是整个 `ui_kit` 只能在有显示环境被覆盖，CI 里必然缺失 —— 这是它长期无法
纳入覆盖率门禁的根因。

改成「`winfo_class()` → 处理函数」表分发后，假控件只需回报类名就能命中任意分支。
本文件因此能**逐条钉住每个分支的外观契约**：选项名、样式名、条件判断、触及计数。

真 Tk 下的端到端验证仍由 `tests/test_panel_ui_quality.py` 承担（两组互补）。
"""

from __future__ import annotations

import tkinter as tk

import pytest

from app.panels import ui_kit

#: 假控件默认"支持一切选项"，除非测试显式收窄
_ALL_OPTIONS = frozenset(
    {
        "style",
        "cursor",
        "relief",
        "bd",
        "font",
        "padx",
        "pady",
        "activebackground",
        "disabledforeground",
        "highlightthickness",
        "highlightbackground",
        "highlightcolor",
        "insertbackground",
        "bg",
        "fg",
        "selectcolor",
        "selectbackground",
        "selectforeground",
        "troughcolor",
        "orient",
    }
)

_SYSTEM_BG = "SystemButtonFace"
_SYSTEM_FG = "SystemWindowText"


class FakeWidget:
    """鸭子类型控件：记录 configure / tag_configure / bind 调用。"""

    def __init__(
        self,
        klass: str,
        *,
        style: str = "",
        orient: str = "vertical",
        bg: str = _SYSTEM_BG,
        fg: str = _SYSTEM_FG,
        padx: object = 0,
        pady: object = 0,
        supported: frozenset[str] | None = None,
        children: list | None = None,
        broken_children: bool = False,
        configure_raises: bool = False,
        class_raises: bool = False,
    ):
        self._klass = klass
        self._values = {"style": style, "orient": orient, "bg": bg, "fg": fg, "padx": padx, "pady": pady}
        self._supported = supported if supported is not None else _ALL_OPTIONS
        self._children = list(children or [])
        self._broken_children = broken_children
        self._configure_raises = configure_raises
        self._class_raises = class_raises
        self.configured: list[dict] = []
        self.tags: list[dict] = []
        self.binds: list[str] = []

    # ---- 控件协议 ----
    def winfo_class(self) -> str:
        if self._class_raises:
            raise tk.TclError("application has been destroyed")
        return self._klass

    def winfo_children(self) -> list:
        if self._broken_children:
            raise tk.TclError("bad window path name")
        return list(self._children)

    def keys(self) -> list[str]:
        return sorted(self._supported)

    def cget(self, option: str):
        return self._values.get(option, "")

    def configure(self, **kwargs):
        if self._configure_raises:
            raise tk.TclError("unknown option")
        self.configured.append(kwargs)

    def tag_configure(self, tag: str, **kwargs):
        self.tags.append({"tag": tag, **kwargs})

    def bind(self, sequence: str, func=None, add=None):
        self.binds.append(sequence)


# ─────────────────────────── ttk 分支 ───────────────────────────


class TestThemedBranches:
    def test_combobox_gets_dark_style(self):
        w = FakeWidget("TCombobox")
        assert ui_kit.polish_legacy(w) == 1
        assert w.configured == [{"style": "Dark.TCombobox"}]

    def test_treeview_style_plus_three_zebra_tags(self):
        w = FakeWidget("Treeview")
        assert ui_kit.polish_legacy(w) == 1
        assert w.configured == [{"style": "Panel.Treeview"}]
        assert [t["tag"] for t in w.tags] == ["odd", "even", "muted"]
        assert all("background" in t for t in w.tags)

    @pytest.mark.parametrize("klass", ["TEntry", "TSpinbox"])
    def test_themed_entry_and_spinbox_share_style(self, klass):
        w = FakeWidget(klass)
        ui_kit.polish_legacy(w)
        assert w.configured == [{"style": "Panel.TEntry"}]

    def test_themed_button_without_style(self):
        w = FakeWidget("TButton")
        ui_kit.polish_legacy(w)
        assert w.configured == [{"style": "Secondary.TButton"}]

    def test_themed_button_explicit_style_untouched(self):
        w = FakeWidget("TButton", style="Accent.TButton")
        assert ui_kit.polish_legacy(w) == 0
        assert w.configured == []

    @pytest.mark.parametrize(
        ("klass", "expected"),
        [
            ("TLabel", "Dark.TLabel"),
            ("TLabelframe", "Card.TLabelframe"),
            ("TCheckbutton", "Dark.TCheckbutton"),
            ("TRadiobutton", "Dark.TRadiobutton"),
            ("TNotebook", "Dark.TNotebook"),
            ("TFrame", "Dark.TFrame"),
        ],
    )
    def test_themed_style_only_when_unset(self, klass, expected):
        w = FakeWidget(klass)
        ui_kit.polish_legacy(w)
        assert w.configured == [{"style": expected}]

    @pytest.mark.parametrize("klass", ["TLabel", "TLabelframe", "TFrame", "TNotebook"])
    def test_themed_explicit_style_skipped(self, klass):
        w = FakeWidget(klass, style="Custom.TStyle")
        assert ui_kit.polish_legacy(w) == 0

    @pytest.mark.parametrize(
        ("orient", "expected"),
        [("vertical", "Dark.Vertical.TScrollbar"), ("horizontal", "Dark.Horizontal.TScrollbar")],
    )
    def test_themed_scrollbar_orientation(self, orient, expected):
        w = FakeWidget("TScrollbar", orient=orient)
        ui_kit.polish_legacy(w)
        assert w.configured == [{"style": expected}]

    def test_themed_scrollbar_style_skipped(self):
        w = FakeWidget("TScrollbar", style="X.TScrollbar")
        assert ui_kit.polish_legacy(w) == 0


# ─────────────────────────── 经典 tk 分支 ───────────────────────────


class TestClassicBranches:
    def test_button_gets_full_treatment_and_hover(self):
        w = FakeWidget("Button", bg="#222222", padx=0, pady=0)
        assert ui_kit.polish_legacy(w) == 1
        opts = w.configured[0]
        assert opts["cursor"] == "hand2"
        assert opts["relief"] == tk.FLAT
        assert opts["highlightthickness"] == 0
        # 点击高度：padx/pady 至少抬到 SPACE 的最小值
        assert opts["padx"] >= ui_kit.SPACE["md"]
        assert opts["pady"] >= ui_kit.SPACE["sm"]
        # 悬停：Enter / Leave 各绑一次
        assert w.binds == ["<Enter>", "<Leave>"]
        assert w._ui_hover[0] == "#222222"

    def test_button_keeps_larger_existing_padding(self):
        w = FakeWidget("Button", padx=40, pady=20)
        ui_kit.polish_legacy(w)
        assert w.configured[0]["padx"] == 40
        assert w.configured[0]["pady"] == 20

    @pytest.mark.parametrize("klass", ["Entry", "Spinbox"])
    def test_classic_entry_gets_focus_border(self, klass):
        w = FakeWidget(klass)
        ui_kit.polish_legacy(w)
        opts = w.configured[0]
        assert opts["highlightthickness"] == 1
        assert "insertbackground" in opts
        assert opts["relief"] == tk.FLAT

    def test_text_gets_card_colors(self):
        w = FakeWidget("Text")
        ui_kit.polish_legacy(w)
        opts = w.configured[0]
        assert opts["bg"] == ui_kit.C["bg_card"]
        assert opts["fg"] == ui_kit.C["text_primary"]

    def test_labelframe_gets_title_color_and_padding(self):
        w = FakeWidget("Labelframe")
        ui_kit.polish_legacy(w)
        opts = w.configured[0]
        assert opts["fg"] == ui_kit.C["text_secondary"]
        assert opts["padx"] == ui_kit.SPACE["md"]

    def test_checkbutton_gets_hand_cursor(self):
        w = FakeWidget("Checkbutton")
        ui_kit.polish_legacy(w)
        assert w.configured[0]["cursor"] == "hand2"

    def test_listbox_gets_selection_colors(self):
        w = FakeWidget("Listbox")
        ui_kit.polish_legacy(w)
        opts = w.configured[0]
        assert opts["selectbackground"] == ui_kit.C["accent"]
        assert opts["bg"] == ui_kit.C["bg_card"]

    def test_classic_scrollbar_gets_trough(self):
        w = FakeWidget("Scrollbar")
        ui_kit.polish_legacy(w)
        assert w.configured[0]["troughcolor"] == ui_kit.C["bg_dark"]

    def test_default_colored_label_is_themed(self):
        w = FakeWidget("Label")
        ui_kit.polish_legacy(w)
        assert w.configured[0]["bg"] == ui_kit.C["bg_dark"]

    def test_explicitly_colored_label_untouched(self):
        w = FakeWidget("Label", bg="#00ff00", fg="#111111")
        assert ui_kit.polish_legacy(w) == 0
        assert w.configured == []

    def test_label_with_only_bg_colored_untouched(self):
        """bg 与 fg **都**是系统色才改；只默认一边也不动。"""
        w = FakeWidget("Label", bg="#00ff00", fg=_SYSTEM_FG)
        assert ui_kit.polish_legacy(w) == 0

    def test_default_colored_frame_is_themed(self):
        w = FakeWidget("Frame")
        ui_kit.polish_legacy(w)
        assert w.configured[0]["bg"] == ui_kit.C["bg_dark"]

    def test_explicitly_colored_frame_untouched(self):
        w = FakeWidget("Frame", bg="#123456")
        assert ui_kit.polish_legacy(w) == 0


# ─────────────────────────── 不支持选项的过滤 ───────────────────────────


class TestUnsupportedOptionFilter:
    def test_only_supported_options_are_applied(self):
        """ttk 控件没有 insertbackground：传了也只应用支持的项，不抛错。"""
        w = FakeWidget("Entry", supported=frozenset({"font", "relief"}))
        ui_kit.polish_legacy(w)
        assert set(w.configured[0]) == {"font", "relief"}

    def test_no_usable_option_returns_zero(self):
        w = FakeWidget("Entry", supported=frozenset({"nothing"}))
        assert ui_kit.polish_legacy(w) == 0
        assert w.configured == []

    def test_configure_tcl_error_swallowed(self):
        w = FakeWidget("Entry", configure_raises=True)
        assert ui_kit.polish_legacy(w) == 0


# ─────────────────────────── 遍历骨架 ───────────────────────────


class TestTraversal:
    def test_none_container_returns_zero(self):
        assert ui_kit.polish_legacy(None) == 0

    def test_nested_tree_counted(self):
        leaf1 = FakeWidget("Button")
        leaf2 = FakeWidget("Entry")
        mid = FakeWidget("Frame", bg="#111111", children=[leaf1, leaf2])
        root = FakeWidget("Frame", bg="#222222", children=[mid])
        assert ui_kit.polish_legacy(root) == 2

    def test_unmatched_class_is_skipped_silently(self):
        canvas = FakeWidget("Canvas")
        assert ui_kit.polish_legacy(canvas) == 0
        assert canvas.configured == []

    def test_max_depth_truncates_descent(self):
        deep = FakeWidget("Button")
        mid = FakeWidget("Frame", bg="#111111", children=[deep])
        root = FakeWidget("Frame", bg="#222222", children=[mid])
        # depth 0 = root，depth 1 = mid，depth 2 = deep；max_depth=1 时 deep 不应被处理
        assert ui_kit.polish_legacy(root, max_depth=1) == 0

    def test_destroyed_children_skipped(self):
        broken = FakeWidget("Frame", broken_children=True)
        assert ui_kit.polish_legacy(broken) == 0

    def test_destroyed_widget_class_is_safe(self):
        w = FakeWidget("Button", class_raises=True)
        assert ui_kit.polish_legacy(w) == 0
