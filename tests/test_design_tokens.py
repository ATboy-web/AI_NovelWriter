"""
设计系统测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.design_tokens import DesignTokens


class TestDesignTokens:
    """DesignTokens 测试套件"""
    
    def test_colors_defined(self):
        """测试颜色定义"""
        colors = DesignTokens.COLORS
        
        assert len(colors) > 0
        
        # 验证必要的颜色
        assert 'bg_primary' in colors
        assert 'bg_secondary' in colors
        assert 'bg_card' in colors
        assert 'primary' in colors
        assert 'text_primary' in colors
    
    def test_color_values_are_hex(self):
        """测试颜色值是十六进制"""
        colors = DesignTokens.COLORS
        
        for key, value in colors.items():
            assert isinstance(value, str), f"{key} 应该是字符串"
            assert value.startswith('#'), f"{key} 应该以#开头"
            assert len(value) == 7, f"{key} 应该是7字符（#RRGGBB）"
    
    def test_spacing_defined(self):
        """测试间距定义"""
        spacing = DesignTokens.SPACING
        
        assert 'xs' in spacing
        assert 'sm' in spacing
        assert 'md' in spacing
        assert 'lg' in spacing
        assert 'xl' in spacing
        assert '2xl' in spacing
    
    def test_spacing_values_are_integers(self):
        """测试间距值是整数"""
        spacing = DesignTokens.SPACING
        
        for key, value in spacing.items():
            assert isinstance(value, int), f"{key} 应该是整数"
            assert value >= 0, f"{key} 应该大于等于0"
    
    def test_spacing_ordering(self):
        """测试间距排序"""
        spacing = DesignTokens.SPACING
        
        assert spacing['xs'] < spacing['sm']
        assert spacing['sm'] < spacing['md']
        assert spacing['md'] < spacing['lg']
        assert spacing['lg'] < spacing['xl']
        assert spacing['xl'] < spacing['2xl']
    
    def test_radius_defined(self):
        """测试圆角定义"""
        radius = DesignTokens.RADIUS
        
        assert 'sm' in radius
        assert 'md' in radius
        assert 'lg' in radius
        assert 'xl' in radius
        assert 'full' in radius
    
    def test_radius_values(self):
        """测试圆角值"""
        radius = DesignTokens.RADIUS
        
        assert radius['sm'] == 4
        assert radius['md'] == 8
        assert radius['lg'] == 12
        assert radius['xl'] == 16
        assert radius['full'] == 9999
    
    def test_fonts_defined(self):
        """测试字体定义"""
        fonts = DesignTokens.FONTS
        
        assert 'family' in fonts
        assert 'mono' in fonts
        assert 'sizes' in fonts
    
    def test_font_sizes_defined(self):
        """测试字体大小定义"""
        sizes = DesignTokens.FONTS['sizes']
        
        assert 'xs' in sizes
        assert 'sm' in sizes
        assert 'md' in sizes
        assert 'lg' in sizes
        assert 'xl' in sizes
        assert '2xl' in sizes
    
    def test_font_size_values(self):
        """测试字体大小值"""
        sizes = DesignTokens.FONTS['sizes']
        
        assert sizes['xs'] == 10
        assert sizes['sm'] == 11
        assert sizes['md'] == 13
        assert sizes['lg'] == 15
        assert sizes['xl'] == 18
        assert sizes['2xl'] == 24
    
    def test_font_size_ordering(self):
        """测试字体大小排序"""
        sizes = DesignTokens.FONTS['sizes']
        
        assert sizes['xs'] < sizes['sm']
        assert sizes['sm'] < sizes['md']
        assert sizes['md'] < sizes['lg']
        assert sizes['lg'] < sizes['xl']
        assert sizes['xl'] < sizes['2xl']


class TestDesignTokensComponents:
    """组件样式测试"""
    
    def test_button_primary_defined(self):
        """测试主按钮样式"""
        button = DesignTokens.BUTTON_PRIMARY
        
        assert 'bg' in button
        assert 'fg' in button
        assert 'hover_bg' in button
        assert 'radius' in button
        assert 'padx' in button
        assert 'pady' in button
        assert 'font_size' in button
    
    def test_button_secondary_defined(self):
        """测试次按钮样式"""
        button = DesignTokens.BUTTON_SECONDARY
        
        assert 'bg' in button
        assert 'fg' in button
        assert 'hover_bg' in button
        assert 'border' in button
        assert 'radius' in button
    
    def test_button_danger_defined(self):
        """测试危险按钮样式"""
        button = DesignTokens.BUTTON_DANGER
        
        assert 'bg' in button
        assert 'fg' in button
        assert 'hover_bg' in button
        assert 'radius' in button
    
    def test_card_defined(self):
        """测试卡片样式"""
        card = DesignTokens.CARD
        
        assert 'bg' in card
        assert 'border' in card
        assert 'radius' in card
        assert 'pad' in card
    
    def test_avatar_defined(self):
        """测试头像样式"""
        avatar = DesignTokens.AVATAR
        
        assert 'size' in avatar
        assert 'radius' in avatar
        assert 'font_size' in avatar
        assert 'font_weight' in avatar
    
    def test_button_colors_reference(self):
        """测试按钮颜色引用"""
        primary = DesignTokens.BUTTON_PRIMARY
        colors = DesignTokens.COLORS
        
        # 主按钮应该使用主色调
        assert primary['bg'] == colors['primary']
        assert primary['fg'] == colors['text_inverse']
        assert primary['hover_bg'] == colors['primary_hover']
    
    def test_button_radius_reference(self):
        """测试按钮圆角引用"""
        primary = DesignTokens.BUTTON_PRIMARY
        radius = DesignTokens.RADIUS
        
        assert primary['radius'] == radius['md']
    
    def test_card_colors_reference(self):
        """测试卡片颜色引用"""
        card = DesignTokens.CARD
        colors = DesignTokens.COLORS
        
        assert card['bg'] == colors['bg_card']
        assert card['border'] == colors['border']
    
    def test_card_radius_reference(self):
        """测试卡片圆角引用"""
        card = DesignTokens.CARD
        radius = DesignTokens.RADIUS
        
        assert card['radius'] == radius['md']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
