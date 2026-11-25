"""数据一致性检查器的测试。

## 两个方向都要测

- **检出力**：造出每一类漂移，断言检查器能报出来（否则工具是摆设）
- **不误报**：造一部完全健康的作品，断言零 issue

第二条同样重要：第一版判据把 639 个 `plot_*` 条目全判成 error，
纯属误报 —— 所以"健康作品必须零告警"是硬要求。

`scripts/` 不在包内，用 sys.path 注入后直接导入（与 `test_bundle_manifest` 同法）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import check_data_consistency as cdc  # noqa: E402


def _make_novel(tmp: Path, chapters=(1, 2, 3), summaries=None, *, count: int | None = None) -> Path:
    """造一部作品；`summaries` 默认与 chapters 一致。"""
    (tmp / "chapters").mkdir(parents=True)
    (tmp / "memory" / "chapters").mkdir(parents=True)
    meta = {"title": "测试书"}
    if count is not None:
        meta["chapter_count"] = count
    (tmp / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    for n in chapters:
        (tmp / "chapters" / f"chapter_{n:04d}.txt").write_text(f"正文{n}", encoding="utf-8")
    for n in summaries if summaries is not None else chapters:
        (tmp / "memory" / "chapters" / f"chapter_{n:05d}.txt").write_text(f"摘要{n}", encoding="utf-8")
    return tmp


class TestHealthyNovel:
    def test_no_issues_at_all(self, tmp_path):
        novel = _make_novel(tmp_path, count=3)
        report = cdc.check_novel(novel)
        assert report.issues == [], f"健康作品被误报：{[i.detail for i in report.issues]}"

    def test_chapter_prefix_index_is_clean(self, tmp_path):
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text(
            json.dumps({"林风": ["chapter_00001", "chapter_00002"]}), encoding="utf-8"
        )
        assert cdc.check_novel(novel).issues == []


class TestChapterCount:
    def test_mismatch_reported(self, tmp_path):
        novel = _make_novel(tmp_path, count=10)
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "chapter_count_mismatch" and i.severity == "warn" for i in issues)

    def test_non_numeric_count_reported(self, tmp_path):
        novel = _make_novel(tmp_path, count="很多")
        assert any(i.kind == "chapter_count_mismatch" for i in cdc.check_novel(novel).issues)

    def test_absent_count_not_reported(self, tmp_path):
        novel = _make_novel(tmp_path)
        assert not any(i.kind == "chapter_count_mismatch" for i in cdc.check_novel(novel).issues)


class TestSummaries:
    def test_missing_summary(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 2, 3), summaries=(1, 2))
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "missing_summary" and "3" in i.detail for i in issues)

    def test_orphan_summary(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 2), summaries=(1, 2, 9))
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "orphan_summary" and "9" in i.detail for i in issues)


class TestGaps:
    def test_gap_reported(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 3, 4), summaries=(1, 3, 4))
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "chapter_gap" and "2" in i.detail for i in issues)

    def test_no_gap_on_continuous(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 2, 3), summaries=(1, 2, 3))
        assert not any(i.kind == "chapter_gap" for i in cdc.check_novel(novel).issues)


class TestInvertedIndex:
    def test_chapter_orphan_is_error(self, tmp_path):
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text(
            json.dumps({"林风": ["chapter_00001", "chapter_00099"]}), encoding="utf-8"
        )
        issues = cdc.check_novel(novel).issues
        orphan = [i for i in issues if i.kind == "index_orphan"]
        assert orphan and orphan[0].severity == "error"
        assert "chapter_00099" in orphan[0].detail

    def test_unmapped_type_is_only_warning(self, tmp_path):
        """plot_* 这类无对应存储的文档**不能**判 error —— 那是第一版的误报。"""
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text(
            json.dumps({"某情节": ["plot_123", "plot_456"]}), encoding="utf-8"
        )
        issues = cdc.check_novel(novel).issues
        assert not any(i.kind == "index_orphan" for i in issues), "非章节文档被误判为孤儿"
        hits = [i for i in issues if i.kind == "index_unmapped_type"]
        assert hits and hits[0].severity == "warn"
        assert "plot 2 个" in hits[0].detail

    def test_corrupt_index_does_not_crash(self, tmp_path):
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text("{broken", encoding="utf-8")
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "index_orphan" and i.severity == "error" for i in issues)

    def test_non_dict_index_root_reported(self, tmp_path):
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text("[1,2,3]", encoding="utf-8")
        assert any("根节点" in i.detail for i in cdc.check_novel(novel).issues)


class TestTimeline:
    def _write(self, novel: Path, events) -> None:
        tdir = novel / "memory" / "timeline"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "timeline_000.json").write_text(json.dumps(events), encoding="utf-8")

    def test_out_of_range_chapter_is_error(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 2, 3), summaries=(1, 2, 3))
        self._write(novel, [{"chapter": 1, "event": "a"}, {"chapter": 99, "event": "b"}])
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "timeline_chapter_invalid" and i.severity == "error" for i in issues)

    def test_zero_chapter_is_error(self, tmp_path):
        novel = _make_novel(tmp_path)
        self._write(novel, [{"chapter": 0, "event": "a"}])
        assert any(i.kind == "timeline_chapter_invalid" for i in cdc.check_novel(novel).issues)

    def test_valid_events_pass(self, tmp_path):
        novel = _make_novel(tmp_path, chapters=(1, 2, 3), summaries=(1, 2, 3))
        self._write(novel, [{"chapter": 1, "event": "a"}, {"chapter": 3, "event": "b"}])
        assert not any(i.kind == "timeline_chapter_invalid" for i in cdc.check_novel(novel).issues)

    def test_corrupt_shard_does_not_crash(self, tmp_path):
        novel = _make_novel(tmp_path)
        tdir = novel / "memory" / "timeline"
        tdir.mkdir(parents=True)
        (tdir / "timeline_000.json").write_text("{broken", encoding="utf-8")
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "timeline_chapter_invalid" for i in issues)


class TestBranches:
    def test_unopenable_branch_warns(self, tmp_path):
        novel = _make_novel(tmp_path)
        (novel / "timelines" / "branch_000").mkdir(parents=True)  # 无 meta.json
        issues = cdc.check_novel(novel).issues
        assert any(i.kind == "branch_unopenable" and i.severity == "warn" for i in issues)

    def test_openable_branch_is_clean(self, tmp_path):
        novel = _make_novel(tmp_path)
        branch = novel / "timelines" / "branch_000"
        branch.mkdir(parents=True)
        (branch / "meta.json").write_text(json.dumps({"title": "分支甲"}), encoding="utf-8")
        assert not any(i.kind == "branch_unopenable" for i in cdc.check_novel(novel).issues)


class TestCli:
    def test_missing_path_returns_2(self, tmp_path):
        assert cdc.main([str(tmp_path / "nope")]) == 2

    def test_healthy_novel_returns_0(self, tmp_path):
        novel = _make_novel(tmp_path, count=3)
        assert cdc.main([str(novel)]) == 0

    def test_error_novel_returns_1(self, tmp_path, capsys):
        novel = _make_novel(tmp_path)
        (novel / "memory" / "inverted_index.json").write_text(json.dumps({"x": ["chapter_00099"]}), encoding="utf-8")
        assert cdc.main([str(novel)]) == 1

    def test_json_output_is_parseable(self, tmp_path, capsys):
        novel = _make_novel(tmp_path)
        cdc.main([str(novel), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list) and payload[0]["novel"] == novel.name

    def test_root_directory_scans_multiple(self, tmp_path):
        _make_novel(tmp_path / "a", count=3)
        _make_novel(tmp_path / "b", count=3)
        assert cdc.main([str(tmp_path)]) == 0
