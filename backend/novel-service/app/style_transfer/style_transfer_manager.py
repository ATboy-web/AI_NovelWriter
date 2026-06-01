"""
风格转换模块
提取指定文风进行仿写或改写
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class StyleType(str, Enum):
    """风格类型"""
    LITERARY = "literary"  # 文学风格
    POPULAR = "popular"  # 通俗风格
    CLASSICAL = "classical"  # 古典风格
    MODERN = "modern"  # 现代风格
    HUMOROUS = "humorous"  # 幽默风格
    SERIOUS = "serious"  # 严肃风格
    ROMANTIC = "romantic"  # 浪漫风格
    DARK = "dark"  # 黑暗风格

class TransferMode(str, Enum):
    """转换模式"""
    IMITATE = "imitate"  # 仿写
    REWRITE = "rewrite"  # 改写
    ADAPT = "adapt"  # 改编
    SIMPLIFY = "simplify"  # 简化
    EXPAND = "expand"  # 扩写

class StyleTransferManager:
    """风格转换管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.style_templates: Dict[str, Dict[str, Any]] = {}
        self.transfer_history: List[Dict[str, Any]] = []
        
        # 初始化内置风格模板
        self._init_builtin_styles()
    
    def _init_builtin_styles(self):
        """初始化内置风格模板"""
        self.style_templates = {
            "金庸武侠": {
                "description": "金庸武侠小说风格，语言古朴典雅，武功描写生动",
                "features": ["古朴典雅", "武功描写", "侠义精神", "诗词引用"],
                "example": "他身形一晃，使出一招'亢龙有悔'，掌风凌厉，势不可挡。"
            },
            "莫言魔幻": {
                "description": "莫言魔幻现实主义风格，想象力丰富，语言奔放",
                "features": ["魔幻现实", "想象力丰富", "语言奔放", "乡土气息"],
                "example": "那片高粱地红得像血，在月光下摇曳，仿佛在诉说着什么。"
            },
            "张爱玲都市": {
                "description": "张爱玲都市小说风格，细腻敏感，心理描写深刻",
                "features": ["细腻敏感", "心理描写", "都市气息", "苍凉美感"],
                "example": "上海的月亮，该是铜钱大的一个红黄的湿晕，像朵云轩信笺上落了一滴泪珠。"
            },
            "刘慈欣科幻": {
                "description": "刘慈欣科幻小说风格，宏大叙事，科学严谨",
                "features": ["宏大叙事", "科学严谨", "哲学思考", "宇宙视野"],
                "example": "黑暗森林中，每个文明都是带枪的猎人，必须小心翼翼地前行。"
            },
            "东野圭吾推理": {
                "description": "东野圭吾推理小说风格，逻辑严密，人性深刻",
                "features": ["逻辑严密", "人性深刻", "悬念设置", "意外结局"],
                "example": "嫌疑人X的献身，不是简单的犯罪，而是一个数学天才的完美证明。"
            },
            "网络小说": {
                "description": "网络小说风格，节奏明快，爽点密集",
                "features": ["节奏明快", "爽点密集", "升级打怪", "装逼打脸"],
                "example": "叶凡冷笑一声，区区一个蝼蚁，也敢在他面前嚣张？"
            },
            "严肃文学": {
                "description": "严肃文学风格，语言精炼，思想深刻",
                "features": ["语言精炼", "思想深刻", "人性探索", "社会批判"],
                "example": "他站在那里，看着远方的夕阳，心中涌起一股难以言喻的悲凉。"
            }
        }
    
    async def analyze_style(
        self,
        text: str,
        analysis_depth: str = "detailed"
    ) -> Dict[str, Any]:
        """分析文本风格"""
        try:
            import httpx
            
            prompt = f"""请分析以下文本的写作风格。

文本内容：
{text[:2000]}

请从以下方面进行分析：
1. 语言特点（词汇、句式、修辞）
2. 叙事视角（第一人称/第三人称/全知视角）
3. 情感基调（积极/消极/中性/复杂）
4. 文学手法（比喻、拟人、排比等）
5. 节奏特点（快节奏/慢节奏/变化）
6. 整体风格（属于哪种文学流派）

请以JSON格式输出：
{{
    "language_features": {{
        "vocabulary": "词汇特点",
        "sentence_structure": "句式特点",
        "rhetoric": "修辞手法"
    }},
    "narrative_perspective": "叙事视角",
    "emotional_tone": "情感基调",
    "literary_devices": ["手法1", "手法2"],
    "rhythm": "节奏特点",
    "overall_style": "整体风格",
    "similar_authors": ["相似作家1", "相似作家2"],
    "style_tags": ["标签1", "标签2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "风格分析",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 1000,
                        "temperature": 0.3
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析分析结果
                    analysis_data = self._parse_style_analysis(content)
                    
                    if analysis_data:
                        return {
                            "success": True,
                            "original_text_preview": text[:200],
                            "analysis": analysis_data
                        }
            
            return {
                "success": False,
                "error": "风格分析失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def transfer_style(
        self,
        source_text: str,
        target_style: str,
        mode: TransferMode = TransferMode.IMITATE,
        preserve_plot: bool = True,
        length_adjustment: Optional[str] = None
    ) -> Dict[str, Any]:
        """转换文本风格"""
        try:
            import httpx
            
            # 获取目标风格描述
            style_desc = self._get_style_description(target_style)
            
            prompt = f"""请将以下文本转换为指定风格。

原文：
{source_text[:1500]}

目标风格：{target_style}
风格描述：{style_desc}

转换模式：{mode.value}
保持情节：{'是' if preserve_plot else '否'}
{f'长度调整：{length_adjustment}' if length_adjustment else ''}

请按照以下要求进行转换：
1. 保持原文的核心情节和人物关系
2. 调整语言风格以匹配目标风格
3. 修改叙事方式和表达习惯
4. 适当添加或删减细节

请直接输出转换后的文本。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "风格转换",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.7
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    transferred_text = result.get("content", "")
                    
                    # 保存到历史
                    self.transfer_history.append({
                        "source_text_preview": source_text[:200],
                        "target_style": target_style,
                        "mode": mode.value,
                        "transferred_text_preview": transferred_text[:200],
                        "transferred_at": datetime.now().isoformat()
                    })
                    
                    return {
                        "success": True,
                        "original_text": source_text,
                        "transferred_text": transferred_text,
                        "target_style": target_style,
                        "mode": mode.value,
                        "original_length": len(source_text),
                        "transferred_length": len(transferred_text)
                    }
            
            return {
                "success": False,
                "error": "风格转换失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def imitate_author_style(
        self,
        text: str,
        author_name: str,
        sample_works: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """模仿作家风格"""
        try:
            import httpx
            
            # 构建作家风格描述
            author_desc = f"作家：{author_name}"
            if sample_works:
                author_desc += f"\n参考作品：{', '.join(sample_works[:3])}"
            
            prompt = f"""请将以下文本改写为模仿{author_name}的风格。

原文：
{text[:1500]}

{author_desc}

请模仿该作家的：
1. 语言特点和用词习惯
2. 叙事方式和视角
3. 描写手法和修辞
4. 情感表达和氛围营造

请直接输出改写后的文本。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "风格模仿",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.7
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    imitated_text = result.get("content", "")
                    
                    return {
                        "success": True,
                        "original_text": text,
                        "imitated_text": imitated_text,
                        "author_name": author_name,
                        "original_length": len(text),
                        "imitated_length": len(imitated_text)
                    }
            
            return {
                "success": False,
                "error": "风格模仿失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def adapt_to_genre(
        self,
        text: str,
        target_genre: str,
        adaptation_level: str = "moderate"
    ) -> Dict[str, Any]:
        """改编为其他类型"""
        try:
            import httpx
            
            prompt = f"""请将以下文本改编为{target_genre}类型。

原文：
{text[:1500]}

改编程度：{adaptation_level}

请按照以下要求进行改编：
1. 保持原文的核心故事框架
2. 调整情节以适应目标类型
3. 修改人物设定和关系
4. 调整叙事节奏和重点

请直接输出改编后的文本。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "类型改编",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.7
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    adapted_text = result.get("content", "")
                    
                    return {
                        "success": True,
                        "original_text": text,
                        "adapted_text": adapted_text,
                        "target_genre": target_genre,
                        "adaptation_level": adaptation_level,
                        "original_length": len(text),
                        "adapted_length": len(adapted_text)
                    }
            
            return {
                "success": False,
                "error": "类型改编失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_style_description(self, style_name: str) -> str:
        """获取风格描述"""
        if style_name in self.style_templates:
            template = self.style_templates[style_name]
            return f"{template['description']}。特点：{', '.join(template['features'])}"
        
        return f"{style_name}风格"
    
    def _parse_style_analysis(self, content: str) -> Optional[Dict[str, Any]]:
        """解析风格分析结果"""
        try:
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def get_style_templates(self) -> Dict[str, Dict[str, Any]]:
        """获取风格模板"""
        return self.style_templates
    
    def add_style_template(
        self,
        name: str,
        description: str,
        features: List[str],
        example: str
    ):
        """添加风格模板"""
        self.style_templates[name] = {
            "description": description,
            "features": features,
            "example": example
        }
    
    def get_transfer_history(self) -> List[Dict[str, Any]]:
        """获取转换历史"""
        return self.transfer_history
    
    def clear_transfer_history(self):
        """清空转换历史"""
        self.transfer_history = []


# 全局实例
_style_transfer_manager = None

def get_style_transfer_manager() -> StyleTransferManager:
    """获取风格转换管理器实例"""
    global _style_transfer_manager
    if _style_transfer_manager is None:
        _style_transfer_manager = StyleTransferManager()
    return _style_transfer_manager


# 便捷函数
async def analyze_style(
    text: str,
    analysis_depth: str = "detailed"
) -> Dict[str, Any]:
    """分析文本风格"""
    manager = get_style_transfer_manager()
    return await manager.analyze_style(
        text=text,
        analysis_depth=analysis_depth
    )

async def transfer_style(
    source_text: str,
    target_style: str,
    mode: str = "imitate",
    preserve_plot: bool = True,
    length_adjustment: Optional[str] = None
) -> Dict[str, Any]:
    """转换文本风格"""
    manager = get_style_transfer_manager()
    return await manager.transfer_style(
        source_text=source_text,
        target_style=target_style,
        mode=TransferMode(mode),
        preserve_plot=preserve_plot,
        length_adjustment=length_adjustment
    )

async def imitate_author_style(
    text: str,
    author_name: str,
    sample_works: Optional[List[str]] = None
) -> Dict[str, Any]:
    """模仿作家风格"""
    manager = get_style_transfer_manager()
    return await manager.imitate_author_style(
        text=text,
        author_name=author_name,
        sample_works=sample_works
    )

async def adapt_to_genre(
    text: str,
    target_genre: str,
    adaptation_level: str = "moderate"
) -> Dict[str, Any]:
    """改编为其他类型"""
    manager = get_style_transfer_manager()
    return await manager.adapt_to_genre(
        text=text,
        target_genre=target_genre,
        adaptation_level=adaptation_level
    )
