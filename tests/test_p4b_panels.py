"""P4b 三个新面板的测试（v3 §2.4 ①②③）。

分三层：

1. **登记与元数据** —— 三个面板必须被注册表认到，且分组落在「世界与世代」；
2. **纯数据构造** —— 视图行、筛选、提示词、继承行，全部不需要 Tk；
3. **源码级护栏** —— 传记面板**绝无删除角色入口**、三个面板**不裸写**既有数据文件、
   新面板不靠分发层分支（"新增面板只需 1 处改动"的兑现验证）。

Tk 相关（真实构建窗口）单独放在文件末尾，若无显示环境则 `skip`。
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402

from app import lineage as lin  # noqa: E402
from app.events import TOPIC_CHAPTER_SAVED, TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED  # noqa: E402
from app.panels import BiographyPanel, LineagePanel, TimelinePanel, registry  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
P4B_MODULES = ("timeline_panel", "biography_panel", "lineage_panel")


@pytest.fixture(scope="module", autouse=True)
def loaded():
    registry.load_panels()


# ============================================================ 1. 登记与元数据


class TestRegistration:
    @pytest.mark.parametrize(
        ("key", "cls", "title"),
        [
            ("timeline", TimelinePanel, "世界线与时间线"),
            ("biography", BiographyPanel, "角色传记"),
            ("lineage", LineagePanel, "世代传承"),
        ],
    )
    def test_registered_with_expected_metadata(self, key, cls, title):
        spec = registry.get(key)
        assert spec is not None, f"面板 {key} 未登记"
        assert spec.panel_cls is cls
        assert spec.title == title
        assert spec.category == "世界与世代"
        assert spec.description, "面板必须有 description（选择器 tooltip 与自检报告都用它）"
        assert spec.legacy is False, "P4b 面板是原生面板，不是迁移适配器"

    def test_category_is_a_known_group(self):
        assert "世界与世代" in registry.CATEGORY_ORDER

    def test_p4b_panels_share_one_group(self):
        specs = [s for s in registry.all_panels() if s.category == "世界与世代"]
        assert {s.key for s in specs} == {"timeline", "biography", "lineage"}

    def test_native_modules_listed_in_registry(self):
        assert set(registry.NATIVE_PANEL_MODULES) == {f"app.panels.{m}" for m in P4B_MODULES}

    def test_orders_ascending_within_group(self):
        specs = sorted((s for s in registry.all_panels() if s.category == "世界与世代"), key=lambda s: s.order)
        assert [s.key for s in specs] == ["timeline", "biography", "lineage"]

    def test_topics_of_interest_declared(self):
        """订阅总线的唯一开关：声明了才订阅（避免空转的通配处理器）。"""
        assert set(TimelinePanel.topics_of_interest) == {TOPIC_TIMELINE_CHANGED, TOPIC_CHAPTER_SAVED}
        assert set(BiographyPanel.topics_of_interest) == {TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED}
        # 世代面板只展示"当前作品"，换书由宿主重建 → 无需订阅任何主题
        assert LineagePanel.topics_of_interest == ()

    def test_empty_topics_means_no_subscription(self):
        class FakeBus:
            def __init__(self):
                self.subscribed = []

            def subscribe(self, topic, handler):
                self.subscribed.append(topic)
                return lambda: None

        bus = FakeBus()
        assert LineagePanel(None).attach_events(bus) == []
        assert bus.subscribed == []

    def test_new_panels_are_reachable_without_dispatch_changes(self):
        """分发层不得出现新面板的 key —— 否则"新增面板只需 1 处改动"就不成立了。"""
        for rel in ("app/toolkit_ui.py", "app/shell_ui.py"):
            code = _scan.code_only(rel)
            for key in ("timeline", "biography", "lineage"):
                assert f'"{key}"' not in code, f"{rel} 里硬编码了新面板 key {key!r}"


# ============================================================ 2. 时间线视图行


class TestTimelineRows:
    def test_chapter_axis_rows(self):
        from app.panels.timeline_panel import chapter_axis_rows
        from app.timeline_store import TimelineEvent

        rows = chapter_axis_rows(
            [
                {
                    "chapter": 3,
                    "count": 2,
                    "characters": ["甲"],
                    "events": [TimelineEvent(chapter=3, event="事件" * 40)],
                },
            ]
        )
        iid, values = rows[0]
        assert iid == "ch3"
        assert values[0] == "第3章"
        assert values[1] == "2"
        assert values[2] == "甲"
        assert len(values[3]) <= 60

    def test_track_rows_sorted_by_importance(self):
        from app.panels.timeline_panel import track_rows

        rows = track_rows(
            {
                "乙": {"appearances": [1], "importance": 3},
                "甲": {"appearances": [1, 2], "importance": 9},
            }
        )
        assert [iid for iid, _ in rows] == ["tr甲", "tr乙"]

    def test_track_rows_truncates_long_history(self):
        from app.panels.timeline_panel import track_rows

        rows = track_rows({"甲": {"appearances": list(range(1, 31)), "importance": 5}})
        assert rows[0][1][3].endswith("…")

    def test_branch_rows_two_levels(self):
        from app.panels.timeline_panel import branch_rows

        rows = branch_rows(
            [
                {
                    "name": "主线",
                    "file": "main.json",
                    "branches": [{"chapter": 5, "decision": "去留", "chosen": "留下", "alternative": "离开"}],
                }
            ]
        )
        assert [iid for iid, _ in rows] == ["wlmain.json", "wlmain.json#5"]
        assert rows[0][1][1] == "1 处抉择"

    def test_chronicle_rows_marks_readonly(self):
        from app.panels.timeline_panel import chronicle_rows

        rows = chronicle_rows(
            [
                {"generation": 1, "chapter": 1, "event": "父", "readonly": True},
                {"generation": 2, "chapter": 2, "event": "子", "readonly": False},
            ]
        )
        assert rows[0][1][4] == "前代史（只读）"
        assert rows[1][1][4] == "本代（可编辑）"

    def test_chronicle_iids_are_unique_per_event(self):
        from app.panels.timeline_panel import chronicle_rows

        rows = chronicle_rows(
            [
                {"generation": 1, "chapter": 5, "event": "A"},
                {"generation": 1, "chapter": 5, "event": "B"},
            ]
        )
        assert len({iid for iid, _ in rows}) == 2

    def test_stats_text_omits_zero_extras(self):
        from app.panels.timeline_panel import stats_text

        text = stats_text(
            {
                "events": 3,
                "chapters": 2,
                "characters": 1,
                "world_lines": 1,
                "branch_dirs": 0,
                "manual": 0,
                "low_confidence": 0,
            }
        )
        assert "手工" not in text and "低置信" not in text
        assert "事件 3 条" in text

    def test_stats_text_includes_extras_when_present(self):
        from app.panels.timeline_panel import stats_text

        text = stats_text({"events": 3, "manual": 2, "low_confidence": 1, "first_chapter": 1, "last_chapter": 9})
        assert "手工 2 条" in text and "低置信 1 条" in text and "1–9" in text


# ============================================================ 2b. 传记纯逻辑


class TestBiographyLogic:
    def test_filter_by_keyword_matches_name_and_background(self):
        from app.panels.biography_panel import filter_characters

        chars = {
            "甲": {"personality": "沉默"},
            "乙": {"background": "来自沙漠的剑客"},
            "丙": {},
        }
        assert set(filter_characters(chars, keyword="甲")) == {"甲"}
        assert set(filter_characters(chars, keyword="沙漠")) == {"乙"}
        assert set(filter_characters(chars, keyword="")) == {"甲", "乙", "丙"}

    def test_filter_by_category_and_faction(self):
        from app.panels.biography_panel import filter_characters

        chars = {
            "甲": {"category": "主角", "faction": "正道"},
            "乙": {"category": "配角", "faction": "正道"},
        }
        assert set(filter_characters(chars, category="主角")) == {"甲"}
        assert set(filter_characters(chars, faction="正道")) == {"甲", "乙"}
        assert set(filter_characters(chars, category="主角", faction="魔道")) == set()

    def test_filter_only_with_biography(self):
        from app.panels.biography_panel import filter_characters

        chars = {"甲": {"biography": "有"}, "乙": {"biography_file": "p"}, "丙": {}}
        assert set(filter_characters(chars, only_with_biography=True)) == {"甲", "乙"}

    def test_filter_tolerates_non_dict_entries(self):
        from app.panels.biography_panel import filter_characters

        assert set(filter_characters({"甲": "垃圾"})) == {"甲"}

    def test_character_rows_sorted_and_flags_biography(self):
        from app.panels.biography_panel import character_rows

        rows = character_rows(
            {
                "甲": {"importance": 9, "biography": "x"},
                "乙": {"importance": 2},
            }
        )
        assert [iid for iid, _ in rows] == ["ch甲", "ch乙"]
        assert rows[0][1][4] == "✓"
        assert rows[1][1][4] == "—"

    def test_material_summary_empty_state(self):
        from app.panels.biography_panel import material_summary

        assert "无" in material_summary([], [], [], [])

    def test_material_summary_counts(self):
        from app.panels.biography_panel import material_summary

        text = material_summary([1, 2, 3], ["e1", "e2"], [{"content": "a"}], [{"title": "t"}])
        assert "出场章节 3 章" in text
        assert "相关事件 2 条" in text
        assert "记忆检索命中 1 段" in text
        assert "手工故事线 1 段" in text

    def test_split_sections_with_headings(self):
        from app.panels.biography_panel import split_sections

        sections = split_sections("## 出身\n内容A\n## 转折\n内容B")
        assert [s["title"] for s in sections] == ["出身", "转折"]
        assert sections[0]["content"] == "内容A"
        assert sections[0]["id"] == "sec1"

    def test_split_sections_without_headings(self):
        from app.panels.biography_panel import split_sections

        sections = split_sections("只有一段正文")
        assert len(sections) == 1
        assert sections[0]["title"] == "正文"

    def test_split_sections_empty(self):
        from app.panels.biography_panel import split_sections

        assert split_sections("") == []
        assert split_sections("   ") == []

    def test_story_arcs_from_sections(self):
        from app.panels.biography_panel import story_arcs_from_sections

        arcs = story_arcs_from_sections([{"title": "t", "content": "c"}, {"title": "空", "content": " "}])
        assert arcs == [{"title": "t", "content": "c"}]

    def test_structured_biography_shape(self):
        from app.panels.biography_panel import structured_biography

        data = structured_biography(
            "甲",
            [{"id": "sec1", "title": "t", "content": "c"}],
            sources={"chapters": [1, 2]},
            provider="deepseek",
            model="m",
            tokens=100,
            generated_at="2026-01-01T00:00:00",
        )
        assert data["name"] == "甲"
        assert data["version"] == 1
        assert data["sections"][0]["id"] == "sec1"
        assert data["sources"]["chapters"] == [1, 2]
        assert data["provider"] == "deepseek"

    def test_prompt_includes_materials(self):
        from app.panels.biography_panel import build_biography_prompt
        from app.timeline_store import TimelineEvent

        prompt = build_biography_prompt(
            "甲",
            {"gender": "男", "age": 20, "weapon": {"name": "断剑", "quality": "凡品"}},
            word_count=1200,
            anchors=[{"content": "他曾在此地立誓"}],
            events=[TimelineEvent(chapter=7, event="得到断剑")],
            story_arcs=[{"title": "旧弧线", "content": "内容"}],
        )
        assert "甲" in prompt
        assert "1200" in prompt
        assert "断剑" in prompt
        assert "第7章" in prompt
        assert "他曾在此地立誓" in prompt
        assert "旧弧线" in prompt
        assert "不要编造" in prompt

    def test_prompt_without_materials_still_valid(self):
        from app.panels.biography_panel import build_biography_prompt

        prompt = build_biography_prompt("甲", {})
        assert "甲" in prompt
        assert "【角色档案】" in prompt

    def test_read_story_arcs_defaults(self, tmp_path):
        from app.panels.biography_panel import read_story_arcs

        assert read_story_arcs(tmp_path, "甲")["story_arcs"] == []
        assert read_story_arcs(None, "甲")["name"] == "甲"

    def test_read_story_arcs_corrupt_file(self, tmp_path):
        from app.panels.biography_panel import read_story_arcs

        stories = tmp_path / "character_stories"
        stories.mkdir()
        (stories / "甲.json").write_text("{坏", encoding="utf-8")
        assert read_story_arcs(tmp_path, "甲")["story_arcs"] == []

    def test_load_biography_json(self, tmp_path):
        from app.panels.biography_panel import load_biography_json

        assert load_biography_json(tmp_path, "甲") is None
        bio = tmp_path / "biographies"
        bio.mkdir()
        (bio / "甲.json").write_text(json.dumps({"name": "甲", "sections": []}, ensure_ascii=False), encoding="utf-8")
        assert load_biography_json(tmp_path, "甲")["name"] == "甲"

    def test_biography_filename_is_sanitised(self, tmp_path):
        """角色名可能含路径分隔符等非法字符，落盘必须净化。"""
        from app.panels.biography_panel import load_biography_json

        assert load_biography_json(tmp_path, "a/b:c") is None  # 不抛错即可


# ============================================================ 2c. 世代纯逻辑


class TestLineagePanelLogic:
    def test_novel_candidates_lists_novels_with_meta(self, tmp_path):
        from app.panels.lineage_panel import novel_candidates

        (tmp_path / "有meta").mkdir()
        (tmp_path / "有meta" / "meta.json").write_text(
            json.dumps({"title": "甲"}, ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "无meta").mkdir()

        candidates = novel_candidates(tmp_path)

        assert [c["title"] for c in candidates] == ["甲"]

    def test_novel_candidates_excludes_self(self, tmp_path):
        from app.panels.lineage_panel import novel_candidates

        me = tmp_path / "我"
        me.mkdir()
        (me / "meta.json").write_text("{}", encoding="utf-8")

        assert novel_candidates(tmp_path, exclude_dir=me) == []

    def test_novel_candidates_skips_corrupt_meta(self, tmp_path):
        from app.panels.lineage_panel import novel_candidates

        bad = tmp_path / "坏"
        bad.mkdir()
        (bad / "meta.json").write_text("{坏", encoding="utf-8")

        assert novel_candidates(tmp_path) == []

    def test_novel_candidates_excludes_descendants(self, tmp_path):
        """把**子代**设成父代同样会造出环，必须排除。

        方向容易写反：`is_within(root, target)` 的含义是「target 在 root 之内」。
        """
        from app.panels.lineage_panel import novel_candidates

        me = tmp_path / "我"
        (me / "第二部").mkdir(parents=True)
        (me / "meta.json").write_text("{}", encoding="utf-8")
        (me / "第二部" / "meta.json").write_text("{}", encoding="utf-8")
        sibling = tmp_path / "兄弟"
        sibling.mkdir()
        (sibling / "meta.json").write_text("{}", encoding="utf-8")

        # 遍历的是 novels_dir 的直接子项，所以要把"我"当成根才能看到后代
        names = {c["dir"] for c in novel_candidates(me, exclude_dir=me)}
        assert names == set(), "自己与自己的后代都不应出现在父代候选里"

        names2 = {c["dir"] for c in novel_candidates(tmp_path, exclude_dir=me)}
        assert str(sibling) in names2

    def test_novel_candidates_missing_root(self, tmp_path):
        from app.panels.lineage_panel import novel_candidates

        assert novel_candidates(None) == []
        assert novel_candidates(tmp_path / "无") == []

    def test_lineage_rows(self):
        from app.panels.lineage_panel import lineage_rows

        rows = lineage_rows(
            [
                {
                    "generation": 2,
                    "title": "二",
                    "novel_dir": "p2",
                    "is_current": True,
                    "readonly": False,
                    "missing": False,
                },
                {
                    "generation": 1,
                    "title": "一",
                    "novel_dir": "p1",
                    "is_current": False,
                    "readonly": True,
                    "missing": False,
                },
            ]
        )
        assert [iid for iid, _ in rows] == ["g0", "g1"]
        assert rows[0][1][2] == "当前作品"
        assert rows[1][1][2] == "前代史（只读）"

    def test_lineage_rows_marks_missing_dir(self):
        from app.panels.lineage_panel import lineage_rows

        rows = lineage_rows(
            [{"generation": 1, "title": "一", "novel_dir": "p", "is_current": False, "readonly": True, "missing": True}]
        )
        assert rows[0][1][4] == "目录丢失"

    def test_inheritance_rows_without_plan(self):
        from app.panels.lineage_panel import inheritance_rows

        rows = inheritance_rows({d: True for d in lin.INHERIT_DIMENSIONS}, None)
        assert len(rows) == len(lin.INHERIT_DIMENSIONS)
        assert rows[0][1][0] == "☑"
        assert "尚未选择父代" in rows[0][1][2]

    def test_inheritance_rows_marks_skipped(self, tmp_path):
        from app.panels.lineage_panel import inheritance_rows

        parent = tmp_path / "p"
        parent.mkdir()
        checked = {d: (d != "outline") for d in lin.INHERIT_DIMENSIONS}
        rows = inheritance_rows(checked, lin.plan_inheritance(parent, checked))
        outline_row = next(r for r in rows if r[0] == "dimoutline")
        assert outline_row[1][0] == "☐"
        assert "取消继承" in outline_row[1][2]

    def test_summary_without_lineage(self):
        from app.panels.lineage_panel import lineage_summary

        assert "第 1 代" in lineage_summary(None)

    def test_summary_with_lineage(self):
        from app.panels.lineage_panel import lineage_summary

        record = lin.LineageRecord(generation=2, parent_novel="p", parent_title="第一部", era_gap_years=20)
        text = lineage_summary(record)
        assert "第 2 代" in text
        assert "第一部" in text
        assert "时间跳跃 20 年" in text
        assert "readonly_parent" in text


class TestBiographyPersist:
    """`_persist` 必须**如实**分别报告"文件落盘"与"档案回写"两件事。"""

    def _panel(self, novel_dir, memory=None):
        app = FakeApp(novel_dir)
        app.memory = memory
        return BiographyPanel(app)

    def test_writes_both_files(self, tmp_path):
        novel = _novel(tmp_path)
        panel = self._panel(novel)

        files_ok, profile_ok = panel._persist("甲", "## 出身\n内容", {"chapters": [1]})

        assert files_ok is True
        assert (novel / "biographies" / "甲_传记.txt").exists()
        assert (novel / "biographies" / "甲.json").exists()
        # 没有 memory → 档案未回写，必须如实返回 False
        assert profile_ok is False

    def test_reports_profile_writeback_when_memory_available(self, tmp_path):
        novel = _novel(tmp_path)
        (novel / "memory" / "characters.json").write_text(
            json.dumps({"甲": {"name": "甲"}}, ensure_ascii=False), encoding="utf-8"
        )

        class FakeMemory:
            def __init__(self):
                self.calls = 0

            def mutate_characters(self, mutator):
                self.calls += 1
                return mutator({"甲": {"name": "甲"}})

        memory = FakeMemory()
        panel = self._panel(novel, memory)

        files_ok, profile_ok = panel._persist("甲", "## 出身\n内容", {"chapters": []})

        assert (files_ok, profile_ok) == (True, True)
        assert memory.calls == 1, "角色档案必须走 mutate_characters（锁 + 三道闸门）"

    def test_reports_failure_without_novel(self, tmp_path):
        panel = self._panel(None)
        assert panel._persist("甲", "内容", {}) == (False, False)


# ============================================================ 3. 源码级护栏


class TestPanelGuards:
    def _code(self, module: str) -> str:
        return _scan.code_only(f"app/panels/{module}.py")

    @pytest.mark.parametrize("module", P4B_MODULES)
    def test_no_delete_character_entry(self, module):
        """🚨 项目硬约束：任何面板都不得提供删除角色的入口。"""
        code = self._code(module)
        for forbidden in ("_delete_character", "delete_character", "删除角色", "remove_character"):
            assert forbidden not in code, f"{module} 出现了删除角色相关代码：{forbidden}"

    def test_biography_panel_writes_characters_only_via_mutate(self):
        code = self._code("biography_panel")
        assert "mutate_characters" in code
        assert "save_characters" not in code, "角色落盘必须走 mutate_characters（锁 + 三道闸门）"

    @pytest.mark.parametrize("module", P4B_MODULES)
    def test_panels_do_not_write_characters_json_directly(self, module):
        """裸写 characters.json 会绕过闸门，可能清空 286 个角色。"""
        code = self._code(module)
        for line in code.splitlines():
            if "characters.json" in line:
                assert not re.search(r"atomic_write|open\s*\(|write_text|\.write\(", line), (
                    f"{module} 直接写了 characters.json：{line.strip()}"
                )

    def test_timeline_panel_writes_world_line_only_through_store(self):
        """世界线文件由 TimelineStore 统一原子写；面板不得自己拼 timelines 路径。"""
        code = self._code("timeline_panel")
        assert "TimelineStore" in code
        assert not re.search(r"open\([^)]*['\"]w['\"]", code)
        # 只拦"当作路径用"的写法；`description` 里提到文件名是正常的说明文字
        assert not re.search(r"[/\\]\s*[\"']timelines[\"']", code), "面板不应自己拼 timelines 路径"

    def test_lineage_panel_uses_guarded_inheritance(self):
        """继承必须走 lineage 模块（每次写入都过 guard_child_path）。"""
        code = self._code("lineage_panel")
        assert "inherit_into_child" in code
        assert "make_character_transform" in code

    def test_lineage_module_guards_every_copy(self):
        """`lineage.py` 里所有落盘/复制都必须经过护栏函数。"""
        code = _scan.code_only("app/lineage.py")
        assert "guard_child_path(child_dir, target)" in code
        assert "dst = guard_child_path(child_dir, Path(child_dir) / rel)" in code

    def test_timeline_store_does_not_write_memory_timeline(self):
        """事件源是 `MemoryManager` 的地盘，store 只读它。"""
        code = _scan.code_only("app/timeline_store.py")
        assert "atomic_write_json(path, payload" in code  # 只写世界线
        for line in code.splitlines():
            if "timeline_dir" in line and ("atomic_write" in line or "open(" in line):
                raise AssertionError(f"timeline_store 写入了事件源目录：{line.strip()}")


# ============================================================ 4. 真实 Tk 构建（可跳过）


@pytest.fixture(scope="module")
def tk_root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as exc:  # noqa: BLE001 - 无显示环境则跳过
        pytest.skip(f"无可用 Tk 环境：{exc}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


class FakeApp:
    """最小宿主：只提供三个面板真正会读的东西。"""

    def __init__(self, novel_dir):
        self.current_novel_dir = novel_dir
        self.current_chapter = 1
        self.logs = []
        self.notebook = None
        self.panel_host = None
        self.memory = None
        self.ai_client = None

    def _log(self, message):
        self.logs.append(message)


def _novel(tmp_path: Path) -> Path:
    novel = tmp_path / "试作"
    (novel / "memory" / "timeline").mkdir(parents=True)
    (novel / "meta.json").write_text(json.dumps({"title": "试作"}, ensure_ascii=False), encoding="utf-8")
    (novel / "outline.json").write_text(json.dumps([{"title": "第1章"}], ensure_ascii=False), encoding="utf-8")
    (novel / "chapters").mkdir()
    (novel / "chapters" / "chapter_0001.txt").write_text("第一章正文。", encoding="utf-8")
    (novel / "memory" / "timeline" / "timeline_000.json").write_text(
        json.dumps([{"chapter": 1, "event": "开篇", "characters": ["甲"]}], ensure_ascii=False),
        encoding="utf-8",
    )
    return novel


class TestRealTkBuild:
    @pytest.mark.parametrize("cls", [TimelinePanel, BiographyPanel, LineagePanel])
    def test_builds_without_exception(self, tk_root, tmp_path, cls):
        import tkinter as tk

        app = FakeApp(_novel(tmp_path))
        frame = tk.Frame(tk_root)
        panel = cls(app)
        panel.build(frame)
        assert panel.is_built is True
        assert frame.winfo_children(), "面板必须真的画出内容"
        panel.detach()

    def test_build_without_novel_is_graceful(self, tk_root, tmp_path):
        """未打开小说时应显示提示，而不是抛异常。"""
        import tkinter as tk

        app = FakeApp(None)
        for cls in (TimelinePanel, BiographyPanel, LineagePanel):
            frame = tk.Frame(tk_root)
            panel = cls(app)
            panel.build(frame)
            panel.detach()

    def test_timeline_panel_reload_after_event(self, tk_root, tmp_path):
        import tkinter as tk

        app = FakeApp(_novel(tmp_path))
        frame = tk.Frame(tk_root)
        panel = TimelinePanel(app)
        panel.build(frame)

        panel.on_event(TOPIC_TIMELINE_CHANGED, {"chapter": 1})
        panel.on_event(TOPIC_CHAPTER_SAVED, {"chapter": 1})
        panel.on_event("无关主题", {})

        assert panel.is_built
        panel.detach()

    def test_biography_panel_focus_character(self, tk_root, tmp_path):
        import tkinter as tk

        novel = _novel(tmp_path)
        (novel / "memory" / "characters.json").write_text(
            json.dumps({"甲": {"name": "甲", "importance": 9}}, ensure_ascii=False), encoding="utf-8"
        )
        app = FakeApp(novel)
        panel = BiographyPanel(app)
        panel.build(tk.Frame(tk_root))

        panel.focus_character("甲")

        assert panel._current_name == "甲"
        panel.detach()

    def test_host_can_select_all_three(self, tk_root, tmp_path):
        """端到端：宿主 → 注册表 → 三个面板逐个构建。"""
        import tkinter as tk

        from app.panels.host import PanelHost

        app = FakeApp(_novel(tmp_path))
        app.events = None
        container = tk.Frame(tk_root)
        selector = tk.Frame(tk_root)
        host = PanelHost(app, container, tk.StringVar(), selector)
        host.build_selector(selector)

        for key in ("timeline", "biography", "lineage"):
            assert host.select(key) is True, f"宿主无法选中面板 {key}"
            assert host.panel(key).is_built is True

        host.detach_all()
