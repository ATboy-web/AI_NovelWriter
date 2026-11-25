"""文件系统适配器：把「某路径是否存在」落到真实磁盘上。

对应端口 `app.ports.PathProbe`。放在这里而不是领域层，是为了让
`domain.build_inheritance_plan` 能在**不碰磁盘**的前提下被穷举测试。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["FilesystemProbe", "NeverExistsProbe"]


class FilesystemProbe:
    """以 `root` 为基准，判断相对路径是否存在。"""

    def __init__(self, root: Any):
        self._root = Path(root) if root else None

    def exists(self, relative_path: str) -> bool:
        if self._root is None:
            return False
        try:
            return (self._root / relative_path).exists()
        except OSError:
            # 权限/路径过长等系统级问题按"不存在"处理 ——
            # 继承计划是"给用户看的预估"，不该因此整体失败
            return False


class NeverExistsProbe:
    """所有路径都视为不存在（`parent_dir` 为空时使用）。"""

    def exists(self, relative_path: str) -> bool:
        return False
