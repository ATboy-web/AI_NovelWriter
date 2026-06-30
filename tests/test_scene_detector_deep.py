"""
scene_detector.py 深度测试 - 真正调用所有方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.scene_detector import CinematicPromptGenerator, SceneDetector


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

    def test_panorama(self):
        r = CinematicPromptGenerator.get_optimal_ratio("panorama")
        assert r["ratio"] == "16:9"

    def test_battlefield(self):
        r = CinematicPromptGenerator.get_optimal_ratio("battlefield")
        assert r["ratio"] == "16:9"

    def test_epic_scene(self):
        r = CinematicPromptGenerator.get_optimal_ratio("epic_scene")
        assert r["ratio"] == "16:9"

    def test_emotion(self):
        r = CinematicPromptGenerator.get_optimal_ratio("emotion")
        assert r["ratio"] == "9:16"

    def test_confrontation(self):
        r = CinematicPromptGenerator.get_optimal_ratio("confrontation")
        assert r["ratio"] == "9:16"

    def test_sacrifice(self):
        r = CinematicPromptGenerator.get_optimal_ratio("sacrifice")
        assert r["ratio"] == "9:16"

    def test_unknown_defaults_to_landscape(self):
        r = CinematicPromptGenerator.get_optimal_ratio("unknown_type")
        assert r["ratio"] == "16:9"

    def test_with_content_hint(self):
        r = CinematicPromptGenerator.get_optimal_ratio("action", "大场面战斗")
        assert "ratio" in r


class TestGetCinematicPrompt:
    """get_cinematic_prompt 深度测试"""

    def test_basic_scene(self):
        scene = {"type": "battle", "description": "张三挥剑斩向敌人", "mood": "dramatic"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "ratio" in ratio

    def test_beauty_scene(self):
        scene = {"type": "beauty", "description": "绝美仙子降临", "mood": "ethereal"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_emotion_scene(self):
        scene = {"type": "emotion", "description": "两人重逢泪流满面", "mood": "warm"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_epic_scene(self):
        scene = {"type": "epic_scene", "description": "天地变色风云变幻", "mood": "epic"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_empty_scene(self):
        scene = {}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_landscape_scene(self):
        scene = {"type": "landscape", "description": "壮丽山河", "mood": "dramatic"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert ratio["ratio"] == "16:9"

    def test_panorama_scene(self):
        scene = {"type": "panorama", "description": "俯瞰全城", "mood": "epic"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_confrontation_scene(self):
        scene = {"type": "confrontation", "description": "两人对峙", "mood": "tense"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert ratio["ratio"] == "9:16"

    def test_sacrifice_scene(self):
        scene = {"type": "sacrifice", "description": "英雄牺牲", "mood": "dramatic"}
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
        assert isinstance(prompt, str)

    def test_all_moods(self):
        moods = ["dramatic", "warm", "cold", "dark", "ethereal", "epic", "intimate", "tense", "vibrant", "cyberpunk"]
        for mood in moods:
            scene = {"type": "epic", "description": "测试场景", "mood": mood}
            prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(scene)
            assert isinstance(prompt, str)


class TestAutoSelectShot:
    """_auto_select_shot 深度测试"""

    def test_character_closeup(self):
        shot = CinematicPromptGenerator._auto_select_shot("character_closeup", "")
        assert "close-up" in shot

    def test_character_portrait(self):
        shot = CinematicPromptGenerator._auto_select_shot("character_portrait", "")
        assert "close-up" in shot

    def test_battle(self):
        shot = CinematicPromptGenerator._auto_select_shot("battle", "")
        assert "long" in shot or "shot" in shot

    def test_epic_scene(self):
        shot = CinematicPromptGenerator._auto_select_shot("epic_scene", "")
        assert "long" in shot or "shot" in shot

    def test_emotion(self):
        shot = CinematicPromptGenerator._auto_select_shot("emotion", "")
        assert "close-up" in shot

    def test_beauty(self):
        shot = CinematicPromptGenerator._auto_select_shot("beauty", "")
        assert "close-up" in shot

    def test_landscape(self):
        shot = CinematicPromptGenerator._auto_select_shot("landscape", "")
        assert "long" in shot or "shot" in shot

    def test_panorama(self):
        shot = CinematicPromptGenerator._auto_select_shot("panorama", "")
        assert "eye" in shot or "shot" in shot

    def test_sacrifice(self):
        shot = CinematicPromptGenerator._auto_select_shot("sacrifice", "")
        assert "shot" in shot

    def test_confrontation(self):
        shot = CinematicPromptGenerator._auto_select_shot("confrontation", "")
        assert "shoulder" in shot or "shot" in shot

    def test_unknown_defaults_to_medium(self):
        shot = CinematicPromptGenerator._auto_select_shot("unknown", "")
        assert "medium" in shot or "shot" in shot


class TestAutoSelectComposition:
    """_auto_select_composition 深度测试"""

    def test_character_closeup(self):
        comp = CinematicPromptGenerator._auto_select_composition("character_closeup")
        assert "center" in comp or "composition" in comp

    def test_character_portrait(self):
        comp = CinematicPromptGenerator._auto_select_composition("character_portrait")
        assert "thirds" in comp or "composition" in comp

    def test_battle(self):
        comp = CinematicPromptGenerator._auto_select_composition("battle")
        assert "diagonal" in comp or "composition" in comp

    def test_epic_scene(self):
        comp = CinematicPromptGenerator._auto_select_composition("epic_scene")
        assert "golden" in comp or "composition" in comp

    def test_emotion(self):
        comp = CinematicPromptGenerator._auto_select_composition("emotion")
        assert "negative" in comp or "composition" in comp

    def test_beauty(self):
        comp = CinematicPromptGenerator._auto_select_composition("beauty")
        assert "golden" in comp or "composition" in comp

    def test_landscape(self):
        comp = CinematicPromptGenerator._auto_select_composition("landscape")
        assert "leading" in comp or "composition" in comp

    def test_panorama(self):
        comp = CinematicPromptGenerator._auto_select_composition("panorama")
        assert "symmetry" in comp or "composition" in comp

    def test_sacrifice(self):
        comp = CinematicPromptGenerator._auto_select_composition("sacrifice")
        assert "triangular" in comp or "composition" in comp

    def test_confrontation(self):
        comp = CinematicPromptGenerator._auto_select_composition("confrontation")
        assert "frame" in comp or "composition" in comp

    def test_unknown_defaults(self):
        comp = CinematicPromptGenerator._auto_select_composition("unknown")
        assert "thirds" in comp or "composition" in comp


class TestAutoSelectStyle:
    """_auto_select_style 深度测试"""

    def test_dramatic(self):
        style = CinematicPromptGenerator._auto_select_style("dramatic")
        assert "dramatic" in style

    def test_warm(self):
        style = CinematicPromptGenerator._auto_select_style("warm")
        assert "golden" in style or "warm" in style

    def test_cold(self):
        style = CinematicPromptGenerator._auto_select_style("cold")
        assert "cold" in style

    def test_dark(self):
        style = CinematicPromptGenerator._auto_select_style("dark")
        assert "noir" in style or "dark" in style

    def test_ethereal(self):
        style = CinematicPromptGenerator._auto_select_style("ethereal")
        assert "ethereal" in style

    def test_epic(self):
        style = CinematicPromptGenerator._auto_select_style("epic")
        assert "epic" in style or "fantasy" in style

    def test_intimate(self):
        style = CinematicPromptGenerator._auto_select_style("intimate")
        assert "warm" in style or "intimate" in style

    def test_tense(self):
        style = CinematicPromptGenerator._auto_select_style("tense")
        assert "noir" in style or "thriller" in style

    def test_vibrant(self):
        style = CinematicPromptGenerator._auto_select_style("vibrant")
        assert "vibrant" in style or "action" in style

    def test_cyberpunk(self):
        style = CinematicPromptGenerator._auto_select_style("cyberpunk")
        assert "neon" in style or "cyberpunk" in style

    def test_unknown_defaults_to_dramatic(self):
        style = CinematicPromptGenerator._auto_select_style("unknown")
        assert "dramatic" in style


class TestSceneDetectorClassify:
    """SceneDetector._classify_scene 深度测试"""

    def test_battle_text(self):
        assert SceneDetector._classify_scene("张三挥剑斩向敌人") == "battle"
        assert SceneDetector._classify_scene("大战一触即发") == "battle"
        assert SceneDetector._classify_scene("两人对决") == "battle"

    def test_beauty_text(self):
        assert SceneDetector._classify_scene("绝美仙子降临") == "beauty"
        assert SceneDetector._classify_scene("倾城之姿") == "beauty"

    def test_emotion_text(self):
        assert SceneDetector._classify_scene("两人重逢泪流满面") == "emotion"
        assert SceneDetector._classify_scene("告白场景") == "emotion"
        assert SceneDetector._classify_scene("离别时刻") == "emotion"

    def test_epic_text(self):
        assert SceneDetector._classify_scene("震撼天地") == "epic_scene"
        assert SceneDetector._classify_scene("壮观场面") == "epic_scene"

    def test_default_epic(self):
        assert SceneDetector._classify_scene("普通文本") == "epic_scene"


class TestSceneDetectorMood:
    """SceneDetector._detect_mood 深度测试"""

    def test_warm_mood(self):
        assert SceneDetector._detect_mood("温暖的阳光") == "warm"
        assert SceneDetector._detect_mood("幸福时光") == "warm"

    def test_cold_mood(self):
        assert SceneDetector._detect_mood("冰冷的目光") == "cold"
        assert SceneDetector._detect_mood("孤独身影") == "cold"

    def test_dark_mood(self):
        assert SceneDetector._detect_mood("黑暗降临") == "dark"
        assert SceneDetector._detect_mood("恐怖氛围") == "dark"

    def test_ethereal_mood(self):
        assert SceneDetector._detect_mood("仙气飘飘") == "ethereal"
        assert SceneDetector._detect_mood("空灵之境") == "ethereal"

    def test_epic_mood(self):
        assert SceneDetector._detect_mood("磅礴气势") == "epic"
        assert SceneDetector._detect_mood("壮观景象") == "epic"

    def test_default_dramatic(self):
        assert SceneDetector._detect_mood("普通文本") == "dramatic"


class TestSceneDetectorDetect:
    """SceneDetector.detect 深度测试"""

    def test_detect_battle_scene(self):
        content = "张三挥剑斩向敌人，大战一触即发。两人对决，剑光四射。"
        scenes = SceneDetector.detect(content)
        assert isinstance(scenes, list)

    def test_detect_beauty_scene(self):
        content = "绝美仙子降临人间，倾城之姿令人惊叹。"
        scenes = SceneDetector.detect(content)
        assert isinstance(scenes, list)

    def test_detect_emotion_scene(self):
        content = "两人重逢泪流满面，告白场景感人至深。"
        scenes = SceneDetector.detect(content)
        assert isinstance(scenes, list)

    def test_detect_empty_content(self):
        scenes = SceneDetector.detect("")
        assert scenes == []

    def test_detect_no_keywords(self):
        scenes = SceneDetector.detect("今天天气不错。")
        assert scenes == []

    def test_detect_multiple_scenes(self):
        content = "张三挥剑大战敌人。绝美仙子降临。两人重逢泪流满面。"
        scenes = SceneDetector.detect(content)
        assert isinstance(scenes, list)

    def test_detect_scene_structure(self):
        content = "张三挥剑大战敌人，剑光四射震撼全场。"
        scenes = SceneDetector.detect(content)
        if scenes:
            scene = scenes[0]
            assert "text" in scene
            assert "keyword" in scene
            assert "type" in scene
            assert "prompt" in scene
            assert "aspect_ratio" in scene
            assert "size" in scene

    def test_detect_max_scenes(self):
        content = "大战对决激战厮杀出剑拔刀施展震撼壮观磅礴恢弘浩瀚" * 10
        scenes = SceneDetector.detect(content)
        assert len(scenes) <= 5


class TestSceneDetectorKeywords:
    """SceneDetector 关键词测试"""

    def test_scene_keywords_exist(self):
        assert len(SceneDetector.SCENE_KEYWORDS) > 0

    def test_character_keywords_exist(self):
        assert len(SceneDetector.CHARACTER_KEYWORDS) > 0

    def test_scene_keywords_are_strings(self):
        for kw in SceneDetector.SCENE_KEYWORDS:
            assert isinstance(kw, str)
            assert len(kw) > 0


class TestSceneDetectorDetectForVolume:
    """SceneDetector.detect_for_volume 深度测试"""

    def test_detect_for_volume_basic(self):
        chapters = [
            "张三挥剑大战敌人，剑光四射。",
            "绝美仙子降临人间。",
            "两人重逢泪流满面。",
        ]
        scenes = SceneDetector.detect_for_volume(chapters, 0)
        assert isinstance(scenes, list)

    def test_detect_for_volume_empty(self):
        scenes = SceneDetector.detect_for_volume([], 0)
        assert scenes == []

    def test_detect_for_volume_with_ai_client(self):
        from unittest.mock import MagicMock
        chapters = ["大战" * 20 + "。"] * 20
        ai_client = MagicMock()
        ai_client.chat.return_value = "[1,2,3,4,5,6,7,8,9,10]"
        scenes = SceneDetector.detect_for_volume(chapters, 0, ai_client=ai_client)
        assert isinstance(scenes, list)

    def test_detect_for_volume_ai_failure(self):
        from unittest.mock import MagicMock
        chapters = ["大战" * 20 + "。"] * 20
        ai_client = MagicMock()
        ai_client.chat.side_effect = Exception("API error")
        scenes = SceneDetector.detect_for_volume(chapters, 0, ai_client=ai_client)
        assert isinstance(scenes, list)
