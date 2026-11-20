"""整书重写引擎 —— 「全书重写」功能的后端。

## 它是什么

把一个**已完成但质量不达标**的作品，按章逐块交给模型重写文字表达。
与「回炉重造」的分工：

| | 回炉重造（`rework.py`） | 整书重写（本模块） |
|---|---|---|
| 干什么 | 把章**打回队列**，改状态、留原文 | 真的**调用模型**重写正文 |
| 谁执行重写 | 作者/主编辑器 | 本模块 |
| 结果 | 队列状态 | `chapters_rewritten/` 新文件 |

两者串起来就是完整流水线：扫描（`rework.scan`）→ 全书写入队列 → 本模块批量重写 →
回炉面板审核 → 定稿/废弃。

## 三条硬约束

1. **绝不覆盖原文**。输出写到 `chapters_rewritten/`，`chapters/` 一个字不动。
2. **断点续跑**。`rewrite_log.json` 逐章记状态（`done`/`failed`/`skipped`），
   中断或取消后重跑只补未完成的。判据是「内容指纹 + 状态」双条件：
   原文改过了，即使记着 `done` 也会重做。
3. **可暂停、可取消**。用 `CancelToken`（协作式）+ 暂停标志（`threading.Event`）。
   检查点只放在**块与块之间** —— 不放在一次 HTTP 请求中间，否则退出时请求还在飞。

## 为什么分段不用「续写」

`max_tokens` 默认 4096（约 2400 汉字），单章 1.4 万字一轮写不完。分段有两种：

| 方式 | 后果 |
|---|---|
| 生成式续写（给开头让它往下写） | 模型自由发挥，上千章情节必然漂移 |
| **按原段落切块，逐块改写** | 段落数与顺序不变，只可能"表达变化" |

本模块选后者：**原章正文就是事实骨架**，提示词明确禁止改情节/人物/对话/专名。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from .async_runner import CancelledError, CancelToken
from .rework import ReworkError
from .storage import atomic_write_json, atomic_write_text
from .text_stats import count_hanzi

__all__ = [
    "BulkPlan",
    "BulkProgress",
    "BulkRewriter",
    "BulkStats",
    "CHUNK_HANZI",
    "OUTPUT_DIR",
    "REWRITE_LOG",
    "SYSTEM_PROMPT",
]

#: 每块目标汉字数。取 1800：`max_tokens=4096` 下模型输出约 2000–2400 汉字，
#: 留余量避免被截断（截断会把段落切在半句上，是最难修的一种坏）。
CHUNK_HANZI = 1800

#: 每块最大尝试次数。
MAX_CHUNK_TRIES = 3

#: 上一章末尾取多少字给模型看衔接点。
PREV_TAIL_CHARS = 600

#: 输出目录（相对作品根）。
OUTPUT_DIR = "chapters_rewritten"

#: 断点续跑日志。
REWRITE_LOG = "rewrite_log.json"

#: 单块预计耗时（秒），仅用于进度预估。
SECONDS_PER_CHUNK = 75

SYSTEM_PROMPT = """你是资深中文网络小说编辑，负责把一个已完成的章节**重新誊写**。

## 你的任务边界（违反即任务失败）
你拿到的是原章正文。你的工作是**改写文字表达**，不是重新创作：
1. **情节必须完全一致**：事件顺序、因果、场景转换一处不改。
2. **人物言行必须一致**：谁做了什么、说了什么（对话的意思）、去了哪里，一律不变。
3. **设定与专名必须一致**：人名、地名、功法名、势力名、境界名、道具名原样保留。
4. **篇幅相当**：改写后字数不低于原文的 85%，不高于 115%。
5. **段落顺序不变**：输入几段，输出就几段，按顺序对应。

## 文字层面的要求
- 去掉机械的句式模板：不要「不是……而是……」「与其说……不如说……」这类对举套式。
  需要下判断就直接下。
- 不要用「这意味着」「换句话说」「说白了」这类解释性插入语开头。
- 句子长度自然变化，不要为了"有节奏"刻意把句子写短或写长。
- 保留原文的信息密度：数字、限定词（可能/通常/多数）、引语都要留住。
- 不要添加原文没有的比喻、心理独白、环境描写；也不要删掉原有关键细节。

## 输出格式
只输出改写后的正文段落，段落之间**空一行**。
不要输出任何说明、标题、编号、注释、markdown 标记。
不要输出「以下是改写结果」这类开场白。"""


# ====================================================================== 数据结构


@dataclass
class BulkPlan:
    """执行前的规模预估 —— 让用户在点"开始"之前知道要花多少时间。"""

    chapters: int = 0
    chunks: int = 0
    hanzi: int = 0
    todo_chapters: int = 0
    done_chapters: int = 0

    @property
    def estimated_minutes(self) -> float:
        return round(self.chunks * SECONDS_PER_CHUNK / 60, 1)

    @property
    def estimated_text(self) -> str:
        """人读的耗时预估。超过 2 小时就换算成小时 —— 「11949 分钟」没人能直观理解。"""
        minutes = self.estimated_minutes
        if minutes < 120:
            return f"约 {minutes:.0f} 分钟"
        hours = minutes / 60
        if hours < 48:
            return f"约 {hours:.0f} 小时"
        return f"约 {hours / 24:.1f} 天"

    def as_text(self) -> str:
        return (
            f"共 {self.chapters} 章 / {self.hanzi:,} 汉字，切 {self.chunks} 块；"
            f"已完成 {self.done_chapters} 章，本次待处理 {self.todo_chapters} 章；"
            f"串行预计 {self.estimated_text}"
        )


@dataclass
class BulkProgress:
    """一次进度回调。面板据此刷新进度条与状态行。"""

    status: str = "running"  # running / paused / done / failed / cancelled
    chapter: int = 0
    chapter_index: int = 0
    total_chapters: int = 0
    chunk_index: int = 0
    total_chunks: int = 0
    hanzi_before: int = 0
    hanzi_after: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0
    elapsed: float = 0.0
    message: str = ""

    @property
    def percent(self) -> float:
        if not self.total_chapters:
            return 0.0
        return min(100.0, self.chapter_index / self.total_chapters * 100)

    def as_line(self) -> str:
        if self.status == "paused":
            return f"已暂停 · 第 {self.chapter_index}/{self.total_chapters} 章"
        if self.status == "done":
            return f"完成 {self.done} 章 · 失败 {self.failed} · 跳过 {self.skipped} · {self.elapsed / 60:.1f} 分钟"
        if self.status == "cancelled":
            return f"已取消 · 完成 {self.done} 章 · {self.elapsed / 60:.1f} 分钟"
        head = f"第 {self.chapter} 章（{self.chapter_index}/{self.total_chapters}）"
        if self.total_chunks:
            head += f" · 第 {self.chunk_index}/{self.total_chunks} 块"
        return f"{head} · 已完成 {self.done} 章 · {self.elapsed / 60:.1f} 分钟"


@dataclass
class BulkStats:
    done: int = 0
    failed: int = 0
    skipped: int = 0
    hanzi_before: int = 0
    hanzi_after: int = 0
    seconds: float = 0.0
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)

    def as_text(self) -> str:
        return (
            f"完成 {self.done} · 失败 {self.failed} · 跳过 {self.skipped}；"
            f"字数 {self.hanzi_before:,} → {self.hanzi_after:,}；"
            f"调用 {self.calls} 次，token 输入 {self.prompt_tokens:,} / 输出 {self.completion_tokens:,}"
        )


# ====================================================================== 工具函数


def split_title(text: str) -> Tuple[str, str]:
    lines = (text or "").splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if first.startswith("#"):
        return first, "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def split_paragraphs(body: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]


def chunk_paragraphs(paragraphs: Sequence[str], target: int = CHUNK_HANZI) -> List[List[str]]:
    """按目标字数聚块，**不切断段落** —— 断在段落中间模型接不上。"""
    chunks: List[List[str]] = []
    current: List[str] = []
    size = 0
    for paragraph in paragraphs:
        length = count_hanzi(paragraph)
        if current and size + length > target:
            chunks.append(current)
            current, size = [], 0
        current.append(paragraph)
        size += length
    if current:
        chunks.append(current)
    return chunks


def clean_output(text: str) -> str:
    """去掉模型可能的开场白/围栏/分隔线，保留正文段落。"""
    body = str(text or "").strip()
    if not body:
        return ""
    body = re.sub(r"^```[a-zA-Z]*\s*", "", body)
    body = re.sub(r"\s*```$", "", body)
    first_line, _, rest = body.partition("\n")
    if rest and re.match(r"^[\s*#]*(以下|下面|这是|改写后|重写后)", first_line.strip()):
        body = rest.strip()
    body = "\n".join(line for line in body.splitlines() if not re.fullmatch(r"\s*[-*_]{3,}\s*", line))
    return body.strip()


# ====================================================================== 主引擎


class BulkRewriter:
    """整书重写。线程安全性由"同一时刻只允许一个实例"保证（面板侧持锁）。"""

    def __init__(
        self,
        novel_dir: Any,
        ai_client: Any,
        output_dir: Optional[Path] = None,
        chunk_hanzi: int = CHUNK_HANZI,
        force: bool = False,
    ) -> None:
        self.novel_dir: Optional[Path] = Path(novel_dir) if isinstance(novel_dir, (str, Path)) else None
        self.chapters_dir = (self.novel_dir / "chapters") if self.novel_dir else None
        self.out_dir = output_dir or ((self.novel_dir / OUTPUT_DIR) if self.novel_dir else None)
        self.ai = ai_client
        self.chunk_hanzi = max(400, int(chunk_hanzi))
        self.force = force

        self.stats = BulkStats()
        self._log_path = (self.novel_dir / REWRITE_LOG) if self.novel_dir else None
        self._log: Dict[str, Any] = {"version": 1, "chapters": {}}
        self._log_lock = threading.RLock()

        #: 暂停标志。置位时在**块之间**等待，不打断进行中的请求。
        self._pause_event = threading.Event()
        self._pause_event.set()  # set = 允许运行
        self._style_cache: Optional[str] = None

    # ------------------------------------------------------------------ 前置

    def check_ready(self) -> Tuple[bool, str]:
        """结构就绪检查（作品目录 + 章节）。

        刻意**不在这里查 AI**：`plan()` 是纯统计，dry-run 与"看规模"都不需要模型。
        AI 可用性由 `check_ai()` 单独实测，执行时 `run()` 自己兜。
        """
        if self.novel_dir is None or self.chapters_dir is None or not self.chapters_dir.is_dir():
            return False, "没有打开的作品（或作品缺少 chapters 目录）"
        if not self.chapter_files():
            return False, "作品里没有章节文件"
        return True, ""

    def check_ai(self) -> Tuple[bool, str]:
        """真的发一次极小请求确认模型可用。

        为什么必须实测而不是看配置：配置里有 key ≠ key 有效。
        本机就出现过"配置文件有 35 字符的明文 key，但服务端回 401"的情况 ——
        不实测的话，用户会在点了"开始"之后看 1094 章连续失败。
        """
        if self.ai is None:
            return False, "没有可用的 AI 客户端"
        try:
            self.ai.chat([{"role": "user", "content": "回复一个字：好"}], max_tokens=8)
            return True, ""
        except Exception as exc:  # noqa: BLE001 - 任何异常都意味着不可用
            return False, f"AI 调用失败：{str(exc)[:160]}"

    # ------------------------------------------------------------------ 计划

    def chapter_files(self) -> List[Tuple[int, Path]]:
        if self.chapters_dir is None:
            return []
        rows: List[Tuple[int, Path]] = []
        for path in sorted(self.chapters_dir.glob("chapter_*.txt")):
            match = re.search(r"chapter_(\d+)", path.name)
            if match:
                rows.append((int(match.group(1)), path))
        rows.sort()
        return rows

    def load_log(self) -> None:
        if self._log_path is None or not self._log_path.is_file():
            return
        try:
            data = json.loads(self._log_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and isinstance(data.get("chapters"), dict):
            self._log = data

    def plan(self) -> BulkPlan:
        self.load_log()
        plan = BulkPlan()
        for number, path in self.chapter_files():
            try:
                body = split_title(path.read_text(encoding="utf-8", errors="replace"))[1]
            except OSError:
                continue
            hanzi = count_hanzi(body)
            if hanzi == 0:
                continue
            chunks = len(chunk_paragraphs(split_paragraphs(body), self.chunk_hanzi))
            plan.chapters += 1
            plan.hanzi += hanzi
            plan.chunks += chunks
            if self._is_done(number, body):
                plan.done_chapters += 1
            else:
                plan.todo_chapters += 1
        return plan

    # ------------------------------------------------------------------ 控制

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    @property
    def paused(self) -> bool:
        return not self._pause_event.is_set()

    def _wait_if_paused(self, token: Optional[CancelToken]) -> None:
        """在块之间等暂停。等待期间仍响应取消。"""
        while not self._pause_event.is_set():
            if token is not None:
                token.raise_if_cancelled()
            time.sleep(0.2)

    # ------------------------------------------------------------------ 日志

    @staticmethod
    def _fingerprint(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _is_done(self, chapter: int, body: str) -> bool:
        if self.force:
            return False
        record = self._log["chapters"].get(str(chapter)) or {}
        return record.get("status") == "done" and record.get("fingerprint") == self._fingerprint(body)

    def _record(self, chapter: int, status: str, **extra: Any) -> None:
        if self._log_path is None:
            return
        with self._log_lock:
            row = {"status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            row.update(extra)
            self._log["chapters"][str(chapter)] = row
            try:
                # 🔴 原子写：这份日志是**断点续跑的唯一依据**。
                # 裸写被杀会留下半截 JSON ⇒ 下次读不出来 ⇒ 已重写过的章全部重做，
                # 那是真金白银的重复模型调用。
                atomic_write_json(self._log_path, self._log, indent=2)
            except OSError as exc:
                logger.warning(f"[整书重写] 日志写入失败：{exc}")

    # ------------------------------------------------------------------ 上下文

    def _prev_tail(self, chapter: int) -> str:
        if self.chapters_dir is None:
            return ""
        prev = self.chapters_dir / f"chapter_{chapter - 1:04d}.txt"
        if not prev.is_file():
            return ""
        try:
            body = split_title(prev.read_text(encoding="utf-8", errors="replace"))[1]
        except OSError:
            return ""
        return body[-PREV_TAIL_CHARS:]

    def _style_block(self) -> str:
        """风格约束（全书同一份）—— 这是"风格统一"的落点。"""
        if self._style_cache is not None:
            return self._style_cache
        try:
            from .writing_presets import PRESETS

            rules = "\n".join(f"- {item}" for item in PRESETS["deai-full"].norms)
            self._style_cache = f"\n## 本次誊写的风格纪律\n{rules}\n"
        except Exception:  # noqa: BLE001 - 预设不可用不该中断重写
            self._style_cache = ""
        return self._style_cache

    # ------------------------------------------------------------------ 单块

    def _ask(self, prompt: str) -> Tuple[str, Dict[str, int]]:
        """一次模型调用，返回 `(文本, token 用量)`。

        token 用量取模块级 `token_stats` 的**前后差值** —— 它是累计计数器，
        直接读会得到历史总量。
        """
        from . import ai_client as ai_module

        before = ai_module.token_stats.get_summary()
        response = self.ai.chat(
            [{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT + self._style_block(),
            max_tokens=4096,
            temperature=0.7,
        )
        after = ai_module.token_stats.get_summary()
        return str(response or ""), {
            "prompt": after["prompt_tokens"] - before["prompt_tokens"],
            "completion": after["completion_tokens"] - before["completion_tokens"],
        }

    def rewrite_chunk(
        self,
        chapter: int,
        chunk: Sequence[str],
        index: int,
        prev_tail: str,
        before: str,
        after: str,
        token: Optional[CancelToken] = None,
    ) -> Tuple[bool, str, str]:
        """重写一块。返回 `(是否成功, 文本, 错误)`。

        字数比例超出 75%–135% 视为失败并重试：比例异常通常意味着模型
        偷工（漏写细节）或注水（加戏），两者都会破坏"情节一致"的承诺。
        """
        source = "\n\n".join(chunk)
        source_hanzi = count_hanzi(source)

        parts = ["## 章节上下文（仅供理解，不要重写它）"]
        if prev_tail:
            parts.append(f"上一章结尾：…{prev_tail}")
        parts.append(f"\n## 本块在原章中的位置\n这是第 {index + 1} 块。段落数：{len(chunk)}。")
        if before:
            parts.append(f"上一块的结尾（已重写，仅供衔接）：…{before[-300:]}")
        if after:
            parts.append(f"下一块的开头（未重写，仅供衔接）：{after[:300]}…")
        parts.append(f"\n## 待重写的原文（{source_hanzi} 汉字，{len(chunk)} 段）\n\n{source}")
        parts.append(f"\n请按前述规则重写，输出 {len(chunk)} 段，段间空一行。")

        prompt = "\n".join(parts)
        last_error = ""

        for attempt in range(1, MAX_CHUNK_TRIES + 1):
            if token is not None:
                # 检查点放在**调用之前**：请求发出后就不能安全退出了
                token.raise_if_cancelled()
            self._wait_if_paused(token)
            self.stats.calls += 1
            try:
                text, usage = self._ask(prompt)
            except Exception as exc:  # noqa: BLE001 - 网络/限流都可重试
                last_error = f"调用失败：{str(exc)[:120]}"
                time.sleep(min(2 * attempt, 8))
                continue

            self.stats.prompt_tokens += usage["prompt"]
            self.stats.completion_tokens += usage["completion"]

            cleaned = clean_output(text)
            if not cleaned:
                last_error = "模型返回空内容"
                continue

            ratio = count_hanzi(cleaned) / max(source_hanzi, 1)
            if ratio < 0.75 or ratio > 1.35:
                last_error = f"字数比例异常 {ratio:.0%}"
                prompt += f"\n\n注意：上一次只写了约 {ratio:.0%} 的篇幅，这次请写足原文的信息量。"
                continue

            return True, cleaned, ""

        return False, "", last_error

    # ------------------------------------------------------------------ 单章

    def rewrite_chapter(
        self,
        chapter: int,
        path: Path,
        token: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[BulkProgress], None]] = None,
        chapter_index: int = 0,
        total_chapters: int = 0,
    ) -> str:
        """返回状态：`done` / `skipped` / `failed` / `cancelled`。"""
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.stats.failed += 1
            self.stats.failures.append({"chapter": chapter, "error": f"读取失败：{exc}"})
            return "failed"

        title, body = split_title(raw)
        fingerprint = self._fingerprint(body)

        if self._is_done(chapter, body):
            self.stats.skipped += 1
            self._notify(
                on_progress,
                BulkProgress(
                    chapter=chapter,
                    chapter_index=chapter_index,
                    total_chapters=total_chapters,
                    skipped=self.stats.skipped,
                    done=self.stats.done,
                    elapsed=self.stats.seconds,
                    message="已重写，跳过",
                ),
            )
            return "skipped"

        paragraphs = split_paragraphs(body)
        chunks = chunk_paragraphs(paragraphs, self.chunk_hanzi)
        if not chunks:
            self.stats.failed += 1
            self.stats.failures.append({"chapter": chapter, "error": "正文为空"})
            return "failed"

        prev_tail = self._prev_tail(chapter)
        started = time.perf_counter()
        rewritten: List[str] = []
        before_text = ""

        for index, chunk in enumerate(chunks):
            if token is not None and token.cancelled:
                self._record(chapter, "cancelled", message="用户取消")
                return "cancelled"
            after = chunks[index + 1][0] if index + 1 < len(chunks) else ""
            self._notify(
                on_progress,
                BulkProgress(
                    chapter=chapter,
                    chapter_index=chapter_index,
                    total_chapters=total_chapters,
                    chunk_index=index + 1,
                    total_chunks=len(chunks),
                    done=self.stats.done,
                    failed=self.stats.failed,
                    skipped=self.stats.skipped,
                    elapsed=self.stats.seconds + (time.perf_counter() - started),
                ),
            )
            try:
                ok, text, error = self.rewrite_chunk(chapter, chunk, index, prev_tail, before_text, after, token)
            except CancelledError:
                # 取消是**正常路径**，不是异常：记录后返回，让上层收尾。
                # 不捕获的话它会一路抛到 CLI/线程顶层，已完成章的统计就丢了。
                self._record(chapter, "cancelled", message="用户取消")
                self.stats.seconds += time.perf_counter() - started
                return "cancelled"
            if not ok:
                elapsed = time.perf_counter() - started
                self.stats.failed += 1
                self.stats.failures.append({"chapter": chapter, "error": f"第{index + 1}块：{error}"})
                self._record(chapter, "failed", error=error, fingerprint=fingerprint)
                self.stats.seconds += elapsed
                return "failed"
            rewritten.append(text)
            before_text = text

        new_body = "\n\n".join(rewritten)
        if self.out_dir is None:
            return "failed"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        payload = (title + "\n\n" + new_body) if title else new_body
        target = self.out_dir / f"chapter_{chapter:04d}.txt"
        try:
            # 原子写：半章文件比"没写"更危险 —— 它看起来像完成了，
            # 用户可能直接拿去用，而段落只到一半。
            atomic_write_text(target, payload)
        except OSError as exc:
            self.stats.failed += 1
            self.stats.failures.append({"chapter": chapter, "error": f"写入失败：{exc}"})
            return "failed"

        elapsed = time.perf_counter() - started
        self.stats.done += 1
        self.stats.seconds += elapsed
        self.stats.hanzi_before += count_hanzi(body)
        self.stats.hanzi_after += count_hanzi(new_body)
        self._record(
            chapter,
            "done",
            fingerprint=fingerprint,
            hanzi_before=count_hanzi(body),
            hanzi_after=count_hanzi(new_body),
            seconds=round(elapsed, 1),
            output=str(target),
        )
        return "done"

    @staticmethod
    def _notify(callback: Optional[Callable[[BulkProgress], None]], progress: BulkProgress) -> None:
        if callback is None:
            return
        try:
            callback(progress)
        except Exception as exc:  # noqa: BLE001 - 回调失败不能中断重写
            logger.debug(f"[整书重写] 进度回调异常：{exc}")

    # ------------------------------------------------------------------ 批量

    def run(
        self,
        on_progress: Optional[Callable[[BulkProgress], None]] = None,
        token: Optional[CancelToken] = None,
        chapters: Optional[Sequence[int]] = None,
    ) -> BulkStats:
        """执行重写。`on_progress` 在**后台线程**被调用 —— 面板要自己 marshal 回主线程。"""
        if self.ai is None:
            raise ReworkError("没有可用的 AI 客户端，无法执行重写")
        self.load_log()
        rows = self.chapter_files()
        if chapters is not None:
            wanted = set(chapters)
            rows = [(num, path) for num, path in rows if num in wanted]

        total = len(rows)
        self.stats = BulkStats()
        started = time.perf_counter()

        for position, (number, path) in enumerate(rows, 1):
            if token is not None and token.cancelled:
                status = "cancelled"
                self._notify(
                    on_progress,
                    BulkProgress(
                        status=status,
                        chapter_index=position - 1,
                        total_chapters=total,
                        done=self.stats.done,
                        failed=self.stats.failed,
                        skipped=self.stats.skipped,
                        elapsed=time.perf_counter() - started,
                    ),
                )
                return self.stats

            status = self.rewrite_chapter(
                number,
                path,
                token=token,
                on_progress=on_progress,
                chapter_index=position,
                total_chapters=total,
            )
            if status == "cancelled":
                return self.stats

        self._notify(
            on_progress,
            BulkProgress(
                status="done",
                chapter_index=total,
                total_chapters=total,
                done=self.stats.done,
                failed=self.stats.failed,
                skipped=self.stats.skipped,
                elapsed=time.perf_counter() - started,
            ),
        )
        return self.stats

    # ------------------------------------------------------------------ 结果

    def failed_chapters(self) -> List[int]:
        """从日志里读出历史失败/取消的章节，供"只重试失败项"使用。"""
        self.load_log()
        rows = []
        for key, record in self._log["chapters"].items():
            if not isinstance(record, dict):
                continue
            if record.get("status") in ("failed", "cancelled"):
                try:
                    rows.append(int(key))
                except (TypeError, ValueError):
                    continue
        return sorted(rows)

    def summary_text(self) -> str:
        """人读的完成摘要（面板结果区）。"""
        lines = [self.stats.as_text()]
        if self.stats.failures:
            lines.append("")
            lines.append("失败章节：")
            for item in self.stats.failures[:15]:
                lines.append(f"  第{item['chapter']}章：{item['error']}")
            if len(self.stats.failures) > 15:
                lines.append(f"  …另有 {len(self.stats.failures) - 15} 章")
        if self.out_dir is not None:
            lines.append("")
            lines.append(f"输出目录：{self.out_dir}")
        return "\n".join(lines)
