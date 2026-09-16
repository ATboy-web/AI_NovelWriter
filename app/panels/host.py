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
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from typing import Any, Callable

from loguru import logger

from . import registry
from .base import BasePanel

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
    ) -> None:
        self.app = app
        self.container = container
        self.select_var = select_var
        self.selector_parent = selector_parent
        self.bus = bus if bus is not None else getattr(app, "event_bus", None)
        self._log: Callable[[str], None] = log or getattr(app, "_log", None) or (lambda _m: None)

        self._panels: dict[str, BasePanel] = {}
        self._frames: dict[str, tk.Frame] = {}
        self._subscriptions: list[Callable[[], None]] = []
        self._current = ""
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
        return parent

    # ------------------------------------------------------------------ 显示

    def select(self, key: str) -> bool:
        """切换到 `key` 面板：隐藏上一个、构建或刷新这一个。"""
        spec = registry.get(key)
        if spec is None:
            logger.warning(f"面板宿主收到未登记的 key: {key!r}（已登记: {sorted(registry.PANEL_REGISTRY)}）")
            return False

        if self._current and self._current != key:
            self._hide(self._current)

        panel = self._panel_for(spec)
        frame = self._frame_for(key)
        if panel.is_built:
            self._safe(panel, "on_show", key)
        else:
            try:
                panel.build(frame)
            except Exception as e:  # noqa: BLE001 - 单个面板构建失败不应中断切换
                logger.error(f"面板 {key!r} 构建失败: {type(e).__name__}: {e}")
                return False
        frame.pack(fill=tk.BOTH, expand=True)
        self._current = key
        if self.select_var is not None:
            self.select_var.set(key)
        return True

    def refresh(self) -> bool:
        """重建当前面板（等价于 v2 到处调用的 `_refresh_toolkit()`）。"""
        key = self._current or registry.default_key()
        if not key:
            return False
        panel = self._panels.get(key)
        if panel is not None:
            panel.mark_built(False)
        return self.select(key)

    def _hide(self, key: str) -> None:
        panel = self._panels.get(key)
        if panel is not None:
            self._safe(panel, "on_hide", key)
        frame = self._frames.get(key)
        if frame is not None:
            frame.pack_forget()

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
        """取消全部订阅并让面板脱离宿主（应用退出时调用）。"""
        for unsubscribe in self._subscriptions:
            try:
                unsubscribe()
            except Exception as e:  # noqa: BLE001 - 收尾阶段不抛异常
                logger.debug(f"取消面板订阅失败（忽略）: {e}")
        self._subscriptions.clear()
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
            try:
                bg = self.container.cget("bg")
            except tk.TclError:
                bg = ""
            frame = tk.Frame(self.container, bg=bg) if bg else tk.Frame(self.container)
            self._frames[key] = frame
        return frame

    @staticmethod
    def _safe(panel: BasePanel, method: str, key: str) -> None:
        try:
            getattr(panel, method)()
        except Exception as e:  # noqa: BLE001 - 生命周期钩子不得中断切换
            logger.error(f"面板 {key!r} 的 {method}() 抛错: {type(e).__name__}: {e}")
