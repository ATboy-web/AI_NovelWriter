"""`cloud_storage` 的越界防护与降级（第 1 档：同步可能覆盖本地）。

## 为什么先测这一层

云端返回的**文件名是不可信输入**：恶意 WebDAV、被入侵的网盘账号、代理篡改响应
都能构造 `../../x`。旧实现直接 `local_dir / name`，实测可覆盖任意可写文件。

`_safe_local_target` 是"下载不得越界"的**唯一强制点**，所以它的每条拒绝分支
都值得钉死 —— 这类漏洞一旦回归，是**静默**的：下载"成功"了，只是文件落到了别处。

## 覆盖范围

- `_safe_local_target` 的全部拒绝分支（穿越、空名、保留设备名、符号链接逃逸）
- `download_novel` 跳过可疑条目的行为（**记录失败而不是静默忽略**）
- 清单写盘失败不影响同步、provider 未连接时的返回值
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cloud_storage import CloudStorageManager, _safe_local_target


class TestSafeLocalTarget:
    """把"云端给的名字"变成"base 之内的本地路径"。"""

    def test_plain_name(self, tmp_path):
        assert _safe_local_target(tmp_path, "chapter_1.txt") == (tmp_path / "chapter_1.txt").resolve()

    @pytest.mark.parametrize(
        "name",
        [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\x.dll",
            "sub/dir/file.txt",
        ],
    )
    def test_traversal_is_collapsed_to_leaf(self, tmp_path, name):
        """无论远端给多深的路径，只取最后一段 —— 目录结构由调用方决定。"""
        result = _safe_local_target(tmp_path, name)

        assert result is not None
        assert result.parent == tmp_path.resolve(), f"{name} 逃出了 base"

    @pytest.mark.parametrize("name", ["", "   ", None, ".", "..", "./", "../", "/"])
    def test_empty_and_dot_names_rejected(self, tmp_path, name):
        assert _safe_local_target(tmp_path, name) is None

    @pytest.mark.parametrize("name", ["CON", "NUL", "COM1", "con.txt", "LPT9"])
    def test_windows_reserved_names_rejected(self, tmp_path, name):
        """Windows 保留设备名会被系统拒绝创建 —— 提前挡掉，别等到 IO 报错。"""
        assert _safe_local_target(tmp_path, name) is None

    def test_normal_names_with_reserved_prefix_allowed(self, tmp_path):
        """`CONSOLE.txt` 不是保留名，不能误杀。"""
        assert _safe_local_target(tmp_path, "CONSOLE.txt") is not None

    def test_symlink_escape_rejected(self, tmp_path):
        """软链接把子目录指向 base 之外时必须拒绝（`resolve()` 后二次校验）。"""
        base = tmp_path / "base"
        outside = tmp_path / "outside"
        base.mkdir()
        outside.mkdir()
        (outside / "secret.txt").write_text("x", encoding="utf-8")
        # 在 base 里建一个指向 outside 的软链接"文件"
        link = base / "偷渡.txt"
        try:
            link.symlink_to(outside / "secret.txt")
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不支持创建符号链接")

        result = _safe_local_target(base, "偷渡.txt")

        assert result is None, "符号链接逃出了 base"

    def test_resolve_error_rejected(self, tmp_path, monkeypatch):
        """`resolve()` 抛错（路径过长/权限）时返回 None，不能把异常抛给下载循环。"""

        def boom(self, *a, **kw):
            raise OSError("路径解析失败")

        monkeypatch.setattr(Path, "resolve", boom)

        assert _safe_local_target(tmp_path, "x.txt") is None


class FakeProvider:
    """够用的云盘替身：只实现下载流程用到的方法。"""

    def __init__(self, files):
        self.connected = True
        self.supports_recursive_listing = False
        self._files = files  # [(name, is_dir), ...]
        self.downloaded: list[Path] = []

    def list_files(self, path):
        return [{"name": n, "dir": d} for n, d in self._files]

    def file_name(self, info):
        return info["name"]

    def is_dir(self, info):
        return info["dir"]

    def download(self, remote, local_target):
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_text("内容", encoding="utf-8")
        self.downloaded.append(local_target)
        return True


@pytest.fixture
def manager(tmp_path):
    return CloudStorageManager(config_file=tmp_path / "cloud.json")


class TestDownloadGuards:
    def test_normal_files_are_downloaded(self, tmp_path, manager):
        provider = FakeProvider([("a.txt", False), ("b.txt", False)])
        manager.providers["fake"] = provider
        base = tmp_path / "book"

        ok = manager.download_novel("/remote", base, "fake")

        assert ok is True
        assert sorted(p.name for p in base.glob("*.txt")) == ["a.txt", "b.txt"]

    def test_suspicious_names_are_skipped_and_reported(self, tmp_path, manager):
        """🔴 可疑名字要**跳过并记录失败** —— 静默忽略会让"同步成功"变成谎报。"""
        provider = FakeProvider([("好文件.txt", False), ("CON", False), ("", False)])
        manager.providers["fake"] = provider
        base = tmp_path / "book"

        ok = manager.download_novel("/remote", base, "fake")

        assert ok is False, "有文件被跳过却报成功"
        assert [p.name for p in base.glob("*.txt")] == ["好文件.txt"]

    def test_traversal_name_lands_inside_base(self, tmp_path, manager):
        provider = FakeProvider([("../../逃逸.txt", False)])
        manager.providers["fake"] = provider
        base = tmp_path / "book"

        manager.download_novel("/remote", base, "fake")

        escaped = list(tmp_path.glob("逃逸.txt"))
        assert not escaped, "文件被写到了作品目录之外"
        assert (base / "逃逸.txt").exists(), "应当降级为 base 内的同名文件"

    def test_unknown_provider_returns_false(self, tmp_path, manager):
        assert manager.download_novel("/remote", tmp_path / "book", "不存在") is False


class TestManifest:
    def test_missing_manifest_returns_empty(self, tmp_path, manager):
        assert manager._load_manifest(tmp_path) == {}

    def test_corrupt_manifest_returns_empty(self, tmp_path, manager):
        (tmp_path / manager._MANIFEST_NAME).write_text("{ 坏", encoding="utf-8")

        assert manager._load_manifest(tmp_path) == {}

    def test_non_dict_manifest_returns_empty(self, tmp_path, manager):
        (tmp_path / manager._MANIFEST_NAME).write_text("[]", encoding="utf-8")

        assert manager._load_manifest(tmp_path) == {}

    def test_save_manifest_failure_is_logged_not_raised(self, tmp_path, manager, monkeypatch):
        """清单只是加速用的缓存 —— 写失败不能影响本次同步。"""
        import app.cloud_storage as mod

        def boom(*_a, **_kw):
            raise OSError("只读")

        monkeypatch.setattr(mod, "atomic_write_json", boom)

        manager._save_manifest(tmp_path, {"a": {"size": 1}})  # 不抛即通过

    def test_save_then_load_roundtrip(self, tmp_path, manager):
        manager._save_manifest(tmp_path, {"a.txt": {"size": 3, "mtime": 1.0}})

        assert manager._load_manifest(tmp_path)["a.txt"]["size"] == 3


class TestSyncGuards:
    def test_sync_without_provider_returns_false(self, tmp_path, manager):
        assert manager.sync_novel(tmp_path, "不存在") is False

    def test_sync_with_disconnected_provider_returns_false(self, tmp_path, manager):
        provider = FakeProvider([])
        provider.connected = False
        manager.providers["fake"] = provider

        assert manager.sync_novel(tmp_path, "fake") is False
