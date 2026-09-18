"""控件挂载守卫（v3.2.1）—— 防"控件被创建却永不显示"。

## 这次修的到底是什么

本地实测发现 **MCP / 插件 / 插图三个面板的按钮全部不可见**
（「添加服务器」「安装插件」「生成插图」都点了不到）。根因不是逻辑写错，
而是 `ui_kit` 的助手**契约不一致**：

| 自挂载（7 个） | 需调用方挂载（4 个） |
|---|---|
| `card` · `toolbar` · `search_entry` · `empty_state` · `kpi_row` · `scrollable` · `pretty_tree` | `button` · `badge` · `section_title` · `hint` |

后四个**只创建控件并返回**，调用方必须自己 `.pack()`。
而这三个面板全都写成裸调用 ⇒ 控件被创建、进了 widget 树，但**没有任何几何管理器管它**，
于是**永不显示、且不报任何错**。

> 为什么这么难发现：`winfo_children()` 里**有**它们，单元测试若只断言"对象存在"照样通过。
> 所以本守卫的判据不是"控件存在"，而是 **"控件被几何管理器接管"**。

## 本文件守两层

1. **静态层**：扫描全仓，凡 `ui_kit.<需挂载助手>(...)` 的结果既未链式 `.pack()`、
   也未赋给变量后再挂载 ⇒ 变红。**这是能在写代码时就拦住的一层。**
2. **运行层**：真的建出三个面板，断言每个预期按钮/标题都存在**且被接管**
   （`winfo_manager()` 非空）。**这是能证明"用户真的看得见"的一层。**

两层都配了反例（人造未挂载控件），因为本仓的硬纪律是：
**守卫必须证明自己有感知力，否则"全绿"可能只是恒真。**
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

#: 需要调用方自行挂载的 ui_kit 助手。
#: ❗ `polish_legacy` **不在其中**：它返回"触及控件数"（int），不是控件。
NEEDS_MOUNT = {"button", "badge", "section_title", "hint"}

_MOUNT_ATTRS = {"pack", "grid", "place"}


def _text_of(node: ast.AST) -> str | None:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return None


def find_unmounted_calls(path: Path) -> list[tuple[int, str, str]]:
    """返回 `[(行号, 助手名, 原因)]`，即"建了控件但没挂载"的调用点。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[tuple[int, str, str]] = []

    for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        # 本函数内所有被挂载的"目标表达式文本"
        mounted: set[str] = set()
        for call in ast.walk(func):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in _MOUNT_ATTRS:
                text = _text_of(call.func.value)
                if text:
                    mounted.add(text)

        for call in ast.walk(func):
            if not isinstance(call, ast.Call):
                continue
            f = call.func
            if not (isinstance(f, ast.Attribute) and f.attr in NEEDS_MOUNT):
                continue

            # 形式 A：ui_kit.button(...).pack(...)  —— 链式挂载
            chained = any(
                isinstance(s, ast.Call)
                and isinstance(s.func, ast.Attribute)
                and s.func.attr in _MOUNT_ATTRS
                and s.func.value is call
                for s in ast.walk(tree)
            )
            if chained:
                continue

            # 形式 B：x = ui_kit.button(...) → 稍后 x.pack(...)
            assigned: str | None = None
            for s in ast.walk(func):
                if isinstance(s, ast.Assign) and s.value is call and s.targets:
                    assigned = _text_of(s.targets[0])
            if assigned and assigned in mounted:
                continue

            if assigned:
                problems.append((call.lineno, f.attr, f"赋给 `{assigned}` 后从未挂载"))
            else:
                problems.append((call.lineno, f.attr, "裸调用，返回值被丢弃 ⇒ 控件永不显示"))
    return problems


def _scan_repo() -> list[str]:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")) + [REPO_ROOT / "novel_app.py"]:
        if not path.exists():
            continue
        try:
            problems = find_unmounted_calls(path)
        except SyntaxError:  # pragma: no cover
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        offenders += [f"{rel}:{ln} ui_kit.{helper} — {why}" for ln, helper, why in problems]
    return offenders


class TestStaticMountGuard:
    def test_every_created_control_is_mounted(self):
        offenders = _scan_repo()
        assert not offenders, (
            "这些位置的控件被创建但**从未挂载**（不会显示，也不报错）：\n  "
            + "\n  ".join(offenders)
            + "\n\n修法：`ui_kit.button(...).pack(side=tk.LEFT)` "
            "或 `btn = ui_kit.button(...)` 后 `btn.pack(...)`"
        )

    def test_scanner_has_teeth(self, tmp_path, monkeypatch):
        """❗ 反例：人造一处"裸调用"必须被检出 —— 否则本守卫可能恒真。"""
        fake = tmp_path / "app"
        fake.mkdir()
        (fake / "x.py").write_text(
            "import tkinter as tk\n"
            "from app.panels import ui_kit\n\n"
            "def build(root):\n"
            "    ui_kit.button(root, '不该消失的按钮')\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
        offenders = _scan_repo()
        assert len(offenders) == 1, f"扫描器没检出人造的未挂载控件：{offenders}"
        assert "button" in offenders[0]

    def test_scanner_accepts_chained_and_assigned_forms(self, tmp_path, monkeypatch):
        """反例的反面：两种**正确**写法都不能被误报（否则判据过宽）。"""
        fake = tmp_path / "app"
        fake.mkdir()
        (fake / "x.py").write_text(
            "import tkinter as tk\n"
            "from app.panels import ui_kit\n\n"
            "def build(root):\n"
            "    ui_kit.button(root, 'A').pack(side=tk.LEFT)\n"
            "    b = ui_kit.button(root, 'B')\n"
            "    b.pack(side=tk.LEFT)\n"
            "    self_btn = ui_kit.button(root, 'C')\n"
            "    self_btn.pack(side=tk.LEFT)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
        assert _scan_repo() == []

    def test_scanner_ignores_non_widget_helpers(self, tmp_path, monkeypatch):
        """`polish_legacy` 返回 int（触及控件数），裸调用是**正确**用法，不得误报。"""
        fake = tmp_path / "app"
        fake.mkdir()
        (fake / "x.py").write_text(
            "from app.panels import ui_kit\n\ndef build(root):\n    ui_kit.polish_legacy(root)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
        assert _scan_repo() == []


# ====================================================================== 运行层


def _tk_ok() -> bool:
    try:
        import tkinter

        r = tkinter.Tk()
        r.withdraw()
        r.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


def _collect(root) -> dict[str, str]:
    """收集 `{可见文字: 几何管理器}`；管理器为空串表示**没有被挂载**。"""
    out: dict[str, str] = {}
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
        except Exception:  # noqa: BLE001
            continue
        try:
            text = str(w.cget("text"))
        except Exception:  # noqa: BLE001
            continue
        if text.strip():
            try:
                out[text.strip()] = w.winfo_manager()
            except Exception:  # noqa: BLE001
                out[text.strip()] = "?"
    return out


EXPECTED = {
    "mcp": {
        "buttons": ["添加服务器", "测试连接", "刷新工具", "打开配置文件", "启用", "停用", "删除"],
        "titles": ["MCP 服务器", "服务器详情", "可用 MCP 工具（来自已启用的服务器）"],
    },
    "plugins": {
        "buttons": ["安装插件", "重新扫描", "打开插件目录", "启用", "停用", "卸载"],
        "titles": ["已安装插件", "插件详情"],
    },
    "illustration": {
        "buttons": ["检测后端", "刷新提示词", "打开图片目录", "生成插图"],
        "titles": ["名场面提示词", "提示词内容"],
    },
}


@pytest.mark.skipif(not _tk_ok(), reason="无显示环境")
class TestPanelsActuallyRenderControls:
    """❗ 判据是 **"被几何管理器接管"**，不是"对象存在"。

    这正是本次 bug 的教训：控件确实存在于 `winfo_children()` 里，
    只断言"存在"的测试照样绿，而用户在界面上看不到任何按钮。
    """

    def _build(self, key: str, tmp_path, monkeypatch):
        import tkinter as tk

        from app.panels.illustration_panel import IllustrationPanel
        from app.panels.mcp_panel import MCPPanel
        from app.panels.plugin_panel import PluginPanel

        if key == "mcp":
            from app import mcp_system as mcp

            monkeypatch.setattr(mcp, "_manager", None)
            monkeypatch.setattr(mcp, "default_servers_file", lambda: tmp_path / "mcp.json")
            panel = MCPPanel()
        elif key == "plugins":
            from app import plugin_system as ps

            monkeypatch.setattr(ps, "_manager", None)
            monkeypatch.setattr(
                ps,
                "_manager",
                ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "state.json"),
            )
            panel = PluginPanel()
        else:
            panel = IllustrationPanel()

        root = tk.Tk()
        root.withdraw()
        panel.build(root)
        return root, panel

    @pytest.mark.parametrize("key", sorted(EXPECTED), ids=sorted(EXPECTED))
    def test_expected_buttons_are_visible(self, key, tmp_path, monkeypatch):
        root, _panel = self._build(key, tmp_path, monkeypatch)
        try:
            found = _collect(root)
            missing = [t for t in EXPECTED[key]["buttons"] if t not in found]
            unmounted = [t for t in EXPECTED[key]["buttons"] if found.get(t) == ""]
            assert not missing, f"{key} 面板缺按钮：{missing}"
            assert not unmounted, f"{key} 面板这些按钮**未被挂载**（用户看不到）：{unmounted}"
        finally:
            root.destroy()

    @pytest.mark.parametrize("key", sorted(EXPECTED), ids=sorted(EXPECTED))
    def test_expected_section_titles_are_visible(self, key, tmp_path, monkeypatch):
        root, _panel = self._build(key, tmp_path, monkeypatch)
        try:
            found = _collect(root)
            bad = [t for t in EXPECTED[key]["titles"] if found.get(t, "") == ""]
            assert not bad, f"{key} 面板这些小标题未被挂载：{bad}"
        finally:
            root.destroy()

    def test_unmounted_widget_is_detected(self, tmp_path):
        """❗ 反例：人造一个未挂载按钮，必须被判为"未挂载"。

        没有这条，上面两个用例可能因为 `_collect` 恒返回非空而假绿。
        """
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            tk.Button(root, text="幽灵按钮")  # 故意不 pack
            tk.Button(root, text="正常按钮").pack()
            found = _collect(root)
            assert found.get("幽灵按钮") == "", "未挂载按钮应报告空管理器"
            assert found.get("正常按钮") == "pack", "已挂载按钮应报告 pack"
        finally:
            root.destroy()
