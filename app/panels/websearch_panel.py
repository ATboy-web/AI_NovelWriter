"""联网搜索热点改编面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from app.ui_style import UIStyle
from novel_toolkit import WebSearchAdaptEngine


class WebSearchPanelMixin:
    """联网搜索热点改编面板混入 - 提供热点改编相关的构建和操作方法"""

    def _build_websearch_tool(self):
        """热点改编界面"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="联网搜索热点改编 - 将网络热点改编为小说桥段", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        # 分类选择
        cat_frame = tk.Frame(f, bg=C['bg_dark'])
        cat_frame.pack(fill=tk.X, pady=3)
        
        self.ws_category_var = tk.StringVar(value="热梗改编")
        self.web_search_engine = WebSearchAdaptEngine(self.ai_client)
        cats = self.web_search_engine.get_categories()
        
        for i, cat in enumerate(cats):
            tk.Radiobutton(cat_frame, text=cat, variable=self.ws_category_var, value=cat,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], command=self._refresh_ws_list).pack(side=tk.LEFT, padx=5)
        
        # 搜索输入
        search_frame = tk.Frame(f, bg=C['bg_dark'])
        search_frame.pack(fill=tk.X, pady=5)
        self.ws_search_entry = tk.Entry(search_frame, font=('微软雅黑', 10), width=40,
                                       bg=C['input_bg'], fg=C['text_primary'])
        self.ws_search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.ws_search_entry.insert(0, "输入热点关键词或梗，AI自动改编...")
        
        tk.Button(search_frame, text="AI搜索改编", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_adapt).pack(side=tk.LEFT, padx=5)
        
        # 随机按钮
        tk.Button(f, text="随机来一个热点", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_random).pack(pady=5)
        
        # 内置热点列表
        tk.Label(f, text="内置热点（点击直接生成）：", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        items = self.web_search_engine.get_items(self.ws_category_var.get())
        list_frame = tk.Frame(f, bg=C['bg_dark'])
        list_frame.pack(fill=tk.X)
        self.ws_listbox = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                     font=('微软雅黑', 9), height=8,
                                     selectbackground=C['accent'], relief=tk.FLAT)
        for item in items:
            self.ws_listbox.insert(tk.END, f"{item.get('name','')}: {item.get('desc','')}")
        scrollbar = tk.Scrollbar(list_frame, command=self.ws_listbox.yview)
        self.ws_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ws_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ws_listbox.bind('<Double-Button-1>', self._ws_generate_from_list)
        
        # 生成按钮
        tk.Button(f, text="改编选中热点为小说桥段", font=('微软雅黑', 9, 'bold'),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_generate_from_list).pack(pady=5)
        
        # 自定义添加按钮区
        add_btn_frame = tk.Frame(f, bg=C['bg_dark'])
        add_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(add_btn_frame, text="+ 添加自定义热点", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_add_custom).pack(side=tk.LEFT, padx=5)
        tk.Button(add_btn_frame, text="删除自定义", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_delete_custom).pack(side=tk.LEFT, padx=5)
        
        # 结果展示
        self.ws_result = tk.Text(f, height=12, wrap=tk.WORD, font=('微软雅黑', 10),
                                bg=C['bg_card'], fg=C['text_primary'],
                                relief=tk.FLAT, padx=15, pady=15)
        self.ws_result.pack(fill=tk.BOTH, expand=True, pady=5)
        
        tk.Button(f, text="插入到章节", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=lambda: self._insert_to_chapter(self.ws_result)).pack(pady=5)

    def _ws_random(self):
        """随机获取一个热点改编"""
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client)
        result = self.web_search_engine.random_meme()
        self._show_tool_result(self.ws_result, result)

    def _ws_adapt(self):
        """AI搜索改编"""
        query = self.ws_search_entry.get().strip()
        if not query or query == "输入热点关键词或梗，AI自动改编...":
            messagebox.showinfo("提示", "请输入关键词")
            return
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                engine = WebSearchAdaptEngine(self.ai_client)
                result = engine.search_and_adapt(query)
                self.root.after(0, lambda: self._show_tool_result(self.ws_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _ws_generate_from_list(self, event=None):
        """从列表生成改编"""
        sel = self.ws_listbox.curselection()
        if not sel:
            return
        category = self.ws_category_var.get()
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        
        items = self.web_search_engine.get_items(category)
        idx = sel[0]
        if idx < len(items):
            item = items[idx]
            template = item.get("adapt", item.get("template", ""))
            result = self.web_search_engine._fill_template(template)
            self._show_tool_result(self.ws_result, result)

    def _ws_add_custom(self):
        """用户添加自定义热点"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加自定义热点")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        ttk.Label(dialog, text="分类:").pack(anchor=tk.W, padx=20, pady=(15,3))
        cat_var = tk.StringVar(value=self.ws_category_var.get())
        cats = WebSearchAdaptEngine(self.ai_client).get_categories()
        ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=47).pack(padx=20)
        
        ttk.Label(dialog, text="热点名称:").pack(anchor=tk.W, padx=20, pady=(10,3))
        name_entry = ttk.Entry(dialog, width=50)
        name_entry.pack(padx=20)
        
        ttk.Label(dialog, text="描述（一句话说明）:").pack(anchor=tk.W, padx=20, pady=(10,3))
        desc_entry = ttk.Entry(dialog, width=50)
        desc_entry.pack(padx=20)
        
        ttk.Label(dialog, text="改编模板（用{name}等变量）:").pack(anchor=tk.W, padx=20, pady=(10,3))
        template_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=6)
        template_text.pack(padx=20, fill=tk.X)
        template_text.insert("1.0", "{name}是一个普通{职业}，直到那天{事件}...")
        
        def save():
            name = name_entry.get().strip()
            desc = desc_entry.get().strip()
            tmpl = template_text.get("1.0", tk.END).strip()
            if not name or not tmpl:
                messagebox.showwarning("提示", "请填写名称和模板")
                return
            if not self.web_search_engine:
                self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
            self.web_search_engine.add_custom_meme(cat_var.get(), name, desc, tmpl)
            self._log(f"已添加自定义热点: {name}")
            dialog.destroy()
            # 刷新列表
            self._refresh_ws_list()
            messagebox.showinfo("成功", f"已保存自定义热点「{name}」")
        
        ttk.Button(dialog, text="保存", command=save).pack(pady=15)

    def _ws_delete_custom(self):
        """删除自定义热点"""
        sel = self.ws_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的热点")
            return
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        category = self.ws_category_var.get()
        items = self.web_search_engine.get_items(category)
        idx = sel[0]
        if idx < len(items):
            if not items[idx].get("custom"):
                messagebox.showinfo("提示", "只能删除自定义添加的热点")
                return
            if messagebox.askyesno("确认", f"确定删除「{items[idx].get('name','')}」？"):
                # 直接从列表中移除并持久化
                removed = items.pop(idx)
                self.web_search_engine._save_custom(category, items)
                self._refresh_ws_list()
                self._log(f"已删除自定义热点: {removed.get('name','')}")

    def _refresh_ws_list(self):
        """刷新热点列表"""
        self.ws_listbox.delete(0, tk.END)
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        items = self.web_search_engine.get_items(self.ws_category_var.get())
        for item in items:
            marker = "[自定义]" if item.get("custom") else ""
            self.ws_listbox.insert(tk.END, f"{marker}{item.get('name','')}: {item.get('desc','')}")
