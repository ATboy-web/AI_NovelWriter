"""
定稿管理器
每章完成后自动更新全局摘要、角色状态、向量检索库
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class ChapterStatus(str, Enum):
    """章节状态"""
    DRAFT = "draft"  # 草稿
    REVIEWING = "reviewing"  # 审校中
    REVISED = "revised"  # 已修改
    FINALIZED = "finalized"  # 已定稿

class FinalizationManager:
    """定稿管理器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.novel_data: Dict[str, Any] = {}
        self.character_states: Dict[str, Dict[str, Any]] = {}
        self.global_summary: str = ""
        self.chapter_summaries: Dict[int, str] = {}
    
    def initialize_novel(
        self,
        novel_id: str,
        title: str,
        synopsis: str,
        novel_type: str,
        character_profiles: Dict[str, Dict[str, Any]],
        settings: Dict[str, Any]
    ):
        """初始化小说数据"""
        self.novel_data = {
            "novel_id": novel_id,
            "title": title,
            "synopsis": synopsis,
            "novel_type": novel_type,
            "settings": settings,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "total_chapters": 0,
            "total_words": 0,
            "status": "in_progress"
        }
        
        # 初始化角色状态
        for char_name, char_profile in character_profiles.items():
            self.character_states[char_name] = {
                **char_profile,
                "current_status": "active",
                "last_appearance": 0,
                "development_arc": [],
                "relationships": char_profile.get("relationships", {})
            }
        
        print(f"小说 '{title}' 初始化完成")
    
    async def finalize_chapter(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        chapter_outline: str
    ) -> Dict[str, Any]:
        """定稿章节"""
        try:
            # 1. 生成章节摘要
            chapter_summary = await self._generate_chapter_summary(
                chapter_number, chapter_title, chapter_content
            )
            
            # 2. 更新角色状态
            character_updates = await self._update_character_states(
                chapter_number, chapter_content
            )
            
            # 3. 更新全局摘要
            await self._update_global_summary(
                chapter_number, chapter_title, chapter_summary
            )
            
            # 4. 更新向量数据库
            vector_update_result = await self._update_vector_store(
                chapter_number, chapter_title, chapter_content
            )
            
            # 5. 更新小说统计
            self._update_novel_statistics(chapter_number, chapter_content)
            
            # 保存章节摘要
            self.chapter_summaries[chapter_number] = chapter_summary
            
            return {
                "success": True,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "status": ChapterStatus.FINALIZED.value,
                "chapter_summary": chapter_summary,
                "character_updates": character_updates,
                "global_summary_updated": True,
                "vector_store_updated": vector_update_result,
                "finalized_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "chapter_number": chapter_number,
                "chapter_title": chapter_title
            }
    
    async def _generate_chapter_summary(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str
    ) -> str:
        """生成章节摘要"""
        try:
            import httpx
            
            prompt = f"""请为以下章节生成简洁的摘要（100-200字）。

章节标题：{chapter_title}
章节内容：
{chapter_content[:1500]}

请提取：
1. 主要事件
2. 关键转折点
3. 角色发展
4. 重要信息

请直接输出摘要内容，不要添加额外说明。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "摘要生成",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 300,
                        "temperature": 0.3
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("content", f"第{chapter_number}章：{chapter_title}")
            
            return f"第{chapter_number}章：{chapter_title}"
            
        except Exception as e:
            print(f"生成章节摘要失败: {e}")
            return f"第{chapter_number}章：{chapter_title}"
    
    async def _update_character_states(
        self,
        chapter_number: int,
        chapter_content: str
    ) -> Dict[str, Any]:
        """更新角色状态"""
        updates = {}
        
        try:
            import httpx
            
            # 提取章节中提到的角色
            mentioned_characters = []
            for char_name in self.character_states.keys():
                if char_name in chapter_content:
                    mentioned_characters.append(char_name)
            
            for character in mentioned_characters:
                # 构建更新提示词
                prompt = f"""根据以下章节内容，更新角色"{character}"的状态。

当前角色状态：
{json.dumps(self.character_states[character], ensure_ascii=False, indent=2)[:500]}

章节内容：
{chapter_content[:1000]}

请分析：
1. 角色在本章中的主要行为
2. 角色的情感变化
3. 角色关系的变化
4. 角色的成长或发展

请以JSON格式输出更新信息：
{{
    "status_change": "状态变化描述",
    "emotion_change": "情感变化描述",
    "relationship_changes": ["关系变化1", "关系变化2"],
    "development": "成长发展描述"
}}"""
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.ai_service_url}/api/v1/generate/chapter",
                        json={
                            "novel_type": "urban",
                            "chapter_title": "角色更新",
                            "chapter_outline": prompt,
                            "model_type": "local",
                            "max_tokens": 500,
                            "temperature": 0.3
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result.get("content", "")
                        
                        # 解析更新信息
                        update_info = self._parse_character_update(content)
                        
                        if update_info:
                            # 更新角色状态
                            self.character_states[character]["last_appearance"] = chapter_number
                            self.character_states[character]["development_arc"].append({
                                "chapter": chapter_number,
                                "update": update_info
                            })
                            
                            updates[character] = update_info
            
            return updates
            
        except Exception as e:
            print(f"更新角色状态失败: {e}")
            return updates
    
    def _parse_character_update(self, content: str) -> Optional[Dict[str, Any]]:
        """解析角色更新信息"""
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
    
    async def _update_global_summary(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_summary: str
    ):
        """更新全局摘要"""
        try:
            import httpx
            
            # 构建更新提示词
            prompt = f"""请根据以下信息更新小说的全局摘要。

当前全局摘要：
{self.global_summary[:500] if self.global_summary else "暂无"}

新章节信息：
第{chapter_number}章 {chapter_title}
摘要：{chapter_summary}

请生成更新后的全局摘要（200-300字），包括：
1. 故事主线进展
2. 主要角色状态
3. 当前剧情阶段
4. 关键悬念或伏笔

请直接输出更新后的全局摘要。"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "全局摘要更新",
                        "chapter_outline": prompt,
                        "model_type": "local",
                        "max_tokens": 500,
                        "temperature": 0.3
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    self.global_summary = result.get("content", self.global_summary)
            
        except Exception as e:
            print(f"更新全局摘要失败: {e}")
    
    async def _update_vector_store(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str
    ) -> bool:
        """更新向量数据库"""
        try:
            # 导入向量数据库管理器
            from ..vector_store.vector_manager import add_chapter_to_vector_store
            
            # 添加章节到向量数据库
            result = add_chapter_to_vector_store(
                novel_id=self.novel_data.get("novel_id", "default"),
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                metadata={
                    "novel_type": self.novel_data.get("novel_type", ""),
                    "title": self.novel_data.get("title", "")
                }
            )
            
            return result
            
        except Exception as e:
            print(f"更新向量数据库失败: {e}")
            return False
    
    def _update_novel_statistics(
        self,
        chapter_number: int,
        chapter_content: str
    ):
        """更新小说统计"""
        # 更新总章节数
        self.novel_data["total_chapters"] = max(
            self.novel_data.get("total_chapters", 0),
            chapter_number
        )
        
        # 更新总字数
        self.novel_data["total_words"] = self.novel_data.get("total_words", 0) + len(chapter_content)
        
        # 更新时间
        self.novel_data["updated_at"] = datetime.now().isoformat()
    
    def get_chapter_summary(self, chapter_number: int) -> Optional[str]:
        """获取章节摘要"""
        return self.chapter_summaries.get(chapter_number)
    
    def get_global_summary(self) -> str:
        """获取全局摘要"""
        return self.global_summary
    
    def get_character_state(self, character_name: str) -> Optional[Dict[str, Any]]:
        """获取角色状态"""
        return self.character_states.get(character_name)
    
    def get_all_character_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有角色状态"""
        return self.character_states
    
    def get_novel_data(self) -> Dict[str, Any]:
        """获取小说数据"""
        return self.novel_data
    
    def get_chapter_summaries(self) -> Dict[int, str]:
        """获取所有章节摘要"""
        return self.chapter_summaries
    
    def save_state(self, filepath: str):
        """保存状态到文件"""
        try:
            state = {
                "novel_data": self.novel_data,
                "character_states": self.character_states,
                "global_summary": self.global_summary,
                "chapter_summaries": {str(k): v for k, v in self.chapter_summaries.items()},
                "saved_at": datetime.now().isoformat()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            print(f"状态已保存到: {filepath}")
            
        except Exception as e:
            print(f"保存状态失败: {e}")
    
    def load_state(self, filepath: str):
        """从文件加载状态"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            self.novel_data = state.get("novel_data", {})
            self.character_states = state.get("character_states", {})
            self.global_summary = state.get("global_summary", "")
            self.chapter_summaries = {int(k): v for k, v in state.get("chapter_summaries", {}).items()}
            
            print(f"状态已从 {filepath} 加载")
            
        except Exception as e:
            print(f"加载状态失败: {e}")


# 全局实例
_finalization_manager = None

def get_finalization_manager() -> FinalizationManager:
    """获取定稿管理器实例"""
    global _finalization_manager
    if _finalization_manager is None:
        _finalization_manager = FinalizationManager()
    return _finalization_manager


# 便捷函数
async def finalize_chapter(
    chapter_number: int,
    chapter_title: str,
    chapter_content: str,
    chapter_outline: str,
    novel_id: str = "default",
    title: str = "",
    synopsis: str = "",
    novel_type: str = "",
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """定稿章节"""
    manager = get_finalization_manager()
    
    # 如果小说未初始化，则初始化
    if not manager.novel_data:
        manager.initialize_novel(
            novel_id=novel_id,
            title=title,
            synopsis=synopsis,
            novel_type=novel_type,
            character_profiles=character_profiles or {},
            settings=settings or {}
        )
    
    return await manager.finalize_chapter(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        chapter_outline=chapter_outline
    )
