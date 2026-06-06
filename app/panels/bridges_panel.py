"""桥段库面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class BridgesPanelMixin:
    """桥段库面板混入 - 提供桥段库相关的构建和操作方法"""

    def _build_bridges_tool(self):
        """桥段库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="角色桥段库 - 经典网文桥段生成", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="桥段类型:").pack(side=tk.LEFT)
        self.bridge_cat_var = tk.StringVar()
        cats = [c["name"] for c in self.bridge_lib.get_categories()]
        ttk.Combobox(cat_frame, textvariable=self.bridge_cat_var, values=cats, state="readonly", width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(f, text="场景设定:").pack(anchor=tk.W, pady=2)
        self.bridge_setting = ttk.Entry(f, width=60)
        self.bridge_setting.pack(fill=tk.X, pady=2)
        self.bridge_setting.insert(0, "深夜的修炼室中")
        
        # 按钮行 + 自定义桥段
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="查看模板", command=self._view_bridge_template).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="AI生成桥段", command=self._gen_bridge).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="|").pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_bridge_entry = ttk.Entry(btn_frame, width=20)
        self.custom_bridge_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加", command=self._add_custom_bridge).pack(side=tk.LEFT)
        
        self.bridge_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.bridge_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.bridge_cat_var.set(cats[0])

    def _view_bridge_template(self):
        templates = self.bridge_lib.get_templates(self.bridge_cat_var.get())
        self.bridge_result.delete("1.0", tk.END)
        self.bridge_result.insert("1.0", "\n\n".join(templates))

    def _gen_bridge(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        # 使用角色系统中的实际角色数据
        characters = {}
        if self.character_system and self.character_system.character:
            char = self.character_system.character
            characters = {char.name: char.personality or "性格待定"}
        elif self.memory:
            chars = self.memory.get_characters()
            if chars:
                for name, info in list(chars.items())[:3]:
                    characters[name] = info.get("personality", "") if isinstance(info, dict) else ""
        if not characters:
            characters = {"主角": "待设定"}
        
        def run():
            try:
                result = self.bridge_lib.generate_bridge(
                    self.ai_client, self.bridge_cat_var.get(),
                    characters, self.bridge_setting.get()
                )
                self.root.after(0, lambda: self._show_tool_result(self.bridge_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _add_custom_bridge(self):
        """添加自定义桥段"""
        template = self.custom_bridge_entry.get().strip()
        if not template:
            messagebox.showinfo("提示", "请输入桥段模板")
            return
        cat = self.bridge_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择桥段类型")
            return
        self.bridge_lib.add_custom_item(cat, template)
        self.custom_bridge_entry.delete(0, tk.END)
        self._log(f"添加自定义桥段: {template[:30]}... (类型: {cat})")
        messagebox.showinfo("成功", f"已添加自定义桥段到 {cat}")
