"""统一后台执行器（v3 §1.1 A6 + §3.5(1)）。

## 它同时解决三件事

1. **去重**：v2 有 **40 处手工 `threading.Thread(...)`**，散在 17 个文件里，
   四类回调风格各异（弹窗 / 仅日志 / 静默 / 进度回调），没有统一的异常兜底 ——
   子线程里抛出的异常默认只是打到 stderr，用户看不到，表现为"点了没反应"。

2. **让 token 归因真正生效**：用量归因靠 `contextvars`（见 `usage_tracker`），
   而 **`contextvars` 在 `threading.Thread` 里不会继承父上下文**（这点与 asyncio
   不同）。若不做处理，每个 `Thread` 里读到的都是 `default=None`，
   `novel_agent` 设置的 `chapter=N` 会全部丢失。
   `Thread(target=ctx.run, args=(fn,))` 是官方给出的正确做法 ——
   在这里做一次，**40 处调用点自动全部获得正确的归因上下文**。

3. **可取消**（v3.2 新增，见 `CancelToken`）：长时间运行的任务（章节生成、
   自动创作整本）原本**只能等**。用户点「停止」只在**两章之间**生效，
   已经发出的那一章必须跑完 —— 表现为"点了停止没反应"，也就是用户感知的**卡死**。
   `CancelToken` 提供了一个协作式中断点，配合 `cancellable()` 可在
   请求之间、重试之间、循环内主动退出。

## 用法

    runner = BackgroundRunner(ui=self.root, log=self._log)
    runner.submit(self._do_heavy_work, on_success=lambda r: self._log(f"完成 {r}"),
                  on_error=runner.messagebox_on_error("生成失败"), log_errors=True)

`ui` 只要求「有 `after(0, fn)` 方法」。传 `None` 时回调**原地同步执行** ——
这正是单测里需要的行为（无需真实 Tk 事件循环）。

取消用法：

    token = runner.submit_cancellable(my_long_job, name="anw-chapter")
    ...
    token.cancel()          # 请求取消；`my_long_job` 内的检查点会尽快退出

任务内部必须**主动**检查（协作式）：

    def my_long_job(token):
        for chapter in chapters:
            token.raise_if_cancelled()      # 在"该能退出"的位置检查
            generate(chapter)
"""

from __future__ import annotations

import contextvars
import threading
import time
import traceback

__all__ = [
    "BackgroundRunner",
    "CancelToken",
    "CancelledError",
    "copy_context_snapshot",
    "context_runner",
    "join_all",
    "DEFAULT_THREAD_NAME",
]

DEFAULT_THREAD_NAME = "anw-worker"

#: 进程内已派发的线程（仅用于测试收尾与调试观测，不参与业务逻辑）
_ISSUED_LOCK = threading.Lock()
_ISSUED: list = []


class CancelledError(Exception):
    """任务因收到取消请求而主动退出。

    ❗ 这是**正常控制流**，不是故障。调用方（`BackgroundRunner.on_cancelled`）
    应当把它和真正的异常分开处理，否则"用户点了停止"会被当成"生成失败"弹窗。
    """


class CancelToken:
    """协作式取消令牌（线程安全）。

    为什么需要它：`threading.Thread` **无法被安全强杀** ——
    `PyThreadState_SetAsyncExc` 之类的手法会留下锁未释放、文件句柄未关、
    半写完的章节文件，比"多跑一会儿"危险得多。所以 Python 里唯一正确的
    取消是**协作式**：调用方置标志，任务在**自己定义的安全点**检查并退出。

    这让"取消"变成双方的契约：

    ====================  ==============================================
    任务方                必须做的
    ====================  ==============================================
    `generate_chapter`    每章开始前 `raise_if_cancelled()`
    `_chat_with_retry`    每次重试前 `raise_if_cancelled()`
    长循环                每轮迭代检查一次
    ====================  ==============================================

    检查点**不该**打在"任意位置"：如果打在一次 HTTP 请求中间，
    退出时请求还在飞、响应没人读 —— 那不是取消，那是泄漏。
    """

    __slots__ = ("_event", "_cancelled_at", "_reason", "_lock")

    def __init__(self, reason: str = ""):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._cancelled_at: float | None = None
        self._reason = reason

    # ---------- 请求取消（任意线程可调） ----------

    def cancel(self, reason: str = "") -> bool:
        """请求取消。返回 `True` 表示**本次调用真的触发了状态变化**。

        幂等：重复调用返回 `False`，不覆盖首次取消的时间与原因
        （首次原因比后续覆盖更有诊断价值）。
        """
        with self._lock:
            if self._event.is_set():
                return False
            if reason:
                self._reason = reason
            self._cancelled_at = time.perf_counter()
            self._event.set()
            return True

    # ---------- 查询 ----------

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason or "用户请求停止"

    @property
    def elapsed(self) -> float | None:
        """从发出取消请求到现在的秒数（未取消返回 `None`）。

        用途：判断"任务是否对取消无响应" —— 超过若干秒仍在跑，
        说明任务的检查点打得太稀，是需要修的信号而不是无法修的问题。
        """
        if self._cancelled_at is None:
            return None
        return time.perf_counter() - self._cancelled_at

    def raise_if_cancelled(self) -> None:
        """检查点。已取消则抛 `CancelledError`。"""
        if self._event.is_set():
            raise CancelledError(self.reason)

    def wait(self, timeout: float | None = None) -> bool:
        """等待被取消（`True` = 已取消）。可用于带超时的短睡眠。"""
        return self._event.wait(timeout)

    # ---------- 上下文管理器 ----------

    def __enter__(self) -> "CancelToken":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # 不吞异常，只保证退出时标记已取消（避免任务"退出但标志未置"的错觉）
        self.cancel()
        return False


#: 当前线程正在执行的任务令牌（供深层调用点用 `current_token()` 取用，
#: 避免把 token 一路当参数往下传 20 层）。
_CURRENT_TOKEN: contextvars.ContextVar["CancelToken | None"] = contextvars.ContextVar("anw_cancel_token", default=None)


def current_token() -> "CancelToken | None":
    """取当前执行上下文的取消令牌（没有则 `None`）。

    为什么用 `contextvars` 而不是 `threading.local`：
    本模块已经用 `contextvars` 传 token 归因上下文，且 `context_runner`
    会把父线程的上下文快照交给子线程 —— 令牌**自动**跟着过去，
    不需要每层函数都加一个 `token=` 参数。
    """
    return _CURRENT_TOKEN.get()


def cancellable(fn):
    """装饰器：把 `fn` 包成"执行前先检查取消"。

    适合给**纯计算或短 IO** 的函数加检查点 —— 长网络请求不该用它
    （见 `CancelToken` 文档里"检查点不该打在哪"的说明）。
    """

    def _wrapper(*args, **kwargs):
        token = current_token()
        if token is not None:
            token.raise_if_cancelled()
        return fn(*args, **kwargs)

    _wrapper.__name__ = getattr(fn, "__name__", "cancellable")
    _wrapper.__doc__ = getattr(fn, "__doc__", None)
    return _wrapper


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
            except BaseException as exc:  # noqa: BLE001 - 兜底是职责
                runner._handle_error(exc, log_errors, on_error, name)
            else:
                runner.dispatch(on_success, result)
            finally:
                runner.dispatch(on_finally)

        # 关键：**在父线程**把上下文快照交给子线程执行。
        # （`threading.Thread` 不继承 contextvars；若在子线程里 copy_context()
        #  就会拷到子线程自己那份空上下文，等于没做。见 `context_runner`。）
        thread = threading.Thread(target=context_runner(_target), name=name, daemon=daemon)
        self._threads.append(thread)
        with _ISSUED_LOCK:
            # 顺手清掉已结束的登记，5000 章长跑下这个列表才不会无限增长
            _ISSUED[:] = [t for t in _ISSUED if t.is_alive()]
            _ISSUED.append(thread)
        thread.start()
        return thread

    def submit_cancellable(
        self,
        work,
        *args,
        token: "CancelToken | None" = None,
        on_success=None,
        on_cancelled=None,
        on_error=None,
        on_finally=None,
        name: str = DEFAULT_THREAD_NAME,
        log_errors: bool = False,
        watchdog: float | None = None,
        **kwargs,
    ) -> CancelToken:
        """派发一个**可取消**的后台任务，返回它的 `CancelToken`。

        与 `submit` 的三点不同：

        1. `work` 会被传入 `token` 作为**第一个位置参数**；
        2. 任务内抛出的 `CancelledError` **不算失败**，走 `on_cancelled()` ——
           否则"用户点了停止"会被当成"生成失败"弹窗（这是很容易犯的错）；
        3. `token` 通过 `contextvars` 发布，深层代码可用 `current_token()`
           取到，不必逐层传参。

        `watchdog`：取消后允许任务继续跑多久（秒）。超过则记一条**警告日志**
        （不是强杀 —— 强杀线程不安全，见 `CancelToken` 文档）。
        它的价值在于**让"停止无响应"从"说不清的现象"变成"可观测的事件"**。
        """
        token = token or CancelToken()
        runner = self

        def _target():
            try:
                result = work(token, *args, **kwargs)
            except CancelledError:
                # ❗ 正常控制流，不是故障 —— 必须走独立出口
                runner.dispatch(on_cancelled, token)
            except BaseException as exc:  # noqa: BLE001 - 兜底是职责
                runner._handle_error(exc, log_errors, on_error, name)
            else:
                runner.dispatch(on_success, result)
            finally:
                runner.dispatch(on_finally)

        def _run_in_context():
            # token 通过 contextvars 发布；`context_runner` 已把父线程快照
            # 交给子线程，所以这里 set 的值只对**本任务**可见，不会串台。
            _CURRENT_TOKEN.set(token)
            _target()

        thread = threading.Thread(target=context_runner(_run_in_context), name=name, daemon=True)
        self._threads.append(thread)
        with _ISSUED_LOCK:
            _ISSUED[:] = [t for t in _ISSUED if t.is_alive()]
            _ISSUED.append(thread)
        thread.start()

        if watchdog is not None and watchdog > 0:
            self._start_watchdog(token, thread, watchdog, name)
        return token

    def _start_watchdog(self, token: CancelToken, thread: threading.Thread, grace: float, name: str) -> None:
        """监视"取消后任务是否真的退出"（daemon 线程，不阻塞退出）。"""

        def _watch():
            while not token.cancelled:
                if not thread.is_alive():
                    return  # 任务自己先结束了，无需监视
                time.sleep(min(0.2, grace))
            thread.join(grace)
            if thread.is_alive():
                elapsed = token.elapsed or 0.0
                self.dispatch(
                    self._log,
                    f"[{name}] 已请求停止 {elapsed:.1f}s，但任务仍在运行 —— "
                    f"该任务的取消检查点可能打得太稀（这是需要修的信号）。",
                )

        threading.Thread(target=_watch, name=f"{name}-watchdog", daemon=True).start()

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

        ⚠️ 延迟 import（两层都是）：本模块要能在**无 Tk 的服务器/单测环境**被导入，
        而 `app.dialogs` 顶层 `import tkinter`。所以这里既不能顶层导入 dialogs，
        也不能在工厂里导入 —— 必须等到真的要弹窗时。
        """

        def _show(exc):
            from app import dialogs

            dialogs.showerror(title, f"{type(exc).__name__}: {exc}", parent=parent)

        return _show

    # ------------------------------------------------------------ 生命周期

    def join(self, timeout: float = 5.0) -> None:
        """等待本实例派发的全部线程结束（测试用）。"""
        for thread in list(self._threads):
            thread.join(timeout)

    @property
    def alive(self) -> list:
        return [t for t in self._threads if t.is_alive()]
