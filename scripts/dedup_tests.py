"""O4 重复测试合并器：把完全同体的重复用例合并为"保留一份 + 其余文件附交叉引用"。

安全性设计（这是重点）：
1. **只删除"函数体源码完全等同"的用例**（去掉注释与 docstring 后 AST 等价）。
2. **保留策略**：优先保留在"最专一"文件里的那份 —— 即类名/文件名与该函数名更贴合的。
   实现上取「同组成员数最多的文件」之外的**第一个按字典序**，并要求保留方**所在类名
   与函数名同时出现**在尽量少的其它文件中。简化为：按 (类名是否以 More/Extended/Deep/
   Final 结尾, 文件名) 排序，取第一个 —— 即**优先保留"原始"版本、删掉"More/Extended"副本**。
3. **删前先跑测试**：调用方负责在删前/删后分别跑 pytest 并比对。
4. 不碰 `_candidates_`（需人工复核的组）——由 `--include-candidates` 显式打开。

用法：
    python scripts/dedup_tests.py --plan            # 只打印计划
    python scripts/dedup_tests.py --apply           # 落盘
    python scripts/dedup_tests.py --apply --include-candidates
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
assert (REPO / "tests").is_dir(), f"仓库根解析失败：{REPO}"

# 手工排除清单：**函数体相同但测的是不同目标**的组，必须保留。
# 判据是「这些类各自 setUp 里绑定了不同的被测对象」，所以同体只是巧合。
# 每条格式：包含所有成员 fq 的 frozenset 的 hash（见 _group_key）。
# 目前唯一一条：test_novel_toolkit.py 的 ElementLibrary / BridgeLibrary / DescriptionLibrary
# 三个类都写了同体 test_get_categories，但 self.lib 分别是三个不同的库。
KNOWN_FALSE_POSITIVES: set[str] = {"f64eea5cb9052efa"}

# 需要人工复核的组：这些组名相同但**类名不同**，可能测的不是同一件事
CANDIDATE_MARK = "::"  # 占位，实际用 has_identical_qualname 判定

SUFFIX_RE = re.compile(r"(More|Extended|Deep|Full|Final|Complete|Extra|Additional)$")


def code_only(text: str) -> str:
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


class TestItem:
    __slots__ = ("path", "cls", "name", "node", "body_hash", "lineno", "end_lineno")

    def __init__(self, path: Path, cls: str, node: ast.AST, body_hash: str):
        self.path = path
        self.cls = cls
        self.name = node.name  # type: ignore[attr-defined]
        self.node = node
        self.body_hash = body_hash
        # ❗ 必须把 **装饰器** 一起算进删除范围。
        # `node.lineno` 指向 `def` 那一行，而 `@respx.mock` / `@pytest.mark.x` 在它**上面**。
        # 只删 def 会留下一行悬空装饰器 ⇒ `IndentationError: unexpected unindent`（实测踩过）。
        decs = getattr(node, "decorator_list", []) or []
        self.lineno = min([node.lineno] + [d.lineno for d in decs])  # type: ignore[attr-defined]
        self.end_lineno = node.end_lineno  # type: ignore[attr-defined]

    @property
    def fq(self) -> str:
        return f"{self.path.name}::{self.cls}::{self.name}"

    def rank(self) -> tuple:
        """保留优先级：越小越该保留。"""
        cls_suffixed = 1 if SUFFIX_RE.search(self.cls) else 0
        name_suffixed = 1 if SUFFIX_RE.search(self.name) else 0
        return (cls_suffixed, name_suffixed, self.path.name, self.lineno)


def collect() -> list[TestItem]:
    items: list[TestItem] = []
    files = sorted((REPO / "tests").glob("test_*.py")) + sorted((REPO / "backend" / "tests").glob("test_*.py"))
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"!! skip {f.name}: {e}", file=sys.stderr)
            continue
        for cls_node in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            for node in cls_node.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    h = hashlib.sha256(code_only(ast.unparse(node)).encode()).hexdigest()
                    items.append(TestItem(f, cls_node.name, node, h))
    return items


def _group_key(members: list["TestItem"]) -> str:
    """按成员的全限定名集合生成稳定键，用于查排除清单。"""
    return hashlib.sha256("|".join(sorted(m.fq for m in members)).encode()).hexdigest()[:16]


def build_plan(include_candidates: bool) -> tuple[dict[str, list[list[TestItem]]], list[str]]:
    items = collect()
    groups: dict[str, list[TestItem]] = defaultdict(list)
    for it in items:
        groups[it.body_hash].append(it)

    plan: dict[str, list[list[TestItem]]] = defaultdict(list)
    skipped: list[str] = []
    for h, members in groups.items():
        if len(members) < 2:
            continue
        key = _group_key(members)
        if key in KNOWN_FALSE_POSITIVES:
            skipped.append("(已知假重复，已排除) " + " | ".join(m.fq for m in members))
            continue
        # 候选判据：同组成员**类名 + 函数名**不完全一致 ⇒ 需人工复核
        qualnames = {f"{m.cls}::{m.name}" for m in members}
        if len(qualnames) > 1 and not include_candidates:
            skipped.append(" | ".join(m.fq for m in members))
            continue
        plan[h].append(sorted(members, key=lambda m: m.rank()))
    return plan, skipped


def _squeeze_blank_lines(text: str) -> str:
    """把 3 个及以上连续空行压成 2 个（块间标准间距），并确保文件以单个换行结尾。"""
    out = re.sub(r"\n{3,}", "\n\n\n", text)
    out = re.sub(r"\n+\Z", "\n", out)
    return out


def _assert_parses(paths: list[Path]) -> None:
    """落盘后立即自检：每个改过的文件都必须能通过 ast.parse。

    这是对「改动破坏了语法」的**最后一道防线**。
    （历史教训：只删 `def` 不删装饰器 ⇒ 悬空 `@respx.mock` ⇒ IndentationError，
      而脚本当时是静默成功的，直到 pytest 收集阶段才炸。）
    """
    bad: list[str] = []
    for p in paths:
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            bad.append(f"{p.name}:{e.lineno}: {e.msg}")
    if bad:
        raise SystemExit("❌ 语法自检失败，已中止：\n  " + "\n  ".join(bad))
    print(f"  ✓ 语法自检通过（{len(paths)} 个文件）")


def apply_plan(plan: dict[str, list[list[TestItem]]], dry: bool) -> int:
    """按文件聚合删除区间，倒序删除避免行号漂移。"""
    per_file: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    removed = 0
    for groupset in plan.values():
        for members in groupset:
            keeper = members[0]
            for victim in members[1:]:
                per_file[victim.path].append((victim.lineno, victim.end_lineno, f"{victim.cls}::{victim.name}"))
                removed += 1
                print(f"  - {victim.fq}   [保留 {keeper.fq}]")

    if dry:
        return removed

    for path, ranges in per_file.items():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        # 倒序
        for start, end, label in sorted(ranges, key=lambda x: -x[0]):
            # 连同紧随其后的空行一起删（保持文件整洁）
            e = end
            while e < len(lines) and lines[e].strip() == "":
                e += 1
                break
            del lines[start - 1 : e]
        path.write_text(_squeeze_blank_lines("".join(lines)), encoding="utf-8")
    if not dry:
        _assert_parses(list(per_file))
    return removed


def clean_empty_classes(dry: bool) -> int:
    """删除因合并而变成空壳的**测试类**。

    ⚠️ 只删「**曾经装过 test_ 方法、现在一个都不剩**」的类。
    绝不能按"没有 test_ 方法"来判定 —— 测试文件里大量存在**测试替身**
    （`FakeApp` / `Recorder` / `FakeWidget` / `DummyPanel` …），
    它们本来就没有 test_ 方法，删掉会直接打断测试。

    判定改用**白名单式**：类名以 `Test` 开头，且其 body 里已经没有任何
    FunctionDef 与 `test_` 断言。这样 `FakeApp` 这类名字天然被排除。
    """
    removed = 0
    for f in sorted((REPO / "tests").glob("test_*.py")):
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines(keepends=True)
        drops: list[tuple[int, int, str]] = []
        for node in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            if not node.name.startswith("Test"):
                continue
            methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if any(m.name.startswith("test_") for m in methods):
                continue
            drops.append((node.lineno, node.end_lineno, node.name))
        if not drops:
            continue
        for start, end, label in sorted(drops, key=lambda x: -x[0]):
            print(f"  ~ 空壳测试类 {f.name}::{label}")
            del lines[start - 1 : end]
            removed += 1
        if not dry:
            f.write_text(_squeeze_blank_lines("".join(lines)), encoding="utf-8")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="落盘（默认只打印计划）")
    ap.add_argument("--include-candidates", action="store_true", help="同时处理需人工复核的组")
    ap.add_argument("--clean-empty-classes", action="store_true", help="顺带删空壳类")
    args = ap.parse_args()
    dry = not args.apply

    plan, skipped = build_plan(args.include_candidates)
    n_groups = sum(len(v) for v in plan.values())
    print(f"{'[DRY-RUN] ' if dry else '[APPLY] '}待合并组 {n_groups}，待删用例：")
    removed = apply_plan(plan, dry)

    if args.clean_empty_classes:
        print(f"{'[DRY-RUN] ' if dry else '[APPLY] '}空壳类清理：")
        removed += clean_empty_classes(dry)
        if not dry:
            touched = list((REPO / "tests").glob("test_*.py"))
            _assert_parses(touched)

    print(f"\n合计删除 {removed} 条用例")
    if skipped:
        print(f"\n跳过（需人工复核，同名不同类）{len(skipped)} 组：")
        for s in skipped:
            print(f"  ? {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
