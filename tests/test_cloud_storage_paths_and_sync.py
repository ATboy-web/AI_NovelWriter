"""云存储：路径穿越、配置健壮性、厂商差异与增量同步（2026-11-17 修复回归）。

本文件覆盖审查报告中的 H-1 / M-3 / M-4 / M-5 / M-6 / M-7 / M-8，
与 `test_cloud_storage_security.py`（凭据明文、ZIP 炸弹、端点协议）互补。

设计原则：**不联网**。所有厂商交互都用内存假对象替代，
断言的是"我们怎么处理对方返回的数据"，而不是对方服务是否可用。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.cloud_storage import (
    AliyunPanProvider,
    BaiduPanProvider,
    CloudProvider,
    CloudStorageManager,
    QuarkPanProvider,
    WebDAVProvider,
    XunleiPanProvider,
    _safe_local_target,
)

# ====================================================================== 假 Provider


class FakeProvider(CloudProvider):
    """可编程的内存 Provider：列什么、传什么都由测试决定。"""

    supports_recursive_listing = False

    def __init__(self, tree=None, fail_upload=False):
        super().__init__({})
        self.name = "fake"
        self.connected = True
        self.tree = tree or {}
        self.uploads = []
        self.downloads = []
        self.fail_upload = fail_upload

    def connect(self) -> bool:
        return True

    def upload(self, local_path: Path, remote_path: str) -> bool:
        self.uploads.append(remote_path)
        return not self.fail_upload

    def download(self, remote_path: str, local_path: Path) -> bool:
        self.downloads.append((remote_path, str(local_path)))
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("x", encoding="utf-8")
        return True

    def list_files(self, remote_path: str = "/"):
        return self.tree.get(remote_path.rstrip("/") or "/", [])

    def delete_file(self, remote_path: str) -> bool:
        return True

    def create_folder(self, remote_path: str) -> bool:
        return True


class RecursiveFakeProvider(FakeProvider):
    supports_recursive_listing = True


# ====================================================================== H-1 路径穿越


class TestDownloadPathTraversal:
    """🔴 高危 H-1：云端返回的文件名一律不可信。"""

    @pytest.mark.parametrize(
        "evil",
        ["../../victim.txt", "..\\..\\victim.txt", "/etc/passwd", "a/../../b.txt", "sub/../../x"],
    )
    def test_traversal_name_is_confined(self, tmp_path: Path, evil: str):
        base = tmp_path / "novel"
        base.mkdir()
        target = _safe_local_target(base, evil)
        assert target is not None
        assert target.parent == base.resolve(), evil

    @pytest.mark.parametrize("name", ["", "   ", ".", ".."])
    def test_empty_and_dot_rejected(self, tmp_path: Path, name: str):
        assert _safe_local_target(tmp_path, name) is None

    @pytest.mark.parametrize("name", ["CON", "NUL", "COM1", "LPT9", "con.txt", "NUL.tar.gz"])
    def test_windows_reserved_names_rejected(self, tmp_path: Path, name: str):
        assert _safe_local_target(tmp_path, name) is None

    def test_normal_names_pass(self, tmp_path: Path):
        assert _safe_local_target(tmp_path, "第一章.txt") == (tmp_path.resolve() / "第一章.txt")
        # 远端路径只取最后一段：目录结构由调用方的递归决定
        assert _safe_local_target(tmp_path, "sub/name.md") == (tmp_path.resolve() / "name.md")

    def test_download_does_not_escape(self, tmp_path: Path):
        """端到端复现原始 PoC：目录外文件必须保持原样。"""
        novel = tmp_path / "novels" / "mine"
        novel.mkdir(parents=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("原始内容", encoding="utf-8")

        provider = FakeProvider(tree={"/remote": [{"name": "../../victim.txt", "isdir": False, "size": 3}]})
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        manager.providers["fake"] = provider

        manager.download_novel("/remote", novel, "fake")
        assert victim.read_text(encoding="utf-8") == "原始内容"

    def test_nested_dirs_stay_inside(self, tmp_path: Path):
        novel = tmp_path / "novel"
        novel.mkdir()
        provider = FakeProvider(
            tree={
                "/r": [{"name": "chapters", "isdir": True}],
                "/r/chapters": [{"name": "002.md", "isdir": False, "size": 1}],
            }
        )
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        manager.providers["fake"] = provider
        assert manager.download_novel("/r", novel, "fake")
        assert (novel / "chapters" / "002.md").is_file()

    def test_recursion_depth_is_capped(self, tmp_path: Path):
        """自引用目录不能让下载无限递归。"""
        novel = tmp_path / "novel"
        novel.mkdir()

        class LoopProvider(FakeProvider):
            def list_files(self, remote_path: str = "/"):
                return [{"name": "loop", "isdir": True}]

        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        manager.providers["fake"] = LoopProvider()
        manager.download_novel("/r", novel, "fake")  # 不抛、不挂
        assert novel.exists()


# ====================================================================== M-3 配置损坏


class TestCorruptConfig:
    def test_corrupt_json_does_not_raise(self, tmp_path: Path):
        cfg = tmp_path / "cloud_config.json"
        cfg.write_text('{"webdav": {', encoding="utf-8")
        manager = CloudStorageManager(config_file=cfg)
        assert manager.config == {}
        archived = list(tmp_path.glob("cloud_config.corrupt-*.json"))
        assert archived and archived[0].read_text(encoding="utf-8") == '{"webdav": {'

    def test_non_object_root_does_not_raise(self, tmp_path: Path):
        cfg = tmp_path / "cloud_config.json"
        cfg.write_text("[1, 2, 3]", encoding="utf-8")
        assert CloudStorageManager(config_file=cfg).config == {}

    def test_missing_file_is_fine(self, tmp_path: Path):
        assert CloudStorageManager(config_file=tmp_path / "nope.json").config == {}


# ====================================================================== M-4 原子写


class TestAtomicConfigSave:
    def test_saves_valid_json_without_temp_leftovers(self, tmp_path: Path):
        cfg = tmp_path / "cloud_config.json"
        manager = CloudStorageManager(config_file=cfg)
        manager._secure_config = None  # 加密不可用 → 凭据写空，但不崩
        assert manager.configure_provider("baidu", {"access_token": ""})
        assert json.loads(cfg.read_text(encoding="utf-8"))["baidu"]["access_token"] == ""
        assert not list(tmp_path.glob("*.tmp*"))

    def test_write_failure_keeps_original(self, tmp_path: Path, monkeypatch):
        cfg = tmp_path / "cloud_config.json"
        cfg.write_text('{"keep": 1}', encoding="utf-8")
        manager = CloudStorageManager(config_file=cfg)
        manager._secure_config = None

        def boom(*_a, **_k):
            raise OSError("磁盘满了")

        monkeypatch.setattr("app.cloud_storage.atomic_write_json", boom)
        assert manager.configure_provider("baidu", {"access_token": ""}) is False
        assert json.loads(cfg.read_text(encoding="utf-8")) == {"keep": 1}


# ====================================================================== M-7 PROPFIND


PROPFIND_XML = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/dav/</D:href>
    <D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/dav/chapters/</D:href>
    <D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/dav/%E7%AC%AC%E4%B8%80%E7%AB%A0.txt</D:href>
    <D:propstat><D:prop><D:getcontentlength>1234</D:getcontentlength></D:prop></D:propstat>
  </D:response>
</D:multistatus>
"""


class TestWebDavPropfind:
    def test_parses_entries_and_skips_self(self):
        items = WebDAVProvider.parse_propfind(PROPFIND_XML, "/dav/")
        names = [i["name"] for i in items]
        assert "chapters" in names
        assert "第一章.txt" in names  # 百分号已解码
        assert all(n != "" for n in names)

    def test_marks_directories_and_sizes(self):
        items = {i["name"]: i for i in WebDAVProvider.parse_propfind(PROPFIND_XML, "/dav/")}
        assert items["chapters"]["isdir"] is True
        assert items["第一章.txt"]["isdir"] is False
        assert items["第一章.txt"]["size"] == 1234

    def test_bad_xml_returns_empty(self):
        assert WebDAVProvider.parse_propfind("<not xml", "/dav/") == []

    def test_list_files_uses_parser(self):
        """`list_files` 必须真的把响应交给解析器（旧实现固定 return []）。"""
        calls = {}

        class FakeClient:
            def request(self, method, path, headers=None):
                calls["method"] = method

                class R:
                    status_code = 207
                    text = PROPFIND_XML

                return R()

        provider = WebDAVProvider({"url": "https://x"})
        provider.client = FakeClient()
        items = provider.list_files("/dav/")
        assert calls["method"] == "PROPFIND"
        assert len(items) == 2


# ====================================================================== M-8 目录字段


class TestProviderDirDetection:
    @pytest.mark.parametrize(
        "provider,sample_dir,sample_file",
        [
            (BaiduPanProvider, {"isdir": 1, "server_filename": "d"}, {"isdir": 0, "server_filename": "f"}),
            (QuarkPanProvider, {"file_type": 1, "file_name": "d"}, {"file_type": 0, "file_name": "f"}),
            (XunleiPanProvider, {"kind": "drive#folder", "name": "d"}, {"kind": "drive#file", "name": "f"}),
            (AliyunPanProvider, {"type": "folder", "name": "d"}, {"type": "file", "name": "f"}),
            (WebDAVProvider, {"isdir": True, "name": "d"}, {"isdir": False, "name": "f"}),
        ],
    )
    def test_is_dir_per_vendor(self, provider, sample_dir, sample_file):
        instance = provider({"access_token": "", "cookie": "", "url": ""})
        assert instance.is_dir(sample_dir) is True
        assert instance.is_dir(sample_file) is False

    @pytest.mark.parametrize(
        "provider,sample,expected",
        [
            (BaiduPanProvider, {"server_filename": "书.txt"}, "书.txt"),
            (QuarkPanProvider, {"file_name": "书.txt"}, "书.txt"),
            (AliyunPanProvider, {"name": "书.txt"}, "书.txt"),
            (XunleiPanProvider, {"name": "书.txt"}, "书.txt"),
        ],
    )
    def test_file_name_per_vendor(self, provider, sample, expected):
        assert provider({"access_token": "", "cookie": "", "url": ""}).file_name(sample) == expected


# ====================================================================== M-5 百度分片


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = {}
        self.text = ""

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self):
        self.posts = []

    def post(self, url, params=None, json=None, content=None):  # noqa: A002 - 对齐 httpx 签名
        self.posts.append({"params": params or {}, "json": json, "len": len(content or b"")})
        if (params or {}).get("method") == "upload":
            return _FakeResponse(200, {"uploadid": "U1"})
        return _FakeResponse(200, {})


class TestBaiduChunkedUpload:
    def test_upload_splits_into_4mb_chunks(self, tmp_path: Path):
        size = 9 * 1024 * 1024  # 9 MB → 4 + 4 + 1
        source = tmp_path / "big.bin"
        source.write_bytes(b"a" * size)

        provider = BaiduPanProvider({"access_token": "T"})
        client = _FakeHTTPClient()
        provider.client = client

        assert provider.upload(source, "/novel/big.bin") is True

        parts = [p for p in client.posts if p["params"].get("type") == "tmpfile"]
        assert len(parts) == 3
        assert [p["params"]["partseq"] for p in parts] == [0, 1, 2]
        assert [p["len"] for p in parts] == [4 * 1024 * 1024, 4 * 1024 * 1024, 1024 * 1024]

        creates = [p for p in client.posts if p["params"].get("method") == "createsuperfile"]
        block_list = json.loads(creates[0]["json"]["block_list"])
        payload = source.read_bytes()
        expected = [
            hashlib.md5(payload[: 4 * 1024 * 1024]).hexdigest(),
            hashlib.md5(payload[4 * 1024 * 1024 : 8 * 1024 * 1024]).hexdigest(),
            hashlib.md5(payload[8 * 1024 * 1024 :]).hexdigest(),
        ]
        assert block_list == expected

    def test_empty_file_is_rejected_not_crashed(self, tmp_path: Path):
        source = tmp_path / "empty.bin"
        source.write_bytes(b"")
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = _FakeHTTPClient()
        assert provider.upload(source, "/x") is False


# ====================================================================== M-6 增量同步


class TestIncrementalSync:
    def _novel(self, tmp_path: Path) -> Path:
        novel = tmp_path / "novel"
        (novel / "chapters").mkdir(parents=True)
        (novel / "chapters" / "001.txt").write_text("a", encoding="utf-8")
        (novel / "meta.json").write_text("{}", encoding="utf-8")
        return novel

    def test_second_sync_uploads_nothing_with_manifest(self, tmp_path: Path):
        novel = self._novel(tmp_path)
        provider = FakeProvider()  # 非递归 ⇒ 走本地清单
        manager = CloudStorageManager(config_file=tmp_path / "c.json")
        manager.providers["fake"] = provider

        assert manager.sync_novel(novel, "fake")
        assert len(provider.uploads) == 2, provider.uploads

        provider.uploads.clear()
        assert manager.sync_novel(novel, "fake")
        assert provider.uploads == [], "未改动的文件不应重传"

    def test_changed_file_is_uploaded_again(self, tmp_path: Path):
        novel = self._novel(tmp_path)
        provider = FakeProvider()
        manager = CloudStorageManager(config_file=tmp_path / "c.json")
        manager.providers["fake"] = provider
        manager.sync_novel(novel, "fake")

        provider.uploads.clear()
        (novel / "chapters" / "001.txt").write_text("changed-size", encoding="utf-8")
        assert manager.sync_novel(novel, "fake")
        assert provider.uploads == ["/AI_NovelWriter/chapters/001.txt"]

    def test_recursive_provider_uses_remote_index(self, tmp_path: Path):
        novel = self._novel(tmp_path)
        provider = RecursiveFakeProvider(
            tree={
                "/AI_NovelWriter": [
                    {"name": "meta.json", "isdir": False, "size": 2},
                    {"name": "chapters", "isdir": True},
                ],
                "/AI_NovelWriter/chapters": [{"name": "001.txt", "isdir": False, "size": 1}],
            }
        )
        manager = CloudStorageManager(config_file=tmp_path / "c.json")
        manager.providers["fake"] = provider
        assert manager.sync_novel(novel, "fake")
        # 远端已有同尺寸 ⇒ 不再上传（证明子目录也匹配上了）
        assert provider.uploads == []

    def test_upload_failure_is_reported(self, tmp_path: Path):
        novel = self._novel(tmp_path)
        provider = FakeProvider(fail_upload=True)
        manager = CloudStorageManager(config_file=tmp_path / "c.json")
        manager.providers["fake"] = provider
        assert manager.sync_novel(novel, "fake") is False


# ====================================================================== 连接释放


class TestClientLifecycle:
    def test_close_is_idempotent(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.close()
        provider.close()
        assert provider.client is None

    def test_manager_close_does_not_raise(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "c.json")
        manager.providers["fake"] = FakeProvider()
        manager.close()
