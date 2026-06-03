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

class RomanceNovelGenerator(NovelGenerator):
    """言情小说生成器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = NovelType.ROMANCE
        self.metadata = {
            "genre": "言情",
            "features": ["情感细腻", "人物关系复杂", "甜蜜虐心", "浪漫氛围"],
            "style": "注重情感描写和人物内心世界"
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成言情小说大纲"""
        try:
            data = {
                "novel_type": "romance",
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
        """创建默认言情小说大纲"""
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [
                {
                    "title": f"第{i+1}章",
                    "summary": f"言情故事第{i+1}部分",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(chapter_count)
            ],
            "characters": [
                {"name": "女主角", "role": "主角", "traits": ["温柔", "善良", "坚强"]},
                {"name": "男主角", "role": "男主", "traits": ["帅气", "专一", "深情"]},
                {"name": "情敌", "role": "配角", "traits": ["嫉妒", "心机"]}
            ],
            "romance_structure": {
                "meeting": "浪漫邂逅",
                "conflict": "误会分离",
                "climax": "真情告白",
                "ending": "幸福结局"
            }
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成言情章节内容"""
        try:
            data = {
                "novel_type": "romance",
                "chapter_title": f"第{chapter_index + 1}章",
                "chapter_outline": chapter_outline,
                "previous_content": previous_content,
                "model_type": "local",
                "max_tokens": 2000,
                "temperature": 0.9
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
        """创建默认言情章节内容"""
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的言情内容，包含甜蜜、虐心、浪漫等元素）

阳光透过咖啡厅的玻璃窗洒进来，她坐在角落的位置，手指无意识地搅动着杯中的拿铁。

"你好，这里有人吗？"

她抬起头，对上了一双深邃的眼眸。那是一个穿着白色衬衫的男人，笑容温暖得像是三月的春风。

"没...没有。"她有些慌乱地回答。

男人坐下，从口袋里拿出一本书。她偷偷看了一眼，竟然是她最喜欢的那本小说。

"你也喜欢这本书？"男人注意到她的目光，微笑着问道。

她的心跳漏了一拍，命运的齿轮在这一刻开始转动。"""
    
    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成言情人物设定"""
        try:
            data = {
                "novel_type": "romance",
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
        """创建默认言情人物设定"""
        return {
            "basic_info": {
                "age": 25,
                "gender": "女" if "女" in character_role else "男",
                "appearance": "清秀可人，笑起来有两个小酒窝" if "女" in character_role else "帅气俊朗，眼神温柔",
                "occupation": "设计师" if "女" in character_role else "总裁"
            },
            "personality": character_traits,
            "background": f"{character_name}是一个{('温柔善良' if '女' in character_role else '成熟稳重')}的人，有着不为人知的过去。",
            "relationships": [],
            "growth": "从情伤中走出，学会真正地爱与被爱",
            "skills": ["厨艺", "绘画", "钢琴", "写作"] if "女" in character_role else ["商业头脑", "音乐", "运动", "厨艺"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析言情文本风格"""
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
        """创建默认言情风格分析"""
        return {
            "language_style": "言情风格，情感细腻，描写细腻",
            "narrative_perspective": "第一人称或第三人称限制视角",
            "emotional_tone": "甜蜜、虐心、浪漫、温馨",
            "literary_devices": ["心理描写", "环境烘托", "对话推动", "细节刻画"],
            "sentence_features": "短句为主，节奏轻快，情感充沛",
            "vocabulary_features": "情感词汇丰富，描写细腻",
            "overall_evaluation": "典型的言情风格，适合喜欢浪漫故事的读者"
        }

class FantasyNovelGenerator(NovelGenerator):
    """奇幻小说生成器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = NovelType.FANTASY
        self.metadata = {
            "genre": "奇幻",
            "features": ["魔法系统", "异世界", "种族多样", "史诗冒险"],
            "style": "注重世界观构建和奇幻元素"
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成奇幻小说大纲"""
        try:
            data = {
                "novel_type": "fantasy",
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
        """创建默认奇幻小说大纲"""
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [
                {
                    "title": f"第{i+1}章",
                    "summary": f"奇幻故事第{i+1}部分",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(chapter_count)
            ],
            "characters": [
                {"name": "勇者", "role": "主角", "traits": ["勇敢", "正义", "成长"]},
                {"name": "法师", "role": "伙伴", "traits": ["智慧", "神秘", "强大"]},
                {"name": "魔王", "role": "反派", "traits": ["强大", "残忍", "野心"]}
            ],
            "world_building": {
                "magic_system": "元素魔法体系",
                "races": ["人类", "精灵", "矮人", "兽人"],
                "geography": "多块大陆，各有特色",
                "history": "古老的战争与预言"
            }
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成奇幻章节内容"""
        try:
            data = {
                "novel_type": "fantasy",
                "chapter_title": f"第{chapter_index + 1}章",
                "chapter_outline": chapter_outline,
                "previous_content": previous_content,
                "model_type": "local",
                "max_tokens": 2000,
                "temperature": 0.85
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
        """创建默认奇幻章节内容"""
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的奇幻内容，包含魔法、异世界、冒险等元素）

月光洒在古老的石板路上，勇者紧握着手中的圣剑，感受着剑身传来的温暖力量。

"前面就是魔王城了。"法师指着远处那座笼罩在黑暗中的城堡，"我能感受到那里强大的魔力波动。"

勇者点点头："我们已经走了这么远，不能在这里退缩。"

精灵弓箭手从树梢上跳下来："前方有巡逻的魔物，数量不少。"

矮人战士锤了锤自己的盾牌："那就让他们来吧！我的斧头已经饥渴难耐了！"

勇者看着自己的伙伴们，心中涌起一股暖流。无论前方有什么危险，他们都会一起面对。

"出发！"勇者高举圣剑，剑身绽放出耀眼的光芒。"""
    
    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成奇幻人物设定"""
        try:
            data = {
                "novel_type": "fantasy",
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
        """创建默认奇幻人物设定"""
        return {
            "basic_info": {
                "age": 20,
                "gender": "男",
                "appearance": "棕色短发，眼神坚定，身穿皮甲",
                "occupation": "冒险者"
            },
            "personality": character_traits,
            "background": f"{character_name}是一个来自小村庄的年轻人，被命运选中成为勇者。",
            "relationships": [],
            "growth": "从普通村民成长为拯救世界的英雄",
            "skills": ["剑术", "基础魔法", "野外生存", "领导力"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析奇幻文本风格"""
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
        """创建默认奇幻风格分析"""
        return {
            "language_style": "奇幻风格，想象力丰富，描写宏大",
            "narrative_perspective": "第三人称全知视角",
            "emotional_tone": "史诗、冒险、热血、神秘",
            "literary_devices": ["世界观构建", "魔法描写", "种族设定", "史诗叙事"],
            "sentence_features": "长短句结合，描写细腻，场景宏大",
            "vocabulary_features": "奇幻词汇丰富，独创性强",
            "overall_evaluation": "典型的奇幻风格，适合喜欢冒险故事的读者"
        }

class UrbanNovelGenerator(NovelGenerator):
    """都市小说生成器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        super().__init__(ai_service_url)
        self.novel_type = NovelType.URBAN
        self.metadata = {
            "genre": "都市",
            "features": ["现实背景", "人物鲜明", "生活气息", "社会百态"],
            "style": "贴近现实，描写都市生活和人情世故"
        }
    
    async def generate_outline(self, title: str, synopsis: str, chapter_count: int = 10) -> Dict[str, Any]:
        """生成都市小说大纲"""
        try:
            data = {
                "novel_type": "urban",
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
        """创建默认都市小说大纲"""
        return {
            "title": title,
            "synopsis": synopsis,
            "chapters": [
                {
                    "title": f"第{i+1}章",
                    "summary": f"都市故事第{i+1}部分",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(chapter_count)
            ],
            "characters": [
                {"name": "主角", "role": "主角", "traits": ["聪明", "努力", "上进"]},
                {"name": "女主", "role": "女主", "traits": ["独立", "善良", "美丽"]},
                {"name": "对手", "role": "配角", "traits": ["野心", "手段", "城府"]}
            ],
            "urban_elements": {
                "setting": "现代都市",
                "industry": "科技/金融/娱乐",
                "conflicts": "职场竞争、感情纠葛、家庭矛盾"
            }
        }
    
    async def generate_chapter(self, chapter_index: int, chapter_outline: str, previous_content: str = "") -> str:
        """生成都市章节内容"""
        try:
            data = {
                "novel_type": "urban",
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
        """创建默认都市章节内容"""
        return f"""第{chapter_index + 1}章

{chapter_outline}

（此处为AI生成的都市内容，包含职场、生活、情感等元素）

清晨的阳光透过落地窗洒进办公室，李明站在窗前，俯瞰着这座繁华的城市。

"李总，早会要开始了。"秘书敲门提醒道。

李明点点头，整理了一下西装领带。今天有一个重要的项目提案，关系到公司未来的发展方向。

会议室里，各部门负责人已经就座。竞争对手的代表也来了，带着挑衅的笑容。

"李总，听说你们也在争取这个项目？"对手代表假惺惺地笑着。

李明不卑不亢地回答："公平竞争，各凭本事。"

会议开始了，李明打开精心准备的PPT，自信地开始讲解他的方案。在这个弱肉强食的商业世界里，只有最强者才能生存。"""
    
    async def generate_character(self, character_name: str, character_role: str, character_traits: List[str]) -> Dict[str, Any]:
        """生成都市人物设定"""
        try:
            data = {
                "novel_type": "urban",
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
        """创建默认都市人物设定"""
        return {
            "basic_info": {
                "age": 28,
                "gender": "男",
                "appearance": "穿着得体，气质不凡",
                "occupation": "企业高管"
            },
            "personality": character_traits,
            "background": f"{character_name}是白手起家的创业者，凭借自己的努力在城市站稳脚跟。",
            "relationships": [],
            "growth": "从普通职员成长为商业精英",
            "skills": ["商业谈判", "领导力", "人脉资源", "危机处理"]
        }
    
    async def analyze_style(self, content: str) -> Dict[str, Any]:
        """分析都市文本风格"""
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
        """创建默认都市风格分析"""
        return {
            "language_style": "都市风格，贴近现实，描写细腻",
            "narrative_perspective": "第三人称限制视角",
            "emotional_tone": "现实、励志、热血、温情",
            "literary_devices": ["生活细节", "职场描写", "人物对话", "心理刻画"],
            "sentence_features": "短句为主，节奏明快，对话多",
            "vocabulary_features": "现代词汇丰富，生活化表达",
            "overall_evaluation": "典型的都市风格，适合喜欢现实题材的读者"
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