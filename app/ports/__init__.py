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

__all__ = ["BranchMetaReader"]


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
