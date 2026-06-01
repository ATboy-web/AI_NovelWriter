"""
事物描写库模块
管理和生成事物描写
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class DescriptionCategory(str, Enum):
    """描写类别"""
    NATURE = "nature"  # 自然景观
    ARCHITECTURE = "architecture"  # 建筑
    CHARACTER = "character"  # 人物外貌
    EMOTION = "emotion"  # 情感
    ACTION = "action"  # 动作
    WEATHER = "weather"  # 天气
    FOOD = "food"  # 食物
    CLOTHING = "clothing"  # 服饰
    WEAPON = "weapon"  # 武器
    MAGICAL = "magical"  # 魔法/超自然

class DescriptionStyle(str, Enum):
    """描写风格"""
    DETAILED = "detailed"  # 详细
    CONCISE = "concise"  # 简洁
    POETIC = "poetic"  # 诗意
    REALISTIC = "realistic"  # 写实
    FANTASTICAL = "fantastical"  # 奇幻

class DescriptionManager:
    """描写管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.description_library: Dict[str, List[Dict[str, Any]]] = {}
        self.user_descriptions: Dict[str, List[Dict[str, Any]]] = {}
        
        # 初始化内置描写库
        self._init_builtin_descriptions()
    
    def _init_builtin_descriptions(self):
        """初始化内置描写库"""
        self.description_library = {
            DescriptionCategory.NATURE.value: [
                {
                    "name": "日出",
                    "tags": ["自然", "日出", "清晨"],
                    "description": "东方的天际泛起鱼肚白，一轮红日缓缓升起，金色的阳光穿透云层，洒向大地。晨露在草叶上闪烁，仿佛无数颗钻石。",
                    "usage": "适合描写清晨、希望、新开始"
                },
                {
                    "name": "月夜",
                    "tags": ["自然", "月亮", "夜晚"],
                    "description": "一轮明月高悬天际，银色的月光洒满大地。远处的山峦在月光下显得朦胧而神秘，近处的湖水波光粼粼，倒映着月亮的影子。",
                    "usage": "适合描写夜晚、宁静、思念"
                },
                {
                    "name": "暴风雨",
                    "tags": ["自然", "天气", "暴风雨"],
                    "description": "乌云密布，狂风呼啸，豆大的雨点砸向大地。闪电划破夜空，雷声震耳欲聋。树木在风中摇曳，仿佛随时会被连根拔起。",
                    "usage": "适合描写冲突、危机、情绪激动"
                }
            ],
            DescriptionCategory.CHARACTER.value: [
                {
                    "name": "英俊男子",
                    "tags": ["人物", "外貌", "男性"],
                    "description": "他身材高大，面容英俊，剑眉星目，鼻梁高挺。一头黑发随风飘动，眼神深邃而锐利，仿佛能看透人心。",
                    "usage": "适合描写男主角、英俊潇洒的角色"
                },
                {
                    "name": "美丽女子",
                    "tags": ["人物", "外貌", "女性"],
                    "description": "她容貌绝美，肤如凝脂，眉如远山，目若秋水。一头青丝如瀑布般垂落，举手投足间散发着优雅的气质。",
                    "usage": "适合描写女主角、美丽动人的角色"
                }
            ],
            DescriptionCategory.EMOTION.value: [
                {
                    "name": "愤怒",
                    "tags": ["情感", "愤怒", "激动"],
                    "description": "他的双眼喷出怒火，拳头紧握，青筋暴起。胸膛剧烈起伏，仿佛一座即将爆发的火山。",
                    "usage": "适合描写角色愤怒、激动的情绪"
                },
                {
                    "name": "悲伤",
                    "tags": ["情感", "悲伤", "失落"],
                    "description": "她的眼眶泛红，泪水在眼眶中打转。嘴角微微下垂，整个人仿佛失去了灵魂，空洞地望着远方。",
                    "usage": "适合描写角色悲伤、失落的情绪"
                }
            ],
            DescriptionCategory.ACTION.value: [
                {
                    "name": "战斗",
                    "tags": ["动作", "战斗", "打斗"],
                    "description": "他身形一闪，如鬼魅般冲向敌人。拳风呼啸，每一击都带着千钧之力。敌人节节败退，根本无法抵挡这凌厉的攻势。",
                    "usage": "适合描写战斗、打斗场面"
                }
            ],
            DescriptionCategory.WEATHER.value: [
                {
                    "name": "晴天",
                    "tags": ["天气", "晴天", "阳光"],
                    "description": "天空湛蓝如洗，白云悠悠飘过。阳光明媚，温暖而舒适，照在身上暖洋洋的。",
                    "usage": "适合描写好天气、愉快的心情"
                }
            ]
        }
    
    async def generate_description(
        self,
        subject: str,
        category: DescriptionCategory,
        style: DescriptionStyle = DescriptionStyle.DETAILED,
        context: Optional[str] = None,
        length: str = "medium"
    ) -> Dict[str, Any]:
        """生成事物描写"""
        try:
            import httpx
            
            # 获取相关描写作为参考
            reference_descriptions = self._get_reference_descriptions(
                category, subject
            )
            
            prompt = f"""请生成关于"{subject}"的描写。

类别：{category.value}
风格：{style.value}
长度：{length}
{f'上下文：{context}' if context else ''}

参考描写：
{reference_descriptions}

请按照以下要求生成描写：
1. 语言生动形象，富有画面感
2. 运用多种修辞手法（比喻、拟人、排比等）
3. 符合指定的风格和长度
4. 适合在小说中使用

请直接输出描写内容。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "事物描写",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 500,
                        "temperature": 0.8
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    description = result.get("content", "")
                    
                    return {
                        "success": True,
                        "subject": subject,
                        "category": category.value,
                        "style": style.value,
                        "description": description,
                        "length": len(description)
                    }
            
            return {
                "success": False,
                "error": "描写生成失败",
                "subject": subject
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "subject": subject
            }
    
    async def generate_scene_description(
        self,
        scene_type: str,
        elements: List[str],
        mood: Optional[str] = None,
        time_of_day: Optional[str] = None,
        weather: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成场景描写"""
        try:
            import httpx
            
            prompt = f"""请生成一个完整的场景描写。

场景类型：{scene_type}
场景元素：{', '.join(elements)}
{f'氛围：{mood}' if mood else ''}
{f'时间：{time_of_day}' if time_of_day else ''}
{f'天气：{weather}' if weather else ''}

请生成一个连贯的场景描写，要求：
1. 包含所有指定的元素
2. 营造出指定的氛围
3. 运用多种感官描写（视觉、听觉、嗅觉、触觉）
4. 语言生动，富有画面感

请直接输出场景描写。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "场景描写",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 800,
                        "temperature": 0.8
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    description = result.get("content", "")
                    
                    return {
                        "success": True,
                        "scene_type": scene_type,
                        "elements": elements,
                        "mood": mood,
                        "description": description,
                        "length": len(description)
                    }
            
            return {
                "success": False,
                "error": "场景描写生成失败",
                "scene_type": scene_type
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "scene_type": scene_type
            }
    
    async def enhance_description(
        self,
        original_description: str,
        enhancement_type: str = "vivid"
    ) -> Dict[str, Any]:
        """增强描写"""
        try:
            import httpx
            
            prompt = f"""请增强以下描写的表达效果。

原文描写：
{original_description}

增强类型：{enhancement_type}

请按照以下要求进行增强：
1. 添加更多细节和感官描写
2. 使用更生动的修辞手法
3. 增强画面感和氛围感
4. 保持原文的核心意思

请直接输出增强后的描写。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "描写增强",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 600,
                        "temperature": 0.7
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    enhanced_description = result.get("content", "")
                    
                    return {
                        "success": True,
                        "original_description": original_description,
                        "enhanced_description": enhanced_description,
                        "enhancement_type": enhancement_type,
                        "original_length": len(original_description),
                        "enhanced_length": len(enhanced_description)
                    }
            
            return {
                "success": False,
                "error": "描写增强失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_reference_descriptions(
        self,
        category: DescriptionCategory,
        subject: str
    ) -> str:
        """获取参考描写"""
        references = []
        
        # 从内置库中查找
        category_descriptions = self.description_library.get(
            category.value, []
        )
        
        for desc in category_descriptions:
            # 检查标签匹配
            tags = desc.get("tags", [])
            if any(tag in subject for tag in tags):
                references.append(f"- {desc['name']}: {desc['description'][:100]}...")
        
        # 从用户库中查找
        user_category_descriptions = self.user_descriptions.get(
            category.value, []
        )
        
        for desc in user_category_descriptions:
            tags = desc.get("tags", [])
            if any(tag in subject for tag in tags):
                references.append(f"- {desc['name']}: {desc['description'][:100]}...")
        
        if references:
            return "\n".join(references[:3])
        
        return "暂无参考描写"
    
    def add_to_library(
        self,
        category: DescriptionCategory,
        name: str,
        description: str,
        tags: List[str],
        usage: Optional[str] = None
    ):
        """添加描写到用户库"""
        if category.value not in self.user_descriptions:
            self.user_descriptions[category.value] = []
        
        self.user_descriptions[category.value].append({
            "name": name,
            "description": description,
            "tags": tags,
            "usage": usage,
            "added_at": datetime.now().isoformat()
        })
    
    def search_descriptions(
        self,
        query: str,
        category: Optional[DescriptionCategory] = None
    ) -> List[Dict[str, Any]]:
        """搜索描写"""
        results = []
        
        # 搜索内置库
        for cat, descriptions in self.description_library.items():
            if category and cat != category.value:
                continue
            
            for desc in descriptions:
                if self._matches_query(desc, query):
                    results.append({
                        **desc,
                        "category": cat,
                        "source": "builtin"
                    })
        
        # 搜索用户库
        for cat, descriptions in self.user_descriptions.items():
            if category and cat != category.value:
                continue
            
            for desc in descriptions:
                if self._matches_query(desc, query):
                    results.append({
                        **desc,
                        "category": cat,
                        "source": "user"
                    })
        
        return results
    
    def _matches_query(self, description: Dict[str, Any], query: str) -> bool:
        """检查描写是否匹配查询"""
        # 检查名称
        if query.lower() in description.get("name", "").lower():
            return True
        
        # 检查标签
        tags = description.get("tags", [])
        for tag in tags:
            if query.lower() in tag.lower():
                return True
        
        # 检查描述内容
        if query.lower() in description.get("description", "").lower():
            return True
        
        return False
    
    def get_library_stats(self) -> Dict[str, Any]:
        """获取库统计信息"""
        stats = {
            "builtin_categories": len(self.description_library),
            "user_categories": len(self.user_descriptions),
            "total_builtin": sum(
                len(descs) for descs in self.description_library.values()
            ),
            "total_user": sum(
                len(descs) for descs in self.user_descriptions.values()
            )
        }
        
        return stats
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """获取所有类别"""
        categories = []
        
        for category in DescriptionCategory:
            builtin_count = len(
                self.description_library.get(category.value, [])
            )
            user_count = len(
                self.user_descriptions.get(category.value, [])
            )
            
            categories.append({
                "name": category.value,
                "builtin_count": builtin_count,
                "user_count": user_count,
                "total_count": builtin_count + user_count
            })
        
        return categories
    
    def export_library(self, filepath: str):
        """导出库"""
        try:
            data = {
                "description_library": self.description_library,
                "user_descriptions": self.user_descriptions,
                "exported_at": datetime.now().isoformat()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"库已导出到: {filepath}")
            
        except Exception as e:
            print(f"导出失败: {e}")
    
    def import_library(self, filepath: str):
        """导入库"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.description_library.update(
                data.get("description_library", {})
            )
            self.user_descriptions.update(
                data.get("user_descriptions", {})
            )
            
            print(f"库已从 {filepath} 导入")
            
        except Exception as e:
            print(f"导入失败: {e}")


# 全局实例
_description_manager = None

def get_description_manager() -> DescriptionManager:
    """获取描写管理器实例"""
    global _description_manager
    if _description_manager is None:
        _description_manager = DescriptionManager()
    return _description_manager


# 便捷函数
async def generate_description(
    subject: str,
    category: str = "nature",
    style: str = "detailed",
    context: Optional[str] = None,
    length: str = "medium"
) -> Dict[str, Any]:
    """生成事物描写"""
    manager = get_description_manager()
    return await manager.generate_description(
        subject=subject,
        category=DescriptionCategory(category),
        style=DescriptionStyle(style),
        context=context,
        length=length
    )

async def generate_scene_description(
    scene_type: str,
    elements: List[str],
    mood: Optional[str] = None,
    time_of_day: Optional[str] = None,
    weather: Optional[str] = None
) -> Dict[str, Any]:
    """生成场景描写"""
    manager = get_description_manager()
    return await manager.generate_scene_description(
        scene_type=scene_type,
        elements=elements,
        mood=mood,
        time_of_day=time_of_day,
        weather=weather
    )

async def enhance_description(
    original_description: str,
    enhancement_type: str = "vivid"
) -> Dict[str, Any]:
    """增强描写"""
    manager = get_description_manager()
    return await manager.enhance_description(
        original_description=original_description,
        enhancement_type=enhancement_type
    )

def search_descriptions(
    query: str,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """搜索描写"""
    manager = get_description_manager()
    return manager.search_descriptions(
        query=query,
        category=DescriptionCategory(category) if category else None
    )
