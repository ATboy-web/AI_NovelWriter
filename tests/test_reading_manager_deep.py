"""
reading_manager.py 深度测试 - 真正调用方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.reading_manager import ReadingManager


class TestReadingManagerDeep:
    """ReadingManager 深度测试"""

    def test_init(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.books_dir == tmp_path / "books"
        assert rm.books_dir.exists()

    def test_get_supported_formats(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        formats = rm.get_supported_formats()
        assert ".txt" in formats
        assert ".epub" in formats
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".md" in formats

    def test_import_book_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        result = rm.import_book("/nonexistent/file.txt")
        assert result is None

    def test_import_book_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.xyz"
        test_file.write_text("test")
        result = rm.import_book(str(test_file))
        assert result is None

    def test_import_book_txt(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("这是测试内容\n第二行\n第三行")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_book_md(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.md"
        test_file.write_text("# 测试标题\n\n这是测试内容")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_book_empty(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_book_unicode(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("中文内容\n🎮📚\n日文: こんにちは")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_book_large(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "large.txt"
        test_file.write_text("测试内容\n" * 10000)
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_import_book_special_chars_filename(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "测试文件 (1) [副本].txt"
        test_file.write_text("测试内容")
        result = rm.import_book(str(test_file))
        assert result is not None

    def test_default_settings(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.font_size == 16
        assert rm.font_family == "微软雅黑"
        assert rm.line_spacing == 1.5
        assert rm.theme == "light"

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

    def test_supported_formats_descriptions(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert ReadingManager.SUPPORTED_FORMATS[".txt"] == "TXT文本文件"
        assert ReadingManager.SUPPORTED_FORMATS[".epub"] == "EPUB电子书"
        assert ReadingManager.SUPPORTED_FORMATS[".pdf"] == "PDF文档"
