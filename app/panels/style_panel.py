"""风格转换面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from novel_toolkit import StyleTransferEngine


class StylePanelMixin:
    """风格转换面板混入 - 提供风格转换相关的构建和操作方法"""

    def _build_style_tool(self):
        """风格转换界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="风格转换 - 仿写、改写、风格调整", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        style_frame = ttk.Frame(f)
        style_frame.pack(fill=tk.X, pady=3)
        ttk.Label(style_frame, text="目标风格:").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="热血爽文")
        styles = list(StyleTransferEngine.STYLES.keys())
        ttk.Combobox(style_frame, textvariable=self.style_var, values=styles, state="readonly", width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(style_frame, text="转换当前章节风格", command=self._convert_style).pack(side=tk.LEFT, padx=10)
        
        self.style_result = scrolledtext.ScrolledText(f, height=12, wrap=tk.WORD, font=("微软雅黑", 10))
        self.style_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def _convert_style(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        current_text = self.content_text.get("1.0", tk.END).strip()
        if not current_text:
            messagebox.showinfo("提示", "没有可转换的内容")
            return
        
        self.style_engine = StyleTransferEngine(self.ai_client)
        
        def run():
            try:
                result = self.style_engine.convert_style(current_text, self.style_var.get())
                self.root.after(0, lambda: self._show_tool_result(self.style_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
