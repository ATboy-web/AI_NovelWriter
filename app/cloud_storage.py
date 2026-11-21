"""云端存储模块 —— 支持 WebDAV（坚果云）/ 百度网盘 / 夸克网盘 / 迅雷网盘 / 阿里云盘。

## 安全与可靠性约定（2026-11-17 审查后重写）

| 主题 | 约定 |
|---|---|
| 传输安全 | 除 localhost / 127.0.0.1 / ::1 外**拒绝明文 http**（凭据会明文出网） |
| 凭据落盘 | 一律 Fernet 加密；**任何失败路径都不得回落明文**（宁可写空） |
| 配置落盘 | 原子写（临时文件 + `os.replace`）+ `.bak` 轮转 |
| 配置损坏 | 留档 `cloud_config.corrupt-<时间戳>.json` 后以空配置继续，**不得阻断启动** |
| 下载落盘 | 云端返回的文件名必须经 `_safe_local_target()` 归一化，**禁止越界写入** |
| 内存占用 | 上传/下载一律分块或流式，不把整个文件读进内存 |
| 连接 | `httpx.Client` 懒创建并提供 `close()`，避免句柄泄漏 |

## 目录字段的厂商差异

五家网盘对"这是不是目录"的字段完全不同（`isdir` / `file_type` / `kind` / `type`）。
统一由 `CloudProvider.is_dir()` 归一化，各 Provider 覆写自己的判据；
上层只调 `is_dir()`，不再直接读厂商字段 —— 否则新增一家就要改主流程
（这也是"新增一家只改注册表一处"原则的一部分）。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Dict, List, Optional
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import httpx
from loguru import logger

from .storage import atomic_write_json

# 允许使用明文 http 的本机地址（本地 WebDAV / 自建网盘）
_ALLOWED_INSECURE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

#: 分块上传的块大小。百度网盘要求按 4 MB 切片；其余厂商沿用同一块大小即可。
_UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024

#: 单文件下载上限（防远端 Content-Length 造假把磁盘写满）。
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

#: 递归下载/列举的最大深度（防远端返回自引用目录导致无限递归）。
_MAX_TRAVERSE_DEPTH = 8

#: Windows 保留设备名（写成文件会失败或指向设备）。
_WIN_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)

__all__ = [
    "CloudProvider",
    "CloudStorageManager",
    "WebDAVProvider",
    "BaiduPanProvider",
    "QuarkPanProvider",
    "XunleiPanProvider",
    "AliyunPanProvider",
    "_require_secure_url",
    "_safe_error",
    "_safe_local_target",
]


# ====================================================================== 通用工具


def _require_secure_url(url: str, what: str = "云盘地址") -> str:
    """校验云盘端点协议：除本机地址外必须使用 https（S7）。

    WebDAV 用 HTTP Basic 承载口令（``auth=(user, password)``），
    迅雷/阿里云盘用 ``Authorization: Bearer <token>``。若 base_url 被写成
    ``http://``，这些凭据就会以**明文**发出。
    """
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{what}协议非法: {url!r}（仅支持 http/https）")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host not in _ALLOWED_INSECURE_HOSTS:
        raise ValueError(
            f"拒绝向非本机地址 {host!r} 用明文 HTTP 发送云盘凭据（{url!r}）；"
            "请改用 https://，或把地址指向 localhost / 127.0.0.1 上的本地服务"
        )
    return url


def _safe_error(message: str, error, *secrets: str) -> str:
    """构造不会泄露凭据的错误文本（S6 / M10）。

    第三方 SDK 与 httpx 的异常 ``str()`` 会带上完整请求 URL，而百度网盘把
    ``access_token`` 放在查询串里 —— 一次失败的上传就会把长期令牌打印出来。

    这里在输出前做两件事：
    1. 把调用方已知的凭据字面量替换成 ``***``；
    2. 用正则清掉 URL / 文本里 ``access_token=...`` 一类的查询串键值。
    """
    text = f"{message}: {error}"
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "***")
    return re.sub(
        r"(?i)(access_token|refresh_token|api_key|apikey|token|password|secret)=[^&\s\"']+",
        r"\1=***",
        text,
    )


def _safe_local_target(base: Path, name: str) -> Optional[Path]:
    """把**云端返回的名字**转换成 `base` 之内的安全本地路径（H-1）。

    这是"下载不得越界"的**唯一强制点**。云端返回的名字是不可信输入：
    恶意 WebDAV、被入侵的网盘账号、代理篡改响应都能构造 `../../x`。
    旧实现直接 `local_dir / name`，实测可覆盖任意可写文件。

    处理顺序（每一步都必要）：
    1. 反斜杠统一成正斜杠（Windows 上 `..\\..\\x` 同样是穿越）；
    2. **只取最后一段**（`PurePosixPath(...).name`）—— 目录结构由调用方的
       递归决定，不由远端字符串决定；
    3. 拒绝空名、`.`、`..` 与 Windows 保留设备名；
    4. `resolve()` 后再校验一次 `is_relative_to(base)`（防符号链接逃逸）。

    Returns:
        安全的绝对路径；不安全时返回 `None`（调用方必须跳过并告警）。
    """
    raw = str(name or "").replace("\\", "/").strip()
    if not raw:
        return None
    leaf = PurePosixPath(raw).name.strip()
    if not leaf or leaf in (".", ".."):
        return None
    if _WIN_RESERVED.match(leaf):
        return None
    try:
        base_p = Path(base).resolve()
        target = (base_p / leaf).resolve()
    except (OSError, RuntimeError):
        return None
    if target == base_p or not target.is_relative_to(base_p):
        return None
    return target


def _iter_file_chunks(handle: BinaryIO, size: int = _UPLOAD_CHUNK_BYTES):
    """按块读取文件，返回 `(序号, 数据)`。用于分片上传，避免整文件入内存。"""
    index = 0
    while True:
        chunk = handle.read(size)
        if not chunk:
            return
        yield index, chunk
        index += 1


# ====================================================================== 提供者基类


class CloudProvider(ABC):
    """云存储提供者基类。

    子类只需要覆写"厂商差异"（目录字段、名字字段），公共的
    安全校验 / 分块 / 流式落盘都在基类或管理器里做一次。
    """

    #: 该厂商的 `list_files` 是否支持路径式递归（WebDAV 为 True）。
    #: False 时 `sync_novel` 退回本地清单比对（见 `_load_manifest`）。
    supports_recursive_listing = False

    #: 未显式指定 timeout 时的兜底值。httpx 默认仅 5s，网盘大文件传输必然误超时。
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, config: Dict):
        self.config = config
        self.name = "Unknown"
        self.connected = False
        self.client: Optional[httpx.Client] = None
        # 按「生效参数」分桶缓存：同参数复用连接，不同参数各建一个客户端。
        self._clients: Dict[tuple, httpx.Client] = {}
        # 首次显式建连的参数作为该 provider 的基准（base_url/auth 等），
        # 后续裸调用沿用它，避免"先 upload 后 connect"丢掉鉴权与站点。
        self._base_kwargs: Optional[Dict] = None

    # ------------------------------------------------------------------ 连接

    @staticmethod
    def _client_key(kwargs: Dict) -> tuple:
        """把生效参数归一化成可哈希的缓存键（auth 元组等按 repr 稳定序列化）。"""
        return tuple(sorted((k, repr(v)) for k, v in kwargs.items()))

    def _get_client(self, **kwargs) -> httpx.Client:
        """懒创建客户端（构造 provider 时不建，避免未使用的连接泄漏）。

        ❗ 旧实现是 `if self.client is None: self.client = httpx.Client(**kwargs)`，
        **首次调用的参数被永久固化**：connect() 先以 timeout=30 建连后，
        配额/上传再传 timeout=60 会被静默忽略；反之若首次是裸调用，
        则整条链路落到 httpx 默认的 5s，大文件同步必然超时。
        现改为「基准参数 + 本次覆盖」合并后按参数分桶缓存：
        裸调用沿用基准（保持 WebDAV 的 base_url/auth 语义），
        显式覆盖则拿到真正生效的新客户端。
        """
        if self.client is not None and not self._clients:
            # 外部注入/历史默认客户端：沿用它（既有契约），但显式 timeout 必须生效，
            # 不能像旧实现那样把传进来的 60s 静默丢掉。
            timeout = kwargs.get("timeout")
            if timeout is not None:
                try:
                    self.client.timeout = timeout
                except Exception as exc:  # noqa: BLE001 - 测试替身可能不支持该属性
                    logger.debug(f"[云存储] 注入客户端不支持 timeout 覆盖：{exc}")
            return self.client
        if not kwargs and self.client is not None:
            # 裸调用沿用当前默认客户端（含外部注入的替身），保持既有语义
            return self.client
        if self._base_kwargs is None:
            self._base_kwargs = dict(kwargs)
        merged = {**self._base_kwargs, **kwargs}
        merged.setdefault("timeout", self.DEFAULT_TIMEOUT)
        key = self._client_key(merged)
        client = self._clients.get(key)
        if client is None:
            client = httpx.Client(**merged)
            self._clients[key] = client
        self.client = client
        return client

    def close(self) -> None:
        """释放全部连接。幂等。"""
        for client in self._clients.values():
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001 - 关闭失败不该影响退出
                logger.debug(f"[云存储] 关闭 {self.name} 客户端失败：{exc}")
        self._clients.clear()
        self._base_kwargs = None
        self.client = None

    # ------------------------------------------------------------------ 厂商字段归一化

    def file_name(self, info: Dict) -> str:
        """从列表项里取文件名（各家字段不同）。"""
        for key in ("name", "file_name", "server_filename", "filename"):
            value = info.get(key)
            if value:
                return str(value)
        return ""

    def file_size(self, info: Dict) -> int:
        """从列表项里取大小（取不到返回 -1，表示"未知"，不参与相等比较）。"""
        for key in ("size", "file_size", "getcontentlength", "length"):
            value = info.get(key)
            if value is None or value == "":
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return -1

    def is_dir(self, info: Dict) -> bool:
        """统一判定"是不是目录"。

        默认实现覆盖常见布尔字段与字符串枚举；**数值型**
        （夸克的 `file_type` 0/1）与厂商专有枚举由子类覆写。
        """
        for key in ("isdir", "is_dir", "isDir", "dir", "is_folder", "isFolder", "folder"):
            if info.get(key):
                return True
        for key in ("type", "kind", "category", "file_type"):
            value = info.get(key)
            if isinstance(value, str) and value.lower() in (
                "dir",
                "folder",
                "directory",
                "drive#folder",
            ):
                return True
        return False

    # ------------------------------------------------------------------ 抽象接口

    @abstractmethod
    def connect(self) -> bool:
        """连接到云存储"""

    @abstractmethod
    def upload(self, local_path: Path, remote_path: str) -> bool:
        """上传文件"""

    @abstractmethod
    def download(self, remote_path: str, local_path: Path) -> bool:
        """下载文件"""

    @abstractmethod
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        """列出文件"""

    @abstractmethod
    def delete_file(self, remote_path: str) -> bool:
        """删除文件"""

    @abstractmethod
    def create_folder(self, remote_path: str) -> bool:
        """创建文件夹"""

    def get_file_info(self, remote_path: str) -> Optional[Dict]:
        """获取文件信息"""
        return None

    # ------------------------------------------------------------------ 公共辅助

    def _stream_to_file(self, response: httpx.Response, local_path: Path) -> bool:
        """把响应流式写入本地文件，带体积上限（L-3 / 防磁盘写满）。

        先看 `Content-Length`（可被伪造，只作为提前拒绝），
        再按实际字节数计账（真正的护栏）。
        """
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > _MAX_DOWNLOAD_BYTES:
            logger.warning(f"[云存储] 文件过大（{int(declared) / 1048576:.1f} MB），已拒绝下载")
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        tmp = local_path.with_name(local_path.name + ".part")
        try:
            with open(tmp, "wb") as f:
                for chunk in response.iter_bytes():
                    written += len(chunk)
                    if written > _MAX_DOWNLOAD_BYTES:
                        raise ValueError(f"下载体积超过上限 {_MAX_DOWNLOAD_BYTES // 1048576} MB")
                    f.write(chunk)
            tmp.replace(local_path)
            return True
        except Exception as exc:  # noqa: BLE001 - 失败要清理半截文件
            logger.warning(f"[云存储] 下载写入失败：{_safe_error('下载失败', exc)}")
            try:
                tmp.unlink(missing_ok=True)
            except OSError as exc:
                logger.debug(f"[cloud_storage] 已忽略异常（OSError）：{exc}")
            return False


# ====================================================================== WebDAV


class WebDAVProvider(CloudProvider):
    """WebDAV 提供者（坚果云等）。"""

    supports_recursive_listing = True

    #: 常见 WebDAV 命名空间（坚果云/Nextcloud 用 `D:`，部分服务端不带前缀）
    _NS = {"d": "DAV:"}

    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "WebDAV"
        self.base_url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def connect(self) -> bool:
        try:
            # S7: WebDAV 走 HTTP Basic，必须拒绝非本机的明文 http 端点
            self.base_url = _require_secure_url(self.base_url, "WebDAV 地址")
            client = self._get_client(base_url=self.base_url, auth=(self.username, self.password), timeout=30.0)
            resp = client.request("PROPFIND", "/", headers={"Depth": "0"})
            self.connected = resp.status_code in (200, 207)
            return self.connected
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("WebDAV连接失败", e, self.password))
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            client = self._get_client()
            # L-3：用文件对象流式上传，不 `f.read()` 整文件
            with open(local_path, "rb") as f:
                resp = client.put(remote_path, content=f)
            return resp.status_code in (200, 201, 204)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("上传失败", e, self.password))
            return False

    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            client = self._get_client()
            with client.stream("GET", remote_path) as resp:
                if resp.status_code != 200:
                    return False
                return self._stream_to_file(resp, local_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("下载失败", e, self.password))
            return False

    def list_files(self, remote_path: str = "/") -> List[Dict]:
        """解析 `PROPFIND` 的 207 多状态响应（M-7）。

        旧实现请求了 PROPFIND 却**从不解析 XML**，固定返回 `[]` ——
        于是"下载 / 同步"永远无文件可下，界面上还提示成功。
        """
        try:
            client = self._get_client()
            resp = client.request("PROPFIND", remote_path, headers={"Depth": "1"})
            if resp.status_code not in (200, 207):
                return []
            return self.parse_propfind(resp.text, remote_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[云盘] WebDAV 列目录失败：{_safe_error('', exc, self.password)}")
            return []

    @classmethod
    def parse_propfind(cls, xml_text: str, request_path: str = "/") -> List[Dict]:
        """把 PROPFIND 响应解析成 `[{name, isdir, size, href}]`（纯函数，可单测）。

        - 命名空间按 `DAV:` 取，兼容带 `D:` 前缀与不带前缀两种写法；
        - 跳过"自身"条目（`href` 与请求路径等价的那条）；
        - `href` 做百分号解码（中文文件名必须解，否则存成 `%E4%B8%AD`）。
        """
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return []

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        want = unquote(request_path).rstrip("/") or "/"
        items: List[Dict] = []
        for node in root.iter():
            if local(node.tag) != "response":
                continue
            href = ""
            is_dir = False
            size: Optional[int] = None
            for child in node.iter():
                name = local(child.tag)
                if name == "href" and not href:
                    href = (child.text or "").strip()
                elif name == "collection":
                    is_dir = True
                elif name == "getcontentlength" and size is None:
                    try:
                        size = int((child.text or "").strip())
                    except ValueError:
                        size = None
            if not href:
                continue
            path = unquote(urlparse(href).path or href)
            norm = path.rstrip("/") or "/"
            if norm == want:
                continue  # 目录自身
            leaf = PurePosixPath(norm).name
            if not leaf:
                continue
            items.append(
                {
                    "name": leaf,
                    "isdir": is_dir,
                    "size": size if size is not None else -1,
                    "href": path,
                }
            )
        return items

    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().delete(remote_path)
            return resp.status_code in (200, 204)
        except Exception:  # noqa: BLE001
            return False

    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().request("MKCOL", remote_path)
            return resp.status_code in (200, 201, 405)  # 405 = 已存在
        except Exception:  # noqa: BLE001
            return False


# ====================================================================== 百度网盘


class BaiduPanProvider(CloudProvider):
    """百度网盘提供者。"""

    API_BASE = "https://pan.baidu.com/rest/2.0/xpan"

    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "百度网盘"
        self.access_token = config.get("access_token", "")
        self.refresh_token = config.get("refresh_token", "")

    def file_name(self, info: Dict) -> str:
        return str(info.get("server_filename") or info.get("name") or "")

    def is_dir(self, info: Dict) -> bool:
        return bool(info.get("isdir")) or super().is_dir(info)

    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self._get_client(timeout=60.0).get(
                f"{self.API_BASE}/quota", params={"access_token": self.access_token}
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:  # noqa: BLE001
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """分片上传（M-5）。

        旧实现把整个文件当成**唯一**分片上传（`partseq=0`，`block_list` 一个 md5），
        而百度要求每片 ≤ 4 MB 且 `block_list` 与片数一一对应 ——
        超过 4 MB 的文件必然失败，且整文件读入内存。
        """
        try:
            file_size = local_path.stat().st_size
            client = self._get_client()

            # 1. 预上传
            resp = client.post(
                f"{self.API_BASE}/file",
                params={"method": "upload", "access_token": self.access_token},
                json={"path": remote_path, "size": file_size, "isdir": 0, "autoinit": 1, "rtype": 3},
            )
            if resp.status_code != 200:
                return False
            uploadid = resp.json().get("uploadid")
            if not uploadid:
                return False

            # 2. 逐片上传，累积每片 md5
            block_list: List[str] = []
            with open(local_path, "rb") as f:
                for partseq, chunk in _iter_file_chunks(f):
                    resp = client.post(
                        f"{self.API_BASE}/file",
                        params={
                            "method": "upload",
                            "access_token": self.access_token,
                            "type": "tmpfile",
                            "path": remote_path,
                            "uploadid": uploadid,
                            "partseq": partseq,
                        },
                        content=chunk,
                    )
                    if resp.status_code != 200:
                        return False
                    block_list.append(hashlib.md5(chunk).hexdigest())

            if not block_list:
                return False

            # 3. 合并
            resp = client.post(
                f"{self.API_BASE}/file",
                params={"method": "createsuperfile", "access_token": self.access_token},
                json={
                    "path": remote_path,
                    "size": file_size,
                    "isdir": 0,
                    "rtype": 3,
                    "uploadid": uploadid,
                    "block_list": json.dumps(block_list),
                },
            )
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("百度网盘上传失败", e, self.access_token, self.refresh_token))
            return False

    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            client = self._get_client()
            with client.stream(
                "GET",
                f"{self.API_BASE}/file",
                params={"method": "download", "access_token": self.access_token, "path": remote_path},
            ) as resp:
                if resp.status_code != 200:
                    return False
                return self._stream_to_file(resp, local_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("百度网盘下载失败", e, self.access_token))
            return False

    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self._get_client().get(
                f"{self.API_BASE}/file",
                params={"method": "list", "access_token": self.access_token, "dir": remote_path},
            )
            if resp.status_code == 200:
                return resp.json().get("list", []) or []
            return []
        except Exception:  # noqa: BLE001
            return []

    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file",
                params={"method": "delete", "access_token": self.access_token},
                json={"filelist": [remote_path]},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file",
                params={"method": "create", "access_token": self.access_token},
                json={"path": remote_path, "isdir": 1},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


# ====================================================================== 夸克网盘


class QuarkPanProvider(CloudProvider):
    """夸克网盘提供者。"""

    API_BASE = "https://drive-pc.quark.cn/1/clouddrive"

    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "夸克网盘"
        self.cookie = config.get("cookie", "")

    def file_name(self, info: Dict) -> str:
        return str(info.get("file_name") or info.get("name") or "")

    def is_dir(self, info: Dict) -> bool:
        """夸克用 `file_type` 数值：0 = 文件，1 = 目录。"""
        file_type = info.get("file_type")
        if isinstance(file_type, int):
            return file_type == 1
        if isinstance(file_type, str) and file_type.isdigit():
            return file_type == "1"
        return super().is_dir(info)

    def _headers(self) -> Dict[str, str]:
        return {"Cookie": self.cookie}

    def connect(self) -> bool:
        try:
            if not self.cookie:
                return False
            resp = self._get_client(timeout=60.0).get(f"{self.API_BASE}/quota", headers=self._headers())
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:  # noqa: BLE001
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            client = self._get_client()
            resp = client.post(
                f"{self.API_BASE}/file",
                headers=self._headers(),
                json={
                    "file_name": local_path.name,
                    "size": file_size,
                    "parent": remote_path,
                    "file_type": "file",
                },
            )
            if resp.status_code != 200:
                return False
            upload_id = resp.json().get("data", {}).get("upload_id")
            if not upload_id:
                return False
            # 流式 PUT，避免整文件入内存（L-3）
            with open(local_path, "rb") as f:
                resp = client.put(f"{self.API_BASE}/file/upload/{upload_id}", headers=self._headers(), content=f)
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("夸克网盘上传失败", e, self.cookie))
            return False

    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            client = self._get_client()
            with client.stream(
                "GET", f"{self.API_BASE}/file/download", headers=self._headers(), params={"file_id": remote_path}
            ) as resp:
                if resp.status_code != 200:
                    return False
                return self._stream_to_file(resp, local_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("夸克网盘下载失败", e, self.cookie))
            return False

    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self._get_client().get(
                f"{self.API_BASE}/file/sort",
                headers=self._headers(),
                params={"pdir_fid": remote_path, "_sort": "file_type", "_size": 50},
            )
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("list", []) or []
            return []
        except Exception:  # noqa: BLE001
            return []

    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file/delete", headers=self._headers(), json={"filelist": [remote_path]}
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file",
                headers=self._headers(),
                json={"file_name": remote_path, "pdir_fid": "", "file_type": "folder"},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


# ====================================================================== 迅雷网盘


class XunleiPanProvider(CloudProvider):
    """迅雷网盘提供者。"""

    API_BASE = "https://api-pan.xunlei.com/drive/v1"

    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "迅雷网盘"
        self.access_token = config.get("access_token", "")

    def is_dir(self, info: Dict) -> bool:
        """迅雷用 `kind`：`drive#folder` / `drive#file`。"""
        kind = str(info.get("kind") or "").lower()
        if kind:
            return kind.endswith("folder")
        return super().is_dir(info)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self._get_client(timeout=60.0).get(f"{self.API_BASE}/quota", headers=self._headers())
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:  # noqa: BLE001
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            client = self._get_client()
            resp = client.post(
                f"{self.API_BASE}/file",
                headers=self._headers(),
                json={"name": local_path.name, "size": file_size, "parent_id": remote_path},
            )
            if resp.status_code != 200:
                return False
            upload_id = resp.json().get("id")
            if not upload_id:
                return False
            with open(local_path, "rb") as f:
                resp = client.put(f"{self.API_BASE}/file/{upload_id}", headers=self._headers(), content=f)
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("迅雷网盘上传失败", e, self.access_token))
            return False

    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            client = self._get_client()
            with client.stream("GET", f"{self.API_BASE}/file/{remote_path}/download", headers=self._headers()) as resp:
                if resp.status_code != 200:
                    return False
                return self._stream_to_file(resp, local_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("迅雷网盘下载失败", e, self.access_token))
            return False

    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self._get_client().get(
                f"{self.API_BASE}/file", headers=self._headers(), params={"parent_id": remote_path}
            )
            if resp.status_code == 200:
                return resp.json().get("files", []) or []
            return []
        except Exception:  # noqa: BLE001
            return []

    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().delete(f"{self.API_BASE}/file/{remote_path}", headers=self._headers())
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file",
                headers=self._headers(),
                json={"name": remote_path, "parent_id": "", "kind": "folder"},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


# ====================================================================== 阿里云盘


class AliyunPanProvider(CloudProvider):
    """阿里云盘提供者。"""

    API_BASE = "https://api.aliyundrive.com/v2"

    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "阿里云盘"
        self.access_token = config.get("access_token", "")
        self.refresh_token = config.get("refresh_token", "")

    def is_dir(self, info: Dict) -> bool:
        """阿里用 `type`：`folder` / `file`。"""
        value = str(info.get("type") or "").lower()
        if value:
            return value == "folder"
        return super().is_dir(info)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self._get_client(timeout=60.0).post(f"{self.API_BASE}/user/get", headers=self._headers())
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:  # noqa: BLE001
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            # 阿里云盘要求 sha1 做秒传校验；流式计算，避免整文件入内存
            digest = hashlib.sha1()
            with open(local_path, "rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)
            client = self._get_client()
            resp = client.post(
                f"{self.API_BASE}/file/create",
                headers=self._headers(),
                json={
                    "name": local_path.name,
                    "size": file_size,
                    "parent_file_id": remote_path,
                    "type": "file",
                    "check_name_mode": "auto_rename",
                    "content_hash": digest.hexdigest(),
                    "content_hash_name": "sha1",
                },
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
            # 秒传命中：没有 upload_url，视为成功
            if data.get("rapid_upload"):
                return True
            upload_url = data.get("upload_url")
            if not upload_url:
                return False
            _require_secure_url(upload_url, "阿里云盘上传地址")
            with open(local_path, "rb") as f:
                resp = client.put(
                    upload_url,
                    headers={**self._headers(), "Content-Type": "application/octet-stream"},
                    content=f,
                )
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("阿里云盘上传失败", e, self.access_token, self.refresh_token))
            return False

    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            client = self._get_client()
            resp = client.post(
                f"{self.API_BASE}/file/get_download_url",
                headers=self._headers(),
                json={"file_id": remote_path},
            )
            if resp.status_code != 200:
                return False
            download_url = resp.json().get("url")
            if not download_url:
                return False
            with client.stream("GET", download_url) as stream:
                if stream.status_code != 200:
                    return False
                return self._stream_to_file(stream, local_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("阿里云盘下载失败", e, self.access_token))
            return False

    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file/list",
                headers=self._headers(),
                json={"parent_file_id": remote_path, "limit": 100},
            )
            if resp.status_code == 200:
                return resp.json().get("items", []) or []
            return []
        except Exception:  # noqa: BLE001
            return []

    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file/delete", headers=self._headers(), json={"file_id": remote_path}
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self._get_client().post(
                f"{self.API_BASE}/file/create",
                headers=self._headers(),
                json={"name": remote_path, "parent_file_id": "", "type": "folder"},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


# ====================================================================== 管理器


class CloudStorageManager:
    """云存储管理器。"""

    PROVIDERS = {
        "webdav": {"name": "WebDAV（坚果云）", "class": WebDAVProvider},
        "baidu": {"name": "百度网盘", "class": BaiduPanProvider},
        "quark": {"name": "夸克网盘", "class": QuarkPanProvider},
        "xunlei": {"name": "迅雷网盘", "class": XunleiPanProvider},
        "aliyun": {"name": "阿里云盘", "class": AliyunPanProvider},
    }

    #: 需要加密存储的敏感字段（云盘凭据）
    _SENSITIVE_FIELDS = {"password", "access_token", "refresh_token", "cookie", "token"}

    #: 增量同步的本地清单文件名（远端不支持递归列举时使用）
    _MANIFEST_NAME = ".cloud_sync.json"

    def __init__(self, config_file: Path = None, secure_config=None):
        """`secure_config` 可注入 —— 生产留空即用默认（`~/.ai_novel_writer`）。

        ❗ 为什么需要这个参数：`SecureConfig()` 默认读**真实用户目录**下的密钥文件，
        于是"加密是否可用"取决于机器状态（例如密钥来自其他账户就打不开）。
        测试如果无法注入，就只能 `skip("本机加密后端不可用")` ——
        加密回归在 CI 上等于没跑，而"凭据不得明文落盘"是安全项。
        """
        self.config_file = Path(config_file) if config_file else Path.home() / ".ai_novel_writer" / "cloud_config.json"
        self._secure_config = None
        if secure_config is not None:
            self._secure_config = secure_config
        else:
            try:
                from app.secure_config import SecureConfig

                self._secure_config = SecureConfig()
            except Exception as exc:  # noqa: BLE001 - 加密不可用不应阻断启动
                logger.warning(f"[云存储] 加密组件初始化失败，凭据将不会被保存：{exc}")
        self.config = self._load_config()
        self.providers: Dict[str, CloudProvider] = {}
        self._init_providers()

    # ------------------------------------------------------------------ 配置

    def _load_config(self) -> Dict:
        """加载配置。**损坏时必须能继续启动**（M-3）。

        旧实现直接 `json.load` 且不捕获异常，一路抛到 `NovelWriterApp.__init__`，
        而入口没有 try ⇒ 配置文件被截断/手改后，**双击 EXE 无窗口直接退出**。
        现在的行为：留档原文件 → 以空配置继续 → 记录明确的告警。
        """
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"配置根节点不是对象（{type(data).__name__}）")
        except Exception as exc:  # noqa: BLE001
            archived = self._archive_corrupt_config()
            logger.error(
                f"[云存储] 配置读取失败（{type(exc).__name__}: {exc}），"
                f"已留档为 {archived.name if archived else '（留档失败）'}；本次以空配置继续。"
            )
            return {}
        return self._transform_config(data, decrypt=True)

    def _archive_corrupt_config(self) -> Optional[Path]:
        """把损坏的配置文件留档，供人工恢复。失败返回 None（不抛）。"""
        try:
            if not self.config_file.exists():
                return None
            stamp = time.strftime("%Y%m%d_%H%M%S")
            dst = self.config_file.with_name(f"{self.config_file.stem}.corrupt-{stamp}.json")
            seq = 1
            while dst.exists():
                dst = self.config_file.with_name(f"{self.config_file.stem}.corrupt-{stamp}_{seq}.json")
                seq += 1
            dst.write_bytes(self.config_file.read_bytes())
            return dst
        except OSError as exc:
            logger.error(f"[云存储] 留档损坏配置失败：{exc}")
            return None

    def _save_config(self) -> bool:
        """保存配置（敏感字段加密后原子落盘）。返回是否成功。

        M-4：旧实现是裸 `open(..., "w")` + `json.dump`，写入中途被杀会留下
        截断文件 —— 下次启动就命中 M-3。现在复用 `atomic_write_json`：
        临时文件 + `os.replace`，并在替换前施加 `0600`。
        """
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            config_to_save = self._transform_config(self.config, decrypt=False)
            atomic_write_json(self.config_file, config_to_save, indent=2, mode=0o600, backup=True)
            return True
        except OSError as exc:
            logger.error(f"[云存储] 保存配置失败：{exc}")
            return False

    def _transform_config(self, config: Dict, decrypt: bool) -> Dict:
        """递归加密/解密配置中的敏感字段。

        🔴 **任何失败路径都不得回落到明文**（S8）：
        旧实现在加密后端不可用、或单字段加密抛异常时直接 `result[key] = value`，
        于是 `cloud_config.json` 会静静出现 `"access_token": "..."` 明文 ——
        用户以为"已加密"，直到文件被同步/备份/上传才暴露。
        现在的策略是：**宁可写空（用户需重新填写），也不落明文**。
        """
        if not self._secure_config:
            if decrypt:
                # 读盘：没有加密后端就无法解密，原样返回（供本次运行使用）
                return config
            logger.warning(
                "[云存储] 加密组件不可用：本次保存不会写入任何云盘凭据（避免明文落盘），"
                "请修复 cryptography / SecureConfig 后重新填写。"
            )
            return self._blank_sensitive(config)

        result = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = self._transform_config(value, decrypt)
            elif key in self._SENSITIVE_FIELDS and isinstance(value, str) and value:
                try:
                    if decrypt:
                        result[key] = self._secure_config._decrypt(value) or ""
                    else:
                        result[key] = self._secure_config._encrypt(value)
                except Exception as exc:  # noqa: BLE001 - 单字段失败不该中断整份配置
                    logger.warning(f"[云存储] 字段 {key} {'解密' if decrypt else '加密'}失败：{exc}")
                    # 写盘失败 ⇒ 留空；读盘失败 ⇒ 也留空（无法解密的值没有意义）
                    result[key] = ""
            else:
                result[key] = value
        return result

    def _blank_sensitive(self, config: Dict) -> Dict:
        """返回一份敏感字段被清空的副本（**不修改入参**）。"""
        result = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = self._blank_sensitive(value)
            elif key in self._SENSITIVE_FIELDS and isinstance(value, str) and value:
                result[key] = ""
            else:
                result[key] = value
        return result

    # ------------------------------------------------------------------ Provider

    def _init_providers(self):
        for provider_id, provider_info in self.PROVIDERS.items():
            provider_config = self.config.get(provider_id, {})
            if provider_config:
                provider_class = provider_info["class"]
                self.providers[provider_id] = provider_class(provider_config)

    def get_provider(self, provider_id: str) -> Optional[CloudProvider]:
        return self.providers.get(provider_id)

    def get_available_providers(self) -> List[Dict]:
        available = []
        for provider_id, provider_info in self.PROVIDERS.items():
            provider = self.providers.get(provider_id)
            available.append(
                {
                    "id": provider_id,
                    "name": provider_info["name"],
                    "configured": provider_id in self.config,
                    "connected": provider.connected if provider else False,
                    "recursive_listing": bool(getattr(provider, "supports_recursive_listing", False)),
                }
            )
        return available

    def configure_provider(self, provider_id: str, config: Dict) -> bool:
        """配置云存储提供商。返回配置是否**成功落盘**。

        ❗ 返回值有意义：加密不可用时 `_save_config()` 会返回 False，
        调用方据此提示"凭据未被保存"，而不是假装成功。
        """
        self.config[provider_id] = config
        saved = self._save_config()
        # 重新初始化提供商（旧实例先释放连接）
        old = self.providers.pop(provider_id, None)
        if old is not None:
            old.close()
        provider_info = self.PROVIDERS.get(provider_id)
        if provider_info:
            self.providers[provider_id] = provider_info["class"](config)
        return saved

    def connect_provider(self, provider_id: str) -> bool:
        provider = self.providers.get(provider_id)
        if provider:
            return provider.connect()
        return False

    def close(self) -> None:
        """释放所有 Provider 的连接（L-4）。"""
        for provider in self.providers.values():
            provider.close()

    # ------------------------------------------------------------------ 上传

    def upload_novel(self, novel_dir: Path, provider_id: str, remote_path: str = "/AI_NovelWriter") -> bool:
        """上传整个作品目录。只有**全部文件成功**才返回 True（附带修复）。"""
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False

        novel_dir = Path(novel_dir)
        try:
            provider.create_folder(remote_path)
            failed: List[str] = []
            for file in novel_dir.rglob("*"):
                if not file.is_file():
                    continue
                relative_path = file.relative_to(novel_dir).as_posix()
                remote_file = f"{remote_path}/{relative_path}"
                if not provider.upload(file, remote_file):
                    failed.append(relative_path)
            if failed:
                logger.warning(f"[云存储] {len(failed)} 个文件上传失败，首个：{failed[0]}")
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("上传小说失败", e))
            return False

    # ------------------------------------------------------------------ 列举

    def remote_index(
        self, provider: CloudProvider, remote_path: str, max_depth: int = _MAX_TRAVERSE_DEPTH
    ) -> Dict[str, int]:
        """递归列出远端文件，返回 `{相对路径: 大小}`。

        - WebDAV（路径式）真的递归；
        - id 式厂商（百度/夸克/迅雷/阿里）的 `list_files` 只列一层且以 id 为父，
          递归没有意义 ⇒ 只返回根层，`sync_novel` 会退回本地清单比对。
        """
        index: Dict[str, int] = {}

        def walk(path: str, prefix: str, depth: int) -> None:
            if depth > max_depth:
                logger.warning(f"[云存储] 远端目录层级超过 {max_depth}，停止遍历：{path}")
                return
            for info in provider.list_files(path):
                name = provider.file_name(info)
                if not name:
                    continue
                rel = f"{prefix}{name}"
                if provider.is_dir(info):
                    walk(f"{path.rstrip('/')}/{name}", f"{rel}/", depth + 1)
                else:
                    index[rel] = provider.file_size(info)

        walk(remote_path.rstrip("/") or "/", "", 0)
        return index

    # ------------------------------------------------------------------ 下载

    def download_novel(self, remote_path: str, local_dir: Path, provider_id: str) -> bool:
        """从云端下载整个目录到 `local_dir`。

        🔴 **H-1**：远端返回的名字一律经 `_safe_local_target()` 归一化。
        旧实现是 `local_dir / file_info.get("name", "")`，实测 `../../victim.txt`
        可覆盖目录外的任意可写文件。

        另加递归深度上限（`_MAX_TRAVERSE_DEPTH`），防远端返回自引用目录。
        只有全部文件成功才返回 True（附带修复：旧实现无脑返回 True）。
        """
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False
        base = Path(local_dir)
        root = base.resolve()
        failures: List[str] = []

        def walk(path: str, target_dir: Path, depth: int) -> None:
            if depth > _MAX_TRAVERSE_DEPTH:
                logger.warning(f"[云存储] 下载层级超过 {_MAX_TRAVERSE_DEPTH}，停止：{path}")
                return
            # ❗ 每一层都要对**根目录**复核，而不是对"当前目录自己"复核
            # （后者恒为真，等于没检查）。防的是符号链接把子目录指向根之外。
            if not Path(target_dir).resolve().is_relative_to(root):
                logger.warning(f"[云存储] 目标目录越出作品根，已跳过：{target_dir}")
                failures.append(str(target_dir))
                return
            base_resolved = Path(target_dir).resolve()
            for info in provider.list_files(path):
                name = provider.file_name(info)
                if not name:
                    continue
                if provider.is_dir(info):
                    child = _safe_local_target(base_resolved, name)
                    if child is None:
                        logger.warning(f"[云存储] 跳过可疑目录名（可能越界）：{name!r}")
                        failures.append(name)
                        continue
                    if not child.resolve().is_relative_to(root):
                        logger.warning(f"[云存储] 目录越出作品根，已跳过：{name!r}")
                        failures.append(name)
                        continue
                    child.mkdir(parents=True, exist_ok=True)
                    walk(f"{path.rstrip('/')}/{name}", child, depth + 1)
                else:
                    local_file = _safe_local_target(base_resolved, name)
                    if local_file is None:
                        logger.warning(f"[云存储] 跳过可疑文件名（可能越界）：{name!r}")
                        failures.append(name)
                        continue
                    remote_file = f"{path.rstrip('/')}/{name}"
                    if not provider.download(remote_file, local_file):
                        failures.append(name)

        try:
            walk(remote_path, base, 0)
            if failures:
                logger.warning(f"[云存储] 下载完成但有 {len(failures)} 个条目失败/跳过，首个：{failures[0]}")
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("下载小说失败", e))
            return False

    # ------------------------------------------------------------------ 同步

    def _manifest_path(self, novel_dir: Path) -> Path:
        return Path(novel_dir) / self._MANIFEST_NAME

    def _load_manifest(self, novel_dir: Path) -> Dict[str, Dict]:
        try:
            with open(self._manifest_path(novel_dir), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_manifest(self, novel_dir: Path, manifest: Dict[str, Dict]) -> None:
        try:
            atomic_write_json(self._manifest_path(novel_dir), manifest, indent=2)
        except OSError as exc:
            logger.debug(f"[云存储] 写同步清单失败（不影响本次同步）：{exc}")

    def sync_novel(self, novel_dir: Path, provider_id: str, remote_path: str = "/AI_NovelWriter") -> bool:
        """增量同步到云端：只上传"新增或大小/mtime 变化"的文件（M-6）。

        旧实现用**非递归**的根目录列表建索引，却拿**相对路径**（含子目录）去查，
        子目录文件永远查不到 ⇒ 每次都会重传 `chapters/`、`memory/` 等全部文件。

        现在的判定顺序：
        1. 远端支持递归列举（WebDAV）⇒ 用远端大小比对；
        2. 否则用本地清单 `.cloud_sync.json` 记录 `{relpath: {size, mtime}}`。
        两者都拿不到时才上传（宁可多传，不可漏传）。
        """
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False

        novel_dir = Path(novel_dir)
        try:
            remote_index: Dict[str, int] = {}
            if getattr(provider, "supports_recursive_listing", False):
                remote_index = self.remote_index(provider, remote_path)
            manifest = self._load_manifest(novel_dir)
            new_manifest: Dict[str, Dict] = {}
            failed: List[str] = []

            for file in novel_dir.rglob("*"):
                if not file.is_file() or file.name == self._MANIFEST_NAME:
                    continue
                rel = file.relative_to(novel_dir).as_posix()
                stat = file.stat()
                record = {"size": stat.st_size, "mtime": int(stat.st_mtime)}
                new_manifest[rel] = record

                if remote_index:
                    needs = remote_index.get(rel) != record["size"]
                else:
                    previous = manifest.get(rel)
                    needs = previous != record
                if not needs:
                    continue

                if not provider.upload(file, f"{remote_path}/{rel}"):
                    failed.append(rel)

            self._save_manifest(novel_dir, new_manifest)
            if failed:
                logger.warning(f"[云存储] {len(failed)} 个文件同步失败，首个：{failed[0]}")
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(_safe_error("同步小说失败", e))
            return False
