"""O4 重复测试普查：按函数体源码哈希分组，报告每个族的多余份数。

口径（与 docs/BACKLOG_REGISTER.md §3 一致）：
- 只统计 tests/ 与 backend/tests/ 下的 test_*.py
- 分组键 = (函数体源码，去掉注释与 docstring)
- 同名不同类也参与分组 —— 但会被标记为"候选，需人工复核"
"""

from __future__ import annotations

import ast
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
assert (REPO / "tests").is_dir(), f"仓库根解析失败：{REPO}"


def code_only(text: str) -> str:
    """去掉注释与 docstring，只留可执行代码。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def norm_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return code_only(ast.unparse(node))


def family_of(path: Path) -> str:
    """从测试文件名推断被测族：test_<family>_*.py 或 test_<family>.py"""
    stem = path.stem
    if not stem.startswith("test_"):
        return stem
    rest = stem[5:]
    for known in (
        "novel_agent",
        "reading_manager",
        "agent_orchestrator",
        "ai_client",
        "note_manager",
        "diagnostic_logger",
        "memory_manager",
        "character_system",
        "writing_skills",
        "parsing",
        "panel",
    ):
        if rest == known or rest.startswith(known + "_"):
            return known
    return rest.split("_")[0]


def main() -> int:
    files = sorted((REPO / "tests").glob("test_*.py"))
    files += sorted((REPO / "backend" / "tests").glob("test_*.py"))

    # (family, body_hash) -> [(file, class, func, name)]
    groups: dict[tuple[str, str], list[tuple[str, str, str, str]]] = defaultdict(list)

    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"!! skip {f.name}: {e}", file=sys.stderr)
            continue
        fam = family_of(f)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            cls = ""
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and node in parent.body:
                    cls = parent.name
                    break
            h = hashlib.sha256(norm_body(node).encode("utf-8")).hexdigest()[:16]
            groups[(fam, h)].append((f.name, cls, node.name, f"{cls}::{node.name}"))

    # 汇总
    by_fam: dict[str, dict] = defaultdict(lambda: {"groups": 0, "extra": 0, "files": set(), "detail": []})
    total_extra = 0
    for (fam, h), members in groups.items():
        if len(members) < 2:
            continue
        extra = len(members) - 1
        total_extra += extra
        d = by_fam[fam]
        d["groups"] += 1
        d["extra"] += extra
        for m in members:
            d["files"].add(m[0])
        d["detail"].append((h, extra, members))

    print("=" * 78)
    print(f"{'族':<22} {'同体分组':>8} {'可删用例':>8} {'文件数':>6}")
    print("=" * 78)
    for fam in sorted(by_fam, key=lambda k: -by_fam[k]["extra"]):
        d = by_fam[fam]
        print(f"{fam:<22} {d['groups']:>8} {d['extra']:>8} {len(d['files']):>6}")
    print("-" * 78)
    print(f"{'合计':<22} {'':>8} {total_extra:>8}")
    print()

    # novel_agent 明细（最大的族）
    for target in ("novel_agent", "reading_manager", "agent_orchestrator", "ai_client", "note_manager"):
        d = by_fam.get(target)
        if not d:
            print(f"\n### {target}: 无重复")
            continue
        print(f"\n### {target} 明细（{d['groups']} 组 / 可删 {d['extra']}）")
        for h, extra, members in sorted(d["detail"], key=lambda x: -x[1]):
            names = "; ".join(f"{m[0]}::{m[3]}" for m in members)
            print(f"  [{extra}] {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
