"""
名场面检测器模块 - 检测适合生成插图的场景
"""

from typing import Dict, List


class SceneDetector:
    """名场面检测器 - 检测适合生成插图的场景"""
    
    # 触发关键词
    SCENE_KEYWORDS = [
        # 战斗场面
        "大战", "对决", "交锋", "激战", "厮杀", "出剑", "拔刀", "施展",
        # 震撼场面
        "震撼", "壮观", "磅礴", "恢弘", "浩瀚", "天地变色", "风云变幻",
        # 帅气描写
        "英俊", "潇洒", "飘逸", "凌厉", "霸气", "威严", "冷峻", "邪魅",
        # 美丽描写
        "绝美", "倾城", "惊艳", "如画", "仙子", "出尘", "清丽", "妩媚",
        # 情感高潮
        "告白", "拥吻", "热泪", "重逢", "离别", "生死", "牺牲",
        # 场景转换
        "踏入", "登临", "俯瞰", "仰望", "穿越", "降临",
    ]
    
    CHARACTER_KEYWORDS = [
        "主角", "少年", "少女", "男子", "女子", "将军", "帝王", "仙人",
        "剑客", "侠女", "公主", "王子", "魔王", "天使", "龙", "凤",
    ]
    
    @staticmethod
    def detect(content: str) -> List[Dict[str, str]]:
        """检测内容中的名场面，返回场景列表"""
        scenes = []
        
        # 方法1: 关键词匹配
        for keyword in SceneDetector.SCENE_KEYWORDS:
            if keyword in content:
                # 找到关键词所在的句子
                for sentence in content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n"):
                    if keyword in sentence and len(sentence.strip()) > 10:
                        scene_type = SceneDetector._classify_scene(sentence)
                        scenes.append({
                            "text": sentence.strip()[:200],
                            "keyword": keyword,
                            "type": scene_type,
                            "prompt": SceneDetector._build_prompt(sentence, scene_type),
                        })
        
        # 去重
        seen = set()
        unique_scenes = []
        for s in scenes:
            key = s["text"][:50]
            if key not in seen:
                seen.add(key)
                unique_scenes.append(s)
        
        return unique_scenes[:5]  # 最多返回5个场景
    
    @staticmethod
    def _classify_scene(text: str) -> str:
        """分类场景类型"""
        battle_words = ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击"]
        beauty_words = ["美", "仙", "丽", "艳", "俊", "帅", "魅"]
        emotion_words = ["泪", "笑", "爱", "恨", "告白", "拥", "吻"]
        
        for w in battle_words:
            if w in text:
                return "battle"
        for w in beauty_words:
            if w in text:
                return "beauty"
        for w in emotion_words:
            if w in text:
                return "emotion"
        return "epic"
    
    @staticmethod
    def _build_prompt(text: str, scene_type: str) -> str:
        """构建文生图提示词"""
        style_map = {
            "battle": "epic battle scene, dynamic action, dramatic lighting, cinematic, anime style, high detail",
            "beauty": "beautiful character portrait, elegant pose, soft lighting, anime style, highly detailed",
            "emotion": "emotional scene, cinematic composition, warm lighting, anime style, expressive",
            "epic": "epic fantasy scene, grand scale, dramatic atmosphere, anime style, masterpiece",
        }
        base_style = style_map.get(scene_type, style_map["epic"])
        return f"{text[:100]}, {base_style}, best quality, masterpiece"
