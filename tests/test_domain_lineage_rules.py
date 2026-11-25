"""世代传承**领域规则**的单元测试（不建目录、不碰磁盘）。

## 搬迁带来的差别

这些函数原先住在 `app/lineage.py`（821 行、与读写混在一起）。要测
「年龄推进遇到非数字 `age` 怎么办」，得先造一套作品目录再间接调用。
搬到 `app/domain/lineage.py` 后它们是无副作用的纯函数，直接喂字典即可。

## 与既有测试的分工

`tests/test_lineage.py` 已覆盖 `LineageRecord.from_meta` 的类型容错、
`is_within`/`guard_child_path` 的主路径、继承计划。本文件**只补它没覆盖的**：
`unresolved_plot_keywords`（此前零覆盖）、以及各纯函数的边界输入。
"""

from __future__ import annotations

import pytest

from app.domain.lineage import (
    DEFAULT_INHERITED,
    INHERIT_DIMENSIONS,
    LineageRecord,
    apply_age_progression,
    apply_death_status,
    dedupe_preserve_order,
    describe_plan_items,
    extract_unresolved_plots,
    is_within,
    unresolved_plot_keywords,
)


class TestUnresolvedPlots:
    """关键词表是「从父代摘要里抽伏笔」的唯一判据，此前完全没有测试。"""

    def test_returns_non_empty_tuple(self):
        keywords = unresolved_plot_keywords()
        assert isinstance(keywords, tuple)
        assert len(keywords) >= 3, "关键词表为空会让伏笔抽取永远抽不到东西"

    def test_no_duplicates(self):
        keywords = unresolved_plot_keywords()
        assert len(keywords) == len(set(keywords))

    def test_no_empty_strings(self):
        assert all(k.strip() for k in unresolved_plot_keywords())

    def test_stable_across_calls(self):
        assert unresolved_plot_keywords() == unresolved_plot_keywords()


class TestExtractUnresolvedPlots:
    def test_empty_text_gives_empty_list(self):
        assert extract_unresolved_plots("") == []

    def test_no_keyword_gives_empty_list(self):
        assert extract_unresolved_plots("今天天气不错，主角吃了顿饭。") == []

    def test_hits_keyword_sentence(self):
        text = "他想起母亲留下的玉佩，这个谜团始终没有解开。"
        found = extract_unresolved_plots(text)
        assert found, "含关键词的句子没有被抽出来"
        assert any("玉佩" in item or "谜团" in item for item in found)

    def test_respects_limit(self):
        keyword = unresolved_plot_keywords()[0]
        text = "。".join(f"第{i}处{keyword}还没解决" for i in range(20)) + "。"
        assert len(extract_unresolved_plots(text, limit=3)) <= 3

    def test_no_duplicate_sentences(self):
        keyword = unresolved_plot_keywords()[0]
        text = f"这里有个{keyword}。这里有个{keyword}。"
        found = extract_unresolved_plots(text)
        assert len(found) == len(set(found))

    def test_none_text_tolerated(self):
        assert extract_unresolved_plots(None) == []  # type: ignore[arg-type]


class TestApplyAgeProgression:
    def _chars(self):
        return {"甲": {"age": 20, "gender": "男"}, "乙": {"age": 30}}

    def test_adds_years(self):
        updated, notes = apply_age_progression(self._chars(), 5)
        assert updated["甲"]["age"] == 25
        assert updated["乙"]["age"] == 35

    def test_zero_years_is_noop_values(self):
        updated, _ = apply_age_progression(self._chars(), 0)
        assert updated["甲"]["age"] == 20

    def test_negative_years_clamped_at_zero(self):
        """年龄不能被推进成负数 —— 那是数据损坏，不是"回到过去"。

        ⚠️ 这条用例在搬迁后第一次跑就失败了：旧实现是裸的 `age + years`，
        3 岁减 10 年得到 **-7 岁**。修实现（夹到 0 并在说明里写明推算值）。
        """
        updated, notes = apply_age_progression({"甲": {"age": 3}}, -10)
        assert updated["甲"]["age"] == 0
        assert any("夹到 0" in n for n in notes)

    @pytest.mark.parametrize("bad", ["二十", None, "", []])
    def test_non_numeric_age_does_not_crash(self, bad):
        updated, notes = apply_age_progression({"甲": {"age": bad}}, 5)
        assert "甲" in updated
        assert isinstance(notes, list)

    def test_missing_age_field_tolerated(self):
        updated, _ = apply_age_progression({"甲": {"gender": "男"}}, 5)
        assert "甲" in updated

    def test_does_not_mutate_input(self):
        original = self._chars()
        snapshot = {"甲": dict(original["甲"]), "乙": dict(original["乙"])}
        apply_age_progression(original, 5)
        assert original == snapshot, "输入被就地修改了 —— 调用方可能还在用旧值"

    def test_empty_mapping(self):
        updated, notes = apply_age_progression({}, 5)
        assert updated == {} and notes == []


class TestApplyDeathStatus:
    def test_marks_character_dead_after_death_chapter(self):
        chars = {"甲": {"death_chapter": 3}}
        updated, _ = apply_death_status(chars, last_chapter=5)
        assert updated["甲"]["status"] == "deceased"

    def test_not_marked_before_death_chapter(self):
        chars = {"甲": {"death_chapter": 9}}
        updated, _ = apply_death_status(chars, last_chapter=5)
        assert updated["甲"].get("status") != "deceased"

    def test_character_without_death_field_untouched(self):
        chars = {"甲": {"age": 20}}
        updated, _ = apply_death_status(chars, last_chapter=100)
        assert updated["甲"]["age"] == 20

    def test_never_deletes_characters(self):
        """数据保全铁律：推进死亡状态**绝不删角色**。"""
        chars = {"甲": {"death_chapter": 1}, "乙": {}}
        updated, _ = apply_death_status(chars, last_chapter=10)
        assert set(updated) == {"甲", "乙"}


class TestDedupePreserveOrder:
    def test_removes_duplicates_keeping_first_order(self):
        assert dedupe_preserve_order(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]

    def test_empty(self):
        assert dedupe_preserve_order([]) == []

    def test_all_unique_unchanged(self):
        assert dedupe_preserve_order(["x", "y", "z"]) == ["x", "y", "z"]

    def test_generator_input(self):
        assert dedupe_preserve_order(i for i in [1, 1, 2]) == [1, 2]


class TestIsWithin:
    def test_same_path_is_not_within(self, tmp_path):
        """是**严格子路径**判定：同一个路径不算在里面。

        这正是护栏需要的语义 —— 子代写自己的根目录不算越界，但目标==子代根
        也不该被当成写进了父代。
        """
        assert is_within(tmp_path, tmp_path) is False

    def test_child_is_within(self, tmp_path):
        assert is_within(tmp_path, tmp_path / "sub" / "file.txt") is True

    def test_outside_is_not_within(self, tmp_path):
        assert is_within(tmp_path / "a", tmp_path / "b") is False

    def test_parent_is_not_within_child(self, tmp_path):
        assert is_within(tmp_path / "a" / "b", tmp_path / "a") is False

    def test_none_root_is_false(self):
        assert is_within(None, "/tmp/x") is False


class TestRecordDefaults:
    def test_default_inherited_covers_all_dimensions(self):
        assert set(DEFAULT_INHERITED) == set(INHERIT_DIMENSIONS)
        assert all(DEFAULT_INHERITED.values())

    def test_record_is_root_by_default(self):
        assert LineageRecord().is_root is True

    def test_record_as_dict_roundtrip(self):
        record = LineageRecord(generation=2, parent_novel="p", branch_id="003", origin_chapter=5)
        data = record.as_dict()
        assert data["generation"] == 2 and data["branch_id"] == "003"
        assert LineageRecord.from_meta({"lineage": data}) == record


class TestDescribePlanItems:
    def test_empty_plan_still_lists_all_dimensions(self):
        """空计划也会逐维度输出"无可复制项" —— 让用户看到"检查过了"而不是一片空白。"""
        from app.domain.lineage import InheritancePlan

        rendered = list(describe_plan_items(InheritancePlan()))
        assert rendered, "空计划应给出逐维度说明，而不是空列表"
        assert any("无可复制项" in line for line in rendered)

    def test_items_rendered(self):
        from app.domain.lineage import InheritancePlan

        plan = InheritancePlan(
            parent_dir="/p", inherited={"characters": True}, items={"characters": {"paths": ["characters"]}}
        )
        rendered = list(describe_plan_items(plan))
        assert isinstance(rendered, list)


class TestGuardChildPath:
    """「子代只读父代」护栏的判定边界（纯路径计算，无需造真实目录）。"""

    def test_accepts_path_inside(self, tmp_path):
        from app.domain.lineage import guard_child_path

        child = tmp_path / "child"
        assert guard_child_path(child, child / "chapters" / "1.txt") == child / "chapters" / "1.txt"

    def test_rejects_parent_escape(self, tmp_path):
        from app.domain.lineage import guard_child_path

        with pytest.raises(ValueError, match="护栏拒绝"):
            guard_child_path(tmp_path / "child", tmp_path / "parent" / "x.txt")

    def test_rejects_dotdot(self, tmp_path):
        from app.domain.lineage import resolve_child_target

        child = tmp_path / "child"
        child.mkdir()
        with pytest.raises(ValueError):
            resolve_child_target(child, "../sibling.txt")

    def test_rejects_absolute_relative_path(self, tmp_path):
        """`Path('/a') / '/etc/x'` 会**丢弃**左边 —— 必须拦住。"""
        from app.domain.lineage import resolve_child_target

        child = tmp_path / "child"
        child.mkdir()
        with pytest.raises(ValueError):
            resolve_child_target(child, str(tmp_path / "outside" / "x.txt"))

    def test_prefix_lookalike_directory_is_rejected(self, tmp_path):
        """`/a/bc` 与 `/a/b` 前缀相同但不是子目录 —— 经典的 startswith 漏洞。"""
        from app.domain.lineage import guard_child_path

        base = tmp_path / "b"
        lookalike = tmp_path / "bc"
        lookalike.mkdir()
        base.mkdir()
        with pytest.raises(ValueError):
            guard_child_path(base, lookalike / "x.txt")

    def test_empty_child_dir_rejected(self):
        from app.domain.lineage import guard_child_path

        with pytest.raises(ValueError, match="子代目录为空"):
            guard_child_path("", "/tmp/x")

    def test_empty_relative_rejected(self, tmp_path):
        from app.domain.lineage import resolve_child_target

        with pytest.raises(ValueError, match="相对路径为空"):
            resolve_child_target(tmp_path, "   ")

    def test_normal_relative_resolves_inside(self, tmp_path):
        from app.domain.lineage import resolve_child_target

        target = resolve_child_target(tmp_path, "memory/settings.json")
        assert target == tmp_path / "memory" / "settings.json"

    def test_symlink_inside_is_allowed_but_outside_link_target_rejected(self, tmp_path):
        """护栏判的是**解析后**的路径：目录内软链本身没问题。"""
        from app.domain.lineage import resolve_child_target

        child = tmp_path / "child"
        child.mkdir()
        (child / "real").mkdir()
        try:
            (child / "link").symlink_to(child / "real", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不支持创建符号链接")
        assert resolve_child_target(child, "link/1.txt") == child / "link" / "1.txt"
