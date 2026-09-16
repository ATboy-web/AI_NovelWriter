"""事件总线测试（v3 §2.3）。

总线是「面板 ↔ 主面板联动」的唯一底座，因此这里盯死四件事：

1. **投递语义**：订阅/取消/通配、处理器签名统一为 `(topic, payload)`
2. **异常隔离**：一个订阅者抛错不得影响其他订阅者（面板是并列关系，不是调用链）
3. **线程模型**：子线程发布必须改道到主线程排队 —— Tk 非线程安全，
   而本仓有 40 处裸 `threading.Thread`
4. **不漏登记**：定义了 `TOPIC_*` 常量却忘了放进 `ALL_TOPICS`，
   会让宿主静默不转发该事件（这类漏项只能靠源码扫描发现）
"""

import re
import sys
import threading
from pathlib import Path

import pytest

from app.events import (
    ALL_TOPICS,
    TOPIC_AI_USAGE,
    TOPIC_BIOGRAPHY_GENERATED,
    TOPIC_CHAPTER_SAVED,
    TOPIC_CHARACTER_CHANGED,
    TOPIC_CONFIG_CHANGED,
    TOPIC_NOVEL_CLOSED,
    TOPIC_NOVEL_OPENED,
    TOPIC_OUTLINE_CHANGED,
    TOPIC_TIMELINE_CHANGED,
    WILDCARD,
    EventBus,
    EventSink,
)
from app.events.bus import publish_threadaware

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


class FakeRoot:
    """只实现 `after`：把回调存起来，由测试显式 flush（模拟主线程事件循环）。"""

    def __init__(self):
        self.pending = []

    def after(self, _delay, fn):
        self.pending.append(fn)

    def flush(self):
        queued, self.pending = list(self.pending), []
        for fn in queued:
            fn()
        return len(queued)


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, topic, payload=None):
        self.events.append((topic, payload))

    def topics(self):
        return [t for t, _p in self.events]


# ============================================================ 投递语义


class TestDelivery:
    def test_subscribe_publish_delivers_topic_and_payload(self):
        bus = EventBus(name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        dispatched = bus.publish(TOPIC_CHAPTER_SAVED, {"chapter": 3})

        assert dispatched == 1
        assert rec.events == [(TOPIC_CHAPTER_SAVED, {"chapter": 3})]

    def test_handler_signature_is_always_topic_and_payload(self):
        """统一签名让 `BasePanel.on_event` 能直接当处理器用，不必包 lambda。"""
        bus = EventBus(name="t")
        seen = []

        def handler(topic, payload):
            seen.append((topic, payload))

        bus.subscribe(TOPIC_NOVEL_OPENED, handler)
        bus.publish(TOPIC_NOVEL_OPENED)

        assert seen == [(TOPIC_NOVEL_OPENED, None)]

    def test_unrelated_topics_are_not_delivered(self):
        bus = EventBus(name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        assert bus.publish(TOPIC_OUTLINE_CHANGED, {}) == 0
        assert rec.events == []

    def test_wildcard_receives_everything(self):
        bus = EventBus(name="t")
        rec = Recorder()
        bus.subscribe(WILDCARD, rec)

        bus.publish(TOPIC_CHAPTER_SAVED, 1)
        bus.publish(TOPIC_AI_USAGE, 2)

        assert rec.topics() == [TOPIC_CHAPTER_SAVED, TOPIC_AI_USAGE]

    def test_wildcard_and_exact_on_same_handler_delivers_twice(self):
        """刻意保留的直白语义：不去重（绑定方法每次取值都是新对象，去重会时灵时不灵）。"""
        bus = EventBus(name="t")
        rec = Recorder()
        bus.subscribe(WILDCARD, rec)
        bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        assert bus.publish(TOPIC_CHAPTER_SAVED) == 2
        assert len(rec.events) == 2

    def test_unsubscribe_is_idempotent(self):
        bus = EventBus(name="t")
        rec = Recorder()
        off = bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        assert bus.unsubscribe(TOPIC_CHAPTER_SAVED, rec) is True
        assert bus.unsubscribe(TOPIC_CHAPTER_SAVED, rec) is False
        off()  # 再调用一次不得抛错

        assert bus.publish(TOPIC_CHAPTER_SAVED) == 0

    def test_unsubscribe_handle_from_closure(self):
        bus = EventBus(name="t")
        rec = Recorder()
        off = bus.subscribe(TOPIC_CHAPTER_SAVED, rec)
        off()
        assert rec.events == []

    def test_multiple_handlers_run_in_subscription_order(self):
        bus = EventBus(name="t")
        order = []
        bus.subscribe(TOPIC_CHAPTER_SAVED, lambda t, p: order.append("a"))
        bus.subscribe(TOPIC_CHAPTER_SAVED, lambda t, p: order.append("b"))

        bus.publish(TOPIC_CHAPTER_SAVED)

        assert order == ["a", "b"]

    def test_handler_may_unsubscribe_during_dispatch(self):
        """派发中改订阅表不得影响本次派发（内部用快照）。"""
        bus = EventBus(name="t")
        order = []

        def first(topic, payload):
            order.append("first")
            bus.unsubscribe(TOPIC_CHAPTER_SAVED, second)

        def second(topic, payload):
            order.append("second")

        bus.subscribe(TOPIC_CHAPTER_SAVED, first)
        bus.subscribe(TOPIC_CHAPTER_SAVED, second)

        bus.publish(TOPIC_CHAPTER_SAVED)

        assert order == ["first", "second"]  # 快照生效，本次仍会调用 second

    def test_subscribe_validates_arguments(self):
        bus = EventBus(name="t")
        with pytest.raises(ValueError):
            bus.subscribe("", lambda t, p: None)
        with pytest.raises(TypeError):
            bus.subscribe(TOPIC_CHAPTER_SAVED, "not-callable")


# ============================================================ 异常隔离


class TestErrorIsolation:
    def test_broken_handler_does_not_stop_others(self):
        bus = EventBus(name="t")
        rec = Recorder()

        def boom(topic, payload):
            raise RuntimeError("面板炸了")

        bus.subscribe(TOPIC_CHAPTER_SAVED, boom)
        bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        dispatched = bus.publish(TOPIC_CHAPTER_SAVED)

        assert dispatched == 1          # 只有正常的那个算成功
        assert rec.events                # 但它确实收到了
        assert bus.error_count == 1

    def test_error_count_accumulates_and_is_observable(self):
        """被隔离的异常不能静默消失：计数器 + 日志是唯一线索。"""
        bus = EventBus(name="t")
        bus.subscribe(TOPIC_CHAPTER_SAVED, lambda t, p: 1 / 0)

        bus.publish(TOPIC_CHAPTER_SAVED)
        bus.publish(TOPIC_CHAPTER_SAVED)

        assert bus.error_count == 2


# ============================================================ 线程模型


class TestThreadModel:
    def test_publish_from_worker_thread_is_rerouted(self):
        root = FakeRoot()
        bus = EventBus(root=root, name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_CHAPTER_SAVED, rec)

        result = {}

        def worker():
            result["ret"] = bus.publish(TOPIC_CHAPTER_SAVED, {"chapter": 9})

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert result["ret"] == -1        # -1 = 已改道排队，未同步派发
        assert rec.events == []           # 还没派发
        assert root.flush() == 1          # 已排进主线程队列
        assert rec.events == [(TOPIC_CHAPTER_SAVED, {"chapter": 9})]

    def test_publish_threadsafe_queues_via_after(self):
        root = FakeRoot()
        bus = EventBus(root=root, name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_AI_USAGE, rec)

        assert bus.publish_threadsafe(TOPIC_AI_USAGE, {"tokens": 5}) is True
        assert rec.events == []
        root.flush()
        assert rec.events == [(TOPIC_AI_USAGE, {"tokens": 5})]

    def test_publish_threadsafe_without_root_dispatches_inline(self):
        """没有 Tk（单测 / 无 GUI 环境）时退化为就地派发，事件链仍可验证。"""
        bus = EventBus(name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_AI_USAGE, rec)

        assert bus.publish_threadsafe(TOPIC_AI_USAGE, 1) is False
        assert rec.events == [(TOPIC_AI_USAGE, 1)]

    def test_publish_threadsafe_survives_dead_root(self):
        """窗口已销毁时 `after` 抛 RuntimeError，不得把调用方带崩。"""

        class DeadRoot:
            def after(self, _delay, _fn):
                raise RuntimeError("main thread is not in main loop")

        bus = EventBus(root=DeadRoot(), name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_AI_USAGE, rec)

        assert bus.publish_threadsafe(TOPIC_AI_USAGE, 1) is False
        assert rec.events == [(TOPIC_AI_USAGE, 1)]   # 降级为就地派发


# ============================================================ 查询与门面


class TestQueriesAndSink:
    def test_topics_and_counts(self):
        bus = EventBus(name="t")
        bus.subscribe(TOPIC_CHAPTER_SAVED, lambda t, p: None)
        bus.subscribe(WILDCARD, lambda t, p: None)

        assert bus.topics() == sorted([TOPIC_CHAPTER_SAVED, WILDCARD])
        assert bus.subscriber_count(TOPIC_CHAPTER_SAVED) == 1
        assert bus.has_subscribers(TOPIC_CHAPTER_SAVED) is True   # 靠通配
        assert bus.has_subscribers(TOPIC_NOVEL_OPENED) is True     # 靠通配
        assert bus.has_subscribers(WILDCARD) is True

    def test_has_subscribers_without_wildcard(self):
        bus = EventBus(name="t")
        assert bus.has_subscribers(TOPIC_CHAPTER_SAVED) is False

    def test_unsubscribe_all(self):
        bus = EventBus(name="t")
        bus.subscribe(TOPIC_CHAPTER_SAVED, lambda t, p: None)
        bus.subscribe(TOPIC_AI_USAGE, lambda t, p: None)

        assert bus.unsubscribe_all() == 2
        assert bus.publish(TOPIC_CHAPTER_SAVED) == 0

    def test_sink_is_stable_and_thread_routed(self):
        root = FakeRoot()
        bus = EventBus(root=root, name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_AI_USAGE, rec)

        sink = bus.sink()
        assert isinstance(sink, EventSink)
        assert bus.sink() is sink            # 同一总线只造一个门面
        assert sink.bus is bus

        sink.publish(TOPIC_AI_USAGE, {"a": 1})       # 主线程 → 同步
        assert rec.events == [(TOPIC_AI_USAGE, {"a": 1})]

        thread = threading.Thread(target=lambda: sink.publish(TOPIC_AI_USAGE, {"a": 2}))
        thread.start()
        thread.join()
        assert rec.events == [(TOPIC_AI_USAGE, {"a": 1})]   # 未入库
        root.flush()
        assert len(rec.events) == 2

    def test_sink_subscribe_delegates(self):
        bus = EventBus(name="t")
        rec = Recorder()
        bus.sink().subscribe(TOPIC_CHAPTER_SAVED, rec)
        bus.publish(TOPIC_CHAPTER_SAVED)
        assert rec.events

    def test_publish_threadaware_helper(self):
        root = FakeRoot()
        bus = EventBus(root=root, name="t")
        rec = Recorder()
        bus.subscribe(TOPIC_CONFIG_CHANGED, rec)

        publish_threadaware(bus, TOPIC_CONFIG_CHANGED, 1)      # 主线程 → 立即
        assert len(rec.events) == 1

        thread = threading.Thread(target=lambda: publish_threadaware(bus, TOPIC_CONFIG_CHANGED, 2))
        thread.start()
        thread.join()
        assert len(rec.events) == 1                            # 排队中
        root.flush()
        assert len(rec.events) == 2


# ============================================================ 主题常量的完整性


class TestTopicConstants:
    def test_all_topics_covers_every_defined_topic(self):
        """定义了 `TOPIC_*` 却漏放进 `ALL_TOPICS`，宿主就不会转发它（静默失效）。"""
        src = _scan.read("app/events/bus.py")
        pairs = re.findall(r'^(TOPIC_[A-Z_]+)\s*=\s*"([^"]+)"', src, re.MULTILINE)
        name_to_value = dict(pairs)

        assert name_to_value, "没扫到任何 TOPIC_* 常量，扫描正则可能已失效"
        missing = sorted(set(name_to_value.values()) - set(ALL_TOPICS))
        assert not missing, f"这些主题没有进 ALL_TOPICS：{missing}"

    def test_roadmap_topics_are_all_present(self):
        """ROADMAP §2.3 表格里的 9 个主题必须一个不少（联动链路都挂在它们上）。"""
        assert set(ALL_TOPICS) == {
            TOPIC_NOVEL_OPENED, TOPIC_NOVEL_CLOSED,
            TOPIC_CHAPTER_SAVED, TOPIC_OUTLINE_CHANGED,
            TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED,
            TOPIC_BIOGRAPHY_GENERATED, TOPIC_AI_USAGE,
            TOPIC_CONFIG_CHANGED,
        }

    def test_topic_values_are_domain_named(self):
        """主题名必须是领域事件（`a.b` 小写），不是 UI 事件名 —— 否则联动无法复用。"""
        for topic in ALL_TOPICS:
            assert re.fullmatch(r"[a-z]+\.[a-z_]+", topic), topic
