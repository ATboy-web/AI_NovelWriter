"""同构对话框 helper（v3 A8）。

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
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional

from .ui_style import UIStyle

__all__ = ["ask_text", "edit_items", "show_text"]

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
