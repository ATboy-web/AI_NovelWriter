"""章节切分：把 1.4 万字/章的超长章按场景切成 3000–4000 字/章。

## 为什么这是"整体重写"里最该先做的一步

单章 1.4 万字意味着读者要读 40 分钟才见到章末钩子，追读机制直接失效；
平台算法看的是读完率/追更率，长章会把数据压垮。而这一步**不改任何文字**，
只是重新打包 —— 风险最低、收益最直接，且是后续任何重写/发布的前提。

## 切分点怎么选

贪心累加到目标字数只是兜底。优先在**场景转换**处切：

| 信号 | 例子 |
|---|---|
| 时间跳跃 | 第二天 / 三日后 / 与此同时 / 半个时辰后 / 夜色渐深 |
| 场景迁移 | 回到 / 走进 / 离开 + 地点 |
| 对话开启 | 段落以引号开头（换人说话了，往往是新场景） |

在这些位置切，读者感知是"换场景了"；在段落中间硬切，感知是"断了"。

## 标题怎么办（不编造）

切分后原章变 N 章，后 N-1 章没有独立标题。本工具**不生成新标题**，
沿用原标题加序号：`第71章 交界弃儿（一）/（二）/（三）`。

理由：从正文抽关键词拼标题必然难看，而让模型编标题在 key 失效时做不到。
序号是诚实的，且之后可以随时替换成真标题（标题与正文解耦，替换零风险）。

## 输出

写到 `chapters_split/`，**原 `chapters/` 一个字不动**。
同时产出 `split_manifest.json`：每章 → 新章号范围、字数、切分位置，
供后续合并/回滚/替换标题使用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.text_stats import count_hanzi  # noqa: E402

#: 默认目标字数（网文单章常规区间 2000–4000）。
TARGET_HANZI = 3500

#: 允许的最小章（低于它说明切碎了，宁可并回上一块）。
MIN_HANZI = 1800

#: 场景转换信号：段首出现这些词，是天然的切分点。
SCENE_BREAKS = (
    "第二天",
    "次日",
    "翌日",
    "三日后",
    "数日后",
    "几日后",
    "半月后",
    "一个月后",
    "与此同时",
    "同一时间",
    "另一边",
    "半个时辰后",
    "一个时辰后",
    "片刻后",
    "稍顷",
    "入夜",
    "夜色",
    "天亮",
    "清晨",
    "黄昏",
    "回到",
    "离开",
    "走出",
    "走进",
)

#: 引号开头 = 换人说话，常伴随场景切换。
QUOTE_HEADS = ("「", "“", "『", '"', "‘")

OUTPUT_DIR = "chapters_split"
MANIFEST = "split_manifest.json"


@dataclass
class Slice:
    index: int
    paragraphs: List[str] = field(default_factory=list)
    hanzi: int = 0
    starts_scene: bool = False

    def add(self, paragraph: str) -> None:
        self.paragraphs.append(paragraph)
        self.hanzi += count_hanzi(paragraph)


@dataclass
class SplitResult:
    chapter: int
    title: str
    before_hanzi: int
    slices: List[Slice]
    written: int = 0


def split_title(text: str) -> Tuple[str, str]:
    lines = (text or "").splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if first.startswith("#"):
        return first.lstrip("#").strip(), "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def split_paragraphs(body: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]


def is_scene_start(paragraph: str) -> bool:
    text = paragraph.strip()
    if not text:
        return False
    if text[0] in QUOTE_HEADS:
        return True
    return any(text.startswith(marker) for marker in SCENE_BREAKS)


def slice_paragraphs(
    paragraphs: Sequence[str],
    target: int = TARGET_HANZI,
    min_hanzi: int = MIN_HANZI,
) -> List[Slice]:
    """按目标字数切，优先在场景转换处落刀。"""
    slices: List[Slice] = []
    current = Slice(index=0)

    for paragraph in paragraphs:
        scene = is_scene_start(paragraph)

        # 该切了：已够字数，且（当前段是新场景 或 已明显超出目标）
        if current.paragraphs and (
            (current.hanzi >= target and (scene or current.hanzi >= target * 1.35)) or current.hanzi >= target * 1.6
        ):
            slices.append(current)
            current = Slice(index=len(slices), starts_scene=scene)

        current.add(paragraph)

    if current.paragraphs:
        slices.append(current)

    # 末块过短 ⇒ 并回上一块（避免出现 300 字的残章）
    if len(slices) >= 2 and slices[-1].hanzi < min_hanzi:
        tail = slices.pop()
        for paragraph in tail.paragraphs:
            slices[-1].add(paragraph)

    for position, item in enumerate(slices):
        item.index = position
    return slices


def _ordinal(count: int, index: int) -> str:
    """`（一）` 形式的中文序号。"""
    digits = "零一二三四五六七八九十"
    if count <= 1:
        return ""
    if index < 10:
        return f"（{digits[index + 1]}）"
    if index < 19:
        return f"（十{digits[index - 9]}）"
    tens, ones = divmod(index + 1, 10)
    return f"（{digits[tens]}十{digits[ones] if ones else ''}）"


def split_chapter(
    paragraph_list: Sequence[str],
    title: str,
    target: int = TARGET_HANZI,
    min_hanzi: int = MIN_HANZI,
) -> List[Slice]:
    return slice_paragraphs(paragraph_list, target=target, min_hanzi=min_hanzi)


def run(
    novel: Path,
    target: int = TARGET_HANZI,
    chapters: Optional[Sequence[int]] = None,
    dry_run: bool = False,
) -> dict:
    chapters_dir = novel / "chapters"
    out_dir = novel / OUTPUT_DIR
    rows = []
    for path in sorted(chapters_dir.glob("chapter_*.txt")):
        match = re.search(r"chapter_(\d+)", path.name)
        if not match:
            continue
        number = int(match.group(1))
        if chapters is not None and number not in chapters:
            continue
        rows.append((number, path))

    manifest = {"version": 1, "target_hanzi": target, "chapters": [], "map": []}
    next_number = 1
    total_before = 0
    total_slices = 0

    for number, path in rows:
        raw = path.read_text(encoding="utf-8", errors="replace")
        title, body = split_title(raw)
        paragraphs = split_paragraphs(body)
        before = count_hanzi(body)
        total_before += before
        slices = split_chapter(paragraphs, title, target=target)

        entry = {
            "chapter": number,
            "title": title,
            "hanzi_before": before,
            "slice_count": len(slices),
            "slices": [{"hanzi": s.hanzi, "starts_scene": s.starts_scene} for s in slices],
        }

        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            # 去掉「第N章：」前缀留下真正的标题词。
            # 若原标题本身就是占位符（只有「第71章」），这里会是空 —— 那就**不编造**，
            # 只写章号，避免出现「第1章 第71章（一）」这种自相矛盾的标题。
            base_title = re.sub(r"^第\s*\d+\s*章\s*[:：]?\s*", "", title).strip()
            for position, item in enumerate(slices):
                suffix = _ordinal(len(slices), position)
                if base_title:
                    new_title = f"# 第{next_number}章 {base_title}{suffix}"
                else:
                    new_title = f"# 第{next_number}章"
                payload = new_title + "\n\n" + "\n\n".join(item.paragraphs) + "\n"
                (out_dir / f"chapter_{next_number:04d}.txt").write_text(payload, encoding="utf-8")
                manifest["map"].append(
                    {
                        "new_chapter": next_number,
                        "from_chapter": number,
                        "slice_index": position,
                        "hanzi": item.hanzi,
                    }
                )
                next_number += 1
                entry["written"] = entry.get("written", 0) + 1

        manifest["chapters"].append(entry)
        total_slices += len(slices)

    manifest["summary"] = {
        "chapters_in": len(rows),
        "chapters_out": next_number - 1 if not dry_run else total_slices,
        "hanzi_in": total_before,
        "avg_slice_hanzi": round(total_before / total_slices, 0) if total_slices else 0,
    }

    if not dry_run:
        (novel / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="按场景切分超长章节")
    parser.add_argument("--novel", required=True)
    parser.add_argument("--target", type=int, default=TARGET_HANZI, help="目标每章汉字数")
    parser.add_argument("--chapters", help="只处理这些章，如 1-3 或 71,72")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    novel = Path(args.novel)
    if not (novel / "chapters").is_dir():
        print(f"不是有效作品目录：{novel}", file=sys.stderr)
        return 2

    wanted = None
    if args.chapters:
        wanted = []
        for part in args.chapters.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                wanted.extend(range(int(low), int(high) + 1))
            elif part:
                wanted.append(int(part))

    manifest = run(novel, target=args.target, chapters=wanted, dry_run=args.dry_run)
    summary = manifest["summary"]
    print(f"输入 {summary['chapters_in']} 章 / {summary['hanzi_in']:,} 汉字")
    print(f"输出 {summary['chapters_out']} 章 / 平均 {summary['avg_slice_hanzi']:.0f} 字")
    if args.dry_run:
        print("(dry-run，未写任何文件)")
    else:
        print(f"已写入 {novel / OUTPUT_DIR}")
        print(f"清单 {novel / MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
