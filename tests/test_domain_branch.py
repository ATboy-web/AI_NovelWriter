"""领域层与用例的单元测试（**不建任何目录**）。

## 这个文件要证明的事

重构前，要验证"缺 meta 的分支判为不可打开"，必须先 `mkdir` 一套
`timelines/branch_000/meta.json` 再调 `discover_branches()` —— 测试与文件系统耦合。

分层后：
- `domain.describe_branch(branch_id, meta)` 是纯函数 ⇒ 直接喂字典，穷举边界；
- `application.ListBranches` 依赖注入 `BranchMetaReader` ⇒ 用内存替身即可跑完用例。

同一批断言，成本从"造目录 + 清目录"降到"传一个字面量"。
"""

from __future__ import annotations

import pytest

from app.application import ListBranches
from app.domain import BranchInfo, describe_branch
from app.domain.branch import REASON_NO_META


class TestDescribeBranch:
    def test_none_meta_is_not_openable(self):
        info = describe_branch("003", None, fallback_title="branch_003")
        assert isinstance(info, BranchInfo)
        assert info.openable is False
        assert info.reason == REASON_NO_META
        assert info.branch_id == "003"

    def test_empty_meta_is_not_openable(self):
        assert describe_branch("003", {}).openable is False

    def test_non_mapping_meta_is_tolerated(self):
        """适配器可能顺手传进 list/str —— 领域层不该因此抛异常。"""
        assert describe_branch("003", ["not", "a", "dict"]).openable is False

    def test_full_meta_maps_every_field(self):
        info = describe_branch(
            "001",
            {"title": "分支: 留下", "origin_chapter": 5, "status": "active", "chapter_count": 7},
            fallback_title="branch_001",
        )
        assert info == BranchInfo(
            branch_id="001",
            title="分支: 留下",
            origin_chapter=5,
            status="active",
            chapter_count=7,
            openable=True,
            reason="",
        )

    def test_title_falls_back_to_meta_name(self):
        assert describe_branch("001", {"name": "备用名"}).title == "备用名"

    def test_title_falls_back_to_dir_name(self):
        assert describe_branch("001", {"status": "x"}, fallback_title="branch_001").title == "branch_001"

    def test_title_falls_back_to_branch_id(self):
        assert describe_branch("009", {"status": "x"}).title == "009"

    @pytest.mark.parametrize("bad", ["第5章", None, "", {}, []])
    def test_bad_origin_chapter_coerced_to_zero(self, bad):
        """旧实现直接 int() —— 非数字串会让**整个列表**抛 ValueError。"""
        assert describe_branch("001", {"origin_chapter": bad}).origin_chapter == 0

    @pytest.mark.parametrize("bad", ["很多", None, "3abc"])
    def test_bad_chapter_count_coerced_to_zero(self, bad):
        assert describe_branch("001", {"chapter_count": bad}).chapter_count == 0

    def test_numeric_strings_accepted(self):
        info = describe_branch("001", {"origin_chapter": "12", "chapter_count": "34"})
        assert (info.origin_chapter, info.chapter_count) == (12, 34)

    def test_missing_status_becomes_empty_string(self):
        assert describe_branch("001", {"title": "t"}).status == ""

    def test_result_is_frozen(self):
        info = describe_branch("001", {"title": "t"})
        with pytest.raises(Exception):
            info.title = "changed"  # type: ignore[misc]


class _FakeReader:
    """内存替身：不需要任何目录。"""

    def __init__(self, rows):
        self._rows = rows
        self.calls: list = []

    def list_branch_metas(self, parent_dir):
        self.calls.append(parent_dir)
        return self._rows


class TestListBranchesUseCase:
    def test_empty_reader_gives_empty_result(self):
        assert ListBranches(reader=_FakeReader([])).execute("/any") == []

    def test_prefix_stripped_from_directory_name(self):
        rows = ListBranches(reader=_FakeReader([("branch_007", {"title": "t"})])).execute("/any")
        assert rows[0].info.branch_id == "007"

    def test_unexpected_directory_name_kept_as_is(self):
        """不是 branch_ 前缀的目录名不硬切，避免切出空串。"""
        rows = ListBranches(reader=_FakeReader([("legacy_dir", {"title": "t"})])).execute("/any")
        assert rows[0].info.branch_id == "legacy_dir"

    def test_meta_preserved_for_legacy_generation_calc(self):
        meta = {"title": "t", "lineage": {"generation": 3}}
        rows = ListBranches(reader=_FakeReader([("branch_001", meta)])).execute("/any")
        assert rows[0].meta == meta

    def test_reader_receives_parent_dir(self):
        reader = _FakeReader([])
        ListBranches(reader=reader).execute("/some/novel")
        assert reader.calls == ["/some/novel"]

    def test_ordering_follows_reader(self):
        rows = ListBranches(reader=_FakeReader([("branch_000", {}), ("branch_001", {}), ("branch_002", {})])).execute(
            "/any"
        )
        assert [r.info.branch_id for r in rows] == ["000", "001", "002"]
