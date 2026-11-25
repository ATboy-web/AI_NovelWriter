"""端口层：业务代码依赖的**接口**，而不是具体实现。

## 为什么需要它

应用层要"列出某作品的所有分支"，它需要的只是"给我每个分支目录的 meta"——
至于 meta 来自文件、SQLite 还是远端，应用层不该知道。把这条需求写成 `Protocol`，
换实现时应用层一行不用改，测试时也不必造目录。

## 约定

- 端口只描述**能力**，不描述实现细节（不出现 `Path` 以外的文件系统概念也可以，
  但保留 `Any` 以便适配器自由决定接收路径还是 ID）。
- 端口不 import 适配器（反过来才对）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["BranchMetaReader", "LineageMetaReader", "PathProbe"]


@runtime_checkable
class BranchMetaReader(Protocol):
    """读取分支子项目的元数据。"""

    def list_branch_metas(self, parent_dir: Any) -> list[tuple[str, dict]]:
        """返回 `[(分支目录名, meta 字典)]`，按目录名升序。

        约定：
        - 目录不存在 ⇒ 返回空列表（不是异常）；
        - 某个分支的 meta 缺失或损坏 ⇒ 该条目的字典为 `{}`（由领域层判定不可打开）；
        - 不改动任何文件。
        """
        ...


@runtime_checkable
class PathProbe(Protocol):
    """判断「父代里的某个相对路径是否存在」。

    这个端口存在，是为了把**继承计划**里的唯一一处磁盘操作抽出来：
    `domain.build_inheritance_plan` 需要知道"父代有没有 outline.json"，
    但它不该自己去碰文件系统 —— 否则那条规则只能在"造一套目录"的条件下测。
    """

    def exists(self, relative_path: str) -> bool:
        """`relative_path` 是相对父代根目录的路径（如 `memory/settings.json`）。"""
        ...


@runtime_checkable
class LineageMetaReader(Protocol):
    """读取一个作品目录的 `meta.json`，并报告该目录是否存在。

    代际链（`generation_tree`）需要三样东西：这一代在哪、它的 `lineage` 记录、
    以及父代目录还在不在。把它们打包成一个返回值，是为了让应用层的遍历循环
    只依赖一次调用 —— 否则每层都要分别问"存在吗"和"meta 是什么"，
    两次询问之间目录可能已被移动（竞态）。
    """

    def read(self, novel_dir: str) -> tuple[dict, str, bool]:
        """返回 `(meta 字典, 状态, 目录是否存在)`。

        状态取值与 `storage.read_json_with_backup` 对齐：
        `"ok"`（读到）/ `"missing"`（文件不存在）/ `"corrupt"`（内容损坏）。
        meta 不是对象时按空字典处理；**任何情况下都不抛异常**。
        """
        ...
