"""面板基类契约测试（无显示环境可跑）。

## 为什么值得测

`BasePanel` 是全部 20 个面板的地基，其中**代理语义**（`__getattr__` /
`__setattr__`）是 v2 面板"一行不用改"迁移的关键：写入落点若与 v2 不等价，
面板就会静默失灵（构建写进面板、回调读的是应用 —— 控件引用丢失）。
这些行为全部不依赖真 Tk，用鸭子类型假宿主即可钉住。

测试子类的 `key` 留空以避免污染全局注册表；注册路径单独测并在结束时反注册。
"""

from __future__ import annotations

import tkinter as tk  # noqa: F401 - 仅验证模块可导入（import 本身不需要显示）

import pytest

from app.panels import registry
from app.panels.base import BasePanel


class _Host:
    """鸭子类型宿主。"""

    def __init__(self):
        self.x = 1
        self.calls: list = []

    def _load_novel(self, path):
        self.calls.append(("load", str(path)))

    def _log(self, message):
        self.calls.append(("log", message))


class _LocalPanel(BasePanel):
    key = ""  # 空键 → 不进注册表，避免污染


class _ProxyPanel(_LocalPanel):
    proxy_writes = True


@pytest.fixture
def panel():
    return _LocalPanel(_Host())


# ─────────────────────────── 构造与注册 ───────────────────────────


class TestConstruction:
    def test_init_binds_app_and_not_built(self):
        host = _Host()
        p = _LocalPanel(host)
        assert p.__dict__["app"] is host
        assert p.is_built is False

    def test_subclass_with_key_registers(self):
        class _Registered(BasePanel):
            key = "_test_reg_key"
            title = "注册探测"

        try:
            spec = registry.PANEL_REGISTRY.get("_test_reg_key")
            assert spec is not None and spec.panel_cls is _Registered
        finally:
            registry.PANEL_REGISTRY.pop("_test_reg_key", None)

    def test_subclass_without_key_not_registered(self):
        assert registry.PANEL_REGISTRY.get("") is None


# ─────────────────────────── 代理语义（迁移契约） ───────────────────────────


class TestProxySemantics:
    def test_getattr_forwards_to_host(self, panel):
        assert panel.x == 1

    def test_getattr_unbound_host_raises(self):
        p = _LocalPanel(None)
        with pytest.raises(AttributeError, match="未绑定宿主"):
            p.anything

    def test_dunder_not_proxied(self, panel):
        with pytest.raises(AttributeError):
            panel.__wrapped__

    def test_default_setattr_stays_local(self, panel):
        panel.foo = 42
        assert panel.__dict__["foo"] == 42
        assert not hasattr(panel.__dict__["app"], "foo")

    def test_proxy_writes_forwards_to_host(self):
        host = _Host()
        p = _ProxyPanel(host)
        p.current_chapter = 7
        assert host.current_chapter == 7
        assert "current_chapter" not in p.__dict__

    def test_proxy_writes_keeps_local_attrs_local(self):
        host = _Host()
        p = _ProxyPanel(host)
        p.app = "self"
        p.tool_content_frame = "frame"
        assert p.__dict__["app"] == "self"
        assert p.__dict__["tool_content_frame"] == "frame"

    def test_proxy_writes_keeps_private_names_local(self):
        host = _Host()
        p = _ProxyPanel(host)
        p._internal = "secret"
        assert p.__dict__["_internal"] == "secret"
        assert not hasattr(host, "_internal")

    def test_proxy_writes_without_host_falls_back_local(self):
        p = _ProxyPanel(None)
        p.thing = 1
        assert p.__dict__["thing"] == 1

    def test_detach_unbinds_and_calls_on_hide(self):
        seen = []

        class _Panel(_LocalPanel):
            def on_hide(self):
                seen.append("hidden")

        host = _Host()
        p = _Panel(host)
        p.mark_built(True)
        p.detach()
        assert seen == ["hidden"]
        assert p.__dict__["app"] is None
        assert p.is_built is False


# ─────────────────────────── 生命周期与联动 ───────────────────────────


class TestLifecycle:
    def test_build_not_implemented(self, panel):
        with pytest.raises(NotImplementedError):
            panel.build(None)

    def test_on_show_on_hide_on_event_are_noops(self, panel):
        panel.on_show()
        panel.on_hide()
        panel.on_event("any.topic", {"k": 1})

    def test_mark_built_roundtrip(self, panel):
        panel.mark_built(True)
        assert panel.is_built is True
        panel.mark_built(False)
        assert panel.is_built is False


class TestAttachEvents:
    class _Bus:
        def __init__(self):
            self.topics: list[str] = []

        def subscribe(self, topic, handler):
            self.topics.append(topic)
            return lambda: None

    def test_empty_topics_returns_empty(self, panel):
        assert panel.attach_events(self._Bus()) == []

    def test_class_topics_subscribed(self):
        class _Panel(_LocalPanel):
            topics_of_interest = ("a", "b")

        bus = self._Bus()
        handles = _Panel(_Host()).attach_events(bus)
        assert bus.topics == ["a", "b"]
        assert len(handles) == 2

    def test_explicit_topics_override_class(self):
        class _Panel(_LocalPanel):
            topics_of_interest = ("a",)

        bus = self._Bus()
        _Panel(_Host()).attach_events(bus, topics=("x",))
        assert bus.topics == ["x"]

    def test_wildcard_collapses_duplicates(self):
        from app.events import WILDCARD

        class _Panel(_LocalPanel):
            topics_of_interest = (WILDCARD, "a", "b")

        bus = self._Bus()
        _Panel(_Host()).attach_events(bus)
        assert bus.topics == [WILDCARD]


# ─────────────────────────── 宿主协作 ───────────────────────────


class TestOpenNovelDir:
    def test_empty_path_returns_false(self, panel):
        assert panel.open_novel_dir(None) is False
        assert panel.open_novel_dir("") is False

    def test_host_without_loader_returns_false(self):
        class _BareHost:
            pass

        assert _LocalPanel(_BareHost()).open_novel_dir("some/dir") is False

    def test_successful_load_returns_true(self, panel):
        assert panel.open_novel_dir("books/x") is True
        assert panel.__dict__["app"].calls == [("load", "books\\x")] or ("load", "books/x") in panel.__dict__["app"].calls

    def test_loader_error_returns_false(self):
        class _BadHost:
            def _load_novel(self, path):
                raise RuntimeError("boom")

        assert _LocalPanel(_BadHost()).open_novel_dir("x") is False


class _FakeWidget:
    """记录调用序列的假控件。"""

    def __init__(self, ops=None):
        self.ops = ops if ops is not None else []

    def config(self, **kw):
        self.ops.append(("config", kw))

    def delete(self, *a):
        self.ops.append(("delete", a))

    def insert(self, *a):
        self.ops.append(("insert", a))

    def focus_set(self):
        self.ops.append(("focus",))


class TestSetDetail:
    def test_missing_detail_is_noop(self, panel):
        panel._set_detail("text")  # 不抛即通过

    def test_writes_through_disabled_cycle(self, panel):
        ops: list = []
        panel._detail = _FakeWidget(ops)
        panel._set_detail("内容")
        kinds = [op[0] for op in ops]
        assert kinds == ["config", "delete", "insert", "config"]
        assert ops[2] == ("insert", ("1.0", "内容"))
        assert ops[0][1]["state"] == "normal"
        assert ops[3][1]["state"] == "disabled"

    def test_widget_error_swallowed(self, panel):
        class _Boom:
            def config(self, **kw):
                raise tk.TclError("widget destroyed")

        panel._detail = _Boom()
        panel._set_detail("x")  # 不抛即通过


class TestStatusAndFocus:
    def test_set_status_without_bar_is_noop(self, panel):
        panel.set_status("hi")

    def test_set_status_forwards_kind(self, panel):
        got = []

        class _Bar:
            def set(self, text, kind):
                got.append((text, kind))

        panel._status_bar = _Bar()
        panel.set_status("完成", "success")
        assert got == [("完成", "success")]

    def test_focus_search_via_dedicated_entry(self, panel):
        ops: list = []
        panel._toolkit_search_entry = _FakeWidget(ops)
        assert panel.focus_search() is True
        assert ops == [("focus",)]

    def test_focus_search_tcl_error_returns_false(self):
        class _Dead:
            def focus_set(self):
                raise tk.TclError("gone")

        panel = _LocalPanel(_Host())
        panel._toolkit_search_entry = _Dead()
        assert panel.focus_search() is False

    def test_focus_search_without_anything_returns_false(self, panel):
        assert panel.focus_search() is False

    def test_host_widget_prefers_root(self, panel):
        class _WithRoot(_Host):
            root = "ROOT"

        assert _LocalPanel(_WithRoot())._host_widget() == "ROOT"

    def test_host_widget_falls_back_to_frame(self):
        class _WithFrame(_Host):
            tool_content_frame = "FRAME"

        assert _LocalPanel(_WithFrame())._host_widget() == "FRAME"
