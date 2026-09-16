"""面板 UI 组件库（v3 §2.5）—— 让 15 个面板长成**同一套语言**。

## 为什么需要它

2026-09-16 的界面体检（`tests/_ui_metrics.py` 可复现）显示问题不在"某个面板没画好"，
而在**没有共享的视觉与交互语言**：

| 度量 | 改造前 | 后果 |
|---|---|---|
| `text_muted` 对比度 | `bg_card` 上 **2.68:1** | 全应用提示文字发灰难认 |
| `messagebox` 调用 | **64 处** | 每次提示都打断操作流 |
| 键盘绑定 | 全仓 **5 个** | 只能靠鼠标，重复操作成本高 |
| 进度指示 | **0 个** | 长任务期间界面像卡死 |
| 面板控件数 | 记忆可视化 **6 个** | 谈不上信息结构 |
| Treeview 主题 | **未配置**（clam 默认灰） | 列表与暗色主题冲突 |

所以这里提供的是**一套组件**，而不是给某个面板打补丁：卡片、工具栏、搜索框、
空态、状态栏、轻提示、可滚动容器、KPI 小块、徽标、Treeview 主题。
面板只负责"放什么内容"，"长什么样、怎么交互"由这里统一。

## 使用约定

- 颜色/字体一律走 `UIStyle.COLORS` / `UIStyle.font(...)`，**不要写字面值**
  （`tests/test_font_token_ratchet.py` 的棘轮会拦）；
- 间距一律用 `SPACE`（来自 `UIStyle.SPACING`），不要再写裸数字；
- 提示优先用 `toast` / `StatusBar`，`messagebox` 只留"需要用户确认"的场景。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Mapping, Sequence

from loguru import logger

from app.ui_style import UIStyle

C = UIStyle.COLORS

#: 间距刻度（4px 基准，直接复用既有设计令牌）
SPACE: dict[str, int] = UIStyle.SPACING

#: 交互控件的**最小点击高**（低于此值鼠标很难点中；实测本仓按钮原本都 ≥26，保持一致）
MIN_TARGET_HEIGHT = 26

#: Treeview 行高（默认 20 太挤，中文更显拥挤）
TREE_ROW_HEIGHT = 28


# ====================================================================== 主题


def apply_widget_theme(root: tk.Misc) -> None:
    """补齐 `UIStyle.apply_theme` 没覆盖的部分（**Treeview / 焦点环 / 悬停**）。

    `apply_theme` 已经处理了 Frame/Label/Button/Combobox/Scrollbar/Scale，
    唯独 **Treeview 没有配置** —— 于是 4 个 Treeview 用的是 clam 默认灰底，
    与暗色皮肤明显冲突。这里补齐，并在 `PanelHost` 建好后调用一次。
    """
    try:
        style = ttk.Style()
    except tk.TclError:  # pragma: no cover - 无显示环境
        return

    style.configure(
        "Panel.Treeview",
        background=C["bg_card"],
        fieldbackground=C["bg_card"],
        foreground=C["text_primary"],
        rowheight=TREE_ROW_HEIGHT,
        borderwidth=0,
        font=UIStyle.font("label"),
    )
    style.configure(
        "Panel.Treeview.Heading",
        background=C["bg_medium"],
        foreground=C["text_secondary"],
        relief="flat",
        font=UIStyle.font("label_bold"),
        padding=(SPACE["sm"], SPACE["sm"]),
    )
    style.map(
        "Panel.Treeview",
        background=[("selected", C["accent"])],
        foreground=[("selected", "white")],
    )
    style.map(
        "Panel.Treeview.Heading",
        background=[("active", C["hover_light"])],
        foreground=[("active", C["text_primary"])],
    )
    style.configure("Panel.TSeparator", background=C["border"])
    # 输入控件的焦点环：不设的话聚焦时是一圈系统白边，很突兀
    style.configure("Panel.TEntry", fieldbackground=C["bg_medium"], foreground=C["text_primary"], borderwidth=0)
    style.map("Panel.TEntry", bordercolor=[("focus", C["border_focus"])])

    # Combobox 点开后弹出的列表是一个**独立的 tk Listbox**（不在面板控件树里，
    # polish_legacy 够不着），只能靠 option 数据库全局着色，否则下拉一片白
    try:
        root.option_add("*TCombobox*Listbox.background", C["bg_medium"])
        root.option_add("*TCombobox*Listbox.foreground", C["text_primary"])
        root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", UIStyle.font("label"))
    except (tk.TclError, AttributeError):  # 无显示环境 / 测试替身控件没有 option_add
        pass


# ====================================================================== 基础件


def card(
    parent: tk.Misc,
    title: str | None = None,
    subtitle: str | None = None,
    *,
    pad: int | None = None,
    bg: str | None = None,
) -> dict[str, Any]:
    """一张卡片：细边框 + 内边距 +（可选）标题区。返回 `{"frame", "body", "title_bg"}`。

    Tk 没有圆角，用"细边框 + 留白 + 标题层级"营造卡片感 —— 比裸 `Frame` 好得多，
    且不引入图片/CSS 之类额外依赖。
    """
    pad = SPACE["lg"] if pad is None else pad
    card_bg = bg or C["bg_card"]
    frame = tk.Frame(parent, bg=card_bg, highlightbackground=C["border"], highlightthickness=1, bd=0)
    body = tk.Frame(frame, bg=card_bg)
    body.pack(fill=tk.BOTH, expand=True, padx=pad, pady=pad)
    if title:
        head = tk.Frame(body, bg=card_bg)
        head.pack(fill=tk.X, pady=(0, SPACE["sm"]))
        tk.Label(head, text=title, bg=card_bg, fg=C["text_primary"], font=UIStyle.font("subtitle_bold")).pack(
            side=tk.LEFT
        )
        if subtitle:
            tk.Label(head, text=subtitle, bg=card_bg, fg=C["text_muted"], font=UIStyle.font("caption")).pack(
                side=tk.LEFT, padx=(SPACE["sm"], 0)
            )
    return {"frame": frame, "body": body, "title_bg": card_bg}


def section_title(parent: tk.Misc, text: str, *, bg: str | None = None) -> tk.Label:
    """小节标题（比正文大一号、加粗），用来建立层级。"""
    label = tk.Label(
        parent,
        text=text,
        bg=bg or C["bg_dark"],
        fg=C["text_primary"],
        font=UIStyle.font("subtitle_bold"),
        anchor=tk.W,
    )
    return label


def hint(parent: tk.Misc, text: str, *, bg: str | None = None) -> tk.Label:
    """说明/提示文字（用已修正对比度的 `text_muted`）。"""
    return tk.Label(
        parent,
        text=text,
        bg=bg or C["bg_dark"],
        fg=C["text_muted"],
        font=UIStyle.font("caption"),
        anchor=tk.W,
        justify=tk.LEFT,
    )


_KIND_STYLE = {
    "primary": (C["accent"], "white", C["accent_hover"], C["accent"]),
    "secondary": (C["bg_light"], C["text_primary"], C["hover"], C["border_light"]),
    "ghost": (C["bg_medium"], C["text_secondary"], C["hover"], C["bg_medium"]),
    "danger": (C["error"], "white", "#dc2626", C["error"]),
}


def button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], Any] | None = None,
    *,
    kind: str = "secondary",
    width: int | None = None,
    padx: int | None = None,
    pady: int | None = None,
) -> tk.Button:
    """统一样式的按钮：角色字体、手型光标、悬停反馈、满足最小点击高度。"""
    bg, fg, hover_bg, active_bg = _KIND_STYLE.get(kind, _KIND_STYLE["secondary"])
    widget = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=fg,
        disabledforeground=C["text_muted"],
        font=UIStyle.font("label"),
        relief=tk.FLAT,
        bd=0,
        cursor="hand2",
        padx=SPACE["md"] if padx is None else padx,
        pady=SPACE["sm"] if pady is None else pady,
        highlightthickness=0,
    )
    if width:
        widget.configure(width=width)
    add_hover(widget, bg, hover_bg)
    return widget


def add_hover(widget: tk.Misc, normal: str, hover: str) -> None:
    """悬停高亮（`<Enter>/<Leave>`），并在销毁后不再回调（避免 TclError）。"""

    def on_enter(_event=None) -> None:
        try:
            widget.configure(bg=hover)
        except tk.TclError:
            pass

    def on_leave(_event=None) -> None:
        try:
            widget.configure(bg=normal)
        except tk.TclError:
            pass

    widget.bind("<Enter>", on_enter, add="+")
    widget.bind("<Leave>", on_leave, add="+")


def toolbar(parent: tk.Misc, *, bg: str | None = None) -> dict[str, tk.Frame]:
    """工具栏：`left` 放主操作、`right` 放次要操作（左右对齐让视线有落点）。"""
    bar = tk.Frame(parent, bg=bg or C["bg_dark"])
    left = tk.Frame(bar, bg=bg or C["bg_dark"])
    right = tk.Frame(bar, bg=bg or C["bg_dark"])
    left.pack(side=tk.LEFT)
    right.pack(side=tk.RIGHT)
    return {"bar": bar, "left": left, "right": right}


def search_entry(
    parent: tk.Misc,
    variable: tk.StringVar,
    *,
    placeholder: str = "搜索…",
    on_change: Callable[[], Any] | None = None,
    width: int = 24,
    bg: str | None = None,
) -> dict[str, Any]:
    """带占位符与清除按钮的搜索框（并标记为 Ctrl+F 的聚焦目标）。"""
    container_bg = bg or C["bg_dark"]
    holder = tk.Frame(parent, bg=C["bg_medium"], highlightbackground=C["border"], highlightthickness=1, bd=0)
    entry = tk.Entry(
        holder,
        textvariable=variable,
        bg=C["bg_medium"],
        fg=C["text_primary"],
        insertbackground=C["text_primary"],
        font=UIStyle.font("label"),
        relief=tk.FLAT,
        width=width,
        highlightthickness=0,
    )
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(SPACE["sm"], 0), pady=SPACE["xs"])

    def clear() -> None:
        variable.set("")
        entry.focus_set()
        if on_change:
            on_change()

    clear_btn = tk.Label(
        holder,
        text="✕",
        bg=C["bg_medium"],
        fg=C["text_muted"],
        font=UIStyle.font("caption"),
        cursor="hand2",
        padx=SPACE["sm"],
    )
    clear_btn.pack(side=tk.RIGHT)
    clear_btn.bind("<Button-1>", lambda _e: clear())

    if on_change:
        variable.trace_add("write", lambda *_: on_change())
    #: 供宿主 `Ctrl+F` 定位（见 `BasePanel.focus_search`）
    entry._ui_kit_search = True  # type: ignore[attr-defined]
    return {"frame": holder, "entry": entry, "clear": clear_btn, "bg": container_bg}


def empty_state(
    parent: tk.Misc,
    title: str,
    detail: str = "",
    *,
    glyph: str = "◌",
    action_text: str | None = None,
    action_command: Callable[[], Any] | None = None,
    bg: str | None = None,
) -> tk.Frame:
    """空态：说清"现在没有内容"和"下一步该做什么"。

    比"什么都不显示"或"只打印一行日志"好：用户不会以为功能坏了。
    """
    container_bg = bg or C["bg_dark"]
    frame = tk.Frame(parent, bg=container_bg)
    tk.Label(frame, text=glyph, bg=container_bg, fg=C["border_light"], font=(UIStyle.FONTS["family"], 30)).pack(
        pady=(SPACE["xl"], SPACE["sm"])
    )
    tk.Label(frame, text=title, bg=container_bg, fg=C["text_secondary"], font=UIStyle.font("body")).pack()
    if detail:
        tk.Label(
            frame,
            text=detail,
            bg=container_bg,
            fg=C["text_muted"],
            font=UIStyle.font("caption"),
            justify=tk.CENTER,
            wraplength=420,
        ).pack(pady=(SPACE["xs"], SPACE["md"]))
    if action_text and action_command:
        button(frame, action_text, action_command, kind="primary").pack()
    return frame


class StatusBar:
    """内联状态栏：把"操作结果"显示在界面上，代替 messagebox 打断。

    用法：`self._status.set("已写入 3 条事件", kind="ok")`。
    """

    _KINDS = {
        "info": ("text_secondary", "●"),
        "ok": ("success_text", "✔"),
        "warn": ("warning_text", "▲"),
        "error": ("error_text", "✖"),
    }

    def __init__(self, parent: tk.Misc, *, bg: str | None = None, width: int | None = None) -> None:
        self._bg = bg or C["bg_dark"]
        self.frame = tk.Frame(parent, bg=self._bg)
        self._icon = tk.Label(self.frame, text="", bg=self._bg, fg=C["text_muted"], font=UIStyle.font("caption"))
        self._icon.pack(side=tk.LEFT)
        self._label = tk.Label(
            self.frame,
            text="",
            bg=self._bg,
            fg=C["text_secondary"],
            font=UIStyle.font("caption"),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=width or 900,
        )
        self._label.pack(side=tk.LEFT, padx=(SPACE["xs"], 0), fill=tk.X, expand=True)

    def set(self, text: str, kind: str = "info") -> None:
        color, glyph = self._KINDS.get(kind, self._KINDS["info"])
        try:
            self._icon.configure(text=glyph, fg=C[color])
            self._label.configure(text=text, fg=C["text_secondary"] if kind == "info" else C[color])
        except tk.TclError:
            pass

    def clear(self) -> None:
        self.set("")


def toast(widget: tk.Misc, message: str, *, kind: str = "info", ms: int = 2600) -> None:
    """轻提示：浮在主窗口右上角，**不抢焦点、不阻塞**，到点自动消失。

    用来替代"什么都弹一个 messagebox"（全仓 64 处）。需要用户**确认**的场景仍用
    `messagebox.askyesno` —— 那类弹窗是合理的。
    """
    try:
        root = widget.winfo_toplevel()
        top = tk.Toplevel(root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        color_key = {"info": "info_text", "ok": "success_text", "warn": "warning_text", "error": "error_text"}.get(
            kind, "info_text"
        )
        frame = tk.Frame(top, bg=C["bg_light"], highlightbackground=C[color_key], highlightthickness=1, bd=0)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            frame,
            text=message,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=UIStyle.font("label"),
            padx=SPACE["lg"],
            pady=SPACE["md"],
            justify=tk.LEFT,
            wraplength=420,
        ).pack()

        root.update_idletasks()
        x = root.winfo_rootx() + root.winfo_width() - 460
        y = root.winfo_rooty() + 70
        top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        top.after(ms, lambda: _safe_destroy(top))
    except (tk.TclError, RuntimeError) as exc:  # pragma: no cover - 无显示环境
        logger.debug(f"[ui_kit] toast 失败（忽略）: {exc}")


def _safe_destroy(window: tk.Misc) -> None:
    try:
        window.destroy()
    except tk.TclError:
        pass


def badge(parent: tk.Misc, text: str, *, kind: str = "info", bg: str | None = None) -> tk.Label:
    """小徽标（状态/计数），用于列表行或标题旁。"""
    color_key = {
        "info": "info_text",
        "ok": "success_text",
        "warn": "warning_text",
        "error": "error_text",
        "muted": "text_muted",
    }.get(kind, "info_text")
    return tk.Label(
        parent,
        text=text,
        bg=bg or C["bg_medium"],
        fg=C[color_key],
        font=UIStyle.font("caption"),
        padx=SPACE["sm"],
        pady=1,
    )


def kpi_row(parent: tk.Misc, items: Sequence[tuple[str, str]], *, bg: str | None = None) -> tk.Frame:
    """一排"指标小块"（标签 + 数值）。比一行长文本更易扫读。

    返回的 Frame 上挂有 `value_labels`（与各小块数值对应的 Label 列表，
    顺序同 `items`）—— 刷新数值时**直接 configure 这些 Label**。
    不要靠"比对字体找 Label"来定位：`cget("font")` 返回的是 Tcl 字体名，
    与 `UIStyle.font()` 的元组永远不相等（这个坑让 KPI 一度永远显示占位符）。
    """
    container_bg = bg or C["bg_dark"]
    row = tk.Frame(parent, bg=container_bg)
    value_labels: list[tk.Label] = []
    for index, (label, value) in enumerate(items):
        cell = tk.Frame(row, bg=C["bg_card"], highlightbackground=C["border"], highlightthickness=1, bd=0)
        cell.pack(side=tk.LEFT, padx=(0 if index == 0 else SPACE["sm"], 0), fill=tk.X, expand=True)
        value_label = tk.Label(cell, text=str(value), bg=C["bg_card"], fg=C["text_primary"], font=UIStyle.font("title"))
        value_label.pack(anchor=tk.W, padx=SPACE["md"], pady=(SPACE["sm"], 0))
        value_labels.append(value_label)
        tk.Label(cell, text=label, bg=C["bg_card"], fg=C["text_muted"], font=UIStyle.font("caption")).pack(
            anchor=tk.W, padx=SPACE["md"], pady=(0, SPACE["sm"])
        )
    row.value_labels = value_labels  # type: ignore[attr-defined]
    return row


def scrollable(parent: tk.Misc, *, bg: str | None = None, height: int | None = None) -> dict[str, Any]:
    """可滚动容器。返回 `{"frame", "canvas", "inner"}`，内容放进 `inner`。

    内容不超高时滚动条自动隐藏（否则会常驻一条灰色竖条，很难看）。
    """
    container_bg = bg or C["bg_dark"]
    frame = tk.Frame(parent, bg=container_bg)
    canvas = tk.Canvas(frame, bg=container_bg, highlightthickness=0, bd=0, height=height or 0)
    scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview, style="Dark.Vertical.TScrollbar")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    inner = tk.Frame(canvas, bg=container_bg)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")

    def on_inner_configure(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        _sync_scrollbar()

    def on_canvas_configure(event) -> None:
        canvas.itemconfigure(window, width=event.width)
        _sync_scrollbar()

    def _sync_scrollbar() -> None:
        try:
            needed = inner.winfo_reqheight() > canvas.winfo_height()
        except tk.TclError:
            return
        if needed and not scrollbar.winfo_ismapped():
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        elif not needed and scrollbar.winfo_ismapped():
            scrollbar.pack_forget()

    inner.bind("<Configure>", on_inner_configure)
    canvas.bind("<Configure>", on_canvas_configure)
    # 鼠标滚轮只在指针位于容器内时生效，避免抢别处的滚动
    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel(canvas)))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
    return {"frame": frame, "canvas": canvas, "inner": inner, "scrollbar": scrollbar}


def _wheel(canvas: tk.Canvas) -> Callable[[tk.Event], None]:
    def handler(event: tk.Event) -> None:
        try:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    return handler


# ====================================================================== 表格


def pretty_tree(
    parent: tk.Misc,
    columns: Sequence[str],
    widths: Sequence[int] | None = None,
    *,
    on_double: Callable[[tk.Event], Any] | None = None,
    on_select: Callable[[tk.Event], Any] | None = None,
    height: int = 14,
    sortable: bool = True,
    bg: str | None = None,
) -> dict[str, Any]:
    """统一风格的表格：斑马纹、28px 行高、表头可点击排序、按 Enter 触发双击动作。

    Tk 的 Treeview 默认 20px 行高 + clam 灰底，中文显得又挤又脏；这里统一到
    `Panel.Treeview` 样式（见 `apply_widget_theme`），并补上排序与键盘操作。
    """
    container_bg = bg or C["bg_dark"]
    holder = tk.Frame(parent, bg=container_bg)
    tree = ttk.Treeview(holder, columns=list(columns), show="headings", height=height, style="Panel.Treeview")
    tree.tag_configure("odd", background=C["bg_card"])
    tree.tag_configure("even", background=C["bg_medium"])
    tree.tag_configure("muted", foreground=C["text_muted"])

    for index, name in enumerate(columns):
        width = widths[index] if widths and index < len(widths) else 120
        tree.heading(name, text=name)
        tree.column(name, width=width, anchor=tk.W, stretch=True)

    scrollbar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=tree.yview, style="Dark.Vertical.TScrollbar")
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    if on_double:
        tree.bind("<Double-1>", on_double)
        tree.bind("<Return>", on_double)  # 键盘等效操作
    if on_select:
        tree.bind("<<TreeviewSelect>>", on_select)

    state = {"sort_column": None, "descending": False}

    def sort_by(column: str) -> None:
        descending = state["sort_column"] == column and not state["descending"]
        rows = [(tree.set(item, column), item) for item in tree.get_children("")]

        def key(pair: tuple[str, str]) -> tuple:
            raw = pair[0].strip()
            try:
                return (0, float(raw.replace(",", "").replace("章", "").replace("处", "") or 0))
            except ValueError:
                return (1, raw)

        rows.sort(key=key, reverse=descending)
        for index, (_, item) in enumerate(rows):
            tree.move(item, "", index)
        state["sort_column"], state["descending"] = column, descending

    if sortable:
        for name in columns:
            tree.heading(name, command=lambda n=name: sort_by(n))
    return {"frame": holder, "tree": tree, "scrollbar": scrollbar, "sort_by": sort_by}


def fill_tree(
    tree: ttk.Treeview, rows: Iterable[tuple[str, tuple]], *, children_of: Mapping[str, str] | None = None
) -> None:
    """填充表格：自动套斑马纹；`children_of` 指定 iid → 父 iid 的嵌套关系。"""
    for item in tree.get_children(""):
        tree.delete(item)
    children_of = children_of or {}
    for index, (iid, values) in enumerate(rows):
        parent = children_of.get(iid, "")
        tags = ["odd" if index % 2 else "even"]
        tree.insert(parent, tk.END, iid=iid, values=values, tags=tuple(tags), open=True)


# ====================================================================== 键盘


def bind_shortcuts(widget: tk.Misc, mapping: Mapping[str, Callable[[], Any]]) -> None:
    """批量绑定快捷键（`{"<F5>": refresh, "<Control-f>": focus}`）。"""
    for sequence, handler in mapping.items():
        widget.bind(sequence, lambda _event, fn=handler: fn())


# ====================================================================== 迁移面板的润色


def _configure_supported(widget: tk.Misc, **options: Any) -> int:
    """只设置控件**真正支持**的选项，返回实际生效的项数。

    为什么不能直接 `configure(**options)`：`tk` 与 `ttk` 的选项集不同 ——
    `ttk.Entry` / `ttk.Combobox` 没有 `insertbackground`，直接传会抛
    `unknown option`，进而整套润色在那一个控件上中断（实测踩到）。
    """
    try:
        supported = set(widget.keys())
    except tk.TclError:
        return 0
    # `ttk` 控件的 `keys()` 不含 "style"（它由 themed engine 维护，不在选项列表里），
    # 但 `configure(style=...)` 是完全合法的 —— 对它放行，否则换肤永远被过滤掉
    supported.add("style")
    usable = {key: value for key, value in options.items() if key in supported}
    if not usable:
        return 0
    try:
        widget.configure(**usable)
    except tk.TclError as exc:
        logger.debug(f"[ui_kit] 配置 {type(widget).__name__} 失败: {exc}")
        return 0
    return 1


def _as_px(value: Any, default: int = 0) -> int:
    """把 Tk 的尺寸值转成整数像素。

    `cget("padx")` 可能返回 `Tcl_Obj`（`int()` 会抛 TypeError），
    也可能返回 `"0 0"` 这类双值字符串，所以统一走字符串解析。
    """
    try:
        return int(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return default


#: Tk 未显式配色时报告的系统色名（Windows 上 `SystemButtonFace` 就是那种米色）。
#: 显式设过颜色的控件报的是 `#rrggbb`，不会落进这个集合 —— 这就是
#: "没配色的控件换肤、配过色的不动"的判据。
_SYSTEM_COLOR_NAMES = frozenset(
    name.lower()
    for name in (
        "SystemButtonFace",
        "SystemButtonText",
        "SystemWindow",
        "SystemWindowText",
        "SystemHighlight",
        "SystemHighlightText",
        "SystemMenu",
        "SystemMenuText",
    )
)


def _uses_system_color(widget: tk.Misc, option: str) -> bool:
    """该控件的 `option` 是否仍是**系统默认色**（= 创建时没显式配色）。"""
    try:
        return str(widget.cget(option)).strip().lower() in _SYSTEM_COLOR_NAMES
    except (tk.TclError, AttributeError):
        return False


def polish_legacy(container: tk.Misc, *, max_depth: int = 12) -> int:
    """给 **v2 迁移面板**已构建好的控件树做一次统一样式润色，返回触及的控件数。

    为什么用"事后润色"而不是改写 12 个 v2 面板：那 12 个文件是 v2 的原始实现，
    改动它们等于同时改 12 处逻辑；而"外观统一"是**横切关注点**，
    在适配器这一层统一处理，一处生效、一处可回退。

    只做**低风险、纯外观**的调整：
    - 按钮：手型光标、角色字体、悬停反馈、保证点击高度 ≥ `MIN_TARGET_HEIGHT`；
    - 输入框/文本域：字体与插入光标颜色、去浮雕、聚焦边框；
    - `LabelFrame`：标题配色与内边距。
    **不动布局与几何**（位置参数不改），因此不会打乱既有排版。
    """
    if container is None:
        return 0

    touched = 0
    stack: list[tuple[tk.Misc, int]] = [(container, 0)]
    while stack:
        widget, depth = stack.pop()
        if depth > max_depth:
            continue
        try:
            children = widget.winfo_children()
        except tk.TclError:
            continue
        stack.extend((child, depth + 1) for child in children)

        try:
            # ⚠️ ttk 分支必须排在 tk 分支**前面**：`ttk.Entry` / `ttk.Spinbox` /
            # `ttk.Combobox` 继承自 `tk.Entry` / `tk.Spinbox`（为了复用 validate 机制），
            # 若 tk 分支在前，Combobox 会被"Entry 分支"截胡，永远轮不到换肤（实测踩到）。
            if isinstance(widget, ttk.Combobox):
                # `Dark.TCombobox` 由 `UIStyle.apply_theme` 定义；
                # v2 面板建下拉框时不指定 style，于是退回 clam 默认浅色
                touched += _configure_supported(widget, style="Dark.TCombobox")
            elif isinstance(widget, ttk.Treeview):
                touched += _configure_supported(widget, style="Panel.Treeview")
                # 迁移面板自建的表格也套上斑马纹（否则只有原生面板好看，很割裂）
                for tag, color in (("odd", C["bg_card"]), ("even", C["bg_medium"]), ("muted", C["text_muted"])):
                    try:
                        widget.tag_configure(tag, background=color)
                    except tk.TclError:
                        break
            elif isinstance(widget, (ttk.Entry, ttk.Spinbox)):
                touched += _configure_supported(widget, style="Panel.TEntry")
            elif isinstance(widget, ttk.Button):
                # v2 面板几乎都不指定 ttk style → 退回 clam 默认浅色（米色横带的来源）。
                # 只在"没显式指定 style"时换成深色风格；显式指定的不动。
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Secondary.TButton")
            elif isinstance(widget, ttk.Label):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Dark.TLabel")
            elif isinstance(widget, ttk.LabelFrame):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Card.TLabelframe")
            elif isinstance(widget, ttk.Scrollbar):
                if not str(widget.cget("style")):
                    orient = str(widget.cget("orient"))
                    name = "Dark.Vertical.TScrollbar" if orient == "vertical" else "Dark.Horizontal.TScrollbar"
                    touched += _configure_supported(widget, style=name)
            elif isinstance(widget, ttk.Checkbutton):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Dark.TCheckbutton")
            elif isinstance(widget, ttk.Radiobutton):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Dark.TRadiobutton")
            elif isinstance(widget, ttk.Notebook):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Dark.TNotebook")
            elif isinstance(widget, ttk.Frame):
                if not str(widget.cget("style")):
                    touched += _configure_supported(widget, style="Dark.TFrame")
            elif isinstance(widget, tk.Button):
                newly = _configure_supported(
                    widget,
                    cursor="hand2",
                    relief=tk.FLAT,
                    bd=0,
                    font=UIStyle.font("label"),
                    padx=max(_as_px(widget.cget("padx")), SPACE["md"]),
                    pady=max(_as_px(widget.cget("pady")), SPACE["sm"]),
                    activebackground=C["accent_hover"],
                    disabledforeground=C["text_muted"],
                    highlightthickness=0,
                )
                if newly:
                    add_hover(widget, str(widget.cget("bg")), C["hover"])
                touched += newly
            elif isinstance(widget, (tk.Entry, tk.Spinbox)):
                touched += _configure_supported(
                    widget,
                    font=UIStyle.font("label"),
                    insertbackground=C["text_primary"],
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    highlightcolor=C["border_focus"],
                    bd=0,
                )
            elif isinstance(widget, tk.Text):
                touched += _configure_supported(
                    widget,
                    font=UIStyle.font("label"),
                    bg=C["bg_card"],
                    fg=C["text_primary"],
                    insertbackground=C["text_primary"],
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    highlightcolor=C["border_focus"],
                    bd=0,
                )
            elif isinstance(widget, tk.LabelFrame):
                touched += _configure_supported(
                    widget,
                    fg=C["text_secondary"],
                    font=UIStyle.font("label_bold"),
                    bd=0,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    padx=SPACE["md"],
                    pady=SPACE["sm"],
                )
            elif isinstance(widget, tk.Checkbutton):
                touched += _configure_supported(
                    widget,
                    cursor="hand2",
                    selectcolor=C["bg_medium"],
                    font=UIStyle.font("label"),
                )
            elif isinstance(widget, tk.Listbox):
                # v2 面板里的 Listbox 大多没设颜色（系统默认浅底），
                # 在暗色主题里就是一块扎眼的"米色斑"（元素库/网搜/摘要管理都中招）
                touched += _configure_supported(
                    widget,
                    font=UIStyle.font("label"),
                    bg=C["bg_card"],
                    fg=C["text_primary"],
                    selectbackground=C["accent"],
                    selectforeground="#ffffff",
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    highlightcolor=C["border_focus"],
                    bd=0,
                )
            elif isinstance(widget, tk.Scrollbar):
                # ScrolledText 自带的滚动条是经典 tk 控件：默认 SystemButtonFace 米色
                touched += _configure_supported(
                    widget,
                    bg=C["bg_medium"],
                    troughcolor=C["bg_dark"],
                    activebackground=C["hover"],
                    highlightthickness=0,
                    bd=0,
                    relief=tk.FLAT,
                )
            elif isinstance(widget, tk.Label):
                # 只换"完全没配过色"的 Label（bg 与 fg 都是系统默认）；
                # 显式配色的强调标签（成功绿/警告黄等）一律不动
                if _uses_system_color(widget, "bg") and _uses_system_color(widget, "fg"):
                    touched += _configure_supported(widget, bg=C["bg_dark"], fg=C["text_primary"])
            elif isinstance(widget, tk.Frame):
                # 默认色的容器 Frame 是大片"米色横带/区块"的来源（按钮行/分区底色）
                if _uses_system_color(widget, "bg"):
                    touched += _configure_supported(widget, bg=C["bg_dark"])
        except (tk.TclError, ValueError, TypeError) as exc:
            logger.debug(f"[ui_kit] 润色跳过 {type(widget).__name__}: {exc}")

    return touched
