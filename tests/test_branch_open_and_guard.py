"""S6 续：分支的「可打开」与护栏、以及时间线面板的分支行。

三件事：
1. **打开走宿主入口**（`BasePanel.open_novel_dir` → 宿主 `_load_novel`），不自己拼流程；
2. **护栏仍然成立**：打开一个分支后，任何写入都只落在这个分支目录内 ——
   分支目录是**父代作品的子目录**，这是"子代只读父代"最容易破的地方；
3. 时间线面板的「世界线 / 分支」视图里，分支子项目是可双击打开的一行。
"""

import sys
from pathlib import Path

import pytest

from app import lineage as lin
from app.panels.timeline_panel import branch_rows

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


def hardcoded_fonts(path: Path) -> int:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "font":
            value = node.value
            if isinstance(value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in value.elts):
                count += 1
    return count


# ============================================================ 打开入口


class TestOpenNovelDir:
    def test_delegates_to_host_loader(self):
        """必须走宿主的 `_load_novel`（它会设目录、建 memory、广播 novel.opened）。"""
        from app.panels.base import BasePanel

        class Panel(BasePanel):
            key = "probe-open"

        calls = []

        class App:
            def _load_novel(self, path):
                calls.append(path)

        panel = Panel(App())
        assert panel.open_novel_dir("/tmp/some-branch") is True
        # `Path("/tmp/x")` 在 Windows 上会规范化成 `\tmp\x` —— 比路径对象而不是字符串
        assert len(calls) == 1
        assert Path(calls[0]) == Path("/tmp/some-branch")

    def test_without_host_loader_returns_false(self):
        from app.panels.base import BasePanel

        class Panel(BasePanel):
            key = "probe-open2"

        assert Panel(object()).open_novel_dir("/tmp/x") is False

    def test_loader_failure_is_contained(self):
        from app.panels.base import BasePanel

        class Panel(BasePanel):
            key = "probe-open3"

        class App:
            def _load_novel(self, path):
                raise OSError("目录不可读")

        assert Panel(App()).open_novel_dir("/tmp/x") is False

    def test_empty_dir_returns_false(self):
        from app.panels.base import BasePanel

        class Panel(BasePanel):
            key = "probe-open4"

        assert Panel(object()).open_novel_dir("") is False

    def test_panels_do_not_set_current_novel_dir_directly(self):
        """源码级：面板**不得**自己写 `current_novel_dir`（那会漏掉 memory/广播/刷新）。"""
        for rel in ("app/panels/timeline_panel.py", "app/panels/lineage_panel.py"):
            code = _scan.code_only(rel)
            assert "current_novel_dir =" not in code, f"{rel} 不应自己设置 current_novel_dir"


class TestBranchOpenKeepGuard:
    def test_writes_inside_branch_are_allowed(self, tmp_path):
        parent = tmp_path / "父代"
        parent.mkdir()
        (parent / "meta.json").write_text('{"title": "父代"}', encoding="utf-8")
        branch = parent / "timelines" / "branch_000"
        branch.mkdir(parents=True)
        (branch / "meta.json").write_text('{"title": "分支"}', encoding="utf-8")

        # 打开分支 = 把它当 child_dir；写入必须允许落在它内部
        assert lin.guard_child_path(branch, branch / "memory" / "characters.json")

    def test_writes_escaping_to_parent_are_refused(self, tmp_path):
        """**最关键的一条**：分支在父代目录**内部**，所以"写到父代"看起来像"写到上层" —— 必须拒绝。"""
        parent = tmp_path / "父代"
        parent.mkdir()
        branch = parent / "timelines" / "branch_000"
        branch.mkdir(parents=True)

        with pytest.raises(ValueError, match="护栏拒绝"):
            lin.guard_child_path(branch, parent / "memory" / "characters.json")

    def test_copy_into_branch_cannot_reach_parent(self, tmp_path):

        parent = tmp_path / "父代"
        parent.mkdir()
        branch = parent / "timelines" / "branch_000"
        branch.mkdir(parents=True)
        source = parent / "outline.json"
        source.write_text("[]", encoding="utf-8")

        with pytest.raises(ValueError):
            lin.copy_into_child(branch, source, "../../outline.json")

        assert source.exists()


# ============================================================ 时间线面板的分支行


class TestTimelineBranchRows:
    def test_branch_dir_becomes_openable_row(self):
        rows = branch_rows(
            [],
            [
                {
                    "dir": r"C:\n\父代\timelines\branch_000",
                    "branch_id": "000",
                    "title": "分支: 留下",
                    "origin_chapter": 5,
                    "status": "pending",
                    "chapter_count": 3,
                    "openable": True,
                }
            ],
        )
        iid, values = rows[0]
        assert iid.startswith("br")
        assert "分支" in values[0]
        assert values[1] == "第5章分叉"
        assert values[3] == "3 章"

    def test_unopenable_branch_is_marked(self):
        rows = branch_rows(
            [],
            [
                {
                    "dir": "d",
                    "title": "坏分支",
                    "origin_chapter": 0,
                    "status": "",
                    "chapter_count": 0,
                    "openable": False,
                }
            ],
        )
        assert "无法打开" in rows[0][1][2]

    def test_world_lines_still_listed_first(self):
        tree = [{"name": "主线", "file": "main.json", "branches": [{"chapter": 3, "decision": "去留"}]}]
        dirs = [{"dir": "d", "title": "分支 A", "origin_chapter": 1, "chapter_count": 2, "openable": True}]
        rows = branch_rows(tree, dirs)
        assert [iid for iid, _ in rows][:2] == ["wlmain.json", "wlmain.json#3"]
        assert rows[-1][0].startswith("br")

    def test_branch_rows_defaults_to_empty(self):
        rows = branch_rows([{"name": "主线", "file": "main.json", "branches": []}])
        assert len(rows) == 1

    def test_double_click_dispatches_by_prefix(self):
        code = _scan.code_only("app/panels/timeline_panel.py")
        assert 'iid.startswith("br")' in code
        assert "open_novel_dir" in code


# ============================================================ 面板约束


class TestPanelStillClean:
    @pytest.mark.parametrize(
        "rel",
        ["app/panels/timeline_panel.py", "app/panels/lineage_panel.py", "app/panels/base.py"],
    )
    def test_no_new_hardcoded_fonts(self, rel):
        """S5 的棘轮在改动后仍须成立（这轮又动了这两个面板）。"""
        assert hardcoded_fonts(Path(__file__).parent.parent / rel) == 0

    def test_tree_helpers_keep_rows_nested(self):
        """世代的树填充必须把分支挂成子节点，而不是平铺。"""
        from app.panels.lineage_panel import lineage_rows

        rows = lineage_rows(
            [
                {
                    "generation": 1,
                    "title": "父代",
                    "novel_dir": "p",
                    "is_current": True,
                    "readonly": False,
                    "missing": False,
                    "kind": "novel",
                    "branches": [
                        {"dir": "b", "branch_id": "000", "title": "分支", "origin_chapter": 2, "openable": True}
                    ],
                }
            ]
        )
        assert [iid for iid, _ in rows] == ["g0", "b0-0"]
