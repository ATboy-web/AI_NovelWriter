"""插件中心面板（第 17 个面板）—— 让插件系统**可见、可控、可审计**。

## 为什么必须有这个面板

`plugin_system.py` 曾因"全仓零引用"被删。恢复它的文件**不等于**恢复它的功能：
如果只有 `PluginManager` 而没有界面，用户装不了、看不见、启不了 ——
等于把死代码从"没人调用的模块"变成"没人调用的模块 + 一个用户看不到的类"。

本面板是**两端接通的证据**：

| 能力 | 面板上的位置 |
|---|---|
| 发现 / 列表 | 左侧插件表（名称 / 版本 / 类型 / 状态 / 风险） |
| 安装 | 工具条「安装插件」（目录 / ZIP / URL 三种来源都支持） |
| 启用 / 停用 | 右侧详情区按钮（**启用状态持久化**，重启后仍生效） |
| 卸载 | 右侧详情区「卸载」（带确认） |
| 安全审计 | 详情区显示**静态体检结论**：会 import 什么、触及哪些高危符号 |
| 生效验证 | 底部显示"当前有 N 个技能包注入写作提示词" —— **能证明它真的被读了** |

## 最后一项是关键

"装上了"和"生效了"是两件事。本面板底部专门显示**消费端统计**
（`PluginManager.all_writing_skills()` 的结果条数），
这直接对应 `writing_skills.WritingSkillManager.plugin_skill_context()`
的读取 —— 也就是"注册即遗忘"检测法在 UI 层的落地。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Optional

from loguru import logger

from app import dialogs
from app.async_runner import BackgroundRunner
from app.plugin_system import (
    PLUGIN_TYPE_LABELS,
    PluginManager,
    PluginResult,
    get_plugin_manager,
)
from app.ui_style import UIStyle

from . import ui_kit
from .base import BasePanel

__all__ = ["PluginPanel", "plugin_rows", "plugin_detail_lines"]

#: 风险等级 → 颜色键（走令牌，不硬编码色值）
_RISK_KIND = {"safe": "success", "notice": "info", "high": "error"}
_RISK_LABEL = {"safe": "低", "notice": "中", "high": "高"}


# ====================================================================== 纯函数（可单测）


def plugin_rows(plugins: list[dict]) -> list[tuple[str, tuple[str, ...]]]:
    """把 `PluginManager.list_plugins()` 的结果变成表格行。

    提成纯函数是为了**可测**：面板逻辑一旦只活在 Tk 回调里，
    就只能靠"真起一个 Tk 窗口点一下"来验证，成本高且易漏。
    """
    rows: list[tuple[str, tuple[str, ...]]] = []
    for info in plugins:
        name = str(info.get("name", ""))
        version = str(info.get("version", ""))
        type_label = str(info.get("type_label") or PLUGIN_TYPE_LABELS.get(str(info.get("type")), "未知"))
        if info.get("load_error"):
            status = "加载失败"
        elif info.get("enabled"):
            status = "已启用"
        else:
            status = "未启用"
        risk = _RISK_LABEL.get(str(info.get("risk_level", "")), "未知")
        rows.append((name, (name, version, type_label, status, risk)))
    return rows


def plugin_detail_lines(info: dict) -> list[tuple[str, str]]:
    """插件详情 → `[(标题, 内容)]`。内容为空则不返回该项。"""
    if not info:
        return []
    lines: list[tuple[str, str]] = []
    lines.append(("名称", f"{info.get('name', '')}  v{info.get('version', '')}"))
    if info.get("author"):
        lines.append(("作者", str(info["author"])))
    if info.get("description"):
        lines.append(("说明", str(info["description"])))
    lines.append(("类型", str(info.get("type_label") or info.get("type", ""))))
    caps = info.get("capabilities") or []
    cap_text = "、".join(PLUGIN_TYPE_LABELS.get(str(c), str(c)) for c in caps) or "无"
    lines.append(("提供能力", cap_text))
    lines.append(("状态", "已启用" if info.get("enabled") else "未启用"))
    lines.append(("风险", f"{_RISK_LABEL.get(str(info.get('risk_level')), '未知')} —— {info.get('risk_summary', '')}"))
    if info.get("load_error"):
        lines.append(("加载错误", str(info["load_error"])))
    lines.append(("目录", str(info.get("plugin_dir", ""))))
    return lines


# ====================================================================== 面板


class PluginPanel(BasePanel):
    """插件中心：安装 / 启停 / 卸载 / 安全审计。"""

    key = "plugins"
    title = "插件中心"
    category = "运维"
    order = 60
    description = "安装、启用与管理插件（写作技能包 / 素材库 / 导出格式）"

    #: 插件会影响写作上下文，而写作上下文的消费发生在章节生成时；
    #: 本面板自身只在切换作品时刷新（插件根目录与作品无关）。
    topics_of_interest = ()

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._plugins: list[dict] = []
        self._current: str = ""
        self._busy = False
        # ❗ 原生面板**不能假设宿主一定绑定了**（自动化测试、独立预览都会用 `app=None`）。
        # 直接写 `self._log` 会经 `BasePanel.__getattr__` 转发到宿主并抛
        # "未绑定宿主" —— 于是面板连 build 都过不去。这里给一个兜底。
        self._runner = BackgroundRunner(ui=getattr(self.app, "root", None), log=self._log_safe)

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 工具条
        bar = ui_kit.toolbar(body)
        bar["bar"].pack(fill=tk.X)  # ❗ toolbar 不自行 pack
        # ❗ 与插图/MCP 面板同因：`ui_kit.button / badge` **不自行 pack**，
        # 必须显式挂载，否则按钮被创建却永不显示（曾整排消失）。
        ui_kit.button(bar["left"], "安装插件", self._on_install, kind="primary").pack(side=tk.LEFT)
        ui_kit.button(bar["left"], "重新扫描", self._on_reload, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        ui_kit.button(bar["left"], "打开插件目录", self._on_open_dir, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        self._count_badge = ui_kit.badge(bar["right"], "未扫描", kind="info")
        self._count_badge.pack(side=tk.RIGHT)

        # ---- 左右分栏
        split = tk.Frame(body, bg=C["bg_dark"])
        split.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(split, bg=C["bg_dark"], width=460)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left.pack_propagate(False)
        ui_kit.section_title(left, "已安装插件").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
        # ❗ `pretty_tree` 返回 dict，columns 是列名序列、宽度另传 widths，
        # 且返回的 frame 需要自行 pack（与"传 (名,宽) 元组"的直觉不同）
        holder = ui_kit.pretty_tree(
            left,
            columns=["插件", "版本", "类型", "状态", "风险"],
            widths=[168, 66, 90, 66, 48],
            height=14,
            on_select=lambda _e: self._on_pick(),
        )
        holder["frame"].pack(fill=tk.BOTH, expand=True)
        self._tree = holder["tree"]

        right = tk.Frame(split, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        ui_kit.section_title(right, "插件详情").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
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
            height=14,
        )
        self._detail.pack(fill=tk.BOTH, expand=True)
        self._detail.config(state=tk.DISABLED)

        actions = tk.Frame(right, bg=C["bg_dark"])
        actions.pack(fill=tk.X, pady=(6, 2))
        self._enable_btn = ui_kit.button(actions, "启用", self._on_enable, kind="primary")
        self._enable_btn.pack(side=tk.LEFT)
        self._disable_btn = ui_kit.button(actions, "停用", self._on_disable, kind="ghost")
        self._disable_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._uninstall_btn = ui_kit.button(actions, "卸载", self._on_uninstall, kind="danger")
        self._uninstall_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))

        # ---- 底部：生效证据（"装上了" vs "生效了"）
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
        """宿主绑定则走宿主的日志面板，否则只落 logger。

        为什么需要它：`BackgroundRunner(log=...)` 会在安装/检测过程中回传进度，
        而 `self._log` 在**未绑定宿主**时是会抛异常的属性（见 `build` 的注释）。
        """
        host_log = getattr(self.app, "_log", None) if self.app is not None else None
        if callable(host_log):
            host_log(message)
        else:
            logger.debug(f"[插件中心] {message}")

    def _manager(self) -> Optional[PluginManager]:
        mgr = get_plugin_manager()
        if mgr is None:
            self._set_effect("插件系统不可用（插件目录无法访问），本面板功能受限", "error")
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
            self._plugins = []
            ui_kit.fill_tree(self._tree, [])
            self._set_detail("插件系统不可用。")
            return
        mgr.reload()
        self._plugins = mgr.list_plugins()
        ui_kit.fill_tree(self._tree, plugin_rows(self._plugins))
        enabled = [p for p in self._plugins if p.get("enabled")]
        broken = [p for p in self._plugins if p.get("load_error")]
        self._count_badge.config(
            text=f"共 {len(self._plugins)} 个 / 启用 {len(enabled)}",
            fg=UIStyle.COLORS.get("error_text" if broken else "text_secondary", ""),
        )
        if not self._plugins:
            self._set_detail(
                "尚未安装任何插件。\n\n"
                "点左上角「安装插件」选择来源：\n"
                "  · 本地目录（含 plugin.json）\n"
                "  · ZIP 压缩包\n"
                "  · GitHub 仓库或直链 URL\n\n"
                "安装后默认**不启用** —— 请先看详情里的安全体检结论，再点「启用」。"
            )
        self._refresh_effect()

    def _refresh_effect(self) -> None:
        """底部"生效证据"：插件提供的写作技能包是否真的被消费端读到。"""
        mgr = get_plugin_manager()
        if mgr is None:
            return
        try:
            skills = mgr.all_writing_skills()
            libs = mgr.all_libraries()
            exporters = mgr.all_exporters()
        except Exception as exc:  # noqa: BLE001 - 统计失败不该影响面板
            logger.debug(f"[插件中心] 汇总能力失败：{exc}")
            return
        lib_count = sum(len(v) for v in libs.values())
        if not (skills or lib_count or exporters):
            self._set_effect("当前没有已启用的插件提供写作技能 / 素材库 / 导出格式。", "info")
            return
        self._set_effect(
            f"已生效：{len(skills)} 个写作技能包注入写作提示词"
            f" · {lib_count} 个素材库扩充"
            f" · {len(exporters)} 个导出格式",
            "success",
        )

    def _set_detail(self, text: str) -> None:
        self._detail.config(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.config(state=tk.DISABLED)

    def _info_of(self, name: str) -> dict:
        for info in self._plugins:
            if str(info.get("name")) == name:
                return info
        return {}

    def _on_pick(self) -> None:
        name = self._selected_name()
        self._current = name
        info = self._info_of(name)
        if not info:
            return
        lines = plugin_detail_lines(info)
        text = "\n".join(f"{title}：{value}" for title, value in lines)
        self._set_detail(text)
        # 按钮状态按选中项调整（加载失败的插件不允许启用）
        broken = bool(info.get("load_error"))
        self._enable_btn.config(state=tk.DISABLED if broken or info.get("enabled") else tk.NORMAL)
        self._disable_btn.config(state=tk.NORMAL if info.get("enabled") else tk.DISABLED)

    # ------------------------------------------------------------------ 动作

    def _on_open_dir(self) -> None:
        mgr = self._manager()
        if mgr is None:
            return
        mgr.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(mgr.plugins_dir)

    @staticmethod
    def _open_path(path: Path) -> None:
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
            logger.debug(f"[插件中心] 打开目录失败：{exc}")

    def _on_install(self) -> None:
        if self._busy:
            self._set_effect("正在安装上一个插件，请稍候…", "info")
            return
        mgr = self._manager()
        if mgr is None:
            return
        # ❗ 本仓的弹窗一律走 `app.dialogs`（有门禁）；`dialogs.ask_text` 需要 parent。
        # 这里用"先选来源类型，再按类型取路径"的两步式，而不是自造一个选择对话框 ——
        # 复用既有 `filedialog` 与 `ask_text` 才能保持一致的外观与校验行为。
        parent = self._host_widget()
        kind = dialogs.ask_text(
            parent,
            "安装插件",
            "选择来源类型并填入内容：\n\n"
            "  dir  —— 本地目录（下一步选目录）\n"
            "  zip  —— ZIP 压缩包（下一步选文件）\n"
            "  url  —— 直链或 GitHub 仓库地址（下一步粘贴 URL）\n\n"
            "请输入 dir / zip / url：",
        )
        if kind is None:
            return
        kind = kind.strip().lower()
        if kind not in ("dir", "zip", "url"):
            self._set_effect("来源类型无效，请输入 dir / zip / url", "error")
            return

        source = ""
        if kind == "dir":
            source = filedialog.askdirectory(title="选择插件目录") or ""
        elif kind == "zip":
            source = (
                filedialog.askopenfilename(
                    title="选择插件 ZIP",
                    filetypes=[("ZIP 压缩包", "*.zip"), ("所有文件", "*.*")],
                )
                or ""
            )
        else:
            source = dialogs.ask_text(parent, "从 URL 安装", "插件 ZIP 直链或 GitHub 仓库地址：") or ""
        source = source.strip()
        if not source:
            return

        self._busy = True
        self._set_effect(f"正在安装：{source} …", "info")
        # 下载/解压是网络 + 磁盘操作，走后台线程，回主线程再碰控件（Tk 非线程安全）
        self._runner.submit(
            mgr.install,
            source,
            on_success=self._after_install,
            on_finally=self._clear_busy,
        )

    def _clear_busy(self) -> None:
        self._busy = False

    def _after_install(self, result: PluginResult) -> None:
        if not isinstance(result, PluginResult):
            self._set_effect("安装返回了非预期结果", "error")
            return
        kind = "success" if result.ok else "error"
        self._set_effect(result.message, kind)
        if result.security_warning:
            # 安全提示用**模态**：它要求用户明确知道"我即将运行别人的代码"
            dialogs.showwarning("安全提示", result.security_warning)
        self._on_reload()

    def _on_enable(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            self._set_effect("请先在左侧选中一个插件", "info")
            return
        result = mgr.enable(name)
        self._set_effect(result.message, "success" if result.ok else "error")
        if result.ok and result.security_warning:
            dialogs.showwarning("安全提示", result.security_warning)
        self._on_reload()
        self._on_pick()

    def _on_disable(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            return
        result = mgr.disable(name)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._on_pick()

    def _on_uninstall(self) -> None:
        mgr = self._manager()
        name = self._selected_name()
        if mgr is None or not name:
            return
        if not dialogs.confirm(
            f"确定要删除插件「{name}」的全部文件吗？此操作不可撤销。",
            title="卸载插件",
            parent=self._host_widget(),
        ):
            return
        result = mgr.uninstall(name)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._set_detail("已卸载。")
