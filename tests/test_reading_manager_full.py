"""
reading_manager.py 全量测试 - 覆盖read_book和extract_metadata
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.reading_manager import ReadingManager


class TestReadBook:
    """read_book 深度测试"""

    def test_read_txt(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("第一行\n第二行\n第三行", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert content is not None
        assert "第一行" in content

    def test_read_md(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.md"
        test_file.write_text("# 标题\n\n内容", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert content is not None
        assert "标题" in content

    def test_read_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        content = rm.read_book("/nonexistent/file.txt")
        assert content is None

    def test_read_unsupported_format(self, tmp_path):
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

    def test_read_unicode_txt(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("中文内容 🎮📚", encoding="utf-8")
        content = rm.read_book(str(test_file))
        assert content is not None
        assert "中文" in content


class TestImportBookMetadata:
    """import_book 元数据测试"""

    def test_import_txt_has_metadata(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("第一章 开始\n\n内容", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert "title" in result
        assert "format" in result
        assert "size" in result

    def test_import_md_has_metadata(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.md"
        test_file.write_text("# 标题\n\n内容", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert "title" in result

    def test_import_nonexistent(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        result = rm.import_book("/nonexistent/file.txt")
        assert result is None

    def test_import_has_format(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert result["format"] == ".txt"

    def test_import_has_size(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.txt"
        test_file.write_text("12345", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is not None
        assert result["size"] > 0


class TestImportBookExtended:
    """import_book 扩展测试"""

    def test_import_txt_creates_metadata(self, tmp_path):
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

    def test_import_unsupported(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content", encoding="utf-8")
        result = rm.import_book(str(test_file))
        assert result is None


class TestReadingSettings:
    """阅读设置测试"""

    def test_default_font_size(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.font_size == 16

    def test_default_font_family(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.font_family == "微软雅黑"

    def test_default_line_spacing(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
        assert rm.line_spacing == 1.5

    def test_default_theme(self, tmp_path):
        mock_config = type('Config', (), {'config_dir': tmp_path})()
        rm = ReadingManager(mock_config)
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
