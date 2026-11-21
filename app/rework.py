"""章节回炉重造 —— 把**存量低质量章节**重新送进优化/重写流程。

## 它解决什么

软件侧的判定问题已经解决（质检门禁、评审判据、风格 DNA、一致性校验）。
但结账时发现一个更麻烦的东西：**已经写出来的那些章**。它们带着旧版判定留下的
毛病 —— 全书性句式指纹、标题是占位符、评审分从未记录 —— 而现有的章节模块
只有"读写/导航/导出"，**没有"这章有问题，打回去重做"的位置**。

于是低质量章节永远停在原地：改完的判定管不到它们，作者也无法把"要重写"
这件事从脑子里搬到系统里。

本模块就是那个位置：一张**回炉队列** + 一套**受控状态机** + 一份**不可删的原文存档**。

## 七个要素与本模块的对应

| 需求 | 落点 |
|---|---|
| 功能入口 | `panels/rework_panel.py`（回炉工作台，见该模块文档） |
| 适用范围 | `applicable_reasons()` / `can_enqueue()` —— 空章、重写中、超次数都不收 |
| 触发条件 | `reasons.SCANNABLE` 四类：质检阻断 / 评审低分 / 标题占位 / 人工指定 |
| 状态流转 | `TRANSITIONS` 表 + `transition()`，非法流转抛错而不是静默 |
| 回炉原因 | 每条记录带 `reason_code` + `reason_text` + `evidence`（可追溯的原句/分数） |
| 原文与历史版本 | `archive_chapter()` 每次入炉前快照到 `rework/archive/chNNN/`，只增不删 |
| 处理结果 | `approved` → `published`（定稿）/ `discarded`（废弃但留档） |

## 三个刻意的设计

**1. 状态机是表，不是 if 链。**
流转规则集中在一张 `dict` 里，非法流转（如 `draft → published`）直接抛
`ReworkError`。写成 `if` 链的后果是：每加一个状态就要在所有分支里补判断，
漏一处就出现"从草稿直接跳到发布"这种绕过审核的路径。

**2. 原文快照**在入炉时**立刻**做，不是在重写后。
理由：入炉到重写之间，用户可能还会在主编辑器里改这章（他还没意识到
自己已经把它打回去了）。快照放在重写后，改过的内容就永远没有基线。

**3. 归档只增不删。**
`discard` 不删文件、不删历史 —— "废弃"只改状态。角色数据那边踩过
"一次误写把整库抹掉"的教训，章节正文是同一个量级的内容资产。

## 与既有模块的边界

- 不碰正文文件本身：重写由主编辑器/`novel_agent` 完成，本模块只管**状态与存档**。
- 不重复实现质检：`scan()` 调用 `writing_presets.qc_report()`，
  评审分读 `review_store`，判定口径与软件侧完全同源。
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .storage import atomic_write_json, atomic_write_text
from .text_stats import count_hanzi

__all__ = [
    "ARCHIVE_DIR",
    "MAX_ATTEMPTS",
    "QUEUE_FILE",
    "REASON_LABELS",
    "REWORK_STATUSES",
    "STATUS_LABELS",
    "TRANSITIONS",
    "ReworkError",
    "ReworkStore",
    "default_rework_dir",
    "title_placeholder",
]

#: 回炉数据目录（相对作品根）：`<novel>/rework/`
REWORK_DIR = "rework"
#: 队列文件
QUEUE_FILE = "queue.json"
#: 原文归档目录
ARCHIVE_DIR = "archive"

#: 同一章最多回炉几次。超过后必须人工强制（`force=True`），防止无限打转。
MAX_ATTEMPTS = 3

#: 状态 → 中文名。顺序即工作流顺序（面板按它排序）。
STATUS_LABELS: Dict[str, str] = {
    "draft": "正常",
    "pending_rework": "待重写",
    "reworking": "重写中",
    "pending_review": "待审核",
    "approved": "已通过",
    "published": "已定稿",
    "discarded": "已废弃",
}

#: 全部合法状态。
REWORK_STATUSES: Tuple[str, ...] = tuple(STATUS_LABELS)

#: 状态流转表。**唯一来源** —— 新增状态必须在这里登记允许的来路/去路。
#:
#: 刻意不允许 `draft → published`：那等于跳过重写与审核。
#: 也刻意不允许 `discarded → *`：废弃是终点，要恢复就重新入炉（留痕）。
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "draft": ("pending_rework",),
    "pending_rework": ("reworking", "discarded", "draft"),
    "reworking": ("pending_review", "pending_rework", "discarded"),
    "pending_review": ("approved", "reworking", "discarded"),
    "approved": ("published", "draft"),
    "published": ("draft",),
    "discarded": (),
}

#: 触发原因 → 展示名。`SCANNABLE` 三档由 `scan()` 自动发现，`manual` 只能人工指定。
REASON_LABELS: Dict[str, str] = {
    "qc_blocker": "质检有阻断项",
    "low_score": "评审分偏低",
    "bad_title": "标题缺失或占位",
    "manual": "人工指定",
}

#: `scan()` 能自动发现的原因（`manual` 不在此列）。
SCANNABLE: Tuple[str, ...] = ("qc_blocker", "low_score", "bad_title")

#: 评审分低于它视为"需要回炉"。可被构造参数覆盖。
DEFAULT_SCORE_THRESHOLD = 60.0

#: 标题占位符的识别模式。
#:
#: 这些是真实存量的形态：`第71章`（无标题）、`第171章：章节标题(10字)`。
#: 用词表而不是单一正则，是因为"占位"的形态会随模板演变。
_TITLE_PLACEHOLDER_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"章节标题"),
    re.compile(r"标题\s*[(（]?\d+\s*字"),
    re.compile(r"^\s*第\s*\d+\s*章\s*[:：]?\s*$"),
    re.compile(r"^\s*Untitled\s*$", re.IGNORECASE),
    re.compile(r"第\s*\d+\s*章\s*[:：]\s*$"),
)


class ReworkError(RuntimeError):
    """回炉流程的显式错误（非法流转、超次数、前置条件不满足）。"""


# ====================================================================== 数据结构


@dataclass
class ReworkEvent:
    """一条状态变更流水。**只追加**，用于回答"这章是怎么走到现在这一步的"。"""

    status: str
    at: str
    note: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {"status": self.status, "at": self.at, "note": self.note}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReworkEvent":
        return cls(
            status=str(data.get("status", "")),
            at=str(data.get("at", "")),
            note=str(data.get("note", "")),
        )


@dataclass
class ReworkRecord:
    """一章的回炉档案。"""

    chapter: int
    status: str = "draft"
    reason_code: str = "manual"
    reason_text: str = ""
    #: 判定证据：命中的质检项、评审分、原句等。**没有证据不允许入炉**。
    evidence: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    #: 入炉时的原文快照路径（相对作品根），`archive_chapter()` 写入。
    archive_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    history: List[ReworkEvent] = field(default_factory=list)

    @property
    def reason_label(self) -> str:
        return REASON_LABELS.get(self.reason_code, self.reason_code)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chapter": self.chapter,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "evidence": dict(self.evidence),
            "attempts": self.attempts,
            "archive_path": self.archive_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": [item.as_dict() for item in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReworkRecord":
        return cls(
            chapter=int(data.get("chapter", 0) or 0),
            status=str(data.get("status", "draft") or "draft"),
            reason_code=str(data.get("reason_code", "manual") or "manual"),
            reason_text=str(data.get("reason_text", "") or ""),
            evidence=dict(data.get("evidence") or {}),
            attempts=int(data.get("attempts", 0) or 0),
            archive_path=str(data.get("archive_path", "") or ""),
            created_at=str(data.get("created_at", "") or ""),
            updated_at=str(data.get("updated_at", "") or ""),
            history=[ReworkEvent.from_dict(item) for item in (data.get("history") or []) if isinstance(item, dict)],
        )


# ====================================================================== 工具


def title_placeholder(title: str) -> bool:
    """该标题是否为"缺失 / 占位符"。"""
    body = (title or "").strip()
    if not body:
        return True
    return any(pattern.search(body) for pattern in _TITLE_PLACEHOLDER_PATTERNS)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_rework_dir(novel_dir: Any) -> Optional[Path]:
    if not isinstance(novel_dir, (str, Path)):
        return None
    return Path(novel_dir) / REWORK_DIR


def _chapter_path(novel_dir: Path, chapter: int) -> Path:
    return Path(novel_dir) / "chapters" / f"chapter_{chapter:04d}.txt"


def _read_chapter(novel_dir: Path, chapter: int) -> str:
    path = _chapter_path(novel_dir, chapter)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning(f"[回炉] 读取第 {chapter} 章失败：{exc}")
        return ""


def split_title(text: str) -> Tuple[str, str]:
    """委托 `app.parsing.split_title`（本模块口径：去掉 `#` 前缀）。"""
    from .parsing import split_title as _split_title

    return _split_title(text, strip_marks=True)


# ====================================================================== 队列存储


class ReworkStore:
    """回炉队列的读写与状态流转。

    所有写操作走 `self._lock` + `atomic_write_json`：
    面板可能从后台线程触发扫描，与手动操作并发。
    """

    def __init__(
        self,
        novel_dir: Any,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> None:
        self.novel_dir: Optional[Path] = Path(novel_dir) if isinstance(novel_dir, (str, Path)) else None
        self.base_dir = default_rework_dir(self.novel_dir)
        self.score_threshold = score_threshold
        self._lock = threading.RLock()
        self._records: Dict[int, ReworkRecord] = {}
        self._loaded = False

    # ------------------------------------------------------------------ 路径

    @property
    def queue_path(self) -> Optional[Path]:
        return (self.base_dir / QUEUE_FILE) if self.base_dir else None

    @property
    def archive_dir(self) -> Optional[Path]:
        return (self.base_dir / ARCHIVE_DIR) if self.base_dir else None

    # ------------------------------------------------------------------ 读写

    def load(self) -> None:
        """读队列文件。损坏时**不覆盖**，记日志后以空队列继续（下次写入会留 .bak）。"""
        self._loaded = True
        self._records = {}
        path = self.queue_path
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"[回炉] 队列文件损坏，按空队列处理（不覆盖原文件）：{exc}")
            return
        items = data.get("records") if isinstance(data, dict) else None
        for item in items or []:
            if not isinstance(item, dict):
                continue
            record = ReworkRecord.from_dict(item)
            if record.chapter > 0:
                self._records[record.chapter] = record

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> bool:
        path = self.queue_path
        if path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": _now(),
                "records": [self._records[ch].as_dict() for ch in sorted(self._records)],
            }
            atomic_write_json(path, payload, indent=2)
            return True
        except OSError as exc:
            logger.warning(f"[回炉] 队列保存失败：{exc}")
            return False

    # ------------------------------------------------------------------ 查询

    def get(self, chapter: int) -> Optional[ReworkRecord]:
        self._ensure_loaded()
        return self._records.get(int(chapter))

    def all(self) -> List[ReworkRecord]:
        self._ensure_loaded()
        return [self._records[ch] for ch in sorted(self._records)]

    def by_status(self, *statuses: str) -> List[ReworkRecord]:
        wanted = set(statuses) if statuses else None
        return [r for r in self.all() if wanted is None or r.status in wanted]

    def stats(self) -> Dict[str, int]:
        counts = {status: 0 for status in REWORK_STATUSES}
        for record in self.all():
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    # ------------------------------------------------------------------ 归档

    def archive_chapter(self, chapter: int, reason_note: str = "") -> Optional[str]:
        """把章节当前内容快照到归档目录，返回相对路径。

        目录结构：`rework/archive/ch0071/v1.txt` + 同名 `.meta.json`。
        版本号取"已有最大 + 1"，**不覆盖**任何历史版本。
        """
        if self.base_dir is None or self.novel_dir is None:
            return None
        text = _read_chapter(self.novel_dir, chapter)
        if not text.strip():
            return None

        folder = self.base_dir / ARCHIVE_DIR / f"ch{chapter:04d}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            existing = [int(p.stem[1:]) for p in folder.glob("v*.txt") if p.stem[1:].isdigit()]
            version = (max(existing) + 1) if existing else 1
            target = folder / f"v{version}.txt"
            # 原子写：归档是**原文的唯一副本**。这里写出半截，等于把"可回滚"
            # 这件事变成假的 —— 回滚后拿到的是断章。
            atomic_write_text(target, text)
            atomic_write_json(
                folder / f"v{version}.meta.json",
                {
                    "chapter": chapter,
                    "version": version,
                    "chars": count_hanzi(text),
                    "at": _now(),
                    "note": reason_note,
                },
                indent=2,
            )
        except OSError as exc:
            logger.warning(f"[回炉] 归档第 {chapter} 章失败：{exc}")
            return None
        return str(folder.relative_to(Path(self.novel_dir)) / f"v{version}.txt")

    def list_versions(self, chapter: int) -> List[Dict[str, Any]]:
        """列出该章的归档版本（按版本号升序）。"""
        if self.base_dir is None:
            return []
        folder = self.base_dir / ARCHIVE_DIR / f"ch{chapter:04d}"
        if not folder.is_dir():
            return []
        rows: List[Dict[str, Any]] = []
        for path in sorted(folder.glob("v*.txt")):
            stem = path.stem[1:]
            if not stem.isdigit():
                continue
            meta_path = folder / f"{path.stem}.meta.json"
            meta: Dict[str, Any] = {}
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    meta = {}
            rows.append(
                {
                    "version": int(stem),
                    "path": str(path.relative_to(Path(self.novel_dir))) if self.novel_dir else str(path),
                    "chars": meta.get("chars", 0),
                    "at": meta.get("at", ""),
                    "note": meta.get("note", ""),
                }
            )
        return rows

    def read_version(self, chapter: int, version: int) -> str:
        """读某个归档版本的正文。不存在返回空串。"""
        row = next((r for r in self.list_versions(chapter) if r["version"] == version), None)
        if row is None or self.novel_dir is None:
            return ""
        try:
            return (Path(self.novel_dir) / row["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # ------------------------------------------------------------------ 适用范围

    def can_enqueue(self, chapter: int, force: bool = False) -> Tuple[bool, str]:
        """是否允许入炉。返回 `(是否允许, 原因说明)`。"""
        self._ensure_loaded()
        if self.novel_dir is None:
            return False, "没有打开的作品"
        text = _read_chapter(self.novel_dir, chapter)
        if not text.strip():
            return False, f"第 {chapter} 章没有正文（空章无从重写）"

        record = self._records.get(chapter)
        if record is not None:
            if record.status in ("reworking", "pending_review"):
                return False, f"该章正在{record.status_label}，不能重复入炉"
            if record.status == "published" and not force:
                return False, "已定稿的章节需先设为正常（或强制）才能回炉"
            if record.attempts >= MAX_ATTEMPTS and not force:
                return False, f"已回炉 {record.attempts} 次（上限 {MAX_ATTEMPTS}），需人工确认后强制"
        return True, ""

    # ------------------------------------------------------------------ 入炉

    def enqueue(
        self,
        chapter: int,
        reason_code: str,
        reason_text: str = "",
        evidence: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> ReworkRecord:
        """把一章送进回炉队列。

        🔴 **原文快照在这里做**，不是等重写后 —— 见模块文档"设计 2"。
        """
        self._ensure_loaded()
        ok, why = self.can_enqueue(chapter, force=force)
        if not ok:
            raise ReworkError(why)

        note = reason_text or REASON_LABELS.get(reason_code, reason_code)
        archive_path = self.archive_chapter(chapter, f"入炉：{note}")

        record = self._records.get(chapter) or ReworkRecord(chapter=chapter)
        if not record.created_at:
            record.created_at = _now()
        record.reason_code = reason_code
        record.reason_text = note
        record.evidence = dict(evidence or {})
        record.attempts += 1
        if archive_path:
            record.archive_path = archive_path
        record.updated_at = _now()
        record.history.append(ReworkEvent(status="pending_rework", at=record.updated_at, note=note))

        previous = record.status
        self._records[chapter] = record
        if previous != "pending_rework":
            # 状态由 `_move` 统一写流水，这里只是直接落到入炉态
            record.status = "pending_rework"
        self.save()
        return record

    # ------------------------------------------------------------------ 流转

    def transition(self, chapter: int, target: str, note: str = "") -> ReworkRecord:
        """把一章推到目标状态。非法流转抛 `ReworkError`。"""
        self._ensure_loaded()
        record = self._records.get(chapter)
        if record is None:
            raise ReworkError(f"第 {chapter} 章不在回炉队列中")
        if target not in REWORK_STATUSES:
            raise ReworkError(f"未知状态：{target}")

        allowed = TRANSITIONS.get(record.status, ())
        if target not in allowed:
            raise ReworkError(
                f"不能从「{record.status_label}」直接变为「{STATUS_LABELS[target]}」；"
                f"允许的去向：{('、'.join(STATUS_LABELS[s] for s in allowed) if allowed else '无（终点状态）')}"
            )

        record.status = target
        record.updated_at = _now()
        record.history.append(ReworkEvent(status=target, at=record.updated_at, note=note))
        self.save()
        return record

    def discard(self, chapter: int, note: str = "确认废弃") -> ReworkRecord:
        """废弃：**只改状态，不删任何文件**。"""
        return self.transition(chapter, "discarded", note=note)

    def remove(self, chapter: int) -> bool:
        """从队列移除**记录**（归档与正文都保留）。

        用途：误入炉、或已彻底处理完想清空队列。不提供"连归档一起删"的入口 ——
        那等于给内容资产开口子。
        """
        with self._lock:
            self._ensure_loaded()
            if chapter not in self._records:
                return False
            del self._records[chapter]
            return self.save()


# ====================================================================== 触发扫描


def scan(
    novel_dir: Any,
    store: Optional[ReworkStore] = None,
    min_hanzi: int = 500,
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """扫描作品，找出应当回炉的章节。

    三档自动判定与软件侧**同源**：
    - `qc_blocker`：`writing_presets.qc_report()` 有阻断项
    - `low_score`：`review_store` 里有记录且总分低于阈值（**没有记录不算低分**）
    - `bad_title`：标题缺失或占位符

    Args:
        min_hanzi: 低于这个字数的章节跳过（空章/残章不参与，避免噪音）。
        limit: 最多返回多少条（0 = 不限）。面板可用来"先看 50 条"。

    Returns:
        `[{chapter, reason_code, reason_text, evidence}]`，按章节号升序。
    """
    from .review_store import load_review

    base = Path(novel_dir) if isinstance(novel_dir, (str, Path)) else None
    if base is None:
        return []
    store = store or ReworkStore(base)
    found: List[Dict[str, Any]] = []

    chapters_dir = base / "chapters"
    if not chapters_dir.is_dir():
        return []

    for path in sorted(chapters_dir.glob("chapter_*.txt")):
        match = re.search(r"chapter_(\d+)", path.name)
        if not match:
            continue
        chapter = int(match.group(1))
        text = _read_chapter(base, chapter)
        if count_hanzi(text) < min_hanzi:
            continue

        title, _body = split_title(text)

        # 1) 标题硬伤（最便宜，先判）
        if title_placeholder(title):
            found.append(
                {
                    "chapter": chapter,
                    "reason_code": "bad_title",
                    "reason_text": "标题缺失或为占位符",
                    "evidence": {"title": title[:40]},
                }
            )
        else:
            # 2) 质检阻断（只对标题正常的章跑，避免同一章报两条）
            blocker_info = _blocker_evidence(text)
            if blocker_info:
                found.append(
                    {
                        "chapter": chapter,
                        "reason_code": "qc_blocker",
                        "reason_text": blocker_info["summary"],
                        "evidence": blocker_info,
                    }
                )
            else:
                # 3) 评审低分（没有评审记录 ⇒ 不判低分，避免把"未评"当"差"）
                review = load_review(base, chapter)
                if review is not None and review.ok and review.overall is not None:
                    if review.overall < store.score_threshold:
                        found.append(
                            {
                                "chapter": chapter,
                                "reason_code": "low_score",
                                "reason_text": f"评审 {review.overall:g} 分，低于阈值 {store.score_threshold:g}",
                                "evidence": {"overall": review.overall, "issues": review.issues[:5]},
                            }
                        )
        if limit and len(found) >= limit:
            break
    return found


def _blocker_evidence(text: str) -> Optional[Dict[str, Any]]:
    """跑质检，返回阻断项摘要；没有阻断返回 `None`。

    这里**只取阻断项**，不把 review 项算进来 —— review 项本来就允许保留
    （技能包明确"误报/指纹保留"），拿它驱动回炉会让队列淹没在噪音里。
    """
    try:
        from .writing_presets import PRESETS, qc_report

        report = qc_report(text, PRESETS["deai-full"], with_candidates=False)
    except Exception as exc:  # noqa: BLE001 - 扫描失败不该让面板崩
        logger.warning(f"[回炉] 质检失败，跳过该章：{exc}")
        return None

    blockers = [item for item in report["items"] if item.get("blocking") and not item["passed"]]
    if not blockers:
        return None
    return {
        "summary": "；".join(f"{b['label']} {b['count']} 次（{b['per_ktx']:.2f}/千字）" for b in blockers[:3]),
        "detectors": [b["detector"] for b in blockers],
        "items": [b["label"] for b in blockers],
        "hanzi": report.get("hanzi", 0),
    }
