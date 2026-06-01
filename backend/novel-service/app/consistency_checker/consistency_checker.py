"""
一致性审校模块
检测角色行为、剧情矛盾等逻辑冲突
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class ConflictType(str, Enum):
    """冲突类型"""
    CHARACTER_BEHAVIOR = "character_behavior"  # 角色行为矛盾
    PLOT_CONTRADICTION = "plot_contradiction"  # 剧情矛盾
    TIMELINE_ERROR = "timeline_error"  # 时间线错误
    SETTING_INCONSISTENCY = "setting_inconsistency"  # 设定不一致
    LOGIC_ERROR = "logic_error"  # 逻辑错误

class ConflictSeverity(str, Enum):
    """冲突严重程度"""
    LOW = "low"  # 低
    MEDIUM = "medium"  # 中
    HIGH = "high"  # 高
    CRITICAL = "critical"  # 严重

class ConsistencyChecker:
    """一致性检查器"""
    
    def __init__(self, ai_service_url: str = "http://localhost:8001"):
        self.ai_service_url = ai_service_url
        self.character_profiles: Dict[str, Dict[str, Any]] = {}
        self.plot_points: List[Dict[str, Any]] = []
        self.settings: Dict[str, Any] = {}
    
    def load_character_profiles(self, profiles: Dict[str, Dict[str, Any]]):
        """加载角色档案"""
        self.character_profiles = profiles
    
    def load_plot_points(self, plot_points: List[Dict[str, Any]]):
        """加载剧情点"""
        self.plot_points = plot_points
    
    def load_settings(self, settings: Dict[str, Any]):
        """加载设定"""
        self.settings = settings
    
    async def check_chapter(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        previous_chapters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """检查章节一致性"""
        try:
            conflicts = []
            
            # 1. 检查角色行为一致性
            character_conflicts = await self._check_character_behavior(
                chapter_content, previous_chapters
            )
            conflicts.extend(character_conflicts)
            
            # 2. 检查剧情矛盾
            plot_conflicts = await self._check_plot_contradiction(
                chapter_content, previous_chapters
            )
            conflicts.extend(plot_conflicts)
            
            # 3. 检查时间线错误
            timeline_conflicts = await self._check_timeline_error(
                chapter_content, previous_chapters
            )
            conflicts.extend(timeline_conflicts)
            
            # 4. 检查设定不一致
            setting_conflicts = await self._check_setting_inconsistency(
                chapter_content
            )
            conflicts.extend(setting_conflicts)
            
            # 5. 检查逻辑错误
            logic_conflicts = await self._check_logic_error(
                chapter_content, previous_chapters
            )
            conflicts.extend(logic_conflicts)
            
            # 生成审校报告
            report = self._generate_report(
                chapter_number, chapter_title, conflicts
            )
            
            return report
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "chapter_number": chapter_number,
                "chapter_title": chapter_title
            }
    
    async def _check_character_behavior(
        self,
        chapter_content: str,
        previous_chapters: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """检查角色行为一致性"""
        conflicts = []
        
        try:
            import httpx
            
            # 提取章节中提到的角色
            mentioned_characters = self._extract_characters(chapter_content)
            
            for character in mentioned_characters:
                if character in self.character_profiles:
                    profile = self.character_profiles[character]
                    
                    # 构建检查提示词
                    prompt = f"""请检查以下章节内容中角色"{character}"的行为是否与其设定一致。

角色设定：
{self._format_character_profile(profile)}

章节内容：
{chapter_content[:1000]}

请分析：
1. 角色的行为是否符合其性格特点？
2. 角色的决策是否符合其背景故事？
3. 角色的能力表现是否合理？

如果发现不一致，请以JSON格式输出：
{{
    "has_conflict": true,
    "conflict_type": "character_behavior",
    "severity": "low/medium/high/critical",
    "description": "冲突描述",
    "suggestion": "修改建议"
}}

如果没有发现不一致，输出：
{{
    "has_conflict": false
}}"""
                    
                    # 调用AI服务
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.ai_service_url}/api/v1/generate/chapter",
                            json={
                                "novel_type": "urban",
                                "chapter_title": "一致性检查",
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
                            
                            # 解析结果
                            conflict_data = self._parse_conflict_result(content)
                            if conflict_data and conflict_data.get("has_conflict"):
                                conflicts.append({
                                    "type": ConflictType.CHARACTER_BEHAVIOR.value,
                                    "severity": conflict_data.get("severity", "medium"),
                                    "character": character,
                                    "description": conflict_data.get("description", ""),
                                    "suggestion": conflict_data.get("suggestion", ""),
                                    "chapter_content_preview": chapter_content[:200]
                                })
            
            return conflicts
            
        except Exception as e:
            print(f"检查角色行为失败: {e}")
            return []
    
    async def _check_plot_contradiction(
        self,
        chapter_content: str,
        previous_chapters: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """检查剧情矛盾"""
        conflicts = []
        
        try:
            import httpx
            
            if not previous_chapters:
                return []
            
            # 构建前文摘要
            previous_summary = self._build_previous_summary(previous_chapters)
            
            # 构建检查提示词
            prompt = f"""请检查以下章节内容是否与前文存在剧情矛盾。

前文摘要：
{previous_summary}

当前章节：
{chapter_content[:1000]}

请分析：
1. 当前章节的事件是否与前文矛盾？
2. 角色关系是否发生变化？
3. 重要物品或事件的描述是否一致？

如果发现矛盾，请以JSON格式输出：
{{
    "has_conflict": true,
    "conflict_type": "plot_contradiction",
    "severity": "low/medium/high/critical",
    "description": "矛盾描述",
    "suggestion": "修改建议"
}}

如果没有发现矛盾，输出：
{{
    "has_conflict": false
}}"""
            
            # 调用AI服务
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "一致性检查",
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
                    
                    # 解析结果
                    conflict_data = self._parse_conflict_result(content)
                    if conflict_data and conflict_data.get("has_conflict"):
                        conflicts.append({
                            "type": ConflictType.PLOT_CONTRADICTION.value,
                            "severity": conflict_data.get("severity", "medium"),
                            "description": conflict_data.get("description", ""),
                            "suggestion": conflict_data.get("suggestion", ""),
                            "chapter_content_preview": chapter_content[:200]
                        })
            
            return conflicts
            
        except Exception as e:
            print(f"检查剧情矛盾失败: {e}")
            return []
    
    async def _check_timeline_error(
        self,
        chapter_content: str,
        previous_chapters: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """检查时间线错误"""
        conflicts = []
        
        try:
            import httpx
            
            # 提取时间信息
            time_references = self._extract_time_references(chapter_content)
            
            if not time_references:
                return []
            
            # 构建检查提示词
            prompt = f"""请检查以下章节内容中的时间线是否合理。

时间引用：
{json.dumps(time_references, ensure_ascii=False, indent=2)}

章节内容：
{chapter_content[:1000]}

请分析：
1. 时间顺序是否合理？
2. 时间跨度是否符合逻辑？
3. 是否存在时间跳跃或时间倒流？

如果发现时间线错误，请以JSON格式输出：
{{
    "has_conflict": true,
    "conflict_type": "timeline_error",
    "severity": "low/medium/high/critical",
    "description": "错误描述",
    "suggestion": "修改建议"
}}

如果没有发现错误，输出：
{{
    "has_conflict": false
}}"""
            
            # 调用AI服务
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "一致性检查",
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
                    
                    # 解析结果
                    conflict_data = self._parse_conflict_result(content)
                    if conflict_data and conflict_data.get("has_conflict"):
                        conflicts.append({
                            "type": ConflictType.TIMELINE_ERROR.value,
                            "severity": conflict_data.get("severity", "medium"),
                            "description": conflict_data.get("description", ""),
                            "suggestion": conflict_data.get("suggestion", ""),
                            "time_references": time_references
                        })
            
            return conflicts
            
        except Exception as e:
            print(f"检查时间线失败: {e}")
            return []
    
    async def _check_setting_inconsistency(
        self,
        chapter_content: str
    ) -> List[Dict[str, Any]]:
        """检查设定不一致"""
        conflicts = []
        
        try:
            import httpx
            
            if not self.settings:
                return []
            
            # 构建检查提示词
            prompt = f"""请检查以下章节内容是否与设定一致。

世界观设定：
{json.dumps(self.settings, ensure_ascii=False, indent=2)[:1000]}

章节内容：
{chapter_content[:1000]}

请分析：
1. 地点描述是否符合设定？
2. 物品或能力描述是否符合设定？
3. 社会结构或规则是否符合设定？

如果发现不一致，请以JSON格式输出：
{{
    "has_conflict": true,
    "conflict_type": "setting_inconsistency",
    "severity": "low/medium/high/critical",
    "description": "不一致描述",
    "suggestion": "修改建议"
}}

如果没有发现不一致，输出：
{{
    "has_conflict": false
}}"""
            
            # 调用AI服务
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "一致性检查",
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
                    
                    # 解析结果
                    conflict_data = self._parse_conflict_result(content)
                    if conflict_data and conflict_data.get("has_conflict"):
                        conflicts.append({
                            "type": ConflictType.SETTING_INCONSISTENCY.value,
                            "severity": conflict_data.get("severity", "medium"),
                            "description": conflict_data.get("description", ""),
                            "suggestion": conflict_data.get("suggestion", "")
                        })
            
            return conflicts
            
        except Exception as e:
            print(f"检查设定不一致失败: {e}")
            return []
    
    async def _check_logic_error(
        self,
        chapter_content: str,
        previous_chapters: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """检查逻辑错误"""
        conflicts = []
        
        try:
            import httpx
            
            # 构建检查提示词
            prompt = f"""请检查以下章节内容是否存在逻辑错误。

章节内容：
{chapter_content[:1000]}

请分析：
1. 因果关系是否合理？
2. 事件发展是否符合逻辑？
3. 是否存在明显的逻辑漏洞？

如果发现逻辑错误，请以JSON格式输出：
{{
    "has_conflict": true,
    "conflict_type": "logic_error",
    "severity": "low/medium/high/critical",
    "description": "错误描述",
    "suggestion": "修改建议"
}}

如果没有发现错误，输出：
{{
    "has_conflict": false
}}"""
            
            # 调用AI服务
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/generate/chapter",
                    json={
                        "novel_type": "urban",
                        "chapter_title": "一致性检查",
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
                    
                    # 解析结果
                    conflict_data = self._parse_conflict_result(content)
                    if conflict_data and conflict_data.get("has_conflict"):
                        conflicts.append({
                            "type": ConflictType.LOGIC_ERROR.value,
                            "severity": conflict_data.get("severity", "medium"),
                            "description": conflict_data.get("description", ""),
                            "suggestion": conflict_data.get("suggestion", "")
                        })
            
            return conflicts
            
        except Exception as e:
            print(f"检查逻辑错误失败: {e}")
            return []
    
    def _extract_characters(self, text: str) -> List[str]:
        """提取文本中提到的角色"""
        characters = []
        
        # 简单的角色提取（基于角色档案中的名字）
        for character_name in self.character_profiles.keys():
            if character_name in text:
                characters.append(character_name)
        
        return characters
    
    def _extract_time_references(self, text: str) -> List[Dict[str, str]]:
        """提取时间引用"""
        time_references = []
        
        # 简单的时间模式匹配
        patterns = [
            (r'(\d+)天前', 'days_ago'),
            (r'(\d+)小时前', 'hours_ago'),
            (r'昨天', 'yesterday'),
            (r'今天', 'today'),
            (r'明天', 'tomorrow'),
            (r'(\d+)年', 'year'),
            (r'清晨', 'morning'),
            (r'中午', 'noon'),
            (r'傍晚', 'evening'),
            (r'深夜', 'night'),
        ]
        
        for pattern, time_type in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                time_references.append({
                    "type": time_type,
                    "value": match if match else time_type,
                    "context": text[max(0, text.find(match)-20):text.find(match)+20] if match else ""
                })
        
        return time_references
    
    def _build_previous_summary(self, previous_chapters: List[Dict[str, Any]]) -> str:
        """构建前文摘要"""
        summary_parts = []
        
        for chapter in previous_chapters[-3:]:  # 只取最近3章
            chapter_num = chapter.get("chapter_number", 0)
            chapter_title = chapter.get("chapter_title", "")
            chapter_content = chapter.get("content", "")
            
            summary_parts.append(f"第{chapter_num}章 {chapter_title}: {chapter_content[:200]}...")
        
        return "\n\n".join(summary_parts)
    
    def _format_character_profile(self, profile: Dict[str, Any]) -> str:
        """格式化角色档案"""
        parts = []
        
        if "name" in profile:
            parts.append(f"姓名: {profile['name']}")
        if "personality" in profile:
            parts.append(f"性格: {', '.join(profile['personality'])}")
        if "background" in profile:
            parts.append(f"背景: {profile['background']}")
        if "skills" in profile:
            parts.append(f"技能: {', '.join(profile['skills'])}")
        
        return "\n".join(parts)
    
    def _parse_conflict_result(self, content: str) -> Optional[Dict[str, Any]]:
        """解析冲突检查结果"""
        try:
            import json
            
            # 尝试提取JSON
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            return None
            
        except Exception:
            return None
    
    def _generate_report(
        self,
        chapter_number: int,
        chapter_title: str,
        conflicts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成审校报告"""
        # 统计冲突
        severity_counts = {
            ConflictSeverity.LOW.value: 0,
            ConflictSeverity.MEDIUM.value: 0,
            ConflictSeverity.HIGH.value: 0,
            ConflictSeverity.CRITICAL.value: 0
        }
        
        for conflict in conflicts:
            severity = conflict.get("severity", ConflictSeverity.MEDIUM.value)
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        # 计算总体评分
        total_score = 100
        total_score -= severity_counts[ConflictSeverity.LOW.value] * 5
        total_score -= severity_counts[ConflictSeverity.MEDIUM.value] * 10
        total_score -= severity_counts[ConflictSeverity.HIGH.value] * 20
        total_score -= severity_counts[ConflictSeverity.CRITICAL.value] * 30
        total_score = max(0, total_score)
        
        return {
            "success": True,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "total_conflicts": len(conflicts),
            "severity_counts": severity_counts,
            "score": total_score,
            "conflicts": conflicts,
            "checked_at": datetime.now().isoformat()
        }


# 全局实例
_consistency_checker = None

def get_consistency_checker() -> ConsistencyChecker:
    """获取一致性检查器实例"""
    global _consistency_checker
    if _consistency_checker is None:
        _consistency_checker = ConsistencyChecker()
    return _consistency_checker


# 便捷函数
async def check_chapter_consistency(
    chapter_number: int,
    chapter_title: str,
    chapter_content: str,
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    previous_chapters: Optional[List[Dict[str, Any]]] = None,
    settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """检查章节一致性"""
    checker = get_consistency_checker()
    
    if character_profiles:
        checker.load_character_profiles(character_profiles)
    if settings:
        checker.load_settings(settings)
    
    return await checker.check_chapter(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        previous_chapters=previous_chapters
    )
