"""app/storage.py 单元测试（第二轮优化新增）。

覆盖点：原子写语义、临时名唯一性、`.bak` 轮转、损坏回退的状态区分、
失败时临时文件清理，以及文件名消毒。
"""

import json
import threading
from pathlib import Path

import pytest

from app.storage import (
    STATUS_BACKUP,
    STATUS_CORRUPT,
    STATUS_MISSING,
    STATUS_OK,
    atomic_write_json,
    atomic_write_text,
    backup_file,
    read_json,
    read_json_with_backup,
    safe_filename,
)


def _leftover_tmp_files(directory: Path):
    return [p.name for p in directory.iterdir() if p.name.endswith(".tmp")]


class TestAtomicWriteText:
    def test_writes_exact_content(self, tmp_path):
        target = tmp_path / "a.txt"
        atomic_write_text(target, "你好\n世界")
        assert target.read_text(encoding="utf-8") == "你好\n世界"

    def test_no_tmp_left_behind(self, tmp_path):
        atomic_write_text(tmp_path / "a.txt", "x")
        assert _leftover_tmp_files(tmp_path) == []

    def test_creates_parent_directory(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "a.txt"
        atomic_write_text(target, "x")
        assert target.read_text(encoding="utf-8") == "x"

    def test_overwrites_existing_file_atomically(self, tmp_path):
        target = tmp_path / "a.txt"
        atomic_write_text(target, "old")
        atomic_write_text(target, "new")
        assert target.read_text(encoding="utf-8") == "new"

    def test_tmp_name_is_unique_per_caller(self, tmp_path):
        """同目录同 stem、仅扩展名不同的文件不得争用同一个临时名（R7）。

        旧实现用 `with_suffix('.tmp')`，`settings.json` 与 `settings.md`
        都会映射到 `settings.tmp`。这里并发写 200 次，若临时名碰撞则内容会串。
        """
        a = tmp_path / "settings.json"
        b = tmp_path / "settings.md"
        errors = []

        def writer(target, payload):
            try:
                for _ in range(100):
                    atomic_write_text(target, payload)
            except Exception as e:  # pragma: no cover - 失败时提供诊断
                errors.append(repr(e))

        t1 = threading.Thread(target=writer, args=(a, "JSON-PAYLOAD"))
        t2 = threading.Thread(target=writer, args=(b, "MD-PAYLOAD"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []
        assert a.read_text(encoding="utf-8") == "JSON-PAYLOAD"
        assert b.read_text(encoding="utf-8") == "MD-PAYLOAD"
        assert _leftover_tmp_files(tmp_path) == []

    def test_failure_cleans_tmp_and_raises(self, tmp_path):
        """写失败必须抛错且不留临时文件（不能被静默吞掉）。"""
        target = tmp_path / "occupied"
        target.mkdir()  # 目标位置被目录占用 -> os.replace 失败
        with pytest.raises(OSError):
            atomic_write_text(target, "x")
        assert _leftover_tmp_files(tmp_path) == []


class TestAtomicWriteJson:
    def test_roundtrip_utf8(self, tmp_path):
        target = tmp_path / "c.json"
        data = {"张三": {"personality": "勇敢"}}
        atomic_write_json(target, data)
        assert read_json(target) == data
        raw = target.read_text(encoding="utf-8")
        assert "张三" in raw  # ensure_ascii=False

    def test_backup_rotates_previous_content(self, tmp_path):
        target = tmp_path / "c.json"
        atomic_write_json(target, {"v": 1})
        atomic_write_json(target, {"v": 2}, backup=True)
        assert read_json(target) == {"v": 2}
        assert read_json(tmp_path / "c.json.bak") == {"v": 1}

    def test_backup_on_first_write_is_noop(self, tmp_path):
        target = tmp_path / "c.json"
        atomic_write_json(target, {"v": 1}, backup=True)
        assert not (tmp_path / "c.json.bak").exists()

    def test_backup_file_helper(self, tmp_path):
        assert backup_file(tmp_path / "missing.json") is None
        (tmp_path / "x.json").write_text("{}", encoding="utf-8")
        assert backup_file(tmp_path / "x.json") == tmp_path / "x.json.bak"
        assert (tmp_path / "x.json.bak").exists()


class TestReadJsonWithBackup:
    def test_missing_returns_default(self, tmp_path):
        data, status = read_json_with_backup(tmp_path / "nope.json", default={"d": 1})
        assert data == {"d": 1}
        assert status == STATUS_MISSING

    def test_ok(self, tmp_path):
        target = tmp_path / "c.json"
        atomic_write_json(target, {"a": 1})
        assert read_json_with_backup(target) == ({"a": 1}, STATUS_OK)

    def test_corrupt_falls_back_to_backup(self, tmp_path):
        """主文件损坏时必须回退 .bak —— 而不是当作"空"返回。"""
        target = tmp_path / "c.json"
        atomic_write_json(target, {"a": 1})
        atomic_write_json(target, {"a": 2}, backup=True)  # .bak = {"a":1}
        target.write_text('{"a": 2', encoding="utf-8")  # 截断损坏
        data, status = read_json_with_backup(target)
        assert status == STATUS_BACKUP
        assert data == {"a": 1}

    def test_corrupt_without_backup_reports_corrupt(self, tmp_path):
        target = tmp_path / "c.json"
        target.write_text("not json at all", encoding="utf-8")
        data, status = read_json_with_backup(target, default=None)
        assert data is None
        assert status == STATUS_CORRUPT

    def test_corrupt_backup_is_reported_corrupt(self, tmp_path):
        target = tmp_path / "c.json"
        target.write_text("{broken", encoding="utf-8")
        (tmp_path / "c.json.bak").write_text("{also broken", encoding="utf-8")
        data, status = read_json_with_backup(target)
        assert data is None
        assert status == STATUS_CORRUPT

    def test_read_json_raises_on_corrupt(self, tmp_path):
        target = tmp_path / "c.json"
        target.write_text("{oops", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            read_json(target)


class TestSafeFilename:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("林风", "林风"),
            ('a<b>c:d"e/f\\g|h?i*j', "a_b_c_d_e_f_g_h_i_j"),
            ("", "unnamed"),
            ("   ", "unnamed"),
        ],
    )
    def test_sanitizes(self, raw, expected):
        assert safe_filename(raw) == expected

    def test_neutralizes_traversal(self):
        assert ".." not in safe_filename("../../secret")
        # 路径分隔符与 `..` 都被中和（`/`、`\` → `_`，`..` → `_`）
        assert safe_filename("..\\..\\etc") == "____etc"
        assert safe_filename("../../secret") == "____secret"

    def test_keeps_chinese_and_parens(self):
        assert safe_filename("罗刹（真名未知）") == "罗刹（真名未知）"

    def test_used_by_character_system(self):
        """两处调用点必须共用同一实现（避免再次漂移）。"""
        from app.character_system import CharacterSystem

        assert CharacterSystem._sanitize_name("../../x") == safe_filename("../../x")


class TestNoDuplicateImplementations:
    """结构性回归：原子写必须只有一处实现。"""

    def test_persistence_ui_delegates_to_storage(self):
        src = (Path(__file__).parent.parent / "app" / "persistence_ui.py").read_text(encoding="utf-8")
        # 不应再有自建的临时文件变量与手写 replace
        assert "tmp_file" not in src
        assert "atomic_write_text" in src
        # 零调用的重复实现应已删除
        assert "_atomic_json_write" not in src

    def test_memory_manager_and_character_system_use_storage(self):
        root = Path(__file__).parent.parent / "app"
        for name in ("memory_manager.py", "character_system.py", "novel_agent.py"):
            src = (root / name).read_text(encoding="utf-8")
            assert "from app.storage import" in src or "from .storage import" in src, name
