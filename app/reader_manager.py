"""
阅读管理器UI - 处理阅读相关的界面操作
从novel_app.py中提取的阅读器相关代码
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class ReaderManagerMixin:
    """阅读管理器Mixin类"""
    
    def _build_reader_ui(self: 'NovelWriterApp', parent):
        """构建阅读器界面"""
        C = self.C
        
        # 工具栏
        toolbar = tk.Frame(parent, bg=C['bg_dark'])
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(toolbar, text="📖 导入书籍", command=self._import_book,
                 bg=C['accent'], fg='white', font=('微软雅黑', 9),
                 padx=10, pady=3).pack(side=tk.LEFT, padx=3)
        
        tk.Button(toolbar, text="🔄 刷新书库", command=self._refresh_library,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 9),
                 padx=10, pady=3).pack(side=tk.LEFT, padx=3)
        
        # 搜索框
        search_frame = tk.Frame(toolbar, bg=C['bg_dark'])
        search_frame.pack(side=tk.RIGHT, padx=5)
        
        self.reader_search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.reader_search_var,
                              font=('微软雅黑', 9), bg=C['bg_medium'], fg=C['text_primary'],
                              width=15)
        search_entry.pack(side=tk.LEFT)
        
        tk.Button(search_frame, text="🔍", command=self._search_in_book,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 9),
                 padx=5).pack(side=tk.LEFT, padx=2)
        
        # 主内容区
        content_frame = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=C['bg_dark'])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧 - 书库列表
        left_frame = tk.Frame(content_frame, bg=C['bg_card'])
        content_frame.add(left_frame, width=200)
        
        tk.Label(left_frame, text="📚 书库", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_card'], fg=C['accent']).pack(anchor=tk.W, padx=10, pady=5)
        
        self.book_listbox = tk.Listbox(left_frame, bg=C['bg_medium'], fg=C['text_primary'],
                                      font=('微软雅黑', 9), selectbackground=C['accent'])
        self.book_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.book_listbox.bind('<<ListboxSelect>>', self._on_book_select)
        
        # 右侧 - 阅读区
        right_frame = tk.Frame(content_frame, bg=C['bg_card'])
        content_frame.add(right_frame, width=600)
        
        # 书签工具栏
        bookmark_toolbar = tk.Frame(right_frame, bg=C['bg_dark'])
        bookmark_toolbar.pack(fill=tk.X, padx=5, pady=3)
        
        tk.Button(bookmark_toolbar, text="🔖 添加书签", command=self._add_bookmark,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 8),
                 padx=8, pady=2).pack(side=tk.LEFT, padx=2)
        
        tk.Button(bookmark_toolbar, text="📋 导入书签", command=self._import_bookmarks,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 8),
                 padx=8, pady=2).pack(side=tk.LEFT, padx=2)
        
        tk.Button(bookmark_toolbar, text="💾 导出书签", command=self._export_bookmarks,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 8),
                 padx=8, pady=2).pack(side=tk.LEFT, padx=2)
        
        # 书签列表
        self.bookmark_listbox = tk.Listbox(bookmark_toolbar, bg=C['bg_medium'], fg=C['text_primary'],
                                          font=('微软雅黑', 8), height=2, width=20)
        self.bookmark_listbox.pack(side=tk.RIGHT, padx=5)
        self.bookmark_listbox.bind('<<ListboxSelect>>', self._on_bookmark_select)
        
        # 阅读文本区
        self.reader_text = tk.Text(right_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                  bg=C['bg_medium'], fg=C['text_primary'],
                                  padx=20, pady=15, spacing1=2, spacing2=2)
        
        reader_scrollbar = tk.Scrollbar(right_frame, command=self.reader_text.yview)
        self.reader_text.configure(yscrollcommand=reader_scrollbar.set)
        
        self.reader_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        reader_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 初始化阅读器数据
        self._current_book = None
        self._bookmarks = []
        self._reading_history = {}
    
    def _import_book(self: 'NovelWriterApp'):
        """导入书籍"""
        filetypes = [
            ("支持的格式", "*.txt *.epub *.pdf *.docx *.md"),
            ("文本文件", "*.txt"),
            ("EPUB文件", "*.epub"),
            ("PDF文件", "*.pdf"),
            ("Word文档", "*.docx"),
            ("Markdown", "*.md")
        ]
        
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if not filepath:
            return
        
        try:
            # 复制到书库
            library_dir = Path.home() / ".ai_novel_writer" / "library"
            library_dir.mkdir(parents=True, exist_ok=True)
            
            source = Path(filepath)
            dest = library_dir / source.name
            
            import shutil
            shutil.copy2(source, dest)
            
            self._refresh_library()
            self._log(f"[阅读] 导入书籍: {source.name}")
            messagebox.showinfo("成功", f"已导入: {source.name}")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))
    
    def _refresh_library(self: 'NovelWriterApp'):
        """刷新书库列表"""
        if not hasattr(self, 'book_listbox'):
            return
        
        self.book_listbox.delete(0, tk.END)
        
        library_dir = Path.home() / ".ai_novel_writer" / "library"
        if not library_dir.exists():
            return
        
        for book_file in sorted(library_dir.glob("*")):
            if book_file.suffix.lower() in ['.txt', '.epub', '.pdf', '.docx', '.md']:
                self.book_listbox.insert(tk.END, f"📖 {book_file.name}")
    
    def _refresh_bookmarks(self: 'NovelWriterApp'):
        """刷新书签列表"""
        if not hasattr(self, 'bookmark_listbox'):
            return
        
        self.bookmark_listbox.delete(0, tk.END)
        
        for bm in self._bookmarks:
            self.bookmark_listbox.insert(tk.END, f"📍 {bm['name']}")
    
    def _on_book_select(self: 'NovelWriterApp', event):
        """书籍选择事件"""
        if not hasattr(self, 'book_listbox'):
            return
        
        selection = self.book_listbox.curselection()
        if not selection:
            return
        
        book_name = self.book_listbox.get(selection[0]).lstrip('📖 ')
        library_dir = Path.home() / ".ai_novel_writer" / "library"
        book_path = library_dir / book_name
        
        if book_path.exists():
            self._load_book(str(book_path))
    
    def _on_bookmark_select(self: 'NovelWriterApp', event):
        """书签选择事件"""
        if not hasattr(self, 'bookmark_listbox') or not self._bookmarks:
            return
        
        selection = self.bookmark_listbox.curselection()
        if not selection:
            return
        
        bm = self._bookmarks[selection[0]]
        if hasattr(self, 'reader_text'):
            self.reader_text.see(f"1.0+{bm['position']}c")
    
    def _load_book(self: 'NovelWriterApp', file_path: str, position: int = 0):
        """加载书籍内容"""
        try:
            path = Path(file_path)
            content = ""
            
            if path.suffix.lower() == '.txt' or path.suffix.lower() == '.md':
                content = path.read_text(encoding='utf-8', errors='ignore')
            elif path.suffix.lower() == '.epub':
                # 简化EPUB读取
                import zipfile
                with zipfile.ZipFile(path, 'r') as z:
                    for name in z.namelist():
                        if name.endswith('.html') or name.endswith('.xhtml'):
                            html_content = z.read(name).decode('utf-8', errors='ignore')
                            # 简单HTML转文本
                            import re
                            text = re.sub(r'<[^>]+>', '', html_content)
                            content += text + "\n\n"
            elif path.suffix.lower() == '.pdf':
                content = "[PDF文件暂不支持直接阅读]"
            elif path.suffix.lower() == '.docx':
                try:
                    import docx
                    doc = docx.Document(path)
                    content = '\n\n'.join([p.text for p in doc.paragraphs])
                except ImportError:
                    content = "[需要安装python-docx库才能读取DOCX文件]"
            
            if hasattr(self, 'reader_text'):
                self.reader_text.delete("1.0", tk.END)
                self.reader_text.insert("1.0", content)
                
                # 恢复阅读位置
                if position > 0:
                    self.reader_text.see(f"1.0+{position}c")
            
            self._current_book = file_path
            self._bookmarks = []
            self._refresh_bookmarks()
            
            self._log(f"[阅读] 加载书籍: {path.name}")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
    
    def _update_reader_font(self: 'NovelWriterApp'):
        """更新阅读器字体"""
        if hasattr(self, 'reader_text'):
            # 简单的字体调整
            current_font = self.reader_text.cget("font")
            self._log(f"[阅读] 当前字体: {current_font}")
    
    def _change_reader_theme(self: 'NovelWriterApp'):
        """切换阅读主题"""
        themes = {
            "默认": {"bg": "#16213e", "fg": "#e0e0e0"},
            "护眼": {"bg": "#f5f5dc", "fg": "#333333"},
            "夜间": {"bg": "#0a0a0a", "fg": "#cccccc"},
        }
        
        # 简单的主题切换
        if hasattr(self, 'reader_text'):
            current_bg = self.reader_text.cget("background")
            if current_bg == "#16213e":
                self.reader_text.configure(background="#f5f5dc", foreground="#333333")
            elif current_bg == "#f5f5dc":
                self.reader_text.configure(background="#0a0a0a", foreground="#cccccc")
            else:
                self.reader_text.configure(background="#16213e", foreground="#e0e0e0")
    
    def _add_bookmark(self: 'NovelWriterApp'):
        """添加书签"""
        if not self._current_book:
            messagebox.showwarning("提示", "请先打开一本书")
            return
        
        if not hasattr(self, 'reader_text'):
            return
        
        # 获取当前位置
        position = self.reader_text.index(tk.INSERT)
        
        # 获取当前行内容作为书签名
        line_start = f"{position.split('.')[0]}.0"
        line_content = self.reader_text.get(line_start, f"{line_start} lineend")[:30]
        
        bookmark = {
            "name": line_content or f"书签{len(self._bookmarks) + 1}",
            "position": position,
            "book": self._current_book
        }
        
        self._bookmarks.append(bookmark)
        self._refresh_bookmarks()
        
        self._log(f"[阅读] 添加书签: {bookmark['name']}")
    
    def _import_bookmarks(self: 'NovelWriterApp'):
        """导入书签"""
        filepath = filedialog.askopenfilename(filetypes=[("JSON文件", "*.json")])
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                bookmarks = json.load(f)
            
            self._bookmarks.extend(bookmarks)
            self._refresh_bookmarks()
            
            self._log(f"[阅读] 导入了{len(bookmarks)}个书签")
            messagebox.showinfo("成功", f"导入了{len(bookmarks)}个书签")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))
    
    def _export_bookmarks(self: 'NovelWriterApp'):
        """导出书签"""
        if not self._bookmarks:
            messagebox.showwarning("提示", "没有书签可导出")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile="bookmarks.json"
        )
        if not filepath:
            return
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._bookmarks, f, indent=2, ensure_ascii=False)
            
            self._log(f"[阅读] 导出了{len(self._bookmarks)}个书签")
            messagebox.showinfo("成功", f"书签已保存到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
    
    def _search_in_book(self: 'NovelWriterApp'):
        """在书中搜索"""
        if not hasattr(self, 'reader_text') or not hasattr(self, 'reader_search_var'):
            return
        
        keyword = self.reader_search_var.get().strip()
        if not keyword:
            return
        
        # 清除之前的高亮
        self.reader_text.tag_remove("search_highlight", "1.0", tk.END)
        
        # 搜索并高亮
        count = 0
        start = "1.0"
        while True:
            pos = self.reader_text.search(keyword, start, tk.END)
            if not pos:
                break
            
            end = f"{pos}+{len(keyword)}c"
            self.reader_text.tag_add("search_highlight", pos, end)
            self.reader_text.see(pos)
            start = end
            count += 1
        
        # 设置高亮样式
        self.reader_text.tag_config("search_highlight", background="#ffa502", foreground="black")
        
        self._log(f"[阅读] 搜索'{keyword}': 找到{count}处")
