"""MCP（Model Context Protocol）支持（v3.2 新增）。

## 先澄清一件容易误解的事

本仓 **早就有 MCP 形状的内部约定**，只是没有 MCP 传输层：

| 已有 | 位置 | 说明 |
|---|---|---|
| `AgentMessage` | `novel_agent.py:197` | 注释就写着"参考MCP协议" |
| `Tool` / `ToolRegistry` | `novel_agent.py:220/240` | 有 `input_schema`、有 `list_tools(agent_type)` / `call(tool_name, **kwargs)` |
| `MessageRole` | `novel_agent.py:187` | 含 `TOOL` 角色 |

所以本模块**不重新发明工具系统**，而是：

> 把已有的 `Tool` / `ToolRegistry` **接到真正的 MCP 线路上** ——
> 一边是 **客户端**（连外部 MCP server，把它的工具变成本应用可调用的工具），
> 一边是 **服务端**（把本应用自己的工具按 MCP 规范暴露出去）。

这正是"接线"而不是"又一次注册即遗忘"：如果没有真实消费者，
本模块会和被删掉的 `plugin_system.py` 一样，只是又一个漂亮的空壳。

## 设计约束（与仓内既有惯例对齐）

1. **注册表驱动** —— 支持的传输方式与 JSON-RPC 方法各有一张表，
   新增一种传输 / 一个方法只改表一处（同 `PLUGIN_TYPES` / `ProviderRegistry`）。
2. **结构化结果** —— `MCPResult`（`ok` / `message` / `detail` / `as_dict()`），
   仿 `BalanceResult` / `PluginResult` / `ImageGenResult`。
3. **路径唯一来源** —— `default_servers_file()`；别在面板或 UI 里再拼一次。
4. **懒加载 + 失败即降级** —— `get_mcp_manager()` 构造失败返回 `None`，
   绝不让 MCP 不可用拖垮应用启动。
5. **不阻塞界面** —— 连外部 server 要起进程 / 发网络请求，全部走 `BackgroundRunner`。

## 安全边界（不承诺做不到的事）

MCP server 有两种来源，风险完全不同，必须分开说：

- **stdio server**：本应用会**启动一个本地进程**（`command` + `args`）。
  它和插件一样是"以本应用同等权限运行的代码"。本模块能做的是：
  把要执行的命令行**在启用前原文展示**、默认**不启用**、
  启用状态持久化以便审计 —— **不能**沙箱化它。
- **HTTP server**：一次出网请求。会带上你在配置里写的 headers
  （可能含 API Key）—— 面板必须**明确提示**这一点。

结论：本模块的定位是**让"将执行什么"变得可见**，而不是"让不可信 server 变安全"。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

__all__ = [
    "TRANSPORTS",
    "TRANSPORT_LABELS",
    "JSONRPC_METHODS",
    "MCP_PROTOCOL_VERSION",
    "MCPResult",
    "MCPToolInfo",
    "MCPServerSpec",
    "MCPClient",
    "MCPServer",
    "MCPManager",
    "default_servers_file",
    "sanitize_server_name",
    "parse_sse_payload",
    "extract_rpc_result",
    "build_initialize_params",
    "build_tools_list_params",
    "build_tools_call_params",
    "get_mcp_manager",
    "reset_mcp_manager",
]

#: MCP 协议版本（2024-11-05 是当前被广泛实现的一版）。
MCP_PROTOCOL_VERSION = "2024-11-05"

#: 支持的传输方式 → 说明（「新增一种传输只改这里一处」）。
TRANSPORTS: dict[str, str] = {
    "stdio": "本地进程（command + args，走标准输入输出）",
    "http": "远程 HTTP 服务（JSON-RPC over HTTP）",
}

TRANSPORT_LABELS: dict[str, str] = dict(TRANSPORTS)

#: JSON-RPC 方法表：方法名 → (是否通知、默认超时秒)。
#: 与 `ProviderRegistry` 同构 —— 路由靠查表，不靠 if/elif 长链。
JSONRPC_METHODS: dict[str, dict[str, Any]] = {
    "initialize": {"notification": False, "timeout": 15.0, "desc": "握手，协商协议版本与能力"},
    "notifications/initialized": {"notification": True, "timeout": 5.0, "desc": "握手完成通知"},
    "tools/list": {"notification": False, "timeout": 20.0, "desc": "列出服务端可用工具"},
    "tools/call": {"notification": False, "timeout": 120.0, "desc": "调用服务端某个工具"},
    "ping": {"notification": False, "timeout": 10.0, "desc": "连通性探测"},
}

#: 服务器名白名单：字母 / 数字 / 中文 / 下划线 / 连字符 / 点。
_SERVER_NAME_PATTERN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


#: 单次 stdio 调用的最大等待秒数（超过判定为挂死并 kill）。
_STDIO_CALL_TIMEOUT = 120.0

#: 读取一行响应的上限（防止服务端狂刷输出撑爆内存）。
_MAX_LINE_BYTES = 8 * 1024 * 1024


def default_servers_file() -> Path:
    """MCP 服务器配置文件的唯一来源 —— 别在别处再拼一次这个路径。"""
    return Path.home() / ".ai_novel_writer" / "mcp_servers.json"


def sanitize_server_name(name: str) -> Optional[str]:
    """校验服务器名：非空、≤64、只含白名单字符、不以下划线/点开头。

    返回清洗后的名字，非法返回 `None`。
    """
    if not name:
        return None
    cleaned = name.strip()
    if not cleaned or len(cleaned) > 64:
        return None
    if cleaned.startswith(".") or cleaned.startswith("_"):
        return None
    if any(ch not in _SERVER_NAME_PATTERN_CHARS and not ("\u4e00" <= ch <= "\u9fff") for ch in cleaned):
        return None
    return cleaned


def parse_sse_payload(text: str) -> Optional[dict]:
    """从 SSE 风格的响应体里取出第一条 JSON-RPC 消息。

    MCP 的 Streamable HTTP 传输会返回 `event: message\\ndata: {...}`。
    兼容三种形态：
    1. 纯 JSON（`{"jsonrpc": ...}`）
    2. 单条 SSE（`data: {...}`）
    3. 多行 SSE（取第一条带 `data:` 的行）

    取不到返回 `None`。
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    # 形态 1：纯 JSON
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
    # 形态 2/3：SSE
    for line in stripped.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def extract_rpc_result(message: dict) -> tuple[bool, Any, str]:
    """把一条 JSON-RPC 响应拆成 `(ok, result, error_text)`。

    这是**唯一**的判据点 —— 别在客户端各方法里各写一遍。
    """
    if not isinstance(message, dict):
        return False, None, "响应不是 JSON 对象"
    if "error" in message and message["error"]:
        err = message["error"]
        if isinstance(err, dict):
            text = f"{err.get('code', '?')}: {err.get('message', '未知错误')}"
        else:
            text = str(err)
        return False, None, text
    if "result" not in message:
        return False, None, "响应缺少 result 字段"
    return True, message["result"], ""


def build_initialize_params(client_name: str = "ai-novel-writer") -> dict:
    """构造 `initialize` 请求参数。"""
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "clientInfo": {"name": client_name, "version": "1.0"},
    }


def build_tools_list_params(cursor: str = "") -> dict:
    """构造 `tools/list` 请求参数（cursor 为空则不带分页字段）。"""
    params: dict[str, Any] = {}
    if cursor:
        params["cursor"] = cursor
    return params


def build_tools_call_params(tool_name: str, arguments: Optional[dict] = None) -> dict:
    """构造 `tools/call` 请求参数。"""
    return {"name": tool_name, "arguments": dict(arguments or {})}


@dataclass
class MCPResult:
    """MCP 操作结果（结构化）。

    仿 `BalanceResult` / `PluginResult`：界面能直接展示"为什么失败"，
    而不是只拿到一个 `None` 或一句异常字符串。
    """

    ok: bool
    message: str = ""
    detail: dict = field(default_factory=dict)
    server: str = ""
    tool: str = ""

    @classmethod
    def success(cls, message: str = "", **detail: Any) -> "MCPResult":
        return cls(ok=True, message=message, detail=dict(detail))

    @classmethod
    def failed(cls, message: str, **detail: Any) -> "MCPResult":
        return cls(ok=False, message=message, detail=dict(detail))

    @classmethod
    def not_configured(cls, message: str = "未配置任何 MCP 服务器") -> "MCPResult":
        return cls(ok=False, message=message, detail={"reason": "not_configured"})

    @classmethod
    def timeout(cls, message: str, **detail: Any) -> "MCPResult":
        d = dict(detail)
        d["reason"] = "timeout"
        return cls(ok=False, message=message, detail=d)

    @property
    def reason(self) -> str:
        return str(self.detail.get("reason", "") or "")

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message": self.message,
            "detail": self.detail,
            "server": self.server,
            "tool": self.tool,
        }

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class MCPToolInfo:
    """一个 MCP 工具的描述（服务端返回的 `tools/list` 条目）。"""

    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    server: str = ""

    @classmethod
    def from_wire(cls, raw: dict, server: str = "") -> "MCPToolInfo":
        schema = raw.get("inputSchema") or raw.get("input_schema") or {}
        return cls(
            name=str(raw.get("name", "")),
            description=str(raw.get("description", "") or ""),
            input_schema=schema if isinstance(schema, dict) else {},
            server=server,
        )

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server": self.server,
        }


@dataclass
class MCPServerSpec:
    """一个 MCP 服务器的配置（来自 `mcp_servers.json` 的一条）。"""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list = field(default_factory=list)
    url: str = ""
    headers: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    enabled: bool = False
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "url": self.url,
            "headers": dict(self.headers),
            "env": dict(self.env),
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Optional["MCPServerSpec"]:
        if not isinstance(raw, dict):
            return None
        name = sanitize_server_name(str(raw.get("name", "")))
        if not name:
            return None
        transport = str(raw.get("transport", "stdio") or "stdio").strip().lower()
        if transport not in TRANSPORTS:
            transport = "stdio"
        args = raw.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        headers = raw.get("headers") or {}
        env = raw.get("env") or {}
        return cls(
            name=name,
            transport=transport,
            command=str(raw.get("command", "") or ""),
            args=[str(a) for a in args],
            url=str(raw.get("url", "") or ""),
            headers=dict(headers) if isinstance(headers, dict) else {},
            env=dict(env) if isinstance(env, dict) else {},
            enabled=bool(raw.get("enabled", False)),
            description=str(raw.get("description", "") or ""),
        )

    def is_usable(self) -> tuple[bool, str]:
        """这条配置是否足以发起连接（不实际连）。"""
        if self.transport == "stdio":
            if not self.command:
                return False, "stdio 传输缺少 command"
            if shutil.which(self.command) is None and not os.path.isabs(self.command):
                return False, f"找不到可执行文件：{self.command}"
            return True, ""
        if self.transport == "http":
            if not self.url:
                return False, "http 传输缺少 url"
            if not (self.url.startswith("http://") or self.url.startswith("https://")):
                return False, "url 必须以 http:// 或 https:// 开头"
            return True, ""
        return False, f"未知传输方式：{self.transport}"

    def command_line(self) -> str:
        """给用户看的、将被执行的完整命令行（用于启用前展示）。"""
        if self.transport != "stdio":
            return self.url
        parts = [self.command] + list(self.args)
        return " ".join(p if " " not in p else f'"{p}"' for p in parts)


class _JsonRpcError(Exception):
    """内部：一次 JSON-RPC 往返失败。"""


class MCPClient:
    """连一个 MCP 服务器。

    两种传输：

    - `stdio`：起本地进程，按行读写 JSON-RPC（MCP 的标准 stdio 传输）。
    - `http`：POST JSON-RPC 到 `url`，响应体可能是纯 JSON 或 SSE。

    **每次调用起一个短命连接，用完即关**。理由：MCP server 的常驻连接
    需要处理进程僵死、管道半闭、并发复用等一堆状态；本应用对 MCP 的调用
    是**低频**的（列工具 / 按需调工具），短命连接的实现复杂度和故障面都小得多。
    """

    def __init__(self, spec: MCPServerSpec, log: Callable[[str], None] = None):
        self.spec = spec
        self._log = log or (lambda _m: None)
        self._counter = 0
        self._lock = threading.Lock()

    # ---------- JSON-RPC 信封 ----------

    def _next_id(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def _envelope(self, method: str, params: Optional[dict]) -> dict:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not JSONRPC_METHODS.get(method, {}).get("notification", False):
            msg["id"] = self._next_id()
        return msg

    def _timeout_for(self, method: str) -> float:
        return float(JSONRPC_METHODS.get(method, {}).get("timeout", 30.0))

    # ---------- stdio ----------

    def _call_stdio(self, method: str, params: Optional[dict]) -> dict:
        cmd = [self.spec.command] + list(self.spec.args)
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (self.spec.env or {}).items()})
        payload = self._envelope(method, params)
        if JSONRPC_METHODS.get(method, {}).get("notification", False):
            # 通知：发完即走，不等响应
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                )
                proc.communicate(json.dumps(payload, ensure_ascii=False) + "\n", timeout=5.0)
            except Exception as e:  # noqa: BLE001 - 通知失败不影响主流程
                self._log(f"[MCP] 通知 {method} 发送失败：{e}")
            return {}
        # ❗ 起进程本身会失败（命令不存在、没有执行权限、路径含非法字符）。
        # 不在这里兜住的话，`FileNotFoundError` 会一路冒到调用方 ——
        # 而调用方（面板）已经把它当"结构化结果"处理了。
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except (OSError, ValueError) as e:
            raise _JsonRpcError(f"无法启动 {self.spec.command}：{e}") from None
        try:
            stdout, stderr = proc.communicate(
                json.dumps(payload, ensure_ascii=False) + "\n",
                timeout=self._timeout_for(method),
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise _JsonRpcError(f"{method} 超时（>{self._timeout_for(method):.0f}s）") from None
        finally:
            if proc.poll() is None:
                proc.kill()
        if len(stdout or "") > _MAX_LINE_BYTES:
            raise _JsonRpcError("服务端输出超过 8MB，已中止")
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and ("result" in message or "error" in message):
                return message
        detail = (stderr or "").strip()[:400]
        raise _JsonRpcError("服务端未返回有效 JSON-RPC 响应" + (f"（stderr: {detail}）" if detail else ""))

    # ---------- http ----------

    def _call_http(self, method: str, params: Optional[dict]) -> dict:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover - httpx 是运行依赖
            raise _JsonRpcError(f"缺少 httpx，无法走 HTTP 传输：{e}") from None
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update({str(k): str(v) for k, v in (self.spec.headers or {}).items()})
        payload = self._envelope(method, params)
        timeout = self._timeout_for(method)
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(self.spec.url, json=payload, headers=headers)
        except Exception as e:  # noqa: BLE001 - 统一转成内部异常
            raise _JsonRpcError(f"HTTP 请求失败：{e}") from None
        if response.status_code >= 400:
            raise _JsonRpcError(f"HTTP {response.status_code}：{response.text[:200]}")
        message = parse_sse_payload(response.text)
        if message is None:
            raise _JsonRpcError(f"响应无法解析为 JSON-RPC：{response.text[:200]}")
        return message

    # ---------- 公开 API ----------

    def call(self, method: str, params: Optional[dict] = None) -> MCPResult:
        """发起一次 JSON-RPC 往返，返回结构化结果。"""
        if method not in JSONRPC_METHODS:
            return MCPResult.failed(
                f"未登记的 MCP 方法：{method}",
                reason="unknown_method",
                known=sorted(JSONRPC_METHODS),
            )
        try:
            if self.spec.transport == "stdio":
                message = self._call_stdio(method, params)
            elif self.spec.transport == "http":
                message = self._call_http(method, params)
            else:
                return MCPResult.failed(f"未知传输方式：{self.spec.transport}", reason="bad_transport")
        except _JsonRpcError as e:
            text = str(e)
            if "超时" in text:
                return MCPResult.timeout(text, method=method)
            return MCPResult.failed(text, reason="rpc_error", method=method)
        ok, result, err = extract_rpc_result(message)
        if not ok:
            return MCPResult.failed(err, reason="rpc_error", method=method)
        out = MCPResult.success(f"{method} 成功", method=method, result=result)
        return out

    def initialize(self) -> MCPResult:
        """握手：协商协议版本与能力。"""
        res = self.call("initialize", build_initialize_params())
        if not res.ok:
            return res
        # 按 MCP 规范补一条 initialized 通知（失败不致命）
        self.call("notifications/initialized", None)
        info = (res.detail.get("result") or {}) if isinstance(res.detail.get("result"), dict) else {}
        server_info = info.get("serverInfo") if isinstance(info, dict) else None
        res.message = f"已连接 {self.spec.name}"
        if isinstance(server_info, dict) and server_info.get("name"):
            res.detail["server_info"] = server_info
            res.message = f"已连接 {server_info.get('name')}"
        return res

    def list_tools(self) -> MCPResult:
        """列出服务端工具，结果里带 `tools`（`MCPToolInfo` 列表）。"""
        res = self.call("tools/list", build_tools_list_params())
        if not res.ok:
            return res
        raw = res.detail.get("result") or {}
        items = raw.get("tools") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            items = []
        tools = [MCPToolInfo.from_wire(item, server=self.spec.name) for item in items if isinstance(item, dict)]
        res.detail["tools"] = tools
        res.message = f"发现 {len(tools)} 个工具"
        return res

    def call_tool(self, tool_name: str, arguments: Optional[dict] = None) -> MCPResult:
        """调用服务端的一个工具。"""
        if not tool_name:
            return MCPResult.failed("工具名不能为空", reason="bad_argument")
        res = self.call("tools/call", build_tools_call_params(tool_name, arguments))
        if not res.ok:
            res.tool = tool_name
            return res
        res.tool = tool_name
        raw = res.detail.get("result") or {}
        # MCP 工具结果有两种形态：直接内容列表，或 {"content": [...], "isError": bool}
        if isinstance(raw, dict):
            res.detail["is_error"] = bool(raw.get("isError", False))
            res.message = self._render_content(raw.get("content"))
        res.detail["raw"] = raw
        return res

    @staticmethod
    def _render_content(content: Any) -> str:
        """把 MCP 的 content 列表渲染成人类可读文本。"""
        if not content:
            return "（无内容）"
        if isinstance(content, str):
            return content
        chunks = []
        for block in content if isinstance(content, list) else [content]:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    chunks.append(str(block.get("text", "")))
                else:
                    chunks.append(json.dumps(block, ensure_ascii=False)[:500])
            else:
                chunks.append(str(block))
        return "\n".join(c for c in chunks if c) or "（无内容）"

    def ping(self) -> MCPResult:
        """连通性探测。"""
        return self.call("ping", None)


class MCPServer:
    """把本应用自己的 `ToolRegistry` 暴露成 MCP 服务端（进程内语义）。

    为什么要有服务端：只有"能连别人"是单向的 —— 那意味着本应用只能当消费者。
    有了服务端，`novel_agent` 注册的工具（`detect_scenes` / `get_characters` …）
    就能按标准 `tools/list` + `tools/call` 被**任何** MCP 客户端访问。

    本类**不绑定监听端口**（那会把桌面应用变成网络服务，安全面完全不同）。
    它只实现"收到一条 JSON-RPC 消息 → 回一条 JSON-RPC 消息"的纯函数语义，
    这样既可被进程内调用、也可在未来被任意传输层（stdio / http）挂载。
    """

    def __init__(self, registry, name: str = "ai-novel-writer", version: str = "1.0"):
        self.registry = registry
        self.name = name
        self.version = version

    def handle(self, message: dict) -> Optional[dict]:
        """处理一条 JSON-RPC 消息。

        规范：**通知（没有 id）不返回响应**（返回 `None`）。
        未知方法回 `-32601`（Method not found）—— 与 JSON-RPC 2.0 一致。
        """
        if not isinstance(message, dict):
            return self._error(None, -32600, "Invalid Request")
        msg_id = message.get("id")
        method = str(message.get("method", ""))
        params = message.get("params") or {}
        is_notification = "id" not in message or msg_id is None

        if method not in JSONRPC_METHODS:
            if is_notification:
                return None
            return self._error(msg_id, -32601, f"Method not found: {method}")

        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            }
            return None if is_notification else self._ok(msg_id, result)

        if method == "notifications/initialized":
            return None

        if method == "ping":
            return None if is_notification else self._ok(msg_id, {})

        if method == "tools/list":
            tools = self.registry.list_tools(None) if self.registry else []
            wire = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "inputSchema": t.get("input_schema") or {"type": "object", "properties": {}},
                }
                for t in tools
            ]
            return None if is_notification else self._ok(msg_id, {"tools": wire})

        if method == "tools/call":
            name = str(params.get("name", "")) if isinstance(params, dict) else ""
            arguments = params.get("arguments") if isinstance(params, dict) else {}
            if not isinstance(arguments, dict):
                arguments = {}
            if not self.registry:
                return self._error(msg_id, -32603, "本应用无可暴露的工具注册中心")
            outcome = self.registry.call(name, **arguments)
            if not outcome.get("success"):
                # 工具不存在 → 按 MCP 语义回 isError 的内容，而不是协议错误
                text = str(outcome.get("error", "未知错误"))
                return self._ok(
                    msg_id,
                    {"content": [{"type": "text", "text": text}], "isError": True},
                )
            payload = outcome.get("result")
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
            return self._ok(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})

        return self._error(msg_id, -32601, f"Method not implemented: {method}")

    @staticmethod
    def _ok(msg_id: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


class MCPManager:
    """MCP 服务器集合的管理器：读配置 / 启停 / 列工具 / 调工具。

    配置文件（`default_servers_file()`）形如：

    ```json
    {
      "servers": [
        {"name": "filesystem", "transport": "stdio",
         "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
         "enabled": true},
        {"name": "remote", "transport": "http", "url": "https://example.com/mcp",
         "headers": {"Authorization": "Bearer xxx"}, "enabled": false}
      ]
    }
    ```
    """

    def __init__(self, servers_file: Optional[Path] = None, log: Callable[[str], None] = None):
        self.servers_file = Path(servers_file) if servers_file else default_servers_file()
        self._log = log or (lambda _m: None)
        self._specs: dict[str, MCPServerSpec] = {}
        self._tool_cache: dict[str, list[MCPToolInfo]] = {}
        self._load()

    # ---------- 配置读写 ----------

    def _load(self) -> None:
        """读配置文件。文件不存在 / 损坏都不抛 —— MCP 不可用不该拖垮启动。"""
        self._specs = {}
        if not self.servers_file.exists():
            return
        try:
            raw = json.loads(self.servers_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._log(f"[MCP] 配置文件无法读取，已忽略：{e}")
            return
        entries = raw.get("servers") if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            self._log("[MCP] 配置文件格式不对（期望 servers 数组），已忽略")
            return
        for item in entries:
            spec = MCPServerSpec.from_dict(item)
            if spec is None:
                continue
            self._specs[spec.name] = spec

    def save(self) -> MCPResult:
        """把当前配置写回磁盘（原子写：先写临时文件再替换）。"""
        payload = {"servers": [spec.as_dict() for spec in self._specs.values()]}
        try:
            self.servers_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.servers_file.with_suffix(self.servers_file.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.servers_file)
        except OSError as e:
            return MCPResult.failed(f"保存失败：{e}", reason="io_error")
        return MCPResult.success(f"已保存 {len(self._specs)} 个服务器配置")

    def reload(self) -> MCPResult:
        self._load()
        self._tool_cache.clear()
        return MCPResult.success(f"已重新加载 {len(self._specs)} 个服务器配置")

    # ---------- 查询 / 启停 ----------

    def all_servers(self) -> list[MCPServerSpec]:
        return list(self._specs.values())

    def get(self, name: str) -> Optional[MCPServerSpec]:
        return self._specs.get(name)

    def enabled_servers(self) -> list[MCPServerSpec]:
        return [spec for spec in self._specs.values() if spec.enabled]

    def add_server(self, spec: MCPServerSpec) -> MCPResult:
        """新增 / 覆盖一个服务器配置。"""
        if spec is None or not spec.name:
            return MCPResult.failed("服务器名非法", reason="bad_argument")
        existed = spec.name in self._specs
        self._specs[spec.name] = spec
        self._tool_cache.pop(spec.name, None)
        res = self.save()
        if not res.ok:
            return res
        return MCPResult.success(
            f"{'已更新' if existed else '已添加'}服务器 {spec.name}",
            name=spec.name,
            updated=existed,
        )

    def remove_server(self, name: str) -> MCPResult:
        if name not in self._specs:
            return MCPResult.failed(f"没有名为 {name} 的服务器", reason="not_found")
        self._specs.pop(name, None)
        self._tool_cache.pop(name, None)
        res = self.save()
        if not res.ok:
            return res
        return MCPResult.success(f"已删除服务器 {name}", name=name)

    def set_enabled(self, name: str, enabled: bool) -> MCPResult:
        spec = self._specs.get(name)
        if spec is None:
            return MCPResult.failed(f"没有名为 {name} 的服务器", reason="not_found")
        if enabled:
            usable, why = spec.is_usable()
            if not usable:
                return MCPResult.failed(f"无法启用：{why}", reason="not_usable", name=name)
        spec.enabled = bool(enabled)
        res = self.save()
        if not res.ok:
            return res
        if not enabled:
            self._tool_cache.pop(name, None)
        return MCPResult.success(f"{'已启用' if enabled else '已停用'} {name}", name=name, enabled=bool(enabled))

    # ---------- 连接 / 调用 ----------

    def client_for(self, name: str) -> Optional[MCPClient]:
        spec = self._specs.get(name)
        if spec is None:
            return None
        return MCPClient(spec, log=self._log)

    def test_connection(self, name: str) -> MCPResult:
        """握手测试（不起长连接，用完即关）。"""
        client = self.client_for(name)
        if client is None:
            return MCPResult.failed(f"没有名为 {name} 的服务器", reason="not_found")
        res = client.initialize()
        res.server = name
        if res.ok:
            listing = client.list_tools()
            if listing.ok:
                tools = listing.detail.get("tools") or []
                self._tool_cache[name] = tools
                res.detail["tool_count"] = len(tools)
                res.message = f"连接成功，共 {len(tools)} 个工具"
        return res

    def list_tools(self, name: str, *, use_cache: bool = True) -> MCPResult:
        """列出某个 server 的工具（默认走缓存，避免每次开面板都拉一遍）。"""
        if use_cache and name in self._tool_cache:
            tools = self._tool_cache[name]
            return MCPResult.success(f"发现 {len(tools)} 个工具（缓存）", tools=tools, cached=True)
        client = self.client_for(name)
        if client is None:
            return MCPResult.failed(f"没有名为 {name} 的服务器", reason="not_found")
        res = client.list_tools()
        res.server = name
        if res.ok:
            self._tool_cache[name] = res.detail.get("tools") or []
        return res

    def call_tool(self, server: str, tool_name: str, arguments: Optional[dict] = None) -> MCPResult:
        """调用某个 server 的工具。"""
        client = self.client_for(server)
        if client is None:
            return MCPResult.failed(f"没有名为 {server} 的服务器", reason="not_found")
        res = client.call_tool(tool_name, arguments)
        res.server = server
        return res

    def list_all_tools(self, *, use_cache: bool = True) -> MCPResult:
        """把**所有已启用** server 的工具汇总成一张扁平列表（面板与 Agent 共用）。"""
        enabled = self.enabled_servers()
        if not enabled:
            return MCPResult.not_configured("没有已启用的 MCP 服务器")
        rows: list[MCPToolInfo] = []
        failures: list[dict] = []
        for spec in enabled:
            res = self.list_tools(spec.name, use_cache=use_cache)
            if not res.ok:
                failures.append({"server": spec.name, "error": res.message})
                continue
            rows.extend(res.detail.get("tools") or [])
        detail: dict[str, Any] = {"tools": rows, "failures": failures}
        if not rows and failures:
            return MCPResult.failed(
                f"{len(failures)} 个服务器连接失败",
                reason="all_failed",
                **detail,
            )
        msg = f"共 {len(rows)} 个 MCP 工具（来自 {len(enabled)} 个服务器）"
        if failures:
            msg += f"，{len(failures)} 个失败"
        return MCPResult.success(msg, **detail)

    def clear_cache(self) -> None:
        self._tool_cache.clear()


# ---------- 模块级单例（懒加载 + 失败即降级） ----------

_manager: Optional[MCPManager] = None


def get_mcp_manager() -> Optional[MCPManager]:
    """拿到全局管理器；构造失败返回 `None`（绝不抛）。

    懒加载 + 吞异常，和 `get_plugin_manager()` 同一策略 ——
    MCP 不可用只是少一个功能，不该让应用起不来。
    """
    global _manager
    if _manager is None:
        try:
            _manager = MCPManager()
        except Exception as e:  # noqa: BLE001 - 见 docstring
            logger.warning(f"[MCP] 管理器初始化失败：{e}")
            return None
    return _manager


def reset_mcp_manager() -> None:
    """清空单例（**仅供测试**：真实运行中不该有人调它）。"""
    global _manager
    _manager = None
