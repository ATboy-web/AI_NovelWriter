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
    SCIFI = "scifi"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    FANTASY = "fantasy"
    URBAN = "urban"

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

class SciFiNovelGenerator(NovelGenerator):
    """科幻小说生成器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = NovelType.SCIFI
        self.metadata = {
            "genre": "科幻",
            "features": ["未来科技", "太空探索", "人工智能", "时间旅行"],
            "style": "硬科幻风格，注重科学逻辑和世界观设定"
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成科幻小说大纲"""
        try:
            data = {
                "novel_type": "scifi",
                "title": title,
                "synopsis": synopsis,
                "chapter_count": chapter_count,
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/generate/outline", data)
            
            if result.get("success"):
                return result
            else:
                # 使用默认大纲结构
                return self._create_default_outline(title, synopsis, chapter_count)
                
        except Exception as e:
            print(f"大纲生成失败，使用默认结构: {e}")
            return self._create_default_outline(title, synopsis, chapter_count)
    
    def _create_default_outline(self, title: str, synopsis: str, chapter_count: int) -> Dict[str, Any]:
        """创建默认科幻小说大纲"""
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [
                {
                    "title": f"第{i+1}章",
                    "summary": f"科幻故事第{i+1}部分",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(chapter_count)
            ],
            "characters": [
                {"name": "主角", "role": "主角", "traits": ["聪明", "勇敢"]},
                {"name": "配角", "role": "配角", "traits": ["忠诚", "幽默"]}
            ],
            "world_building": {
                "time_period": "未来",
                "technology_level": "高度发达",
                "society_structure": "待设定"
            }
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成科幻章节内容"""
        try:
            data = {
                "novel_type": "scifi",
                "chapter_title": f"第{chapter_index + 1}章",
                "chapter_outline": chapter_outline,
                "previous_content": previous_content,
                "model_type": "local",
                "max_tokens": 2000,
                "temperature": 0.8
            }
            
            result = await self._call_ai_service("/api/v1/generate/chapter", data)
            
            if result.get("success"):
                return result.get("content", "")
            else:
                return self._create_default_chapter(chapter_index, chapter_outline)
                
        except Exception as e:
            print(f"章节生成失败，使用默认内容: {e}")
            return self._create_default_chapter(chapter_index, chapter_outline)
    
    def _create_default_chapter(self, chapter_index: int, chapter_outline: str) -> str:
        """创建默认科幻章节内容"""
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的科幻内容，包含未来科技、太空探索等元素）

在遥远的未来，人类已经掌握了星际旅行的技术。主角站在宇宙飞船的观景窗前，望着浩瀚的星空，思考着人类在宇宙中的位置。

"我们真的准备好了吗？"主角喃喃自语。

飞船的AI助手回应道："根据我的计算，人类已经有78.3%的概率准备好面对宇宙的挑战。"

主角笑了笑："那剩下的21.7%呢？"

"那是未知的领域，"AI助手回答，"但正是这些未知，让探索变得有意义。"""

    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成科幻人物设定"""
        try:
            data = {
                "novel_type": "scifi",
                "character_name": character_name,
                "character_role": character_role,
                "character_traits": character_traits,
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/generate/character", data)
            
            if result.get("success"):
                return result.get("character_profile", {})
            else:
                return self._create_default_character(character_name, character_role, character_traits)
                
        except Exception as e:
            print(f"人物生成失败，使用默认设定: {e}")
            return self._create_default_character(character_name, character_role, character_traits)
    
    def _create_default_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """创建默认科幻人物设定"""
        return {
            "basic_info": {
                "age": 30,
                "gender": "男",
                "appearance": "身高180cm，短发，眼神坚定",
                "occupation": "星际探险家"
            },
            "personality": character_traits,
            "background": f"{character_name}是一位经验丰富的星际探险家，曾参与多次重要的太空任务。",
            "relationships": [],
            "growth": "从普通飞行员成长为星际舰队的指挥官",
            "skills": ["星际导航", "外星语言", "高级驾驶技术", "危机处理"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析科幻文本风格"""
        try:
            data = {
                "content": content,
                "analysis_type": "comprehensive",
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/analyze/style", data)
            
            if result.get("success"):
                return result.get("analysis_results", {})
            else:
                return self._create_default_style_analysis()
                
        except Exception as e:
            print(f"风格分析失败，使用默认分析: {e}")
            return self._create_default_style_analysis()
    
    def _create_default_style_analysis(self) -> Dict[str, Any]:
        """创建默认科幻风格分析"""
        return {
            "language_style": "硬科幻风格，注重科学逻辑",
            "narrative_perspective": "第三人称全知视角",
            "emotional_tone": "理性、探索、充满希望",
            "literary_devices": ["科学术语", "未来设定", "技术描写"],
            "sentence_features": "长句为主，包含技术细节",
            "vocabulary_features": "科技术语丰富，专业性强",
            "overall_evaluation": "典型的硬科幻风格，适合科幻爱好者"
        }

class MysteryNovelGenerator(NovelGenerator):
    """悬疑推理小说生成器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = NovelType.MYSTERY
        self.metadata = {
            "genre": "悬疑推理",
            "features": ["犯罪谜题", "逻辑推理", "悬疑氛围", "意外结局"],
            "style": "注重逻辑推理和悬疑氛围营造"
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成悬疑推理小说大纲"""
        try:
            data = {
                "novel_type": "mystery",
                "title": title,
                "synopsis": synopsis,
                "chapter_count": chapter_count,
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/generate/outline", data)
            
            if result.get("success"):
                return result
            else:
                return self._create_default_outline(title, synopsis, chapter_count)
                
        except Exception as e:
            print(f"大纲生成失败，使用默认结构: {e}")
            return self._create_default_outline(title, synopsis, chapter_count)
    
    def _create_default_outline(self, title: str, synopsis: str, chapter_count: int) -> Dict[str, Any]:
        """创建默认悬疑推理小说大纲"""
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [
                {
                    "title": f"第{i+1}章",
                    "summary": f"悬疑推理故事第{i+1}部分",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(chapter_count)
            ],
            "characters": [
                {"name": "侦探", "role": "主角", "traits": ["聪明", "观察力强", "逻辑严密"]},
                {"name": "嫌疑人A", "role": "嫌疑人", "traits": ["神秘", "可疑"]},
                {"name": "嫌疑人B", "role": "嫌疑人", "traits": ["冷静", "难以捉摸"]}
            ],
            "mystery_structure": {
                "crime": "待设定",
                "clues": [],
                "red_herrings": [],
                "solution": "待揭示"
            }
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成悬疑推理章节内容"""
        try:
            data = {
                "novel_type": "mystery",
                "chapter_title": f"第{chapter_index + 1}章",
                "chapter_outline": chapter_outline,
                "previous_content": previous_content,
                "model_type": "local",
                "max_tokens": 2000,
                "temperature": 0.7
            }
            
            result = await self._call_ai_service("/api/v1/generate/chapter", data)
            
            if result.get("success"):
                return result.get("content", "")
            else:
                return self._create_default_chapter(chapter_index, chapter_outline)
                
        except Exception as e:
            print(f"章节生成失败，使用默认内容: {e}")
            return self._create_default_chapter(chapter_index, chapter_outline)
    
    def _create_default_chapter(self, chapter_index: int, chapter_outline: str) -> str:
        """创建默认悬疑推理章节内容"""
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的悬疑推理内容，包含逻辑推理、悬疑氛围等元素）

雨夜，侦探站在犯罪现场，仔细观察着每一个细节。死者是一位著名的收藏家，他的书房被翻得乱七八糟。

"奇怪，"侦探喃喃自语，"如果是为了财物，为什么只拿走了那幅画？"

助手回答："也许那幅画价值连城？"

侦探摇摇头："不，这里一定有更深的原因。"

他注意到窗户上的痕迹："看，这里有撬痕，但工具痕迹很专业，不像是普通小偷。"

助手若有所思："您的意思是...这是内部人员干的？"

侦探微微一笑："让我们继续调查，真相总会浮出水面的。"""

    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成悬疑推理人物设定"""
        try:
            data = {
                "novel_type": "mystery",
                "character_name": character_name,
                "character_role": character_role,
                "character_traits": character_traits,
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/generate/character", data)
            
            if result.get("success"):
                return result.get("character_profile", {})
            else:
                return self._create_default_character(character_name, character_role, character_traits)
                
        except Exception as e:
            print(f"人物生成失败，使用默认设定: {e}")
            return self._create_default_character(character_name, character_role, character_traits)
    
    def _create_default_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """创建默认悬疑推理人物设定"""
        return {
            "basic_info": {
                "age": 35,
                "gender": "男",
                "appearance": "身材高大，目光锐利，总是穿着风衣",
                "occupation": "私家侦探"
            },
            "personality": character_traits,
            "background": f"{character_name}是一位经验丰富的侦探，破获过无数棘手案件。",
            "relationships": [],
            "growth": "从普通警察成长为传奇侦探",
            "skills": ["逻辑推理", "观察力", "审讯技巧", "犯罪心理学"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析悬疑推理文本风格"""
        try:
            data = {
                "content": content,
                "analysis_type": "comprehensive",
                "model_type": "local"
            }
            
            result = await self._call_ai_service("/api/v1/analyze/style", data)
            
            if result.get("success"):
                return result.get("analysis_results", {})
            else:
                return self._create_default_style_analysis()
                
        except Exception as e:
            print(f"风格分析失败，使用默认分析: {e}")
            return self._create_default_style_analysis()
    
    def _create_default_style_analysis(self) -> Dict[str, Any]:
        """创建默认悬疑推理风格分析"""
        return {
            "language_style": "悬疑推理风格，注重细节描写",
            "narrative_perspective": "第三人称限制视角",
            "emotional_tone": "紧张、悬疑、引人入胜",
            "literary_devices": ["伏笔", "悬念", "误导", "反转"],
            "sentence_features": "长短句结合，节奏紧凑",
            "vocabulary_features": "描述性词汇丰富，专业术语适度",
            "overall_evaluation": "典型的悬疑推理风格，适合推理爱好者"
        }

# 小说生成器工厂
class NovelGeneratorFactory:
    """小说生成器工厂"""
    
    @staticmethod
    def create_generator(novel_type: NovelType, ai_service_url: str = "http://localhost:8001") -> NovelGenerator:
        """创建小说生成器"""
        generators = {
            NovelType.SCIFI: SciFiNovelGenerator,
            NovelType.MYSTERY: MysteryNovelGenerator,
            # 可以继续添加其他类型
        }
        
        generator_class = generators.get(novel_type)
        if not generator_class:
            raise ValueError(f"不支持的小说类型: {novel_type}")
        
        return generator_class(ai_service_url)
    
    @staticmethod
    def get_supported_types() -> List[Dict[str, str]]:
        """获取支持的小说类型"""
        return [
            {
                "type": "scifi",
                "name": "科幻小说",
                "description": "具有前瞻性的科技设定和世界观"
            },
            {
                "type": "mystery",
                "name": "悬疑推理",
                "description": "逻辑严密、情节曲折的推理故事"
            },
            {
                "type": "romance",
                "name": "言情小说",
                "description": "情感细腻、人物关系复杂的情感故事"
            },
            {
                "type": "fantasy",
                "name": "奇幻小说",
                "description": "丰富的魔法和世界观设定的奇幻故事"
            },
            {
                "type": "urban",
                "name": "都市小说",
                "description": "贴近现实、人物鲜明的都市故事"
            }
        ]