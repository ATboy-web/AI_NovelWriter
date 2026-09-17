"""把 dedup_tests.py 跳过的"候选组"导出成可读报告，供逐组人工判断。

判据要点（写进报告，避免重复解释）：
- 「同体 + 同类名 + 同函数名」⇒ 确定重复（已被 dedup_tests.py 自动处理）
- 「同体 + **异类名**」⇒ 需要判断：两个类是否真的测同一个对象？
  - 若两个类都只是"包一层"，且被测目标相同 ⇒ 真重复
  - 若两个类分别测不同目标（如 ElementLibrary / BridgeLibrary）⇒ **假重复，必须保留**
"""

from __future__ import annotations

import ast
import io
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from dedup_tests import TestItem, code_only, collect  # noqa: E402


def class_context(cls_name: str, path: Path) -> str:
    """取出类的 setUp（或等价初始化）里的关键行，用于判断这一类到底在测什么。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return "?"
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name in (
                    "setUp",
                    "setup_method",
                ):
                    body = code_only(ast.unparse(m)).splitlines()
                    keep = [ln.strip() for ln in body if "=" in ln and "self." in ln]
                    return "; ".join(keep[:2]) or "?"
            # 没有 setUp：找 __init__ 之外的类级赋值
            return "(无 setUp)"
    return "(类未找到)"


def main() -> int:
    buf = io.StringIO()
    with redirect_stdout(buf):
        items = collect()

    groups: dict[str, list[TestItem]] = defaultdict(list)
    for it in items:
        groups[it.body_hash].append(it)

    candidates = []
    for h, members in groups.items():
        if len(members) < 2:
            continue
        qualnames = {f"{m.cls}::{m.name}" for m in members}
        if len(qualnames) == 1:
            continue  # 已被自动处理
        candidates.append((h, members))

    print(f"# 候选组复核报告（共 {len(candidates)} 组）\n")
    print("> 「自动可删」= 已由 dedup_tests.py 按同类名同函数名自动处理；本报告只列需人判断的。\n")

    verdict = defaultdict(int)
    for h, members in candidates:
        ctxs = [(m, class_context(m.cls, m.path)) for m in members]
        # 启发式判据
        targets = {c for _, c in ctxs}
        same_target = len(targets) == 1
        verdict["真重复" if same_target else "假重复(需保留)"] += 1

        print(f"## {members[0].name}  ·  {len(members)} 份")
        print(f"- 判定：**{'真重复（可删 N-1 份）' if same_target else '假重复 —— 各测不同目标，保留'}**")
        print("- 被测目标（setUp 里的赋值）：")
        for m, ctx in ctxs:
            print(f"    - `{m.fq}`")
            print(f"      → {ctx}")
        print()

    print("\n## 汇总\n")
    print("| 判定 | 组数 |")
    print("|---|---|")
    for k, v in sorted(verdict.items(), key=lambda x: -x[1]):
        print(f"| {k} | {v} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
