"""元素库面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class ElementsPanelMixin:
    """元素库面板混入 - 提供元素库相关的构建和操作方法"""

    def _build_elements_tool(self):
        """元素库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="小说元素库 - 选择元素组合生成背景设定", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        # 类别选择
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="类别:").pack(side=tk.LEFT)
        self.elem_cat_var = tk.StringVar()
        cats = [c["name"] for c in self.element_lib.get_categories()]
        cat_combo = ttk.Combobox(cat_frame, textvariable=self.elem_cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(side=tk.LEFT, padx=5)
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_element_list())
        
        # 元素列表
        self.elem_listbox = tk.Listbox(f, height=8, selectmode=tk.MULTIPLE)
        self.elem_listbox.pack(fill=tk.X, pady=3)
        self.elem_listbox.bind("<Double-1>", lambda e: self._view_element_detail())
        
        # 生成按钮 + 自定义元素（同一行）
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="组合生成背景设定", command=self._gen_background_from_elements).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="查看元素详情", command=self._view_element_detail).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="|").pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_elem_entry = ttk.Entry(btn_frame, width=12)
        self.custom_elem_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加", command=self._add_custom_element).pack(side=tk.LEFT)
        
        # 结果（填充剩余空间）
        self.elem_result = scrolledtext.ScrolledText(f, height=8, wrap=tk.WORD, font=("微软雅黑", 10))
        self.elem_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.elem_cat_var.set(cats[0])
            self._refresh_element_list()

    def _refresh_element_list(self):
        self.elem_listbox.delete(0, tk.END)
        items = self.element_lib.get_items(self.elem_cat_var.get())
        for item in items:
            self.elem_listbox.insert(tk.END, item.get("name", ""))

    def _view_element_detail(self):
        sel = self.elem_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择要查看的元素（可多选）")
            return
        items = self.element_lib.get_items(self.elem_cat_var.get())
        if not items:
            messagebox.showinfo("提示", "当前类别没有元素")
            return
        
        self.elem_result.delete("1.0", tk.END)
        parts = []
        for idx in sel:
            if idx < len(items):
                item = items[idx]
                name = item.get('name', '（无名称）')
                template = item.get('template', '（无模板）')
                tags = item.get('tags', [])
                tags_str = '、'.join(tags) if tags else '（无标签）'
                parts.append(
                    f"【{name}】\n"
                    f"模板: {template}\n"
                    f"标签: {tags_str}"
                )
        self.elem_result.insert("1.0", "\n\n".join(parts))

    def _gen_background_from_elements(self):
        sel = self.elem_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选择元素")
            return
        
        items = self.element_lib.get_items(self.elem_cat_var.get())
        selected = [items[i] for i in sel if i < len(items)]
        
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                result = self.element_lib.generate_background(
                    self.ai_client, selected, 
                    self.genre_var.get(), self.title_var.get() or "未命名"
                )
                self.root.after(0, lambda: self._show_tool_result(self.elem_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _add_custom_element(self):
        """添加自定义元素"""
        name = self.custom_elem_entry.get().strip()
        if not name:
            messagebox.showinfo("提示", "请输入元素名称")
            return
        cat = self.elem_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择类别")
            return
        self.element_lib.add_custom_item(cat, {"name": name, "template": f"自定义元素: {name}", "tags": ["自定义"]})
        self._refresh_element_list()
        self.custom_elem_entry.delete(0, tk.END)
        self._log(f"添加自定义元素: {name} (类别: {cat})")
        messagebox.showinfo("成功", f"已添加自定义元素: {name}")
