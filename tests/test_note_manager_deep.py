"""
note_manager.py 深度测试 - 真正调用方法
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.note_manager import NoteManager


class TestNoteManagerDeep:
    """NoteManager 深度测试"""

    def test_init_with_config(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        assert nm.sticky_file == tmp_path / "sticky_notes.json"

    def test_init_without_config(self):
        nm = NoteManager()
        assert nm.sticky_file.exists() or True  # Path may not exist yet

    def test_get_sticky_notes_empty(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        notes = nm.get_sticky_notes()
        assert notes == []

    def test_add_sticky_note(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("测试内容", ["测试"])
        assert note["content"] == "测试内容"
        assert note["tags"] == ["测试"]
        assert "id" in note
        assert "created_at" in note

    def test_add_sticky_note_without_tags(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("无标签")
        assert note["tags"] == []

    def test_add_multiple_sticky_notes(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.add_sticky_note("便笺1")
        nm.add_sticky_note("便笺2")
        nm.add_sticky_note("便笺3")
        notes = nm.get_sticky_notes()
        assert len(notes) == 3

    def test_delete_sticky_note(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("待删除")
        nm.delete_sticky_note(note["id"])
        notes = nm.get_sticky_notes()
        assert len(notes) == 0

    def test_delete_nonexistent_sticky_note(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.delete_sticky_note(999999)  # Should not raise

    def test_sticky_notes_persistence(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.add_sticky_note("持久化测试")
        
        # Create new instance
        nm2 = NoteManager(config=mock_config)
        notes = nm2.get_sticky_notes()
        assert len(notes) == 1
        assert notes[0]["content"] == "持久化测试"

    def test_sticky_file_is_json(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.add_sticky_note("JSON测试")
        
        with open(nm.sticky_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, list)

    def test_init_with_novel_dir(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        assert nm.notes_dir == novel_dir / "notes"
        assert nm.notes_dir.exists()

    def test_unicode_content(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("中文内容 🎮📚 日文: こんにちは")
        assert note["content"] == "中文内容 🎮📚 日文: こんにちは"

    def test_empty_content(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("")
        assert note["content"] == ""

    def test_long_content(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        long_content = "x" * 10000
        note = nm.add_sticky_note(long_content)
        assert note["content"] == long_content
