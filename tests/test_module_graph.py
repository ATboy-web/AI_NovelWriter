"""模块依赖图的守卫测试（v3.2）。

## 本文件守住三件事

1. **没有 hard 循环依赖** —— 这是"降低运行崩坏风险"的直接防线。
   hard 环意味着导入期就会互相等待 ⇒ `ImportError`，而且**取决于谁先被导入**，
   所以不会在测试里稳定复现。必须静态拦。

2. **依赖图文档不漂移** —— `docs/MODULE_DEPENDENCY_MAP.md` 是从源码现算的。
   源码结构变了而文档没重算，就等于文档在骗人。
   这是本仓「同一事实写两处必然漂移」的标准收口手法：**一处派生 + 测试钉住**。

3. **分析器本身有牙齿** —— ❗ 最容易忽略的一条。
   一个"永远报告没有循环"的分析器会让上面两条变成恒真断言。
   所以要用**人造的 hard 环**验证它真的能报出来。
   本仓已多次因为"守卫恒真"白跑验证（负向对照是硬纪律）。

## 为什么允许 latent 环存在

两个 latent 环都是**有意为之**的历史决策，不是疏漏：

- `panels.base ↔ panels.legacy ↔ panels.registry`：
  `base.py` 里的延迟导入带注释"registry 需反向引用本模块做类型标注"。
- `config ↔ secure_config`：`secure_config` 必须在模块级拿到
  `SENSITIVE_CONFIG_FIELDS` 等常量，而 `config` 只在方法里需要 `SecureConfig`。

拆掉它们需要"把共享常量下沉成第三个模块"，而那会**动到一条安全不变式**：
`tests/test_config_consistency.py` 明确规定"全仓只允许 `config.py` 出现该清单的字面量"。
为一个**当前不会炸**的环去改安全守卫，风险大于收益。

所以本轮的处置是：**不动代码，把这个"脆弱但安全"的性质变成被测试强制的性质** ——
任何人把那条延迟导入提到模块级，立刻变红。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DOC_PATH = REPO_ROOT / "docs" / "MODULE_DEPENDENCY_MAP.md"


def _load_module_graph():
    """按路径加载 `scripts/module_graph.py`（`scripts` 不是包，不能直接 import）。"""
    path = REPO_ROOT / "scripts" / "module_graph.py"
    spec = importlib.util.spec_from_file_location("_anw_module_graph", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_anw_module_graph"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mg = _load_module_graph()

#: 已知的 latent 环（已人工确认过成因与不修的理由，见本文件文档字符串）。
#: 这里**把集合写死**：新增环必须显式登记，否则测试变红 ——
#: 目的是让"结构变化"永远需要一次人工确认，而不是被静默接受。
KNOWN_LATENT_CYCLES: set[frozenset[str]] = {
    frozenset({"app.panels.base", "app.panels.legacy", "app.panels.registry"}),
    frozenset({"app.config", "app.secure_config"}),
}


@pytest.fixture(scope="module")
def graph():
    return mg.build_graph()


@pytest.fixture(scope="module")
def cycles(graph):
    return mg.find_cycles(graph["edges"])


# ====================================================================== 1. 没有 hard 环


class TestNoHardCycles:
    def test_no_hard_circular_imports(self, graph, cycles):
        """🔴 核心防线：任何 hard 环都必须立刻修。

        hard 环 = 环上每条边都是模块级 import ⇒ 导入期死锁。
        修法通常是把它中的某条 import 挪进函数体（延迟导入）。
        """
        hard = [c for c in cycles if mg.classify_cycle(c, graph["edges"]) == "hard"]
        pretty = "\n".join("  " + " <-> ".join(mg._short(m) for m in c) for c in hard)
        assert not hard, f"发现 hard 循环依赖（导入期会 ImportError）：\n{pretty}"

    def test_all_cycles_are_latent(self, graph, cycles):
        """当前所有环都应是 latent —— 若这条红了，说明结构真的变脆弱了。"""
        for c in cycles:
            assert mg.classify_cycle(c, graph["edges"]) == "latent", f"{c} 变成了 hard 环"


class TestCycleRegistry:
    def test_no_unexpected_new_cycles(self, cycles):
        """新增环必须显式登记（迫使一次人工确认）。

        ❗ 反过来也要拦：如果某个已知环**消失**了，说明有人重构了 ——
        那就该把它从 `KNOWN_LATENT_CYCLES` 里删掉，保持这份登记是事实。
        """
        found = {frozenset(c) for c in cycles}
        new = found - KNOWN_LATENT_CYCLES
        gone = KNOWN_LATENT_CYCLES - found
        assert not new, f"出现了未登记的新循环依赖：{[sorted(c) for c in new]}"
        assert not gone, f"这些已登记的环消失了，请更新 KNOWN_LATENT_CYCLES：{[sorted(c) for c in gone]}"

    def test_no_syntax_errors_in_any_module(self, graph):
        assert graph["broken"] == [], f"这些文件无法解析：{graph['broken']}"

    def test_graph_is_not_trivially_empty(self, graph):
        """防"分析器啥也没扫到"式的空转通过。"""
        assert len(graph["modules"]) > 60, f"只扫到 {len(graph['modules'])} 个模块，疑似扫描失效"
        assert sum(len(v) for v in graph["edges"].values()) > 100


# ====================================================================== 2. 文档不漂移


class TestDocumentIsInSync:
    def test_doc_exists(self):
        assert DOC_PATH.exists(), "依赖图文档不存在，请运行 `python scripts/module_graph.py`"

    def test_doc_matches_current_source(self, graph, cycles):
        """文档必须等于"现在重算一遍"的结果。

        ❗ 这是本仓处理"派生文件"的标准做法：不靠人记得重算，靠测试。
        """
        expected = mg.render_markdown(graph, cycles)
        actual = DOC_PATH.read_text(encoding="utf-8")
        assert actual == expected, (
            "docs/MODULE_DEPENDENCY_MAP.md 与源码不一致 —— "
            "源码结构变了但文档没重算。运行 `python scripts/module_graph.py` 重新生成。"
        )

    def test_doc_declares_it_is_generated(self):
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "自动生成" in text and "请勿手工编辑" in text


# ====================================================================== 3. 分析器有牙齿


class TestAnalyzerHasTeeth:
    """❗ 本组最重要：负向对照。

    一个"永远说没问题"的分析器会让前面所有断言变成恒真 ——
    本仓已多次因"守卫恒真"白跑验证，所以分析器必须被反证一次。
    """

    def _write_pkg(self, tmp_path: Path, files: dict[str, str]) -> Path:
        for rel, body in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        return tmp_path

    def test_detects_a_synthetic_hard_cycle(self, tmp_path, monkeypatch):
        """人造一个"两条边都是模块级"的环 ⇒ 必须被判为 hard。"""
        self._write_pkg(
            tmp_path,
            {
                "app/__init__.py": "",
                "app/a.py": "from . import b\n",
                "app/b.py": "from . import a\n",
            },
        )
        monkeypatch.setattr(mg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mg, "APP_DIR", tmp_path / "app")
        graph = mg.build_graph()
        cycles = mg.find_cycles(graph["edges"])
        assert cycles, "分析器没检出人造的环 —— 它可能在空转"
        assert mg.classify_cycle(cycles[0], graph["edges"]) == "hard"

    def test_latent_when_one_edge_is_deferred(self, tmp_path, monkeypatch):
        """同样的环，但只要一条边在函数体内 ⇒ 必须判为 latent。"""
        self._write_pkg(
            tmp_path,
            {
                "app/__init__.py": "",
                "app/a.py": "from . import b\n",
                "app/b.py": "def f():\n    from . import a\n    return a\n",
            },
        )
        monkeypatch.setattr(mg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mg, "APP_DIR", tmp_path / "app")
        graph = mg.build_graph()
        cycles = mg.find_cycles(graph["edges"])
        assert cycles, "延迟导入的环也应被检出（它是真实存在的依赖）"
        assert mg.classify_cycle(cycles[0], graph["edges"]) == "latent"

    def test_type_checking_imports_are_not_dependencies(self, tmp_path, monkeypatch):
        """❗ `if TYPE_CHECKING:` 里的 import 运行时不存在 ⇒ 不得算作依赖。

        实测误报过 `writing_skills_panel <-> novel_app`，就是栽在这里。
        """
        self._write_pkg(
            tmp_path,
            {
                "app/__init__.py": "",
                "app/a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from . import b\n",
                "app/b.py": "from . import a\n",
            },
        )
        monkeypatch.setattr(mg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mg, "APP_DIR", tmp_path / "app")
        graph = mg.build_graph()
        assert mg.find_cycles(graph["edges"]) == [], "TYPE_CHECKING 被误当成了运行时依赖"

    def test_deferred_imports_are_still_recorded(self, tmp_path, monkeypatch):
        """延迟导入虽然不致命，但**是**真实依赖，必须出现在图里。"""
        self._write_pkg(
            tmp_path,
            {
                "app/__init__.py": "",
                "app/a.py": "def f():\n    from . import b\n",
                "app/b.py": "",
            },
        )
        monkeypatch.setattr(mg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mg, "APP_DIR", tmp_path / "app")
        graph = mg.build_graph()
        assert graph["edges"].get("app.a", {}).get("app.b") == "deferred"

    def test_module_level_beats_deferred_for_same_target(self, tmp_path, monkeypatch):
        """同一目标既有模块级又有延迟引用时，应记"模块级"（更强的约束）。"""
        self._write_pkg(
            tmp_path,
            {
                "app/__init__.py": "",
                "app/a.py": "from . import b\n\n\ndef f():\n    from . import b\n    return b\n",
                "app/b.py": "",
            },
        )
        monkeypatch.setattr(mg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mg, "APP_DIR", tmp_path / "app")
        graph = mg.build_graph()
        assert graph["edges"]["app.a"]["app.b"] == "module"
