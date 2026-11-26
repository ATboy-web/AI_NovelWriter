"""分层架构守卫：把"单向依赖"写成可执行的断言。

## 为什么必须用测试而不是文档

架构评审的意见是「设定单向依赖：领域层不要反向导入面板或具体 Provider」。
这句话写在文档里，半年后没人记得；写成断言，违反时 CI 立刻红。

本文件扫描**源码的 import 语句**（AST），不是靠人眼 review。

## 分层与允许的依赖

    ui (panels 等)  →  application  →  domain
                            ↓
                         ports  ←  adapters

- `domain`：**只允许标准库**。连 `app.storage` 都不行 —— 一旦允许，存储细节就会渗进规则层。
- `ports`：只允许标准库 + `typing`。
- `adapters`：允许 `app.storage`、第三方 SDK；禁止界面与 `application`。
- `application`：允许 `domain` / `ports`；禁止 `adapters`（否则用例就绑死实现）。

## 反向断言（防止"空转通过"）

只断言"没有违规"会漏掉一种情况：**扫描器根本没读到文件**。
所以每个包都额外断言"扫到了至少 N 个模块、且这些模块确实有 import 语句"。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parent.parent / "app"

#: 各层**禁止**出现的顶层模块前缀
FORBIDDEN_PREFIXES: dict[str, tuple[str, ...]] = {
    # 领域层：只有标准库。任何 app.* 都不该出现。
    "domain": ("app.", "tkinter", "customtkinter"),
    # 端口层：只描述接口，不该引入任何具体实现或第三方 SDK。
    "ports": ("app.adapters", "app.application", "app.panels", "app.storage", "app.ai_client", "tkinter"),
    # 适配器：可以碰存储与 SDK，但不能碰界面，也不能反向依赖用例层。
    "adapters": ("app.application", "app.panels", "tkinter", "customtkinter"),
    # 应用层：只编排 domain 与 ports。直接 import 适配器会让用例绑死实现。
    "application": ("app.adapters", "app.panels", "tkinter", "customtkinter"),
}


def _imported_modules(path: Path) -> list[str]:
    """返回该文件里所有 import 的模块名（含 `from x import y` 的 x）。"""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对导入（from . import x / from .mod import y）
                # 相对导入归一到本层内部，不构成跨层违规
                names.append("." * node.level + (node.module or ""))
            elif node.module:
                names.append(node.module)
    return names


class TestLayerIsolation:
    @pytest.mark.parametrize("layer", sorted(FORBIDDEN_PREFIXES))
    def test_layer_does_not_import_upward(self, layer):
        """本层不得 import 上层/越界模块。"""
        pkg = _APP / layer
        assert pkg.is_dir(), f"分层目录不存在：{pkg}"
        files = sorted(pkg.rglob("*.py"))
        assert files, f"{layer} 层没有任何模块（分层被删空？）"

        violations: list[str] = []
        for path in files:
            for module in _imported_modules(path):
                if module.startswith("."):
                    continue  # 相对导入：本层内部
                for bad in FORBIDDEN_PREFIXES[layer]:
                    if module == bad.rstrip(".") or module.startswith(bad):
                        violations.append(f"{path.relative_to(_APP.parent)} → {module}")

        assert not violations, f"{layer} 层出现了越界导入：\n  " + "\n  ".join(violations)

    def test_domain_is_importable_without_side_effects(self):
        """领域层应当能被单独导入（不触发任何 Tk / 网络 / 磁盘副作用）。"""
        import importlib

        importlib.import_module("app.domain.branch")

    def test_each_layer_has_modules(self):
        """反向断言：确认扫描器真的读到了文件，避免"空目录 ⇒ 通过"。"""
        counts = {layer: len(list((_APP / layer).rglob("*.py"))) for layer in FORBIDDEN_PREFIXES}
        assert all(n >= 1 for n in counts.values()), f"某层为空，守卫可能空转：{counts}"


class TestCompatibility:
    """旧调用路径必须继续可用 —— 这是"渐进式迁移"的底线。"""

    def test_legacy_entry_point_still_exists(self):
        from app import lineage

        assert callable(lineage.discover_branches)

    def test_legacy_and_new_layers_agree(self, tmp_path):
        """同一个目录，旧接口与新分层给出的分支信息必须一致。"""
        from app.adapters import FileBranchMetaReader
        from app.application import ListBranches
        from app.lineage import discover_branches

        # 造两个分支：一个正常，一个缺 meta
        base = tmp_path / "timelines"
        base.mkdir()
        good = base / "branch_000"
        good.mkdir()
        (good / "meta.json").write_text(
            '{"title": "分支甲", "origin_chapter": 5, "chapter_count": 7}', encoding="utf-8"
        )
        (base / "branch_001").mkdir()

        legacy = {b["branch_id"]: b for b in discover_branches(tmp_path)}
        modern = {row.info.branch_id: row.info for row in ListBranches(reader=FileBranchMetaReader()).execute(tmp_path)}

        assert set(legacy) == set(modern) == {"000", "001"}
        for bid, info in modern.items():
            assert legacy[bid]["title"] == info.title
            assert legacy[bid]["origin_chapter"] == info.origin_chapter
            assert legacy[bid]["chapter_count"] == info.chapter_count
            assert legacy[bid]["openable"] == info.openable
            assert legacy[bid]["reason"] == info.reason


class TestAgentLayerSourceList:
    """`_source_scan.AGENT_LAYER_FILES` 的正确性由 4 个守卫共同依赖。

    清单里只要有一个路径写错（或文件被删），`agent_layer_code()` 就会少一段内容，
    那些守卫随之静默放宽 —— 而它们本身是"某段实现还在不在"的唯一防线。
    """

    def test_every_listed_file_exists(self):
        import _source_scan as scan

        missing = [p for p in scan.AGENT_LAYER_FILES if not (Path(__file__).parent.parent / p).is_file()]
        assert not missing, f"agent 层清单里的文件不存在：{missing}"

    def test_agent_layer_code_is_substantial(self):
        import _source_scan as scan

        code = scan.agent_layer_code()
        assert len(code) > 50_000, f"agent 层源码只有 {len(code)} 字符，拼接可能失效"

    def test_layer_files_live_in_expected_places(self):
        import _source_scan as scan

        for path in scan.AGENT_LAYER_FILES:
            assert path.startswith("app/"), f"{path} 不在 app/ 下"


class TestRelativeImportsResolve:
    """子包内的相对导入必须指向**真实存在**的同级模块。

    只查一层 `from .x import`：多级（`from ..x`）另有分层守卫管，
    而这类事故的实际形态就是"单级相对导入跟着函数体搬错了包"。
    """

    @pytest.mark.parametrize("package", ["application", "domain", "adapters", "ports"])
    def test_single_dot_imports_point_to_existing_modules(self, package: str):
        pkg_dir = _APP / package
        missing: list[str] = []

        for path in sorted(pkg_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level != 1 or not node.module:
                    continue
                target = pkg_dir / f"{node.module.split('.')[0]}.py"
                target_pkg = pkg_dir / node.module.split(".")[0]
                if not target.is_file() and not target_pkg.is_dir():
                    missing.append(f"{path.name}:{node.lineno} → .{node.module}")

        assert not missing, (
            "这些相对导入在 " + package + "/ 下解析不到（会静默 ImportError）：\n  " + "\n  ".join(missing)
        )

    def test_scanner_sees_imports_at_all(self):
        """反向断言：扫描器要真读到相对导入，否则上面那条永远绿。"""
        found = 0
        for path in sorted((_APP / "application").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found += sum(1 for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module)
        assert found >= 3, f"application/ 下只扫到 {found} 条相对导入，扫描器可能失效"
