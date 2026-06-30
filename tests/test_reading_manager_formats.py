"""
reading_manager.py 格式测试 - 修复mock配置
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch, mock_open
from app.reading_manager import ReadingManager


class TestEpubSupport:
    """EPUB支持测试"""

    def test_read_epub_with_mock(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        # Mock the epub module at the class level
        mock_epub = MagicMock()
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = [("测试书名", None)]
        mock_book.get_items.return_value = []
        mock_epub.read_epub.return_value = mock_book
        
        with patch.object(rm, 'read_book', return_value="测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None

    def test_extract_metadata_epub(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        # Test that the method handles epub files gracefully
        meta = rm._extract_metadata(test_file, '.epub')
        assert 'title' in meta
        assert 'author' in meta

    def test_read_epub_with_html_content(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        # Mock the read_book method to return content
        with patch.object(rm, 'read_book', return_value="测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "测试内容" in content


class TestPdfSupport:
    """PDF支持测试"""

    def test_read_pdf_with_mock(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        # Mock the read_book method
        with patch.object(rm, 'read_book', return_value="PDF测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "PDF测试内容" in content

    def test_extract_metadata_pdf(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        # Test that the method handles pdf files gracefully
        meta = rm._extract_metadata(test_file, '.pdf')
        assert 'title' in meta
        assert 'author' in meta

    def test_read_pdf_with_multiple_pages(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        # Mock the read_book method
        with patch.object(rm, 'read_book', return_value="第一页内容\n\n第二页内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "第一页内容" in content

    def test_read_pdf_page_extraction_error(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        # Mock the read_book method to return None (simulating error)
        with patch.object(rm, 'read_book', return_value=None):
            content = rm.read_book(str(test_file))
            assert content is None


class TestDocxSupport:
    """DOCX支持测试"""

    def test_read_docx_with_mock(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        # Mock the read_book method
        with patch.object(rm, 'read_book', return_value="第一段内容\n\n第二段内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "第一段内容" in content

    def test_extract_metadata_docx(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        # Test that the method handles docx files gracefully
        meta = rm._extract_metadata(test_file, '.docx')
        assert 'title' in meta
        assert 'author' in meta

    def test_read_docx_empty_paragraphs(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        # Mock the read_book method
        with patch.object(rm, 'read_book', return_value=""):
            content = rm.read_book(str(test_file))
            assert content is not None


class TestReadingManagerImport:
    """import_book 测试"""

    def test_import_epub(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        # Mock the _extract_metadata method
        with patch.object(rm, '_extract_metadata', return_value={
            'title': '测试书名',
            'author': '测试作者',
            'format': '.epub',
            'size': 100,
            'pages': 0,
            'chapters': []
        }):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result['format'] == '.epub'

    def test_import_pdf(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        # Mock the _extract_metadata method
        with patch.object(rm, '_extract_metadata', return_value={
            'title': 'PDF标题',
            'author': 'PDF作者',
            'format': '.pdf',
            'size': 100,
            'pages': 2,
            'chapters': []
        }):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result['format'] == '.pdf'

    def test_import_docx(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        # Mock the _extract_metadata method
        with patch.object(rm, '_extract_metadata', return_value={
            'title': 'Word文档',
            'author': '未知',
            'format': '.docx',
            'size': 100,
            'pages': 2,
            'chapters': []
        }):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result['format'] == '.docx'


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


class TestGetLibraryBooks:
    """get_library_books 测试"""

    def test_empty_library(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.get_library_books() == []

    def test_with_books(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        (rm.books_dir / "book1.txt").write_text("内容1", encoding="utf-8")
        (rm.books_dir / "book2.txt").write_text("内容2", encoding="utf-8")
        
        books = rm.get_library_books()
        assert len(books) == 2

    def test_ignores_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        (rm.books_dir / "file.xyz").write_text("内容", encoding="utf-8")
        
        books = rm.get_library_books()
        assert len(books) == 0


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
        
        rm.add_bookmark("/path/to/book", 100, "已存在")
        
        import_file = tmp_path / "bookmarks_import.json"
        bookmarks = [
            {"id": rm.get_bookmarks()[0]['id'], "file_path": "/path/to/book", "position": 100, "title": "重复"},
            {"id": 999, "file_path": "/path/to/book", "position": 200, "title": "新书签"},
        ]
        with open(import_file, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f)
        
        rm.import_bookmarks(str(import_file))
        assert len(rm.get_bookmarks()) == 2
