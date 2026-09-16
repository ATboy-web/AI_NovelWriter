"""S6：分支子项目「可打开」+ 进代际树。

背景：`timelines/branch_%03d/` 由 `timeline_ui` 建出来（含完整目录树），
**全仓没有任何读取方** —— 写了却看不见、也打不开。本文件锁住三件事：

1. **写入侧**：新建分支时 `meta.json` 必须带 `title` 与 `lineage`
   （前者决定它能否被当作品打开后显示标题，后者决定它能否进代际树）；
2. **语义**：分支与父代**同一代**（它是另一条世界线，不是下一代），
   但 `child_scope=readonly_parent` **仍然成立**（分支也不能改父代数据）；
3. **发现与打开**：代际树把分支挂在所属作品下、标记当前项，
   并且"打开分支"走宿主既有入口而不是自己拼流程。
"""

import json
import sys
from pathlib import Path

from app import lineage as lin

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


def make_parent(tmp_path: Path, title: str = "父代作品") -> Path:
    parent = tmp_path / "父代作品"
    parent.mkdir(parents=True, exist_ok=True)
    (parent / "meta.json").write_text(json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8")
    return parent


def make_branch(parent: Path, branch_id: str = "000", **meta_extra) -> Path:
    """造一个分支子项目（形状与 `timeline_ui._generate_branch_story` 一致）。"""
    branch = parent / "timelines" / f"branch_{branch_id}"
    (branch / "chapters").mkdir(parents=True, exist_ok=True)
    (branch / "memory").mkdir(parents=True, exist_ok=True)
    title = meta_extra.pop("title", f"分支: 另一条路 {branch_id}")
    meta = {
        "title": title,
        "name": title,
        "origin_chapter": meta_extra.pop("origin_chapter", 5),
        "status": meta_extra.pop("status", "pending"),
        "chapter_count": meta_extra.pop("chapter_count", 3),
        "lineage": lin.branch_lineage_record(parent, branch_id, 5, title).as_dict(),
    }
    meta.update(meta_extra)
    (branch / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return branch


# ============================================================ 写入侧


class TestBranchMetaPayload:
    def test_branch_record_is_same_generation_and_still_readonly_parent(self, tmp_path):
        """分支是**同一代**的另一条世界线，但对父代依然只读。"""
        parent = make_parent(tmp_path)
        record = lin.branch_lineage_record(parent, "002", origin_chapter=9, title="分支: 留下")

        assert record.is_branch is True
        assert record.kind == lin.KIND_BRANCH
        assert record.branch_id == "002"
        assert record.origin_chapter == 9
        # 父代没有 lineage → 父代是第 1 代 → 分支也是第 1 代（**不是第 2 代**）
        assert record.generation == 1
        assert record.child_scope == lin.SCOPE_READONLY_PARENT

    def test_branch_of_a_generation_two_work_stays_generation_two(self, tmp_path):
        parent = make_parent(tmp_path)
        child = tmp_path / "第二代"
        child.mkdir()
        (child / "meta.json").write_text(
            json.dumps(
                {"title": "第二代", "lineage": {"generation": 2, "parent_novel": str(parent)}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        record = lin.branch_lineage_record(child, "000", 3, "分支")

        assert record.generation == 2, "分支与父代同代"

    def test_record_round_trips_through_meta(self, tmp_path):
        parent = make_parent(tmp_path)
        branch = make_branch(parent, "001")
        record = lin.read_lineage(branch)

        assert record is not None
        assert record.kind == lin.KIND_BRANCH
        assert record.branch_id == "001"
        assert record.origin_chapter == 5
        assert record.parent_novel == str(parent)

    def test_unknown_kind_falls_back_to_novel(self):
        """手改 meta 写错 kind 时按普通作品处理，不抛错。"""
        record = lin.LineageRecord.from_meta({"lineage": {"kind": "乱写"}})
        assert record.kind == lin.KIND_NOVEL
        assert record.is_branch is False

    def test_timeline_ui_writes_title_and_lineage(self):
        """源码级：分支创建处必须写 `title` 与 `lineage`（否则打不开/进不了树）。"""
        code = _scan.code_only("app/timeline_ui.py")
        assert "branch_lineage_record" in code
        assert '"title": branch_title' in code
        assert '"lineage":' in code


# ============================================================ 发现


class TestDiscoverBranches:
    def test_lists_branches_with_metadata(self, tmp_path):
        parent = make_parent(tmp_path)
        make_branch(parent, "000", title="分支: 留下", chapter_count=7)

        found = lin.discover_branches(parent)

        assert len(found) == 1
        assert found[0]["branch_id"] == "000"
        assert found[0]["title"] == "分支: 留下"
        assert found[0]["origin_chapter"] == 5
        assert found[0]["chapter_count"] == 7
        assert found[0]["kind"] == lin.KIND_BRANCH
        assert found[0]["openable"] is True

    def test_sorted_by_branch_id(self, tmp_path):
        parent = make_parent(tmp_path)
        for branch_id in ("002", "000", "001"):
            make_branch(parent, branch_id)
        assert [b["branch_id"] for b in lin.discover_branches(parent)] == ["000", "001", "002"]

    def test_branch_without_meta_is_not_openable(self, tmp_path):
        parent = make_parent(tmp_path)
        broken = parent / "timelines" / "branch_003"
        broken.mkdir(parents=True)

        found = lin.discover_branches(parent)

        assert found[0]["openable"] is False
        assert found[0]["reason"], "必须给出不可打开的原因（面板要显示它）"

    def test_corrupt_meta_is_not_openable(self, tmp_path):
        parent = make_parent(tmp_path)
        branch = parent / "timelines" / "branch_004"
        branch.mkdir(parents=True)
        (branch / "meta.json").write_text("{坏", encoding="utf-8")

        assert lin.discover_branches(parent)[0]["openable"] is False

    def test_non_branch_dirs_ignored(self, tmp_path):
        parent = make_parent(tmp_path)
        (parent / "timelines" / "something_else").mkdir(parents=True)
        assert lin.discover_branches(parent) == []

    def test_no_timelines_dir(self, tmp_path):
        parent = make_parent(tmp_path)
        assert lin.discover_branches(parent) == []
        assert lin.discover_branches(None) == []


# ============================================================ 代际树


class TestBranchInGenerationTree:
    def test_branches_attached_to_their_owner(self, tmp_path):
        parent = make_parent(tmp_path)
        make_branch(parent, "000")
        make_branch(parent, "001")

        tree = lin.generation_tree(parent)

        assert len(tree) == 1
        assert [b["branch_id"] for b in tree[0]["branches"]] == ["000", "001"]

    def test_include_branches_can_be_disabled(self, tmp_path):
        parent = make_parent(tmp_path)
        make_branch(parent, "000")
        assert lin.generation_tree(parent, include_branches=False)[0]["branches"] == []

    def test_branch_of_parent_is_reachable_from_child(self, tmp_path):
        """从第二代往下看，也要能看到第一代的分支子项目。"""
        parent = make_parent(tmp_path)
        make_branch(parent, "000")
        child = tmp_path / "第二代"
        child.mkdir()
        (child / "meta.json").write_text(
            json.dumps({"title": "第二代", "lineage": {"generation": 2, "parent_novel": str(parent)}}),
            encoding="utf-8",
        )

        tree = lin.generation_tree(child)

        assert [row["title"] for row in tree] == ["第二代", "父代作品"]
        assert len(tree[1]["branches"]) == 1, "第一代的分支应挂在第一代那一行"

    def test_opening_from_a_branch_marks_it_current(self, tmp_path):
        """从分支里打开时：第 0 行是分支，且它的 kind 为 branch。"""
        parent = make_parent(tmp_path)
        branch = make_branch(parent, "000")

        tree = lin.generation_tree(branch)

        assert tree[0]["kind"] == lin.KIND_BRANCH
        assert tree[0]["is_current"] is True
        assert tree[1]["title"] == "父代作品"
        assert tree[1]["readonly"] is True
        # 同一个分支在父代行的 branches 里也要被标成"当前"，否则看起来像两个东西
        assert tree[1]["branches"][0]["is_current"] is True

    def test_panel_rows_put_branch_under_its_owner(self, tmp_path):
        """面板层的行构造：作品一行 + 分支一行（`b{父行号}-{分支序号}`）。"""
        from app.panels.lineage_panel import lineage_rows

        parent = make_parent(tmp_path)
        make_branch(parent, "000")

        rows = lineage_rows(lin.generation_tree(parent))

        assert [iid for iid, _ in rows] == ["g0", "b0-0"]
        assert rows[1][1][1].startswith("　↳ 分支 000")
        assert "分叉" in rows[1][1][2]

    def test_panel_rows_mark_unopenable_branch(self, tmp_path):
        from app.panels.lineage_panel import lineage_rows

        parent = make_parent(tmp_path)
        (parent / "timelines" / "branch_009").mkdir(parents=True)

        rows = lineage_rows(lin.generation_tree(parent))

        assert "无法打开" in rows[1][1][2]
        assert rows[1][1][4] == "缺少 meta"

    def test_panel_rows_mark_current_branch(self, tmp_path):
        from app.panels.lineage_panel import lineage_rows

        parent = make_parent(tmp_path)
        branch = make_branch(parent, "000")

        rows = lineage_rows(lin.generation_tree(branch))

        assert "分支（同代）" in rows[0][1][2] or "当前作品（分支）" in rows[0][1][2]
