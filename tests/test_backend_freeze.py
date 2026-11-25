"""backend 冻结的**机器可验证**守卫。

## 为什么冻结需要一个测试

`docs/ARCHITECTURE_BOUNDARY.md` 早就写了"后端冻结"，但文档不会拦住任何提交。
真正的风险不是"有人故意违反"，而是**顺手**：

- 桌面端某个功能临时想复用后端的 `vector_store`，于是 `app/` 里多了一行
  `from backend.shared...` —— 编译通过、测试通过，但两条产品线从此绑死；
- 半年后想改后端部署形态，发现桌面端 EXE 依赖它，改不动了。

这种依赖一旦建立就很难拆，所以必须在建立的那一刻就失败。

## 三条判据

1. **`app/` 不得 import `backend.`** —— 核心约束（实测当前为 0 处）
2. `backend/README.md` 与 `docs/ARCHITECTURE_BOUNDARY.md` 必须同时存在，
   且都声明了"冻结"
3. `README.md` 目录树里 `backend/` 那行必须带冻结标注

## 判据为什么用 AST 而不是 grep

`app/` 里有一处注释提到 "backend"（本文件的说明、以及 `cloud_storage.py` 里
可能有历史说明）。字符串搜索会把注释里的词当成依赖。用 AST 只看真实的
`import` / `from ... import` 语句。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_APP = _REPO / "app"
_BACKEND = _REPO / "backend"


def _display(path: Path) -> str:
    """展示用路径：仓库内显示相对路径，仓库外（测试临时目录）显示绝对路径。"""
    try:
        return str(path.relative_to(_REPO))
    except ValueError:
        return str(path)


def _backend_imports(root: Path | None = None) -> list[tuple[str, int, str]]:
    """扫 `app/`（或指定目录）下所有 .py，返回真实的 backend 导入。

    返回 `[(文件, 行号, 模块)]`。`root` 可显式传入 —— 反证用例靠它指向临时目录，
    比 monkeypatch 全局变量更可靠（模块路径在 conftest 的 sys.path 收束下不稳定）。
    """
    hits: list[tuple[str, int, str]] = []
    for path in sorted((root or _APP).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "backend" or alias.name.startswith("backend."):
                        hits.append((_display(path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "backend" or mod.startswith("backend."):
                    hits.append((_display(path), node.lineno, mod))
    return hits


class TestDesktopDoesNotDependOnBackend:
    def test_no_backend_imports_in_app(self):
        """核心约束：桌面端不得依赖后端。

        违反后的补救成本极高（要拆共享代码、改部署），所以这里必须硬失败。
        若确实需要共享某个工具函数，应把它**复制/下沉**到 `app/` 内，
        而不是让桌面端 import 后端。
        """
        hits = _backend_imports()
        assert not hits, "桌面端代码依赖了 backend（会绑死两条产品线）：\n" + "\n".join(
            f"  {file}:{line} -> {mod}" for file, line, mod in hits
        )

    def test_scanner_actually_scans(self):
        """反证：扫描器必须真的读到了文件，否则上面那条是空转。"""
        files = [p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts]
        assert len(files) > 100, f"只扫到 {len(files)} 个文件，扫描器可能失效了"

    def test_scanner_detects_a_planted_import(self, tmp_path):
        """反证：把一条 `import backend.x` 塞进 app/，扫描器必须发现。

        这条是本文件最重要的一条 —— 没有它，`test_no_backend_imports_in_app`
        可能因为"扫描逻辑写错"而永远返回空列表（假绿）。
        """
        fake_app = tmp_path / "app"
        fake_app.mkdir()
        (fake_app / "planted.py").write_text("import backend.shared.middleware\n", encoding="utf-8")

        hits = _backend_imports(fake_app)
        assert hits, "扫描器没发现植入的 backend 导入 —— 判据失效"
        assert "backend.shared.middleware" in hits[0][2]

    def test_scanner_ignores_comments_and_strings(self, tmp_path):
        """反证：注释/字符串里提到 backend 不算依赖（否则会误报）。"""
        fake_app = tmp_path / "app"
        fake_app.mkdir()
        (fake_app / "harmless.py").write_text(
            "# 这里说明：不要 import backend\n"
            'MSG = "backend/ 已冻结"\n'
            "def f():\n"
            '    """docstring 里提到 backend 也不算依赖。"""\n',
            encoding="utf-8",
        )
        assert _backend_imports(fake_app) == []


class TestFreezeIsDocumented:
    def test_backend_readme_exists_and_declares_freeze(self):
        readme = _BACKEND / "README.md"
        assert readme.exists(), "backend/README.md 缺失 —— 冻结声明没有落盘"
        text = readme.read_text(encoding="utf-8")
        assert "冻结" in text, "README 没有声明冻结"
        assert "ARCHITECTURE_BOUNDARY" in text, "README 没有指向边界文档（判定标准会分叉）"

    def test_architecture_boundary_exists(self):
        doc = _REPO / "docs" / "ARCHITECTURE_BOUNDARY.md"
        assert doc.exists(), "边界文档缺失 —— 它是冻结约定的权威来源"
        assert "冻结" in doc.read_text(encoding="utf-8")

    def test_root_readme_marks_backend_frozen(self):
        """根 README 的目录树里，`backend/` 那行必须带冻结标注。

        这一条防的是"新人看 README 以为后端还在演进"，然后往里加功能。
        """
        readme = (_REPO / "README.md").read_text(encoding="utf-8")
        lines = [ln for ln in readme.splitlines() if "backend/" in ln and ln.lstrip().startswith(("├", "└", "│"))]
        assert lines, "README 的目录树里找不到 backend/ 条目"
        assert any("冻结" in ln or "⛔" in ln for ln in lines), f"backend/ 条目没有冻结标注：{lines}"

    def test_backend_has_own_tests(self):
        """冻结不意味着不测：已有行为仍要有测试兜住（否则改依赖升级时没保护）。"""
        tests = list((_BACKEND / "tests").glob("test_*.py"))
        assert tests, "backend/tests/ 下没有测试 —— 冻结后连回归保护都没有"


@pytest.mark.parametrize("subdir", ["ai-service", "novel-service", "shared"])
def test_expected_subdirs_exist(subdir):
    """冻结快照里的子目录必须都在（防止"悄悄删掉一个服务"没人发现）。"""
    assert (_BACKEND / subdir).is_dir(), f"backend/{subdir} 不见了"
