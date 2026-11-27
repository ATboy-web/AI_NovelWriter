"""`app.dialogs` 的两层测试。

## 分两层的原因

| 层 | 内容 | 需要 Tk | 为什么这样分 |
|---|---|---|---|
| 模型层 | `_ItemListModel` 的增删改移 | ❌ | 边界条件（空选择、越界移动）是真实逻辑，不该只能靠点界面验 |
| 宿主层 | `edit_items` 的保存/取消/提示/空校验 | ✅ | 返回值语义（取消返回 `None`、清空返回 `[]`）必须真的走一遍 |

`edit_items` 的清单逻辑原先写在四个内嵌回调里，覆盖率为 0 ——
把逻辑抽到 `_ItemListModel` 之后，边界条件可以穷举；同时保留一条真 Tk 用例，
确保"抽出来之后对话框仍然返回正确的列表"。

## 关于 CI

含 `Tk` 的类名会被 CI 的 `-k "not Tk"` 排除（CI 无显示环境），与仓库既有约定一致。
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import _tk_harness
import pytest

from app import dialogs
from app.dialogs import _ItemListModel


class TestItemListModel:
    """增删改移的边界 —— 出错的表现是"点了上移却没动"或"删错了行"。"""

    def test_starts_from_copy_of_input(self):
        source = ["a", "b"]
        model = _ItemListModel(source)

        model.add("c")

        assert source == ["a", "b"], "改动泄露回调用方的列表了"

    def test_empty_list(self):
        model = _ItemListModel()

        assert model.is_empty() is True
        assert len(model) == 0
        assert model.as_list() == []

    def test_add_returns_new_index(self):
        model = _ItemListModel(["a"])

        assert model.add("b") == 1
        assert model.as_list() == ["a", "b"]

    def test_get_handles_none_and_out_of_range(self):
        model = _ItemListModel(["a"])

        assert model.get(0) == "a"
        assert model.get(None) is None
        assert model.get(5) is None
        assert model.get(-1) is None, "负下标不能被当成'最后一项'（界面上的选中项不会是负数）"

    def test_edit(self):
        model = _ItemListModel(["a", "b"])

        assert model.edit(1, "B") is True
        assert model.as_list() == ["a", "B"]

    @pytest.mark.parametrize("index", [None, 2, -1])
    def test_edit_rejects_bad_index(self, index):
        model = _ItemListModel(["a"])

        assert model.edit(index, "X") is False
        assert model.as_list() == ["a"]

    def test_remove(self):
        model = _ItemListModel(["a", "b", "c"])

        assert model.remove(1) is True
        assert model.as_list() == ["a", "c"]

    @pytest.mark.parametrize("index", [None, 3, -1])
    def test_remove_rejects_bad_index(self, index):
        model = _ItemListModel(["a"])

        assert model.remove(index) is False
        assert model.as_list() == ["a"]

    def test_move_down(self):
        model = _ItemListModel(["a", "b"])

        assert model.move(0, 1) == 1
        assert model.as_list() == ["b", "a"]

    def test_move_up(self):
        model = _ItemListModel(["a", "b"])

        assert model.move(1, -1) == 0
        assert model.as_list() == ["b", "a"]

    def test_move_beyond_top_does_nothing(self):
        model = _ItemListModel(["a", "b"])

        assert model.move(0, -1) is None
        assert model.as_list() == ["a", "b"], "越界移动把列表改了"

    def test_move_beyond_bottom_does_nothing(self):
        model = _ItemListModel(["a", "b"])

        assert model.move(1, 1) is None
        assert model.as_list() == ["a", "b"]

    @pytest.mark.parametrize("index", [None, 5, -1])
    def test_move_rejects_bad_index(self, index):
        model = _ItemListModel(["a"])

        assert model.move(index, 1) is None

    def test_as_list_is_a_copy(self):
        model = _ItemListModel(["a"])

        returned = model.as_list()
        returned.append("偷偷加的")

        assert model.as_list() == ["a"], "调用方拿到的是内部列表的引用"


class TestCenterOnParent:
    """`_center_on_parent` 的容错：父窗口还没有几何信息时必须**静默跳过**。

    启动阶段父窗口尚未映射，`winfo_width()` 返回 1 —— 此时强行居中会把
    对话框丢到屏幕角落。异常也应被吞掉：定位失败不该阻断弹窗。
    """

    def test_silently_skips_when_geometry_unavailable(self):
        class NoGeometry:
            pass

        # 不抛即通过
        dialogs._center_on_parent(NoGeometry(), NoGeometry())

    def test_silently_skips_on_tcl_error(self):
        class Boom:
            def update_idletasks(self):
                raise tk.TclError("窗口已销毁")

        dialogs._center_on_parent(Boom(), Boom())


@pytest.mark.skipif(not _tk_harness.tk_available(), reason="无显示环境")
class TestEditItemsTk:
    """真 Tk 走一遍 `edit_items` —— 验返回值语义与控件构建。

    用 `after()` 在事件循环里点按钮：`wait_window()` 期间回调照常触发，
    所以不需要线程，也不会卡住。
    """

    @staticmethod
    def _dialog(root) -> Optional[tk.Toplevel]:
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel):
                return child
        return None

    @classmethod
    def _button(cls, root, text: str) -> Optional[tk.Button]:
        win = cls._dialog(root)
        if win is None:
            return None
        for widget in win.winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, tk.Button) and child.cget("text") == text:
                    return child
            if isinstance(widget, tk.Button) and widget.cget("text") == text:
                return widget
        return None

    def _drive(self, root, action, *, timeout_ms: int = 3000):
        """在事件循环里执行 `action`；超时则关窗，避免测试挂死。"""

        def go():
            try:
                action()
            finally:
                win = self._dialog(root)
                if win is not None:
                    win.destroy()

        root.after(80, go)
        root.after(timeout_ms, lambda: (self._dialog(root) or root).destroy() or None)

    def test_save_returns_edited_list(self):
        root = _tk_harness.create_root()
        try:
            self._drive(root, lambda: self._button(root, "保存").invoke())
            result = dialogs.edit_items(root, "编辑", ["甲", "乙"])
        finally:
            root.destroy()

        assert result == ["甲", "乙"]

    def test_cancel_returns_none(self):
        """取消必须返回 `None` —— 这样"取消"与"清空列表"才能区分。"""
        root = _tk_harness.create_root()
        try:
            self._drive(root, lambda: self._dialog(root).event_generate("<Escape>"))
            result = dialogs.edit_items(root, "编辑", ["甲"])
        finally:
            root.destroy()

        assert result is None

    def test_empty_input_list_returns_empty_on_save(self):
        root = _tk_harness.create_root()
        try:
            self._drive(root, lambda: self._button(root, "保存").invoke())
            result = dialogs.edit_items(root, "编辑", [])
        finally:
            root.destroy()

        assert result == []

    def test_hint_is_rendered(self):
        """有 hint 时必须建出说明文字 —— 没有它用户不知道这一栏填什么。"""
        seen: list[str] = []
        root = _tk_harness.create_root()
        try:

            def capture():
                win = self._dialog(root)
                for widget in win.winfo_children():
                    if isinstance(widget, tk.Label):
                        seen.append(str(widget.cget("text")))
                self._button(root, "保存").invoke()

            self._drive(root, capture)
            dialogs.edit_items(root, "编辑", ["甲"], hint="每行一个关键词")
        finally:
            root.destroy()

        assert any("每行一个关键词" in text for text in seen)

    def test_empty_list_is_blocked_when_not_allowed(self):
        """`allow_empty=False` 且列表为空 ⇒ 点保存**不关窗**并提示。"""
        blocked: list[bool] = []
        root = _tk_harness.create_root()
        try:

            def click_save_twice():
                button = self._button(root, "保存")
                button.invoke()
                # 第一次点击应被拦下：窗口还在
                blocked.append(self._dialog(root) is not None)
                button.invoke()  # 第二次仍被拦（列表依旧空）

            self._drive(root, click_save_twice)
            result = dialogs.edit_items(root, "编辑", [], allow_empty=False)
        finally:
            root.destroy()

        assert blocked == [True], "空列表没有被拦下，窗口直接关了"
        assert result is None, "被拦下后应等同取消（超时关窗 → None）"


@pytest.mark.skipif(not _tk_harness.tk_available(), reason="无显示环境")
class TestEditItemsOperationsTk:
    """四个操作按钮的回调接线。

    新增/编辑会弹出 `ask_text`（嵌套模态，驱动成本高且脆），
    所以这里把 `dialogs.ask_text` 换成固定返回值 —— 要验的是
    **"按钮 → 模型 → 列表"这条链通不通**，而 `ask_text` 自身另有覆盖。
    删除/上下移不弹窗，直接点。
    """

    @staticmethod
    def _find(widget, kind):
        for child in widget.winfo_children():
            if isinstance(child, kind):
                return child
            found = TestEditItemsOperationsTk._find(child, kind)
            if found is not None:
                return found
        return None

    def _run(self, action, items, monkeypatch, *, ask_returns=None, allow_empty=True):
        seen: dict = {}
        root = _tk_harness.create_root()
        if ask_returns is not None:
            monkeypatch.setattr(dialogs, "ask_text", lambda *a, **kw: ask_returns)

        def go():
            try:
                action(root, seen)
            finally:
                win = next((c for c in root.winfo_children() if isinstance(c, tk.Toplevel)), None)
                if win is not None:
                    win.destroy()

        root.after(80, go)
        root.after(3000, lambda: root.destroy())
        try:
            seen["result"] = dialogs.edit_items(root, "编辑", items, allow_empty=allow_empty)
        finally:
            try:
                root.destroy()
            except tk.TclError:  # pragma: no cover
                pass
        return seen

    def _button(self, root, text):
        win = next((c for c in root.winfo_children() if isinstance(c, tk.Toplevel)), None)
        button = self._find(win, tk.Button)
        # 按文本精确找（同一层里按钮不止一个）
        stack = [win]
        while stack:
            current = stack.pop()
            for child in current.winfo_children():
                if isinstance(child, tk.Button) and child.cget("text") == text:
                    return child
                stack.append(child)
        return button

    def test_add_button_appends(self, monkeypatch):
        def act(root, seen):
            self._button(root, "新增").invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲"], monkeypatch, ask_returns="乙")

        assert seen["result"] == ["甲", "乙"]

    def test_edit_button_replaces_selected(self, monkeypatch):
        def act(root, seen):
            win = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            self._find(win, tk.Listbox).selection_set(0)
            self._button(root, "编辑").invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲", "乙"], monkeypatch, ask_returns="甲改")

        assert seen["result"] == ["甲改", "乙"]

    def test_remove_button_deletes_selected(self):
        def act(root, seen):
            win = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            self._find(win, tk.Listbox).selection_set(0)
            self._button(root, "删除").invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲", "乙"], monkeypatch=None)

        assert seen["result"] == ["乙"]

    def test_move_down_button_reorders(self):
        def act(root, seen):
            win = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            self._find(win, tk.Listbox).selection_set(0)
            self._button(root, "下移").invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲", "乙"], monkeypatch=None)

        assert seen["result"] == ["乙", "甲"]

    def test_move_up_button_reorders(self):
        def act(root, seen):
            win = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            box = self._find(win, tk.Listbox)
            # 🔴 必须先清空：refresh() 建完后已自动选中第 0 项，
            # 而 selection_set 是**追加**而不是替换 ⇒ 直接 set(1) 得到 (0, 1)，
            # 后面取 selection[0] 依然是 0，用例会验成"移动没生效"。
            box.selection_clear(0, tk.END)
            box.selection_set(1)
            self._button(root, "上移").invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲", "乙"], monkeypatch=None)

        assert seen["result"] == ["乙", "甲"]

    def test_operations_without_selection_do_nothing(self):
        """没有选中项时点删除/上移/下移必须是**静默无操作**，不能崩。"""

        def act(root, seen):
            win = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            self._find(win, tk.Listbox).selection_clear(0, tk.END)
            for label in ("删除", "上移", "下移"):
                self._button(root, label).invoke()
            self._button(root, "保存").invoke()

        seen = self._run(act, ["甲", "乙"], monkeypatch=None)

        assert seen["result"] == ["甲", "乙"]
