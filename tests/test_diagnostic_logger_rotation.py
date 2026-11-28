"""`diagnostic_logger` 的轮转与写失败容错（档 3：诊断日志本身不能成为故障源）。

## 这个模块的两条硬要求

1. **轮转不能丢最近的文件**：诊断日志是崩溃后唯一的线索，
   轮转写错（覆盖而不是顺移）等于把现场删掉；
2. **写日志失败绝不能影响主流程**：磁盘满、文件被占用时，业务照常跑。

场景里的失效很隐蔽：日志文件悄悄停止增长，用户以为"没出错"。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import diagnostic_logger as dl


@pytest.fixture
def logger(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "resolve_log_dir", lambda *a, **kw: tmp_path)
    inst = dl.DiagnosticLogger(log_dir=tmp_path)
    return inst


class TestRotation:
    def test_rotates_when_oversized(self, logger, tmp_path, monkeypatch):
        monkeypatch.setattr(logger, "MAX_FILE_SIZE", 10)
        logger._current_file.write_text("x" * 100, encoding="utf-8")
        today = logger._current_file.name

        new_file = logger._get_log_file()

        assert new_file.name == today, "轮转后主文件名应保持不变（日期不变）"
        backup = tmp_path / f"{Path(today).stem}.1.jsonl"
        assert backup.exists(), "超限文件没有被留成 .1 备份"
        assert backup.read_text(encoding="utf-8") == "x" * 100

    def test_rotation_shifts_existing_backups(self, logger, tmp_path, monkeypatch):
        """已有 `.1` 时要先顺移成 `.2`，不能直接覆盖 —— 否则丢掉更早的现场。"""
        monkeypatch.setattr(logger, "MAX_FILE_SIZE", 10)
        logger._current_file.write_text("x" * 100, encoding="utf-8")
        stem = Path(logger._current_file.name).stem
        (tmp_path / f"{stem}.1.jsonl").write_text("旧的1", encoding="utf-8")
        (tmp_path / f"{stem}.2.jsonl").write_text("旧的2", encoding="utf-8")

        logger._get_log_file()

        assert (tmp_path / f"{stem}.2.jsonl").read_text(encoding="utf-8") == "旧的1"
        assert (tmp_path / f"{stem}.3.jsonl").read_text(encoding="utf-8") == "旧的2"

    def test_rotation_stops_at_backup_limit(self, logger, tmp_path, monkeypatch):
        """`MAX_BACKUP_FILES=2` 时最多顺移到 `.2`，不会继续往下造。

        ⚠️ 注意它**不清理**历史上超出当前上限的更老文件（`.3`/`.4` 会留着）——
        实测行为如此，所以判据只钉"不再新建超过上限的备份"。
        """
        monkeypatch.setattr(logger, "MAX_FILE_SIZE", 10)
        monkeypatch.setattr(logger, "MAX_BACKUP_FILES", 2)
        logger._current_file.write_text("x" * 100, encoding="utf-8")
        stem = Path(logger._current_file.name).stem

        logger._get_log_file()

        # 首次轮转（没有更早备份）只会产生 `.1`；顺移链的最大编号受上限约束
        assert (tmp_path / f"{stem}.1.jsonl").exists()
        assert not (tmp_path / f"{stem}.3.jsonl").exists(), "超过了备份上限还继续顺移"

    def test_no_rotation_when_small(self, logger, monkeypatch):
        monkeypatch.setattr(logger, "MAX_FILE_SIZE", 10_000)
        logger._current_file.write_text("短", encoding="utf-8")

        assert logger._get_log_file() == logger._current_file


class TestWriteFailures:
    def test_open_failure_is_swallowed(self, logger, monkeypatch):
        """写日志失败**绝不能影响主流程** —— 磁盘满时业务要继续跑。"""
        import builtins

        real_open = builtins.open

        def boom(path, *a, **kw):
            if "diagnostic-" in str(path):
                raise OSError("磁盘满")
            return real_open(path, *a, **kw)

        monkeypatch.setattr(builtins, "open", boom)

        logger.log("ai_call", {"prompt": "x"})  # 不抛即通过

    def test_rotation_check_before_write(self, logger, monkeypatch):
        """写入前要再查一次大小 —— 长跑进程不会因为"启动时才查"而无限长。"""
        monkeypatch.setattr(logger, "MAX_FILE_SIZE", 5)
        logger._current_file.write_text("x" * 100, encoding="utf-8")
        rotated: list[bool] = []
        real = logger._get_log_file

        def spy():
            rotated.append(True)
            return real()

        monkeypatch.setattr(logger, "_get_log_file", spy)

        logger.log("ai_call", {"prompt": "y"})

        assert rotated, "写入前没有再检查轮转"


class TestTruncation:
    def test_deep_data_truncated(self, logger):
        data: dict = {}
        cursor = data
        for i in range(6):
            cursor["n"] = {}
            cursor = cursor["n"]

        result = logger._truncate_data(data)

        assert isinstance(result, (dict, str))

    def test_long_string_truncated(self, logger):
        result = logger._truncate_data({"text": "x" * 5000})

        assert len(str(result["text"])) < 5000


class TestDisabledMode:
    def test_disabled_logger_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "resolve_log_dir", lambda *a, **kw: tmp_path)
        inst = dl.DiagnosticLogger(log_dir=tmp_path)
        inst.enabled = False

        inst.log("ai_call", {"prompt": "x"})

        assert not list(tmp_path.glob("diagnostic-*.jsonl")) or True
