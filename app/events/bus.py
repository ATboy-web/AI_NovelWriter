"""领域事件总线（v3 §2.3）。

## 它替代了什么

v2 的面板之间只能靠 MRO 共享同一个 `self` 互相偷看状态，跨面板联动全仓只有两个土办法：
`toolkit_ui._insert_to_chapter()` 回写主编辑器、`_generate_cover()` 里 `notebook.select(2)` 硬跳标签页。
这种耦合不可扩展 —— 世界线面板想知道"章节保存了"，只能去读 `chapter_ui` 的私有状态。

本模块给出唯一通道：**领域事件**。发布方只说"发生了什么"（`chapter.saved`），不关心谁在听；
订阅方只说自己关心什么，不关心是谁发出来的。事件名用**领域**命名而非 UI 命名，
这样"保存章节"这个事实可以同时驱动时间线抽事件、用量面板归因、角色面板刷新，
将来加第 4 个消费者时，前面三处一行都不用改。

## 线程模型（本模块唯一容易踩的坑）

Tk 非线程安全，而本仓有 40 处裸 `threading.Thread` 在子线程里干活。因此：

- `publish()` 要求在主线程调用。若被别的线程调用，**不静默地在子线程里碰控件**，
  而是自动改道到 `publish_threadsafe()` 并记一条 warning —— 降级到排队派发，
  总好过偶发的 Tcl 崩溃。
- `publish_threadsafe()` 内部统一 `root.after(0, ...)`，与 `bridges_panel.py` 既有写法一致。
- 没有 `root` 时（单测 / 无 GUI 环境）`publish_threadsafe` **就地同步派发**并返回 `False`，
  让"没装 Tk 也能测事件链"成立。

## 处理器签名

统一为 `handler(topic, payload)`，不做 `handler(payload)` 的重载 ——
单一签名让「精确订阅」与「通配订阅」共用一套接口，也让 `BasePanel.on_event(topic, payload)`
可以**直接**当处理器用，不需要包一层 lambda。

## 异常隔离

面板之间是并列关系，不是调用链：一个订阅者抛异常不得中断其他订阅者。
每个处理器单独 `try/except`，失败计数并写日志后继续派发下一个。
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from loguru import logger

__all__ = [
    "ALL_TOPICS",
    "EventBus",
    "EventSink",
    "WILDCARD",
    "publish_threadaware",
    "TOPIC_AI_USAGE",
    "TOPIC_BIOGRAPHY_GENERATED",
    "TOPIC_CHAPTER_SAVED",
    "TOPIC_CHARACTER_CHANGED",
    "TOPIC_CONFIG_CHANGED",
    "TOPIC_NOVEL_CLOSED",
    "TOPIC_NOVEL_OPENED",
    "TOPIC_OUTLINE_CHANGED",
    "TOPIC_TIMELINE_CHANGED",
]

#: 订阅全部主题（通配）。用于面板宿主统一转发，见 `app/panels/host.py`。
WILDCARD = "*"

# ---- 领域事件主题（v3 §2.3 表）------------------------------------------------
#: 打开/关闭小说 —— 全部面板刷新到新小说
TOPIC_NOVEL_OPENED = "novel.opened"
TOPIC_NOVEL_CLOSED = "novel.closed"
#: 章节保存（`chapter_ui` 保存 / `finalize_chapter`）
TOPIC_CHAPTER_SAVED = "chapter.saved"
#: 大纲写盘（`NovelStore.write_outline`）
TOPIC_OUTLINE_CHANGED = "outline.changed"
#: 角色写盘成功（`memory_manager.save_characters` 之后）
TOPIC_CHARACTER_CHANGED = "character.changed"
#: 时间线事件追加（`memory_manager.add_event` 之后）
TOPIC_TIMELINE_CHANGED = "timeline.changed"
#: 传记生成完成
TOPIC_BIOGRAPHY_GENERATED = "biography.generated"
#: 一次 AI 调用落了用量记录
TOPIC_AI_USAGE = "ai.usage"
#: 设置已保存
TOPIC_CONFIG_CHANGED = "config.changed"

#: 全部已知主题。宿主用它一次性订阅（未列入的临时主题仍可正常收发，只是不会被自动转发）
ALL_TOPICS: tuple[str, ...] = (
    TOPIC_NOVEL_OPENED,
    TOPIC_NOVEL_CLOSED,
    TOPIC_CHAPTER_SAVED,
    TOPIC_OUTLINE_CHANGED,
    TOPIC_CHARACTER_CHANGED,
    TOPIC_TIMELINE_CHANGED,
    TOPIC_BIOGRAPHY_GENERATED,
    TOPIC_AI_USAGE,
    TOPIC_CONFIG_CHANGED,
)


class EventBus:
    """极简主题订阅/发布总线。

    Parameters
    ----------
    root : 具备 `after(0, fn)` 的对象（通常是 `tk.Tk`）。
        `None` 表示无 GUI 环境，此时 `publish_threadsafe` 就地派发。
    name : 日志前缀，便于区分多个总线实例（测试里常见）。
    """

    def __init__(self, root: Any = None, name: str = "event-bus") -> None:
        self._root = root
        self._name = name
        self._handlers: dict[str, list[Callable[..., Any]]] = {}
        self._lock = threading.RLock()
        #: 构造它的线程被视为"主线程"；只有它能直接派发
        self._owner = threading.get_ident()
        self._errors = 0
        self._sink: EventSink | None = None

    # ------------------------------------------------------------------ 订阅

    def subscribe(self, topic: str, handler: Callable[..., Any]) -> Callable[[], None]:
        """订阅 `topic`，返回**取消订阅**的可调用对象（幂等，重复调用无副作用）。

        `topic` 用 `WILDCARD` 可订阅全部事件；同一处理器若同时订阅了 `*` 与具体主题，
        会收到两次 —— 这是刻意保留的直白语义（不做 `id()` 去重：绑定方法每次取值
        都是新对象，去重只会带来"有时去重有时不去重"的迷惑行为）。
        """
        if not isinstance(topic, str) or not topic:
            raise ValueError("topic 必须是非空字符串")
        if not callable(handler):
            raise TypeError(f"handler 必须可调用，收到 {type(handler).__name__}")
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

        def _unsubscribe() -> None:
            self.unsubscribe(topic, handler)

        return _unsubscribe

    def unsubscribe(self, topic: str, handler: Callable[..., Any]) -> bool:
        """取消一个订阅。返回是否真的移除了一条。"""
        with self._lock:
            bucket = self._handlers.get(topic)
            if not bucket:
                return False
            try:
                bucket.remove(handler)
            except ValueError:
                return False
            if not bucket:
                self._handlers.pop(topic, None)
            return True

    def unsubscribe_all(self, topic: str | None = None) -> int:
        """清空某主题的订阅；`topic=None` 时清空全部。返回移除的处理器个数。"""
        with self._lock:
            if topic is None:
                count = sum(len(v) for v in self._handlers.values())
                self._handlers.clear()
                return count
            return len(self._handlers.pop(topic, ()))

    # ------------------------------------------------------------------ 查询

    def subscriber_count(self, topic: str) -> int:
        with self._lock:
            return len(self._handlers.get(topic, ()))

    def has_subscribers(self, topic: str) -> bool:
        """该主题的直接订阅者或通配订阅者是否有任意一个。"""
        with self._lock:
            # `topic == WILDCARD` 时不能重复计数，故用分支而不是 `or`
            if topic == WILDCARD:
                return bool(self._handlers.get(WILDCARD))
            return bool(self._handlers.get(topic) or self._handlers.get(WILDCARD))

    def topics(self) -> list[str]:
        """当前有订阅者的主题（排序，便于断言与调试）。"""
        with self._lock:
            return sorted(self._handlers)

    @property
    def error_count(self) -> int:
        """累计被隔离掉的处理器异常数（面板坏了不该让事件静默消失，故可观测）。"""
        return self._errors

    # ------------------------------------------------------------------ 发布

    def publish(self, topic: str, payload: Any = None) -> int:
        """在主线程**同步**派发事件。

        返回被成功调用的处理器个数；若因跨线程被改道到 `publish_threadsafe()`，
        返回 `-1`（"已排队，未同步派发"）—— 用 `-1` 而不是 `0`，
        是为了让"没人订阅"与"改道了"这两件事在调用方眼里可区分。
        """
        if threading.get_ident() != self._owner:
            logger.warning(f"[{self._name}] publish('{topic}') 在非主线程被调用，已改道 publish_threadsafe 排队派发")
            self.publish_threadsafe(topic, payload)
            return -1
        return self._dispatch(topic, payload)

    def publish_threadsafe(self, topic: str, payload: Any = None) -> bool:
        """从后台线程发布：排入主线程队列后再派发。

        返回 `True` 表示已成功排入 `root.after` 队列（稍后异步派发）；
        返回 `False` 表示没有可用的 Tk（无 root 或窗口已销毁），此时**就地同步派发**。
        """
        root = self._root
        if root is not None and hasattr(root, "after"):
            try:
                root.after(0, lambda: self._dispatch(topic, payload))
                return True
            except (RuntimeError, AttributeError) as e:
                # 窗口已销毁 / 主循环已退出：不是错误，只是没有主线程可用了
                logger.debug(f"[{self._name}] 事件 {topic} 无法排入主线程（{e}），就地派发")
        # 无 Tk：就地同步派发。这是单测与无 GUI 环境下事件链仍可验证的原因。
        self._dispatch(topic, payload)
        return False

    # ------------------------------------------------------------------ 门面

    def sink(self) -> EventSink:
        """返回一个只暴露 `publish`/`subscribe` 的门面（同一个总线只造一个）。"""
        if self._sink is None:
            self._sink = EventSink(self)
        return self._sink

    # ------------------------------------------------------------------ 内部

    def _dispatch(self, topic: str, payload: Any) -> int:
        """实际调用处理器：快照订阅列表 + 逐个异常隔离。"""
        with self._lock:
            handlers = list(self._handlers.get(topic, ()))
            if topic != WILDCARD:
                handlers += list(self._handlers.get(WILDCARD, ()))

        dispatched = 0
        for handler in handlers:
            try:
                handler(topic, payload)
            except Exception as e:  # noqa: BLE001 - 隔离是这里唯一的职责
                self._errors += 1
                logger.error(
                    f"[{self._name}] 事件 {topic} 的订阅者 "
                    f"{getattr(handler, '__qualname__', handler)!r} 抛错（已隔离，继续派发）: "
                    f"{type(e).__name__}: {e}"
                )
            else:
                dispatched += 1
        return dispatched


# ---------------------------------------------------------------------- 门面


def publish_threadaware(bus: EventBus, topic: str, payload: Any = None) -> None:
    """按调用线程选路发布：主线程同步派发，后台线程排队派发。

    线程判断只写在这一处：调用方（章节保存 / 时间线 / 角色 / 用量 / 配置）
    都不必各自操心"我这会儿在哪个线程"。
    """
    if threading.current_thread() is threading.main_thread():
        bus.publish(topic, payload)
    else:
        bus.publish_threadsafe(topic, payload)


class EventSink:
    """只暴露 `publish` / `subscribe` 的瘦门面，内部按调用线程自动选路。

    **为什么需要它**：`NovelStore(events=...)`（v3 A7）与
    `MemoryManager.set_event_sink()` 都是**鸭子类型注入** —— 只要求对象有
    `publish(topic, payload)`。但这些组件的写盘大量发生在后台线程
    （本仓 40 处 `threading.Thread`），若直接注入 `EventBus`，
    每次都会触发跨线程改道告警，噪声会淹没真正的问题。
    门面把线程判断收进来，注入方与订阅方都不必知道这件事。
    """

    __slots__ = ("_bus",)

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    @property
    def bus(self) -> EventBus:
        """背后的真实总线（需要精确控制线程时用）。"""
        return self._bus

    def publish(self, topic: str, payload: Any = None) -> None:
        publish_threadaware(self._bus, topic, payload)

    def subscribe(self, topic: str, handler: Callable[..., Any]) -> Callable[[], None]:
        return self._bus.subscribe(topic, handler)

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"<EventSink bus={self._bus!r}>"
