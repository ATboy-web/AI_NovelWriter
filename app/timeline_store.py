"""时间线统一存储（v3 §2.4 ①）。

## 为什么必须有一个统一层

改造前时间线数据**两套并存、互不关联**：

| 存储 | 谁写 | 谁读 |
|---|---|---|
| `timelines/<世界线>.json`（`name`/`events`/`chapters`/`branches`） | `timeline_ui` 的手工入口、`generation_ui._auto_detect_decisions` | 只被 `timeline_ui` 自己的弹窗读 |
| `memory/timeline/timeline_%03d.json`（`chapter`/`event`/`type`/`characters`/`timestamp`） | `MemoryManager.add_event`（每章自动写） | `MemoryManager.get_timeline` |

于是"作者每章记下的事件"与"世界线视图里看到的事件"是两份数据：前者一直在自动增长，
后者只反映手工添加过的那几条。面板要展示的显然是前者。

本模块把 **`memory/timeline/` 定为唯一事件源**（它是自动的、覆盖每章），
`timelines/*.json` 的 `events` 由它**重建**；而 `branches` / `chapters` / 多世界线等
人工结构**原样保留**（它们不是事件，是本模块无权推断的创作决策）。

## 它不做什么（边界）

- 不占用 `memory/timeline/` 的写权限：事件本身由 `MemoryManager.add_event` 负责，
  本模块只在**同步世界线视图**时写 `timelines/`。唯一例外是 `annotate()`，
  它把"地点 / 故事内时间"这类人工补充委托给 `MemoryManager.annotate_event`，
  仍走那边的锁与原子写。
- 不发起 AI 调用：正文抽取只提供 `extraction_prompt()` 这个**纯函数**，
  真正的调用由面板在后台线程里做，便于单测覆盖提示词而不触碰网络。
- 不依赖 Tk：视图方法返回**纯数据**（list/dict），面板负责画。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from loguru import logger

from app.storage import atomic_write_json, read_json_with_backup, safe_filename

__all__ = [
    "DEFAULT_WORLD_LINE",
    "TimelineEvent",
    "SyncResult",
    "TimelineSnapshot",
    "TimelineStore",
    "extraction_prompt",
    "parse_extraction_result",
]

#: 默认世界线文件名（与既有 `timeline_ui` 一致）
DEFAULT_WORLD_LINE = "main.json"

#: 事件来源标记：`auto` = 从正文/流程自动记录，`manual` = 作者手工添加
SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"

#: 置信度：`auto` 抽取出来的默认低置信，人工确认后升为 high
CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"


@dataclass(frozen=True)
class TimelineEvent:
    """一条时间线事件（与 `memory/timeline/` 里的记录一一对应）。

    `location` / `story_time` / `arc` / `source` / `confidence` 是 v3 新增字段
    （见 `MemoryManager.add_event`）；老数据里没有这些键，读出来是空串/默认值，
    因此**兼容读取**而不需要数据迁移。
    """

    chapter: int
    event: str
    type: str = "story"
    characters: tuple[str, ...] = ()
    timestamp: str = ""
    location: str = ""
    story_time: str = ""
    arc: str = ""
    source: str = SOURCE_AUTO
    confidence: str = CONFIDENCE_HIGH

    #: 事件来自哪一代（跨代编年史用；当前代为空）
    generation: int | None = None
    #: 事件来自哪个小说目录（跨代编年史用）
    novel_dir: str = ""
    #: 只读标记（父代事件在子代面板里灰显、禁止编辑）
    readonly: bool = False

    @property
    def key(self) -> tuple[int, str]:
        """稳定标识：章节 + 事件原文。用于合并两套存储时判重。"""
        return (int(self.chapter), self.event)

    def as_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "event": self.event,
            "type": self.type,
            "characters": list(self.characters),
            "timestamp": self.timestamp,
            "location": self.location,
            "story_time": self.story_time,
            "arc": self.arc,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_record(cls, record: dict, **overrides: Any) -> "TimelineEvent":
        """从 `memory/timeline/` 的原始记录构造；**缺字段一律给默认值**。

        老数据没有 v3 的 5 个增强字段，直接 `record["location"]` 会 KeyError。
        """
        chars = record.get("characters") or ()
        if isinstance(chars, str):
            chars = (chars,)
        # 显式标注：否则 mypy 推出 `dict[str, object]`，`TimelineEvent(**payload)` 会报一堆
        # 「incompatible type」——那些报警本身无价值，但会淹没真正的问题。
        payload: dict[str, Any] = {
            "chapter": int(record.get("chapter", 0) or 0),
            "event": str(record.get("event", "") or ""),
            "type": str(record.get("type", "story") or "story"),
            "characters": tuple(str(c) for c in chars),
            "timestamp": str(record.get("timestamp", "") or ""),
            "location": str(record.get("location", "") or ""),
            "story_time": str(record.get("story_time", "") or ""),
            "arc": str(record.get("arc", "") or ""),
            "source": str(record.get("source", SOURCE_AUTO) or SOURCE_AUTO),
            "confidence": str(record.get("confidence", CONFIDENCE_HIGH) or CONFIDENCE_HIGH),
        }
        payload.update(overrides)
        return cls(**payload)


@dataclass
class SyncResult:
    """`sync()` 的结果，供面板给出可验证的反馈（而不是"点了没反应"）。"""

    world_line: str = DEFAULT_WORLD_LINE
    total: int = 0
    added: int = 0
    kept_manual: int = 0
    dropped: int = 0
    written: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "world_line": self.world_line,
            "total": self.total,
            "added": self.added,
            "kept_manual": self.kept_manual,
            "dropped": self.dropped,
            "written": self.written,
            "reason": self.reason,
        }

    def describe(self) -> str:
        if not self.written:
            return f"未写入（{self.reason or '无变化'}）"
        return (
            f"世界线 {self.world_line}：事件共 {self.total} 条"
            f"（新增 {self.added}，保留手工 {self.kept_manual}，移除失联 {self.dropped}）"
        )


@dataclass
class TimelineSnapshot:
    """一次取数得到的**全部**视图数据（面板据此渲染，不再各自去问 store）。

    为什么要有它：面板刷新原本是「四个视图各调一次 + 摘要再调一次」，
    每次都独立触发一遍事件源读取。把取数收成一次，有两个好处：

    1. **一致性** —— 四个视图保证来自同一批读数，不会出现"章节轴已更新、
       人物轨迹还是上一秒"的撕裂；
    2. **成本** —— 面板层不再有机会重复读（即使将来有人去掉缓存也不会退化）。
    """

    events: list[TimelineEvent] = field(default_factory=list)
    axis: list[dict] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    branch_dirs: list[dict] = field(default_factory=list)
    tracks: dict[str, dict] = field(default_factory=dict)
    chronicle: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class TimelineStore:
    """时间线的唯一读写入口（面板与脚本都用它，不要各自 `open()` JSON）。

    Parameters
    ----------
    novel_dir : 小说目录；传 `None` 时所有读操作返回空、写操作抛 `ValueError`
        （面板在"未打开小说"状态下应展示提示而不是崩溃）。
    events : 可选的事件出口（与 `NovelStore(events=...)` 同一鸭子类型约定：
        只要求对象有 `publish(topic, payload)`）。`sync()` 写盘成功后广播
        `timeline.changed`。

    Notes
    -----
    **读取结果按文件指纹缓存**。这不是过早优化：面板一次刷新要取四个视图 + 摘要，
    实测会把同一批分页文件**重复读 4 遍**（1094 章 / 11 分页 → 48 次磁盘读取 / 68ms），
    而 `timeline.changed` / `chapter.saved` 每次都会触发一次刷新；
    传记面板更是每选一个角色就全量扫一遍（23 次读取/次，浏览 300 角色 ≈ 6900 次）。

    缓存键是「分页文件的 `(名字, 大小, mtime_ns)` 元组」——它同时给出两个保证：

    - 命中时**零解析成本**（只做 11 次 `stat`，而不是 11 次读盘 + JSON 解析 + 排序）；
    - **别人写了也能立刻看见**：任何外部进程改动文件都会改变指纹，下次读取自动重算。
      因此不需要调用方记得"写完了要清缓存"。

    ⚠️ **已知边界（实测踩到）**：若有人以**完全相同的字节长度**在**同一文件系统时间粒度内**
    重写文件，`(大小, mtime_ns)` 可能都不变，缓存不会察觉。本机实测（2026-09-16）
    同长度重写确实会漏（见 `test_same_size_rewrite_is_a_documented_limitation`）。
    典型场景不受影响：事件是**追加**写（大小必然变化）。
    两条补救：
    1. 本模块自己的写操作（`sync` / `annotate`）成功后**主动 `invalidate()`**；
    2. 调用方若明确知道"我刚写了同一个文件"，调 `invalidate()` 即可。
    """

    def __init__(self, novel_dir: Any = None, events: Any = None) -> None:
        self.novel_dir = Path(novel_dir) if novel_dir else None
        self.events = events
        #: 指纹 → 解析结果。键名见 `_CACHE_*`，值都带指纹以便自动失效。
        self._cache: dict[str, tuple[Any, Any]] = {}
        #: 父代 store（代际链上只读；惰性创建并复用，见 `parent_store()`）
        self._parent_store_cache: TimelineStore | None = None

    # ------------------------------------------------------------------ 路径

    @property
    def timelines_dir(self) -> Path | None:
        return None if self.novel_dir is None else self.novel_dir / "timelines"

    @property
    def timeline_dir(self) -> Path | None:
        """`memory/timeline/` —— 事件源（只读）。"""
        return None if self.novel_dir is None else self.novel_dir / "memory" / "timeline"

    @property
    def character_activity_file(self) -> Path | None:
        return None if self.novel_dir is None else self.novel_dir / "memory" / "character_activity.json"

    def world_line_path(self, name: str = DEFAULT_WORLD_LINE) -> Path | None:
        base = self.timelines_dir
        if base is None:
            return None
        # 防目录穿越：世界线名会被用作文件名
        safe = safe_filename(name) if "/" in name or "\\" in name else name
        return base / safe

    # ------------------------------------------------------------------ 读取缓存

    @staticmethod
    def _scan_dir(
        dir_path: Path | None, prefix: str = "", suffix: str = ".json"
    ) -> tuple[tuple[tuple[str, int, int], ...], list[Path]]:
        """**一次目录枚举**同时得到指纹与文件列表。

        为什么不用 `glob()` + `Path.stat()`：实测（11 个文件 / Windows）
        `glob + 2×Path.stat` 要 **5.96 ms**，而 `os.scandir + entry.stat()`
        只要 **0.24 ms**（**24.9 倍**）—— Windows 上 `DirEntry.stat()` 直接复用
        目录枚举已经返回的数据，不再逐个发起系统调用。两者结果逐字节一致。

        这一个函数同时给出「要不要重算」和「读哪些文件」，
        于是缓存命中路径上只剩一次目录枚举。
        """
        if dir_path is None:
            return (), []
        found: list[tuple[str, int, int]] = []
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if prefix and not entry.name.startswith(prefix):
                        continue
                    if suffix and not entry.name.endswith(suffix):
                        continue
                    try:
                        if not entry.is_file():
                            continue
                        stat_result = entry.stat()
                    except OSError:
                        continue
                    found.append((entry.name, stat_result.st_size, stat_result.st_mtime_ns))
        except OSError:
            return (), []
        found.sort()
        return tuple(found), [dir_path / name for name, _size, _mtime in found]

    @staticmethod
    def _signature(paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
        """**显式文件列表**的指纹 `(名字, 大小, mtime_ns)`。

        只用于少量、已知路径的场景（`meta.json`、`character_activity.json`、
        `branch_*/meta.json`）。目录扫描请用 `_scan_dir`（快 25 倍）。
        """
        signature = []
        for path in paths:
            try:
                stat_result = path.stat()
            except OSError:
                signature.append((path.name, -1, -1))
                continue
            signature.append((path.name, stat_result.st_size, stat_result.st_mtime_ns))
        return tuple(signature)

    def invalidate(self) -> None:
        """清空读取缓存。

        正常**不需要**调用：指纹会自动发现外部改动。它的用途是
        「本进程刚写完、要把同一实例的读数强制对齐」以及在测试里显式重置。
        """
        self._cache.clear()

    def _cached(self, key: str, fingerprint: Any, compute: Any) -> Any:
        """按指纹取缓存；指纹变了就重算并替换。"""
        hit = self._cache.get(key)
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
        value = compute()
        self._cache[key] = (fingerprint, value)
        return value

    # ------------------------------------------------------------------ 读：事件源

    def _page_scan(self) -> tuple[tuple[tuple[str, int, int], ...], list[Path]]:
        """事件源分页（一次枚举同时给出指纹与文件列表）。"""
        return self._scan_dir(self.timeline_dir, "timeline_", ".json")

    def page_files(self) -> list[Path]:
        """事件源的分页文件（已排序）。"""
        return self._page_scan()[1]

    def _parse_pages(self, pages: list[Path]) -> list[TimelineEvent]:
        """真正读盘并解析分页（只在缓存未命中时调用）。"""
        events: list[TimelineEvent] = []
        for page_file in pages:
            data, status = read_json_with_backup(page_file, default=None)
            if status == "corrupt":
                logger.warning(f"[timeline_store] 时间线分页损坏，已跳过: {page_file.name}")
                continue
            if not isinstance(data, list):
                continue
            for record in data:
                if not isinstance(record, dict):
                    continue
                try:
                    events.append(TimelineEvent.from_record(record))
                except (TypeError, ValueError):
                    continue
        return sorted(events, key=lambda e: (e.chapter, e.timestamp, e.event))

    def _all_events(self) -> list[TimelineEvent]:
        """全部事件（缓存）。**调用方只读**，不要就地排序或修改。"""
        signature, pages = self._page_scan()
        return self._cached("events", signature, lambda: self._parse_pages(pages))

    def read_memory_events(self, from_chapter: int = 0, to_chapter: int | None = None) -> list[TimelineEvent]:
        """从 `memory/timeline/timeline_*.json` 读事件（唯一事件源），可按章号区间过滤。

        直接读文件而不是走 `MemoryManager.get_timeline`：后者需要构造
        `MemoryManager`（会建目录、跑一次完整初始化），而面板只要数据。
        分页规则与 `MemoryManager._get_timeline_page` 保持一致：每 100 章一页。

        区间过滤作用在**已缓存的完整列表**上（列表推导比一次磁盘读便宜两个数量级），
        因此带上区间也不会让缓存失效。
        """
        events = self._all_events()
        if not from_chapter and to_chapter is None:
            return list(events)
        return [
            event
            for event in events
            if (not from_chapter or event.chapter >= from_chapter)
            and (to_chapter is None or event.chapter <= to_chapter)
        ]

    # ------------------------------------------------------------------ 读：世界线视图

    def _world_line_scan(self) -> tuple[tuple[tuple[str, int, int], ...], list[Path]]:
        """世界线文件（一次枚举同时给出指纹与文件列表）。

        只取 `timelines/` **顶层** 的 `*.json`：分支子项目目录也叫
        `timelines/branch_xxx/`，它的 `meta.json` 在下一层，`os.scandir` 看不到，
        而 `entry.is_file()` 会把子目录本身排除掉。
        """
        return self._scan_dir(self.timelines_dir, "", ".json")

    def world_line_files(self) -> list[Path]:
        return self._world_line_scan()[1]

    def read_world_lines(self) -> list[dict]:
        """读取全部世界线（每个文件一条），并注入 `_file` 便于回写。结果带缓存。

        与 `timeline_ui` 的历史行为一致：结构缺失时给出默认骨架，
        而不是让调用方处理 `KeyError`。
        """
        signature, files = self._world_line_scan()
        return self._cached("world_lines", signature, lambda: self._parse_world_lines(files))

    def _parse_world_lines(self, files: list[Path]) -> list[dict]:
        result: list[dict] = []
        for path in files:
            data, status = read_json_with_backup(path, default=None)
            if status == "corrupt" or not isinstance(data, dict):
                logger.warning(f"[timeline_store] 世界线损坏，已跳过: {path.name}")
                continue
            data.setdefault("name", path.stem)
            data.setdefault("events", [])
            data.setdefault("chapters", [])
            data.setdefault("branches", [])
            data["_file"] = path.name
            result.append(data)
        return result

    def read_world_line(self, name: str = DEFAULT_WORLD_LINE) -> dict:
        """读单条世界线；不存在时返回**默认骨架**（不抛错，方便面板直接画）。"""
        path = self.world_line_path(name)
        if path is None:
            return self._empty_world_line(name)
        data, status = read_json_with_backup(path, default=None)
        if status == "corrupt" or not isinstance(data, dict):
            if status == "corrupt":
                logger.warning(f"[timeline_store] 世界线损坏，返回空骨架: {name}")
            return self._empty_world_line(name)
        data.setdefault("name", Path(name).stem)
        data.setdefault("events", [])
        data.setdefault("chapters", [])
        data.setdefault("branches", [])
        data["_file"] = name
        return data

    @staticmethod
    def _empty_world_line(name: str) -> dict:
        return {
            "name": Path(name).stem,
            "events": [],
            "chapters": [],
            "branches": [],
            "_file": name,
        }

    # ------------------------------------------------------------------ 合并与同步

    @staticmethod
    def _manual_events(world_line: dict) -> list[dict]:
        """挑出世界线里**手工**维护、事件源里没有的条目。

        这些是作者直接在世界线视图里加的（`source` 不再是 `auto`），
        重建时**必须保留**，否则同步一次就把人工内容擦掉了。
        """
        kept: list[dict] = []
        for raw in world_line.get("events") or []:
            if isinstance(raw, dict) and str(raw.get("source", "")) == SOURCE_MANUAL:
                kept.append(raw)
        return kept

    def merge_events(
        self, world_line: dict, memory_events: Sequence[TimelineEvent] | None = None
    ) -> tuple[list[dict], SyncResult]:
        """把事件源合并进世界线视图（**纯计算，不写盘**）。

        合并规则：
        - 事件源（memory）优先，按 `(chapter, event)` 去重；
        - 世界线里标记 `source=manual` 的条目保留（人工内容不可被同步抹掉）；
        - 其余（旧的 `auto` 条目）会被重建，`dropped` 记录被替换掉的数量。
        """
        events = list(memory_events) if memory_events is not None else self.read_memory_events()
        merged: dict[tuple[int, str], dict] = {}
        for event in events:
            merged[event.key] = event.as_dict()

        manual = self._manual_events(world_line)
        manual_keys: set[tuple[int, str]] = set()
        for raw in manual:
            try:
                key = (int(raw.get("chapter", 0) or 0), str(raw.get("event", "") or ""))
            except (TypeError, ValueError):
                continue
            if key in merged:
                # 同一事件既在事件源又在手工表：以事件源为准，避免重复行
                continue
            manual_keys.add(key)
            merged[key] = dict(raw)

        previous = [r for r in (world_line.get("events") or []) if isinstance(r, dict)]
        previous_keys = {
            (int(r.get("chapter", 0) or 0), str(r.get("event", "") or "")) for r in previous if r.get("event")
        }
        added = len(set(merged) - previous_keys)
        dropped = len(previous_keys - set(merged))
        ordered = [merged[k] for k in sorted(merged, key=lambda k: (k[0], k[1]))]
        result = SyncResult(
            world_line=str(world_line.get("_file") or DEFAULT_WORLD_LINE),
            total=len(ordered),
            added=added,
            kept_manual=len(manual_keys),
            dropped=dropped,
        )
        return ordered, result

    def sync(self, world_line: str = DEFAULT_WORLD_LINE) -> SyncResult:
        """重建世界线视图的 `events` 并原子写盘；成功后广播 `timeline.changed`。

        `branches` / `chapters` / `name` 原样保留 —— 它们是创作决策，不是事件。
        """
        path = self.world_line_path(world_line)
        if path is None:
            return SyncResult(world_line=world_line, reason="尚未打开小说")

        current = self.read_world_line(world_line)
        ordered, result = self.merge_events(current, self.read_memory_events())

        if ordered == [r for r in (current.get("events") or []) if isinstance(r, dict)]:
            result.written = False
            result.reason = "事件已是最新，无需重写"
            return result

        payload = {
            "name": current.get("name") or Path(world_line).stem,
            "events": ordered,
            "chapters": current.get("chapters") or [],
            "branches": current.get("branches") or [],
        }
        try:
            atomic_write_json(path, payload, indent=2, backup=True)
        except OSError as e:
            logger.error(f"[timeline_store] 写入世界线失败: {e}")
            result.written = False
            result.reason = f"写入失败: {e}"
            return result

        result.written = True
        # 本进程刚写过：主动失效，避免"同长度重写"这类指纹察觉不到的情况（见类文档）
        self.invalidate()
        self._publish()
        return result

    def _publish(self, payload: dict | None = None) -> None:
        """广播 `timeline.changed`（旁路：广播失败不影响写盘结果）。"""
        if self.events is None:
            return
        try:
            from app.events import TOPIC_TIMELINE_CHANGED

            self.events.publish(
                TOPIC_TIMELINE_CHANGED, payload or {"novel_dir": str(self.novel_dir or ""), "source": "sync"}
            )
        except Exception as e:  # noqa: BLE001 - 事件是旁路，绝不影响数据写入
            logger.debug(f"[timeline_store] 广播 timeline.changed 失败（忽略）: {e}")

    # ------------------------------------------------------------------ 写：人工补充字段

    def annotate(self, chapter: int, event: str, **fields: Any) -> bool:
        """给既有事件补 `location` / `story_time` / `arc` 等人工字段。

        委托给 `MemoryManager.annotate_event`（走那边的锁与原子写），
        本模块不直接碰 `memory/timeline/`。
        """
        if self.novel_dir is None:
            return False
        try:
            from app.memory_manager import MemoryManager

            memory = MemoryManager(self.novel_dir)
            if not hasattr(memory, "annotate_event"):  # pragma: no cover - 防御性
                return False
            ok = bool(memory.annotate_event(int(chapter), str(event), **fields))
        except Exception as e:  # noqa: BLE001 - 面板按钮不应因数据问题崩掉
            logger.error(f"[timeline_store] 标注事件失败: {type(e).__name__}: {e}")
            return False
        if ok:
            # 事件源被改了（`annotate_event` 走的是 MemoryManager 的写路径）——
            # 主动失效，别依赖指纹能察觉"等长重写"（见类文档）
            self.invalidate()
            self._publish({"novel_dir": str(self.novel_dir), "chapter": int(chapter), "event": str(event)})
        return ok

    # ------------------------------------------------------------------ 视图一：章节轴

    def chapter_axis(self, from_chapter: int = 0, to_chapter: int | None = None) -> list[dict]:
        """视图一：按章聚合。每行 `{chapter, count, characters, events}`。"""
        grouped: dict[int, list[TimelineEvent]] = {}
        for event in self.read_memory_events(from_chapter, to_chapter):
            grouped.setdefault(event.chapter, []).append(event)
        rows = []
        for chapter in sorted(grouped):
            items = grouped[chapter]
            chars: list[str] = []
            for item in items:
                for name in item.characters:
                    if name not in chars:
                        chars.append(name)
            rows.append(
                {
                    "chapter": chapter,
                    "count": len(items),
                    "characters": chars,
                    "events": items,
                    "summary": "；".join(i.event for i in items if i.event),
                }
            )
        return rows

    # ------------------------------------------------------------------ 视图二：世界线与分支

    def branch_tree(self) -> list[dict]:
        """视图二：世界线 → 分支。返回 `[{name, file, branches:[{...}]}]`。

        `branches` 项来自 `generation_ui._auto_detect_decisions`，
        字段为 `chapter/decision/chosen/alternative/story`。
        """
        tree: list[dict[str, Any]] = []
        for world in self.read_world_lines():
            branches: list[dict[str, Any]] = []
            for raw in world.get("branches") or []:
                if not isinstance(raw, dict):
                    continue
                branches.append(
                    {
                        "chapter": int(raw.get("chapter", 0) or 0),
                        "decision": str(raw.get("decision", "") or ""),
                        "chosen": str(raw.get("chosen", "") or ""),
                        "alternative": str(raw.get("alternative", "") or ""),
                        "story": str(raw.get("story", "") or ""),
                    }
                )
            branches.sort(key=lambda b: b["chapter"])
            tree.append(
                {
                    "name": str(world.get("name") or ""),
                    "file": str(world.get("_file") or ""),
                    "branches": branches,
                    "chapters": list(world.get("chapters") or []),
                }
            )
        return tree

    def branch_dirs(self) -> list[dict]:
        """已建立的**分支子项目**目录（`timelines/branch_%03d/`）。

        ⚠️ 这些目录原本是**只写不读**的：`timeline_ui` 建出来（含完整目录树）就再没人碰。
        现在它们既是本视图的一行，也能被当成作品打开、并出现在代际树里。

        解析委托给 `app.lineage.discover_branches`（**同一份读取器**），
        这里只映射成时间线视图用的字段名，避免两处各解析一遍 `meta.json`。
        """
        from app.lineage import discover_branches

        out = []
        for node in discover_branches(self.novel_dir):
            out.append(
                {
                    "dir": node["dir"],
                    "branch_id": node["branch_id"],
                    "name": node["title"],
                    "title": node["title"],
                    "origin_chapter": node["origin_chapter"],
                    "status": node["status"],
                    "chapter_count": node["chapter_count"],
                    "meta_ok": node["openable"],
                    "openable": node["openable"],
                    "reason": node["reason"],
                }
            )
        return out

    # ------------------------------------------------------------------ 视图三：人物轨迹泳道

    def character_activity(self) -> dict:
        """读 `memory/character_activity.json`（读不到就返回空字典）。**结果带缓存。**"""
        path = self.character_activity_file
        if path is None:
            return {}
        return self._cached("activity", self._signature([path]), lambda: self._parse_activity(path))

    @staticmethod
    def _parse_activity(path: Path) -> dict:
        data, status = read_json_with_backup(path, default=None)
        if status == "corrupt" or not isinstance(data, dict):
            if status == "corrupt":
                logger.warning("[timeline_store] character_activity.json 损坏，按空处理")
            return {}
        return data

    def character_tracks(self) -> dict[str, dict]:
        """视图三：人物轨迹。以 `character_activity.json` 为主，用事件源兜底补齐。**结果带缓存。**

        为什么要兜底：`update_character_activity` 目前**没有任何生产调用方**
        （只有测试调用），所以真实小说里这个文件可能是空的。此时直接从事件源的
        `characters` 字段反推出现章，泳道依然有内容可看。

        返回的是**缓存对象，调用方只读**（不要就地改）。
        """
        fingerprint = (
            self._page_scan()[0],
            self._signature([self.character_activity_file] if self.character_activity_file else []),
        )
        return self._cached("tracks", fingerprint, self._build_tracks)

    def _build_tracks(self) -> dict[str, dict]:
        tracks: dict[str, dict] = {}

        def slot(name: str) -> dict:
            return tracks.setdefault(name, {"appearances": [], "last_seen": 0, "importance": 5, "event_chapters": []})

        for name, raw in self.character_activity().items():
            if not isinstance(raw, dict):
                continue
            entry = slot(str(name))
            appearances = [int(c) for c in (raw.get("appearances") or []) if isinstance(c, (int, float))]
            entry["appearances"] = sorted({c for c in appearances if c > 0})
            entry["last_seen"] = int(raw.get("last_seen", 0) or 0)
            entry["importance"] = int(raw.get("importance", 5) or 5)

        for event in self._all_events():
            for name in event.characters:
                entry = slot(name)
                if event.chapter not in entry["event_chapters"]:
                    entry["event_chapters"].append(event.chapter)
                entry["last_seen"] = max(entry["last_seen"], event.chapter)

        for entry in tracks.values():
            entry["event_chapters"] = sorted(set(entry["event_chapters"]))
            if not entry["appearances"]:
                entry["appearances"] = list(entry["event_chapters"])
        return tracks

    # ------------------------------------------------------------------ 视图四：跨代编年史

    def meta(self) -> dict:
        """本作的 `meta.json`（读不到/损坏时返回空字典）。**结果带缓存。**"""
        if self.novel_dir is None:
            return {}
        path = self.novel_dir / "meta.json"
        return self._cached("meta", self._signature([path]), lambda: self._parse_meta(path))

    @staticmethod
    def _parse_meta(path: Path) -> dict:
        data, status = read_json_with_backup(path, default=None)
        if status == "corrupt" or not isinstance(data, dict):
            return {}
        return data

    def parent_store(self) -> "TimelineStore | None":
        """代际链上的父代 store（**只读**；无 lineage 或父代目录不存在时返回 None）。

        复用实例而不是每次 new：父代的事件源同样要被 `lineage_chronicle()` 读，
        而它每次面板刷新都会被调用。
        """
        lineage = self.meta().get("lineage")
        parent = lineage.get("parent_novel") if isinstance(lineage, dict) else None
        if not parent:
            return None
        store = self._parent_store_cache
        if store is None or str(store.novel_dir) != str(parent):
            store = TimelineStore(parent)
            self._parent_store_cache = store
        return store

    def lineage_chronicle(self) -> list[dict]:
        """视图四：跨代编年史。父代事件**只读**（`readonly=True`、`generation` 递减）。

        数据来源是子代 `meta.json` 的 `lineage.parent_novel`（由世代传承面板写入）。
        父代目录**只读打开**：本方法只调 `read_memory_events`，不写任何文件 ——
        这是「子代不得污染父代」护栏在时间线侧的落点。

        结果带缓存，指纹覆盖**双方**的事件源与本人的 meta：任何一边有写入都会自动重算。
        """
        parent_store = self.parent_store()
        fingerprint = (
            self._signature([self.novel_dir / "meta.json"]) if self.novel_dir else (),
            self._page_scan()[0],
            str(parent_store.novel_dir) if parent_store else "",
            parent_store._page_scan()[0] if parent_store else (),
        )
        return self._cached("chronicle", fingerprint, lambda: self._build_chronicle(parent_store))

    def _build_chronicle(self, parent_store: "TimelineStore | None") -> list[dict]:
        chronicle: list[dict[str, Any]] = []
        if self.novel_dir is None:
            return chronicle
        lineage = self.meta().get("lineage")
        if not isinstance(lineage, dict):
            return chronicle

        generation = int(lineage.get("generation", 1) or 1)
        parent = lineage.get("parent_novel")
        if parent and parent_store is not None:
            try:
                for event in parent_store.read_memory_events():
                    row = event.as_dict()
                    row.update(
                        {
                            "generation": max(generation - 1, 1),
                            "novel_dir": str(parent),
                            "readonly": True,
                            "ancestor": True,
                        }
                    )
                    chronicle.append(row)
            except Exception as e:  # noqa: BLE001 - 父代不可读不应让面板崩掉
                logger.warning(f"[timeline_store] 读取父代时间线失败（已跳过）: {e}")

        for event in self._all_events():
            row = event.as_dict()
            row.update({"generation": generation, "novel_dir": str(self.novel_dir), "readonly": False})
            chronicle.append(row)

        chronicle.sort(
            key=lambda r: (
                int(r.get("generation", 1) or 1),
                int(r.get("chapter", 0) or 0),
                str(r.get("event", "")),
            )
        )
        return chronicle

    # ------------------------------------------------------------------ 一次取数

    def snapshot(self) -> TimelineSnapshot:
        """一次取回四个视图 + 摘要（**面板唯一该调的入口**）。

        内部全部走缓存，因此重复调用几乎零成本；但语义上它保证
        「这一份数据是同一次读取的产物」。
        """
        events = self._all_events()
        tracks = self.character_tracks()
        return TimelineSnapshot(
            events=list(events),
            axis=self.chapter_axis(),
            branches=self.branch_tree(),
            branch_dirs=self.branch_dirs(),
            tracks=tracks,
            chronicle=self.lineage_chronicle(),
            stats=self._stats_from(events, tracks),
        )

    # ------------------------------------------------------------------ 统计（面板侧栏）

    def stats(self) -> dict:
        """一行摘要，供面板标题/侧栏显示。"""
        return self._stats_from(self._all_events(), self.character_tracks())

    def _stats_from(self, events: list[TimelineEvent], tracks: dict[str, dict]) -> dict:
        chapters = {e.chapter for e in events}
        return {
            "events": len(events),
            "chapters": len(chapters),
            "characters": len(tracks),
            "world_lines": len(self.world_line_files()),
            "branch_dirs": len(self.branch_dirs()),
            "manual": sum(1 for e in events if e.source == SOURCE_MANUAL),
            "low_confidence": sum(1 for e in events if e.confidence == CONFIDENCE_LOW),
            "first_chapter": min(chapters) if chapters else 0,
            "last_chapter": max(chapters) if chapters else 0,
        }


# ====================================================================== 纯函数


#: 抽取事件用的返回契约（面板把它拼进提示词，也据此解析结果）
EXTRACTION_SCHEMA_HINT = (
    "只输出 JSON 数组，不要任何解释文字。每项形如："
    '{"chapter": 12, "event": "一句话事件", "type": "story", '
    '"characters": ["角色A"], "location": "地点", "story_time": "故事内时间", '
    '"arc": "所属弧线", "confidence": "high"}'
)


def extraction_prompt(
    chapter_num: int,
    text: str,
    known_characters: Iterable[str] = (),
    max_events: int = 12,
    max_chars: int = 6000,
) -> str:
    """构造"从正文抽取事件"的提示词（**纯函数**，便于单测）。

    为什么单独抽出来：抽取本身要调 AI（不可单测、有网络依赖），
    而"提示词是否把章节号、角色白名单、输出契约交代清楚"是**可以单测**的，
    也是这类功能最容易出错的地方（模型返回散文、返回错章节号、自造角色名）。

    正文超过 `max_chars` 时**只取头尾**：开头交代场景与人物，结尾是结果与悬念，
    中间过程对"发生了什么"贡献最小。
    """
    body = (text or "").strip()
    if len(body) > max_chars:
        head = body[: max_chars * 2 // 3]
        tail = body[-max_chars // 3 :]
        body = f"{head}\n……（中间省略）……\n{tail}"

    names = [str(n) for n in known_characters if str(n).strip()]
    roster = (
        "已知角色（**只能**从中选取 characters，不要自造名字）：" + "、".join(names[:120])
        if names
        else "本作尚未登记角色，characters 可留空数组。"
    )

    return (
        f"你在为长篇小说维护时间线。请从下面第 {chapter_num} 章的正文中抽取关键事件"
        f"（最多 {max_events} 条，只抽推进情节或改变人物关系的事件，不要抽景物描写）。\n\n"
        f"{roster}\n\n"
        f"硬性要求：\n"
        f"1. 每条事件的 `chapter` 必须是 {chapter_num}（不要写别的章号）；\n"
        f"2. `event` 是一句话，不要抄原文长句；\n"
        f"3. 判断不了 `location` / `story_time` 时留空字符串，不要编造；\n"
        f'4. `confidence` 只在事件明确写到时才用 "high"，否则 "low"；\n'
        f"5. {EXTRACTION_SCHEMA_HINT}\n\n"
        f"【第 {chapter_num} 章正文】\n{body}"
    )


def parse_extraction_result(raw: str, chapter_num: int, known_characters: Iterable[str] = ()) -> list[dict]:
    """解析模型返回的 JSON，并**修正**明显不可信的结果。

    三处纠正（都是实测里最容易出的问题）：
    - 章号被模型写成别的值 → 强制改回 `chapter_num`；
    - `characters` 里出现未登记的名字 → 丢弃该名字（避免污染角色库）；
    - 返回的不是数组/无法解析 → 返回空列表（调用方据此报"没抽到"，而不是崩）。
    """
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        text = text.rstrip("`").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []

    allowed = {str(n) for n in known_characters}
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event", "") or "").strip()
        if not event:
            continue
        chars = item.get("characters") or []
        if isinstance(chars, str):
            chars = [chars]
        chars = [str(c).strip() for c in chars if str(c).strip()]
        if allowed:
            chars = [c for c in chars if c in allowed]
        confidence = str(item.get("confidence", "") or "").strip().lower()
        out.append(
            {
                "chapter": int(chapter_num),
                "event": event,
                "type": str(item.get("type", "story") or "story"),
                "characters": char_list_unique(chars),
                "location": str(item.get("location", "") or "").strip(),
                "story_time": str(item.get("story_time", "") or "").strip(),
                "arc": str(item.get("arc", "") or "").strip(),
                "source": SOURCE_AUTO,
                "confidence": CONFIDENCE_HIGH if confidence == CONFIDENCE_HIGH else CONFIDENCE_LOW,
            }
        )
    return out


def char_list_unique(names: Sequence[str]) -> list[str]:
    """保序去重（`characters` 里同一个角色只留一次）。"""
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out
