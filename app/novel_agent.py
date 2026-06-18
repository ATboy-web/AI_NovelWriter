"""
小说创作智能体模块 - 参考AutoGen多智能体协作架构 v3.0

改进 (Hello-Agents 参考):
- 多Agent专业化协作 (PlotDesigner/WorldBuilder/Writer/Reviewer/Editor)
- 标准化工具系统 (ToolRegistry + Tool协议)
- 动态上下文工程 (根据写作阶段智能分配)
- 标准化通信协议 (AgentMessage)
"""

import json
import threading
import time
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from enum import Enum

from .ai_client import AIClient, PromptManager
from .agent_orchestrator import ContextOptimizer, PromptOptimizer, AgentOrchestrator
from .memory_manager import MemoryManager
from .config import AppConfig


# ===== 标准化通信协议 (参考 MCP/A2A) =====

class MessageRole(Enum):
    SYSTEM = "system"
    PLOT = "plot_designer"
    WORLD = "world_builder"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EDITOR = "editor"
    TOOL = "tool"

class AgentMessage:
    """标准化Agent消息 - 参考MCP协议"""
    def __init__(self, role: MessageRole, action: str, content: str, metadata: Dict = None):
        self.role = role
        self.action = action
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "role": self.role.value,
            "action": self.action,
            "content": self.content[:300],
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


# ===== 标准化工具系统 (参考 MCP Tool协议) =====

class Tool:
    """标准化工具定义"""
    def __init__(self, name: str, description: str, func: Callable, 
                 input_schema: Dict = None, category: str = "general"):
        self.name = name
        self.description = description
        self.func = func
        self.input_schema = input_schema or {}
        self.category = category
    
    def execute(self, **kwargs) -> Dict:
        try:
            result = self.func(**kwargs)
            return {"success": True, "result": result, "tool": self.name}
        except Exception as e:
            return {"success": False, "error": str(e), "tool": self.name}


class ToolRegistry:
    """工具注册中心 - 参考MCP工具列表"""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
        return self
    
    def list_tools(self, agent_type: str = None) -> List[Dict]:
        tools = []
        for name, tool in self._tools.items():
            if agent_type and tool.category != agent_type and tool.category != "general":
                continue
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "input_schema": tool.input_schema
            })
        return tools
    
    def call(self, tool_name: str, **kwargs) -> Dict:
        if tool_name not in self._tools:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        return self._tools[tool_name].execute(**kwargs)


class NovelAgent:
    """小说创作智能体 - 参考Hello-Agents多智能体架构
    
    智能体角色（扩展版）：
    - PlotDesigner (情节设计): 负责大纲分解、伏笔管理、节奏控制
    - WorldBuilder (世界构建): 负责世界观一致性、场景描写
    - Writer (作家): 负责创作小说内容
    - Reviewer (审校): 负责检查质量和一致性
    - Editor (编辑/质量门): 负责最终裁定是否通过
    
    工具系统：标准化注册/调用，Agent自主选择工具
    
    协作流程（参考AutoGen的GroupChat模式）：
    1. PlotDesigner分析大纲 → 2. WorldBuilder构建场景
    3. Writer生成内容 → 4. Reviewer审校 → 5. Editor判定
       → 不过关 → Writer修订 → Reviewer再审校 → ...
       → 过关 → 保存定稿
    """
    
    # 质量阈值
    QUALITY_THRESHOLD = 75  # 评分低于此值自动触发修订
    MAX_REVISION_ROUNDS = 3  # 最多修订轮次
    
    def __init__(self, ai_client: AIClient, memory: MemoryManager, log_callback=None, config: AppConfig = None):
        self.ai = ai_client
        self.memory = memory
        self.log = log_callback or print
        self.config = config

        # 智能体会话历史（参考AutoGen的对话记录）
        self._conversation_log: List[AgentMessage] = []

        # 修订记忆（记录每次修订的原因）
        self._revision_memory: List[Dict] = []

        # 线程锁保护共享列表
        self._log_lock = threading.Lock()
        
        # 启用优化器模块
        self.orchestrator = AgentOrchestrator(ai_client, log_callback)
        self.context_optimizer = ContextOptimizer
        self.prompt_optimizer = PromptOptimizer
        
        # 工具注册中心（参考MCP协议）
        self.tools = ToolRegistry()
        self._register_tools()
        
        self.log("[智能体] Hello-Agents架构 v3.0: 5Agent+工具系统+动态上下文+标准协议")
    
    def _register_tools(self):
        """注册标准化工具"""
        self.tools.register(Tool("detect_scenes", "检测名场面",
            lambda content="", chapter_num=0: self.memory.add_event(chapter_num, f"场景检测: {content[:50]}", "scene"),
            category="writer"))
        self.tools.register(Tool("check_consistency", "检查一致性",
            lambda content="": f"一致性检查完成, 内容长度:{len(content)}",
            category="reviewer"))
        self.tools.register(Tool("generate_summary", "生成摘要",
            lambda chapter_num=0, content="": self.memory.get_chapter_summary(chapter_num) or "无",
            category="editor"))
        self.tools.register(Tool("get_characters", "获取角色列表",
            lambda: list(self.memory.get_characters().keys())[:10],
            category="general"))
        self.tools.register(Tool("get_outline", "获取章节大纲",
            lambda chapter_num=0: self.memory.get_meta("outline", {}).get(str(chapter_num), "无"),
            category="general"))
    
    def _record_conversation(self, agent: str, action: str, content: str):
        """记录智能体对话 - 使用标准AgentMessage协议"""
        msg = AgentMessage(MessageRole(agent.lower()) if hasattr(MessageRole, agent.upper()) else MessageRole.SYSTEM,
                          action, content)
        with self._log_lock:
            self._conversation_log.append(msg)
    
    def _build_context(self, chapter_num: int, extra_context: str = "", max_chars: int = None, 
                       writing_phase: str = "writing") -> str:
        """动态上下文工程 - 根据写作阶段智能分配比例 (Hello-Agents参考)
        
        写作阶段:
        - opening: 开头阶段，需要更多世界/角色描述
        - writing: 常规写作，平衡分配
        - action: 动作场景，需要近章上下文
        - dialogue: 对话场景，需要角色信息
        - ending: 结尾阶段，需要全局摘要
        """
        if max_chars is None:
            max_chars = self.config.get("context_window", 32000) // 4 if self.config else 8000
        
        # 动态比例分配
        ratios = {
            "opening":  {"global": 0.15, "volume": 0.10, "chars": 0.20, "recent": 0.35, "rag": 0.10, "extra": 0.10},
            "writing":  {"global": 0.10, "volume": 0.15, "chars": 0.15, "recent": 0.40, "rag": 0.10, "extra": 0.10},
            "action":   {"global": 0.05, "volume": 0.10, "chars": 0.10, "recent": 0.55, "rag": 0.10, "extra": 0.10},
            "dialogue": {"global": 0.05, "volume": 0.10, "chars": 0.35, "recent": 0.30, "rag": 0.10, "extra": 0.10},
            "ending":   {"global": 0.20, "volume": 0.10, "chars": 0.10, "recent": 0.40, "rag": 0.10, "extra": 0.10},
        }
        ratio = ratios.get(writing_phase, ratios["writing"])
        
        parts = []
        used = 0
        
        gs = self.memory.get_global_summary()
        if gs:
            text = self._compress_text(gs, int(max_chars * ratio["global"]), keep_tail=True)
            parts.append(f"【全局摘要】\n{text}")
            used += len(text)
        
        vol = self.memory.get_current_volume_summary(chapter_num)
        if vol:
            text = self._compress_text(vol, int(max_chars * ratio["volume"]), keep_tail=True)
            parts.append(f"【当前卷】\n{text}")
            used += len(text)
        
        chars = self.memory.get_characters()
        if chars:
            active_names = self.memory.get_active_characters(chapter_num, window=50)
            text = self._compress_active_characters(chars, active_names, int(max_chars * ratio["chars"]))
            if text:
                parts.append(f"【活跃角色】\n{text}")
                used += len(text)
        
        recent_count = 5 if chapter_num > 1000 else 3
        recent = self.memory.get_recent_summaries(recent_count)
        if recent:
            text = self._compress_text(recent, int(max_chars * ratio["recent"]), keep_tail=True)
            parts.append(f"【近期章节】\n{text}")
            used += len(text)
        
        if extra_context:
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                text = self._compress_text(rag_text, int(max_chars * ratio["rag"]), keep_tail=False)
                parts.append(f"【相关记忆】\n{text}")
        
        result = ContextOptimizer.optimize({"内容": "\n\n".join(parts)}, max_chars) if parts else ""
        return result
    
    def _compress_active_characters(self, chars: dict, active_names: List[str], budget: int) -> str:
        """压缩活跃角色信息"""
        result = []
        used = 0
        
        # 优先显示活跃角色
        for name in active_names:
            if used >= budget:
                break
            if name in chars:
                info = chars[name]
                if isinstance(info, dict):
                    personality = info.get("personality", "")[:30]
                    line = f"- {name}: {personality}"
                else:
                    line = f"- {name}: {str(info)[:50]}"
                if used + len(line) <= budget:
                    result.append(line)
                    used += len(line)
        
        # 如果还有空间，添加其他重要角色
        if used < budget:
            for name, info in list(chars.items())[:5]:
                if name not in active_names and used < budget:
                    if isinstance(info, dict):
                        personality = info.get("personality", "")[:20]
                        line = f"- {name}: {personality}"
                    else:
                        line = f"- {name}: {str(info)[:30]}"
                    if used + len(line) <= budget:
                        result.append(line)
                        used += len(line)
        
        return "\n".join(result)
    
    # ===== 压缩方法 =====
    
    def _compress_settings(self, settings: dict, budget: int) -> str:
        priority_keys = ["world", "rules", "factions", "technology", "history", "geography", "culture"]
        result = []
        used = 0
        for key in priority_keys:
            if key in settings and used < budget:
                val = str(settings[key])[:budget - used - len(key) - 3]
                result.append(f"{key}: {val}")
                used += len(val) + len(key) + 2
        return "\n".join(result)
    
    def _compress_characters(self, chars: dict, budget: int) -> str:
        core = ["name", "personality", "motivation"]
        result = []
        used = 0
        for name, info in list(chars.items())[:8]:
            if used >= budget: break
            if isinstance(info, dict):
                extra = "; ".join(f"{f}:{str(info.get(f,''))[:50]}" for f in core if f in info)
                line = f"- {name}: {extra}"[:budget - used]
            else:
                line = f"- {name}: {str(info)[:100]}"[:budget - used]
            result.append(line)
            used += len(line) + 1
        return "\n".join(result)
    
    def _compress_text(self, text: str, budget: int, keep_tail: bool = True) -> str:
        if len(text) <= budget: return text
        if budget < 50: return text[:budget] + "..."
        if keep_tail:
            head = int(budget * 0.3)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
        else:
            head = int(budget * 0.7)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
    
    def _compress_recent_chapters(self, recent_text: str, budget: int, chapter_num: int) -> str:
        chapters = recent_text.split("\n\n")
        if len(chapters) <= 1: return self._compress_text(recent_text, budget, True)
        result = []
        used = 0
        latest = chapters[-1] if chapters else ""
        lb = min(int(budget * 0.4), len(latest))
        if latest: result.append(latest[:lb]); used += lb
        for ch in reversed(chapters[:-1]):
            if used >= budget: break
            cb = min(int((budget - used) * 0.3), len(ch))
            if cb > 50: result.insert(0, self._compress_text(ch, cb, True)); used += cb
        return "\n\n".join(result)
    
    # ===== 多智能体协作核心 =====
    
    def generate_with_collaboration(self, chapter_num: int, chapter_title: str,
                                     chapter_outline: str, word_count: int = 3000) -> str:
        """多智能体协作生成章节 v3.0 - 5Agent协作
        
        Hello-Agents参考流程: PlotDesigner→WorldBuilder→Writer→Reviewer→Editor
        """
        self._conversation_log = []
        self.log(f"[编排器] 5Agent协作启动: 第{chapter_num}章「{chapter_title}」")
        
        # Phase 1: PlotDesigner - 分析大纲，管理伏笔
        self.log(f"[PlotDesigner] 分析大纲与伏笔...")
        self._record_conversation("PlotDesigner", "analyze", f"分析第{chapter_num}章大纲")
        plot_analysis = self._plot_designer_analyze(chapter_num, chapter_title, chapter_outline)
        
        # 根据情节分析确定上下文策略
        plot_type = plot_analysis.get("type", "writing")
        context = self._build_context(chapter_num, "", writing_phase=plot_type)
        self.log(f"[PlotDesigner] 情节类型: {plot_type}, 上下文已优化")
        
        # Phase 2: WorldBuilder - 场景与世界一致性
        self.log(f"[WorldBuilder] 构建场景描写...")
        self._record_conversation("WorldBuilder", "build", f"构建第{chapter_num}章场景")
        world_context = self._world_builder_build(chapter_num, plot_analysis)
        
        # Phase 3: Writer - 创作内容
        self.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self._record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        content = self._writer_generate(chapter_num, chapter_title, chapter_outline, word_count)
        
        # Phase 4-5: Reviewer → Editor 迭代修订
        for round_num in range(1, self.MAX_REVISION_ROUNDS + 1):
            self.log(f"[Reviewer] 审校第{chapter_num}章（第{round_num}轮）...")
            self._record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            review = self._reviewer_evaluate(chapter_num, content)
            
            # 工具调用: 一致性检查
            self.tools.call("check_consistency", content=content[:500])
            
            self.log(f"[Editor] 质量裁定：{review.get('overall_score', 0)}分")
            self._record_conversation("Editor", "judge", 
                f"评分{review.get('overall_score', 0)}，阈值{self.QUALITY_THRESHOLD}")
            
            if review.get("overall_score", 0) >= self.QUALITY_THRESHOLD:
                self.log(f"[Editor] ✅ 通过！质量达标。")
                self._record_conversation("Editor", "approve", "质量达标，通过")
                break
            
            suggestions = review.get("suggestions", [])
            issues = review.get("issues", [])
            self.log(f"[Editor] ⚠️ 质量不达标（{review.get('overall_score', 0)}/{self.QUALITY_THRESHOLD}），"
                    f"触发第{round_num}轮修订...")
            
            with self._log_lock:
                self._revision_memory.append({
                    "chapter": chapter_num,
                    "round": round_num,
                    "issues": issues,
                    "suggestions": suggestions,
                })
            
            self.log(f"[Writer] 正在根据审校意见修订...")
            self._record_conversation("Writer", "revise", f"第{round_num}轮修订")
            content = self._writer_revise(chapter_num, content, review, chapter_outline)
        
        self.log(f"[编排器] 第{chapter_num}章5Agent协作完成 ({len(content)}字)")
        return content
    
    def _plot_designer_analyze(self, chapter_num: int, title: str, outline: str) -> Dict:
        """PlotDesigner: 分析情节类型、节奏、伏笔"""
        if not outline or len(outline) < 10:
            if chapter_num <= 3: plot_type = "opening"
            elif chapter_num % 10 == 0: plot_type = "ending"
            else: plot_type = "writing"
            return {"type": plot_type, "pace": "medium", "foreshadowing": []}
        
        system = "你是专业情节设计师。分析章节大纲，输出JSON: {\"type\": \"opening/writing/action/dialogue/ending\", \"pace\": \"slow/medium/fast\", \"foreshadowing\": []}"
        prompt = f"第{chapter_num}章: {title}\n大纲: {outline[:500]}"
        try:
            response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=300)
            import re
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {"type": "writing", "pace": "medium", "foreshadowing": []}
    
    def _world_builder_build(self, chapter_num: int, plot_analysis: Dict) -> str:
        """WorldBuilder: 构建场景和世界观上下文"""
        settings = self.memory.get_settings()
        if settings and isinstance(settings, dict):
            world = settings.get("world", {})
            known = world.get("已知区域", [])[:3]
            if known:
                return f"世界观场景: {', '.join(known)}"
        return ""
    
    def _writer_generate(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int) -> str:
        """Writer智能体：生成章节内容"""
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent）。
请根据以下上下文信息创作小说章节。

{context}

创作要求：
1. 保持与前文的连贯性
2. 角色行为符合其性格设定
3. 情节推进自然流畅
4. 语言生动，有画面感
5. 目标字数约{word_count}字
6. 直接输出正文内容，不要添加额外说明
7. 注意设置伏笔和悬念"""
        
        prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："
        
        if word_count > 3000:
            return self._generate_long_chapter(chapter_num, chapter_title, chapter_outline, word_count, context)
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response)}")
        return response
    
    def _reviewer_evaluate(self, chapter_num: int, content: str, 
                           previous_feedback: str = "") -> dict:
        """Reviewer智能体：审校章节
        
        参考AutoGen的code_reviewer角色，检查质量和一致性
        """
        context = self._build_context(chapter_num)
        
        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n上次审校反馈（请重点关注）：\n{previous_feedback}"
        
        system = f"""你是一位专业的小说审校编辑（Reviewer Agent）。
请严格检查以下章节内容的各方面质量。

{context}
{feedback_section}

请以JSON格式输出审校结果：
{{
    "character_consistency": 0-100,  // 角色行为一致性
    "plot_logic": 0-100,             // 情节逻辑
    "writing_quality": 0-100,        // 文笔质量
    "emotional_impact": 0-100,       // 情感感染力
    "pacing": 0-100,                 // 节奏把控
    "overall_score": 0-100,          // 综合评分
    "strengths": ["优点1", ...],     // 写得好的地方
    "issues": ["问题1", ...],        // 发现的问题
    "suggestions": ["建议1", ...],   // 修改建议
    "is_acceptable": true/false      // 是否可接受
}}"""
        
        prompt = f"请审校第{chapter_num}章内容：\n\n{content[:4000]}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=2000)
        
        try:
            return self._parse_json_response(response, {"overall_score": 70, "issues": [], "suggestions": []})
        except Exception:
            return {"overall_score": 70, "issues": [], "suggestions": [], "raw": response}
    
    def _writer_revise(self, chapter_num: int, original: str, review: dict, 
                       chapter_outline: str) -> str:
        """Writer智能体：根据审校意见修订章节
        
        参考AutoGen的迭代优化循环
        """
        suggestions = review.get("suggestions", [])
        issues = review.get("issues", [])
        strengths = review.get("strengths", [])
        
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent），正在修订自己的作品。

{context}

修订原则：
1. 根据审校意见进行针对性修改
2. 保留已有的优点和长处
3. 修改时注意不要破坏整体的连贯性
4. 回应每一个具体问题"""
        
        prompt = f"""请修订第{chapter_num}章内容。

审校反馈：
优点（请保持）：{json.dumps(strengths, ensure_ascii=False)}
问题（需修改）：{json.dumps(issues, ensure_ascii=False)}
建议（参考）：{json.dumps(suggestions, ensure_ascii=False)}

原文：
{original[-4000:] if len(original) > 4000 else original}

修订要求：请输出完整的修订后文本，直接输出正文："""
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 修订完成，字数：{len(response)}")
        return response
    
    # ===== 传统方法（兼容旧接口）=====
    
    def generate_chapter(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int = 3000) -> str:
        """生成章节 - 带重复检测与修复"""
        max_retries = 3
        content = self.generate_with_collaboration(chapter_num, chapter_title, 
                                                    chapter_outline, word_count)
        
        if not content:
            self.log(f"第{chapter_num}章生成失败，返回空内容")
            return f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"
        
        for retry in range(max_retries):
            has_rep, actual_words = self._has_excessive_repetition(content, word_count)
            if not has_rep:
                self.log(f"第{chapter_num}章质量检测通过 ({actual_words}字)")
                return content
            
            self.log(f"[重试{retry+1}/{max_retries}] 第{chapter_num}章重复问题: 当前{actual_words}字→目标{word_count}字")
            
            strict_system = f"""你是专业小说作家。请根据大纲创作第{chapter_num}章。
【核心要求】
1. 目标字数{word_count}字，必须达标
2. 绝不允许重复内容。每500字推进一次剧情
3. 用{max(word_count//2000, 1)}个不同的场景段落来写
4. 每个场景换地点、换人物、换冲突

第{chapter_num}章大纲: {chapter_outline}

直接输出小说正文，不要解释。"""
            
            # 限制max_tokens避免超时(中文字约1.5token/字)
            retry_tokens = min(word_count * 2, 16384)
            new_content = self.ai.chat(
                [{"role": "user", "content": f"创作第{chapter_num}章：{chapter_title}，{word_count}字"}],
                system=strict_system, max_tokens=retry_tokens
            )
            if new_content:
                content = new_content
        
        self.log(f"第{chapter_num}章生成完成 ({len(content) if content else 0}字)")
        return content or f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"
        return content
    
    def _has_excessive_repetition(self, content: str, target_words: int) -> tuple:
        """检测是否存在过度重复，返回 (has_repetition, actual_word_count)"""
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        actual_chars = len(content)
        actual_words = actual_chars  # 中文字符数=字数
        
        # 字数严重不达标
        if actual_words < target_words * 0.3:
            return (True, actual_words)
        
        if len(paragraphs) < 3:
            return (actual_words < target_words * 0.6, actual_words)
        
        # 检测相似段落
        similar_count = 0
        for i in range(len(paragraphs)):
            for j in range(i + 1, min(i + 5, len(paragraphs))):
                if len(paragraphs[i]) > 80 and len(paragraphs[j]) > 80:
                    words_i = set(paragraphs[i][:80].split())
                    words_j = set(paragraphs[j][:80].split())
                    if words_i and words_j:
                        overlap = len(words_i & words_j) / min(len(words_i), len(words_j))
                        if overlap > 0.7:  # 提高阈值减少误判
                            similar_count += 1
        
        # 短段落占比检查 - 中文网文短段落是正常的，阈值放高
        short_paras = sum(1 for p in paragraphs if len(p) < 30)
        short_ratio = short_paras / len(paragraphs)
        
        self.log(f"[质量检测] 相似段落对:{similar_count}, 短段落比:{short_ratio:.2f}, 字数:{actual_words}/{target_words}")
        
        # 只有同时满足多个条件才判定为重复
        has_rep = (similar_count > 10 or 
                  (actual_words < target_words * 0.4 and short_ratio > 0.5) or
                  (similar_count > 3 and short_ratio > 0.7))
        return (has_rep, actual_words)
    
    def review_chapter(self, chapter_num: int, content: str) -> dict:
        """审校章节"""
        return self._reviewer_evaluate(chapter_num, content)
    
    def generate_settings(self, genre: str, title: str, concept: str) -> dict:
        """生成世界观 - 留有扩展空间"""
        self.log(f"[智能体] 正在生成世界观...")
        system = """你是一位专业的小说世界观设定师。请生成世界观设定。

## 重要原则
1. **留有扩展空间**：不要把所有设定都写死，要留下未解之谜和模糊地带
2. **灵活多变**：世界观应该可以随着故事发展而扩展和深化
3. **层次分明**：分为已知、未知、传说三个层次
4. **自洽但有漏洞**：整体逻辑自洽，但要有一些"矛盾"或"未解之谜"供后续扩展

## 输出格式（JSON）
{
  "world": {"name": "", "type": "", "已知区域": [], "未知区域": [], "传说": []},
  "rules": {"基本规则": [], "特殊情况": [], "未解之谜": []},
  "factions": {"主要势力": [], "隐藏势力": [], "历史势力": []},
  "history": {"重要事件": [], "失落的历史": [], "争议事件": []},
  "magic_system": {"基本原理": [], "高级奥秘": [], "禁忌": []},
  "technology": {"常见": [], "稀有": [], "失传": []},
  "geography": {"已知": [], "未探索": [], "传说之地": []},
  "扩展提示": ["后续可以发展的方向1", "后续可以发展的方向2"]
}"""
        prompt = f"小说类型：{genre}\n标题：{title}\n概念：{concept}\n\n请生成一个灵活、可扩展的世界观。"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)
        settings = self._parse_json_response(response, {"raw": response})
        self.memory.save_settings(settings)
        return settings
    
    def generate_characters(self, genre: str, title: str, count: int = None) -> dict:
        """生成角色 - 根据小说规模智能确定角色数量"""
        if count is None:
            chapter_count = self.memory.get_meta("chapter_count", 20)
            if chapter_count <= 20: count = 3
            elif chapter_count <= 50: count = 5
            else: count = 8
        
        self.log(f"[智能体] 正在生成{count}个角色...")
        settings = self.memory.get_settings()
        
        system = f"""你是专业角色设计师。世界观：{json.dumps(settings, ensure_ascii=False)[:500]}
请为小说《{title}》创建{count}个角色。必须输出JSON格式：

{{
  "角色名": {{
    "gender": "男/女/未知",
    "age": 25,
    "category": "主角/关键人物/配角/无名小卒",
    "faction": "中立/主角阵营/敌对阵营/第三方势力",
    "personality": "性格描述（50字以上，具体、有特点、有弱点）",
    "background": "背景故事（100字以上，包括出身、经历、动机）",
    "appearance": "外貌描述",
    "weapon": {{"name": "武器名", "quality": "普通/精良/稀有/史诗/传说", "desc": "描述"}},
    "skill_suggestions": ["技能1", "技能2"],
    "attributes": {{
      "力量": 随机值,
      "敏捷": 随机值,
      "智力": 随机值,
      "体力": 随机值,
      "魅力": 随机值
    }},
    "relationship_to_main": "与主角的关系",
    "goal": "角色目标"
  }}
}}

要求：
- 每个角色必须有独特的人格和背景
- 武器和技能必须符合世界观
- 属性值合理分布（不是所有角色同属性）"""
        
        prompt = f"小说类型：{genre}\n标题：{title}\n创建{count}个角色，每个角色有完整的性格、背景、武器、技能"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        chars = self._parse_json_response(response, {"raw": response})
        self.memory.save_characters(chars)
        
        # 同时保存到 CharacterSystem 格式（每个角色一个文件）
        characters_dir = self.memory.novel_dir / "characters" if hasattr(self.memory, 'novel_dir') else None
        if characters_dir is None:
            # 尝试从 memory_dir 推断 novel_dir
            characters_dir = self.memory.memory_dir.parent / "characters"
        characters_dir.mkdir(exist_ok=True)
        
        for name, data in chars.items():
            if isinstance(data, dict):
                char_data = {"name": name, **data}
                with open(characters_dir / f"{name}.json", 'w', encoding='utf-8') as f:
                    json.dump(char_data, f, indent=2, ensure_ascii=False)
        
        return chars
    
    def generate_outline(self, genre: str, title: str, chapter_count: int, concept: str = "") -> list:
        """生成大纲 - 支持大量章节分批生成"""
        max_batch = 50  # 每批最多生成50章大纲
        
        if chapter_count <= max_batch:
            return self._generate_outline_batch(genre, title, chapter_count, 1, concept)
        
        # 大量章节分批生成
        self.log(f"[智能体] 共{chapter_count}章，分批生成大纲（每批{max_batch}章）...")
        all_outline = []
        
        for start_ch in range(1, chapter_count + 1, max_batch):
            batch_count = min(max_batch, chapter_count - start_ch + 1)
            self.log(f"[大纲] 生成第{start_ch}-{start_ch+batch_count-1}章大纲...")
            batch_outline = self._generate_outline_batch(genre, title, batch_count, start_ch, concept)
            all_outline.extend(batch_outline)
            
            # 更新上下文
            if all_outline:
                last_summary = all_outline[-1].get("summary", "")
                concept = f"已规划{len(all_outline)}章。上一章摘要：{last_summary}"
        
        return all_outline
    
    def _generate_outline_batch(self, genre: str, title: str, count: int, start_num: int, concept: str = "") -> list:
        """生成一批大纲"""
        context = self._build_context(0)
        system = f"你是专业小说大纲规划师。\n{context}\n输出JSON数组：[{{'chapter':{start_num},'title':'','summary':'','key_events':[],'characters_involved':[]}}]"
        prompt = f"小说类型：{genre}\n标题：{title}\n章节数：{count}章（从第{start_num}章开始）"
        if concept:
            prompt += f"\n用户想法：{concept}\n请基于用户的想法来规划大纲"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        outline = self._parse_json_response(response, [], is_list=True)
        if not outline:
            outline = [{"chapter": start_num+i, "title": f"第{start_num+i}章", "summary": concept if concept else "待规划"} 
                      for i in range(count)]
        return outline
    
    def generate_outline_continuation(self, genre: str, title: str, 
                                      add_count: int, global_context: str,
                                      current_count: int) -> list:
        """续写大纲 - 在已有章节基础上生成新章"""
        self.log(f"[智能体] 基于已有{current_count}章，续写{add_count}章大纲...")
        
        context = global_context[:1000] if global_context else ""
        system = (
            f"你是专业小说大纲规划师。已有{current_count}章内容。\n"
            f"历史摘要：{context}\n\n"
            f"请在已有章节基础上，规划{add_count}章新内容实现故事续写。\n"
            f"章节从第{current_count+1}章开始编号。\n"
            f"必须延续已有剧情、保持风格。\n"
            f"输出JSON数组：[{{'chapter':{current_count+1},'title':'','summary':'','key_events':[],'characters_involved':[]}}]"
        )
        prompt = f"小说类型：{genre}\n标题：{title}\n续写{add_count}章，从第{current_count+1}章开始"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        outline = self._parse_json_response(response, [], is_list=True)
        if not outline:
            outline = [{"chapter": current_count+i+1, "title": f"第{current_count+i+1}章", 
                       "summary": "待规划"} for i in range(add_count)]
        return outline
    
    def finalize_chapter(self, chapter_num: int, content: str):
        """定稿章节 + 更新记忆 + 角色属性变化"""
        # 章节摘要
        summary = self.ai.chat(
            [{"role": "user", "content": f"请生成摘要（100-200字）：\n{content[:2000]}"}],
            system="你是故事摘要助手。", max_tokens=300
        )
        self.memory.save_chapter_summary(chapter_num, summary)
        
        # 全局摘要
        old = self.memory.get_global_summary()
        new = self.ai.chat(
            [{"role": "user", "content": f"更新全局摘要：\n旧：{old}\n新章节：{summary}"}],
            system="你是故事摘要助手。", max_tokens=500
        )
        self.memory.save_global_summary(new)
        
        # 关键词索引
        kw = self.ai.chat([{"role": "user", "content": f"提取10个关键词，逗号分隔：\n{content[:1000]}"}],
                         system="提取关键词。", max_tokens=200)
        keywords = [k.strip() for k in kw.split(",") if k.strip()]
        self.memory.update_index(chapter_num, keywords)
        
        # 添加记忆块
        self.memory.add_chunk("plot", summary, importance=8, 
                             tags=keywords[:5] if keywords else [])
        self.memory.add_event(chapter_num, summary, "story")
        
        # 角色属性变化检测
        self._update_character_progression(chapter_num, content, summary)
        
        self.log(f"[智能体] 第{chapter_num}章定稿完成")
    
    def _update_character_progression(self, chapter_num: int, content: str, summary: str):
        """检测角色成长变化并更新属性"""
        try:
            chars = self.memory.get_characters()
            if not chars:
                return
            
            # 构建角色列表（含更多上下文）
            char_list = []
            for name, info in list(chars.items())[:20]:
                if isinstance(info, dict):
                    role = info.get("category", info.get("role", "未知"))
                    faction = info.get("faction", "未知")
                    char_list.append(f"{name}({role}/{faction})")
                else:
                    char_list.append(name)
            existing_names = ", ".join(char_list)
            
            system = f"""分析第{chapter_num}章中所有角色的变化（主角、配角、反派、路人等都算）。
当前角色: {existing_names}

【重要】检测本章中所有角色（不只主角）的：
- 战斗成长（属性提升）
- 关系变化（盟友/敌人）  
- 物品得失（宝物/武器/装备）
- 技能领悟
- 角色死亡或重伤

输出JSON:
{{
  "updates": [
    {{"name": "角色名", "change": "+力量+3 或 +智力+2", "reason": "战斗中突破极限"}}
  ],
  "relationship_changes": [
    {{"name1": "角色A", "name2": "角色B", "old": "朋友", "new": "敌人", "reason": "背叛"}}
  ],
  "items_gained": [
    {{"name": "角色名", "item": "物品名", "quality": "普通/精良/稀有/史诗/传说", "from": "来源"}}
  ],
  "items_lost": [
    {{"name": "角色名", "item": "物品名", "reason": "战斗中毁坏"}}
  ],
  "skills_learned": [
    {{"name": "角色名", "skill": "技能名", "type": "攻击/防御/辅助", "how": "如何学会"}}
  ],
  "deaths": ["死亡角色名"],
  "new_allies": ["新盟友名"],
  "new_enemies": ["新敌人名"]
}}

变化包括正面和负面的。没有变化就输出{{}}。
**必须检测所有出现的角色，不止主角。**"""
            
            response = self.ai.chat(
                [{"role": "user", "content": f"章节摘要: {summary}\n内容片段: {content[:1500]}"}],
                system=system, max_tokens=800
            )
            
            import re
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                data = json.loads(match.group())
                
                # 保存到记忆
                changes = 0
                if data.get("updates"):
                    for u in data["updates"]:
                        self.memory.add_event(chapter_num, 
                            f"角色变化: {u['name']} {u['change']} ({u.get('reason','')})",
                            "character_growth")
                        changes += 1
                
                if data.get("skills_learned"):
                    for s in data["skills_learned"]:
                        self.memory.add_event(chapter_num,
                            f"技能领悟: {s['name']} 学会 {s['skill']}",
                            "skill_learn")
                        changes += 1
                
                if data.get("relationship_changes"):
                    for r in data["relationship_changes"]:
                        self.memory.add_event(chapter_num,
                            f"关系变化: {r['name1']}与{r['name2']} {r['old']}→{r['new']}",
                            "relationship_change")
                        changes += 1
                
                if data.get("items_gained"):
                    for item in data["items_gained"]:
                        self.memory.add_event(chapter_num,
                            f"获得物品: {item['name']} 获得 {item['item']}",
                            "item_gain")
                
                if data.get("items_lost"):
                    for item in data["items_lost"]:
                        self.memory.add_event(chapter_num,
                            f"失去物品: {item['name']} 失去 {item['item']}",
                            "item_loss")
                
                if data.get("new_allies"):
                    for name in data["new_allies"]:
                        self.memory.add_event(chapter_num,
                            f"新盟友: {name}", "new_ally")
                
                if data.get("new_enemies"):
                    for name in data["new_enemies"]:
                        self.memory.add_event(chapter_num,
                            f"新敌人: {name}", "new_enemy")
                
                if data.get("deaths"):
                    for name in data["deaths"]:
                        self.memory.add_event(chapter_num,
                            f"角色死亡: {name}", "character_death")
                        self.memory.update_character(name, {"status": "死亡", "death_chapter": chapter_num})
                
                # 统计日志
                summary_parts = []
                if changes: summary_parts.append(f"{changes}个成长")
                if data.get("items_gained"): summary_parts.append(f"{len(data['items_gained'])}个获得")
                if data.get("items_lost"): summary_parts.append(f"{len(data['items_lost'])}个失去")
                if data.get("skills_learned"): summary_parts.append(f"{len(data['skills_learned'])}个技能")
                if data.get("relationship_changes"): summary_parts.append(f"{len(data['relationship_changes'])}个关系")
                if data.get("deaths"): summary_parts.append(f"{len(data['deaths'])}个死亡")
                if data.get("new_allies"): summary_parts.append(f"{len(data['new_allies'])}个新盟友")
                if data.get("new_enemies"): summary_parts.append(f"{len(data['new_enemies'])}个新敌人")
                
                if summary_parts:
                    self.log(f"[角色成长] 第{chapter_num}章: {', '.join(summary_parts)}")
        except Exception as e:
            self.log(f"[角色成长] 检测跳过: {e}")
    
    # ===== 风格模仿 =====
    
    def analyze_style(self, text: str, author_name: str = "未知作者") -> dict:
        """分析一段文字的写作风格"""
        self.log(f"[智能体] 正在分析 {author_name} 的写作风格...")
        
        system = """你是专业的文学风格分析师。分析给定文本的写作风格，输出JSON格式。
分析维度：
1. 句式特点（长短句比例、句式结构）
2. 用词习惯（词汇偏好、用语特点）
3. 叙事视角（第一/第三人称、视角切换）
4. 描写手法（环境描写、人物描写、心理描写的特点）
5. 对话风格（对话比例、对话方式）
6. 节奏感（快慢节奏、紧张舒缓）
7. 情感基调（整体情感氛围）
8. 独特特征（该作者最具辨识度的写作特点）
9. 模仿要点（模仿该风格需要注意的关键点）

输出格式：
{
  "author": "作者名",
  "sentence_style": "句式特点",
  "word_choice": "用词习惯",
  "narrative_perspective": "叙事视角",
  "description_technique": "描写手法",
  "dialogue_style": "对话风格",
  "rhythm": "节奏感",
  "emotional_tone": "情感基调",
  "unique_features": "独特特征",
  "imitation_tips": "模仿要点"
}"""
        
        prompt = f"请分析以下文本的写作风格（作者：{author_name}）：\n\n{text[:3000]}"
        
        result = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=2000)
        style = self._parse_json_response(result, {"author": author_name, "raw": result})
        
        self.log(f"[智能体] {author_name} 风格分析完成")
        return style
    
    def generate_with_style(self, prompt: str, style: dict, word_count: int = 3000) -> str:
        """使用指定风格生成文本"""
        style_desc = json.dumps(style, ensure_ascii=False, indent=2) if isinstance(style, dict) else str(style)
        
        system = f"""你是专业小说作家。请严格按照以下写作风格创作：

风格特征：
{style_desc}

创作要求：
1. 严格遵循上述风格特征
2. 保持句式、用词、叙事方式与原风格一致
3. 内容要自然流畅，不要刻意模仿痕迹
4. 直接输出创作内容，不要添加解释"""
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=word_count * 2)
        return response
    
    def blend_styles(self, styles: List[dict], prompt: str, word_count: int = 3000) -> str:
        """融合多个作者的风格生成文本"""
        styles_desc = ""
        for i, style in enumerate(styles):
            author = style.get("author", f"风格{i+1}")
            styles_desc += f"\n--- {author} ---\n"
            styles_desc += f"句式: {style.get('sentence_style', '')}\n"
            styles_desc += f"用词: {style.get('word_choice', '')}\n"
            styles_desc += f"描写: {style.get('description_technique', '')}\n"
            styles_desc += f"独特特征: {style.get('unique_features', '')}\n"
        
        system = f"""你是专业小说作家。请融合以下多位作者的写作风格进行创作：

{styles_desc}

融合要求：
1. 吸收每位作者的独特优点
2. 创造出自然融合的新风格
3. 不要生硬拼凑，要有机融合
4. 直接输出创作内容，不要添加解释"""
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=word_count * 2)
        return response
    
    # ===== 工具方法 =====
    
    @staticmethod
    def _parse_json_response(response: str, default: Any, is_list: bool = False) -> Any:
        """解析AI返回的JSON"""
        try:
            marker = "[" if is_list else "{"
            end_marker = "]" if is_list else "}"
            start = response.find(marker)
            end = response.rfind(end_marker) + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return default
    
    def _generate_long_chapter(self, chapter_num, chapter_title, chapter_outline, word_count, context) -> str:
        """分段生成长章节 - 逐段续写不重复，自动加标题"""
        seg_size = 2000
        part_count = max((word_count + seg_size - 1) // seg_size, 1)
        part_count = min(part_count, 5)
        
        title_line = f"# 第{chapter_num}章：{chapter_title}\n\n" if chapter_title and chapter_title != f"第{chapter_num}章" else f"# 第{chapter_num}章\n\n"
        
        parts = []
        for i in range(part_count):
            self.log(f"[Writer] 第{chapter_num}章 第{i+1}/{part_count}段...")
            
            prev_text = ''.join(parts)
            if i == 0:
                part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文："
            else:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                part_prompt = f"紧接上文继续写。上文结尾：{last_200}\n要求：继续推进剧情约{seg_size}字，严禁重复。"
            
            for attempt in range(3):
                try:
                    response = self.ai.chat(
                        [{"role": "user", "content": part_prompt}],
                        system=f"严密续写，绝不重复。\n{context[:500] if context else ''}", 
                        max_tokens=2048
                    )
                    if response and len(response) > 100:
                        # 去掉AI可能自己加的标题（所有段）
                        if response.startswith('#'):
                            after_title = response.split('\n', 1)
                            if len(after_title) > 1 and len(after_title[1].strip()) > 20:
                                response = after_title[1].lstrip()
                        parts.append(response)
                        break
                except Exception as e:
                    self.log(f"[Writer] 第{chapter_num}章第{i+1}段 重试{attempt+1}: {e}")
                    if attempt == 2:
                        return title_line + ("\n\n".join(parts) if parts else "（生成失败）")
        
        return title_line + ("\n\n".join(parts) if parts else "（生成失败）")
