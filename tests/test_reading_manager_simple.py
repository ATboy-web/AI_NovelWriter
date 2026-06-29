"""
阅读管理模块简化测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from app.reading_manager import ReadingManager


class TestReadingManagerSimple:
    """ReadingManager 简化测试套件"""
    
    def test_class_exists(self):
        """测试类存在"""
        assert ReadingManager is not None
    
    def test_supported_formats(self):
        """测试支持的格式"""
        formats = ReadingManager.SUPPORTED_FORMATS
        
        assert '.txt' in formats
        assert '.epub' in formats
        assert '.pdf' in formats
        assert '.docx' in formats
        assert '.md' in formats
    
    def test_format_descriptions(self):
        """测试格式描述"""
        formats = ReadingManager.SUPPORTED_FORMATS
        
        assert formats['.txt'] == 'TXT文本文件'
        assert formats['.epub'] == 'EPUB电子书'
        assert formats['.pdf'] == 'PDF文档'
        assert formats['.docx'] == 'Word文档'
        assert formats['.md'] == 'Markdown文件'
    
    def test_has_methods(self):
        """测试方法存在"""
        assert hasattr(ReadingManager, 'get_supported_formats')
        assert hasattr(ReadingManager, 'import_book')
    
    def test_init_parameters(self):
        """测试初始化参数"""
        mock_config = MagicMock()
        mock_config.config_dir = Path("/tmp/test")
        
        # 创建临时目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config.config_dir = Path(tmpdir)
            manager = ReadingManager(mock_config)
            
            assert manager.font_size == 16
            assert manager.font_family == "微软雅黑"
            assert manager.line_spacing == 1.5
            assert manager.theme == "light"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
