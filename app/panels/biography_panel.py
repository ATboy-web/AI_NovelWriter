"""角色传记面板（v3 §2.4 ②）。

## 现状与三处提升

`character_ui._generate_character_biography` 已经能生成传记，但：

1. **输入太薄** —— 提示词只有 `char_info` + `outline[:5]`，**完全没用已写出的章节正文**。
   同一批材料每次生成的传记都差不多，且与人物实际经历脱节。
2. **无结构** —— 只落一个 txt，回写角色档案时还把传记**截断到 500 字**，
   于是"档案里的传记"和"文件里的传记"是两份长度不同的东西。
3. **与手工故事线脱节** —— `character_stories/<名>.json` 是作者手写的弧线，
   与 AI 传记互不可见。

本面板对应地：接入 `memory.retrieve_relevant()`（倒排索引 RAG）+ 时间线事件 +
出场章列表作为材料；新增 `biographies/<名>.json` 作为**结构化源**（txt 保留用于导出）；
并列展示 AI 传记与手工故事线，并支持把 AI 分段一键转成 story_arcs。

## 🚨 硬护栏：本面板**没有**删除角色的入口

角色名是小说内容资产（线上 286 个），项目约定「已有角色名不可删除」。
因此这里只提供 查看 / 编辑 / 生成 / 导出，**不提供任何删除路径**；
`tests/test_p4b_panels.py` 用源码扫描把这条钉死。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Mapping

from loguru import logger

from app.events import TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED
from app.storage import atomic_write_json, atomic_write_text, read_json_with_backup, safe_filename
from app.timeline_store import TimelineStore
from app.ui_style import UIStyle

from .base import BasePanel

__all__ = [
    "BiographyPanel",
    "build_biography_prompt",
    "character_rows",
    "filter_characters",
    "load_biography_json",
    "material_summary",
    "read_story_arcs",
    "split_sections",
    "story_arcs_from_sections",
    "structured_biography",
]

#: 传记落盘目录（与既有 `_generate_character_biography` 一致）
# ====================================================================== 纯逻辑（单一来源）
# 实现已搬到 `app/biography.py`（纯函数、无 Tk、可被 character_ui 共用）。
# 这里**再导出**一份，保持既有导入路径不变（测试与面板内部都用这些名字）。
from app.biography import (  # noqa: E402 - 需在常量区之后集中声明，便于对照
    BIOGRAPHIES_DIR,
    MAX_BIO_TOKENS,
    PROFILE_BIOGRAPHY_LIMIT,
    STORIES_DIR,
    build_biography_prompt,
    character_rows,
    filter_characters,
    load_biography_json,
    material_summary,
    read_story_arcs,
    split_sections,
    story_arcs_from_sections,
    structured_biography,
)

# ====================================================================== 面板


class BiographyPanel(BasePanel):
    """角色传记面板：左树 + 右编辑区 + 素材侧栏。"""

    key = "biography"
    title = "角色传记"
    category = "世界与世代"
    order = 20
    description = "286 个角色可搜索筛选；传记可编辑；生成接入 RAG + 时间线事件；结构化落盘 biographies/<名>.json"
    topics_of_interest = (TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED)

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._all_characters: dict[str, dict] = {}
        self._current_name = ""
        #: 复用的时间线 store（`_materials` 每次选角都要用，缓存挂在实例上）
        self._timeline_store: TimelineStore | None = None

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 左列：搜索 + 筛选 + 角色树
        left = tk.Frame(body, bg=C["bg_dark"], width=320)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        self._keyword_var = tk.StringVar()
        entry = tk.Entry(left, textvariable=self._keyword_var, font=("微软雅黑", 9))
        entry.pack(fill=tk.X, pady=(2, 2))
        entry.bind("<KeyRelease>", lambda _e: self._refresh_character_list())

        filters = tk.Frame(left, bg=C["bg_dark"])
        filters.pack(fill=tk.X, pady=(0, 2))
        self._category_var = tk.StringVar(value="全部分类")
        self._category_box = ttk.Combobox(
            filters,
            textvariable=self._category_var,
            state="readonly",
            width=12,
            values=["全部分类"],
        )
        self._category_box.pack(side=tk.LEFT, padx=(0, 2))
        self._category_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_character_list())
        self._faction_var = tk.StringVar(value="全部阵营")
        self._faction_box = ttk.Combobox(
            filters,
            textvariable=self._faction_var,
            state="readonly",
            width=12,
            values=["全部阵营"],
        )
        self._faction_box.pack(side=tk.LEFT)
        self._faction_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_character_list())

        self._only_bio_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            left,
            text="仅看已有传记",
            variable=self._only_bio_var,
            bg=C["bg_dark"],
            fg=C["text_secondary"],
            selectcolor=C["bg_medium"],
            font=("微软雅黑", 8),
            command=self._refresh_character_list,
        ).pack(anchor=tk.W)

        self._tree = ttk.Treeview(left, columns=("角色", "分类", "阵营", "重要", "传记"), show="headings", height=16)
        for col, width in (("角色", 110), ("分类", 60), ("阵营", 70), ("重要", 40), ("传记", 40)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=width, anchor=tk.W, stretch=False)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())

        # ---- 右区：传记正文 + 素材
        right = tk.Frame(body, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._title_label = tk.Label(
            right,
            text="请选择左侧角色",
            font=("微软雅黑", 11, "bold"),
            bg=C["bg_dark"],
            fg=C["text_primary"],
            anchor=tk.W,
        )
        self._title_label.pack(fill=tk.X)

        self._material_label = tk.Label(
            right,
            text="",
            font=("微软雅黑", 8),
            bg=C["bg_dark"],
            fg=C["text_muted"],
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=700,
        )
        self._material_label.pack(fill=tk.X, pady=(0, 2))

        bar = tk.Frame(right, bg=C["bg_dark"])
        bar.pack(fill=tk.X)
        self._words_var = tk.StringVar(value="1500")
        tk.Label(bar, text="目标字数", font=("微软雅黑", 9), bg=C["bg_dark"], fg=C["text_secondary"]).pack(side=tk.LEFT)
        tk.Spinbox(bar, from_=300, to=5000, increment=100, width=7, textvariable=self._words_var).pack(
            side=tk.LEFT, padx=(2, 8)
        )
        for text, command in (
            ("AI 生成传记", self._on_generate),
            ("保存", self._on_save),
            ("导出 TXT", self._on_export),
            ("转为手工故事线", self._on_push_to_story_arcs),
        ):
            tk.Button(
                bar, text=text, font=("微软雅黑", 9), bg=C["bg_medium"], fg=C["text_primary"], command=command
            ).pack(side=tk.LEFT, padx=2)

        text_frame = tk.Frame(right, bg=C["bg_dark"])
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self._text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("微软雅黑", 10),
            undo=True,
            bg=C["bg_medium"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
        )
        scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.mark_built(True)
        self._reload_characters()
        return parent

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        if self.is_built:
            self._reload_characters()

    def on_event(self, topic: str, payload: Any = None) -> None:
        """角色档案或时间线变化 → 重新加载（保留当前选中的角色）。"""
        if topic in (TOPIC_CHARACTER_CHANGED, TOPIC_TIMELINE_CHANGED) and self.is_built:
            self._reload_characters()

    # ------------------------------------------------------------------ 数据

    def _novel_dir(self):
        return getattr(self, "current_novel_dir", None)

    def _characters(self) -> dict[str, dict]:
        """角色字典。优先用宿主已有的 memory（带锁与闸门），否则只读文件。"""
        memory = getattr(self, "memory", None)
        if memory is not None and callable(getattr(memory, "get_characters", None)):
            try:
                data = memory.get_characters()
                if isinstance(data, dict):
                    return {str(k): (v if isinstance(v, dict) else {}) for k, v in data.items()}
            except Exception as e:  # noqa: BLE001
                logger.error(f"[biography_panel] 读取角色失败: {type(e).__name__}: {e}")
                return {}
        novel_dir = self._novel_dir()
        if not novel_dir:
            return {}
        data, status = read_json_with_backup(novel_dir / "memory" / "characters.json", default=None)
        if status == "corrupt" or not isinstance(data, dict):
            return {}
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in data.items()}

    def _reload_characters(self) -> None:
        """重新载入角色并刷新筛选下拉（保留当前选中项）。"""
        if not self._novel_dir():
            self._title_label.configure(text="尚未打开小说")
            self._material_label.configure(text="")
            self._all_characters = {}
            self._fill_tree({})
            return

        self._all_characters = self._characters()
        categories = sorted({str(i.get("category", "")) for i in self._all_characters.values() if i.get("category")})
        factions = sorted({str(i.get("faction", "")) for i in self._all_characters.values() if i.get("faction")})
        self._category_box.configure(values=["全部分类"] + categories)
        self._faction_box.configure(values=["全部阵营"] + factions)
        if self._category_var.get() not in ("全部分类", *categories):
            self._category_var.set("全部分类")
        if self._faction_var.get() not in ("全部阵营", *factions):
            self._faction_var.set("全部阵营")
        self._refresh_character_list()

    def _refresh_character_list(self) -> None:
        category = "" if self._category_var.get() == "全部分类" else self._category_var.get()
        faction = "" if self._faction_var.get() == "全部阵营" else self._faction_var.get()
        selected = filter_characters(
            self._all_characters,
            keyword=self._keyword_var.get(),
            category=category,
            faction=faction,
            only_with_biography=self._only_bio_var.get(),
        )
        self._fill_tree(selected)

    def _fill_tree(self, characters: Mapping[str, Any]) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        rows = character_rows(characters)
        if not rows:
            self._tree.insert("", tk.END, iid="__empty__", values=("无匹配角色", "", "", "", ""))
            return
        for iid, values in rows:
            self._tree.insert("", tk.END, iid=iid, values=values)
        if self._current_name and f"ch{self._current_name}" in self._tree.get_children():
            self._tree.selection_set(f"ch{self._current_name}")

    # ------------------------------------------------------------------ 选中 → 编辑区

    def focus_character(self, name: str) -> None:
        """外部联动入口（时间线面板双击角色时调用）。"""
        if not self.is_built:
            return
        self._current_name = str(name)
        iid = f"ch{name}"
        if iid in self._tree.get_children():
            self._tree.selection_set(iid)
            self._tree.see(iid)
        self._load_character(name)

    def _load_selected(self) -> None:
        selection = self._tree.selection()
        if not selection or selection[0].startswith("__"):
            return
        iid = selection[0]
        if not iid.startswith("ch"):
            return
        self._current_name = iid[2:]
        self._load_character(self._current_name)

    def _load_character(self, name: str) -> None:
        info = self._all_characters.get(name) or {}
        self._title_label.configure(
            text=f"{name}　（{info.get('category', '') or '未分类'}／{info.get('faction', '') or '无阵营'}）"
        )
        chapters, events = self._materials(name)
        arcs = (read_story_arcs(self._novel_dir(), name).get("story_arcs") or []) if self._novel_dir() else []
        self._material_label.configure(text=material_summary(chapters, events, (), arcs))

        text = self._read_biography_text(name)
        self._text.delete("1.0", tk.END)
        if text:
            self._text.insert("1.0", text)
        elif info.get("biography"):
            self._text.insert("1.0", str(info.get("biography")))
        else:
            self._text.insert("1.0", "（该角色尚无传记；可点「AI 生成传记」）")

    def _materials(self, name: str) -> tuple[list[int], list[Any]]:
        """该角色的素材：出场章 + 相关事件。全部来自既有数据，不发起 AI 调用。

        **必须复用同一个 store**：`character_tracks()` 与 `read_memory_events()` 都要
        遍历整个事件源，而本方法每选中一个角色就会被调一次 ——
        实测不复用时"浏览 300 个角色"= 6900 次磁盘读取。
        """
        store = self._timeline()
        if store is None:
            return [], []
        entry = store.character_tracks().get(name) or {}
        chapters = [int(c) for c in (entry.get("appearances") or [])]
        events = [e for e in store.read_memory_events() if name in e.characters]
        return sorted(set(chapters)), events

    def _timeline(self) -> TimelineStore | None:
        """本面板复用的 `TimelineStore`（读取缓存挂在实例上，换书即重建）。"""
        novel_dir = self._novel_dir()
        if not novel_dir:
            return None
        store = self._timeline_store
        if store is None or store.novel_dir != Path(novel_dir):
            store = TimelineStore(novel_dir, events=getattr(self, "events", None))
            self._timeline_store = store
        return store

    def _biography_paths(self, name: str) -> tuple[Any, Any]:
        novel_dir = self._novel_dir()
        if not novel_dir:
            return None, None
        base = novel_dir / BIOGRAPHIES_DIR
        safe = safe_filename(name)
        return base / f"{safe}_传记.txt", base / f"{safe}.json"

    def _read_biography_text(self, name: str) -> str:
        """优先读**结构化源** json（它是权威），没有才回退 txt。"""
        data = load_biography_json(self._novel_dir(), name)
        if data:
            sections = data.get("sections") or []
            if sections:
                return "\n\n".join(f"## {s.get('title', '')}\n{s.get('content', '')}".strip() for s in sections)
        txt_path, _json_path = self._biography_paths(name)
        if txt_path is not None and txt_path.exists():
            try:
                return txt_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"[biography_panel] 读取传记失败: {e}")
        return ""

    # ------------------------------------------------------------------ 动作

    def _on_save(self) -> None:
        """保存传记：txt（导出用）+ json（结构化源）+ 角色档案字段（走 mutate）。"""
        name = self._current_name
        if not name:
            self._set_material("请先选择角色。")
            return
        text = self._text.get("1.0", tk.END).strip()
        if not text:
            self._set_material("传记内容为空，未保存。")
            return
        try:
            files_ok, profile_ok = self._persist(name, text, {"chapters": self._materials(name)[0]})
        except Exception as e:  # noqa: BLE001 - 保存失败要显示原因
            logger.error(f"[biography_panel] 保存传记失败: {type(e).__name__}: {e}")
            self._set_material(f"保存失败：{type(e).__name__}: {e}")
            return
        if not files_ok:
            self._set_material("尚未打开小说，无法保存。")
        elif profile_ok:
            self._set_material("已保存（txt + json，并回写角色档案）。")
        else:
            self._set_material("已保存 txt + json，但**未回写角色档案**（宿主未提供角色管理器）。")
        self._log(f"传记已保存：{name}")

    def _persist(self, name: str, text: str, sources: Mapping[str, Any]) -> tuple[bool, bool]:
        """落盘三件事：txt、json、角色档案字段。**角色档案只走 `mutate_characters`。**

        Returns:
            `(文件是否落盘, 角色档案是否回写)`。分成两个布尔是为了**如实报告** ——
            没有宿主 memory 时文件仍然写成功，但档案没更新，此时不能告诉用户"已回写"。
        """
        novel_dir = self._novel_dir()
        if not novel_dir:
            return (False, False)
        txt_path, json_path = self._biography_paths(name)
        if txt_path is None or json_path is None:
            return (False, False)
        sections = split_sections(text)
        payload = structured_biography(
            name,
            sections,
            sources={"chapters": list(sources.get("chapters") or []), "timeline_events": [], "anchors": []},
        )
        json_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(txt_path, text)
        atomic_write_json(json_path, payload)

        snippet = text[:PROFILE_BIOGRAPHY_LIMIT] + ("..." if len(text) > PROFILE_BIOGRAPHY_LIMIT else "")
        memory = getattr(self, "memory", None)
        if memory is None or not callable(getattr(memory, "mutate_characters", None)):
            return (True, False)

        def _mutate(chars: Mapping[str, Any]) -> dict:
            out = {str(k): (v if isinstance(v, dict) else {}) for k, v in (chars or {}).items()}
            if name in out:
                out[name] = {**out[name], "biography": snippet, "biography_file": str(txt_path)}
            return out

        memory.mutate_characters(_mutate)
        return (True, True)

    def _on_export(self) -> None:
        """把当前编辑区内容写回 txt（"导出"= 确保文件与界面一致）。"""
        name = self._current_name
        if not name:
            self._set_material("请先选择角色。")
            return
        txt_path, _json_path = self._biography_paths(name)
        if txt_path is None:
            self._set_material("尚未打开小说，无法导出。")
            return
        try:
            atomic_write_text(txt_path, self._text.get("1.0", tk.END).strip())
        except OSError as e:
            self._set_material(f"导出失败：{e}")
            return
        self._set_material(f"已导出：{txt_path.name}")

    def _on_push_to_story_arcs(self) -> None:
        """把传记分段**追加**到手工故事线（不覆盖作者已有内容）。"""
        name = self._current_name
        novel_dir = self._novel_dir()
        if not name or not novel_dir:
            self._set_material("请先选择角色。")
            return
        sections = split_sections(self._text.get("1.0", tk.END).strip())
        new_arcs = story_arcs_from_sections(sections)
        if not new_arcs:
            self._set_material("没有可转换的分段。")
            return
        current = read_story_arcs(novel_dir, name)
        existing = [a for a in (current.get("story_arcs") or []) if isinstance(a, Mapping)]
        merged = existing + [a for a in new_arcs if a["title"] not in {str(e.get("title", "")) for e in existing}]
        path = novel_dir / STORIES_DIR / f"{safe_filename(name)}.json"
        try:
            atomic_write_json(path, {**current, "name": name, "story_arcs": merged})
        except OSError as e:
            self._set_material(f"转换失败：{e}")
            return
        self._set_material(f"已追加 {len(merged) - len(existing)} 段到手工故事线（共 {len(merged)} 段）。")
        self._log(f"传记分段转故事线：{name} +{len(merged) - len(existing)}")

    def _on_generate(self) -> None:
        """后台线程生成传记：材料取自 RAG + 时间线，回主线程落盘。"""
        name = self._current_name
        if not name:
            self._set_material("请先选择角色。")
            return
        info = self._all_characters.get(name) or {}
        chapters, events = self._materials(name)
        arcs = read_story_arcs(self._novel_dir(), name).get("story_arcs") or []
        anchors = self._retrieve(name)
        try:
            word_count = int(self._words_var.get())
        except (TypeError, ValueError):
            word_count = 1500
        prompt = build_biography_prompt(name, info, word_count, anchors, events, arcs)
        self._set_material(f"正在生成「{name}」的传记…（{material_summary(chapters, events, anchors, arcs)}）")

        def work() -> None:
            try:
                ai = getattr(self, "ai_client", None)
                if ai is None or not callable(getattr(ai, "chat", None)):
                    raise RuntimeError("AI 客户端不可用")
                result = ai.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=min(max(word_count * 2, 1024), MAX_BIO_TOKENS),
                )
                if isinstance(result, dict):
                    result = result.get("content", "")
                text = str(result).strip()
                if not text:
                    raise RuntimeError("模型返回空内容")
            except Exception as e:  # noqa: BLE001 - 线程里必须兜住一切
                # ⚠️ 必须**立刻**取出消息：`except ... as e` 在块结束时删除 `e`，
                # 而 lambda 是稍后经 `root.after` 执行的，届时 `e` 已不存在（NameError）。
                message = f"{type(e).__name__}: {e}"
                logger.error(f"[biography_panel] 生成传记失败: {message}")
                self._ui(lambda: self._set_material(f"生成失败：{message}"))
                return
            self._ui(lambda: self._finish_generate(name, text, chapters, anchors))

        threading.Thread(target=work, daemon=True).start()

    def _retrieve(self, name: str) -> list[dict]:
        """RAG 检索（既有 `retrieve_relevant`，倒排索引 + 相关度排序）。"""
        memory = getattr(self, "memory", None)
        if memory is None or not callable(getattr(memory, "retrieve_relevant", None)):
            return []
        try:
            result = memory.retrieve_relevant(name, top_k=5)
            return [r for r in (result or []) if isinstance(r, dict)]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[biography_panel] 记忆检索失败（继续无锚点生成）: {e}")
            return []

    def _finish_generate(self, name: str, text: str, chapters: list[int], anchors: list[dict]) -> None:
        """回到主线程：把结果填进编辑区并落盘，然后广播 `biography.generated`。"""
        if self._current_name == name:
            self._text.delete("1.0", tk.END)
            self._text.insert("1.0", text)
        try:
            files_ok, profile_ok = self._persist(name, text, {"chapters": chapters, "anchors": anchors})
        except Exception as e:  # noqa: BLE001
            logger.error(f"[biography_panel] 落盘失败: {type(e).__name__}: {e}")
            self._set_material(f"生成成功但落盘失败：{type(e).__name__}: {e}")
            return
        if not files_ok:
            self._set_material("已生成，但尚未打开小说，无法保存。")
        elif profile_ok:
            self._set_material("已生成并保存（txt + json + 角色档案）。")
        else:
            self._set_material("已生成并保存 txt + json，但**未回写角色档案**（宿主未提供角色管理器）。")
        self._log(f"传记已生成：{name}（{len(text)} 字）")
        self._publish_generated(name, text, chapters)

    def _publish_generated(self, name: str, text: str, chapters: list[int]) -> None:
        """广播 `biography.generated`（旁路：失败不影响落盘）。"""
        events = getattr(self, "events", None)
        if events is None:
            return
        try:
            from app.events import TOPIC_BIOGRAPHY_GENERATED

            events.publish(
                TOPIC_BIOGRAPHY_GENERATED,
                {
                    "novel_dir": str(self._novel_dir() or ""),
                    "character": name,
                    "words": len(text),
                    "chapters": list(chapters),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[biography_panel] 广播 biography.generated 失败（忽略）: {e}")

    # ------------------------------------------------------------------ 辅助

    def _ui(self, callback) -> None:
        root = getattr(self, "root", None)
        if root is not None and hasattr(root, "after"):
            root.after(0, callback)
        else:  # pragma: no cover - 仅无 Tk 的单测路径
            callback()

    def _set_material(self, text: str) -> None:
        self._material_label.configure(text=text)
