"""补全空/过短的章节摘要（抽取式，不生成新情节）。

## 为什么需要

全书 1094 个摘要里有 **74 个内容为空或过短**（少于 20 汉字）。摘要是后续写作的
上下文来源（`build_smart_context` / 章节间衔接），空摘要等于"这一章在记忆里不存在"。

## 为什么用抽取式而不是让模型写

本机 API key 已失效（401），无法调用模型。而抽取式是**可验证**的：
它只从原文里挑句子，不会编造情节。代价是语言不如模型摘要通顺 ——
所以每份产出都带 `（机器摘要·抽取式，待润色）` 标记，不让它冒充成品。

## 抽取规则（四段式）

1. **起点**：正文首段（场景/事件从哪开始）
2. **关键句**：含主要人物名、且长度适中的句子（做了什么）
3. **转折**：含「却/但/然而/忽然/竟」等转折标记的句子
4. **钩子**：末段（这一章停在哪）

总长控制在 120–260 汉字。没有可用句子的槽位直接跳过，不硬凑。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.text_stats import count_hanzi  # noqa: E402

#: 少于这个汉字数的摘要视为"空/过短"，需要补。
MIN_SUMMARY_HANZI = 20

#: 目标摘要长度。
TARGET_HANZI = 200

#: 转折标记。
TURN_MARKS = ("却", "但", "然而", "忽然", "突然", "竟", "偏偏", "不料", "谁知")

#: 机器摘要标记（必须出现，让人一眼看出未润色）。
MACHINE_MARK = "（机器摘要·抽取式，待润色）"


def split_title(text: str) -> tuple[str, str]:
    lines = (text or "").splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if first.startswith("#"):
        return first.lstrip("#").strip(), "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def split_paragraphs(body: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]


def split_sentences(text: str) -> List[str]:
    found: List[str] = []
    buffer: List[str] = []
    for char in text:
        buffer.append(char)
        if char in "。！？!?":
            sentence = "".join(buffer).strip()
            if sentence:
                found.append(sentence)
            buffer = []
    if buffer:
        tail = "".join(buffer).strip()
        if tail:
            found.append(tail)
    return found


def _trim(text: str, limit: int) -> str:
    """截到 `limit` 字以内，尽量在标点处收尾。"""
    body = text.strip()
    if count_hanzi(body) <= limit:
        return body
    buffer = ""
    for char in body:
        buffer += char
        if count_hanzi(buffer) >= limit:
            break
    cut = max(buffer.rfind(mark) for mark in "。！？，；")
    if cut > len(buffer) * 0.6:
        return buffer[: cut + 1]
    return buffer + "…"


def extract_summary(text: str, names: Sequence[str] = ()) -> str:
    """从章节正文抽取摘要。**只挑句子，不改写**。"""
    _title, body = split_title(text)
    paragraphs = split_paragraphs(body)
    if not paragraphs:
        return ""

    pieces: List[str] = []

    # 1) 起点：首段前两句
    head_sentences = split_sentences(paragraphs[0])[:2]
    if head_sentences:
        pieces.append(_trim("".join(head_sentences), 90))

    # 2) 关键句：句中含主要人物名，且长度 15–80 字
    if names:
        for paragraph in paragraphs[1:]:
            for sentence in split_sentences(paragraph):
                length = count_hanzi(sentence)
                if any(name in sentence for name in names) and 15 <= length <= 80:
                    pieces.append(_trim(sentence, 80))
                    break
            if len(pieces) >= 2:
                break

    # 3) 转折句
    if len(pieces) < 3:
        for paragraph in paragraphs[1:]:
            for sentence in split_sentences(paragraph):
                if any(mark in sentence for mark in TURN_MARKS) and 15 <= count_hanzi(sentence) <= 80:
                    pieces.append(_trim(sentence, 80))
                    break
            if len(pieces) >= 3:
                break

    # 4) 钩子：末段最后一句
    tail_sentences = split_sentences(paragraphs[-1])
    if tail_sentences:
        pieces.append(_trim(tail_sentences[-1], 70))

    # 去重（同一句别出现两次）
    unique: List[str] = []
    for piece in pieces:
        if piece and piece not in unique:
            unique.append(piece)

    summary = "".join(unique)
    return _trim(summary, TARGET_HANZI) if summary else ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="补全空章节摘要（抽取式）")
    parser.add_argument("--novel", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    args = parser.parse_args(argv)

    novel = Path(args.novel)
    chapters_dir = novel / "chapters"
    summaries_dir = novel / "summaries"
    if not chapters_dir.is_dir():
        print(f"不是有效作品目录：{novel}", file=sys.stderr)
        return 2

    # 主要人物名：从角色档案取，用于"关键句"筛选
    names: List[str] = []
    characters_file = novel / "memory" / "characters.json"
    if characters_file.is_file():
        try:
            data = json.loads(characters_file.read_text(encoding="utf-8"))
            names = [n for n in data if isinstance(n, str) and len(n) >= 2][:40]
        except (OSError, ValueError):
            names = []

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = novel / "backups" / f"summary_fill_{stamp}" if not args.dry_run else None

    targets: List[dict] = []
    for path in sorted(summaries_dir.glob("chapter_*_summary.txt")):
        match = re.search(r"chapter_(\d+)_summary", path.name)
        if not match:
            continue
        number = int(match.group(1))
        body = path.read_text(encoding="utf-8", errors="replace")
        if count_hanzi(body) >= MIN_SUMMARY_HANZI:
            continue
        targets.append({"chapter": number, "path": path, "old": body.strip()})

    if args.limit:
        targets = targets[: args.limit]

    print(f"待补摘要：{len(targets)} 章")

    filled = 0
    skipped: List[dict] = []
    if not args.dry_run and targets and backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)

    for item in targets:
        number = item["chapter"]
        chapter_path = chapters_dir / f"chapter_{number:04d}.txt"
        if not chapter_path.is_file():
            skipped.append({"chapter": number, "reason": "正文章节缺失"})
            continue
        text = chapter_path.read_text(encoding="utf-8", errors="replace")
        summary = extract_summary(text, names)
        if not summary:
            skipped.append({"chapter": number, "reason": "抽取不出可用句子"})
            continue

        if args.dry_run:
            print(f"  第{number}章 → {summary[:60]}…")
            filled += 1
            continue

        assert backup_dir is not None
        shutil.copyfile(item["path"], backup_dir / item["path"].name)
        title, _body = split_title(text)
        prefix = f"第{number}章摘要" + (f"｜{title}" if title else "")
        payload = f"{prefix}{MACHINE_MARK}\n\n{summary}\n"
        item["path"].write_text(payload, encoding="utf-8")
        filled += 1

    print(f"已补 {filled} 章" + ("" if args.dry_run else f"（备份：{backup_dir.relative_to(novel) if backup_dir else '-'}）"))
    for row in skipped[:10]:
        print(f"  跳过第{row['chapter']}章：{row['reason']}")
    if args.dry_run:
        print("(dry-run，未写任何文件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
