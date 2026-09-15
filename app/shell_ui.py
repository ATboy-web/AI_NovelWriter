"""应用外壳层：主窗口构建 / 运行循环 / 日志 / 状态栏 / 帮助关于

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from loguru import logger

from app import UIStyle, __version__


class ShellMixin:
    """应用外壳层：主窗口构建 / 运行循环 / 日志 / 状态栏 / 帮助关于"""


    def _create_widgets(self):
        """创建主界面 - 深色主题美化版"""
        C = UIStyle.COLORS

        # ===== 顶部标题栏 =====
        header = tk.Frame(self.root, bg=C['accent'], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        # Logo和标题
        title_frame = tk.Frame(header, bg=C['accent'])
        title_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)

        tk.Label(title_frame, text="AI", font=('Arial', 18, 'bold'),
                bg=C['accent'], fg='white').pack(side=tk.LEFT)
        tk.Label(title_frame, text=" 小说创作工坊", font=('微软雅黑', 14),
                bg=C['accent'], fg='white').pack(side=tk.LEFT, padx=(5, 0))

        # 顶部按钮
        btn_frame = tk.Frame(header, bg=C['accent'])
        btn_frame.pack(side=tk.RIGHT, padx=20, fill=tk.Y)

        for text, cmd in [("新建", self._new_novel), ("打开", self._open_novel),
                         ("导出", self._export_txt), ("格式转换", self._show_format_converter),
                         ("插入图片", self._insert_image), ("云端同步", self._cloud_sync),
                         ("设置", self._show_settings)]:
            tk.Button(btn_frame, text=text, font=('微软雅黑', 10),
                     bg=C['accent_hover'], fg='white', relief=tk.FLAT,
                     padx=15, pady=5, cursor='hand2',
                     activebackground=C['accent_light'],
                     command=cmd).pack(side=tk.LEFT, padx=3)

        # 状态指示
        self.status_indicator = tk.Label(btn_frame, text="未配置",
                                        font=('微软雅黑', 9), bg=C['accent'], fg='#ffd700')
        self.status_indicator.pack(side=tk.RIGHT, padx=10)

        # ===== 主内容区 - 三栏布局 =====
        main_container = tk.Frame(self.root, bg=C['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # 快速操作工具栏 (顶部)
        toolbar = tk.Frame(main_container, bg=C['bg_medium'], height=48)
        toolbar.pack(fill=tk.X, padx=0, pady=0)
        toolbar.pack_propagate(False)

        # 工具栏左侧 - 标题
        tk.Label(toolbar, text="AI小说创作工坊", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(side=tk.LEFT, padx=15)

        # 工具栏中间 - 快速操作按钮
        quick_btn_frame = tk.Frame(toolbar, bg=C['bg_medium'])
        quick_btn_frame.pack(side=tk.LEFT, padx=20)

        for text, cmd, color in [
            ("新建小说", lambda: self._new_novel(), C['accent']),
            ("打开小说", lambda: self._open_novel(), C['bg_light']),
            ("续写新章", lambda: self._continue_novel(), C['success']),
        ]:
            btn = tk.Button(quick_btn_frame, text=text, font=('微软雅黑', 9),
                          bg=color, fg='white' if color == C['accent'] else C['text_primary'],
                          relief=tk.FLAT, padx=12, pady=4, cursor='hand2',
                          activebackground=C['accent_hover'],
                          command=cmd)
            btn.pack(side=tk.LEFT, padx=3)

        # 工具栏右侧 - 状态信息
        status_frame = tk.Frame(toolbar, bg=C['bg_medium'])
        status_frame.pack(side=tk.RIGHT, padx=15)

        self.ai_status_label = tk.Label(status_frame, text="未连接AI", font=('微软雅黑', 9),
                                        bg=C['bg_medium'], fg=C['warning'])
        self.ai_status_label.pack(side=tk.RIGHT, padx=10)

        # 左侧面板 - 可滚动 (280px)
        left_container = tk.Frame(main_container, bg=C['bg_dark'], width=280)
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, padx=0, pady=0)
        left_container.pack_propagate(False)

        # 左侧滚动画布
        left_canvas = tk.Canvas(left_container, bg=C['bg_medium'], highlightthickness=0, bd=0, width=280)
        left_scrollbar = tk.Scrollbar(left_container, orient=tk.VERTICAL, command=left_canvas.yview)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        left_panel = tk.Frame(left_canvas, bg=C['bg_medium'])
        left_canvas.create_window((0, 0), window=left_panel, anchor=tk.NW)

        def on_left_canvas_configure(event):
            left_canvas.itemconfig(1, width=event.width)
        left_canvas.bind("<Configure>", on_left_canvas_configure)

        # 鼠标滚轮绑定
        def on_left_scroll(event):
            left_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        left_canvas.bind("<MouseWheel>", on_left_scroll)
        left_panel.bind("<MouseWheel>", on_left_scroll)
        left_scrollbar.bind("<MouseWheel>", on_left_scroll)

        # 左侧 - 小说信息卡片
        info_card = tk.Frame(left_panel, bg=C['bg_card'], padx=15, pady=15)
        info_card.pack(fill=tk.X, padx=10, pady=10)

        self.title_var = tk.StringVar(value="未创建小说")
        tk.Label(info_card, textvariable=self.title_var, font=('微软雅黑', 12, 'bold'),
                bg=C['bg_card'], fg=C['text_primary']).pack(anchor=tk.W)

        info_grid = tk.Frame(info_card, bg=C['bg_card'])
        info_grid.pack(fill=tk.X, pady=(10, 0))

        self.genre_var = tk.StringVar(value="-")
        self.chapter_var = tk.StringVar(value="0/0")
        self.word_count_var = tk.StringVar(value="0")

        for i, (label, var) in enumerate([("类型", self.genre_var), ("进度", self.chapter_var), ("字数", self.word_count_var)]):
            tk.Label(info_grid, text=label, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_muted']).grid(row=i, column=0, sticky=tk.W, pady=2)
            tk.Label(info_grid, textvariable=var, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_secondary']).grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)

        # 左侧 - 模式切换
        mode_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        mode_frame.pack(fill=tk.X, padx=10)

        tk.Label(mode_frame, text="创作模式", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))

        # 自动创作 + 停止 同一行
        btn_row = tk.Frame(mode_frame, bg=C['bg_medium'])
        btn_row.pack(fill=tk.X, pady=2)

        self.auto_btn = tk.Button(btn_row, text="自动创作", font=('微软雅黑', 10),
                                 bg=C['accent'], fg='white', relief=tk.FLAT,
                                 padx=10, pady=6, cursor='hand2',
                                 activebackground=C['accent_hover'],
                                 command=self._auto_generate)
        self.auto_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.stop_btn = tk.Button(btn_row, text="停止", font=('微软雅黑', 10),
                                 bg=C['error'], fg='white', relief=tk.FLAT,
                                 padx=10, pady=6, cursor='hand2',
                                 activebackground='#dc2626',
                                 command=self._stop_generate)
        self.stop_btn.pack(side=tk.RIGHT)

        # AI辅助写作按钮
        self.assist_btn = tk.Button(mode_frame, text="AI辅助写作 (F11)", font=('微软雅黑', 10),
                                   bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT,
                                   padx=10, pady=6, cursor='hand2',
                                   activebackground=C['hover'],
                                   command=self._open_fullscreen_writer)
        self.assist_btn.pack(fill=tk.X, pady=2)

        # 续写按钮
        self.continue_btn = tk.Button(mode_frame, text="续写新章", font=('微软雅黑', 10),
                                     bg=C['success'], fg='white', relief=tk.FLAT,
                                     padx=10, pady=6, cursor='hand2',
                                     activebackground='#059669',
                                     command=self._continue_novel)
        self.continue_btn.pack(fill=tk.X, pady=2)

        # 重新创作按钮
        regen_row = tk.Frame(mode_frame, bg=C['bg_medium'])
        regen_row.pack(fill=tk.X, pady=2)

        self.regen_chapter_btn = tk.Button(regen_row, text="重新创作本章", font=('微软雅黑', 9),
                                          bg=C['warning'], fg='white', relief=tk.FLAT,
                                          padx=8, pady=4, cursor='hand2',
                                          activebackground='#d97706',
                                          command=self._regen_current_chapter)
        self.regen_chapter_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.regen_all_btn = tk.Button(regen_row, text="全部重新创作", font=('微软雅黑', 9),
                                      bg=C['error'], fg='white', relief=tk.FLAT,
                                      padx=8, pady=4, cursor='hand2',
                                      activebackground='#dc2626',
                                      command=self._regen_all_chapters)
        self.regen_all_btn.pack(side=tk.RIGHT)

        # 章节回顾按钮
        self.review_btn = tk.Button(mode_frame, text="章节回顾 (F12)", font=('微软雅黑', 10),
                                   bg=C['info'] if 'info' in C else '#3b82f6', fg='white', relief=tk.FLAT,
                                   padx=10, pady=6, cursor='hand2',
                                   command=self._chapter_review)
        self.review_btn.pack(fill=tk.X, pady=2)

        self.cover_btn = tk.Button(mode_frame, text="生成封面", font=('微软雅黑', 10),
                                   bg=C['accent'], fg='white', relief=tk.FLAT,
                                   padx=10, pady=6, cursor='hand2',
                                   command=self._generate_cover)
        self.cover_btn.pack(fill=tk.X, pady=2)

        self.timeline_btn = tk.Button(mode_frame, text="世界线/时间线", font=('微软雅黑', 10),
                                   bg=C['warning'], fg='white', relief=tk.FLAT,
                                   padx=10, pady=6, cursor='hand2',
                                   command=self._open_timeline)
        self.timeline_btn.pack(fill=tk.X, pady=2)

        self.extend_btn = tk.Button(mode_frame, text="续写小说", font=('微软雅黑', 10),
                                   bg=C['success'], fg='white', relief=tk.FLAT,
                                   padx=10, pady=6, cursor='hand2',
                                   command=self._extend_novel)
        self.extend_btn.pack(fill=tk.X, pady=2)

        # 左侧 - 智能体步骤
        agent_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        agent_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        tk.Label(agent_frame, text="创作流程", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))

        # 基础步骤
        basic_label = tk.Label(agent_frame, text="基础设置", font=('微软雅黑', 8),
                              bg=C['bg_medium'], fg=C['text_muted'])
        basic_label.pack(anchor=tk.W, pady=(0, 2))

        basic_steps = [
            ("1. 世界观设定", self._gen_settings),
            ("2. 角色创建", self._gen_characters),
            ("3. 故事大纲", self._gen_outline),
        ]

        for text, cmd in basic_steps:
            btn = tk.Button(agent_frame, text=text, font=('微软雅黑', 9),
                          bg=C['bg_light'], fg=C['text_secondary'], relief=tk.FLAT,
                          padx=8, pady=4, cursor='hand2', anchor=tk.W,
                          activebackground=C['hover'],
                          command=cmd)
            btn.pack(fill=tk.X, pady=1)

        # 创作步骤
        write_label = tk.Label(agent_frame, text="章节创作", font=('微软雅黑', 8),
                              bg=C['bg_medium'], fg=C['text_muted'])
        write_label.pack(anchor=tk.W, pady=(8, 2))

        write_steps = [
            ("4. 生成初稿", self._gen_chapter),
            ("5. AI审校", self._review_chapter),
            ("6. 风格优化", self._style_optimize),
            ("7. 保存章节", self._save_chapter),
        ]

        for text, cmd in write_steps:
            btn = tk.Button(agent_frame, text=text, font=('微软雅黑', 9),
                          bg=C['bg_light'], fg=C['text_secondary'], relief=tk.FLAT,
                          padx=8, pady=4, cursor='hand2', anchor=tk.W,
                          activebackground=C['hover'],
                          command=cmd)
            btn.pack(fill=tk.X, pady=1)

        # 导入与分析
        import_label = tk.Label(agent_frame, text="导入分析", font=('微软雅黑', 8),
                               bg=C['bg_medium'], fg=C['text_muted'])
        import_label.pack(anchor=tk.W, pady=(8, 2))

        import_steps = [
            ("导入文档", self._import_document),
            ("AI分析建议", self._ai_analyze_content),
        ]

        for text, cmd in import_steps:
            btn = tk.Button(agent_frame, text=text, font=('微软雅黑', 9),
                          bg=C['accent_bg'], fg=C['accent_light'], relief=tk.FLAT,
                          padx=8, pady=4, cursor='hand2', anchor=tk.W,
                          activebackground=C['hover'],
                          command=cmd)
            btn.pack(fill=tk.X, pady=1)

        # 左侧 - 大纲列表
        outline_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        outline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))

        # 大纲类型选择
        outline_header = tk.Frame(outline_frame, bg=C['bg_medium'])
        outline_header.pack(fill=tk.X, pady=(0, 5))

        tk.Label(outline_header, text="大纲", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(side=tk.LEFT)

        # 大纲类型下拉框
        self.outline_type_var = tk.StringVar(value="章节大纲")
        outline_type_combo = ttk.Combobox(outline_header, textvariable=self.outline_type_var,
                                         values=["整体大纲", "章节大纲", "故事大纲"],
                                         state="readonly", width=10, font=('微软雅黑', 8))
        outline_type_combo.pack(side=tk.RIGHT)
        outline_type_combo.bind('<<ComboboxSelected>>', self._on_outline_type_change)

        # 大纲操作按钮
        outline_btn_frame = tk.Frame(outline_frame, bg=C['bg_medium'])
        outline_btn_frame.pack(fill=tk.X, pady=2)

        tk.Button(outline_btn_frame, text="生成", font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=4,
                 command=self._gen_outline).pack(side=tk.LEFT, padx=1)
        tk.Button(outline_btn_frame, text="添加", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=4,
                 command=self._add_outline_item).pack(side=tk.LEFT, padx=1)
        tk.Button(outline_btn_frame, text="编辑", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=4,
                 command=self._edit_outline_item).pack(side=tk.LEFT, padx=1)
        tk.Button(outline_btn_frame, text="删除", font=('微软雅黑', 8),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=4,
                 command=self._delete_outline_item).pack(side=tk.RIGHT, padx=1)

        # 大纲列表框
        list_frame = tk.Frame(outline_frame, bg=C['bg_dark'])
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.outline_list = tk.Listbox(list_frame, bg=C['bg_dark'], fg=C['text_secondary'],
                                      font=('微软雅黑', 9), selectbackground=C['accent'],
                                      selectforeground='white', relief=tk.FLAT,
                                      highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(list_frame, command=self.outline_list.yview)
        self.outline_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.outline_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.outline_list.bind('<<ListboxSelect>>', self._on_outline_select)

        # 左侧 - 角色卡片 (新增)
        char_cards_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        char_cards_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Label(char_cards_frame, text="角色", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))

        # 角色卡片容器
        self.char_cards_container = tk.Frame(char_cards_frame, bg=C['bg_medium'])
        self.char_cards_container.pack(fill=tk.X)

        # 角色操作按钮
        char_btn_frame = tk.Frame(char_cards_frame, bg=C['bg_medium'])
        char_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(char_btn_frame, text="新建", font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=6,
                 command=self._create_character_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="AI生成", font=('微软雅黑', 8),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=6,
                 command=self._ai_create_character).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="传记", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=6,
                 command=self._gen_char_biography).pack(side=tk.LEFT, padx=1)
        # 「详情」入口：此前 _show_char_detail（含重命名 / 休息恢复 / 故事线）
        # 是全仓零调用的孤儿对话框，这 3 项能力用户根本点不到。
        tk.Button(char_btn_frame, text="详情", font=('微软雅黑', 8),
                 bg=C['accent_light'], fg=C['text_primary'], relief=tk.FLAT, padx=6,
                 command=self._show_char_detail).pack(side=tk.LEFT, padx=1)

        # ===== 右侧主内容区 =====
        right_panel = tk.Frame(main_container, bg=C['bg_dark'])
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 右侧 - 标签页
        self.notebook = ttk.Notebook(right_panel, style='Dark.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === 章节内容页 ===
        chapter_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(chapter_frame, text=" 章节内容 ")

        # 章节标题和导航
        title_bar = tk.Frame(chapter_frame, bg=C['bg_dark'])
        title_bar.pack(fill=tk.X, padx=15, pady=(10, 5))

        self.chapter_title_var = tk.StringVar(value="选择或生成章节")
        tk.Label(title_bar, textvariable=self.chapter_title_var,
                font=('微软雅黑', 13, 'bold'), bg=C['bg_dark'], fg=C['text_primary']).pack(side=tk.LEFT)

        # 章节导航按钮
        nav_frame = tk.Frame(title_bar, bg=C['bg_dark'])
        nav_frame.pack(side=tk.RIGHT)

        self.prev_chapter_btn = tk.Button(nav_frame, text="◀ 上一章", font=('微软雅黑', 9),
                                         bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT,
                                         padx=8, pady=2, cursor='hand2',
                                         command=self._prev_chapter)
        self.prev_chapter_btn.pack(side=tk.LEFT, padx=2)

        self.chapter_select_var = tk.StringVar(value="")
        self.chapter_select = ttk.Combobox(nav_frame, textvariable=self.chapter_select_var,
                                          state="readonly", width=12, font=('微软雅黑', 9))
        self.chapter_select.pack(side=tk.LEFT, padx=2)
        self.chapter_select.bind('<<ComboboxSelected>>', self._on_chapter_select)

        self.next_chapter_btn = tk.Button(nav_frame, text="下一章 ▶", font=('微软雅黑', 9),
                                         bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT,
                                         padx=8, pady=2, cursor='hand2',
                                         command=self._next_chapter)
        self.next_chapter_btn.pack(side=tk.LEFT, padx=2)

        self.save_chapter_btn = tk.Button(nav_frame, text="💾 保存", font=('微软雅黑', 9),
                                          bg=C['accent'], fg='white', relief=tk.FLAT,
                                          padx=8, pady=2, cursor='hand2',
                                          command=self._save_chapter)
        self.save_chapter_btn.pack(side=tk.LEFT, padx=2)

        # 写作区域
        text_frame = tk.Frame(chapter_frame, bg=C['bg_dark'])
        text_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        self.content_text = tk.Text(text_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   insertbackground=C['accent_light'],
                                   selectbackground=C['accent'],
                                   relief=tk.FLAT, padx=15, pady=15,
                                   spacing1=3, spacing3=3, undo=True)

        content_scrollbar = tk.Scrollbar(text_frame, command=self.content_text.yview)
        self.content_text.configure(yscrollcommand=content_scrollbar.set)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 绑定文本变化事件
        self.content_text.bind('<KeyRelease>', self._on_text_change)
        self.content_text.bind('<Button-3>', self._show_editor_context_menu)

        # === 日志页 ===
        log_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(log_frame, text=" 运行日志 & 角色 ")

        # 左侧 - 角色面板（在日志左边）
        char_frame = tk.Frame(log_frame, bg=C['bg_medium'], width=240)
        char_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(10, 5), pady=10)
        char_frame.pack_propagate(False)

        tk.Label(char_frame, text="角色面板", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(5, 5), padx=5)

        # 角色选择下拉框
        char_select_frame = tk.Frame(char_frame, bg=C['bg_medium'])
        char_select_frame.pack(fill=tk.X, padx=5, pady=2)
        self.char_select_var = tk.StringVar(value="无角色")
        self.char_select_combo = ttk.Combobox(char_select_frame, textvariable=self.char_select_var,
                                              state="readonly", width=16)
        self.char_select_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.char_select_combo.bind('<<ComboboxSelected>>', self._on_char_select)

        # 传记按钮
        tk.Button(char_select_frame, text="传", font=('微软雅黑', 8),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=5,
                 command=self._gen_char_biography).pack(side=tk.RIGHT, padx=2)

        # 角色信息滚动显示
        char_canvas = tk.Canvas(char_frame, bg=C['bg_medium'], highlightthickness=0, bd=0)
        char_scrollbar = tk.Scrollbar(char_frame, orient=tk.VERTICAL, command=char_canvas.yview)
        char_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        char_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        char_canvas.configure(yscrollcommand=char_scrollbar.set)

        self.char_detail_frame = tk.Frame(char_canvas, bg=C['bg_medium'])
        char_canvas.create_window((0, 0), window=self.char_detail_frame, anchor=tk.NW)

        def on_char_canvas_configure(event):
            char_canvas.itemconfig(1, width=event.width)
        char_canvas.bind("<Configure>", on_char_canvas_configure)
        for w in [char_canvas, self.char_detail_frame, char_scrollbar]:
            w.bind("<MouseWheel>", lambda e: char_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # 角色操作按钮
        char_btn_frame = tk.Frame(char_frame, bg=C['bg_medium'])
        char_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(char_btn_frame, text="新建", font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=5,
                 command=self._create_character_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="AI", font=('微软雅黑', 8),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=5,
                 command=self._ai_create_character).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="武器", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=5,
                 command=self._equip_weapon).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="技能", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=5,
                 command=self._learn_skill).pack(side=tk.LEFT, padx=1)

        # 右侧 - 日志
        log_toolbar = tk.Frame(log_frame, bg=C['bg_dark'])
        log_toolbar.pack(side=tk.TOP, fill=tk.X, padx=(0, 10), pady=(10, 0))
        tk.Label(log_toolbar, text="运行日志", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['text_secondary']).pack(side=tk.LEFT, padx=5)
        tk.Button(log_toolbar, text="导出日志", font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10, pady=2,
                 command=self._export_log).pack(side=tk.RIGHT, padx=2)
        tk.Button(log_toolbar, text="清空", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=8, pady=2,
                 command=self._clear_log).pack(side=tk.RIGHT, padx=2)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, font=('Consolas', 10),
                               bg=C['bg_card'], fg=C['text_muted'],
                               relief=tk.FLAT, padx=15, pady=15, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=(0, 10))

        # === 审校结果页 ===
        review_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(review_frame, text=" 审校结果 ")

        self.review_text = tk.Text(review_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                  bg=C['bg_card'], fg=C['text_primary'],
                                  relief=tk.FLAT, padx=15, pady=15)
        self.review_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # === 笔记页 ===
        notes_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(notes_frame, text=" 笔记 ")

        # 笔记类型选择
        note_type_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_type_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        self.note_type_var = tk.StringVar(value="project")
        for val, label in [("project", "工程笔记"), ("doc", "文档笔记"), ("sticky", "便笺本")]:
            tk.Radiobutton(note_type_frame, text=label, variable=self.note_type_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], activebackground=C['bg_dark'],
                          command=self._refresh_notes).pack(side=tk.LEFT, padx=10)

        tk.Button(note_type_frame, text="+ 新建", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._add_note).pack(side=tk.RIGHT)

        # 笔记列表和内容
        note_content_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        self.notes_list = tk.Listbox(note_content_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                    font=('微软雅黑', 9), selectbackground=C['accent'],
                                    relief=tk.FLAT, highlightthickness=0, width=30)
        self.notes_list.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.notes_list.bind('<<ListboxSelect>>', self._on_note_select)

        self.note_content = tk.Text(note_content_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   relief=tk.FLAT, padx=15, pady=15)
        self.note_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 笔记操作按钮
        note_btn_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 15))

        tk.Button(note_btn_frame, text="保存笔记", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._save_note).pack(side=tk.LEFT, padx=5)
        tk.Button(note_btn_frame, text="删除笔记", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._delete_note).pack(side=tk.LEFT, padx=5)
        tk.Button(note_btn_frame, text="发送到工程", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._send_sticky_to_project).pack(side=tk.RIGHT, padx=5)

        # === 创作工具页 ===
        toolkit_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(toolkit_frame, text=" 创作工具 ")

        # 工具选择
        tool_select_frame = tk.Frame(toolkit_frame, bg=C['bg_dark'])
        tool_select_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        self.tool_type_var = tk.StringVar(value="elements")
        tools = [("elements", "元素库"), ("bridges", "桥段库"), ("descriptions", "描写库"),
                 ("dialogue", "对话推演"), ("story_flow", "故事流"), ("style", "风格转换"),
                 ("adapt", "智能改编"), ("websearch", "热点改编"), ("chapters", "章节分析"),
                 ("memory_viz", "记忆可视化"), ("summary_mgmt", "摘要管理"), ("batch_ops", "批量操作")]

        for val, label in tools:
            tk.Radiobutton(tool_select_frame, text=label, variable=self.tool_type_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], activebackground=C['bg_dark'],
                          command=self._refresh_toolkit).pack(side=tk.LEFT, padx=8)

        # 工具内容区
        self.tool_content_frame = tk.Frame(toolkit_frame, bg=C['bg_dark'])
        self.tool_content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        # 初始化工具集界面
        self._refresh_toolkit()

        # 更新左侧面板滚动区域
        left_panel.update_idletasks()
        left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        # === 阅读管理器页 ===
        reader_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(reader_frame, text=" 阅读管理器 ")

        # 阅读管理器内容
        self._build_reader_ui(reader_frame)

        # === 写作技能页 ===
        writing_skills_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(writing_skills_frame, text=" 写作技能 ")
        self._create_writing_skills_panel(writing_skills_frame)
    def _log(self, message: str):
        """添加日志（线程安全）"""
        # 使用loguru记录日志
        logger.info(message)

        # 同时更新UI日志区域
        def _do_log():
            self.log_text.config(state=tk.NORMAL)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do_log)
        except RuntimeError:
            pass
    def _export_log(self):
        """导出运行日志到桌面"""
        desktop = Path.home() / "Desktop"
        filename = f"AI_NovelWriter_日志_{time.strftime('%Y%m%d_%H%M%S')}.log"
        filepath = desktop / filename
        try:
            content = self.log_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("提示", "日志为空，无需导出")
                return
            filepath.write_text(content, encoding='utf-8')
            self._log(f"日志已导出: {filepath}")
            messagebox.showinfo("导出成功", f"日志已保存到桌面:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", f"无法导出日志:\n{e}")
    def _clear_log(self):
        """清空运行日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self._log("日志已清空")
    def _update_status(self):
        """更新状态栏"""
        if self.ai_client.is_configured():
            provider = self.config.get("api_provider", "ollama")
            model = self.config.get("model", "")
            img_status = " + 文生图" if self.image_gen.is_configured() else ""

            # Token消耗统计
            from app.ai_client import token_stats
            token_display = token_stats.get_display()

            text = f"{provider}/{model}{img_status} | {token_display}"
            self.status_indicator.config(text=text, fg='#10b981')
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.config(text=text, fg=UIStyle.COLORS.get('success', '#10b981'))
        else:
            self.status_indicator.config(text="未配置AI", fg='#ffd700')
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.config(text="未连接AI", fg='#f59e0b')
    def _check_ready(self, silent=False) -> bool:
        """检查是否就绪"""
        if not self.ai_client.is_configured():
            if not silent:
                messagebox.showwarning("提示", "请先配置AI API（设置 → AI配置）")
            return False
        if not self.current_novel_dir:
            if not silent:
                messagebox.showwarning("提示", "请先创建或打开小说")
            return False
        return True
    def _get_meta(self) -> dict:
        """获取小说元数据"""
        with open(self.current_novel_dir / "meta.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    def _show_help(self):
        """显示帮助"""
        help_text = """AI自动写小说系统 v2.0 使用说明

═══ 1. 配置AI模型 ═══
菜单 → 设置 → AI模型

支持的AI后端：
- Ollama（本地免费）: 默认 http://localhost:11434
- OpenAI: 需要API密钥
- DeepSeek: 需要API密钥
- Claude: 需要API密钥
- 自定义API: 兼容OpenAI格式

点击"检测Ollama"可自动发现本地模型。

═══ 2. 配置文生图（可选）═══
菜单 → 设置 → 文生图

支持的后端：
- ComfyUI: 默认端口 8188
- SD WebUI API: 默认端口 7860
- Disabled: 不使用文生图

勾选"自动检测名场面"后，每章生成完毕会自动
检测适合插图的场景并提醒生成图片。

═══ 3. 新建小说 ═══
点击"新建小说"，填写：
- 标题、类型、核心概念
- 目标章节数

═══ 4. 创作流程 ═══
分步模式：
  1. 生成世界观 → 创建世界设定
  2. 生成角色 → 创建角色档案
  3. 生成大纲 → 规划故事结构
  4. 生成下一章 → 逐章创作
  5. 审校当前章 → 检查质量

自动模式：
  点击"自动创作"一键完成全流程

═══ 5. 长上下文记忆 ═══
系统自动维护：
- 世界观设定
- 角色档案
- 全局故事摘要
- 最近5章摘要
- 关键词索引

确保长篇小说的连贯性。

═══ 6. 导出 ═══
点击"导出全文"生成TXT文件
"""
        dialog = tk.Toplevel(self.root)
        dialog.title("使用说明")
        dialog.geometry("500x600")
        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=("微软雅黑", 11))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", help_text)
        text.config(state=tk.DISABLED)
    def _show_about(self):
        """显示关于"""
        dialog = tk.Toplevel(self.root)
        dialog.title("关于")
        dialog.geometry("420x320")
        dialog.resizable(False, False)

        frame = tk.Frame(dialog, padx=20, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=f"AI自动写小说系统 v{__version__}", font=("微软雅黑", 14, "bold")).pack(anchor=tk.W)
        tk.Label(frame, text="功能：AI API / 长上下文记忆 / 智能体创作 / 文生图 / 名场面检测",
                font=("微软雅黑", 10), fg="#666", wraplength=380, justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 10))

        tk.Label(frame, text="开源地址：", font=("微软雅黑", 10)).pack(anchor=tk.W)
        link = tk.Label(frame, text="https://github.com/ATboy-web/AI_NovelWriter",
                       font=("微软雅黑", 10), fg="#2563eb", cursor="hand2")
        link.pack(anchor=tk.W)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/ATboy-web/AI_NovelWriter"))

        tk.Button(frame, text="关闭", command=dialog.destroy, width=10).pack(pady=(15, 0))
    def _on_close(self):
        """关闭应用"""
        if messagebox.askyesno("确认", "确定要退出吗？"):
            self.root.destroy()
    def run(self):
        """运行应用"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
