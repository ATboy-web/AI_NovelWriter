"""面板布局（分栏 / 停靠记忆）的测试。

两部分：

- **模型层**（不需要 Tk）：`PanelLayout` 的序列化、校验、持久化容错。
  它的失败模式很具体 —— 一个损坏的 `panel_layout.json` **不能**让应用起不来，
  一个跨版本残留的面板 key **不能**变成空栏；
- **宿主层**（真实 Tk）：分栏真的分成两栏、两栏各自显示正确的面板、
  同一面板不会同时占两栏、比例可拖可记、脱出与分栏不会互相矛盾。

探针面板在夹具里动态创建，并在结束时恢复真实注册表 —— 见 `test_panel_popout.py`
的同类说明（模块级定义会污染整个会话的面板计数断言）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.panels import registry  # noqa: E402
from app.panels.base import BasePanel  # noqa: E402
from app.panels.host import PanelHost  # noqa: E402
from app.panels.layout import (  # noqa: E402
    MAX_RATIO,
    MIN_RATIO,
    MODE_SINGLE,
    MODE_SPLIT,
    PanelLayout,
    load,
    save,
)

PROBE_A = "_test_layout_a"
PROBE_B = "_test_layout_b"
PROBE_C = "_test_layout_c"
PROBE_KEYS = (PROBE_A, PROBE_B, PROBE_C)


class _FakeApp:
    def __init__(self) -> None:
        self.event_bus = None
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)


def _make_probe(key: str, title: str, category: str = "运维") -> type:
    def build(self: Any, parent: Any) -> Any:
        import tkinter as tk

        self.build_count = int(self.__dict__.get("build_count", 0)) + 1
        tk.Label(parent, text=f"{title} 内容").pack()
        self.mark_built(True)
        return parent

    return type(
        "ProbePanel",
        (BasePanel,),
        {"key": key, "title": title, "category": category, "order": 9001, "build": build},
    )


# ====================================================================== 模型层


class TestPanelLayoutModel:
    def test_defaults(self):
        layout = PanelLayout()
        assert layout.mode == MODE_SINGLE
        assert layout.primary == ""
        assert layout.secondary == ""
        assert layout.ratio == 0.5
        assert layout.popped_out == []

    def test_round_trip(self):
        original = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="b", ratio=0.33, popped_out=["c"])
        assert PanelLayout.from_dict(original.to_dict()) == original

    def test_from_dict_tolerates_garbage(self):
        """**回归**：布局文件是跨版本存在的，任何字段都可能被手改坏。"""
        layout = PanelLayout.from_dict({"mode": 7, "primary": None, "ratio": "x", "popped_out": "no"})
        assert layout == PanelLayout()
        assert PanelLayout.from_dict(None) == PanelLayout()
        assert PanelLayout.from_dict(["not", "a", "dict"]) == PanelLayout()

    def test_from_dict_keeps_valid_fields_when_others_are_broken(self):
        layout = PanelLayout.from_dict({"mode": "split", "primary": "a", "ratio": "oops"})
        assert layout.mode == MODE_SPLIT
        assert layout.primary == "a"
        assert layout.ratio == 0.5

    def test_ratio_is_clamped(self):
        assert PanelLayout(ratio=9).sanitize(["a"]).ratio == MAX_RATIO
        assert PanelLayout(ratio=-1).sanitize(["a"]).ratio == MIN_RATIO

    def test_unknown_keys_are_dropped(self):
        cleaned = PanelLayout(mode=MODE_SPLIT, primary="ghost", secondary="ghost2").sanitize(["a", "b"])
        assert cleaned.primary == ""
        assert cleaned.mode == MODE_SINGLE, "主/副栏都不存在时应退回单栏"

    def test_split_degrades_when_secondary_is_missing(self):
        cleaned = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="ghost").sanitize(["a", "b"])
        assert cleaned.primary == "a"
        assert cleaned.secondary == ""
        assert cleaned.mode == MODE_SINGLE, "副栏落空时必须降级，不能留一个空栏"

    def test_same_panel_cannot_occupy_both_panes(self):
        cleaned = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="a").sanitize(["a", "b"])
        assert cleaned.secondary == ""
        assert cleaned.mode == MODE_SINGLE

    def test_popped_out_panel_cannot_also_be_docked(self):
        """同一面板同时"在右栏"和"在独立窗口"是自相矛盾的状态。"""
        cleaned = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="b", popped_out=["b"]).sanitize(["a", "b"])
        assert cleaned.popped_out == ["b"]
        assert cleaned.secondary == ""
        assert cleaned.mode == MODE_SINGLE

    def test_popped_out_is_deduplicated_and_filtered(self):
        cleaned = PanelLayout(popped_out=["a", "a", "ghost"]).sanitize(["a", "b"])
        assert cleaned.popped_out == ["a"]

    def test_copy_derives_a_new_object(self):
        base = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="b")
        derived = base.copy(ratio=0.7)
        assert derived.ratio == 0.7
        assert derived.primary == "a"
        assert base.ratio == 0.5, "copy 不能就地改原对象"


class TestPanelLayoutPersistence:
    def test_load_missing_file_returns_defaults(self, tmp_path):
        assert load(tmp_path / "nope.json") == PanelLayout()

    def test_load_corrupt_file_returns_defaults(self, tmp_path):
        """**关键**：坏掉的布局文件绝不能让应用起不来。"""
        path = tmp_path / "panel_layout.json"
        path.write_text("{ 这不是 JSON", encoding="utf-8")
        assert load(path) == PanelLayout()

    def test_load_wrong_shape_returns_defaults(self, tmp_path):
        path = tmp_path / "panel_layout.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert load(path) == PanelLayout()

    def test_save_then_load_round_trip(self, tmp_path):
        path = tmp_path / "sub" / "panel_layout.json"
        layout = PanelLayout(mode=MODE_SPLIT, primary="a", secondary="b", ratio=0.4, popped_out=["c"])
        assert save(layout, path) is True
        assert load(path) == layout

    def test_save_failure_returns_false_instead_of_raising(self, tmp_path):
        """布局是锦上添花：写不进去也只返回 False，不打断用户写作。"""
        directory = tmp_path / "not-a-file"
        directory.mkdir()
        assert save(PanelLayout(), directory) is False


# ====================================================================== 宿主层


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
def changes():
    """记录宿主广播出来的布局（应用层就是靠这个回调落盘的）。"""
    return []


@pytest.fixture()
def host(tk_root, changes):
    """**只含探针面板**的注册表 + 真实 Tk 容器上的宿主。

    为什么要清空注册表：分栏的默认右栏是从注册表里挑的，如果真实面板混在里面，
    它们需要完整应用状态才能构建（测试里没有）⇒ 会走"构建失败降级单栏"分支，
    测不到真正想测的东西。
    """
    import tkinter as tk

    registry.reset_registry()
    _make_probe(PROBE_A, "探针甲", category="创作素材")
    _make_probe(PROBE_B, "探针乙", category="创作素材")
    _make_probe(PROBE_C, "探针丙", category="结构分析")

    container = tk.Frame(tk_root)
    container.pack(fill=tk.BOTH, expand=True)
    built = PanelHost(
        _FakeApp(),
        container,
        bus=None,
        on_layout_changed=changes.append,
    )
    built.select(PROBE_A)
    yield built
    for key in list(built._popouts):
        try:
            built._popouts[key].destroy()
        except tk.TclError:
            pass
    built._popouts.clear()
    # 恢复真实注册表，避免影响其他测试文件的面板计数断言
    registry.reset_registry()
    registry.load_panels(force=True)


def _content_of(built: PanelHost, key: str):
    panel = built.panel(key)
    assert panel is not None, f"面板 {key} 未实例化"
    return getattr(panel, "_chrome_content", None)


def _pane_of(built: PanelHost, key: str):
    """该面板当前挂在哪个栏里（未挂则 None）。

    比的是**面板自己那个 frame** 的父级 —— 面板内容区（`_chrome_content`）
    是挂在 frame 下面的子控件，不是直接挂在栏上（外壳与内容同处一个 frame）。
    """
    frame = built._frames.get(key)
    if frame is None:
        return None
    for name, pane in built._panes.items():
        if frame.master is pane:
            return name
    return None


class TestSingleMode:
    def test_default_is_single_with_one_pane(self, host):
        assert host.is_split() is False
        assert list(host._panes) == ["primary"]

    def test_default_layout_ratio_is_half(self, host):
        assert host.layout().ratio == 0.5

    def test_ratio_falls_back_to_stored_value_when_not_realized(self, host):
        host.set_ratio(0.35)
        assert host.ratio() == pytest.approx(0.35)


class TestSplitMode:
    def test_split_creates_two_panes(self, host):
        assert host.set_layout_mode(MODE_SPLIT) is True
        assert host.is_split() is True
        assert set(host._panes) == {"primary", "secondary"}
        assert host._paned is not None

    def test_both_panes_show_their_own_panel(self, host):
        host.set_layout_mode(MODE_SPLIT)
        primary, secondary = host.layout().primary, host.layout().secondary
        assert _pane_of(host, primary) == "primary"
        assert _pane_of(host, secondary) == "secondary"
        # 两栏内容都在（而不是"建了栏但只画了一栏"）
        assert "探针甲 内容" in _label_texts(host._panes["primary"])
        assert "内容" in " ".join(_label_texts(host._panes["secondary"]))

    def test_default_secondary_prefers_the_same_category(self, host):
        """并排看的两个面板通常属于同一类工作（同分组优先）。"""
        host.set_layout_mode(MODE_SPLIT)
        assert host.layout().secondary == PROBE_B

    def test_split_is_refused_when_only_one_panel_exists(self, tk_root):
        import tkinter as tk

        registry.reset_registry()
        _make_probe(PROBE_A, "独苗")
        container = tk.Frame(tk_root)
        try:
            built = PanelHost(_FakeApp(), container, bus=None)
            built.select(PROBE_A)
            assert built.set_layout_mode(MODE_SPLIT) is False
            assert built.is_split() is False
        finally:
            registry.reset_registry()
            registry.load_panels(force=True)

    def test_set_secondary_switches_the_right_pane(self, host):
        host.set_layout_mode(MODE_SPLIT)
        assert host.set_secondary(PROBE_C) is True
        assert host.layout().secondary == PROBE_C
        assert _pane_of(host, PROBE_C) == "secondary"
        assert _pane_of(host, PROBE_A) == "primary"

    def test_set_secondary_rejects_the_primary_panel(self, host):
        """同一面板占两栏 ⇒ 两份控件争同一份状态，必须拒绝。"""
        host.set_layout_mode(MODE_SPLIT)
        assert host.set_secondary(PROBE_A) is False
        assert host.layout().secondary != PROBE_A

    def test_set_secondary_rejects_unknown_key(self, host):
        assert host.set_secondary("__nope__") is False

    def test_set_secondary_enters_split_from_single(self, host):
        assert host.is_split() is False
        assert host.set_secondary(PROBE_C) is True
        assert host.is_split() is True

    def test_selecting_the_secondary_swaps_the_panes(self, host):
        host.set_layout_mode(MODE_SPLIT)
        secondary = host.layout().secondary
        assert host.select(secondary) is True
        layout = host.layout()
        assert layout.primary == secondary
        assert layout.secondary == PROBE_A, "选右栏面板应与主栏互换，而不是让同一面板占两栏"
        assert _pane_of(host, layout.primary) == "primary"
        assert _pane_of(host, layout.secondary) == "secondary"

    def test_close_split_returns_to_single(self, host):
        host.set_layout_mode(MODE_SPLIT)
        assert host.close_split() is True
        assert host.is_split() is False
        assert host.layout().secondary == ""
        assert list(host._panes) == ["primary"]
        assert _pane_of(host, PROBE_A) == "primary"

    def test_split_panel_cannot_be_popped_out(self, host):
        host.set_layout_mode(MODE_SPLIT)
        secondary = host.layout().secondary
        # 允许脱出，但脱出后必须从右栏消失（不能同时存在于两处）
        host.pop_out(secondary)
        assert host.is_split() is False, "右栏面板脱出后分栏失去意义，应降级为单栏"
        assert host.layout().secondary == ""
        assert secondary in host.layout().popped_out

    def test_popped_out_panel_cannot_be_docked(self, host):
        host.pop_out(PROBE_B)
        assert host.set_secondary(PROBE_B) is False


class TestRatioPersistence:
    def test_set_ratio_is_clamped_and_broadcast(self, host, changes):
        changes.clear()
        host.set_ratio(5.0)
        assert host.layout().ratio == MAX_RATIO
        assert changes and changes[-1].ratio == MAX_RATIO

    def test_sash_position_is_applied_when_the_window_is_realized(self, host, tk_root):
        """给窗口一个真实尺寸再断言 —— 窄窗口下比例会被"两栏最小宽度"压住。

        （`MIN_PANE_WIDTH` 是**有意**的限制：拖到某一边消失会让人以为面板没了。
        所以断言必须在一个宽度足够放得下两栏的窗口上做。）
        """
        host.set_layout_mode(MODE_SPLIT)
        tk_root.geometry("1200x700+40+40")
        tk_root.deiconify()
        tk_root.update()
        host.set_ratio(0.3)
        tk_root.update()
        width = host._paned.winfo_width()
        if width <= 1:  # pragma: no cover - 无显示环境
            pytest.skip("窗口未真正映射，跳过分隔条位置断言")
        measured = host._measure_ratio()
        assert measured is not None
        assert measured == pytest.approx(0.3, abs=0.08)

    def test_ratio_never_collapses_a_pane(self, host, tk_root):
        """比例被夹在 `[MIN_RATIO, MAX_RATIO]`：任一侧都不会被拖到消失。"""
        host.set_layout_mode(MODE_SPLIT)
        host.set_ratio(0.0)
        assert host.layout().ratio == MIN_RATIO
        host.set_ratio(1.0)
        assert host.layout().ratio == MAX_RATIO

    def test_dragging_the_sash_is_remembered(self, host, tk_root, changes):
        """拖完分隔条要记下来（"停靠记忆"的一部分）。

        模拟方式：先把分隔条放到一个与记忆值不同的位置（等同用户拖动），
        再触发 `<ButtonRelease-1>` 的处理器，断言新比例被记住并广播出去。
        """
        host.set_layout_mode(MODE_SPLIT)
        tk_root.geometry("1200x700+40+40")
        tk_root.deiconify()
        tk_root.update()
        width = host._paned.winfo_width()
        if width <= 1:  # pragma: no cover - 无显示环境
            pytest.skip("窗口未真正映射，无法模拟拖动")

        host._paned.sash_place(0, int(width * 0.62), 0)
        tk_root.update()
        changes.clear()
        host._on_sash_released()

        assert changes, "拖动分隔条后应广播布局变化"
        assert changes[-1].ratio == pytest.approx(0.62, abs=0.08)
        assert host.layout().ratio == pytest.approx(0.62, abs=0.08)


class TestLayoutCallbackAndRestore:
    def test_layout_changes_are_broadcast(self, host, changes):
        changes.clear()
        host.set_layout_mode(MODE_SPLIT)
        assert changes and changes[-1].mode == MODE_SPLIT

    def test_layout_returns_a_copy(self, host):
        snap = host.layout()
        snap.primary = "mutated"
        snap.popped_out.append("x")
        assert host.layout().primary != "mutated"
        assert host.layout().popped_out == []

    def test_apply_layout_restores_a_split(self, host, changes):
        saved = PanelLayout(mode=MODE_SPLIT, primary=PROBE_B, secondary=PROBE_C, ratio=0.4)
        assert host.apply_layout(saved) is True
        assert host.layout().mode == MODE_SPLIT
        assert host.layout().primary == PROBE_B
        assert host.layout().secondary == PROBE_C
        assert _pane_of(host, PROBE_B) == "primary"
        assert _pane_of(host, PROBE_C) == "secondary"

    def test_apply_layout_sanitizes_unknown_panels(self, host):
        """跨版本残留的面板 key 必须被洗掉，而不是变成空栏。"""
        stale = PanelLayout(mode=MODE_SPLIT, primary="ghost", secondary="ghost2")
        assert host.apply_layout(stale) is True
        layout = host.layout()
        assert layout.primary in PROBE_KEYS, "主栏应回落到默认面板"
        assert layout.mode == MODE_SINGLE

    def test_apply_layout_restores_popped_out_windows(self, host, tk_root):
        saved = PanelLayout(mode=MODE_SINGLE, primary=PROBE_A, popped_out=[PROBE_B])
        host.apply_layout(saved)
        assert host.is_popped_out(PROBE_B) is True
        assert host.layout().popped_out == [PROBE_B]
        window = host._popouts[PROBE_B]
        assert window.winfo_exists()

    def test_reapplying_the_same_layout_is_stable(self, host, changes):
        host.set_layout_mode(MODE_SPLIT)
        current = host.layout()
        changes.clear()
        host.apply_layout(current)
        assert host.layout() == current
        assert _pane_of(host, current.secondary) == "secondary"


class TestRefreshWithSplit:
    def test_refresh_rebuilds_both_panes(self, host):
        host.set_layout_mode(MODE_SPLIT)
        secondary = host.layout().secondary
        before_primary = host.panel(host.layout().primary).build_count
        before_secondary = host.panel(secondary).build_count
        assert host.refresh() is True
        assert host.panel(host.layout().primary).build_count == before_primary + 1
        assert host.panel(secondary).build_count == before_secondary + 1, "右栏也必须刷新，否则停在旧数据"

    def test_refresh_keeps_the_split(self, host):
        host.set_layout_mode(MODE_SPLIT)
        host.refresh()
        assert host.is_split() is True
        assert _pane_of(host, host.layout().secondary) == "secondary"


def _label_texts(widget) -> list[str]:
    """子树里的 Label 文本（用于确认"内容真的画出来了"）。"""
    out: list[str] = []
    stack = [widget]
    while stack:
        item = stack.pop()
        try:
            stack.extend(item.winfo_children())
            if item.winfo_class() == "Label":
                out.append(str(item.cget("text")))
        except Exception:  # noqa: BLE001 - 个别控件无 text
            continue
    return out
