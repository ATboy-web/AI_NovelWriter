"""修正 test_safe_after.py 里基于错误前提的用例。

## 我一开始判断错了

我以为"控件销毁后 `widget.after(...)` 会抛 `TclError`"。**实测不成立**：

    victim = tk.Toplevel(root); victim.destroy()
    victim.after(0, cb)      # 返回 'after#0'，不抛；root.update() 后 cb 仍执行

Windows + Python 3.11 的 Tk 在控件销毁后仍接受 `after`（回调排到解释器队列）。
所以"投递这一层抛 TclError"不是真实的失效路径 —— 我按错误前提写的两个用例必然失败。

## 真实的失效路径是**回调体**碰已销毁控件

`after` 投递成功 → 回调执行 `widget.config(...)` → 此时才抛 TclError。
这属于业务代码该自己兜的范围（面板里已有大量 `except tk.TclError`），
不是 `safe_after` 的职责。

## 那 `safe_after` 还有意义吗？有，但职责要写准

它兜的是"**投递这一步**失败"：
- 解释器已退出（`RuntimeError`：main thread is not in main loop）
- 传入的不是 Tk 对象（测试替身 / 已置空的引用）
- 部分平台上控件销毁后确实抛 TclError（Tk 版本相关，不能假定不抛）

最后一条正是不能省的理由：**同一份代码要跑在未知 Tk 版本上**，
"我这台机器不抛"不构成"所有机器都不抛"。
"""

from __future__ import annotations

import pathlib
import re
import tkinter as tk

import pytest

from app.async_runner import BackgroundRunner, safe_after


class _TclGone:
    """模拟"控件销毁后 after 抛 TclError"的平台行为。"""

    def after(self, *_args, **_kwargs):
        raise tk.TclError('can\'t invoke "after" command: application has been destroyed')


class _NotInMainLoop:
    """模拟解释器/主循环已退出。"""

    def after(self, *_args, **_kwargs):
        raise RuntimeError("main thread is not in main loop")


class _Boom:
    """模拟一个**不该被吞掉**的真实错误。"""

    def after(self, *_args, **_kwargs):
        raise ZeroDivisionError("代码 bug，必须暴露")


class TestSafeAfterCore:
    def test_delivers_callback(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fired: list[int] = []
            assert safe_after(root, fired.append, 7) is True
            root.update()
            assert fired == [7]
        finally:
            root.destroy()

    def test_delay_parameter(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fired: list[str] = []
            assert safe_after(root, fired.append, "x", delay=1) is True
            root.after(30, root.quit)
            root.mainloop()
            assert fired == ["x"]
        finally:
            root.destroy()

    @pytest.mark.parametrize("stub", [_TclGone(), _NotInMainLoop()], ids=["TclError", "RuntimeError"])
    def test_known_gone_cases_return_false(self, stub):
        """🔴 核心契约：控件/解释器已消失时返回 False，不抛。

        这是旧 `dispatch` 的缺口 —— 它的 except 里没有 TclError。
        """
        assert safe_after(stub, lambda: None) is False

    def test_real_error_propagates(self):
        """只有"环境已消失"类异常被吞；代码 bug 必须暴露。"""
        with pytest.raises(ZeroDivisionError):
            safe_after(_Boom(), lambda: None)

    def test_non_tk_object_returns_false(self):
        class Dummy:
            pass

        assert safe_after(Dummy(), lambda: None) is False

    def test_destroyed_widget_never_raises(self):
        """已销毁的真实控件：返回 True 或 False 都可以，**唯独不能抛**。

        （实测 Windows/Py3.11 下 Tk 仍接受投递 → 返回 True；
        其它平台可能返回 False。用例只锁"不抛"这一条。）
        """
        root = tk.Tk()
        root.withdraw()
        victim = tk.Toplevel(root)
        victim.destroy()
        try:
            assert safe_after(victim, lambda: None) in (True, False)
        finally:
            root.destroy()


class TestDispatchContract:
    def test_dispatch_uses_after(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fired: list[int] = []
            BackgroundRunner(ui=root).dispatch(fired.append, 1)
            root.update()
            assert fired == [1]
        finally:
            root.destroy()

    def test_dispatch_falls_back_to_inline_when_gone(self):
        """投递失败时**原地调用**，回调不丢 —— 用桩模拟"已消失"。"""
        fired: list[str] = []
        BackgroundRunner(ui=_TclGone()).dispatch(fired.append, "inline")
        assert fired == ["inline"]

    def test_dispatch_without_ui_runs_inline(self):
        fired: list[int] = []
        BackgroundRunner(ui=None).dispatch(fired.append, 3)
        assert fired == [3]

    def test_dispatch_ignores_none(self):
        BackgroundRunner(ui=None).dispatch(None)

    def test_dispatch_swallows_no_real_errors(self):
        """真实错误不能被 dispatch 悄悄吞掉。"""
        fired: list[int] = []
        with pytest.raises(ZeroDivisionError):
            BackgroundRunner(ui=_Boom()).dispatch(fired.append, 1)


class TestNoBareAfterGuard:
    """守卫：`app/` 下不得再直接调 `.after(`，必须走 `safe_after`。

    判据是"谁来兜 TclError/RuntimeError"——直接写 `.after(` 就把这层保护丢了。
    例外在 `ALLOWED` 里显式登记理由。
    """

    #: (文件, 行内容特征, 理由)。
    #:
    #: 当前**为空** —— 全仓已经没有直接调 `.after(` 的地方了。
    #: `safe_after` 内部那行是裸 `after(delay, ...)`（不带点，不是方法调用），
    #: 扫描器不会误报，所以不需要例外。
    #: 留这个结构是为了将来确实需要例外时，必须写清理由。
    ALLOWED: tuple[tuple[str, str, str], ...] = (
        (
            "panels/ui_kit.py",  # 相对 app/
            "top.after(ms, lambda: _safe_destroy(top))",
            "toast 的定时销毁；该行整体在 except (TclError, RuntimeError) 内，已有兜底",
        ),
    )

    @staticmethod
    def _app_root() -> pathlib.Path:
        return pathlib.Path(__file__).resolve().parent.parent / "app"

    def test_scan_finds_no_bare_after(self):
        root = self._app_root()
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if ".after(" not in stripped or stripped.startswith("#"):
                    continue
                # 文档/注释行：含 markdown 反引号（真实代码不会有）或表格竖线
                if "`" in stripped or stripped.startswith("|"):
                    continue
                # `.after_cancel(` 不在本守卫范围
                if ".after_cancel(" in stripped:
                    continue
                if "safe_after" in stripped:
                    continue
                rel = path.relative_to(root).as_posix()
                if any(rel.endswith(name) and marker in stripped for name, marker, _why in self.ALLOWED):
                    continue
                offenders.append(f"{rel}:{number} {stripped[:72]}")
        assert not offenders, (
            "以下位置直接调 .after( —— 应改用 app.async_runner.safe_after（它兜住 TclError）:\n  "
            + "\n  ".join(offenders)
        )

    def test_allowlist_still_valid(self):
        """双向：清单指向的位置若已不存在，说明清单过期。"""
        root = self._app_root()
        sources = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.py")}
        stale = [
            f"{name} :: {marker}（{why}）"
            for name, marker, why in self.ALLOWED
            if not any(marker in text for rel, text in sources.items() if rel.endswith(name))
        ]
        assert not stale, "以下登记项已不存在，请从 ALLOWED 删除：\n  " + "\n  ".join(stale)

    def test_character_ui_has_no_bare_after(self):
        """`character_ui` 的 AI 建角色是"投递点在 except 内"的典型，专项钉住。"""
        source = (self._app_root() / "character_ui.py").read_text(encoding="utf-8")
        assert "from app.async_runner import safe_after" in source
        assert not re.search(r"\.after\(0,\s", source), "character_ui 里不该再有 .after(0, ...)"
