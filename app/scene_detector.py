"""
名场面检测器 v2.0 - AI驱动的电影级提示词生成

特性：
- AI智能检测名场面、人物描写、关键时刻
- 自动选择画面比例（1:1, 3:4, 9:16, 16:9）
- 电影级镜头语言（特写、中景、远景、俯仰角等）
- 专业摄影构图（三分法、引导线、框架构图等）
- 支持按卷批量生成
"""

import json
from typing import Dict, List, Any


class CinematicPromptGenerator:
    """电影级提示词生成器"""
    
    # 画面比例规则
    ASPECT_RATIOS = {
        "portrait": {"label": "1:1 正方形", "ratio": "1:1", "size": "1024x1024", "use": "人物特写、头像"},
        "portrait_tall": {"label": "3:4 竖版", "ratio": "3:4", "size": "768x1024", "use": "半身像、站立人物"},
        "vertical": {"label": "9:16 竖版", "ratio": "9:16", "size": "576x1024", "use": "全身人物、竖构图场景"},
        "landscape": {"label": "16:9 横版", "ratio": "16:9", "size": "1024x576", "use": "全景、大场面、风景"},
    }
    
    # 镜头类型
    SHOT_TYPES = {
        "extreme_closeup": "extreme close-up shot, macro detail",
        "closeup": "close-up shot, face detail, shallow depth of field",
        "medium_closeup": "medium close-up shot, chest up",
        "medium": "medium shot, waist up, environmental portrait",
        "medium_long": "medium long shot, full body",
        "long": "long shot, full figure with environment",
        "extreme_long": "extreme long shot, wide establishing shot",
        "birds_eye": "bird's eye view, overhead shot",
        "low_angle": "low angle shot, looking up, dramatic perspective",
        "high_angle": "high angle shot, looking down",
        "dutch_angle": "dutch angle, tilted, tension",
        "over_shoulder": "over the shoulder shot",
    }
    
    # 构图方式
    COMPOSITIONS = {
        "rule_of_thirds": "rule of thirds composition, subject at intersection point",
        "center": "centered composition, symmetrical, powerful presence",
        "leading_lines": "leading lines composition, depth perspective",
        "frame_in_frame": "frame within frame composition, natural framing",
        "golden_ratio": "golden ratio composition, balanced harmony",
        "diagonal": "diagonal composition, dynamic energy",
        "symmetry": "perfect symmetry, mirror reflection",
        "negative_space": "negative space, minimalist, isolation",
        "triangular": "triangular composition, stable and powerful",
        "spiral": "spiral composition, fibonacci, natural flow",
    }
    
    # 电影质感
    CINEMATIC_STYLES = {
        "film_noir": "film noir style, high contrast, dramatic shadows, moody",
        "golden_hour": "golden hour lighting, warm tones, cinematic glow",
        "neon_cyberpunk": "neon cyberpunk lighting, vibrant colors, futuristic",
        "ethereal": "ethereal atmosphere, soft diffused light, dreamy",
        "dramatic": "dramatic lighting, chiaroscuro, bold shadows",
        "epic_fantasy": "epic fantasy, volumetric lighting, god rays",
        "noir_thriller": "noir thriller style, dark atmosphere, tension",
        "warm_intimate": "warm intimate lighting, soft focus, emotional",
        "cold_emptiness": "cold desolate atmosphere, blue-grey tones, isolation",
        "vibrant_action": "vibrant action, motion blur, dynamic energy",
    }
    
    @classmethod
    def get_optimal_ratio(cls, scene_type: str, content_hint: str = "") -> dict:
        """根据场景类型自动选择最佳画面比例"""
        # 人物特写 → 1:1
        if scene_type in ["character_closeup", "character_portrait"]:
            return cls.ASPECT_RATIOS["portrait"]
        # 站立/半身人物 → 3:4
        if scene_type in ["character_half", "character_standing", "beauty"]:
            return cls.ASPECT_RATIOS["portrait_tall"]
        # 大场面/全景 → 16:9
        if scene_type in ["landscape", "panorama", "battlefield", "epic_scene"]:
            return cls.ASPECT_RATIOS["landscape"]
        # 情感/对峙 → 9:16
        if scene_type in ["emotion", "confrontation", "sacrifice"]:
            return cls.ASPECT_RATIOS["vertical"]
        # 默认16:9
        return cls.ASPECT_RATIOS["landscape"]
    
    @classmethod
    def get_cinematic_prompt(cls, scene: dict) -> str:
        """生成电影级提示词"""
        scene_type = scene.get("type", "epic")
        description = scene.get("description", "")
        mood = scene.get("mood", "dramatic")
        
        # 自动选择镜头
        shot = cls._auto_select_shot(scene_type, description)
        # 自动选择构图
        comp = cls._auto_select_composition(scene_type)
        # 自动选择质感
        style = cls._auto_select_style(mood)
        # 选择比例
        ratio_info = cls.get_optimal_ratio(scene_type, description)
        
        # 构建提示词
        prompt_parts = [
            description,
            f"({shot})",
            f"({comp})",
            f"({style})",
            "masterpiece, best quality, cinematic, 8k, highly detailed",
            "professional photography, award-winning"
        ]
        
        return ", ".join(prompt_parts), ratio_info
    
    @classmethod
    def _auto_select_shot(cls, scene_type: str, desc: str) -> str:
        """AI自动选择镜头类型"""
        shot_rules = {
            "character_closeup": "closeup",
            "character_portrait": "medium_closeup",
            "battle": "medium_long",
            "epic_scene": "extreme_long",
            "emotion": "closeup",
            "beauty": "medium_closeup",
            "landscape": "extreme_long",
            "panorama": "birds_eye",
            "sacrifice": "medium",
            "confrontation": "over_shoulder",
        }
        shot_key = shot_rules.get(scene_type, "medium")
        return cls.SHOT_TYPES[shot_key]
    
    @classmethod
    def _auto_select_composition(cls, scene_type: str) -> str:
        """AI自动选择构图方式"""
        comp_rules = {
            "character_closeup": "center",
            "character_portrait": "rule_of_thirds",
            "battle": "diagonal",
            "epic_scene": "golden_ratio",
            "emotion": "negative_space",
            "beauty": "golden_ratio",
            "landscape": "leading_lines",
            "panorama": "symmetry",
            "sacrifice": "triangular",
            "confrontation": "frame_in_frame",
        }
        comp_key = comp_rules.get(scene_type, "rule_of_thirds")
        return cls.COMPOSITIONS[comp_key]
    
    @classmethod
    def _auto_select_style(cls, mood: str) -> str:
        """AI自动选择电影质感"""
        mood_to_style = {
            "dramatic": "dramatic",
            "warm": "golden_hour",
            "cold": "cold_emptiness",
            "dark": "film_noir",
            "ethereal": "ethereal",
            "epic": "epic_fantasy",
            "intimate": "warm_intimate",
            "tense": "noir_thriller",
            "vibrant": "vibrant_action",
            "cyberpunk": "neon_cyberpunk",
        }
        style_key = mood_to_style.get(mood, "dramatic")
        return cls.CINEMATIC_STYLES[style_key]


class SceneDetector:
    """名场面检测器 v2.0 - AI驱动"""
    
    # 触发关键词（预筛选）
    SCENE_KEYWORDS = [
        "大战", "对决", "交锋", "激战", "厮杀", "出剑", "拔刀", "施展",
        "震撼", "壮观", "磅礴", "恢弘", "浩瀚", "天地变色", "风云变幻",
        "英俊", "潇洒", "飘逸", "凌厉", "霸气", "威严", "冷峻", "邪魅",
        "绝美", "倾城", "惊艳", "如画", "仙子", "出尘", "清丽", "妩媚",
        "告白", "拥吻", "热泪", "重逢", "离别", "生死", "牺牲",
        "踏入", "登临", "俯瞰", "仰望", "穿越", "降临",
    ]
    
    CHARACTER_KEYWORDS = [
        "主角", "少年", "少女", "男子", "女子", "将军", "帝王", "仙人",
        "剑客", "侠女", "公主", "王子", "魔王", "天使",
    ]
    
    @staticmethod
    def detect(content: str) -> List[Dict[str, str]]:
        """检测内容中的名场面"""
        scenes = []
        
        for keyword in SceneDetector.SCENE_KEYWORDS:
            if keyword in content:
                for sentence in content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n"):
                    if keyword in sentence and len(sentence.strip()) > 10:
                        scene_type = SceneDetector._classify_scene(sentence)
                        desc = sentence.strip()[:200]
                        
                        # 使用电影级提示词生成器
                        scene_data = {
                            "type": scene_type,
                            "description": desc,
                            "mood": SceneDetector._detect_mood(sentence),
                        }
                        prompt, ratio_info = CinematicPromptGenerator.get_cinematic_prompt(scene_data)
                        
                        scenes.append({
                            "text": desc,
                            "keyword": keyword,
                            "type": scene_type,
                            "prompt": prompt,
                            "aspect_ratio": ratio_info["ratio"],
                            "size": ratio_info["size"],
                            "shot_type": CinematicPromptGenerator._auto_select_shot(scene_type, desc),
                            "composition": CinematicPromptGenerator._auto_select_composition(scene_type),
                            "style": CinematicPromptGenerator._auto_select_style(scene_data["mood"]),
                        })
        
        # 去重
        seen = set()
        unique_scenes = []
        for s in scenes:
            key = s["text"][:50]
            if key not in seen:
                seen.add(key)
                unique_scenes.append(s)
        
        return unique_scenes[:5]
    
    @staticmethod
    def detect_for_volume(chapters: List[str], volume_num: int, ai_client=None) -> List[Dict]:
        """为整卷检测名场面（AI增强版）"""
        all_scenes = []
        
        for ch_idx, ch_content in enumerate(chapters):
            ch_num = volume_num * 100 + ch_idx + 1
            scenes = SceneDetector.detect(ch_content)
            for scene in scenes:
                scene["chapter"] = ch_num
                all_scenes.append(scene)
        
        # 如果有AI客户端，用AI筛选最佳场景
        if ai_client and len(all_scenes) > 10:
            return SceneDetector._ai_filter_scenes(ai_client, all_scenes, volume_num)
        
        return all_scenes[:10]
    
    @staticmethod
    def _ai_filter_scenes(ai_client, scenes: List[Dict], volume_num: int) -> List[Dict]:
        """用AI筛选最具画面感的场景"""
        scene_summaries = []
        for i, s in enumerate(scenes[:20]):
            scene_summaries.append(f"{i+1}. [{s['type']}] 第{s['chapter']}章: {s['text'][:80]}")
        
        prompt = f"第{volume_num+1}卷有以下候选场景，请选出最具画面感和视觉冲击力的10个场景，输出JSON数组[场景序号]：\n" + "\n".join(scene_summaries)
        
        try:
            result = ai_client.chat([{"role": "user", "content": prompt}], 
                                   system="你是专业的影视选景导演。只输出JSON数组，如[1,3,5,7,9,11,13,15,17,19]",
                                   max_tokens=200)
            selected = json.loads(result.strip().strip("`").replace("json", ""))
            return [scenes[i-1] for i in selected if 0 < i <= len(scenes)]
        except Exception:
            return scenes[:10]
    
    @staticmethod
    def _classify_scene(text: str) -> str:
        """分类场景类型"""
        battle_words = ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击", "对决", "厮杀"]
        beauty_words = ["美", "仙", "丽", "艳", "俊", "帅", "魅", "绝美", "倾城"]
        emotion_words = ["泪", "笑", "爱", "恨", "告白", "拥", "吻", "重逢", "离别", "牺牲"]
        epic_words = ["震撼", "壮观", "磅礴", "恢弘", "浩瀚", "天地", "风云", "降临", "登临"]
        
        for w in battle_words:
            if w in text:
                return "battle"
        for w in beauty_words:
            if w in text:
                return "beauty"
        for w in emotion_words:
            if w in text:
                return "emotion"
        for w in epic_words:
            if w in text:
                return "epic_scene"
        return "epic_scene"
    
    @staticmethod
    def _detect_mood(text: str) -> str:
        """检测情绪基调"""
        warm_words = ["温暖", "幸福", "甜蜜", "微笑", "阳光"]
        cold_words = ["冰冷", "寒", "冷酷", "无情", "孤独"]
        dark_words = ["黑暗", "暗", "阴", "恐怖", "死亡"]
        ethereal_words = ["仙", "灵", "飘", "空灵", "出尘"]
        epic_words = ["磅礴", "恢弘", "壮观", "浩瀚", "天地"]
        
        for w in warm_words:
            if w in text:
                return "warm"
        for w in cold_words:
            if w in text:
                return "cold"
        for w in dark_words:
            if w in text:
                return "dark"
        for w in ethereal_words:
            if w in text:
                return "ethereal"
        for w in epic_words:
            if w in text:
                return "epic"
        return "dramatic"
