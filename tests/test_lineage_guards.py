"""`lineage` 的元数据容错与继承护栏（档 1：子代可能写坏父代）。

## 这个模块的唯一职责

`lineage` 是「**子代只读父代**」这条硬不变式的落点：
`guard_child_path` / `resolve_child_target` 是唯一强制点，`discover_branches`
是唯一入口。它出错的方式是**两个作品互相污染** —— 那种损坏事后极难拆开。

## 覆盖

- `read_meta` 的三种回落（空目录 / 损坏 / 正常）
- `copy_into_child` 的目录合并（子代已存在同名目录时不能抛）
- 父代全局摘要读不出来时**跳过伏笔继承**而不是让续集建不起来
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import lineage as lg


def _novel(root: Path, *, meta: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(exist_ok=True)
    if meta is not None:
        (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return root


class TestReadMeta:
    def test_empty_dir_returns_empty(self):
        assert lg.read_meta(None) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert lg.read_meta(_novel(tmp_path / "book")) == {}

    def test_corrupt_file_returns_empty(self, tmp_path):
        book = _novel(tmp_path / "book")
        (book / "meta.json").write_text("{ 坏", encoding="utf-8")

        assert lg.read_meta(book) == {}

    def test_valid_meta_returned_as_dict(self, tmp_path):
        book = _novel(tmp_path / "book", meta={"title": "长篇", "protagonist": "林风"})

        assert lg.read_meta(book)["title"] == "长篇"


class TestCopyIntoChild:
    """复制进子代时每一步都要过护栏 —— 拼错路径就是两个作品互相污染。"""

    def test_missing_source_returns_none(self, tmp_path):
        child = _novel(tmp_path / "child")

        assert lg.copy_into_child(child, tmp_path / "没有这个") is None

    def test_file_copy(self, tmp_path):
        child = _novel(tmp_path / "child")
        src = tmp_path / "父代角色.json"
        src.write_text("{}", encoding="utf-8")

        dst = lg.copy_into_child(child, src)

        assert dst is not None and dst.exists()
        assert dst.parent == child.resolve() or child.resolve() in dst.parents

    def test_directory_merges_into_existing(self, tmp_path):
        """子代可能已经有 `characters/`（续集流程先建过）——
        要**合并**，不能抛 FileExistsError 让建续集失败。
        """
        child = _novel(tmp_path / "child")
        (child / "characters").mkdir()
        (child / "characters" / "子代已有.json").write_text("{}", encoding="utf-8")
        src = tmp_path / "父代" / "characters"
        src.mkdir(parents=True)
        (src / "父代角色.json").write_text("{}", encoding="utf-8")

        dst = lg.copy_into_child(child, src, "characters")

        assert dst is not None
        names = {p.name for p in dst.iterdir()}
        assert names == {"子代已有.json", "父代角色.json"}, "合并把子代已有文件覆盖丢了"

    def test_traversal_relative_is_rejected(self, tmp_path):
        """`..` 必须在 `resolve_child_target` 就被拒 —— 不能等 copytree 才发现。"""
        child = _novel(tmp_path / "child")
        src = tmp_path / "父代文件.txt"
        src.write_text("x", encoding="utf-8")

        with pytest.raises(Exception):
            lg.copy_into_child(child, src, "../逃逸.txt")


class TestInheritedPlotReport:
    def test_no_parent_returns_empty(self):
        assert lg.inherited_plot_report(None) == ""

    def test_missing_summary_returns_empty(self, tmp_path):
        assert lg.inherited_plot_report(_novel(tmp_path / "book")) == ""

    def test_unreadable_summary_is_skipped(self, tmp_path, monkeypatch):
        """父代摘要读不出来时**跳过伏笔继承** —— 不能因此建不了续集。"""
        book = _novel(tmp_path / "book")
        (book / "memory" / "global_summary.txt").write_text("伏笔：黑剑的来历", encoding="utf-8")
        real = Path.read_text

        def boom(self, *a, **kw):
            if "global_summary" in str(self):
                raise OSError("文件被占用")
            return real(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", boom)

        assert lg.inherited_plot_report(book) == ""

    def test_no_unresolved_plots_returns_empty(self, tmp_path):
        book = _novel(tmp_path / "book")
        (book / "memory" / "global_summary.txt").write_text("一切都已经交代清楚。", encoding="utf-8")

        assert lg.inherited_plot_report(book) == ""

    def test_plots_become_markdown_checklist(self, tmp_path):
        book = _novel(tmp_path / "book")
        (book / "memory" / "global_summary.txt").write_text(
            "未回收伏笔：黑剑的来历\n未回收伏笔：师父的真实身份\n", encoding="utf-8"
        )

        text = lg.inherited_plot_report(book)

        assert text.startswith("# 前代未回收伏笔")
        assert "- [ ]" in text


class TestBranchesAndTree:
    """`discover_branches` 是子代目录的**唯一入口** —— 它错了会把父代当子代。"""

    def test_no_timelines_dir_returns_empty(self, tmp_path):
        assert lg.discover_branches(_novel(tmp_path / "book")) == []

    def test_branches_are_listed(self, tmp_path):
        book = _novel(tmp_path / "book")
        for i in (1, 2):
            branch = book / "timelines" / f"branch_{i:03d}"
            _novel(branch, meta={"title": f"分支{i}"})

        rows = lg.discover_branches(book)

        assert len(rows) == 2
        assert all("branch" in str(r) for r in rows)

    def test_generation_tree_without_meta(self, tmp_path):
        book = _novel(tmp_path / "book")

        tree = lg.generation_tree(book)

        assert isinstance(tree, list)
