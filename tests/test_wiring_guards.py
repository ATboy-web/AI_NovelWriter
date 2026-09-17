""" "注册即遗忘"守门测试（D3 / D4 / D5）。

项目的失败模式不是"功能有 bug"，而是**功能建好却没人调用** ——
`docs/` 里称之为"注册即遗忘"。检测法是：
**对每个注册/定义项统计「生产代码」调用点，必须排除 `tests/`**
（`tests/` 的高覆盖率不等于功能被用上：`KnowledgeGraph.add_relation`
曾有多处测试调用、却零生产调用，于是 `get_character_relations()` 恒空）。

本文件把 2026-09-17 这一轮修好的三处钉住，防止回退：

| ID | 现象 | 修法 |
|---|---|---|
| D3 | `FullscreenWriter._toggle_ai` 有定义、有消费方，但**无入口控件** | 工具栏补 `AI辅助` 复选框 |
| D4 | `UIStyle.create_styled_*` 四个工厂全仓零引用 | 删除（并移除随之无用的 `import tkinter`） |
| D5 | `PerformanceMonitor.save_report` 全仓零调用 ⇒ 指标采集了但从不落盘 | 退出时写 `diagnostic_logs/performance-*.json` |
"""

import ast
import inspect
from pathlib import Path

from app import fullscreen_writer as fsw_module
from app import shell_ui as shell_ui_module
from app import ui_style as ui_style_module

REPO_ROOT = Path(__file__).resolve().parents[1]


def _code_only(source: str) -> str:
    """剔除注释与文档字符串（修复说明会提到旧名字）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    for idx in range(first.lineno - 1, min(first.end_lineno, len(lines))):
                        lines[idx] = ""
    return "\n".join(line.split("#", 1)[0] for line in lines)


class TestD3AiToggleIsWired:
    """`_toggle_ai` 必须有一个真实的 UI 入口。"""

    def test_toggle_ai_has_a_control(self):
        """工具栏必须构造一个绑定到 `_toggle_ai` 的控件。"""
        module_src = _code_only(inspect.getsource(fsw_module))
        assert "command=self._toggle_ai" in module_src, "_toggle_ai 又没有入口了（D3 回退）"

    def test_ai_var_exists(self):
        module_src = inspect.getsource(fsw_module)
        assert "self.ai_var" in module_src, "缺少与 AI 辅助开关绑定的 BooleanVar"

    def test_toggle_ai_syncs_checkbox(self):
        src = _code_only(inspect.getsource(fsw_module.FullscreenWriter._toggle_ai))
        assert "ai_var" in src, "_toggle_ai 未同步复选框状态"

    def test_settings_load_syncs_checkboxes(self):
        """读回配置后必须把值同步到复选框，否则界面显示与实际生效值不符。"""
        src = _code_only(inspect.getsource(fsw_module.FullscreenWriter._load_writer_settings))
        assert "ai_var" in src and "tw_var" in src


class TestD4StyledFactoriesAreGone:
    """四个零引用的 `create_styled_*` 不得回来。"""

    NAMES = (
        "create_styled_button",
        "create_styled_entry",
        "create_styled_text",
        "create_styled_listbox",
    )

    def test_factories_are_removed(self):
        for name in self.NAMES:
            assert not hasattr(ui_style_module.UIStyle, name), f"UIStyle.{name} 又回来了（D4 回退）"

    def test_nothing_anywhere_references_them(self):
        """全仓（含动态调用面）不得再出现这些名字 —— **只看代码，不看注释**。

        ⚠️ 必须剔除注释和文档字符串：`ui_style.py` 里留着"删掉了这四个方法"
        的说明注释，本测试文件也写着这些名字，直接扫原文必然自报假阳性
        （这是"验证判据本身要先自检"的典型踩坑）。
        """
        offenders = []
        self_path = Path(__file__).resolve()
        for py in REPO_ROOT.rglob("*.py"):
            if any(part in {".git", "node_modules", ".venv", "_venv_probe"} for part in py.parts):
                continue
            if py.resolve() == self_path:
                continue  # 本文件自身就是列举这些名字的地方
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            code = _code_only(text)
            for name in self.NAMES:
                if name in code:
                    offenders.append(f"{py.relative_to(REPO_ROOT)}: {name}")
        assert not offenders, f"仍有引用：{offenders}"

    def test_tkinter_import_not_kept_unused(self):
        """四个工厂删掉后 `tk` 应已无用；不得为了"以后可能用"留下未使用导入。"""
        code = _code_only(inspect.getsource(ui_style_module))
        assert "import tkinter as tk" not in code

    def test_ttk_still_present(self):
        """本模块仍需要 ttk 配置全局主题 —— 别删过头。"""
        source = inspect.getsource(ui_style_module)
        assert "from tkinter import ttk" in source
        assert "ttk.Style()" in source


class TestD5PerformanceReportIsFlushed:
    """指标采集了就必须落盘。"""

    def test_close_flushes_report(self):
        src = inspect.getsource(shell_ui_module)
        assert "_flush_performance_report" in src, "退出时不再落盘性能报告（D5 回退）"
        assert "save_report" in src, "没有调用 save_report"

    def test_flush_writes_under_diagnostic_logs(self):
        """与面板诊断日志同目录，便于一起排查。"""
        src = inspect.getsource(shell_ui_module)
        assert "diagnostic_logs" in src
        assert "performance-" in src, "文件名前缀缺失"

    def test_flush_is_fault_tolerant(self):
        """保存失败绝不能阻止退出。"""
        src = inspect.getsource(shell_ui_module.ShellMixin._flush_performance_report)
        assert "except Exception" in src, "缺少兜底异常处理"

    def test_no_empty_report_written(self):
        """零请求时不写空报告，避免刷出一堆无意义文件。"""
        src = inspect.getsource(shell_ui_module)
        assert "total_requests" in src, "缺少'无请求不落盘'的判断"
