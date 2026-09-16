"""世界线与时间线面板（v3 §2.4 ①）。

## 它解决什么

`timeline_ui._open_timeline` 是个 Toplevel 弹窗：数据源只认 `timelines/main.json`，
而真正在增长的是 `MemoryManager.add_event` 写的 `memory/timeline/`。
于是"作者每章记的事"与"时间线里看到的事"长期是两份。

本面板以 `TimelineStore` 为唯一数据入口，把两套合流，并给出**四视图**：

| 视图 | 数据 | 联动 |
|---|---|---|
| 章节轴 | `memory/timeline/` 按章聚合 | 双击事件 → 主编辑器跳到该章 |
| 世界线分支 | `timelines/*.json` 的 `branches` + `branch_*/` 子项目 | 展开查看抉择 |
| 人物轨迹泳道 | `character_activity.json`（事件源兜底） | 双击 → 打开传记面板 |
| 跨代编年史 | 父代 + 本代事件（`meta.lineage`） | 父代行灰显只读，禁止跳转 |

## 为什么不重写 `timeline_ui`

那个弹窗里有"生成分支小说"等重逻辑（`_generate_branch_story` 等）。破坏性重写的收益
低于风险，因此本面板是**新增视图 + 同步入口**，原弹窗原样保留；
两者共享同一份数据（都读 `timelines/`，本面板负责让它保持为事件源的镜像）。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from loguru import logger

from app.events import TOPIC_CHAPTER_SAVED, TOPIC_TIMELINE_CHANGED
from app.timeline_store import TimelineStore, extraction_prompt, parse_extraction_result
from app.ui_style import UIStyle

from . import ui_kit
from .base import BasePanel

__all__ = [
    "TimelinePanel",
    "branch_rows",
    "chapter_axis_rows",
    "chronicle_rows",
    "stats_text",
    "track_rows",
]


# ====================================================================== 纯数据行（可单测）


def chapter_axis_rows(rows: list[dict]) -> list[tuple[str, tuple]]:
    """章节轴 → Treeview 行。`iid` 用 `ch{章号}` 便于回调取章号。

    事件正文截断到 60 字：一列放不下整句，完整内容由面板下方详情区显示。
    """
    out: list[tuple[str, tuple]] = []
    for row in rows:
        chapter = int(row.get("chapter", 0) or 0)
        events = row.get("events") or []
        first = events[0].event if events else str(row.get("summary", ""))
        out.append(
            (
                f"ch{chapter}",
                (
                    f"第{chapter}章",
                    str(row.get("count", len(events))),
                    "、".join(row.get("characters") or []) or "—",
                    (first or "")[:60],
                ),
            )
        )
    return out


def track_rows(tracks: dict[str, dict]) -> list[tuple[str, tuple]]:
    """人物轨迹 → Treeview 行。按重要度倒序、同重要度按名字排，`iid` 用 `tr{角色名}`。"""
    out: list[tuple[str, tuple]] = []
    for name in sorted(tracks, key=lambda n: (-int(tracks[n].get("importance", 5) or 5), n)):
        entry = tracks.get(name) or {}
        appearances = [str(c) for c in (entry.get("appearances") or [])]
        preview = "、".join(appearances[:12]) + (" …" if len(appearances) > 12 else "")
        out.append(
            (
                f"tr{name}",
                (name, str(len(appearances)), str(entry.get("last_seen", 0) or 0), preview or "—"),
            )
        )
    return out


def branch_rows(tree: list[dict], branch_dirs: list[dict] | None = None) -> list[tuple[str, tuple]]:
    """世界线 → 分支的两级行，外加**分支子项目**（可双击打开）。

    `iid`：世界线 `wl{文件}`、抉择 `wl{文件}#{章号}`、**分支子项目 `br{目录}`**。
    列语义对两类条目略有不同，因此表头用中性词（`世界线 / 分支` 等）。
    """
    out: list[tuple[str, tuple]] = []
    for world in tree:
        file_key = str(world.get("file") or "")
        wl_iid = f"wl{file_key}"
        branches = world.get("branches") or []
        out.append(
            (
                wl_iid,
                (str(world.get("name") or file_key), f"{len(branches)} 处抉择", "", ""),
            )
        )
        for branch in branches:
            chapter = int(branch.get("chapter", 0) or 0)
            out.append(
                (
                    f"{wl_iid}#{chapter}",
                    (
                        f"　第{chapter}章",
                        str(branch.get("decision") or "")[:40],
                        str(branch.get("chosen") or "")[:24],
                        str(branch.get("alternative") or "")[:24],
                    ),
                )
            )

    for node in branch_dirs or []:
        origin = int(node.get("origin_chapter", 0) or 0)
        size = int(node.get("chapter_count", 0) or 0)
        status = str(node.get("status") or "") or "—"
        out.append(
            (
                f"br{node.get('dir')}",
                (
                    f"↳ 分支 {node.get('title') or ''}",
                    f"第{origin}章分叉" if origin else "分叉点未知",
                    status + ("" if node.get("openable", True) else "（无法打开）"),
                    f"{size} 章" if size else "—",
                ),
            )
        )
    return out


def chronicle_rows(chronicle: list[dict]) -> list[tuple[str, tuple]]:
    """跨代编年史 → 行。`iid` 用 `lg{代}-{章}-{序号}`（同代同章可有多条事件）。"""
    out: list[tuple[str, tuple]] = []
    for index, row in enumerate(chronicle):
        generation = int(row.get("generation", 1) or 1)
        chapter = int(row.get("chapter", 0) or 0)
        out.append(
            (
                f"lg{generation}-{chapter}-{index}",
                (
                    f"第{generation}代",
                    f"第{chapter}章",
                    str(row.get("location") or "—"),
                    str(row.get("event") or "")[:60],
                    "前代史（只读）" if row.get("readonly") else "本代（可编辑）",
                ),
            )
        )
    return out


def stats_text(stats: dict) -> str:
    """把 `TimelineStore.stats()` 变成一行中文摘要（空项不显示，避免噪声）。"""
    parts = [
        f"事件 {stats.get('events', 0)} 条",
        f"覆盖 {stats.get('chapters', 0)} 章",
        f"角色 {stats.get('characters', 0)} 个",
        f"世界线 {stats.get('world_lines', 0)} 条",
        f"分支项目 {stats.get('branch_dirs', 0)} 个",
    ]
    if stats.get("manual"):
        parts.append(f"手工 {stats['manual']} 条")
    if stats.get("low_confidence"):
        parts.append(f"低置信 {stats['low_confidence']} 条")
    if stats.get("first_chapter"):
        parts.append(f"第 {stats['first_chapter']}–{stats['last_chapter']} 章")
    return " / ".join(parts)


# ====================================================================== 面板


class TimelinePanel(BasePanel):
    """四视图时间线面板。"""

    key = "timeline"
    title = "世界线与时间线"
    category = "世界与世代"
    order = 10
    description = "统一 timelines/ 与 memory/timeline/ 两套存储：章节轴 / 世界线分支 / 人物轨迹 / 跨代编年史"
    #: `novel.opened` 由宿主统一处理（它会重建当前面板），这里只关心数据变化
    topics_of_interest = (TOPIC_TIMELINE_CHANGED, TOPIC_CHAPTER_SAVED)

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._tree: dict[str, ttk.Treeview] = {}
        self._rows: dict[str, dict[str, dict]] = {"axis": {}, "lineage": {}}
        #: 复用的 store（读取缓存挂在它身上）与各视图的行集指纹（避免无谓重建）
        self._timeline_store: TimelineStore | None = None
        self._seen_signatures: dict[str, tuple] = {}
        #: 各视图的**完整行集**（搜索过滤在它之上做，随时可还原）
        self._all_rows: dict[str, list[tuple[str, tuple]]] = {}
        self._search_var = tk.StringVar()

        # ── 工具栏：主操作在左、搜索在右（左主右辅，视线有落点）────────────────
        bar = ui_kit.toolbar(parent)
        bar["bar"].pack(fill=tk.X, pady=(0, ui_kit.SPACE["sm"]))
        self._extract_btn = ui_kit.button(bar["left"], "从正文抽取事件", self._on_extract, kind="primary")
        self._extract_btn.pack(side=tk.LEFT)
        self._sync_btn = ui_kit.button(bar["left"], "同步到世界线", self._on_sync, kind="secondary")
        self._sync_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        search = ui_kit.search_entry(
            bar["right"],
            self._search_var,
            placeholder="过滤当前视图（Ctrl+F）…",
            on_change=self._apply_filter,
            width=26,
        )
        search["frame"].pack(side=tk.RIGHT)
        self._toolkit_search_entry = search["entry"]

        # ── KPI 小块：用"数值 + 标签"替代一行长文字，扫一眼就能读到量级 ────────
        self._kpi = ui_kit.kpi_row(
            parent, [("事件", "—"), ("覆盖章节", "—"), ("角色", "—"), ("世界线", "—"), ("分支项目", "—")]
        )
        self._kpi.pack(fill=tk.X, pady=(0, ui_kit.SPACE["xs"]))
        self._stats_label = ui_kit.hint(parent, "")
        self._stats_label.pack(fill=tk.X)

        self._notebook = ttk.Notebook(parent, style="Dark.TNotebook")
        self._notebook.pack(fill=tk.BOTH, expand=True, pady=(ui_kit.SPACE["sm"], 0))

        self._tree["axis"] = self._add_view(
            "章节轴", ("章", "事件数", "涉及角色", "事件摘要"), (90, 70, 190, 420), self._on_axis_double
        )
        self._tree["branches"] = self._add_view(
            "世界线 / 分支",
            ("世界线 / 分支", "抉择 / 分叉点", "所选 / 状态", "未选项 / 章数"),
            (170, 220, 140, 110),
            self._on_branch_double,
        )
        self._tree["tracks"] = self._add_view(
            "人物轨迹", ("角色", "出场章数", "最近章", "出现章节"), (140, 80, 70, 460), self._on_track_double
        )
        self._tree["lineage"] = self._add_view(
            "跨代编年史", ("代", "章", "地点", "事件", "范围"), (70, 70, 100, 430, 110), self._on_lineage_double
        )

        detail_card = ui_kit.card(parent, "详情", pad=ui_kit.SPACE["md"])
        detail_card["frame"].pack(fill=tk.X, pady=(ui_kit.SPACE["sm"], 0))
        self._detail = tk.Label(
            detail_card["body"],
            text="选中一行查看详情；双击可跳转或打开。",
            bg=C["bg_card"],
            fg=C["text_secondary"],
            font=UIStyle.font("label"),
            anchor=tk.NW,
            justify=tk.LEFT,
            wraplength=1180,
        )
        self._detail.pack(fill=tk.X)

        self.mark_built(True)
        self.reload()
        return parent

    def _add_view(self, title, columns, widths, on_double) -> ttk.Treeview:
        """一个视图 = 一个表格页签（统一用 `ui_kit.pretty_tree`：斑马纹 / 可排序 / Enter 触发）。"""
        frame = tk.Frame(self._notebook, bg=UIStyle.COLORS["bg_dark"])
        self._notebook.add(frame, text=title)
        built = ui_kit.pretty_tree(frame, columns, widths, on_double=on_double, height=12)
        built["frame"].pack(fill=tk.BOTH, expand=True)
        return built["tree"]

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        if self.is_built:
            self.reload()

    def on_event(self, topic: str, payload: Any = None) -> None:
        """`timeline.changed` / `chapter.saved` → 重新加载。

        换书（`novel.opened`）由宿主统一重建本面板，这里不重复处理，
        否则同一次切换会被刷新两遍。
        """
        if topic in (TOPIC_TIMELINE_CHANGED, TOPIC_CHAPTER_SAVED) and self.is_built:
            self.reload()

    # ------------------------------------------------------------------ 数据

    def _store(self) -> TimelineStore:
        """本面板自己的 store（**跨刷新复用**，让读取缓存生效）。

        为什么不每次 new 一个：面板在同一部小说上会被反复刷新，而 store 的读取缓存
        以文件指纹为准，复用实例才能把"一次刷新 = 一次读盘"落到实处。
        换书时 `novel_dir` 变了 → 重建实例（缓存自然不跨书串味）。
        """
        novel_dir = getattr(self, "current_novel_dir", None)
        store = self._timeline_store
        if store is None or store.novel_dir != (Path(novel_dir) if novel_dir else None):
            store = TimelineStore(novel_dir, events=getattr(self, "events", None))
            self._timeline_store = store
        return store

    def reload(self) -> None:
        """重新填充四个视图与摘要行。数据为空时给出**可执行的提示**而不是一片空白。

        **一次取数、四视图渲染**：只向 store 要一份 `snapshot()`，
        不再"每个视图各问一次" —— 后者实测会把同一批分页文件重复读 4 遍。
        """
        if not getattr(self, "current_novel_dir", None):
            self._set_stats("尚未打开小说：请先新建或打开一部作品。")
            self._update_kpi(None)
            for tree in self._tree.values():
                self._clear(tree)
            self._rows = {"axis": {}, "lineage": {}}
            self._all_rows.clear()
            self._seen_signatures.clear()
            return

        try:
            snapshot = self._store().snapshot()
        except Exception as e:  # noqa: BLE001 - 面板刷新失败不该让整个 UI 崩
            logger.error(f"[timeline_panel] 刷新失败: {type(e).__name__}: {e}")
            self._set_stats(f"刷新失败：{type(e).__name__}: {e}")
            self.set_status(f"刷新失败：{type(e).__name__}: {e}", kind="error")
            return

        self._rows["axis"] = {f"ch{int(r.get('chapter', 0) or 0)}": r for r in snapshot.axis}
        self._rows["lineage"] = {
            f"lg{int(r.get('generation', 1) or 1)}-{int(r.get('chapter', 0) or 0)}-{i}": r
            for i, r in enumerate(snapshot.chronicle)
        }
        self._fill(self._tree["axis"], chapter_axis_rows(snapshot.axis))
        self._fill(self._tree["branches"], branch_rows(snapshot.branches, snapshot.branch_dirs))
        self._fill(self._tree["tracks"], track_rows(snapshot.tracks))
        self._fill(self._tree["lineage"], chronicle_rows(snapshot.chronicle))
        self._set_stats(stats_text(snapshot.stats))
        self._update_kpi(snapshot.stats)

    def _update_kpi(self, stats: dict | None) -> None:
        """刷新顶部的指标小块（数量级一眼可见，比一行长文字好扫读）。

        数值 Label 由 `ui_kit.kpi_row` 直接给出（`value_labels`），
        不再靠"比对字体"定位 —— 那种写法让 KPI 永远停在占位符。
        """
        stats = stats or {}
        values = [
            f"{stats.get('events', 0)}",
            f"{stats.get('chapters', 0)}",
            f"{stats.get('characters', 0)}",
            f"{stats.get('world_lines', 0)}",
            f"{stats.get('branch_dirs', 0)}",
        ]
        for label, value in zip(getattr(self._kpi, "value_labels", []), values):
            label.configure(text=value)

    def _query(self) -> str:
        var = self.__dict__.get("_search_var")
        return (var.get() if var is not None else "").strip().lower()

    def _apply_filter(self) -> None:
        """搜索框内容变化 → 用**已缓存的完整行集**重算四个视图（不重新读盘）。"""
        for view, tree in self._tree.items():
            rows = self._all_rows.get(view)
            if rows is not None:
                self._fill(tree, rows)

    def _view_key(self, tree: ttk.Treeview) -> str:
        for key, candidate in self._tree.items():
            if candidate is tree:
                return key
        return str(tree)

    @staticmethod
    def _clear(tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _fill(self, tree: ttk.Treeview, rows: list[tuple[str, tuple]]) -> None:
        """填充一个视图；**行集未变就整体跳过**（避免成百上千次 Treeview 插入）。

        这是必要的：1094 章的章节轴有 1094 行，而 `chapter.saved` 每存一次章
        都会触发一次刷新 —— 每次都重建 1094 行会让面板明显掉帧。
        行集里带斑马纹标签（`ui_kit` 的统一表格风格）。
        """
        view = self._view_key(tree)
        self._all_rows[view] = rows
        query = self._query()
        visible = rows if not query else [row for row in rows if any(query in str(cell).lower() for cell in row[1])]

        signature = (query, tuple(visible))
        if self._seen_signatures.get(view) == signature:
            return
        self._seen_signatures[view] = signature
        self._clear(tree)
        if not visible:
            hint_text = f"没有匹配「{query}」的行。" if query else _empty_hint(tree)
            tree.insert("", tk.END, iid="__empty__", values=(hint_text,), tags=("muted",))
            return
        for index, (iid, values) in enumerate(visible):
            parent = iid.split("#", 1)[0] if "#" in iid else ""
            tree.insert(
                parent,
                tk.END,
                iid=iid,
                values=values,
                tags=("odd" if index % 2 else "even",),
                open=True,
            )

    def _set_stats(self, text: str) -> None:
        self._stats_label.configure(text=text)

    def _set_detail(self, text: str) -> None:
        self._detail.configure(text=text)

    # ------------------------------------------------------------------ 动作

    def _on_sync(self) -> None:
        """把事件源镜像到 `timelines/<世界线>.json`（人工条目不会被抹掉）。"""
        result = self._store().sync()
        self._set_detail(f"同步结果：{result.describe()}")
        self._log(f"时间线同步：{result.describe()}")
        self.reload()

    def _on_axis_double(self, _event=None) -> None:
        """双击事件 → 跳到该章并切回正文页。"""
        iid = self._selected_iid("axis")
        row = self._rows.get("axis", {}).get(iid)
        if row is None:
            return
        self._jump_to_chapter(int(row.get("chapter", 0) or 0), row.get("events") or [])

    def _on_lineage_double(self, _event=None) -> None:
        """双击编年史：本代行可跳章；**前代史只读**，只显示信息，不跳转。"""
        iid = self._selected_iid("lineage")
        row = self._rows.get("lineage", {}).get(iid)
        if row is None:
            return
        chapter = int(row.get("chapter", 0) or 0)
        if row.get("readonly"):
            self._set_detail(
                f"前代史（只读）：第{chapter}章 · {row.get('event', '')}\n"
                f"来源目录：{row.get('novel_dir', '')}\n"
                f"该事件属于父代作品，子代不得修改（child_scope=readonly_parent）。"
            )
            return
        self._jump_to_chapter(chapter, [row])

    def _on_branch_double(self, _event=None) -> None:
        """双击「分支子项目」→ **把它当作作品打开**；双击世界线/抉择行只显示详情。

        这是"只写不读的分支目录"真正被接上的地方：分支目录本身就是一份完整数据
        （`meta.json` + `chapters/` + `memory/`），`_load_novel` 的校验它已经满足。
        """
        iid = self._selected_iid("branches")
        if not iid:
            return
        if not iid.startswith("br"):
            self._set_detail(
                "世界线 / 抉择条目：双击它的子项「分支 …」可以把该分支作为作品打开。\n"
                "（抉择本身只是记录，没有独立正文）"
            )
            return

        branch_dir = iid[2:]
        if not Path(branch_dir).is_dir():
            self._set_detail(f"分支目录不存在（可能已被删除）：{branch_dir}")
            return
        if not self.open_novel_dir(branch_dir):
            self._set_detail(f"无法打开该分支：{branch_dir}\n（宿主未提供打开入口，或该目录不是有效作品）")
            return
        self._set_detail(
            f"已作为作品打开分支：{Path(branch_dir).name}\n它是父代作品的另一条世界线（同一代、只读父代）。"
        )
        self._log(f"时间线面板：打开分支作品 {branch_dir}")

    def _on_track_double(self, _event=None) -> None:
        """双击角色 → 打开角色传记面板（面板间联动的落点）。"""
        iid = self._selected_iid("tracks")
        if not iid.startswith("tr"):
            return
        name = iid[2:]
        host = getattr(self, "panel_host", None)
        if host is None:
            self._set_detail(f"角色：{name}（未找到面板宿主，无法跳转）")
            return
        if not host.select("biography"):
            self._set_detail(f"角色：{name}（传记面板不可用）")
            return
        panel = host.panel("biography")
        if panel is not None and hasattr(panel, "focus_character"):
            panel.focus_character(name)

    def _jump_to_chapter(self, chapter: int, events: list[Any]) -> None:
        """跳到指定章节：复用 `chapter_ui._load_chapter_by_number`（既有入口）。"""
        detail = "\n".join(
            f"· {getattr(e, 'event', '')}"
            + (
                f"（{e.location}／{e.story_time}）"
                if getattr(e, "location", "") or getattr(e, "story_time", "")
                else ""
            )
            for e in events
        )
        loader = getattr(self, "_load_chapter_by_number", None)
        if not callable(loader):
            self._set_detail(f"第{chapter}章（当前宿主未提供章节跳转入口）\n{detail}")
            return
        try:
            loader(int(chapter))
            self._select_notebook_tab("章内容")
            self._set_detail(f"已跳到第{chapter}章\n{detail}")
            self._log(f"已从时间线跳到第{chapter}章")
        except Exception as e:  # noqa: BLE001 - 跳转失败只提示，不动数据
            logger.error(f"[timeline_panel] 跳章失败: {type(e).__name__}: {e}")
            self._set_detail(f"跳到第{chapter}章失败：{type(e).__name__}: {e}\n{detail}")

    def _select_notebook_tab(self, title: str) -> None:
        """按标题切 notebook 页（沿用 `editor_ui` 的写法，不硬编码索引）。"""
        notebook = getattr(self, "notebook", None)
        if notebook is None:
            return
        try:
            for index in range(notebook.index("end")):
                if str(notebook.tab(index, "text")).strip() == title:
                    notebook.select(index)
                    return
        except tk.TclError as e:  # pragma: no cover - 仅真实 UI 下可能
            logger.debug(f"[timeline_panel] 切换标签页失败: {e}")

    def _selected_iid(self, view: str) -> str:
        tree = self._tree.get(view)
        if tree is None:
            return ""
        selection = tree.selection()
        return selection[0] if selection else ""

    # ------------------------------------------------------------------ 从正文抽取

    def _on_extract(self) -> None:
        """从**当前章**正文抽取事件（后台线程调 AI，回主线程写盘）。"""
        novel_dir = getattr(self, "current_novel_dir", None)
        if not novel_dir:
            self._set_detail("尚未打开小说，无法抽取。")
            return
        chapter = int(getattr(self, "current_chapter", 0) or 0)
        if chapter <= 0:
            self._set_detail("请先在正文页选中一章，再回到本面板抽取。")
            return

        chapter_file = novel_dir / "chapters" / f"chapter_{chapter:04d}.txt"
        if not chapter_file.exists():
            self._set_detail(f"第{chapter}章尚无正文（缺 {chapter_file.name}）。")
            return
        try:
            text = chapter_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            self._set_detail(f"读取第{chapter}章失败：{e}")
            return

        characters = self._known_characters()
        prompt = extraction_prompt(chapter, text, known_characters=characters)
        self._extract_btn.configure(state=tk.DISABLED)
        self._set_detail(f"正在从第{chapter}章抽取事件…（正文 {len(text)} 字）")

        def work() -> None:
            try:
                ai = getattr(self, "ai_client", None)
                if ai is None or not callable(getattr(ai, "chat", None)):
                    raise RuntimeError("AI 客户端不可用")
                raw = ai.chat([{"role": "user", "content": prompt}])
                if isinstance(raw, dict):
                    raw = raw.get("content", "")
                events = parse_extraction_result(str(raw), chapter, characters)
            except Exception as e:  # noqa: BLE001 - 线程里必须兜住一切
                # ⚠️ 必须**立刻**把消息取出来：`except ... as e` 在块结束时删除 `e`，
                # 而 lambda 是稍后经 `root.after` 执行的，届时 `e` 已不存在（NameError）。
                message = f"{type(e).__name__}: {e}"
                logger.error(f"[timeline_panel] 抽取事件失败: {message}")
                self._ui(lambda: self._finish_extract(0, chapter, message))
                return
            self._ui(lambda: self._record_extracted(events, chapter))

        threading.Thread(target=work, daemon=True).start()

    def _ui(self, callback) -> None:
        """把回调送回主线程（Tk 非线程安全）。宿主无 root 时同步执行。"""
        root = getattr(self, "root", None)
        if root is not None and hasattr(root, "after"):
            root.after(0, callback)
        else:  # pragma: no cover - 仅无 Tk 的单测路径
            callback()

    def _record_extracted(self, events: list[dict], chapter: int) -> None:
        """写进事件源。**复用宿主已有的 `MemoryManager`**，不另建一份。"""
        if not events:
            self._finish_extract(0, chapter, "模型未返回可用事件")
            return
        try:
            memory = getattr(self, "memory", None)
            if memory is None:
                from app.memory_manager import MemoryManager

                memory = MemoryManager(getattr(self, "current_novel_dir"))
                memory.set_event_sink(getattr(self, "events", None))
            for event in events:
                memory.add_event(
                    int(event["chapter"]),
                    str(event["event"]),
                    event_type=str(event.get("type", "story") or "story"),
                    characters_involved=list(event.get("characters") or []),
                    location=str(event.get("location", "") or ""),
                    story_time=str(event.get("story_time", "") or ""),
                    arc=str(event.get("arc", "") or ""),
                    source=str(event.get("source", "auto") or "auto"),
                    confidence=str(event.get("confidence", "low") or "low"),
                )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[timeline_panel] 写入抽取结果失败: {type(e).__name__}: {e}")
            self._finish_extract(0, chapter, f"写入失败：{type(e).__name__}: {e}")
            return
        # 本面板刚通过 MemoryManager 写了事件源：显式失效，不依赖指纹察觉"等长重写"
        self._store().invalidate()
        self._finish_extract(len(events), chapter, "")

    def _finish_extract(self, count: int, chapter: int, error: str) -> None:
        self._extract_btn.configure(state=tk.NORMAL)
        if error:
            self._set_detail(f"第{chapter}章抽取失败：{error}")
        else:
            self._set_detail(f"第{chapter}章已抽取 {count} 条事件（已写入时间线；低置信项建议人工确认）。")
        self._log(f"时间线抽取：第{chapter}章 → {count} 条{('，' + error) if error else ''}")
        self.reload()

    def _known_characters(self) -> list[str]:
        """已知角色名，作为抽取提示词的白名单，避免模型自造名字污染角色库。"""
        novel_dir = getattr(self, "current_novel_dir", None)
        if not novel_dir:
            return []
        try:
            from app.storage import read_json_with_backup

            data, status = read_json_with_backup(novel_dir / "memory" / "characters.json", default=None)
            if status == "corrupt" or not isinstance(data, dict):
                return []
            return [str(name) for name in data]
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[timeline_panel] 读取角色白名单失败（忽略）: {e}")
            return []


# ====================================================================== 辅助


def _empty_hint(tree: ttk.Treeview) -> str:
    """空视图的提示语：让用户知道"为什么空、下一步做什么"，而不是盯着空白。"""
    columns = tuple(tree["columns"])
    if "涉及角色" in columns:
        return "暂无事件：生成章节时会自动记录；也可点右上「从正文抽取事件」。"
    if "抉择" in columns:
        return "暂无世界线数据：成章后选择分支会自动记录；可先点「同步到世界线」镜像事件源。"
    if "出场章数" in columns:
        return "暂无人物轨迹：character_activity.json 为空，且事件里也未记录角色。"
    return "暂无跨代数据：本作没有 meta.lineage（即第 1 代）；用「世代传承」面板创建续集后可见。"
