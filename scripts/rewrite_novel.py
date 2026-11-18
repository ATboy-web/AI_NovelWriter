"""整书重写的命令行入口（薄封装）。

## 为什么这个文件这么短

重写逻辑只有一份，在 `app/bulk_rewrite.py` —— 面板点的「开始整书重写」按钮走的是
同一条路径。本文件只做参数解析与终端输出：任何"分块策略 / 字数校验 / 提示词"的改动
都改 app 模块，否则 CLI 与面板会各写一套、跑出两种结果
（本项目踩过"同一事实写两处必然漂移"5 次）。

## 用法

```bash
# 先看规模与代价（不调用模型、不写文件）
python scripts/rewrite_novel.py --novel "<作品目录>" --dry-run

# 试写 3 章
python scripts/rewrite_novel.py --novel "<作品目录>" --chapters 1-3

# 全量（可断点续跑，中断后重跑只补未完成）
python scripts/rewrite_novel.py --novel "<作品目录>" --all

# 只重试上次失败/取消的章
python scripts/rewrite_novel.py --novel "<作品目录>" --retry-failed
```
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.bulk_rewrite import BulkRewriter  # noqa: E402


def _parse_chapters(spec: str) -> List[int]:
    rows: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            rows.extend(range(int(low), int(high) + 1))
        else:
            rows.append(int(part))
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="整书重写（保留情节骨架，统一文风）")
    parser.add_argument("--novel", required=True, help="作品目录")
    parser.add_argument("--chapters", help="章节范围，如 1-3 或 71,72")
    parser.add_argument("--all", action="store_true", help="全部章节")
    parser.add_argument("--retry-failed", action="store_true", help="只重试上次失败/取消的章")
    parser.add_argument("--dry-run", action="store_true", help="只统计规模")
    parser.add_argument("--force", action="store_true", help="重做已完成的章节")
    parser.add_argument("--chunk-hanzi", type=int, default=0, help="每块目标汉字数（默认 1800）")
    args = parser.parse_args(argv)

    novel = Path(args.novel)
    if not (novel / "chapters").is_dir():
        print(f"不是有效的作品目录：{novel}", file=sys.stderr)
        return 2

    ai = None
    if not args.dry_run:
        from app.ai_client import AIClient
        from app.config import AppConfig

        ai = AIClient(AppConfig())

    kwargs = {"force": args.force}
    if args.chunk_hanzi:
        kwargs["chunk_hanzi"] = args.chunk_hanzi
    rewriter = BulkRewriter(novel, ai, **kwargs)

    ok, why = rewriter.check_ready()
    if not ok:
        print(why, file=sys.stderr)
        return 2

    chapters: Optional[List[int]] = None
    if args.chapters:
        chapters = _parse_chapters(args.chapters)
    elif args.retry_failed:
        chapters = rewriter.failed_chapters()
        if not chapters:
            print("上次没有失败的章节")
            return 0
        print(f"重试 {len(chapters)} 章：{chapters[:20]}{'…' if len(chapters) > 20 else ''}")
    elif not args.all and not args.dry_run:
        parser.error("请用 --chapters / --all / --retry-failed 指定范围")

    if args.dry_run:
        print(f"[dry-run] {rewriter.plan().as_text()}")
        print("[dry-run] 未创建任何文件、未调用模型")
        return 0

    if ai is not None:
        ok, why = rewriter.check_ai()
        if not ok:
            print(f"AI 不可用：{why}", file=sys.stderr)
            print("请先在软件「AI 设置」里配置有效的服务与密钥。", file=sys.stderr)
            return 3

    def progress(update) -> None:
        if update.status == "running":
            print(f"  {update.as_line()}", flush=True)

    stats = rewriter.run(on_progress=progress, chapters=chapters)
    print()
    print(stats.as_text())
    print(f"耗时 {stats.seconds / 60:.1f} 分钟")
    if stats.failures:
        print("\n失败章节：")
        for item in stats.failures[:20]:
            print(f"  第{item['chapter']}章：{item['error']}")
    print(f"\n输出目录：{rewriter.out_dir}")
    return 0 if not stats.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
