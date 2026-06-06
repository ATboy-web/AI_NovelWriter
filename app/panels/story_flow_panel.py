"""故事流推演面板混入"""
import threading
import tkinter as tk
from tkinter import messagebox

from app.ui_style import UIStyle
from novel_toolkit import StoryFlowEngine


class StoryFlowPanelMixin:
    """故事流推演面板混入 - 提供故事流推演相关的构建和操作方法"""

    def _build_story_flow_tool(self):
        """故事流推演界面"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="故事流推演 - 4种模式", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        self.sf_mode_var = tk.IntVar(value=1)
        modes = [
            (1, "正向推演", "背景+事件→推演过程"),
            (2, "桥接推演", "开端+结局→推演中间"),
            (3, "分支推演", "当前故事→多个走向"),
            (4, "冲突升级", "当前局面→逐步升级"),
        ]
        mode_frame = tk.Frame(f, bg=C['bg_dark'])
        mode_frame.pack(fill=tk.X, pady=3)
        for val, name, desc in modes:
            tk.Radiobutton(mode_frame, text=f"{name}", variable=self.sf_mode_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent']).pack(side=tk.LEFT, padx=5)
        
        # 提示文字
        self.sf_hint = tk.Label(f, text="模式1: 输入背景和事件，推演故事发展过程", 
                               font=('微软雅黑', 8), bg=C['bg_dark'], fg=C['text_muted'])
        self.sf_hint.pack(anchor=tk.W, pady=2)
        
        # 模式切换时更新提示
        def update_hint(*args):
            hints = {1: "模式1: 输入背景和事件，推演故事发展过程",
                    2: "模式2: 第一行写开端，最后一行写结局，推演中间过程",
                    3: "模式3: 输入当前故事，生成多个可能走向分支",
                    4: "模式4: 输入当前局面，推演冲突逐步升级的过程"}
            self.sf_hint.config(text=hints.get(self.sf_mode_var.get(), ""))
        
        self.sf_mode_var.trace_add('write', update_hint)
        
        tk.Label(f, text="输入内容:", font=('微软雅黑', 9),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=3)
        self.sf_input = tk.Text(f, height=5, wrap=tk.WORD, font=('微软雅黑', 10),
                               bg=C['input_bg'], fg=C['text_primary'])
        self.sf_input.pack(fill=tk.X, pady=3)
        
        btn_frame = tk.Frame(f, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="开始推演", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._run_story_flow).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="插入到章节", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=lambda: self._insert_to_chapter(self.sf_result)).pack(side=tk.RIGHT)
        
        self.sf_result = tk.Text(f, height=10, wrap=tk.WORD, font=('微软雅黑', 10),
                                bg=C['bg_card'], fg=C['text_primary'])
        self.sf_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def _run_story_flow(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        self.story_flow_engine = StoryFlowEngine(self.ai_client)
        input_text = self.sf_input.get("1.0", tk.END).strip()
        
        if not input_text:
            messagebox.showinfo("提示", "请输入内容")
            return
        
        mode = self.sf_mode_var.get()
        
        def run():
            try:
                if mode == 1:
                    result = self.story_flow_engine.mode1_forward(input_text, "主角", input_text)
                elif mode == 2:
                    lines = input_text.split("\n")
                    beginning = lines[0] if lines else ""
                    ending = lines[-1] if len(lines) > 1 else "结局待定"
                    result = self.story_flow_engine.mode2_bridge(beginning, ending)
                elif mode == 3:
                    result = self.story_flow_engine.mode3_branch(input_text, 3)
                elif mode == 4:
                    result = self.story_flow_engine.mode4_conflict_escalation(input_text)
                else:
                    result = "请选择推演模式"
                
                self.root.after(0, lambda: self._show_tool_result(self.sf_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
