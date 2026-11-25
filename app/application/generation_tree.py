"""用例：沿 `parent_novel` 向上回溯出代际链。

## 分层对应

- 每层的"什么存在、meta 是什么"由 `ports.LineageMetaReader` 提供
- 每行的字段定型由 `domain.describe_generation_row` 完成（纯函数）
- 本用例只负责**遍历与防环** —— 以及 `include_branches` 时调注入的分支加载器

`branch_loader` 用注入而不是 import：`discover_branches` 仍在兼容层
`app.lineage` 里，应用层直接 import 它会形成反向依赖（也会让分层退化）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from loguru import logger

from app.domain.lineage import describe_generation_row
from app.ports import LineageMetaReader

__all__ = ["BuildGenerationTree"]

#: 分支加载器签名：给作品目录，返回该作品的分支列表
BranchLoader = Callable[[str], list[dict]]


@dataclass
class BuildGenerationTree:
    """代际链用例。`branch_loader=None` 等价于 `include_branches=False`。"""

    reader: LineageMetaReader
    branch_loader: BranchLoader | None = None

    def execute(self, novel_dir: Any, max_depth: int = 8, include_branches: bool = True) -> list[dict]:
        rows: list[dict] = []
        if not novel_dir:
            return rows

        loader = self.branch_loader if include_branches else None
        seen: set[str] = set()
        node: str | None = str(novel_dir)

        for depth in range(max_depth):
            if node is None:
                break
            if node in seen:  # 环状 lineage（手改 meta 可能造成）—— 截断而不是死循环
                logger.warning(f"[lineage] 代际链出现环，已截断: {node}")
                break
            seen.add(node)

            meta, status, exists = self.reader.read(node)
            branches = loader(node) if loader and exists else []
            rows.append(
                describe_generation_row(
                    node,
                    meta,
                    depth=depth,
                    exists=exists,
                    status=status,
                    branches=branches,
                )
            )
            # 父代路径只从结构合法的 `lineage` 记录里取 —— 手改坏的 meta 不该让遍历中断
            lineage_raw = meta.get("lineage")
            parent = ""
            if isinstance(lineage_raw, Mapping):
                parent = str(lineage_raw.get("parent_novel") or "")
            node = parent or None

        if rows and include_branches:
            self._mark_current_branch(rows, novel_dir)
        return rows

    @staticmethod
    def _mark_current_branch(rows: list[dict], novel_dir: Any) -> None:
        """标出"这一行就是当前打开的作品"。

        从分支里打开时，该分支会同时出现在自己的第 0 行与父代节点的 `branches` 里；
        不标出来，用户会以为是两个不同的东西。
        """
        try:
            from pathlib import Path

            current = str(Path(str(novel_dir)).resolve())
        except OSError:
            return
        for row in rows:
            for branch in row.get("branches") or []:
                try:
                    branch["is_current"] = str(Path(branch["dir"]).resolve()) == current
                except (OSError, KeyError, TypeError):
                    branch["is_current"] = False
