"""
note_manager.py 全量测试 - 覆盖project notes和doc notes
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.note_manager import NoteManager


class TestStickyNotes:
    """便笺测试"""

    def test_get_empty(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        assert nm.get_sticky_notes() == []

    def test_add(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("内容", ["标签"])
        assert note["content"] == "内容"
        assert note["tags"] == ["标签"]

    def test_add_no_tags(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("内容")
        assert note["tags"] == []

    def test_add_multiple(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.add_sticky_note("1")
        nm.add_sticky_note("2")
        nm.add_sticky_note("3")
        assert len(nm.get_sticky_notes()) == 3

    def test_delete(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("删除")
        nm.delete_sticky_note(note["id"])
        assert len(nm.get_sticky_notes()) == 0

    def test_delete_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.delete_sticky_note(999)  # Should not raise

    def test_persistence(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.add_sticky_note("持久化")
        nm2 = NoteManager(config=mock_config)
        assert len(nm2.get_sticky_notes()) == 1

    def test_save_sticky_notes(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.save_sticky_notes([{"id": 1, "content": "手动保存"}])
        assert len(nm.get_sticky_notes()) == 1


class TestProjectNotes:
    """工程笔记测试"""

    def test_get_empty_no_novel_dir(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        assert nm.get_project_notes() == []

    def test_get_empty_with_novel_dir(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        assert nm.get_project_notes() == []

    def test_add_project_note(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_project_note("标题", "内容")
        assert note["title"] == "标题"
        assert note["content"] == "内容"

    def test_add_multiple_project_notes(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        nm.add_project_note("标题1", "内容1")
        nm.add_project_note("标题2", "内容2")
        assert len(nm.get_project_notes()) == 2

    def test_update_project_note(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_project_note("原标题", "原内容")
        nm.update_project_note(note["id"], title="新标题", content="新内容")
        notes = nm.get_project_notes()
        assert notes[0]["title"] == "新标题"
        assert notes[0]["content"] == "新内容"

    def test_update_project_note_title_only(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_project_note("原标题", "原内容")
        nm.update_project_note(note["id"], title="新标题")
        notes = nm.get_project_notes()
        assert notes[0]["title"] == "新标题"
        assert notes[0]["content"] == "原内容"

    def test_delete_project_note(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_project_note("删除", "内容")
        nm.delete_project_note(note["id"])
        assert len(nm.get_project_notes()) == 0

    def test_save_project_notes_no_novel_dir(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.save_project_notes([{"id": 1}])  # Should not raise


class TestDocNotes:
    """文档笔记测试"""

    def test_get_empty_no_novel_dir(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        assert nm.get_doc_notes(1) == []

    def test_get_empty_with_novel_dir(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        assert nm.get_doc_notes(1) == []

    def test_add_doc_note(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_doc_note(1, "内容", position=100)
        assert note["content"] == "内容"
        assert note["position"] == 100

    def test_add_multiple_doc_notes(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        nm.add_doc_note(1, "笔记1")
        nm.add_doc_note(1, "笔记2")
        assert len(nm.get_doc_notes(1)) == 2

    def test_delete_doc_note(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_doc_note(1, "删除")
        nm.delete_doc_note(1, note["id"])
        assert len(nm.get_doc_notes(1)) == 0

    def test_save_doc_notes_no_novel_dir(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        nm.save_doc_notes(1, [{"id": 1}])  # Should not raise


class TestSendStickyToProject:
    """send_sticky_to_project 测试"""

    def test_send(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        note = nm.add_sticky_note("发送到工程")
        nm.send_sticky_to_project(note["id"])
        assert len(nm.get_project_notes()) == 1

    def test_send_nonexistent(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        nm.send_sticky_to_project(999)  # Should not raise

    def test_send_no_novel_dir(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        note = nm.add_sticky_note("发送")
        nm.send_sticky_to_project(note["id"])  # Should not raise


class TestNoteManagerInit:
    """初始化测试"""

    def test_init_with_config(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(config=mock_config)
        assert nm.sticky_file == tmp_path / "sticky_notes.json"

    def test_init_without_config(self):
        nm = NoteManager()
        assert nm.sticky_file is not None

    def test_init_with_novel_dir(self, tmp_path):
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        nm = NoteManager(novel_dir=novel_dir, config=mock_config)
        assert nm.notes_dir.exists()
        assert nm.doc_notes_dir.exists()
