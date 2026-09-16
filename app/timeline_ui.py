"""时间线/分支层：时间线可视化、分支故事与分支小说创作

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from app import UIStyle
from app.lineage import branch_lineage_record


class TimelineMixin:
    """时间线/分支层：时间线可视化、分支故事与分支小说创作"""

    def _open_timeline(self):
        """世界线/时间线管理"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("世界线 / 时间线")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(1000, sw - 60), int(sh * 0.78)
        x, y = (sw - w) // 2, (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog, text="🌐 世界线 / 时间线管理", font=UIStyle.font("title"), bg=C["bg_dark"], fg=C["accent_text"]
        ).pack(pady=10)

        # 加载已有世界线
        timeline_dir = self.current_novel_dir / "timelines"
        timeline_dir.mkdir(exist_ok=True)
        main_file = timeline_dir / "main.json"

        if not main_file.exists():
            main_timeline = {"name": "主线", "events": [], "chapters": [], "branches": []}
            main_file.write_text(json.dumps(main_timeline, indent=2, ensure_ascii=False), encoding="utf-8")

        # 读取世界线列表
        timelines = []
        for f in sorted(timeline_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["_file"] = f.name
                timelines.append(data)
            except Exception:
                pass

        # 顶部工具栏
        toolbar = tk.Frame(dialog, bg=C["bg_dark"])
        toolbar.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(toolbar, text="选择世界线:", font=UIStyle.font("body"), bg=C["bg_dark"], fg=C["text_primary"]).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        tl_var = tk.StringVar(value="主线")
        tl_names = [t.get("name", "未命名") for t in timelines]
        tl_combo = ttk.Combobox(
            toolbar, textvariable=tl_var, values=tl_names, state="readonly", width=20, font=UIStyle.font("body")
        )
        tl_combo.pack(side=tk.LEFT, padx=(0, 15))

        # 统计信息
        stats_label = tk.Label(toolbar, text="", font=UIStyle.font("label"), bg=C["bg_dark"], fg=C["text_muted"])
        stats_label.pack(side=tk.LEFT, padx=10)

        # 内容区域 - 主面板
        main_paned = tk.PanedWindow(dialog, orient=tk.HORIZONTAL, bg=C["bg_dark"])
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # === 左侧面板 - 决策点列表 ===
        left_frame = tk.Frame(main_paned, bg=C["bg_card"])
        main_paned.add(left_frame, width=w // 3)

        tk.Label(
            left_frame, text="📋 决策点列表", font=UIStyle.font("body_bold"), bg=C["bg_card"], fg=C["accent_text"]
        ).pack(anchor=tk.W, padx=10, pady=(8, 2))

        # 决策点列表使用Canvas+滚动
        left_canvas = tk.Canvas(left_frame, bg=C["bg_card"], highlightthickness=0)
        left_scrollbar = tk.Scrollbar(left_frame, orient=tk.VERTICAL, command=left_canvas.yview)
        left_inner = tk.Frame(left_canvas, bg=C["bg_card"])
        left_inner.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=left_inner, anchor=tk.NW, width=w // 3 - 20)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # === 右侧面板 ===
        right_frame = tk.Frame(main_paned, bg=C["bg_card"])
        main_paned.add(right_frame, width=2 * w // 3)

        # 右侧使用Notebook多标签页
        right_notebook = ttk.Notebook(right_frame)
        right_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 标签1: 详情
        detail_frame = tk.Frame(right_notebook, bg=C["bg_card"])
        right_notebook.add(detail_frame, text="📖 详情")

        tk.Label(detail_frame, text="决策详情", font=UIStyle.font("body_bold"), bg=C["bg_card"], fg=C["warning"]).pack(
            anchor=tk.W, padx=10, pady=5
        )

        detail_text = tk.Text(
            detail_frame,
            wrap=tk.WORD,
            font=UIStyle.font("body"),
            bg=C["bg_medium"],
            fg=C["text_primary"],
            height=12,
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        detail_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # 标签2: 影响分析
        impact_frame = tk.Frame(right_notebook, bg=C["bg_card"])
        right_notebook.add(impact_frame, text="🔍 影响分析")

        tk.Label(
            impact_frame, text="决策影响分析", font=UIStyle.font("body_bold"), bg=C["bg_card"], fg=C["warning"]
        ).pack(anchor=tk.W, padx=10, pady=5)

        impact_text = tk.Text(
            impact_frame,
            wrap=tk.WORD,
            font=UIStyle.font("body"),
            bg=C["bg_medium"],
            fg=C["text_primary"],
            height=12,
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        impact_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # 标签3: 时间线图
        graph_frame = tk.Frame(right_notebook, bg=C["bg_card"])
        right_notebook.add(graph_frame, text="📊 时间线")

        timeline_canvas = tk.Canvas(graph_frame, bg=C["bg_medium"], highlightthickness=0)
        timeline_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # 存储数据
        all_branches = []
        selected_idx = [-1]

        def update_timeline_graph():
            """在Canvas上绘制时间线图"""
            timeline_canvas.delete("all")
            if not all_branches:
                return

            cw = timeline_canvas.winfo_width()
            ch = timeline_canvas.winfo_height()
            if cw < 50 or ch < 50:
                return

            # 虚线主线
            timeline_canvas.create_line(60, 0, 60, ch, fill=C["accent"], width=2, dash=(4, 4))

            # 绘制节点
            step = max(60, (ch - 40) // max(len(all_branches), 1))
            for i, br in enumerate(all_branches):
                y = 30 + i * step
                # 节点圆
                timeline_canvas.create_oval(52, y - 4, 68, y + 12, fill=C["accent"], outline="")
                # 章节标签
                ch_num = br.get("chapter", "?")
                timeline_canvas.create_text(
                    30, y + 4, text=f"第{ch_num}章", fill=C["text_muted"], font=UIStyle.font("micro")
                )
                # 决策摘要
                desc = br.get("decision", "")[:25]
                timeline_canvas.create_text(
                    140, y + 4, text=desc, anchor=tk.W, fill=C["text_primary"], font=UIStyle.font("caption")
                )
                # 分支线
                timeline_canvas.create_line(60, y + 4, 90, y + 4 - 15, fill=C["warning"], width=1)
                timeline_canvas.create_line(60, y + 4, 90, y + 4 + 20, fill=C["success"], width=1)

        def show_branch_detail(idx):
            """显示决策点详情"""
            if idx < 0 or idx >= len(all_branches):
                return
            selected_idx[0] = idx
            br = all_branches[idx]

            detail_text.delete("1.0", tk.END)

            # 标题
            detail_text.insert(tk.END, f"📍 第{br.get('chapter', '?')}章 决策点\n\n", "title")
            detail_text.insert(tk.END, f"📝 决策情境:\n{br.get('decision', '未知')}\n\n", "section")
            detail_text.insert(tk.END, f"✅ 选择方案:\n{br.get('chosen', '未知')}\n\n", "chosen")
            detail_text.insert(tk.END, f"❓ 另一可能:\n{br.get('alternative', '未知')}\n\n", "alternative")

            story = br.get("story", "")
            if story:
                detail_text.insert(tk.END, f"━━━━━━━━━━━━━━━━━━\n📖 分支故事:\n{story}\n", "story")
            else:
                detail_text.insert(tk.END, "(点击下方「生成此分支」查看更多what-if故事)", "hint")

            # 格式化文本
            detail_text.tag_config("title", font=UIStyle.font("title"), foreground=C["accent"])
            detail_text.tag_config("section", font=UIStyle.font("body"), foreground=C["text_primary"])
            detail_text.tag_config("chosen", font=UIStyle.font("body"), foreground=C["success"])
            detail_text.tag_config("alternative", font=UIStyle.font("body"), foreground=C["warning"])
            detail_text.tag_config("story", font=UIStyle.font("body"), foreground=C["text_primary"])
            detail_text.tag_config("hint", font=UIStyle.font("label"), foreground=C["text_muted"])

            # 影响分析
            impact_text.delete("1.0", tk.END)
            impact_text.insert(tk.END, "🔍 决策影响分析\n\n", "title")
            impact_text.insert(tk.END, "👉 直接影响:\n", "section")
            chosen = br.get("chosen", "")
            alternative = br.get("alternative", "")
            if chosen:
                impact_text.insert(tk.END, f"  • 选择了「{chosen[:60]}」\n")
                impact_text.insert(tk.END, "  • 这导致后续故事朝此方向发展\n")
            impact_text.insert(tk.END, f"\n🔄 如果选择「{alternative[:40]}」:\n", "alt")
            impact_text.insert(tk.END, "  • 故事将走向完全不同的方向\n")
            impact_text.insert(tk.END, f"  • 可能影响后续{n_impact(all_branches, idx)}个相关情节\n")
            impact_text.insert(tk.END, "\n📊 量化分析:\n", "section")
            impact_text.insert(tk.END, f"  • 是否关键决策: {'是' if br.get('story') else '待评估'}\n")
            impact_text.insert(tk.END, f"  • 影响范围: {estimate_scope(br)}\n")
            impact_text.insert(tk.END, f"  • 可逆性: {estimate_reversibility(br)}\n")

            impact_text.tag_config("title", font=UIStyle.font("title"), foreground=C["accent"])
            impact_text.tag_config("section", font=UIStyle.font("body_bold"), foreground=C["text_primary"])
            impact_text.tag_config("alt", font=UIStyle.font("body_bold"), foreground=C["warning"])

            update_timeline_graph()

        def n_impact(branches, idx):
            return len(branches) - idx - 1

        def estimate_scope(br):
            desc = br.get("decision", "")
            if any(w in desc for w in ["生死", "背叛", "选择", "关键", "命运", "决战"]):
                return "全局性影响"
            elif any(w in desc for w in ["获得", "失去", "结交", "学习"]):
                return "中期影响"
            return "局部影响"

        def estimate_reversibility(br):
            desc = br.get("decision", "")
            if any(w in desc for w in ["死亡", "杀死", "毁灭", "封印"]):
                return "不可逆"
            return "可逆转"

        def refresh_timeline(name=None):
            name = name or tl_var.get()
            all_branches.clear()

            # 清除左侧列表
            for w in left_inner.winfo_children():
                w.destroy()

            target = next((t for t in timelines if t.get("name") == name), None)
            if not target:
                return

            chapters_count = len(target.get("chapters", []))
            branches = target.get("branches", [])

            stats_label.config(text=f"📊 {len(branches)}个决策点 | {chapters_count}个章节")

            if branches:
                for i, br in enumerate(branches):
                    all_branches.append(br)
                    ch = br.get("chapter", "?")
                    desc = br.get("decision", "")[:50]
                    chosen = br.get("chosen", "")[:25]
                    has_story = "📖" if br.get("story") else "  "

                    # 创建可点击的卡片
                    card = tk.Frame(
                        left_inner, bg=C["bg_medium"] if i % 2 == 0 else C["bg_card"], cursor="hand2", padx=8, pady=5
                    )
                    card.pack(fill=tk.X, padx=3, pady=1)

                    # 章节标签
                    chapter_lbl = tk.Label(
                        card,
                        text=f"第{ch}章",
                        font=UIStyle.font("caption_bold"),
                        bg=C["accent"],
                        fg="white",
                        padx=4,
                        pady=1,
                    )
                    chapter_lbl.pack(side=tk.LEFT, padx=(0, 6))

                    # 决策描述
                    desc_lbl = tk.Label(
                        card,
                        text=f"{has_story} {desc}",
                        font=UIStyle.font("label"),
                        bg=card["bg"],
                        fg=C["text_primary"],
                        anchor=tk.W,
                        justify=tk.LEFT,
                    )
                    desc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    # 选择标签
                    chosen_lbl = tk.Label(
                        card,
                        text=f"✅{chosen}",
                        font=UIStyle.font("caption"),
                        bg=card["bg"],
                        fg=C["success_text"],
                        padx=4,
                    )
                    chosen_lbl.pack(side=tk.RIGHT)

                    # 点击事件
                    card.bind("<Button-1>", lambda e, idx=i: show_branch_detail(idx))
                    chapter_lbl.bind("<Button-1>", lambda e, idx=i: show_branch_detail(idx))
                    desc_lbl.bind("<Button-1>", lambda e, idx=i: show_branch_detail(idx))
                    chosen_lbl.bind("<Button-1>", lambda e, idx=i: show_branch_detail(idx))

                    # 悬停效果
                    def on_enter(e, c=card):
                        c.configure(bg=C["bg_light"])

                    def on_leave(e, c=card, i=i):
                        c.configure(bg=C["bg_medium"] if i % 2 == 0 else C["bg_card"])

                    for w in [card, chapter_lbl, desc_lbl, chosen_lbl]:
                        w.bind("<Enter>", on_enter)
                        w.bind("<Leave>", on_leave)
            else:
                tk.Label(
                    left_inner,
                    text="暂未检测到决策点\n\n每章创作完成后会自动记录。",
                    font=UIStyle.font("label"),
                    bg=C["bg_card"],
                    fg=C["text_muted"],
                ).pack(pady=20)

            detail_text.delete("1.0", tk.END)
            detail_text.insert(tk.END, "👈 点击左侧决策点查看详情", "hint")
            detail_text.tag_config("hint", font=UIStyle.font("subtitle"), foreground=C["text_muted"], justify=tk.CENTER)

            impact_text.delete("1.0", tk.END)
            impact_text.insert(tk.END, "👈 点击左侧决策点查看影响分析", "hint")
            impact_text.tag_config("hint", font=UIStyle.font("subtitle"), foreground=C["text_muted"], justify=tk.CENTER)

            update_timeline_graph()

        refresh_timeline("主线")

        # 按钮区域
        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def on_select(event=None):
            refresh_timeline()

        tl_combo.bind("<<ComboboxSelected>>", on_select)

        # 左侧操作按钮
        tk.Button(
            btn_frame,
            text="🔄 刷新",
            font=UIStyle.font("label"),
            padx=10,
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            command=refresh_timeline,
        ).pack(side=tk.LEFT, padx=3)

        # 右侧操作按钮
        tk.Button(
            btn_frame,
            text="✏️ 编辑决策点",
            font=UIStyle.font("label"),
            padx=10,
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            command=lambda: self._edit_decision(
                dialog, all_branches, selected_idx, timelines, tl_var.get(), main_file, refresh_timeline
            ),
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            btn_frame,
            text="📖 生成此分支",
            font=UIStyle.font("body"),
            padx=12,
            bg=C["warning"],
            fg="white",
            relief=tk.FLAT,
            command=lambda: self._generate_branch_story(
                dialog, timeline_dir, timelines, all_branches, detail_text, refresh_timeline
            ),
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            btn_frame,
            text="🚀 开始分支创作",
            font=UIStyle.font("body"),
            padx=12,
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            command=lambda: self._start_branch_novel(dialog, timeline_dir, timelines, all_branches, refresh_timeline),
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            btn_frame,
            text="关闭",
            font=UIStyle.font("body"),
            padx=20,
            bg=C["bg_light"],
            fg=C["text_primary"],
            command=dialog.destroy,
        ).pack(side=tk.RIGHT, padx=5)

    def _generate_branch_story(self, dialog, timeline_dir, timelines, all_branches, detail_text, refresh_callback):
        """为当前选中的决策点生成分支故事"""
        if not all_branches:
            messagebox.showwarning("提示", "请先在左侧点击选择一个决策点")
            return

        # 从dialog的变量中获取selected_idx
        idx = -1
        for name in dir(dialog):
            if "selected_idx" in name:
                continue
        # 遍历子widget找到selected_idx引用
        # 使用更简单的方法：从refresh_callback的闭包中获取
        idx = -1
        try:
            # 从detail_text的内容判断是否选中
            content = detail_text.get("1.0", "1.0+5c")
            if not content or "点击左侧" in content:
                messagebox.showwarning("提示", "请先在左侧点击选择一个决策点")
                return
        except Exception:
            pass

        # 重新查找选中的决策点
        for i, br in enumerate(all_branches):
            decision = br.get("decision", "")
            detail_content = detail_text.get("1.0", tk.END)
            if decision[:20] in detail_content:
                idx = i
                break

        if idx < 0 or idx >= len(all_branches):
            messagebox.showwarning("提示", "请先在左侧点击选择一个决策点")
            return
        br = all_branches[idx]

        chapter_num = br["chapter"]
        chapter_file = self.current_novel_dir / "chapters" / f"chapter_{chapter_num:04d}.txt"

        def run():
            try:
                content = chapter_file.read_text(encoding="utf-8")[:2000] if chapter_file.exists() else ""
                system = "你是平行世界故事创作者。基于决策分支创作 what-if 故事。直接叙述故事，500-1000字。"
                prompt = f"当时情况: {br['decision']}\n原选择: {br['chosen']}\n另一种选择: {br['alternative']}\n原文: {content[:500]}\n\n请创作如果主角选择了「{br['alternative']}」会发生什么。"

                response = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1000)
                if not response:
                    return

                # 更新决策点的 story 字段
                br["story"] = response

                # 保存到 main.json
                main_file = timeline_dir / "main.json"
                main_data = json.loads(main_file.read_text(encoding="utf-8"))
                for mb in main_data["branches"]:
                    if mb["chapter"] == br["chapter"] and mb["decision"] == br["decision"]:
                        mb["story"] = response
                        break
                main_file.write_text(json.dumps(main_data, indent=2, ensure_ascii=False), encoding="utf-8")

                self._log("[世界线] 分支故事已生成")
                self.root.after(0, lambda: refresh_callback())
            except Exception as e:
                self.root.after(0, lambda _exc=e: messagebox.showerror("失败", str(_exc)))

        threading.Thread(target=run, daemon=True).start()

    def _start_branch_novel(self, dialog, timeline_dir, timelines, all_branches, refresh_callback):
        """基于决策点创建独立分支世界线，可连续创作"""
        if not all_branches:
            messagebox.showwarning("提示", "没有决策点")
            return

        # 先让用户选择决策点
        ask = tk.Toplevel(dialog)
        ask.title("开始分支世界线创作")
        ask.geometry("550x450")
        ask.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            ask, text="选择决策点创建分支世界线:", font=UIStyle.font("body_bold"), bg=C["bg_dark"], fg=C["accent_text"]
        ).pack(pady=10)

        lb = tk.Listbox(ask, bg=C["bg_card"], fg=C["text_primary"], font=UIStyle.font("label"))
        lb.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        for i, b in enumerate(all_branches):
            has_story = "📖" if b.get("story") else "  "
            lb.insert(tk.END, f"{has_story} 第{b['chapter']}章: {b.get('alternative', '')[:40]}")

        tk.Label(ask, text="生成长度:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).pack(
            anchor=tk.W, padx=20, pady=(10, 0)
        )
        count_frame = tk.Frame(ask, bg=C["bg_dark"])
        count_frame.pack(fill=tk.X, padx=20)
        chapter_count = tk.StringVar(value="10")
        tk.Spinbox(
            count_frame,
            from_=1,
            to=500,
            textvariable=chapter_count,
            width=6,
            font=UIStyle.font("label"),
            bg=C["bg_card"],
        ).pack(side=tk.LEFT)
        tk.Label(
            count_frame,
            text="章（从该决策点继续）",
            bg=C["bg_dark"],
            fg=C["text_secondary"],
            font=UIStyle.font("label"),
        ).pack(side=tk.LEFT, padx=5)

        def start():
            idx = lb.curselection()
            if not idx:
                return
            br = all_branches[idx[0]]
            n_chapters = int(chapter_count.get())
            ask.destroy()

            self._create_branch_novel(br, n_chapters)

        tk.Button(
            ask,
            text="开始分支世界线创作",
            font=UIStyle.font("body"),
            padx=15,
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            command=start,
        ).pack(pady=10)

    def _create_branch_novel(self, decision_point: dict, n_chapters: int):
        """创建分支世界线独立创作项目"""
        br = decision_point
        origin_ch = br["chapter"]

        # 创建分支目录
        branch_id = len(list((self.current_novel_dir / "timelines").glob("branch_*")))
        branch_dir = self.current_novel_dir / "timelines" / f"branch_{branch_id:03d}"
        branch_dir.mkdir(parents=True, exist_ok=True)
        (branch_dir / "chapters").mkdir(exist_ok=True)
        (branch_dir / "summaries").mkdir(exist_ok=True)

        # 元数据
        # ⚠️ 必须带 `title` 与 `lineage`（2026-09-16）：
        # - `title`：`_load_novel` 与各面板都按它显示；此前这里只写 `name`，
        #   于是分支被打开后标题是空的；
        # - `lineage`：有了它，分支才能进代际树（`app/lineage.py` 的发现逻辑按它归类），
        #   并且**同一代**（不是下一代）+ `child_scope=readonly_parent`（分支也不能改父代）。
        branch_title = f"分支: {br['alternative'][:30]}"
        branch_meta = {
            "title": branch_title,
            "name": branch_title,
            "origin_chapter": origin_ch,
            "original_decision": br["decision"],
            "original_choice": br["chosen"],
            "branch_choice": br["alternative"],
            "chapter_count": n_chapters,
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "lineage": branch_lineage_record(
                self.current_novel_dir, f"{branch_id:03d}", origin_ch, branch_title
            ).as_dict(),
        }
        (branch_dir / "meta.json").write_text(json.dumps(branch_meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # 复制原章节内容作为起点上下文
        origin_file = self.current_novel_dir / "chapters" / f"chapter_{origin_ch:04d}.txt"
        context_text = origin_file.read_text(encoding="utf-8")[:2000] if origin_file.exists() else ""

        # 复制角色系统到分支
        src_chars_dir = self.current_novel_dir / "characters"
        b_chars_dir = branch_dir / "characters"
        if src_chars_dir.exists():
            import shutil

            shutil.copytree(src_chars_dir, b_chars_dir, dirs_exist_ok=True)

        # 复制世界观
        src_memory = self.current_novel_dir / "memory"
        b_memory = branch_dir / "memory"
        b_memory.mkdir(exist_ok=True)
        for fname in ["settings.json", "global_summary.txt"]:
            sf = src_memory / fname
            if sf.exists():
                shutil.copy2(sf, b_memory / fname)

        # 生成分支大纲
        def run():
            nonlocal context_text  # context_text 在外层初始化，此处需跨章更新滑窗
            try:
                self._log(f"[分支创作] 为「{br['alternative'][:20]}」生成{n_chapters}章大纲...")

                system = """你是有创意的故事策划师。基于决策分支重新规划故事走向。
输出JSON格式: {"outline": [{"title": "章节标题", "summary": "内容概要(50字)"}, ...]}
章节数等于指定数量，从决策点开始新故事线。"""

                prompt = f"""原文决策点: {br["decision"]}
原选择: {br["chosen"]}
新选择: {br["alternative"]}
原文上下文: {context_text[:1000]}
请规划{n_chapters}章的独立故事线。"""

                response = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1500)
                if not response:
                    return

                # 多策略JSON解析
                outline_data = None

                # Strategy 1: 括号深度追踪
                start = response.find("{")
                if start >= 0:
                    depth = 0
                    end_idx = -1
                    for i in range(start, len(response)):
                        if response[i] == "{":
                            depth += 1
                        elif response[i] == "}":
                            depth -= 1
                            if depth == 0:
                                end_idx = i + 1
                                break
                    if end_idx > start:
                        json_str = response[start:end_idx]
                        json_str = re.sub(r",\s*}", "}", json_str)
                        json_str = re.sub(r",\s*]", "]", json_str)
                        try:
                            outline_data = json.loads(json_str)
                        except json.JSONDecodeError:
                            pass

                # Strategy 2: 清理markdown后重试
                if not outline_data:
                    cleaned = response.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    match = re.search(r"\{[\s\S]*\}", cleaned.strip())
                    if match:
                        try:
                            outline_data = json.loads(match.group())
                        except json.JSONDecodeError:
                            pass

                if not outline_data:
                    self._log("[分支创作] 大纲JSON解析失败")
                    return

                outline = outline_data.get("outline", [])
                if not outline:
                    self._log("[分支创作] 大纲为空")
                    return

                (branch_dir / "outline.json").write_text(
                    json.dumps(outline, indent=2, ensure_ascii=False), encoding="utf-8"
                )

                self._log(f"[分支创作] 大纲生成完成: {len(outline)}章")

                # 初始化分支的CharacterSystem
                from app.character_system import CharacterSystem

                branch_chars = CharacterSystem(branch_dir)
                branch_chars.load()

                # 初始化分支MemoryManager
                from app.memory_manager import MemoryManager

                branch_mem = MemoryManager(branch_dir)

                meta = self._get_meta()
                genre = meta.get("genre", "玄幻")
                word_count = meta.get("word_count_per_chapter", 5000)

                for i, ch in enumerate(outline):
                    ch_num = origin_ch + i
                    title = ch.get("title", f"分支第{i + 1}章")
                    ch_summary = ch.get("summary", "")

                    self._log(f"[分支创作] 第{ch_num}章: {title}")

                    ch_prompt = f"""基于决策分支继续创作。
分支选择: {br["alternative"]}
原文: {context_text[:800]}
章节大纲: {title}: {ch_summary}
请创作约{word_count}字的小说正文。"""

                    content = self.ai_client.chat(
                        [{"role": "user", "content": ch_prompt}],
                        system=f"你是专业小说作家。从决策分支点继续故事。\n类型: {genre}",
                        max_tokens=4096,
                    )
                    if not content:
                        content = f"（第{ch_num}章生成失败）"

                    ch_file = branch_dir / "chapters" / f"chapter_{ch_num:04d}.txt"
                    ch_file.write_text(f"# 分支第{i + 1}章: {title}\n\n{content}", encoding="utf-8")

                    # 定稿流程：摘要 + 角色成长 + 角色检测
                    if self.agent:
                        try:
                            ch_summary_text = self.ai_client.chat(
                                [{"role": "user", "content": f"请生成摘要(50-100字):\n{content[:1500]}"}],
                                system="生成精简摘要。",
                                max_tokens=1000,
                            )
                            branch_mem.save_chapter_summary(ch_num, ch_summary_text or content[:200])
                            (branch_dir / "summaries" / f"chapter_{ch_num:04d}_summary.txt").write_text(
                                f"分支第{i + 1}章: {title}\n\n{ch_summary_text or content[:200]}", encoding="utf-8"
                            )
                        except Exception:
                            pass

                    # 角色自动检测
                    try:
                        ch_detect_system = """提取新角色名(逗号分隔)，无则输出"无":"""
                        ch_response = self.ai_client.chat(
                            [{"role": "user", "content": f"第{ch_num}章:\n{content[:2000]}"}],
                            system=ch_detect_system,
                            max_tokens=1000,
                        )
                        if ch_response and ch_response.strip() != "无":
                            names = [n.strip() for n in ch_response.split(",") if n.strip()]
                            for name in names:
                                if not branch_chars.get_character(name):
                                    branch_chars.create_character(name=name, first_appearance=ch_num)
                                    branch_chars.save_character(name)
                                    self._log(f"[分支角色] 新增: {name}")
                    except Exception:
                        pass

                    # 更新上下文用于下一章
                    context_text = content[-1500:] if len(content) > 1500 else content

                    self._log(f"[分支创作] 第{ch_num}章完成 ({len(content)}字)")

                    if self._stop_flag:
                        break

                branch_meta["status"] = "completed"
                (branch_dir / "meta.json").write_text(
                    json.dumps(branch_meta, indent=2, ensure_ascii=False), encoding="utf-8"
                )

                self._log(f"[分支创作] 分支世界线完成: {branch_dir.name}")
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "完成", f"分支世界线创作完成！\n{branch_dir.name}/\n共{n_chapters}章\n\n角色系统/摘要均已生成"
                    ),
                )

            except Exception as e:
                self._log(f"[分支创作] 失败: {e}")
                self.root.after(0, lambda _exc=e: messagebox.showerror("失败", str(_exc)))

        self._stop_flag = False
        threading.Thread(target=run, daemon=True).start()
