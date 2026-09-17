"""同构对话框 helper（v3 A8）。

本模块是**所有用户可见对话框的唯一实现处**，分两层：

| 层 | 接口 | 用途 |
|---|---|---|
| 自绘 Toplevel | `ask_text` / `edit_items` / `show_text` | 输入、编辑列表、展示长文本 |
| 消息弹窗 | `showinfo` / `showwarning` / `showerror` / `askyesno`（同 `messagebox` 签名）<br>`info` / `warn` / `error` / `confirm`（语义化，新代码用） | 提示与确认 |

现状：全仓 `tk.Toplevel(` 共 36 处，归纳后只有三类同构形态：

1. **输入框 + 确定/取消** —— 取一个字符串（书名、字数、关键词…）
2. **列表 + 编辑** —— 增删改一组条目（关键词表、标签、世界线名…）
3. **只读文本展示** —— 展示一段长文本（提示词、预览、诊断）

这里的三个函数就是这三类的唯一实现。**不要**在这里加业务逻辑，
它只负责"把控件摆好、返回值、处理取消"，数据由调用方准备。

约定（全部 36 处手写对话框都应有的一致行为，但此前各不相同）：
- **取消一律返回 None / False，不抛异常**（此前有的抛 `ValueError`，有的返回空串）
- 模态（`grab_set` + `wait_window`），关闭窗口（`WM_DELETE_WINDOW`）等同取消
- Enter 提交、Escape 取消
- 颜色/字体一律走 `UIStyle` 令牌

本模块不创建 Tk 根窗口，也不在 import 时触碰任何 Tk API —— 可被无 GUI 环境 import。
（`tkinter.messagebox` 同样是按需在函数内取得，见 `_messagebox()`。）

⚠️ **使用政策**：操作结果优先用 `ui_kit.toast` / `StatusBar`（不打断操作流）；
模态只留给**需要用户决定**的场景。这不是风格问题 —— 全仓原有 64 处弹窗
意味着每个操作都要用户点一下才能继续。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional

from .ui_style import UIStyle

__all__ = [
    "APP_TITLE",
    # 自绘对话框
    "ask_text",
    "edit_items",
    "show_text",
    # 消息弹窗（同 messagebox 签名）
    "askyesno",
    "showerror",
    "showinfo",
    "showwarning",
    # 消息弹窗（语义化）
    "confirm",
    "error",
    "info",
    "is_silent",
    "set_silent",
    "silent_modals",
    "warn",
]

_C = UIStyle.COLORS
_F = UIStyle.FONTS


def _center_on_parent(window: tk.Toplevel, parent) -> None:
    """把对话框摆到父窗口中间（取不到几何信息时静默跳过）。"""
    try:
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = window.winfo_width(), window.winfo_height()
        if pw > 1 and ph > 1:
            window.geometry(f"+{px + (pw - w) // 2}+{py + max((ph - h) // 3, 0)}")
    except (tk.TclError, AttributeError):
        pass


def _prepare(parent, title: str) -> tk.Toplevel:
    """建一个已套用主题的模态 Toplevel，并绑定 Escape=关闭。"""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=_C["bg_dark"])
    win.transient(parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent)
    win.bind("<Escape>", lambda _e: win.destroy())
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    return win


def ask_text(
    parent,
    title: str,
    prompt: str,
    initial: str = "",
    width: int = 40,
    height: int = 1,
    validate: Optional[Callable[[str], Optional[str]]] = None,
    ok_text: str = "确定",
) -> Optional[str]:
    """输入框 + 确定/取消。

    Args:
        validate: 可选校验器。返回**错误文案**表示不通过（对话框不关闭、在下方红字提示），
            返回 None 表示通过。这样调用方不必自己弹二次错误框。

    Returns:
        用户输入的字符串（**已 strip**）；取消返回 ``None``。
        注意：空字符串是合法返回值（用户确实输入了空），只有取消才是 None。
    """
    win = _prepare(parent, title)
    result: dict = {"value": None}

    tk.Label(
        win,
        text=prompt,
        bg=_C["bg_dark"],
        fg=_C["text_primary"],
        font=(_F["family"], _F["size_base"]),
        justify=tk.LEFT,
        wraplength=380,
    ).pack(padx=20, pady=(16, 8), anchor=tk.W)

    if height > 1:
        body = tk.Text(
            win,
            width=width,
            height=height,
            bg=_C["bg_medium"],
            fg=_C["text_primary"],
            insertbackground=_C["text_primary"],
            relief=tk.FLAT,
            font=(_F["family"], _F["size_base"]),
        )
        body.pack(padx=20, pady=4)
        body.insert("1.0", initial)
        widget = body
    else:
        var = tk.StringVar(value=initial)
        entry = tk.Entry(
            win,
            textvariable=var,
            width=width,
            bg=_C["bg_medium"],
            fg=_C["text_primary"],
            insertbackground=_C["text_primary"],
            relief=tk.FLAT,
            font=(_F["family"], _F["size_base"]),
        )
        entry.pack(padx=20, pady=4, ipady=6)
        widget = entry
        body = None

    error_label = tk.Label(
        win,
        text="",
        bg=_C["bg_dark"],
        fg=_C["error"],
        font=(_F["family"], _F["size_sm"]),
        wraplength=380,
        justify=tk.LEFT,
    )
    error_label.pack(padx=20, pady=(0, 4), anchor=tk.W)

    def submit(_event=None) -> None:
        if body is not None:
            value = body.get("1.0", tk.END).strip()
        else:
            value = var.get().strip()
        if validate is not None:
            message = validate(value)
            if message:
                error_label.configure(text=message)
                return
        result["value"] = value
        win.destroy()

    buttons = tk.Frame(win, bg=_C["bg_dark"])
    buttons.pack(padx=20, pady=(6, 16), anchor=tk.E)
    tk.Button(
        buttons,
        text=ok_text,
        command=submit,
        bg=_C["accent"],
        fg="white",
        relief=tk.FLAT,
        padx=18,
        pady=5,
        cursor="hand2",
        font=(_F["family"], _F["size_base"]),
    ).pack(side=tk.LEFT, padx=4)
    tk.Button(
        buttons,
        text="取消",
        command=win.destroy,
        bg=_C["bg_light"],
        fg=_C["text_primary"],
        relief=tk.FLAT,
        padx=18,
        pady=5,
        cursor="hand2",
        font=(_F["family"], _F["size_base"]),
    ).pack(side=tk.LEFT, padx=4)

    win.bind("<Return>", submit)
    widget.focus_set()
    _center_on_parent(win, parent)
    win.grab_set()
    win.wait_window()
    return result["value"]


def edit_items(
    parent,
    title: str,
    items: Optional[List[str]] = None,
    hint: str = "",
    allow_empty: bool = True,
) -> Optional[List[str]]:
    """列表 + 编辑（增 / 删 / 上下移 / 双击改）。

    Returns:
        编辑后的**新列表**（不修改传入的 `items`，调用方需自行保存）；
        取消返回 ``None`` —— 这样"用户取消了"和"用户清空了列表"可区分。
    """
    win = _prepare(parent, title)
    win.geometry("460x440")
    result: dict = {"value": None}
    working = list(items or [])

    if hint:
        tk.Label(
            win,
            text=hint,
            bg=_C["bg_dark"],
            fg=_C["text_muted"],
            font=(_F["family"], _F["size_sm"]),
            wraplength=420,
            justify=tk.LEFT,
        ).pack(padx=16, pady=(12, 4), anchor=tk.W)

    list_frame = tk.Frame(win, bg=_C["bg_dark"])
    list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

    listbox = tk.Listbox(
        list_frame,
        bg=_C["bg_card"],
        fg=_C["text_primary"],
        selectbackground=_C["accent"],
        selectforeground="white",
        relief=tk.FLAT,
        font=(_F["family"], _F["size_base"]),
        highlightthickness=0,
        activestyle="none",
    )
    scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh(select: Optional[int] = None) -> None:
        listbox.delete(0, tk.END)
        for item in working:
            listbox.insert(tk.END, item)
        if working:
            index = 0 if select is None else max(0, min(select, len(working) - 1))
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.see(index)

    def selected_index() -> Optional[int]:
        selection = listbox.curselection()
        return selection[0] if selection else None

    def add_item() -> None:
        value = ask_text(win, "新增条目", "内容：", validate=_non_empty)
        if value:
            working.append(value)
            refresh(len(working) - 1)

    def edit_selected() -> None:
        index = selected_index()
        if index is None:
            return
        value = ask_text(win, "编辑条目", "内容：", initial=working[index], validate=_non_empty)
        if value is not None:
            working[index] = value
            refresh(index)

    def remove_selected() -> None:
        index = selected_index()
        if index is None:
            return
        del working[index]
        refresh(index)

    def move(delta: int) -> None:
        index = selected_index()
        if index is None:
            return
        target = index + delta
        if not 0 <= target < len(working):
            return
        working[index], working[target] = working[target], working[index]
        refresh(target)

    operations = tk.Frame(win, bg=_C["bg_dark"])
    operations.pack(fill=tk.X, padx=16, pady=4)
    for label, command in (
        ("新增", add_item),
        ("编辑", edit_selected),
        ("删除", remove_selected),
        ("上移", lambda: move(-1)),
        ("下移", lambda: move(1)),
    ):
        tk.Button(
            operations,
            text=label,
            command=command,
            bg=_C["bg_light"],
            fg=_C["text_primary"],
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            font=(_F["family"], _F["size_sm"]),
        ).pack(side=tk.LEFT, padx=3)

    error_label = tk.Label(
        win,
        text="",
        bg=_C["bg_dark"],
        fg=_C["error"],
        font=(_F["family"], _F["size_sm"]),
    )
    error_label.pack(padx=16, anchor=tk.W)

    def submit() -> None:
        if not allow_empty and not working:
            error_label.configure(text="列表不能为空")
            return
        result["value"] = list(working)
        win.destroy()

    buttons = tk.Frame(win, bg=_C["bg_dark"])
    buttons.pack(padx=16, pady=(4, 14), anchor=tk.E)
    tk.Button(
        buttons,
        text="保存",
        command=submit,
        bg=_C["accent"],
        fg="white",
        relief=tk.FLAT,
        padx=18,
        pady=5,
        cursor="hand2",
        font=(_F["family"], _F["size_base"]),
    ).pack(side=tk.LEFT, padx=4)
    tk.Button(
        buttons,
        text="取消",
        command=win.destroy,
        bg=_C["bg_light"],
        fg=_C["text_primary"],
        relief=tk.FLAT,
        padx=18,
        pady=5,
        cursor="hand2",
        font=(_F["family"], _F["size_base"]),
    ).pack(side=tk.LEFT, padx=4)

    listbox.bind("<Double-Button-1>", lambda _e: edit_selected())
    listbox.bind("<Delete>", lambda _e: remove_selected())

    refresh()
    listbox.focus_set()
    _center_on_parent(win, parent)
    win.grab_set()
    win.wait_window()
    return result["value"]


def show_text(
    parent,
    title: str,
    text: str,
    width: int = 80,
    height: int = 24,
    copyable: bool = True,
    on_copy: Optional[Callable[[str], None]] = None,
) -> None:
    """只读长文本展示（提示词 / 预览 / 诊断信息）。

    只读但**可选中复制** —— 正文提示词需要能复制到 Midjourney/SD 里。
    """
    win = _prepare(parent, title)
    win.geometry(f"{min(width * 8, 1000)}x{max(height * 18, 320)}")

    text_frame = tk.Frame(win, bg=_C["bg_dark"])
    text_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 6))

    body = tk.Text(
        text_frame,
        wrap=tk.WORD,
        bg=_C["bg_card"],
        fg=_C["text_primary"],
        insertbackground=_C["text_primary"],
        relief=tk.FLAT,
        font=(_F["family"], _F["size_base"]),
        padx=12,
        pady=10,
    )
    scrollbar = tk.Scrollbar(text_frame, command=body.yview)
    body.configure(yscrollcommand=scrollbar.set)
    body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    body.insert("1.0", text or "")
    body.configure(state=tk.DISABLED)

    buttons = tk.Frame(win, bg=_C["bg_dark"])
    buttons.pack(fill=tk.X, padx=14, pady=(0, 14))

    def copy_all() -> None:
        payload = text or ""
        if on_copy is not None:
            on_copy(payload)
            win.destroy()
            return
        try:
            win.clipboard_clear()
            win.clipboard_append(payload)
        except tk.TclError:
            pass

    if copyable:
        tk.Button(
            buttons,
            text="复制全部",
            command=copy_all,
            bg=_C["bg_light"],
            fg=_C["text_primary"],
            relief=tk.FLAT,
            padx=14,
            pady=5,
            cursor="hand2",
            font=(_F["family"], _F["size_sm"]),
        ).pack(side=tk.LEFT)
    tk.Button(
        buttons,
        text="关闭",
        command=win.destroy,
        bg=_C["accent"],
        fg="white",
        relief=tk.FLAT,
        padx=18,
        pady=5,
        cursor="hand2",
        font=(_F["family"], _F["size_base"]),
    ).pack(side=tk.RIGHT)

    _center_on_parent(win, parent)
    win.grab_set()
    win.wait_window()


def _non_empty(value: str) -> Optional[str]:
    """校验器：非空。返回错误文案或 None。"""
    return None if value else "内容不能为空"


# ====================================================================== 消息弹窗
#
# 全仓的 `messagebox.*` 调用**统一走这里**（2026-09-17 收口，此前散落在 27 个文件、
# 217 处，每个文件各自 `from tkinter import messagebox`）。
#
# ## 为什么要收口，而不是"反正只是弹个框"
#
# 1. **一个改点**：以后要把原生弹窗换成主题化的自绘对话框、要给弹窗加"不再提示"、
#    要在弹窗上做埋点 —— 都只改这一个文件，而不是再翻 27 个文件。
#    （原生 messagebox 在深色主题下是浅色的，这是迟早要做的事。）
# 2. **自动化可开关**：模态弹窗是自动化的大敌 —— 截图脚本为了不被卡死，
#    只能去 monkeypatch `tkinter.messagebox` 的内部属性（脆、且要写对每个方法名。
#    实测漏了 `askinteger` 就被卡 14 分钟）。现在有 `set_silent()` / `silent_modals()`。
# 3. **使用政策有地方写**：`ui_kit` 的 toast / `StatusBar` 才是"操作结果"的默认表达，
#    模态只留给**需要用户决定**的场景（删除、覆盖、不可逆操作）。
#
# ## 为什么是"与 messagebox 同签名"
#
# `showinfo(title, message, **options)` 的参数顺序、返回值、选项名都与
# `tkinter.messagebox` 完全一致 ⇒ 调用点只需把 `messagebox.` 换成 `dialogs.`，
# **不改变任何可见行为**，171 处替换因此可以机械完成并逐条复核。
# 想要更好的默认值（标题、parent）时用下面那组语义化函数（`info` / `warn` / ...）。

#: 语义化接口的默认标题
APP_TITLE = "AI小说创作工坊"

_silent = False
_silent_depth = 0


def set_silent(value: bool) -> bool:
    """开关"静默模式"，返回此前的值（便于调用方恢复）。

    静默下：`show*` 直接返回、不弹窗；`ask*` 返回**安全默认**（`False` = 不做那件事）。
    自动化脚本、UI 冒烟、批量演示用它替代 monkeypatch。
    """
    global _silent
    previous = _silent
    _silent = bool(value)
    return previous


def is_silent() -> bool:
    """当前是否静默（供测试与调用方判断）。"""
    return _silent


class silent_modals:
    """`with silent_modals(): ...` —— 作用域内静默，异常也保证恢复（可嵌套）。

    ❗ **只恢复自己见过的状态，不无条件置回 `False`**。
    旧实现用 `_silent_depth` 计数，`__exit__` 在深度归零时直接 `set_silent(False)`。
    于是下面这种用法会**丢掉外层的静默**：

        set_silent(True)            # 用户在别处开了全局静默
        with silent_modals():       # depth 0→1
            ...
        # __exit__：depth 归零 → set_silent(False)  ⇒ 外层那个 True 被抹掉

    对"全局静默了却突然弹出模态框"的自动化脚本，这正是最伤的场景。
    改为像 BLAS 那样**只置位自己那一层**：进入前记下原值，退出时恢复原值。
    """

    def __init__(self) -> None:
        self._previous: bool | None = None

    def __enter__(self) -> "silent_modals":
        global _silent_depth
        _silent_depth += 1
        self._previous = set_silent(True)
        return self

    def __exit__(self, *_exc) -> bool:
        global _silent_depth
        _silent_depth = max(0, _silent_depth - 1)
        # 恢复进入前的状态：若外层本来就是静默的，退出后仍然是静默的。
        if self._previous is not None:
            set_silent(self._previous)
        return False


def _messagebox():
    """延迟取得 `tkinter.messagebox`。

    不在模块顶层 import：本模块要能在**无 Tk 的环境**（CI / 服务器 / 单测）被导入，
    与本文件开头"import 时触碰任何 Tk API"的承诺一致。
    """
    from tkinter import messagebox

    return messagebox


# ---- 同签名层（迁移用，行为与 messagebox 完全一致）--------------------


def showinfo(title: str, message: str = "", **options) -> Optional[str]:
    """同 `messagebox.showinfo`。"""
    if _silent:
        return None
    return _messagebox().showinfo(title, message, **options)


def showwarning(title: str, message: str = "", **options) -> Optional[str]:
    """同 `messagebox.showwarning`。"""
    if _silent:
        return None
    return _messagebox().showwarning(title, message, **options)


def showerror(title: str, message: str = "", **options) -> Optional[str]:
    """同 `messagebox.showerror`。"""
    if _silent:
        return None
    return _messagebox().showerror(title, message, **options)


def askyesno(title: str, message: str = "", **options) -> bool:
    """同 `messagebox.askyesno`；静默时返回 `False`（不做破坏性动作）。"""
    if _silent:
        return False
    return bool(_messagebox().askyesno(title, message, **options))


# ---- 语义化层（新代码用）--------------------------------------------


def info(message: str, *, title: str = APP_TITLE, parent=None) -> None:
    """告知类提示。⚠️ 能用 `ui_kit.toast` / `StatusBar` 就不要用模态（会打断操作流）。"""
    showinfo(title, message, parent=parent)


def warn(message: str, *, title: str = APP_TITLE, parent=None) -> None:
    """警告类提示（用户需要知道，但无需做决定）。"""
    showwarning(title, message, parent=parent)


def error(message: str, *, title: str = APP_TITLE, parent=None) -> None:
    """错误类提示。"""
    showerror(title, message, parent=parent)


def confirm(message: str, *, title: str = APP_TITLE, parent=None, default: bool = False) -> bool:
    """确认类弹窗 —— **模态只该用在这里**（删除 / 覆盖 / 不可逆操作）。

    静默时返回 `default`（默认 `False`），绝不替用户默认"同意"。
    """
    if _silent:
        return default
    return bool(_messagebox().askyesno(title, message, parent=parent))
