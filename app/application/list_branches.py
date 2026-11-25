"""用例：列出某作品的分支子项目。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain import BranchInfo, describe_branch
from app.ports import BranchMetaReader

__all__ = ["BranchRow", "ListBranches"]

#: 分支目录名前缀（与适配器的 `BRANCH_PREFIX` 同值）。
#: 放在这里是因为"如何从目录名解析出分支编号"属于**用例语义**，
#: 不该埋进文件系统适配器里 —— 换存储时不希望再实现一遍前缀切分。
_BRANCH_PREFIX = "branch_"


@dataclass(frozen=True)
class BranchRow:
    """一条分支的完整上下文：目录名 + 原始 meta + 领域判定。

    带上 `meta` 是为了让兼容层能算旧接口里的 `generation`（依赖 `LineageRecord`），
    而**不必**让应用层反向 import 旧模块 —— 那会让分层退回互相依赖。
    """

    dir_name: str
    meta: dict
    info: BranchInfo


@dataclass
class ListBranches:
    """列出分支子项目的用例。

    依赖注入 `reader`：生产用 `FileBranchMetaReader`，测试用内存替身 —— 无需造目录。
    """

    reader: BranchMetaReader

    def execute(self, parent_dir: Any) -> list[BranchRow]:
        rows: list[BranchRow] = []
        for dir_name, meta in self.reader.list_branch_metas(parent_dir):
            branch_id = dir_name[len(_BRANCH_PREFIX) :] if dir_name.startswith(_BRANCH_PREFIX) else dir_name
            rows.append(
                BranchRow(
                    dir_name=dir_name,
                    meta=dict(meta or {}),
                    info=describe_branch(branch_id, meta, fallback_title=dir_name),
                )
            )
        return rows
