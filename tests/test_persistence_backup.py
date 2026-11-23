"""持久化层（备份 / 检查点 / 断电恢复）的无显示测试。

## 为什么值得测

`persistence_ui` 整文件被门禁 omit，但它负责的正是**用户资产保全**：
备份结构、保留策略（最近 10 份）、断电恢复判定。这里的缺陷
（例如备份清理误删、检查点状态判断反了）不会在开发机显形，
却在用户断电时造成真实损失。

Mixin 的全部方法只依赖 `current_novel_dir` / `outline` / `_log`，
假宿主即可在 CI 上完整执行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.persistence_ui import PersistenceMixin


class _Host(PersistenceMixin):
    """鸭子类型宿主：只提供 Mixin 用到的三个属性。"""

    def __init__(self, novel_dir: Path | None, outline=None):
        self.current_novel_dir = novel_dir
        self.outline = outline
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)


@pytest.fixture
def novel_dir(tmp_path: Path) -> Path:
    """预置一本「有大纲、有角色、有记忆」的小说目录。"""
    d = tmp_path / "novel"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"title": "测试书"}), encoding="utf-8")
    (d / "outline.json").write_text(json.dumps([{"title": "一"}]), encoding="utf-8")
    (d / "outlines").mkdir()
    (d / "outlines" / "overall.json").write_text(json.dumps([]), encoding="utf-8")
    (d / "characters").mkdir()
    (d / "characters" / "c1.json").write_text(json.dumps({"name": "甲"}), encoding="utf-8")
    (d / "memory").mkdir()
    (d / "memory" / "settings.json").write_text(json.dumps({"raw": "设定"}), encoding="utf-8")
    (d / "chapters").mkdir()
    return d


# ─────────────────────────── 数据入口 ───────────────────────────


class TestNovelStore:
    def test_requires_open_novel(self):
        with pytest.raises(RuntimeError, match="未打开小说"):
            _Host(None)._novel_store()

    def test_returns_store_for_open_novel(self, novel_dir):
        store = _Host(novel_dir)._novel_store()
        assert store is not None


# ─────────────────────────── 备份 ───────────────────────────


class TestBackupNovel:
    def test_no_novel_returns_none(self):
        assert _Host(None)._backup_novel() is None

    def test_copies_key_directories(self, novel_dir):
        host = _Host(novel_dir)
        backup = host._backup_novel("manual")
        assert backup is not None and backup.exists()
        assert (backup / "meta.json").exists()
        assert (backup / "outlines" / "overall.json").exists()
        assert (backup / "characters" / "c1.json").exists()
        assert (backup / "memory" / "settings.json").exists()

    def test_backup_failure_returns_none_not_raises(self, novel_dir, monkeypatch):
        import shutil as _shutil

        monkeypatch.setattr(_shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        host = _Host(novel_dir)
        assert host._backup_novel() is None
        assert any("备份失败" in m for m in host.logs)

    def test_only_ten_newest_backups_kept(self, novel_dir):
        host = _Host(novel_dir)
        # 先手工造 10 份「旧」备份（名字按时间戳递增，越后越新）
        backups = novel_dir / "backups"
        backups.mkdir()
        for i in range(10):
            (backups / f"auto_20260101_00000{i}").mkdir()
        # 再触发一次真备份 → 总数 11，应只剩 10
        host._backup_novel()
        remaining = sorted(p.name for p in backups.iterdir() if p.is_dir())
        assert len(remaining) == 10
        # 最旧的（000000）应被清掉，最新的真备份应在
        assert "auto_20260101_000000" not in remaining


# ─────────────────────────── 检查点 ───────────────────────────


class TestCheckpoint:
    def test_save_writes_checkpoint(self, novel_dir):
        host = _Host(novel_dir, outline=[{"t": 1}, {"t": 2}])
        host._save_checkpoint(7, "generating")
        cp = json.loads((novel_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert cp["chapter"] == 7
        assert cp["status"] == "generating"
        assert cp["outline_count"] == 2

    def test_save_without_novel_is_noop(self):
        _Host(None)._save_checkpoint(1)  # 不抛即通过

    def test_clear_removes_file(self, novel_dir):
        host = _Host(novel_dir)
        host._save_checkpoint(3)
        host._clear_checkpoint()
        assert not (novel_dir / "checkpoint.json").exists()

    def test_clear_missing_file_is_noop(self, novel_dir):
        _Host(novel_dir)._clear_checkpoint()  # 不抛即通过


class TestRecovery:
    def test_generating_logs_hint_and_keeps_file(self, novel_dir):
        (novel_dir / "checkpoint.json").write_text(
            json.dumps({"chapter": 12, "status": "generating", "timestamp": "t"}), encoding="utf-8"
        )
        host = _Host(novel_dir)
        host._check_recovery()
        assert any("未完成的生成任务" in m and "12" in m for m in host.logs)
        assert (novel_dir / "checkpoint.json").exists()

    def test_completed_clears_checkpoint(self, novel_dir):
        (novel_dir / "checkpoint.json").write_text(json.dumps({"chapter": 12, "status": "completed"}), encoding="utf-8")
        _Host(novel_dir)._check_recovery()
        assert not (novel_dir / "checkpoint.json").exists()

    def test_unknown_status_keeps_file_silently(self, novel_dir):
        (novel_dir / "checkpoint.json").write_text(json.dumps({"chapter": 1, "status": "weird"}), encoding="utf-8")
        host = _Host(novel_dir)
        host._check_recovery()
        assert (novel_dir / "checkpoint.json").exists()
        assert not any("未完成" in m for m in host.logs)

    def test_corrupt_checkpoint_ignored(self, novel_dir):
        (novel_dir / "checkpoint.json").write_text("{not json", encoding="utf-8")
        host = _Host(novel_dir)
        host._check_recovery()  # 不抛
        assert any("不可读" in m for m in host.logs)

    def test_no_novel_or_no_file_is_noop(self):
        _Host(None)._check_recovery()  # 不抛


# ─────────────────────────── 原子写 ───────────────────────────


class TestAtomicWrite:
    def test_delegates_and_writes(self, novel_dir, tmp_path):
        target = tmp_path / "settings.json"
        _Host(novel_dir)._atomic_write(target, '{"a": 1}')
        assert target.read_text(encoding="utf-8") == '{"a": 1}'

    def test_custom_encoding(self, tmp_path):
        target = tmp_path / "note.txt"
        _Host(None)._atomic_write(target, "中文", encoding="utf-8")
        assert target.read_text(encoding="utf-8") == "中文"
