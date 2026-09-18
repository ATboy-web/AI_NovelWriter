# MCP 支持（v3.2）

## 一、先澄清：本仓早就有"MCP 形状"，缺的是"MCP 线路"

这次新增 MCP 功能前，仓库里**已经**存在 MCP 形状的内部约定，只是没有传输层：

| 已有 | 位置 | 说明 |
|---|---|---|
| `MessageRole`（含 `TOOL`） | `app/novel_agent.py:187` | 角色枚举 |
| `AgentMessage` | `app/novel_agent.py:197` | 注释原文："标准化Agent消息 - 参考MCP协议" |
| `Tool` | `app/novel_agent.py:220` | 有 `name` / `description` / `func` / `input_schema` / `category` |
| `ToolRegistry` | `app/novel_agent.py:240` | 有 `register()` / `list_tools(agent_type)` / `call(tool_name, **kwargs)` |

所以本次**没有重新发明工具系统**，而是把上面这套接到**真正的 MCP 线路上**：

```
                    ┌──────────────────────────────┐
   外部 MCP 服务器   │   MCPClient（stdio / http）   │
   ───────────────► │   list_tools / call_tool      │
                    └───────────────┬──────────────┘
                                    │ 复用
                                    ▼
                    ┌──────────────────────────────┐
   本应用自己的工具   │  ToolRegistry（已有，7 个工具）│
   ◄───────────────  │  MCPServer.handle(msg)        │
                    └──────────────────────────────┘
```

**双向**是这个设计的重点：
- 只能连别人（客户端）⇒ 本应用永远是消费者；
- 加上服务端 ⇒ 本应用的工具也能被**任何** MCP 客户端按标准 `tools/list` / `tools/call` 访问。

## 二、模块与文件

| 文件 | 职责 |
|---|---|
| `app/mcp_system.py` | 客户端 + 服务端 + 管理器 + 结构化结果 |
| `app/panels/mcp_panel.py` | 「MCP 服务器」面板（第 18 个面板，运维分组） |
| `app/novel_agent.py` | 注册 `list_mcp_tools` / `call_mcp_tool` 两个工具 |
| `tests/test_mcp_system.py` | 129 条测试，含双向接线守卫 |

## 三、配置文件

**唯一来源**：`app/mcp_system.py::default_servers_file()`
= `~/.ai_novel_writer/mcp_servers.json`

```json
{
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/novels"],
      "enabled": false,
      "description": "本地文件系统访问"
    },
    {
      "name": "remote",
      "transport": "http",
      "url": "https://example.com/mcp",
      "headers": {"Authorization": "Bearer <token>"},
      "enabled": false
    }
  ]
}
```

> 面板**不自己拼这个路径** —— 有守卫测试拦"在别处重复拼"。

## 四、界面操作（无需手改 JSON、无需重启）

打开「MCP 服务器」面板：

| 操作 | 位置 |
|---|---|
| 添加服务器 | 工具条「添加服务器」 |
| 查看配置 | 左侧表（名称 / 传输 / 状态 / 目标） |
| 看清将执行什么 | 右侧详情：stdio 显示**完整命令行原文**，http 显示 URL + header 名 |
| 启用 / 停用 | 右侧「启用」/「停用」 |
| **连接测试** | 工具条「测试连接」—— 真握手 + 真列工具 |
| 工具发现 | 下半部表：已启用服务器的全部工具 |
| 生效证据 | 底部："Agent 可调用 N 个 MCP 工具（来自 M 个服务器）" |

添加时用紧凑的单行格式：

```
名称 | 传输 | 目标 [| 参数]

filesystem | stdio | npx | -y @modelcontextprotocol/server-filesystem /tmp
remote     | http  | https://example.com/mcp
```

HTTP 类型的 `headers` 会**单独再问一次**（避免密钥与主格式挤在一行）。

## 五、Agent 侧用法

`NovelAgent` 把 MCP 工具挂进**同一个** `ToolRegistry`：

```python
agent.tools.call("list_mcp_tools")                      # 列出所有可用 MCP 工具
agent.tools.call("call_mcp_tool", server="fs", tool="read_file",
                 arguments={"path": "outline.txt"})
```

两个工具的返回都是**结构化字典**（`{"ok", "message", "tools"/"detail"}`），
而不是裸字符串 —— 因为 MCP 服务端还要把它们序列化后转发出去。

## 六、🔴 安全边界（不做虚假承诺）

MCP server 与插件一样是**要执行的东西**，两种传输的风险不同：

| 传输 | 风险 | 本模块能做的 |
|---|---|---|
| `stdio` | 本应用**启动一个本地进程**，它与本应用同等权限 | 启用前**原文展示命令行** + 默认不启用 + 启用时二次确认 |
| `http` | 一次出网请求，会带上配置里的 headers（**可能含 API Key**） | 详情区明确提示 header 会被发送 |

**做不到**：沙箱化对端进程 / 校验对端返回内容的安全性。
定位是**让"将执行什么"可见**，不是"让不可信 server 变安全"。

其余工程防护：

- 服务器名白名单校验（拒绝 `/` `\` `:` 空格等）；
- 配置文件损坏 / 形状不对 ⇒ **忽略并降级**，绝不抛（MCP 不该拖垮启动）；
- stdio 调用有**超时**（`JSONRPC_METHODS` 表里逐方法配置），超时即 `kill` 子进程；
- 服务端输出上限 8MB，防止撑爆内存；
- `get_mcp_manager()` 构造失败返回 `None`，同 `get_plugin_manager()` 策略。

## 七、测试分层

`tests/test_mcp_system.py` 共 129 条，六层：

| 层 | 覆盖 |
|---|---|
| 1. 纯逻辑 | 名称校验 / SSE 解析 / JSON-RPC 信封 / 结果对象 / spec 往返 |
| 2. 服务端 | 每条 JSON-RPC 消息的应答；**通知不回响应**；`-32601`；`inputSchema` 大小写 |
| 3. 客户端（**真起子进程**） | 用自写的假 MCP server 走真 stdio 管道；断开 / 挂死 / 超时 / kill |
| 3b. 管理器 | 配置读写 / 启停 / 缓存 / 失败汇总 |
| 4. 消费端 | `NovelAgent` 真注册了工具；**闭环**：本应用工具能被 MCP 服务端列出并调用 |
| 4b/5. 面板 | 纯函数 + 真 Tk（`app=None` 也必须能 build） |

### 接线守卫（最重要的一层）

`TestWiringGuard` **双向**断言：

- **正向**：`list_mcp_tools` / `call_mcp_tool` / `list_all_tools` / `get_mcp_manager`
  在 `app/` 下**有真实调用点**（`tests/` 不算）；
- **反向**：`MCPManager` 的 11 个方法**仍然存在**
  —— 只查调用点是不够的：**把定义删掉，调用点还在，测试照样过**。

另外钉住三条约定：
1. `mcp_panel.build()` 必须 `mark_built(True)` 结尾；
2. 必须用 `_log_safe` 而非 `self._log`（未绑定宿主时会抛）；
3. MCP 配置路径**只允许**出现在 `mcp_system.py` 一处。

> ❗ 负向对照（`_production_call_sites` 的实现教训）：
> 本仓把工具名当**字符串**注册（`Tool("list_mcp_tools", ...)`），
> 又在 lambda 里调同名方法。最初版本用"名字出现过就算命中"，被"改名测试"骗过；
> 现在要求**至少一个真正的 `obj.name(...)` 调用点**才计数。
