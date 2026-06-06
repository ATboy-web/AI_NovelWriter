"""
笔记管理模块 - 文档笔记、工程笔记、便笺本
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .config import AppConfig


class NoteManager:
    """笔记管理器 - 文档笔记、工程笔记、便笺本"""
    
    def __init__(self, novel_dir: Optional[Path] = None, config: Optional[AppConfig] = None):
        self.novel_dir = novel_dir
        self.config = config
        
        # 便笺本（全局共享）
        if config:
            self.sticky_file = config.config_dir / "sticky_notes.json"
        else:
            self.sticky_file = Path.home() / ".ai_novel_writer" / "sticky_notes.json"
        
        # 工程笔记和文档笔记在 novel_dir 下
        if novel_dir:
            self.notes_dir = novel_dir / "notes"
            self.notes_dir.mkdir(exist_ok=True)
            self.project_note_file = self.notes_dir / "_project_notes.json"
            self.doc_notes_dir = self.notes_dir / "docs"
            self.doc_notes_dir.mkdir(exist_ok=True)
    
    # ===== 便笺本（全局）=====
    
    def get_sticky_notes(self) -> List[Dict]:
        if self.sticky_file.exists():
            with open(self.sticky_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_sticky_notes(self, notes: List[Dict]):
        with open(self.sticky_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_sticky_note(self, content: str, tags: List[str] = None) -> Dict:
        notes = self.get_sticky_notes()
        note = {
            "id": int(time.time() * 1000),
            "content": content,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_sticky_notes(notes)
        return note
    
    def delete_sticky_note(self, note_id: int):
        notes = self.get_sticky_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_sticky_notes(notes)
    
    # ===== 工程笔记 =====
    
    def get_project_notes(self) -> List[Dict]:
        if not self.novel_dir:
            return []
        if self.project_note_file.exists():
            with open(self.project_note_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_project_notes(self, notes: List[Dict]):
        if not self.novel_dir:
            return
        with open(self.project_note_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_project_note(self, title: str, content: str) -> Dict:
        notes = self.get_project_notes()
        note = {
            "id": int(time.time() * 1000),
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_project_notes(notes)
        return note
    
    def update_project_note(self, note_id: int, title: str = None, content: str = None):
        notes = self.get_project_notes()
        for n in notes:
            if n.get("id") == note_id:
                if title is not None:
                    n["title"] = title
                if content is not None:
                    n["content"] = content
                n["updated_at"] = datetime.now().isoformat()
                break
        self.save_project_notes(notes)
    
    def delete_project_note(self, note_id: int):
        notes = self.get_project_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_project_notes(notes)
    
    # ===== 文档笔记 =====
    
    def get_doc_notes(self, chapter_num: int) -> List[Dict]:
        if not self.novel_dir:
            return []
        note_file = self.doc_notes_dir / f"chapter_{chapter_num:04d}.json"
        if note_file.exists():
            with open(note_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_doc_notes(self, chapter_num: int, notes: List[Dict]):
        if not self.novel_dir:
            return
        note_file = self.doc_notes_dir / f"chapter_{chapter_num:04d}.json"
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_doc_note(self, chapter_num: int, content: str, position: int = 0) -> Dict:
        notes = self.get_doc_notes(chapter_num)
        note = {
            "id": int(time.time() * 1000),
            "content": content,
            "position": position,
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_doc_notes(chapter_num, notes)
        return note
    
    def delete_doc_note(self, chapter_num: int, note_id: int):
        notes = self.get_doc_notes(chapter_num)
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_doc_notes(chapter_num, notes)
    
    # ===== 便笺发送到工程 =====
    
    def send_sticky_to_project(self, note_id: int, target: str = "project"):
        """将便笺内容发送到工程笔记"""
        sticky_notes = self.get_sticky_notes()
        note = None
        for n in sticky_notes:
            if n.get("id") == note_id:
                note = n
                break
        if note and self.novel_dir:
            self.add_project_note(
                title=f"来自便笺 - {note['content'][:20]}",
                content=note["content"]
            )
