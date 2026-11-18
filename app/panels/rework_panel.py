"""回炉重造工作台（第 20 个面板）。

## 它解决什么

章节编辑区（`chapter_ui`）只有读写/导航/导出，**没有"这章有问题，打回去重做"的位置**。
于是存量低质量章节永远停在原地：软件侧的判定（质检门禁、评审判据、一致性）
管不到它们，作者也没法把"要重写"这件事从脑子里搬进系统。

本面板是那个位置：一张队列、一套受控状态、一份不可删的原文存档。

## 界面的三个区

| 区 | 内容 | 说明 |
|---|---|---|
| 工具条 | 扫描 / 全部入炉 / 刷新 + 统计 | 扫描走**后台线程**（1094 章要跑质检） |
| 左：队列 | 章节 / 状态 / 原因 / 次数 / 更新时间 | 双击行 = 在主编辑器打开该章 |
| 右：详情 | 原因证据 + 状态流水 + 归档版本 | 操作按钮按当前状态**动态启用** |

## 为什么按钮是动态启用的，而不是点了再报错

状态机的合法去向由 `rework.TRANSITIONS` 决定。界面上把非法的按钮置灰，
是为了让"下一步能做什么"**一眼可见** —— 让用户点一下再收到"不能从待重写直接定稿"
的报错，是把这个认知成本推给用户。

（`rework.transition()` 仍会再校验一次：界面置灰是体验，状态机校验是契约。）
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Optional

from loguru import logger

from app.async_runner import BackgroundRunner, CancelToken
from app.bulk_rewrite import BulkProgress, BulkRewriter
from app.dialogs import askyesno, show_text
from app.rework import (
    MAX_ATTEMPTS,
    REASON_LABELS,
    STATUS_LABELS,
    TRANSITIONS,
    ReworkError,
    ReworkStore,
    scan,
)
from app.ui_style import UIStyle

from . import ui_kit
from .base import BasePanel

__all__ = ["ReworkPanel"]

#: 候选超过这个数量时，批量入炉前先确认。
#: 真实作品实测：1094 章里 1077 章（98.4%）命中 —— 没有闸门就是"一点就写满盘"。
BULK_CONFIRM_THRESHOLD = 20

#: 表格列（与 `_fill_tree` 一一对应）。
COLUMNS = ["章节", "状态", "回炉原因", "次数", "更新时间"]
WIDTHS = [64, 84, 300, 48, 132]


class ReworkPanel(BasePanel):
    """回炉重造：把低质量章节送进重写流程，并留下原文与流水。"""

    key = "rework"
    title = "回炉重造"
    category = "运维"
    order = 64
    description = "扫描低质量章节，打回重写流程；保留原文与历史版本，可审核、定稿或废弃"

    #: 章节保存后队列可能变化（章号/内容）；切书也要重载
    topics_of_interest = ("chapter.saved", "novel.opened", "novel.closed")

    # ------------------------------------------------------------------ 状态

    def _store(self) -> Optional[ReworkStore]:
        novel_dir = getattr(self.app, "current_novel_dir", None) if self.app is not None else None
        if not novel_dir:
            return None
        return ReworkStore(novel_dir)

    def _selected_chapter(self) -> int:
        selection = self._tree.selection() if getattr(self, "_tree", None) else ()
        if not selection:
            return 0
        try:
            return int(str(self._tree.item(selection[0], "values")[0]).lstrip("#"))
        except (ValueError, IndexError, tk.TclError):
            return 0

    def _log_safe(self, message: str) -> None:
        """宿主绑定则走宿主日志，否则只落 logger。

        ❗ `BackgroundRunner(log=self._log)` 在**未绑定宿主**时会抛：
        `BasePanel.__getattr__` 把未定义属性转发给宿主，宿主为 None 即抛。
        崩在构造 runner 这一步，后面的控件全来不及创建 —— 表现为面板一片空白。
        """
        host_log = getattr(self.app, "_log", None) if self.app is not None else None
        if callable(host_log):
            host_log(message)
        else:
            logger.debug(f"[回炉] {message}")

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._candidates: list[dict[str, Any]] = []
        self._runner = BackgroundRunner(ui=getattr(self.app, "root", None), log=self._log_safe)

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 工具条（toolbar 不自行 pack；button / badge 需显式挂载）
        bar = ui_kit.toolbar(body)
        bar["bar"].pack(fill=tk.X)
        self._scan_btn = ui_kit.button(bar["left"], "扫描低质量章节", self._on_scan, kind="primary")
        self._scan_btn.pack(side=tk.LEFT)
        self._enqueue_btn = ui_kit.button(bar["left"], "全部入炉", self._on_enqueue_all, kind="ghost")
        self._enqueue_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        ui_kit.button(bar["left"], "刷新", self._on_refresh, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        self._count_badge = ui_kit.badge(bar["right"], "未扫描", kind="info")
        self._count_badge.pack(side=tk.RIGHT)

        # ---- 全书重写区
        # 与"回炉"的分工：回炉只把章**打回队列**（改状态），这里才真的**调模型重写正文**。
        # 两者串起来是完整流水线：扫描 → 入炉 → 整书重写 → 审核 → 定稿。
        bulk = tk.Frame(body, bg=C["bg_dark"])
        bulk.pack(fill=tk.X, pady=(ui_kit.SPACE["xs"], 0))
        ui_kit.section_title(bulk, "全书重写").pack(side=tk.LEFT)
        self._bulk_start_btn = ui_kit.button(bulk, "开始整书重写", self._on_bulk_start, kind="primary")
        self._bulk_start_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._bulk_pause_btn = ui_kit.button(bulk, "暂停", self._on_bulk_toggle_pause, kind="ghost")
        self._bulk_pause_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["xs"], 0))
        self._bulk_cancel_btn = ui_kit.button(bulk, "取消", self._on_bulk_cancel, kind="danger")
        self._bulk_cancel_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["xs"], 0))
        self._bulk_bar = ttk.Progressbar(bulk, mode="determinate", maximum=100, length=220)
        self._bulk_bar.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._bulk_status = ui_kit.hint(bulk, "未开始")
        self._bulk_status.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._bulk_rewriter: Any = None
        self._bulk_token: Any = None
        self._bulk_busy = False
        self._bulk_set_idle()

        # ---- 左右分栏
        split = tk.Frame(body, bg=C["bg_dark"])
        split.pack(fill=tk.BOTH, expand=True, padx=2, pady=(ui_kit.SPACE["sm"], 2))

        left = tk.Frame(split, bg=C["bg_dark"], width=620)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left.pack_propagate(False)
        ui_kit.section_title(left, "回炉队列").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
        holder = ui_kit.pretty_tree(
            left,
            columns=COLUMNS,
            widths=WIDTHS,
            height=13,
            on_select=lambda _e: self._on_pick(),
            on_double=lambda _e: self._on_open_chapter(),
        )
        holder["frame"].pack(fill=tk.BOTH, expand=True)  # ❗ pretty_tree 的 frame 需自行 pack
        self._tree = holder["tree"]

        right = tk.Frame(split, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        ui_kit.section_title(right, "原因与历史").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
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
            height=13,
        )
        self._detail.pack(fill=tk.BOTH, expand=True)
        self._detail.config(state=tk.DISABLED)

        # ---- 状态流转按钮（按当前状态动态启用）
        actions = tk.Frame(right, bg=C["bg_dark"])
        actions.pack(fill=tk.X, pady=(6, 2))
        self._action_buttons: dict[str, Any] = {}
        for label, target in (
            ("开始重写", "reworking"),
            ("提交审核", "pending_review"),
            ("审核通过", "approved"),
            ("定稿", "published"),
        ):
            button = ui_kit.button(actions, label, lambda t=target: self._on_transition(t), kind="ghost")
            button.pack(side=tk.LEFT, padx=(0, ui_kit.SPACE["xs"]))
            self._action_buttons[target] = button
        self._reopen_btn = ui_kit.button(actions, "退回正常", lambda: self._on_transition("draft"), kind="ghost")
        self._reopen_btn.pack(side=tk.LEFT, padx=(0, ui_kit.SPACE["xs"]))
        self._discard_btn = ui_kit.button(actions, "废弃", self._on_discard, kind="danger")
        self._discard_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))

        # ---- 底部
        self._effect_line = ui_kit.hint(body, "")
        self._effect_line.pack(fill=tk.X, pady=(4, 0))

        self._on_refresh()
        self.mark_built(True)  # ❗ 不标记会被宿主反复重建
        return body

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        if self.is_built:
            self._on_refresh()

    def on_event(self, topic: str, payload: Any = None) -> None:
        """章节保存 / 换书 → 队列可能变化，刷新即可（不做重建）。"""
        if self.is_built:
            self._on_refresh()

    # ------------------------------------------------------------------ 渲染

    def _fill_tree(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        store = self._store()
        if store is None:
            return
        for record in store.all():
            tree.insert(
                "",
                tk.END,
                values=(
                    f"#{record.chapter}",
                    record.status_label,
                    f"{record.reason_label}：{record.reason_text}"[:60],
                    str(record.attempts),
                    record.updated_at.replace("T", " ")[:16],
                ),
            )

    def _refresh_badge(self) -> None:
        store = self._store()
        if store is None:
            self._count_badge.config(text="未打开作品")
            return
        stats = store.stats()
        pending = stats.get("pending_rework", 0) + stats.get("reworking", 0)
        review = stats.get("pending_review", 0)
        done = stats.get("published", 0) + stats.get("discarded", 0)
        text = f"队列 {len(store.all())} · 处理中 {pending} · 待审 {review} · 已结 {done}"
        if self._candidates:
            text += f" · 候选 {len(self._candidates)}"
        self._count_badge.config(text=text)

    def _update_actions(self) -> None:
        """按选中章节的状态启用/置灰按钮。"""
        store = self._store()
        chapter = self._selected_chapter()
        record = store.get(chapter) if (store is not None and chapter) else None
        allowed = set(TRANSITIONS.get(record.status, ())) if record is not None else set()

        for target, button in self._action_buttons.items():
            is_reopen = target == "draft"
            enabled = target in allowed or (is_reopen and record is not None and target in allowed)
            button.config(state=tk.NORMAL if enabled else tk.DISABLED)
        self._reopen_btn.config(state=tk.NORMAL if "draft" in allowed else tk.DISABLED)
        self._discard_btn.config(state=tk.NORMAL if (record is not None and "discarded" in allowed) else tk.DISABLED)

    def _render_detail(self) -> None:
        store = self._store()
        chapter = self._selected_chapter()
        if store is None or not chapter:
            self._set_detail("在左侧选择一章查看回炉原因与历史。")
            return
        record = store.get(chapter)
        if record is None:
            self._set_detail(
                f"第 {chapter} 章不在回炉队列中。\n\n"
                f"如需打回重写，先点「扫描低质量章节」找到它，或在下方的候选清单里入炉。"
            )
            return

        lines = [
            f"第 {chapter} 章 · {record.status_label}",
            "",
            f"原因：{record.reason_label}",
            f"说明：{record.reason_text or '（未填写）'}",
            f"已回炉：{record.attempts} 次（上限 {MAX_ATTEMPTS}）",
            f"入炉时间：{record.created_at.replace('T', ' ')}",
            "",
        ]
        if record.evidence:
            lines.append("判定证据：")
            for key, value in record.evidence.items():
                if isinstance(value, (list, tuple)):
                    lines.append(f"  · {key}: {'、'.join(str(v) for v in value[:5])}")
                else:
                    lines.append(f"  · {key}: {value}")
            lines.append("")

        versions = store.list_versions(chapter)
        if versions:
            lines.append(f"归档版本（{len(versions)} 个，只增不删）：")
            for row in versions:
                lines.append(
                    f"  v{row['version']} · {row['chars']} 字 · "
                    f"{str(row['at']).replace('T', ' ')[:16]} · {row['note'] or '—'}"
                )
            lines.append("")

        lines.append("状态流水：")
        for event in record.history:
            lines.append(
                f"  {event.at.replace('T', ' ')[:16]} → {STATUS_LABELS.get(event.status, event.status)}"
                + (f"（{event.note}）" if event.note else "")
            )
        self._set_detail("\n".join(lines))

    def _set_effect(self, text: str, kind: str = "info") -> None:
        if not getattr(self, "_effect_line", None):
            return
        colors = {
            "info": UIStyle.COLORS.get("text_secondary", "#94a3b8"),
            "success": UIStyle.COLORS.get("success_text", "#22c55e"),
            "error": UIStyle.COLORS.get("error_text", "#ef4444"),
        }
        try:
            self._effect_line.config(text=text, fg=colors.get(kind, colors["info"]))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ 动作

    def _on_refresh(self) -> None:
        self._fill_tree()
        self._refresh_badge()
        self._update_actions()
        self._render_detail()

    def _on_pick(self) -> None:
        self._update_actions()
        self._render_detail()

    def _on_open_chapter(self) -> None:
        """双击队列行 → 让主编辑器打开该章（不在本面板改正文）。"""
        chapter = self._selected_chapter()
        if not chapter or self.app is None:
            return
        loader = getattr(self.app, "_load_chapter_by_number", None)
        if callable(loader):
            try:
                loader(chapter)
                self._set_effect(f"已在编辑区打开第 {chapter} 章", "success")
                return
            except Exception as exc:  # noqa: BLE001 - 宿主接口可能变化
                logger.debug(f"[回炉] 跳转章节失败：{exc}")
        self._set_effect("宿主未提供章节跳转接口", "info")

    # ------------------------------------------------------------------ 全书重写

    def _bulk_ai_client(self) -> Any:
        """优先用宿主已配置的客户端；宿主没有就自己构造一个。

        构造失败返回 `None` —— 由调用方给出"请先在 AI 设置里配置"的提示，
        而不是让按钮点了没反应。
        """
        client = getattr(self.app, "ai_client", None) if self.app is not None else None
        if client is not None:
            return client
        try:
            from app.ai_client import AIClient
            from app.config import AppConfig

            return AIClient(AppConfig())
        except Exception as exc:  # noqa: BLE001 - 配置损坏也不该让面板崩
            logger.warning(f"[整书重写] 构造 AI 客户端失败：{exc}")
            return None

    def _bulk_ui(self, fn) -> None:
        """把回调排到主线程。`BulkRewriter` 的进度回调在**后台线程**触发。"""
        root = getattr(self.app, "root", None) if self.app is not None else None
        after = getattr(root, "after", None)
        if callable(after):
            try:
                after(0, fn)
                return
            except tk.TclError:
                pass
        fn()

    def _bulk_set_idle(self) -> None:
        """回到空闲态：只有「开始」可点。"""
        if not getattr(self, "_bulk_start_btn", None):
            return
        self._bulk_start_btn.config(state=tk.NORMAL)
        self._bulk_pause_btn.config(state=tk.DISABLED, text="暂停")
        self._bulk_cancel_btn.config(state=tk.DISABLED)

    def _bulk_set_running(self) -> None:
        self._bulk_start_btn.config(state=tk.DISABLED)
        self._bulk_pause_btn.config(state=tk.NORMAL, text="暂停")
        self._bulk_cancel_btn.config(state=tk.NORMAL)

    def _on_bulk_start(self) -> None:
        """整书重写：先实测 AI 可用性 + 出规模预估，确认后才执行。

        🔴 顺序很重要：**先实测再执行**。本机出现过"配置文件里有 key 但服务端回 401"，
        不实测就会让用户点完"开始"后看 1094 章连续失败。
        """
        if getattr(self, "_bulk_busy", False):
            self._set_effect("正在执行中，请先暂停或取消", "info")
            return

        novel_dir = getattr(self.app, "current_novel_dir", None) if self.app is not None else None
        if not novel_dir:
            self._set_effect("没有打开的作品", "info")
            return

        ai = self._bulk_ai_client()
        if ai is None:
            self._set_effect("没有可用的 AI 客户端 —— 请先在「AI 设置」里配置服务与密钥", "error")
            return

        self._bulk_busy = True
        self._bulk_start_btn.config(state=tk.DISABLED)
        self._bulk_status.config(text="正在检查 AI 与统计规模…")
        self._set_effect("正在检查 AI 可用性（会发一次最小请求）…", "info")

        rewriter = BulkRewriter(novel_dir, ai)
        self._bulk_rewriter = rewriter

        def probe() -> tuple[bool, str, Any]:
            ok, why = rewriter.check_ai()
            return ok, why, (rewriter.plan() if ok else None)

        self._runner.submit(
            probe,
            on_success=self._on_bulk_probed,
            on_error=self._on_bulk_probe_failed,
            log_errors=True,
        )

    def _on_bulk_probe_failed(self, exc: BaseException) -> None:
        self._bulk_busy = False
        self._bulk_set_idle()
        self._bulk_status.config(text="检查失败")
        self._set_effect(f"检查 AI 失败：{exc}", "error")

    def _on_bulk_probed(self, result: tuple[bool, str, Any]) -> None:
        ok, why, plan = result
        if not ok:
            self._bulk_busy = False
            self._bulk_set_idle()
            self._bulk_status.config(text="AI 不可用")
            self._set_effect(f"AI 不可用：{why}", "error")
            show_text(
                self._host_widget(),
                "AI 不可用，无法整书重写",
                "整书重写需要调用大模型，但当前 AI 服务不可用：\n\n"
                f"{why}\n\n"
                "请到「AI 设置」检查服务地址与 API Key 是否有效，然后重试。\n"
                "（这一检查是**实测**——发一次真实请求，而不是只看配置里有没有填 key。）",
            )
            return

        if plan.todo_chapters == 0:
            self._bulk_busy = False
            self._bulk_set_idle()
            self._bulk_status.config(text="无需重写")
            self._set_effect(f"全部 {plan.chapters} 章都已重写，无需重复处理", "success")
            return

        if not askyesno(
            "确认整书重写",
            f"{plan.as_text()}\n\n"
            "重写只改文字表达，不改情节、人物、对话与专名；\n"
            "结果写入 chapters_rewritten/，**原文不会被覆盖**；\n"
            "中途可暂停或取消，下次继续时只补未完成的章。\n\n开始执行？",
        ):
            self._bulk_busy = False
            self._bulk_set_idle()
            self._bulk_status.config(text="已取消")
            self._set_effect("已取消，未做任何改动", "info")
            return

        self._bulk_run(plan)

    def _bulk_run(self, plan: Any) -> None:
        rewriter = self._bulk_rewriter
        if rewriter is None:
            self._bulk_busy = False
            self._bulk_set_idle()
            return

        self._bulk_set_running()
        self._bulk_bar["value"] = 0
        self._bulk_status.config(text=f"开始：{plan.todo_chapters} 章待处理")

        def progress(update: BulkProgress) -> None:
            self._bulk_ui(lambda p=update: self._on_bulk_progress(p))

        # 先建 token 再派发：work 通过**闭包捕获**它，不依赖"submit 之后赋值"的时序
        # （旧写法 `self._bulk_token = submit(...)` 有竞态：work 可能先跑，读到 None）
        token = CancelToken("用户取消")
        self._bulk_token = token
        self._runner.submit_cancellable(
            lambda: rewriter.run(on_progress=progress, token=token),
            token=token,
            on_success=self._on_bulk_done,
            on_cancelled=self._on_bulk_cancelled,
            on_error=self._on_bulk_error,
            log_errors=True,
        )

    def _on_bulk_progress(self, update: BulkProgress) -> None:
        try:
            self._bulk_bar["value"] = update.percent
            self._bulk_status.config(text=update.as_line())
        except tk.TclError:
            return

    def _on_bulk_toggle_pause(self) -> None:
        rewriter = self._bulk_rewriter
        if rewriter is None:
            return
        if rewriter.paused:
            rewriter.resume()
            self._bulk_pause_btn.config(text="暂停")
            self._set_effect("已继续", "info")
        else:
            rewriter.pause()
            self._bulk_pause_btn.config(text="继续")
            self._set_effect("已暂停（当前块完成后停住）", "info")

    def _on_bulk_cancel(self) -> None:
        token = self._bulk_token
        if token is not None:
            try:
                token.cancel("用户取消")
            except Exception as exc:  # noqa: BLE001 - 取消失败也要给出反馈
                logger.debug(f"[整书重写] 取消失败：{exc}")
        if self._bulk_rewriter is not None:
            self._bulk_rewriter.resume()  # 暂停中也能取消
        self._set_effect("正在取消（当前块结束后停止）…", "info")

    def _on_bulk_done(self, stats: Any) -> None:
        self._bulk_busy = False
        self._bulk_set_idle()
        self._bulk_bar["value"] = 100
        rewriter = self._bulk_rewriter
        text = stats.as_text() if stats is not None else "完成"
        self._bulk_status.config(text=text)
        self._set_effect(text, "success" if not getattr(stats, "failed", 0) else "error")
        if rewriter is not None:
            show_text(self._host_widget(), "整书重写完成", rewriter.summary_text())
        self._on_refresh()

    def _on_bulk_cancelled(self) -> None:
        self._bulk_busy = False
        self._bulk_set_idle()
        self._bulk_status.config(text="已取消")
        self._set_effect("已取消（已完成的章已写入日志，下次继续时跳过）", "info")
        self._on_refresh()

    def _on_bulk_error(self, exc: BaseException) -> None:
        self._bulk_busy = False
        self._bulk_set_idle()
        self._bulk_status.config(text="出错")
        self._set_effect(f"整书重写出错：{exc}", "error")

    # ------------------------------------------------------------------ 扫描

    def _on_scan(self) -> None:
        """扫描走后台：1094 章要逐章跑质检，放主线程会卡界面。"""
        store = self._store()
        if store is None:
            self._set_effect("没有打开的作品", "info")
            return
        novel_dir = store.novel_dir
        self._set_effect("正在扫描（逐章质检，可能需要一会儿）…", "info")

        # `on_success` / `on_error` 由 runner 调度回主线程 —— 不要在子线程里碰控件
        self._runner.submit(
            lambda: scan(novel_dir, store),
            on_success=self._on_scan_done,
            on_error=lambda exc: self._set_effect(f"扫描失败：{exc}", "error"),
            log_errors=True,
        )

    def _on_scan_done(self, found: list[dict[str, Any]]) -> None:
        self._candidates = found
        self._refresh_badge()
        if not found:
            self._set_effect("扫描完成：没有发现需要回炉的章节", "success")
            return
        groups: dict[str, int] = {}
        for item in found:
            groups[item["reason_code"]] = groups.get(item["reason_code"], 0) + 1
        summary = "、".join(f"{REASON_LABELS.get(k, k)} {v} 章" for k, v in groups.items())
        self._set_effect(f"扫描完成：{len(found)} 章候选（{summary}）—— 点「全部入炉」处理", "success")
        preview = "\n".join(
            f"第 {item['chapter']} 章 · {REASON_LABELS.get(item['reason_code'], item['reason_code'])}"
            f" · {item['reason_text']}"
            for item in found[:40]
        )
        if len(found) > 40:
            preview += f"\n…（另有 {len(found) - 40} 章）"
        show_text(
            self._host_widget(),
            f"扫描到 {len(found)} 章候选",
            "以下章节建议回炉重造。入炉会**先归档当前原文**，再进入重写队列。\n\n" + preview,
        )

    def _on_enqueue_all(self) -> None:
        """把扫描候选批量入炉。已入炉 / 不适用（空章、超次数）的跳过并计数。"""
        store = self._store()
        if store is None:
            self._set_effect("没有打开的作品", "info")
            return
        if not self._candidates:
            self._set_effect("还没有候选 —— 先点「扫描低质量章节」", "info")
            return

        # 规模较大时先确认：真实作品一次可能上千章，入炉会写上千个归档文件。
        # 十几个章的用户不需要多点一次；上千章的必须知道自己要做什么。
        if len(self._candidates) > BULK_CONFIRM_THRESHOLD:
            if not askyesno(
                "确认批量入炉",
                f"即将把 {len(self._candidates)} 章送入回炉队列。\n\n"
                "每章会先归档当前原文（写入 rework/archive/），再进入重写队列；"
                "归档只增不删。\n\n继续？",
            ):
                self._set_effect("已取消：未做任何改动", "info")
                return

        added = 0
        skipped: list[str] = []
        for item in self._candidates:
            chapter = int(item["chapter"])
            try:
                store.enqueue(
                    chapter,
                    item["reason_code"],
                    item["reason_text"],
                    evidence=item.get("evidence"),
                )
                added += 1
            except ReworkError as exc:
                skipped.append(f"#{chapter}（{exc}）")
            except Exception as exc:  # noqa: BLE001 - 单章失败不该中断整批
                skipped.append(f"#{chapter}（{exc}）")

        self._candidates = []
        self._on_refresh()
        message = f"已入炉 {added} 章"
        if skipped:
            message += f"；跳过 {len(skipped)} 章：{'、'.join(skipped[:5])}"
            if len(skipped) > 5:
                message += "…"
        self._set_effect(message, "success" if added else "error")

    def _on_transition(self, target: str) -> None:
        store = self._store()
        chapter = self._selected_chapter()
        if store is None or not chapter:
            self._set_effect("先在左侧选中一章", "info")
            return
        try:
            record = store.transition(chapter, target)
        except ReworkError as exc:
            self._set_effect(f"无法推进：{exc}", "error")
            return
        self._on_refresh()
        self._set_effect(f"第 {chapter} 章 → {record.status_label}", "success")

    def _on_discard(self) -> None:
        store = self._store()
        chapter = self._selected_chapter()
        if store is None or not chapter:
            self._set_effect("先在左侧选中一章", "info")
            return
        try:
            store.discard(chapter)
        except ReworkError as exc:
            self._set_effect(f"无法废弃：{exc}", "error")
            return
        self._on_refresh()
        self._set_effect(f"第 {chapter} 章已标记废弃（原文与归档保留）", "success")
