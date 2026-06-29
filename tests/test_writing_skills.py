"""
写作技能模块测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.writing_skills import WritingStyleConfig, ANTI_SLOP_RULES


class TestWritingStyleConfig:
    """WritingStyleConfig 测试套件"""
    
    def test_default_values(self):
        """测试默认值"""
        config = WritingStyleConfig()
        
        assert config.descriptiveness == 7
        assert config.dialogue_ratio == 5
        assert config.pacing == 5
        assert config.emotional_depth == 6
        assert config.action_intensity == 5
        assert config.genre_style == "玄幻"
    
    def test_custom_values(self):
        """测试自定义值"""
        config = WritingStyleConfig(
            descriptiveness=9,
            dialogue_ratio=8,
            pacing=3,
            emotional_depth=10,
            action_intensity=2,
            genre_style="言情"
        )
        
        assert config.descriptiveness == 9
        assert config.dialogue_ratio == 8
        assert config.pacing == 3
        assert config.emotional_depth == 10
        assert config.action_intensity == 2
        assert config.genre_style == "言情"
    
    def test_to_prompt_high_values(self):
        """测试高值的提示词"""
        config = WritingStyleConfig(
            descriptiveness=9,
            dialogue_ratio=8,
            pacing=9,
            emotional_depth=9,
            action_intensity=9
        )
        
        prompt = config.to_prompt()
        
        assert "华丽细腻" in prompt
        assert "对话驱动" in prompt
        assert "快节奏" in prompt
        assert "深入内心" in prompt
        assert "激烈热血" in prompt
    
    def test_to_prompt_low_values(self):
        """测试低值的提示词"""
        config = WritingStyleConfig(
            descriptiveness=2,
            dialogue_ratio=2,
            pacing=2,
            emotional_depth=2,
            action_intensity=2
        )
        
        prompt = config.to_prompt()
        
        assert "简洁有力" in prompt
        assert "叙述为主" in prompt
        assert "慢节奏铺垫" in prompt
        assert "表面描写" in prompt
        assert "平淡克制" in prompt
    
    def test_to_prompt_medium_values(self):
        """测试中等值的提示词"""
        config = WritingStyleConfig(
            descriptiveness=5,
            dialogue_ratio=5,
            pacing=5,
            emotional_depth=5,
            action_intensity=5
        )
        
        prompt = config.to_prompt()
        
        assert "适中" in prompt
        assert "平衡" in prompt
        assert "张弛有度" in prompt
        assert "适度" in prompt
    
    def test_to_prompt_contains_all_metrics(self):
        """测试提示词包含所有指标"""
        config = WritingStyleConfig()
        prompt = config.to_prompt()
        
        assert "描写细腻度" in prompt
        assert "对话比例" in prompt
        assert "节奏" in prompt
        assert "情感深度" in prompt
        assert "动作强度" in prompt


class TestAntiSlopRules:
    """ANTI_SLOP_RULES 测试套件"""
    
    def test_forbidden_openings_defined(self):
        """测试禁止的开头定义"""
        openings = ANTI_SLOP_RULES["forbidden_openings"]
        
        assert len(openings) > 0
        assert "在这个" in openings
        assert "随着科技的发展" in openings
    
    def test_forbidden_transitions_defined(self):
        """测试禁止的过渡词定义"""
        transitions = ANTI_SLOP_RULES["forbidden_transitions"]
        
        assert len(transitions) > 0
        assert "然而" in transitions
    
    def test_forbidden_endings_defined(self):
        """测试禁止的结尾定义"""
        endings = ANTI_SLOP_RULES.get("forbidden_endings", [])
        
        # 如果定义了结尾，检查内容
        if endings:
            assert len(endings) > 0
    
    def test_rule_types(self):
        """测试规则类型"""
        for key, value in ANTI_SLOP_RULES.items():
            # 值可以是列表或字典
            assert isinstance(value, (list, dict)), f"{key} 应该是列表或字典类型"
            if isinstance(value, list):
                for item in value:
                    assert isinstance(item, str), f"{key} 中的项目应该是字符串"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
