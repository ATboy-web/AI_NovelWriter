"""S4 的两项收敛：

**F3 —— 角色轨迹终于被采集**：`update_character_activity` 此前**没有任何生产调用方**
（只有测试调用），于是真实小说里 `memory/character_activity.json` 一直是空的，
时间线面板的"人物轨迹"只能靠事件源兜底反推。现在 `add_event` 会把它登记下来 ——
`add_event` 是**唯一**携带 `characters` 的写入口，所以这是单点接线。

**F4 —— 传记逻辑收敛为一份**：纯逻辑搬到 `app/biography.py`，面板再导出（既有导入路径不变），
`character_ui` 的角色页入口也改用它 —— 此前那个入口的提示词只用 `char_info + outline[:5]`，
完全不用已写正文，与面板版本质量明显不同。
"""

import json
import sys
from pathlib import Path

import pytest

from app import biography as bio
from app import character_ui
from app.live_data import summarize_novel
from app.memory_manager import MemoryManager
from app.panels import biography_panel as bp
from app.timeline_store import TimelineStore

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


def _activity_file(novel_dir: Path) -> Path:
    return novel_dir / "memory" / "character_activity.json"


# ============================================================ F3：轨迹采集


class TestCharacterActivityCollection:
    def test_add_event_records_activity(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(3, "会面", characters_involved=["甲", "乙"])

        data = json.loads(_activity_file(tmp_path).read_text(encoding="utf-8"))

        assert set(data) == {"甲", "乙"}
        assert data["甲"]["appearances"] == [3]
        assert data["甲"]["last_seen"] == 3

    def test_add_event_without_characters_writes_nothing(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(1, "纯景物描写")

        assert not _activity_file(tmp_path).exists()

    def test_activity_dedupes_same_chapter(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(5, "A", characters_involved=["甲"])
        memory.add_event(5, "B", characters_involved=["甲"])

        assert json.loads(_activity_file(tmp_path).read_text(encoding="utf-8"))["甲"]["appearances"] == [5]

    def test_activity_keeps_only_recent_100(self, tmp_path):
        """与 `update_character_activity` 同一规则：只保留最近 100 次出场。"""
        memory = MemoryManager(tmp_path)
        for chapter in range(1, 121):
            memory.add_event(chapter, f"事件{chapter}", characters_involved=["甲"])

        appearances = json.loads(_activity_file(tmp_path).read_text(encoding="utf-8"))["甲"]["appearances"]
        assert len(appearances) == 100
        assert appearances[-1] == 120
        assert 1 not in appearances

    def test_blank_names_are_skipped(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(1, "事件", characters_involved=["", "甲", None])

        assert set(json.loads(_activity_file(tmp_path).read_text(encoding="utf-8"))) == {"甲"}

    def test_activity_failure_does_not_break_event_write(self, tmp_path):
        """轨迹是锦上添花：它写失败**绝不能**影响事件本身的落盘。"""
        memory = MemoryManager(tmp_path)

        def boom():
            raise OSError("磁盘满了（模拟）")

        memory._save_character_activity = boom  # noqa: SLF001 - 故意打桩

        memory.add_event(2, "重要事件", characters_involved=["甲"])

        events = TimelineStore(tmp_path).read_memory_events()
        assert [e.event for e in events] == ["重要事件"]

    def test_public_update_still_works(self, tmp_path):
        """公开入口保持原行为（面板/脚本仍可直接调用它）。"""
        memory = MemoryManager(tmp_path)
        memory.update_character_activity("甲", 7)

        assert json.loads(_activity_file(tmp_path).read_text(encoding="utf-8"))["甲"]["last_seen"] == 7

    def test_store_tracks_reads_what_add_event_wrote(self, tmp_path):
        """端到端：`add_event` 写下的轨迹，能被时间线面板的数据源直接读到。"""
        memory = MemoryManager(tmp_path)
        memory.add_event(1, "A", characters_involved=["甲"])
        memory.add_event(4, "B", characters_involved=["甲", "乙"])

        tracks = TimelineStore(tmp_path).character_tracks()

        assert tracks["甲"]["appearances"] == [1, 4]
        assert tracks["乙"]["appearances"] == [4]
        assert tracks["甲"]["last_seen"] == 4

    def test_add_event_still_writes_page_and_keeps_counts(self, tmp_path):
        """接线不得影响原有落盘语义与基线计数维度。"""
        memory = MemoryManager(tmp_path)
        memory.add_event(1, "A", characters_involved=["甲"])
        # `summarize_novel` 只接受含 characters.json 的有效作品目录
        (tmp_path / "memory" / "characters.json").write_text("{}", encoding="utf-8")

        summary = summarize_novel(tmp_path)

        assert summary.chapter_count == 0  # 没有 chapters/*.txt
        assert summary.character_file_count == 0  # 也没有 characters/*.json

    def test_summarize_rejects_dir_without_characters_file(self, tmp_path):
        """边界：给出**可执行**的报错，而不是 pathlib 的原始 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError, match="不是有效的作品目录"):
            summarize_novel(tmp_path)


# ============================================================ F4：单一来源


class TestBiographySingleSource:
    def test_panel_reexports_the_same_objects(self):
        """再导出必须是**同一个对象**（`is` 比较）—— 而不是同名副本。"""
        for name in (
            "BIOGRAPHIES_DIR",
            "MAX_BIO_TOKENS",
            "PROFILE_BIOGRAPHY_LIMIT",
            "STORIES_DIR",
            "build_biography_prompt",
            "character_rows",
            "filter_characters",
            "load_biography_json",
            "material_summary",
            "read_story_arcs",
            "split_sections",
            "story_arcs_from_sections",
            "structured_biography",
        ):
            assert getattr(bp, name) is getattr(bio, name), f"{name} 不是同一对象（出现了副本）"

    def test_shared_module_has_no_tk_dependency(self):
        """纯逻辑模块不得依赖 Tk —— 否则无法在无显示环境下复用。"""
        code = _scan.code_only("app/biography.py")
        assert "tkinter" not in code
        assert "import tkinter" not in code

    def test_character_ui_uses_shared_builder(self):
        code = _scan.code_only("app/character_ui.py")
        assert "build_biography_prompt" in code, "角色页入口必须走共享构造器"
        assert "_biography_materials" in code

    def test_old_thin_prompt_is_gone(self):
        """旧提示词只用 `outline[:5]`、不喂正文 —— 必须已消失。"""
        code = _scan.code_only("app/character_ui.py")
        assert "outline[:5]" not in code
        assert "大纲参考" not in code

    def test_character_ui_pulls_the_same_four_material_sources(self):
        """两条入口的素材来源必须一致：RAG / 时间线事件 / 出场章 / 手工故事线。"""
        code = _scan.code_only("app/character_ui.py")
        for marker in ("retrieve_relevant", "read_memory_events", "character_tracks", "read_story_arcs"):
            assert marker in code, f"角色页入口缺少素材来源：{marker}"

    def test_character_ui_writes_structured_json_too(self):
        """两条入口产出必须一致：txt + 结构化 json（此前角色页只写 txt）。"""
        code = _scan.code_only("app/character_ui.py")
        assert "structured_biography" in code
        assert "atomic_write_json" in code


class LiteCharacterApp(character_ui.CharacterUIMixin):
    """最小宿主：只提供 `_biography_materials` 会读的东西。"""

    def __init__(self, novel_dir, memory=None):
        self.current_novel_dir = novel_dir
        self.memory = memory
        self.logs = []

    def _log(self, message):
        self.logs.append(message)


class TestBiographyMaterials:
    def test_returns_all_keys(self, tmp_path):
        app = LiteCharacterApp(tmp_path)
        materials = app._biography_materials("甲")

        assert set(materials) == {"char_info", "anchors", "events", "arcs", "chapters"}

    def test_collects_from_timeline_and_stories(self, tmp_path):
        memory = MemoryManager(tmp_path)
        memory.add_event(2, "得到断剑", characters_involved=["甲"])
        stories = tmp_path / "character_stories"
        stories.mkdir()
        (stories / "甲.json").write_text(
            json.dumps({"name": "甲", "story_arcs": [{"title": "旧弧线", "content": "内容"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        app = LiteCharacterApp(tmp_path, memory)

        materials = app._biography_materials("甲")

        assert [e.event for e in materials["events"]] == ["得到断剑"]
        assert materials["chapters"] == [2]
        assert materials["arcs"][0]["title"] == "旧弧线"

    def test_tolerates_missing_novel_dir(self):
        app = LiteCharacterApp(None)
        materials = app._biography_materials("甲")

        assert materials["events"] == []
        assert materials["char_info"] == {}

    def test_tolerates_broken_memory(self, tmp_path):
        class BrokenMemory:
            def get_characters(self):
                raise RuntimeError("坏")

            def retrieve_relevant(self, *_a, **_k):
                raise RuntimeError("坏")

        app = LiteCharacterApp(tmp_path, BrokenMemory())

        materials = app._biography_materials("甲")

        assert materials["char_info"] == {}
        assert materials["anchors"] == []

    def test_prompt_built_from_materials_is_enriched(self, tmp_path):
        """共享构造器 + 材料 ⇒ 提示词里必须出现正文锚点与事件（这正是"输入太薄"的修法）。"""
        memory = MemoryManager(tmp_path)
        memory.add_event(2, "得到断剑", characters_involved=["甲"])
        app = LiteCharacterApp(tmp_path, memory)
        materials = app._biography_materials("甲")

        prompt = bio.build_biography_prompt(
            "甲", materials["char_info"], 1200, materials["anchors"], materials["events"], materials["arcs"]
        )

        assert "第2章" in prompt
        assert "得到断剑" in prompt
        assert "不要编造" in prompt


@pytest.mark.parametrize("name", ["BIOGRAPHIES_DIR", "STORIES_DIR"])
def test_dir_constants_are_plain_names(name):
    """目录常量只是目录名，不应含路径分隔符（调用方负责拼到小说目录下）。"""
    assert "/" not in getattr(bio, name)
    assert "\\" not in getattr(bio, name)
