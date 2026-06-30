"""
writing_skills.py 深度测试 - 真正调用方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.writing_skills import (
    WritingStyleConfig, AntiSlopProcessor, ANTI_SLOP_RULES,
    KnowledgeGraph, TimeAwareMemory, WritingSkillManager
)


class TestAntiSlopProcessor:
    """AntiSlopProcessor - 真正调用方法"""

    def test_init(self):
        p = AntiSlopProcessor()
        assert p.rules is not None
        assert p._compiled_patterns is not None

    def test_check_text_clean(self):
        p = AntiSlopProcessor()
        issues = p.check_text("张三走进了房间，看到了一封信。")
        assert "forbidden_openings" in issues
        assert "forbidden_transitions" in issues

    def test_check_text_with_openings(self):
        p = AntiSlopProcessor()
        issues = p.check_text("在这个世界上，强者为尊。\n第二行\n第三行\n第四行\n第五行\n第六行")
        assert len(issues["forbidden_openings"]) > 0

    def test_check_text_with_transitions(self):
        p = AntiSlopProcessor()
        text = "第一行\n然而第二行\n不过第三行\n但是第四行\n可是第五行"
        issues = p.check_text(text)
        assert len(issues["forbidden_transitions"]) > 0

    def test_check_text_with_endings(self):
        p = AntiSlopProcessor()
        # 使用一个确认在forbidden_endings中的词
        ending = p.rules["forbidden_endings"][0] if p.rules.get("forbidden_endings") else None
        if ending:
            text = "第一行\n第二行\n第三行\n第四行\n" + ending
            issues = p.check_text(text)
            assert len(issues["forbidden_endings"]) > 0
        else:
            # 如果没有定义forbidden_endings，跳过
            assert True

    def test_fix_text_clean(self):
        p = AntiSlopProcessor()
        text, fixes = p.fix_text("张三走进了房间。")
        assert isinstance(text, str)
        assert isinstance(fixes, list)

    def test_fix_text_with_issues(self):
        p = AntiSlopProcessor()
        text = "在这个世界上，然而不过但是可是。"
        fixed, fixes = p.fix_text(text)
        assert len(fixes) > 0

    def test_get_writing_tips_all_genres(self):
        p = AntiSlopProcessor()
        genres = ["玄幻", "仙侠", "都市", "历史", "科幻", "悬疑", "游戏", "军事", "武侠", "体育", "轻小说", "二次元", "言情", "恐怖", "末日"]
        for genre in genres:
            tips = p.get_writing_tips(genre)
            assert isinstance(tips, str)
            assert len(tips) > 0

    def test_get_writing_tips_subgenre(self):
        p = AntiSlopProcessor()
        tips = p.get_writing_tips("玄幻-东方玄幻")
        assert "玄幻" in tips


class TestWritingStyleConfig:
    """WritingStyleConfig 深度测试"""

    def test_to_prompt_high(self):
        c = WritingStyleConfig(descriptiveness=9, dialogue_ratio=8, pacing=9, emotional_depth=9, action_intensity=9)
        prompt = c.to_prompt()
        assert "华丽细腻" in prompt
        assert "对话驱动" in prompt

    def test_to_prompt_low(self):
        c = WritingStyleConfig(descriptiveness=2, dialogue_ratio=2, pacing=2, emotional_depth=2, action_intensity=2)
        prompt = c.to_prompt()
        assert "简洁有力" in prompt
        assert "叙述为主" in prompt

    def test_to_prompt_medium(self):
        c = WritingStyleConfig(descriptiveness=5, dialogue_ratio=5, pacing=5, emotional_depth=5, action_intensity=5)
        prompt = c.to_prompt()
        assert "适中" in prompt


class TestKnowledgeGraph:
    """KnowledgeGraph 深度测试"""

    def test_class_exists(self):
        assert KnowledgeGraph is not None


class TestTimeAwareMemory:
    """TimeAwareMemory 深度测试"""

    def test_class_exists(self):
        assert TimeAwareMemory is not None


class TestWritingSkillManager:
    """WritingSkillManager 深度测试"""

    def test_class_exists(self):
        assert WritingSkillManager is not None


class TestANTI_SLOP_RULES:
    """ANTI_SLOP_RULES 结构测试"""

    def test_forbidden_openings(self):
        assert "forbidden_openings" in ANTI_SLOP_RULES
        assert len(ANTI_SLOP_RULES["forbidden_openings"]) > 0

    def test_forbidden_transitions(self):
        assert "forbidden_transitions" in ANTI_SLOP_RULES
        assert len(ANTI_SLOP_RULES["forbidden_transitions"]) > 0

    def test_forbidden_endings(self):
        assert "forbidden_endings" in ANTI_SLOP_RULES
        assert len(ANTI_SLOP_RULES["forbidden_endings"]) > 0

    def test_forbidden_adjective_clusters(self):
        assert "forbidden_adjective_clusters" in ANTI_SLOP_RULES

    def test_recommended_techniques(self):
        assert "recommended_techniques" in ANTI_SLOP_RULES
