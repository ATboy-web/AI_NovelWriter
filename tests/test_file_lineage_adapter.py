"""适配器容错路径测试（`FileBranchMetaReader`）。

适配器是"外部世界"的边界：目录不存在、名字不合法、meta 损坏都可能在真实机器上出现，
且**不该让"列分支"整个失败**。这几种情形在领域层测不到（它不碰磁盘），
只能在适配器层用临时目录 + monkeypatch 覆盖。
"""

from __future__ import annotations

from pathlib import Path

from app.adapters import FileBranchMetaReader, file_lineage


class TestFileBranchMetaReader:
    def test_empty_parent_dir(self):
        assert FileBranchMetaReader().list_branch_metas(None) == []
        assert FileBranchMetaReader().list_branch_metas("") == []

    def test_missing_timelines_dir(self, tmp_path):
        assert FileBranchMetaReader().list_branch_metas(tmp_path) == []

    def test_timelines_is_a_file_not_dir(self, tmp_path):
        (tmp_path / "timelines").write_text("x", encoding="utf-8")
        assert FileBranchMetaReader().list_branch_metas(tmp_path) == []

    def test_unreadable_dir_returns_empty(self, tmp_path, monkeypatch):
        """目录权限异常（如被占用）时应降级为空列表而不是抛给调用方。"""
        base = tmp_path / "timelines"
        base.mkdir()

        def boom(self):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "iterdir", boom)
        assert FileBranchMetaReader().list_branch_metas(tmp_path) == []

    def test_corrupt_meta_mapped_to_empty_dict(self, tmp_path):
        base = tmp_path / "timelines"
        broken = base / "branch_000"
        broken.mkdir(parents=True)
        (broken / "meta.json").write_text("{not json", encoding="utf-8")

        rows = FileBranchMetaReader().list_branch_metas(tmp_path)
        assert rows == [("branch_000", {})]

    def test_non_object_meta_mapped_to_empty_dict(self, tmp_path):
        base = tmp_path / "timelines"
        b = base / "branch_001"
        b.mkdir(parents=True)
        (b / "meta.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert FileBranchMetaReader().list_branch_metas(tmp_path) == [("branch_001", {})]

    def test_ignores_non_branch_directories(self, tmp_path):
        base = tmp_path / "timelines"
        base.mkdir()
        (base / "branch_000").mkdir()
        (base / "other_dir").mkdir()
        (base / "stray_file.txt").write_text("x", encoding="utf-8")
        rows = FileBranchMetaReader().list_branch_metas(tmp_path)
        assert [name for name, _ in rows] == ["branch_000"]

    def test_sorted_ascending(self, tmp_path):
        base = tmp_path / "timelines"
        for name in ("branch_002", "branch_000", "branch_001"):
            (base / name).mkdir(parents=True)
        rows = FileBranchMetaReader().list_branch_metas(tmp_path)
        assert [n for n, _ in rows] == ["branch_000", "branch_001", "branch_002"]

    def test_constants_match_legacy(self):
        """前缀与目录名必须与旧实现一致，否则老数据读不到。"""
        from app import lineage

        assert file_lineage.BRANCH_PREFIX == lineage.BRANCH_PREFIX
        assert file_lineage.BRANCH_PARENT_REL == lineage.BRANCH_PARENT_REL
