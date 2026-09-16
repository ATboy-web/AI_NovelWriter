"""面板"脱离为独立窗口"（P5 收尾项）。

## 为什么这件事需要测试而不是靠手点

Tk 的控件**不能改父**（没有 reparent），所以"面板换个容器"只能是
「销毁 + 重建」。这条路有三个容易悄悄坏掉的点，肉眼都看不出来：

1. **同一面板活在两个容器里**：忘了销毁旧控件，于是两份控件同时存在，
   回调写进 A、界面读的是 B —— 表现为"点了没反应/数据不刷新"；
2. **刷新把面板拽回宿主区**：`refresh()` 若只认 `_frames`，那么在窗口里按 F5
   会把面板搬回主界面（用户视角是"窗口突然空了"）；
3. **退出后进程不退出**：独立顶层窗口不随主窗口销毁，`detach_all()` 漏关
   就会留下一个空窗口与一个不结束的进程。

这三条都在下面有对应用例。需要 Tk；无显示环境时自动跳过。

## 探针面板为什么在**夹具里动态创建**

`BasePanel.__init_subclass__` 在**类定义时**就登记进全局注册表，而测试模块的
导入发生在**收集阶段**（早于任何用例）。模块级定义探针类 ⇒ 整个会话里注册表
都多了一个面板，会污染其他文件里"面板数量/分组"类的断言。放进夹具里创建、
结束时 `pop()` 掉，污染窗口就只有用例自身。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.panels import registry  # noqa: E402
from app.panels.base import BasePanel  # noqa: E402

PROBE_A = "_test_popout_a"
PROBE_B = "_test_popout_b"
PROBE_KEYS = (PROBE_A, PROBE_B)


class _FakeApp:
    """宿主替身：面板只经 `__getattr__` 从这里取共享状态。"""

    def __init__(self) -> None:
        self.event_bus = None
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)


def _make_probe(key: str, title: str) -> type:
    """造一个最小可用面板：每次 `build()` 记一次数，并放三个可识别的 Label。"""

    def build(self: Any, parent: Any) -> Any:
        import tkinter as tk

        self.build_count = int(self.__dict__.get("build_count", 0)) + 1
        for index in range(3):
            tk.Label(parent, text=f"行 {index}").pack()
        self.mark_built(True)
        return parent

    return type(
        "ProbePanel",
        (BasePanel,),
        {"key": key, "title": title, "category": "运维", "order": 9001, "build": build},
    )


# ---------------------------------------------------------------------- 工具


def _walk(widget: Any) -> list[Any]:
    """深度遍历控件树（含 Toplevel 子节点）。"""
    found = [widget]
    for child in widget.winfo_children():
        found.extend(_walk(child))
    return found


def _texts(widget: Any, kind: str) -> list[str]:
    """子树里指定类的 `text` 选项取值。"""
    out = []
    for item in _walk(widget):
        try:
            if item.winfo_class() == kind:
                out.append(str(item.cget("text")))
        except Exception:  # noqa: BLE001 - 个别控件无 text 选项
            continue
    return out


def _window(built: Any, key: str):
    return built._popouts[key]


def _teardown(built: Any) -> None:
    for key in list(getattr(built, "_popouts", {})):
        try:
            built._popouts[key].destroy()
        except Exception:  # noqa: BLE001
            pass
    built._popouts.clear()
    for key in PROBE_KEYS:
        registry.PANEL_REGISTRY.pop(key, None)


@pytest.fixture()
def tk_root():
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


@pytest.fixture()
def host(tk_root):
    """真实 Tk 容器上的宿主，探针面板 A 已选中。"""
    import tkinter as tk

    from app.panels.host import PanelHost

    _make_probe(PROBE_A, "探针甲")
    _make_probe(PROBE_B, "探针乙")
    container = tk.Frame(tk_root)
    container.pack(fill=tk.BOTH, expand=True)
    built = PanelHost(_FakeApp(), container, bus=None)
    assert built.select(PROBE_A) is True
    yield built
    _teardown(built)


def _panel(built: Any, key: str = PROBE_A) -> Any:
    panel = built.panel(key)
    assert panel is not None
    return panel


# ====================================================================== 外壳入口


class TestChromeOffersTheToggle:
    def test_host_chrome_has_a_popout_button(self, host):
        texts = _texts(host.container, "Button")
        assert "独立窗口" in texts, f"宿主区外壳缺少独立窗口入口，实际按钮：{texts}"

    def test_window_chrome_swaps_button_to_pop_in(self, host):
        host.pop_out(PROBE_A)
        texts = _texts(_window(host, PROBE_A), "Button")
        assert "收回面板" in texts, f"独立窗口里应提供收回入口，实际按钮：{texts}"
        assert "独立窗口" not in texts, "窗口里不该再出现'独立窗口'（会自我嵌套）"

    def test_window_carries_panel_title(self, host):
        host.pop_out(PROBE_A)
        assert "探针甲" in str(_window(host, PROBE_A).title())


# ====================================================================== 基本往返


class TestPopOutAndBack:
    def test_pop_out_returns_true_and_marks_state(self, host):
        assert host.pop_out(PROBE_A) is True
        assert host.is_popped_out(PROBE_A) is True
        assert host.popped_out_keys() == (PROBE_A,)

    def test_panel_is_built_in_the_window(self, host):
        host.pop_out(PROBE_A)
        assert _panel(host).is_built is True
        assert _texts(_window(host, PROBE_A), "Label").count("行 1") == 1

    def test_panel_lives_in_exactly_one_container(self, host):
        """**核心不变量**：旧容器必须被清空，否则两份控件争同一份状态。"""
        host.pop_out(PROBE_A)
        assert _texts(host._frames[PROBE_A], "Label").count("行 1") == 0, "宿主区仍有面板内容 ⇒ 出现两份控件"
        assert _texts(_window(host, PROBE_A), "Label").count("行 1") == 1

    def test_host_area_shows_a_notice_instead_of_the_panel(self, host):
        host.pop_out(PROBE_A)
        host_frame = host._frames[PROBE_A]
        labels = " ".join(_texts(host_frame, "Label"))
        assert "独立窗口" in labels, f"宿主区应说明面板去哪了，实际文字：{labels!r}"
        assert "收回面板" in _texts(host_frame, "Button")

    def test_pop_in_returns_panel_to_host(self, host):
        host.pop_out(PROBE_A)
        assert host.pop_in(PROBE_A) is True
        assert host.is_popped_out(PROBE_A) is False
        host_frame = host._frames[PROBE_A]
        assert _texts(host_frame, "Label").count("行 1") == 1
        assert "独立窗口" not in " ".join(_texts(host_frame, "Label")), "收回后占位说明应消失"

    def test_pop_in_without_popout_is_a_no_op(self, host):
        assert host.pop_in(PROBE_A) is False

    def test_toggle_flips_both_ways(self, host):
        assert host.toggle_pop_out(PROBE_A) is True
        assert host.is_popped_out(PROBE_A) is True
        assert host.toggle_pop_out(PROBE_A) is True
        assert host.is_popped_out(PROBE_A) is False

    def test_closing_the_window_pops_the_panel_back_in(self, host):
        """关窗等于收回：否则会留下"窗口没了、宿主还显示占位"的错觉状态。

        `protocol("WM_DELETE_WINDOW")` 取回的是 **Tcl 命令名**（不是 Python 可调用
        对象），要用 `tk.call()` 触发 —— 直接 `()` 调用会 `TypeError`。
        """
        host.pop_out(PROBE_A)
        window = _window(host, PROBE_A)
        command = window.protocol("WM_DELETE_WINDOW")
        assert command, "独立窗口必须注册 WM_DELETE_WINDOW（关窗要把面板收回宿主区）"
        window.tk.call(command)
        assert host.is_popped_out(PROBE_A) is False
        assert _texts(host._frames[PROBE_A], "Label").count("行 1") == 1


# ====================================================================== 刷新语义


class TestRefreshStaysPut:
    def test_refresh_rebuilds_inside_the_window(self, host):
        """**回归**：刷新不能把面板搬回宿主区（用户视角是"窗口突然空了"）。"""
        host.pop_out(PROBE_A)
        before = _panel(host).build_count
        assert host.refresh() is True
        assert host.is_popped_out(PROBE_A) is True
        assert _panel(host).build_count == before + 1
        assert _texts(_window(host, PROBE_A), "Label").count("行 1") == 1
        assert _texts(host._frames[PROBE_A], "Label").count("行 1") == 0

    def test_select_of_popped_out_panel_does_not_rebuild(self, host):
        host.pop_out(PROBE_A)
        before = _panel(host).build_count
        assert host.select(PROBE_A) is True
        assert host.current_key == PROBE_A
        assert _panel(host).build_count == before, "已脱出的面板不该在宿主区被重建"
        assert _texts(host._frames[PROBE_A], "Button").count("收回面板") == 1

    def test_switching_away_and_back_keeps_the_window(self, host):
        """切到别的面板再切回来：独立窗口应当仍在，而不是被收回。"""
        host.pop_out(PROBE_A)
        assert host.select(PROBE_B) is True
        assert host.is_popped_out(PROBE_A) is True
        assert host.select(PROBE_A) is True
        assert host.is_popped_out(PROBE_A) is True


# ====================================================================== 多窗口与换书


class TestMultipleWindowsAndNovelSwitch:
    def test_two_panels_of_one_host_can_be_out_together(self, host):
        host.pop_out(PROBE_A)
        assert host.select(PROBE_B) is True
        assert host.pop_out(PROBE_B) is True
        assert set(host.popped_out_keys()) == {PROBE_A, PROBE_B}
        for key in PROBE_KEYS:
            assert _texts(_window(host, key), "Label").count("行 1") == 1

    def test_novel_opened_rebuilds_popped_out_panels(self, tk_root):
        """换书后独立窗口里的面板同样过期 —— 它们不走 `select()`，必须单独重建。"""
        import tkinter as tk

        from app.events import TOPIC_NOVEL_OPENED, EventBus
        from app.panels.host import PanelHost

        _make_probe(PROBE_A, "探针甲")
        _make_probe(PROBE_B, "探针乙")
        container = tk.Frame(tk_root)
        container.pack()
        app = _FakeApp()
        bus = EventBus()
        app.event_bus = bus
        built = PanelHost(app, container, bus=bus)
        try:
            assert built.select(PROBE_A) is True
            built.pop_out(PROBE_A)
            assert built.select(PROBE_B) is True  # 非当前面板也脱出
            built.pop_out(PROBE_B)
            before_a = _panel(built, PROBE_A).build_count
            before_b = _panel(built, PROBE_B).build_count
            bus.publish(TOPIC_NOVEL_OPENED, {"novel_dir": "x"})
            assert _panel(built, PROBE_A).build_count == before_a + 1, "当前面板(已脱出)换书后没重建"
            assert _panel(built, PROBE_B).build_count == before_b + 1, "非当前面板(已脱出)换书后没重建"
            assert set(built.popped_out_keys()) == {PROBE_A, PROBE_B}, "换书不应把面板收回宿主区"
        finally:
            _teardown(built)

    def test_detach_all_closes_windows(self, host):
        """退出时必须关掉：独立顶层窗口不会随主窗口销毁，留着进程不结束。"""
        import tkinter as tk

        host.pop_out(PROBE_A)
        window = _window(host, PROBE_A)
        host.detach_all()
        assert host.popped_out_keys() == ()
        destroyed = False
        try:
            window.winfo_children()
        except tk.TclError:
            destroyed = True
        assert destroyed, "detach_all 没有销毁独立窗口"


# ====================================================================== 退化路径


class TestDegradedPaths:
    def test_unknown_key_returns_false(self, host):
        assert host.pop_out("__no_such_panel__") is False

    def test_non_tk_container_returns_false(self):
        """测试替身容器（非 Tk）下不能抛异常 —— 独立窗口无从建立。"""
        from app.panels.host import PanelHost

        class _FakeWidget:
            def winfo_children(self):
                return []

            def destroy(self):
                pass

            def cget(self, key):
                return "#101020" if key == "bg" else ""

        _make_probe(PROBE_A, "探针甲")
        built = PanelHost(_FakeApp(), _FakeWidget(), bus=None)
        try:
            assert built.pop_out(PROBE_A) is False
            assert built.is_popped_out(PROBE_A) is False
        finally:
            registry.PANEL_REGISTRY.pop(PROBE_A, None)

    def test_pop_out_twice_reuses_the_same_window(self, host):
        host.pop_out(PROBE_A)
        window = _window(host, PROBE_A)
        assert host.pop_out(PROBE_A) is True
        assert _window(host, PROBE_A) is window, "重复弹出应复用既有窗口，而不是再开一个"
        assert len(host.popped_out_keys()) == 1
