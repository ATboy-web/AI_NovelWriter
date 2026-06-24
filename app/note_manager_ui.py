"""
笔记管理UI - 处理笔记相关的界面操作
从novel_app.py中提取的笔记相关代码
"""

import json
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class NoteManagerMixin:
    """笔记管理Mixin类"""
    
    def _refresh_notes(self: 'NovelWriterApp'):
        """刷新笔记列表"""
        if not hasattr(self, 'note_listbox') or not self.current_novel_dir:
            return
        
        self.note_listbox.delete(0, tk.END)
        
        notes_dir = self.current_novel_dir / "notes"
        if not notes_dir.exists():
            return
        
        for note_file in sorted(notes_dir.glob("*.md"), reverse=True):
            title = note_file.stem
            # 尝试读取第一行作为标题
            try:
                first_line = note_file.read_text(encoding='utf-8').split('\n')[0][:50]
                if first_line:
                    title = first_line.lstrip('# ')
            except Exception:
                pass
            self.note_listbox.insert(tk.END, f"📝 {title}")
    
    def _on_note_select(self: 'NovelWriterApp', event):
        """笔记选择事件"""
        if not hasattr(self, 'note_listbox') or not self.current_novel_dir:
            return
        
        selection = self.note_listbox.curselection()
        if not selection:
            return
        
        note_title = self.note_listbox.get(selection[0]).lstrip('📝 ')
        
        # 查找对应的笔记文件
        notes_dir = self.current_novel_dir / "notes"
        for note_file in notes_dir.glob("*.md"):
            if note_file.stem == note_title or note_title in note_file.read_text(encoding='utf-8').split('\n')[0]:
                content = note_file.read_text(encoding='utf-8')
                if hasattr(self, 'note_text'):
                    self.note_text.delete("1.0", tk.END)
                    self.note_text.insert("1.0", content)
                self._current_note_file = note_file
                break
    
    def _add_note(self: 'NovelWriterApp'):
        """添加新笔记"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        # 创建笔记目录
        notes_dir = self.current_novel_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_file = notes_dir / f"note_{timestamp}.md"
        
        # 创建默认内容
        default_content = f"""# 新笔记

创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

"""
        
        note_file.write_text(default_content, encoding='utf-8')
        
        # 刷新列表
        self._refresh_notes()
        
        # 选中新笔记
        self.note_listbox.selection_set(0)
        self._on_note_select(None)
        
        self._log(f"[笔记] 创建新笔记: {note_file.name}")
    
    def _save_note(self: 'NovelWriterApp'):
        """保存当前笔记"""
        if not hasattr(self, '_current_note_file') or not self._current_note_file:
            messagebox.showwarning("提示", "没有选中的笔记")
            return
        
        if not hasattr(self, 'note_text'):
            return
        
        content = self.note_text.get("1.0", tk.END).strip()
        self._current_note_file.write_text(content, encoding='utf-8')
        
        self._log(f"[笔记] 笔记已保存")
        self._refresh_notes()
    
    def _delete_note(self: 'NovelWriterApp'):
        """删除当前笔记"""
        if not hasattr(self, '_current_note_file') or not self._current_note_file:
            messagebox.showwarning("提示", "没有选中的笔记")
            return
        
        if messagebox.askyesno("确认删除", "确定要删除这个笔记吗？"):
            self._current_note_file.unlink()
            self._current_note_file = None
            
            if hasattr(self, 'note_text'):
                self.note_text.delete("1.0", tk.END)
            
            self._refresh_notes()
            self._log("[笔记] 笔记已删除")
    
    def _send_sticky_to_project(self: 'NovelWriterApp'):
        """将便签内容发送到项目"""
        if not hasattr(self, 'sticky_text') or not self.current_novel_dir:
            return
        
        content = self.sticky_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "便签内容为空")
            return
        
        # 保存到项目笔记
        notes_dir = self.current_novel_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_file = notes_dir / f"sticky_{timestamp}.md"
        
        note_content = f"""# 便签

创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

{content}
"""
        
        note_file.write_text(note_content, encoding='utf-8')
        
        # 清空便签
        self.sticky_text.delete("1.0", tk.END)
        
        # 刷新笔记列表
        self._refresh_notes()
        
        self._log(f"[便签] 内容已发送到项目笔记")
        messagebox.showinfo("成功", "便签内容已保存到项目笔记！")
