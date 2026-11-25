"""适配器层：端口的具体实现（文件系统、SQLite、Provider SDK 等）。

## 边界

允许：`app.storage`、标准库、第三方 SDK。
禁止：`app.panels.*`、`tkinter`（适配器不认识界面）。

## 当前实现

- `FileBranchMetaReader` —— 从 `timelines/branch_%03d/meta.json` 读分支元数据。
  这是旧 `lineage.read_meta` 的同款行为（`read_json_with_backup`，损坏视为空）。
"""

from __future__ import annotations

from .child_writer import FileChildWriter
from .file_lineage import FileBranchMetaReader, FileLineageMetaReader
from .path_probe import FilesystemProbe, NeverExistsProbe

__all__ = [
    "FileBranchMetaReader",
    "FileChildWriter",
    "FileLineageMetaReader",
    "FilesystemProbe",
    "NeverExistsProbe",
]
