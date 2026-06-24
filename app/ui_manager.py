"""
UI管理器 - 处理界面相关的操作
从novel_app.py中提取的UI相关代码
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class UIManagerMixin:
    """UI管理Mixin类"""
    
    def _log(self: 'NovelWriterApp', message: str):
        """记录日志到日志面板和控制台"""
        timestamp = __import__('datetime').datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        
        # 写入loguru
        from loguru import logger
        logger.info(message)
        
        # 写入诊断日志
        if _diag := __import__('app.diagnostic_logger', fromlist=['get_logger']).get_logger():
            _diag.info(message)
        
        # 更新UI日志面板（线程安全）
        if hasattr(self, 'log_text') and self.log_text:
            self.root.after(0, lambda: self._append_log(log_msg))
    
    def _append_log(self: 'NovelWriterApp', message: str):
        """追加日志到文本框"""
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            # 限制日志行数
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 500:
                self.log_text.delete('1.0', f'{lines - 300}.0')
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass
    
    def _update_status(self: 'NovelWriterApp'):
        """更新状态栏"""
        if not hasattr(self, 'status_var'):
            return
        
        parts = []
        if self.current_novel_dir:
            meta = self._get_meta()
            title = meta.get('title', '未命名')
            parts.append(f"📖 {title}")
            
            if self.current_chapter:
                total = meta.get('total_chapters', meta.get('chapter_count', '?'))
                parts.append(f"第{self.current_chapter}/{total}章")
            
            word_count = 0
            if hasattr(self, 'content_text'):
                content = self.content_text.get("1.0", tk.END).strip()
                word_count = len(content)
            parts.append(f"{word_count}字")
        else:
            parts.append("未打开小说")
        
        self.status_var.set(" | ".join(parts))
    
    def _check_ready(self: 'NovelWriterApp', silent=False) -> bool:
        """检查是否已配置API"""
        if not self.ai_client or not self.ai_client.is_configured():
            if not silent:
                messagebox.showwarning("提示", "请先在设置中配置AI API")
            return False
        return True
    
    def _get_meta(self: 'NovelWriterApp') -> dict:
        """获取当前小说的meta信息"""
        if not self.current_novel_dir:
            return {}
        try:
            import json
            meta_file = self.current_novel_dir / "meta.json"
            if meta_file.exists():
                return json.loads(meta_file.read_text(encoding='utf-8'))
        except Exception:
            pass
        return {}
    
    def _show_help(self: 'NovelWriterApp'):
        """显示帮助信息"""
        help_text = """📖 AI小说创作工坊 - 使用帮助

═══════════════════════════════════════

🚀 快速开始
1. 点击「设置」配置AI API（支持OpenAI/DeepSeek/MIMO等）
2. 点击「新建小说」创建项目
3. 使用「自动创作」一键生成完整小说

═══════════════════════════════════════

✨ 核心功能

📝 自动创作 - AI自动完成世界观→角色→大纲→章节→定稿
🖊️ 全屏写作 - 沉浸式创作体验
📊 5Agent协作 - PlotDesigner/WorldBuilder/Writer/Reviewer/Editor
🧠 记忆系统 - 长篇小说连贯性保障
👥 角色管理 - 自动检测/经验值/等级系统
📖 阅读管理 - 支持TXT/EPUB/PDF/DOCX格式

═══════════════════════════════════════

💡 技巧

• 自动创作会自动跳过已完成的章节
• 全部重新创作可选择是否重置大纲
• 世界线功能支持分支故事创作
• 角色经验值会影响战斗力模拟

═══════════════════════════════════════

🔗 项目地址
https://github.com/ATboy-web/AI_NovelWriter
"""
        dialog = tk.Toplevel(self.root)
        dialog.title("使用帮助")
        dialog.geometry("550x500")
        dialog.configure(bg=self.C['bg_dark'])
        
        text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                      bg=self.C['bg_medium'], fg=self.C['text_primary'],
                      padx=15, pady=15)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", help_text)
        text.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="关闭", command=dialog.destroy,
                 bg=self.C['bg_light'], fg=self.C['text_primary'],
                 font=('微软雅黑', 10), padx=20).pack(pady=10)
    
    def _show_about(self: 'NovelWriterApp'):
        """显示关于对话框"""
        messagebox.showinfo("关于", 
            "AI小说创作工坊 v2.14\n\n"
            "支持15种小说类型\n"
            "5Agent协作生成\n"
            "长篇小说记忆系统\n\n"
            "https://github.com/ATboy-web/AI_NovelWriter")
    
    def _on_close(self: 'NovelWriterApp'):
        """窗口关闭处理"""
        if messagebox.askokcancel("退出", "确定退出AI小说创作工坊吗？"):
            # 停止自动创作
            self._stop_flag = True
            self._auto_running = False
            
            # 保存当前状态
            if self.current_novel_dir and hasattr(self, 'content_text'):
                try:
                    content = self.content_text.get("1.0", tk.END).strip()
                    if content and self.current_chapter:
                        ch_file = self.current_novel_dir / "chapters" / f"chapter_{self.current_chapter:04d}.txt"
                        ch_file.write_text(content, encoding='utf-8')
                except Exception:
                    pass
            
            self.root.destroy()
    
    def _export_log(self: 'NovelWriterApp'):
        """导出日志"""
        try:
            from tkinter import filedialog
            import json
            from datetime import datetime
            
            filepath = filedialog.asksaveasfilename(
                defaultextension=".log",
                filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt")],
                initialfile=f"AI_NovelWriter_日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            if not filepath:
                return
            
            # 收集日志
            log_content = f"AI小说创作工坊 · 运行日志\n"
            log_content += f"导出: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n"
            log_content += f"版本: v2.14\n"
            log_content += "═" * 40 + "\n\n"
            
            if hasattr(self, 'log_text'):
                log_text = self.log_text.get("1.0", tk.END)
                log_lines = [l for l in log_text.split('\n') if l.strip()]
                log_content += f"═══ {len(log_lines)}条 ═══\n\n"
                log_content += '\n'.join(log_lines)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            self._log(f"[日志] 已导出到: {filepath}")
            messagebox.showinfo("导出成功", f"日志已保存到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
    
    def _clear_log(self: 'NovelWriterApp'):
        """清空日志"""
        if hasattr(self, 'log_text'):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state=tk.DISABLED)
