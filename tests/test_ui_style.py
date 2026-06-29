"""
UI样式管理模块测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.ui_style import UIStyle


class TestUIStyle:
    """UIStyle 测试套件"""
    
    def test_colors_defined(self):
        """测试颜色定义"""
        colors = UIStyle.COLORS
        
        assert len(colors) > 0
        
        # 验证必要的颜色
        assert 'bg_dark' in colors
        assert 'bg_medium' in colors
        assert 'bg_light' in colors
        assert 'accent' in colors
        assert 'text_primary' in colors
    
    def test_color_values_are_hex(self):
        """测试颜色值是十六进制"""
        colors = UIStyle.COLORS
        
        for key, value in colors.items():
            assert isinstance(value, str), f"{key} 应该是字符串"
            assert value.startswith('#'), f"{key} 应该以#开头"
            assert len(value) == 7, f"{key} 应该是7字符（#RRGGBB）"
    
    def test_fonts_defined(self):
        """测试字体定义"""
        fonts = UIStyle.FONTS
        
        assert 'family' in fonts
        assert 'family_mono' in fonts
        assert 'size_xs' in fonts
        assert 'size_sm' in fonts
        assert 'size_base' in fonts
        assert 'size_lg' in fonts
        assert 'size_xl' in fonts
        assert 'size_xxl' in fonts
    
    def test_font_sizes_are_integers(self):
        """测试字体大小是整数"""
        fonts = UIStyle.FONTS
        
        for key, value in fonts.items():
            if key.startswith('size_'):
                assert isinstance(value, int), f"{key} 应该是整数"
                assert value > 0, f"{key} 应该大于0"
    
    def test_font_size_ordering(self):
        """测试字体大小排序"""
        fonts = UIStyle.FONTS
        
        assert fonts['size_xs'] < fonts['size_sm']
        assert fonts['size_sm'] < fonts['size_base']
        assert fonts['size_base'] < fonts['size_lg']
        assert fonts['size_lg'] < fonts['size_xl']
        assert fonts['size_xl'] < fonts['size_xxl']
    
    def test_spacing_defined(self):
        """测试间距定义"""
        spacing = UIStyle.SPACING
        
        assert 'xs' in spacing
        assert 'sm' in spacing
        assert 'md' in spacing
        assert 'lg' in spacing
        assert 'xl' in spacing
        assert 'xxl' in spacing
    
    def test_spacing_values_are_integers(self):
        """测试间距值是整数"""
        spacing = UIStyle.SPACING
        
        for key, value in spacing.items():
            assert isinstance(value, int), f"{key} 应该是整数"
            assert value >= 0, f"{key} 应该大于等于0"
    
    def test_spacing_ordering(self):
        """测试间距排序"""
        spacing = UIStyle.SPACING
        
        assert spacing['xs'] < spacing['sm']
        assert spacing['sm'] < spacing['md']
        assert spacing['md'] < spacing['lg']
        assert spacing['lg'] < spacing['xl']
        assert spacing['xl'] < spacing['xxl']
    
    def test_color_groups(self):
        """测试颜色分组"""
        colors = UIStyle.COLORS
        
        # 背景色
        bg_colors = [k for k in colors if k.startswith('bg_')]
        assert len(bg_colors) > 0
        
        # 强调色
        accent_colors = [k for k in colors if k.startswith('accent')]
        assert len(accent_colors) > 0
        
        # 语义色
        semantic_colors = ['success', 'warning', 'error', 'info']
        for color in semantic_colors:
            assert color in colors
        
        # 文字色
        text_colors = [k for k in colors if k.startswith('text_')]
        assert len(text_colors) > 0
    
    def test_border_colors(self):
        """测试边框颜色"""
        colors = UIStyle.COLORS
        
        assert 'border' in colors
        assert 'border_light' in colors
        assert 'border_focus' in colors
    
    def test_hover_colors(self):
        """测试悬停颜色"""
        colors = UIStyle.COLORS
        
        assert 'hover' in colors
        assert 'hover_light' in colors
        assert 'bg_hover' in colors


class TestUIStyleConstants:
    """UIStyle 常量测试"""
    
    def test_font_family(self):
        """测试字体族"""
        assert UIStyle.FONTS['family'] == '微软雅黑'
        assert UIStyle.FONTS['family_mono'] == 'Consolas'
    
    def test_spacing_base(self):
        """测试间距基准"""
        # 4px基准
        assert UIStyle.SPACING['sm'] == 4
    
    def test_color_contrast(self):
        """测试颜色对比度"""
        colors = UIStyle.COLORS
        
        # 深色主题应该有浅色文字
        bg_dark = colors['bg_dark']
        text_primary = colors['text_primary']
        
        # 简单验证：背景应该比文字暗
        assert bg_dark < text_primary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
