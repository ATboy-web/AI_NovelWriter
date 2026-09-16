"""笔记层：笔记增删改查、便签发送到项目

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import tkinter as tk
from tkinter import messagebox


class NoteUIMixin:
    """笔记层：笔记增删改查、便签发送到项目"""

    def _refresh_notes(self):
        """刷新笔记列表"""
        self.notes_list.delete(0, tk.END)
        note_type = self.note_type_var.get()

        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            for n in notes:
                self.notes_list.insert(tk.END, f"{n.get('title', '无标题')}")
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            for n in notes:
                self.notes_list.insert(tk.END, f"[位置{n.get('position', 0)}] {n.get('content', '')[:30]}")
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            for n in notes:
                self.notes_list.insert(tk.END, f"{n.get('content', '')[:40]}")

    def _on_note_select(self, event):
        """笔记选中"""
        selection = self.notes_list.curselection()
        if not selection:
            return
        idx = selection[0]
        note_type = self.note_type_var.get()

        notes = []
        if note_type == "project":
            notes = self.note_manager.get_project_notes()
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()

        if idx < len(notes):
            self.note_content.delete("1.0", tk.END)
            self.note_content.insert("1.0", notes[idx].get("content", ""))

    def _add_note(self):
        """新建笔记"""
        note_type = self.note_type_var.get()
        content = "新笔记内容..."

        if note_type == "project":
            self.note_manager.add_project_note("新笔记", content)
        elif note_type == "doc":
            self.note_manager.add_doc_note(self.current_chapter, content)
        elif note_type == "sticky":
            self.note_manager.add_sticky_note(content)

        self._refresh_notes()

    def _save_note(self):
        """保存当前笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个笔记")
            return

        idx = selection[0]
        note_type = self.note_type_var.get()
        content = self.note_content.get("1.0", tk.END).strip()

        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            if idx < len(notes):
                self.note_manager.update_project_note(notes[idx]["id"], content=content)
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            if idx < len(notes):
                notes[idx]["content"] = content
                self.note_manager.save_doc_notes(self.current_chapter, notes)
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            if idx < len(notes):
                notes[idx]["content"] = content
                self.note_manager.save_sticky_notes(notes)

        self._log("笔记已保存")

    def _delete_note(self):
        """删除笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            return

        if not messagebox.askyesno("确认", "确定删除此笔记？"):
            return

        idx = selection[0]
        note_type = self.note_type_var.get()

        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            if idx < len(notes):
                self.note_manager.delete_project_note(notes[idx]["id"])
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            if idx < len(notes):
                self.note_manager.delete_doc_note(self.current_chapter, notes[idx]["id"])
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            if idx < len(notes):
                self.note_manager.delete_sticky_note(notes[idx]["id"])

        self.note_content.delete("1.0", tk.END)
        self._refresh_notes()

    def _send_sticky_to_project(self):
        """将便笺发送到工程笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个便笺")
            return

        idx = selection[0]
        if self.note_type_var.get() != "sticky":
            messagebox.showinfo("提示", "请先切换到便笺本")
            return

        notes = self.note_manager.get_sticky_notes()
        if idx < len(notes):
            self.note_manager.send_sticky_to_project(notes[idx]["id"])
            self._log("便笺已发送到工程笔记")
            messagebox.showinfo("成功", "便笺已发送到工程笔记")
