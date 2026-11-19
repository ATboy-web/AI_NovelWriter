"""滚动容器工具：把滚轮事件绑到整棵子树。

## 为什么单独一个模块

`ui_style.py` 是**纯设计令牌**（颜色/字体/圆角），刻意不依赖 `tkinter` 与 `logger`
（文件头写明"本模块现在只用 ttk"）。滚轮绑定需要 `tk.TclError` 与日志，
放进去会破坏那个约定，也让"样式模块"变成一个什么都干的杂物间。

## 要解决的问题（实测）

左栏 canvas 原来只绑了 3 个 widget：

    left_canvas.bind("<MouseWheel>", on_left_scroll)
    left_panel.bind("<MouseWheel>", on_left_scroll)
    left_scrollbar.bind("<MouseWheel>", on_left_scroll)

Tk 的 `<MouseWheel>` **不冒泡**：事件发给鼠标正下方的控件，不会向上传递。
而左栏里几乎全是 Button / Label —— 用户的鼠标必然落在它们身上：

    滚轮发给按钮「自动创作」→ ❌ 无效（0.000 → 0.000，纹丝不动）
    对照：滚轮发给 canvas 本身 → 有效（0.000 → 0.060）

而左栏内容占 **1.67 屏**高 ⇒ 表现为"滚轮功能不存在"，只能去拖 8px 宽的滚动条。
"""

from __future__ import annotations

import tkinter as tk

from loguru import logger

__all__ = ["bind_wheel_to_tree"]


def bind_wheel_to_tree(widget, handler) -> int:
    """把 `<MouseWheel>` 绑到 `widget` 及其**全部后代**，返回绑定的控件数。

    ❗ Tk 的滚轮事件不冒泡：只绑 canvas/frame 等于"只有鼠标正好停在空白处才滚"。
    而容器里往往铺满按钮/标签，用户几乎不可能命中空白 —— 表现为"滚轮失灵"。

    ⚠️ **时序**：必须在内容构建**完成之后**调用。若在容器刚创建时调用，
    递归那一刻它还没有子控件，等于绑了个空壳（实测修复后仍是 0.000 → 0.000）。
    动态重建内容后也需要重新调用（新控件不在旧绑定里）。

    返回值用于自检"到底绑上了几个"——本次就是靠它发现第一次绑了个空壳。
    """
    count = 0
    try:
        widget.bind("<MouseWheel>", handler)
        count += 1
    except tk.TclError:
        # 控件已销毁 / 该类控件不接受事件绑定：记 debug 而不是静默吞
        # （本仓 `test_no_silent_swallow` 要求宽泛 except 必须登记理由）
        logger.debug("[ui_scroll] 跳过滚轮绑定（控件不可绑）: %s", type(widget).__name__)

    try:
        children = widget.winfo_children()
    except tk.TclError:
        logger.debug("[ui_scroll] 跳过子树遍历（控件已销毁）: %s", type(widget).__name__)
        return count

    for child in children:
        count += bind_wheel_to_tree(child, handler)
    return count
