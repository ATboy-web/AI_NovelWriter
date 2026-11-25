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

__all__ = [
    "BranchMetaReader",
    "ChildWriter",
    "LineageMetaReader",
    "PathProbe",
    "TimelineReader",
    "TimelineWriter",
]


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


@runtime_checkable
class ChildWriter(Protocol):
    """把父代数据写进子代。**每个方法内部都必须过护栏**（`guard_child_path`）。

    为什么把"复制"和"写文本"合成一个端口：两者都是"往子代落盘"，
    分开会让调用方有机会只对其中一种过护栏。实现侧统一用
    `domain.resolve_child_target` 解析目标，越界即抛 `ValueError`。
    """

    def copy(self, parent_dir: str, child_dir: str, relative: str) -> bool:
        """把 `<parent_dir>/<relative>` 复制到 `<child_dir>/<relative>`。

        - 源不存在 ⇒ 返回 `False`（缺某类历史数据是正常的，不是错误）
        - 目标越界 ⇒ 抛 `ValueError`（护栏），**调用方不得重试绕过**
        """
        ...

    def write_text(self, child_dir: str, relative: str, content: str) -> bool:
        """把文本写到 `<child_dir>/<relative>`；越界抛 `ValueError`。"""
        ...


@runtime_checkable
class TimelineReader(Protocol):
    """读世界线 / 时间线。

    只列**稳定**的读方法。`stats` / `branch_tree` / `lineage_chronicle` 这类派生
    视图会随面板需求变化，不纳入端口 —— 否则每个实现都要跟着改签名。
    """

    def read_memory_events(self, from_chapter: int = 0, to_chapter: int = 0) -> list[Any]:
        """读 `memory/timeline/` 里的事件（按章号过滤；传 0 表示不限）。"""
        ...

    def read_world_lines(self) -> list[dict]:
        """列出全部世界线（每条含名称、章节数等摘要）。"""
        ...

    def chapter_axis(self, from_chapter: int = 0, to_chapter: int = 0) -> list[dict]:
        """按章号聚合的事件轴（面板画时间线用）。"""
        ...

    def snapshot(self) -> Any:
        """当前状态快照（供缓存失效判断与回滚）。"""
        ...


@runtime_checkable
class TimelineWriter(Protocol):
    """写世界线。

    这两个方法都**不直接碰 memory/timeline/**：事件源归 `MemoryManager` 所有，
    世界线只做筛选与标注（`tests/test_p4b_panels` 里有守卫钉住这一点）。
    """

    def sync(self, world_line: Any = None) -> Any:
        """按当前事件源重建世界线；返回同步结果（新增/移除/总数）。"""
        ...

    def annotate(self, chapter: int, event: Any) -> bool:
        """给某一章打世界线标注；返回是否成功。"""
        ...

    def invalidate(self) -> None:
        """丢弃缓存，下次读取重新从磁盘加载。"""
        ...
