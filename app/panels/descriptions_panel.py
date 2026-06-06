"""描写库面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class DescriptionsPanelMixin:
    """描写库面板混入 - 提供描写库相关的构建和操作方法"""

    def _build_descriptions_tool(self):
        """描写库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="事物描写库 - 生成各类描写", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="类别:").pack(side=tk.LEFT)
        self.desc_cat_var = tk.StringVar()
        cats = self.desc_lib.get_categories()
        ttk.Combobox(cat_frame, textvariable=self.desc_cat_var, values=cats, state="readonly", width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(cat_frame, text="描写对象:").pack(side=tk.LEFT, padx=(10,0))
        self.desc_subject = ttk.Entry(cat_frame, width=15)
        self.desc_subject.pack(side=tk.LEFT, padx=5)
        ttk.Button(cat_frame, text="生成描写", command=self._gen_description).pack(side=tk.LEFT, padx=5)
        ttk.Label(cat_frame, text="|").pack(side=tk.LEFT, padx=3)
        ttk.Label(cat_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_desc_entry = ttk.Entry(cat_frame, width=10)
        self.custom_desc_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(cat_frame, text="添加", command=self._add_custom_description).pack(side=tk.LEFT)
        
        self.desc_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.desc_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.desc_cat_var.set(cats[0])

    def _gen_description(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                result = self.desc_lib.generate_description(
                    self.ai_client, self.desc_subject.get() or "日出",
                    self.desc_cat_var.get()
                )
                self.root.after(0, lambda: self._show_tool_result(self.desc_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _add_custom_description(self):
        """添加自定义描写关键词"""
        keyword = self.custom_desc_entry.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入描写关键词")
            return
        cat = self.desc_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择类别")
            return
        self.desc_lib.add_custom_item(cat, keyword)
        self.custom_desc_entry.delete(0, tk.END)
        self._log(f"添加自定义描写关键词: {keyword} (类别: {cat})")
        messagebox.showinfo("成功", f"已添加自定义关键词: {keyword} 到 {cat}")
