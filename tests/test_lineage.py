"""世代传承测试（v3 P4b §2.4 ③）。

本文件最重要的不是"能复制文件"，而是**护栏**：

> 🚨 子代读父代的数据、又写自己的目录。一次路径拼接错误就会改掉父代的书
> （父代往往已经写完甚至已发布）。

因此 `TestReadonlyParentGuard` 用**父代目录的完整快照哈希**来断言
「继承过程中父代一个字节都没变」，而不是检查某个函数返回值。
"""

import hashlib
import json
from pathlib import Path

import pytest

from app import lineage as lin

# ============================================================ 工具


def snapshot(root: Path) -> dict[str, str]:
    """目录全量快照：相对路径 → 内容哈希（用于"父代零改动"断言）。"""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def make_novel(root: Path, title: str, **meta_extra) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "meta.json").write_text(json.dumps({"title": title, **meta_extra}, ensure_ascii=False), encoding="utf-8")
    return root


def make_parent(tmp_path: Path) -> Path:
    """造一个内容齐全的"第 1 代"作品。"""
    parent = make_novel(tmp_path / "第一部", "第一部", chapter_count=120)
    (parent / "outline.json").write_text(
        json.dumps([{"title": "第1章", "summary": "开端"}], ensure_ascii=False), encoding="utf-8"
    )
    memory = parent / "memory"
    (memory / "timeline").mkdir(parents=True)
    (memory / "characters.json").write_text(
        json.dumps({"甲": {"name": "甲", "age": 20}, "乙": {"name": "乙", "age": "不明"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (memory / "settings.json").write_text(json.dumps({"world": "浮空岛"}), encoding="utf-8")
    (memory / "global_summary.txt").write_text(
        "故事发生在浮空岛。\n- 主角身世仍是未解之谜\n- 断剑的来历悬而未决\n- 天气很好\n",
        encoding="utf-8",
    )
    (memory / "timeline" / "timeline_000.json").write_text(
        json.dumps([{"chapter": 1, "event": "开篇", "characters": ["甲"]}], ensure_ascii=False),
        encoding="utf-8",
    )
    characters = parent / "characters"
    characters.mkdir()
    (characters / "甲.json").write_text(json.dumps({"name": "甲", "level": 10}), encoding="utf-8")
    return parent


# ============================================================ 记录解析


class TestLineageRecord:
    def test_from_meta_returns_none_without_key(self):
        """没有 lineage 键 = 第 1 代，是**正常历史状态**，不是错误。"""
        assert lin.LineageRecord.from_meta({"title": "x"}) is None
        assert lin.LineageRecord.from_meta(None) is None
        assert lin.LineageRecord.from_meta("不是字典") is None

    def test_from_meta_reads_all_fields(self):
        record = lin.LineageRecord.from_meta(
            {
                "lineage": {
                    "generation": 3,
                    "parent_novel": "P",
                    "parent_title": "前作",
                    "era_gap_years": 20,
                    "child_scope": "readonly_parent",
                    "inherited": {"outline": False, "timeline": True},
                }
            }
        )
        assert record.generation == 3
        assert record.era_gap_years == 20
        assert record.inherited["outline"] is False
        assert record.inherited["timeline"] is True
        # 未提及的维度回落默认（全继承）
        assert record.inherited["characters"] is True

    @pytest.mark.parametrize("bad", ["abc", None, [], {}])
    def test_from_meta_coerces_bad_types(self, bad):
        record = lin.LineageRecord.from_meta({"lineage": {"generation": bad, "era_gap_years": bad}})
        assert record.generation == 1
        assert record.era_gap_years == 0

    def test_is_root(self):
        assert lin.LineageRecord().is_root is True
        assert lin.LineageRecord(generation=2, parent_novel="P").is_root is False

    def test_scope_defaults_to_readonly_parent(self):
        assert lin.LineageRecord.from_meta({"lineage": {}}).child_scope == lin.SCOPE_READONLY_PARENT

    def test_read_lineage_tolerates_corrupt_meta(self, tmp_path):
        novel = tmp_path / "坏书"
        novel.mkdir()
        (novel / "meta.json").write_text("{坏", encoding="utf-8")
        assert lin.read_lineage(novel) is None

    def test_read_lineage_without_dir(self):
        assert lin.read_lineage(None) is None

    def test_build_lineage_record_auto_generation(self, tmp_path):
        parent = make_novel(tmp_path / "第一部", "第一部")
        child = make_novel(tmp_path / "第二部", "第二部", lineage={"generation": 2, "parent_novel": str(parent)})
        record = lin.build_lineage_record(child, era_gap_years=10)
        assert record.generation == 3  # 父代是第 2 代 → 子代第 3 代
        assert record.era_gap_years == 10
        assert record.parent_novel == str(child)
        assert record.child_scope == lin.SCOPE_READONLY_PARENT

    def test_build_lineage_record_root_parent_defaults_to_2(self, tmp_path):
        parent = make_novel(tmp_path / "第一部", "第一部")
        assert lin.build_lineage_record(parent).generation == 2


# ============================================================ 代际树


class TestGenerationTree:
    def test_walks_up_the_chain(self, tmp_path):
        gp = make_novel(tmp_path / "第一代", "第一代")
        parent = make_novel(tmp_path / "第二代", "第二代", lineage={"generation": 2, "parent_novel": str(gp)})
        child = make_novel(tmp_path / "第三代", "第三代", lineage={"generation": 3, "parent_novel": str(parent)})

        rows = lin.generation_tree(child)

        assert [r["generation"] for r in rows] == [3, 2, 1]
        assert rows[0]["is_current"] is True
        assert rows[0]["readonly"] is False
        assert all(r["readonly"] for r in rows[1:])
        assert rows[2]["title"] == "第一代"

    def test_flags_missing_parent(self, tmp_path):
        child = make_novel(
            tmp_path / "第二部", "第二部", lineage={"generation": 2, "parent_novel": str(tmp_path / "已删除")}
        )
        rows = lin.generation_tree(child)
        assert rows[1]["missing"] is True

    def test_cycle_is_broken_not_hung(self, tmp_path):
        """手改 meta 可能造出环；必须截断而不是无限循环。"""
        a = tmp_path / "A"
        b = tmp_path / "B"
        make_novel(a, "A", lineage={"generation": 2, "parent_novel": str(b)})
        make_novel(b, "B", lineage={"generation": 2, "parent_novel": str(a)})
        rows = lin.generation_tree(a, max_depth=8)
        assert len(rows) == 2

    def test_without_novel_returns_empty(self):
        assert lin.generation_tree(None) == []


# ============================================================ 🚨 护栏


class TestReadonlyParentGuard:
    def test_is_within_semantics(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        assert lin.is_within(root, root / "a" / "b") is True
        assert lin.is_within(root, root) is False  # 自身不算"之内"
        assert lin.is_within(root, tmp_path / "other") is False
        assert lin.is_within(root, root / ".." / "outside") is False

    def test_is_within_handles_junk(self, tmp_path):
        assert lin.is_within(None, tmp_path) is False
        assert lin.is_within(tmp_path, None) is False

    def test_guard_rejects_outside_target(self, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        with pytest.raises(ValueError, match="护栏拒绝"):
            lin.guard_child_path(child, tmp_path / "parent" / "file.json")

    def test_guard_rejects_traversal(self, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        with pytest.raises(ValueError):
            lin.guard_child_path(child, child / ".." / "parent" / "evil.json")

    def test_guard_rejects_empty_child(self, tmp_path):
        with pytest.raises(ValueError, match="子代目录为空"):
            lin.guard_child_path(None, tmp_path / "x")

    def test_guard_accepts_inside_target(self, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        assert lin.guard_child_path(child, child / "ok.json")

    def test_copy_into_child_refuses_outside(self, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        src = tmp_path / "src.txt"
        src.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            lin.copy_into_child(child, src, "../escaped.txt")

    def test_copy_missing_source_returns_none(self, tmp_path):
        child = tmp_path / "child"
        child.mkdir()
        assert lin.copy_into_child(child, tmp_path / "不存在.txt") is None

    def test_inherit_never_touches_parent(self, tmp_path):
        """**本文件最重要的一条**：继承前后父代目录逐字节不变。"""
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部", lineage={"generation": 2, "parent_novel": str(parent)})
        before = snapshot(parent)

        result = lin.inherit_into_child(child, parent)

        assert result["copied"], "应当有内容被复制，否则本测试没有验证力"
        assert snapshot(parent) == before, "护栏失效：父代目录被改动了"

    def test_inherit_writes_only_inside_child(self, tmp_path):
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")
        lin.inherit_into_child(child, parent)
        for path in child.rglob("*"):
            assert str(path).startswith(str(child))

    def test_scope_constant_is_recorded(self, tmp_path):
        parent = make_parent(tmp_path)
        record = lin.build_lineage_record(parent, era_gap_years=5)
        assert record.as_dict()["child_scope"] == "readonly_parent"


# ============================================================ 继承计划与执行


class TestInheritance:
    def test_plan_reports_missing(self, tmp_path):
        parent = make_novel(tmp_path / "第一部", "第一部")  # 只有 meta.json
        plan = lin.plan_inheritance(parent)
        assert "outline.json" in plan.missing
        assert plan.inherited["characters"] is True

    def test_plan_respects_checkboxes(self, tmp_path):
        parent = make_parent(tmp_path)
        plan = lin.plan_inheritance(parent, {"outline": False, "timeline": False})
        assert plan.items["outline"]["skipped"] is True
        assert plan.items["outline"]["copy"] == []
        assert plan.items["characters"]["copy"]

    def test_plan_is_pure(self, tmp_path):
        parent = make_parent(tmp_path)
        child = tmp_path / "第二部"
        lin.plan_inheritance(parent)
        assert not child.exists()

    def test_describe_mentions_counts(self, tmp_path):
        parent = make_parent(tmp_path)
        plan = lin.plan_inheritance(parent)
        assert "继承" in plan.describe()

    def test_execute_copies_selected_dimensions(self, tmp_path):
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")

        result = lin.inherit_into_child(child, parent, {"outline": True, "timeline": True})

        assert (child / "outline.json").exists()
        assert (child / "memory" / "timeline" / "timeline_000.json").exists()
        assert "outline.json" in result["copied"]

    def test_execute_skips_unchecked(self, tmp_path):
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")

        lin.inherit_into_child(child, parent, {"outline": False, "characters": False})

        assert not (child / "outline.json").exists()
        assert not (child / "characters").exists()

    def test_execute_merges_into_existing_child_dir(self, tmp_path):
        """`_create_sequel` 已经建过 characters/，继承必须合并而不是抛错。"""
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")
        (child / "characters").mkdir()
        (child / "characters" / "丙.json").write_text("{}", encoding="utf-8")

        lin.inherit_into_child(child, parent, {"characters": True})

        names = {p.name for p in (child / "characters").glob("*.json")}
        assert {"甲.json", "丙.json"} <= names

    def test_execute_writes_plot_report(self, tmp_path):
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")

        result = lin.inherit_into_child(child, parent)

        assert result["plots_file"] == "inherited_plots.md"
        text = (child / "inherited_plots.md").read_text(encoding="utf-8")
        assert "未解之谜" in text and "悬而未决" in text
        assert "天气很好" not in text

    def test_execute_with_no_args_is_noop(self, tmp_path):
        result = lin.inherit_into_child(None, None)
        assert result["copied"] == [] and result["plan"] is None

    def test_describe_plan_items(self, tmp_path):
        parent = make_parent(tmp_path)
        lines = list(lin.describe_plan_items(lin.plan_inheritance(parent)))
        assert any(line.startswith("✓") for line in lines)

    def test_describe_plan_items_marks_skipped(self, tmp_path):
        parent = make_parent(tmp_path)
        plan = lin.plan_inheritance(parent, {"plots": False})
        assert any("不继承" in line for line in lin.describe_plan_items(plan))


# ============================================================ 角色代际换算


class TestCharacterTransform:
    def test_age_progression_numeric(self):
        chars, notes = lin.apply_age_progression({"甲": {"age": 20}}, 15)
        assert chars["甲"]["age"] == 35
        assert any("20 → 35" in n for n in notes)

    def test_age_progression_string_with_digits(self):
        chars, _ = lin.apply_age_progression({"甲": {"age": "18岁"}}, 3)
        assert chars["甲"]["age"] == 21

    def test_non_numeric_age_preserved_with_note(self):
        chars, notes = lin.apply_age_progression({"甲": {"age": "不明"}}, 10)
        assert chars["甲"]["age"] == "不明"
        assert any("非数字" in n for n in notes)

    def test_missing_age_is_not_invented(self):
        chars, _ = lin.apply_age_progression({"甲": {"name": "甲"}}, 10)
        assert "age" not in chars["甲"]

    def test_zero_years_is_identity(self):
        chars, _ = lin.apply_age_progression({"甲": {"age": 20}}, 0)
        assert chars["甲"]["age"] == 20

    def test_never_deletes_characters(self):
        """项目硬约束：任何代际换算都不得让角色消失。"""
        source = {"甲": {"age": 20}, "乙": {"age": "?"}, "丙": {"age": 99}}
        chars, _ = lin.apply_age_progression(source, 30)
        chars, _ = lin.apply_death_status(chars, 500)
        assert set(chars) == set(source)

    def test_death_marks_deceased_without_deleting(self):
        chars, notes = lin.apply_death_status({"甲": {"name": "甲", "death_chapter": 80}}, last_chapter=120)
        assert chars["甲"]["status"] == "deceased"
        assert any("deceased" in n for n in notes)

    def test_death_after_parent_range_is_untouched(self):
        chars, _ = lin.apply_death_status({"甲": {"death_chapter": 200}}, last_chapter=120)
        assert "status" not in chars["甲"]

    def test_existing_status_is_not_overwritten(self):
        chars, _ = lin.apply_death_status({"甲": {"death_chapter": 10, "status": "复活"}}, last_chapter=120)
        assert chars["甲"]["status"] == "复活"

    @pytest.mark.parametrize("value", ["", None, "?", "未知"])
    def test_no_death_chapter_means_no_status(self, value):
        chars, _ = lin.apply_death_status({"甲": {"death_chapter": value}}, last_chapter=120)
        assert "status" not in chars["甲"]

    def test_make_character_transform_composes_both_steps(self):
        notes: list[str] = []
        transform = lin.make_character_transform(era_gap_years=10, last_chapter=100, notes=notes)
        result = transform({"甲": {"age": 20, "death_chapter": 50}})
        assert result["甲"]["age"] == 30
        assert result["甲"]["status"] == "deceased"
        assert len(notes) == 2

    def test_transform_tolerates_non_dict_entries(self):
        result = lin.make_character_transform()({"甲": "不是字典"})
        assert result["甲"] == "不是字典"


# ============================================================ 伏笔与章数


class TestPlotsAndChapters:
    def test_extract_unresolved_plots(self):
        text = "- 主角身世仍是未解之谜\n- 天气很好\n- 断剑来历悬而未决"
        plots = lin.extract_unresolved_plots(text)
        assert len(plots) == 2
        assert all("天气" not in p for p in plots)

    def test_extract_respects_limit(self):
        text = "\n".join(f"- 第{i}个未解之谜" for i in range(30))
        assert len(lin.extract_unresolved_plots(text, limit=5)) == 5

    def test_extract_dedupes(self):
        text = "- 未解之谜\n- 未解之谜\n"
        assert lin.extract_unresolved_plots(text) == ["未解之谜"]

    def test_extract_empty(self):
        assert lin.extract_unresolved_plots("") == []
        assert lin.extract_unresolved_plots("全是普通句子。") == []

    def test_inherited_plot_report_markdown(self, tmp_path):
        parent = make_parent(tmp_path)
        report = lin.inherited_plot_report(parent)
        assert report.startswith("#")
        assert "- [ ] " in report

    def test_inherited_plot_report_missing(self, tmp_path):
        assert lin.inherited_plot_report(tmp_path / "无") == ""
        assert lin.inherited_plot_report(None) == ""

    def test_parent_last_chapter_from_meta(self, tmp_path):
        parent = make_novel(tmp_path / "第一部", "第一部", chapter_count=120)
        assert lin.parent_last_chapter(parent) == 120

    def test_parent_last_chapter_falls_back_to_files(self, tmp_path):
        parent = make_novel(tmp_path / "第一部", "第一部")
        chapters = parent / "chapters"
        chapters.mkdir()
        for number in (1, 7, 42):
            (chapters / f"chapter_{number:04d}.txt").write_text("x", encoding="utf-8")
        assert lin.parent_last_chapter(parent) == 42

    def test_parent_last_chapter_without_data(self, tmp_path):
        assert lin.parent_last_chapter(tmp_path / "无") == 0
        assert lin.parent_last_chapter(None) == 0


# ============================================================ 去重辅助


class TestDedupePreserveOrder:
    """`inherit_into_child` 用它去重（`memory` 与 `plots` 都会带上 global_summary.txt）。"""

    def test_keeps_first_occurrence_order(self):
        assert lin.dedupe_preserve_order(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]

    def test_empty(self):
        assert lin.dedupe_preserve_order([]) == []

    def test_inherit_result_has_no_duplicates(self, tmp_path):
        """`memory/global_summary.txt` 同时属于 memory 与 plots 两个维度，结果不得重复。"""
        parent = make_parent(tmp_path)
        child = make_novel(tmp_path / "第二部", "第二部")

        result = lin.inherit_into_child(child, parent, {"memory": True, "plots": True})

        assert len(result["copied"]) == len(set(result["copied"]))
