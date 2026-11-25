"""继承计划的领域层测试（假 probe，**不建任何目录**）。

## 这个文件证明的事

`lineage.plan_inheritance(parent_dir, inherited)` 以前必须**造一套真实目录**
才能验证"父代缺大纲时会不会如实报告 missing"。抽了 `PathProbe` 之后，
判定逻辑变成 `domain.build_inheritance_plan(parent_dir, inherited, probe)`：
喂一个记录调用次数的假 probe 就能穷举所有组合。

`lineage.plan_inheritance` 的原签名仍保留（面板在用），由
`tests/test_lineage.py::TestInheritance` 覆盖真实磁盘路径 —— 两组互补。
"""

from __future__ import annotations

import pytest

from app.domain.lineage import (
    DEFAULT_INHERITED,
    DIMENSION_SOURCES,
    INHERIT_DIMENSIONS,
    build_inheritance_plan,
    describe_plan_items,
)


class FakeProbe:
    """按给定的"存在集合"回答；同时记录被问过哪些相对路径。"""

    def __init__(self, existing: set[str] | None = None):
        self._existing = set(existing or ())
        self.asked: list[str] = []

    def exists(self, relative_path: str) -> bool:
        self.asked.append(relative_path)
        return relative_path in self._existing


class TestBuildInheritancePlan:
    def test_all_dimensions_present(self):
        every = {rel for rels in DIMENSION_SOURCES.values() for rel in rels}
        plan = build_inheritance_plan("/parent", None, FakeProbe(every))
        assert plan.missing == []
        for dim in INHERIT_DIMENSIONS:
            assert plan.items[dim]["copy"] == list(DIMENSION_SOURCES[dim])
            assert plan.items[dim]["skipped"] is False

    def test_nothing_present_marks_all_missing(self):
        plan = build_inheritance_plan("/parent", None, FakeProbe())
        expected = sum(len(v) for v in DIMENSION_SOURCES.values())
        assert len(plan.missing) == expected
        assert all(plan.items[d]["copy"] == [] for d in INHERIT_DIMENSIONS)

    def test_partial_presence_splits_copy_and_missing(self):
        probe = FakeProbe({"outline.json"})
        plan = build_inheritance_plan("/parent", None, probe)
        assert plan.items["outline"]["copy"] == ["outline.json"]
        assert "memory/settings.json" in plan.items["settings"]["missing"]

    def test_unchecked_dimension_is_skipped_and_not_probed(self):
        probe = FakeProbe()
        plan = build_inheritance_plan("/parent", {"outline": False}, probe)
        assert plan.items["outline"]["skipped"] is True
        assert plan.items["outline"]["copy"] == []
        assert "outline.json" not in probe.asked, "未勾选的维度不该去问 probe（无谓 IO）"

    def test_checked_dimension_is_probed(self):
        probe = FakeProbe()
        build_inheritance_plan("/parent", {"characters": True}, probe)
        for rel in DIMENSION_SOURCES["characters"]:
            assert rel in probe.asked

    def test_unknown_keys_in_inherited_are_ignored(self):
        plan = build_inheritance_plan("/parent", {"不存在的维度": True}, FakeProbe())
        assert set(plan.items) == set(INHERIT_DIMENSIONS)

    def test_defaults_apply_when_inherited_is_none(self):
        plan = build_inheritance_plan("/parent", None, FakeProbe())
        assert plan.inherited == DEFAULT_INHERITED
        assert all(plan.inherited.values())

    def test_empty_parent_dir_skips_probing(self):
        """父代目录为空时没有可比对的基准 —— 不去问 probe，也不报 missing。"""
        probe = FakeProbe()
        plan = build_inheritance_plan("", None, probe)
        assert probe.asked == []
        assert all(plan.items[d]["copy"] == [] for d in INHERIT_DIMENSIONS)
        assert plan.missing == []

    def test_parent_dir_is_preserved_as_string(self):
        plan = build_inheritance_plan("/some/parent", None, FakeProbe())
        assert plan.parent_dir == "/some/parent"

    def test_probe_receives_relative_paths_only(self):
        """probe 的契约是**相对路径**；收到绝对路径说明拼装逻辑漏到了领域层。"""
        probe = FakeProbe()
        build_inheritance_plan("/parent", None, probe)
        assert probe.asked, "probe 一次都没被问，用例失去意义"
        assert all(not p.startswith("/") for p in probe.asked)

    def test_plan_is_describable(self):
        plan = build_inheritance_plan("/parent", None, FakeProbe())
        text = plan.describe()
        assert "继承" in text and "缺" in text

    @pytest.mark.parametrize("dim", list(INHERIT_DIMENSIONS))
    def test_every_dimension_has_sources(self, dim):
        """维度表与勾选项必须一一对应，否则面板上会出现"勾了但没东西可拷"。"""
        assert DIMENSION_SOURCES.get(dim), f"{dim} 没有配置任何来源路径"

    def test_rendered_items_cover_all_dimensions(self):
        plan = build_inheritance_plan("/parent", None, FakeProbe())
        rendered = list(describe_plan_items(plan))
        assert len(rendered) >= len(INHERIT_DIMENSIONS)


class TestPathProbes:
    """端口两个实现的契约（领域层只依赖 `exists(relative_path) -> bool`）。"""

    def test_filesystem_probe_reads_real_disk(self, tmp_path):
        from app.adapters import FilesystemProbe

        (tmp_path / "outline.json").write_text("{}", encoding="utf-8")
        probe = FilesystemProbe(tmp_path)
        assert probe.exists("outline.json") is True
        assert probe.exists("missing.json") is False

    def test_filesystem_probe_without_root(self):
        from app.adapters import FilesystemProbe

        assert FilesystemProbe(None).exists("anything") is False

    def test_never_exists_probe(self):
        from app.adapters import NeverExistsProbe

        assert NeverExistsProbe().exists("anything") is False

    def test_oserror_treated_as_absent(self, tmp_path, monkeypatch):
        """权限不足 / 路径过长时按"不存在"处理 —— 继承计划不该整体失败。"""
        from pathlib import Path

        from app.adapters import FilesystemProbe

        def boom(self):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "exists", boom)
        assert FilesystemProbe(tmp_path).exists("x") is False
