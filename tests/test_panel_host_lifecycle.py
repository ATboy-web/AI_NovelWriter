"""`host` 的宿主生命周期与布局查询（档 3：面板宿主，管着 20 个面板的生死）。

## 为什么挑这些方法

`host` 大部分代码是 Tk 布局，但**下面这些不碰真实 Tk**，而且都是"漏了就有后果"的：

| 方法 | 漏了会怎样 |
|---|---|
| `detach_all` | 退出后进程残留（独立窗口把进程拖在后台） |
| `notify` | 一个面板抛异常，其余面板收不到事件 |
| `_notify_layout_changed` | 布局改了没落盘，下次启动回到旧布局 |
| `built_panels` | 遍历时创建新面板 ⇒ `dict changed size during iteration` |
| `_default_secondary` | 右栏挑不出面板，分栏功能形同虚设 |

用例用假控件顶替 `tk.Frame`（与既有 `test_panel_framework` 同一手法），
所以它们在 `-k "not Tk"` 的 CI 口径下也会跑。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.events import TOPIC_CHAPTER_SAVED
from app.panels import host as host_module
from app.panels import registry
from app.panels.base import BasePanel
from app.panels.host import PanelHost


class FakeWidget:
    """只实现面板框架用到的那几个方法。"""

    def __init__(self, *args, **kwargs):
        self.children: list[Any] = []
        self.destroyed = 0
        self.options = kwargs

    def winfo_children(self):
        return [c for c in self.children if c.destroyed == 0]

    def destroy(self):
        self.destroyed += 1
        self.children.clear()

    def pack(self, **_kw):
        pass

    def pack_forget(self):
        pass

    def grid(self, **_kw):
        pass

    def grid_forget(self):
        pass

    def cget(self, key):
        return "" if key == "bg" else ""

    def configure(self, **_kw):
        pass

    def winfo_width(self):
        return 1


class FakeApp:
    def __init__(self):
        self.ai_client = object()
        self.current_novel_dir = None
        self.event_bus = None


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(host_module.tk, "Frame", lambda *a, **kw: FakeWidget())
    monkeypatch.setattr(host_module.tk, "PanedWindow", lambda *a, **kw: FakeWidget(), raising=False)
    return PanelHost(FakeApp(), FakeWidget())


def _register(cls):
    registry.register(cls)
    return cls


def _drop(key):
    registry.PANEL_REGISTRY.pop(key, None)


class ProbePanel(BasePanel):
    key = "host-probe-a"
    title = "探针甲"
    category = "运维"

    def __init__(self, app=None):
        super().__init__(app)
        self.events: list[str] = []
        self.detached = False

    def build(self, parent):
        self.mark_built()
        return parent

    def on_event(self, topic, payload=None):
        self.events.append(topic)

    def detach(self):
        self.detached = True


class BrokenPanel(ProbePanel):
    key = "host-probe-broken"
    title = "会崩的探针"

    def on_event(self, topic, payload=None):
        raise RuntimeError("这个面板坏了")

    def detach(self):
        raise RuntimeError("detach 也坏了")


@pytest.fixture
def panels():
    _register(ProbePanel)
    _register(BrokenPanel)
    try:
        yield
    finally:
        _drop("host-probe-a")
        _drop("host-probe-broken")


class TestNotify:
    def test_delivers_to_all_panels(self, host, panels):
        host.select("host-probe-a")

        delivered = host.notify(TOPIC_CHAPTER_SAVED, {"chapter": 1})

        assert delivered == 1
        assert host.panel("host-probe-a").events == [TOPIC_CHAPTER_SAVED]

    def test_broken_panel_does_not_block_others(self, host, panels):
        """🔴 一个面板抛异常，其余面板必须照常收到事件。"""
        host.select("host-probe-a")
        host.select("host-probe-broken")

        delivered = host.notify(TOPIC_CHAPTER_SAVED, {})

        assert delivered == 1, "坏面板把整轮投递吃掉了"
        assert host.panel("host-probe-a").events == [TOPIC_CHAPTER_SAVED]

    def test_unknown_topic_is_still_delivered(self, host, panels):
        """`notify` 是直投，不按订阅过滤 —— 过滤是总线的事。"""
        host.select("host-probe-a")

        assert host.notify("完全没订阅的主题", {}) == 1


class TestBuiltPanels:
    def test_returns_copy(self, host, panels):
        host.select("host-probe-a")

        snapshot = host.built_panels()
        snapshot["伪造"] = object()

        assert "伪造" not in host.built_panels(), "返回的是内部字典本身（遍历时会被改）"

    def test_unbuilt_panel_is_none(self, host, panels):
        assert host.panel("host-probe-a") is None


class TestDetachAll:
    def test_clears_subscriptions_and_detaches(self, host, panels):
        host.select("host-probe-a")
        host._subscriptions.append(lambda: None)

        host.detach_all()

        assert host._subscriptions == []
        assert host.panel("host-probe-a").detached is True

    def test_broken_unsubscribe_is_ignored(self, host, panels):
        def boom():
            raise RuntimeError("取消订阅失败")

        host._subscriptions.append(boom)

        host.detach_all()  # 不抛即通过

    def test_broken_panel_detach_is_ignored(self, host, panels):
        """ "收尾阶段不抛异常" —— 退出流程不能因为一个面板炸掉而卡住。"""
        host.select("host-probe-broken")

        host.detach_all()

    def test_popout_windows_are_destroyed(self, host, panels):
        window = FakeWidget()
        host._popouts["host-probe-a"] = window

        host.detach_all()

        assert window.destroyed == 1, "独立窗口没关 —— 进程会被它拖在后台"
        assert host._popouts == {}

    def test_popout_destroy_failure_is_ignored(self, host, panels):
        class BadWindow:
            def destroy(self):
                raise RuntimeError("窗口已死")

        host._popouts["x"] = BadWindow()

        host.detach_all()


class TestLayoutChanged:
    def test_callback_receives_layout(self, host, panels):
        seen: list[dict] = []
        host._on_layout_changed = seen.append

        host._notify_layout_changed()

        assert seen, "布局变化没有回调（下次启动会回到旧布局）"

    def test_callback_failure_is_swallowed(self, host, panels):
        """落盘失败不该影响界面 —— 布局只是偏好。"""

        def boom(_layout):
            raise OSError("磁盘满")

        host._on_layout_changed = boom

        host._notify_layout_changed()  # 不抛即通过

    def test_no_callback_is_safe(self, host, panels):
        host._on_layout_changed = None

        host._notify_layout_changed()


class TestDefaultSecondary:
    def test_returns_empty_with_single_panel(self, host, panels):
        """只有主栏一个面板时不该硬塞一个右栏。"""
        host._layout.primary = "host-probe-a"

        assert isinstance(host._default_secondary(), str)

    def test_skips_primary_and_popouts(self, host, panels):
        host._layout.primary = "host-probe-a"
        host._popouts["host-probe-broken"] = FakeWidget()

        candidate = host._default_secondary()

        assert candidate != "host-probe-a"
        assert candidate != "host-probe-broken"

    def test_prefers_same_category(self, host, panels, monkeypatch):
        """同分组优先 —— 并排看的两个面板通常属于同一类工作。"""
        monkeypatch.setattr(host, "_popouts", {})
        specs = [
            registry.PanelSpec(key="a", title="A", category="运维", order=0, panel_cls=ProbePanel),
            registry.PanelSpec(key="b", title="B", category="写作", order=1, panel_cls=ProbePanel),
            registry.PanelSpec(key="c", title="C", category="运维", order=2, panel_cls=ProbePanel),
        ]
        monkeypatch.setattr(registry, "all_panels", lambda: specs)
        monkeypatch.setattr(registry, "get", lambda key: next((s for s in specs if s.key == key), None))
        host._layout.primary = "a"

        assert host._default_secondary() == "c"


class TestMeasureRatio:
    def test_none_without_paned(self, host):
        host._paned = None

        assert host._measure_ratio() is None

    def test_none_when_width_not_laid_out(self, host):
        class Paned:
            def update_idletasks(self):
                pass

            def winfo_width(self):
                return 1

        host._paned = Paned()

        assert host._measure_ratio() is None

    def test_ratio_clamped(self, host):
        """分隔条位置要夹在 `MIN_RATIO` / `MAX_RATIO` 之间 —— 否则面板会被拖成 0 宽。"""

        class Paned:
            def update_idletasks(self):
                pass

            def winfo_width(self):
                return 100

            def sash_coord(self, _index):
                return (5, 0)

        host._paned = Paned()

        ratio = host._measure_ratio()

        assert ratio is not None
        assert host_module.MIN_RATIO <= ratio <= host_module.MAX_RATIO
