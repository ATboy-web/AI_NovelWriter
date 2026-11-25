"""文件系统实现：从 `timelines/branch_%03d/meta.json` 读分支元数据。

行为与旧 `app/lineage.read_meta` **逐条对齐**（这是兼容性的关键）：

| 情形 | 结果 |
|---|---|
| `parent_dir` 为空 / `timelines/` 不存在 | `[]` |
| 目录存在但无 `branch_*` 子目录 | `[]` |
| 某分支 meta.json 缺失 | 该条目 `{}` |
| 某分支 meta.json 损坏（JSON 解析失败） | 该条目 `{}`，并记 warning |
| meta.json 是数组而非对象 | 该条目 `{}` |

排序：按目录名升序（与旧实现的 `sorted(...)` 一致，保证 `000/001/002` 稳定）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from loguru import logger

from app.storage import read_json_with_backup

__all__ = ["FileBranchMetaReader", "FileLineageMetaReader"]

#: 分支子目录名的前缀；与旧 `lineage.BRANCH_PREFIX` 同值
BRANCH_PREFIX = "branch_"
#: 分支所在目录；与旧 `lineage.BRANCH_PARENT_REL` 同值
BRANCH_PARENT_REL = "timelines"


class FileBranchMetaReader:
    """`ports.BranchMetaReader` 的文件系统实现。"""

    def list_branch_metas(self, parent_dir: Any) -> list[tuple[str, dict]]:
        if not parent_dir:
            return []
        base = Path(parent_dir) / BRANCH_PARENT_REL
        if not base.is_dir():
            return []

        out: list[tuple[str, dict]] = []
        try:
            entries = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith(BRANCH_PREFIX))
        except OSError as exc:
            logger.warning(f"[lineage] 分支目录不可读（按无分支处理）：{base} ({exc})")
            return []

        for path in entries:
            meta, status = read_json_with_backup(path / "meta.json", default=None)
            if status == "corrupt":
                logger.warning(f"[lineage] 分支 meta.json 损坏，按不可打开处理: {path}")
                out.append((path.name, {}))
                continue
            out.append((path.name, dict(meta) if isinstance(meta, Mapping) else {}))
        return out


class FileLineageMetaReader:
    """`ports.LineageMetaReader` 的文件实现。

    行为与旧 `lineage.read_json_with_backup(node / "meta.json")` 对齐：
    主文件不可用时回退 `.bak`，损坏时状态为 `"corrupt"`（调用方据此标记 `missing`）。
    """

    def read(self, novel_dir: str) -> tuple[dict, str, bool]:
        try:
            base = Path(novel_dir)
            exists = base.exists()
        except OSError:
            return {}, "missing", False

        meta, status = read_json_with_backup(base / "meta.json", default=None)
        if status == "corrupt":
            logger.warning(f"[lineage] meta.json 损坏，按无代际信息处理: {novel_dir}")
            return {}, "corrupt", exists
        if not isinstance(meta, Mapping):
            return {}, status, exists
        return dict(meta), status, exists
