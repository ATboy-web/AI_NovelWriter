"""
scene_detector.py 深度测试 - 真正调用方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.scene_detector import CinematicPromptGenerator


class TestGetOptimalRatio:
    """get_optimal_ratio 深度测试"""

    def test_character_closeup(self):
        r = CinematicPromptGenerator.get_optimal_ratio("character_closeup")
        assert r["ratio"] == "1:1"

    def test_character_portrait(self):
        r = CinematicPromptGenerator.get_optimal_ratio("character_portrait")
        assert r["ratio"] == "1:1"

    def test_character_half(self):
        r = CinematicPromptGenerator.get_optimal_ratio("character_half")
        assert r["ratio"] == "3:4"

    def test_character_standing(self):
        r = CinematicPromptGenerator.get_optimal_ratio("character_standing")
        assert r["ratio"] == "3:4"

    def test_beauty(self):
        r = CinematicPromptGenerator.get_optimal_ratio("beauty")
        assert r["ratio"] == "3:4"

    def test_landscape(self):
        r = CinematicPromptGenerator.get_optimal_ratio("landscape")
        assert r["ratio"] == "16:9"

    def test_battle(self):
        r = CinematicPromptGenerator.get_optimal_ratio("battle")
        assert r["ratio"] == "16:9"

    def test_unknown_defaults(self):
        r = CinematicPromptGenerator.get_optimal_ratio("unknown_type")
        assert "ratio" in r

    def test_with_content_hint(self):
        r = CinematicPromptGenerator.get_optimal_ratio("action", "大场面战斗")
        assert "ratio" in r


class TestAspectRatios:
    """ASPECT_RATIOS 完整测试"""

    def test_all_ratios_have_required_fields(self):
        for key, ratio in CinematicPromptGenerator.ASPECT_RATIOS.items():
            assert "label" in ratio
            assert "ratio" in ratio
            assert "size" in ratio
            assert "use" in ratio

    def test_portrait_size(self):
        assert CinematicPromptGenerator.ASPECT_RATIOS["portrait"]["size"] == "1024x1024"

    def test_landscape_size(self):
        assert CinematicPromptGenerator.ASPECT_RATIOS["landscape"]["size"] == "1024x576"


class TestShotTypes:
    """SHOT_TYPES 完整测试"""

    def test_all_shots_are_strings(self):
        for key, value in CinematicPromptGenerator.SHOT_TYPES.items():
            assert isinstance(value, str)
            assert len(value) > 0

    def test_extreme_closeup(self):
        assert "close-up" in CinematicPromptGenerator.SHOT_TYPES["extreme_closeup"]

    def test_birds_eye(self):
        assert "overhead" in CinematicPromptGenerator.SHOT_TYPES["birds_eye"]


class TestCompositions:
    """COMPOSITIONS 完整测试"""

    def test_all_compositions_are_strings(self):
        for key, value in CinematicPromptGenerator.COMPOSITIONS.items():
            assert isinstance(value, str)
            assert len(value) > 0

    def test_rule_of_thirds(self):
        assert "thirds" in CinematicPromptGenerator.COMPOSITIONS["rule_of_thirds"]


class TestCinematicStyles:
    """CINEMATIC_STYLES 完整测试"""

    def test_all_styles_are_strings(self):
        for key, value in CinematicPromptGenerator.CINEMATIC_STYLES.items():
            assert isinstance(value, str)
            assert len(value) > 0

    def test_film_noir(self):
        assert "noir" in CinematicPromptGenerator.CINEMATIC_STYLES["film_noir"]
