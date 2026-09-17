"""阅读器层：书库/导入/阅读/字体主题/书签/书内搜索

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from app import UIStyle, dialogs


class ReaderUIMixin:
    """阅读器层：书库/导入/阅读/字体主题/书签/书内搜索"""

    def _build_reader_ui(self, parent):
        """构建阅读管理器界面"""
        C = UIStyle.COLORS

        # 工具栏
        toolbar = tk.Frame(parent, bg=C["bg_medium"])
        toolbar.pack(fill=tk.X, padx=15, pady=(15, 5))

        tk.Button(
            toolbar,
            text="导入书籍",
            font=UIStyle.font("label"),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=10,
            command=self._import_book,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            toolbar,
            text="刷新书库",
            font=UIStyle.font("label"),
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=10,
            command=self._refresh_library,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            toolbar,
            text="搜索",
            font=UIStyle.font("label"),
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=10,
            command=self._search_in_book,
        ).pack(side=tk.LEFT, padx=5)

        # 搜索框
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(
            toolbar,
            textvariable=self.search_var,
            font=UIStyle.font("label"),
            width=20,
            bg=C["bg_medium"],
            fg=C["text_primary"],
        )
        search_entry.pack(side=tk.LEFT, padx=5)

        # 书库列表和阅读区域
        main_frame = tk.Frame(parent, bg=C["bg_dark"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        # 左侧书库列表
        left_frame = tk.Frame(main_frame, bg=C["bg_dark"], width=250)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        tk.Label(
            left_frame, text="书库", font=UIStyle.font("subtitle_bold"), bg=C["bg_dark"], fg=C["accent_light"]
        ).pack(anchor=tk.W, pady=(0, 10))

        # 书库列表框
        list_frame = tk.Frame(left_frame, bg=C["bg_dark"])
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.library_list = tk.Listbox(
            list_frame,
            bg=C["bg_card"],
            fg=C["text_secondary"],
            font=UIStyle.font("label"),
            selectbackground=C["accent"],
            relief=tk.FLAT,
            highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.library_list.yview)
        self.library_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.library_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.library_list.bind("<<ListboxSelect>>", self._on_book_select)

        # 书签列表
        bookmark_frame = tk.Frame(left_frame, bg=C["bg_dark"])
        bookmark_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Label(
            bookmark_frame, text="书签", font=UIStyle.font("body_bold"), bg=C["bg_dark"], fg=C["accent_light"]
        ).pack(anchor=tk.W, pady=(0, 5))

        self.bookmark_list = tk.Listbox(
            bookmark_frame,
            bg=C["bg_card"],
            fg=C["text_secondary"],
            font=UIStyle.font("caption"),
            height=4,
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.bookmark_list.pack(fill=tk.X)
        self.bookmark_list.bind("<<ListboxSelect>>", self._on_bookmark_select)

        # 书签操作按钮
        bookmark_btn_frame = tk.Frame(bookmark_frame, bg=C["bg_dark"])
        bookmark_btn_frame.pack(fill=tk.X, pady=(5, 0))
        tk.Button(
            bookmark_btn_frame,
            text="导入书签",
            font=UIStyle.font("caption"),
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=5,
            command=self._import_bookmarks,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            bookmark_btn_frame,
            text="导出书签",
            font=UIStyle.font("caption"),
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=5,
            command=self._export_bookmarks,
        ).pack(side=tk.LEFT, padx=2)

        # 右侧阅读区域
        right_frame = tk.Frame(main_frame, bg=C["bg_dark"])
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 阅读工具栏
        read_toolbar = tk.Frame(right_frame, bg=C["bg_medium"])
        read_toolbar.pack(fill=tk.X, pady=(0, 10))

        # 字体大小
        tk.Label(
            read_toolbar, text="字体:", font=UIStyle.font("label"), bg=C["bg_medium"], fg=C["text_secondary"]
        ).pack(side=tk.LEFT, padx=5)
        self.font_size_var = tk.StringVar(value="16")
        font_size_spin = tk.Spinbox(
            read_toolbar, from_=10, to=36, width=5, textvariable=self.font_size_var, command=self._update_reader_font
        )
        font_size_spin.pack(side=tk.LEFT, padx=5)

        # 主题选择
        tk.Label(
            read_toolbar, text="主题:", font=UIStyle.font("label"), bg=C["bg_medium"], fg=C["text_secondary"]
        ).pack(side=tk.LEFT, padx=5)
        self.reader_theme_var = tk.StringVar(value="light")
        themes = [("浅色", "light"), ("深色", "dark"), ("护眼", "sepia")]
        for text, value in themes:
            tk.Radiobutton(
                read_toolbar,
                text=text,
                variable=self.reader_theme_var,
                value=value,
                font=UIStyle.font("caption"),
                bg=C["bg_medium"],
                fg=C["text_secondary"],
                selectcolor=C["accent"],
                command=self._change_reader_theme,
            ).pack(side=tk.LEFT, padx=2)

        # 添加书签按钮
        tk.Button(
            read_toolbar,
            text="添加书签",
            font=UIStyle.font("label"),
            bg=C["success"],
            fg="white",
            relief=tk.FLAT,
            padx=10,
            command=self._add_bookmark,
        ).pack(side=tk.RIGHT, padx=5)

        # 阅读内容区域
        self.reader_text = tk.Text(
            right_frame,
            wrap=tk.WORD,
            font=UIStyle.font("display"),
            bg="#f5f0e8",
            fg="#2c2c2c",
            padx=20,
            pady=20,
            spacing1=3,
            spacing3=3,
            relief=tk.FLAT,
            state=tk.DISABLED,
        )

        reader_scrollbar = tk.Scrollbar(right_frame, command=self.reader_text.yview)
        self.reader_text.configure(yscrollcommand=reader_scrollbar.set)
        reader_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.reader_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 当前书籍信息
        self.current_book_path = None
        self.current_book_content = None

        # 初始化书库
        self._refresh_library()
        self._refresh_bookmarks()

    def _import_book(self):
        """导入书籍"""
        file_path = filedialog.askopenfilename(
            title="选择书籍文件",
            filetypes=[
                ("所有支持格式", "*.txt *.epub *.pdf *.docx *.md"),
                ("TXT文件", "*.txt"),
                ("EPUB文件", "*.epub"),
                ("PDF文件", "*.pdf"),
                ("Word文档", "*.docx"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*"),
            ],
        )

        if file_path:
            meta = self.reading_manager.import_book(file_path)
            if meta:
                self._log(f"已导入书籍: {meta['title']}")
                self._refresh_library()
                dialogs.showinfo("成功", f"已导入《{meta['title']}》")
            else:
                dialogs.showerror("错误", "导入失败，不支持该文件格式")

    def _refresh_library(self):
        """刷新书库列表"""
        self.library_list.delete(0, tk.END)
        books = self.reading_manager.get_library_books()
        for book in books:
            self.library_list.insert(tk.END, f"{book['title']} ({book['format']})")

    def _refresh_bookmarks(self):
        """刷新书签列表"""
        self.bookmark_list.delete(0, tk.END)
        bookmarks = self.reading_manager.get_bookmarks()
        for bm in bookmarks:
            self.bookmark_list.insert(tk.END, f"{bm['title']} - {bm.get('position', 0)}%")

    def _on_book_select(self, event):
        """书籍选中事件"""
        selection = self.library_list.curselection()
        if not selection:
            return

        books = self.reading_manager.get_library_books()
        idx = selection[0]
        if idx < len(books):
            book = books[idx]
            self._load_book(book["file_path"])

    def _on_bookmark_select(self, event):
        """书签选中事件"""
        selection = self.bookmark_list.curselection()
        if not selection:
            return

        bookmarks = self.reading_manager.get_bookmarks()
        idx = selection[0]
        if idx < len(bookmarks):
            bookmark = bookmarks[idx]
            # 加载对应的书籍并跳转到位置
            if bookmark.get("file_path"):
                self._load_book(bookmark["file_path"], bookmark.get("position", 0))

    def _load_book(self, file_path: str, position: int = 0):
        """加载书籍内容"""
        content = self.reading_manager.read_book(file_path)
        if content:
            self.current_book_path = file_path
            self.current_book_content = content

            # 显示内容
            self.reader_text.config(state=tk.NORMAL)
            self.reader_text.delete("1.0", tk.END)
            self.reader_text.insert("1.0", content)
            self.reader_text.config(state=tk.DISABLED)

            # 跳转到指定位置
            if position > 0:
                # 计算字符位置
                char_pos = int(len(content) * position / 100)
                self.reader_text.see(f"1.0+{char_pos}c")

            self._log(f"已加载书籍: {Path(file_path).name}")
        else:
            dialogs.showerror("错误", "无法读取书籍内容")

    def _update_reader_font(self):
        """更新阅读字体大小"""
        try:
            size = int(self.font_size_var.get())
            self.reader_text.configure(font=("微软雅黑", size))
        except ValueError:
            pass

    def _change_reader_theme(self):
        """改变阅读主题"""
        theme = self.reader_theme_var.get()
        themes = {
            "light": {"bg": "#f5f0e8", "fg": "#2c2c2c"},
            "dark": {"bg": "#1e1e2e", "fg": "#f8fafc"},
            "sepia": {"bg": "#f4f0e8", "fg": "#5c4b37"},
        }

        if theme in themes:
            self.reader_text.configure(bg=themes[theme]["bg"], fg=themes[theme]["fg"])

    def _add_bookmark(self):
        """添加书签"""
        if not self.current_book_path:
            dialogs.showinfo("提示", "请先打开一本书")
            return

        # 获取当前位置（百分比）
        # 简单估算：基于滚动位置
        try:
            first_visible = self.reader_text.index("@0,0")
            # 解析行号
            line_num = int(first_visible.split(".")[0])
            total_lines = int(self.reader_text.index(tk.END).split(".")[0])
            position = int(line_num / total_lines * 100) if total_lines > 0 else 0
        except (tk.TclError, ValueError, ZeroDivisionError):
            position = 0

        title = f"书签 - {Path(self.current_book_path).stem} - {position}%"
        self.reading_manager.add_bookmark(self.current_book_path, position, title)
        self._refresh_bookmarks()
        self._log(f"已添加书签: {title}")

    def _import_bookmarks(self):
        """导入书签"""
        file_path = filedialog.askopenfilename(
            title="导入书签", filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                bookmarks = json.load(f)

            if isinstance(bookmarks, list):
                for bm in bookmarks:
                    if "book_path" in bm and "position" in bm:
                        self.reading_manager.add_bookmark(
                            bm["book_path"], bm["position"], bm.get("title", "导入的书签")
                        )
                self._refresh_bookmarks()
                self._log(f"已导入 {len(bookmarks)} 个书签")
                dialogs.showinfo("成功", f"已导入 {len(bookmarks)} 个书签")
            else:
                dialogs.showerror("错误", "无效的书签文件格式")
        except Exception as e:
            dialogs.showerror("错误", f"导入失败: {str(e)}")

    def _export_bookmarks(self):
        """导出书签"""
        bm_list = self.reading_manager.get_bookmarks()
        if not bm_list:
            dialogs.showinfo("提示", "没有可导出的书签")
            return

        file_path = filedialog.asksaveasfilename(
            title="导出书签", defaultextension=".json", filetypes=[("JSON文件", "*.json")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(bm_list, f, indent=2, ensure_ascii=False)
            self._log(f"已导出 {len(bm_list)} 个书签")
            dialogs.showinfo("成功", f"已导出 {len(bm_list)} 个书签")
        except Exception as e:
            dialogs.showerror("错误", f"导出失败: {str(e)}")

    def _search_in_book(self):
        """在当前书籍中搜索"""
        if not self.current_book_path:
            dialogs.showinfo("提示", "请先打开一本书")
            return

        keyword = self.search_var.get().strip()
        if not keyword:
            dialogs.showinfo("提示", "请输入搜索关键词")
            return

        results = self.reading_manager.search_in_book(self.current_book_path, keyword)
        if results:
            # 高亮显示搜索结果
            self.reader_text.tag_remove("search_highlight", "1.0", tk.END)
            self.reader_text.tag_configure("search_highlight", background="#ffff00", foreground="#000000")

            for result in results[:10]:  # 最多显示10个结果
                line_num = result["line_number"]
                # 高亮该行中的关键词
                start = f"{line_num}.0"
                end = f"{line_num}.end"
                self.reader_text.tag_add("search_highlight", start, end)

            # 跳转到第一个结果
            self.reader_text.see(f"{results[0]['line_number']}.0")
            self._log(f"找到 {len(results)} 个匹配结果")
        else:
            dialogs.showinfo("搜索", "未找到匹配内容")
