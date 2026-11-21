"""`app/dialogs.py` 行为测试（P1-4 补测）。

此前该模块覆盖率 31.17%：静默模式被测过，但真正的自绘对话框
（ask_text / edit_items / show_text）与 messagebox 包装层一行未测。
这些是"用户输入能不能正确回到业务代码"的最后一环，必须有守卫。

模态窗用 `wait_window()` 阻塞，因此测试通过 `root.after()` 在其事件循环内
驱动控件；断言值先收集到字典，回到主流程再断言（Tk 回调里抛异常不会冒泡）。
"""

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from _tk_harness import optional_root

from app import dialogs


@pytest.fixture
def root():
    r = optional_root()
    try:
        yield r
    finally:
        r.destroy()


@pytest.fixture(autouse=True)
def _not_silent():
    previous = dialogs.set_silent(False)
    yield
    dialogs.set_silent(previous)


def _walk(win):
    stack = [win]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


def _button(win, text):
    for w in _walk(win):
        if isinstance(w, tk.Button) and w.cget("text") == text:
            return w
    raise AssertionError(f"找不到按钮 {text}")


def _newest_toplevel(root):
    wins = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert wins, "对话框没有建出来"
    return wins[-1]


# ------------------------------------------------------------------ 静默模式


def test_silent_returns_safe_defaults():
    with dialogs.silent_modals():
        assert dialogs.is_silent() is True
        assert dialogs.showinfo("t", "m") is None
        assert dialogs.showwarning("t", "m") is None
        assert dialogs.showerror("t", "m") is None
        assert dialogs.askyesno("t", "m") is False
        assert dialogs.confirm("删除？") is False
        assert dialogs.ask_text(None, "t", "p") is None
    assert dialogs.is_silent() is False


def test_silent_modals_restores_previous_state_on_exception():
    dialogs.set_silent(True)
    with pytest.raises(RuntimeError):
        with dialogs.silent_modals():
            raise RuntimeError("boom")
    assert dialogs.is_silent() is True, "嵌套退出不得把外层的静默状态改掉"
    dialogs.set_silent(False)


def test_confirm_respects_explicit_default_in_silent():
    with dialogs.silent_modals():
        assert dialogs.confirm("覆盖？", default=True) is True


# ------------------------------------------------------------------ 包装层


@pytest.mark.parametrize(
    "name,wrapper",
    [("showinfo", dialogs.showinfo), ("showwarning", dialogs.showwarning), ("showerror", dialogs.showerror)],
)
def test_show_wrappers_delegate(monkeypatch, name, wrapper):
    calls = []

    class MB:
        def __getattr__(self, item):
            return lambda *a, **k: calls.append((item, a, k)) or "ok"

    monkeypatch.setattr(dialogs, "_messagebox", lambda: MB())
    assert wrapper("标题", "内容", parent=None) == "ok"
    assert calls[0][0] == name
    assert calls[0][1] == ("标题", "内容")


def test_askyesno_coerces_to_bool(monkeypatch):
    class MB:
        def askyesno(self, *a, **k):
            return 1

    monkeypatch.setattr(dialogs, "_messagebox", lambda: MB())
    assert dialogs.askyesno("t", "m") is True


def test_semantic_helpers_use_app_title(monkeypatch):
    seen = []
    monkeypatch.setattr(dialogs, "showinfo", lambda *a, **k: seen.append(("info", a)))
    monkeypatch.setattr(dialogs, "showwarning", lambda *a, **k: seen.append(("warn", a)))
    monkeypatch.setattr(dialogs, "showerror", lambda *a, **k: seen.append(("error", a)))
    dialogs.info("i")
    dialogs.warn("w")
    dialogs.error("e")
    assert [kind for kind, _ in seen] == ["info", "warn", "error"]
    assert all(a[0] == dialogs.APP_TITLE for _, a in seen)


# ------------------------------------------------------------------ ask_text


def test_ask_text_confirm_strips_input(root):
    def drive():
        win = _newest_toplevel(root)
        entry = next(w for w in _walk(win) if isinstance(w, tk.Entry))
        entry.delete(0, tk.END)
        entry.insert(0, "  你好  ")
        _button(win, "确定").invoke()

    root.after(60, drive)
    assert dialogs.ask_text(root, "标题", "提示") == "你好"


def test_ask_text_cancel_returns_none(root):
    def drive():
        _button(_newest_toplevel(root), "取消").invoke()

    root.after(60, drive)
    assert dialogs.ask_text(root, "标题", "提示", initial="预填") is None


def test_ask_text_empty_string_is_valid(root):
    def drive():
        win = _newest_toplevel(root)
        entry = next(w for w in _walk(win) if isinstance(w, tk.Entry))
        entry.delete(0, tk.END)
        _button(win, "确定").invoke()

    root.after(60, drive)
    assert dialogs.ask_text(root, "标题", "提示") == "", "空输入是合法值，只有取消才是 None"


def test_ask_text_validator_blocks_then_passes(root):
    seen = {}

    def drive():
        win = _newest_toplevel(root)
        entry = next(w for w in _walk(win) if isinstance(w, tk.Entry))
        _button(win, "确定").invoke()  # 空值应被校验器拦下
        seen["still_open"] = bool(win.winfo_exists())
        seen["error_text"] = next(
            (w.cget("text") for w in _walk(win) if isinstance(w, tk.Label) and w.cget("text")), ""
        )
        entry.insert(0, "合法内容")
        _button(win, "确定").invoke()

    root.after(60, drive)
    value = dialogs.ask_text(root, "标题", "提示", validate=dialogs._non_empty)
    assert seen["still_open"] is True, "校验不通过时对话框不得关闭"
    assert value == "合法内容"


def test_ask_text_multiline(root):
    def drive():
        win = _newest_toplevel(root)
        body = next(w for w in _walk(win) if isinstance(w, tk.Text))
        body.delete("1.0", tk.END)
        body.insert("1.0", "第一行\n第二行\n")
        _button(win, "确定").invoke()

    root.after(60, drive)
    assert dialogs.ask_text(root, "标题", "提示", height=5) == "第一行\n第二行"


def test_non_empty_validator():
    assert dialogs._non_empty("") == "内容不能为空"
    assert dialogs._non_empty("x") is None


# ------------------------------------------------------------------ 其它对话框


def test_show_text_renders_and_closes(root):
    def drive():
        win = _newest_toplevel(root)
        body = next(w for w in _walk(win) if isinstance(w, tk.Text))
        seen["content"] = body.get("1.0", tk.END).strip()
        _button(win, "关闭").invoke()

    seen = {}
    root.after(60, drive)
    dialogs.show_text(root, "标题", "正文内容")
    assert seen["content"] == "正文内容"


def test_edit_items_cancel_keeps_original(root):
    def drive():
        _button(_newest_toplevel(root), "取消").invoke()

    root.after(60, drive)
    assert dialogs.edit_items(root, "标题", ["甲", "乙"]) is None


def test_edit_items_save_returns_items(root):
    def drive():
        _button(_newest_toplevel(root), "保存").invoke()

    root.after(60, drive)
    assert dialogs.edit_items(root, "标题", ["甲", "乙"]) == ["甲", "乙"]


def test_edit_items_silent_returns_none():
    with dialogs.silent_modals():
        assert dialogs.edit_items(None, "标题", ["甲"]) is None
        assert dialogs.show_text(None, "标题", "正文") is None
