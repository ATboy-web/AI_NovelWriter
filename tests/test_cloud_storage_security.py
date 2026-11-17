"""云存储与解压路径的安全回归测试（2026-11-17 审查新增）。

## 覆盖的修复

| 修复 | 原缺陷 | 本文件的用例 |
|---|---|---|
| `cloud_storage._transform_config` | 加密后端不可用 / 加密抛异常时**明文落盘** | `TestNoPlaintextFallback` |
| `plugin_system.safe_extract` | 只防路径穿越，**不防压缩炸弹** | `TestZipBombGuard` |

另外覆盖了这两个模块中此前**完全没有测试**的安全函数
（`_require_secure_url` / `_safe_error`）—— 它们写在代码里但从未被执行过，
等于"没人验证过它真的拦得住"。

> 已知未修复项（见审查报告）：`CloudStorageManager.download_novel()`
> 用云端返回的 `name` 直接拼本地路径，可越界写入。该问题被判定为**高危**，
> 按用户要求只报告、待确认后再改，因此这里不放会失败的用例。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.cloud_storage import (
    _ALLOWED_INSECURE_HOSTS,
    CloudStorageManager,
    _require_secure_url,
    _safe_error,
)
from app.plugin_system import (
    _MAX_EXTRACT_BYTES,
    _MAX_EXTRACT_MEMBER_BYTES,
    _MAX_EXTRACT_MEMBERS,
    safe_extract,
)

# ====================================================================== 端点校验


class TestRequireSecureUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://dav.jianguoyun.com/dav/",
            "https://api.aliyundrive.com/v2",
            "http://localhost:8080/dav",
            "http://127.0.0.1:9000",
            "",
        ],
    )
    def test_allowed(self, url):
        assert _require_secure_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "http://dav.jianguoyun.com/dav/",
            "http://192.168.1.10/dav",
            "http://evil.example.com",
        ],
    )
    def test_plain_http_rejected(self, url):
        with pytest.raises(ValueError, match="明文 HTTP"):
            _require_secure_url(url)

    @pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"])
    def test_bad_scheme_rejected(self, url):
        with pytest.raises(ValueError, match="协议非法"):
            _require_secure_url(url)

    def test_loopback_allowlist_contents(self):
        """白名单只应包含真正的回环地址（防止以后被人加进内网段）。"""
        assert _ALLOWED_INSECURE_HOSTS == frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


# ====================================================================== 错误脱敏


class TestSafeError:
    def test_known_secret_replaced(self):
        # 凭据只有在**真的出现在错误文本里**时才需要替换 —— 这正是该函数的目的
        text = _safe_error("失败", RuntimeError("boom SECRET-TOKEN boom"), "SECRET-TOKEN")
        assert "SECRET-TOKEN" not in text
        assert "***" in text

    def test_secret_absent_from_text_leaves_text_intact(self):
        assert _safe_error("失败", RuntimeError("boom"), "SECRET-TOKEN") == "失败: boom"

    def test_query_string_token_redacted(self):
        text = _safe_error("失败", RuntimeError("https://pan.baidu.com/x?access_token=abc123&path=/a"))
        assert "abc123" not in text
        assert "access_token=***" in text

    def test_multiple_sensitive_keys(self):
        raw = "api_key=kkk password=ppp secret=sss refresh_token=rrr"
        text = _safe_error("失败", RuntimeError(raw))
        for secret in ("kkk", "ppp", "sss", "rrr"):
            assert secret not in text

    def test_empty_secret_not_crashing(self):
        assert "失败" in _safe_error("失败", RuntimeError("x"), "", None)


# ====================================================================== 不得明文落盘


class TestNoPlaintextFallback:
    """🔴 本轮修复的核心：任何失败路径都不得把凭据写成明文。"""

    @pytest.fixture()
    def manager(self, tmp_path: Path) -> CloudStorageManager:
        return CloudStorageManager(config_file=tmp_path / "cloud.json")

    def test_no_backend_blanks_credentials(self, manager, tmp_path: Path):
        manager._secure_config = None  # 模拟加密组件不可用
        manager.configure_provider("baidu", {"access_token": "SECRET-TOKEN-123456"})
        raw = (tmp_path / "cloud.json").read_text(encoding="utf-8")
        assert "SECRET-TOKEN-123456" not in raw, "加密不可用时不得明文落盘"
        assert '"access_token": ""' in raw

    def test_no_backend_blanks_nested_provider(self, manager, tmp_path: Path):
        manager._secure_config = None
        manager.config["webdav"] = {"url": "https://x", "password": "P@ssw0rd!", "username": "u"}
        manager._save_config()
        raw = (tmp_path / "cloud.json").read_text(encoding="utf-8")
        assert "P@ssw0rd!" not in raw
        assert "https://x" in raw  # 非敏感字段照常保存
        assert "u" in raw

    def test_encrypt_exception_blanks_field(self, manager, tmp_path: Path):
        class BrokenSecure:
            def _encrypt(self, value):
                raise RuntimeError("密钥损坏")

            def _decrypt(self, value):
                raise RuntimeError("密钥损坏")

        manager._secure_config = BrokenSecure()
        manager.config["webdav"] = {"password": "SHOULD-NOT-LEAK"}
        manager._save_config()
        raw = (tmp_path / "cloud.json").read_text(encoding="utf-8")
        assert "SHOULD-NOT-LEAK" not in raw

    def test_decrypt_failure_yields_empty_not_ciphertext(self, manager):
        class BrokenSecure:
            def _encrypt(self, value):
                raise RuntimeError("x")

            def _decrypt(self, value):
                raise RuntimeError("x")

        manager._secure_config = BrokenSecure()
        out = manager._transform_config({"baidu": {"access_token": "gAAAAAxxx"}}, decrypt=True)
        assert out["baidu"]["access_token"] == ""

    def test_blank_sensitive_does_not_mutate_input(self, manager):
        original = {"baidu": {"access_token": "abc", "app": "keep"}}
        blanked = manager._blank_sensitive(original)
        assert original["baidu"]["access_token"] == "abc"
        assert blanked["baidu"]["access_token"] == ""
        assert blanked["baidu"]["app"] == "keep"


# ====================================================================== 压缩炸弹


class TestZipBombGuard:
    def _zip(self, path: Path, entries: dict[str, bytes]) -> Path:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return path

    def test_normal_zip_extracts(self, tmp_path: Path):
        archive = self._zip(tmp_path / "ok.zip", {"SKILL.md": b"---\nname: x\n---\n", "a/b.txt": b"hi"})
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf:
            safe_extract(zf, dest)
        assert (dest / "SKILL.md").is_file()
        assert (dest / "a" / "b.txt").is_file()

    def test_zip_slip_still_rejected(self, tmp_path: Path):
        archive = self._zip(tmp_path / "slip.zip", {"../../evil.txt": b"x"})
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="不安全的 ZIP 路径"):
            safe_extract(zf, dest)
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_single_member_too_large(self, tmp_path: Path, monkeypatch):
        import app.plugin_system as ps

        monkeypatch.setattr(ps, "_MAX_EXTRACT_MEMBER_BYTES", 10)
        archive = self._zip(tmp_path / "big.zip", {"big.bin": b"x" * 100})
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="单个文件过大"):
            safe_extract(zf, dest)

    def test_total_too_large(self, tmp_path: Path, monkeypatch):
        import app.plugin_system as ps

        monkeypatch.setattr(ps, "_MAX_EXTRACT_MEMBER_BYTES", 10_000)
        monkeypatch.setattr(ps, "_MAX_EXTRACT_BYTES", 50)
        archive = self._zip(tmp_path / "sum.zip", {"a.bin": b"x" * 40, "b.bin": b"y" * 40})
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="压缩炸弹"):
            safe_extract(zf, dest)

    def test_too_many_members(self, tmp_path: Path, monkeypatch):
        import app.plugin_system as ps

        monkeypatch.setattr(ps, "_MAX_EXTRACT_MEMBERS", 3)
        archive = self._zip(tmp_path / "many.zip", {f"f{i}.txt": b"x" for i in range(5)})
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="成员过多"):
            safe_extract(zf, dest)

    def test_limits_are_sane(self):
        """上限本身要合理：太小会误伤正常技能包（含 1.5 MB 截图）。"""
        assert _MAX_EXTRACT_BYTES >= 100 * 1024 * 1024
        assert _MAX_EXTRACT_MEMBER_BYTES <= _MAX_EXTRACT_BYTES
        assert _MAX_EXTRACT_MEMBERS >= 1000
