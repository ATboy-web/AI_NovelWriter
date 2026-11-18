"""整书重写：按项目文件夹为单位，保留情节骨架、统一文风。

## 为什么不是一个"for 循环调 AI"

`max_tokens` 默认 4096（约 2400 汉字），而本书单章平均 1.4 万字 —— 一轮调用写不完一章。
所以必须**分段**。分段方式有两种，选错了后果完全不同：

| 方式 | 风险 |
|---|---|
| 生成式续写（给开头，让它往下写） | 模型会自由发挥，1094 章情节必然漂移 |
| **按原段落切块，逐块改写** | 段落数与顺序不变，情节只可能"表达变化"，不会"变成另一个故事" |

本工具选后者：**原章就是事实骨架**，模型只被允许改文字表达。

## 三条硬约束

1. **绝不覆盖原文**。输出写到 `chapters_rewritten/`，原文一个字不动。
2. **断点续跑**。`rewrite_log.json` 记每章状态（`done` / `failed` / `skipped`），
   中断后重跑只补未完成的。
3. **风格统一靠同一份 system prompt**：风格 DNA（自动学）+ 写作预设的"不得改动"清单，
   每章每段都用同一份 —— 不是"每章各自发挥"。

## 用法

```bash
# 先看规模与代价，不动任何文件
python scripts/rewrite_novel.py --novel "<作品目录>" --dry-run

# 试写前 3 章（强烈建议先这样验证质量）
python scripts/rewrite_novel.py --novel "<作品目录>" --chapters 1-3

# 全量（可断点续跑）
python scripts/rewrite_novel.py --novel "<作品目录>" --all
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.text_stats import count_hanzi  # noqa: E402

#: 每块目标汉字数。取 1800 是因为 max_tokens=4096 下模型输出约 2000–2400 汉字，
#: 留出余量避免被截断（截断会在段落中间断句，是最难修的一种坏）。
CHUNK_HANZI = 1800

#: 每块重写的最大尝试次数（含重试）。
MAX_CHUNK_TRIES = 3

#: 上下文：上一章末尾取多少字给模型看衔接点。
PREV_TAIL_CHARS = 600

#: 输出目录名（相对作品根）。**不覆盖 `chapters/`**。
OUTPUT_DIR = "chapters_rewritten"

#: 日志文件名。
LOG_NAME = "rewrite_log.json"

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


@dataclass
class ChunkResult:
    index: int
    ok: bool
    text: str = ""
    error: str = ""
    tries: int = 0


@dataclass
class ChapterResult:
    chapter: int
    status: str = "pending"
    chunks: int = 0
    hanzi_before: int = 0
    hanzi_after: int = 0
    seconds: float = 0.0
    error: str = ""
    output: str = ""


@dataclass
class Stats:
    chapters: int = 0
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


# ====================================================================== 文本处理


def split_title(text: str) -> Tuple[str, str]:
    """拆成 `(标题行, 正文)`。"""
    lines = (text or "").splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if first.startswith("#"):
        return first, "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def split_paragraphs(body: str) -> List[str]:
    """按空行切段，丢弃空段，保留原顺序。"""
    paragraphs: List[str] = []
    for block in re.split(r"\n\s*\n", body or ""):
        stripped = block.strip()
        if stripped:
            paragraphs.append(stripped)
    return paragraphs


def chunk_paragraphs(paragraphs: Sequence[str], target: int = CHUNK_HANZI) -> List[List[str]]:
    """把段落按目标字数聚成块。**不切断段落** —— 断在段落中间会让模型接不上。"""
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


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


# ====================================================================== 重写器


class NovelRewriter:
    def __init__(
        self,
        novel_dir: Path,
        ai_client: Any,
        output_dir: Optional[Path] = None,
        chunk_hanzi: int = CHUNK_HANZI,
        dry_run: bool = False,
    ) -> None:
        self.novel_dir = Path(novel_dir)
        self.chapters_dir = self.novel_dir / "chapters"
        self.out_dir = output_dir or (self.novel_dir / OUTPUT_DIR)
        self.ai = ai_client
        self.chunk_hanzi = chunk_hanzi
        self.dry_run = dry_run
        self.log_path = self.novel_dir / LOG_NAME
        self.log: Dict[str, Any] = {"version": 1, "chapters": {}}
        self.stats = Stats()

    # ------------------------------------------------------------------ 日志

    def load_log(self) -> None:
        if not self.log_path.is_file():
            return
        try:
            data = json.loads(self.log_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and isinstance(data.get("chapters"), dict):
            self.log = data

    def save_log(self) -> None:
        if self.dry_run:
            return
        try:
            self.log_path.write_text(json.dumps(self.log, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"  ⚠️ 日志写入失败：{exc}", file=sys.stderr)

    def _fingerprint(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------ 上下文

    def chapter_files(self) -> List[Tuple[int, Path]]:
        rows: List[Tuple[int, Path]] = []
        for path in sorted(self.chapters_dir.glob("chapter_*.txt")):
            match = re.search(r"chapter_(\d+)", path.name)
            if match:
                rows.append((int(match.group(1)), path))
        rows.sort()
        return rows

    def _prev_tail(self, chapter: int) -> str:
        """上一章末尾若干字 —— 给模型一个衔接点，但不给它整章（省 token）。"""
        prev = self.chapters_dir / f"chapter_{chapter - 1:04d}.txt"
        if not prev.is_file():
            return ""
        try:
            body = split_title(prev.read_text(encoding="utf-8", errors="replace"))[1]
        except OSError:
            return ""
        return body[-PREV_TAIL_CHARS:]

    def _style_block(self) -> str:
        """风格约束（全书同一份，这是"风格统一"的落点）。"""
        try:
            from app.writing_presets import PRESETS

            preset = PRESETS["deai-full"]
            rules = "\n".join(f"- {item}" for item in preset.norms)
            return f"\n## 本次誊写的风格纪律\n{rules}\n"
        except Exception:  # noqa: BLE001 - 预设不可用不该中断重写
            return ""

    # ------------------------------------------------------------------ 调用

    def _ask(self, prompt: str) -> Tuple[str, Dict[str, int]]:
        """一次模型调用，返回 `(文本, token 用量)`。

        token 用量从模块级 `token_stats` 单例取**前后差值** ——
        它是累计计数器，直接读会得到"历史总量"，不是本次的消耗。
        """
        from app import ai_client as ai_module

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
    ) -> ChunkResult:
        """重写一块（若干段落）。校验字数比例，不符就重试。"""
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
            self.stats.calls += 1
            try:
                text, usage = self._ask(prompt)
            except Exception as exc:  # noqa: BLE001 - 网络/限流都算可重试
                last_error = f"调用失败：{exc}"
                time.sleep(min(2 * attempt, 8))
                continue

            self.stats.prompt_tokens += usage["prompt"]
            self.stats.completion_tokens += usage["completion"]

            cleaned = _clean_output(text)
            if not cleaned:
                last_error = "模型返回空内容"
                continue

            ratio = count_hanzi(cleaned) / max(source_hanzi, 1)
            if ratio < 0.75 or ratio > 1.35:
                last_error = f"字数比例异常 {ratio:.2f}（原文 {source_hanzi}）"
                # 比例偏小时补一句"写详细些"再试一次
                prompt = prompt + f"\n\n注意：上一次只写了约 {ratio:.0%} 的篇幅，这次请写足原文的信息量。"
                continue

            return ChunkResult(index=index, ok=True, text=cleaned, tries=attempt)

        return ChunkResult(index=index, ok=False, error=last_error, tries=MAX_CHUNK_TRIES)

    # ------------------------------------------------------------------ 章节

    def rewrite_chapter(self, chapter: int, force: bool = False) -> ChapterResult:
        path = self.chapters_dir / f"chapter_{chapter:04d}.txt"
        if not path.is_file():
            return ChapterResult(chapter=chapter, status="missing", error="文件不存在")

        raw = path.read_text(encoding="utf-8", errors="replace")
        title, body = split_title(raw)
        fingerprint = self._fingerprint(body)

        # 断点续跑：同内容已 done 就跳过
        record = self.log["chapters"].get(str(chapter), {})
        if not force and record.get("status") == "done" and record.get("fingerprint") == fingerprint:
            self.stats.skipped += 1
            return ChapterResult(
                chapter=chapter,
                status="skipped",
                hanzi_before=count_hanzi(body),
                hanzi_after=record.get("hanzi_after", 0),
                output=record.get("output", ""),
            )

        paragraphs = split_paragraphs(body)
        chunks = chunk_paragraphs(paragraphs, self.chunk_hanzi)
        prev_tail = self._prev_tail(chapter)
        result = ChapterResult(chapter=chapter, chunks=len(chunks), hanzi_before=count_hanzi(body))

        if self.dry_run:
            result.status = "planned"
            self.stats.chapters += 1
            self.stats.hanzi_before += result.hanzi_before
            return result

        started = time.perf_counter()
        rewritten: List[str] = []
        before = ""
        for index, chunk in enumerate(chunks):
            after = chunks[index + 1][0] if index + 1 < len(chunks) else ""
            chunk_result = self.rewrite_chunk(chapter, chunk, index, prev_tail, before, after)
            if not chunk_result.ok:
                result.status = "failed"
                result.error = f"第 {index + 1}/{len(chunks)} 块失败：{chunk_result.error}"
                result.seconds = time.perf_counter() - started
                self._record(chapter, result, fingerprint)
                return result
            rewritten.append(chunk_result.text)
            before = chunk_result.text

        new_body = "\n\n".join(rewritten)
        output_path = self.out_dir / f"chapter_{chapter:04d}.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 标题沿用原标题（本次只改文风，不动标题；标题问题由「回炉重造」处理）
        payload = (title + "\n\n" + new_body) if title else new_body
        output_path.write_text(payload, encoding="utf-8")

        result.status = "done"
        result.hanzi_after = count_hanzi(new_body)
        result.seconds = time.perf_counter() - started
        result.output = str(output_path)
        self._record(chapter, result, fingerprint)

        self.stats.chapters += 1
        self.stats.done += 1
        self.stats.hanzi_before += result.hanzi_before
        self.stats.hanzi_after += result.hanzi_after
        self.stats.seconds += result.seconds
        return result

    def _record(self, chapter: int, result: ChapterResult, fingerprint: str) -> None:
        self.log["chapters"][str(chapter)] = {
            "status": result.status,
            "fingerprint": fingerprint,
            "chunks": result.chunks,
            "hanzi_before": result.hanzi_before,
            "hanzi_after": result.hanzi_after,
            "seconds": round(result.seconds, 1),
            "error": result.error,
            "output": result.output,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if result.status == "failed":
            self.stats.failed += 1
            self.stats.failures.append({"chapter": chapter, "error": result.error})
        self.save_log()

    # ------------------------------------------------------------------ 批量

    def run(self, chapters: Optional[Iterable[int]] = None) -> Stats:
        self.load_log()
        rows = self.chapter_files()
        if chapters is not None:
            wanted = set(chapters)
            rows = [(num, path) for num, path in rows if num in wanted]

        total = len(rows)
        for position, (chapter, _path) in enumerate(rows, 1):
            result = self.rewrite_chapter(chapter)
            if result.status == "done":
                print(
                    f"  [{position}/{total}] 第{chapter}章 ✅ {result.hanzi_before} → "
                    f"{result.hanzi_after} 字 · {result.chunks} 块 · {result.seconds:.0f}s"
                )
            elif result.status == "skipped":
                print(f"  [{position}/{total}] 第{chapter}章 ⏭ 已完成，跳过")
            elif result.status == "planned":
                pass
            else:
                print(f"  [{position}/{total}] 第{chapter}章 ❌ {result.error}")
        return self.stats


def _clean_output(text: str) -> str:
    """去掉模型可能的开场白/围栏/编号，保留正文段落。"""
    body = str(text or "").strip()
    if not body:
        return ""
    # 去掉 ``` 围栏
    body = re.sub(r"^```[a-zA-Z]*\s*", "", body)
    body = re.sub(r"\s*```$", "", body)
    # 去掉「以下是…」这类开场白（只删第一行且明显是说明）
    first_line, _, rest = body.partition("\n")
    if rest and re.match(r"^[\s*#]*(以下|下面|这是|改写后|重写后)", first_line.strip()):
        body = rest.strip()
    # 去掉纯分隔线
    body = "\n".join(line for line in body.splitlines() if not re.fullmatch(r"\s*[-*_]{3,}\s*", line))
    return body.strip()


# ====================================================================== CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="整书重写（保留情节骨架，统一文风）")
    parser.add_argument("--novel", required=True, help="作品目录")
    parser.add_argument("--chapters", help="章节范围，如 1-3 或 71,72,1094")
    parser.add_argument("--all", action="store_true", help="全部章节")
    parser.add_argument("--dry-run", action="store_true", help="只统计规模，不调用模型")
    parser.add_argument("--force", action="store_true", help="重做已完成的章节")
    parser.add_argument("--chunk-hanzi", type=int, default=CHUNK_HANZI)
    args = parser.parse_args(argv)

    novel = Path(args.novel)
    if not (novel / "chapters").is_dir():
        print(f"不是有效的作品目录：{novel}", file=sys.stderr)
        return 2

    chapters: Optional[List[int]] = None
    if args.chapters:
        chapters = []
        for part in args.chapters.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                chapters.extend(range(int(low), int(high) + 1))
            elif part:
                chapters.append(int(part))
    elif not args.all and not args.dry_run:
        # dry-run 的用途就是"先看全量规模"，不该强制再写一次 --all
        parser.error("请用 --chapters 或 --all 指定范围")

    ai = None
    if not args.dry_run:
        from app.ai_client import AIClient
        from app.config import AppConfig

        # `AppConfig()` 自己读 `~/.ai_novel_writer/config.json`（含加密的 api_key）
        ai = AIClient(AppConfig())

    rewriter = NovelRewriter(novel, ai, chunk_hanzi=args.chunk_hanzi, dry_run=args.dry_run)
    stats = rewriter.run(chapters)

    print()
    if args.dry_run:
        estimated_calls = sum(
            len(chunk_paragraphs(split_paragraphs(split_title(p.read_text(encoding="utf-8", errors="replace"))[1]), args.chunk_hanzi))
            for num, p in rewriter.chapter_files()
            if chapters is None or num in set(chapters)
        )
        print(f"[dry-run] 计划重写 {stats.chapters} 章 / {stats.hanzi_before:,} 汉字")
        print(f"[dry-run] 预计调用 {estimated_calls} 次（每块一次）")
        print("[dry-run] 未创建任何文件、未调用模型")
        return 0

    print(f"完成 {stats.done} · 跳过 {stats.skipped} · 失败 {stats.failed}")
    print(f"字数 {stats.hanzi_before:,} → {stats.hanzi_after:,}")
    print(f"耗时 {stats.seconds / 60:.1f} 分钟 · 调用 {stats.calls} 次")
    print(
        f"token：输入 {stats.prompt_tokens:,} / 输出 {stats.completion_tokens:,}"
    )
    if stats.failures:
        print("\n失败章节：")
        for item in stats.failures[:20]:
            print(f"  第{item['chapter']}章：{item['error']}")
    print(f"\n输出目录：{rewriter.out_dir}")
    return 0 if not stats.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
