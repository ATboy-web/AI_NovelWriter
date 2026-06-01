"""
情景对话推演模块
实现专门的对话生成和推演功能
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class DialogueStyle(str, Enum):
    """对话风格"""
    FORMAL = "formal"  # 正式
    CASUAL = "casual"  # 随意
    HUMOROUS = "humorous"  # 幽默
    SERIOUS = "serious"  # 严肃
    ROMANTIC = "romantic"  # 浪漫
    SUSPENSE = "suspense"  # 悬疑

class DialogueType(str, Enum):
    """对话类型"""
    CONVERSATION = "conversation"  # 普通对话
    ARGUMENT = "argument"  # 争论
    CONFESSION = "confession"  # 告白
    INTERROGATION = "interrogation"  # 审问
    NEGOTIATION = "negotiation"  # 谈判
    MONOLOGUE = "monologue"  # 独白

class DialogueManager:
    """对话管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.character_profiles: Dict[str, Dict[str, Any]] = {}
        self.dialogue_history: List[Dict[str, Any]] = []
    
    def load_character_profiles(self, profiles: Dict[str, Dict[str, Any]]):
        """加载角色档案"""
        self.character_profiles = profiles
    
    async def generate_dialogue(
        self,
        characters: List[str],
        scenario: str,
        dialogue_type: DialogueType = DialogueType.CONVERSATION,
        style: DialogueStyle = DialogueStyle.CASUAL,
        rounds: int = 5,
        context: Optional[str] = None,
        emotional_tone: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成对话"""
        try:
            import httpx
            
            # 构建角色描述
            character_descriptions = []
            for char_name in characters:
                if char_name in self.character_profiles:
                    profile = self.character_profiles[char_name]
                    desc = f"{char_name}: {self._format_character_brief(profile)}"
                    character_descriptions.append(desc)
            
            # 构建提示词
            prompt = f"""请生成以下场景的对话。

场景：{scenario}

参与角色：
{chr(10).join(character_descriptions)}

对话类型：{dialogue_type.value}
对话风格：{style.value}
对话轮数：{rounds}轮
{f'情感基调：{emotional_tone}' if emotional_tone else ''}
{f'上下文：{context}' if context else ''}

请生成符合角色性格的对话，要求：
1. 每个角色的说话风格要符合其性格特点
2. 对话要自然流畅，符合场景设定
3. 包含适当的动作和表情描写
4. 推动情节发展或揭示角色关系

请以JSON格式输出：
{{
    "dialogue": [
        {{
            "character": "角色名",
            "content": "对话内容",
            "action": "动作描写",
            "emotion": "情感状态"
        }}
    ],
    "summary": "对话摘要",
    "relationship_changes": ["关系变化描述"]
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "对话生成",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 2000,
                        "temperature": 0.7
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析对话
                    dialogue_data = self._parse_dialogue(content)
                    
                    if dialogue_data:
                        # 保存到历史
                        self.dialogue_history.append({
                            "characters": characters,
                            "scenario": scenario,
                            "dialogue_type": dialogue_type.value,
                            "style": style.value,
                            "dialogue": dialogue_data.get("dialogue", []),
                            "generated_at": datetime.now().isoformat()
                        })
                        
                        return {
                            "success": True,
                            "characters": characters,
                            "scenario": scenario,
                            "dialogue_type": dialogue_type.value,
                            "style": style.value,
                            "dialogue": dialogue_data.get("dialogue", []),
                            "summary": dialogue_data.get("summary", ""),
                            "relationship_changes": dialogue_data.get("relationship_changes", [])
                        }
            
            return {
                "success": False,
                "error": "对话生成失败",
                "characters": characters,
                "scenario": scenario
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "characters": characters,
                "scenario": scenario
            }
    
    async def continue_dialogue(
        self,
        dialogue_history: List[Dict[str, Any]],
        next_character: str,
        response_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """继续对话"""
        try:
            import httpx
            
            # 构建历史对话
            history_text = self._format_dialogue_history(dialogue_history)
            
            # 获取角色信息
            character_desc = ""
            if next_character in self.character_profiles:
                profile = self.character_profiles[next_character]
                character_desc = f"{next_character}: {self._format_character_brief(profile)}"
            
            # 构建提示词
            prompt = f"""请根据以下对话历史，生成角色"{next_character}"的下一句对话。

对话历史：
{history_text}

角色信息：
{character_desc}

{f'回应提示：{response_hint}' if response_hint else ''}

请生成符合角色性格和对话情境的回应，包含：
1. 对话内容
2. 动作描写
3. 情感状态

请以JSON格式输出：
{{
    "character": "{next_character}",
    "content": "对话内容",
    "action": "动作描写",
    "emotion": "情感状态"
}}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "对话继续",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 500,
                        "temperature": 0.7
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", "")
                    
                    # 解析回应
                    response_data = self._parse_single_dialogue(content)
                    
                    if response_data:
                        return {
                            "success": True,
                            "character": next_character,
                            "content": response_data.get("content", ""),
                            "action": response_data.get("action", ""),
                            "emotion": response_data.get("emotion", "")
                        }
            
            return {
                "success": False,
                "error": "对话继续失败",
                "character": next_character
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "character": next_character
            }
    
    async def generate_dialogue_with_conflict(
        self,
        characters: List[str],
        conflict: str,
        dialogue_type: DialogueType = DialogueType.ARGUMENT,
        style: DialogueStyle = DialogueStyle.SERIOUS,
        rounds: int = 8
    ) -> Dict[str, Any]:
        """生成冲突对话"""
        return await self.generate_dialogue(
            characters=characters,
            scenario=f"冲突场景：{conflict}",
            dialogue_type=dialogue_type,
            style=style,
            rounds=rounds,
            emotional_tone="紧张、对抗"
        )
    
    async def generate_dialogue_with_revelation(
        self,
        characters: List[str],
        revelation: str,
        dialogue_type: DialogueType = DialogueType.CONFESSION,
        style: DialogueStyle = DialogueStyle.SERIOUS,
        rounds: int = 6
    ) -> Dict[str, Any]:
        """生成揭示真相的对话"""
        return await self.generate_dialogue(
            characters=characters,
            scenario=f"揭示真相：{revelation}",
            dialogue_type=dialogue_type,
            style=style,
            rounds=rounds,
            emotional_tone="震惊、揭示"
        )
    
    async def generate_dialogue_with_negotiation(
        self,
        characters: List[str],
        topic: str,
        stakes: str,
        dialogue_type: DialogueType = DialogueType.NEGOTIATION,
        style: DialogueStyle = DialogueStyle.FORMAL,
        rounds: int = 10
    ) -> Dict[str, Any]:
        """生成谈判对话"""
        return await self.generate_dialogue(
            characters=characters,
            scenario=f"谈判主题：{topic}，赌注：{stakes}",
            dialogue_type=dialogue_type,
            style=style,
            rounds=rounds,
            emotional_tone="紧张、博弈"
        )
    
    def _format_character_brief(self, profile: Dict[str, Any]) -> str:
        """格式化角色简介"""
        parts = []
        
        if "personality" in profile:
            parts.append(f"性格：{', '.join(profile['personality'][:3])}")
        if "background" in profile:
            parts.append(f"背景：{profile['background'][:100]}")
        if "speech_style" in profile:
            parts.append(f"说话风格：{profile['speech_style']}")
        
        return "；".join(parts)
    
    def _format_dialogue_history(self, history: List[Dict[str, Any]]) -> str:
        """格式化对话历史"""
        lines = []
        
        for entry in history:
            character = entry.get("character", "未知")
            content = entry.get("content", "")
            action = entry.get("action", "")
            
            if action:
                lines.append(f"{character}（{action}）：{content}")
            else:
                lines.append(f"{character}：{content}")
        
        return "\n".join(lines)
    
    def _parse_dialogue(self, content: str) -> Optional[Dict[str, Any]]:
        """解析对话"""
        try:
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def _parse_single_dialogue(self, content: str) -> Optional[Dict[str, Any]]:
        """解析单条对话"""
        try:
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def get_dialogue_history(self) -> List[Dict[str, Any]]:
        """获取对话历史"""
        return self.dialogue_history
    
    def clear_dialogue_history(self):
        """清空对话历史"""
        self.dialogue_history = []
    
    def export_dialogue(
        self,
        dialogue_data: Dict[str, Any],
        format: str = "text"
    ) -> str:
        """导出对话"""
        if format == "text":
            return self._export_as_text(dialogue_data)
        elif format == "json":
            return json.dumps(dialogue_data, ensure_ascii=False, indent=2)
        else:
            return ""
    
    def _export_as_text(self, dialogue_data: Dict[str, Any]) -> str:
        """导出为文本格式"""
        lines = []
        
        # 添加场景描述
        scenario = dialogue_data.get("scenario", "")
        if scenario:
            lines.append(f"【场景】{scenario}")
            lines.append("")
        
        # 添加对话
        dialogue = dialogue_data.get("dialogue", [])
        for entry in dialogue:
            character = entry.get("character", "未知")
            content = entry.get("content", "")
            action = entry.get("action", "")
            emotion = entry.get("emotion", "")
            
            if action:
                lines.append(f"{character}（{action}，{emotion}）：{content}")
            else:
                lines.append(f"{character}（{emotion}）：{content}")
        
        # 添加摘要
        summary = dialogue_data.get("summary", "")
        if summary:
            lines.append("")
            lines.append(f"【摘要】{summary}")
        
        return "\n".join(lines)


# 全局实例
_dialogue_manager = None

def get_dialogue_manager() -> DialogueManager:
    """获取对话管理器实例"""
    global _dialogue_manager
    if _dialogue_manager is None:
        _dialogue_manager = DialogueManager()
    return _dialogue_manager


# 便捷函数
async def generate_dialogue(
    characters: List[str],
    scenario: str,
    dialogue_type: str = "conversation",
    style: str = "casual",
    rounds: int = 5,
    context: Optional[str] = None,
    emotional_tone: Optional[str] = None,
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """生成对话"""
    manager = get_dialogue_manager()
    
    if character_profiles:
        manager.load_character_profiles(character_profiles)
    
    return await manager.generate_dialogue(
        characters=characters,
        scenario=scenario,
        dialogue_type=DialogueType(dialogue_type),
        style=DialogueStyle(style),
        rounds=rounds,
        context=context,
        emotional_tone=emotional_tone
    )

async def continue_dialogue(
    dialogue_history: List[Dict[str, Any]],
    next_character: str,
    response_hint: Optional[str] = None,
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """继续对话"""
    manager = get_dialogue_manager()
    
    if character_profiles:
        manager.load_character_profiles(character_profiles)
    
    return await manager.continue_dialogue(
        dialogue_history=dialogue_history,
        next_character=next_character,
        response_hint=response_hint
    )
