"""世代传承面板（v3 §2.4 ③ —— "小说续写第二代"）。

## 补的是什么

`lifecycle_ui._create_sequel` 建第二部时只复制 `memory/settings.json` 与 `characters/`：
不继承 `outline.json`、`timelines/`、`memory/`（摘要/弧线/卷）与伏笔线索，
`original_novel` 写进 `meta.json` 后也不参与任何逻辑。于是"续写第二代"实际只是
"新建一本带同样角色的书"。

本面板做三件事：

1. **看得见** —— 代际树：第 1 代 → 第 2 代 → …，点一行可切到那一代；
2. **说清楚** —— 勾选继承范围（角色 / 世界观 / 大纲 / 时间线 / 记忆 / 伏笔），
   点「补齐继承」**按计划补齐**，并如实报告"父代缺哪些"；
3. **守住线** —— 子代对父代只读：界面上标注范围，执行时每一步都过
   `lineage.guard_child_path`（`child_scope=readonly_parent`）。

## 为什么不做"一键创建续集"

创建流程（选风格、填构想、建目录树）已经在 `_create_sequel` 里成熟且被用户熟悉；
本面板改为"对**已存在**的子代补齐继承"，避免两套创建逻辑分叉
（分叉的典型后果是"从菜单建的和从面板建的结果不一样"）。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Mapping

from loguru import logger

from app import lineage as lin
from app.storage import read_json_with_backup
from app.ui_style import UIStyle

from .base import BasePanel

__all__ = ["LineagePanel", "inheritance_rows", "lineage_rows", "novel_candidates"]

#: 维度 → 中文标签（面板展示，与 `lin.DIMENSION_SOURCES` 的键一一对应）
DIMENSION_LABELS: dict[str, str] = {
    "characters": "角色（含年龄推进）",
    "settings": "世界观设定",
    "outline": "大纲",
    "timeline": "时间线（作为前代史，只读）",
    "memory": "记忆（全局摘要 / 弧线 / 卷 / 章摘要）",
    "plots": "未回收伏笔清单",
}


# ====================================================================== 纯函数（可单测）


def novel_candidates(novels_dir: Any, exclude_dir: Any = None) -> list[dict]:
    """列出可作为"父代"的小说（有 `meta.json` 的目录）。

    `exclude_dir` 用来排掉**自己**（不能把自己设为自己的父代 —— 那会造出环），
    以及**自己的后代**（把子代设成父代同样会成环）。

    ⚠️ 方向很容易写反：`is_within(root, target)` 的含义是「target 在 root 之内」。
    要"排除后代"必须写 `is_within(exclude, entry)`（entry 在 exclude 之内），
    而**不是** `is_within(entry, exclude)`（那排除的是祖先 —— 而祖先恰恰是
    最合法的父代候选）。
    """
    root = Path(novels_dir) if novels_dir else None
    if root is None or not root.exists():
        return []
    exclude = Path(exclude_dir).resolve() if exclude_dir else None
    out: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            continue
        if exclude is not None:
            if entry.resolve() == exclude:
                continue
            if lin.is_within(exclude, entry):  # entry 是 exclude 的后代 → 不能当父代
                continue
        meta, status = read_json_with_backup(meta_path, default=None)
        if status == "corrupt" or not isinstance(meta, Mapping):
            continue
        record = lin.LineageRecord.from_meta(meta)
        out.append(
            {
                "dir": str(entry),
                "title": str(meta.get("title") or entry.name),
                "generation": record.generation if record else 1,
                "has_lineage": record is not None,
            }
        )
    return out


def lineage_rows(tree: list[dict]) -> list[tuple[str, tuple]]:
    """代际树 → Treeview 行。`iid` 用 `g{序号}`（目录名含空格，不适合进 iid）。"""
    out: list[tuple[str, tuple]] = []
    for index, node in enumerate(tree):
        scope = "当前作品" if node.get("is_current") else ("前代史（只读）" if node.get("readonly") else "—")
        state = "目录丢失" if node.get("missing") else "正常"
        out.append(
            (
                f"g{index}",
                (
                    f"第{int(node.get('generation', 1) or 1)}代",
                    str(node.get("title") or ""),
                    scope,
                    str(node.get("novel_dir") or ""),
                    state,
                ),
            )
        )
    return out


def inheritance_rows(inherited: Mapping[str, bool], plan: lin.InheritancePlan | None) -> list[tuple[str, tuple]]:
    """继承范围 → 行：勾选状态 + 父代是否有可继承内容 + 明细。"""
    out: list[tuple[str, tuple]] = []
    for dim in lin.INHERIT_DIMENSIONS:
        checked = "☑" if (inherited or {}).get(dim) else "☐"
        if plan is None:
            detail = "（尚未选择父代）"
        else:
            entry = (plan.items or {}).get(dim) or {}
            if entry.get("skipped"):
                detail = "已取消继承"
            elif entry.get("copy"):
                detail = "将复制：" + "、".join(entry["copy"])
            else:
                detail = "父代缺失：" + "、".join(entry.get("missing") or []) or "无可复制项"
        out.append(
            (
                f"dim{dim}",
                (checked, DIMENSION_LABELS.get(dim, dim), detail),
            )
        )
    return out


def lineage_summary(record: lin.LineageRecord | None, plan: lin.InheritancePlan | None = None) -> str:
    """一行摘要：本作是第几代、父代是谁、护栏范围、继承计划。"""
    if record is None:
        return "本作是第 1 代（meta.json 无 lineage）。可在下方选择父代，把它登记为续作。"
    parts = [f"本作是第 {record.generation} 代"]
    if record.parent_novel:
        parts.append(f"父代：{record.parent_title or record.parent_novel}")
    if record.era_gap_years:
        parts.append(f"时间跳跃 {record.era_gap_years} 年")
    parts.append(f"范围：{record.child_scope}（子代只读父代）")
    text = " / ".join(parts)
    if plan is not None:
        text += f"　｜　{plan.describe()}"
    return text


# ====================================================================== 面板


class LineagePanel(BasePanel):
    """代际树 + 继承范围 + 只读护栏。"""

    key = "lineage"
    title = "世代传承"
    category = "世界与世代"
    order = 30
    description = "meta.lineage 代际树；可勾选继承角色/世界观/大纲/时间线/记忆/伏笔；子代只读父代"
    #: 本面板只展示"当前作品"的代际信息，换书后宿主会重建它，故无需订阅任何主题
    topics_of_interest = ()

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._tree_rows: list[dict] = []
        self._inherited_vars: dict[str, tk.BooleanVar] = {}

        self._summary_label = tk.Label(
            parent,
            text="",
            font=("微软雅黑", 9),
            bg=C["bg_dark"],
            fg=C["text_secondary"],
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=760,
        )
        self._summary_label.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            parent,
            text="代际链（双击切到该代）",
            font=("微软雅黑", 9, "bold"),
            bg=C["bg_dark"],
            fg=C["text_primary"],
            anchor=tk.W,
        ).pack(fill=tk.X)
        tree_frame = tk.Frame(parent, bg=C["bg_dark"])
        tree_frame.pack(fill=tk.BOTH, expand=False)
        self._tree = ttk.Treeview(tree_frame, columns=("代", "作品", "范围", "目录", "状态"), show="headings", height=5)
        for col, width in (("代", 60), ("作品", 180), ("范围", 110), ("目录", 330), ("状态", 70)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=width, anchor=tk.W, stretch=False)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_switch_generation)

        # ---- 继承设置
        settings = tk.LabelFrame(parent, text="继承设置", font=("微软雅黑", 9), bg=C["bg_dark"], fg=C["text_primary"])
        settings.pack(fill=tk.X, pady=(6, 2))

        picker = tk.Frame(settings, bg=C["bg_dark"])
        picker.pack(fill=tk.X, pady=2)
        tk.Label(picker, text="父代作品", font=("微软雅黑", 9), bg=C["bg_dark"], fg=C["text_secondary"]).pack(
            side=tk.LEFT
        )
        self._parent_var = tk.StringVar(value="")
        self._parent_box = ttk.Combobox(picker, textvariable=self._parent_var, state="readonly", width=36)
        self._parent_box.pack(side=tk.LEFT, padx=4)
        self._parent_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_plan())
        tk.Label(picker, text="时间跳跃（年）", font=("微软雅黑", 9), bg=C["bg_dark"], fg=C["text_secondary"]).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        self._gap_var = tk.StringVar(value="0")
        tk.Spinbox(picker, from_=0, to=500, increment=1, width=6, textvariable=self._gap_var).pack(side=tk.LEFT, padx=4)

        checks = tk.Frame(settings, bg=C["bg_dark"])
        checks.pack(fill=tk.X, pady=2)
        for dim in lin.INHERIT_DIMENSIONS:
            var = tk.BooleanVar(value=True)
            self._inherited_vars[dim] = var
            tk.Checkbutton(
                checks,
                text=DIMENSION_LABELS.get(dim, dim),
                variable=var,
                bg=C["bg_dark"],
                fg=C["text_secondary"],
                selectcolor=C["bg_medium"],
                font=("微软雅黑", 8),
                command=self._refresh_plan,
            ).pack(side=tk.LEFT, padx=(0, 8))

        self._plan_tree = ttk.Treeview(parent, columns=("选", "维度", "明细"), show="headings", height=6)
        for col, width in (("选", 40), ("维度", 200), ("明细", 520)):
            self._plan_tree.heading(col, text=col)
            self._plan_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self._plan_tree.pack(fill=tk.BOTH, expand=True, pady=(4, 2))

        bar = tk.Frame(parent, bg=C["bg_dark"])
        bar.pack(fill=tk.X)
        for text, command in (
            ("登记为续作（写 meta.lineage）", self._on_register_lineage),
            ("按勾选补齐继承", self._on_apply_inheritance),
            ("刷新", self.reload),
        ):
            tk.Button(
                bar, text=text, font=("微软雅黑", 9), bg=C["bg_medium"], fg=C["text_primary"], command=command
            ).pack(side=tk.LEFT, padx=2)

        self._detail = tk.Text(
            parent, height=6, wrap=tk.WORD, font=("微软雅黑", 9), bg=C["bg_medium"], fg=C["text_primary"]
        )
        self._detail.pack(fill=tk.X, pady=(4, 0))
        self._detail.configure(state=tk.DISABLED)

        self.mark_built(True)
        self.reload()
        return parent

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        if self.is_built:
            self.reload()

    # ------------------------------------------------------------------ 数据

    def _novel_dir(self) -> Path | None:
        return getattr(self, "current_novel_dir", None)

    def _novels_dir(self) -> Any:
        config = getattr(self, "config", None)
        return getattr(config, "novels_dir", None)

    def reload(self) -> None:
        """刷新代际树、父代候选与计划预览。"""
        novel_dir = self._novel_dir()
        if not novel_dir:
            self._summary_label.configure(text="尚未打开小说。")
            self._tree_rows = []
            self._fill_tree(self._tree, [])
            self._fill_tree(self._plan_tree, [])
            return

        record = lin.read_lineage(novel_dir)
        self._tree_rows = lin.generation_tree(novel_dir)

        candidates = novel_candidates(self._novels_dir(), exclude_dir=novel_dir)
        labels = [f"第{c['generation']}代 · {c['title']}" for c in candidates]
        self._parent_box.configure(values=labels)
        self._candidates = candidates
        current_parent = record.parent_novel if record else ""
        for index, candidate in enumerate(candidates):
            if candidate["dir"] == current_parent:
                self._parent_var.set(labels[index])
                break
        else:
            self._parent_var.set("")

        if record:
            for dim, var in self._inherited_vars.items():
                var.set(bool(record.inherited.get(dim, True)))
            self._gap_var.set(str(record.era_gap_years))

        plan = self._plan()
        self._fill_tree(self._tree, lineage_rows(self._tree_rows))
        self._fill_tree(self._plan_tree, inheritance_rows(self._current_inherited(), plan))
        self._summary_label.configure(text=lineage_summary(record, plan))

    @staticmethod
    def _fill_tree(tree: ttk.Treeview, rows: list[tuple[str, tuple]]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for iid, values in rows:
            tree.insert("", tk.END, iid=iid, values=values)

    def _selected_parent_dir(self) -> str:
        index = self._parent_box.current()
        if index < 0:
            return ""
        candidates = getattr(self, "_candidates", [])
        if index >= len(candidates):
            return ""
        return str(candidates[index]["dir"])

    def _current_inherited(self) -> dict[str, bool]:
        return {dim: bool(var.get()) for dim, var in self._inherited_vars.items()}

    def _plan(self) -> lin.InheritancePlan | None:
        parent = self._selected_parent_dir()
        if not parent:
            return None
        return lin.plan_inheritance(parent, self._current_inherited())

    def _refresh_plan(self) -> None:
        plan = self._plan()
        self._fill_tree(self._plan_tree, inheritance_rows(self._current_inherited(), plan))
        self._summary_label.configure(text=lineage_summary(lin.read_lineage(self._novel_dir()), plan))

    # ------------------------------------------------------------------ 动作

    def _on_register_lineage(self) -> None:
        """把当前作品登记为所选父代的续作（写 `meta.lineage`）。"""
        novel_dir = self._novel_dir()
        parent = self._selected_parent_dir()
        if not novel_dir or not parent:
            self._set_detail("请先选择父代作品。")
            return
        if str(Path(novel_dir).resolve()) == str(Path(parent).resolve()):
            self._set_detail("父代不能是自己。")
            return
        self._guard_parent(novel_dir, parent)
        try:
            gap = int(self._gap_var.get())
        except (TypeError, ValueError):
            gap = 0
        record = lin.build_lineage_record(parent, era_gap_years=gap, inherited=self._current_inherited())
        try:
            self._write_lineage(novel_dir, record)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[lineage_panel] 写入 lineage 失败: {type(e).__name__}: {e}")
            self._set_detail(f"写入失败：{type(e).__name__}: {e}")
            return
        self._set_detail(
            f"已登记为第 {record.generation} 代（父代：{record.parent_title or parent}）。\n"
            f"护栏：child_scope={record.child_scope} —— 子代只读父代。\n"
            f"下一步可点「按勾选补齐继承」把大纲/时间线/记忆/伏笔补上。"
        )
        self._log(f"世代传承：{Path(novel_dir).name} → 第 {record.generation} 代")
        self.reload()

    def _write_lineage(self, novel_dir: Path, record: lin.LineageRecord) -> None:
        """写 `meta.json`。优先走 `NovelStore.update_meta`（原子写 + 统一入口）。"""
        store_factory = None
        try:
            from app.novel_store import NovelStore

            store_factory = NovelStore
        except ImportError:  # pragma: no cover - novel_store 一定存在
            store_factory = None
        if store_factory is not None:
            store = store_factory(novel_dir, events=getattr(self, "events", None))
            store.update_meta({lin.LINEAGE_KEY: record.as_dict()})
            return
        from app.storage import atomic_write_json

        meta, _status = read_json_with_backup(novel_dir / "meta.json", default={})
        meta = dict(meta) if isinstance(meta, Mapping) else {}
        meta[lin.LINEAGE_KEY] = record.as_dict()
        atomic_write_json(novel_dir / "meta.json", meta)

    def _guard_parent(self, child_dir: Path, parent_dir: str) -> None:
        """护栏自检：确认"子代目录"与"父代目录"不是同一处、也不是父子包含。

        真正的强制点在 `lin.guard_child_path`（每次写入都过）；这里提前拦一次，
        是为了在用户点按钮时就给出明确提示，而不是等写盘时抛错。
        """
        if lin.is_within(parent_dir, child_dir) or lin.is_within(child_dir, parent_dir):
            logger.warning(f"[lineage_panel] 父子目录存在包含关系: {child_dir} vs {parent_dir}")

    def _on_apply_inheritance(self) -> None:
        """按勾选把父代数据补进当前作品（每一次写入都过护栏）。"""
        novel_dir = self._novel_dir()
        if not novel_dir:
            self._set_detail("尚未打开小说。")
            return

        # 只读一次 lineage：此前写成 `... if lin.read_lineage(x) else ""` 会调用两次，
        # 且 mypy 正确地指出第二次返回 None 时会被解引用（union-attr）。
        record = lin.read_lineage(novel_dir)
        parent = self._selected_parent_dir() or (record.parent_novel if record else "")
        if not parent:
            self._set_detail("请先选择父代（或先「登记为续作」）。")
            return
        if not Path(parent).exists():
            self._set_detail(f"父代目录不存在：{parent}")
            return

        inherited = self._current_inherited()
        try:
            gap = int(self._gap_var.get())
        except (TypeError, ValueError):
            gap = 0

        result = lin.inherit_into_child(novel_dir, parent, inherited)
        notes: list[str] = []
        # ⚠️ 必须把**同一个** parent 传下去：先前 `_apply_character_transform` 自己再取一遍
        # 下拉框，于是"继承用已登记的父代、年龄换算用下拉框"两条路径可能指向不同作品。
        char_note = self._apply_character_transform(novel_dir, parent, gap, notes)
        self._set_detail(
            "继承完成。\n"
            f"- 父代：{parent}\n"
            f"- 已复制 {len(result['copied'])} 项：{'、'.join(result['copied']) or '无'}\n"
            f"- 父代缺失 {len(result['missing'])} 项：{'、'.join(result['missing']) or '无'}\n"
            f"- 伏笔清单：{result['plots_file'] or '未生成'}\n"
            f"- 角色：{char_note}\n" + ("\n".join(f"  · {n}" for n in notes[:12]) if notes else "")
        )
        self._log(f"世代传承：补齐继承 {len(result['copied'])} 项，角色{char_note}")
        self.reload()

    def _apply_character_transform(self, novel_dir: Path, parent: str, gap: int, notes: list[str]) -> str:
        """年龄推进 + 死亡转状态。**必须走 `mutate_characters`**（锁 + 三道闸门）。"""
        memory = getattr(self, "memory", None)
        if memory is None or not callable(getattr(memory, "mutate_characters", None)):
            return "跳过（宿主未提供角色管理器）"
        last_chapter = lin.parent_last_chapter(parent)
        transform = lin.make_character_transform(gap, last_chapter, notes)
        try:
            before = len(memory.get_characters() or {})
            after_chars = memory.mutate_characters(transform)
        except Exception as e:  # noqa: BLE001 - 闸门拒绝是正常业务结果，要如实显示
            logger.error(f"[lineage_panel] 角色代际换算失败: {type(e).__name__}: {e}")
            return f"失败（{type(e).__name__}: {e}）"
        after = len(after_chars or {})
        if before != after:
            # 角色数变化是硬约束的红线，必须显式暴露而不是悄悄放过
            logger.warning(f"[lineage_panel] 角色数发生变化: {before} → {after}")
            return f"⚠ 角色数发生变化（{before} → {after}），请检查"
        return f"已推进（{after} 个角色，角色数未变）"

    def _on_switch_generation(self, _event=None) -> None:
        """双击某代 → 切换当前作品。父代行也可切（切过去就是打开父代作品）。"""
        selection = self._tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0].lstrip("g"))
        except ValueError:
            return
        rows = self._tree_rows
        if index >= len(rows):
            return
        node = rows[index]
        if node.get("is_current"):
            self._set_detail("已经是当前作品。")
            return
        if node.get("missing"):
            self._set_detail(f"该代目录不存在（可能被移动或删除）：{node.get('novel_dir')}")
            return
        loader = getattr(self, "_load_novel", None)
        if not callable(loader):
            self._set_detail(f"当前宿主未提供打开作品入口：{node.get('novel_dir')}")
            return
        try:
            loader(Path(node["novel_dir"]))
            self._set_detail(f"已切换到第 {node.get('generation')} 代：{node.get('title')}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[lineage_panel] 切换世代失败: {type(e).__name__}: {e}")
            self._set_detail(f"切换失败：{type(e).__name__}: {e}")

    # ------------------------------------------------------------------ 辅助

    def _set_detail(self, text: str) -> None:
        self._detail.configure(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.configure(state=tk.DISABLED)
