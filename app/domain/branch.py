"""分支子项目（世界线分支）的领域视图。

## 为什么把它从 `app/lineage.py` 里挪出来

旧实现 `discover_branches()` 把三件事焊在一个函数里：

1. **遍历目录**（`timelines/branch_%03d/`）—— 基础设施细节
2. **判断"这个分支能不能打开"** —— 领域规则
3. **拼装成给界面用的 dict**（12 个键，含绝对路径、`kind` 常量）—— 表现形态

后果是：想单独验证"缺 meta.json 的分支应判定为不可打开"这条规则，
必须先造一套目录；想换存储（比如将来把分支记进 SQLite），得重写整个函数。

拆开之后，本模块只剩第 2 件事：**给一个已解析的 meta，给出分支的领域判断**。
它不碰磁盘、不认识 `Path`、也不知道界面需要哪些键 —— 因此可以被穷举测试。

## 与旧接口的对应关系

| 旧 `discover_branches()` 的键 | 现在的来源 |
|---|---|
| `branch_id` | `BranchInfo.branch_id` |
| `title` / `origin_chapter` / `status` / `chapter_count` | 同名字段 |
| `openable` / `reason` | `BranchInfo.openable` / `.reason` |
| `dir` / `kind` / `generation` / `parent_novel` | **不属领域** —— 由调用方（兼容层）补 |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = ["BranchInfo", "describe_branch"]

#: 判定为"可打开"的失败原因（旧接口的 `reason` 字段用它，文案保持不变）
REASON_NO_META = "缺少可解析的 meta.json"


@dataclass(frozen=True)
class BranchInfo:
    """一条分支子项目的领域视图（不可变）。"""

    #: 分支编号：目录名 `branch_003` → `"003"`
    branch_id: str
    #: 展示标题（meta.title → meta.name → 目录名的回落顺序在 `describe_branch` 里完成）
    title: str
    #: 从父代第几章分叉
    origin_chapter: int
    #: meta 里的状态字段（原样透传，领域层不解释取值）
    status: str
    #: 章节数
    chapter_count: int
    #: 是否可被当作作品打开（= meta 可解析）
    openable: bool
    #: 不可打开的原因；可打开时为空串
    reason: str


def _as_int(value: Any, default: int = 0) -> int:
    """把 meta 里的值稳妥转成 int（旧实现对 None / 字符串抛过 TypeError 的同类问题）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def describe_branch(
    branch_id: str,
    meta: Mapping[str, Any] | None,
    *,
    fallback_title: str = "",
) -> BranchInfo:
    """由**已解析的 meta** 构造分支视图 —— 纯函数，不碰磁盘。

    `meta` 为空（缺文件 / 内容损坏）时返回 `openable=False` 且 `reason` 写明原因，
    而不是抛异常：分支目录可能是用户手工拷进来的，不该让"列分支"整个失败。
    """
    data: Mapping[str, Any] = meta if isinstance(meta, Mapping) else {}
    openable = bool(data)

    if not openable:
        return BranchInfo(
            branch_id=branch_id,
            title=fallback_title or branch_id,
            origin_chapter=0,
            status="",
            chapter_count=0,
            openable=False,
            reason=REASON_NO_META,
        )

    title = str(data.get("title") or data.get("name") or fallback_title or branch_id)
    return BranchInfo(
        branch_id=branch_id,
        title=title,
        origin_chapter=_as_int(data.get("origin_chapter", 0)),
        status=str(data.get("status") or ""),
        chapter_count=_as_int(data.get("chapter_count", 0)),
        openable=True,
        reason="",
    )
