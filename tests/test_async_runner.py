"""统一后台执行器测试（v3 §1.1 A6）。

本文件的核心不是"能起线程"，而是三件容易做错的事：

1. **回调必须回主线程**（`ui.after(0, ...)`），且窗口已销毁时不能崩
2. **异常不能被吞** —— v2 的 40 处裸线程表现为"点了没反应"，正是异常只落在 stderr
3. **上下文必须继承** —— `contextvars` 在裸 `Thread` 里会丢（见 usage_tracker 测试）
"""

import sys
import threading
from pathlib import Path

from app.async_runner import (
    DEFAULT_THREAD_NAME,
    BackgroundRunner,
    context_runner,
    copy_context_snapshot,
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
        runner.submit(lambda: names.append(threading.current_thread().name),
                      name="anw-test").join()
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
        BackgroundRunner(ui=ui).submit(
            lambda: "ok", on_finally=lambda: calls.append("finally")
        ).join()
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
        BackgroundRunner(ui=ui, log=messages.append).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("lost"))
        ).join()
        ui.flush()
        assert messages and "Traceback" in messages[0]
        assert "lost" in messages[0]

    def test_error_callback_takes_priority_over_log(self):
        ui = FakeUi()
        seen = []
        messages = []
        BackgroundRunner(ui=ui, log=messages.append).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            on_error=seen.append, log_errors=True,
        ).join()
        ui.flush()
        assert len(seen) == 1
        assert messages == []

    def test_finally_runs_after_error(self):
        ui = FakeUi()
        calls = []
        BackgroundRunner(ui=ui).submit(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            on_error=lambda _exc: None, on_finally=lambda: calls.append("f"),
        ).join()
        ui.flush()
        assert calls == ["f"]

    def test_base_exception_is_caught(self):
        """`BaseException`（如任务被中断）也必须走统一出口，不能静默消失。"""
        ui = FakeUi()
        seen = []
        BackgroundRunner(ui=ui).submit(
            lambda: (_ for _ in ()).throw(KeyboardInterrupt()), on_error=seen.append
        ).join()
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
        assert seen == []              # 还没 flush
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
        """工厂本身不能 import tkinter —— 否则无 GUI 环境（服务器/CI）导入即失败。"""
        code = _scan.code_only("app/async_runner.py")
        assert "from tkinter import messagebox" in code
        # 顶层（模块级导入区）不得出现 tkinter —— 只允许出现在函数体内
        header = code.split("def messagebox_on_error")[0]
        assert "tkinter" not in header


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
