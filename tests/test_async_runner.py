"""统一后台执行器测试（v3 §1.1 A6 + v3.2 取消）。

本文件的核心不是"能起线程"，而是四件容易做错的事：

1. **回调必须回主线程**（`ui.after(0, ...)`），且窗口已销毁时不能崩
2. **异常不能被吞** —— v2 的 40 处裸线程表现为"点了没反应"，正是异常只落在 stderr
3. **上下文必须继承** —— `contextvars` 在裸 `Thread` 里会丢（见 usage_tracker 测试）
4. **取消是正常控制流，不是故障**（v3.2）—— 与 `on_error` 必须分开，
   否则"用户点了停止"会被弹成"生成失败"
"""

import sys
import threading
import time
from pathlib import Path

import pytest

from app.async_runner import (
    DEFAULT_THREAD_NAME,
    BackgroundRunner,
    CancelledError,
    CancelToken,
    context_runner,
    copy_context_snapshot,
    current_token,
    join_all,
)

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


class FakeUi:
    """伪 Tk：`after(0, fn)` 记录回调但不立即执行，便于断言"确实派发了"。"""

    def __init__(self):
        self.scheduled = []

    def after(self, delay, fn):
        self.scheduled.append((delay, fn))
        return "id-1"

    def flush(self):
        """在"主线程"里执行所有已派发的回调（测试里就是当前线程）。"""
        while self.scheduled:
            _delay, fn = self.scheduled.pop(0)
            fn()


class DeadUi:
    """窗口已关闭的 Tk：`after` 抛 RuntimeError。"""

    def after(self, delay, fn):
        raise RuntimeError("main thread is not in main loop")


class TestContextHelpers:
    def test_snapshot_returns_context(self):
        import contextvars

        assert isinstance(copy_context_snapshot(), contextvars.Context)

    def test_context_runner_executes_fn(self):
        assert context_runner(lambda: 42)() == 42

    def test_runner_constructed_in_parent_sees_parent_context(self):
        """快照必须在**父线程**取 —— 这是本模块最核心的一条正确性要求。"""
        from app.usage_tracker import current_usage_context, usage_context

        seen = {}
        with usage_context(chapter=5):
            runner = BackgroundRunner()
            runner.submit(lambda: seen.update(current_usage_context())).join()
        assert seen == {"chapter": 5}

    def test_runner_constructed_inside_child_would_lose_context(self):
        """反向固化：若在子线程里才 `copy_context`，章号就会丢。

        这条用例把"为什么 `submit` 必须在父线程拷贝"变成了可执行文档 ——
        将来有人把 `context_runner` 挪进线程体，这里就会红。
        """
        import threading

        from app.usage_tracker import current_usage_context, usage_context

        seen = {}

        def child():
            seen.update(current_usage_context())

        with usage_context(chapter=5):
            thread = threading.Thread(target=child)
            thread.start()
            thread.join()
        assert "chapter" not in seen


class TestSubmit:
    def test_runs_work_and_dispatches_success(self):
        ui = FakeUi()
        runner = BackgroundRunner(ui=ui)
        runner.submit(lambda: "done").join()
        ui.flush()
        assert True  # 不抛异常即通过；结果断言在下一个用例

    def test_success_callback_receives_result(self):
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).submit(lambda: 7, on_success=seen.append).join()
        ui.flush()
        assert seen == [7]

    def test_thread_name_is_used(self):
        names = []
        runner = BackgroundRunner()
        runner.submit(lambda: names.append(threading.current_thread().name), name="anw-test").join()
        assert names == ["anw-test"]
        assert DEFAULT_THREAD_NAME == "anw-worker"

    def test_returns_joinable_thread(self):
        thread = BackgroundRunner().submit(lambda: None)
        assert isinstance(thread, threading.Thread)
        thread.join(2)
        assert not thread.is_alive()

    def test_finally_callback_runs_on_success(self):
        ui = FakeUi()
        calls = []
        BackgroundRunner(ui=ui).submit(lambda: "ok", on_finally=lambda: calls.append("finally")).join()
        ui.flush()
        assert calls == ["finally"]


class TestErrorHandling:
    def test_error_callback_receives_exception(self):
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            on_error=seen.append,
        ).join()
        ui.flush()
        assert isinstance(seen[0], RuntimeError)
        assert str(seen[0]) == "boom"

    def test_log_errors_routes_to_log(self):
        ui = FakeUi()
        messages = []
        BackgroundRunner(ui=ui, log=messages.append).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")), log_errors=True
        ).join()
        ui.flush()
        assert any("boom" in message for message in messages)

    def test_silent_failure_still_logs_traceback(self):
        """两个出口都没配时，也**必须**留下 traceback —— 绝不静默。

        这正是 v2 那 40 处裸线程的病灶：用户只看到"点了没反应"。
        """
        ui = FakeUi()
        messages = []
        BackgroundRunner(ui=ui, log=messages.append).submit(lambda: (_ for _ in ()).throw(RuntimeError("lost"))).join()
        ui.flush()
        assert messages and "Traceback" in messages[0]
        assert "lost" in messages[0]

    def test_error_callback_takes_priority_over_log(self):
        ui = FakeUi()
        seen = []
        messages = []
        BackgroundRunner(ui=ui, log=messages.append).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            on_error=seen.append,
            log_errors=True,
        ).join()
        ui.flush()
        assert len(seen) == 1
        assert messages == []

    def test_finally_runs_after_error(self):
        ui = FakeUi()
        calls = []
        BackgroundRunner(ui=ui).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            on_error=lambda _exc: None,
            on_finally=lambda: calls.append("f"),
        ).join()
        ui.flush()
        assert calls == ["f"]

    def test_base_exception_is_caught(self):
        """`BaseException`（如任务被中断）也必须走统一出口，不能静默消失。"""
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).submit(lambda: (_ for _ in ()).throw(KeyboardInterrupt()), on_error=seen.append).join()
        ui.flush()
        assert isinstance(seen[0], KeyboardInterrupt)


class TestDispatch:
    def test_without_ui_callbacks_run_inline(self):
        seen = []
        BackgroundRunner().dispatch(seen.append, 1)
        assert seen == [1]

    def test_ui_after_is_used(self):
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).dispatch(seen.append, 2)
        assert seen == []  # 还没 flush
        ui.flush()
        assert seen == [2]

    def test_dead_ui_falls_back_to_inline(self):
        """窗口已销毁时：`after` 抛 RuntimeError → 原地执行，不让后台线程崩。"""
        seen = []
        BackgroundRunner(ui=DeadUi()).dispatch(seen.append, 3)
        assert seen == [3]

    def test_none_callback_is_noop(self):
        BackgroundRunner(ui=FakeUi()).dispatch(None)

    def test_after_values_are_passed(self):
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).submit(lambda: "r", on_success=seen.append).join()
        ui.flush()
        assert seen == ["r"]


class TestMessageboxFactory:
    def test_returns_callable(self):
        handler = BackgroundRunner.messagebox_on_error("失败")
        assert callable(handler)

    def test_imports_tkinter_lazily(self):
        """工厂本身不能 import tkinter / dialogs —— 否则无 GUI 环境（服务器/CI）导入即失败。

        ⚠️ 注意是**两层**都要延迟：`app/dialogs.py` 顶层 `import tkinter`，
        所以既不能在模块顶层导入 dialogs，也不能在工厂里导入 ——
        必须等到真的要弹窗（`_show` 被调用）时。
        """
        code = _scan.code_only("app/async_runner.py")
        assert "from app import dialogs" in code
        assert "dialogs.showerror(" in code
        # 顶层（模块级导入区）不得出现 tkinter / dialogs —— 只允许出现在函数体内
        header = code.split("def messagebox_on_error")[0]
        assert "tkinter" not in header
        assert "dialogs" not in header


class TestJoinAll:
    def test_joins_issued_threads(self):
        holder = []

        def slow():
            holder.append(1)

        runner = BackgroundRunner()
        runner.submit(slow)
        runner.join(timeout=2)
        assert holder == [1]

    def test_module_level_join_all(self):
        counter = {"n": 0}

        def bump():
            counter["n"] += 1

        BackgroundRunner().submit(bump)
        join_all(timeout=2)
        assert counter["n"] == 1

    def test_alive_property(self):
        import time

        runner = BackgroundRunner()
        runner.submit(lambda: time.sleep(0.3))
        assert runner.alive
        runner.join(timeout=3)
        assert runner.alive == []


# ====================================================================== v3.2 取消


class TestCancelToken:
    """取消令牌的纯逻辑（不涉及线程）。"""

    def test_initial_state_is_not_cancelled(self):
        token = CancelToken()
        assert not token.cancelled and token.elapsed is None
        assert token.reason == "用户请求停止"  # 未给原因时的默认文案

    def test_cancel_is_idempotent_and_keeps_first_reason(self):
        token = CancelToken()
        assert token.cancel("第一次") is True
        assert token.cancel("第二次") is False, "重复取消应返回 False（表示无状态变化）"
        assert token.reason == "第一次", "后一次不该覆盖先到达的原因"
        assert token.elapsed is not None

    def test_raise_if_cancelled(self):
        token = CancelToken()
        token.raise_if_cancelled()  # 未取消 ⇒ 不抛
        token.cancel("够了")
        with pytest.raises(CancelledError) as exc:
            token.raise_if_cancelled()
        assert "够了" in str(exc.value)

    def test_elapsed_grows(self):
        token = CancelToken()
        token.cancel()
        first = token.elapsed
        time.sleep(0.05)
        assert token.elapsed > first

    def test_wait_returns_true_when_cancelled(self):
        token = CancelToken()
        threading.Timer(0.05, token.cancel).start()
        assert token.wait(2.0) is True

    def test_wait_times_out_when_not_cancelled(self):
        assert CancelToken().wait(0.05) is False

    def test_context_manager_cancels_on_exit(self):
        token = CancelToken()
        with token:
            assert not token.cancelled
        assert token.cancelled

    def test_cancelled_error_is_an_exception(self):
        assert issubclass(CancelledError, Exception)


class TestCancellableExecution:
    """`submit_cancellable` 的真实线程行为。"""

    def test_task_receives_token_as_first_arg(self):
        holder = {}

        def work(token):
            holder["token"] = token
            return "done"

        runner = BackgroundRunner()
        token = runner.submit_cancellable(work)
        runner.join(timeout=2)
        assert holder["token"] is token

    def test_token_is_published_via_contextvars(self):
        """深层代码能用 `current_token()` 取到令牌，不必逐层传参。"""
        holder = {}

        def work(token):
            holder["same"] = current_token() is token

        runner = BackgroundRunner()
        runner.submit_cancellable(work)
        runner.join(timeout=2)
        assert holder["same"] is True

    def test_token_does_not_leak_after_task(self):
        """任务结束后当前上下文里不该还留着旧令牌。"""

        def work(_token):
            return None

        runner = BackgroundRunner()
        runner.submit_cancellable(work)
        runner.join(timeout=2)
        assert current_token() is None

    def test_cancellation_routes_to_on_cancelled_not_on_error(self):
        """❗ 本组最重要的一条：取消是**正常控制流**，不是故障。

        若把 `CancelledError` 混进 `on_error`，用户点「停止」会看到"生成失败"弹窗。
        """
        seen = {}

        def work(token):
            for _ in range(200):
                token.raise_if_cancelled()
                time.sleep(0.005)
            return "never"

        runner = BackgroundRunner()
        token = runner.submit_cancellable(
            work,
            on_success=lambda r: seen.update(success=r),
            on_cancelled=lambda t: seen.update(cancelled=t.reason),
            on_error=lambda e: seen.update(error=repr(e)),
        )
        time.sleep(0.05)
        token.cancel("测试取消")
        runner.join(timeout=3)
        assert "cancelled" in seen, f"未走到 on_cancelled：{seen}"
        assert "error" not in seen and "success" not in seen

    def test_task_completes_normally_when_not_cancelled(self):
        seen = {}

        def work(_token):
            return 42

        runner = BackgroundRunner()
        runner.submit_cancellable(work, on_success=lambda r: seen.update(r=r))
        runner.join(timeout=2)
        assert seen["r"] == 42

    def test_real_exception_still_goes_to_on_error(self):
        """真正的异常不能被取消出口吞掉 —— 两个出口必须区分开。"""
        seen = {}

        def work(_token):
            raise ValueError("真的出错了")

        runner = BackgroundRunner()
        runner.submit_cancellable(
            work,
            on_error=lambda e: seen.update(error=type(e).__name__),
            on_cancelled=lambda _t: seen.update(cancelled=True),
        )
        runner.join(timeout=2)
        assert seen.get("error") == "ValueError" and "cancelled" not in seen

    def test_on_finally_runs_on_both_paths(self):
        for cancel in (False, True):
            calls = []

            def work(token):
                if cancel:
                    token.cancel()
                    token.raise_if_cancelled()
                return "ok"

            runner = BackgroundRunner()
            runner.submit_cancellable(work, on_finally=lambda: calls.append(1))
            runner.join(timeout=2)
            assert calls == [1], f"cancel={cancel} 时 on_finally 未执行"


class TestWatchdog:
    """看门狗：把"停止无响应"从现象变成可观测事件。"""

    def test_watchdog_warns_when_task_ignores_cancel(self):
        logs = []
        started = threading.Event()

        def stubborn(token):
            started.set()
            time.sleep(1.2)  # 故意忽略 token
            return "finally"

        runner = BackgroundRunner(log=logs.append)
        token = runner.submit_cancellable(stubborn, watchdog=0.15, name="anw-stubborn")
        assert started.wait(2)
        token.cancel("停")
        runner.join(timeout=3)
        assert any("仍在运行" in m for m in logs), f"看门狗没报警：{logs}"

    def test_watchdog_is_silent_when_task_exits_promptly(self):
        logs = []

        def cooperative(token):
            for _ in range(200):
                token.raise_if_cancelled()
                time.sleep(0.005)

        runner = BackgroundRunner(log=logs.append)
        token = runner.submit_cancellable(cooperative, watchdog=0.15, name="anw-good")
        time.sleep(0.05)
        token.cancel("停")
        runner.join(timeout=3)
        assert not any("仍在运行" in m for m in logs), f"不该报警：{logs}"


class TestCancellationWiring:
    """接线守卫：生成流程必须真的用上取消令牌。"""

    def test_generation_ui_creates_token(self):
        code = _scan.code_only("app/generation_ui.py")
        assert "CancelToken()" in code, "自动创作没有创建取消令牌"
        assert "_auto_token" in code

    def test_stop_handler_cancels_token(self):
        """❗ 只创建令牌而不在「停止」里 cancel，等于没做 —— 必须钉住。"""
        body = _scan.method_body("app/generation_ui.py", "def _stop_generate", "def _auto_detect_decisions")
        assert ".cancel(" in body, "「停止」按钮没有触发取消令牌"

    def test_loop_checks_token(self):
        code = _scan.code_only("app/generation_ui.py")
        assert "token.cancelled" in code or "raise_if_cancelled" in code
