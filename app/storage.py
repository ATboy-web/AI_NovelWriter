"""统一原子写与 JSON 读盘工具（第二轮优化新增）。

背景
----
项目里"原子写"被重复实现了 4 次（`persistence_ui._atomic_write` /
`_atomic_json_write` / `memory_manager.save_characters` /
`character_system.save_character` / `novel_agent` 的角色落盘），且都使用
`Path.with_suffix('.tmp')` 生成临时名 —— 同目录下 `settings.json` 与
`settings.md` 会同时映射到 `settings.tmp`，并发写会互相破坏（见
docs/OPTIMIZATION_ROUND2.md R7）。

本模块提供单一定义：
- 临时名唯一（`<name>.<pid>.<tid>.<uuid8>.tmp`），不同文件/线程/进程互不干扰
- `os.replace` 原子替换，杜绝"写一半被截断"
- `write_json` 可选轮转 `.bak`，为损坏回退提供依据
- `read_json_with_backup` **返回状态而不是静默兜底**，让调用方能区分
  「文件不存在」与「文件损坏」，避免"读到空 → 写回空 → 清库"的级联事故

本模块为纯 I/O 工具：不依赖 `app` 内其它模块，也不依赖 GUI。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

__all__ = [
    "atomic_write_text",
    "atomic_write_json",
    "backup_file",
    "read_json",
    "read_json_with_backup",
    "safe_filename",
]

# 文件名中非法或危险的字符（Windows 不允许 / \ : * ? " < > |）
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_filename(name: str) -> str:
    """把任意字符串（角色名等）转成安全的单层文件名片段。

    同时中和目录穿越序列（``..``），避免被用作路径拼接时逃逸目录。
    原先该逻辑在 `character_system._sanitize_name`、`character_ui._write_char_files`、
    `novel_agent` 三处各写一遍（其中两处漏了 ``..`` 处理），现统一到此处。
    """
    safe = _ILLEGAL_FILENAME_CHARS.sub("_", str(name))
    safe = safe.replace("..", "_")
    return safe.strip() or "unnamed"

# 状态常量：read_json_with_backup 的第二个返回值
STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_BACKUP = "backup"
STATUS_CORRUPT = "corrupt"

# 读盘时视为"内容不可用"的异常集合
_READ_ERRORS = (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError)


def _unique_tmp_path(path: Path) -> Path:
    """生成与目标文件同目录的唯一临时路径。

    不用 `with_suffix('.tmp')`：那会丢掉原扩展名，导致同目录下的
    `a.json` 与 `a.txt` 争用同一个 `a.tmp`。
    """
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")


def atomic_write_text(path, text: str, encoding: str = "utf-8", fsync: bool = True) -> Path:
    """原子写入文本：写临时文件 → fsync → `os.replace` 覆盖目标。

    任一步失败都会清理临时文件并把异常抛给调用方（不静默）。
    """
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _unique_tmp_path(path)
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            if fsync:
                os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return path


def backup_file(path, suffix: str = ".bak", keep: int = 1) -> Optional[Path]:
    """把现有文件轮转为备份。文件不存在返回 None。"""
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    dst = path.with_name(path.name + suffix)
    shutil.copy2(path, dst)
    return dst


def atomic_write_json(
    path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    backup: bool = False,
    fsync: bool = True,
) -> Path:
    """原子写入 JSON。`backup=True` 时先轮转 `.bak`（供损坏回退使用）。"""
    path = Path(path)
    if backup:
        backup_file(path)
    return atomic_write_text(
        path,
        json.dumps(data, indent=indent, ensure_ascii=ensure_ascii),
        fsync=fsync,
    )


def read_json(path) -> Any:
    """读取 JSON，失败时原样抛出（供需要感知错误的上层使用）。"""
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def read_json_with_backup(path, default: Any = None) -> Tuple[Any, str]:
    """读取 JSON，主文件不可用时回退 `.bak`。

    Returns:
        (数据, 状态)，状态取值见 STATUS_* 常量：
        - ``ok``      主文件正常
        - ``backup``  主文件不可用，已回退到 `.bak`
        - ``missing`` 主文件与备份都不存在（返回 default）
        - ``corrupt`` 主文件与备份都无法解析（返回 default，调用方应告警/阻断写入）
    """
    path = Path(path)
    bak = path.with_name(path.name + ".bak")

    if not path.exists():
        if bak.exists():
            try:
                return read_json(bak), STATUS_BACKUP
            except _READ_ERRORS:
                pass
        return default, STATUS_MISSING

    try:
        return read_json(path), STATUS_OK
    except _READ_ERRORS:
        pass

    if bak.exists():
        try:
            return read_json(bak), STATUS_BACKUP
        except _READ_ERRORS:
            pass
    return default, STATUS_CORRUPT
