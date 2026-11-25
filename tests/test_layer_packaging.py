"""分层包的打包可达性守卫。

## 为什么需要

PyInstaller 靠**模块级** import 静态分析来收集依赖。函数内的 `import x`
它看不见 —— 除非把 x 写进 spec 的 `hiddenimports`。

本次新增的 `app/domain` / `app/ports` / `app/adapters` / `app/application`
**没有**进 `installer/novel_app.spec` 的 hiddenimports，而是靠
`app/lineage.py` 里的模块级 import 被自动收集。

这条路径很脆弱：谁把那条 import 挪进函数，打包出来的 EXE 就会在
"列出分支"时 `ModuleNotFoundError` —— 而本地跑测试永远发现不了
（本地能 import，因为源码在）。

所以这里直接断言：**每个分层包至少被一处模块级 import 引用**。
一旦变成"只在函数内导入"，测试变红，提示要么改回模块级、要么补 hiddenimports。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parent.parent / "app"

#: 本次架构样板新增的包（需要保证打包时被收集）
LAYER_PACKAGES = ("app.domain", "app.ports", "app.adapters", "app.application")


def _module_level_imports() -> set[str]:
    """收集全仓**模块级**（非函数内）的 import 目标。"""
    found: set[str] = set()
    for path in _APP.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:  # 只看顶层语句，不进函数体
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module)
    return found


class TestLayerPackaging:
    @pytest.mark.parametrize("pkg", LAYER_PACKAGES)
    def test_layer_package_is_statically_imported(self, pkg):
        """每个分层包必须被至少一处模块级 import —— 否则 EXE 会缺它。"""
        imports = _module_level_imports()
        hit = any(name == pkg or name.startswith(pkg + ".") for name in imports)
        assert hit, (
            f"{pkg} 没有被任何模块级 import 引用。PyInstaller 将不会收集它，"
            f"打包后的 EXE 会在运行时 ModuleNotFoundError。"
            f"解法：在引用处改回模块级 import，或把它加进 installer/novel_app.spec 的 hiddenimports。"
        )

    def test_guard_is_not_vacuous(self):
        """反证：确认扫描器真的读到了模块级 import（否则上面的断言是空转）。"""
        imports = _module_level_imports()
        assert len(imports) > 20, f"只扫到 {len(imports)} 个模块级 import，疑似扫描失效"
        assert "app.storage" in imports
