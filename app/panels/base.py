"""面板基类（v3 §2.2）。

## 为什么要基类

v2 的 12 个工具面板是 12 个 Mixin，靠 `toolkit_ui._refresh_toolkit()` 里 12 路 `if/elif`
手工分发，既没有生命周期（谁被隐藏了？谁该刷新？），也没有统一的容器概念
（全都往 `self.tool_content_frame` 里画）。新增一个面板要在 5 个文件里各改一处。

`BasePanel` 把"面板"变成一等对象：有元数据（key/title/category/order）、
有生命周期（build/on_show/on_hide/detach）、有联动入口（on_event）。

## `__getattr__` + `__setattr__` 代理：迁移的关键（也是对 ROADMAP 方案的补强）

ROADMAP §2.2 只给了 `__getattr__`。只代理读是不够的，因为 v2 面板**把控件挂在 self 上**：

    # elements_panel.py:43（构建时写入）
    self.elem_result = scrolledtext.ScrolledText(f, ...)
    # elements_panel.py:66（回调里读出）
    self.elem_result.delete("1.0", tk.END)

而 `chapter_analysis_panel.py:378` 写的是真正的应用状态 `self.current_chapter = chapter_num`。
在 v2 里这些 `self` **就是应用本身**，所以写入落在 `app` 上、回调从 `app` 读得到。
迁移时若只代理读，构建写进面板、回调读的是应用 —— 控件引用直接丢失，面板静默失灵。

因此 `LegacyPanelAdapter` 打开 `proxy_writes`：**未声明的属性写入一律转发给宿主**，
与 v2 完全同义；只有 `LOCAL_ATTRS` 里声明的面板私有名（`app` / `tool_content_frame`）
留在面板自己身上 —— 后者正是"每个面板各有一个容器"得以成立的原因。

结论：v2 面板**一行不用改**，且写入落点与 v2 逐字节等价。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, ClassVar

__all__ = ["BasePanel"]


class BasePanel:
    """所有面板的抽象基类（迁移面板见 `legacy.LegacyPanelAdapter`）。"""

    # ------------------------------------------------------------------ 元数据

    #: 唯一键，用作选择器的值与持久化的标识（如 `"timeline"`）
    key: str = ""
    #: 显示名（如 `"世界线与时间线"`）
    title: str = ""
    #: 分组小标题，取值见 `registry.CATEGORY_ORDER`
    category: str = "运维"
    #: 组内排序，越小越靠前
    order: int = 100
    #: 一句话说明（选择器 tooltip 与自检报告用）
    description: str = ""
    # 注：P4a 曾声明 `requires_novel`，但宿主/选择器从未读取它（零可观察面），
    # 且各面板本就会自行显示"请先新建或打开小说"。按本仓死代码判据已移除；
    # 若将来真要"宿主提前拦一道"，请连同**消费者**一起加，而不是只加标记。

    #: 属性写入是否转发给宿主 —— **只有迁移适配器打开**，见模块文档
    proxy_writes: ClassVar[bool] = False

    #: 面板私有、永不代理的属性名
    LOCAL_ATTRS: ClassVar[frozenset[str]] = frozenset({"app", "tool_content_frame"})

    #: 面板感兴趣的主题（**订阅总线的唯一开关**）。
    #: 空元组 = 不订阅 —— 迁移来的 v2 面板就是这种情况：它们没有 `on_event`，
    #: 订阅只会得到 12 个永远不干活的处理器。面板声明了自己关心什么，
    #: 宿主才会把它接上总线。
    topics_of_interest: ClassVar[tuple[str, ...]] = ()

    # ------------------------------------------------------------------ 构造

    def __init__(self, app: Any = None) -> None:
        # 用 object.__setattr__ 绕开本类的 __setattr__：`app` 必须落在面板自己身上，
        # 否则代理就没有宿主可指向了（鸡生蛋问题）。
        object.__setattr__(self, "app", app)
        object.__setattr__(self, "_built", False)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """子类带非空 `key` 时自动登记进注册表（v3「新增面板只需 1 处改动」）。

        只新建文件 + 在 `registry.NATIVE_PANEL_MODULES` 加一行导入，分发层零改动。
        """
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "key", ""):
            return
        from .registry import register  # 延迟导入：registry 需反向引用本模块做类型标注

        register(cls)

    # ------------------------------------------------------------------ 代理

    def __getattr__(self, name: str) -> Any:
        """仅在常规属性查找失败时触发：把读取转发给宿主。

        这让面板可以直接写 `self.ai_client` / `self.current_novel_dir` / `self._log`，
        与 v2 的写法完全一致。
        """
        # 不代理 dunder：`copy` / `pickle` 等协议会探测一堆 `__xxx__`，
        # 转发到宿主只会得到一堆迷惑的 AttributeError 或错误命中。
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        app = self.__dict__.get("app")
        if app is None:
            raise AttributeError(f"{type(self).__name__} 未绑定宿主，无法解析 {name!r}")
        return getattr(app, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """属性写入策略。

        默认写在面板自己身上（v3 原生面板的正常行为）；
        `proxy_writes=True` 的迁移面板则把非私有名转发给宿主，与 v2 语义一致。
        """
        if not type(self).proxy_writes or name in type(self).LOCAL_ATTRS or name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        app = self.__dict__.get("app")
        if app is None:
            object.__setattr__(self, name, value)
            return
        setattr(app, name, value)

    # ------------------------------------------------------------------ 生命周期

    def build(self, parent: tk.Widget) -> tk.Widget:
        """首次构建，把内容画进 `parent`。返回放入容器的控件（默认就是 `parent`）。"""
        raise NotImplementedError(f"{type(self).__name__}.build() 未实现")

    def on_show(self) -> None:
        """每次被显示时调用（替代 v2 手工到处调 `_refresh_toolkit` 的做法）。"""

    def on_hide(self) -> None:
        """被切走时调用。"""

    def on_event(self, topic: str, payload: Any = None) -> None:
        """联动入口。签名与 `EventBus` 处理器一致，可直接 `bus.subscribe(topic, panel.on_event)`。

        约定：面板**自行过滤**不需要的主题（默认实现不做事）。
        """

    def detach(self) -> None:
        """脱离宿主（面板被移除 / 应用关闭）。取消订阅由宿主统一负责。"""
        try:
            self.on_hide()
        finally:
            object.__setattr__(self, "app", None)
            object.__setattr__(self, "_built", False)

    # ------------------------------------------------------------------ 辅助

    @property
    def is_built(self) -> bool:
        return bool(self.__dict__.get("_built", False))

    def mark_built(self, built: bool = True) -> None:
        object.__setattr__(self, "_built", built)

    def attach_events(self, bus: Any, topics: tuple[str, ...] | None = None) -> list[Callable[[], None]]:
        """把 `on_event` 挂到总线，返回取消订阅句柄列表（宿主负责在 `detach_all` 时调用）。

        订阅范围取 `topics` 参数，未传则取类属性 `topics_of_interest`；
        两者都为空时**不订阅任何主题**并返回空列表 —— 见 `topics_of_interest` 的说明。
        """
        from app.events import WILDCARD

        targets = tuple(topics) if topics else tuple(self.topics_of_interest)
        if not targets:
            return []
        if WILDCARD in targets:
            # 通配已经覆盖一切，避免与具体主题同时订阅导致同一事件被投递两遍
            targets = (WILDCARD,)
        return [bus.subscribe(topic, self.on_event) for topic in targets]

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"<{type(self).__name__} key={self.key!r} title={self.title!r}>"
