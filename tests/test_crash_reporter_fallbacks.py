"""`crash_reporter` 的降级路径（档 3：崩了还得留下现场）。

## 这个模块最反直觉的要求

它自己**必须比崩溃更结实**：崩溃时磁盘可能已满、日志系统可能已坏、
原 `excepthook` 可能是 IDE 的调试钩子。任何一步失败都**不能掩盖原始崩溃**
（否则用户看到的是"报告器报错"，而不是"程序为什么崩"）。

所以这里测的全是"坏情况下还剩什么"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app import crash_reporter as cr


class TestResolveDir:
    def test_explicit_dir_wins(self, tmp_path):
        assert cr.resolve_crash_dir(tmp_path) == tmp_path

    def test_default_sits_next_to_logs(self):
        resolved = cr.resolve_crash_dir()

        assert resolved.name == "crashes"


class TestAppVersion:
    def test_version_readable(self):
        assert cr._app_version() not in ("", None)

    def test_version_failure_returns_unknown(self, monkeypatch):
        """版本读不到不该影响崩溃报告本身。"""
        monkeypatch.setitem(sys.modules, "app", None)

        assert cr._app_version() == "unknown"


class TestRecentLogs:
    def test_no_shards_returns_empty(self, tmp_path):
        assert cr._recent_logs(tmp_path) == []

    def test_takes_tail_of_newest_shard(self, tmp_path):
        (tmp_path / "2026-01-01.jsonl").write_text("旧\n", encoding="utf-8")
        (tmp_path / "2026-11-28.jsonl").write_text("新1\n新2\n", encoding="utf-8")

        lines = cr._recent_logs(tmp_path)

        assert "新2" in lines

    def test_read_error_returns_empty(self, tmp_path, monkeypatch):
        (tmp_path / "2026-11-28.jsonl").write_text("x\n", encoding="utf-8")
        real = Path.read_text

        def boom(self, *a, **kw):
            raise OSError("占用")

        monkeypatch.setattr(Path, "read_text", boom)
        assert cr._recent_logs(tmp_path) == []
        monkeypatch.setattr(Path, "read_text", real)


class TestPrune:
    def test_keeps_only_latest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cr, "_MAX_REPORTS", 2)
        for i in range(5):
            (tmp_path / f"crash-2026010{i}-000000.json").write_text("{}", encoding="utf-8")

        cr._prune(tmp_path)

        names = sorted(p.name for p in tmp_path.glob("crash-*.json"))
        assert names == ["crash-20260103-000000.json", "crash-20260104-000000.json"]

    def test_unlink_failure_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cr, "_MAX_REPORTS", 1)
        for i in range(3):
            (tmp_path / f"crash-2026010{i}-000000.json").write_text("{}", encoding="utf-8")

        def boom(self, *a, **kw):
            raise OSError("只读")

        monkeypatch.setattr(Path, "unlink", boom)

        cr._prune(tmp_path)  # 不抛即通过


class TestWriteReport:
    def test_writes_json_with_traceback(self, tmp_path):
        try:
            raise ValueError("原始错误")
        except ValueError:
            exc_type, exc, tb = sys.exc_info()
            path = cr.write_crash_report("uncaught", exc_type, exc, tb, crash_dir=tmp_path, log_dir=tmp_path)

        assert path is not None and path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["kind"] == "uncaught"
        assert any("原始错误" in line for line in payload["traceback"])

    def test_traceback_without_exception(self, tmp_path):
        """只有 tb 没有 exc（某些解释器退出期）时走 `format_tb` 分支。"""
        try:
            raise ValueError("x")
        except ValueError:
            _t, _e, tb = sys.exc_info()
            path = cr.write_crash_report("uncaught", None, None, tb, crash_dir=tmp_path, log_dir=tmp_path)

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["traceback"]

    def test_write_failure_returns_none(self, tmp_path, monkeypatch):
        """报告写不出来返回 None，**绝不抛** —— 否则原始崩溃被掩盖。"""

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(cr, "atomic_write_json", boom)

        assert cr.write_crash_report("uncaught", None, None, None, crash_dir=tmp_path, log_dir=tmp_path) is None

    def test_log_also_broken_only_prints_to_stderr(self, tmp_path, monkeypatch, capsys):
        """连日志器都坏了 ⇒ 只剩 stderr 这一条路（仍不能抛）。"""

        class DeadLogger:
            def debug(self, *_a, **_kw):
                raise RuntimeError("日志系统已死")

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(cr, "atomic_write_json", boom)
        monkeypatch.setattr(cr, "logger", DeadLogger())

        assert cr.write_crash_report("uncaught", None, None, None, crash_dir=tmp_path, log_dir=tmp_path) is None
        assert "报告与日志均不可用" in capsys.readouterr().err


class TestInstallHooks:
    def test_installs_and_chains_previous_hook(self, tmp_path, monkeypatch):
        """必须**链式调用**原钩子 —— 否则 IDE/调试器的崩溃处理被顶掉。"""
        monkeypatch.setattr(cr, "_INSTALLED", False)
        called: list[str] = []
        original = sys.excepthook
        monkeypatch.setattr(sys, "excepthook", lambda *a: called.append("prev"))
        try:
            assert cr.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=False) is True

            sys.excepthook(ValueError, ValueError("x"), None)

            assert called == ["prev"], "原 excepthook 没有被调用"
            assert list(tmp_path.glob("crash-*.json")), "崩溃报告没有落盘"
        finally:
            sys.excepthook = original

    def test_previous_hook_failure_is_swallowed(self, tmp_path, monkeypatch):
        """原钩子抛错不能掩盖原始崩溃。"""
        monkeypatch.setattr(cr, "_INSTALLED", False)
        original = sys.excepthook

        def bad_hook(*_a):
            raise RuntimeError("IDE 钩子坏了")

        monkeypatch.setattr(sys, "excepthook", bad_hook)
        try:
            cr.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=False)

            sys.excepthook(ValueError, ValueError("x"), None)  # 不抛即通过
        finally:
            sys.excepthook = original

    def test_thread_hook_handles_missing_exc_type(self, tmp_path, monkeypatch):
        """解释器退出期 `args.exc_type` 可能为 None —— 此时不写报告但不能崩。"""
        monkeypatch.setattr(cr, "_INSTALLED", False)
        import threading

        original = getattr(threading, "excepthook", None)
        # pytest 自己也挂了一个 threading.excepthook，它会对假 args 抛 RuntimeError；
        # 这里先把"上一个钩子"换成空操作，验的是**被链式调用**而不是它的实现
        monkeypatch.setattr(threading, "excepthook", lambda _args: None)
        try:
            cr.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=False)

            args = type("Args", (), {"exc_type": None, "exc_value": None, "exc_traceback": None})()
            threading.excepthook(args)  # 不抛即通过
        finally:
            if original is not None:
                threading.excepthook = original

    def test_faulthandler_failure_degrades(self, tmp_path, monkeypatch):
        """faulthandler 起不来只降级，不影响 JSON 报告。"""

        def boom(*_a, **_kw):
            raise OSError("无写权限")

        monkeypatch.setattr(cr, "_INSTALLED", False)
        monkeypatch.setattr(cr.faulthandler, "enable", boom)

        assert cr.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=True) is True
