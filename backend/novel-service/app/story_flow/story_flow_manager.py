"""
故事流推演模块
基于背景/人物/事件推演故事发展
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class FlowType(str, Enum):
    """故事流类型"""
    FORWARD = "forward"  # 正向推演
    BACKWARD = "backward"  # 反向推演
    BRANCHING = "branching"  # 分支推演
    INTERPOLATION = "interpolation"  # 插值推演

class EventType(str, Enum):
    """事件类型"""
    MAIN_PLOT = "main_plot"  # 主线剧情
    SUB_PLOT = "sub_plot"  # 支线剧情
    CHARACTER_DEVELOPMENT = "character_development"  # 角色发展
    CONFLICT = "conflict"  # 冲突事件
    RESOLUTION = "resolution"  # 解决事件
    TWIST = "twist"  # 转折事件

class StoryFlowManager:
    """故事流管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.story_elements: Dict[str, Any] = {
            "setting": {},
            "characters": {},
            "plot_points": [],
            "conflicts": [],
            "themes": []
        }
        self.flow_history: List[Dict[str, Any]] = []
    
    def initialize_story(
        self,
        setting: Dict[str, Any],
        characters: Dict[str, Dict[str, Any]],
        initial_plot: Optional[Dict[str, Any]] = None,
        themes: Optional[List[str]] = None
    ):
        """初始化故事元素"""
        self.story_elements = {
            "setting": setting,
            "characters": characters,
            "plot_points": [initial_plot] if initial_plot else [],
            "conflicts": [],
            "themes": themes or []
        }
    
    async def generate_story_flow(
        self,
        flow_type: FlowType,
        start_point: str,
        end_point: Optional[str] = None,
        num_events: int = 5,
        complexity: str = "medium"
    ) -> Dict[str, Any]:
        """生成故事流"""
        try:
            import httpx
            
            # 构建故事元素描述
            setting_desc = self._format_setting()
            characters_desc = self._format_characters()
            themes_desc = ", ".join(self.story_elements.get("themes", []))
            
            # 构建提示词
            prompt = self._build_flow_prompt(
                flow_type=flow_type,
                start_point=start_point,
                end_point=end_point,
                num_events=num_events,
                complexity=complexity,
                setting_desc=setting_desc,
                characters_desc=characters_desc,
                themes_desc=themes_desc
            )
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "故事流推演",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 3000,
                        "temperature": 0.8
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析故事流
                    flow_data = self._parse_story_flow(content)
                    
                    if flow_data:
                        # 保存到历史
                        self.flow_history.append({
                            "flow_type": flow_type.value,
                            "start_point": start_point,
                            "end_point": end_point,
                            "events": flow_data.get("events", []),
                            "generated_at": datetime.now().isoformat()
                        })
                        
                        return {
                            "success": True,
                            "flow_type": flow_type.value,
                            "start_point": start_point,
                            "end_point": end_point,
                            "events": flow_data.get("events", []),
                            "summary": flow_data.get("summary", ""),
                            "branching_points": flow_data.get("branching_points", [])
                        }
            
            return {
                "success": False,
                "error": "故事流生成失败",
                "flow_type": flow_type.value,
                "start_point": start_point
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "flow_type": flow_type.value,
                "start_point": start_point
            }
    
    async def generate_from_beginning_to_end(
        self,
        beginning: str,
        ending: str,
        num_events: int = 8
    ) -> Dict[str, Any]:
        """从开端推演到结局"""
        return await self.generate_story_flow(
            flow_type=FlowType.INTERPOLATION,
            start_point=beginning,
            end_point=ending,
            num_events=num_events,
            complexity="high"
        )
    
    async def generate_branching_scenarios(
        self,
        current_situation: str,
        num_branches: int = 3,
        events_per_branch: int = 4
    ) -> Dict[str, Any]:
        """生成分支场景"""
        try:
            import httpx
            
            # 构建故事元素描述
            setting_desc = self._format_setting()
            characters_desc = self._format_characters()
            
            prompt = f"""请根据以下当前情境，生成{num_branches}个不同的故事分支。

当前情境：{current_situation}

世界观设定：
{setting_desc}

角色信息：
{characters_desc}

请为每个分支生成{events_per_branch}个事件，要求：
1. 每个分支要有不同的发展方向
2. 事件要符合逻辑和角色性格
3. 分支之间要有明显的差异
4. 包含冲突和转折

请以JSON格式输出：
{{
    "branches": [
        {{
            "branch_id": 1,
            "direction": "分支方向描述",
            "events": [
                {{
                    "event_number": 1,
                    "event_type": "事件类型",
                    "description": "事件描述",
                    "characters_involved": ["角色1", "角色2"],
                    "impact": "事件影响"
                }}
            ],
            "potential_outcome": "潜在结局"
        }}
    ],
    "decision_point": "决策点描述",
    "factors": ["影响因素1", "影响因素2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "分支推演",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 3000,
                        "temperature": 0.9
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析分支
                    branch_data = self._parse_branching_scenarios(content)
                    
                    if branch_data:
                        return {
                            "success": True,
                            "current_situation": current_situation,
                            "branches": branch_data.get("branches", []),
                            "decision_point": branch_data.get("decision_point", ""),
                            "factors": branch_data.get("factors", [])
                        }
            
            return {
                "success": False,
                "error": "分支场景生成失败",
                "current_situation": current_situation
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "current_situation": current_situation
            }
    
    async def generate_conflict_escalation(
        self,
        initial_conflict: str,
        characters_involved: List[str],
        escalation_steps: int = 4
    ) -> Dict[str, Any]:
        """生成冲突升级"""
        try:
            import httpx
            
            # 获取角色信息
            characters_info = []
            for char_name in characters_involved:
                if char_name in self.story_elements.get("characters", {}):
                    profile = self.story_elements["characters"][char_name]
                    characters_info.append(f"{char_name}: {self._format_character_brief(profile)}")
            
            prompt = f"""请根据以下初始冲突，生成冲突升级的过程。

初始冲突：{initial_conflict}

涉及角色：
{chr(10).join(characters_info)}

请生成{escalation_steps}个冲突升级步骤，要求：
1. 冲突逐步升级，越来越激烈
2. 每个步骤要有明确的触发点
3. 角色的反应要符合其性格
4. 包含转折和意外

请以JSON格式输出：
{{
    "initial_conflict": "初始冲突描述",
    "escalation_steps": [
        {{
            "step": 1,
            "trigger": "触发点",
            "escalation": "升级描述",
            "character_reactions": {{
                "角色名": "反应描述"
            }},
            "stakes": "风险/赌注"
        }}
    ],
    "climax": "高潮描述",
    "potential_resolutions": ["可能的解决方式1", "可能的解决方式2"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "冲突升级",
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
                    
                    # 解析冲突升级
                    escalation_data = self._parse_conflict_escalation(content)
                    
                    if escalation_data:
                        return {
                            "success": True,
                            "initial_conflict": initial_conflict,
                            "characters_involved": characters_involved,
                            "escalation_steps": escalation_data.get("escalation_steps", []),
                            "climax": escalation_data.get("climax", ""),
                            "potential_resolutions": escalation_data.get("potential_resolutions", [])
                        }
            
            return {
                "success": False,
                "error": "冲突升级生成失败",
                "initial_conflict": initial_conflict
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "initial_conflict": initial_conflict
            }
    
    def _build_flow_prompt(
        self,
        flow_type: FlowType,
        start_point: str,
        end_point: Optional[str],
        num_events: int,
        complexity: str,
        setting_desc: str,
        characters_desc: str,
        themes_desc: str
    ) -> str:
        """构建推演提示词"""
        base_prompt = f"""请根据以下信息生成故事流。

世界观设定：
{setting_desc}

角色信息：
{characters_desc}

主题：{themes_desc}

"""
        
        if flow_type == FlowType.FORWARD:
            base_prompt += f"""正向推演：
起始点：{start_point}
事件数量：{num_events}
复杂度：{complexity}

请从起始点开始，推演故事的发展，生成{num_events}个关键事件。"""
        
        elif flow_type == FlowType.BACKWARD:
            base_prompt += f"""反向推演：
结局：{start_point}
事件数量：{num_events}
复杂度：{complexity}

请从结局开始，反向推演导致这个结局的原因和过程，生成{num_events}个关键事件。"""
        
        elif flow_type == FlowType.INTERPOLATION:
            base_prompt += f"""插值推演：
开端：{start_point}
结局：{end_point}
事件数量：{num_events}
复杂度：{complexity}

请从开端推演到结局，生成{num_events}个关键事件，确保逻辑连贯。"""
        
        elif flow_type == FlowType.BRANCHING:
            base_prompt += f"""分支推演：
起始点：{start_point}
分支数量：{num_events}
复杂度：{complexity}

请从起始点开始，生成{num_events}个不同的故事分支。"""
        
        base_prompt += """

请以JSON格式输出：
{
    "events": [
        {
            "event_number": 1,
            "event_type": "事件类型",
            "description": "事件描述",
            "characters_involved": ["角色1", "角色2"],
            "impact": "事件影响",
            "consequences": ["后果1", "后果2"]
        }
    ],
    "summary": "故事流摘要",
    "branching_points": ["分支点1", "分支点2"]
}"""
        
        return base_prompt
    
    def _format_setting(self) -> str:
        """格式化世界观设定"""
        setting = self.story_elements.get("setting", {})
        if not setting:
            return "暂无设定"
        
        parts = []
        for key, value in setting.items():
            if isinstance(value, str):
                parts.append(f"{key}: {value}")
            elif isinstance(value, list):
                parts.append(f"{key}: {', '.join(str(v) for v in value)}")
        
        return "\n".join(parts)
    
    def _format_characters(self) -> str:
        """格式化角色信息"""
        characters = self.story_elements.get("characters", {})
        if not characters:
            return "暂无角色"
        
        parts = []
        for char_name, profile in characters.items():
            parts.append(f"{char_name}: {self._format_character_brief(profile)}")
        
        return "\n".join(parts)
    
    def _format_character_brief(self, profile: Dict[str, Any]) -> str:
        """格式化角色简介"""
        parts = []
        
        if "personality" in profile:
            parts.append(f"性格：{', '.join(profile['personality'][:3])}")
        if "background" in profile:
            parts.append(f"背景：{profile['background'][:100]}")
        
        return "；".join(parts)
    
    def _parse_story_flow(self, content: str) -> Optional[Dict[str, Any]]:
        """解析故事流"""
        try:
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def _parse_branching_scenarios(self, content: str) -> Optional[Dict[str, Any]]:
        """解析分支场景"""
        try:
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def _parse_conflict_escalation(self, content: str) -> Optional[Dict[str, Any]]:
        """解析冲突升级"""
        try:
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def get_flow_history(self) -> List[Dict[str, Any]]:
        """获取推演历史"""
        return self.flow_history
    
    def clear_flow_history(self):
        """清空推演历史"""
        self.flow_history = []
    
    def add_plot_point(self, plot_point: Dict[str, Any]):
        """添加剧情点"""
        self.story_elements["plot_points"].append(plot_point)
    
    def add_conflict(self, conflict: Dict[str, Any]):
        """添加冲突"""
        self.story_elements["conflicts"].append(conflict)
    
    def get_story_elements(self) -> Dict[str, Any]:
        """获取故事元素"""
        return self.story_elements


# 全局实例
_story_flow_manager = None

def get_story_flow_manager() -> StoryFlowManager:
    """获取故事流管理器实例"""
    global _story_flow_manager
    if _story_flow_manager is None:
        _story_flow_manager = StoryFlowManager()
    return _story_flow_manager


# 便捷函数
async def generate_story_flow(
    flow_type: str,
    start_point: str,
    end_point: Optional[str] = None,
    num_events: int = 5,
    complexity: str = "medium",
    setting: Optional[Dict[str, Any]] = None,
    characters: Optional[Dict[str, Dict[str, Any]]] = None,
    themes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """生成故事流"""
    manager = get_story_flow_manager()
    
    if setting or characters or themes:
        manager.initialize_story(
            setting=setting or {},
            characters=characters or {},
            themes=themes
        )
    
    return await manager.generate_story_flow(
        flow_type=FlowType(flow_type),
        start_point=start_point,
        end_point=end_point,
        num_events=num_events,
        complexity=complexity
    )

async def generate_branching_scenarios(
    current_situation: str,
    num_branches: int = 3,
    events_per_branch: int = 4,
    setting: Optional[Dict[str, Any]] = None,
    characters: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """生成分支场景"""
    manager = get_story_flow_manager()
    
    if setting or characters:
        manager.initialize_story(
            setting=setting or {},
            characters=characters or {}
        )
    
    return await manager.generate_branching_scenarios(
        current_situation=current_situation,
        num_branches=num_branches,
        events_per_branch=events_per_branch
    )

async def generate_conflict_escalation(
    initial_conflict: str,
    characters_involved: List[str],
    escalation_steps: int = 4,
    characters: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """生成冲突升级"""
    manager = get_story_flow_manager()
    
    if characters:
        manager.initialize_story(
            setting={},
            characters=characters
        )
    
    return await manager.generate_conflict_escalation(
        initial_conflict=initial_conflict,
        characters_involved=characters_involved,
        escalation_steps=escalation_steps
    )
