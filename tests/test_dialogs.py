"""`app/dialogs.py` 的行为与"调用点收口"门禁。

## 这个文件存在的理由

2026-09-17 之前，全仓 **215 处** `messagebox.*` 调用散落在 25 个文件里，每个文件
各自 `from tkinter import messagebox`。后果不是"代码不好看"，而是：

1. **改不动**：想把原生弹窗换成主题化对话框（深色主题下原生弹窗是浅色的），
   要翻 25 个文件；
2. **自动化被卡死**：模态弹窗会阻塞脚本，截图脚本只能去 monkeypatch
   `tkinter.messagebox` 的内部属性 —— 实测漏了一个 `askinteger` 就被卡 14 分钟；
3. **没有使用政策**：到底该弹窗还是用 `ui_kit.toast`，没有地方写、也没人拦。

现在调用点全部走 `app.dialogs`，本文件就是它的**回归测试 + 门禁**。
"""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import _source_scan  # noqa: E402  （同目录测试工具）

from app import dialogs  # noqa: E402

#: 允许直接调用 `messagebox.*` 的唯一文件（它就是这个能力的实现处）
IMPLEMENTATION_FILE = REPO_ROOT / "app" / "dialogs.py"

#: 与 `messagebox` 同签名的那一层
PASSTHROUGH = ("showinfo", "showwarning", "showerror", "askyesno")

#: 统计"有人真的在用"时计入的所有消息接口名
USAGE_NAMES = (*PASSTHROUGH, "info", "warn", "error", "confirm")


# ====================================================================== 调用点收口


def _code_messagebox_calls(path: Path) -> list[int]:
    """代码里（不含注释/docstring）直接调用 `messagebox.*` 的行号。

    用 tokenize 而不是正则：`ui_kit` / `base` 的 **docstring 里**写了
    ``messagebox.askyesno`` 之类作为政策说明，正则会把文档误判成调用点。
    """
    source = path.read_text(encoding="utf-8")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):  # pragma: no cover - 坏文件由别的测试管
        return []
    rows: list[int] = []
    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME or token.string != "messagebox":
            continue
        nxt = tokens[index + 1] if index + 1 < len(tokens) else None
        if nxt and nxt.type == tokenize.OP and nxt.string == ".":
            rows.append(token.start[0])
    return rows


def test_no_direct_messagebox_calls_in_app():
    """**门禁**：业务代码不得直接调 `messagebox` —— 一律走 `app.dialogs`。

    这条守卫的价值不在今天，而在下一次：新增代码时"随手 `messagebox.showinfo`"
    是最自然的写法，而它会让收口慢慢失效（本仓 215 处就是这么攒出来的）。
    """
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        if path == IMPLEMENTATION_FILE:
            continue
        for row in _code_messagebox_calls(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{row}")
    assert offenders == [], "以下位置直接调用了 messagebox，请改用 app.dialogs（同签名，只换前缀）：\n  " + "\n  ".join(
        offenders
    )


def _uses_dialogs_names(path: Path) -> bool:
    """代码里（不含注释/docstring）是否调用了 `dialogs.<消息函数>(`。"""
    relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    code = _source_scan.code_only(relative)
    return any(f"dialogs.{name}(" in code for name in USAGE_NAMES)


def _imports_dialogs(path: Path) -> bool:
    """AST 判定：该模块是否把 `dialogs` 这个名字导入进来了。

    为什么不用字符串匹配 `"from app import dialogs"`：ruff 的 isort 会把同源的
    `from app import` 合并成一行（`from app import UIStyle, dialogs`），
    字符串断言会**假红**（实测踩到）。
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            if any(alias.name == "dialogs" for alias in node.names):
                return True
        if isinstance(node, ast.Import) and any(alias.name == "app.dialogs" for alias in node.names):
            return True
    return False


def test_dialogs_is_actually_used():
    """反向检查：收口之后必须**真的有人在用** `dialogs.*`。

    否则容易出现"门禁拦住了直接调用，但功能整体被绕过"的假胜利。
    统计走 `code_only`（剔除注释与 docstring），避免把政策说明里的示例算成调用。
    """
    total = 0
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        if path == IMPLEMENTATION_FILE:
            continue
        relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        code = _source_scan.code_only(relative)
        total += sum(code.count(f"dialogs.{name}(") for name in USAGE_NAMES)
    assert total >= 200, f"仅找到 {total} 处 dialogs.* 调用，收口可能已被绕过"


def test_every_module_that_reports_uses_dialogs():
    """用了 `dialogs.*` 的模块必须真的导入它（避免只改一半留下运行期 NameError）。"""
    missing: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        if path == IMPLEMENTATION_FILE:
            continue
        if _uses_dialogs_names(path) and not _imports_dialogs(path):
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert missing == [], f"以下文件用了 dialogs 但没导入它：{missing}"


# ====================================================================== 同签名层


@pytest.fixture()
def fake_messagebox(monkeypatch):
    """替掉 `tkinter.messagebox`：记录调用并返回可控值（测试里不真的弹窗）。"""
    calls: list[tuple[str, tuple, dict]] = []

    class _Fake:
        @staticmethod
        def _record(name, args, kwargs):
            calls.append((name, args, kwargs))
            return True if name.startswith("ask") else "ok"

        showinfo = staticmethod(lambda *a, **k: _Fake._record("showinfo", a, k))
        showwarning = staticmethod(lambda *a, **k: _Fake._record("showwarning", a, k))
        showerror = staticmethod(lambda *a, **k: _Fake._record("showerror", a, k))
        askyesno = staticmethod(lambda *a, **k: _Fake._record("askyesno", a, k))

    monkeypatch.setattr(dialogs, "_messagebox", lambda: _Fake)
    return calls


class TestPassthroughLayer:
    """同签名层是 215 处迁移能"等值"的前提，所以逐个钉住。"""

    @pytest.mark.parametrize("name", PASSTHROUGH)
    def test_signature_matches_messagebox(self, name):
        """参数名与顺序必须与 `tkinter.messagebox` 一致（迁移只是换前缀）。"""
        import inspect
        import tkinter.messagebox as real

        ours = inspect.signature(getattr(dialogs, name))
        theirs = inspect.signature(getattr(real, name))
        assert list(ours.parameters)[:2] == list(theirs.parameters)[:2] == ["title", "message"], (
            f"{name}: 前两个参数应为 title, message，实际 {list(ours.parameters)[:2]}"
        )
        # 我们照样收 **options 并原样透传（与 tkinter 的 **options 同义）
        assert ours.parameters["options"].kind is inspect.Parameter.VAR_KEYWORD

    def test_forwards_title_message_and_options(self, fake_messagebox):
        dialogs.showwarning("标题", "内容", parent="P")
        assert fake_messagebox == [("showwarning", ("标题", "内容"), {"parent": "P"})]

    def test_askyesno_returns_bool(self, fake_messagebox):
        assert dialogs.askyesno("确认", "确定吗？") is True

    def test_show_returns_messagebox_result(self, fake_messagebox):
        assert dialogs.showinfo("标题", "内容") == "ok"


class TestSilentMode:
    """静默模式：自动化不再需要 monkeypatch 内部属性。"""

    def test_defaults_to_not_silent(self):
        assert dialogs.is_silent() is False

    def test_show_functions_do_not_popup_when_silent(self, fake_messagebox):
        previous = dialogs.set_silent(True)
        try:
            for name in ("showinfo", "showwarning", "showerror"):
                assert getattr(dialogs, name)("标题", "内容") is None
            assert fake_messagebox == [], "静默模式下不应触达 messagebox"
        finally:
            dialogs.set_silent(previous)

    def test_ask_returns_safe_default_when_silent(self, fake_messagebox):
        previous = dialogs.set_silent(True)
        try:
            assert dialogs.askyesno("确认", "要删除吗？") is False
            assert dialogs.confirm("要删除吗？") is False
            assert dialogs.confirm("要删除吗？", default=True) is True
        finally:
            dialogs.set_silent(previous)

    def test_context_manager_restores_even_on_exception(self, fake_messagebox):
        with pytest.raises(RuntimeError):
            with dialogs.silent_modals():
                assert dialogs.is_silent() is True
                raise RuntimeError("boom")
        assert dialogs.is_silent() is False

    def test_context_manager_nests(self, fake_messagebox):
        with dialogs.silent_modals():
            with dialogs.silent_modals():
                assert dialogs.is_silent() is True
            assert dialogs.is_silent() is True, "内层退出不应解除外层的静默"
        assert dialogs.is_silent() is False

    def test_context_manager_keeps_an_outer_set_silent(self, fake_messagebox):
        """回归：`set_silent(True)` 之后的 `with silent_modals()` 退出时**不得**解除静默。

        旧实现用深度计数，`__exit__` 在深度归零时无条件 `set_silent(False)`，
        于是会把进入之前就存在的全局静默一起抹掉。对"关了全局静默去做自动化"
        的脚本，这等于在作用域结束后又开始弹模态框。
        """
        previous = dialogs.set_silent(True)
        try:
            with dialogs.silent_modals():
                assert dialogs.is_silent() is True
            assert dialogs.is_silent() is True, "外层 set_silent(True) 必须仍然生效"
        finally:
            dialogs.set_silent(previous)

    def test_context_manager_does_not_enable_silent_afterwards(self, fake_messagebox):
        """反向边界：原本非静默时，退出后必须是非静默（不能反过来粘住）。"""
        previous = dialogs.set_silent(False)
        try:
            with dialogs.silent_modals():
                assert dialogs.is_silent() is True
            assert dialogs.is_silent() is False
        finally:
            dialogs.set_silent(previous)

    def test_set_silent_returns_previous(self, fake_messagebox):
        assert dialogs.set_silent(True) is False
        assert dialogs.set_silent(True) is True
        dialogs.set_silent(False)


class TestSemanticLayer:
    def test_default_title_is_the_app_name(self, fake_messagebox):
        dialogs.info("已完成")
        name, args, kwargs = fake_messagebox[0]
        assert name == "showinfo"
        assert args[0] == dialogs.APP_TITLE
        assert args[1] == "已完成"

    def test_each_kind_maps_to_the_right_messagebox_function(self, fake_messagebox):
        dialogs.info("a")
        dialogs.warn("b")
        dialogs.error("c")
        dialogs.confirm("d")
        assert [name for name, _a, _k in fake_messagebox] == [
            "showinfo",
            "showwarning",
            "showerror",
            "askyesno",
        ]

    def test_confirm_passes_parent_through(self, fake_messagebox):
        dialogs.confirm("要覆盖吗？", parent="P", title="危险操作")
        name, args, kwargs = fake_messagebox[0]
        assert name == "askyesno"
        assert args == ("危险操作", "要覆盖吗？")
        assert kwargs == {"parent": "P"}


# ====================================================================== 无 Tk 环境


def test_module_import_does_not_touch_tk_root():
    """`import app.dialogs` 不得创建 Tk 根窗口 —— 无显示环境必须能导入。"""
    import subprocess

    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import tkinter;"
        "import app.dialogs as d;"
        "assert tkinter._default_root is None, '导入时就创建了 Tk 根窗口';"
        "assert callable(d.showinfo);"
        "print('ok')" % REPO_ROOT
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"子进程失败：{result.stderr}"
    assert "ok" in result.stdout


def test_messagebox_is_not_imported_at_module_level():
    """`tkinter.messagebox` 也必须是按需取得（`_messagebox()`），不是模块级导入。

    否则无 GUI 环境下 `import app.dialogs` 会顺带要求可用的 Tk。
    """
    source = IMPLEMENTATION_FILE.read_text(encoding="utf-8")
    header = source.split("def _center_on_parent")[0]
    assert "from tkinter import messagebox" not in header, "messagebox 不应出现在模块级导入区"
