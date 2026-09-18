"""模块依赖关系梳理器（v3.2 新增）。

## 用途

把 `app/` 与根编排文件的 **import 关系**变成可读的图与报告，用于：

1. **发现循环依赖** —— 循环导入在 Python 里的表现是"有时能跑、有时 ImportError"，
   取决于谁先被导入。这是典型的"运行崩坏"来源，且**不会在测试里稳定复现**，
   所以必须靠静态分析找。
2. **发现分层破坏** —— 例如 `app/parsing.py`（纯工具）反向 import `app/panels/*`（UI）。
3. **发现孤儿模块** —— 没有任何生产代码引用（本仓最高频失效模式「注册即遗忘」的入口）。
4. **给出"谁被最多人依赖"的热点** —— 这些模块的改动风险最高，值得加测试。

## 为什么是脚本而不是文档里手画一张图

手画的图**必然漂移**（本仓已因「同一事实写两处」踩过 5 次）。
这里的图是**从源码现算**的，还配了守卫测试：
源码结构变了而图没更新，测试会变红。

## 用法

    python scripts/module_graph.py              # 打印摘要 + 写 docs/MODULE_DEPENDENCY_MAP.md
    python scripts/module_graph.py --check      # 只校验（有循环则退出码 1），不写文件
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _console_utf8 import make_stdout_utf8_safe  # noqa: E402

# ❗ 不在模块级调用 `make_stdout_utf8_safe()`：
# 本模块会被 `tests/test_module_graph.py` import 来复用分析函数，
# 而模块级重配 stdout 会干扰 pytest 的输出捕获。
# 切编码只在**真正当脚本跑**时需要，所以放进 `main()`。

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
DOC_PATH = REPO_ROOT / "docs" / "MODULE_DEPENDENCY_MAP.md"

#: 按字符串动态加载的模块（静态 import 图看不到这些边，需单独标注）。
#: 依据：`panels/registry.NATIVE_PANEL_MODULES` 与 `panels/legacy.py` 的 `importlib` 用法。
DYNAMIC_HINT = "（由 registry/legacy 按字符串加载，静态图看不到这条边）"


def _module_name(path: Path) -> str:
    """文件路径 → 模块名（`app/panels/host.py` → `app.panels.host`）。"""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(module: str, level: int, target: str | None) -> str | None:
    """把 `from ..foo import bar` 解析成绝对模块名。"""
    if level == 0:
        return target
    parts = module.split(".")
    if not target:
        # `from . import x` —— 目标就是包本身
        base = parts[: len(parts) - level] if level <= len(parts) else []
        return ".".join(base) if base else None
    # 相对导入的基准是"当前包的父级"
    base = parts[: len(parts) - level]
    return ".".join(base + [target]) if base else target


def _type_checking_lines(tree: ast.AST) -> set[int]:
    """收集 `if TYPE_CHECKING:` 块覆盖的行号。

    ❗ 这一条是本工具**准确性**的关键。`if TYPE_CHECKING:` 里的 import
    **运行时根本不执行**，它只是给类型标注用的。若把它算作依赖，
    会凭空造出"循环依赖" —— 实测就误报了 `writing_skills_panel <-> novel_app`
    （真正的 import 在 `if TYPE_CHECKING:` 内，`novel_app` 反向 module-level 导入它，
    看图上是个环，实际运行永远不成立）。

    误报的代价不只是"图难看"：别人会去"修"一个并不存在的问题。
    """
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_tc:
            continue
        for sub in ast.walk(node):
            lineno = getattr(sub, "lineno", None)
            if lineno is not None:
                lines.add(lineno)
    return lines


def collect_imports(path: Path) -> tuple[dict[str, str], bool]:
    """返回 `({目标模块: 边类型}, 是否有语法错误)`；边类型取 `"module"` / `"deferred"`。

    ❗ 函数内 `import` 必须单独标注，不能与模块级等同看待：
    一条边是"模块级"还是"延迟"**决定了循环依赖是否真的会炸**（见 `classify_cycle`）。
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return {}, True

    module = _module_name(path)
    type_checking = _type_checking_lines(tree)
    edges: dict[str, str] = {}

    # 模块级 import 的行号集合：不在其中的即"函数内延迟导入"
    module_level_lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for sub in ast.walk(node):
                if hasattr(sub, "lineno"):
                    module_level_lines.add(sub.lineno)

    def _record(target: str | None, lineno: int) -> None:
        if not target or not _is_internal(target):
            return
        if target == module:
            return  # 自环无意义
        if lineno in type_checking:
            return  # TYPE_CHECKING 不是运行时依赖
        kind = "module" if lineno in module_level_lines else "deferred"
        # 同一目标同时有模块级与延迟引用时，"模块级"更强，保留它
        if edges.get(target) == "module":
            return
        edges[target] = kind

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _record(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_relative(module, node.level or 0, node.module)
            _record(target, node.lineno)
            # `from app.providers import balance` 里 balance 可能是个模块
            for alias in node.names:
                if target:
                    candidate = f"{target}.{alias.name}"
                    if _module_exists(candidate):
                        _record(candidate, node.lineno)
    return edges, False


_INTERNAL_PREFIXES = ("app", "novel_app")


def _is_internal(name: str) -> bool:
    return name.split(".")[0] in _INTERNAL_PREFIXES


_MODULE_CACHE: dict[str, bool] = {}


def _module_exists(name: str) -> bool:
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    parts = name.split(".")
    base = REPO_ROOT.joinpath(*parts)
    exists = base.with_suffix(".py").exists() or (base / "__init__.py").exists()
    _MODULE_CACHE[name] = exists
    return exists


def discover_modules() -> list[Path]:
    files = sorted(APP_DIR.rglob("*.py"))
    root_entry = REPO_ROOT / "novel_app.py"
    if root_entry.exists():
        files.append(root_entry)
    return [f for f in files if "__pycache__" not in f.parts]


def build_graph() -> dict:
    modules = discover_modules()
    names = {_module_name(p) for p in modules}
    edges: dict[str, dict[str, str]] = defaultdict(dict)
    broken: list[str] = []
    for path in modules:
        name = _module_name(path)
        found, bad = collect_imports(path)
        if bad:
            broken.append(name)
            continue
        for target, kind in found.items():
            # 只保留指向真实内部模块（或已知包的父级）的边
            if target in names or _is_prefix_of_known(target, names):
                edges[name][target] = kind
    return {
        "modules": sorted(names),
        "edges": {k: dict(sorted(v.items())) for k, v in sorted(edges.items())},
        "broken": broken,
    }


def classify_cycle(component: list[str], edges: dict[str, dict[str, str]]) -> str:
    """判断一个环是 **hard**（真会炸）还是 **latent**（当前安全，但有隐患）。

    判据：**环上所有边都是模块级 import** ⇒ hard。

    - 全是模块级 ⇒ 导入其中任意一个都会在导入期把整条链拉起来，
      而链上最后一个又要回过头导入第一个（还没执行完）⇒ `ImportError`。
    - 只要**有一条**边是延迟导入（写在函数体里）⇒ Python 能顺利走完初始导入，
      那条边等到函数被调用时才执行，此时模块早已加载完 ⇒ 不会炸。

    这个区分很重要：本仓目前 3 个环**全部是 latent**，
    所以"发现循环依赖"不等于"程序会崩" —— 报告必须说清楚，
    否则会让人误以为有 3 个严重 bug 要紧急修。
    """
    for i, src in enumerate(component):
        dst = component[(i + 1) % len(component)]
        kinds = []
        if dst in edges.get(src, {}):
            kinds.append(edges[src][dst])
        # 环上的边可能不是"相邻"配对（SCC 只保证连通），
        # 所以退化判据：只要环内任意一条边是模块级，就算 hard 的候选
        if not kinds:
            kinds = [k for t, k in edges.get(src, {}).items() if t in component]
        if kinds and all(k == "module" for k in kinds):
            continue
        return "latent"
    return "hard"


def _cycle_edges(component: list[str], edges: dict[str, dict[str, str]]) -> list[tuple[str, str, str]]:
    """列出环内的边（含种类），用于报告里展示"哪条是延迟的"。"""
    inside = set(component)
    result = []
    for src in component:
        for dst, kind in edges.get(src, {}).items():
            if dst in inside:
                result.append((src, dst, kind))
    return sorted(result)


def _is_prefix_of_known(name: str, known: set[str]) -> bool:
    """`from app.providers import x` 里 `app.providers` 是包 ⇒ 目标可能不存在同名模块。"""
    return any(k.startswith(name + ".") for k in known)


def find_cycles(edges: dict[str, dict[str, str]]) -> list[list[str]]:
    """Tarjan 强连通分量 —— 任一大小 > 1 的分量就是一个环。"""
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    result: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True
        for successor in sorted(edges.get(node, {})):
            if successor not in index:
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif on_stack.get(successor):
                lowlink[node] = min(lowlink[node], index[successor])
        if lowlink[node] == index[node]:
            component = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == node:
                    break
            if len(component) > 1:
                result.append(sorted(component))

    all_nodes = set(edges) | {t for targets in edges.values() for t in targets}
    for node in sorted(all_nodes):
        if node not in index:
            strongconnect(node)
    return sorted(result, key=lambda c: (-len(c), c))


def _short(name: str) -> str:
    """`app.panels.host` → `panels.host`（去掉 app. 前缀，报告更紧凑）。"""
    return name[4:] if name.startswith("app.") else name


def render_markdown(graph: dict, cycles: list[list[str]]) -> str:
    modules: list[str] = graph["modules"]
    edges: dict[str, dict[str, str]] = graph["edges"]

    reverse: dict[str, set[str]] = defaultdict(set)
    for src, targets in edges.items():
        for t in targets:
            reverse[t].add(src)

    total_edges = sum(len(v) for v in edges.values())
    deferred_count = sum(1 for v in edges.values() for k in v.values() if k == "deferred")
    graded = [(comp, classify_cycle(comp, edges)) for comp in cycles]
    hard = [c for c, g in graded if g == "hard"]

    lines = [
        "# 模块依赖关系图（自动生成）",
        "",
        "> ⚠️ **本文件由 `scripts/module_graph.py` 从源码现算生成，请勿手工编辑。**",
        "> 手工维护的依赖图必然漂移（本仓「同一事实写两处」已踩过 5 次）。",
        "> 重新生成：`python scripts/module_graph.py`",
        "",
        "## 1. 总览",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 内部模块数 | {len(modules)} |",
        f"| 依赖边数 | {total_edges} |",
        f"| 其中函数内延迟导入 | {deferred_count} |",
        f"| 循环依赖环数 | {len(cycles)}（**会真炸的：{len(hard)}**） |",
        f"| 语法错误文件 | {len(graph['broken'])} |",
        "",
        "> **口径说明**：`if TYPE_CHECKING:` 里的 import **不计入** —— 运行时根本不执行。",
        "> 把类型标注当依赖会凭空造出循环（实测误报过 `writing_skills_panel <-> novel_app`）。",
        "",
    ]

    if graph["broken"]:
        lines += ["### ⚠️ 解析失败的文件", ""]
        lines += [f"- `{m}`" for m in graph["broken"]]
        lines.append("")

    lines += ["## 2. 循环依赖", ""]
    if not cycles:
        lines += ["✅ **未发现循环依赖。**", ""]
    else:
        lines += [
            "环分两类，**处置优先级完全不同**：",
            "",
            "| 类型 | 判据 | 含义 |",
            "|---|---|---|",
            "| 🔴 **hard** | 环上**每条边都是模块级 import** | 导入期就会互相等待 ⇒ 真的会 `ImportError` |",
            "| 🟡 **latent** | 环上**至少有一条延迟导入** | 当前不会炸，但结构脆弱：有人把那条延迟导入提到模块级，立刻变 hard |",
            "",
        ]
        for i, comp in enumerate(cycles, 1):
            grade = classify_cycle(comp, edges)
            icon = "🔴" if grade == "hard" else "🟡"
            lines.append(f"### {icon} 环 {i} · {grade}（{len(comp)} 个模块）")
            lines.append("")
            lines += [f"- `{_short(name)}`" for name in comp]
            lines.append("")
            lines.append("| 边 | 种类 |")
            lines.append("|---|---|")
            for src, dst, kind in _cycle_edges(comp, edges):
                label = "🔴 模块级" if kind == "module" else "🟡 延迟（函数内）"
                lines.append(f"| `{_short(src)}` → `{_short(dst)}` | {label} |")
            lines.append("")

    lines += ["## 3. 被依赖最多的模块（改动风险最高）", ""]
    lines += ["| 模块 | 被引用次数 |", "|---|---|"]
    hot = sorted(reverse.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:20]
    for name, dependents in hot:
        lines.append(f"| `{_short(name)}` | {len(dependents)} |")
    lines.append("")
    lines += [
        "> 这些模块被最多人依赖 ⇒ 改它们的破坏面最大，应当优先保证测试覆盖。",
        "",
    ]

    lines += ["## 4. 孤儿模块（无生产代码引用）", ""]
    orphans = [
        m
        for m in modules
        if not reverse.get(m) and not m.endswith("__init__") and m != "novel_app" and not m.startswith("app.panels.")
    ]
    if orphans:
        lines += [
            "> ❗ 本仓最高频失效模式「注册即遗忘」的第一道筛查。",
            "> 但要人工确认：**面板、入口脚本、按字符串加载的模块会正常出现在这里**。",
            "",
        ]
        lines += [f"- `{_short(m)}`" for m in orphans]
    else:
        lines += ["✅ 无。"]
    lines.append("")

    lines += ["## 5. 完整依赖表", "", "| 模块 | 依赖（🔴=模块级 / ⚪=延迟） |", "|---|---|"]
    for name in modules:
        targets = edges.get(name)
        if not targets:
            lines.append(f"| `{_short(name)}` | — |")
            continue
        shown = ", ".join(f"{'🔴' if kind == 'module' else '⚪'}`{_short(t)}`" for t, kind in sorted(targets.items()))
        lines.append(f"| `{_short(name)}` | {shown} |")
    lines.append("")
    lines += [
        "## 6. 动态加载说明",
        "",
        DYNAMIC_HINT,
        "",
        "受影响的模块：",
        "",
    ]
    lines += [f"- `{_short(m)}`" for m in modules if m.startswith("app.panels.")]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    make_stdout_utf8_safe()  # 只有真当脚本跑时才需要（见文件上方说明）
    parser = argparse.ArgumentParser(description="模块依赖关系梳理")
    parser.add_argument("--check", action="store_true", help="只校验：存在 hard 循环则退出码 1")
    args = parser.parse_args()

    graph = build_graph()
    edges = graph["edges"]
    cycles = find_cycles(edges)

    print(f"内部模块数：{len(graph['modules'])}")
    print(f"依赖边数：{sum(len(v) for v in edges.values())}")
    hard = [c for c in cycles if classify_cycle(c, edges) == "hard"]
    print(f"循环依赖环数：{len(cycles)}（hard={len(hard)} / latent={len(cycles) - len(hard)}）")
    for i, comp in enumerate(cycles, 1):
        grade = classify_cycle(comp, edges)
        print(f"  [{grade}] 环 {i}: {' <-> '.join(_short(c) for c in comp)}")
    if graph["broken"]:
        print(f"❗ 解析失败：{graph['broken']}")

    if args.check:
        return 1 if hard else 0

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render_markdown(graph, cycles), encoding="utf-8")
    print(f"已写入 {DOC_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
