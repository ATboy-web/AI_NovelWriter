"""崩溃报告的契约测试（不写真实用户目录）。

## 为什么值得测

崩溃报告只在"出事时"运行 —— 它自己崩掉或写错字段，平时永远发现不了，
等到用户反馈时才发现报告是空的。因此这里把三条硬契约钉住：

1. **字段完整**：kind/version/python/platform/frozen/exception/traceback
2. **绝不抛异常**：目录不可写、日志读不到时返回 None 而不是把原始崩溃掩盖掉
3. **有上限**：长时间运行不会把崩溃文件堆满磁盘

`install_crash_hooks` 还会改全局 `sys.excepthook` 与模块级哨兵，测试必须复原。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from app import crash_reporter


@pytest.fixture(autouse=True)
def _reset_installed(monkeypatch):
    """每个用例都从"未安装"开始，结束后恢复哨兵与原 hook。"""
    monkeypatch.setattr(crash_reporter, "_INSTALLED", False)
    origin = sys.excepthook
    origin_thread = threading.excepthook
    yield
    sys.excepthook = origin
    threading.excepthook = origin_thread


def _raise_and_report(tmp: Path, kind: str = "uncaught") -> Path | None:
    try:
        raise KeyError("missing_key")
    except KeyError as exc:
        return crash_reporter.write_crash_report(kind, type(exc), exc, exc.__traceback__, crash_dir=tmp, log_dir=tmp)


class TestWriteReport:
    def test_writes_json_with_all_fields(self, tmp_path):
        path = _raise_and_report(tmp_path)
        assert path is not None and path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) >= {
            "kind",
            "timestamp",
            "app_version",
            "python",
            "platform",
            "executable",
            "frozen",
            "exception",
            "traceback",
            "recent_logs",
        }
        assert data["kind"] == "uncaught"
        assert data["exception"] == {"type": "KeyError", "message": "'missing_key'"}
        assert any("KeyError" in line for line in data["traceback"])

    def test_filename_contains_kind_and_pid(self, tmp_path):
        path = _raise_and_report(tmp_path, kind="thread")
        assert path is not None
        assert "thread" in path.name
        assert path.parent == tmp_path  # crash_dir 参数即落点目录

    def test_keeps_only_max_reports(self, tmp_path):
        # 造 25 份旧报告（文件名含时间戳，按名排序即按时间排序）
        tmp_path.mkdir(parents=True, exist_ok=True)
        for i in range(25):
            (tmp_path / f"crash-20260101-0000{i:02d}-1-uncaught.json").write_text("{}", encoding="utf-8")
        _raise_and_report(tmp_path)
        remaining = list(tmp_path.glob("crash-*.json"))
        assert len(remaining) == crash_reporter._MAX_REPORTS

    def test_unwritable_dir_returns_none(self, tmp_path):
        # 用一个"父路径是文件"的非法目录制造失败
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        result = crash_reporter.write_crash_report(
            "uncaught", ValueError, ValueError("x"), None, crash_dir=blocker / "sub"
        )
        assert result is None

    def test_recent_logs_attached(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "app-2026-11-25.jsonl").write_text("\n".join(f'{{"i": {i}}}' for i in range(80)), encoding="utf-8")
        crash_dir = tmp_path / "crashes"
        path = crash_reporter.write_crash_report(
            "uncaught", ValueError, ValueError("x"), None, crash_dir=crash_dir, log_dir=log_dir
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["recent_logs"]) == crash_reporter._RECENT_LOG_LINES
        assert '"i": 79' in data["recent_logs"][-1]

    def test_missing_log_dir_is_tolerated(self, tmp_path):
        path = crash_reporter.write_crash_report(
            "uncaught", ValueError, ValueError("x"), None, crash_dir=tmp_path, log_dir=tmp_path / "nope"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["recent_logs"] == []


class TestInstallHooks:
    def test_install_is_idempotent(self, tmp_path):
        assert crash_reporter.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path) is True
        assert crash_reporter.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path) is False

    def test_uncaught_hook_writes_report_and_chains(self, tmp_path, monkeypatch):
        chained: list = []
        monkeypatch.setattr(sys, "excepthook", lambda *a: chained.append(a))

        crash_reporter.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=False)
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)

        reports = list(tmp_path.glob("crash-*-uncaught.json"))
        assert len(reports) == 1
        assert chained, "原 excepthook 必须被链式调用"

    def test_thread_hook_writes_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(threading, "excepthook", lambda args: None)
        crash_reporter.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=False)

        def worker():
            raise ValueError("子线程炸了")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        reports = list(tmp_path.glob("crash-*-thread.json"))
        assert len(reports) == 1
        data = json.loads(reports[0].read_text(encoding="utf-8"))
        assert data["exception"]["type"] == "ValueError"

    def test_faulthandler_file_created(self, tmp_path):
        crash_reporter.install_crash_hooks(crash_dir=tmp_path, log_dir=tmp_path, enable_faulthandler=True)
        assert (tmp_path / "faulthandler.log").exists()
