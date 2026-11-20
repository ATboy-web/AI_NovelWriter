# -*- coding: utf-8 -*-
"""theme_switch 换肤逻辑补测（鸭子类型假控件，无需显示器，CI 亦计入覆盖率）。

覆盖 _swap_option / _swap_tags / _swap_canvas_items / _swap_hover_refs 的
命中、未命中、同值跳过与各类 TclError 容错分支，以及 retheme_widgets 的
控件树遍历与 switch_theme 的幂等/正常/无显示容错/非法回落四条路径。
"""

import tkinter as tk

import pytest

from app import theme_switch, theme_system
from app.ui_style import UIStyle

OLD = theme_system.THEMES["cyberpunk"]
NEW = theme_system.THEMES["wasteland"]


@pytest.fixture(autouse=True)
def restore_palette():
    original = UIStyle.ACTIVE_THEME
    yield
    UIStyle.set_palette(original)


class FakeWidget:
    def __init__(self, options=None, children=None, fail_configure=False, fail_children=False):
        self._options = dict(options or {})
        self._children = list(children or [])
        self._fail_configure = fail_configure
        self._fail_children = fail_children
        self.configured = {}

    def cget(self, option):
        if option in self._options:
            return self._options[option]
        raise tk.TclError(f"unknown option {option}")

    def configure(self, **kwargs):
        if self._fail_configure:
            raise tk.TclError("configure boom")
        self._options.update(kwargs)
        self.configured.update(kwargs)

    def winfo_children(self):
        if self._fail_children:
            raise tk.TclError("children boom")
        return self._children


class FakeTagWidget:
    def __init__(self, tags=None, fail_names=False, fail_configure=False):
        self._tags = dict(tags or {})
        self._fail_names = fail_names
        self._fail_configure = fail_configure
        self.configured = []

    def tag_names(self):
        if self._fail_names:
            raise tk.TclError("names boom")
        return tuple(self._tags)

    def tag_cget(self, tag, option):
        return self._tags[tag][option]

    def tag_configure(self, tag, **kwargs):
        if self._fail_configure:
            raise tk.TclError("tag boom")
        self._tags[tag].update(kwargs)
        self.configured.append((tag, kwargs))


class FakeCanvas:
    def __init__(self, items=None, fail_find=False, fail_configure=False):
        self._items = dict(items or {})
        self._fail_find = fail_find
        self._fail_configure = fail_configure
        self.configured = []

    def find_all(self):
        if self._fail_find:
            raise tk.TclError("find boom")
        return tuple(self._items)

    def itemcget(self, item, option):
        return self._items[item].get(option, "")

    def itemconfigure(self, item, **kwargs):
        if self._fail_configure:
            raise tk.TclError("item boom")
        self._items[item].update(kwargs)
        self.configured.append((item, kwargs))


class TestSwapOption:
    def test_hit_recolors(self):
        widget = FakeWidget({"bg": OLD["bg_dark"]})
        assert theme_switch._swap_option(widget, "bg", theme_system.palette_swap_map(OLD, NEW)) is True
        assert widget.configured["bg"] == NEW["bg_dark"]

    def test_miss_untouched(self):
        widget = FakeWidget({"bg": "#123456"})
        assert theme_switch._swap_option(widget, "bg", theme_system.palette_swap_map(OLD, NEW)) is False
        assert widget.configured == {}

    def test_same_value_skipped(self):
        mapping = {OLD["bg_dark"]: OLD["bg_dark"]}
        widget = FakeWidget({"bg": OLD["bg_dark"]})
        assert theme_switch._swap_option(widget, "bg", mapping) is False

    def test_cget_error_returns_false(self):
        widget = FakeWidget({})
        assert theme_switch._swap_option(widget, "fg", theme_system.palette_swap_map(OLD, NEW)) is False

    def test_configure_error_returns_false(self):
        widget = FakeWidget({"bg": OLD["bg_dark"]}, fail_configure=True)
        assert theme_switch._swap_option(widget, "bg", theme_system.palette_swap_map(OLD, NEW)) is False


class TestSwapTags:
    def test_hit_counts_changes(self):
        widget = FakeTagWidget({"zebra": {"foreground": OLD["text_primary"], "background": OLD["bg_card"]}})
        changed = theme_switch._swap_tags(widget, theme_system.palette_swap_map(OLD, NEW))
        assert changed == 2
        assert widget._tags["zebra"]["foreground"] == NEW["text_primary"]

    def test_tag_names_error_returns_zero(self):
        assert theme_switch._swap_tags(FakeTagWidget(fail_names=True), {}) == 0

    def test_tag_cget_error_skipped(self):
        widget = FakeTagWidget({"t": {"foreground": OLD["text_primary"]}})  # 缺 background 键
        changed = theme_switch._swap_tags(widget, theme_system.palette_swap_map(OLD, NEW))
        assert changed == 1

    def test_tag_configure_error_swallowed(self):
        widget = FakeTagWidget({"t": {"foreground": OLD["text_primary"]}}, fail_configure=True)
        assert theme_switch._swap_tags(widget, theme_system.palette_swap_map(OLD, NEW)) == 0


class TestSwapCanvasItems:
    def test_hit_counts_changes(self):
        canvas = FakeCanvas({1: {"fill": OLD["accent"], "outline": OLD["border"]}})
        changed = theme_switch._swap_canvas_items(canvas, theme_system.palette_swap_map(OLD, NEW))
        assert changed == 2
        assert canvas._items[1]["fill"] == NEW["accent"]

    def test_find_all_error_returns_zero(self):
        assert theme_switch._swap_canvas_items(FakeCanvas(fail_find=True), {}) == 0

    def test_empty_current_skipped(self):
        canvas = FakeCanvas({1: {"fill": ""}})
        assert theme_switch._swap_canvas_items(canvas, theme_system.palette_swap_map(OLD, NEW)) == 0

    def test_item_configure_error_swallowed(self):
        canvas = FakeCanvas({1: {"fill": OLD["accent"]}}, fail_configure=True)
        assert theme_switch._swap_canvas_items(canvas, theme_system.palette_swap_map(OLD, NEW)) == 0


class TestSwapHoverRefs:
    def test_string_mapped_callable_preserved(self):
        widget = FakeWidget()
        live = lambda: NEW["bg_hover"]  # noqa: E731
        widget._ui_hover = (OLD["bg_hover"], live)
        theme_switch._swap_hover_refs(widget, theme_system.palette_swap_map(OLD, NEW))
        assert widget._ui_hover[0] == NEW["bg_hover"]
        assert widget._ui_hover[1] is live

    def test_invalid_refs_untouched(self):
        widget = FakeWidget()
        widget._ui_hover = "not-a-tuple"
        theme_switch._swap_hover_refs(widget, {})
        assert widget._ui_hover == "not-a-tuple"

    def test_missing_refs_noop(self):
        widget = FakeWidget()
        theme_switch._swap_hover_refs(widget, {})
        assert not hasattr(widget, "_ui_hover")


class TestRethemeWidgets:
    def test_traversal_and_touched_count(self):
        child = FakeWidget({"bg": OLD["bg_dark"]})
        root = FakeWidget({"bg": OLD["bg_medium"]}, children=[child])
        touched = theme_switch.retheme_widgets(root, OLD, NEW)
        assert touched == 2
        assert root.configured["bg"] == NEW["bg_medium"]
        assert child.configured["bg"] == NEW["bg_dark"]

    def test_children_error_skips_destroyed_widget(self):
        # winfo_children 抛 TclError ⇒ 控件视为已销毁，整体跳过（不改色、不计数）。
        root = FakeWidget({"bg": OLD["bg_dark"]}, fail_children=True)
        assert theme_switch.retheme_widgets(root, OLD, NEW) == 0
        assert root.configured == {}

    def test_no_hit_zero_touched(self):
        root = FakeWidget({"bg": "#ffffff"})
        assert theme_switch.retheme_widgets(root, OLD, NEW) == 0


class FakeConfig:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value


class TestSwitchTheme:
    def test_idempotent_same_theme(self, monkeypatch):
        UIStyle.set_palette("wasteland")

        def _boom(cls, root, theme=None):
            raise AssertionError("幂等路径不应触发 apply_theme")

        monkeypatch.setattr(UIStyle, "apply_theme", classmethod(_boom))
        config = FakeConfig()
        assert theme_switch.switch_theme(FakeWidget(), "wasteland", config) == "wasteland"
        assert config.values["theme"] == "wasteland"

    def test_normal_switch_recolors_and_persists(self, monkeypatch):
        UIStyle.set_palette("cyberpunk")
        monkeypatch.setattr(UIStyle, "apply_theme", classmethod(lambda cls, root, theme=None: None))
        monkeypatch.setattr("app.panels.ui_kit.apply_widget_theme", lambda root: None)
        root = FakeWidget({"bg": OLD["bg_dark"]})
        config = FakeConfig()
        tid = theme_switch.switch_theme(root, "wasteland", config)
        assert tid == "wasteland"
        assert UIStyle.ACTIVE_THEME == "wasteland"
        assert root.configured["bg"] == NEW["bg_dark"]
        assert config.values["theme"] == "wasteland"

    def test_tcl_error_branch_still_persists(self, monkeypatch):
        UIStyle.set_palette("cyberpunk")

        def _raise(cls, root, theme=None):
            raise tk.TclError("no display")

        monkeypatch.setattr(UIStyle, "apply_theme", classmethod(_raise))
        config = FakeConfig()
        tid = theme_switch.switch_theme(FakeWidget(), "mechapunk", config)
        assert tid == "mechapunk"
        assert UIStyle.ACTIVE_THEME == "mechapunk"
        assert config.values["theme"] == "mechapunk"

    def test_invalid_id_falls_back_without_config(self, monkeypatch):
        UIStyle.set_palette("cyberpunk")
        monkeypatch.setattr(UIStyle, "apply_theme", classmethod(lambda cls, root, theme=None: None))
        monkeypatch.setattr("app.panels.ui_kit.apply_widget_theme", lambda root: None)
        tid = theme_switch.switch_theme(FakeWidget(), "light-legacy", None)
        assert tid == theme_system.DEFAULT_THEME
