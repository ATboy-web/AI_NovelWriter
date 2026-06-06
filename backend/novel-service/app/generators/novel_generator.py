"""
小说生成引擎
负责生成各种类型的小说内容
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import json
from abc import ABC, abstractmethod

class NovelType(str, Enum):
    # 基础类型
    SCIFI = "scifi"           # 科幻
    MYSTERY = "mystery"       # 悬疑推理
    ROMANCE = "romance"       # 言情
    FANTASY = "fantasy"       # 奇幻
    URBAN = "urban"           # 都市
    
    # 新增类型
    HISTORY = "history"       # 历史
    MARTIAL_ARTS = "martial_arts"  # 武侠
    XIANXIA = "xianxia"       # 仙侠
    HORROR = "horror"         # 恐怖
    MILITARY = "military"     # 军事
    GAME = "game"             # 游戏
    SPORTS = "sports"         # 体育
    TIME_TRAVEL = "time_travel"  # 穿越
    SYSTEM_FLOW = "system_flow"  # 系统流
    APOCALYPSE = "apocalypse"    # 末日

class NovelGenerator(ABC):
    """小说生成器基类"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.novel_type = None
        self.title = ""
        self.synopsis = ""
        self.chapters: List[Dict[str, Any]] = []
        self.characters: List[Dict[str, Any]] = []
        self.outline: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        
    @abstractmethod
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成小说大纲"""
        pass
    
    @abstractmethod
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成章节内容"""
        pass
    
    @abstractmethod
    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成人物设定"""
        pass
    
    @abstractmethod
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析文本风格"""
        pass
    
    async def _call_ai_service(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """调用AI服务"""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}{endpoint}",
                    json=data,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise ValueError(f"AI服务调用失败: {e}")
    
    async def generate_full_novel(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成完整小说"""
        try:
            # 生成大纲
            outline = await self.generate_outline(title, synopsis, chapter_count)
            self.outline = outline
            self.title = title
            self.synopsis = synopsis
            
            # 生成人物设定
            characters = []
            if "characters" in outline:
                for char_info in outline["characters"]:
                    character = await self.generate_character(
                        character_name=char_info.get("name", "未知"),
                        character_role=char_info.get("role", "配角"),
                        character_traits=char_info.get("traits", [])
                    )
                    characters.append(character)
            
            self.characters = characters
            
            # 生成章节内容
            chapters = []
            previous_content = ""
            
            for i, chapter_outline in enumerate(outline.get("chapters", [])):
                print(f"生成第 {i+1}/{len(outline.get('chapters', []))} 章...")
                
                chapter_content = await self.generate_chapter(
                    chapter_index=i,
                    chapter_outline=chapter_outline.get("summary", ""),
                    previous_content=previous_content
                )
                
                chapter_data = {
                    "index": i,
                    "title": chapter_outline.get("title", f"第{i+1}章"),
                    "outline": chapter_outline,
                    "content": chapter_content,
                    "word_count": len(chapter_content),
                    "generated_at": datetime.now().isoformat()
                }
                
                chapters.append(chapter_data)
                previous_content = chapter_content
                
                # 添加延迟避免API限流
                await asyncio.sleep(1)
            
            self.chapters = chapters
            
            # 计算统计信息
            total_words = sum(chapter["word_count"] for chapter in chapters)
            
            return {
                "success": True,
                "title": title,
                "synopsis": synopsis,
                "novel_type": self.novel_type.value if self.novel_type else "unknown",
                "chapters": chapters,
                "characters": characters,
                "outline": outline,
                "statistics": {
                    "total_chapters": len(chapters),
                    "total_words": total_words,
                    "average_words_per_chapter": total_words / len(chapters) if chapters else 0,
                    "generation_time": datetime.now().isoformat()
                },
                "metadata": self.metadata
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "title": title,
                "novel_type": self.novel_type.value if self.novel_type else "unknown"
            }

class GenericNovelGenerator(NovelGenerator):
    """通用小说生成器 - 用于快速扩展新类型"""
    
    def __init__(self, novel_type: NovelType, genre_name: str, features: List[str], 
                 style_desc: str, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = novel_type
        self.genre_name = genre_name
        self.features = features
        self.style_desc = style_desc
        self.metadata = {
            "genre": genre_name,
            "features": features,
            "style": style_desc
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        try:
            data = {
                "novel_type": self.novel_type.value,
                "title": title,
                "synopsis": synopsis,
                "chapter_count": chapter_count,
                "model_type": "local"
            }
            result = await self._call_ai_service("/api/v1/generate/outline", data)
            return result if result.get("success") else self._create_default_outline(title, synopsis, chapter_count)
        except Exception as e:
            print(f"大纲生成失败，使用默认结构: {e}")
            return self._create_default_outline(title, synopsis, chapter_count)
    
    def _create_default_outline(self, title: str, synopsis: str, chapter_count: int) -> Dict[str, Any]:
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [{"title": f"第{i+1}章", "summary": f"{self.genre_name}故事第{i+1}部分", "plot": "待补充", "characters": []} for i in range(chapter_count)],
            "characters": [
                {"name": "主角", "role": "主角", "traits": ["勇敢", "聪明", "坚韧"]},
                {"name": "伙伴", "role": "配角", "traits": ["忠诚", "幽默"]}
            ]
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        try:
            data = {
                "novel_type": self.novel_type.value,
                "chapter_title": f"第{chapter_index + 1}章",
                "chapter_outline": chapter_outline,
                "previous_content": previous_content,
                "model_type": "local",
                "max_tokens": 2000,
                "temperature": 0.8
            }
            result = await self._call_ai_service("/api/v1/generate/chapter", data)
            return result.get("content", "") if result.get("success") else self._create_default_chapter(chapter_index, chapter_outline)
        except Exception as e:
            print(f"章节生成失败，使用默认内容: {e}")
            return self._create_default_chapter(chapter_index, chapter_outline)
    
    def _create_default_chapter(self, chapter_index: int, chapter_outline: str) -> str:
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的{self.genre_name}内容）

"""
    
    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        try:
            data = {
                "novel_type": self.novel_type.value,
                "character_name": character_name,
                "character_role": character_role,
                "character_traits": character_traits,
                "model_type": "local"
            }
            result = await self._call_ai_service("/api/v1/generate/character", data)
            return result.get("character_profile", {}) if result.get("success") else self._create_default_character(character_name, character_role, character_traits)
        except Exception as e:
            print(f"人物生成失败，使用默认设定: {e}")
            return self._create_default_character(character_name, character_role, character_traits)
    
    def _create_default_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        return {
            "basic_info": {"age": 25, "gender": "男", "appearance": "普通外表", "occupation": self.genre_name + "主角"},
            "personality": character_traits,
            "background": f"{character_name}是{self.genre_name}故事的主角。",
            "relationships": [],
            "growth": "经历磨难，最终成长",
            "skills": ["基础技能"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        try:
            data = {"content": content, "analysis_type": "comprehensive", "model_type": "local"}
            result = await self._call_ai_service("/api/v1/analyze/style", data)
            return result.get("analysis_results", {}) if result.get("success") else self._create_default_style_analysis()
        except Exception as e:
            print(f"风格分析失败，使用默认分析: {e}")
            return self._create_default_style_analysis()
    
    def _create_default_style_analysis(self) -> Dict[str, Any]:
        return {
            "language_style": f"{self.genre_name}风格",
            "narrative_perspective": "第三人称视角",
            "emotional_tone": "紧凑、引人入胜",
            "literary_devices": self.features[:3],
            "sentence_features": "节奏明快",
            "vocabulary_features": f"{self.genre_name}相关词汇丰富",
            "overall_evaluation": f"典型的{self.genre_name}风格"
        }


# 历史小说生成器

class SciFiNovelGenerator(GenericNovelGenerator):
    """科幻小说生成器"""
    novel_type = NovelType.SCIFI
    metadata = {
        "name": "科幻小说生成器",
        "description": "生成硬科幻、软科幻、太空歌剧等科幻类小说",
        "elements": ["未来科技", "星际文明", "人工智能", "时间旅行", "平行宇宙"],
        "atmosphere": "硬科幻、赛博朋克、太空歌剧、近未来",
        "style": "理性、宏大、充满想象力"
    }
    _type_name = "科幻小说"
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.SCIFI, "科幻",
            ["未来科技", "太空探索", "人工智能", "时间旅行"],
            "硬科幻风格，注重科学逻辑和世界观设定",
            ai_service_url
        )

class MysteryNovelGenerator(GenericNovelGenerator):
    """悬疑推理小说生成器"""
    novel_type = NovelType.MYSTERY
    metadata = {
        "name": "悬疑推理小说生成器",
        "description": "生成逻辑严密、情节曲折的推理小说",
        "elements": ["犯罪谜题", "逻辑推理", "悬疑氛围", "意外结局", "侦探角色"],
        "atmosphere": "悬疑、紧张、引人入胜",
        "style": "理性、逻辑严密、注重细节"
    }
    _type_name = "悬疑推理小说"
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.MYSTERY, "悬疑推理",
            ["犯罪谜题", "逻辑推理", "悬疑氛围", "意外结局"],
            "注重逻辑推理和悬疑氛围营造",
            ai_service_url
        )

class RomanceNovelGenerator(GenericNovelGenerator):
    """言情小说生成器"""
    novel_type = NovelType.ROMANCE
    metadata = {
        "name": "言情小说生成器",
        "description": "生成情感细腻、人物关系复杂的言情小说",
        "elements": ["情感细腻", "人物关系复杂", "甜蜜虐心", "浪漫氛围", "情感冲突"],
        "atmosphere": "甜蜜、浪漫、温馨、虐心",
        "style": "情感细腻、描写生动、注重内心世界"
    }
    _type_name = "言情小说"
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.ROMANCE, "言情",
            ["情感细腻", "人物关系复杂", "甜蜜虐心", "浪漫氛围"],
            "注重情感描写和人物内心世界",
            ai_service_url
        )

class FantasyNovelGenerator(GenericNovelGenerator):
    """奇幻小说生成器"""
    novel_type = NovelType.FANTASY
    metadata = {
        "name": "奇幻小说生成器",
        "description": "生成魔法系统、异世界、种族多样的奇幻小说",
        "elements": ["魔法系统", "异世界", "种族多样", "史诗冒险", "世界观构建"],
        "atmosphere": "史诗、冒险、热血、神秘",
        "style": "想象力丰富、描写宏大、注重世界观"
    }
    _type_name = "奇幻小说"
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.FANTASY, "奇幻",
            ["魔法系统", "异世界", "种族多样", "史诗冒险"],
            "注重世界观构建和奇幻元素",
            ai_service_url
        )

class UrbanNovelGenerator(GenericNovelGenerator):
    """都市小说生成器"""
    novel_type = NovelType.URBAN
    metadata = {
        "name": "都市小说生成器",
        "description": "生成贴近现实、人物鲜明的都市小说",
        "elements": ["现实背景", "人物鲜明", "生活气息", "社会百态", "职场竞争"],
        "atmosphere": "现实、励志、热血、温情",
        "style": "贴近现实、描写细腻、注重人情世故"
    }
    _type_name = "都市小说"
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.URBAN, "都市",
            ["现实背景", "人物鲜明", "生活气息", "社会百态"],
            "贴近现实，描写都市生活和人情世故",
            ai_service_url
        )


class HistoryNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.HISTORY, "历史",
            ["历史背景", "朝代更迭", "权谋斗争", "英雄人物", "文化描写"],
            "注重历史细节和时代氛围，融合真实历史事件与虚构情节"
        )

# 武侠小说生成器
class MartialArtsNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.MARTIAL_ARTS, "武侠",
            ["江湖恩怨", "武功招式", "侠义精神", "门派纷争", "武林秘籍"],
            "传统武侠风格，注重武功描写和江湖情义"
        )

# 仙侠小说生成器
class XianxiaNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.XIANXIA, "仙侠",
            ["修仙体系", "法宝灵器", "渡劫飞升", "宗门势力", "天材地宝"],
            "玄幻仙侠风格，注重修炼体系和仙界设定"
        )

# 恐怖小说生成器
class HorrorNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.HORROR, "恐怖",
            ["恐怖氛围", "心理恐惧", "超自然现象", "悬疑解谜", "惊悚反转"],
            "恐怖悬疑风格，注重氛围营造和心理描写"
        )

# 军事小说生成器
class MilitaryNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.MILITARY, "军事",
            ["战争场面", "军事策略", "战友情谊", "武器装备", "铁血精神"],
            "军事题材风格，注重战术描写和军人血性"
        )

# 游戏小说生成器
class GameNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.GAME, "游戏",
            ["游戏系统", "等级提升", "装备道具", "副本挑战", "公会争霸"],
            "游戏流风格，注重系统设定和升级爽感"
        )

# 体育小说生成器
class SportsNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.SPORTS, "体育",
            ["竞技比赛", "团队合作", "热血拼搏", "成长历程", "体育精神"],
            "体育竞技风格，注重比赛描写和人物成长"
        )

# 穿越小说生成器
class TimeTravelNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.TIME_TRAVEL, "穿越",
            ["时空穿越", "蝴蝶效应", "历史改变", "现代知识", "异世界生存"],
            "穿越题材风格，注重古今对比和情节反转"
        )

# 系统流小说生成器
class SystemFlowNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.SYSTEM_FLOW, "系统流",
            ["金手指系统", "任务奖励", "属性面板", "技能树", "逆袭打脸"],
            "系统流风格，注重系统设定和爽点设计"
        )

# 末日小说生成器
class ApocalypseNovelGenerator(GenericNovelGenerator):
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(
            NovelType.APOCALYPSE, "末日",
            ["末世生存", "丧尸变异", "资源争夺", "基地建设", "人性考验"],
            "末日废土风格，注重生存描写和人性刻画"
        )


# 小说生成器工厂
class NovelGeneratorFactory:
    """小说生成器工厂"""
    
    @staticmethod
    def create_generator(novel_type: NovelType, ai_service_url: str = "http://localhost:8001") -> NovelGenerator:
        """创建小说生成器"""
        generators = {
            # 基础类型
            NovelType.SCIFI: SciFiNovelGenerator,
            NovelType.MYSTERY: MysteryNovelGenerator,
            NovelType.ROMANCE: RomanceNovelGenerator,
            NovelType.FANTASY: FantasyNovelGenerator,
            NovelType.URBAN: UrbanNovelGenerator,
            # 新增类型
            NovelType.HISTORY: HistoryNovelGenerator,
            NovelType.MARTIAL_ARTS: MartialArtsNovelGenerator,
            NovelType.XIANXIA: XianxiaNovelGenerator,
            NovelType.HORROR: HorrorNovelGenerator,
            NovelType.MILITARY: MilitaryNovelGenerator,
            NovelType.GAME: GameNovelGenerator,
            NovelType.SPORTS: SportsNovelGenerator,
            NovelType.TIME_TRAVEL: TimeTravelNovelGenerator,
            NovelType.SYSTEM_FLOW: SystemFlowNovelGenerator,
            NovelType.APOCALYPSE: ApocalypseNovelGenerator,
        }
        
        generator_class = generators.get(novel_type)
        if not generator_class:
            raise ValueError(f"不支持的小说类型: {novel_type}")
        
        return generator_class(ai_service_url)
    
    @staticmethod
    def get_supported_types() -> List[Dict[str, str]]:
        """获取支持的小说类型"""
        return [
            {"type": "scifi", "name": "科幻小说", "description": "具有前瞻性的科技设定和世界观"},
            {"type": "mystery", "name": "悬疑推理", "description": "逻辑严密、情节曲折的推理故事"},
            {"type": "romance", "name": "言情小说", "description": "情感细腻、人物关系复杂的情感故事"},
            {"type": "fantasy", "name": "奇幻小说", "description": "丰富的魔法和世界观设定的奇幻故事"},
            {"type": "urban", "name": "都市小说", "description": "贴近现实、人物鲜明的都市故事"},
            {"type": "history", "name": "历史小说", "description": "融合真实历史事件的古代故事"},
            {"type": "martial_arts", "name": "武侠小说", "description": "江湖恩怨、侠义精神的武侠世界"},
            {"type": "xianxia", "name": "仙侠小说", "description": "修仙渡劫、宗门纷争的仙侠世界"},
            {"type": "horror", "name": "恐怖小说", "description": "恐怖悬疑、心理恐惧的惊悚故事"},
            {"type": "military", "name": "军事小说", "description": "战争场面、战友情谊的军旅故事"},
            {"type": "game", "name": "游戏小说", "description": "游戏系统、升级打怪的虚拟世界"},
            {"type": "sports", "name": "体育小说", "description": "竞技比赛、热血拼搏的体育故事"},
            {"type": "time_travel", "name": "穿越小说", "description": "时空穿越、改变历史的奇幻旅程"},
            {"type": "system_flow", "name": "系统流小说", "description": "金手指系统、逆袭打脸的爽文"},
            {"type": "apocalypse", "name": "末日小说", "description": "末世生存、人性考验的废土世界"},
        ]