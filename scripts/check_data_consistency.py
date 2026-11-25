#!/usr/bin/env python
"""作品数据一致性检查（**只读**，不修改任何文件）。

## 为什么需要

本仓的历史教训反复指向同一类问题：**同一事实写在多处，必然漂移**。
在用户数据上尤其明显 —— 实测某部 1094 章的作品：

- `meta.json` 的 `chapter_count` 写成 **1200**（差 106）
- 倒排索引 1279 个条目里，**639 个指向不存在的摘要文件**
  （`_update_inverted_index` 只增不删，删章后条目留下来）

这些漂移不会让程序崩，但会静默影响检索质量与用户判断
（"我明明有 1200 章" / "为什么搜不到那章"）。本脚本把这类问题**显式化**。

## 用法

    python scripts/check_data_consistency.py                  # 扫默认作品目录
    python scripts/check_data_consistency.py <novel_dir>      # 扫单部作品
    python scripts/check_data_consistency.py --json           # 结构化输出

退出码：0 = 未发现问题；1 = 发现 error 级问题（warn 不影响退出码）。

## 检查项

| 类型 | 级别 | 含义 |
|---|---|---|
| `chapter_count_mismatch` | warn | `meta.chapter_count` 与实际章节数不符 |
| `missing_summary` | warn | 有正文但没有对应摘要 |
| `orphan_summary` | warn | 有摘要但没有对应正文 |
| `chapter_gap` | warn | 章节号不连续（1..max 之间缺号） |
| `index_orphan` | error | 倒排索引的 chapter 条目指向不存在的摘要 |
| `index_unmapped_type` | warn | 索引里有非章节文档（如 plot_*），无对应存储 |
| `timeline_chapter_invalid` | error | 时间线事件的章号越界或非法 |
| `branch_unopenable` | warn | 分支目录缺可解析的 meta.json |

**只读保证**：本脚本只调用读方法，绝不写盘。可用 `--dry-run` 语义默认即为 true。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@dataclass
class Issue:
    """一条一致性问题。"""

    kind: str
    severity: str  # "error" | "warn"
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "detail": self.detail}


@dataclass
class NovelReport:
    novel_dir: Path
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")


# ─────────────────────────────────────────────────────────── 单项检查


def _chapter_numbers(chapters_dir: Path) -> set[int]:
    """`chapters/chapter_0001.txt` → {1, 2, ...}；非标准名忽略。"""
    if not chapters_dir.is_dir():
        return set()
    out: set[int] = set()
    for path in chapters_dir.glob("chapter_*.txt"):
        stem = path.stem  # chapter_0001
        tail = stem.rsplit("_", 1)[-1]
        if tail.isdigit():
            out.add(int(tail))
    return out


def check_chapter_count(novel_dir: Path, numbers: set[int]) -> list[Issue]:
    """`meta.json` 里的 chapter_count 是否与实际章节数一致。"""
    meta_path = novel_dir / "meta.json"
    if not meta_path.exists():
        return []
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [Issue("chapter_count_mismatch", "warn", "meta.json 不可解析，无法核对 chapter_count")]
    if not isinstance(meta, dict):
        return []

    declared = meta.get("chapter_count")
    if declared is None:
        return []
    try:
        declared_int = int(declared)
    except (TypeError, ValueError):
        return [Issue("chapter_count_mismatch", "warn", f"meta.chapter_count 不是数字：{declared!r}")]

    actual = len(numbers)
    if declared_int != actual:
        return [
            Issue(
                "chapter_count_mismatch",
                "warn",
                f"meta.chapter_count={declared_int}，实际章节文件 {actual} 个（差 {declared_int - actual:+d}）",
            )
        ]
    return []


def check_gaps(numbers: set[int]) -> list[Issue]:
    """章节号是否连续（1..max 之间不应有缺号）。"""
    if not numbers:
        return []
    top = max(numbers)
    missing = sorted(set(range(1, top + 1)) - numbers)
    if not missing:
        return []
    head = ", ".join(str(n) for n in missing[:10])
    more = f" 等 {len(missing)} 章" if len(missing) > 10 else ""
    return [Issue("chapter_gap", "warn", f"章节号缺 {head}{more}")]


def check_summaries(novel_dir: Path, numbers: set[int]) -> list[Issue]:
    """摘要与正文的对应关系（双向）。"""
    issues: list[Issue] = []
    summary_dir = novel_dir / "memory" / "chapters"
    summary_nums = _chapter_numbers(summary_dir)

    missing = sorted(numbers - summary_nums)
    if missing:
        head = ", ".join(str(n) for n in missing[:10])
        more = f" 等 {len(missing)} 章" if len(missing) > 10 else ""
        issues.append(Issue("missing_summary", "warn", f"有正文但无摘要：第 {head}{more}"))

    orphan = sorted(summary_nums - numbers)
    if orphan:
        head = ", ".join(str(n) for n in orphan[:10])
        more = f" 等 {len(orphan)} 章" if len(orphan) > 10 else ""
        issues.append(Issue("orphan_summary", "warn", f"有摘要但无正文：第 {head}{more}"))
    return issues


def check_inverted_index(novel_dir: Path) -> list[Issue]:
    """倒排索引里的 `chapter_*` 条目必须指向存在的摘要文件。

    ## 判据为什么只针对 `chapter_*`

    实测某部 1094 章的作品，索引里有 **640 个 `chapter_*` + 639 个 `plot_*`**。
    `plot_*` 在 `memory/` 下**没有任何对应存储**（只有 chapters / chunks /
    timeline / volumes / arcs），因此不能用"文件是否存在"去判它 ——
    第一版判据把 639 个 `plot_*` 全判成 error，纯属误报。

    现在的口径：
    - `chapter_*` 缺对应摘要 ⇒ **error**（检索会命中空章节，用户可感知）
    - 其他前缀 ⇒ **warn**，只报告"存在但无法定位"，因为无法证明它是错的
      （可能是别的模块按需生成，也可能是历史残留）
    """
    index_path = novel_dir / "memory" / "inverted_index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [Issue("index_orphan", "error", "inverted_index.json 不可解析")]

    if not isinstance(data, dict):
        return [Issue("index_orphan", "error", "inverted_index.json 根节点不是对象")]

    summary_dir = novel_dir / "memory" / "chapters"
    by_prefix: dict[str, set[str]] = {}
    for doc_ids in data.values():
        if not isinstance(doc_ids, list):
            continue
        for doc in doc_ids:
            text = str(doc)
            prefix = text.split("_", 1)[0] if "_" in text else "(无前缀)"
            by_prefix.setdefault(prefix, set()).add(text)

    issues: list[Issue] = []

    missing = sorted(d for d in by_prefix.get("chapter", set()) if not (summary_dir / f"{d}.txt").exists())
    if missing:
        head = ", ".join(missing[:5])
        issues.append(
            Issue(
                "index_orphan",
                "error",
                f"倒排索引有 {len(missing)} 个 chapter 条目指向不存在的摘要（如 {head}），检索会命中空章节",
            )
        )

    orphan_types = {p: len(v) for p, v in by_prefix.items() if p not in ("chapter", "(无前缀)")}
    if orphan_types:
        detail = "、".join(f"{p} {n} 个" for p, n in sorted(orphan_types.items()))
        issues.append(
            Issue(
                "index_unmapped_type",
                "warn",
                f"索引含非章节文档（{detail}），memory/ 下无对应存储，无法判定其有效性",
            )
        )
    return issues


def check_timeline(novel_dir: Path, numbers: set[int]) -> list[Issue]:
    """时间线事件的章号必须在 [1, max_chapter] 内。"""
    timeline_dir = novel_dir / "memory" / "timeline"
    if not timeline_dir.is_dir():
        return []

    top = max(numbers) if numbers else 0
    bad: list[str] = []
    for shard in sorted(timeline_dir.glob("*.json")):
        try:
            data = json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f"{shard.name}(不可解析)")
            continue
        if not isinstance(data, list):
            continue
        for event in data:
            if not isinstance(event, dict):
                continue
            chapter = event.get("chapter")
            try:
                chapter_int = int(chapter)
            except (TypeError, ValueError):
                bad.append(f"{shard.name}(章号非数字:{chapter!r})")
                continue
            if chapter_int < 1 or (top and chapter_int > top):
                bad.append(f"{shard.name}(第{chapter_int}章越界, 上限{top})")
                break  # 每个分片报一次就够

    if not bad:
        return []
    return [Issue("timeline_chapter_invalid", "error", f"时间线事件章号异常：{'; '.join(bad[:5])}")]


def check_branches(novel_dir: Path) -> list[Issue]:
    """分支子项目是否可打开。"""
    try:
        from app.lineage import discover_branches
    except Exception:  # noqa: BLE001 - 脚本应能在任何环境下跑
        return []

    try:
        branches = discover_branches(novel_dir)
    except Exception as exc:  # noqa: BLE001
        return [Issue("branch_unopenable", "warn", f"列分支失败：{exc}")]

    bad = [b for b in branches if not b.get("openable")]
    if not bad:
        return []
    names = ", ".join(str(b.get("branch_id")) for b in bad[:5])
    return [Issue("branch_unopenable", "warn", f"{len(bad)} 个分支缺可解析的 meta.json：{names}")]


# ─────────────────────────────────────────────────────────── 汇总


def check_novel(novel_dir: Path) -> NovelReport:
    """对单部作品跑全部检查。**只读**。"""
    novel_dir = Path(novel_dir)
    report = NovelReport(novel_dir=novel_dir)
    if not novel_dir.is_dir():
        report.issues.append(Issue("workspace_missing", "error", f"目录不存在：{novel_dir}"))
        return report

    numbers = _chapter_numbers(novel_dir / "chapters")
    report.issues.extend(check_chapter_count(novel_dir, numbers))
    report.issues.extend(check_gaps(numbers))
    report.issues.extend(check_summaries(novel_dir, numbers))
    report.issues.extend(check_inverted_index(novel_dir))
    report.issues.extend(check_timeline(novel_dir, numbers))
    report.issues.extend(check_branches(novel_dir))
    return report


def iter_novels(root: Path) -> Iterable[Path]:
    """作品根目录下的每个子目录（跳过 `_` 开头的临时/备份目录）。"""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))


def default_novels_root() -> Path:
    return Path.home() / ".ai_novel_writer" / "novels"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="作品数据一致性检查（只读）")
    parser.add_argument("path", nargs="?", help="作品目录，或包含多部作品的根目录；缺省为默认作品根")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    target = Path(args.path) if args.path else default_novels_root()
    if not target.exists():
        print(f"路径不存在：{target}", file=sys.stderr)
        return 2

    # 单部作品（有 meta.json）还是作品根（有多个子目录）？
    if (target / "meta.json").exists() or (target / "chapters").is_dir():
        reports = [check_novel(target)]
    else:
        reports = [check_novel(p) for p in iter_novels(target)]

    # 跳过"临时/备份/探针"目录产生的噪音
    reports = [r for r in reports if not r.novel_dir.name.startswith("_")]

    if args.json:
        payload = [
            {
                "novel": r.novel_dir.name,
                "errors": r.errors,
                "warnings": r.warnings,
                "issues": [i.as_dict() for i in r.issues],
            }
            for r in reports
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        total_e = sum(r.errors for r in reports)
        total_w = sum(r.warnings for r in reports)
        for r in reports:
            if not r.issues:
                print(f"✓ {r.novel_dir.name}")
                continue
            print(f"✗ {r.novel_dir.name}  （error {r.errors} / warn {r.warnings}）")
            for issue in r.issues:
                mark = "  !!" if issue.severity == "error" else "  · "
                print(f"{mark} [{issue.kind}] {issue.detail}")
        print()
        print(f"合计：{len(reports)} 部作品，{total_e} 条 error，{total_w} 条 warn")

    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
