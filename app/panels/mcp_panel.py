"""MCP 服务器面板（第 18 个面板）—— 让 MCP 功能**可见、可控、可用**。

## 为什么必须有这个面板

本仓已经删过一个"实现完整但零引用"的模块（`plugin_system.py`）。
`mcp_system.py` 如果只提供 `MCPManager` 而没有界面，就是同一个错误的第二次犯：

- 用户**加不了**服务器（要手写 `~/.ai_novel_writer/mcp_servers.json`）；
- 用户**看不见**连上后有哪些工具；
- 用户**验证不了**连接是否真的通。

所以本面板承担三件事：

| 能力 | 面板上的位置 |
|---|---|
| 增删服务器 | 工具条「添加服务器」/「删除」 |
| 看清将执行什么 | 详情区显示 **stdio 的完整命令行原文** / HTTP 的完整 URL + header 名 |
| 启停 | 右侧「启用」/「停用」（**配置持久化**） |
| 连接测试 | 「测试连接」——真的握手 + 列工具，不是只 ping |
| 工具发现 | 左侧第二张表列出**已启用服务器的全部工具** |
| 生效证据 | 底部显示"Agent 当前可调用 N 个 MCP 工具" |

## 与插件面板同构的部分（有意为之）

两张面板的结构、`_log_safe` 兜底、`BackgroundRunner` 用法、
"底部显示消费端统计"的做法都一致 —— 这样维护者只需理解一次。

## 安全提示必须显眼

MCP server 与插件一样是**要执行的东西**：
- stdio：本应用会起一个本地进程；
- http：会把配置里的 headers（可能含 API Key）发给对方。

面板详情区对这两点各有一行明确提示，不做"它很安全"的暗示。
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from loguru import logger

from app import dialogs
from app.async_runner import BackgroundRunner
from app.mcp_system import (
    TRANSPORT_LABELS,
    MCPManager,
    MCPResult,
    MCPServerSpec,
    MCPToolInfo,
    get_mcp_manager,
)
from app.ui_style import UIStyle

from . import ui_kit
from .base import BasePanel

__all__ = [
    "MCPPanel",
    "server_rows",
    "server_detail_lines",
    "tool_rows",
    "transport_summary",
]

#: 传输方式 → 徽章颜色键（走令牌）
_TRANSPORT_KIND = {"stdio": "info", "http": "warn"}


# ====================================================================== 纯函数（可单测）


def transport_summary(spec: MCPServerSpec) -> str:
    """把"将执行什么"压成一行，供表格展示。"""
    if spec is None:
        return ""
    if spec.transport == "stdio":
        return spec.command_line() or "(未填 command)"
    return spec.url or "(未填 url)"


def server_rows(servers: list[MCPServerSpec]) -> list[tuple[str, tuple[str, ...]]]:
    """服务器列表 → 表格行。

    提成纯函数以便单测（面板逻辑不该只活在 Tk 回调里）。
    """
    rows: list[tuple[str, tuple[str, ...]]] = []
    for spec in servers:
        status = "已启用" if spec.enabled else "未启用"
        usable, why = spec.is_usable()
        if not usable and spec.enabled:
            status = "配置有误"
        rows.append(
            (
                spec.name,
                (
                    spec.name,
                    TRANSPORT_LABELS.get(spec.transport, spec.transport),
                    status,
                    transport_summary(spec),
                ),
            )
        )
    return rows


def tool_rows(tools: list[MCPToolInfo]) -> list[tuple[str, tuple[str, ...]]]:
    """工具列表 → 表格行。iid 用 `server::tool` 保证唯一。"""
    rows: list[tuple[str, tuple[str, ...]]] = []
    for tool in tools:
        iid = f"{tool.server}::{tool.name}"
        rows.append((iid, (tool.server, tool.name, tool.description or "-")))
    return rows


def server_detail_lines(spec: MCPServerSpec, tools: list[MCPToolInfo] = None) -> list[tuple[str, str]]:
    """服务器详情 → `[(标题, 内容)]`。内容为空则不返回。"""
    if spec is None:
        return []
    lines: list[tuple[str, str]] = []
    lines.append(("名称", spec.name))
    if spec.description:
        lines.append(("说明", spec.description))
    lines.append(("传输方式", TRANSPORT_LABELS.get(spec.transport, spec.transport)))
    lines.append(("状态", "已启用" if spec.enabled else "未启用"))
    usable, why = spec.is_usable()
    if not usable:
        lines.append(("配置检查", f"⚠ {why}"))
    if spec.transport == "stdio":
        lines.append(("将执行的命令", spec.command_line() or "(未填)"))
        if spec.env:
            lines.append(("注入环境变量", "、".join(sorted(spec.env))))
        lines.append(("⚠ 安全提示", "启用后本应用会**启动上述本地进程**，它与本应用同等权限。"))
    else:
        lines.append(("请求地址", spec.url or "(未填)"))
        if spec.headers:
            lines.append(("请求头字段", "、".join(sorted(spec.headers))))
            lines.append(("⚠ 安全提示", "上述请求头（可能含 API Key）会随每次请求发送到该地址。"))
    if tools:
        lines.append(("已发现工具", str(len(tools))))
    return lines


# ====================================================================== 面板


class MCPPanel(BasePanel):
    """MCP 服务器：增删 / 启停 / 连接测试 / 工具发现。"""

    key = "mcp"
    title = "MCP 服务器"
    category = "运维"
    order = 61
    description = "连接外部 MCP 服务器并把它们的工具接入本应用"

    #: 服务器配置与应用级状态无关（不随作品切换），因此不订阅事件。
    topics_of_interest = ()

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._servers: list[MCPServerSpec] = []
        self._tools: list[MCPToolInfo] = []
        self._current: str = ""
        self._busy = False
        # ❗ 与插件面板同理：原生面板不能假设宿主一定绑定了。
        # `self._log` 在 `app is None` 时会抛；`BackgroundRunner` 却随时会调它。
        self._runner = BackgroundRunner(ui=getattr(self.app, "root", None), log=self._log_safe)

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 工具条
        bar = ui_kit.toolbar(body)
        bar["bar"].pack(fill=tk.X)  # ❗ toolbar 不自行 pack
        ui_kit.button(bar["left"], "添加服务器", self._on_add, kind="primary")
        ui_kit.button(bar["left"], "测试连接", self._on_test, kind="secondary")
        ui_kit.button(bar["left"], "刷新工具", self._on_refresh_tools, kind="ghost")
        ui_kit.button(bar["left"], "打开配置文件", self._on_open_file, kind="ghost")
        self._count_badge = ui_kit.badge(bar["right"], "未加载", kind="info")

        # ---- 上下两栏：上=服务器，下=工具
        top = tk.Frame(body, bg=C["bg_dark"])
        top.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(top, bg=C["bg_dark"], width=520)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left.pack_propagate(False)
        ui_kit.section_title(left, "MCP 服务器")
        # ❗ pretty_tree 返回 dict；columns 是列名序列、宽度另传 widths；frame 需自行 pack
        holder = ui_kit.pretty_tree(
            left,
            columns=["名称", "传输", "状态", "目标"],
            widths=[120, 56, 70, 260],
            height=9,
            on_select=lambda _e: self._on_pick(),
        )
        holder["frame"].pack(fill=tk.BOTH, expand=True)
        self._tree = holder["tree"]

        right = tk.Frame(top, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        ui_kit.section_title(right, "服务器详情")
        detail_box = ui_kit.scrollable(right)
        detail_box["frame"].pack(fill=tk.BOTH, expand=True)
        self._detail = tk.Text(
            detail_box["inner"],
            wrap=tk.WORD,
            font=UIStyle.font("body"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=8,
            pady=6,
            height=10,
        )
        self._detail.pack(fill=tk.BOTH, expand=True)
        self._detail.config(state=tk.DISABLED)

        actions = tk.Frame(right, bg=C["bg_dark"])
        actions.pack(fill=tk.X, pady=(6, 2))
        self._enable_btn = ui_kit.button(actions, "启用", self._on_enable, kind="primary")
        self._disable_btn = ui_kit.button(actions, "停用", self._on_disable, kind="ghost")
        self._remove_btn = ui_kit.button(actions, "删除", self._on_remove, kind="danger")

        # ---- 下部：工具表
        lower = tk.Frame(body, bg=C["bg_dark"])
        lower.pack(fill=tk.BOTH, expand=True, padx=2, pady=(4, 0))
        ui_kit.section_title(lower, "可用 MCP 工具（来自已启用的服务器）")
        t_holder = ui_kit.pretty_tree(
            lower,
            columns=["服务器", "工具", "说明"],
            widths=[120, 170, 360],
            height=7,
            on_select=lambda _e: None,
        )
        t_holder["frame"].pack(fill=tk.BOTH, expand=True)
        self._tool_tree = t_holder["tree"]

        # ---- 底部：生效证据（"连上了" vs "能用了"）
        self._effect_line = ui_kit.hint(body, "")
        self._effect_line.pack(fill=tk.X, pady=(4, 0))

        self._on_reload()
        self.mark_built(True)  # ❗ 不标记会被宿主反复重建
        return body

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        self._on_reload()

    # ------------------------------------------------------------------ 内部

    def _log_safe(self, message: str) -> None:
        """宿主绑定则走宿主的日志面板，否则只落 logger。"""
        host_log = getattr(self.app, "_log", None) if self.app is not None else None
        if callable(host_log):
            host_log(message)
        else:
            logger.debug(f"[MCP] {message}")

    def _manager(self) -> Optional[MCPManager]:
        mgr = get_mcp_manager()
        if mgr is None:
            self._set_effect("MCP 管理器不可用（配置文件无法访问），本面板功能受限", "error")
        return mgr

    def _set_effect(self, text: str, kind: str = "info") -> None:
        self._effect_line.config(text=text)

    def _selected_name(self) -> str:
        sel = self._tree.selection()
        if not sel:
            return ""
        return sel[0]

    def _on_reload(self) -> None:
        mgr = self._manager()
        if mgr is None:
            self._servers = []
            ui_kit.fill_tree(self._tree, [])
            ui_kit.fill_tree(self._tool_tree, [])
            self._set_detail("MCP 管理器不可用。")
            return
        mgr.reload()
        self._servers = mgr.all_servers()
        ui_kit.fill_tree(self._tree, server_rows(self._servers))
        enabled = [s for s in self._servers if s.enabled]
        bad = [s for s in self._servers if not s.is_usable()[0]]
        self._count_badge.config(
            text=f"共 {len(self._servers)} 个 / 启用 {len(enabled)}",
            fg=UIStyle.COLORS.get("error_text" if bad else "text_secondary", ""),
        )
        if not self._servers:
            self._set_detail(
                "尚未配置任何 MCP 服务器。\n\n"
                "点左上角「添加服务器」，按提示填写：\n"
                "  · stdio —— 需要 command 与 args（本应用会启动该本地进程）\n"
                "  · http  —— 需要 url，可选 headers\n\n"
                "添加后默认**不启用** —— 请先看清详情里的命令行 / 地址，再点「启用」，\n"
                "然后点「测试连接」验证是否真的能握手。"
            )
        self._refresh_tools()
        self._refresh_effect()

    def _refresh_tools(self) -> None:
        """拉取已启用服务器的工具清单（走缓存，避免每次切面板都出网）。"""
        mgr = get_mcp_manager()
        if mgr is None:
            return
        try:
            res = mgr.list_all_tools(use_cache=True)
        except Exception as exc:  # noqa: BLE001 - 统计失败不该影响面板
            logger.debug(f"[MCP] 刷新工具失败：{exc}")
            return
        self._tools = list(res.detail.get("tools") or [])
        ui_kit.fill_tree(self._tool_tree, tool_rows(self._tools))

    def _refresh_effect(self) -> None:
        """底部"生效证据"：Agent 现在**真正能调用到**几个 MCP 工具。"""
        mgr = get_mcp_manager()
        if mgr is None:
            return
        enabled = mgr.enabled_servers()
        if not enabled:
            self._set_effect("没有已启用的 MCP 服务器 —— Agent 目前没有额外的 MCP 工具可用。", "info")
            return
        if not self._tools:
            self._set_effect(
                f"已启用 {len(enabled)} 个服务器，但尚未发现任何工具 —— 试试点「测试连接」。",
                "info",
            )
            return
        servers = sorted({t.server for t in self._tools})
        self._set_effect(
            f"已生效：Agent 可调用 {len(self._tools)} 个 MCP 工具（来自 {len(servers)} 个服务器）",
            "success",
        )

    def _set_detail(self, text: str) -> None:
        self._detail.config(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.config(state=tk.DISABLED)

    def _spec_of(self, name: str) -> Optional[MCPServerSpec]:
        for spec in self._servers:
            if spec.name == name:
                return spec
        return None

    def _on_pick(self) -> None:
        name = self._selected_name()
        self._current = name
        spec = self._spec_of(name)
        if spec is None:
            return
        mine = [t for t in self._tools if t.server == name]
        lines = server_detail_lines(spec, mine)
        self._set_detail("\n".join(f"{title}：{value}" for title, value in lines))
        usable, _why = spec.is_usable()
        self._enable_btn.config(state=tk.NORMAL if (usable and not spec.enabled) else tk.DISABLED)
        self._disable_btn.config(state=tk.NORMAL if spec.enabled else tk.DISABLED)

    # ------------------------------------------------------------------ 动作

    def _on_open_file(self) -> None:
        mgr = self._manager()
        if mgr is None:
            return
        # 路径取管理器的 `servers_file`（唯一来源在 `mcp_system.default_servers_file`），
        # 面板**不自己拼** `.ai_novel_writer/mcp_servers.json` —— 那是"同一事实写两处"。
        path = mgr.servers_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('{\n  "servers": []\n}\n', encoding="utf-8")
        except OSError as exc:
            self._set_effect(f"无法创建配置文件：{exc}", "error")
            return
        self._open_path(path.parent)

    @staticmethod
    def _open_path(path) -> None:
        import os
        import subprocess
        import sys

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[MCP] 打开目录失败：{exc}")

    def _on_add(self) -> None:
        if self._busy:
            self._set_effect("正在处理上一个操作，请稍候…", "info")
            return
        mgr = self._manager()
        if mgr is None:
            return
        # ❗ 弹窗一律走 `app.dialogs`（有门禁）。`ask_text` 需要 parent。
        # 两步式：先输一行紧凑格式，再决定是否需要更多输入 ——
        # 避免自造一个多字段表单对话框（那会与既有外观/校验不一致）。
        parent = self._host_widget()
        raw = dialogs.ask_text(
            parent,
            "添加 MCP 服务器",
            "按以下任一格式输入一行：\n\n"
            "  stdio：  名称 | stdio | 命令 | 参数1 参数2 …\n"
            "  示例：  filesystem | stdio | npx | -y @modelcontextprotocol/server-filesystem /tmp\n\n"
            "  http：   名称 | http | 地址\n"
            "  示例：  remote | http | https://example.com/mcp\n\n"
            "（添加后默认不启用，请在详情里确认后再启用）",
        )
        if raw is None:
            return
        parsed = self._parse_add_input(raw)
        if parsed is None:
            self._set_effect("格式无法解析，请按提示的格式输入（用 | 分隔字段）", "error")
            return
        result = mgr.add_server(parsed)
        self._set_effect(result.message, "success" if result.ok else "error")
        if not result.ok:
            return
        # HTTP 服务器的 header（可能含密钥）单独询问，避免与主格式挤在一行
        if parsed.transport == "http":
            hdr = dialogs.ask_text(
                parent,
                "HTTP 请求头（可留空）",
                "每行一个 `键: 值`，例如：\nAuthorization: Bearer sk-xxx\n\n留空则不发送额外请求头。",
            )
            if hdr and hdr.strip():
                headers: dict[str, str] = {}
                for line in hdr.splitlines():
                    if ":" not in line:
                        continue
                    key, _, value = line.partition(":")
                    if key.strip():
                        headers[key.strip()] = value.strip()
                if headers:
                    parsed.headers = headers
                    again = mgr.add_server(parsed)
                    self._set_effect(again.message, "success" if again.ok else "error")
        self._on_reload()

    @staticmethod
    def _parse_add_input(raw: str) -> Optional[MCPServerSpec]:
        """解析"名称 | 传输 | 目标 [| 参数]"这一行紧凑格式。

        提成静态方法以便单测（不依赖 Tk）。
        """
        if not raw or not raw.strip():
            return None
        parts = [p.strip() for p in raw.strip().split("|")]
        if len(parts) < 3:
            return None
        name, transport, target = parts[0], parts[1].lower(), parts[2]
        if not name or not target:
            return None
        if transport == "stdio":
            rest = parts[3] if len(parts) > 3 else ""
            args = [a for a in rest.split() if a]
            return MCPServerSpec(name=name, transport="stdio", command=target, args=args)
        if transport in ("http", "https"):
            return MCPServerSpec(name=name, transport="http", url=target)
        return None

    def _on_test(self) -> None:
        name = self._selected_name()
        mgr = self._manager()
        if mgr is None or not name:
            self._set_effect("请先在左侧选中一个服务器", "info")
            return
        if self._busy:
            self._set_effect("正在测试上一个连接，请稍候…", "info")
            return
        self._busy = True
        self._set_effect(f"正在连接 {name} …", "info")
        # 起进程 / 出网都会阻塞，必须走后台线程，回主线程再碰控件
        self._runner.submit(
            mgr.test_connection,
            name,
            on_success=self._after_test,
            on_finally=self._clear_busy,
        )

    def _clear_busy(self) -> None:
        self._busy = False

    def _after_test(self, result: MCPResult) -> None:
        if not isinstance(result, MCPResult):
            self._set_effect("测试返回了非预期结果", "error")
            return
        self._set_effect(result.message, "success" if result.ok else "error")
        self._refresh_tools()
        self._refresh_effect()
        self._on_pick()

    def _on_refresh_tools(self) -> None:
        mgr = self._manager()
        if mgr is None:
            return
        mgr.clear_cache()
        self._refresh_tools()
        self._refresh_effect()
        self._on_reload()

    def _on_enable(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            self._set_effect("请先在左侧选中一个服务器", "info")
            return
        spec = self._spec_of(name)
        if spec is not None and spec.transport == "stdio":
            # 启用 = 允许本应用启动该进程，属于要明确知情的动作
            if not dialogs.confirm(
                f"启用后将允许本应用执行以下命令：\n\n{spec.command_line()}\n\n确定启用吗？",
                title="确认启用 MCP 服务器",
                parent=self._host_widget(),
            ):
                return
        result = mgr.set_enabled(name, True)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._on_pick()

    def _on_disable(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            return
        result = mgr.set_enabled(name, False)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._on_pick()

    def _on_remove(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            return
        if not dialogs.confirm(
            f"确定要删除 MCP 服务器「{name}」的配置吗？（不影响对方服务）",
            title="删除服务器配置",
            parent=self._host_widget(),
        ):
            return
        result = mgr.remove_server(name)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._set_detail("已删除。")
