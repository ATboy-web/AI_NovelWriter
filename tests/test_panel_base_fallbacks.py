"""`BasePanel` 的容错分支（档 3：面板崩了整页不能用）。

## 为什么这些方法值得单独测

它们是**五个面板共用的**：`_set_detail` 在 lineage / mcp / plugin / rework / skills
里逐字相同（"临时解除只读 → 清空 → 写入 → 恢复只读"）。这种公共代码一旦出错，
五个面板同时坏，而现象是"详情区不刷新"或"面板直接崩"。

判据重点在**最坏情况下不崩**：
- `_detail` 还不存在（事件早于 build）⇒ 静默返回
- 控件已销毁 ⇒ 吞掉异常
- 没有 `app.root` ⇒ `_host_widget` 返回 None 而不是 AttributeError
"""

from __future__ import annotations

from typing import Any

from app.panels import ui_kit
from app.panels.base import BasePanel


class FakeText:
    """只实现 `_set_detail` 用到的那四个方法。"""

    def __init__(self, *, fail_on: str | None = None):
        self.state = "disabled"
        self.content = ""
        self.calls: list[str] = []
        self._fail_on = fail_on

    def config(self, **kwargs):
        if self._fail_on == "config" or "destroyed" in kwargs:
            raise RuntimeError("控件已销毁")
        self.calls.append(f"config:{kwargs.get('state', '')}")
        if "state" in kwargs:
            self.state = kwargs["state"]

    def delete(self, *_args):
        if self._fail_on == "delete":
            raise RuntimeError("控件已销毁")
        self.calls.append("delete")
        self.content = ""

    def insert(self, _index, text):
        if self._fail_on == "insert":
            raise RuntimeError("控件已销毁")
        self.calls.append("insert")
        self.content = text


class FakeApp:
    def __init__(self, *, root: Any = None):
        self.root = root


class Panel(BasePanel):
    panel_key = "test_base_panel"
    title = "测试面板"

    def build(self, parent):
        self.mark_built(True)
        return parent


class TestSetDetail:
    def test_missing_widget_is_noop(self):
        """事件可能早于 build —— "详情没刷新"远好过"面板崩掉"。"""
        panel = Panel(FakeApp())

        panel._set_detail("内容")  # 不抛即通过

    def test_writes_and_restores_readonly(self):
        text = FakeText()
        panel = Panel(FakeApp())
        panel._detail = text

        panel._set_detail("第 3 章：评分 88")

        assert text.content == "第 3 章：评分 88"
        assert text.state == "disabled", "写完没有恢复只读 —— 用户能直接把详情区改成可编辑"
        assert text.calls == ["config:normal", "delete", "insert", "config:disabled"]

    def test_destroyed_widget_is_swallowed(self):
        panel = Panel(FakeApp())
        panel._detail = FakeText(fail_on="insert")

        panel._set_detail("内容")  # 不抛即通过

    def test_empty_text_still_clears(self):
        text = FakeText()
        text.content = "旧内容"
        panel = Panel(FakeApp())
        panel._detail = text

        panel._set_detail("")

        assert text.content == ""


class TestHostWidget:
    def test_prefers_app_root(self):
        root = object()
        panel = Panel(FakeApp(root=root))

        assert panel._host_widget() is root

    def test_falls_back_to_tool_content_frame(self):
        frame = object()

        class AppWithFrame:
            root = None
            tool_content_frame = frame

        panel = Panel(AppWithFrame())

        assert panel._host_widget() is frame

    def test_none_when_app_missing_root(self):
        panel = Panel(None)

        assert panel._host_widget() is None


class TestNotify:
    def test_toast_targets_container(self, monkeypatch):
        seen: list = []
        monkeypatch.setattr(ui_kit, "toast", lambda target, text, **kw: seen.append((target, text, kw)))
        container = object()
        panel = Panel(FakeApp())
        panel.container = container

        panel.notify("已保存", kind="success")

        assert seen and seen[0][0] is container
        assert seen[0][1] == "已保存"

    def test_toast_falls_back_to_host_widget(self, monkeypatch):
        seen: list = []
        monkeypatch.setattr(ui_kit, "toast", lambda target, text, **kw: seen.append(target))
        root = object()
        panel = Panel(FakeApp(root=root))

        panel.notify("提示")

        assert seen[0] is root


class TestBuiltFlag:
    """`is_built` 是**属性**不是方法（写成 `is_built()` 会 TypeError）。"""

    def test_not_built_initially(self):
        assert Panel(FakeApp()).is_built is False

    def test_mark_built(self):
        panel = Panel(FakeApp())
        panel.mark_built(True)

        assert panel.is_built is True

    def test_mark_unbuilt(self):
        panel = Panel(FakeApp())
        panel.mark_built(True)
        panel.mark_built(False)

        assert panel.is_built is False


class TestStatusAndConfirm:
    def test_status_without_bar_is_safe(self):
        """宿主没注入状态栏时静默返回 —— 面板不该因为没状态栏就崩。"""
        panel = Panel(FakeApp())

        panel.set_status("就绪")  # 不抛即通过

    def test_status_goes_to_host_bar(self):
        seen: list = []

        class Bar:
            def set(self, text, kind):
                seen.append((text, kind))

        panel = Panel(FakeApp())
        panel._status_bar = Bar()

        panel.set_status("出错", kind="error")

        assert seen == [("出错", "error")]
