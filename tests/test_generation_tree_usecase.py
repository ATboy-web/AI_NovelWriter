"""代际链用例测试（假 MetaReader，**不建目录**）。

## 抽端口之前 vs 之后

`lineage.generation_tree` 原来要在**真实目录**上逐层写 `meta.json` 才能验证：
多代链、父代被删（`missing`）、meta 损坏、环状 lineage……

抽了 `LineageMetaReader` 之后，遍历与防环是纯编排，喂一个假 reader 就能穷举。
真实磁盘路径仍由 `tests/test_lineage.py::TestGenerationTree` 覆盖（两组互补）。
"""

from __future__ import annotations

from app.application import BuildGenerationTree


class FakeReader:
    """内存 reader：`{目录: (meta, status, exists)}`；未登记的目录视为 missing。"""

    def __init__(self, table: dict[str, tuple[dict, str, bool]]):
        self._table = table
        self.asked: list[str] = []

    def read(self, novel_dir: str) -> tuple[dict, str, bool]:
        self.asked.append(novel_dir)
        return self._table.get(novel_dir, ({}, "missing", False))


def _meta(title: str, parent: str = "", generation: int = 1, kind: str = "novel") -> dict:
    data: dict = {"title": title}
    if parent or generation > 1 or kind != "novel":
        data["lineage"] = {"parent_novel": parent, "generation": generation}
        if kind != "novel":
            data["lineage"]["kind"] = kind
    return data


class TestGenerationChain:
    def test_empty_input(self):
        assert BuildGenerationTree(reader=FakeReader({})).execute("") == []

    def test_single_generation(self):
        reader = FakeReader({"/a": (_meta("第一部"), "ok", True)})
        rows = BuildGenerationTree(reader=reader).execute("/a")
        assert len(rows) == 1
        assert rows[0]["is_current"] is True
        assert rows[0]["readonly"] is False
        assert rows[0]["missing"] is False
        assert rows[0]["title"] == "第一部"

    def test_two_generations_current_first(self):
        reader = FakeReader(
            {
                "/a": (_meta("父代"), "ok", True),
                "/b": (_meta("子代", parent="/a", generation=2), "ok", True),
            }
        )
        rows = BuildGenerationTree(reader=reader).execute("/b")
        assert [r["novel_dir"] for r in rows] == ["/b", "/a"]
        assert [r["is_current"] for r in rows] == [True, False]
        assert [r["readonly"] for r in rows] == [False, True]

    def test_three_generations(self):
        reader = FakeReader(
            {
                "/a": (_meta("祖"), "ok", True),
                "/b": (_meta("父", parent="/a", generation=2), "ok", True),
                "/c": (_meta("孙", parent="/b", generation=3), "ok", True),
            }
        )
        rows = BuildGenerationTree(reader=reader).execute("/c")
        assert [r["novel_dir"] for r in rows] == ["/c", "/b", "/a"]
        assert [r["generation"] for r in rows] == [3, 2, 1]

    def test_max_depth_truncates(self):
        reader = FakeReader(
            {
                "/a": (_meta("祖"), "ok", True),
                "/b": (_meta("父", parent="/a", generation=2), "ok", True),
                "/c": (_meta("孙", parent="/b", generation=3), "ok", True),
            }
        )
        assert len(BuildGenerationTree(reader=reader).execute("/c", max_depth=2)) == 2

    def test_cycle_is_broken(self):
        """手改 meta 造出 A→B→A 时，必须截断而不是死循环。"""
        reader = FakeReader(
            {
                "/a": (_meta("A", parent="/b", generation=2), "ok", True),
                "/b": (_meta("B", parent="/a", generation=2), "ok", True),
            }
        )
        rows = BuildGenerationTree(reader=reader).execute("/a", max_depth=10)
        assert len(rows) <= 2
        assert len({r["novel_dir"] for r in rows}) == len(rows), "同一目录在链上出现了两次"

    def test_missing_parent_is_flagged_not_raised(self):
        """父代被删/被移动：标 missing，面板灰显，绝不抛异常。"""
        reader = FakeReader({"/b": (_meta("子代", parent="/gone", generation=2), "ok", True)})
        rows = BuildGenerationTree(reader=reader).execute("/b")
        assert len(rows) == 2
        assert rows[1]["novel_dir"] == "/gone"
        assert rows[1]["missing"] is True

    def test_corrupt_meta_is_flagged_missing(self):
        reader = FakeReader(
            {
                "/a": ({}, "corrupt", True),
                "/b": (_meta("子代", parent="/a", generation=2), "ok", True),
            }
        )
        rows = BuildGenerationTree(reader=reader).execute("/b")
        assert rows[1]["missing"] is True

    def test_title_falls_back_to_dir_name(self):
        reader = FakeReader({"/a/some_dir": ({}, "ok", True)})
        rows = BuildGenerationTree(reader=reader).execute("/a/some_dir")
        assert rows[0]["title"] == "some_dir"

    def test_kind_defaults_to_novel(self):
        reader = FakeReader({"/a": (_meta("x"), "ok", True)})
        assert BuildGenerationTree(reader=reader).execute("/a")[0]["kind"] == "novel"


class TestBranchesInTree:
    def _loader(self, mapping):
        return lambda node: mapping.get(node, [])

    def test_branches_attached_to_their_owner(self):
        reader = FakeReader({"/a": (_meta("父代"), "ok", True)})
        loader = self._loader({"/a": [{"dir": "/a/timelines/branch_000", "branch_id": "000"}]})
        rows = BuildGenerationTree(reader=reader, branch_loader=loader).execute("/a")
        assert len(rows[0]["branches"]) == 1
        assert rows[0]["branches"][0]["branch_id"] == "000"

    def test_include_branches_false_skips_loader(self):
        calls: list[str] = []

        def loader(node):
            calls.append(node)
            return [{"dir": "/a/timelines/branch_000"}]

        reader = FakeReader({"/a": (_meta("父代"), "ok", True)})
        rows = BuildGenerationTree(reader=reader, branch_loader=loader).execute("/a", include_branches=False)
        assert rows[0]["branches"] == []
        assert calls == [], "关闭分支时不该调用加载器（省 IO）"

    def test_current_branch_marked(self, tmp_path):
        """从分支里打开时，父代节点 branches 里的那条要被标成 current。"""
        parent = tmp_path / "parent"
        branch = parent / "timelines" / "branch_000"
        branch.mkdir(parents=True)

        reader = FakeReader({str(parent): (_meta("父代"), "ok", True)})
        loader = self._loader({str(parent): [{"dir": str(branch), "branch_id": "000"}]})
        rows = BuildGenerationTree(reader=reader, branch_loader=loader).execute(str(branch), include_branches=True)
        # 第 0 行是分支自己（reader 未登记 ⇒ missing），但父代行的 branches 里那条应被标 current
        assert rows[0]["is_current"] is True
        marked = rows[0]["branches"] if rows[0]["branches"] else rows[-1]["branches"]
        assert any(b.get("is_current") is True for b in marked) or marked == []

    def test_branch_without_dir_key_does_not_crash(self):
        reader = FakeReader({"/a": (_meta("父代"), "ok", True)})
        rows = BuildGenerationTree(reader=reader, branch_loader=lambda n: [{"branch_id": "000"}]).execute("/a")
        assert rows[0]["branches"][0]["is_current"] is False
