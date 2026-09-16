"""时间线统一存储测试（v3 P4b §2.4 ①）。

本文件锁住四类东西：

1. **两套存储的合流**：`memory/timeline/`（事件源）→ `timelines/main.json`（视图），
   且人工条目不被同步抹掉；
2. **老数据兼容**：v3 新增的 5 个字段在老记录里不存在，读出来必须是默认值而不是 KeyError；
3. **四个视图的数据正确**：章节轴 / 分支 / 人物轨迹 / 跨代编年史；
4. **纯函数契约**：抽取提示词与结果解析（这部分最容易出错，且完全可单测）。
"""

import json
from pathlib import Path

import pytest

from app.memory_manager import MemoryManager
from app.timeline_store import (
    DEFAULT_WORLD_LINE,
    SOURCE_MANUAL,
    TimelineStore,
    extraction_prompt,
    parse_extraction_result,
)

# ============================================================ 造数据


def write_page(novel_dir: Path, page: int, records: list[dict]) -> Path:
    """直接写 `memory/timeline/timeline_%03d.json`（模拟 `add_event` 的落盘结果）。"""
    timeline_dir = novel_dir / "memory" / "timeline"
    timeline_dir.mkdir(parents=True, exist_ok=True)
    path = timeline_dir / f"timeline_{page:03d}.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def write_world_line(novel_dir: Path, filename: str = DEFAULT_WORLD_LINE, **payload) -> Path:
    """写一条世界线。`filename` 是文件名，`payload` 里的 `name` 是**世界线显示名**。"""
    timelines = novel_dir / "timelines"
    timelines.mkdir(parents=True, exist_ok=True)
    data = {"name": "主线", "events": [], "chapters": [], "branches": []}
    data.update(payload)
    path = timelines / filename
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class SinkRecorder:
    def __init__(self):
        self.events = []

    def publish(self, topic, payload=None):
        self.events.append((topic, payload))

    def topics(self):
        return [t for t, _ in self.events]


class BrokenSink:
    def publish(self, topic, payload=None):
        raise RuntimeError("订阅方炸了")


# ============================================================ 读事件源


class TestReadMemoryEvents:
    def test_reads_all_pages_and_sorts_by_chapter(self, tmp_path):
        # 第 1 页放第 5 章，第 2 页放第 150 章（分页规则每 100 章一页）
        write_page(
            tmp_path,
            0,
            [{"chapter": 5, "event": "乙", "type": "story", "characters": ["甲"], "timestamp": "2026-01-01T00:00:00"}],
        )
        write_page(
            tmp_path,
            1,
            [{"chapter": 150, "event": "丙", "type": "story", "characters": [], "timestamp": "2026-01-02T00:00:00"}],
        )
        write_page(
            tmp_path,
            0,
            [
                {"chapter": 3, "event": "甲", "type": "story", "characters": [], "timestamp": "2025-12-31T00:00:00"},
                {
                    "chapter": 5,
                    "event": "乙",
                    "type": "story",
                    "characters": ["甲"],
                    "timestamp": "2026-01-01T00:00:00",
                },
            ],
        )

        events = TimelineStore(tmp_path).read_memory_events()

        assert [e.chapter for e in events] == [3, 5, 150]
        assert [e.event for e in events] == ["甲", "乙", "丙"]

    def test_range_filter(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": n, "event": f"事件{n}", "timestamp": ""} for n in (1, 2, 3, 4, 5)])
        store = TimelineStore(tmp_path)
        assert [e.chapter for e in store.read_memory_events(from_chapter=2, to_chapter=4)] == [2, 3, 4]

    def test_corrupt_page_is_skipped_not_fatal(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": 1, "event": "好数据", "timestamp": ""}])
        bad = tmp_path / "memory" / "timeline" / "timeline_001.json"
        bad.write_text("{ 这不是 JSON", encoding="utf-8")

        events = TimelineStore(tmp_path).read_memory_events()

        assert [e.event for e in events] == ["好数据"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert TimelineStore(tmp_path).read_memory_events() == []
        assert TimelineStore(None).read_memory_events() == []

    def test_old_records_without_v3_fields_get_defaults(self, tmp_path):
        """v3 新增 5 个字段；老记录没有它们，必须是默认值而不是 KeyError。"""
        write_page(
            tmp_path, 0, [{"chapter": 1, "event": "旧事件", "type": "story", "characters": ["甲"], "timestamp": "t"}]
        )

        event = TimelineStore(tmp_path).read_memory_events()[0]

        assert event.location == ""
        assert event.story_time == ""
        assert event.arc == ""
        assert event.source == "auto"
        assert event.confidence == "high"
        assert event.characters == ("甲",)

    def test_characters_as_string_is_normalised(self, tmp_path):
        """历史数据里 `characters` 是字符串而非数组，也要读得出来。"""
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x", "characters": "独行侠"}])
        assert TimelineStore(tmp_path).read_memory_events()[0].characters == ("独行侠",)

    def test_non_dict_records_are_ignored(self, tmp_path):
        write_page(tmp_path, 0, ["垃圾", 42, {"chapter": 7, "event": "有效"}])
        events = TimelineStore(tmp_path).read_memory_events()
        assert [e.event for e in events] == ["有效"]


# ============================================================ 合并与同步


class TestMergeAndSync:
    def test_sync_mirrors_events_into_world_line(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": 1, "event": "开篇", "characters": ["甲"]}])
        write_world_line(tmp_path, branches=[{"chapter": 1, "decision": "去向", "chosen": "东"}], chapters=[1])

        result = TimelineStore(tmp_path).sync()

        assert result.written is True
        assert result.total == 1
        assert result.added == 1
        data = json.loads((tmp_path / "timelines" / DEFAULT_WORLD_LINE).read_text(encoding="utf-8"))
        assert data["events"][0]["event"] == "开篇"
        # branches / chapters 是创作决策，必须原样保留
        assert data["branches"][0]["chosen"] == "东"
        assert data["chapters"] == [1]

    def test_manual_events_survive_sync(self, tmp_path):
        """标记 `source=manual` 的条目是作者手写的，同步**不得**抹掉。"""
        write_page(tmp_path, 0, [{"chapter": 1, "event": "自动事件"}])
        write_world_line(
            tmp_path,
            events=[
                {"chapter": 9, "event": "作者手写事件", "source": SOURCE_MANUAL},
            ],
        )

        result = TimelineStore(tmp_path).sync()

        data = json.loads((tmp_path / "timelines" / DEFAULT_WORLD_LINE).read_text(encoding="utf-8"))
        events = {e["event"] for e in data["events"]}
        assert events == {"自动事件", "作者手写事件"}
        assert result.kept_manual == 1
        assert result.total == 2

    def test_sync_is_idempotent(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": 1, "event": "开篇"}])
        store = TimelineStore(tmp_path)

        first = store.sync()
        second = store.sync()

        assert first.written is True
        assert second.written is False
        assert "最新" in second.reason

    def test_sync_drops_stale_auto_events(self, tmp_path):
        """事件源里已删掉的事件，重建后不应残留（否则同步等于只增不减）。"""
        write_page(tmp_path, 0, [{"chapter": 1, "event": "留下"}])
        write_world_line(
            tmp_path,
            events=[
                {"chapter": 2, "event": "已被删除的旧自动事件", "source": "auto"},
            ],
        )

        result = TimelineStore(tmp_path).sync()

        assert result.dropped == 1
        data = json.loads((tmp_path / "timelines" / DEFAULT_WORLD_LINE).read_text(encoding="utf-8"))
        assert [e["event"] for e in data["events"]] == ["留下"]

    def test_sync_without_novel_reports_reason(self):
        result = TimelineStore(None).sync()
        assert result.written is False
        assert "尚未打开小说" in result.reason
        assert result.describe()

    def test_sync_publishes_timeline_changed(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x"}])
        sink = SinkRecorder()
        TimelineStore(tmp_path, events=sink).sync()
        assert sink.topics() == ["timeline.changed"]

    def test_broken_sink_does_not_break_write(self, tmp_path):
        """事件是旁路：广播炸了，数据仍必须落盘。"""
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x"}])
        result = TimelineStore(tmp_path, events=BrokenSink()).sync()
        assert result.written is True
        assert (tmp_path / "timelines" / DEFAULT_WORLD_LINE).exists()

    def test_merge_does_not_write(self, tmp_path):
        """`merge_events` 必须是纯计算，不能有副作用。"""
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x"}])
        store = TimelineStore(tmp_path)
        ordered, result = store.merge_events(store.read_world_line())
        assert ordered and result.total == 1
        assert not (tmp_path / "timelines" / DEFAULT_WORLD_LINE).exists()

    def test_世界线名不能穿越目录(self, tmp_path):
        """避免用 `../` 之类把写入引到别处。"""
        store = TimelineStore(tmp_path)
        path = store.world_line_path("../../evil.json")
        assert path is None or tmp_path in path.parents


# ============================================================ 两个写入口


class TestAddEventAndAnnotate:
    def test_add_event_writes_new_fields(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(
            7,
            "找到密道",
            characters_involved=["甲"],
            location="地宫",
            story_time="第三日",
            arc="第一卷",
            source="manual",
            confidence="low",
        )

        event = TimelineStore(tmp_path).read_memory_events()[0]

        assert (event.chapter, event.event) == (7, "找到密道")
        assert event.location == "地宫"
        assert event.story_time == "第三日"
        assert event.arc == "第一卷"
        assert event.source == "manual"
        assert event.confidence == "low"

    def test_add_event_backwards_compatible(self, tmp_path):
        """既有调用方只传前三个参数，行为必须不变。"""
        memory = MemoryManager(tmp_path)
        memory.add_event(3, "旧式调用", "story", ["乙"])

        event = TimelineStore(tmp_path).read_memory_events()[0]
        assert event.characters == ("乙",)
        assert event.source == "auto"

    def test_annotate_event_updates_fields(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(4, "会面")
        assert memory.annotate_event(4, "会面", location="茶馆", confidence="low") is True

        event = TimelineStore(tmp_path).read_memory_events()[0]
        assert event.location == "茶馆"
        assert event.confidence == "low"

    def test_annotate_returns_false_when_nothing_matched(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(4, "会面")
        assert memory.annotate_event(4, "不存在的事件", location="茶馆") is False
        assert memory.annotate_event(99, "会面", location="茶馆") is False

    def test_annotate_ignores_unknown_fields(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(4, "会面")
        assert memory.annotate_event(4, "会面", hacked="x") is False

    def test_store_annotate_delegates(self, tmp_path):
        MemoryManager(tmp_path).add_event(2, "事件")
        assert TimelineStore(tmp_path).annotate(2, "事件", story_time="黄昏") is True
        assert TimelineStore(tmp_path).read_memory_events()[0].story_time == "黄昏"

    def test_store_annotate_without_novel_is_false(self):
        assert TimelineStore(None).annotate(1, "x", location="y") is False


# ============================================================ 四个视图


class TestViews:
    def test_chapter_axis_groups_by_chapter(self, tmp_path):
        write_page(
            tmp_path,
            0,
            [
                {"chapter": 1, "event": "A", "characters": ["甲", "乙"]},
                {"chapter": 1, "event": "B", "characters": ["甲"]},
                {"chapter": 2, "event": "C", "characters": []},
            ],
        )

        rows = TimelineStore(tmp_path).chapter_axis()

        assert [r["chapter"] for r in rows] == [1, 2]
        assert rows[0]["count"] == 2
        assert rows[0]["characters"] == ["甲", "乙"]
        assert "A" in rows[0]["summary"] and "B" in rows[0]["summary"]

    def test_branch_tree_reads_all_world_lines(self, tmp_path):
        write_world_line(
            tmp_path,
            "main.json",
            name="主线",
            branches=[
                {"chapter": 5, "decision": "去留", "chosen": "留下", "alternative": "离开", "story": "分支正文"},
            ],
        )
        write_world_line(tmp_path, "alt.json", name="副线", branches=[])

        tree = TimelineStore(tmp_path).branch_tree()

        assert {w["name"] for w in tree} == {"主线", "副线"}
        main = next(w for w in tree if w["name"] == "主线")
        assert main["branches"][0]["chosen"] == "留下"

    def test_branch_dirs_reads_subprojects(self, tmp_path):
        """`branch_%03d/` 是"只写不读"的历史遗留，本面板首次把它显示出来。"""
        branch = tmp_path / "timelines" / "branch_000"
        branch.mkdir(parents=True)
        (branch / "meta.json").write_text(
            json.dumps(
                {
                    "name": "另一条路",
                    "origin_chapter": 5,
                    "status": "completed",
                    "chapter_count": 3,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        dirs = TimelineStore(tmp_path).branch_dirs()

        assert len(dirs) == 1
        assert dirs[0]["name"] == "另一条路"
        assert dirs[0]["origin_chapter"] == 5
        assert dirs[0]["meta_ok"] is True

    def test_branch_dirs_tolerates_missing_meta(self, tmp_path):
        (tmp_path / "timelines" / "branch_001").mkdir(parents=True)
        dirs = TimelineStore(tmp_path).branch_dirs()
        assert dirs and dirs[0]["meta_ok"] is False

    def test_character_tracks_from_activity_file(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "character_activity.json").write_text(
            json.dumps(
                {
                    "甲": {"appearances": [1, 3, 5], "last_seen": 5, "importance": 9},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        tracks = TimelineStore(tmp_path).character_tracks()

        assert tracks["甲"]["appearances"] == [1, 3, 5]
        assert tracks["甲"]["importance"] == 9

    def test_character_tracks_fall_back_to_events(self, tmp_path):
        """`update_character_activity` 目前没有生产调用方 → 文件常为空，须能兜底。"""
        write_page(
            tmp_path,
            0,
            [
                {"chapter": 1, "event": "A", "characters": ["甲"]},
                {"chapter": 2, "event": "B", "characters": ["甲", "乙"]},
            ],
        )

        tracks = TimelineStore(tmp_path).character_tracks()

        assert tracks["甲"]["appearances"] == [1, 2]
        assert tracks["甲"]["event_chapters"] == [1, 2]
        assert tracks["乙"]["appearances"] == [2]

    def test_character_tracks_corrupt_file_treated_as_empty(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "character_activity.json").write_text("{坏", encoding="utf-8")
        write_page(tmp_path, 0, [{"chapter": 1, "event": "A", "characters": ["甲"]}])

        assert TimelineStore(tmp_path).character_tracks()["甲"]["appearances"] == [1]

    def test_lineage_chronicle_marks_parent_events_readonly(self, tmp_path):
        parent = tmp_path / "第一部"
        child = tmp_path / "第二部"
        parent.mkdir()
        child.mkdir()
        write_page(parent, 0, [{"chapter": 1, "event": "父代事件", "characters": ["甲"]}])
        write_page(child, 0, [{"chapter": 1, "event": "子代事件", "characters": ["乙"]}])
        (child / "meta.json").write_text(
            json.dumps(
                {
                    "title": "第二部",
                    "lineage": {"generation": 2, "parent_novel": str(parent), "parent_title": "第一部"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        chronicle = TimelineStore(child).lineage_chronicle()

        by_event = {row["event"]: row for row in chronicle}
        assert by_event["父代事件"]["readonly"] is True
        assert by_event["父代事件"]["generation"] == 1
        assert by_event["子代事件"]["readonly"] is False
        assert by_event["子代事件"]["generation"] == 2

    def test_lineage_chronicle_without_lineage_is_empty(self, tmp_path):
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x"}])
        assert TimelineStore(tmp_path).lineage_chronicle() == []

    def test_lineage_chronicle_tolerates_missing_parent(self, tmp_path):
        (tmp_path / "meta.json").write_text(
            json.dumps(
                {
                    "lineage": {"generation": 2, "parent_novel": str(tmp_path / "不存在")},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        write_page(tmp_path, 0, [{"chapter": 1, "event": "x"}])
        chronicle = TimelineStore(tmp_path).lineage_chronicle()
        assert [r["event"] for r in chronicle] == ["x"]

    def test_stats(self, tmp_path):
        write_page(
            tmp_path,
            0,
            [
                {"chapter": 1, "event": "A", "characters": ["甲"], "confidence": "low"},
                {"chapter": 2, "event": "B", "characters": ["甲"], "source": "manual"},
            ],
        )
        write_world_line(tmp_path, "main.json")

        stats = TimelineStore(tmp_path).stats()

        assert stats["events"] == 2
        assert stats["chapters"] == 2
        assert stats["characters"] == 1
        assert stats["world_lines"] == 1
        assert stats["manual"] == 1
        assert stats["low_confidence"] == 1
        assert (stats["first_chapter"], stats["last_chapter"]) == (1, 2)


# ============================================================ 纯函数：抽取


class TestExtractionPrompt:
    def test_carries_chapter_number_and_roster(self):
        prompt = extraction_prompt(12, "正文内容", known_characters=["甲", "乙"])
        assert "第 12 章" in prompt or "第12章" in prompt
        assert "甲、乙" in prompt
        assert "正文内容" in prompt

    def test_warns_against_inventing_characters_when_roster_empty(self):
        prompt = extraction_prompt(1, "正文", known_characters=[])
        assert "尚未登记角色" in prompt

    def test_long_text_keeps_head_and_tail(self):
        text = "头" * 100 + "中" * 20000 + "尾" * 100
        prompt = extraction_prompt(3, text, max_chars=600)
        assert "头" in prompt and "尾" in prompt
        assert "中间省略" in prompt
        assert len(prompt) < len(text)

    def test_schema_hint_present(self):
        assert "JSON" in extraction_prompt(1, "x")


class TestParseExtractionResult:
    def test_parses_plain_json_array(self):
        raw = json.dumps([{"chapter": 99, "event": "事件", "characters": ["甲"]}], ensure_ascii=False)
        events = parse_extraction_result(raw, 7, ["甲"])
        assert events[0]["chapter"] == 7  # 章号被强制改回
        assert events[0]["characters"] == ["甲"]

    def test_strips_code_fence(self):
        raw = '```json\n[{"event": "事件"}]\n```'
        assert parse_extraction_result(raw, 1, [])[0]["event"] == "事件"

    def test_drops_unknown_characters(self):
        raw = json.dumps([{"event": "事件", "characters": ["甲", "张三（编造）"]}], ensure_ascii=False)
        events = parse_extraction_result(raw, 1, ["甲"])
        assert events[0]["characters"] == ["甲"]

    def test_keeps_characters_when_no_roster(self):
        raw = json.dumps([{"event": "事件", "characters": ["任何人"]}], ensure_ascii=False)
        assert parse_extraction_result(raw, 1, [])[0]["characters"] == ["任何人"]

    def test_confidence_normalised(self):
        raw = json.dumps(
            [
                {"event": "A", "confidence": "HIGH"},
                {"event": "B", "confidence": "whatever"},
                {"event": "C"},
            ],
            ensure_ascii=False,
        )
        events = parse_extraction_result(raw, 1, [])
        assert [e["confidence"] for e in events] == ["high", "low", "low"]

    def test_empty_events_are_skipped(self):
        raw = json.dumps([{"event": "  "}, {"event": "有效"}], ensure_ascii=False)
        assert [e["event"] for e in parse_extraction_result(raw, 1, [])] == ["有效"]

    @pytest.mark.parametrize("raw", ["", "不是 JSON", "{}", "[", "null", "文字前缀没有数组"])
    def test_invalid_returns_empty(self, raw):
        assert parse_extraction_result(raw, 1, []) == []

    def test_source_is_auto_and_defaults_filled(self):
        raw = json.dumps([{"event": "事件"}], ensure_ascii=False)
        event = parse_extraction_result(raw, 5, [])[0]
        assert event["source"] == "auto"
        assert event["location"] == ""
        assert event["story_time"] == ""
        assert event["arc"] == ""
