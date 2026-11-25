"""文件系统实现：把父代数据复制/写入子代。

对应端口 `app.ports.ChildWriter`。两个方法都经
`domain.resolve_child_target` 解析目标 —— 越界（`..`、绝对路径、前缀相似目录）
在这里就被拒，不会等到 `shutil` 才动手。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.domain.lineage import resolve_child_target
from app.storage import atomic_write_text

__all__ = ["FileChildWriter"]


class FileChildWriter:
    """`ports.ChildWriter` 的文件实现。"""

    def copy(self, parent_dir: str, child_dir: str, relative: str) -> bool:
        src = Path(parent_dir) / relative
        try:
            if not src.exists():
                return False
        except OSError:
            return False

        dst = resolve_child_target(child_dir, relative)  # 越界在此抛 ValueError
        if src.is_dir():
            # dirs_exist_ok：子代可能已有 characters/（续集流程先建过），合并而非报错
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return True

    def write_text(self, child_dir: str, relative: str, content: str) -> bool:
        target = resolve_child_target(child_dir, relative)
        atomic_write_text(target, content)
        return True
