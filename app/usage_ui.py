"""用量统计面板（v3 §3.5(5)）。

## 面板回答的问题

| 子页 | 回答 |
|---|---|
| 按章 | 每章花了多少 token / 多久 / 多少钱（含章节列表徽标的数据源） |
| 按服务 | 各 provider 的消耗占比，以及**这家有没有余额接口** |
| 按任务 | 大纲 / 正文 / 审校 / 角色 / 传记 … 各占多少 |
| 按模型 | 换模型前后消耗怎么变 |
| 价目表 | 内置价目的**来源、查证日期与置信度**（价格会变，用户要能自己判断） |

## 三条诚实原则（与 §3.4 一致）

1. **实测与估算分开显示**：`estimated=True` 的记录在 UI 上带 `≈` 前缀 ——
   把估算当实测展示，会让成本数字变成谎言。
2. **未定价就说未定价**：价目表里没有的模型，成本列显示 `无价目`，
   **不显示 ¥0.0000** —— 后者会被读成"免费"。
3. **有余额接口才显示金额**，否则明说原因（"该服务未提供余额接口" /
   "余额接口需在设置中填写"），而不是报错或留空。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app import UIStyle
from app.events import TOPIC_AI_USAGE

from .async_runner import BackgroundRunner
from .providers import balance as balance_module
from .providers.pricing import PRICE_TABLE_VERIFIED_AT, all_prices
from .token_estimator import format_tokens
from .usage_tracker import usage_tracker

__all__ = ["UsagePanelMixin", "TASK_LABELS", "summarize_rows", "format_cost_cell"]

#: 任务类型的显示名（面板与 CSV 都用它）
TASK_LABELS = {
    "chapter": "正文",
    "outline": "大纲",
    "review": "审校",
    "characters": "角色",
    "biography": "传记",
    "summary": "摘要",
    "polish": "润色",
    "": "未分类",
}


def format_cost_cell(bucket: dict) -> str:
    """把聚合桶渲染成成本单元格。

    未定价（`costs` 为空）与"定价为 0"（本地模型）必须能区分：
    前者显示 `无价目`，后者显示 `¥0.0000`。
    """
    costs = bucket.get("costs") or {}
    if not costs:
        return "无价目"
    return usage_tracker.format_costs(costs)


def summarize_rows(summary: dict) -> str:
    """一行概览文本（面板顶部与状态栏共用）。"""
    totals = summary.get("totals") or {}
    calls = int(totals.get("calls") or 0)
    total = int(totals.get("total_tokens") or 0)
    estimated = int(totals.get("estimated_calls") or 0)
    errors = int(totals.get("errors") or 0)
    measured_calls = max(0, calls - estimated)

    parts = [
        f"累计 {format_tokens(total)} tokens",
        f"实测 {measured_calls} 次 / 估算 {estimated} 次" if estimated else f"{calls} 次调用",
    ]
    if calls:
        parts.append(f"成本 {usage_tracker.format_costs(totals.get('costs') or {})}")
    if errors:
        parts.append(f"失败 {errors} 次")
    return " · ".join(parts)


class UsagePanelMixin:
    """「用量统计」面板 + 与主面板的联动点。"""

    # ------------------------------------------------------------ 联动入口

    def _bind_usage_novel(self, novel_dir) -> None:
        """切换当前小说（新建/打开/续集/同人）时同步用量目录。

        由 `lifecycle_ui` 在 4 处 `self.current_novel_dir = ...` 之后调用 ——
        没有做成 property，是因为「Mixin 拆分行为不变」的审计口径要求
        属性赋值语义保持原样，显式调用更容易被审查。
        """
        try:
            usage_tracker.set_novel_dir(novel_dir)
        except Exception as exc:  # noqa: BLE001 - 统计不影响主流程
            self._log(f"[用量] 切换统计目录失败：{exc}")

    def _usage_status_text(self) -> str:
        """状态栏用的短文本（由 `shell_ui._update_status` 拼接）。"""
        try:
            return summarize_rows(usage_tracker.summary())
        except Exception as exc:  # noqa: BLE001
            return f"用量统计不可用（{type(exc).__name__}）"

    def _subscribe_usage_events(self) -> None:
        """订阅 `ai.usage`（v3 §2.3）：每条记录落账后即时刷新概览行。

        只更新顶部的概览与提示文本，**不重建 Treeview** —— 用量页常被开着
        "看着花销"，重建会把用户正在看的选中行与滚动位置打断。
        """
        bus = getattr(self, "event_bus", None)
        if bus is None:
            return
        self._usage_unsubscribe = bus.subscribe(TOPIC_AI_USAGE, self._on_usage_recorded)

    def _on_usage_recorded(self, _topic, _payload=None) -> None:
        """`ai.usage` 处理器：重算概览文本。单条记录不影响分页明细，故不重填表格。"""
        if not getattr(self, "usage_summary_var", None):
            return
        try:
            self.usage_summary_var.set(summarize_rows(usage_tracker.summary()))
        except Exception as exc:  # noqa: BLE001 - 刷新失败不该冒泡
            self.usage_summary_var.set(f"读取用量失败：{type(exc).__name__}: {exc}")

    def _chapter_token_badges(self) -> dict:
        """`{章号: token}` —— 章节列表徽标用。异常时返回空表，不打断列表渲染。"""
        try:
            return usage_tracker.chapter_tokens()
        except Exception as exc:  # noqa: BLE001
            self._log(f"[用量] 读取章节用量失败：{exc}")
            return {}

    # ------------------------------------------------------------ 构建

    def _build_usage_tab(self, parent) -> None:
        """构建面板（`shell_ui` 在 notebook 里调用一次）。"""
        C = UIStyle.COLORS

        head = tk.Frame(parent, bg=C["bg_dark"])
        head.pack(fill=tk.X, padx=15, pady=(12, 4))

        self.usage_summary_var = tk.StringVar(value="（暂无用量记录）")
        tk.Label(
            head,
            textvariable=self.usage_summary_var,
            font=UIStyle.font("body_bold"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
            anchor=tk.W,
            justify=tk.LEFT,
        ).pack(fill=tk.X)

        self.usage_hint_var = tk.StringVar(value="")
        tk.Label(
            head,
            textvariable=self.usage_hint_var,
            font=UIStyle.font("caption"),
            bg=C["bg_dark"],
            fg=C["text_secondary"],
            anchor=tk.W,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(2, 0))

        buttons = tk.Frame(parent, bg=C["bg_dark"])
        buttons.pack(fill=tk.X, padx=15, pady=(2, 6))
        self._usage_button(buttons, "🔄 刷新", self._refresh_usage_panel, C["accent"])
        self._usage_button(buttons, "📤 导出 CSV", self._export_usage_csv, C["bg_light"])
        self._usage_button(buttons, "💰 查询余额", self._query_balance_async, C["success"])
        self._usage_button(buttons, "📂 打开目录", self._open_usage_dir, C["bg_light"])
        self._usage_button(buttons, "📋 复制概览", self._copy_usage_summary, C["bg_light"])

        balance_row = tk.Frame(parent, bg=C["bg_dark"])
        balance_row.pack(fill=tk.X, padx=15, pady=(0, 6))
        self.usage_balance_var = tk.StringVar(value="余额：未查询")
        tk.Label(
            balance_row,
            textvariable=self.usage_balance_var,
            font=UIStyle.font("label"),
            bg=C["bg_dark"],
            fg=C["text_primary"],
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=900,
        ).pack(fill=tk.X)

        sub = ttk.Notebook(parent, style="Dark.TNotebook")
        sub.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 12))
        self.usage_chapter_tree = self._build_usage_table(
            sub,
            " 按章 ",
            ("章号", "调用", "输入", "输出", "合计", "实测/估算", "耗时(秒)", "成本"),
            (70, 60, 90, 90, 100, 120, 90, 170),
        )
        self.usage_provider_tree = self._build_usage_table(
            sub,
            " 按服务 ",
            ("服务", "调用", "输入", "输出", "合计", "成本", "余额能力"),
            (150, 60, 90, 90, 100, 170, 300),
        )
        self.usage_task_tree = self._build_usage_table(
            sub,
            " 按任务 ",
            ("任务", "调用", "合计", "占比", "成本"),
            (140, 60, 110, 90, 170),
        )
        self.usage_model_tree = self._build_usage_table(
            sub,
            " 按模型 ",
            ("模型", "调用", "合计", "耗时(秒)", "成本"),
            (300, 60, 110, 90, 170),
        )
        self.usage_price_tree = self._build_usage_table(
            sub,
            " 价目表 ",
            ("服务", "模型", "区域", "币种", "输入/百万", "输出/百万", "缓存价", "置信度", "查证日期"),
            (120, 260, 100, 60, 100, 100, 90, 90, 100),
        )

        self._subscribe_usage_events()
        self._refresh_usage_panel()

    def _usage_button(self, parent, text: str, command, bg: str) -> tk.Button:
        color = UIStyle.COLORS
        button = tk.Button(
            parent,
            text=text,
            font=UIStyle.font("label"),
            bg=bg,
            fg="white" if bg in (color["accent"], color["success"]) else color["text_primary"],
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=command,
        )
        button.pack(side=tk.LEFT, padx=3)
        return button

    def _build_usage_table(self, notebook, title: str, columns, widths):
        C = UIStyle.COLORS
        frame = tk.Frame(notebook, bg=C["bg_dark"])
        notebook.add(frame, text=title)

        tree = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        for column, width in zip(columns, widths):
            tree.heading(column, text=column)
            tree.column(
                column,
                width=width,
                anchor=tk.CENTER if column not in ("服务", "模型", "任务", "余额能力", "成本", "区域") else tk.W,
            )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return tree

    # ------------------------------------------------------------ 刷新

    def _refresh_usage_panel(self, *_) -> None:
        """重算并刷新全部子页。异常只提示，不弹栈。"""
        try:
            summary = usage_tracker.summary()
        except Exception as exc:  # noqa: BLE001
            self.usage_summary_var.set(f"读取用量失败：{type(exc).__name__}: {exc}")
            return

        self.usage_summary_var.set(summarize_rows(summary))
        self.usage_hint_var.set(self._usage_hint())

        rows = usage_tracker.chapter_rows()
        self._fill_chapters(self.usage_chapter_tree, rows)
        self._fill_provider(self.usage_provider_tree, summary.get("by_provider") or {})
        self._fill_task(
            self.usage_task_tree,
            summary.get("by_task") or {},
            int((summary.get("totals") or {}).get("total_tokens") or 0),
        )
        self._fill_model(self.usage_model_tree, summary.get("by_model") or {})
        self._fill_prices(self.usage_price_tree)

    @staticmethod
    def _usage_hint() -> str:
        """数据来源与"是否含估算"的说明 —— 不解释清楚，用户会怀疑数字。"""
        target = usage_tracker.novel_dir
        if target is None:
            return "当前未打开小说：仅显示本次会话的内存统计（重启即清空）"
        detail = target / "usage" / "usage.jsonl"
        return (
            f"数据源：{detail}（重启不丢）· 带「≈」的行为估算值"
            f"（provider 未返回 usage）· 价目查证于 {PRICE_TABLE_VERIFIED_AT}"
        )

    def _clear_tree(self, tree) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _fill_chapters(self, tree, rows) -> None:
        self._clear_tree(tree)
        for row in rows:
            estimated = int(row.get("estimated_calls") or 0)
            calls = int(row.get("calls") or 0)
            tree.insert(
                "",
                tk.END,
                values=(
                    row.get("chapter"),
                    calls,
                    format_tokens(row.get("prompt_tokens")),
                    format_tokens(row.get("completion_tokens")),
                    format_tokens(row.get("total_tokens")),
                    f"{calls - estimated} / {estimated}" + (" ≈" if estimated else ""),
                    f"{float(row.get('latency_ms') or 0.0) / 1000.0:.1f}",
                    format_cost_cell(row),
                ),
            )

    def _fill_provider(self, tree, buckets) -> None:
        self._clear_tree(tree)
        for provider in sorted(buckets):
            bucket = buckets[provider]
            tree.insert(
                "",
                tk.END,
                values=(
                    provider,
                    bucket.get("calls"),
                    format_tokens(bucket.get("prompt_tokens")),
                    format_tokens(bucket.get("completion_tokens")),
                    format_tokens(bucket.get("total_tokens")),
                    format_cost_cell(bucket),
                    self._balance_capability_text(provider),
                ),
            )

    def _fill_task(self, tree, buckets, grand_total) -> None:
        self._clear_tree(tree)
        for task in sorted(buckets, key=lambda key: -int((buckets[key] or {}).get("total_tokens") or 0)):
            bucket = buckets[task]
            total = int(bucket.get("total_tokens") or 0)
            share = f"{total / grand_total * 100:.1f}%" if grand_total else "—"
            tree.insert(
                "",
                tk.END,
                values=(
                    TASK_LABELS.get(task, task or "未分类"),
                    bucket.get("calls"),
                    format_tokens(total),
                    share,
                    format_cost_cell(bucket),
                ),
            )

    def _fill_model(self, tree, buckets) -> None:
        self._clear_tree(tree)
        for model in sorted(buckets, key=lambda key: -int((buckets[key] or {}).get("total_tokens") or 0)):
            bucket = buckets[model]
            tree.insert(
                "",
                tk.END,
                values=(
                    model,
                    bucket.get("calls"),
                    format_tokens(bucket.get("total_tokens")),
                    f"{float(bucket.get('latency_ms') or 0.0) / 1000.0:.1f}",
                    format_cost_cell(bucket),
                ),
            )

    def _fill_prices(self, tree) -> None:
        self._clear_tree(tree)
        for price in all_prices():
            tier_note = f"（{len(price.tiers)} 档阶梯）" if price.tiers else ""
            tree.insert(
                "",
                tk.END,
                values=(
                    price.provider,
                    price.model + tier_note,
                    price.region,
                    price.currency,
                    f"{price.input:g}",
                    f"{price.output:g}",
                    "-" if price.cached_input is None else f"{price.cached_input:g}",
                    price.confidence,
                    price.verified_at,
                ),
            )

    @staticmethod
    def _balance_capability_text(provider: str) -> str:
        """这家能不能查余额 —— 面板直接说清楚，别让用户以为功能坏了。"""
        return balance_module.capability_text(provider)

    # ------------------------------------------------------------ 动作

    def _export_usage_csv(self) -> None:
        rows = usage_tracker.read_records()
        if not rows:
            messagebox.showinfo("提示", "暂无可导出的用量记录")
            return
        target = usage_tracker.novel_dir
        initial = Path(target) if target else Path.home()
        path = filedialog.asksaveasfilename(
            title="导出用量明细",
            defaultextension=".csv",
            initialdir=str(initial),
            initialfile="usage.csv",
            filetypes=[("CSV 文件", "*.csv"), ("全部文件", "*.*")],
        )
        if not path:
            return
        try:
            saved = usage_tracker.export_csv(path)
        except OSError as exc:
            messagebox.showerror("导出失败", f"无法写入 {path}\n{exc}")
            return
        self._log(f"[用量] 已导出 {len(rows)} 条记录 → {saved}")
        messagebox.showinfo("导出成功", f"已导出 {len(rows)} 条记录：\n{saved}")

    def _open_usage_dir(self) -> None:
        target = usage_tracker.novel_dir
        if target is None:
            messagebox.showwarning("提示", "请先打开小说")
            return
        path = target / "usage"
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(str(path))  # noqa: S606 - 打开资源管理器
        except (AttributeError, OSError) as exc:
            messagebox.showinfo("用量目录", f"{path}\n（无法自动打开：{exc}）")

    def _copy_usage_summary(self) -> None:
        text = self.usage_summary_var.get()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._log("[用量] 概览已复制到剪贴板")
        except tk.TclError as exc:
            self._log(f"[用量] 复制失败：{exc}")

    def _query_balance_async(self) -> None:
        """余额查询走后台线程（网络动作不能在事件回调里同步跑）。"""
        provider = self.config.get("api_provider", "") or ""
        self.usage_balance_var.set(f"余额：正在查询 {provider or '（未配置服务）'} …")

        runner = BackgroundRunner(ui=self.root, log=self._log)

        def work():
            return self.ai_client.query_balance(provider, use_cache=False)

        def done(result):
            self.usage_balance_var.set(f"余额：{result.format_total()}")
            self._log(f"[余额] {provider}: {result.format_total()}")

        def failed(exc):
            self.usage_balance_var.set(f"余额：查询失败 {type(exc).__name__}: {exc}（不影响其他功能）")
            self._log(f"[余额] 查询失败：{exc}")

        runner.submit(work, on_success=done, on_error=failed, name="anw-balance")
