"""
名场面检测器测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.scene_detector import CinematicPromptGenerator


class TestCinematicPromptGenerator:
    """CinematicPromptGenerator 测试套件"""
    
    def test_aspect_ratios_defined(self):
        """测试画面比例定义"""
        ratios = CinematicPromptGenerator.ASPECT_RATIOS
        
        assert "portrait" in ratios
        assert "portrait_tall" in ratios
        assert "vertical" in ratios
        assert "landscape" in ratios
        
        # 验证每个比例都有必要字段
        for key, ratio in ratios.items():
            assert "label" in ratio
            assert "ratio" in ratio
            assert "size" in ratio
            assert "use" in ratio
    
    def test_shot_types_defined(self):
        """测试镜头类型定义"""
        shots = CinematicPromptGenerator.SHOT_TYPES
        
        assert len(shots) > 0
        assert "closeup" in shots
        assert "long" in shots
        assert "birds_eye" in shots
    
    def test_compositions_defined(self):
        """测试构图方式定义"""
        compositions = CinematicPromptGenerator.COMPOSITIONS
        
        assert len(compositions) > 0
        assert "rule_of_thirds" in compositions
        assert "center" in compositions
        assert "leading_lines" in compositions
    
    def test_cinematic_styles_defined(self):
        """测试电影质感定义"""
        styles = CinematicPromptGenerator.CINEMATIC_STYLES
        
        assert len(styles) > 0
        assert "film_noir" in styles
        assert "golden_hour" in styles
        assert "neon_cyberpunk" in styles
    
    def test_get_optimal_ratio_closeup(self):
        """测试人物特写的最佳比例"""
        ratio = CinematicPromptGenerator.get_optimal_ratio("character_closeup")
        assert ratio["ratio"] == "1:1"
    
    def test_get_optimal_ratio_standing(self):
        """测试站立人物的最佳比例"""
        ratio = CinematicPromptGenerator.get_optimal_ratio("character_standing")
        assert ratio["ratio"] == "3:4"
    
    def test_get_optimal_ratio_landscape(self):
        """测试风景的最佳比例"""
        ratio = CinematicPromptGenerator.get_optimal_ratio("landscape")
        assert ratio["ratio"] == "16:9"
    
    def test_get_optimal_ratio_default(self):
        """测试默认比例"""
        ratio = CinematicPromptGenerator.get_optimal_ratio("unknown")
        # 应该返回一个有效的比例
        assert "ratio" in ratio
        assert "size" in ratio
    
    def test_shot_types_values(self):
        """测试镜头类型的值"""
        shots = CinematicPromptGenerator.SHOT_TYPES
        
        # 验证值是英文描述
        for key, value in shots.items():
            assert isinstance(value, str)
            assert len(value) > 0
    
    def test_compositions_values(self):
        """测试构图方式的值"""
        compositions = CinematicPromptGenerator.COMPOSITIONS
        
        for key, value in compositions.items():
            assert isinstance(value, str)
            assert len(value) > 0
    
    def test_cinematic_styles_values(self):
        """测试电影质感的值"""
        styles = CinematicPromptGenerator.CINEMATIC_STYLES
        
        for key, value in styles.items():
            assert isinstance(value, str)
            assert len(value) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
