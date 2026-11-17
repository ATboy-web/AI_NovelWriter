"""五家网盘 Provider 的 CRUD 与错误分支（`cloud_storage` 覆盖率主力）。

## 为什么不联网也能测

五家 Provider 的全部逻辑都是"发请求 → 看 status_code → 返回 bool/列表"。
把 `provider.client` 换成一个**记录调用 + 按剧本响应**的假对象，
就能把正常分支与错误分支都走一遍 —— 这与 `respx` 的效果相同，
但不引入新依赖，也不需要账号。

## 断言的重点是「失败时必须返回 False，而不是抛异常」

云同步是**可选功能**：网盘挂了、token 过期、服务器返回 500，
用户应该看到"同步失败"的提示，而不是主界面因未捕获异常而崩。
所以每个方法的错误分支都要有一条用例，且断言 `is False`。

## 跳过的部分

`_stream_to_file` 的真实流式落盘在 `test_cloud_storage_paths_and_sync.py`
已验证（含 512 MB 上限）。本文件只覆盖各 Provider 的**协议层**。
"""

from __future__ import annotations

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
)

# ====================================================================== 假 HTTP 层


class FakeResponse:
    """httpx.Response 的最小替身。"""

    def __init__(self, status_code: int = 200, payload=None, text: str = "", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = headers or {}
        self.content = b""

    def json(self):
        return self._payload

    def iter_bytes(self):
        yield b"payload"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    """按剧本响应的假 httpx.Client。

    `routes` 的键是 `(method, 路径片段)`，值是 `FakeResponse` 或 `Exception`。
    没命中任何路由时返回 200 空对象（大多数"成功"场景够用）。
    """

    def __init__(self, routes=None, default=None):
        self.routes = routes or {}
        self.default = default if default is not None else FakeResponse(200)
        self.calls: list[tuple[str, str]] = []

    def _resolve(self, method: str, url: str):
        for (route_method, fragment), result in self.routes.items():
            if route_method == method and fragment in url:
                return result
        return self.default

    def _handle(self, method: str, url: str):
        self.calls.append((method, url))
        result = self._resolve(method, url)
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, url, **kwargs):
        self.calls.append(("GET-params", str(kwargs.get("params", {}))))
        return self._handle("GET", url)

    def post(self, url, **kwargs):
        self.calls.append(("POST-body", str(kwargs.get("json", {}))))
        return self._handle("POST", url)

    def put(self, url, **kwargs):
        return self._handle("PUT", url)

    def delete(self, url, **kwargs):
        return self._handle("DELETE", url)

    def request(self, method, url, **kwargs):
        if method == "PROPFIND" and "headers" in kwargs:
            self.calls.append(("PROPFIND-depth", str(kwargs["headers"].get("Depth"))))
        return self._handle(method, url)

    def stream(self, method, url, **kwargs):
        return self._handle(method, url)

    def close(self):
        self.calls.append(("CLOSE", ""))


@pytest.fixture()
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "chapter.md"
    path.write_text("第一章正文", encoding="utf-8")
    return path


# ====================================================================== 基类公共逻辑


class _MinimalProvider(CloudProvider):
    """只为测试基类默认实现的最小 Provider。"""

    def connect(self):
        return True

    def upload(self, local_path, remote_path):
        return True

    def download(self, remote_path, local_path):
        return True

    def list_files(self, remote_path="/"):
        return []

    def delete_file(self, remote_path):
        return True

    def create_folder(self, remote_path):
        return True


class TestProviderBase:
    def test_file_name_key_priority(self):
        provider = _MinimalProvider({})
        assert provider.file_name({"name": "a", "file_name": "b"}) == "a"
        assert provider.file_name({"file_name": "b", "server_filename": "c"}) == "b"
        assert provider.file_name({"server_filename": "c"}) == "c"
        assert provider.file_name({}) == ""

    def test_file_size_parsing(self):
        provider = _MinimalProvider({})
        assert provider.file_size({"size": "123"}) == 123
        assert provider.file_size({"size": 456}) == 456
        assert provider.file_size({"size": "abc"}) == -1, "解析不了要给 -1（表示未知）"
        assert provider.file_size({}) == -1

    def test_file_size_zero_is_valid(self):
        """0 字节文件是合法的，不能和"未知"混为一谈。"""
        assert _MinimalProvider({}).file_size({"size": 0}) == 0

    @pytest.mark.parametrize("key", ["isdir", "is_dir", "isDir", "dir", "is_folder", "folder"])
    def test_is_dir_boolean_keys(self, key: str):
        assert _MinimalProvider({}).is_dir({key: True}) is True

    @pytest.mark.parametrize("value", ["dir", "folder", "directory", "drive#folder"])
    def test_is_dir_string_values(self, value: str):
        assert _MinimalProvider({}).is_dir({"type": value}) is True

    def test_is_dir_default_false(self):
        assert _MinimalProvider({}).is_dir({"name": "x"}) is False

    def test_get_file_info_default_none(self):
        assert _MinimalProvider({}).get_file_info("/x") is None

    def test_lazy_client_created_once(self):
        provider = _MinimalProvider({})
        first = provider._get_client(timeout=5.0)
        second = provider._get_client(timeout=5.0)
        assert first is second, "同一 Provider 不应重复创建客户端（会泄漏连接）"

    def test_close_is_idempotent(self):
        provider = _MinimalProvider({})
        provider._get_client()
        provider.close()
        provider.close()
        assert provider.client is None


# ====================================================================== WebDAV


class TestWebDAV:
    def test_connect_success(self):
        provider = WebDAVProvider({"url": "https://dav.example.com", "username": "u", "password": "p"})
        provider.client = FakeClient(default=FakeResponse(207))
        assert provider.connect() is True
        assert provider.connected is True

    def test_connect_rejects_plain_http(self):
        """S7：非本机的 http 端点必须被拒（口令会明文出网）。"""
        provider = WebDAVProvider({"url": "http://dav.example.com"})
        provider.client = FakeClient()
        assert provider.connect() is False
        assert provider.connected is False

    def test_connect_allows_localhost_http(self):
        provider = WebDAVProvider({"url": "http://localhost:8080", "username": "u", "password": "p"})
        provider.client = FakeClient(default=FakeResponse(207))
        assert provider.connect() is True

    def test_connect_network_error(self):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=OSError("网络不通"))
        assert provider.connect() is False

    @pytest.mark.parametrize("status", [200, 201, 204])
    def test_upload_accepted_statuses(self, source_file: Path, status: int):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.upload(source_file, "/a/b.md") is True

    def test_upload_rejected_status(self, source_file: Path):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(507))
        assert provider.upload(source_file, "/a/b.md") is False

    def test_upload_missing_file(self, tmp_path: Path):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient()
        assert provider.upload(tmp_path / "不存在.md", "/a.md") is False

    def test_download_success(self, tmp_path: Path):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(200))
        target = tmp_path / "out" / "ch.md"
        assert provider.download("/a.md", target) is True
        assert target.read_bytes() == b"payload"

    def test_download_not_found(self, tmp_path: Path):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(404))
        assert provider.download("/a.md", tmp_path / "out.md") is False

    @pytest.mark.parametrize("status,expected", [(200, True), (204, True), (403, False)])
    def test_delete(self, status: int, expected: bool):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.delete_file("/a.md") is expected

    def test_delete_network_error(self):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=OSError("断了"))
        assert provider.delete_file("/a.md") is False

    @pytest.mark.parametrize("status,expected", [(201, True), (405, True), (403, False)])
    def test_create_folder(self, status: int, expected: bool):
        """405 也算成功：目录已存在时多数 WebDAV 服务端这样回。"""
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.create_folder("/dir") is expected

    def test_create_folder_network_error(self):
        provider = WebDAVProvider({"url": "https://dav.example.com"})
        provider.client = FakeClient(default=OSError("断了"))
        assert provider.create_folder("/dir") is False

    def test_recursive_listing_flag(self):
        assert WebDAVProvider.supports_recursive_listing is True


# ====================================================================== 百度


class TestBaidu:
    def test_connect_without_token(self):
        provider = BaiduPanProvider({})
        assert provider.connect() is False, "没 token 就不该发请求"

    def test_connect_success(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.connect() is True

    def test_connect_error(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("超时"))
        assert provider.connect() is False

    def test_list_files(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(
            default=FakeResponse(200, {"list": [{"server_filename": "a.md", "isdir": 0, "size": 10}]})
        )
        items = provider.list_files("/novel")
        assert items[0]["server_filename"] == "a.md"

    def test_list_files_error_status(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(401))
        assert provider.list_files("/novel") == []

    def test_list_files_exception(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.list_files("/novel") == []

    @pytest.mark.parametrize("status,expected", [(200, True), (400, False)])
    def test_delete(self, status: int, expected: bool):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.delete_file("/a.md") is expected

    def test_delete_exception(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.delete_file("/a.md") is False

    @pytest.mark.parametrize("status,expected", [(200, True), (409, False)])
    def test_create_folder(self, status: int, expected: bool):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.create_folder("/dir") is expected

    def test_create_folder_exception(self):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.create_folder("/dir") is False

    def test_download_success(self, tmp_path: Path):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        target = tmp_path / "ch.md"
        assert provider.download("/a.md", target) is True
        assert target.exists()

    def test_download_error_status(self, tmp_path: Path):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(403))
        assert provider.download("/a.md", tmp_path / "ch.md") is False

    def test_download_exception(self, tmp_path: Path):
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.download("/a.md", tmp_path / "ch.md") is False

    def test_upload_precheck_failure(self, source_file: Path):
        """预上传失败（非 200）⇒ 不该继续传分片。"""
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(400))
        assert provider.upload(source_file, "/a.md") is False

    def test_upload_without_uploadid(self, source_file: Path):
        """预上传返回 200 但没有 uploadid ⇒ 同样要失败，不能拿 None 去传分片。"""
        provider = BaiduPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {}))
        assert provider.upload(source_file, "/a.md") is False


# ====================================================================== 夸克


class TestQuark:
    def test_connect_without_cookie(self):
        assert QuarkPanProvider({}).connect() is False

    def test_connect_success(self):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.connect() is True

    def test_connect_error(self):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=OSError("超时"))
        assert provider.connect() is False

    def test_list_files(self):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(
            default=FakeResponse(200, {"data": {"list": [{"file_name": "a.md", "file_type": 0}]}})
        )
        assert provider.list_files("/")[0]["file_name"] == "a.md"

    def test_list_files_bad_shape(self):
        """返回结构缺 data/list ⇒ 空列表，不能 KeyError。"""
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(200, {}))
        assert provider.list_files("/") == []

    @pytest.mark.parametrize("status,expected", [(200, True), (500, False)])
    def test_delete(self, status: int, expected: bool):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(status))
        assert provider.delete_file("/a") is expected

    def test_create_folder(self):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.create_folder("新目录") is True

    def test_create_folder_exception(self):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.create_folder("新目录") is False

    def test_download_error(self, tmp_path: Path):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(404))
        assert provider.download("/a", tmp_path / "x.md") is False

    def test_upload_without_upload_id(self, source_file: Path):
        provider = QuarkPanProvider({"cookie": "c"})
        provider.client = FakeClient(default=FakeResponse(200, {"data": {}}))
        assert provider.upload(source_file, "/parent") is False


# ====================================================================== 迅雷


class TestXunlei:
    def test_connect_without_token(self):
        assert XunleiPanProvider({}).connect() is False

    def test_connect_success(self):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.connect() is True

    def test_list_files(self):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {"files": [{"name": "a.md"}]}))
        assert provider.list_files("/") == [{"name": "a.md"}]

    def test_delete(self):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.delete_file("fid") is True

    def test_delete_exception(self):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.delete_file("fid") is False

    def test_create_folder(self):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.create_folder("新目录") is True

    def test_download_error(self, tmp_path: Path):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(403))
        assert provider.download("fid", tmp_path / "x.md") is False

    def test_upload_without_id(self, source_file: Path):
        provider = XunleiPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {}))
        assert provider.upload(source_file, "/parent") is False


# ====================================================================== 阿里云盘


class TestAliyun:
    def test_connect_without_token(self):
        assert AliyunPanProvider({}).connect() is False

    def test_connect_success(self):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.connect() is True

    def test_list_files(self):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {"items": [{"name": "a.md"}]}))
        assert provider.list_files("/") == [{"name": "a.md"}]

    def test_rapid_upload_shortcut(self, source_file: Path):
        """秒传命中（rapid_upload）⇒ 直接成功，不发起上传请求。"""
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {"rapid_upload": True}))
        assert provider.upload(source_file, "/parent") is True

    def test_upload_without_url(self, source_file: Path):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {}))
        assert provider.upload(source_file, "/parent") is False

    def test_upload_create_failure(self, source_file: Path):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(400))
        assert provider.upload(source_file, "/parent") is False

    def test_upload_rejects_insecure_url(self, source_file: Path):
        """上传地址若被改成 http，必须拒绝（L-2 同类风险）。"""
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(
            routes={("POST", "/file/create"): FakeResponse(200, {"upload_url": "http://evil/put"})},
            default=FakeResponse(200, {}),
        )
        assert provider.upload(source_file, "/parent") is False

    def test_download_without_url(self, tmp_path: Path):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200, {}))
        assert provider.download("fid", tmp_path / "x.md") is False

    def test_download_get_url_failure(self, tmp_path: Path):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(404))
        assert provider.download("fid", tmp_path / "x.md") is False

    def test_delete(self):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=FakeResponse(200))
        assert provider.delete_file("fid") is True

    def test_create_folder_exception(self):
        provider = AliyunPanProvider({"access_token": "T"})
        provider.client = FakeClient(default=OSError("断网"))
        assert provider.create_folder("新目录") is False


# ====================================================================== 管理器


class TestManagerUpload:
    def test_requires_connected_provider(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.connected = False
        manager.providers["fake"] = provider
        assert manager.upload_novel(tmp_path, "fake") is False

    def test_unknown_provider(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        assert manager.upload_novel(tmp_path, "不存在") is False

    def test_uploads_every_file(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.connected = True
        uploaded: list[tuple[str, str]] = []
        provider.upload = lambda local, remote: uploaded.append((local.name, remote)) or True  # type: ignore[method-assign]
        manager.providers["fake"] = provider

        novel = tmp_path / "novel"
        (novel / "chapters").mkdir(parents=True)
        (novel / "chapters" / "01.md").write_text("a", encoding="utf-8")
        (novel / "meta.json").write_text("{}", encoding="utf-8")

        assert manager.upload_novel(novel, "fake") is True
        assert {name for name, _ in uploaded} == {"01.md", "meta.json"}

    def test_partial_failure_returns_false(self, tmp_path: Path):
        """有文件失败就必须报 False —— 旧实现无脑返回 True，界面会谎报成功。"""
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.connected = True
        provider.upload = lambda local, remote: False  # type: ignore[method-assign]
        manager.providers["fake"] = provider

        novel = tmp_path / "novel"
        novel.mkdir()
        (novel / "meta.json").write_text("{}", encoding="utf-8")
        assert manager.upload_novel(novel, "fake") is False

    def test_exception_returns_false(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.connected = True
        provider.create_folder = lambda path: (_ for _ in ()).throw(OSError("炸了"))  # type: ignore[method-assign]
        manager.providers["fake"] = provider
        assert manager.upload_novel(tmp_path, "fake") is False


class TestManagerListing:
    def test_available_providers_shape(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        rows = manager.get_available_providers()
        assert len(rows) == len(CloudStorageManager.PROVIDERS)
        for row in rows:
            assert {"id", "name", "configured", "connected", "recursive_listing"} <= set(row)

    def test_get_provider(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        manager.providers["fake"] = provider
        assert manager.get_provider("fake") is provider
        assert manager.get_provider("不存在") is None

    def test_configure_replaces_and_closes_old(self, tmp_path: Path):
        """重配 provider 时必须释放旧连接（否则每次改配置泄漏一个 client）。"""
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        old = _MinimalProvider({})
        manager.providers["webdav"] = old
        manager.configure_provider("webdav", {"url": "https://x.example.com"})
        assert old.client is None
        assert manager.providers["webdav"] is not old

    def test_remote_index_walks_dirs(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        tree = {
            "/r": [{"name": "sub", "isdir": True}, {"name": "a.md", "isdir": False, "size": 3}],
            "/r/sub": [{"name": "b.md", "isdir": False, "size": 4}],
        }
        provider.list_files = lambda path="/": tree.get(path, [])  # type: ignore[method-assign]
        index = manager.remote_index(provider, "/r")
        assert index["a.md"] == 3
        assert index["sub/b.md"] == 4

    def test_remote_index_depth_cap(self, tmp_path: Path):
        """自引用目录不能无限递归。"""
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.list_files = lambda path="/": [{"name": "loop", "isdir": True}]  # type: ignore[method-assign]
        assert manager.remote_index(provider, "/r") == {}

    def test_download_partial_failure(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        provider = _MinimalProvider({})
        provider.connected = True
        provider.list_files = lambda path="/": [{"name": "a.md", "isdir": False, "size": 1}]  # type: ignore[method-assign]
        provider.download = lambda remote, local: False  # type: ignore[method-assign]
        manager.providers["fake"] = provider
        assert manager.download_novel("/r", tmp_path / "out", "fake") is False


class TestManagerConfigEncryption:
    def test_sensitive_fields_are_not_plaintext(self, tmp_path: Path):
        """加密可用时，落盘的 token 不得是明文。"""
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        if manager._secure_config is None:
            pytest.skip("本机加密后端不可用")
        manager.configure_provider("baidu", {"access_token": "SECRET-TOKEN-VALUE"})
        raw = (tmp_path / "cfg.json").read_text(encoding="utf-8")
        assert "SECRET-TOKEN-VALUE" not in raw

    def test_roundtrip_decrypts(self, tmp_path: Path):
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        if manager._secure_config is None:
            pytest.skip("本机加密后端不可用")
        manager.configure_provider("baidu", {"access_token": "T-123"})
        reloaded = CloudStorageManager(config_file=tmp_path / "cfg.json")
        assert reloaded.config["baidu"]["access_token"] == "T-123"

    def test_nested_config_encrypted(self, tmp_path: Path):
        """嵌套字典里的凭据也要加密（配置可能按 provider 再分层）。"""
        manager = CloudStorageManager(config_file=tmp_path / "cfg.json")
        if manager._secure_config is None:
            pytest.skip("本机加密后端不可用")
        manager.configure_provider("webdav", {"url": "https://x", "password": "PW-SECRET"})
        raw = json.loads((tmp_path / "cfg.json").read_text(encoding="utf-8"))
        assert raw["webdav"]["password"] != "PW-SECRET"
