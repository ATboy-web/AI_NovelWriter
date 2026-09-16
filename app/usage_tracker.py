"""用量归因与持久化（v3 §3.5）。

## 三件事

1. **归因**：一次 AI 调用属于「哪本书、哪一章、哪个任务（大纲/正文/审校/传记/摘要）」。
   用 `contextvars.ContextVar` 承载，**不侵入 53 个调用点**：
   由 `novel_agent.generate_chapter` 设置 `chapter=N`，UI 面板设置 `task="biography"`，
   adapter 解析到 usage 时读取该上下文完成归因。

2. **持久化**（v2 完全没有，重启即失）::

       novels/<名>/usage/usage.jsonl     # 追加式明细，每行一条调用记录
       novels/<名>/usage/summary.json    # 聚合（走 storage 原子写）

3. **成本**：接 `app/providers/pricing.py` 的价目表，`cost` 与 `cost_currency`
   落进每条记录。币种不同的成本**绝不相加** —— 所以聚合里是 `{"CNY": x, "USD": y}`。

## ⚠️ contextvars 与线程

`contextvars` 在 `threading.Thread` 里**不会继承**父上下文（与 asyncio 不同）。
本仓 40 处手工线程全部改走 `app.async_runner`，那里统一做了
`copy_context()` —— 所以只要线程是用 `BackgroundRunner.submit` 起的，
归因上下文就一定正确。
"""

from __future__ import annotations

import contextvars
import csv
import functools
import inspect
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .events import TOPIC_AI_USAGE
from .storage import atomic_write_json

__all__ = [
    "USAGE_DIR_NAME",
    "USAGE_DETAIL_FILE",
    "USAGE_SUMMARY_FILE",
    "SUMMARY_VERSION",
    "UsageTracker",
    "usage_tracker",
    "usage_context",
    "current_usage_context",
    "set_usage_context",
    "reset_usage_context",
    "clear_usage_context",
    "task_tracker",
    "new_bucket",
]

#: 小说目录下的用量子目录
USAGE_DIR_NAME = "usage"
#: 明细文件名（追加式 JSONL）
USAGE_DETAIL_FILE = "usage.jsonl"
#: 聚合文件名（原子写）
USAGE_SUMMARY_FILE = "summary.json"
#: 聚合结构版本（将来改结构时可据此迁移）
SUMMARY_VERSION = 1

#: 归因上下文。值形如
#: `{"novel_dir": "...", "chapter": 12, "task": "chapter", "generation": "..."}`
_CTX: contextvars.ContextVar = contextvars.ContextVar("anw_usage_ctx", default=None)

#: JSONL 追加锁（跨线程；一次追加必须完整落盘，不能交错）
_APPEND_LOCK = threading.Lock()


# ==================================================================== 归因上下文


def set_usage_context(**fields):
    """设置归因字段，返回可用于 `reset_usage_context` 的 token。

    值为 `None` 的键会被忽略 —— 这样调用方可以无脑传
    `chapter=self.current_chapter or None`，不必先判空。
    """
    current = dict(_CTX.get() or {})
    for key, value in fields.items():
        if value is None:
            continue
        current[key] = value
    return _CTX.set(current)


def reset_usage_context(token) -> None:
    """还原到 `set_usage_context` 之前的状态。"""
    try:
        _CTX.reset(token)
    except (ValueError, LookupError, RuntimeError):
        # token 已被本上下文用过（`ContextVar.reset` 这时抛 RuntimeError）、
        # 或来自别的上下文（ValueError）—— 忽略，不因清理失败影响业务。
        pass


def current_usage_context() -> dict:
    """读取当前归因上下文（副本，改它不影响上下文）。"""
    return dict(_CTX.get() or {})


def clear_usage_context() -> None:
    """把归因上下文彻底清空。

    与 `reset_usage_context(token)` 的分工：后者用于"恢复到进入前"，
    前者用于"无论之前是什么，从现在起什么都不归属" —— 例如一个长驻的
    子线程完成一本书的活、准备接下一本时。
    """
    _CTX.set({})


@contextmanager
def usage_context(**fields):
    """`with usage_context(chapter=3, task="outline"): ...` —— 退出时自动还原。"""
    token = set_usage_context(**fields)
    try:
        yield
    finally:
        reset_usage_context(token)


def task_tracker(task: str, chapter_param: str = ""):
    """方法装饰器：把该方法执行期间的所有 AI 调用归因到 `task`。

    采用装饰器而不是改方法体，是刻意的：「Mixin 拆分以 AST span 逐字节复制
    证明行为不变」是本项目的既定审计口径，装饰器只增加一行、**方法体一字不动**，
    而 `functools.wraps` 保住 `__name__` / `__doc__` / `__wrapped__`
    （`inspect.signature` 仍返回原签名），对外可观察面不变。

    `chapter_param` 给出「章号从哪个参数取」（如 `"chapter_num"`）；
    取不到或为 `None` 时不写 `chapter` 字段 —— 不猜。
    """
    def decorate(fn):
        index = None
        if chapter_param:
            params = list(inspect.signature(fn).parameters)
            if chapter_param in params:
                index = params.index(chapter_param)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            chapter = None
            if index is not None:
                if index < len(args):
                    chapter = args[index]
                else:
                    chapter = kwargs.get(chapter_param)
            elif chapter_param:
                chapter = kwargs.get(chapter_param)
            with usage_context(task=task, chapter=chapter):
                return fn(*args, **kwargs)

        return wrapper

    return decorate


# ==================================================================== 聚合桶


def new_bucket() -> dict:
    """一个空的聚合桶（按章 / 按 provider / 按任务 / 按模型 共用同一形状）。"""
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "estimated_calls": 0,
        "errors": 0,
        "latency_ms": 0.0,
        #: 币种 → 金额。**不同币种绝不相加**（v3 §9.9 第 3 条）
        "costs": {},
        #: 出现过的 provider / model / task（去重后按字典序，便于稳定展示）
        "providers": [],
        "models": [],
        "tasks": [],
    }


def _accumulate(bucket: dict, record: dict) -> None:
    bucket["calls"] += 1
    bucket["prompt_tokens"] += int(record.get("prompt_tokens") or 0)
    bucket["completion_tokens"] += int(record.get("completion_tokens") or 0)
    bucket["total_tokens"] += int(record.get("total_tokens") or 0)
    bucket["cached_tokens"] += int(record.get("cached_tokens") or 0)
    bucket["latency_ms"] += float(record.get("latency_ms") or 0.0)
    if record.get("estimated"):
        bucket["estimated_calls"] += 1
    if record.get("ok") is False:
        bucket["errors"] += 1

    currency = record.get("cost_currency") or ""
    cost = float(record.get("cost") or 0.0)
    if currency and cost:
        bucket["costs"][currency] = bucket["costs"].get(currency, 0.0) + cost

    for key, field in (("providers", "provider"), ("models", "model"), ("tasks", "task")):
        value = record.get(field) or ""
        if value and value not in bucket[key]:
            bucket[key].append(value)
            bucket[key].sort()


# ==================================================================== 追踪器


class UsageTracker:
    """用量明细与聚合的读写入口。

    设计要点：

    - **没有当前小说目录时只进内存**（最多 `MEMORY_LIMIT` 条）——
      用户在"还没打开小说"时也能看到本次会话消耗，与 v2 的全局累计一致。
    - **明细追加不读全文件**：`usage.jsonl` 只 `open('a')` 追加，
      5000 章场景下也不会因为读全量明细而卡住。
    - **聚合走内存增量 + 原子写 summary.json**，不每次重算全量。
    """

    #: 无小说目录时的内存缓冲上限
    MEMORY_LIMIT = 2000

    def __init__(self):
        self._lock = threading.RLock()
        self._novel_dir: Path | None = None
        self._memory: list = []
        self._summary: dict | None = None
        self._summary_dir: Path | None = None
        # v3 P4：领域事件出口（见 set_event_sink / _emit_usage_event）。
        # 默认 None = 不广播，因此本模块在单测、CLI 与后端服务里保持零副作用。
        self._event_sink = None

    # ------------------------------------------------------------ 事件出口

    def set_event_sink(self, sink) -> None:
        """接入事件出口：每条记录落盘后广播 `ai.usage`。

        `sink` 只需具备 `publish(topic, payload)` —— 与 `NovelStore(events=...)`
        （v3 A7）和 `MemoryManager.set_event_sink()` 是**同一套鸭子类型约定**。
        应用传的是 `EventBus.sink()` 门面，它内部按调用线程自动选路
        （AI 调用几乎都发生在后台线程，而 Tk 只能在主线程碰）。
        """
        self._event_sink = sink

    def _emit_usage_event(self, record: dict) -> None:
        """广播一条 `ai.usage`；广播失败绝不影响记账。"""
        sink = self._event_sink
        if sink is None:
            return
        try:
            sink.publish(TOPIC_AI_USAGE, record)
        except Exception:  # noqa: BLE001 - 广播是尽力而为的旁路
            pass

    # ------------------------------------------------------------ 目录

    @property
    def novel_dir(self) -> Path | None:
        return self._novel_dir

    def set_novel_dir(self, novel_dir) -> None:
        """切换当前小说（打开/新建/切换小说时调用）。`None` 表示回到内存模式。"""
        new_dir = Path(novel_dir) if novel_dir else None
        with self._lock:
            if new_dir == self._novel_dir:
                return
            self._novel_dir = new_dir
            # 切书必须丢缓存，否则会把 A 书的聚合显示到 B 书
            self._summary = None
            self._summary_dir = None

    def usage_dir(self, novel_dir=None) -> Path | None:
        target = Path(novel_dir) if novel_dir else self._novel_dir
        return target / USAGE_DIR_NAME if target else None

    # ------------------------------------------------------------ 记录

    def record(
        self,
        *,
        provider: str = "",
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        estimated: bool = False,
        latency_ms: float = 0.0,
        task: str = "",
        chapter=None,
        generation=None,
        ok: bool = True,
        region: str = "default",
        ts: float | None = None,
    ) -> dict:
        """写入一条调用记录，返回落盘的记录字典。

        归因字段（`chapter` / `task` / `generation`）未显式传入时，
        从当前上下文补全 —— 这是"53 个调用点零改动"的关键。
        """
        ctx = current_usage_context()
        if chapter is None:
            chapter = ctx.get("chapter")
        if not task:
            task = ctx.get("task") or ""
        if generation is None:
            generation = ctx.get("generation")

        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)

        cost_est = self._estimate_cost(
            provider, model, prompt_tokens, completion_tokens, cached_tokens,
            estimated, region,
        )

        record = {
            "ts": float(ts if ts is not None else time.time()),
            "time": datetime.fromtimestamp(
                float(ts if ts is not None else time.time())
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider or "",
            "model": model or "",
            "chapter": int(chapter) if isinstance(chapter, (int, float)) else chapter,
            "generation": generation,
            "task": task,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cached_tokens": int(cached_tokens or 0),
            "estimated": bool(estimated),
            "latency_ms": round(float(latency_ms or 0.0), 2),
            "cost": round(float(cost_est.cost), 8),
            "cost_currency": cost_est.currency,
            "cost_reliable": bool(cost_est.reliable),
            "ok": bool(ok),
        }

        with self._lock:
            # ⚠️ 顺序有意义：必须**先**载入/重建聚合快照，**再**追加明细。
            # 反过来会双重计数 —— 因为"重建"是读 `usage.jsonl` 得来的，
            # 若明细里已经有本条，重建结果就含它一次，随后 `_accumulate`
            # 又加一次，于是每次冷启动的第一条记录都被算两遍。
            summary = self._ensure_summary_locked()
            self._append_detail(record)
            self._memory.append(record)
            if len(self._memory) > self.MEMORY_LIMIT:
                del self._memory[: len(self._memory) - self.MEMORY_LIMIT]

            _accumulate(summary["totals"], record)
            self._accumulate_into_groups(summary, record)
            summary["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._persist_summary(summary)

        # v3 P4：落盘之后再广播 —— 订阅方（用量面板/状态栏）读到的一定是已记账的数据
        self._emit_usage_event(record)
        return record

    def _ensure_summary_locked(self) -> dict:
        """在持锁状态下拿到当前小说的聚合快照（必要时从磁盘载入或重建）。

        调用方必须已经持有 `self._lock`。
        """
        if self._summary is not None and self._summary_dir == self._novel_dir:
            return self._summary
        self._summary = self._load_summary(self._novel_dir)
        self._summary_dir = self._novel_dir
        return self._summary

    @staticmethod
    def _estimate_cost(provider, model, prompt_tokens, completion_tokens,
                       cached_tokens, estimated, region):
        """接价目表算成本。**失败绝不影响记账** —— 用量数据本身比成本更重要。"""
        try:
            from .providers.pricing import estimate_cost

            return estimate_cost(
                provider, model, prompt_tokens, completion_tokens,
                cached_tokens=cached_tokens, estimated=estimated, region=region,
            )
        except Exception:                       # noqa: BLE001 - 成本是增值项，不是必需项
            from .providers.pricing import CostEstimate

            return CostEstimate()

    # ------------------------------------------------------------ 明细落盘

    def _append_detail(self, record: dict) -> None:
        usage_dir = self.usage_dir()
        if usage_dir is None:
            return
        try:
            usage_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False)
            with _APPEND_LOCK:
                with open(usage_dir / USAGE_DETAIL_FILE, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    try:
                        os.fsync(handle.fileno())
                    except OSError:
                        pass
        except OSError:
            # 磁盘写不进去（权限/盘满）不能反过来弄崩生成流程
            pass

    # ------------------------------------------------------------ 聚合

    def summary(self, novel_dir=None) -> dict:
        """取聚合结果。首次访问时从 `summary.json` 载入，不存在则从明细重建。"""
        target = Path(novel_dir) if novel_dir else self._novel_dir
        with self._lock:
            if self._summary is not None and self._summary_dir == target:
                return self._summary
            self._summary = self._load_summary(target)
            self._summary_dir = target
            return self._summary

    def _load_summary(self, target: Path | None) -> dict:
        if target is None:
            return self._rebuild_summary([])
        path = target / USAGE_DIR_NAME / USAGE_SUMMARY_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("version") == SUMMARY_VERSION:
                    return data
            except (OSError, ValueError):
                pass
        # summary 缺失/损坏/版本不符 → 从明细重建，绝不返回空聚合
        return self._rebuild_summary(self.read_records(target))

    def _rebuild_summary(self, records) -> dict:
        summary = self._blank_summary()
        for record in records:
            if not isinstance(record, dict):
                continue
            _accumulate(summary["totals"], record)
            self._accumulate_into_groups(summary, record)
        summary["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return summary

    @staticmethod
    def _blank_summary() -> dict:
        return {
            "version": SUMMARY_VERSION,
            "updated_at": "",
            "totals": new_bucket(),
            "by_chapter": {},
            "by_provider": {},
            "by_model": {},
            "by_task": {},
        }

    @staticmethod
    def _accumulate_into_groups(summary: dict, record: dict) -> None:
        chapter = record.get("chapter")
        if isinstance(chapter, (int, float)):
            key = str(int(chapter))
            _accumulate(summary["by_chapter"].setdefault(key, new_bucket()), record)
        provider = record.get("provider") or ""
        if provider:
            _accumulate(summary["by_provider"].setdefault(provider, new_bucket()), record)
        model = record.get("model") or ""
        if model:
            _accumulate(summary["by_model"].setdefault(model, new_bucket()), record)
        task = record.get("task") or ""
        if task:
            _accumulate(summary["by_task"].setdefault(task, new_bucket()), record)

    def _persist_summary(self, summary: dict) -> None:
        usage_dir = self.usage_dir()
        if usage_dir is None:
            return
        try:
            atomic_write_json(usage_dir / USAGE_SUMMARY_FILE, summary, backup=False)
        except OSError:
            pass

    # ------------------------------------------------------------ 读取

    def read_records(self, novel_dir=None, limit: int | None = None) -> list:
        """读取明细。`limit` 为「最近 N 条」（尾部截取，不是头部）。"""
        target = Path(novel_dir) if novel_dir else self._novel_dir
        if target is None:
            with self._lock:
                records = list(self._memory)
            return records[-limit:] if limit else records

        path = target / USAGE_DIR_NAME / USAGE_DETAIL_FILE
        if not path.exists():
            return []
        records = []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        # 单行损坏（写一半断电）不应毁掉整个文件的可读性
                        continue
        except OSError:
            return []
        return records[-limit:] if limit else records

    def chapter_rows(self, novel_dir=None) -> list:
        """按章聚合，返回按章号排序的行（供面板 Treeview 直接消费）。"""
        summary = self.summary(novel_dir)
        rows = []
        for key, bucket in (summary.get("by_chapter") or {}).items():
            try:
                chapter_no = int(key)
            except (TypeError, ValueError):
                chapter_no = 0
            rows.append({"chapter": chapter_no, **bucket})
        rows.sort(key=lambda row: row["chapter"])
        return rows

    def chapter_tokens(self, novel_dir=None) -> dict:
        """`{章号: 总 token}` —— 供章节列表徽标用（O(1) 查表）。"""
        return {
            row["chapter"]: int(row.get("total_tokens") or 0)
            for row in self.chapter_rows(novel_dir)
        }

    # ------------------------------------------------------------ 导出

    CSV_FIELDS = (
        "time", "provider", "model", "chapter", "generation", "task",
        "prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
        "estimated", "latency_ms", "cost", "cost_currency", "ok",
    )

    def export_csv(self, path, novel_dir=None) -> Path:
        """导出明细为 CSV（UTF-8 BOM，Excel 直接双击不乱码）。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        records = self.read_records(novel_dir)
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.CSV_FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        return path

    # ------------------------------------------------------------ 展示辅助

    @staticmethod
    def format_costs(costs: dict) -> str:
        """把 `{"CNY": 0.0123, "USD": 0.004}` 渲染成 `¥0.0123 + $0.0040`。

        空字典 → `"—"`；同时保留"未定价"的语义（不伪装成 0 元）。
        """
        if not costs:
            return "—"
        symbols = {"CNY": "¥", "USD": "$"}
        parts = []
        for currency in sorted(costs):
            amount = costs[currency]
            parts.append(f"{symbols.get(currency, currency + ' ')}{amount:.4f}")
        return " + ".join(parts)

    def reset_memory(self) -> None:
        """清空内存缓冲（测试与"清除本次会话统计"用）。不删磁盘数据。"""
        with self._lock:
            self._memory.clear()
            self._summary = None
            self._summary_dir = None


#: 全局单例。之所以是全局的：`AIClient` 有多个实例（每次改配置都会重建），
#: 而归因与统计必须跨实例连续。
usage_tracker = UsageTracker()
