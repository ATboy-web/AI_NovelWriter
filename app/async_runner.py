"""统一后台执行器（v3 §1.1 A6 + §3.5(1)）。

## 它同时解决两件事

1. **去重**：v2 有 **40 处手工 `threading.Thread(...)`**，散在 17 个文件里，
   四类回调风格各异（弹窗 / 仅日志 / 静默 / 进度回调），没有统一的异常兜底 ——
   子线程里抛出的异常默认只是打到 stderr，用户看不到，表现为"点了没反应"。

2. **让 token 归因真正生效**：用量归因靠 `contextvars`（见 `usage_tracker`），
   而 **`contextvars` 在 `threading.Thread` 里不会继承父上下文**（这点与 asyncio
   不同）。若不做处理，每个 `Thread` 里读到的都是 `default=None`，
   `novel_agent` 设置的 `chapter=N` 会全部丢失。
   `Thread(target=ctx.run, args=(fn,))` 是官方给出的正确做法 ——
   在这里做一次，**40 处调用点自动全部获得正确的归因上下文**。

## 用法

    runner = BackgroundRunner(ui=self.root, log=self._log)
    runner.submit(self._do_heavy_work, on_success=lambda r: self._log(f"完成 {r}"),
                  on_error=runner.messagebox_on_error("生成失败"), log_errors=True)

`ui` 只要求「有 `after(0, fn)` 方法」。传 `None` 时回调**原地同步执行** ——
这正是单测里需要的行为（无需真实 Tk 事件循环）。
"""

from __future__ import annotations

import contextvars
import threading
import traceback

__all__ = [
    "BackgroundRunner",
    "copy_context_snapshot",
    "context_runner",
    "join_all",
    "DEFAULT_THREAD_NAME",
]

DEFAULT_THREAD_NAME = "anw-worker"

#: 进程内已派发的线程（仅用于测试收尾与调试观测，不参与业务逻辑）
_ISSUED_LOCK = threading.Lock()
_ISSUED: list = []


def copy_context_snapshot() -> contextvars.Context:
    """拷贝**当前线程**的上下文，返回一份可在别的线程里 `run` 的快照。

    ⚠️ **必须在父线程调用。** 这是本模块最容易踩的坑：

        # ❌ 错：在子线程里 copy_context() → 拷到的是子线程自己那份空上下文
        Thread(target=lambda: copy_context().run(fn))

        # ✅ 对：父线程先拷贝，再把 Context 交给子线程执行
        ctx = copy_context()
        Thread(target=ctx.run, args=(fn,))
    """
    return contextvars.copy_context()


def context_runner(fn):
    """把 `fn` 包装成「在**当前**上下文的快照里执行」的可调用对象。

    ⚠️ 必须在父线程构造本对象（原因见 `copy_context_snapshot`）。

    这是 `threading.Thread` 不继承 `contextvars` 的官方解法，也是本模块
    存在的核心理由：没有它，`novel_agent` 设的 `chapter=N` 在子线程里全丢，
    用量归因就永远是空的。
    """
    ctx = copy_context_snapshot()
    return lambda: ctx.run(fn)


def join_all(timeout: float = 5.0) -> int:
    """等待所有经本模块派发的线程结束（单测/退出前收尾用）。返回仍未结束的个数。"""
    with _ISSUED_LOCK:
        pending = [t for t in _ISSUED if t.is_alive()]
    for thread in pending:
        thread.join(timeout)
    with _ISSUED_LOCK:
        return len([t for t in _ISSUED if t.is_alive()])


class BackgroundRunner:
    """把「工作函数 + 回调」派发到后台线程，并保证回调在主线程执行。

    Parameters
    ----------
    ui : 具备 `after(0, fn)` 的对象（通常是 `root` 或 `self`）。
         为 `None` 时回调同步执行，便于无 GUI 环境测试。
    log : `Callable[[str], None]`，用于 `log_errors=True` 与调试信息。
    """

    def __init__(self, ui=None, log=None):
        self.ui = ui
        self._log = log or (lambda _msg: None)
        self._threads: list = []

    # ------------------------------------------------------------ 派发

    def dispatch(self, fn, *args) -> None:
        """把回调送回主线程（`ui` 为空则原地调用）。

        Tk 非线程安全，因此**所有**触碰控件的回调都必须走这里。
        `after` 在窗口已销毁时会抛 `RuntimeError`/`TclError`，这时安静放弃 ——
        后台线程继续跑完也不会崩。
        """
        if fn is None:
            return
        ui = self.ui
        if ui is not None and hasattr(ui, "after"):
            try:
                ui.after(0, lambda: fn(*args))
                return
            except (RuntimeError, AttributeError):
                pass
        fn(*args)

    def submit(
        self,
        work,
        *args,
        on_success=None,
        on_error=None,
        on_finally=None,
        name: str = DEFAULT_THREAD_NAME,
        log_errors: bool = False,
        daemon: bool = True,
        **kwargs,
    ) -> threading.Thread:
        """在后台线程执行 `work(*args, **kwargs)`。

        - `on_success(result)` / `on_error(exc)` / `on_finally()` 一律在主线程执行
        - `on_error` 为 `None` 且 `log_errors` 为真时，异常交给 `log`
        - 异常**不会**被吞掉：`on_error` 与 `log_errors` 都没有时，
          仍会把 traceback 写入 `log`，避免"点了没反应"
        - 返回 `Thread`，调用方可 `join()`（本模块也登记在 `join_all` 中）
        """
        runner = self

        def _target():
            try:
                result = work(*args, **kwargs)
            except BaseException as exc:                  # noqa: BLE001 - 兜底是职责
                runner._handle_error(exc, log_errors, on_error, name)
            else:
                runner.dispatch(on_success, result)
            finally:
                runner.dispatch(on_finally)

        # 关键：**在父线程**把上下文快照交给子线程执行。
        # （`threading.Thread` 不继承 contextvars；若在子线程里 copy_context()
        #  就会拷到子线程自己那份空上下文，等于没做。见 `context_runner`。）
        thread = threading.Thread(
            target=context_runner(_target), name=name, daemon=daemon
        )
        self._threads.append(thread)
        with _ISSUED_LOCK:
            # 顺手清掉已结束的登记，5000 章长跑下这个列表才不会无限增长
            _ISSUED[:] = [t for t in _ISSUED if t.is_alive()]
            _ISSUED.append(thread)
        thread.start()
        return thread

    def _handle_error(self, exc, log_errors: bool, on_error, name: str) -> None:
        if on_error is not None:
            self.dispatch(on_error, exc)
            return
        if log_errors:
            self.dispatch(self._log, f"[{name}] 后台任务失败: {type(exc).__name__}: {exc}")
            return
        # 两个出口都没有 → 至少留下 traceback，绝不静默
        self.dispatch(
            self._log,
            f"[{name}] 后台任务未处理异常:\n{traceback.format_exc()}",
        )

    # ------------------------------------------------------------ 回调工厂

    @staticmethod
    def messagebox_on_error(title: str = "操作失败", parent=None):
        """返回一个「弹窗报错」的 `on_error` 回调。

        延迟 import：本模块要能在无 Tk 的服务器/单测环境被导入。
        """
        def _show(exc):
            from tkinter import messagebox

            messagebox.showerror(title, f"{type(exc).__name__}: {exc}", parent=parent)
        return _show

    # ------------------------------------------------------------ 生命周期

    def join(self, timeout: float = 5.0) -> None:
        """等待本实例派发的全部线程结束（测试用）。"""
        for thread in list(self._threads):
            thread.join(timeout)

    @property
    def alive(self) -> list:
        return [t for t in self._threads if t.is_alive()]
