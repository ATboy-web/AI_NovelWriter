"""
reading_manager.py 全量测试 - 覆盖所有方法
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.reading_manager import ReadingManager


class TestBookmarks:
    """书签测试"""

    def test_get_bookmarks_empty(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.get_bookmarks() == []

    def test_add_bookmark(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        bookmark = rm.add_bookmark("/path/to/book", 100, "测试书签")
        assert bookmark['file_path'] == "/path/to/book"
        assert bookmark['position'] == 100
        assert bookmark['title'] == "测试书签"

    def test_add_bookmark_default_title(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        bookmark = rm.add_bookmark("/path/to/book", 100)
        assert "书签" in bookmark['title']

    def test_add_multiple_bookmarks(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.add_bookmark("/path/to/book", 100, "书签1")
        rm.add_bookmark("/path/to/book", 200, "书签2")
        assert len(rm.get_bookmarks()) == 2

    def test_delete_bookmark(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        bookmark = rm.add_bookmark("/path/to/book", 100, "待删除")
        rm.delete_bookmark(bookmark['id'])
        assert len(rm.get_bookmarks()) == 0

    def test_delete_nonexistent_bookmark(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.delete_bookmark(999)  # Should not raise

    def test_bookmarks_persistence(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.add_bookmark("/path/to/book", 100, "持久化书签")
        
        rm2 = ReadingManager(mock_config)
        assert len(rm2.get_bookmarks()) == 1


class TestReadingHistory:
    """阅读历史测试"""

    def test_get_history_empty(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.get_reading_history() == []

    def test_update_progress_new(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.update_reading_progress("/path/to/book", 100, 0.5)
        history = rm.get_reading_history()
        assert len(history) == 1
        assert history[0]['progress'] == 0.5

    def test_update_progress_existing(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.update_reading_progress("/path/to/book", 100, 0.5)
        rm.update_reading_progress("/path/to/book", 200, 0.8)
        history = rm.get_reading_history()
        assert len(history) == 1
        assert history[0]['progress'] == 0.8

    def test_update_progress_multiple_books(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.update_reading_progress("/path/to/book1", 100, 0.5)
        rm.update_reading_progress("/path/to/book2", 200, 0.8)
        history = rm.get_reading_history()
        assert len(history) == 2

    def test_history_persistence(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.update_reading_progress("/path/to/book", 100, 0.5)
        
        rm2 = ReadingManager(mock_config)
        assert len(rm2.get_reading_history()) == 1


class TestGetLibraryBooks:
    """get_library_books 测试"""

    def test_empty_library(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.get_library_books() == []

    def test_with_books(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        # Create test files
        (rm.books_dir / "book1.txt").write_text("内容1", encoding="utf-8")
        (rm.books_dir / "book2.txt").write_text("内容2", encoding="utf-8")
        
        books = rm.get_library_books()
        assert len(books) == 2

    def test_ignores_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        # Create unsupported file
        (rm.books_dir / "file.xyz").write_text("内容", encoding="utf-8")
        
        books = rm.get_library_books()
        assert len(books) == 0


class TestSearchInBook:
    """search_in_book 测试"""

    def test_search_found(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("第一行\n包含关键词的行\n第三行", encoding="utf-8")
        
        results = rm.search_in_book(str(test_file), "关键词")
        assert len(results) == 1
        assert results[0]['line_number'] == 2

    def test_search_not_found(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("第一行\n第二行\n第三行", encoding="utf-8")
        
        results = rm.search_in_book(str(test_file), "不存在")
        assert len(results) == 0

    def test_search_case_insensitive(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World\nhello world\nHELLO WORLD", encoding="utf-8")
        
        results = rm.search_in_book(str(test_file), "hello")
        assert len(results) == 3

    def test_search_nonexistent_file(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        results = rm.search_in_book("/nonexistent/file.txt", "关键词")
        assert results == []


class TestExportImportBookmarks:
    """导出导入书签测试"""

    def test_export_bookmarks(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.add_bookmark("/path/to/book", 100, "书签1")
        
        export_file = tmp_path / "bookmarks_export.json"
        rm.export_bookmarks(str(export_file))
        
        assert export_file.exists()
        with open(export_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data) == 1

    def test_import_bookmarks(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        # Create import file
        import_file = tmp_path / "bookmarks_import.json"
        bookmarks = [
            {"id": 1, "file_path": "/path/to/book", "position": 100, "title": "书签1"},
            {"id": 2, "file_path": "/path/to/book", "position": 200, "title": "书签2"},
        ]
        with open(import_file, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f)
        
        rm.import_bookmarks(str(import_file))
        assert len(rm.get_bookmarks()) == 2

    def test_import_bookmarks_avoids_duplicates(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        # Add existing bookmark
        rm.add_bookmark("/path/to/book", 100, "已存在")
        
        # Import with same id
        import_file = tmp_path / "bookmarks_import.json"
        bookmarks = [
            {"id": rm.get_bookmarks()[0]['id'], "file_path": "/path/to/book", "position": 100, "title": "重复"},
            {"id": 999, "file_path": "/path/to/book", "position": 200, "title": "新书签"},
        ]
        with open(import_file, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f)
        
        rm.import_bookmarks(str(import_file))
        assert len(rm.get_bookmarks()) == 2  # Should not duplicate


class TestReadBookExtended:
    """read_book 扩展测试"""

    def test_read_txt_utf8(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("中文内容\n第二行", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert "中文内容" in content

    def test_read_md(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.md"
        test_file.write_text("# 标题\n\n内容", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert "标题" in content

    def test_read_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        content = rm.read_book("/nonexistent/file.txt")
        assert content is None

    def test_read_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert content is None

    def test_read_empty_txt(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert content is not None

    def test_read_unicode(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("中文内容 🎮📚 日文: こんにちは", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert "中文" in content


class TestImportBookExtended:
    """import_book 扩展测试"""

    def test_import_txt(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("内容", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert "title" in result
        assert "format" in result
        assert "size" in result

    def test_import_md(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.md"
        test_file.write_text("# 标题", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        result = rm.import_book("/nonexistent/file.txt")
        assert result is None

    def test_import_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is None

    def test_import_has_metadata(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("内容", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert "title" in result
        assert "format" in result
        assert "size" in result
        assert "file_path" in result
        assert "import_date" in result
        assert "last_read" in result
        assert "progress" in result


class TestReadingSettings:
    """阅读设置测试"""

    def test_default_settings(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.font_size == 16
        assert rm.font_family == "微软雅黑"
        assert rm.line_spacing == 1.5
        assert rm.theme == "light"
        assert rm.bg_color == "#f5f0e8"
        assert rm.text_color == "#2c2c2c"

    def test_modify_settings(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        rm.font_size = 20
        rm.font_family = "宋体"
        rm.line_spacing = 2.0
        rm.theme = "dark"
        assert rm.font_size == 20
        assert rm.font_family == "宋体"
        assert rm.line_spacing == 2.0
        assert rm.theme == "dark"


class TestSupportedFormats:
    """支持格式测试"""

    def test_all_formats(self):
        formats = ReadingManager.SUPPORTED_FORMATS
        assert ".txt" in formats
        assert ".epub" in formats
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".md" in formats

    def test_format_descriptions(self):
        assert ReadingManager.SUPPORTED_FORMATS[".txt"] == "TXT文本文件"
        assert ReadingManager.SUPPORTED_FORMATS[".epub"] == "EPUB电子书"
        assert ReadingManager.SUPPORTED_FORMATS[".pdf"] == "PDF文档"
        assert ReadingManager.SUPPORTED_FORMATS[".docx"] == "Word文档"
        assert ReadingManager.SUPPORTED_FORMATS[".md"] == "Markdown文件"

    def test_get_supported_formats(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        formats = rm.get_supported_formats()
        assert len(formats) == 5
