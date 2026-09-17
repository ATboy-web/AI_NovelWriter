"""面板宿主（v3 §2.2）：创作工具页的容器 + 分组选择器 + 生命周期调度。

## 它接管了 v2 里两条互相不知道对方存在的逻辑

1. `shell_ui.py:577-586` 硬编码的 12 个 Radiobutton（"有哪些面板"）
2. `toolkit_ui.py:26-49` 的 12 路 `elif`（"选了哪个 → 建哪个"）

两者表达的是同一份信息，却写在两个文件里，必然漂移。现在都由注册表渲染：
`build_selector()` 按 `category` 分组画小标题，`select()` 按 key 找面板。

## 容器保持单区（ROADMAP §5 决策 1）

不升级成二级 Notebook：仍然是一块 `tool_content_frame`，
每个面板在其中各有一个**自己的** Frame，切换时 `pack` / `pack_forget`。
面板内容不会被销毁（v2 每次切走就销毁，回来得重建），
但迁移面板的 `on_show()` 会主动重建内容，因此观感与数据新鲜度与 v2 一致。

## 独立窗口（面板可脱出）

面板可以离开宿主区、放进自己的 `Toplevel`（面包屑右上角"独立窗口"），
宿主区改为显示一个说明与"收回"入口。要点：

- 只能**销毁重建**（Tk 控件不能改父），这与 `refresh()` 是同一套动作；
- 同一面板**同时只活在一个容器**里，不会出现两份控件争同一份状态；
- 换书（`novel.opened`）时要**单独**重建已脱出的面板 —— 它们不走 `select()`；
- 退出时 `detach_all()` 必须关掉这些窗口：独立顶层窗口不会随主窗口销毁，
  留着会把进程拖在后台。

## 布局可配置：分栏与停靠记忆

选择器末行提供「单栏 / 分栏」与「右栏面板」，布局由 `layout.PanelLayout` 描述
（模式、两栏面板、分隔条比例、已脱出的面板）。要点：

- **栏是面板控件的父容器** ⇒ 换布局只能整块重建（Tk 控件不能改父），
  这与 `refresh()` / `pop_out` 是同一套动作，也保证同一面板**只活在一个容器**里；
- 主栏与右栏**不允许是同一个面板**；在右栏拉选择会自动**两栏互换**；
- 已脱出为独立窗口的面板不能再停靠在栏里（否则一个面板两个容器），
  且右栏面板一旦脱出，分栏自动**降级为单栏**；
- 分隔条比例"用户拖过就以拖动为准"，不拖则用记忆值；
- 宿主**不碰文件**：布局变化通过 `on_layout_changed` 回调交给应用层落盘。
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from typing import Any, Callable

from loguru import logger

from . import registry
from .base import BasePanel
from .layout import MAX_RATIO, MIN_PANE_WIDTH, MIN_RATIO, MODE_SINGLE, MODE_SPLIT, PanelLayout

__all__ = ["PanelHost"]


class PanelHost:
    """面板容器与生命周期的唯一管理者。

    Parameters
    ----------
    app : 面板的宿主（`NovelWriterApp`），所有面板经 `__getattr__` 从它取共享状态。
    container : 面板内容区（即 v2 的 `tool_content_frame`）。
    select_var : 与选择器绑定的 `tk.StringVar`，保持 v2 的 `tool_type_var` 语义。
    selector_parent : 选择器挂载的父控件。
    bus : 事件总线；`None` 时退化为 `app.event_bus`，再没有就不订阅（测试场景）。
    """

    def __init__(
        self,
        app: Any,
        container: tk.Widget,
        select_var: Any = None,
        selector_parent: tk.Widget | None = None,
        bus: Any = None,
        log: Callable[[str], None] | None = None,
        on_layout_changed: Callable[[PanelLayout], None] | None = None,
    ) -> None:
        self.app = app
        self.container = container
        self.select_var = select_var
        self.selector_parent = selector_parent
        self.bus = bus if bus is not None else getattr(app, "event_bus", None)
        self._log: Callable[[str], None] = log or getattr(app, "_log", None) or (lambda _m: None)
        # 布局变化回调（由应用层落盘 "停靠记忆"）。宿主**不碰文件** —— 它只广播状态。
        self._on_layout_changed = on_layout_changed

        self._panels: dict[str, BasePanel] = {}
        self._frames: dict[str, tk.Frame] = {}
        self._subscriptions: list[Callable[[], None]] = []
        self._current = ""
        self._popouts: dict[str, tk.Toplevel] = {}
        # 布局：栏（一栏或两栏）+ 舞台控件。栏是面板控件的**父容器**，
        # 换布局只能整块重建（Tk 控件不能改父，见 pop_out 的说明）。
        self._layout = PanelLayout()
        self._panes: dict[str, tk.Frame] = {}
        self._paned: Any = None
        self._mode_var: Any = None
        self._secondary_var: Any = None
        self._title_to_key: dict[str, str] = {}
        self._applying_ratio = False
        self._ratio_applied = False
        self._ensure_stage()
        self._attach_host_events()

    # ------------------------------------------------------------------ 宿主自身的订阅

    def _attach_host_events(self) -> None:
        """宿主自己订阅 `novel.opened`：换书后重建**当前可见**面板。

        为什么由宿主管而不是每个面板各管：换书时旧小说的数据全部失效，
        重建是唯一正确的动作，而"当前可见"是宿主才知道的信息。
        未显示的面板不需要处理 —— 它们下次被显示时 `on_show()` 会重建。
        """
        if self.bus is None:
            return
        from app.events import TOPIC_NOVEL_OPENED

        self._subscriptions.append(self.bus.subscribe(TOPIC_NOVEL_OPENED, self._on_novel_opened))

    def _on_novel_opened(self, _topic: str, _payload: Any = None) -> None:
        if self._current:
            self.refresh()
        # 独立窗口里的面板**不走 `select()`**，换书后不会自动重建 ——
        # 不补这一步，它们会一直显示上一本书的数据（比不显示更糟）。
        for key in tuple(self._popouts):
            if key != self._current:
                self._rebuild_popout(key)

    # ------------------------------------------------------------------ 选择器

    def build_selector(self, parent: tk.Widget | None = None) -> tk.Widget | None:
        """按注册表渲染分组选择器（一行一个分组，行内是该组的面板）。"""
        parent = parent if parent is not None else self.selector_parent
        if parent is None:
            return None
        if self.select_var is None:
            self.select_var = tk.StringVar()

        from app import UIStyle  # 延迟导入：避免 app 包初始化期间的循环引用

        C = UIStyle.COLORS
        for category, specs in registry.grouped():
            row = tk.Frame(parent, bg=C["bg_dark"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row,
                text=category,
                font=UIStyle.font("label_bold"),
                bg=C["bg_dark"],
                fg=C["accent_light"],
                width=7,
                anchor=tk.W,
            ).pack(side=tk.LEFT)
            for spec in specs:
                tk.Radiobutton(
                    row,
                    text=spec.title,
                    variable=self.select_var,
                    value=spec.key,
                    font=UIStyle.font("label"),
                    bg=C["bg_dark"],
                    fg=C["text_secondary"],
                    selectcolor=C["accent"],
                    activebackground=C["bg_dark"],
                    # 用 `functools.partial` 而不是 `lambda k=spec.key:` ——
                    # 默认参数捕获写法 mypy 无法推断 lambda 的类型（advisory 报错），
                    # 且 partial 的意图（"绑定这个 key"）比默认参数更直白。
                    command=partial(self.select, spec.key),
                ).pack(side=tk.LEFT, padx=6)
        self._build_layout_row(parent)
        return parent

    def _build_layout_row(self, parent: tk.Widget) -> tk.Widget | None:
        """选择器末行：**布局**控制（单栏 / 分栏 + 右栏面板选择）。

        为什么放在这里而不是每个面板的面包屑里：布局是**宿主级**概念 ——
        它描述的是"面板之间怎么排"，不属于任何单个面板。放进面包屑会让 15 个面板
        各长一个按钮，语义也错位（"我这个面板要分栏"讲不通）。

        为什么用 `tk.OptionMenu` 而不是再铺一行单选钮：15 个面板再铺一行会把
        选择器撑成三行，且"选右栏放谁"是低频操作，收进下拉更合适。
        """
        if not isinstance(parent, tk.Misc):
            return None

        from app import UIStyle

        from . import ui_kit

        C = UIStyle.COLORS
        row = tk.Frame(parent, bg=C["bg_dark"])
        row.pack(fill=tk.X, pady=1)
        tk.Label(
            row,
            text="布局",
            font=UIStyle.font("label_bold"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
            width=7,
            anchor=tk.W,
        ).pack(side=tk.LEFT)

        self._mode_var = tk.StringVar(value=self._layout.mode)
        for mode, text in ((MODE_SINGLE, "单栏"), (MODE_SPLIT, "分栏")):
            tk.Radiobutton(
                row,
                text=text,
                variable=self._mode_var,
                value=mode,
                font=UIStyle.font("label"),
                bg=C["bg_dark"],
                fg=C["text_secondary"],
                selectcolor=C["accent"],
                activebackground=C["bg_dark"],
                command=partial(self.set_layout_mode, mode),
            ).pack(side=tk.LEFT, padx=6)

        tk.Label(
            row,
            text="右栏",
            font=UIStyle.font("label"),
            bg=C["bg_dark"],
            fg=C["text_muted"],
        ).pack(side=tk.LEFT, padx=(ui_kit.SPACE["md"], ui_kit.SPACE["xs"]))

        self._title_to_key = {spec.title: spec.key for spec in registry.all_panels()}
        self._secondary_var = tk.StringVar()
        option = tk.OptionMenu(row, self._secondary_var, *self._title_to_key, command=self._on_secondary_selected)
        option.config(
            font=UIStyle.font("label"),
            bg=C["bg_light"],
            fg=C["text_secondary"],
            activebackground=C["bg_hover"],
            highlightthickness=0,
            bd=0,
            anchor=tk.W,
        )
        option["menu"].config(font=UIStyle.font("label"), bg=C["bg_light"], fg=C["text_secondary"])
        option.pack(side=tk.LEFT)
        self._sync_secondary_widget()
        return row

    def _sync_secondary_widget(self) -> None:
        """把下拉框的显示文字同步成当前右栏面板（无右栏时给提示语）。"""
        if self._secondary_var is None:
            return
        key = self._layout.secondary if self.is_split() else ""
        spec = registry.get(key) if key else None
        self._secondary_var.set(spec.title if spec is not None else "（未分栏）")

    def _on_secondary_selected(self, title: str) -> None:
        key = self._title_to_key.get(title)
        if key:
            self.set_secondary(key)

    # ------------------------------------------------------------------ 显示

    def select(self, key: str) -> bool:
        """切换到 `key` 面板：隐藏上一个、构建或刷新这一个。

        分栏模式下这里指的是**主栏**（右栏用 `set_secondary`）。若 `key` 正好是
        右栏面板，则两栏**互换** —— 同一面板不能同时占两栏（那会出现两份控件
        争同一份状态）。
        """
        spec = registry.get(key)
        if spec is None:
            logger.warning(f"面板宿主收到未登记的 key: {key!r}（已登记: {sorted(registry.PANEL_REGISTRY)}）")
            return False

        if self._remember_primary(key):
            # 栏位变了 ⇒ 面板控件必须换父容器 ⇒ 整块重建（Tk 控件不能改父）。
            # 重建会重新 `select(primary)`，那时栏位已稳定，不会再进这个分支。
            # 返回值沿用重建结果：`select()` 的契约是"这个面板显示成功了吗"。
            return self._restage()

        if self._current and self._current != key:
            self._hide(self._current)

        if key in self._popouts:
            # 该面板已脱离为独立窗口：宿主区只放一个"它在别处"的提示，不重建内容
            # （否则同一面板会同时活在两个容器里，两份控件争同一份状态）。
            self._render_popout_notice(key, spec)
            self._current = key
            if self.select_var is not None:
                self.select_var.set(key)
            self._raise_popout(key)
            return True

        if not self._render(spec, key):
            return False
        self._current = key
        if self.select_var is not None:
            self.select_var.set(key)
        return True

    def _render(self, spec: registry.PanelSpec, key: str) -> bool:
        """把面板画进它所属的栏；已建好则走 `on_show` 刷新。`select` 与右栏共用。"""
        panel = self._panel_for(spec)
        frame = self._frame_for(key)

        if panel.is_built:
            self._safe(panel, "on_show", key)
            if spec.legacy and isinstance(frame, tk.Misc):
                # 迁移面板的 `on_show()` 会**重建内容**（v2 语义）—— 重建出的新控件
                # 又回到系统默认色，润色必须跟着重跑，否则切走再切回就"掉皮"
                # （截图实证：首次构建是深色，切回来 Listbox 又变回 SystemWindow 白底）
                content = getattr(panel, "_chrome_content", None)
                if content is not None:
                    from . import ui_kit

                    ui_kit.polish_legacy(content)
        else:
            # 重建前必须清空 frame：`refresh()` 会把 is_built 置 False 后回到这里，
            # 而外壳（面包屑/内容区/状态栏）与面板内容都长在这同一个 frame 里 ——
            # 不销毁旧控件就再建一遍，面包屑会叠成两行（截图实证过的重复渲染 bug）。
            # 顺便自愈：上次构建中途异常留下的半个外壳也会被清掉。
            for child in frame.winfo_children():
                child.destroy()
            try:
                if isinstance(frame, tk.Misc):
                    self._build_with_chrome(panel, spec, frame)
                else:
                    # 非 Tk 容器（测试替身）：外壳是真实 Tk 控件，无从构建。
                    # 这些测试关心的是生命周期语义（建一次/on_show/on_hide/refresh），
                    # 与外壳无关 —— 退化为裸构建；外壳行为由真实 Tk 的测试单独把关。
                    panel.build(frame)
            except Exception as e:  # noqa: BLE001 - 单个面板构建失败不应中断切换
                logger.error(f"面板 {key!r} 构建失败: {type(e).__name__}: {e}")
                return False
        frame.pack(fill=tk.BOTH, expand=True)
        return True

    def _build_with_chrome(self, panel: BasePanel, spec: Any, frame: tk.Frame, *, popout: bool = False) -> None:
        """给**任何**面板套上统一外壳：面包屑 → 内容区 → 状态栏（+ 快捷键）。

        为什么放在宿主而不是每个面板里：15 个面板（12 个 v2 迁移 + 3 个原生）
        都要有"我在哪、怎么刷新、刚才那步成没成"，逐面板实现必然各写各的
        （这正是"界面不成体系"的成因）。宿主是唯一的公共点。

        迁移面板额外做一次 `polish_legacy`（纯外观润色，不动布局）。

        `popout=True` 时外壳建在独立窗口里，右上角按钮从"独立窗口"换成"收回面板"
        —— 两种形态共用同一段代码，避免"窗口里的面板长得不一样"。
        """
        from app import UIStyle  # 延迟导入：避免 app 包初始化期间的循环引用

        from . import ui_kit

        ui_kit.apply_widget_theme(frame)
        bg = UIStyle.COLORS["bg_dark"]

        crumbs = tk.Frame(frame, bg=bg)
        crumbs.pack(fill=tk.X, padx=ui_kit.SPACE["md"], pady=(ui_kit.SPACE["sm"], 0))
        tk.Label(
            crumbs,
            text=spec.category,
            bg=bg,
            fg=UIStyle.COLORS["text_muted"],
            font=UIStyle.font("caption"),
        ).pack(side=tk.LEFT)
        tk.Label(crumbs, text="›", bg=bg, fg=UIStyle.COLORS["border_light"], font=UIStyle.font("caption")).pack(
            side=tk.LEFT, padx=ui_kit.SPACE["xs"]
        )
        tk.Label(
            crumbs,
            text=spec.title,
            bg=bg,
            fg=UIStyle.COLORS["text_secondary"],
            font=UIStyle.font("label_bold"),
        ).pack(side=tk.LEFT)
        ui_kit.button(crumbs, "刷新 (F5)", lambda: self.refresh(), kind="ghost", padx=ui_kit.SPACE["sm"]).pack(
            side=tk.RIGHT
        )
        # 独立窗口 / 收回：两种形态各显示相反的那个动作，位置固定在刷新按钮左侧
        if popout:
            ui_kit.button(
                crumbs, "收回面板", partial(self.pop_in, spec.key), kind="ghost", padx=ui_kit.SPACE["sm"]
            ).pack(side=tk.RIGHT, padx=(0, ui_kit.SPACE["xs"]))
        else:
            ui_kit.button(
                crumbs, "独立窗口", partial(self.pop_out, spec.key), kind="ghost", padx=ui_kit.SPACE["sm"]
            ).pack(side=tk.RIGHT, padx=(0, ui_kit.SPACE["xs"]))

        content = tk.Frame(frame, bg=bg)
        content.pack(fill=tk.BOTH, expand=True, padx=ui_kit.SPACE["md"], pady=(ui_kit.SPACE["sm"], 0))

        status = ui_kit.StatusBar(frame, bg=bg)
        # `StatusBar` 是包装类（持有 `frame` / `set()`），不是控件 —— 要 pack 它的 frame
        status.frame.pack(fill=tk.X, padx=ui_kit.SPACE["md"], pady=(ui_kit.SPACE["xs"], ui_kit.SPACE["sm"]))
        # 下划线名 → 面板私有（迁移适配器不会把它转发给宿主）
        object.__setattr__(panel, "_status_bar", status)
        object.__setattr__(panel, "_chrome_content", content)

        panel.build(content)

        if spec.legacy:
            touched = ui_kit.polish_legacy(content)
            logger.debug(f"[panel_host] 迁移面板 {spec.key} 外观润色 {touched} 个控件")

        # 快捷键：宿主统一提供，面板无需各自绑定
        ui_kit.bind_shortcuts(
            content,
            {
                "<F5>": lambda: self.refresh(),
                "<Control-f>": panel.focus_search,
                "<Escape>": lambda: status.clear(),
            },
        )

    def refresh(self) -> bool:
        """重建当前面板（等价于 v2 到处调用的 `_refresh_toolkit()`）。

        面板若在独立窗口里，就重建在那个窗口里 —— 刷新按钮不能把面板"拽"回宿主区。
        """
        key = self._current or registry.default_key()
        if not key:
            return False
        panel = self._panels.get(key)
        if panel is not None:
            panel.mark_built(False)
        if key in self._popouts:
            return self._rebuild_popout(key)

        # 分栏时**两栏都要重建**：只刷主栏的话，右栏会停在旧数据上
        # （它同样受 `novel.opened` 影响，只是不走 `select()`）。
        secondary = self._layout.secondary if self.is_split() else ""
        if secondary:
            other = self._panels.get(secondary)
            if other is not None:
                other.mark_built(False)

        ok = self.select(key)
        if secondary:
            spec = registry.get(secondary)
            if spec is not None:
                ok = self._render(spec, secondary) and ok
        return ok

    def _rebuild_popout(self, key: str) -> bool:
        """就地重建独立窗口里的面板（关掉旧内容、重新套外壳）。"""
        window = self._popouts.get(key)
        spec = registry.get(key)
        panel = self._panels.get(key)
        if window is None or spec is None or panel is None:
            return False

        from app import UIStyle

        bg = UIStyle.COLORS["bg_dark"]
        self._clear_children(window)
        panel.mark_built(False)
        holder = tk.Frame(window, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True)
        try:
            self._build_with_chrome(panel, spec, holder, popout=True)
        except Exception as e:  # noqa: BLE001
            logger.error(f"面板 {key!r} 在独立窗口中重建失败: {type(e).__name__}: {e}")
            return False
        return True

    def _hide(self, key: str) -> None:
        panel = self._panels.get(key)
        if panel is not None:
            self._safe(panel, "on_hide", key)
        frame = self._frames.get(key)
        if frame is not None:
            frame.pack_forget()

    # ------------------------------------------------------------------ 独立窗口

    def is_popped_out(self, key: str) -> bool:
        """该面板此刻是否活在独立窗口里。"""
        return key in self._popouts

    def popped_out_keys(self) -> tuple[str, ...]:
        """已脱离的面板 key（供诊断与测试观察）。"""
        return tuple(self._popouts)

    def pop_out(self, key: str) -> bool:
        """把面板放进独立 `Toplevel`，宿主区留一个说明与"收回"入口。

        为什么是"销毁 + 重建"而不是搬运控件：Tk 的控件**不能改父**（没有 reparent
        语义），窗口间移动只能销毁后在目标容器重建。这在本项目里是安全动作 ——
        面板本来就是"往给定 frame 里建内容"的形态（`refresh()` 与迁移面板的
        `on_show()` 每次都在做同一件事），而面包屑/状态栏/快捷键由宿主统一提供，
        所以两种形态的观感天然一致。

        无真实 Tk 容器时（测试替身）返回 `False` 而不是抛异常。
        """
        spec = registry.get(key)
        if spec is None:
            logger.warning(f"面板宿主收到未登记的 key: {key!r}")
            return False
        if key in self._popouts:
            self._raise_popout(key)
            return True
        if not isinstance(self.container, tk.Misc):
            return False

        # 布局记账：脱出即"不在这两栏里"。若脱出的正是右栏面板，分栏就失去意义
        # ⇒ 降级为单栏（而不是留一个空框）。
        vacated_secondary = key == self._layout.secondary
        changes: dict[str, Any] = {"popped_out": list(dict.fromkeys([*self._layout.popped_out, key]))}
        if vacated_secondary:
            changes.update(mode=MODE_SINGLE, secondary="")
        self._layout = self._layout.copy(**changes)
        if vacated_secondary:
            self._restage()

        from app import UIStyle  # 延迟导入：避免 app 包初始化期间的循环引用

        bg = UIStyle.COLORS["bg_dark"]
        try:
            window = tk.Toplevel(self.container)
            window.title(f"{spec.title} — AI小说创作工坊")
            window.geometry("1000x720")
            window.minsize(600, 420)
            window.configure(bg=bg)
        except tk.TclError as e:  # pragma: no cover - 需要真实 Tk 才能触发
            logger.error(f"为面板 {key!r} 建立独立窗口失败: {e}")
            return False

        # 关窗即"收回面板"：否则会留下"窗口没了、宿主区还显示占位"的错觉状态
        window.protocol("WM_DELETE_WINDOW", partial(self.pop_in, key))
        self._popouts[key] = window

        panel = self._panel_for(spec)
        # 先让面板收尾（迁移面板会在这里停掉定时器之类），再销毁它原来的控件
        if panel.is_built:
            self._safe(panel, "on_hide", key)
        self._clear_children(self._frame_for(key))
        panel.mark_built(False)

        holder = tk.Frame(window, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True)
        try:
            self._build_with_chrome(panel, spec, holder, popout=True)
        except Exception as e:  # noqa: BLE001 - 建窗失败要能回退，不能留下空窗口
            logger.error(f"面板 {key!r} 在独立窗口中构建失败: {type(e).__name__}: {e}")
            self._popouts.pop(key, None)
            try:
                window.destroy()
            except tk.TclError:  # pragma: no cover
                pass
            return False

        # 主栏面板脱出时，宿主区也要显示"它在别处"（`_current` 可能已被 restage 改掉）
        if key in (self._current, self._layout.primary):
            self._render_popout_notice(key, spec)
        self._notify_layout_changed()
        return True

    def pop_in(self, key: str) -> bool:
        """收回独立窗口里的面板，内容重新建回宿主区。"""
        window = self._popouts.pop(key, None)
        if window is None:
            return False

        panel = self._panels.get(key)
        if panel is not None:
            self._safe(panel, "on_hide", key)
            panel.mark_built(False)
        try:
            window.destroy()
        except tk.TclError:  # pragma: no cover - 窗口可能已被 WM 销毁
            pass

        self._layout = self._layout.copy(
            popped_out=[item for item in self._layout.popped_out if item != key],
        )

        if panel is not None and self._current == key:
            # 走 `select()` 而不是自己重建：清空旧控件、套外壳、打包这一整套
            # 已经有测试覆盖，重复实现一遍只会多一处会漂移的逻辑。
            result = self.select(key)
            self._notify_layout_changed()
            return result
        self._notify_layout_changed()
        return True

    def toggle_pop_out(self, key: str) -> bool:
        """在"独立窗口"与"宿主区"之间切换（供菜单项/快捷键使用）。"""
        return self.pop_in(key) if key in self._popouts else self.pop_out(key)

    def _raise_popout(self, key: str) -> None:
        window = self._popouts.get(key)
        if window is None:
            return
        try:
            window.deiconify()
            window.lift()
            window.focus_set()
        except tk.TclError as e:  # pragma: no cover - 窗口已销毁
            logger.debug(f"提升独立窗口 {key!r} 失败（忽略）: {e}")

    def _render_popout_notice(self, key: str, spec: Any) -> None:
        """宿主区占位：说清"面板去哪了"以及怎么拿回来。"""
        from . import ui_kit

        frame = self._frame_for(key)
        self._clear_children(frame)
        ui_kit.empty_state(
            frame,
            f"{spec.title} 已在独立窗口中打开",
            "它可以和主窗口并排摆放。关掉那个窗口、或点下面的按钮，面板就会回到这里。",
            glyph="⧉",
            action_text="收回面板",
            action_command=partial(self.pop_in, key),
        ).pack(fill=tk.BOTH, expand=True)
        frame.pack(fill=tk.BOTH, expand=True)

    @staticmethod
    def _clear_children(widget: tk.Misc) -> None:
        """销毁子控件。宿主外壳与面板内容长在同一容器里，重建前必须先清空。"""
        for child in widget.winfo_children():
            child.destroy()

    # ------------------------------------------------------------------ 布局：栏与停靠

    def layout(self) -> PanelLayout:
        """当前布局（副本语义：改它不会影响宿主）。"""
        return self._layout.copy()

    def is_split(self) -> bool:
        """当前是否分栏。"""
        return self._layout.mode == MODE_SPLIT and bool(self._layout.secondary)

    def apply_layout(self, layout: PanelLayout) -> bool:
        """应用一份**外部**布局（启动恢复 / 测试）。先按当前注册表洗一遍再落地。

        为什么必须 sanitize：布局文件跨版本存在，而面板 key 会改名/删除。
        不洗就会出现"记忆了一个不存在的面板"，表现为启动后空栏。
        """
        cleaned = layout.sanitize(registry.PANEL_REGISTRY)
        if not cleaned.primary or cleaned.primary not in registry.PANEL_REGISTRY:
            cleaned = cleaned.copy(primary=registry.default_key())
        self._layout = cleaned
        self._restage()
        for key in cleaned.popped_out:
            if key in registry.PANEL_REGISTRY and key not in self._popouts:
                self.pop_out(key)
        if self._mode_var is not None:
            self._mode_var.set(self._layout.mode)
        self._sync_secondary_widget()
        return True

    def set_layout_mode(self, mode: str) -> bool:
        """切换单栏 / 分栏。进入分栏时若还没有右栏面板，自动挑一个。

        返回 False 的情形：模式非法，或**面板总数不足以分栏**（注册表里只有一个面板）。
        """
        if mode not in (MODE_SINGLE, MODE_SPLIT):
            return False
        secondary = self._layout.secondary
        if mode == MODE_SPLIT and not secondary:
            secondary = self._default_secondary()
            if not secondary:
                return False
        if mode == self._layout.mode and secondary == self._layout.secondary:
            return True
        self._layout = self._layout.copy(mode=mode, secondary=secondary if mode == MODE_SPLIT else "")
        self._restage()
        if self._mode_var is not None:
            self._mode_var.set(mode)
        self._notify_layout_changed()
        self._log(f"面板布局：{'分栏' if mode == MODE_SPLIT else '单栏'}")
        return True

    def set_secondary(self, key: str) -> bool:
        """把某个面板停靠到右栏（会自动切到分栏模式）。"""
        if key not in registry.PANEL_REGISTRY:
            return False
        if key == self._layout.primary:
            # 同一面板不能同时占两栏 —— 那会出现两份控件争同一份状态
            return False
        if key in self._popouts:
            # 已脱出为独立窗口的面板不能再停靠在栏里，否则同一个面板有两个容器
            return False
        if self._layout.mode != MODE_SPLIT:
            self._layout = self._layout.copy(mode=MODE_SPLIT, secondary=key)
        else:
            self._layout = self._layout.copy(secondary=key)
        self._restage()
        if self._mode_var is not None:
            self._mode_var.set(self._layout.mode)
        self._sync_secondary_widget()
        self._notify_layout_changed()
        return True

    def close_split(self) -> bool:
        """收起右栏，回到单栏。"""
        return self.set_layout_mode(MODE_SINGLE)

    def set_ratio(self, ratio: float) -> None:
        """设置主栏宽度占比（夹到 `[MIN_RATIO, MAX_RATIO]`），并立即应用。

        ⚠️ 实际位置还会受两栏 `MIN_PANE_WIDTH` 限制：窗口太窄时 Tk 会**忽略**
        这个比例以保证两栏都看得见（这是有意的 —— 拖到某一边消失会让人以为面板没了）。
        所以"记忆的比例"与"当前实际比例"可能不同，`ratio()` 取的是实际值。
        """
        self._layout = self._layout.copy(ratio=min(MAX_RATIO, max(MIN_RATIO, float(ratio))))
        self._ratio_applied = False  # 这次是**用户明确要求**，要覆盖"只摆一次"的保护
        self._apply_ratio()
        self._notify_layout_changed()

    def ratio(self) -> float:
        """当前占比：优先取**真实分隔条**位置（用户拖动过就以拖动为准）。"""
        measured = self._measure_ratio()
        return self._layout.ratio if measured is None else measured

    # ---- 内部 ----

    def _slot_for(self, key: str) -> str:
        """该面板此刻属于哪一栏。"""
        if self._layout.mode == MODE_SPLIT and key == self._layout.secondary:
            return "secondary"
        return "primary"

    def _slot_snapshot(self) -> dict[str, str]:
        return {
            key: self._slot_for(key)
            for key in (self._layout.primary, self._layout.secondary)
            if key and key not in self._popouts
        }

    def _remember_primary(self, key: str) -> bool:
        """记下 `primary`；返回**是否需要整块重建栏**。

        判据必须精确到"**已经放置过的**面板换了栏"：

        - 首次填 `primary`（此前为空）**不需要**重建 —— 面板还没建过控件，
          走正常的"构建"路径即可；若在这里重建，`select()` 就会绕过
          `on_hide()` 与 `pack_forget()`，把面板生命周期契约悄悄改掉；
        - 单栏下从 A 切到 B 也不需要（A 只是被隐藏，栏位没变）；
        - 只有"A 在主栏、B 在右栏 → 换成 B 主栏、A 右栏"这种**栏位互换**才需要 ——
          因为面板控件的父容器变了，而 Tk 控件不能改父。
        """
        layout = self._layout
        if layout.primary == key:
            return False

        before = self._slot_snapshot()
        changes: dict[str, Any] = {"primary": key}
        if layout.mode == MODE_SPLIT and key == layout.secondary:
            # 与右栏互换：同一面板不能同时占两栏
            changes["secondary"] = layout.primary
        self._layout = layout.copy(**changes)

        after = self._slot_snapshot()
        return any(before[key_] != slot for key_, slot in after.items() if key_ in before)

    def _default_secondary(self) -> str:
        """挑一个合适的右栏面板：同分组的下一个 → 任意非主栏面板。

        为什么优先同分组：并排看的两个面板通常属于同一类工作
        （"章节分析 + 批量操作"、"记忆可视化 + 摘要管理"）。
        """
        keys = [spec.key for spec in registry.all_panels()]
        if len(keys) < 2:
            return ""
        primary = self._layout.primary
        for spec in registry.all_panels():
            if spec.key == primary:
                primary_category = spec.category
                break
        else:
            primary_category = ""
        candidates = [key for key in keys if key != primary and key not in self._popouts]
        for key in candidates:
            spec = registry.get(key)
            if spec is not None and spec.category == primary_category:
                return key
        return candidates[0] if candidates else ""

    def _ensure_stage(self) -> bool:
        """建立"栏"：单栏一栏，分栏则是一个可拖分隔条的两栏容器。

        返回是否用上了真实 Tk 容器。非 Tk（测试替身）时返回 False ——
        此时面板控件直接挂在 `container` 上，与 v3.0.0 的行为一致。
        """
        self._paned = None
        self._panes = {}
        self._ratio_applied = False
        if not isinstance(self.container, tk.Misc):
            return False

        from app import UIStyle

        bg = UIStyle.COLORS["bg_dark"]
        if self._layout.mode == MODE_SPLIT:
            # ⚠️ `PanedWindow` 的选项集与 `Frame` 不同：没有 `highlightthickness`
            # （那是 Frame 的），直接传会 `unknown option` 让分栏整体建不起来。
            paned = tk.PanedWindow(
                self.container,
                orient=tk.HORIZONTAL,
                sashwidth=6,
                sashrelief=tk.FLAT,
                showhandle=False,
                bd=0,
                bg=bg,
            )
            paned.pack(fill=tk.BOTH, expand=True)
            primary = tk.Frame(paned, bg=bg)
            secondary = tk.Frame(paned, bg=bg)
            paned.add(primary, stretch="always", minsize=MIN_PANE_WIDTH)
            paned.add(secondary, stretch="always", minsize=MIN_PANE_WIDTH)
            # 拖完分隔条就把比例记下来（"停靠记忆"的一部分）
            paned.bind("<ButtonRelease-1>", self._on_sash_released)
            # 首次拿到真实尺寸时把记忆的比例摆上去（只摆一次，避免与拖动打架）
            paned.bind("<Configure>", self._on_paned_configure)
            self._paned = paned
            self._panes = {"primary": primary, "secondary": secondary}
        else:
            pane = tk.Frame(self.container, bg=bg)
            pane.pack(fill=tk.BOTH, expand=True)
            self._panes = {"primary": pane}
        return True

    def _destroy_stage(self) -> None:
        """拆掉栏（连带面板控件），并把面板标记为待重建。

        ⚠️ **已脱出的面板不能标记为待重建**：它们的控件活在独立窗口里，
        与栏无关；标了会造成"`is_built` 为假但界面上明明有内容"的不一致。
        """
        for pane in self._panes.values():
            try:
                pane.destroy()
            except tk.TclError:  # pragma: no cover - 已销毁
                pass
        self._panes = {}
        if self._paned is not None:
            try:
                self._paned.destroy()
            except tk.TclError:  # pragma: no cover - 已销毁
                pass
        self._paned = None
        self._frames.clear()
        for key, panel in self._panels.items():
            if key in self._popouts:
                # 控件活在独立窗口里，与栏无关：既不通知 on_hide，也不标成待重建
                continue
            if panel.is_built:
                # 控件即将被销毁 —— 与"切走"同样要通知面板收尾（停定时器等）
                self._safe(panel, "on_hide", key)
            panel.mark_built(False)
        self._current = ""

    def _restage(self) -> bool:
        """按当前布局重建栏，并重新显示两栏应有的面板。

        返回**主栏是否渲染成功**（`select()` 的返回值直接沿用）。右栏建不起来时
        自动降级为单栏，这不算失败 —— 它是容错，不是错误。

        ⚠️ 重建会销毁面板控件，因此必须先给它们 `on_hide()`：与"切走一个面板"
        一样，负责停定时器/收尾的面板需要被通知到。
        """
        self._destroy_stage()
        self._ensure_stage()
        ok = True
        if self._layout.primary:
            ok = self.select(self._layout.primary)
        if self.is_split():
            spec = registry.get(self._layout.secondary)
            if spec is not None and not self._render(spec, self._layout.secondary):
                # 右栏建不起来（面板自身异常）⇒ 降级为单栏，不留一个空框
                self._layout = self._layout.copy(mode=MODE_SINGLE, secondary="")
        self._apply_ratio()
        return ok

    def _on_sash_released(self, _event: Any = None) -> None:
        measured = self._measure_ratio()
        if measured is None:
            return
        self._layout = self._layout.copy(ratio=measured)
        self._notify_layout_changed()

    def _measure_ratio(self) -> float | None:
        """读取真实分隔条位置对应的占比；取不到返回 None。"""
        if self._paned is None:
            return None
        try:
            self._paned.update_idletasks()
            width = self._paned.winfo_width()
            if width <= 1:
                return None
            position = self._paned.sash_coord(0)[0]
        except (tk.TclError, IndexError):  # pragma: no cover - 尚未布局出来
            return None
        return min(MAX_RATIO, max(MIN_RATIO, position / width))

    def _apply_ratio(self) -> None:
        """把 `ratio` 应用到分隔条。

        ⚠️ **不要在这里用 `after_idle` 递归重试**：窗口尚未映射时 `winfo_width()`
        恒为 1，自重排会变成一个永远跑不完的空闲循环 —— `update()` 直接卡死
        （实测：测试进程挂住 7 分钟只能强杀）。改为让 `<Configure>` 在拿到真实尺寸时
        触发一次（见 `_on_paned_configure`）。
        """
        if self._paned is None or self._applying_ratio:
            return
        try:
            self._paned.update_idletasks()
            width = self._paned.winfo_width()
        except tk.TclError:  # pragma: no cover - 已销毁
            return
        if width <= 1:
            return  # 还没映射出来：交给 <Configure>
        self._applying_ratio = True
        try:
            self._paned.sash_place(0, int(width * self._layout.ratio), 0)
            self._ratio_applied = True
        except tk.TclError as e:  # pragma: no cover
            logger.debug(f"设置分隔条位置失败（忽略）: {e}")
        finally:
            self._applying_ratio = False

    def _on_paned_configure(self, _event: Any = None) -> None:
        """分隔容器第一次拿到真实尺寸时应用一次记忆的比例。

        只应用**一次**（`_ratio_applied`）：否则用户拖动分隔条时 `<Configure>` 会
        不断把它拽回记忆值，拖动直接不可用。
        """
        if self._ratio_applied:
            return
        self._apply_ratio()

    def _notify_layout_changed(self) -> None:
        self._sync_secondary_widget()
        if self._on_layout_changed is None:
            return
        try:
            self._on_layout_changed(self.layout())
        except Exception as e:  # noqa: BLE001 - 落盘失败不该影响界面
            logger.debug(f"布局变化回调失败（忽略）: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------ 查询

    @property
    def current_key(self) -> str:
        return self._current

    def panel(self, key: str) -> BasePanel | None:
        """已实例化的面板（未创建则 `None` —— 面板是懒创建的）。"""
        return self._panels.get(key)

    def built_panels(self) -> dict[str, BasePanel]:
        """已实例化的面板副本（遍历中可能创建新面板，故返回副本）。"""
        return dict(self._panels)

    # ------------------------------------------------------------------ 事件

    def notify(self, topic: str, payload: Any = None) -> int:
        """直接调用所有已实例化面板的 `on_event`（不经总线）。

        应用运行时面板是**各自按 `topics_of_interest` 订阅总线**的（见 `_panel_for`），
        不走这条路，以免同一次事件被投递两遍。本方法供无总线的场景与测试使用。
        """
        delivered = 0
        for panel in list(self._panels.values()):
            try:
                panel.on_event(topic, payload)
            except Exception as e:  # noqa: BLE001 - 一个面板坏掉不该阻断其他面板
                logger.error(f"面板 {panel.key!r} 处理事件 {topic} 失败: {type(e).__name__}: {e}")
            else:
                delivered += 1
        return delivered

    def detach_all(self) -> None:
        """取消全部订阅、关掉独立窗口、让面板脱离宿主（应用退出时调用）。"""
        for unsubscribe in self._subscriptions:
            try:
                unsubscribe()
            except Exception as e:  # noqa: BLE001 - 收尾阶段不抛异常
                logger.debug(f"取消面板订阅失败（忽略）: {e}")
        self._subscriptions.clear()
        # 独立窗口先关：它是独立顶层窗口，主窗口销毁不会连带它，
        # 留着会把进程拖在后台（只剩一个空窗口的任务栏图标）。
        for key, window in list(self._popouts.items()):
            try:
                window.destroy()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"关闭面板 {key!r} 的独立窗口失败（忽略）: {e}")
        self._popouts.clear()
        for panel in self._panels.values():
            try:
                panel.detach()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"面板 {panel.key!r} 脱离失败（忽略）: {e}")

    # ------------------------------------------------------------------ 内部

    def _panel_for(self, spec: registry.PanelSpec) -> BasePanel:
        panel = self._panels.get(spec.key)
        if panel is None:
            panel = spec.panel_cls(self.app)
            self._panels[spec.key] = panel
            if self.bus is not None:
                # 面板 `topics_of_interest` 为空时这里返回空列表（= 不订阅），
                # 迁移来的 v2 面板正是如此：它们没有 on_event，靠 on_show 重建。
                self._subscriptions.extend(panel.attach_events(self.bus))
        return panel

    def _frame_for(self, key: str) -> tk.Frame:
        frame = self._frames.get(key)
        if frame is None:
            # 父容器是**栏**（分栏时有左右两个）；没有舞台时退回 container
            # （非 Tk 的测试替身走这条，与 v3.0.0 行为一致）。
            parent = self._panes.get(self._slot_for(key)) or self.container
            try:
                bg = self.container.cget("bg")
            except tk.TclError:
                bg = ""
            frame = tk.Frame(parent, bg=bg) if bg else tk.Frame(parent)
            self._frames[key] = frame
        return frame

    @staticmethod
    def _safe(panel: BasePanel, method: str, key: str) -> None:
        try:
            getattr(panel, method)()
        except Exception as e:  # noqa: BLE001 - 生命周期钩子不得中断切换
            logger.error(f"面板 {key!r} 的 {method}() 抛错: {type(e).__name__}: {e}")
