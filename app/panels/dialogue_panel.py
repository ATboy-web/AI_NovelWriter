"""对话推演面板混入"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from novel_toolkit import DialogueEngine


class DialoguePanelMixin:
    """对话推演面板混入 - 提供对话推演相关的构建和操作方法"""

    def _build_dialogue_tool(self):
        """对话推演界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="情景对话推演 - 角色互动对话生成", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        ttk.Label(f, text="场景描述:").pack(anchor=tk.W)
        self.dlg_scenario = ttk.Entry(f, width=60)
        self.dlg_scenario.pack(fill=tk.X, pady=3)
        self.dlg_scenario.insert(0, "两个老友多年后重逢，在咖啡馆聊天")
        
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="开始推演", command=self._start_dialogue).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="继续推演", command=self._continue_dialogue).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="插入到章节", command=self._insert_dialogue).pack(side=tk.RIGHT)
        
        self.dlg_result = scrolledtext.ScrolledText(f, height=12, wrap=tk.WORD, font=("微软雅黑", 10))
        self.dlg_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def _start_dialogue(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        self.dialogue_engine = DialogueEngine(self.ai_client)
        
        # 使用角色系统中的实际角色
        characters = []
        if self.character_system:
            for name in self.character_system.get_character_names()[:4]:
                char = self.character_system.characters.get(name)
                if char:
                    characters.append({"name": name, "personality": char.personality or "未知"})
        if not characters and self.memory:
            chars = self.memory.get_characters()
            if chars:
                for name, info in list(chars.items())[:4]:
                    p = info.get("personality", "") if isinstance(info, dict) else ""
                    characters.append({"name": name, "personality": p or "未知"})
        if not characters:
            characters = [{"name": "角色A", "personality": "开朗"}, {"name": "角色B", "personality": "内敛"}]
        
        def run():
            try:
                result = self.dialogue_engine.start_dialogue(
                    self.dlg_scenario.get(), characters
                )
                text = self.dialogue_engine.export_text()
                self.root.after(0, lambda: self._show_tool_result(self.dlg_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _continue_dialogue(self):
        if not self.dialogue_engine:
            messagebox.showinfo("提示", "请先开始推演")
            return
        
        def run():
            try:
                self.dialogue_engine.continue_dialogue()
                text = self.dialogue_engine.export_text()
                self.root.after(0, lambda: self._show_tool_result(self.dlg_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def _insert_dialogue(self):
        content = self.dlg_result.get("1.0", tk.END).strip()
        if content:
            self.content_text.insert(tk.INSERT, "\n\n" + content)
