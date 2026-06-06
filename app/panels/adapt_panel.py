"""智能改编面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from novel_toolkit import AdaptEngine


class AdaptPanelMixin:
    """智能改编面板混入 - 提供智能改编相关的构建和操作方法"""

    def _build_adapt_tool(self):
        """智能改编界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="智能改编 - 圈定截取改编，显示匹配率", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        ttk.Label(f, text="改编指示:").pack(anchor=tk.W)
        self.adapt_instr = ttk.Entry(f, width=60)
        self.adapt_instr.pack(fill=tk.X, pady=3)
        self.adapt_instr.insert(0, "改写为更紧张的氛围")
        
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="改编选中文本", command=self._adapt_selected).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="随机抽取改编", command=self._adapt_random).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="替换原文", command=self._replace_with_adapted).pack(side=tk.RIGHT)
        
        self.adapt_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.adapt_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def _adapt_selected(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        try:
            selected = self.content_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except Exception:
            selected = self.content_text.get("1.0", tk.END).strip()[:500]
        
        if not selected:
            messagebox.showinfo("提示", "请先选择要改编的文本")
            return
        
        self.adapt_engine = AdaptEngine(self.ai_client)
        
        def run():
            try:
                result = self.adapt_engine.adapt_segment(selected, self.adapt_instr.get())
                text = f"【匹配率: {result['match_rate']}%】\n\n{result['adapted']}"
                self.root.after(0, lambda: self._show_tool_result(self.adapt_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _adapt_random(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        current_text = self.content_text.get("1.0", tk.END).strip()
        if not current_text:
            messagebox.showinfo("提示", "没有可改编的内容")
            return
        
        self.adapt_engine = AdaptEngine(self.ai_client)
        
        def run():
            try:
                results = self.adapt_engine.random_adapt(current_text, 2)
                text = ""
                for i, r in enumerate(results):
                    text += f"=== 片段{i+1} (匹配率: {r['match_rate']}%) ===\n"
                    text += f"{r['adapted']}\n\n"
                self.root.after(0, lambda: self._show_tool_result(self.adapt_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _replace_with_adapted(self):
        adapted = self.adapt_result.get("1.0", tk.END).strip()
        if adapted:
            # 去掉匹配率行
            lines = adapted.split("\n")
            content = "\n".join(l for l in lines if not l.startswith("【匹配率"))
            try:
                self.content_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except (IndexError, tk.TclError):
                pass
            self.content_text.insert(tk.INSERT, content.strip())
