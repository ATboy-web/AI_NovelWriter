"""`app/storage.py` 的分支回归（原子写是所有落盘的地基）。

## 为什么值得补

`storage` 是**唯一**的原子写实现，角色档案、章节、配置、备份全走它。
它出错的方式是「文件没了」或「备份也坏了」—— 用户丢的是稿子。

此前 22 行分支没跑过，集中在四类：

| 分支 | 没覆盖的风险 |
|---|---|
| Windows 保留名 / 超长名哈希 | 写进去的文件名打不开，或两个不同名字截成同一个 |
| `chmod` / `unlink` 失败被忽略 | 次要步骤失败把整次写入带崩 |
| `backup_file` 的清理与 `validate` | 主文件已损坏时把损坏内容复制成 `.bak`，毁掉最后可用备份 |
| `archive_corrupt_file` / `read_json_object` 的兜底 | 启动时因为一个坏文件直接失败 |

## 判据原则

这里验的多是**失败路径**：不是"能写成功"，而是"失败时不留下更坏的局面"
（半截临时文件、被覆盖的好备份、被吞掉的异常）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.storage as storage
from app.storage import (
    STATUS_BACKUP,
    STATUS_MISSING,
    archive_corrupt_file,
    atomic_write_text,
    backup_file,
    read_json_object,
    read_json_with_backup,
    safe_filename,
)


class TestSafeFilenameEdgeCases:
    """文件名消毒的边角：跑在 Windows 上"名字合法"比"内容正确"更基础。"""

    @pytest.mark.parametrize("reserved", ["CON", "con", "NUL", "nul", "COM1", "LPT9", "AUX", "PRN"])
    def test_windows_reserved_names_are_prefixed(self, reserved):
        """`CON`/`NUL`/`COM1` 这类名字在 Windows 上**无法创建**，必须加前缀。"""
        assert safe_filename(reserved).startswith("_")

    def test_reserved_with_extension_still_prefixed(self):
        """`CON.txt` 同样被 Windows 拒绝 —— 判定看第一个点之前的部分。"""
        assert safe_filename("CON.txt").startswith("_")

    def test_non_reserved_lookalike_is_untouched(self):
        """`CONSOLE` 不是保留名，不能误加前缀。"""
        assert safe_filename("CONSOLE") == "CONSOLE"

    def test_long_name_is_truncated_with_hash(self):
        """超长名不能直接砍尾 —— 那样两个不同名字会撞成同一个文件。"""
        name = "角" * 200
        result = safe_filename(name)

        assert len(result) <= 120
        assert "_" in result

    def test_different_long_names_do_not_collide(self):
        a = safe_filename("甲" * 200 + "A")
        b = safe_filename("甲" * 200 + "B")

        assert a != b, "超长名截断后撞车了 —— 一个角色会覆盖另一个"

    def test_same_long_name_is_stable(self):
        """同样的名字每次要得到同样的结果（否则读不回自己写的文件）。"""
        assert safe_filename("乙" * 200) == safe_filename("乙" * 200)

    def test_empty_after_cleaning_becomes_unnamed(self):
        """清洗后为空才回落 `unnamed`。

        注意 `...` **不**为空：`..` 会先被替换成 `_`（目录穿越防护），
        于是 `...` → `_.` → 去尾点 → `_`。这个顺序是刻意的，
        把 `..` 当作非法序列而不是多余的点。
        """
        assert safe_filename("   ") == "unnamed"
        assert safe_filename("") == "unnamed"
        assert safe_filename(chr(0) + chr(1)) == "unnamed"
        assert safe_filename("...") == "_"


class TestAtomicWriteFailurePaths:
    def test_chmod_failure_is_ignored(self, tmp_path, monkeypatch):
        """`chmod` 失败只记日志 —— Windows 上本来就不保证权限位，
        为它把整次写入判失败毫无意义（文件其实已经写好了）。"""

        def boom(*_a, **_kw):
            raise OSError("chmod 不支持")

        monkeypatch.setattr(storage.os, "chmod", boom)
        target = tmp_path / "a.txt"

        # 只有传了 mode 才会调 chmod —— 不传的话这条分支根本走不到
        atomic_write_text(target, "内容", mode=0o644)
        assert target.read_text(encoding="utf-8") == "内容"

    def test_unlink_failure_does_not_mask_original_error(self, tmp_path, monkeypatch):
        """清理临时文件失败时，**原异常仍要抛出** ——
        否则真正的错误被 `unlink` 的 OSError 顶替，排查会走偏。"""
        target = tmp_path / "occupied"
        target.mkdir()  # os.replace 到目录上会失败

        real_unlink = Path.unlink

        def broken_unlink(self, *a, **kw):
            if str(self).endswith(".tmp") or ".tmp" in self.name:
                raise OSError("不允许删除")
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", broken_unlink)

        with pytest.raises(OSError) as exc_info:
            atomic_write_text(target, "x")

        assert "不允许删除" not in str(exc_info.value), "原异常被清理失败顶替了"


class TestBackupFilePaths:
    def test_missing_source_returns_none(self, tmp_path):
        assert backup_file(tmp_path / "nope.json") is None

    def test_directory_source_returns_none(self, tmp_path):
        """目录不是文件 —— 不能拿 `copy2` 去撞。"""
        (tmp_path / "adir").mkdir()
        assert backup_file(tmp_path / "adir") is None

    def test_invalid_json_is_not_rotated_when_validated(self, tmp_path):
        """🔴 `validate=True` 时，损坏的主文件**不能**被轮转成 `.bak`。

        否则「主文件坏了」的场景会把损坏内容复制成备份，
        把最后一份可用备份一起毁掉 —— 损坏回退彻底失效。
        """
        good_bak = tmp_path / "data.json.bak"
        good_bak.write_text(json.dumps({"ok": True}), encoding="utf-8")
        bad_main = tmp_path / "data.json"
        bad_main.write_text("{ 坏掉的 JSON", encoding="utf-8")

        assert backup_file(bad_main, validate=True) is None
        assert json.loads(good_bak.read_text(encoding="utf-8")) == {"ok": True}, "好备份被覆盖了"

    def test_valid_json_is_rotated(self, tmp_path):
        main = tmp_path / "data.json"
        main.write_text(json.dumps({"v": 1}), encoding="utf-8")

        dst = backup_file(main, validate=True)

        assert dst is not None and dst.exists()
        assert json.loads(dst.read_text(encoding="utf-8")) == {"v": 1}

    def test_backup_cleanup_failure_is_logged(self, tmp_path, monkeypatch):
        """备份失败时清理临时文件；清理再失败也只记日志，原异常仍抛出。"""
        src = tmp_path / "data.json"
        src.write_text("{}", encoding="utf-8")

        def boom_copy(*_a, **_kw):
            raise OSError("复制失败")

        real_unlink = Path.unlink

        def broken_unlink(self, *a, **kw):
            if self.name.endswith(".tmp"):
                raise OSError("不允许删除")
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(storage.shutil, "copy2", boom_copy)
        monkeypatch.setattr(Path, "unlink", broken_unlink)

        with pytest.raises(OSError) as exc_info:
            backup_file(src)

        assert "复制失败" in str(exc_info.value), "原异常被清理失败顶替了"


class TestReadJsonObject:
    """`read_json_object` 契约：**绝不抛异常**，只返回 dict 或 None。"""

    def test_missing_file_returns_none(self, tmp_path):
        assert read_json_object(tmp_path / "nope.json") is None

    def test_corrupt_file_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ 不是合法 JSON", encoding="utf-8")

        assert read_json_object(p) is None

    def test_non_object_root_returns_none(self, tmp_path):
        """根节点是数组/字符串时也返回 None —— 调用方只认 dict。"""
        for i, payload in enumerate(["[]", '"text"', "42", "null"]):
            p = tmp_path / f"root{i}.json"
            p.write_text(payload, encoding="utf-8")
            assert read_json_object(p) is None, payload

    def test_valid_object_returns_dict(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")

        assert read_json_object(p) == {"a": 1}

    def test_permission_error_returns_none(self, tmp_path, monkeypatch):
        """读盘权限错误也要吞掉 —— 配置读取失败不该阻断启动。"""
        p = tmp_path / "ok.json"
        p.write_text("{}", encoding="utf-8")

        def boom(*_a, **_kw):
            raise PermissionError("拒绝访问")

        monkeypatch.setattr(storage, "read_json", boom)
        assert read_json_object(p) is None


class TestArchiveCorruptFile:
    def test_missing_source_returns_none(self, tmp_path):
        assert archive_corrupt_file(tmp_path / "nope.json") is None

    def test_archives_with_timestamp(self, tmp_path):
        src = tmp_path / "data.json"
        src.write_text("{坏", encoding="utf-8")

        dst = archive_corrupt_file(src)

        assert dst is not None
        assert ".corrupt-" in dst.name
        assert dst.read_text(encoding="utf-8") == "{坏"
        assert src.exists(), "留档是复制而不是改名 —— 原文件必须还在"

    def test_multiple_archives_do_not_overwrite(self, tmp_path):
        """同一秒内多次留档要加序号，不能互相覆盖。"""
        src = tmp_path / "data.json"
        src.write_text("{坏", encoding="utf-8")

        first = archive_corrupt_file(src)
        second = archive_corrupt_file(src)

        assert first != second
        assert first.exists() and second.exists()

    def test_write_failure_returns_none(self, tmp_path, monkeypatch):
        """留档是尽力而为 —— 失败返回 None，不能反过来阻断启动。"""
        src = tmp_path / "data.json"
        src.write_text("{坏", encoding="utf-8")

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(Path, "write_bytes", boom)
        assert archive_corrupt_file(src) is None


class TestReadJsonWithBackupFallbacks:
    def test_missing_main_with_valid_backup(self, tmp_path):
        """主文件不在但 `.bak` 可用 ⇒ 状态是 BACKUP，不是 MISSING。

        这个区分很重要：MISSING 意味着"全新作品"，BACKUP 意味着"上次写盘出了事"。
        """
        bak = tmp_path / "data.json.bak"
        bak.write_text(json.dumps({"v": 2}), encoding="utf-8")

        data, status = read_json_with_backup(tmp_path / "data.json")

        assert data == {"v": 2}
        assert status == STATUS_BACKUP

    def test_missing_main_with_corrupt_backup(self, tmp_path):
        """备份也坏 ⇒ 回报 MISSING（无可用数据），而不是抛异常。"""
        bak = tmp_path / "data.json.bak"
        bak.write_text("{ 坏了", encoding="utf-8")

        data, status = read_json_with_backup(tmp_path / "data.json", default={"d": 1})

        assert data == {"d": 1}
        assert status == STATUS_MISSING

    def test_nothing_exists_returns_default(self, tmp_path):
        data, status = read_json_with_backup(tmp_path / "data.json", default=None)

        assert data is None
        assert status == STATUS_MISSING
