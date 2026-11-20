"""主题切换 —— 让**已经建好**的整棵控件树即时换肤。

## 为什么需要遍历

ttk 控件由全局样式表驱动，`UIStyle.apply_theme` 重配置后自动生效；
但 tk 经典控件（Label/Button/Text/Canvas/Listbox/Frame…）的颜色是
**创建时写进控件选项的**，样式表管不到它们。本模块用"旧调色板值 →
新调色板值"的映射遍历整棵控件树（含所有 Toplevel），把命中旧值的
选项换成新值 —— 因为全仓颜色单一来源于 `UIStyle.COLORS`，
凡主题色必命中映射，凡语义常量（"white"/"#ffd700" 等）必不命中。

覆盖范围：
- 常规颜色选项（bg/fg/active*/select*/insertbackground/troughcolor/
  highlight*/disabledforeground/selectcolor/readonlybackground）
- `tk.Text` 与 `ttk.Treeview` 的 **tag 颜色**（斑马纹、语法高亮、选中色）
- `tk.Canvas` 的**图元颜色**（fill/outline 及其 active/disabled 变体）
- `ui_kit.add_hover` 存在 `_ui_hover` 里的悬停色引用（字符串按映射更新，
  callable 活引用不动）
- Combobox 下拉列表的 option 数据库（重跑 `ui_kit.apply_widget_theme`）

不碰布局、不碰业务数据、不重建控件 —— 纯外观横切。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from loguru import logger

from app import theme_system
from app.ui_style import UIStyle

#: 逐控件尝试的颜色选项（不同控件支持集不同，cget 失败即跳过）
_COLOR_OPTIONS = (
    "bg",
    "fg",
    "activebackground",
    "activeforeground",
    "disabledforeground",
    "selectbackground",
    "selectforeground",
    "insertbackground",
    "troughcolor",
    "highlightbackground",
    "highlightcolor",
    "selectcolor",
    "readonlybackground",
)

#: Canvas 图元的颜色选项
_CANVAS_ITEM_OPTIONS = ("fill", "outline", "activefill", "disabledfill", "activeoutline", "disabledoutline")

#: Text/Treeview tag 的颜色选项
_TAG_OPTIONS = ("foreground", "background")


def _swap_option(widget: tk.Misc, option: str, mapping: dict[str, str]) -> bool:
    try:
        current = str(widget.cget(option)).strip().lower()
    except (tk.TclError, AttributeError, KeyError):
        return False
    new = mapping.get(current)
    if new is None or new.lower() == current:
        return False
    try:
        widget.configure(**{option: new})
        return True
    except tk.TclError:
        return False


def _swap_tags(widget: tk.Misc, mapping: dict[str, str]) -> int:
    """Text / Treeview 的 tag 颜色换肤。返回改动的 tag 选项数。"""
    changed = 0
    try:
        tags = widget.tag_names()
    except (tk.TclError, AttributeError):
        return 0
    for tag in tags:
        for option in _TAG_OPTIONS:
            try:
                current = str(widget.tag_cget(tag, option)).strip().lower()
            except (tk.TclError, AttributeError, KeyError):
                continue
            new = mapping.get(current)
            if new is None or new.lower() == current:
                continue
            try:
                widget.tag_configure(tag, **{option: new})
                changed += 1
            except tk.TclError:
                pass
    return changed


def _swap_canvas_items(canvas: tk.Canvas, mapping: dict[str, str]) -> int:
    changed = 0
    try:
        items = canvas.find_all()
    except tk.TclError:
        return 0
    for item in items:
        for option in _CANVAS_ITEM_OPTIONS:
            try:
                current = str(canvas.itemcget(item, option)).strip().lower()
            except tk.TclError:
                continue
            new = mapping.get(current)
            if not current or new is None or new.lower() == current:
                continue
            try:
                canvas.itemconfigure(item, **{option: new})
                changed += 1
            except tk.TclError:
                pass
    return changed


def _swap_hover_refs(widget: tk.Misc, mapping: dict[str, str]) -> None:
    refs = getattr(widget, "_ui_hover", None)
    if not isinstance(refs, tuple) or len(refs) != 2:
        return
    updated = []
    for ref in refs:
        if isinstance(ref, str):
            updated.append(mapping.get(ref.strip().lower(), ref))
        else:
            updated.append(ref)  # callable 活引用：事件触发时读活调色板
    widget._ui_hover = tuple(updated)  # type: ignore[attr-defined]


def retheme_widgets(root: tk.Misc, old: dict[str, str], new: dict[str, str]) -> int:
    """把整棵控件树里命中旧调色板的颜色换成新调色板。返回触及的控件数。"""
    mapping = theme_system.palette_swap_map(old, new)
    touched = 0
    stack: list[tk.Misc] = [root]
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            continue

        hit = False
        # ttk 控件的颜色由样式表驱动（apply_theme 已重配置），
        # 只有 Treeview 的 tag 是逐控件数据，需要单独换。
        if isinstance(widget, ttk.Treeview):
            hit = _swap_tags(widget, mapping) > 0
        elif isinstance(widget, ttk.Widget):
            pass
        else:
            for option in _COLOR_OPTIONS:
                if _swap_option(widget, option, mapping):
                    hit = True
            if isinstance(widget, tk.Text):
                hit = _swap_tags(widget, mapping) > 0 or hit
            elif isinstance(widget, tk.Canvas):
                hit = _swap_canvas_items(widget, mapping) > 0 or hit
        _swap_hover_refs(widget, mapping)
        if hit:
            touched += 1
    return touched


def switch_theme(root: tk.Misc, theme_id: str, config=None) -> str:
    """切换主题：激活调色板 → 重配 ttk 样式 → 遍历改色 →（可选）持久化。

    - `config` 传入 AppConfig 时把选择写进配置（原子写由配置层保证）；
      不传则只改本次会话外观（设置对话框"预览"用法）。
    - 返回归一后的主题 id；非法值回落默认主题，绝不抛异常。
    - 幂等：重复切到同一主题不产生副作用。
    """
    tid = theme_system.normalize_theme(theme_id)
    if tid == UIStyle.ACTIVE_THEME:
        if config is not None:
            config.set("theme", tid)
        return tid

    old = dict(UIStyle.COLORS)
    UIStyle.set_palette(tid)
    try:
        UIStyle.apply_theme(root)
        # Treeview/焦点环/Combobox 下拉 option 数据库
        from app.panels import ui_kit

        ui_kit.apply_widget_theme(root)
        touched = retheme_widgets(root, old, UIStyle.COLORS)
        logger.info(f"[主题] 已切换到 {tid}（{theme_system.THEME_META[tid]['name_cn']}），触及 {touched} 个控件")
    except tk.TclError as exc:
        # 无显示环境（测试替身）下样式配置可能失败：调色板已切换，
        # 控件改色尽力而为，不让换肤把调用方炸掉。
        logger.debug(f"[主题] 控件树换肤跳过（无显示环境或控件已销毁）: {exc}")
    if config is not None:
        config.set("theme", tid)
    return tid
