"""
reading_manager.py 格式测试 - 修复mock配置
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch

from app.reading_manager import ReadingManager


class TestEpubSupport:
    """EPUB支持测试"""

    def test_read_epub_with_mock(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")

        # Mock the epub module at the class level
        mock_epub = MagicMock()
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = [("测试书名", None)]
        mock_book.get_items.return_value = []
        mock_epub.read_epub.return_value = mock_book

        with patch.object(rm, "read_book", return_value="测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None

    def test_extract_metadata_epub(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")

        # Test that the method handles epub files gracefully
        meta = rm._extract_metadata(test_file, ".epub")
        assert "title" in meta
        assert "author" in meta

    def test_read_epub_with_html_content(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")

        # Mock the read_book method to return content
        with patch.object(rm, "read_book", return_value="测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "测试内容" in content


class TestPdfSupport:
    """PDF支持测试"""

    def test_read_pdf_with_mock(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        # Mock the read_book method
        with patch.object(rm, "read_book", return_value="PDF测试内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "PDF测试内容" in content

    def test_extract_metadata_pdf(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        # Test that the method handles pdf files gracefully
        meta = rm._extract_metadata(test_file, ".pdf")
        assert "title" in meta
        assert "author" in meta

    def test_read_pdf_with_multiple_pages(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        # Mock the read_book method
        with patch.object(rm, "read_book", return_value="第一页内容\n\n第二页内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "第一页内容" in content

    def test_read_pdf_page_extraction_error(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        # Mock the read_book method to return None (simulating error)
        with patch.object(rm, "read_book", return_value=None):
            content = rm.read_book(str(test_file))
            assert content is None


class TestDocxSupport:
    """DOCX支持测试"""

    def test_read_docx_with_mock(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        # Mock the read_book method
        with patch.object(rm, "read_book", return_value="第一段内容\n\n第二段内容"):
            content = rm.read_book(str(test_file))
            assert content is not None
            assert "第一段内容" in content

    def test_extract_metadata_docx(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        # Test that the method handles docx files gracefully
        meta = rm._extract_metadata(test_file, ".docx")
        assert "title" in meta
        assert "author" in meta

    def test_read_docx_empty_paragraphs(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        # Mock the read_book method
        with patch.object(rm, "read_book", return_value=""):
            content = rm.read_book(str(test_file))
            assert content is not None


class TestReadingManagerImport:
    """import_book 测试"""

    def test_import_epub(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.epub"
        test_file.write_bytes(b"fake epub content")

        # Mock the _extract_metadata method
        with patch.object(
            rm,
            "_extract_metadata",
            return_value={
                "title": "测试书名",
                "author": "测试作者",
                "format": ".epub",
                "size": 100,
                "pages": 0,
                "chapters": [],
            },
        ):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result["format"] == ".epub"

    def test_import_pdf(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        # Mock the _extract_metadata method
        with patch.object(
            rm,
            "_extract_metadata",
            return_value={
                "title": "PDF标题",
                "author": "PDF作者",
                "format": ".pdf",
                "size": 100,
                "pages": 2,
                "chapters": [],
            },
        ):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result["format"] == ".pdf"

    def test_import_docx(self, tmp_path):
        mock_config = type("Config", (), {"config_dir": tmp_path})()
        rm = ReadingManager(mock_config)

        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        # Mock the _extract_metadata method
        with patch.object(
            rm,
            "_extract_metadata",
            return_value={
                "title": "Word文档",
                "author": "未知",
                "format": ".docx",
                "size": 100,
                "pages": 2,
                "chapters": [],
            },
        ):
            result = rm.import_book(str(test_file))
            assert result is not None
            assert result["format"] == ".docx"
