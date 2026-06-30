"""
reading_manager.py epub/pdf/docx测试 - 使用mock库
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
        
        with patch('app.reading_manager.EPUB_SUPPORT', True):
            with patch('app.reading_manager.epub') as mock_epub:
                mock_book = MagicMock()
                mock_book.get_metadata.return_value = [("测试书名", None)]
                mock_book.get_items.return_value = []
                mock_epub.read_epub.return_value = mock_book
                
                content = rm.read_book(str(test_file))
                assert content is not None

    def test_extract_metadata_epub(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        with patch('app.reading_manager.EPUB_SUPPORT', True):
            with patch('app.reading_manager.epub') as mock_epub:
                mock_book = MagicMock()
                mock_book.get_metadata.side_effect = lambda ns, key: {
                    'DC': {'title': [('测试书名', None)], 'creator': [('测试作者', None)]}
                }.get(ns, {}).get(key, [])
                
                mock_item = MagicMock()
                mock_item.get_type.return_value = 9
                mock_item.get_name.return_value = "chapter1.html"
                mock_book.get_items.return_value = [mock_item]
                
                mock_epub.read_epub.return_value = mock_book
                
                meta = rm._extract_metadata(test_file, '.epub')
                assert meta['title'] == '测试书名'
                assert meta['author'] == '测试作者'

    def test_read_epub_with_html_content(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        with patch('app.reading_manager.EPUB_SUPPORT', True):
            with patch('app.reading_manager.epub') as mock_epub:
                mock_book = MagicMock()
                mock_book.get_metadata.return_value = []
                
                mock_item = MagicMock()
                mock_item.get_type.return_value = 9
                mock_item.get_content.return_value = '<html><body><p>测试内容</p></body></html>'.encode('utf-8')
                mock_book.get_items.return_value = [mock_item]
                
                mock_epub.read_epub.return_value = mock_book
                
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
        
        with patch('app.reading_manager.PDF_SUPPORT', True):
            with patch('app.reading_manager.PyPDF2') as mock_pypdf2:
                mock_reader = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "PDF测试内容"
                mock_reader.pages = [mock_page]
                mock_reader.metadata = None
                mock_pypdf2.PdfReader.return_value = mock_reader
                
                content = rm.read_book(str(test_file))
                assert content is not None
                assert "PDF测试内容" in content

    def test_extract_metadata_pdf(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        with patch('app.reading_manager.PDF_SUPPORT', True):
            with patch('app.reading_manager.PyPDF2') as mock_pypdf2:
                mock_reader = MagicMock()
                mock_reader.pages = [MagicMock(), MagicMock()]
                mock_reader.metadata = MagicMock()
                mock_reader.metadata.title = "PDF标题"
                mock_reader.metadata.author = "PDF作者"
                mock_pypdf2.PdfReader.return_value = mock_reader
                
                meta = rm._extract_metadata(test_file, '.pdf')
                assert meta['title'] == 'PDF标题'
                assert meta['author'] == 'PDF作者'
                assert meta['pages'] == 2

    def test_read_pdf_with_multiple_pages(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        with patch('app.reading_manager.PDF_SUPPORT', True):
            with patch('app.reading_manager.PyPDF2') as mock_pypdf2:
                mock_reader = MagicMock()
                mock_page1 = MagicMock()
                mock_page1.extract_text.return_value = "第一页内容"
                mock_page2 = MagicMock()
                mock_page2.extract_text.return_value = "第二页内容"
                mock_reader.pages = [mock_page1, mock_page2]
                mock_reader.metadata = None
                mock_pypdf2.PdfReader.return_value = mock_reader
                
                content = rm.read_book(str(test_file))
                assert content is not None
                assert "第一页内容" in content
                assert "第二页内容" in content

    def test_read_pdf_page_extraction_error(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        with patch('app.reading_manager.PDF_SUPPORT', True):
            with patch('app.reading_manager.PyPDF2') as mock_pypdf2:
                mock_reader = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.side_effect = Exception("extraction error")
                mock_reader.pages = [mock_page]
                mock_reader.metadata = None
                mock_pypdf2.PdfReader.return_value = mock_reader
                
                content = rm.read_book(str(test_file))
                assert content is not None


class TestDocxSupport:
    """DOCX支持测试"""

    def test_read_docx_with_mock(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        with patch('app.reading_manager.DOCX_SUPPORT', True):
            with patch('app.reading_manager.Document') as mock_doc_class:
                mock_doc = MagicMock()
                mock_para1 = MagicMock()
                mock_para1.text = "第一段内容"
                mock_para2 = MagicMock()
                mock_para2.text = "第二段内容"
                mock_para3 = MagicMock()
                mock_para3.text = ""
                mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
                mock_doc_class.return_value = mock_doc
                
                content = rm.read_book(str(test_file))
                assert content is not None
                assert "第一段内容" in content
                assert "第二段内容" in content

    def test_extract_metadata_docx(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        with patch('app.reading_manager.DOCX_SUPPORT', True):
            with patch('app.reading_manager.Document') as mock_doc_class:
                mock_doc = MagicMock()
                mock_doc.paragraphs = [MagicMock() for _ in range(100)]
                mock_doc_class.return_value = mock_doc
                
                meta = rm._extract_metadata(test_file, '.docx')
                assert meta['pages'] == 2  # 100 // 50

    def test_read_docx_empty_paragraphs(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        with patch('app.reading_manager.DOCX_SUPPORT', True):
            with patch('app.reading_manager.Document') as mock_doc_class:
                mock_doc = MagicMock()
                mock_para = MagicMock()
                mock_para.text = ""
                mock_doc.paragraphs = [mock_para]
                mock_doc_class.return_value = mock_doc
                
                content = rm.read_book(str(test_file))
                assert content is not None


class TestReadingManagerImport:
    """import_book 测试"""

    def test_import_epub(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")
        
        with patch('app.reading_manager.EPUB_SUPPORT', True):
            with patch('app.reading_manager.epub') as mock_epub:
                mock_book = MagicMock()
                mock_book.get_metadata.return_value = [("测试书名", None)]
                mock_book.get_items.return_value = []
                mock_epub.read_epub.return_value = mock_book
                
                result = rm.import_book(str(test_file))
                assert result is not None
                assert result['format'] == '.epub'

    def test_import_pdf(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")
        
        with patch('app.reading_manager.PDF_SUPPORT', True):
            with patch('app.reading_manager.PyPDF2') as mock_pypdf2:
                mock_reader = MagicMock()
                mock_reader.pages = [MagicMock()]
                mock_reader.metadata = MagicMock()
                mock_reader.metadata.title = "PDF标题"
                mock_reader.metadata.author = "PDF作者"
                mock_pypdf2.PdfReader.return_value = mock_reader
                
                result = rm.import_book(str(test_file))
                assert result is not None
                assert result['format'] == '.pdf'

    def test_import_docx(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")
        
        with patch('app.reading_manager.DOCX_SUPPORT', True):
            with patch('app.reading_manager.Document') as mock_doc_class:
                mock_doc = MagicMock()
                mock_doc.paragraphs = [MagicMock() for _ in range(100)]
                mock_doc_class.return_value = mock_doc
                
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
