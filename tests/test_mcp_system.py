"""MCP 系统测试（v3.2）。

## 分层（与 `test_plugin_system.py` 同构，便于对照阅读）

1. **纯逻辑** —— 名称校验 / SSE 解析 / JSON-RPC 信封 / 结果对象。不需要任何外部进程。
2. **服务端** —— `MCPServer.handle()` 对每条 JSON-RPC 消息的应答，纯函数语义。
3. **客户端（真起进程）** —— 用一个**自己写的假 MCP server 脚本**当对端，
   走真实 stdio 管道。这是唯一能证明"stdio 传输真的能跑通"的层次。
4. **🔴 接线守卫** —— 本文件最重要的一层。功能被删要变红。
5. **真 Tk**（有显示环境才跑）—— 面板能建出来。

## 为什么守卫必须双向

只断言"生产代码里调了 `list_mcp_tools`"是不够的：
**把该函数的定义整个删掉，调用点仍在，测试照样过。**
所以还要反向断言"被调的东西确实存在"。
`TestWiringGuard.test_the_thing_being_called_still_exists` 就是这一条。

## 假 server 为什么写在临时目录

它要能被 `sys.executable` 执行，并且**不能**污染仓库 ——
所以用 `tmp_path` 落盘，并把被测进程的环境变量指过去。
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import _source_scan as _scan  # noqa: E402

from app import mcp_system as mcp  # noqa: E402
from app.panels import registry  # noqa: E402
from app.panels.mcp_panel import (  # noqa: E402
    MCPPanel,
    server_detail_lines,
    server_rows,
    tool_rows,
    transport_summary,
)

REPO_ROOT = Path(__file__).parent.parent


# ====================================================================== 假 MCP server

#: 一个最小的 stdio MCP server：读一行 JSON-RPC，回一行 JSON-RPC。
#: 故意**不复用**被测代码 —— 否则就是"用被测代码验证被测代码"。
FAKE_SERVER = """\
import json
import sys


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-server", "version": "9.9"},
        }}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo", "description": "回显输入",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
            {"name": "boom", "description": "必定失败的工具", "inputSchema": {}},
        ]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "echo":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}],
                "isError": False,
            }}
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": "没有这个工具：" + str(name)}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "Method not found: " + str(method)}}


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        message = json.loads(line)
    except ValueError:
        continue
    reply = handle(message)
    if reply is not None:
        sys.stdout.write(json.dumps(reply) + "\\n")
        sys.stdout.flush()
"""

#: 一个**故意出错**的 server：直接往 stderr 写东西然后退出。
BROKEN_SERVER = """\
import sys
sys.stderr.write("我起不来\\n")
sys.exit(3)
"""

#: 一个**挂死**的 server：读一行后什么都不做，等着被 kill。
HANGING_SERVER = """\
import time
import sys
for _line in sys.stdin:
    time.sleep(600)
"""


def _write_fake_server(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.fixture
def servers_file(tmp_path, monkeypatch):
    """把管理器指向临时配置文件（绝不碰用户真实的 ~/.ai_novel_writer）。"""
    monkeypatch.setattr(mcp, "_manager", None)
    return tmp_path / "mcp_servers.json"


@pytest.fixture
def manager(tmp_path, servers_file):
    return mcp.MCPManager(servers_file=servers_file)


def _stdio_spec(name: str, script: Path, *, enabled: bool = True, extra_args=None) -> mcp.MCPServerSpec:
    return mcp.MCPServerSpec(
        name=name,
        transport="stdio",
        command=sys.executable,
        args=[str(script)] + list(extra_args or []),
        enabled=enabled,
    )


# ====================================================================== 1. 纯逻辑


class TestSanitizeServerName:
    @pytest.mark.parametrize("name", ["filesystem", "my-server", "a.b", "中文名", "s1_2"])
    def test_accepts_valid(self, name):
        assert mcp.sanitize_server_name(name) == name

    @pytest.mark.parametrize(
        "name",
        ["", "   ", ".hidden", "_private", "a" * 65, "a/b", "a\\b", "a:b", "a b", "a$b"],
    )
    def test_rejects_invalid(self, name):
        assert mcp.sanitize_server_name(name) is None

    def test_strips_surrounding_whitespace(self):
        assert mcp.sanitize_server_name("  ok  ") == "ok"


class TestSseParsing:
    def test_plain_json(self):
        assert mcp.parse_sse_payload('{"jsonrpc": "2.0", "id": 1}') == {"jsonrpc": "2.0", "id": 1}

    def test_single_sse_line(self):
        text = 'event: message\ndata: {"jsonrpc": "2.0", "result": {"ok": true}}\n\n'
        assert mcp.parse_sse_payload(text)["result"] == {"ok": True}

    def test_multiple_sse_lines_takes_first_valid(self):
        text = 'data: not-json\ndata: {"a": 1}\ndata: {"b": 2}\n'
        assert mcp.parse_sse_payload(text) == {"a": 1}

    @pytest.mark.parametrize("text", ["", "   ", "garbage", "data: \n", "[1,2,3]"])
    def test_returns_none_when_unusable(self, text):
        assert mcp.parse_sse_payload(text) is None


class TestExtractRpcResult:
    def test_success(self):
        ok, result, err = mcp.extract_rpc_result({"jsonrpc": "2.0", "id": 1, "result": {"x": 1}})
        assert ok and result == {"x": 1} and err == ""

    def test_error_object(self):
        ok, _r, err = mcp.extract_rpc_result({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "nope"}})
        assert not ok and "-32601" in err and "nope" in err

    def test_missing_result(self):
        ok, _r, err = mcp.extract_rpc_result({"jsonrpc": "2.0", "id": 1})
        assert not ok and "result" in err

    def test_non_dict(self):
        ok, _r, err = mcp.extract_rpc_result("nope")
        assert not ok and err


class TestRequestBuilders:
    def test_initialize_params_has_protocol_version(self):
        params = mcp.build_initialize_params()
        assert params["protocolVersion"] == mcp.MCP_PROTOCOL_VERSION
        assert params["capabilities"]["tools"] == {}
        assert params["clientInfo"]["name"] == "ai-novel-writer"

    def test_tools_list_params_omits_empty_cursor(self):
        assert mcp.build_tools_list_params() == {}
        assert mcp.build_tools_list_params("abc") == {"cursor": "abc"}

    def test_tools_call_params_shape(self):
        assert mcp.build_tools_call_params("echo", {"text": "hi"}) == {
            "name": "echo",
            "arguments": {"text": "hi"},
        }
        assert mcp.build_tools_call_params("echo") == {"name": "echo", "arguments": {}}


class TestMCPResult:
    def test_success_and_truthiness(self):
        res = mcp.MCPResult.success("好了", n=1)
        assert res.ok and res and res.detail["n"] == 1 and res.as_dict()["ok"] is True

    def test_failed(self):
        res = mcp.MCPResult.failed("坏了", reason="x")
        assert not res.ok and not res and res.reason == "x"

    def test_not_configured_reason(self):
        assert mcp.MCPResult.not_configured().reason == "not_configured"

    def test_timeout_reason(self):
        res = mcp.MCPResult.timeout("超时了")
        assert res.reason == "timeout" and not res.ok


class TestServerSpec:
    def test_from_dict_roundtrip(self):
        spec = mcp.MCPServerSpec(name="s", transport="stdio", command="npx", args=["-y", "pkg"])
        again = mcp.MCPServerSpec.from_dict(spec.as_dict())
        assert again == spec

    def test_from_dict_rejects_bad_name(self):
        assert mcp.MCPServerSpec.from_dict({"name": "a/b"}) is None
        assert mcp.MCPServerSpec.from_dict("nope") is None

    def test_from_dict_normalises_transport(self):
        assert mcp.MCPServerSpec.from_dict({"name": "s", "transport": "WEIRD"}).transport == "stdio"
        assert mcp.MCPServerSpec.from_dict({"name": "s", "transport": "HTTP"}).transport == "http"

    def test_is_usable_requires_command(self):
        spec = mcp.MCPServerSpec(name="s", transport="stdio", command="")
        ok, why = spec.is_usable()
        assert not ok and "command" in why

    def test_is_usable_requires_absolute_or_on_path(self):
        spec = mcp.MCPServerSpec(name="s", transport="stdio", command="definitely-not-a-real-binary-xyz")
        ok, why = spec.is_usable()
        assert not ok and "找不到" in why

    def test_is_usable_accepts_existing_absolute_path(self):
        spec = mcp.MCPServerSpec(name="s", transport="stdio", command=sys.executable)
        assert spec.is_usable()[0]

    def test_http_requires_url_scheme(self):
        assert not mcp.MCPServerSpec(name="s", transport="http", url="example.com").is_usable()[0]
        assert mcp.MCPServerSpec(name="s", transport="http", url="https://example.com").is_usable()[0]

    def test_command_line_quotes_spaces(self):
        spec = mcp.MCPServerSpec(name="s", command="C:/Program Files/x.exe", args=["--a"])
        assert '"C:/Program Files/x.exe"' in spec.command_line()

    def test_command_line_returns_url_for_http(self):
        spec = mcp.MCPServerSpec(name="s", transport="http", url="https://x.example/mcp")
        assert spec.command_line() == "https://x.example/mcp"

    def test_tool_info_from_wire_accepts_both_schema_keys(self):
        a = mcp.MCPToolInfo.from_wire({"name": "t", "inputSchema": {"type": "object"}})
        b = mcp.MCPToolInfo.from_wire({"name": "t", "input_schema": {"type": "object"}})
        assert a.input_schema == b.input_schema == {"type": "object"}

    def test_tool_info_tolerates_missing_fields(self):
        info = mcp.MCPToolInfo.from_wire({})
        assert info.name == "" and info.input_schema == {}


# ====================================================================== 2. 服务端（纯函数）


class _FakeRegistry:
    """一个最小的 `ToolRegistry` 替身，只实现 `MCPServer` 用到的方法。"""

    def __init__(self, tools=None, results=None):
        self._tools = tools or []
        self._results = results or {}
        self.calls = []

    def list_tools(self, agent_type=None):
        return list(self._tools)

    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name not in self._results:
            return {"success": False, "error": f"Tool '{name}' not found"}
        return {"success": True, "result": self._results[name], "tool": name}


class TestMCPServer:
    def _server(self, registry=None):
        return mcp.MCPServer(registry if registry is not None else _FakeRegistry())

    def test_initialize_returns_capabilities(self):
        reply = self._server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert reply["result"]["protocolVersion"] == mcp.MCP_PROTOCOL_VERSION
        assert reply["result"]["serverInfo"]["name"] == "ai-novel-writer"

    def test_notification_gets_no_reply(self):
        """规范：通知（无 id）**不返回**响应。"""
        assert self._server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        assert self._server().handle({"jsonrpc": "2.0", "method": "ping"}) is None

    def test_unknown_method_is_32601(self):
        reply = self._server().handle({"jsonrpc": "2.0", "id": 7, "method": "no/such"})
        assert reply["error"]["code"] == -32601 and reply["id"] == 7

    def test_non_dict_request(self):
        reply = self._server().handle("nope")
        assert reply["error"]["code"] == -32600

    def test_tools_list_translates_to_wire_shape(self):
        reg = _FakeRegistry(
            tools=[{"name": "detect_scenes", "description": "检测名场面", "input_schema": {"type": "object"}}]
        )
        reply = self._server(reg).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool = reply["result"]["tools"][0]
        # 关键：内部用 input_schema，MCP 线路上必须是 inputSchema
        assert tool["name"] == "detect_scenes" and "inputSchema" in tool and "input_schema" not in tool

    def test_tools_list_fills_default_schema(self):
        reg = _FakeRegistry(tools=[{"name": "t", "description": "d"}])
        reply = self._server(reg).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert reply["result"]["tools"][0]["inputSchema"] == {"type": "object", "properties": {}}

    def test_tools_call_returns_content_blocks(self):
        reg = _FakeRegistry(results={"echo": "hello"})
        reply = self._server(reg).handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {}}}
        )
        assert reply["result"]["content"][0]["type"] == "text"
        assert reply["result"]["content"][0]["text"] == "hello"
        assert reply["result"]["isError"] is False

    def test_tools_call_serialises_non_string_result(self):
        reg = _FakeRegistry(results={"data": {"a": 1}})
        reply = self._server(reg).handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "data"}}
        )
        assert json.loads(reply["result"]["content"][0]["text"]) == {"a": 1}

    def test_missing_tool_is_iserror_content_not_protocol_error(self):
        """工具不存在时按 MCP 语义回 `isError` 内容，而不是 JSON-RPC error。

        理由：对客户端来说"工具报错"是可展示的信息，
        "协议层报错"才是客户端自己的问题 —— 两者不该混。
        """
        reply = self._server(_FakeRegistry()).handle(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}}
        )
        assert "error" not in reply
        assert reply["result"]["isError"] is True
        assert "not found" in reply["result"]["content"][0]["text"]

    def test_ping_with_id_returns_empty_result(self):
        reply = self._server().handle({"jsonrpc": "2.0", "id": 5, "method": "ping"})
        assert reply["result"] == {}

    def test_no_registry_reports_error(self):
        reply = mcp.MCPServer(None).handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "x"}})
        assert reply["error"]["code"] == -32603

    def test_non_dict_params_does_not_crash(self):
        reg = _FakeRegistry(results={"echo": "ok"})
        reply = self._server(reg).handle(
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": "string-not-dict"}
        )
        # name 取空 ⇒ 注册表里找不到 ⇒ isError 内容
        assert reply["result"]["isError"] is True


# ====================================================================== 3. 客户端（真起进程）


class TestStdioTransport:
    """用真实子进程跑 stdio 传输 —— 唯一能证明它真通的层次。"""

    def test_initialize_succeeds(self, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        client = mcp.MCPClient(_stdio_spec("fake", script))
        res = client.initialize()
        assert res.ok, res.message
        assert res.detail["server_info"]["name"] == "fake-server"

    def test_list_tools(self, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        client = mcp.MCPClient(_stdio_spec("fake", script))
        res = client.list_tools()
        assert res.ok, res.message
        names = [t.name for t in res.detail["tools"]]
        assert names == ["echo", "boom"]

    def test_call_tool_success(self, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        client = mcp.MCPClient(_stdio_spec("fake", script))
        res = client.call_tool("echo", {"text": "你好"})
        assert res.ok and res.message == "echo: 你好" and res.tool == "echo"

    def test_call_tool_iserror_flag_surfaces(self, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        client = mcp.MCPClient(_stdio_spec("fake", script))
        res = client.call_tool("boom", {})
        # 传输成功（ok=True），但内容标记了 isError —— 两者是不同层面
        assert res.ok and res.detail["is_error"] is True

    def test_ping(self, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        assert mcp.MCPClient(_stdio_spec("fake", script)).ping().ok

    def test_unknown_method_is_refused_locally(self, tmp_path):
        """未登记的方法应**在本地**被拒（不必出网），避免打错字变成网络错误。"""
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        res = mcp.MCPClient(_stdio_spec("fake", script)).call("no/such/method")
        assert not res.ok and res.reason == "unknown_method"

    def test_broken_server_reports_stderr(self, tmp_path):
        script = _write_fake_server(tmp_path, "broken", BROKEN_SERVER)
        res = mcp.MCPClient(_stdio_spec("broken", script)).initialize()
        assert not res.ok and "我起不来" in res.message

    def test_hanging_server_times_out_and_is_killed(self, tmp_path, monkeypatch):
        """挂死的 server 必须**超时返回**而不是永久卡住 —— 这是"防卡死"的关键一条。"""
        monkeypatch.setitem(mcp.JSONRPC_METHODS["ping"], "timeout", 1.5)
        script = _write_fake_server(tmp_path, "hang", HANGING_SERVER)
        res = mcp.MCPClient(_stdio_spec("hang", script)).ping()
        assert not res.ok and res.reason == "timeout"
        # 超时文案里要能看出是超时，而不是笼统的"失败"
        assert "超时" in res.message

    def test_missing_command_does_not_crash(self, tmp_path):
        spec = mcp.MCPServerSpec(name="nope", transport="stdio", command="definitely-not-real-xyz")
        res = mcp.MCPClient(spec).initialize()
        assert not res.ok and res.reason == "rpc_error"


class TestNodeCompatibility:
    """`node` 是最常见的 stdio MCP 载体；本机有 node ⇒ 值得真跑一次。

    这条测试证明"配 node 命令这条路"是通的（而不是只证明了 python 通）。
    """

    def test_python_as_stdio_host_is_the_mechanism(self, tmp_path):
        """机制验证：任何能被 `subprocess` 启动、按行列 JSON-RPC 的程序都行。

        这里直接用 `python -c` 而非脚本文件，证明**不依赖落盘路径**。
        注释里点明 node 同理（写法一致，只是 command 换成 node）。
        """
        spec = mcp.MCPServerSpec(
            name="inline",
            transport="stdio",
            command=sys.executable,
            args=[
                "-c",
                "import sys,json\n"
                "for l in sys.stdin:\n"
                "    m=json.loads(l)\n"
                "    sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':m.get('id'),'result':{}})+'\\n')\n"
                "    sys.stdout.flush()\n",
            ],
        )
        assert mcp.MCPClient(spec).ping().ok


# ====================================================================== 3b. 管理器


class TestManagerConfig:
    def test_starts_empty_when_file_absent(self, manager):
        assert manager.all_servers() == []

    def test_add_persists_and_reloads(self, manager, servers_file, tmp_path):
        spec = mcp.MCPServerSpec(name="s", command=sys.executable)
        assert manager.add_server(spec).ok
        assert servers_file.exists()
        again = mcp.MCPManager(servers_file=servers_file)
        assert [s.name for s in again.all_servers()] == ["s"]

    def test_add_reports_update_vs_create(self, manager):
        spec = mcp.MCPServerSpec(name="s", command=sys.executable)
        assert manager.add_server(spec).detail["updated"] is False
        assert manager.add_server(spec).detail["updated"] is True

    def test_remove(self, manager):
        manager.add_server(mcp.MCPServerSpec(name="s", command=sys.executable))
        assert manager.remove_server("s").ok and manager.all_servers() == []
        assert not manager.remove_server("s").ok

    def test_set_enabled_refuses_unusable(self, manager):
        manager.add_server(mcp.MCPServerSpec(name="s", transport="stdio", command=""))
        res = manager.set_enabled("s", True)
        assert not res.ok and res.reason == "not_usable"

    def test_set_enabled_persists(self, manager, servers_file):
        manager.add_server(mcp.MCPServerSpec(name="s", command=sys.executable))
        assert manager.set_enabled("s", True).ok
        assert mcp.MCPManager(servers_file=servers_file).get("s").enabled is True
        assert manager.set_enabled("s", False).ok
        assert mcp.MCPManager(servers_file=servers_file).get("s").enabled is False

    def test_unknown_server_returns_not_found(self, manager):
        assert manager.set_enabled("ghost", True).reason == "not_found"
        assert manager.call_tool("ghost", "t").reason == "not_found"

    def test_corrupt_config_is_ignored_not_raised(self, manager, servers_file):
        servers_file.parent.mkdir(parents=True, exist_ok=True)
        servers_file.write_text("{ this is not json", encoding="utf-8")
        again = mcp.MCPManager(servers_file=servers_file)
        assert again.all_servers() == []

    def test_wrong_shape_config_is_ignored(self, manager, servers_file):
        servers_file.parent.mkdir(parents=True, exist_ok=True)
        servers_file.write_text('{"servers": "not-a-list"}', encoding="utf-8")
        assert mcp.MCPManager(servers_file=servers_file).all_servers() == []

    def test_bad_entries_are_skipped_but_good_ones_kept(self, manager, servers_file):
        servers_file.parent.mkdir(parents=True, exist_ok=True)
        servers_file.write_text(
            json.dumps({"servers": [{"name": "a/b"}, {"name": "ok", "command": sys.executable}]}),
            encoding="utf-8",
        )
        assert [s.name for s in mcp.MCPManager(servers_file=servers_file).all_servers()] == ["ok"]

    def test_list_all_tools_not_configured(self, manager):
        res = manager.list_all_tools()
        assert not res.ok and res.reason == "not_configured"

    def test_list_all_tools_aggregates_and_reports_failures(self, manager, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        manager.add_server(_stdio_spec("good", script, enabled=True))
        manager.add_server(
            mcp.MCPServerSpec(
                name="bad",
                transport="stdio",
                command=sys.executable,
                args=[str(_write_fake_server(tmp_path, "broken", BROKEN_SERVER))],
                enabled=True,
            )
        )
        res = manager.list_all_tools(use_cache=False)
        assert res.ok
        assert {t.name for t in res.detail["tools"]} == {"echo", "boom"}
        assert [f["server"] for f in res.detail["failures"]] == ["bad"]

    def test_list_all_tools_all_failed(self, manager, tmp_path):
        manager.add_server(
            mcp.MCPServerSpec(
                name="bad",
                transport="stdio",
                command=sys.executable,
                args=[str(_write_fake_server(tmp_path, "broken", BROKEN_SERVER))],
                enabled=True,
            )
        )
        res = manager.list_all_tools(use_cache=False)
        assert not res.ok and res.reason == "all_failed"

    def test_tool_cache_is_used_by_default(self, manager, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        manager.add_server(_stdio_spec("s", script, enabled=True))
        assert manager.list_tools("s").detail.get("cached") is not True
        assert manager.list_tools("s").detail.get("cached") is True
        manager.clear_cache()
        assert manager.list_tools("s").detail.get("cached") is not True

    def test_test_connection_reports_tool_count(self, manager, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        manager.add_server(_stdio_spec("s", script))  # 注意：未启用也能测连接
        res = manager.test_connection("s")
        assert res.ok and res.detail["tool_count"] == 2

    def test_call_tool_through_manager(self, manager, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        manager.add_server(_stdio_spec("s", script, enabled=True))
        res = manager.call_tool("s", "echo", {"text": "abc"})
        assert res.ok and res.server == "s" and res.message == "echo: abc"

    def test_enabled_servers_filter(self, manager, tmp_path):
        script = _write_fake_server(tmp_path, "fake", FAKE_SERVER)
        manager.add_server(_stdio_spec("on", script, enabled=True))
        manager.add_server(_stdio_spec("off", script, enabled=False))
        assert [s.name for s in manager.enabled_servers()] == ["on"]

    def test_reload_picks_up_external_edits(self, manager, servers_file):
        manager.add_server(mcp.MCPServerSpec(name="a", command=sys.executable))
        servers_file.write_text(json.dumps({"servers": [{"name": "b", "command": sys.executable}]}), encoding="utf-8")
        assert manager.reload().ok
        assert [s.name for s in manager.all_servers()] == ["b"]


class TestGlobalManager:
    def test_get_reset_roundtrip(self, servers_file, monkeypatch):
        monkeypatch.setattr(mcp, "_manager", None)
        monkeypatch.setattr(mcp, "default_servers_file", lambda: servers_file)
        assert mcp.get_mcp_manager() is not None
        mcp.reset_mcp_manager()
        assert mcp._manager is None

    def test_get_returns_none_on_construction_failure(self, monkeypatch):
        monkeypatch.setattr(mcp, "_manager", None)

        def _boom(*_a, **_k):
            raise OSError("磁盘炸了")

        monkeypatch.setattr(mcp, "MCPManager", _boom)
        assert mcp.get_mcp_manager() is None


# ====================================================================== 4. 消费端（真实的"被读"）

#: 这些是 `MCPManager` 上必须仍存在的方法名 ——
#: `TestWiringGuard` 反向断言用。删掉任一即让"接线"断掉。
_REQUIRED_MANAGER_METHODS = (
    "all_servers",
    "enabled_servers",
    "get",
    "add_server",
    "remove_server",
    "set_enabled",
    "test_connection",
    "list_tools",
    "call_tool",
    "list_all_tools",
    "clear_cache",
)


class TestConsumption:
    """`novel_agent` 真的把这些工具**注册进了同一个注册中心**。

    只"能连 MCP"不等于"Agent 用得上" —— 这一层验的是后者。
    """

    def _agent(self):
        """造一个能真正被 `NovelAgent.__init__` 接受的 agent。

        `AgentOrchestrator.__init__` 会读 `ai_client.metrics`，
        所以裸 `object()` 不够 —— 用 `SimpleNamespace` 补上最小契约。
        """
        from types import SimpleNamespace

        from app.novel_agent import NovelAgent

        class _Memory:
            novel_dir = Path(".")

            def add_event(self, *a, **k):
                return None

            def get_characters(self):
                return {}

            def get_meta(self, *a, **k):
                return {}

            def get_chapter_summary(self, *a, **k):
                return None

        fake_ai = SimpleNamespace(metrics={}, config={})
        return NovelAgent(ai_client=fake_ai, memory=_Memory(), log_callback=lambda _m: None)

    def test_mcp_tools_are_registered_in_agent_registry(self):
        agent = self._agent()
        names = {t["name"] for t in agent.tools.list_tools(None)}
        assert "list_mcp_tools" in names
        assert "call_mcp_tool" in names

    def test_agent_registry_exposes_input_schema_for_mcp_tools(self):
        """MCP 工具必须带 `input_schema` —— 否则服务端暴露出去时参数为空。"""
        agent = self._agent()
        tools = {t["name"]: t for t in agent.tools.list_tools(None)}
        assert tools["call_mcp_tool"]["input_schema"]["required"] == ["server", "tool"]

    def test_agent_tool_call_degrades_when_no_servers(self, servers_file, monkeypatch):
        """没有配置任何服务器时，调用必须是**结构化失败**而不是抛异常。"""
        monkeypatch.setattr(mcp, "_manager", None)
        monkeypatch.setattr(mcp, "default_servers_file", lambda: servers_file)
        agent = self._agent()
        outcome = agent.tools.call("list_mcp_tools")
        assert outcome["success"] is True
        assert outcome["result"]["ok"] is False
        assert outcome["result"]["tools"] == []

    def test_agent_call_mcp_tool_missing_server_is_structured(self, servers_file, monkeypatch):
        monkeypatch.setattr(mcp, "_manager", None)
        monkeypatch.setattr(mcp, "default_servers_file", lambda: servers_file)
        agent = self._agent()
        outcome = agent.tools.call("call_mcp_tool", server="ghost", tool="t")
        assert outcome["success"] is True
        assert outcome["result"]["ok"] is False

    def test_server_exposes_agent_tools_over_mcp(self):
        """闭环：**本应用自己的工具**能通过 MCP 服务端被列出来。"""
        agent = self._agent()
        server = mcp.MCPServer(agent.tools)
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in reply["result"]["tools"]}
        # 既有 7 个 + 新增 2 个 MCP 工具
        assert {"detect_scenes", "get_characters", "list_mcp_tools"} <= names

    def test_server_can_call_agent_tool_roundtrip(self):
        """闭环：通过 MCP 服务端**调用**本应用的工具并拿到内容。"""
        agent = self._agent()
        server = mcp.MCPServer(agent.tools)
        reply = server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_characters", "arguments": {}}}
        )
        assert reply["result"]["isError"] is False

    def test_server_tools_list_has_no_legacy_snake_case_key(self):
        """对外线路必须是 `inputSchema`；内部 `input_schema` 不得漏出去。"""
        agent = self._agent()
        server = mcp.MCPServer(agent.tools)
        reply = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        for tool in reply["result"]["tools"]:
            assert "inputSchema" in tool and "input_schema" not in tool


# ====================================================================== 4b. 面板纯函数


class TestPanelPure:
    def test_registered(self):
        registry.load_panels()
        spec = registry.get("mcp")
        assert spec is not None, "MCP 面板未登记"
        assert spec.panel_cls is MCPPanel
        assert spec.title == "MCP 服务器"
        assert spec.category == "运维"

    def test_module_listed_in_registry(self):
        src = _scan.read("app/panels/registry.py")
        assert "app.panels.mcp_panel" in src

    def test_listed_in_packaging_spec(self):
        src = _scan.read("installer/novel_app.spec")
        assert "app.panels.mcp_panel" in src
        assert "app.mcp_system" in src

    def test_transport_summary_stdio(self):
        spec = mcp.MCPServerSpec(name="s", command="npx", args=["-y", "pkg"])
        assert transport_summary(spec) == "npx -y pkg"

    def test_transport_summary_http(self):
        spec = mcp.MCPServerSpec(name="s", transport="http", url="https://x/mcp")
        assert transport_summary(spec) == "https://x/mcp"

    def test_server_rows_shape(self):
        rows = server_rows([mcp.MCPServerSpec(name="s", command=sys.executable, enabled=True)])
        assert rows[0][0] == "s"
        assert rows[0][1][0] == "s" and rows[0][1][2] == "已启用"

    def test_server_rows_flags_enabled_but_misconfigured(self):
        rows = server_rows([mcp.MCPServerSpec(name="s", transport="stdio", command="", enabled=True)])
        assert rows[0][1][2] == "配置有误"

    def test_server_rows_empty(self):
        assert server_rows([]) == []

    def test_tool_rows_use_qualified_iid(self):
        rows = tool_rows([mcp.MCPToolInfo(name="echo", server="s", description="d")])
        # iid 必须带 server 前缀，否则两个 server 的同名工具会互相覆盖
        assert rows[0][0] == "s::echo"

    def test_server_detail_lines_empty(self):
        assert server_detail_lines(None) == []

    def test_server_detail_lines_stdio_has_command_and_warning(self):
        spec = mcp.MCPServerSpec(name="s", command="npx", args=["-y", "pkg"])
        text = "\n".join(f"{a}：{b}" for a, b in server_detail_lines(spec))
        assert "npx -y pkg" in text
        assert "本地进程" in text  # 安全提示必须出现

    def test_server_detail_lines_http_has_url_and_header_warning(self):
        spec = mcp.MCPServerSpec(name="s", transport="http", url="https://x/mcp", headers={"Authorization": "Bearer k"})
        text = "\n".join(f"{a}：{b}" for a, b in server_detail_lines(spec))
        assert "https://x/mcp" in text and "Authorization" in text
        assert "API Key" in text or "请求头" in text

    def test_server_detail_lines_flags_bad_config(self):
        spec = mcp.MCPServerSpec(name="s", transport="stdio", command="")
        text = "\n".join(f"{a}：{b}" for a, b in server_detail_lines(spec))
        assert "⚠" in text

    def test_parse_add_input_stdio(self):
        spec = MCPPanel._parse_add_input("fs | stdio | npx | -y pkg /tmp")
        assert spec.name == "fs" and spec.transport == "stdio"
        assert spec.command == "npx" and spec.args == ["-y", "pkg", "/tmp"]

    def test_parse_add_input_http(self):
        spec = MCPPanel._parse_add_input("remote | http | https://x/mcp")
        assert spec.transport == "http" and spec.url == "https://x/mcp"

    def test_parse_add_input_accepts_https_alias(self):
        assert MCPPanel._parse_add_input("r | https | https://x/mcp").transport == "http"

    @pytest.mark.parametrize("raw", ["", "   ", "only-one-field", "a | b", "a | stdio |", "name | weird | x"])
    def test_parse_add_input_rejects_bad(self, raw):
        assert MCPPanel._parse_add_input(raw) is None


# ====================================================================== 5. 🔴 接线守卫


def _production_call_sites(name: str) -> list[str]:
    """扫描 `app/` 下所有**生产代码**里对 `name` 的调用点。

    ❗ 只在 `app/` 下扫 —— `tests/` 不算调用方
    （"测试也是调用方"是本仓踩过的误判）。

    ❗❗ **必须排除定义本身**。本仓的写法是
    `self.tools.register(Tool("list_mcp_tools", ..., lambda: self.list_mcp_tools()))`
    —— 先把 `"list_mcp_tools"`（字符串，不是 Call）注册进去，再在 lambda 里调它。
    负向对照（把工具名字符串改名）曾经**骗过**这条守卫，原因有两层：
    1. `ast.Name` 分支会把函数**定义**当成调用；
    2. 只查 `ast.Attribute` 也漏不掉 —— 因为改名后 `self.list_mcp_tools()` 仍在。

    所以判据不能只看"有没有这个名字出现"，必须要求**至少一个真正的
    `self.<name>(...)` 调用点**，且该文件不是定义它的地方。
    """
    import ast

    hits: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        # 该文件里出现的 `def <name>(` 行号集合 —— 用来把"定义"从"调用"里剔除
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == name:
                hits.append(rel)
            elif isinstance(func, ast.Name) and func.id == name:
                # `ast.Name` 两种可能：调用 `get_mcp_manager()` 或……**不会**是定义
                # （定义是 `ast.FunctionDef`，不是 `ast.Call`）。
                # 之前误判的根源是把字符串工具名换掉后 `ast.Attribute` 分支也失效，
                # 与这个分支无关 —— 保留它才能覆盖 `from x import f; f()` 这种写法。
                hits.append(rel)
    # 同一文件可能既定义又调用；只要**存在**调用就够，这里不去重文件级只做去处重
    return sorted(set(hits))


def _defines(name: str, rel: str) -> bool:
    """`rel` 里是否有 `def name(` 或 `name = ` 形式的定义。"""
    code = _scan.code_only(rel)
    return f"def {name}(" in code


class TestWiringGuard:
    """功能被删要变红。**双向**：正向查调用点、反向查被调者仍存在。"""

    def test_list_mcp_tools_is_called_in_production(self):
        hits = _production_call_sites("list_mcp_tools")
        assert hits, "没有任何生产代码调用 list_mcp_tools —— MCP 又成了空壳"

    def test_call_mcp_tool_is_called_in_production(self):
        hits = _production_call_sites("call_mcp_tool")
        assert hits, "没有任何生产代码调用 call_mcp_tool"

    def test_list_all_tools_is_called_in_production(self):
        hits = _production_call_sites("list_all_tools")
        assert hits, "MCPManager.list_all_tools 没有消费者 —— 注册即遗忘"
        assert "app/panels/mcp_panel.py" in hits or "app/novel_agent.py" in hits

    def test_the_thing_being_called_still_exists(self):
        """反向断言：只查调用点是不够的 —— 把定义删了调用点还在。"""
        for method in _REQUIRED_MANAGER_METHODS:
            assert hasattr(mcp.MCPManager, method), f"MCPManager.{method} 不见了"

    def test_get_mcp_manager_is_used_in_production(self):
        hits = _production_call_sites("get_mcp_manager")
        assert hits, "get_mcp_manager 没有消费者"

    def test_mcp_module_is_not_orphan(self):
        """模块必须被**生产代码**引用（面板或 Agent 都行，但不能只有测试）。"""
        referenced_by = []
        for rel in ("app/novel_agent.py", "app/panels/mcp_panel.py", "app/panels/registry.py"):
            if "mcp_system" in _scan.read(rel):
                referenced_by.append(rel)
        assert referenced_by, "mcp_system 没有任何生产引用"

    def test_agent_registers_mcp_tools(self):
        """`NovelAgent._register_tools` 里必须有 MCP 两个工具的字面工具名。"""
        code = _scan.code_only("app/novel_agent.py")
        assert '"list_mcp_tools"' in code and '"call_mcp_tool"' in code, "MCP 工具没被注册进 ToolRegistry"

    def test_registration_survives_rename_of_helper(self):
        """更强的判据：即使把**方法名**改掉，只要工具名字符串还在，注册就还在。

        这条锁的是"注册"这件事本身，与 `_production_call_sites` 互补。
        """
        code = _scan.code_only("app/novel_agent.py")
        assert "self.tools.register(" in code
        # 两个 MCP 工具必须各有一处 register 调用把工具名交进去
        assert code.count('"list_mcp_tools"') >= 1
        assert code.count('"call_mcp_tool"') >= 1

    def test_panel_idioms_are_respected(self):
        """面板必须遵守两条易漏的约定：`mark_built(True)` 与不直接用 `self._log`。"""
        code = _scan.code_only("app/panels/mcp_panel.py")
        assert "mark_built(True)" in code, "build() 必须以 mark_built(True) 结尾"
        assert "_log_safe" in code, "未绑定宿主时 self._log 会抛，必须走兜底"

    def test_no_servers_path_rebuilt_outside_owner(self):
        """路径字面量只允许出现在 `mcp_system.py` 里 —— 防"同一事实写两处"。

        ❗ 必须用 `code_only`（剔注释与 docstring）：本面板的文档字符串**故意**
        提到了这个路径来解释"我不自己拼它"，那是说明而非实现。
        本仓的既有守卫全部用 `strip_noise` 预处理，这条也不例外。
        """
        offenders = []
        for path in sorted((REPO_ROOT / "app").rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel == "app/mcp_system.py":
                continue
            code = _scan.code_only(rel)
            if ".ai_novel_writer" in code and "mcp_servers" in code:
                offenders.append(rel)
        assert not offenders, f"这些文件自己拼了 MCP 配置路径：{offenders}"

    def test_default_servers_file_is_the_only_source(self):
        code = _scan.code_only("app/mcp_system.py")
        assert "def default_servers_file" in code
        assert "mcp_servers.json" in code


# ====================================================================== 6. 真 Tk


def _tk_available() -> bool:
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - 无显示环境
        return False


@pytest.mark.skipif(not _tk_available(), reason="无显示环境")
class TestPanelTk:
    def _build(self, tmp_path, monkeypatch):
        import tkinter as tk

        monkeypatch.setattr(mcp, "_manager", None)
        monkeypatch.setattr(mcp, "default_servers_file", lambda: tmp_path / "mcp_servers.json")
        root = tk.Tk()
        root.withdraw()
        panel = MCPPanel()
        # 关键：`app=None`（未绑定宿主）也必须能建出来 —— 这就是 `_log_safe` 的存在理由
        body = panel.build(root)
        return root, panel, body

    def test_build_without_host(self, tmp_path, monkeypatch):
        root, panel, body = self._build(tmp_path, monkeypatch)
        try:
            assert panel.is_built  # 属性，不是方法
            assert body.winfo_exists()
        finally:
            root.destroy()

    def test_build_twice_is_idempotent(self, tmp_path, monkeypatch):
        root, panel, _body = self._build(tmp_path, monkeypatch)
        try:
            second = panel.build(root)
            assert second.winfo_exists()
        finally:
            root.destroy()
