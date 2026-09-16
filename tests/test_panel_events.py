"""事件接线测试（v3 §2.3）。

总线和面板框架是「管道」，本文件验证的是**管道真的接上了**：

| 触发点 | 主题 | 谁来发 |
|---|---|---|
| 打开/新建/续集/同人 | `novel.opened` | `lifecycle_ui._announce_novel_opened` |
| 章节保存（两条路径） | `chapter.saved` | `chapter_ui._announce_chapter_saved` |
| `save_characters` 写盘成功 | `character.changed` | `MemoryManager._emit` |
| `add_event` 写盘成功 | `timeline.changed` | `MemoryManager._emit` |
| `NovelStore.write_outline` | `outline.changed` | P1 已存在的注入点 |
| `usage_tracker.record` | `ai.usage` | `usage_tracker._emit_usage_event` |
| 设置保存 | `config.changed` | `lifecycle_ui` 的 save 闭包 |

两条刻意坚持的原则：

1. **只在写盘成功后广播**：角色档案的两道闸门抛错时不得广播
   —— 否则面板会被"其实没写成功"的假事件叫醒。
2. **广播失败不影响写盘**：事件是旁路，数据落盘才是主职责。
"""

import sys
from pathlib import Path

import pytest

from app.events import (
    TOPIC_AI_USAGE,
    TOPIC_CHARACTER_CHANGED,
    TOPIC_OUTLINE_CHANGED,
    TOPIC_TIMELINE_CHANGED,
    EventBus,
)
from app.lifecycle_ui import NovelLifecycleMixin
from app.memory_manager import CharacterDataGuardError, MemoryManager
from app.novel_store import NovelStore
from app.shell_ui import ShellMixin
from app.usage_tracker import usage_tracker

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


class SinkRecorder:
    """鸭子类型的事件出口（与 `NovelStore(events=...)` 的约定一致：只要有 `publish`）。"""

    def __init__(self):
        self.events = []

    def publish(self, topic, payload=None):
        self.events.append((topic, payload))

    def topics(self):
        return [topic for topic, _payload in self.events]


class BrokenSink:
    def publish(self, topic, payload=None):
        raise RuntimeError("订阅方炸了")


class TopicRecorder:
    def __init__(self):
        self.events = []

    def __call__(self, topic, payload=None):
        self.events.append((topic, payload))


# ============================================================ MemoryManager


class TestMemoryManagerEvents:
    def test_add_event_broadcasts_timeline_changed(self, tmp_path):
        memory = MemoryManager(tmp_path)
        sink = SinkRecorder()
        memory.set_event_sink(sink)

        memory.add_event(3, "主角得到断剑", characters_involved=["张三"])

        assert sink.topics() == [TOPIC_TIMELINE_CHANGED]
        _topic, payload = sink.events[0]
        assert payload["chapter"] == 3
        assert payload["characters"] == ["张三"]
        assert Path(payload["page_file"]).exists()      # 广播的一定是已落盘的事实

    def test_save_characters_broadcasts_character_changed(self, tmp_path):
        memory = MemoryManager(tmp_path)
        sink = SinkRecorder()
        memory.set_event_sink(sink)

        memory.save_characters({"张三": {"name": "张三"}})

        assert sink.topics() == [TOPIC_CHARACTER_CHANGED]
        assert sink.events[0][1]["count"] == 1

    def test_character_guard_failure_does_not_broadcast(self, tmp_path):
        """闸门拒绝写入时不能广播 —— 否则面板会被假事件叫醒。"""
        memory = MemoryManager(tmp_path)
        memory.save_characters({"张三": {"name": "张三"}})
        sink = SinkRecorder()
        memory.set_event_sink(sink)

        with pytest.raises(CharacterDataGuardError):
            memory.save_characters({})

        assert sink.events == []

    def test_mutate_characters_also_broadcasts(self, tmp_path):
        """`update_character` 等增量修改走 mutate → save，同样要广播。"""
        memory = MemoryManager(tmp_path)
        memory.save_characters({"张三": {"name": "张三"}})
        sink = SinkRecorder()
        memory.set_event_sink(sink)

        memory.mutate_characters(lambda chars: {**chars, "李四": {"name": "李四"}})

        assert sink.topics() == [TOPIC_CHARACTER_CHANGED]
        assert sink.events[0][1]["count"] == 2

    def test_no_sink_means_silent(self, tmp_path):
        """默认不广播：本类在单测、CLI 与后端服务里必须零副作用。"""
        memory = MemoryManager(tmp_path)
        assert memory.event_sink is None
        memory.add_event(1, "无事发生")              # 不应抛异常

    def test_broken_sink_does_not_break_writes(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.set_event_sink(BrokenSink())

        memory.add_event(1, "事件")                  # 广播失败不影响写盘
        memory.save_characters({"张三": {"name": "张三"}})

        assert memory.get_characters()                # 数据确实写进去了

    def test_bus_sink_is_a_valid_duck_typed_sink(self, tmp_path):
        """`EventBus.sink()` 必须满足 `publish(topic, payload)` 的注入约定。"""
        bus = EventBus(name="t")
        rec = TopicRecorder()
        bus.subscribe(TOPIC_TIMELINE_CHANGED, rec)

        memory = MemoryManager(tmp_path)
        memory.set_event_sink(bus.sink())
        memory.add_event(2, "事件")

        assert rec.events and rec.events[0][0] == TOPIC_TIMELINE_CHANGED


# ============================================================ NovelStore（P1 注入点）


class TestNovelStoreEvents:
    def test_write_outline_broadcasts_outline_changed(self, tmp_path):
        bus = EventBus(name="t")
        rec = TopicRecorder()
        bus.subscribe(TOPIC_OUTLINE_CHANGED, rec)

        store = NovelStore(tmp_path, events=bus.sink())
        store.write_outline([{"chapter": 1, "title": "开端"}])

        assert [topic for topic, _p in rec.events] == [TOPIC_OUTLINE_CHANGED]
        assert rec.events[0][1]["count"] == 1

    def test_append_outline_also_broadcasts(self, tmp_path):
        bus = EventBus(name="t")
        rec = TopicRecorder()
        bus.subscribe(TOPIC_OUTLINE_CHANGED, rec)

        store = NovelStore(tmp_path, events=bus.sink())
        store.append_outline([{"chapter": 1}, {"chapter": 2}])

        assert rec.events[0][1]["count"] == 2

    def test_persistence_ui_injects_the_app_sink(self):
        """`persistence_ui` 早就写好了注入点，缺的只是"应用确实提供 `self.events`"。"""
        assert 'getattr(self, "events", None)' in _scan.code_only("app/persistence_ui.py")
        app_code = _scan.code_only("novel_app.py")
        assert "self.events = self.event_bus.sink()" in app_code


# ============================================================ 用量记账


@pytest.fixture
def isolated_tracker():
    """隔离全局单例的用量记账器（它是一个模块级单例，测试必须自己收拾干净）。"""
    backup_memory = list(usage_tracker._memory)
    backup_sink = usage_tracker._event_sink
    backup_dir = usage_tracker._novel_dir
    try:
        yield usage_tracker
    finally:
        usage_tracker._memory = backup_memory
        usage_tracker._event_sink = backup_sink
        usage_tracker._novel_dir = backup_dir


class TestUsageEvents:
    def test_record_broadcasts_ai_usage(self, isolated_tracker):
        sink = SinkRecorder()
        isolated_tracker.set_event_sink(sink)

        record = isolated_tracker.record(
            provider="openai", model="gpt-4o-mini",
            prompt_tokens=100, completion_tokens=50, task="chapter",
        )

        assert sink.topics() == [TOPIC_AI_USAGE]
        assert sink.events[0][1] is record          # 广播的就是落盘的那条记录
        assert sink.events[0][1]["total_tokens"] == 150

    def test_no_sink_means_silent(self, isolated_tracker):
        isolated_tracker.set_event_sink(None)
        isolated_tracker.record(provider="openai", prompt_tokens=1)   # 不应抛异常

    def test_broken_sink_does_not_break_accounting(self, isolated_tracker):
        isolated_tracker.set_event_sink(BrokenSink())
        record = isolated_tracker.record(provider="openai", prompt_tokens=7)
        assert record["prompt_tokens"] == 7

    def test_app_wires_the_tracker_sink(self):
        assert "usage_tracker.set_event_sink(self.events)" in _scan.code_only("novel_app.py")

    def test_usage_panel_subscribes_ai_usage(self):
        """用量面板是这个事件的真实消费者（否则接线只是空转）。"""
        code = _scan.code_only("app/usage_ui.py")
        assert "bus.subscribe(TOPIC_AI_USAGE" in code


# ============================================================ 最小联动闭环（ROADMAP §5 验收）


class TestEndToEndCoordination:
    def test_character_change_reaches_a_subscriber_without_tk(self, tmp_path):
        """不依赖 Tk 的最小闭环：写盘 → 广播 → 订阅方收到。

        对应 ROADMAP §5 的验收项「联动场景测试通过」。
        """
        bus = EventBus(name="t")
        seen = []
        bus.subscribe(TOPIC_CHARACTER_CHANGED, lambda topic, payload: seen.append(payload))

        memory = MemoryManager(tmp_path)
        memory.set_event_sink(bus.sink())
        memory.save_characters({"甲": {"name": "甲"}, "乙": {"name": "乙"}})

        assert len(seen) == 1
        assert seen[0]["count"] == 2
        assert seen[0]["novel_dir"] == str(tmp_path)

    def test_chapter_saved_event_drives_multiple_independent_consumers(self):
        """一个事件驱动多个消费者 —— 这是"领域事件"相对"直接调用"的全部价值。"""
        bus = EventBus(name="t")
        hits = {"timeline": 0, "usage": 0, "characters": 0}
        bus.subscribe("chapter.saved", lambda t, p: hits.__setitem__("timeline", hits["timeline"] + 1))
        bus.subscribe("chapter.saved", lambda t, p: hits.__setitem__("usage", hits["usage"] + 1))
        bus.subscribe("chapter.saved", lambda t, p: hits.__setitem__("characters", hits["characters"] + 1))

        bus.publish("chapter.saved", {"chapter": 1})

        assert hits == {"timeline": 1, "usage": 1, "characters": 1}

    def test_switching_novel_emits_closed_then_opened(self, tmp_path):
        """换书 = 关闭旧的 + 打开新的；`novel.closed` 的载荷必须带着**旧**目录。"""

        class LiteApp(NovelLifecycleMixin, ShellMixin):
            pass

        app = LiteApp()
        sink = SinkRecorder()
        app.events = sink
        first, second = tmp_path / "第一部", tmp_path / "第二部"

        app._announce_novel_opened(first)
        app._announce_novel_opened(second)

        assert sink.topics() == ["novel.opened", "novel.closed", "novel.opened"]
        assert sink.events[1][1]["novel_dir"] == str(first)
        assert sink.events[2][1]["novel_dir"] == str(second)

    def test_first_open_has_no_closed_event(self, tmp_path):
        """首次打开不应凭空冒出一个 `novel.closed`。"""

        class LiteApp(NovelLifecycleMixin, ShellMixin):
            pass

        app = LiteApp()
        sink = SinkRecorder()
        app.events = sink

        app._announce_novel_opened(tmp_path / "第一部")

        assert sink.topics() == ["novel.opened"]


# ============================================================ 接线点覆盖（源码扫描）


class TestWiringSites:
    def test_lifecycle_announces_on_all_four_entry_points(self):
        """新建 / 打开 / 续集 / 同人 四条路径必须都广播，漏一条就是面板不同步。"""
        code = _scan.read("app/lifecycle_ui.py")
        assert code.count("self._announce_novel_opened(novel_dir)") == 4
        assert code.count('self.memory.set_event_sink(getattr(self, "events", None))') == 4

    def test_switching_novel_closes_the_previous_one(self):
        """`novel.closed` 不能只是"定义了但没人发"的空头主题。"""
        code = _scan.read("app/lifecycle_ui.py")
        assert "TOPIC_NOVEL_CLOSED" in code
        assert code.count("self._publish_event(TOPIC_NOVEL_CLOSED") == 1

    def test_closed_is_emitted_before_opened(self):
        code = _scan.read("app/lifecycle_ui.py")
        body = code[code.index("def _announce_novel_opened"):]
        body = body[: body.index("def _new_novel")]
        assert body.index("TOPIC_NOVEL_CLOSED") < body.index("TOPIC_NOVEL_OPENED")

    def test_chapter_ui_broadcasts_on_both_save_paths(self):
        code = _scan.read("app/chapter_ui.py")
        assert code.count("self._announce_chapter_saved(self.current_chapter, content)") == 2
        assert "TOPIC_CHAPTER_SAVED" in code

    def test_settings_save_broadcasts_config_changed(self):
        code = _scan.read("app/lifecycle_ui.py")
        assert code.count("self._publish_event(TOPIC_CONFIG_CHANGED") == 1
        assert "TOPIC_CONFIG_CHANGED" in code

    def test_publish_event_is_the_single_outlet(self):
        """所有发布都要走 `_publish_event`（它统一处理"在哪个线程"）。"""
        code = _scan.code_only("app/shell_ui.py")
        assert "events.publish(topic, payload)" in code

        offenders = []
        for path in Path(__file__).parent.parent.glob("app/**/*.py"):
            rel = path.relative_to(Path(__file__).parent.parent).as_posix()
            if rel in ("app/shell_ui.py", "app/panels/host.py"):
                continue
            body = _scan.code_only(rel)
            if "self.event_bus.publish" in body or "self.event_bus.publish_threadsafe" in body:
                offenders.append(rel)

        assert offenders == [], f"这些文件绕过了统一出口直接发布事件：{offenders}"

    def test_novel_app_creates_the_bus_before_building_ui(self):
        """总线必须在 `_create_widgets()` 之前建好 —— 面板宿主构建时就要订阅它。"""
        code = _scan.read("novel_app.py")
        assert code.index("self.event_bus = EventBus(") < code.index("self._create_widgets()")
        assert code.index("self.events = self.event_bus.sink()") < code.index("self._create_widgets()")

    def test_novel_opened_is_broadcast_after_path_is_set(self):
        """广播时 `current_novel_dir` 必须已经是新路径，否则面板刷新会读到旧书。

        ⚠️ 用 `code_only`：说明赋值顺序的文档字符串会原样引用那一行，`read` 会多数一处。
        """
        code = _scan.code_only("app/lifecycle_ui.py")
        blocks = code.split("self.current_novel_dir = novel_dir")[1:]
        assert len(blocks) == 4, f"预期 4 处入口，实际 {len(blocks)} 处"
        for block in blocks:
            head = block[:200]
            assert "_announce_novel_opened(novel_dir)" in head, "novel.opened 广播的位置不对"
