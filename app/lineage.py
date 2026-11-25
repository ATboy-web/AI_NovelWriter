"""世代传承（v3 §2.4 ③）—— 数据与护栏层。

## 现状缺口（勘察确认）

`lifecycle_ui._create_sequel` 建第二部目录时**只复制两样东西**：
`memory/settings.json` 与 `characters/` 整个目录。不继承 `outline.json`、
`timelines/`、`memory/`（摘要/弧线/卷）与伏笔线索；`original_novel` 只被写进
`meta.json` 而**不参与任何逻辑**；也没有"第几代"的层级模型。

结果是"续写第二代"实际退化成"新建一本带同样角色的书"：读者看不到前代史，
作者要自己把大纲和伏笔再抄一遍。

## 🚨 本模块的第一职责是护栏，不是搬运

子代读父代的数据、又要写自己的目录 —— 这是整个 v3 改造里**数据风险最高**的一处：
一次路径拼接错误就会把父代的书改掉（父代往往已经写完、甚至已发布）。

因此本模块**所有**写操作都必须经过 `guard_child_path(child_dir, target)`：
它把目标解析成绝对路径，并要求它**落在子代目录之内**，否则抛 `ValueError`。
`child_scope = "readonly_parent"` 是记录在 `meta.lineage` 里的契约值，
配套测试把它固化为断言（见 `tests/test_lineage.py`）。

## 纯逻辑，无 GUI 无网络

所有函数只吃路径与字典、只吐字典，便于单测把"年龄推进""死亡转状态""继承清单"
这些规则逐条钉住。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

# 分层样板（2026-11-25）：discover_branches 委托给这三层。
# 见 `app/domain/branch.py` 顶部说明为什么值得拆。
from app.adapters import FileBranchMetaReader, FilesystemProbe, NeverExistsProbe
from app.application import ListBranches

# 纯领域部分已搬到 `app/domain/lineage.py`（2026-11-25 分层迁移第二步）。
# 这里**原样 re-export**：`from app.lineage import LineageRecord / is_within / ...`
# 等既有写法全部保持可用；IO 相关函数仍在本模块。
from app.domain.lineage import (  # noqa: F401 - 对外接口的一部分
    BRANCH_PARENT_REL,
    BRANCH_PREFIX,
    DEFAULT_INHERITED,
    DIMENSION_SOURCES,
    INHERIT_DIMENSIONS,
    KIND_BRANCH,
    KIND_NOVEL,
    LINEAGE_KEY,
    SCOPE_READONLY_PARENT,
    InheritancePlan,
    LineageRecord,
    _as_int,
    apply_age_progression,
    apply_death_status,
    build_inheritance_plan,  # 继承计划：纯规则在 domain
    dedupe_preserve_order,
    describe_plan_items,
    extract_unresolved_plots,
    is_within,
    make_character_transform,
    unresolved_plot_keywords,
)
from app.storage import atomic_write_text, read_json_with_backup

#: 从文件名/字符串里提取全部数字段（`chapter_0001` → ["0001"]）
_DIGITS_RE = re.compile(r"\d+")

__all__ = [
    "LINEAGE_KEY",
    "SCOPE_READONLY_PARENT",
    "KIND_NOVEL",
    "KIND_BRANCH",
    "BRANCH_PREFIX",
    "INHERIT_DIMENSIONS",
    "DIMENSION_SOURCES",
    "DEFAULT_INHERITED",
    "LineageRecord",
    "InheritancePlan",
    "read_lineage",
    "read_meta",
    "branches_dir",
    "discover_branches",
    "branch_lineage_record",
    "build_lineage_record",
    "generation_tree",
    "plan_inheritance",
    "apply_age_progression",
    "apply_death_status",
    "extract_unresolved_plots",
    "unresolved_plot_keywords",
    "inherited_plot_report",
    "describe_plan_items",
    "parent_last_chapter",
    "make_character_transform",
    "inherit_into_child",
    "dedupe_preserve_order",
    "is_within",
    "guard_child_path",
    "copy_into_child",
]


# ====================================================================== 代际记录


def read_lineage(novel_dir: Any) -> LineageRecord | None:
    """读某本小说的代际记录；无 `lineage` 或文件损坏时返回 `None`。"""
    if not novel_dir:
        return None
    meta, status = read_json_with_backup(Path(novel_dir) / "meta.json", default=None)
    if status == "corrupt":
        logger.warning(f"[lineage] meta.json 损坏，按无代际信息处理: {novel_dir}")
        return None
    return LineageRecord.from_meta(meta)


def read_meta(novel_dir: Any) -> dict:
    """读一个作品/分支目录的 `meta.json`（缺失或损坏返回空字典）。"""
    if not novel_dir:
        return {}
    data, status = read_json_with_backup(Path(novel_dir) / "meta.json", default=None)
    if status == "corrupt" or not isinstance(data, Mapping):
        return {}
    return dict(data)


def branches_dir(parent_dir: Any) -> Path | None:
    """分支子项目的所在目录：`<父代>/timelines/`。"""
    if not parent_dir:
        return None
    return Path(parent_dir) / BRANCH_PARENT_REL


def discover_branches(parent_dir: Any) -> list[dict]:
    """列出一个作品的**分支子项目**（`timelines/branch_%03d/`）。

    每个分支本身就是一份可被当作品打开的数据（`meta.json` + `chapters/` + `memory/`），
    因此这里同时给出 `openable`：只有 `meta.json` 可解析才算能打开
    （`_load_novel` 的第一道校验就是它）。

    ⚠️ 背景：这些目录原本是**只写不读**的（`timeline_ui` 建出来就再没人碰）。
    本函数与 `generation_tree(include_branches=True)` 一起把它们接进代际树。

    ## 分层说明（2026-11-25，架构样板）

    本函数现在只是**兼容转发**，实现拆到三层：

    - `adapters.FileBranchMetaReader` —— 遍历 `timelines/branch_*` 并读 meta
    - `application.ListBranches` —— 用例编排
    - `domain.describe_branch` —— 「能不能打开」的判定规则（纯函数）

    **返回值与字段逐字未变**：`dir` / `branch_id` / `title` / `origin_chapter` /
    `status` / `chapter_count` / `openable` / `reason` / `kind` / `generation` /
    `parent_novel` 全部保持原样，排序（按目录名升序）也一致。

    ## 一处刻意的行为改进

    旧实现在 `origin_chapter` / `chapter_count` 上直接 `int(...)`：
    meta 里若是 `"第5章"` 这类非数字串，会抛 `ValueError` 让**整个列表**失败。
    现在由 `domain._as_int` 容错为 0 —— 异常数据只影响那一条，
    正常数据下取值完全相同。
    """
    base = branches_dir(parent_dir)
    if base is None or not base.is_dir():
        return []

    use_case = ListBranches(reader=FileBranchMetaReader())
    out: list[dict] = []
    for row in use_case.execute(parent_dir):
        info = row.info
        record = LineageRecord.from_meta(row.meta)
        out.append(
            {
                "dir": str(base / row.dir_name),
                "branch_id": info.branch_id,
                "title": info.title,
                "origin_chapter": info.origin_chapter,
                "status": info.status,
                "chapter_count": info.chapter_count,
                "openable": info.openable,
                "reason": info.reason,
                "kind": KIND_BRANCH,
                "generation": record.generation if record else 1,
                "parent_novel": str(parent_dir),
            }
        )
    return out


def build_lineage_record(
    parent_dir: Any,
    generation: int | None = None,
    era_gap_years: int = 0,
    inherited: Mapping[str, bool] | None = None,
) -> LineageRecord:
    """按父代目录构造一条代际记录（`generation` 不传则自动 = 父代 + 1）。"""
    parent_path = Path(parent_dir) if parent_dir else None
    parent_record = read_lineage(parent_path) if parent_path else None
    parent_title = ""
    if parent_path:
        meta, _status = read_json_with_backup(parent_path / "meta.json", default=None)
        if isinstance(meta, Mapping):
            parent_title = str(meta.get("title") or meta.get("original_title") or "")

    if generation is None:
        generation = (parent_record.generation + 1) if parent_record else 2

    merged = dict(DEFAULT_INHERITED)
    if inherited:
        for key in INHERIT_DIMENSIONS:
            if key in inherited:
                merged[key] = bool(inherited[key])

    return LineageRecord(
        generation=max(int(generation), 1),
        parent_novel=str(parent_path) if parent_path else "",
        parent_title=parent_title,
        era_gap_years=int(era_gap_years or 0),
        inherited=merged,
        child_scope=SCOPE_READONLY_PARENT,
    )


def generation_tree(novel_dir: Any, max_depth: int = 8, include_branches: bool = True) -> list[dict]:
    """沿 `parent_novel` 向上回溯，返回**从最新一代往前**的代际链（含自身）。

    每一行 `{generation, novel_dir, title, is_current, readonly, missing, kind, branches}`。
    `missing=True` 表示父代目录已不存在（被移动/删除）—— 面板应灰显而不是崩。
    `readonly` 对除自身以外的所有祖先恒为 True（子代只读父代）。

    `include_branches=True` 时，每个节点会带上自己的分支子项目（`row["branches"]`）——
    分支是**同一代的另一条世界线**，不是"下一代"，所以它挂在所属作品的下面，
    而不是作为代际链上的一环。
    """
    rows: list[dict] = []
    current = Path(novel_dir) if novel_dir else None
    if current is None:
        return rows

    seen: set[str] = set()
    node: Path | None = current
    for depth in range(max_depth):
        if node is None:
            break
        key = str(node)
        if key in seen:  # 环状 lineage 保护（手改 meta 可能造成）
            logger.warning(f"[lineage] 代际链出现环，已截断: {key}")
            break
        seen.add(key)

        exists = node.exists()
        meta, status = read_json_with_backup(node / "meta.json", default=None)
        meta = meta if isinstance(meta, Mapping) else {}
        record = LineageRecord.from_meta(meta)
        rows.append(
            {
                "generation": record.generation if record else 1,
                "novel_dir": key,
                "title": str(meta.get("title") or node.name),
                "is_current": depth == 0,
                "readonly": depth > 0,
                "missing": not exists or status == "corrupt",
                # 当前节点本身可能就是一个分支（从分支里打开时）
                "kind": record.kind if record else KIND_NOVEL,
                "branches": discover_branches(node) if include_branches else [],
            }
        )
        node = Path(record.parent_novel) if (record and record.parent_novel) else None

    if include_branches and rows:
        # 标记"这一行就是当前打开的作品"：从分支里打开时，该分支会同时出现在
        # 自己的第 0 行与父代节点的 branches 里，标出来才不至于让人以为是两个东西。
        current = str(Path(novel_dir).resolve())
        for row in rows:
            for branch in row.get("branches") or []:
                try:
                    branch["is_current"] = str(Path(branch["dir"]).resolve()) == current
                except OSError:
                    branch["is_current"] = False
    return rows


def branch_lineage_record(parent_dir: Any, branch_id: str, origin_chapter: int = 0, title: str = "") -> LineageRecord:
    """为**新建的分支**构造它的代际记录（供 `timeline_ui` 写进分支的 `meta.json`）。

    关键点：分支与父代**同一代**（`generation` 不变）—— 它是另一条世界线，不是下一代。
    同时保留 `child_scope=readonly_parent`：分支也不能改父代的数据。
    """
    parent_path = Path(parent_dir) if parent_dir else None
    parent_record = read_lineage(parent_path) if parent_path else None
    parent_meta = read_meta(parent_path) if parent_path else {}
    return LineageRecord(
        generation=(parent_record.generation if parent_record else 1),
        parent_novel=str(parent_path) if parent_path else "",
        parent_title=str(parent_meta.get("title") or (parent_path.name if parent_path else "")),
        era_gap_years=0,
        inherited=dict(DEFAULT_INHERITED),
        child_scope=SCOPE_READONLY_PARENT,
        kind=KIND_BRANCH,
        branch_id=str(branch_id),
        origin_chapter=int(origin_chapter or 0),
    )


# ====================================================================== 护栏


def guard_child_path(child_dir: Any, target: Any) -> Path:
    """🚨 **子代写操作的唯一入口**：目标必须落在子代目录之内，否则拒绝。

    这是「子代不得污染父代」护栏的强制点。任何要往子代拷文件/写 JSON 的代码
    都必须先过这一关 —— 而不是各自拼接路径（拼接错了没有第二次机会，
    父代可能已经发布）。

    Raises:
        ValueError: `child_dir` 为空、或 `target` 不在 `child_dir` 之内。
    """
    if not child_dir:
        raise ValueError("子代目录为空，拒绝写入")
    child_p = Path(child_dir).resolve()
    if not is_within(child_p, target):
        raise ValueError(f"护栏拒绝：目标 {target!r} 不在子代目录 {child_p} 之内（子代只读父代，禁止越界写入）")
    return Path(target)


def copy_into_child(child_dir: Any, source: Any, relative: str | None = None) -> Path | None:
    """把父代的文件/目录复制进子代。**每一步都过护栏**。

    `relative` 不传时用 `source` 相对 `child_dir` 的路径（即保持同名同位置）；
    调用方要改名就显式传 `relative`。

    Returns:
        子代侧的最终路径；源不存在时返回 `None`（不抛错 —— 缺某类历史数据是正常的）。
    """
    src = Path(source)
    if not src.exists():
        return None

    rel = relative if relative is not None else src.name
    dst = guard_child_path(child_dir, Path(child_dir) / rel)

    if src.is_dir():
        # dirs_exist_ok：子代可能已经有 characters/（续集流程先建过），
        # 合并而不是抛 FileExistsError。
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return dst


# ====================================================================== 继承计划


def plan_inheritance(parent_dir: Any, inherited: Mapping[str, bool] | None = None) -> InheritancePlan:
    """算出"勾选的维度各要拷哪些路径、哪些不存在"。**不复制任何文件**。

    先算后做，是为了让面板能在用户点"创建"之前就把"父代缺大纲/缺时间线"
    如实说出来 —— 续集最常见的失望就是"以为继承了其实没有"。

    ## 分层说明（2026-11-25）

    判定规则在 `domain.build_inheritance_plan`（纯函数，存在性由 `PathProbe` 提供）。
    本函数只做两件事：把父代目录包成 `FilesystemProbe`、转调。
    **签名与返回值不变** —— 面板与既有测试无需改动。
    """
    parent_p = Path(parent_dir) if parent_dir else None
    probe = FilesystemProbe(parent_p) if parent_p is not None else NeverExistsProbe()
    return build_inheritance_plan(str(parent_p) if parent_p else "", inherited, probe)


# ====================================================================== 代际数据换算


# ====================================================================== 伏笔


def inherited_plot_report(parent_dir: Any, limit: int = 8) -> str:
    """把父代未回收伏笔整理成一份 Markdown 待办（供写入子代）。"""
    if not parent_dir:
        return ""
    path = Path(parent_dir) / "memory" / "global_summary.txt"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"[lineage] 读取父代全局摘要失败（已跳过伏笔继承）: {e}")
        return ""
    items = extract_unresolved_plots(text, limit=limit)
    if not items:
        return ""
    lines = ["# 前代未回收伏笔（自父代全局摘要抽取，供续集处理）", ""]
    lines.extend(f"- [ ] {item}" for item in items)
    return "\n".join(lines) + "\n"


# ====================================================================== 执行继承


def parent_last_chapter(parent_dir: Any) -> int:
    """父代的"最后一章"章号：优先 `meta.chapter_count`，否则数 `chapters/` 下的文件。

    用于判断"哪些角色在父代范围内已经死亡"（见 `apply_death_status`）。
    """
    if not parent_dir:
        return 0
    root = Path(parent_dir)
    meta, status = read_json_with_backup(root / "meta.json", default=None)
    if status != "corrupt" and isinstance(meta, Mapping):
        for key in ("chapter_count", "total_chapters"):
            value = _as_int(meta.get(key))
            if value:
                return value
    chapters_dir = root / "chapters"
    if not chapters_dir.exists():
        return 0
    numbers = []
    for path in chapters_dir.glob("*.txt"):
        # 章节文件命名是 `chapter_0001.txt`：取**最后一段**数字，
        # 不能取第一段（`chapter` 后面才是章号）。
        found = _DIGITS_RE.findall(path.stem)
        if found:
            numbers.append(int(found[-1]))
    return max(numbers) if numbers else 0


def inherit_into_child(
    child_dir: Any,
    parent_dir: Any,
    inherited: Mapping[str, bool] | None = None,
    plots_filename: str = "inherited_plots.md",
) -> dict:
    """按继承计划把父代数据搬进子代。**每一次写入都过 `guard_child_path`**。

    角色年龄/状态**不在这里改**：那必须走 `MemoryManager.mutate_characters`
    （见 `make_character_transform`）。本函数只做文件复制与伏笔清单落盘。

    Returns:
        `{copied: [...], missing: [...], plots_file: str|None, plan: InheritancePlan}`
    """
    if not child_dir or not parent_dir:
        return {"copied": [], "missing": [], "plots_file": None, "plan": None}

    plan = plan_inheritance(parent_dir, inherited)
    parent_p = Path(parent_dir)
    copied: list[str] = []
    missing: list[str] = []

    for dim in INHERIT_DIMENSIONS:
        entry = plan.items.get(dim) or {}
        if entry.get("skipped"):
            continue
        for rel in DIMENSION_SOURCES[dim]:
            if rel not in (entry.get("copy") or []):
                missing.append(rel)
                continue
            try:
                dst = copy_into_child(child_dir, parent_p / rel, rel)
            except (OSError, ValueError) as e:
                # 护栏拒绝或磁盘错误：如实记录，绝不"绕过护栏再试一次"
                logger.error(f"[lineage] 继承 {rel} 失败: {type(e).__name__}: {e}")
                missing.append(rel)
                continue
            if dst is not None:
                copied.append(rel)

    plots_file: str | None = None
    if plan.inherited.get("plots"):
        report = inherited_plot_report(parent_dir)
        if report:
            target = Path(child_dir) / plots_filename
            try:
                guard_child_path(child_dir, target)
                atomic_write_text(target, report)
                plots_file = plots_filename
            except (OSError, ValueError) as e:
                logger.error(f"[lineage] 写入伏笔清单失败: {type(e).__name__}: {e}")

    # 去重但保序（`memory` 与 `plots` 都会带上 `memory/global_summary.txt`）
    return {
        "copied": dedupe_preserve_order(copied),
        "missing": dedupe_preserve_order(missing),
        "plots_file": plots_file,
        "plan": plan,
    }
