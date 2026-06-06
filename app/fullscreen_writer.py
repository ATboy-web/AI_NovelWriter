"""
全屏沉浸式写作窗口模块
"""

import json
import re
import threading
import tkinter as tk
from tkinter import ttk
from loguru import logger

from .ai_client import AIClient
from .config import AppConfig
from .ui_style import UIStyle


class FullscreenWriter:
    """全屏沉浸式写作窗口"""
    
    def __init__(self, parent, ai_client: AIClient, config: AppConfig, 
                 initial_text: str = "", save_callback=None, shared_context: str = ""):
        self.parent = parent
        self.ai = ai_client
        self.config = config
        self.save_callback = save_callback
        self.text_content = initial_text
        self.shared_context = shared_context  # 共享上下文（世界观、角色、大纲等）
        
        # 写作设置
        self.font_size = 18
        self.paper_width = 700
        self.paper_position = "center"  # center / left / right
        self.bg_opacity = 0.85
        self.typewriter_mode = True  # 打字机模式
        self.ai_assist_enabled = True
        
        # AI续写相关
        self.ai_suggestion = ""
        self.suggestion_active = False
        
        # 创建窗口
        self.win = tk.Toplevel(parent)
        self.win.title("全屏写作")
        self.win.attributes('-fullscreen', True)
        self.win.configure(bg='#1a1a2e')
        
        self._create_widgets()
        self._bind_events()
        
        # 加载设置
        self._load_writer_settings()
    
    def _create_widgets(self):
        """创建全屏写作界面"""
        C = UIStyle.COLORS
        
        # 顶部工具栏
        self.toolbar = tk.Frame(self.win, bg='#16213e', height=40)
        self.toolbar.pack(fill=tk.X)
        self.toolbar.pack_propagate(False)
        
        # 左侧按钮
        left_btns = tk.Frame(self.toolbar, bg='#16213e')
        left_btns.pack(side=tk.LEFT, padx=15, fill=tk.Y)
        
        tk.Button(left_btns, text="退出 (Esc)", font=('微软雅黑', 9),
                 bg='#e74c3c', fg='white', relief=tk.FLAT, padx=10,
                 command=self._exit_fullscreen).pack(side=tk.LEFT, pady=5)
        tk.Button(left_btns, text="保存", font=('微软雅黑', 9),
                 bg='#27ae60', fg='white', relief=tk.FLAT, padx=10,
                 command=self._save).pack(side=tk.LEFT, padx=8, pady=5)
        
        # AI功能按钮区
        ai_btns = tk.Frame(self.toolbar, bg='#16213e')
        ai_btns.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        tk.Label(ai_btns, text="AI辅助:", font=('微软雅黑', 9),
                bg='#16213e', fg='#a78bfa').pack(side=tk.LEFT, pady=5)
        
        ai_features = [
            ("续写 (Tab)", self._ai_continue, '#7c3aed'),
            ("扩写", self._ai_expand, '#3b82f6'),
            ("简写", self._ai_compress, '#f59e0b'),
            ("润色", self._ai_polish, '#10b981'),
            ("改写", self._ai_rewrite, '#ef4444'),
            ("对话", self._ai_dialogue, '#8b5cf6'),
        ]
        
        for text, cmd, color in ai_features:
            tk.Button(ai_btns, text=text, font=('微软雅黑', 8),
                     bg=color, fg='white', relief=tk.FLAT, padx=8, pady=3,
                     cursor='hand2', activebackground=color,
                     command=cmd).pack(side=tk.LEFT, padx=2, pady=5)
        
        # 右侧控件
        right_ctrls = tk.Frame(self.toolbar, bg='#16213e')
        right_ctrls.pack(side=tk.RIGHT, padx=15, fill=tk.Y)
        
        # 打字机模式
        self.tw_var = tk.BooleanVar(value=self.typewriter_mode)
        tk.Checkbutton(right_ctrls, text="打字机", variable=self.tw_var,
                      font=('微软雅黑', 9), bg='#16213e', fg='#94a3b8',
                      selectcolor='#7c3aed', activebackground='#16213e',
                      command=self._toggle_typewriter).pack(side=tk.LEFT, pady=5)
        
        # 字数统计
        self.word_count_label = tk.Label(right_ctrls, text="字数: 0",
                                        font=('微软雅黑', 9), bg='#16213e', fg='#94a3b8')
        self.word_count_label.pack(side=tk.LEFT, padx=15, pady=5)
        
        # 设置按钮
        tk.Button(right_ctrls, text="设置", font=('微软雅黑', 9),
                 bg='#353548', fg='#94a3b8', relief=tk.FLAT, padx=10,
                 command=self._show_writer_settings).pack(side=tk.LEFT, pady=5)
        
        # 背景层
        self.bg_frame = tk.Frame(self.win, bg='#1a1a2e')
        self.bg_frame.pack(fill=tk.BOTH, expand=True)
        
        # 纸张容器（用于控制位置）
        self.paper_container = tk.Frame(self.bg_frame, bg='#1a1a2e')
        self.paper_container.pack(fill=tk.BOTH, expand=True, padx=50, pady=20)
        
        # 纸张
        self.paper = tk.Frame(self.paper_container, bg='#f5f0e8', 
                             width=self.paper_width, relief=tk.FLAT)
        
        # 内边距
        self.inner_frame = tk.Frame(self.paper, bg='#f5f0e8')
        self.inner_frame.pack(fill=tk.BOTH, expand=True, padx=60, pady=40)
        
        # Markdown工具栏
        md_toolbar = tk.Frame(self.inner_frame, bg='#f5f0e8')
        md_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        md_btns = [
            ("H1", "heading1", "# "), ("H2", "heading2", "## "), ("H3", "heading3", "### "),
            ("B", "bold", "**"), ("I", "italic", "*"), ("S", "strike", "~~"),
            ("•", "list", "- "), ("1.", "olist", "1. "), (">", "quote", "> "),
            ("—", "hr", "\n---\n"), ("`", "code", "`"), ("```", "codeblock", "```\n"),
        ]
        
        for text, name, prefix in md_btns:
            btn = tk.Button(md_toolbar, text=text, font=('Consolas', 9, 'bold'),
                          bg='#e8e3d8', fg='#5c5647', relief=tk.FLAT,
                          padx=6, pady=2, cursor='hand2',
                          activebackground='#d4cfc4',
                          command=lambda p=prefix, n=name: self._insert_markdown(p, n))
            btn.pack(side=tk.LEFT, padx=1)
        
        # Markdown预览开关
        self.preview_var = tk.BooleanVar(value=False)
        tk.Checkbutton(md_toolbar, text="预览", variable=self.preview_var,
                      font=('微软雅黑', 8), bg='#f5f0e8', fg='#5c5647',
                      selectcolor='#7c3aed',
                      command=self._toggle_preview).pack(side=tk.RIGHT, padx=5)
        
        # 写作区域容器（编辑+预览）
        self.text_container = tk.Frame(self.inner_frame, bg='#f5f0e8')
        self.text_container.pack(fill=tk.BOTH, expand=True)
        
        # 写作区域
        self.text_widget = tk.Text(
            self.text_container,
            wrap=tk.WORD,
            font=("Consolas", self.font_size),
            bg='#f5f0e8',
            fg='#2c2c2c',
            insertbackground='#e74c3c',
            insertwidth=3,
            relief=tk.FLAT,
            padx=20,
            pady=20,
            spacing1=2,
            spacing3=2,
            selectbackground='#3498db',
            undo=True,
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 预览区域（默认隐藏）
        self.preview_widget = tk.Text(
            self.text_container,
            wrap=tk.WORD,
            font=("微软雅黑", self.font_size),
            bg='#ffffff',
            fg='#2c2c2c',
            relief=tk.FLAT,
            padx=20,
            pady=20,
            state=tk.DISABLED,
        )
        # 预览默认不显示
        
        # 配置Markdown语法高亮
        self._setup_markdown_highlighting()
        
        # 加载初始内容
        if self.text_content:
            self.text_widget.insert("1.0", self.text_content)
        
        # AI续写提示标签
        self.suggestion_label = tk.Label(
            self.inner_frame, text="", font=("微软雅黑", self.font_size),
            fg='#999999', bg='#f5f0e8', anchor=tk.W, justify=tk.LEFT
        )
        
        # AI处理状态标签
        self.ai_status_label = tk.Label(
            self.inner_frame, text="", font=("微软雅黑", 12),
            fg='#f59e0b', bg='#f5f0e8', anchor=tk.CENTER
        )
        
        # 右键菜单
        self.context_menu = tk.Menu(self.text_widget, tearoff=0, 
                                   font=('微软雅黑', 10),
                                   bg='#2d2d3f', fg='#f8fafc',
                                   activebackground='#7c3aed',
                                   activeforeground='white')
        self.context_menu.add_command(label="AI续写 (Tab)", command=self._ai_continue)
        self.context_menu.add_command(label="AI扩写", command=self._ai_expand)
        self.context_menu.add_command(label="AI简写", command=self._ai_compress)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="AI润色", command=self._ai_polish)
        self.context_menu.add_command(label="AI改写", command=self._ai_rewrite)
        self.context_menu.add_command(label="AI生成对话", command=self._ai_dialogue)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="撤销 (Ctrl+Z)", command=lambda: self.text_widget.edit_undo())
        self.context_menu.add_command(label="重做 (Ctrl+Y)", command=lambda: self.text_widget.edit_redo())
        
        self.text_widget.bind("<Button-3>", self._show_context_menu)
        
        # 底部状态栏
        self.status_bar = tk.Frame(self.win, bg='#16213e')
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(self.status_bar, text="AI辅助: 开启 | 打字机模式: 开启", 
                                      background='#16213e', foreground='white')
        self.status_label.pack(side=tk.LEFT, padx=20, pady=5)
        
        self._update_paper_position()
    
    def _bind_events(self):
        """绑定事件"""
        self.win.bind('<Escape>', lambda e: self._exit_fullscreen())
        self.win.bind('<Control-s>', lambda e: self._save())
        self.win.bind('<Control-z>', lambda e: self.text_widget.edit_undo())
        self.win.bind('<Control-y>', lambda e: self.text_widget.edit_redo())
        
        # AI功能快捷键
        self.win.bind('<Control-e>', lambda e: self._ai_expand())   # Ctrl+E 扩写
        self.win.bind('<Control-q>', lambda e: self._ai_compress()) # Ctrl+Q 简写
        self.win.bind('<Control-r>', lambda e: self._ai_rewrite())  # Ctrl+R 改写
        self.win.bind('<Control-p>', lambda e: self._ai_polish())   # Ctrl+P 润色
        
        # Markdown快捷键
        self.win.bind('<Control-b>', lambda e: self._insert_markdown('**', 'bold'))     # Ctrl+B 加粗
        self.win.bind('<Control-i>', lambda e: self._insert_markdown('*', 'italic'))    # Ctrl+I 斜体
        self.win.bind('<Control-`>', lambda e: self._insert_markdown('`', 'code'))      # Ctrl+` 代码
        self.win.bind('<Control-l>', lambda e: self._insert_markdown('- ', 'list'))     # Ctrl+L 列表
        self.win.bind('<Control-Shift-P>', lambda e: self._toggle_preview())            # Ctrl+Shift+P 预览
        
        # 按键事件 - 用于打字机模式和AI辅助
        self.text_widget.bind('<KeyRelease>', self._on_key_release)
        self.text_widget.bind('<Tab>', self._on_tab)
        
        # 字体大小调整
        self.win.bind('<Control-plus>', lambda e: self._change_font_size(1))
        self.win.bind('<Control-minus>', lambda e: self._change_font_size(-1))
        self.win.bind('<Control-equal>', lambda e: self._change_font_size(1))
    
    def _show_context_menu(self, event):
        """显示右键菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def _on_key_release(self, event=None):
        """按键释放事件 - 打字机模式+字数统计+Markdown高亮"""
        content = self.text_widget.get("1.0", tk.END).strip()
        self.word_count_label.config(text=f"字数: {len(content)}")
        
        if self.typewriter_mode:
            self._center_current_line()
        
        if self.suggestion_active and event and event.keysym not in ('Tab', 'Shift_L', 'Shift_R', 'Control_L', 'Control_R'):
            self._clear_suggestion()
        
        # Markdown高亮（延迟更新避免频繁触发）
        if hasattr(self, '_highlight_after_id'):
            self.win.after_cancel(self._highlight_after_id)
        self._highlight_after_id = self.win.after(300, self._update_markdown_highlighting)
    
    def _on_tab(self, event):
        """Tab键接受AI建议"""
        if self.suggestion_active and self.ai_suggestion:
            # 插入AI建议
            self.text_widget.insert(tk.INSERT, self.ai_suggestion)
            self._clear_suggestion()
            return "break"  # 阻止默认Tab行为
        
        # 如果没有建议，触发AI续写
        if self.ai_assist_enabled:
            self._trigger_ai_suggestion()
        return "break"
    
    def _trigger_ai_suggestion(self):
        """触发AI续写建议 - 使用共享上下文"""
        if not self.ai.is_configured():
            return
        
        current_text = self.text_widget.get("1.0", tk.END).strip()
        if not current_text:
            return
        
        context = current_text[-500:]
        system = "你是一位小说写作助手。请根据用户正在写的内容，续写20-50字。直接输出续写内容，不要添加任何说明。保持风格和语气一致。"
        if self.shared_context:
            system += f"\n\n小说背景信息（供参考，保持一致性）：\n{self.shared_context[:1000]}"
        
        def generate():
            try:
                response = self.ai.chat(
                    [{"role": "user", "content": f"请续写以下内容：\n\n{context}"}],
                    system=system,
                    max_tokens=200,
                    temperature=0.8
                )
                
                self.ai_suggestion = response.strip()[:100]  # 限制长度
                self.suggestion_active = True
                
                # 在主线程显示建议
                self.win.after(0, self._show_suggestion)
            except Exception as e:
                logger.error(f"AI续写失败: {e}")
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _show_suggestion(self):
        """显示AI建议（灰色提示文字）"""
        if self.ai_suggestion:
            # 在光标位置后显示灰色提示
            cursor_pos = self.text_widget.index(tk.INSERT)
            self.suggestion_label.config(text=self.ai_suggestion)
            self.suggestion_label.place(in_=self.text_widget, relx=0, rely=1.0, anchor=tk.NW)
    
    def _clear_suggestion(self):
        """清除AI建议"""
        self.ai_suggestion = ""
        self.suggestion_active = False
        self.suggestion_label.place_forget()
    
    def _center_current_line(self):
        """打字机模式 - 当前行居中"""
        try:
            # 获取光标位置
            cursor_line = self.text_widget.index(tk.INSERT).split('.')[0]
            
            # 获取文本框高度
            self.text_widget.update_idletasks()
            widget_height = self.text_widget.winfo_height()
            
            # 计算当前行在文本中的位置
            line_y = self.text_widget.dlineinfo(f"{cursor_line}.0")
            if line_y:
                # 计算滚动位置，使当前行居中
                total_lines = int(self.text_widget.index(tk.END).split('.')[0])
                target_pos = (int(cursor_line) - widget_height / (self.font_size * 2)) / total_lines
                target_pos = max(0, min(1, target_pos))
                self.text_widget.yview_moveto(target_pos)
        except tk.TclError:
            pass
    
    def _change_font_size(self, delta):
        """调整字体大小"""
        self.font_size = max(12, min(36, self.font_size + delta))
        self.text_widget.configure(font=("微软雅黑", self.font_size))
    
    def _toggle_ai(self):
        """切换AI辅助"""
        self.ai_assist_enabled = not self.ai_assist_enabled
        self._update_status()
    
    def _toggle_typewriter(self):
        """切换打字机模式"""
        self.typewriter_mode = self.tw_var.get()
        self._update_status()
    
    def _update_status(self):
        """更新状态栏"""
        ai_status = "开启" if self.ai_assist_enabled else "关闭"
        tw_status = "开启" if self.typewriter_mode else "关闭"
        self.status_label.config(text=f"AI辅助: {ai_status} | 打字机模式: {tw_status}")
    
    def _update_paper_position(self):
        """更新纸张位置"""
        self.paper_container.pack_forget()
        
        if self.paper_position == "center":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=50, pady=20)
            self.paper.pack(anchor=tk.CENTER, expand=True)
        elif self.paper_position == "left":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=(50, 100), pady=20)
            self.paper.pack(anchor=tk.W)
        elif self.paper_position == "right":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=(100, 50), pady=20)
            self.paper.pack(anchor=tk.E)
        
        self.paper.configure(width=self.paper_width)
    
    def _ai_expand(self):
        """AI扩写 - 将选中文本或当前段落扩展为更详细的内容"""
        self._ai_transform("expand")
    
    def _ai_compress(self):
        """AI简写 - 将选中文本精简压缩"""
        self._ai_transform("compress")
    
    def _ai_continue(self):
        """AI续写 - 继续写下去（Tab键功能）"""
        if self.suggestion_active and self.ai_suggestion:
            self.text_widget.insert(tk.INSERT, self.ai_suggestion)
            self._clear_suggestion()
        else:
            self._trigger_ai_suggestion()
    
    def _ai_polish(self):
        """AI润色 - 优化语言表达"""
        self._ai_transform("polish")
    
    def _ai_rewrite(self):
        """AI改写 - 重新表达相同内容"""
        self._ai_transform("rewrite")
    
    def _ai_dialogue(self):
        """AI生成对话 - 根据上下文生成角色对话"""
        self._ai_transform("dialogue")
    
    def _ai_transform(self, mode: str):
        """AI文本变换通用方法"""
        if not self.ai.is_configured():
            return
        
        # 获取选中文本，如果没有选中则获取当前段落
        try:
            selected = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # 没有选中文本，获取光标所在段落
            cursor_pos = self.text_widget.index(tk.INSERT)
            line_start = cursor_pos.split('.')[0] + '.0'
            # 找到段落开头
            while line_start > '1.0':
                prev_line = self.text_widget.get(f"{line_start}-1l", line_start)
                if prev_line.strip() == '':
                    break
                line_start = f"{line_start}-1l"
            # 找到段落结尾
            line_end = line_start
            while True:
                next_line = self.text_widget.get(line_end, f"{line_end}+1l")
                if next_line.strip() == '' or line_end == self.text_widget.index(tk.END):
                    break
                line_end = f"{line_end}+1l"
            selected = self.text_widget.get(line_start, line_end).strip()
        
        if not selected:
            selected = self.text_widget.get("1.0", tk.END).strip()[-300:]
        
        # 构建提示词
        prompts = {
            "expand": {
                "system": "你是一位小说写作助手。请将用户提供的文本扩写为更详细、更生动的内容。保持原有情节和风格，增加细节描写、心理活动、环境描写等。直接输出扩写后的内容。",
                "user": f"请扩写以下内容，使其更加详细生动：\n\n{selected}",
                "max_tokens": 1000,
            },
            "compress": {
                "system": "你是一位小说写作助手。请将用户提供的文本精简压缩，保留核心情节和关键信息，去除冗余描写。直接输出精简后的内容。",
                "user": f"请精简以下内容，保留核心情节：\n\n{selected}",
                "max_tokens": 500,
            },
            "polish": {
                "system": "你是一位小说写作助手。请润色用户提供的文本，优化语言表达，使其更加流畅、优美、有感染力。保持原有情节不变。直接输出润色后的内容。",
                "user": f"请润色以下内容，优化语言表达：\n\n{selected}",
                "max_tokens": 800,
            },
            "rewrite": {
                "system": "你是一位小说写作助手。请用不同的表达方式重新改写用户提供的文本，保持相同的情节和含义，但使用不同的词汇和句式。直接输出改写后的内容。",
                "user": f"请改写以下内容，使用不同的表达方式：\n\n{selected}",
                "max_tokens": 800,
            },
            "dialogue": {
                "system": "你是一位小说写作助手。请根据用户提供的文本内容，生成一段角色之间的对话。对话要符合角色性格，自然生动。直接输出对话内容。",
                "user": f"请根据以下内容，生成角色之间的对话：\n\n{selected}",
                "max_tokens": 600,
            },
        }
        
        prompt = prompts.get(mode, prompts["polish"])
        
        # 添加共享上下文
        system = prompt["system"]
        if self.shared_context:
            system += f"\n\n小说背景（保持一致性）：\n{self.shared_context[:500]}"
        
        # 显示处理中状态
        self._show_ai_status(f"AI{mode}中...")
        
        def generate():
            try:
                response = self.ai.chat(
                    [{"role": "user", "content": prompt["user"]}],
                    system=system,
                    max_tokens=prompt["max_tokens"],
                    temperature=0.7
                )
                
                # 在主线程中替换文本
                self.win.after(0, lambda: self._replace_selection(response.strip(), mode))
                self.win.after(0, self._hide_ai_status)
                
            except Exception as e:
                self.win.after(0, lambda: self._show_ai_status(f"AI错误: {str(e)[:30]}"))
                self.win.after(3000, self._hide_ai_status)
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _replace_selection(self, new_text: str, mode: str):
        """替换选中文本"""
        try:
            self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # 没有选中，插入到光标位置
            pass
        
        # 插入新文本
        if mode == "expand":
            # 扩写：插入到原位置后面
            self.text_widget.insert(tk.INSERT, "\n\n" + new_text)
        elif mode == "dialogue":
            # 对话：插入到新行
            self.text_widget.insert(tk.INSERT, "\n\n" + new_text)
        else:
            # 其他：替换
            self.text_widget.insert(tk.INSERT, new_text)
        
        # 更新字数
        content = self.text_widget.get("1.0", tk.END).strip()
        self.word_count_label.config(text=f"字数: {len(content)}")
    
    def _show_ai_status(self, text: str):
        """显示AI处理状态"""
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.config(text=text)
            self.ai_status_label.place(relx=0.5, rely=0.05, anchor=tk.CENTER)
    
    def _hide_ai_status(self):
        """隐藏AI处理状态"""
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.place_forget()
    
    # ===== Markdown功能 =====
    
    def _setup_markdown_highlighting(self):
        """设置Markdown语法高亮"""
        # 定义标签样式
        self.text_widget.tag_configure('md_h1', font=('微软雅黑', self.font_size + 6, 'bold'), foreground='#1a1a2e')
        self.text_widget.tag_configure('md_h2', font=('微软雅黑', self.font_size + 4, 'bold'), foreground='#2d2d3f')
        self.text_widget.tag_configure('md_h3', font=('微软雅黑', self.font_size + 2, 'bold'), foreground='#3d3d52')
        self.text_widget.tag_configure('md_bold', font=('Consolas', self.font_size, 'bold'))
        self.text_widget.tag_configure('md_italic', font=('Consolas', self.font_size, 'italic'))
        self.text_widget.tag_configure('md_strike', overstrike=True, foreground='#888888')
        self.text_widget.tag_configure('md_code', font=('Consolas', self.font_size - 1), 
                                      background='#e8e3d8', foreground='#c0392b')
        self.text_widget.tag_configure('md_codeblock', font=('Consolas', self.font_size - 1),
                                      background='#e8e3d8', foreground='#2c3e50')
        self.text_widget.tag_configure('md_quote', foreground='#7f8c8d', lmargin1=20, lmargin2=20)
        self.text_widget.tag_configure('md_list', lmargin1=20, lmargin2=30)
        self.text_widget.tag_configure('md_link', foreground='#3498db', underline=True)
        self.text_widget.tag_configure('md_hr', foreground='#bdc3c7')
        
        # 绑定按键事件 - 用于打字机模式和AI辅助
        self.text_widget.bind('<KeyRelease>', self._on_key_release)
    
    def _update_markdown_highlighting(self):
        """更新Markdown语法高亮"""
        content = self.text_widget.get("1.0", tk.END)
        
        # 清除所有高亮标签
        for tag in ['md_h1', 'md_h2', 'md_h3', 'md_bold', 'md_italic', 
                    'md_strike', 'md_code', 'md_codeblock', 'md_quote', 'md_list', 'md_link', 'md_hr']:
            self.text_widget.tag_remove(tag, "1.0", tk.END)
        
        # 标题高亮
        for match in re.finditer(r'^(# .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h1', start, end)
        
        for match in re.finditer(r'^(## .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h2', start, end)
        
        for match in re.finditer(r'^(### .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h3', start, end)
        
        # 加粗
        for match in re.finditer(r'(\*\*[^*]+\*\*)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_bold', start, end)
        
        # 斜体
        for match in re.finditer(r'(\*[^*]+\*)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_italic', start, end)
        
        # 删除线
        for match in re.finditer(r'(~~[^~]+~~)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_strike', start, end)
        
        # 行内代码
        for match in re.finditer(r'(`[^`]+`)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_code', start, end)
        
        # 代码块
        for match in re.finditer(r'(```[\s\S]*?```)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_codeblock', start, end)
        
        # 引用
        for match in re.finditer(r'^(> .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_quote', start, end)
        
        # 列表
        for match in re.finditer(r'^(\- .+|\* .+|\d+\. .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_list', start, end)
        
        # 分割线
        for match in re.finditer(r'^(---+|\*\*\*+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_hr', start, end)
    
    def _insert_markdown(self, prefix: str, name: str):
        """插入Markdown标记"""
        try:
            # 获取选中文本
            selected = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            
            if name in ['bold', 'italic', 'strike', 'code']:
                # 包围选中文本
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"{prefix}{selected}{prefix}")
            elif name == 'link':
                # 插入链接
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"[{selected}](url)")
            else:
                # 在选中文本前插入
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"{prefix}{selected}")
        except tk.TclError:
            # 没有选中文本
            if name in ['heading1', 'heading2', 'heading3']:
                # 在行首插入标题
                cursor_pos = self.text_widget.index(tk.INSERT)
                line_start = cursor_pos.split('.')[0] + '.0'
                self.text_widget.insert(line_start, prefix)
            elif name == 'hr':
                self.text_widget.insert(tk.INSERT, "\n---\n")
            elif name == 'codeblock':
                self.text_widget.insert(tk.INSERT, "```\n\n```")
                # 移动光标到代码块中间
                cursor_pos = self.text_widget.index(tk.INSERT)
                self.text_widget.mark_set(tk.INSERT, f"{cursor_pos}-3l")
            elif name in ['list', 'olist', 'quote']:
                # 在行首插入
                cursor_pos = self.text_widget.index(tk.INSERT)
                line_start = cursor_pos.split('.')[0] + '.0'
                self.text_widget.insert(line_start, prefix)
            else:
                # 在光标位置插入标记
                self.text_widget.insert(tk.INSERT, f"{prefix}{prefix}")
                # 移动光标到标记中间
                cursor_pos = self.text_widget.index(tk.INSERT)
                self.text_widget.mark_set(tk.INSERT, f"{cursor_pos}-1c")
        
        # 更新高亮
        self._update_markdown_highlighting()
    
    def _toggle_preview(self):
        """切换Markdown预览"""
        if self.preview_var.get():
            # 显示预览
            self._update_preview()
            self.preview_widget.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        else:
            # 隐藏预览
            self.preview_widget.pack_forget()
    
    def _update_preview(self):
        """更新Markdown预览"""
        content = self.text_widget.get("1.0", tk.END)
        
        # 简单的Markdown转HTML预览
        
        # 转换Markdown为可读文本
        preview = content
        preview = re.sub(r'^# (.+)$', r'【标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^## (.+)$', r'【大标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^### (.+)$', r'【小标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'\*\*([^*]+)\*\*', r'【加粗】\1', preview)
        preview = re.sub(r'\*([^*]+)\*', r'【斜体】\1', preview)
        preview = re.sub(r'~~([^~]+)~~', r'【删除】\1', preview)
        preview = re.sub(r'`([^`]+)`', r'「\1」', preview)
        preview = re.sub(r'^> (.+)$', r'  ┃ \1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^- (.+)$', r'  • \1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^---+$', '─' * 40, preview, flags=re.MULTILINE)
        
        self.preview_widget.config(state=tk.NORMAL)
        self.preview_widget.delete("1.0", tk.END)
        self.preview_widget.insert("1.0", preview)
        self.preview_widget.config(state=tk.DISABLED)
    
    def _show_writer_settings(self):
        """显示写作设置对话框"""
        dialog = tk.Toplevel(self.win)
        dialog.title("写作设置")
        dialog.geometry("400x450")
        dialog.transient(self.win)
        dialog.grab_set()
        
        ttk.Label(dialog, text="字体大小:").pack(anchor=tk.W, padx=20, pady=(15,3))
        font_var = tk.IntVar(value=self.font_size)
        ttk.Scale(dialog, from_=12, to=36, variable=font_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="纸张宽度:").pack(anchor=tk.W, padx=20, pady=(10,3))
        width_var = tk.IntVar(value=self.paper_width)
        ttk.Scale(dialog, from_=400, to=1000, variable=width_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="纸张位置:").pack(anchor=tk.W, padx=20, pady=(10,3))
        pos_var = tk.StringVar(value=self.paper_position)
        pos_frame = ttk.Frame(dialog)
        pos_frame.pack(fill=tk.X, padx=20)
        ttk.Radiobutton(pos_frame, text="居中", variable=pos_var, value="center").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pos_frame, text="左侧", variable=pos_var, value="left").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pos_frame, text="右侧", variable=pos_var, value="right").pack(side=tk.LEFT, padx=10)
        
        ttk.Label(dialog, text="背景透明度:").pack(anchor=tk.W, padx=20, pady=(10,3))
        opacity_var = tk.DoubleVar(value=self.bg_opacity)
        ttk.Scale(dialog, from_=0.3, to=1.0, variable=opacity_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="背景颜色:").pack(anchor=tk.W, padx=20, pady=(10,3))
        bg_var = tk.StringVar(value="#f5f0e8")
        colors = [("#f5f0e8", "米白"), ("#ffffff", "纯白"), ("#2c2c2c", "深灰"), ("#1a1a2e", "深蓝黑")]
        color_frame = ttk.Frame(dialog)
        color_frame.pack(fill=tk.X, padx=20)
        for color, name in colors:
            btn = tk.Button(color_frame, bg=color, width=4, height=2, 
                          command=lambda c=color: bg_var.set(c))
            btn.pack(side=tk.LEFT, padx=5)
            ttk.Label(color_frame, text=name).pack(side=tk.LEFT, padx=(0,10))
        
        def apply():
            self.font_size = font_var.get()
            self.paper_width = width_var.get()
            self.paper_position = pos_var.get()
            self.bg_opacity = opacity_var.get()
            
            bg_color = bg_var.get()
            self.paper.configure(bg=bg_color, width=self.paper_width)
            self.inner_frame.configure(bg=bg_color)
            self.text_widget.configure(bg=bg_color, font=("微软雅黑", self.font_size))
            self.suggestion_label.configure(bg=bg_color)
            
            self._update_paper_position()
            self._save_writer_settings()
            dialog.destroy()
        
        ttk.Button(dialog, text="应用", command=apply).pack(pady=20)
    
    def _load_writer_settings(self):
        """加载写作设置"""
        if self.config:
            settings_file = self.config.config_dir / "writer_settings.json"
            if settings_file.exists():
                with open(settings_file, 'r') as f:
                    s = json.load(f)
                self.font_size = s.get("font_size", 18)
                self.paper_width = s.get("paper_width", 700)
                self.paper_position = s.get("paper_position", "center")
                self.bg_opacity = s.get("bg_opacity", 0.85)
                self.typewriter_mode = s.get("typewriter_mode", True)
                self.ai_assist_enabled = s.get("ai_assist", True)
    
    def _save_writer_settings(self):
        """保存写作设置"""
        if self.config:
            settings_file = self.config.config_dir / "writer_settings.json"
            with open(settings_file, 'w') as f:
                json.dump({
                    "font_size": self.font_size,
                    "paper_width": self.paper_width,
                    "paper_position": self.paper_position,
                    "bg_opacity": self.bg_opacity,
                    "typewriter_mode": self.typewriter_mode,
                    "ai_assist": self.ai_assist_enabled,
                }, f, indent=2)
    
    def _save(self):
        """保存内容"""
        self.text_content = self.text_widget.get("1.0", tk.END).strip()
        if self.save_callback:
            self.save_callback(self.text_content)
    
    def _exit_fullscreen(self):
        """退出全屏"""
        self._save()
        self.win.destroy()
    
    def get_content(self) -> str:
        """获取写作内容"""
        return self.text_widget.get("1.0", tk.END).strip()
