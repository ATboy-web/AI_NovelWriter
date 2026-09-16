"""小说数据领域读写的单一入口（v3 A7）。

**要解决的问题（实测）**：`outline.json` 与 `meta.json` 各自被**三个模块**裸写，
互不知道对方存在：

| 文件 | 裸写位置 |
|---|---|
| `outline.json` | `outline_ui.py:228/308/353`、`generation_ui.py:99/1418/1610/1859`、`lifecycle_ui.py:651`、`timeline_ui.py:570`（分支） |
| `meta.json` | `generation_ui.py:1404/1434/1848`、`lifecycle_ui.py:437/772/919`、`timeline_ui.py:477/651`（分支） |

用 `open(path, 'w')` 写盘有两个后果：

1. **写一半被截断** → 文件损坏（`outline.json` 损坏 = 整本书的结构丢失）；
2. **并发写互相覆盖** —— 生成章节的后台线程与 UI 线程同时改 meta，后者覆盖前者。

`app/storage.py` 已经提供了原子写能力，但调用方仍各写各的。本模块把
「读-改-写」收敛到一处，并按路径加锁串行化。

设计要点：
- **不缓存数据**：磁盘是唯一真相。缓存会让"另一个进程改了文件"变得不可见。
- **按路径加进程内锁**：同一文件的多线程写串行化；跨进程仍靠 `os.replace` 的原子性。
- **事件可选注入**：`events` 参数接受任何有 `publish(topic, payload)` 的对象
  （v3 的 `EventBus`）。P1 阶段事件总线还不存在，因此这里**不 import** 它 ——
  避免制造 P1→P4 的依赖倒挂。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import (
    STATUS_CORRUPT,
    atomic_write_json,
    read_json_with_backup,
)

__all__ = ["NovelStore", "NovelDataError"]

#: 进程内按文件路径串行化（跨实例共享，因此必须是模块级）
_PATH_LOCKS: Dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve()) if path.exists() else str(path.absolute())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


class NovelDataError(RuntimeError):
    """数据文件损坏且无法回退时抛出。

    刻意**不静默返回空** —— "读到空 → 写回空 → 数据清空"是本项目已经踩过的
    级联事故路径（见 `docs/OPTIMIZATION_ROUND2.md` R3）。
    """


class NovelStore:
    """一个小说的领域数据读写。所有写操作原子且串行。"""

    def __init__(self, novel_dir, events=None):
        self.novel_dir = Path(novel_dir)
        self.events = events

    # ------------------------------------------------------------ 路径

    @property
    def meta_path(self) -> Path:
        return self.novel_dir / "meta.json"

    @property
    def outline_path(self) -> Path:
        return self.novel_dir / "outline.json"

    # ------------------------------------------------------------ 事件

    def _publish(self, topic: str, payload: dict) -> None:
        """发布变更事件（events 未注入时静默跳过）。"""
        if self.events is None:
            return
        try:
            self.events.publish(topic, payload)
        except Exception:  # 事件订阅方的异常不得影响数据写入
            pass

    # ------------------------------------------------------------ meta

    def read_meta(self, raise_on_corrupt: bool = False) -> dict:
        """读 meta.json。损坏时按 `raise_on_corrupt` 决定是抛错还是给空 dict。"""
        data, status = read_json_with_backup(self.meta_path, default={})
        if not isinstance(data, dict):
            data = {}
        if status == STATUS_CORRUPT and raise_on_corrupt:
            raise NovelDataError(f"meta.json 损坏且无可用备份: {self.meta_path}")
        return data

    def write_meta(self, meta: dict) -> Path:
        """整份覆盖写 meta.json（原子 + 轮转 .bak）。"""
        if not isinstance(meta, dict):
            raise TypeError("meta 必须是 dict")
        path = self.meta_path
        with _lock_for(path):
            atomic_write_json(path, meta, backup=True)
        self._publish("novel.meta_changed", {"path": str(path), "meta": dict(meta)})
        return path

    def update_meta(self, changes: Optional[dict] = None, **kwargs) -> dict:
        """读-改-写 meta.json，返回更新后的完整 meta。

        这是替代"读出来改两个键再整份写回"的正确做法：
        整个过程在同一把锁内完成，不会把并发方的改动overwrite 掉。
        """
        patch = dict(changes or {})
        patch.update(kwargs)
        path = self.meta_path
        with _lock_for(path):
            meta = self.read_meta()
            meta.update(patch)
            atomic_write_json(path, meta, backup=True)
        self._publish("novel.meta_changed", {"path": str(path), "changed": sorted(patch)})
        return meta

    # ------------------------------------------------------------ outline

    def read_outline(self, raise_on_corrupt: bool = False) -> List[dict]:
        """读 outline.json，**始终返回 list**（写坏的 dict/None 都归一化为 []）。

        归一化而不是抛错：调用方遍历的是章节列表，返回非序列类型会让
        `for ch in outline` 静默遍历到键名字符串。
        """
        data, status = read_json_with_backup(self.outline_path, default=[])
        if status == STATUS_CORRUPT and raise_on_corrupt:
            raise NovelDataError(f"outline.json 损坏且无可用备份: {self.outline_path}")
        return data if isinstance(data, list) else []

    def write_outline(self, outline) -> Path:
        """整份覆盖写 outline.json（原子 + 轮转 .bak）。"""
        if not isinstance(outline, list):
            raise TypeError("outline 必须是 list")
        path = self.outline_path
        with _lock_for(path):
            atomic_write_json(path, outline, backup=True)
        self._publish("outline.changed", {"path": str(path), "count": len(outline)})
        return path

    def append_outline(self, chapters: List[dict]) -> List[dict]:
        """在现有大纲后追加若干章，返回追加后的完整大纲。"""
        if not isinstance(chapters, list):
            raise TypeError("chapters 必须是 list")
        path = self.outline_path
        with _lock_for(path):
            outline = self.read_outline()
            outline.extend(chapters)
            atomic_write_json(path, outline, backup=True)
        self._publish("outline.changed", {"path": str(path), "count": len(outline)})
        return outline

    def update_outline_chapter(self, chapter_num: int, changes: dict) -> List[dict]:
        """更新第 `chapter_num` 章（1 起）的字段，返回更新后的大纲。

        越界时不改任何内容（返回原大纲）—— 宁可什么都不做，
        也不要因为下标算错而写坏别人刚生成的结构。
        """
        path = self.outline_path
        with _lock_for(path):
            outline = self.read_outline()
            index = chapter_num - 1
            if 0 <= index < len(outline) and isinstance(outline[index], dict):
                outline[index].update(changes)
                atomic_write_json(path, outline, backup=True)
            else:
                return outline
        self._publish("outline.changed", {"path": str(path), "chapter": chapter_num})
        return outline

    # ------------------------------------------------------------ 通用

    def read_json(self, relative_path: str, default: Any = None) -> Any:
        """读小说目录下任意 JSON（只读，带 .bak 回退）。"""
        data, _status = read_json_with_backup(self.novel_dir / relative_path, default=default)
        return data

    def write_json(self, relative_path: str, data: Any, backup: bool = True) -> Path:
        """写小说目录下任意 JSON（原子 + 可选轮转）。

        仅用于**不含角色数据**的文件 —— 角色写入必须走
        `memory_manager.mutate_characters`（带三道防丢失闸门）。
        """
        if str(relative_path).replace("\\", "/").split("/")[-1] == "characters.json":
            raise ValueError(
                "characters.json 必须通过 memory_manager.mutate_characters 写入"
                "（角色数据有三道防丢失闸门，绕过会丢角色）"
            )
        path = self.novel_dir / relative_path
        with _lock_for(path):
            atomic_write_json(path, data, backup=backup)
        return path

    def exists(self, relative_path: str) -> bool:
        return (self.novel_dir / relative_path).exists()

    def dump_debug(self) -> str:
        """返回一份简短的存储状态（供诊断面板使用）。"""
        meta = self.read_meta()
        outline = self.read_outline()
        return json.dumps(
            {
                "novel_dir": str(self.novel_dir),
                "meta_keys": sorted(meta)[:12],
                "outline_chapters": len(outline),
                "meta_exists": self.meta_path.exists(),
                "outline_exists": self.outline_path.exists(),
            },
            ensure_ascii=False,
            indent=2,
        )
