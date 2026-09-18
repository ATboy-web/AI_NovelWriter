"""小说生命周期层：新建/打开/载入/续写/续集/外传/设置/简介/导入分析

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import shutil
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

from loguru import logger

from app import AIClient, ImageGenerator, MemoryManager, NoteManager, NovelAgent, UIStyle, dialogs
from app.events import TOPIC_CONFIG_CHANGED, TOPIC_NOVEL_CLOSED, TOPIC_NOVEL_OPENED
from app.genres import get_genre_registry
from app.storage import atomic_write_json, atomic_write_text


class NovelLifecycleMixin:
    """小说生命周期层：新建/打开/载入/续写/续集/外传/设置/简介/导入分析"""

    # ===== v3 P4：领域事件出口 =====

    def _announce_novel_opened(self, novel_dir):
        """广播 `novel.opened`（必要时先广播 `novel.closed`），让全部面板刷新到新小说（v3 §2.3）。

        统一收在这里，而不是散在 4 个打开入口里：新建 / 打开 / 续集 / 同人
        四条路径共用同一处发起，将来加第 5 条路径也不会漏。

        ⚠️ 调用时机：本方法只在入口把 `current_novel_dir` 改成新目录**之后**才被调用
        （4 处入口都是这个顺序），因此 `novel.closed` 的载荷里显式带上旧目录 ——
        订阅方不要在这个事件里读 `app.current_novel_dir`，那时它已经指向新书了。
        """
        events = getattr(self, "events", None)
        if events is None:
            return

        previous = getattr(self, "_announced_novel_dir", None)
        if previous and previous != str(novel_dir):
            self._publish_event(TOPIC_NOVEL_CLOSED, {"novel_dir": previous})
        self._announced_novel_dir = str(novel_dir)

        title = ""
        try:
            meta = json.loads((Path(novel_dir) / "meta.json").read_text(encoding="utf-8"))
            title = meta.get("title") or meta.get("original_title") or ""
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as e:
            # 标题只用于界面展示与日志，读不到不影响广播
            logger.debug(f"读取 meta.json 标题失败（不影响 novel.opened 广播）: {e}")
        self._publish_event(TOPIC_NOVEL_OPENED, {"novel_dir": str(novel_dir), "title": title})

    def _new_novel(self):
        """新建小说 - 支持用户输入想法"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建小说")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(900, sw - 60), int(sh * 0.88)
        x, y = (sw - w) // 2, (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.resizable(True, True)
        dialog.minsize(650, 700)
        dialog.transient(self.root)
        dialog.grab_set()

        C = UIStyle.COLORS

        # ===== 顶部固定区域 =====
        top = tk.Frame(dialog, bg=C["bg_dark"])
        top.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(8, 0))

        tk.Label(top, text="小说标题:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).grid(
            row=0, column=0, sticky=tk.W, pady=3
        )
        title_entry = tk.Entry(
            top,
            font=UIStyle.font("body"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            width=40,
        )
        title_entry.grid(row=0, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        # 用户想法输入框
        tk.Label(top, text="你的想法:", bg=C["bg_dark"], fg=C["warning"], font=UIStyle.font("label_bold")).grid(
            row=1, column=0, sticky=tk.NW, pady=3
        )
        idea_frame = tk.Frame(top, bg=C["bg_dark"])
        idea_frame.grid(row=1, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        idea_text = tk.Text(
            idea_frame,
            font=UIStyle.font("label"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            height=4,
            wrap=tk.WORD,
        )
        idea_text.pack(fill=tk.X)
        idea_text.insert("1.0", "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...")

        # 点击时清空提示文字
        def clear_placeholder(event):
            if idea_text.get("1.0", tk.END).strip() == "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...":
                idea_text.delete("1.0", tk.END)

        idea_text.bind("<FocusIn>", clear_placeholder)

        # 快速模板
        tk.Label(top, text="快速模板:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        template_var = tk.StringVar(value="无")
        template_combo = ttk.Combobox(top, textvariable=template_var, state="readonly", width=35)
        template_combo["values"] = ["无", "穿越异世", "重生归来", "系统流", "都市异能", "修仙问道"]
        template_combo.grid(row=2, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        # 模板变量输入区域
        template_vars_frame = tk.Frame(top, bg=C["bg_dark"])
        template_vars_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=3)

        template_entries = {}

        TEMPLATES = {
            "穿越异世": {
                "genre": "玄幻-异世大陆",
                "tags": ["穿越", "异世界"],
                "template": "一道白光闪过，{name}睁开眼发现自己躺在陌生的{place}，身边站着一位{creature}。",
                "vars": {"name": ("主角名", "李云"), "place": ("地点", "竹林"), "creature": ("人物", "白发老者")},
            },
            "重生归来": {
                "genre": "都市-都市异能",
                "tags": ["重生", "复仇"],
                "template": "当{name}再次睁开眼，发现自己回到了{year}年，一切还来得及改变。",
                "vars": {"name": ("主角名", "张伟"), "year": ("年份", "2010")},
            },
            "系统流": {
                "genre": "玄幻-东方玄幻",
                "tags": ["系统流", "升级"],
                "template": "叮！恭喜宿主{name}激活{system_name}系统，当前等级：Lv.1。",
                "vars": {"name": ("主角名", "王明"), "system_name": ("系统名", "万界商城")},
            },
            "都市异能": {
                "genre": "都市-都市异能",
                "tags": ["异能", "都市"],
                "template": "一场意外让{name}获得了{ability}的能力，从此生活发生了翻天覆地的变化。",
                "vars": {"name": ("主角名", ""), "ability": ("能力", "透视")},
            },
            "修仙问道": {
                "genre": "仙侠-古典仙侠",
                "tags": ["修仙", "问道"],
                "template": "少年{name}偶得{treasure}，踏上漫漫修仙路。",
                "vars": {"name": ("主角名", "陈轩"), "treasure": ("宝物", "上古功法")},
            },
        }

        def on_template_change(event=None):
            # 清除旧的模板变量输入框
            for widget in template_vars_frame.winfo_children():
                widget.destroy()
            template_entries.clear()

            template_name = template_var.get()
            if template_name == "无":
                return

            template = TEMPLATES.get(template_name, {})
            vars_def = template.get("vars", {})

            row = 0
            col = 0
            for var_name, (label, default) in vars_def.items():
                lbl = tk.Label(
                    template_vars_frame,
                    text=f"{label}:",
                    bg=C["bg_dark"],
                    fg=C["text_primary"],
                    font=UIStyle.font("caption"),
                )
                lbl.grid(row=row, column=col * 2, sticky=tk.W, padx=(0, 3), pady=1)
                entry = tk.Entry(
                    template_vars_frame, font=UIStyle.font("caption"), bg=C["bg_card"], fg=C["text_primary"], width=12
                )
                entry.insert(0, default)
                entry.grid(row=row, column=col * 2 + 1, padx=(0, 10), pady=1)
                template_entries[var_name] = entry
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        template_combo.bind("<<ComboboxSelected>>", on_template_change)

        tk.Label(top, text="小说频道:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).grid(
            row=4, column=0, sticky=tk.W, pady=3
        )
        channel_var = tk.StringVar(value="male")
        ch_frame = tk.Frame(top, bg=C["bg_dark"])
        ch_frame.grid(row=4, column=1, sticky=tk.W, padx=(5, 0), pady=3)

        tk.Label(top, text="小说类型:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).grid(
            row=5, column=0, sticky=tk.W, pady=3
        )
        # 题材来自注册表（`app/genres.py`），不再内联在本函数里。
        # ❗ 注册表不可用时**必须降级**而不是崩：题材选不了不该让新建对话框起不来。
        registry = get_genre_registry()
        if registry is None:
            self._log("[题材] 注册表不可用，题材选择已降级")
            genre_var = tk.StringVar(value="")
            genre_combo = ttk.Combobox(top, textvariable=genre_var, values=[], state="readonly", width=35)
        else:
            genre_var = tk.StringVar(value="")
            genre_combo = ttk.Combobox(top, textvariable=genre_var, state="readonly", width=35)
        genre_combo.grid(row=5, column=1, sticky=tk.EW, padx=(5, 0), pady=3)
        top.columnconfigure(1, weight=1)

        # 「管理题材」：增删自定义题材 / 隐藏内置题材
        genre_manage_btn = ttk.Button(top, text="管理题材…", width=11)
        genre_manage_btn.grid(row=5, column=2, sticky=tk.W, padx=(4, 0), pady=3)

        # ===== 中间可滚动标签区域 =====
        tag_outer = tk.LabelFrame(
            dialog,
            text=" 附加标签（可多选，滚轮上下/左右移动） ",
            padx=5,
            pady=5,
            bg=C["bg_dark"],
            fg=C["accent_light"],
            font=UIStyle.font("label"),
        )
        tag_outer.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        tag_canvas = tk.Canvas(tag_outer, bg=C["bg_dark"], highlightthickness=0, bd=0, height=200)
        tag_scrollbar_y = tk.Scrollbar(tag_outer, orient=tk.VERTICAL, command=tag_canvas.yview)
        tag_scrollbar_x = tk.Scrollbar(tag_outer, orient=tk.HORIZONTAL, command=tag_canvas.xview)
        tag_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        tag_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tag_canvas.configure(yscrollcommand=tag_scrollbar_y.set, xscrollcommand=tag_scrollbar_x.set)

        tags_container = tk.Frame(tag_canvas, bg=C["bg_dark"])
        tag_canvas_window = tag_canvas.create_window((0, 0), window=tags_container, anchor=tk.NW)

        # 鼠标滚轮滚动标签 - 支持上下和左右
        def on_tag_mousewheel(event):
            # 垂直滚动
            tag_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_tag_shift_mousewheel(event):
            # Shift+滚轮 = 水平滚动
            tag_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

        tag_canvas.bind("<MouseWheel>", on_tag_mousewheel)
        tag_canvas.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)
        tags_container.bind("<MouseWheel>", on_tag_mousewheel)
        tags_container.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)
        tag_outer.bind("<MouseWheel>", on_tag_mousewheel)
        tag_outer.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)

        # 使tags_container宽度跟随canvas
        def on_canvas_configure(event):
            tag_canvas.itemconfig(tag_canvas_window, width=event.width)

        tag_canvas.bind("<Configure>", on_canvas_configure)

        self.tag_vars = {}

        def update_tags(channel):
            """更新标签显示"""
            # 全部从注册表读；注册表为 None 时用空清单（界面仍可用，只是没得选）
            reg = get_genre_registry()
            if reg is None:
                genre_combo["values"] = []
                genre_var.set("")
                tags = {}
            else:
                names = reg.with_novel_genre(channel, genre_var.get())
                genre_combo["values"] = names
                # ❗ 保留用户/作品已选的题材（切频道时才重置）。
                # 原实现无条件 `set(第一个)`，会把用户刚选的题材清掉 ——
                # 而频道切换回调在初始化时也会被触发一次。
                if genre_var.get() not in names:
                    genre_var.set(names[0] if names else "")
                tags = reg.tags_for(channel)
            for w in tags_container.winfo_children():
                w.destroy()
            self.tag_vars.clear()
            for cat_name, cat_tags in tags.items():
                cat_label = tk.Label(
                    tags_container,
                    text=cat_name,
                    font=UIStyle.font("label_bold"),
                    bg=C["bg_dark"],
                    fg=C["accent_light"],
                    anchor=tk.W,
                )
                cat_label.pack(fill=tk.X, pady=(6, 1), padx=5)
                tag_line = tk.Frame(tags_container, bg=C["bg_dark"])
                tag_line.pack(fill=tk.X, padx=5)
                for tag in cat_tags:
                    var = tk.BooleanVar(value=False)
                    self.tag_vars[tag] = var
                    cb = tk.Checkbutton(
                        tag_line,
                        text=tag,
                        variable=var,
                        font=UIStyle.font("caption"),
                        bg=C["bg_dark"],
                        fg=C["text_secondary"],
                        selectcolor=C["bg_card"],
                        activebackground=C["bg_dark"],
                        activeforeground=C["accent_light"],
                        relief=tk.FLAT,
                        padx=1,
                        pady=0,
                    )
                    cb.pack(side=tk.LEFT, padx=2, pady=1)
            tags_container.update_idletasks()
            tag_canvas.configure(scrollregion=tag_canvas.bbox("all"))
            tag_canvas.yview_moveto(0)

        def on_manage_genres():
            """打开题材管理：增删自定义题材 / 隐藏内置题材。"""
            reg = get_genre_registry()
            if reg is None:
                dialogs.warn("题材配置不可用（无法读写配置文件）", parent=dialog)
                return
            self._open_genre_manager(dialog, channel_var.get(), reg)
            # ❗ 管理结果会改变清单，**必须**刷新 —— 否则用户刚加的题材在下拉里看不到，
            # 会以为"没生效"并反复添加。
            update_tags(channel_var.get())

        genre_manage_btn.config(command=on_manage_genres)

        # 频道选择
        for text, val in [("男生频道", "male"), ("女生频道", "female")]:
            rb = tk.Radiobutton(
                ch_frame,
                text=text,
                variable=channel_var,
                value=val,
                command=lambda v=val: update_tags(v),
                bg=C["bg_dark"],
                fg=C["text_primary"],
                selectcolor=C["bg_card"],
                activebackground=C["bg_dark"],
                activeforeground=C["accent_light"],
                font=UIStyle.font("label"),
            )
            rb.pack(side=tk.LEFT, padx=8)

        # 初始化标签
        update_tags("male")

        # 自定义标签输入
        custom_frame = tk.Frame(tag_outer, bg=C["bg_dark"])
        custom_frame.pack(fill=tk.X, padx=5, pady=(3, 0))
        tk.Label(
            custom_frame, text="自定义:", bg=C["bg_dark"], fg=C["text_secondary"], font=UIStyle.font("caption")
        ).pack(side=tk.LEFT)
        custom_tag_entry = tk.Entry(
            custom_frame,
            font=UIStyle.font("label"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            width=20,
        )
        custom_tag_entry.pack(side=tk.LEFT, padx=3)

        def add_custom_tag():
            tag = custom_tag_entry.get().strip()
            if not tag:
                return
            if tag in self.tag_vars:
                dialogs.showinfo("提示", f"标签 '{tag}' 已存在")
                return
            var = tk.BooleanVar(value=True)
            self.tag_vars[tag] = var
            # 添加到最后一行
            last_line = None
            for w in tags_container.winfo_children():
                if isinstance(w, tk.Frame):
                    last_line = w
            if last_line is None:
                last_line = tk.Frame(tags_container, bg=C["bg_dark"])
                last_line.pack(fill=tk.X, padx=5)
            cb = tk.Checkbutton(
                last_line,
                text=tag,
                variable=var,
                font=UIStyle.font("caption"),
                bg=C["bg_card"],
                fg=C["accent_light"],
                selectcolor=C["bg_dark"],
                activebackground=C["bg_card"],
                activeforeground=C["accent_light"],
                relief=tk.RAISED,
                padx=3,
                pady=1,
            )
            cb.pack(side=tk.LEFT, padx=2, pady=1)
            custom_tag_entry.delete(0, tk.END)
            self._log(f"添加自定义标签: {tag}")

        tk.Button(
            custom_frame,
            text="添加",
            command=add_custom_tag,
            font=UIStyle.font("caption"),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=5,
        ).pack(side=tk.LEFT, padx=3)
        custom_tag_entry.bind("<Return>", lambda e: add_custom_tag())

        # ===== 底部固定区域 =====
        bottom = tk.Frame(dialog, bg=C["bg_dark"])
        bottom.pack(fill=tk.X, padx=15, pady=(0, 5), side=tk.BOTTOM)

        # 章节数 + 每章字数 + 创建按钮（同一行）
        action_row = tk.Frame(bottom, bg=C["bg_dark"])
        action_row.pack(fill=tk.X, pady=3)
        tk.Label(action_row, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).pack(
            side=tk.LEFT
        )
        chapters_var = tk.StringVar(value="20")
        tk.Spinbox(
            action_row,
            from_=1,
            to=500,
            textvariable=chapters_var,
            width=6,
            font=UIStyle.font("label"),
            bg=C["bg_card"],
            fg=C["text_primary"],
        ).pack(side=tk.LEFT, padx=5)

        tk.Label(action_row, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).pack(
            side=tk.LEFT, padx=(15, 0)
        )
        word_count_var = tk.StringVar(value="10000")
        word_count_combo = ttk.Combobox(action_row, textvariable=word_count_var, width=8, font=UIStyle.font("label"))
        word_count_combo["values"] = ["1000", "2000", "3000", "5000", "8000", "10000", "15000", "20000"]
        word_count_combo.pack(side=tk.LEFT, padx=5)

        tk.Label(action_row, text="首次生成:", bg=C["bg_dark"], fg=C["text_primary"], font=UIStyle.font("label")).pack(
            side=tk.LEFT, padx=(15, 0)
        )
        first_batch_var = tk.StringVar(value="0")  # 0=一次性全部生成
        tk.Spinbox(
            action_row,
            from_=0,
            to=100,
            textvariable=first_batch_var,
            width=4,
            font=UIStyle.font("label"),
            bg=C["bg_card"],
            fg=C["text_primary"],
        ).pack(side=tk.LEFT, padx=5)
        tk.Label(
            action_row, text="章(0=全部)", bg=C["bg_dark"], fg=C["text_secondary"], font=UIStyle.font("caption")
        ).pack(side=tk.LEFT)

        def confirm():
            title = title_entry.get().strip()
            if not title:
                dialogs.showwarning("提示", "请输入小说标题")
                return

            genre_full = genre_var.get().split("-")
            genre = genre_full[0] if len(genre_full) > 0 else ""
            sub_genre = genre_full[1] if len(genre_full) > 1 else ""
            total_chapters = int(chapters_var.get())
            first_batch = int(first_batch_var.get())

            # 如果用户指定了首次生成章数，且小于总章节数
            if 0 < first_batch < total_chapters:
                chapters = first_batch
                self._log(f"首次生成{chapters}章，完成后可继续创作剩余章节")
            else:
                chapters = total_chapters

            # 获取用户想法
            user_idea = idea_text.get("1.0", tk.END).strip()
            if user_idea == "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...":
                user_idea = ""

            concept = user_idea  # 优先使用用户想法

            # 收集选中的标签
            selected_tags = [tag for tag, var in self.tag_vars.items() if var.get()]

            # 处理模板
            template_name = template_var.get()
            if template_name != "无" and template_name in TEMPLATES:
                template_data = TEMPLATES[template_name]
                # 收集模板变量值
                vars_values = {}
                for var_name, entry in template_entries.items():
                    vars_values[var_name] = entry.get().strip()

                # 生成模板内容
                template_content = template_data["template"]
                for var_name, value in vars_values.items():
                    template_content = template_content.replace(f"{{{var_name}}}", value)

                # 使用模板的类型和标签
                if not selected_tags:
                    selected_tags = template_data.get("tags", [])

                # 保存模板内容到概念
                if not concept:
                    concept = template_content

            # 创建小说目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存小说元数据
            meta = {
                "title": title,
                "genre": genre,
                "sub_genre": sub_genre,
                "channel": channel_var.get(),
                "tags": selected_tags,
                "concept": concept,
                "chapter_count": chapters,  # 当前要生成的章节数
                "total_chapters": total_chapters,  # 用户期望的总章节数（预览模式下用）
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "template": template_name if template_name != "无" else None,
            }
            atomic_write_json(novel_dir / "meta.json", meta)

            # 初始化
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.genre_var.set(f"{genre}-{sub_genre}")
            self.chapter_var.set(f"0/{total_chapters}")

            dialog.destroy()
            self._log(f"新建小说《{title}》({sub_genre}) 创建成功，目标{total_chapters}章，首先生成{chapters}章")

        tk.Button(
            action_row,
            text="创建小说",
            command=confirm,
            font=UIStyle.font("body_bold"),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=3,
        ).pack(side=tk.RIGHT)

    def _open_genre_manager(self, parent, channel: str, registry) -> None:
        """题材管理对话框：在**生效清单**上增删，按差集回写注册表。

        ## 为什么用"编辑整张清单 + 求差集"而不是"只编辑自定义项"

        用户的心智模型是"我要的题材列表长这样"，而不是"我要维护一份补丁"。
        让他直接编辑最终清单最自然；而差集能天然覆盖两种情况：

        | 用户动作 | 差集结果 | 注册表行为 |
        |---|---|---|
        | 加了新题材 | 新增项 | `add_genre` → 存为自定义 |
        | 删了自定义题材 | 消失项 | `remove_genre` → 从配置移除 |
        | 删了**内置**题材 | 消失项 | `remove_genre` → 加入隐藏表（**不改源码**） |

        这样"隐藏内置题材"不需要单独一套界面 —— 它就是"删除"的自然语义。
        再次添加同一个名字即可恢复（`add_genre` 会识别出它曾是隐藏项）。

        ## 已知取舍（写清楚，不做虚假承诺）

        `dialogs.edit_items` 支持上下移动，但**顺序不会被持久化**：
        生效顺序恒为「内置（保持原位）→ 自定义（追加在末尾）」。
        这是有意的 —— 自定义排序要引入一份完整的顺序表，
        而它带来的收益（微调下拉顺序）不值得那份复杂度与漂移风险。
        """
        current = registry.genres_for(channel)
        label = registry.channel_label(channel)
        new_list = dialogs.edit_items(
            parent,
            f"管理题材 · {label}",
            items=current,
            hint=(
                f"共 {len(current)} 个题材（当前频道：{label}）。\n"
                "· 新增的题材会保存为「自定义题材」，追加在列表末尾；\n"
                "· 删除内置题材只是**隐藏**它（不动源码），再次添加同名即可恢复；\n"
                "· 自定义顺序不保存，生效顺序恒为「内置 → 自定义」。\n"
                f"配置文件：{registry.config_file}"
            ),
        )
        if new_list is None:
            return  # 用户取消 ≠ 清空

        old_set, new_set = set(current), {str(x).strip() for x in new_list if str(x).strip()}
        added = [n for n in new_set - old_set]
        removed = [n for n in old_set - new_set]

        if not added and not removed:
            return

        failures: list[str] = []
        for name in added:
            res = registry.add_genre(channel, name)
            if not res.ok:
                failures.append(f"添加「{name}」失败：{res.message}")
        for name in removed:
            res = registry.remove_genre(channel, name)
            if not res.ok:
                failures.append(f"删除「{name}」失败：{res.message}")

        changed = len(added) + len(removed) - len(failures)
        if failures:
            # 部分失败要**明确告知**，否则用户会以为设置已生效
            dialogs.showwarning(
                "部分题材未生效",
                "\n".join(failures[:10]) + ("\n…" if len(failures) > 10 else ""),
                parent=parent,
            )
        if changed:
            self._log(f"[题材] {label}：新增 {len(added)} 个、删除/隐藏 {len(removed)} 个（共 {len(new_set)} 个生效）")

    def _open_novel(self):
        """打开小说 - 直接使用文件对话框"""
        novel_dir = filedialog.askdirectory(title="选择小说目录", initialdir=str(self.config.novels_dir))
        if not novel_dir:
            return

        self._load_novel(Path(novel_dir))

    def _load_novel(self, novel_dir: Path):
        """加载小说数据"""
        self._log(f"正在加载小说: {novel_dir}")

        meta_file = novel_dir / "meta.json"

        if not meta_file.exists():
            dialogs.showerror("错误", "该目录不是有效的小说目录")
            return

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self._log(f"读取meta.json成功: {meta.get('title')}")
        except Exception as e:
            dialogs.showerror("错误", f"读取meta.json失败: {e}")
            return

        try:
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self._log("设置current_novel_dir成功")
        except Exception as e:
            self._log(f"设置current_novel_dir失败: {e}")
            return

        try:
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self._log("MemoryManager初始化成功")
        except Exception as e:
            self._log(f"MemoryManager初始化失败: {e}")
            return

        try:
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self._log("NovelAgent初始化成功")
        except Exception as e:
            self._log(f"NovelAgent初始化失败: {e}")
            return

        try:
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self._log("NoteManager初始化成功")
        except Exception as e:
            self._log(f"NoteManager初始化失败: {e}")
            return

        try:
            self._init_character_system()
            self._log("角色系统初始化成功")
        except Exception as e:
            self._log(f"角色系统初始化失败: {e}")
            return

        try:
            self.title_var.set(meta.get("title", "未知"))
            self.genre_var.set(meta.get("genre", "未知"))
            self._log("标题和类型设置成功")
        except Exception as e:
            self._log(f"标题设置失败: {e}")

        # 加载大纲
        outline_file = novel_dir / "outline.json"
        if outline_file.exists():
            try:
                with open(outline_file, "r", encoding="utf-8") as f:
                    self.outline = json.load(f)
                self._refresh_outline_list()
                self._log(f"已加载大纲: {len(self.outline)} 章")
            except Exception as e:
                self._log(f"加载大纲失败: {e}")

        # 更新章节选择器
        try:
            self._update_chapter_selector()
            self._log("章节选择器更新成功")
        except Exception as e:
            self._log(f"章节选择器更新失败: {e}")

        # 计算进度
        chapters_dir = novel_dir / "chapters"
        total_chapters = meta.get("total_chapters", meta.get("chapter_count", 0))
        completed_chapters = 0

        if chapters_dir.exists():
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            completed_chapters = len(chapter_files)
            self.current_chapter = completed_chapters
            self.chapter_var.set(f"{completed_chapters}/{total_chapters or '?'}")
            self._log(f"章节数量: {completed_chapters}")

            # 加载最后一章内容到编辑器
            if chapter_files:
                last_chapter_file = chapter_files[-1]
                try:
                    content = last_chapter_file.read_text(encoding="utf-8")
                    self._log(f"读取章节内容: {len(content)} 字符")

                    # 清空并插入内容
                    self.content_text.delete("1.0", tk.END)
                    self.content_text.insert("1.0", content)

                    # 强制更新UI
                    self.content_text.update_idletasks()
                    self.root.update_idletasks()

                    self.word_count_var.set(f"字数: {len(content)}")
                    chapter_num = int(last_chapter_file.stem.split("_")[-1])
                    self.chapter_select_var.set(f"第{chapter_num}章")
                    self._log(f"已加载第{chapter_num}章内容到编辑器")
                except Exception as e:
                    self._log(f"加载最后一章失败: {e}")

        # 切换到章节内容标签页
        try:
            for i in range(self.notebook.index("end")):
                tab_text = self.notebook.tab(i, "text").strip()
                if tab_text == "章节内容":
                    self.notebook.select(i)
                    self._log(f"已切换到标签页: {tab_text}")
                    break
        except Exception as e:
            self._log(f"切换标签页失败: {e}")

        self._sync_characters_from_memory()
        self._log(f"已打开小说《{meta.get('title', '未知')}》")

        # 🛡️ 检查是否有未完成的生成任务（断电恢复）
        self._check_recovery()

        # 显示进度提示
        if total_chapters and completed_chapters > 0:
            if completed_chapters < total_chapters:
                remaining = total_chapters - completed_chapters
                msg = f"小说《{meta.get('title')}》进度：已完成 {completed_chapters}/{total_chapters} 章\n\n"
                msg += f"还剩 {remaining} 章未完成。\n\n"
                msg += "接下来可以：\n"
                msg += "1. 点击「自动创作」继续自动生成剩余章节\n"
                msg += "2. 点击「生成下一章」手动逐章创作\n"
                msg += "3. 在编辑器中手动编写"
                self.root.after(500, lambda: dialogs.showinfo("继续创作", msg))
            elif completed_chapters >= total_chapters:
                result = dialogs.askyesno(
                    "已完成", f"小说《{meta.get('title')}》已全部完成！共 {completed_chapters} 章。\n\n是否续写新章？"
                )
                if result:
                    self._continue_novel()

    def _continue_novel(self):
        """续写已完成的小说 - 扩展大纲和新章节"""
        if not self.current_novel_dir:
            return

        # 计算当前总章数
        chapters_dir = self.current_novel_dir / "chapters"
        existing = sorted(chapters_dir.glob("chapter_*.txt")) if chapters_dir.exists() else []
        current_count = len(existing)

        # 询问续写多少章
        add_count = simpledialog.askinteger(
            "续写",
            f"当前已完成 {current_count} 章\n输入要续写的章数（10-50）:",
            minvalue=1,
            maxvalue=100,
            initialvalue=10,
        )

        if not add_count:
            return

        self._log(f"开始续写 {add_count} 章...")

        # 扩展大纲
        if not self.outline:
            self.outline = []

        meta = self._get_meta()
        title = meta.get("title", "小说")
        genre = meta.get("genre", "未知")

        # 生成新的大纲章节
        try:
            context = self.memory.get_global_summary() if self.memory else ""
            new_chapters = self.agent.generate_outline_continuation(genre, title, add_count, context, current_count)
            self.outline.extend(new_chapters)

            # 保存更新后的大纲
            self._novel_store().write_outline(self.outline)

            # 更新meta（读-改-写在同一把锁内，避免覆盖并发方的改动）
            if self._novel_store().exists("meta.json"):
                self._novel_store().update_meta({"chapter_count": len(self.outline)})

            self.current_chapter = current_count
            self._refresh_outline_list()
            self.chapter_var.set(f"{current_count}/{len(self.outline)}")
            self._log(f"大纲已扩展到 {len(self.outline)} 章，可以继续创作了")

            dialogs.showinfo(
                "续写",
                f"已添加 {add_count} 章新大纲\n总章数: {len(self.outline)}\n\n点击「自动创作」或「生成下一章」继续写作",
            )

        except Exception as e:
            self._log(f"续写大纲生成失败: {e}")
            dialogs.showerror("错误", f"续写失败: {e}")

    def _create_sequel(self):
        """基于当前小说创建续集（第二部）"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先打开一部已完成的小说")
            return

        meta_file = self.current_novel_dir / "meta.json"
        if not meta_file.exists():
            dialogs.showerror("错误", "当前目录不是有效的小说目录")
            return

        with open(meta_file, "r", encoding="utf-8") as f:
            original_meta = json.load(f)

        # 检查是否已完成
        chapters_dir = self.current_novel_dir / "chapters"
        if chapters_dir.exists():
            chapter_count = len(list(chapters_dir.glob("chapter_*.txt")))
            if chapter_count < original_meta.get("chapter_count", 0):
                if not dialogs.askyesno("提示", "当前小说尚未全部完成，确定要创建续集吗？"):
                    return

        # 读取原始小说的全局摘要
        global_summary = ""
        summary_file = self.current_novel_dir / "memory" / "global_summary.txt"
        if summary_file.exists():
            global_summary = summary_file.read_text(encoding="utf-8")

        # 创建续集对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("创建续集 - 第二部")
        dialog.geometry("600x500")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog,
            text=f"《{original_meta.get('title', '')}》续集",
            font=UIStyle.font("heading"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
        ).pack(pady=(15, 10))

        # 续集标题
        title_frame = tk.Frame(dialog, bg=C["bg_dark"])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="续集标题:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=UIStyle.font("body"), bg=C["bg_card"], fg=C["text_primary"])
        title_entry.insert(0, f"{original_meta.get('title', '')} 第二部")
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 续集概念
        tk.Label(dialog, text="续集概念/方向:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
            anchor=tk.W, padx=20, pady=(10, 3)
        )
        concept_text = tk.Text(
            dialog, wrap=tk.WORD, font=UIStyle.font("body"), bg=C["bg_card"], fg=C["text_primary"], height=5
        )
        concept_text.pack(fill=tk.X, padx=20, pady=5)
        concept_text.insert("1.0", "延续第一部的世界观和角色，展开新的冒险...")

        # 原著摘要预览
        if global_summary:
            tk.Label(dialog, text="原著摘要（AI将基于此生成续集）:", bg=C["bg_dark"], fg=C["text_muted"]).pack(
                anchor=tk.W, padx=20, pady=(10, 3)
            )
            summary_preview = tk.Text(
                dialog, wrap=tk.WORD, font=UIStyle.font("label"), bg=C["bg_card"], fg=C["text_secondary"], height=4
            )
            summary_preview.pack(fill=tk.X, padx=20, pady=5)
            summary_preview.insert("1.0", global_summary[:500] + ("..." if len(global_summary) > 500 else ""))
            summary_preview.config(state=tk.DISABLED)

        # 章节数和字数
        params_frame = tk.Frame(dialog, bg=C["bg_dark"])
        params_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(params_frame, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value=str(original_meta.get("chapter_count", 20)))
        tk.Spinbox(params_frame, from_=1, to=500, textvariable=chapters_var, width=6, font=UIStyle.font("label")).pack(
            side=tk.LEFT, padx=5
        )
        tk.Label(params_frame, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT, padx=(15, 0))
        word_count_var = tk.StringVar(value=str(original_meta.get("word_count_per_chapter", 3000)))
        ttk.Combobox(
            params_frame, textvariable=word_count_var, values=["1000", "2000", "3000", "5000", "8000"], width=8
        ).pack(side=tk.LEFT, padx=5)

        def confirm():
            title = title_entry.get().strip()
            if not title:
                dialogs.showwarning("提示", "请输入续集标题")
                return

            concept = concept_text.get("1.0", tk.END).strip()

            # 创建续集目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存续集元数据（关联原著）
            sequel_meta = {
                "title": title,
                "genre": original_meta.get("genre", ""),
                "sub_genre": original_meta.get("sub_genre", ""),
                "channel": original_meta.get("channel", "male"),
                "tags": original_meta.get("tags", []),
                "concept": concept,
                "chapter_count": int(chapters_var.get()),
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "is_sequel": True,
                "original_novel": str(self.current_novel_dir),
                "original_title": original_meta.get("title", ""),
            }
            atomic_write_json(novel_dir / "meta.json", sequel_meta)

            # 复制原著的世界观和角色设定
            orig_memory = self.current_novel_dir / "memory"
            new_memory = novel_dir / "memory"
            new_memory.mkdir(exist_ok=True)

            # 复制世界观
            orig_settings = orig_memory / "settings.json"
            if orig_settings.exists():
                shutil.copy2(orig_settings, new_memory / "settings.json")

            # 复制角色
            orig_chars = self.current_novel_dir / "characters"
            if orig_chars.exists():
                shutil.copytree(orig_chars, novel_dir / "characters", dirs_exist_ok=True)

            # 保存续集概念作为参考
            atomic_write_text(
                novel_dir / "sequel_concept.txt",
                f"原著: {original_meta.get('title', '')}\n\n"
                + f"原著摘要:\n{global_summary}\n\n"
                + f"续集概念:\n{concept}",
            )

            # 切换到续集
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.genre_var.set(f"{original_meta.get('genre', '')}-{original_meta.get('sub_genre', '')}")
            self.chapter_var.set(f"0/{chapters_var.get()}")

            dialog.destroy()
            self._log(f"续集《{title}》已创建，基于原著《{original_meta.get('title', '')}》")
            dialogs.showinfo("成功", f"续集《{title}》已创建！\n世界观和角色已继承自原著。\n点击「自动创作」开始生成。")

        tk.Button(
            dialog,
            text="创建续集",
            command=confirm,
            bg=C["accent"],
            fg="white",
            font=UIStyle.font("subtitle_bold"),
            padx=30,
            pady=8,
        ).pack(pady=15)

    def _create_spinoff(self):
        """基于当前小说创建同人衍生作品"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先打开一部小说作为原著")
            return

        meta_file = self.current_novel_dir / "meta.json"
        if not meta_file.exists():
            dialogs.showerror("错误", "当前目录不是有效的小说目录")
            return

        with open(meta_file, "r", encoding="utf-8") as f:
            original_meta = json.load(f)

        # 读取角色信息
        characters = self.memory.get_characters() if self.memory else {}
        char_names = list(characters.keys()) if characters else []

        # 创建同人作品对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("创建同人衍生作品")
        dialog.geometry("650x600")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog,
            text=f"基于《{original_meta.get('title', '')}》的同人作品",
            font=UIStyle.font("heading"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
        ).pack(pady=(15, 10))

        # 同人作品标题
        title_frame = tk.Frame(dialog, bg=C["bg_dark"])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="作品标题:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=UIStyle.font("body"), bg=C["bg_card"], fg=C["text_primary"])
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 衍生类型
        type_frame = tk.Frame(dialog, bg=C["bg_dark"])
        type_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(type_frame, text="衍生类型:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        spinoff_type = tk.StringVar(value="平行世界")
        ttk.Combobox(
            type_frame,
            textvariable=spinoff_type,
            values=["平行世界", "角色外传", "前传", "IF线", "现代AU", "古代AU", "其他"],
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT, padx=5)

        # 选择主要角色
        if char_names:
            tk.Label(dialog, text="选择主要角色（可多选）:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
                anchor=tk.W, padx=20, pady=(10, 3)
            )
            char_frame = tk.Frame(dialog, bg=C["bg_card"])
            char_frame.pack(fill=tk.X, padx=20, pady=5)

            char_vars = {}
            for name in char_names[:10]:  # 最多显示10个角色
                var = tk.BooleanVar(value=False)
                char_vars[name] = var
                tk.Checkbutton(
                    char_frame,
                    text=name,
                    variable=var,
                    bg=C["bg_card"],
                    fg=C["text_primary"],
                    selectcolor=C["bg_dark"],
                    font=UIStyle.font("label"),
                ).pack(side=tk.LEFT, padx=5)

        # 衍生概念
        tk.Label(dialog, text="衍生概念/设定:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
            anchor=tk.W, padx=20, pady=(10, 3)
        )
        concept_text = tk.Text(
            dialog, wrap=tk.WORD, font=UIStyle.font("body"), bg=C["bg_card"], fg=C["text_primary"], height=6
        )
        concept_text.pack(fill=tk.X, padx=20, pady=5)
        concept_text.insert("1.0", "在这个平行世界中...")

        # 章节数和字数
        params_frame = tk.Frame(dialog, bg=C["bg_dark"])
        params_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(params_frame, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value="10")
        tk.Spinbox(params_frame, from_=1, to=200, textvariable=chapters_var, width=6, font=UIStyle.font("label")).pack(
            side=tk.LEFT, padx=5
        )
        tk.Label(params_frame, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT, padx=(15, 0))
        word_count_var = tk.StringVar(value="3000")
        ttk.Combobox(params_frame, textvariable=word_count_var, values=["1000", "2000", "3000", "5000"], width=8).pack(
            side=tk.LEFT, padx=5
        )

        def confirm():
            title = title_entry.get().strip()
            if not title:
                dialogs.showwarning("提示", "请输入作品标题")
                return

            concept = concept_text.get("1.0", tk.END).strip()
            selected_chars = [name for name, var in char_vars.items() if var.get()] if char_names else []

            # 创建同人作品目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存同人作品元数据
            spinoff_meta = {
                "title": title,
                "genre": original_meta.get("genre", ""),
                "sub_genre": original_meta.get("sub_genre", ""),
                "channel": original_meta.get("channel", "male"),
                "tags": original_meta.get("tags", []) + ["同人", spinoff_type.get()],
                "concept": concept,
                "chapter_count": int(chapters_var.get()),
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "is_spinoff": True,
                "spinoff_type": spinoff_type.get(),
                "original_novel": str(self.current_novel_dir),
                "original_title": original_meta.get("title", ""),
                "selected_characters": selected_chars,
            }
            atomic_write_json(novel_dir / "meta.json", spinoff_meta)

            # 复制世界观设定
            orig_memory = self.current_novel_dir / "memory"
            new_memory = novel_dir / "memory"
            new_memory.mkdir(exist_ok=True)

            orig_settings = orig_memory / "settings.json"
            if orig_settings.exists():
                shutil.copy2(orig_settings, new_memory / "settings.json")

            # 复制选定的角色
            if selected_chars and characters:
                chars_dir = novel_dir / "characters"
                chars_dir.mkdir(exist_ok=True)
                for char_name in selected_chars:
                    char_file = self.current_novel_dir / "characters" / f"{char_name}.json"
                    if char_file.exists():
                        shutil.copy2(char_file, chars_dir / f"{char_name}.json")

            # 保存同人设定文档
            atomic_write_text(
                novel_dir / "spinoff_concept.txt",
                f"原著: {original_meta.get('title', '')}\n"
                + f"衍生类型: {spinoff_type.get()}\n"
                + f"主要角色: {', '.join(selected_chars)}\n\n"
                + f"衍生概念:\n{concept}",
            )

            # 切换到同人作品
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.chapter_var.set(f"0/{chapters_var.get()}")

            dialog.destroy()
            self._log(f"同人作品《{title}》已创建，类型：{spinoff_type.get()}")
            dialogs.showinfo(
                "成功",
                f"同人作品《{title}》已创建！\n类型：{spinoff_type.get()}\n角色：{', '.join(selected_chars) or '无'}\n点击「自动创作」开始生成。",
            )

        tk.Button(
            dialog,
            text="创建同人作品",
            command=confirm,
            bg=C["accent"],
            fg="white",
            font=UIStyle.font("subtitle_bold"),
            padx=30,
            pady=8,
        ).pack(pady=15)

    def _show_settings(self):
        """显示设置对话框 - 带滚动支持"""
        dialog = tk.Toplevel(self.root)
        dialog.title("系统配置")
        dialog.geometry("600x520")
        dialog.transient(self.root)
        dialog.grab_set()

        # 创建Canvas和滚动条
        canvas = tk.Canvas(dialog, highlightthickness=0)
        h_scrollbar = ttk.Scrollbar(dialog, orient=tk.HORIZONTAL, command=canvas.xview)
        v_scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=canvas.yview)

        canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 创建内容框架
        content_frame = tk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=content_frame, anchor=tk.NW)

        # 更新滚动区域
        def update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        content_frame.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_scrollregion)

        # 鼠标滚轮支持
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_shift_mousewheel(event):
            canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Shift-MouseWheel>", on_shift_mousewheel)

        notebook = ttk.Notebook(content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # ===== Tab 1: AI模型配置 =====
        # P2-5：整页交给 AISettingsMixin 构建（注册表驱动下拉 + 多 Profile +
        # 超时/重试/思考模式 + 测试连接/余额/URL 预览）。
        # 旧实现把服务商清单、模型预设、API 地址预设在这里维护了第二份，
        # 与注册表漂移（选不到 kimi/mimo）；并且有两个温度输入框绑同一变量。
        ai_frame = ttk.Frame(notebook)
        notebook.add(ai_frame, text="AI模型")
        ai_save = self._build_ai_settings_tab(ai_frame, dialog)

        # ===== Tab 2: 文生图配置 =====
        img_frame = ttk.Frame(notebook)
        notebook.add(img_frame, text="文生图")

        ttk.Label(img_frame, text="文生图后端:").pack(anchor=tk.W, padx=20, pady=(15, 3))
        img_provider_var = tk.StringVar(value=self.config.get("img_provider", "comfyui"))
        ttk.Combobox(
            img_frame,
            textvariable=img_provider_var,
            values=["comfyui", "sdapi", "disabled"],
            state="readonly",
            width=50,
        ).pack(padx=20, pady=3)

        ttk.Label(img_frame, text="API地址:").pack(anchor=tk.W, padx=20, pady=(10, 3))
        img_base_entry = ttk.Entry(img_frame, width=52)
        img_base_entry.insert(0, self.config.get("img_api_base", "http://127.0.0.1:8188"))
        img_base_entry.pack(padx=20, pady=3)

        ttk.Label(img_frame, text="ComfyUI默认端口: 8188, SD WebUI默认端口: 7860").pack(
            anchor=tk.W, padx=20, pady=(3, 10)
        )

        ttk.Label(img_frame, text="模型文件名:").pack(anchor=tk.W, padx=20, pady=(5, 3))
        img_model_entry = ttk.Entry(img_frame, width=52)
        img_model_entry.insert(0, self.config.get("img_model", "sd_xl_base_1.0.safetensors"))
        img_model_entry.pack(padx=20, pady=3)

        # 尺寸：审计发现 `img_width` / `img_height` 原先既**不可编辑**也**不被读取**
        # （`ImageGenerator.generate` 的默认值写死 1024）—— 属"声明了但完全无效"的配置项。
        # 这里补上输入框，并让 `generate()` 从配置取，两端才接通。
        size_row = tk.Frame(img_frame)
        size_row.pack(anchor=tk.W, padx=20, pady=(8, 3))
        tk.Label(size_row, text="图片宽:").pack(side=tk.LEFT)
        img_width_entry = ttk.Entry(size_row, width=8)
        img_width_entry.insert(0, str(self.config.get("img_width", 1024)))
        img_width_entry.pack(side=tk.LEFT, padx=(4, 16))
        tk.Label(size_row, text="高:").pack(side=tk.LEFT)
        img_height_entry = ttk.Entry(size_row, width=8)
        img_height_entry.insert(0, str(self.config.get("img_height", 1024)))
        img_height_entry.pack(side=tk.LEFT, padx=4)
        tk.Label(size_row, text="（像素，须为正整数且是 8 的倍数）").pack(side=tk.LEFT, padx=8)

        auto_detect_var = tk.BooleanVar(value=self.config.get("auto_detect_scene", True))
        ttk.Checkbutton(img_frame, text="生成章节后自动检测名场面并提醒生成插图", variable=auto_detect_var).pack(
            anchor=tk.W, padx=20, pady=15
        )

        ttk.Label(
            img_frame,
            text="支持的后端:\n- ComfyUI: 本地部署的ComfyUI，需启动API模式\n- SD API: Stable Diffusion WebUI的API模式\n- Disabled: 不使用文生图",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=20, pady=10)

        # ===== Tab 3: 云端存储配置 =====
        cloud_frame = ttk.Frame(notebook)
        notebook.add(cloud_frame, text="云端存储")

        ttk.Label(cloud_frame, text="云端存储配置", font=UIStyle.font("default_bold")).pack(
            anchor=tk.W, padx=20, pady=(15, 10)
        )
        ttk.Label(cloud_frame, text="支持: WebDAV（坚果云）、百度网盘、夸克网盘、迅雷网盘、阿里云盘").pack(
            anchor=tk.W, padx=20, pady=(0, 10)
        )

        # 云存储提供商选择
        cloud_provider_var = tk.StringVar(value="webdav")
        providers = self.cloud_storage.get_available_providers()
        provider_names = [p["name"] for p in providers]
        provider_ids = [p["id"] for p in providers]

        ttk.Label(cloud_frame, text="选择云存储:").pack(anchor=tk.W, padx=20, pady=(5, 3))
        cloud_combo = ttk.Combobox(
            cloud_frame, textvariable=cloud_provider_var, values=provider_names, state="readonly", width=50
        )
        cloud_combo.pack(padx=20, pady=3)
        cloud_combo.set(provider_names[0] if provider_names else "")

        # 配置区域
        config_frame = ttk.LabelFrame(cloud_frame, text="配置信息", padding=10)
        config_frame.pack(fill=tk.X, padx=20, pady=10)

        # WebDAV配置
        webdav_frame = ttk.Frame(config_frame)
        ttk.Label(webdav_frame, text="WebDAV地址:").grid(row=0, column=0, sticky=tk.W, pady=2)
        webdav_url_entry = ttk.Entry(webdav_frame, width=40)
        webdav_url_entry.insert(
            0, self.cloud_storage.config.get("webdav", {}).get("url", "https://dav.jianguoyun.com/dav/")
        )
        webdav_url_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(webdav_frame, text="用户名:").grid(row=1, column=0, sticky=tk.W, pady=2)
        webdav_user_entry = ttk.Entry(webdav_frame, width=40)
        webdav_user_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("username", ""))
        webdav_user_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(webdav_frame, text="密码/应用密钥:").grid(row=2, column=0, sticky=tk.W, pady=2)
        webdav_pass_entry = ttk.Entry(webdav_frame, width=40, show="*")
        webdav_pass_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("password", ""))
        webdav_pass_entry.grid(row=2, column=1, padx=5, pady=2)
        webdav_frame.pack(fill=tk.X, padx=10, pady=5)

        # 百度网盘配置
        baidu_frame = ttk.Frame(config_frame)
        ttk.Label(baidu_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        baidu_token_entry = ttk.Entry(baidu_frame, width=40)
        baidu_token_entry.insert(0, self.cloud_storage.config.get("baidu", {}).get("access_token", ""))
        baidu_token_entry.grid(row=0, column=1, padx=5, pady=2)
        baidu_frame.pack(fill=tk.X, padx=10, pady=5)

        # 夸克网盘配置
        quark_frame = ttk.Frame(config_frame)
        ttk.Label(quark_frame, text="Cookie:").grid(row=0, column=0, sticky=tk.W, pady=2)
        quark_cookie_entry = ttk.Entry(quark_frame, width=40)
        quark_cookie_entry.insert(0, self.cloud_storage.config.get("quark", {}).get("cookie", ""))
        quark_cookie_entry.grid(row=0, column=1, padx=5, pady=2)
        quark_frame.pack(fill=tk.X, padx=10, pady=5)

        # 迅雷网盘配置
        xunlei_frame = ttk.Frame(config_frame)
        ttk.Label(xunlei_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        xunlei_token_entry = ttk.Entry(xunlei_frame, width=40)
        xunlei_token_entry.insert(0, self.cloud_storage.config.get("xunlei", {}).get("access_token", ""))
        xunlei_token_entry.grid(row=0, column=1, padx=5, pady=2)
        xunlei_frame.pack(fill=tk.X, padx=10, pady=5)

        # 阿里云盘配置
        aliyun_frame = ttk.Frame(config_frame)
        ttk.Label(aliyun_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        aliyun_token_entry = ttk.Entry(aliyun_frame, width=40)
        aliyun_token_entry.insert(0, self.cloud_storage.config.get("aliyun", {}).get("access_token", ""))
        aliyun_token_entry.grid(row=0, column=1, padx=5, pady=2)
        aliyun_frame.pack(fill=tk.X, padx=10, pady=5)

        # 测试连接按钮
        def test_cloud_connection():
            provider_name = cloud_combo.get()
            provider_id = (
                provider_ids[provider_names.index(provider_name)] if provider_name in provider_names else "webdav"
            )

            # 保存配置
            if provider_id == "webdav":
                self.cloud_storage.configure_provider(
                    "webdav",
                    {
                        "url": webdav_url_entry.get(),
                        "username": webdav_user_entry.get(),
                        "password": webdav_pass_entry.get(),
                    },
                )
            elif provider_id == "baidu":
                self.cloud_storage.configure_provider("baidu", {"access_token": baidu_token_entry.get()})
            elif provider_id == "quark":
                self.cloud_storage.configure_provider("quark", {"cookie": quark_cookie_entry.get()})
            elif provider_id == "xunlei":
                self.cloud_storage.configure_provider("xunlei", {"access_token": xunlei_token_entry.get()})
            elif provider_id == "aliyun":
                self.cloud_storage.configure_provider("aliyun", {"access_token": aliyun_token_entry.get()})

            # 测试连接
            if self.cloud_storage.connect_provider(provider_id):
                dialogs.showinfo("成功", f"{provider_name} 连接成功！")
            else:
                dialogs.showwarning("失败", f"{provider_name} 连接失败，请检查配置")

        ttk.Button(cloud_frame, text="测试连接", command=test_cloud_connection).pack(pady=10)

        # ===== Tab 5: 高级设置 =====
        advanced_frame = ttk.Frame(notebook)
        notebook.add(advanced_frame, text="高级")

        # 18+内容开关（隐藏按钮）
        adult_frame = tk.LabelFrame(advanced_frame, text=" 内容控制 ", padx=10, pady=10)
        adult_frame.pack(fill=tk.X, padx=15, pady=10)

        # 三角形隐藏按钮
        secret_frame = tk.Frame(adult_frame)
        secret_frame.pack(fill=tk.X, pady=5)

        self._adult_toggle_visible = False
        adult_var = tk.BooleanVar(value=self.config.get("adult_content", False))

        def toggle_adult_visibility():
            """点击三角形显示/隐藏18+开关"""
            self._adult_toggle_visible = not self._adult_toggle_visible
            if self._adult_toggle_visible:
                adult_controls.pack(fill=tk.X, pady=5)
                secret_btn.configure(text="▼ 18+内容设置")
            else:
                adult_controls.pack_forget()
                secret_btn.configure(text="▶ 点击展开更多设置")

        secret_btn = tk.Button(
            secret_frame,
            text="▶ 点击展开更多设置",
            command=toggle_adult_visibility,
            relief=tk.FLAT,
            fg="gray",
            font=UIStyle.font("caption"),
            anchor=tk.W,
        )
        secret_btn.pack(side=tk.LEFT)

        adult_controls = tk.Frame(adult_frame)

        tk.Label(adult_controls, text="⚠️ 以下功能仅供成年用户使用", fg="red", font=UIStyle.font("label_bold")).pack(
            anchor=tk.W, pady=(5, 10)
        )

        adult_check = tk.Checkbutton(
            adult_controls, text="启用18+内容生成", variable=adult_var, font=UIStyle.font("body")
        )
        adult_check.pack(anchor=tk.W, pady=3)

        edge_var = tk.BooleanVar(value=self.config.get("edge_content", False))
        edge_check = tk.Checkbutton(adult_controls, text="允许擦边内容", variable=edge_var, font=UIStyle.font("body"))
        edge_check.pack(anchor=tk.W, pady=3)

        tk.Label(
            adult_controls, text="启用后，AI在创作时会根据剧情需要加入相关描写", fg="gray", font=UIStyle.font("caption")
        ).pack(anchor=tk.W, pady=(5, 0))

        # 卷管理设置
        volume_frame = tk.LabelFrame(advanced_frame, text=" 卷管理 ", padx=10, pady=10)
        volume_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(volume_frame, text="每卷默认章节数:", font=UIStyle.font("body")).pack(anchor=tk.W, pady=3)
        vol_chapters_var = tk.StringVar(value=str(self.config.get("chapters_per_volume", 100)))
        ttk.Spinbox(volume_frame, from_=10, to=500, textvariable=vol_chapters_var, width=10).pack(anchor=tk.W, pady=3)

        tk.Label(volume_frame, text="角色传记默认字数:", font=UIStyle.font("body")).pack(anchor=tk.W, pady=(10, 3))
        bio_words_var = tk.StringVar(value=str(self.config.get("biography_word_count", 100000)))
        bio_combo = ttk.Combobox(
            volume_frame, textvariable=bio_words_var, values=["10000", "30000", "50000", "100000", "200000"], width=10
        )
        bio_combo.pack(anchor=tk.W, pady=3)
        tk.Label(volume_frame, text="生成角色个人传时的默认字数", fg="gray", font=UIStyle.font("caption")).pack(
            anchor=tk.W
        )

        # 智能体优化
        agent_frame = tk.LabelFrame(advanced_frame, text=" 智能体优化 ", padx=10, pady=10)
        agent_frame.pack(fill=tk.X, padx=15, pady=10)

        context_var = tk.BooleanVar(value=self.config.get("smart_context", True))
        tk.Checkbutton(
            agent_frame, text="智能上下文管理（防止章节过多卡死）", variable=context_var, font=UIStyle.font("body")
        ).pack(anchor=tk.W, pady=3)

        summary_var = tk.BooleanVar(value=self.config.get("auto_summary", True))
        tk.Checkbutton(
            agent_frame, text="自动生成章节摘要（改善上下文连贯性）", variable=summary_var, font=UIStyle.font("body")
        ).pack(anchor=tk.W, pady=3)

        # ===== 保存 =====
        def save():
            # AI 页签（含 provider / key / base / model / 采样 / 超时 / 多档案）
            # 由 AISettingsMixin 负责；它内部按字段逐个校验，非法值会弹窗并中止。
            ai_save()

            def _num(var, caster, label):
                """数值输入的统一校验：空串按未填写处理，非法值明确报错。"""
                raw = str(var.get()).strip()
                if not raw:
                    raise ValueError(f"{label}不能为空")
                return caster(raw)

            try:
                self.config.set("img_provider", img_provider_var.get())
                self.config.set("img_api_base", img_base_entry.get().strip())
                self.config.set("img_model", img_model_entry.get().strip())
                # 尺寸：与 `ImageGenerator._dimension` 的读取端配套。
                # 8 的倍数是 SD 系后端的硬要求（不满足会生成失败或出怪图），
                # 所以在入口就拦住并明确报错，而不是让它到生成时才失败。
                for _entry, _key, _label in (
                    (img_width_entry, "img_width", "图片宽"),
                    (img_height_entry, "img_height", "图片高"),
                ):
                    _v = _num(_entry, int, _label)
                    if _v <= 0 or _v % 8:
                        raise ValueError(f"{_label}须为正整数且是 8 的倍数（当前 {_v}）")
                    self.config.set(_key, _v)
                self.config.set("auto_detect_scene", auto_detect_var.get())
                self.config.set("adult_content", adult_var.get())
                self.config.set("edge_content", edge_var.get())
                self.config.set("chapters_per_volume", _num(vol_chapters_var, int, "每卷章节数"))
                self.config.set("biography_word_count", _num(bio_words_var, int, "传记字数"))
                self.config.set("smart_context", context_var.get())
                self.config.set("auto_summary", summary_var.get())
            except (ValueError, RuntimeError) as exc:
                dialogs.showerror("配置未保存", f"输入有误：{exc}", parent=dialog)
                return

            self.ai_client = AIClient(self.config)
            self.image_gen = ImageGenerator(self.config)
            if self.memory:
                self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)

            self._update_status()
            # v3 P4：配置已落盘 + 客户端已重建，广播出去（状态栏/面板据此刷新）
            self._publish_event(
                TOPIC_CONFIG_CHANGED,
                {
                    "active_profile": getattr(self.config, "active_profile", ""),
                },
            )
            dialog.destroy()
            self._log("配置已保存")

        # 底部按钮区
        btn_frame = tk.Frame(content_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        ttk.Button(btn_frame, text="保存配置", command=save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def _generate_synopsis(self):
        """AI生成书籍简介"""
        if not self._check_ready():
            return

        def run():
            try:
                self._log("正在生成书籍简介...")

                meta = self._get_meta()
                settings = self.memory.get_settings() if self.memory else {}
                outline = self.outline if self.outline else []

                system = """你是专业的书籍简介撰写专家。根据小说的世界观、大纲和设定，撰写一段吸引读者的书籍简介。

简介要求：
1. 150-300字
2. 突出故事亮点和卖点
3. 设置悬念，吸引读者
4. 不要剧透关键情节
5. 语言精炼有力"""

                prompt = f"""小说信息：
标题：{meta.get("title", "未命名")}
类型：{meta.get("genre", "未知")}
概念：{meta.get("concept", "无")}

世界观：{json.dumps(settings, ensure_ascii=False)[:500]}

大纲概要：{json.dumps(outline[:10], ensure_ascii=False)[:500]}

请生成书籍简介。"""

                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1000)

                # 保存简介
                synopsis_file = self.current_novel_dir / "synopsis.txt"
                synopsis_file.write_text(result, encoding="utf-8")

                self.root.after(0, lambda: self._show_synopsis(result))
                self._log("书籍简介生成完成")

            except Exception as e:
                self._log(f"简介生成失败: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _show_synopsis(self, content: str):
        """显示书籍简介"""
        dialog = tk.Toplevel(self.root)
        dialog.title("书籍简介")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="书籍简介", font=UIStyle.font("heading"), bg=C["bg_dark"], fg=C["accent_light"]).pack(
            pady=(15, 10)
        )

        synopsis_text = tk.Text(
            dialog,
            wrap=tk.WORD,
            font=UIStyle.font("title_plain"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            padx=20,
            pady=15,
        )
        synopsis_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        synopsis_text.insert("1.0", content)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def save():
            new_content = synopsis_text.get("1.0", tk.END).strip()
            synopsis_file = self.current_novel_dir / "synopsis.txt"
            synopsis_file.write_text(new_content, encoding="utf-8")
            dialog.destroy()
            self._log("书籍简介已保存")

        tk.Button(
            btn_frame, text="保存", command=save, bg=C["success"], fg="white", font=UIStyle.font("body"), padx=20
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="关闭",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)

    def _import_document(self):
        """导入作者文档（txt/docx/md）"""
        file_path = filedialog.askopenfilename(
            title="选择要导入的文档",
            filetypes=[
                ("所有支持格式", "*.txt *.docx *.md"),
                ("TXT文件", "*.txt"),
                ("Word文档", "*.docx"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*"),
            ],
        )

        if not file_path:
            return

        try:
            file_path = Path(file_path)
            content = ""

            if file_path.suffix.lower() == ".txt" or file_path.suffix.lower() == ".md":
                content = file_path.read_text(encoding="utf-8")
            elif file_path.suffix.lower() == ".docx":
                try:
                    from docx import Document

                    doc = Document(str(file_path))
                    content = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                except ImportError:
                    dialogs.showerror(
                        "错误", "需要安装 python-docx 库才能导入 Word 文档\n请运行: pip install python-docx"
                    )
                    return
            else:
                dialogs.showerror("错误", f"不支持的文件格式: {file_path.suffix}")
                return

            if not content.strip():
                dialogs.showwarning("提示", "文档内容为空")
                return

            self._imported_content = content
            self._imported_file = file_path.name

            self._show_import_preview(content, file_path.name)

        except Exception as e:
            dialogs.showerror("错误", f"导入失败: {str(e)}")

    def _show_import_preview(self, content, filename):
        """显示导入内容预览"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"导入预览 - {filename}")
        dialog.geometry("600x500")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog, text=f"已导入: {filename}", font=UIStyle.font("title"), bg=C["bg_dark"], fg=C["accent_light"]
        ).pack(pady=(15, 5))

        tk.Label(
            dialog, text=f"字数: {len(content)}", font=UIStyle.font("body"), bg=C["bg_dark"], fg=C["text_secondary"]
        ).pack(pady=(0, 10))

        preview_text = tk.Text(
            dialog, wrap=tk.WORD, font=UIStyle.font("body"), bg=C["bg_card"], fg=C["text_primary"], height=15
        )
        preview_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        preview_text.insert("1.0", content[:2000] + ("..." if len(content) > 2000 else ""))
        preview_text.config(state=tk.DISABLED)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def insert_direct():
            self.content_text.insert(tk.INSERT, content)
            dialog.destroy()
            self._log(f"已插入导入内容: {filename}")

        def ai_analyze():
            dialog.destroy()
            self._ai_analyze_content()

        tk.Button(
            btn_frame,
            text="直接插入",
            command=insert_direct,
            bg=C["accent"],
            fg="white",
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="AI分析建议",
            command=ai_analyze,
            bg=C["success"],
            fg="white",
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)

    def _ai_analyze_content(self):
        """AI分析导入的内容并给出建议"""
        if not hasattr(self, "_imported_content") or not self._imported_content:
            dialogs.showwarning("提示", "请先导入文档（创作流程 → 导入文档）")
            return

        if not self._check_ready():
            return

        content = self._imported_content
        filename = self._imported_file

        def run():
            try:
                self._log(f"正在AI分析导入内容: {filename}...")

                meta = self._get_meta()
                outline = self.outline if self.outline else []

                system = """你是专业小说顾问。分析导入的文档内容，给出详细的创作建议。

分析维度：
1. 内容摘要（200字以内）
2. 写作风格分析
3. 优点与亮点
4. 需要改进的地方
5. 与当前小说的关联建议
6. 下一步创作建议（具体可执行的3-5条建议）

输出格式要求：
- 使用清晰的标题和分段
- 建议要具体可执行
- 语言要专业但易懂"""

                context = f"当前小说：《{meta.get('title', '未命名')}》\n类型：{meta.get('genre', '未知')}\n"
                if outline:
                    context += f"大纲章节数：{len(outline)}\n"

                prompt = f"""{context}

导入的文档内容（文件名：{filename}）：
---
{content[:3000]}
---

请分析以上内容并给出创作建议。"""

                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)

                self.root.after(0, lambda: self._display_analysis_result(result, filename))
                self._log("AI分析完成")

            except Exception as e:
                self._log(f"AI分析失败: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _display_analysis_result(self, analysis, filename):
        """显示AI分析结果"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"AI分析报告 - {filename}")
        dialog.geometry("700x600")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="AI分析报告", font=UIStyle.font("heading"), bg=C["bg_dark"], fg=C["accent_light"]).pack(
            pady=(15, 10)
        )

        result_text = tk.Text(
            dialog, wrap=tk.WORD, font=UIStyle.font("subtitle"), bg=C["bg_card"], fg=C["text_primary"], padx=20, pady=15
        )
        result_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        result_text.insert("1.0", analysis)

        scrollbar = tk.Scrollbar(result_text, command=result_text.yview)
        result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def insert_content():
            if hasattr(self, "_imported_content"):
                self.content_text.insert(tk.INSERT, self._imported_content)
                dialog.destroy()
                self._log("已插入导入内容")

        def use_as_reference():
            if self.note_manager:
                self.note_manager.add_project_note("AI分析参考", analysis)
                self._log("分析结果已保存到笔记")
            dialog.destroy()

        tk.Button(
            btn_frame,
            text="插入原文",
            command=insert_content,
            bg=C["accent"],
            fg="white",
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="保存为参考",
            command=use_as_reference,
            bg=C["success"],
            fg="white",
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="关闭",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=UIStyle.font("body"),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)
