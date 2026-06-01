"""
角色桥段库模块
管理和生成经典桥段
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class BridgeCategory(str, Enum):
    """桥段类别"""
    ROMANCE = "romance"  # 爱情桥段
    CONFLICT = "conflict"  # 冲突桥段
    REVELATION = "revelation"  # 揭示真相
    GROWTH = "growth"  # 成长桥段
    BETRAYAL = "betrayal"  # 背叛桥段
    REUNION = "reunion"  # 重逢桥段
    SACRIFICE = "sacrifice"  # 牺牲桥段
    REVENGE = "revenge"  # 复仇桥段
    COMEDY = "comedy"  # 喜剧桥段
    DRAMA = "drama"  # 戏剧桥段

class BridgeTone(str, Enum):
    """桥段基调"""
    SERIOUS = "serious"  # 严肃
    HUMOROUS = "humorous"  # 幽默
    ROMANTIC = "romantic"  # 浪漫
    DARK = "dark"  # 黑暗
    INSPIRATIONAL = "inspirational"  # 励志
    MYSTERIOUS = "mysterious"  # 神秘

class BridgeManager:
    """桥段管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.bridge_library: Dict[str, List[Dict[str, Any]]] = {}
        self.user_bridges: Dict[str, List[Dict[str, Any]]] = {}
        
        # 初始化内置桥段库
        self._init_builtin_bridges()
    
    def _init_builtin_bridges(self):
        """初始化内置桥段库"""
        self.bridge_library = {
            BridgeCategory.ROMANCE.value: [
                {
                    "name": "英雄救美",
                    "tags": ["爱情", "英雄", "拯救"],
                    "description": "主角在危急时刻拯救了心仪的对象，两人关系因此拉近。",
                    "structure": ["危机出现", "主角出手", "成功拯救", "感情升温"],
                    "usage": "适合描写爱情开始、建立信任",
                    "examples": ["武侠小说中的英雄救美", "现代都市的紧急救援"]
                },
                {
                    "name": "误会分离",
                    "tags": ["爱情", "误会", "分离"],
                    "description": "因为误会或阴谋，相爱的两人被迫分离，经历痛苦后最终解开误会。",
                    "structure": ["误会产生", "双方痛苦", "真相揭示", "重归于好"],
                    "usage": "适合制造戏剧冲突、推动情节",
                    "examples": ["第三者的挑拨", "身份的误解"]
                },
                {
                    "name": "日久生情",
                    "tags": ["爱情", "相处", "感情"],
                    "description": "两人从陌生到熟悉，在长期相处中逐渐产生感情。",
                    "structure": ["初次相遇", "逐渐了解", "感情萌芽", "确认心意"],
                    "usage": "适合描写细腻的感情发展",
                    "examples": ["青梅竹马", "同事日久生情"]
                }
            ],
            BridgeCategory.CONFLICT.value: [
                {
                    "name": "正邪对决",
                    "tags": ["冲突", "正邪", "对决"],
                    "description": "正义与邪恶的最终对决，主角必须战胜强大的敌人。",
                    "structure": ["敌人出现", "实力差距", "修炼提升", "最终决战"],
                    "usage": "适合高潮部分、最终boss战",
                    "examples": ["武侠小说的最终对决", "科幻小说的拯救世界"]
                },
                {
                    "name": "内部矛盾",
                    "tags": ["冲突", "内部", "矛盾"],
                    "description": "团队或组织内部产生分歧和矛盾，需要解决才能继续前进。",
                    "structure": ["矛盾产生", "分歧扩大", "沟通解决", "团结一致"],
                    "usage": "适合描写团队成长、人物关系",
                    "examples": ["队友之间的理念冲突", "家族内部的权力斗争"]
                }
            ],
            BridgeCategory.REVELATION.value: [
                {
                    "name": "身世揭秘",
                    "tags": ["揭示", "身世", "秘密"],
                    "description": "主角发现自己的真实身份或身世秘密，改变了对自己的认知。",
                    "structure": ["线索出现", "调查真相", "真相揭示", "身份转变"],
                    "usage": "适合重大转折、人物成长",
                    "examples": ["发现自己是皇室后裔", "得知亲生父母的真相"]
                },
                {
                    "name": "阴谋揭露",
                    "tags": ["揭示", "阴谋", "真相"],
                    "description": "隐藏的阴谋被揭露，改变了整个故事的走向。",
                    "structure": ["疑点出现", "调查取证", "真相大白", "局势逆转"],
                    "usage": "适合制造悬疑、推动情节",
                    "examples": ["发现幕后黑手", "揭露虚假身份"]
                }
            ],
            BridgeCategory.GROWTH.value: [
                {
                    "name": "名师指点",
                    "tags": ["成长", "师父", "指点"],
                    "description": "主角得到高人指点，实力或境界得到大幅提升。",
                    "structure": ["遇到高人", "拜师学艺", "刻苦修炼", "实力突破"],
                    "usage": "适合描写实力提升、获得新能力",
                    "examples": ["武侠小说的拜师学艺", "科幻小说的技术指导"]
                },
                {
                    "name": "绝境重生",
                    "tags": ["成长", "绝境", "突破"],
                    "description": "主角在绝境中突破自我，获得新的力量或领悟。",
                    "structure": ["陷入绝境", "挣扎求生", "突破极限", "涅槃重生"],
                    "usage": "适合描写重大转折、实力飞跃",
                    "examples": ["走火入魔后的突破", "濒死体验后的觉醒"]
                }
            ],
            BridgeCategory.BETRAYAL.value: [
                {
                    "name": "挚友背叛",
                    "tags": ["背叛", "朋友", "信任"],
                    "description": "主角最信任的朋友或伙伴背叛，造成巨大伤害。",
                    "structure": ["信任建立", "背叛发生", "伤害造成", "信任重建"],
                    "usage": "适合制造戏剧冲突、人物成长",
                    "examples": ["商业伙伴的背叛", "战友的投敌"]
                }
            ],
            BridgeCategory.REUNION.value: [
                {
                    "name": "久别重逢",
                    "tags": ["重逢", "离别", "思念"],
                    "description": "分离多年的人再次重逢，感慨万千。",
                    "structure": ["离别场景", "多年分离", "重逢时刻", "情感爆发"],
                    "usage": "适合描写情感高潮、人物关系",
                    "examples": ["失散多年的亲人重逢", "初恋情人的重逢"]
                }
            ]
        }
    
    async def generate_bridge(
        self,
        category: BridgeCategory,
        characters: List[str],
        scenario: Optional[str] = None,
        tone: BridgeTone = BridgeTone.SERIOUS,
        complexity: str = "medium"
    ) -> Dict[str, Any]:
        """生成桥段"""
        try:
            import httpx
            
            # 获取参考桥段
            reference_bridges = self._get_reference_bridges(category)
            
            prompt = f"""请生成一个{category.value}类别的经典桥段。

参与角色：{', '.join(characters)}
{f'场景设定：{scenario}' if scenario else ''}
基调：{tone.value}
复杂度：{complexity}

参考桥段：
{reference_bridges}

请生成一个完整的桥段，包括：
1. 桥段名称
2. 情节发展（起承转合）
3. 角色行为和对话
4. 情感变化
5. 转折点
6. 结局

请以JSON格式输出：
{{
    "name": "桥段名称",
    "category": "{category.value}",
    "tone": "{tone.value}",
    "characters": {json.dumps(characters)},
    "structure": {{
        "beginning": "开端描述",
        "development": "发展描述",
        "climax": "高潮描述",
        "ending": "结局描述"
    }},
    "dialogue": [
        {{
            "character": "角色名",
            "content": "对话内容",
            "emotion": "情感状态"
        }}
    ],
    "turning_point": "转折点描述",
    "emotional_arc": ["情感变化1", "情感变化2"],
    "themes": ["主题1", "主题2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "桥段生成",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.8
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析桥段
                    bridge_data = self._parse_bridge(content)
                    
                    if bridge_data:
                        return {
                            "success": True,
                            "bridge": bridge_data
                        }
            
            return {
                "success": False,
                "error": "桥段生成失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def combine_bridges(
        self,
        bridge_names: List[str],
        characters: List[str],
        combination_style: str = "sequential"
    ) -> Dict[str, Any]:
        """组合桥段"""
        try:
            import httpx
            
            # 获取指定桥段
            bridges = []
            for name in bridge_names:
                bridge = self._find_bridge_by_name(name)
                if bridge:
                    bridges.append(bridge)
            
            if not bridges:
                return {
                    "success": False,
                    "error": "未找到指定桥段"
                }
            
            # 构建桥段描述
            bridges_desc = []
            for i, bridge in enumerate(bridges, 1):
                bridges_desc.append(
                    f"{i}. {bridge['name']}: {bridge['description']}"
                )
            
            prompt = f"""请将以下桥段组合成一个完整的情节。

参与角色：{', '.join(characters)}

待组合桥段：
{chr(10).join(bridges_desc)}

组合方式：{combination_style}

请将这些桥段有机地组合在一起，要求：
1. 保持每个桥段的核心要素
2. 使桥段之间过渡自然
3. 形成完整的故事线
4. 包含角色的情感变化

请以JSON格式输出：
{{
    "combined_name": "组合桥段名称",
    "characters": {json.dumps(characters)},
    "structure": {{
        "part1": "第一部分描述",
        "part2": "第二部分描述",
        "part3": "第三部分描述"
    }},
    "bridges_used": {json.dumps(bridge_names)},
    "flow": "整体流程描述",
    "emotional_arc": ["情感变化1", "情感变化2"],
    "themes": ["主题1", "主题2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "桥段组合",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.8
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析组合桥段
                    combined_data = self._parse_bridge(content)
                    
                    if combined_data:
                        return {
                            "success": True,
                            "combined_bridge": combined_data
                        }
            
            return {
                "success": False,
                "error": "桥段组合失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def generate_bridge_with_variation(
        self,
        base_bridge_name: str,
        characters: List[str],
        variation_type: str = "modern"
    ) -> Dict[str, Any]:
        """生成桥段变体"""
        try:
            import httpx
            
            # 获取基础桥段
            base_bridge = self._find_bridge_by_name(base_bridge_name)
            
            if not base_bridge:
                return {
                    "success": False,
                    "error": "未找到基础桥段"
                }
            
            prompt = f"""请基于以下经典桥段，生成一个{variation_type}版本的变体。

基础桥段：{base_bridge['name']}
桥段描述：{base_bridge['description']}
桥段结构：{json.dumps(base_bridge.get('structure', []), ensure_ascii=False)}

参与角色：{', '.join(characters)}
变体类型：{variation_type}

请生成一个保持核心要素但背景和细节不同的变体，要求：
1. 保持桥段的核心冲突和情感
2. 将背景转换为{variation_type}设定
3. 调整角色行为以适应新背景
4. 保持戏剧张力

请以JSON格式输出：
{{
    "name": "变体桥段名称",
    "base_bridge": "{base_bridge_name}",
    "variation_type": "{variation_type}",
    "characters": {json.dumps(characters)},
    "description": "变体描述",
    "structure": {{
        "beginning": "开端",
        "development": "发展",
        "climax": "高潮",
        "ending": "结局"
    }},
    "key_differences": ["差异1", "差异2"],
    "preserved_elements": ["保留元素1", "保留元素2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "桥段变体",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.8
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析变体
                    variation_data = self._parse_bridge(content)
                    
                    if variation_data:
                        return {
                            "success": True,
                            "variation": variation_data
                        }
            
            return {
                "success": False,
                "error": "桥段变体生成失败"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_reference_bridges(self, category: BridgeCategory) -> str:
        """获取参考桥段"""
        references = []
        
        # 从内置库中查找
        category_bridges = self.bridge_library.get(category.value, [])
        
        for bridge in category_bridges[:3]:  # 只取前3个
            references.append(
                f"- {bridge['name']}: {bridge['description'][:100]}..."
            )
        
        if references:
            return "\n".join(references)
        
        return "暂无参考桥段"
    
    def _find_bridge_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称查找桥段"""
        # 搜索内置库
        for category, bridges in self.bridge_library.items():
            for bridge in bridges:
                if bridge['name'] == name:
                    return {**bridge, 'category': category}
        
        # 搜索用户库
        for category, bridges in self.user_bridges.items():
            for bridge in bridges:
                if bridge['name'] == name:
                    return {**bridge, 'category': category}
        
        return None
    
    def _parse_bridge(self, content: str) -> Optional[Dict[str, Any]]:
        """解析桥段"""
        try:
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def add_to_library(
        self,
        category: BridgeCategory,
        name: str,
        description: str,
        structure: List[str],
        tags: List[str],
        usage: Optional[str] = None
    ):
        """添加桥段到用户库"""
        if category.value not in self.user_bridges:
            self.user_bridges[category.value] = []
        
        self.user_bridges[category.value].append({
            "name": name,
            "description": description,
            "structure": structure,
            "tags": tags,
            "usage": usage,
            "added_at": datetime.now().isoformat()
        })
    
    def search_bridges(
        self,
        query: str,
        category: Optional[BridgeCategory] = None
    ) -> List[Dict[str, Any]]:
        """搜索桥段"""
        results = []
        
        # 搜索内置库
        for cat, bridges in self.bridge_library.items():
            if category and cat != category.value:
                continue
            
            for bridge in bridges:
                if self._matches_query(bridge, query):
                    results.append({
                        **bridge,
                        "category": cat,
                        "source": "builtin"
                    })
        
        # 搜索用户库
        for cat, bridges in self.user_bridges.items():
            if category and cat != category.value:
                continue
            
            for bridge in bridges:
                if self._matches_query(bridge, query):
                    results.append({
                        **bridge,
                        "category": cat,
                        "source": "user"
                    })
        
        return results
    
    def _matches_query(self, bridge: Dict[str, Any], query: str) -> bool:
        """检查桥段是否匹配查询"""
        # 检查名称
        if query.lower() in bridge.get("name", "").lower():
            return True
        
        # 检查标签
        tags = bridge.get("tags", [])
        for tag in tags:
            if query.lower() in tag.lower():
                return True
        
        # 检查描述内容
        if query.lower() in bridge.get("description", "").lower():
            return True
        
        return False
    
    def get_library_stats(self) -> Dict[str, Any]:
        """获取库统计信息"""
        stats = {
            "builtin_categories": len(self.bridge_library),
            "user_categories": len(self.user_bridges),
            "total_builtin": sum(
                len(bridges) for bridges in self.bridge_library.values()
            ),
            "total_user": sum(
                len(bridges) for bridges in self.user_bridges.values()
            )
        }
        
        return stats
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """获取所有类别"""
        categories = []
        
        for category in BridgeCategory:
            builtin_count = len(
                self.bridge_library.get(category.value, [])
            )
            user_count = len(
                self.user_bridges.get(category.value, [])
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
                "bridge_library": self.bridge_library,
                "user_bridges": self.user_bridges,
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
            
            self.bridge_library.update(
                data.get("bridge_library", {})
            )
            self.user_bridges.update(
                data.get("user_bridges", {})
            )
            
            print(f"库已从 {filepath} 导入")
            
        except Exception as e:
            print(f"导入失败: {e}")


# 全局实例
_bridge_manager = None

def get_bridge_manager() -> BridgeManager:
    """获取桥段管理器实例"""
    global _bridge_manager
    if _bridge_manager is None:
        _bridge_manager = BridgeManager()
    return _bridge_manager


# 便捷函数
async def generate_bridge(
    category: str,
    characters: List[str],
    scenario: Optional[str] = None,
    tone: str = "serious",
    complexity: str = "medium"
) -> Dict[str, Any]:
    """生成桥段"""
    manager = get_bridge_manager()
    return await manager.generate_bridge(
        category=BridgeCategory(category),
        characters=characters,
        scenario=scenario,
        tone=BridgeTone(tone),
        complexity=complexity
    )

async def combine_bridges(
    bridge_names: List[str],
    characters: List[str],
    combination_style: str = "sequential"
) -> Dict[str, Any]:
    """组合桥段"""
    manager = get_bridge_manager()
    return await manager.combine_bridges(
        bridge_names=bridge_names,
        characters=characters,
        combination_style=combination_style
    )

async def generate_bridge_with_variation(
    base_bridge_name: str,
    characters: List[str],
    variation_type: str = "modern"
) -> Dict[str, Any]:
    """生成桥段变体"""
    manager = get_bridge_manager()
    return await manager.generate_bridge_with_variation(
        base_bridge_name=base_bridge_name,
        characters=characters,
        variation_type=variation_type
    )

def search_bridges(
    query: str,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """搜索桥段"""
    manager = get_bridge_manager()
    return manager.search_bridges(
        query=query,
        category=BridgeCategory(category) if category else None
    )
