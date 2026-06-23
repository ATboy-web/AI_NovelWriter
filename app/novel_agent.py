"""
小说创作智能体模块 - 参考AutoGen多智能体协作架构 v3.0

改进 (Hello-Agents 参考):
- 多Agent专业化协作 (PlotDesigner/WorldBuilder/Writer/Reviewer/Editor)
- 标准化工具系统 (ToolRegistry + Tool协议)
- 动态上下文工程 (根据写作阶段智能分配)
- 标准化通信协议 (AgentMessage)
"""

import json
import re
import threading
import time
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from enum import Enum

from .ai_client import AIClient, PromptManager
from .agent_orchestrator import AgentOrchestrator
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
        # BUG-2修复: 角色名到枚举的正确映射
        _ROLE_MAP = {"PlotDesigner": "PLOT", "WorldBuilder": "WORLD",
                     "Writer": "WRITER", "Reviewer": "REVIEWER", "Editor": "EDITOR"}
        role_name = _ROLE_MAP.get(agent, "SYSTEM")
        role = MessageRole[role_name]
        msg = AgentMessage(role, action, content)
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
            max_chars = self.config.get("context_window", 32000) // 3 if self.config else 10000
        
        # 动态比例分配 — extra_context(前文内容)是连贯性关键，必须占大比例
        ratios = {
            "opening":  {"global": 0.10, "volume": 0.05, "chars": 0.15, "recent": 0.10, "rag": 0.10, "extra": 0.50},
            "writing":  {"global": 0.08, "volume": 0.07, "chars": 0.10, "recent": 0.10, "rag": 0.10, "extra": 0.55},
            "action":   {"global": 0.05, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.65},
            "dialogue": {"global": 0.05, "volume": 0.05, "chars": 0.25, "recent": 0.10, "rag": 0.10, "extra": 0.45},
            "ending":   {"global": 0.10, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.60},
        }
        ratio = ratios.get(writing_phase, ratios["writing"])
        
        parts = []
        used = 0
        
        gs = self.memory.get_global_summary()
        if gs:
            text = self._compress_text(gs, int(max_chars * ratio["global"]), keep_tail=True)
            section = f"【全局摘要】\n{text}"
            parts.append(section)
            used += len(section)
        
        vol = self.memory.get_current_volume_summary(chapter_num)
        if vol:
            text = self._compress_text(vol, int(max_chars * ratio["volume"]), keep_tail=True)
            section = f"【当前卷】\n{text}"
            parts.append(section)
            used += len(section)
        
        chars = self.memory.get_characters()
        if chars:
            active_names = self.memory.get_active_characters(chapter_num, window=50)
            text = self._compress_active_characters(chars, active_names, int(max_chars * ratio["chars"]))
            if text:
                section = f"【活跃角色】\n{text}"
                parts.append(section)
                used += len(section)
        
        recent_count = 5 if chapter_num > 1000 else 3
        recent = self.memory.get_recent_summaries(recent_count)
        if recent:
            text = self._compress_text(recent, int(max_chars * ratio["recent"]), keep_tail=True)
            section = f"【近期章节】\n{text}"
            parts.append(section)
            used += len(section)
        
        if extra_context:
            # 直接注入外部上下文（世界观、大纲等关键信息）
            ec_budget = int(max_chars * ratio["extra"])
            # keep_tail=True: 保留结尾（前一章结尾是连贯性关键）
            ec_text = self._compress_text(extra_context, ec_budget, keep_tail=True)
            parts.append(f"【创作指引】\n{ec_text}")
            used += len(ec_text)
            
            # 同时做RAG检索补充
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                text = self._compress_text(rag_text, min(int(max_chars * ratio["rag"]), max_chars - used), keep_tail=False)
                if text and len(text) > 20:
                    parts.append(f"【相关记忆】\n{text}")
        
        # 🔧 修复: ContextOptimizer.optimize 接口不匹配导致上下文被静默丢弃
        # 原代码: ContextOptimizer.optimize({"内容": ...}) 只接受 "内容" 键
        # 但 optimize 迭代 COMPRESSION_RATIOS 键 (global_summary, volume_summary, ...) 
        # 导致全部内容被跳过 → 返回空字符串 → Writer/Reviewer 无上下文
        # 修复: 直接拼接 parts 并用简单截断
        result = "\n\n".join(parts)
        if len(result) > max_chars:
            marker = "\n...(截断)...\n"
            head = int(max_chars * 0.3)
            tail = max_chars - head - len(marker)
            result = result[:head] + marker + result[-tail:]
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
                                     chapter_outline: str, word_count: int = 3000,
                                     prev_context: str = "") -> str:
        """多智能体协作生成章节 v3.0 - 5Agent协作
        
        Hello-Agents参考流程: PlotDesigner→WorldBuilder→Writer→Reviewer→Editor
        """
        with self._log_lock:
            self._conversation_log = []
        self.log(f"[编排器] 5Agent协作启动: 第{chapter_num}章「{chapter_title}」")
        
        # 🔑 提取前一章结尾（在压缩前保存，确保不丢失）
        prev_ending = ""
        if prev_context and "【前一章" in str(prev_context):
            import re as _re
            m = _re.search(r'【前一章·第\d+章结尾.*?】\n(.+?)(?:\n---|\n【|\Z)', str(prev_context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-1200:]
        
        # Phase 1: PlotDesigner - 分析大纲，管理伏笔
        self.log(f"[PlotDesigner] 分析大纲与伏笔...")
        self._record_conversation("PlotDesigner", "analyze", f"分析第{chapter_num}章大纲")
        plot_analysis = self._plot_designer_analyze(chapter_num, chapter_title, chapter_outline)
        
        # 注入前几章内容上下文
        plot_type = plot_analysis.get("type", "writing")
        context = self._build_context(chapter_num, prev_context, writing_phase=plot_type)
        self.log(f"[PlotDesigner] 情节类型: {plot_type}, 上下文已注入(全局摘要+卷摘要+角色+近期章节+创作指引)")
        
        # Phase 2: WorldBuilder - 场景与世界一致性
        self.log(f"[WorldBuilder] 构建场景描写...")
        self._record_conversation("WorldBuilder", "build", f"构建第{chapter_num}章场景")
        world_context = self._world_builder_build(chapter_num, plot_analysis)
        
        # 🔧 BUG-1修复: 将WorldBuilder输出注入Writer上下文
        if world_context:
            context = f"【场景描写 - WorldBuilder输出】\n{world_context}\n\n{context}"
        
        # Phase 3: Writer - 创作内容
        self.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self._record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        content = self._writer_generate(chapter_num, chapter_title, chapter_outline, word_count, context=context, prev_ending=prev_ending)
        
        # Phase 4-5: Reviewer → Editor 迭代修订
        prev_feedback = ""
        for round_num in range(1, self.MAX_REVISION_ROUNDS + 1):
            self.log(f"[Reviewer] 审校第{chapter_num}章（第{round_num}轮）...")
            self._record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            review = self._reviewer_evaluate(chapter_num, content, previous_feedback=prev_feedback)
            
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
            prev_feedback = f"上轮问题: {'; '.join(issues[:5])}" if issues else ""
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
            content = self._writer_revise(chapter_num, content, review, chapter_outline, context=context, prev_ending=prev_ending)
        
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
            if response:
                import re
                match = re.search(r'\{[\s\S]*\}', response)
                if match:
                    return json.loads(match.group())
        except Exception as e:
            self.log(f"[PlotDesigner] 分析失败: {e}")
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
                         chapter_outline: str, word_count: int,
                         context: str = None, prev_ending: str = "") -> str:
        """Writer智能体：生成章节内容"""
        if context is None:
            context = self._build_context(chapter_num)
        
        # 🔒 读取锁定的主角名
        protagonist = self.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f'\n\n【重要·主角锁定】本小说主角名为「{protagonist}」。所有章节必须以「{protagonist}」为主视角，禁止更换主角名！如果大纲中写"主角"，实际就是「{protagonist}」。'
        
        system = f"""你是一位专业的小说作家（Writer Agent）。
请根据以下上下文信息创作小说章节。
{context}
{protagonist_hint}

【正向要求 - 你必须做到】
1. 【最重要】必须紧接前一章结尾继续，保持时间、地点、情节的绝对连贯！
2. 角色行为符合其性格设定，保持人物形象一致
3. 情节推进自然流畅，有起承转合
4. 语言生动形象，有画面感和代入感
5. 目标字数约{word_count}字，必须写够字数
6. 直接输出正文内容，不要添加额外说明
7. 巧妙设置伏笔和悬念，吸引读者继续阅读
8. 对话要符合角色性格，有个性化特征
9. 场景描写要有细节，调动五感（视觉、听觉、嗅觉、触觉、味觉）
10. 适当运用修辞手法（比喻、拟人、排比等）增强文采

【负面禁止 - 绝对不能做】
1. 禁止使用Markdown格式（禁止**加粗**、*斜体*、#标题等标记），使用纯文本
2. 禁止出现重复内容、凑字数的废话
3. 禁止角色行为前后矛盾（如性格突变、能力突变）
4. 禁止情节逻辑漏洞（如时间线混乱、因果关系错误）
5. 禁止使用现代网络用语（如"666"、"yyds"等），保持文风统一
6. 禁止在正文中出现作者旁白、元叙述（如"接下来会发生什么"）
7. 禁止突然跳出故事视角（如"读者可能会想"）
8. 禁止使用过多的"的"、"了"、"着"等助词堆砌
9. 禁止对话过于书面化，要口语化、自然
10. 禁止场景转换生硬，要有过渡"""
        
        # 直接使用传入的前一章结尾（从generate_with_collaboration提取，未被压缩）
        if not prev_ending and "【前一章" in str(context):
            import re as _re
            m = _re.search(r'【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)', str(context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-800:]
        
        if prev_ending:
            prompt = f"【前一章结尾 — 你必须紧接以下内容继续创作】\n{prev_ending}\n\n---\n\n请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文（必须紧接前文）："
        else:
            prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："
        
        if word_count > 3000:
            return self._generate_long_chapter(chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending)
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response) if response else 0}")
        return response or ""
    
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

【正向检查 - 重点关注优点】
1. 角色塑造是否立体、有成长弧线
2. 情节是否有张力、有悬念
3. 文笔是否生动、有画面感
4. 情感表达是否真挚、有感染力
5. 节奏把控是否得当、有起伏
6. 伏笔设置是否巧妙、有回收
7. 世界观设定是否一致、有深度
8. 对话是否自然、符合角色性格
9. 场景描写是否有细节、氛围感
10. 章节结尾是否有悬念、吸引继续阅读

【负面检查 - 重点发现问题】
1. 角色行为是否前后矛盾（如性格突变、能力突变）
2. 情节是否有逻辑漏洞（如时间线混乱、因果错误）
3. 是否有重复内容或凑字数的情况
4. 文风是否突然变化（如从古风突变现代）
5. 关键设定是否与前文冲突
6. 场景转换是否生硬、缺乏过渡
7. 是否有明显的错别字或语病
8. 是否有过于冗长、拖沓的段落

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
            return self._parse_json_response(response or "{}", {"overall_score": 70, "issues": [], "suggestions": []})
        except Exception:
            return {"overall_score": 70, "issues": [], "suggestions": [], "raw": response}
    
    def _writer_revise(self, chapter_num: int, original: str, review: dict, 
                       chapter_outline: str, context: str = None, prev_ending: str = "") -> str:
        """Writer智能体：根据审校意见修订章节
        
        参考AutoGen的迭代优化循环
        """
        suggestions = review.get("suggestions", [])
        issues = review.get("issues", [])
        strengths = review.get("strengths", [])
        
        if context is None:
            context = self._build_context(chapter_num)
        
        # 🔒 读取锁定的主角名
        protagonist = self.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n\n【重要·主角锁定】主角名为「{protagonist}」，修订时不得更换主角名！"
        
        # 前一章结尾提示
        ending_hint = ""
        if prev_ending:
            ending_hint = f"\n\n【前一章结尾 — 修订后仍需紧接此情节】\n{prev_ending[-600:]}"
        
        system = f"""你是一位专业的小说作家（Writer Agent），正在修订自己的作品。
{context}
{protagonist_hint}
{ending_hint}

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
        self.log(f"[Writer] 修订完成，字数：{len(response) if response else 0}")
        return response or original
    
    # ===== 传统方法（兼容旧接口）=====
    
    def generate_chapter(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int = 3000,
                         prev_context: str = "") -> str:
        """生成章节 - 带重复检测与修复"""
        max_retries = 3
        content = self.generate_with_collaboration(chapter_num, chapter_title, 
                                                    chapter_outline, word_count,
                                                    prev_context)
        
        if not content:
            self.log(f"第{chapter_num}章生成失败，返回空内容")
            return f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"
        
        for retry in range(max_retries):
            has_rep, actual_words = self._has_excessive_repetition(content, word_count)
            if not has_rep:
                self.log(f"第{chapter_num}章质量检测通过 ({actual_words}字)")
                return content
            
            self.log(f"[重试{retry+1}/{max_retries}] 第{chapter_num}章重复问题: 当前{actual_words}字→目标{word_count}字")
            
            # 重试前等待，避免API过载
            if retry > 0:
                time.sleep(retry * 3)  # 3s, 6s
            
            strict_system = f"""你是专业小说作家。请根据大纲创作第{chapter_num}章。
【核心要求】
1. 目标字数{word_count}字，必须达标
2. 绝不允许重复内容。每500字推进一次剧情
3. 用{max(word_count//2000, 1)}个不同的场景段落来写
4. 每个场景换地点、换人物、换冲突
5. 禁止Markdown格式（禁止**加粗**、*斜体*等标记），纯文本输出

第{chapter_num}章大纲: {chapter_outline}

直接输出小说正文，不要解释。"""
            
            # 限制max_tokens避免超时(中文字约1.5token/字)
            retry_tokens = min(word_count * 2, 16384)
            try:
                new_content = self.ai.chat(
                    [{"role": "user", "content": f"创作第{chapter_num}章：{chapter_title}，{word_count}字"}],
                    system=strict_system, max_tokens=retry_tokens
                )
            except Exception as e:
                self.log(f"第{chapter_num}章重试{retry+1}失败: {e}")
                new_content = None
                # 如果是最后一次重试失败，保留原内容
                if retry == max_retries - 1:
                    self.log(f"第{chapter_num}章重试耗尽，保留原内容")
                    break
            if new_content:
                content = new_content
        
        self.log(f"第{chapter_num}章生成完成 ({len(content) if content else 0}字)")
        return content or f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"
    
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
        
        # 检测相似段落 — BUG-3修复: 使用字符级4-gram匹配（中文无空格分词）
        def _char_ngrams(text, n=4):
            """提取字符级n-gram集合"""
            return set(text[i:i+n] for i in range(max(0, len(text)-n+1)))
        
        similar_count = 0
        for i in range(len(paragraphs)):
            for j in range(i + 1, min(i + 5, len(paragraphs))):
                if len(paragraphs[i]) > 40 and len(paragraphs[j]) > 40:
                    ngrams_i = _char_ngrams(paragraphs[i][:100])
                    ngrams_j = _char_ngrams(paragraphs[j][:100])
                    if ngrams_i and ngrams_j:
                        overlap = len(ngrams_i & ngrams_j) / min(len(ngrams_i), len(ngrams_j))
                        if overlap > 0.5:
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
        # ERR-2修复: 验证settings不为空或None
        if not settings or (isinstance(settings, dict) and len(settings) == 0):
            self.log("[警告] 世界观生成失败，使用空设定")
            settings = {"raw": response, "world": {}, "rules": {}, "factions": {}}
        self.memory.save_settings(settings)
        return settings
    
    def generate_characters(self, genre: str, title: str, count: int = None) -> dict:
        """生成角色 - 根据小说规模智能确定角色数量"""
        if count is None:
            chapter_count = self.memory.get_meta("chapter_count", 20)
            if chapter_count <= 20: count = 3
            elif chapter_count <= 50: count = 5
            else: count = 8
        
        # 🔒 读取已锁定的主角名，确保每次生成都用同一个名字
        protagonist = self.memory.get_meta("protagonist", "")
        
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
    "goal": "单一字符串，表示角色核心目标（如：成为最强武者），禁止使用数组！"
  }}
}}

严格要求：
- 每个角色必须有独特的人格和背景
- goal 必须是普通字符串，绝对不能是 [] 数组！
- 所有键名必须用英文双引号，冒号用英文半角 ":"
- 属性值合理分布（不是所有角色同属性）
- 确保 JSON 语法完全正确，可被 json.loads 解析"""

        # 🔒 主角名锁定：如果已有主角名，强制AI使用该名字
        if protagonist:
            system += f"\n\n【重要】主角名已锁定为「{protagonist}」，必须使用此名字，不可更改！"
        
        prompt = f"小说类型：{genre}\n标题：{title}\n创建{count}个角色，每个角色有完整的性格、背景、武器、技能"
        if protagonist:
            prompt = f"主角名：{protagonist}\n" + prompt
        
        # 重试3次，处理AI返回空响应的情况
        response = None
        for attempt in range(3):
            response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=12000)
            if response and len(response) > 50:
                break
            if attempt < 2:
                self.log(f"[角色] AI响应较慢，正在重试({attempt+1}/3)，请稍候...")
                time.sleep(3)
        
        chars = self._parse_json_response(response, None)
        
        # 🔧 关键修复：即使解析成功，如果角色数量不足也需要回退
        parsed_count = len(chars) if isinstance(chars, dict) else 0
        if parsed_count > 0 and parsed_count < count:
            self.log(f"[角色] 初步解析仅获得 {parsed_count}/{count} 个角色，尝试从原始响应补充...")
        
        # 多层回退：如果标准解析失败（或数量不足），尝试从原始响应中提取
        need_extract = (chars is None or not isinstance(chars, dict) or len(chars) == 0 or
                        (isinstance(chars, dict) and len(chars) < count))
        if need_extract:
            self.log(f"[角色] 解析遇到问题 (当前{len(chars) if chars else 0}/{count})，尝试从原始响应恢复...")
            if response:
                self.log(f"[调试] 响应长度: {len(response)} 字符")
                self.log(f"[调试] 响应前200字: {response[:200]}")
            extracted = self._extract_characters_from_raw(response)
            if extracted:
                # 合并而非替换: 保留已解析的，补充新提取的
                if chars and isinstance(chars, dict):
                    for k, v in extracted.items():
                        if k not in chars:
                            chars[k] = v
                else:
                    chars = extracted
                self.log(f"[角色] 从原始响应补充了 {len(extracted)} 个角色 (总计 {len(chars)})")
        
        # Strategy 5: 如果还是失败，尝试逐行提取角色名并创建基础角色
        if not chars or len(chars) == 0:
            self.log(f"[角色] 尝试最终回退策略: 从响应中提取角色名...")
            if response:
                import re as _char_re
                name_patterns = _char_re.findall(r'"([^"]{1,6})"\s*:\s*\{', response)
                if name_patterns:
                    g = genre; t = title
                    for name in name_patterns[:count]:
                        if name not in ['gender','age','category','faction','personality',
                                       'background','appearance','weapon','attributes',
                                       'skill_suggestions','goal','relationship_to_main',
                                       'title','summary','key_events']:
                            if name not in (chars or {}):
                                chars[name] = {
                                    "gender": "未知", "age": 25, "category": "关键人物",
                                    "faction": "中立", "personality": "待展开",
                                    "background": f"《{t}》中的重要角色", "appearance": "待展开",
                                    "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                                    "skill_suggestions": [], "attributes": {"力量":50,"敏捷":50,"智力":50,"体力":50,"魅力":50},
                                    "relationship_to_main": "待展开", "goal": "待展开"
                                }
                    if chars:
                        self.log(f"[角色] 最终回退创建了 {len(chars)} 个基础角色")
        elif isinstance(chars, dict) and len(chars) < count:
            # 补充: 已解析到部分角色但不足count，也从响应中提取角色名做基础角色
            self.log(f"[角色] 角色不足 (当前{len(chars)}/{count})，从响应补充基础角色...")
            if response:
                import re as _char_re2
                name_patterns = _char_re2.findall(r'"([^"]{1,6})"\s*:\s*\{', response)
                existing = set(chars.keys())
                field_names = {'gender','age','category','faction','personality','background',
                              'appearance','weapon','attributes','skill_suggestions','goal',
                              'relationship_to_main','title','summary','key_events','name',
                              'level','hp','mp','exp','stats'}
                g = genre; t = title
                added = 0
                for name in name_patterns:
                    if name not in existing and name not in field_names and added < count - len(chars):
                        chars[name] = {
                            "gender": "未知", "age": 25, "category": "配角",
                            "faction": "中立", "personality": "待AI展开",
                            "background": f"《{t}》中的{name}", "appearance": "待AI展开",
                            "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                            "skill_suggestions": [], "attributes": {"力量":50,"敏捷":50,"智力":50,"体力":50,"魅力":50},
                            "relationship_to_main": f"与主角{protagonist or '林风'}的关系待展开", "goal": "待AI展开"
                        }
                        existing.add(name)
                        added += 1
                if added > 0:
                    self.log(f"[角色] 补充了 {added} 个基础角色 (总计 {len(chars)}/{count})")
        
        if not chars or not isinstance(chars, dict):
            self.log("[角色] AI未能生成有效角色数据，将使用已有角色")
            return {}
        
        # 过滤掉 raw 键（_parse_json_response 的回退值）
        chars = {k: v for k, v in chars.items() if k != "raw" and isinstance(v, dict)}
        if not chars:
            self.log("[角色] 未能提取到有效角色，将使用已有角色")
            return {}
        
        # 保存角色文件
        saved_count = 0
        chars_dir = self.memory.novel_dir / "characters" if hasattr(self.memory, 'novel_dir') else None
        if chars_dir is None:
            chars_dir = self.memory.memory_dir.parent / "characters"
        chars_dir.mkdir(exist_ok=True)
        
        for name, info in chars.items():
            if isinstance(info, dict):
                char_data = {"name": name, **info}
                # API-3修复: 文件名安全处理（Windows不允许 / \ : * ? " < > |）
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
                with open(chars_dir / f"{safe_name}.json", 'w', encoding='utf-8') as f:
                    json.dump(char_data, f, indent=2, ensure_ascii=False)
                saved_count += 1
        
        if saved_count > 0:
            self.log(f"[角色] 已保存 {saved_count} 个角色到 {chars_dir}")
        else:
            self.log("[角色] 警告：未能保存任何角色文件！")
        
        # 返回前更新 self.memory 中的角色缓存
        self.memory.save_characters(chars)
        
        return chars
    
    def generate_outline(self, genre: str, title: str, chapter_count: int, concept: str = "", 
                          total_chapters: int = None) -> list:
        """生成大纲 - 智能分批+故事弧线
        
        策略:
        - 小量(<20章): 一次生成
        - 中量(20-100章): 按故事弧线分批(开端/发展/高潮/结局)
        - 大量(100+章): 生成全局弧线+分批详细大纲
        
        total_chapters: 小说真实总章数，用于计算故事阶段。默认=chapter_count
        """
        if total_chapters is None:
            total_chapters = chapter_count
        
        if chapter_count <= 20:
            return self._generate_outline_batch(genre, title, chapter_count, 1, concept)
        
        # 分批策略: 每批15章
        batch_size = 15
        all_outline = []
        total_batches = (chapter_count + batch_size - 1) // batch_size
        
        # 先规划故事弧线 (基于真实总章数)
        if total_chapters > 50:
            arc_plan = self._plan_story_arcs(genre, title, total_chapters, concept)
        else:
            arc_plan = ""
        
        for batch_idx in range(total_batches):
            start_ch = batch_idx * batch_size + 1
            batch_count = min(batch_size, chapter_count - start_ch + 1)
            
            # 构建上下文
            ctx = concept[:200] if concept else ""
            if all_outline:
                recent = all_outline[-3:]
                ctx = "前文概要:\n" + "\n".join(
                    f"第{r.get('chapter','?')}章 {r.get('title','?')}: {str(r.get('summary',''))[:40]}"
                    for r in recent
                )
            
            # 弧线位置提示 — 基于真实总章数 total_chapters
            progress_pct = (start_ch - 1) / total_chapters * 100
            if total_chapters > 100 and start_ch <= total_chapters * 0.05:
                phase = f"【故事开端】建立世界观，引入主角和核心矛盾 (全书共{total_chapters}章，当前仅为开头)"
            elif progress_pct < 15:
                phase = "【故事开端】建立世界观，引入主角和核心矛盾"
            elif progress_pct < 40:
                phase = "【发展阶段】展开情节，深化冲突，发展角色关系"
            elif progress_pct < 70:
                phase = "【高潮推进】关键冲突升级，重大转折，角色成长"
            elif progress_pct < 90:
                phase = "【高潮巅峰】最终决战或最大冲突"
            else:
                phase = "【结局收束】收尾主线，交代结局，主题升华"
            
            if arc_plan:
                phase += f"\n全局弧线规划: {arc_plan[:200]}"
            
            self.log(f"[大纲] 第{start_ch}-{start_ch+batch_count-1}章 ({batch_idx+1}/{total_batches}) {phase[:20]}")
            
            batch_outline = self._generate_outline_batch(
                genre, title, batch_count, start_ch, 
                f"{ctx}\n创作阶段: {phase}\n剩余{chapter_count-start_ch+1-batch_count}章"
            )
            all_outline.extend(batch_outline)
        
        return all_outline
    
    def _plan_story_arcs(self, genre: str, title: str, chapter_count: int, concept: str) -> str:
        """为长篇规划故事弧线"""
        system = f"你是专业故事架构师。为{chapter_count}章长篇规划故事弧线。输出简洁文本。"
        prompt = f"类型:{genre} 标题:{title} 概念:{concept[:200]}\n为{chapter_count}章规划: 1.开端(前15%) 2.发展(15-70%) 3.高潮(70-90%) 4.结局(90-100%)。每段50字。"
        try:
            response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=500)
            return response or ""
        except Exception as e:
            self.log(f"[故事弧线规划] 失败: {e}")
            return ""
    
    def _generate_outline_batch(self, genre: str, title: str, count: int, start_num: int, concept: str = "") -> list:
        """生成一批大纲 - 确保每章都有实质性内容"""
        # 🔒 读取锁定的主角名
        protagonist = self.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n【重要】本小说主角名为「{protagonist}」，所有章节大纲必须围绕「{protagonist}」展开！"
        
        system = f"""你是专业小说大纲师。为{count}章生成大纲。每章必须完整。
输出JSON数组，每项包含: chapter(章节号), title(章节标题10字内), summary(内容概要80-150字)。
禁止"待规划"或空摘要。关键：摘要要具体，包含本章独特事件。{protagonist_hint}"""
        
        prompt = f"类型:{genre} 标题:{title} 从第{start_num}章起{count}章。{concept}"
        
        # 增加max_tokens: 每章约60 tokens，加上buffer
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, 
                              max_tokens=max(count * 150, 4000))
        outline = self._parse_json_response(response, [], is_list=True)
        
        if not outline or len(outline) < count:
            # 填充缺失的章节 — 使用"待规划"标记，让生成器动态填充
            existing = {o["chapter"] for o in outline if "chapter" in o} if outline else set()
            for i in range(count):
                ch_num = start_num + i
                if ch_num not in existing:
                    outline.append({
                        "chapter": ch_num, 
                        "title": f"第{ch_num}章",
                        "summary": "待规划"
                    })
        
        # 确保有序
        outline.sort(key=lambda x: x.get("chapter", 0))
        return outline
    
    def generate_outline_continuation(self, genre: str, title: str, 
                                      add_count: int, global_context: str,
                                      current_count: int) -> list:
        """续写大纲 - 在已有章节基础上生成新章"""
        self.log(f"[智能体] 基于已有{current_count}章，续写{add_count}章大纲...")
        
        # 🔒 读取锁定的主角名
        protagonist = self.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n【重要】本小说主角名为「{protagonist}」，所有章节必须围绕「{protagonist}」展开！"
        
        context = global_context[:1000] if global_context else ""
        system = (
            f"你是专业小说大纲规划师。已有{current_count}章内容。\n"
            f"历史摘要：{context}\n\n"
            f"请在已有章节基础上，规划{add_count}章新内容实现故事续写。\n"
            f"章节从第{current_count+1}章开始编号。\n"
            f"必须延续已有剧情、保持风格。{protagonist_hint}\n"
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
        keywords = [k.strip() for k in (kw or "").split(",") if k.strip()]
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

变化包括正面和负面的。没有变化就输出{{"updates":[]}}。
**必须检测所有出现的角色，不止主角。只输出JSON，不要其他文字！**"""
            
            # 增加采样字数到3000字，max_tokens到1200
            sample = content[:3000] if len(content) > 3000 else content
            response = self.ai.chat(
                [{"role": "user", "content": f"章节摘要: {summary}\n内容片段: {sample}"}],
                system=system, max_tokens=1200
            )
            if not response:
                return
            
            import re
            data = None
            
            # Strategy 1: 直接正则提取JSON
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                json_str = match.group()
                # 修复常见JSON错误
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            
            # Strategy 2: 移除markdown代码块后重试
            if not data:
                cleaned = response.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                match = re.search(r'\{[\s\S]*\}', cleaned.strip())
                if match:
                    try:
                        data = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass
            
            if not data:
                self.log(f"[角色成长] JSON解析失败，跳过本章")
                return
            
            # 保存到记忆
            changes = 0
            if data.get("updates"):
                for u in data["updates"]:
                    if isinstance(u, dict) and u.get("name"):
                        self.memory.add_event(chapter_num, 
                            f"角色变化: {u['name']} {u.get('change','')} ({u.get('reason','')})",
                            "character_growth")
                        changes += 1
            
            if data.get("skills_learned"):
                for s in data["skills_learned"]:
                    if isinstance(s, dict) and s.get("name"):
                        self.memory.add_event(chapter_num,
                            f"技能领悟: {s['name']} 学会 {s.get('skill','')}",
                            "skill_learn")
                        changes += 1
            
            if data.get("relationship_changes"):
                for r in data["relationship_changes"]:
                    if isinstance(r, dict) and r.get("name1"):
                        self.memory.add_event(chapter_num,
                            f"关系变化: {r['name1']}与{r.get('name2','')} {r.get('old','')}→{r.get('new','')}",
                            "relationship_change")
                        changes += 1
            
            if data.get("items_gained"):
                for item in data["items_gained"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(chapter_num,
                            f"获得物品: {item['name']} 获得 {item.get('item','')}",
                            "item_gain")
            
            if data.get("items_lost"):
                for item in data["items_lost"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(chapter_num,
                            f"失去物品: {item['name']} 失去 {item.get('item','')}",
                            "item_loss")
            
            if data.get("new_allies"):
                for name in data["new_allies"]:
                    if isinstance(name, str) and name:
                        self.memory.add_event(chapter_num,
                            f"新盟友: {name}", "new_ally")
            
            if data.get("new_enemies"):
                for name in data["new_enemies"]:
                    if isinstance(name, str) and name:
                        self.memory.add_event(chapter_num,
                            f"新敌人: {name}", "new_enemy")
            
            if data.get("deaths"):
                for name in data["deaths"]:
                    if isinstance(name, str) and name:
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
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
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
        return response or ""
    
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
        return response or ""
    
    # ===== 工具方法 =====
    
    @staticmethod
    def _extract_characters_from_raw(raw_text: str) -> dict:
        """从AI原始响应中尽最大努力提取角色数据（支持截断JSON）"""
        chars = {}
        if not raw_text or not isinstance(raw_text, str):
            return chars
        text = raw_text.replace('```json', '').replace('```', '').strip()
        text = text.replace('\uff1a', ':')
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        
        depth = 0
        key_buffer = ""
        obj_start = -1
        in_string = False
        escape = False
        
        i = 0
        while i < len(text):
            ch = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if ch == '\\':
                escape = True
                i += 1
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                if not in_string and depth == 0:
                    # 读完键
                    if obj_start < 0:
                        key_buffer = ""
                        for j in range(i-1, -1, -1):
                            if text[j] == '"':
                                break
                            key_buffer = text[j] + key_buffer
                i += 1
                continue
            if in_string:
                i += 1
                continue
            if ch == '{':
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and key_buffer and obj_start >= 0:
                    try:
                        obj = json.loads(text[obj_start:i+1])
                        chars[key_buffer] = obj
                    except (json.JSONDecodeError, ValueError):
                        pass
                    key_buffer = ""
                    obj_start = -1
            i += 1
        
        # 处理截断的JSON：最后一个对象没有闭合 }
        if key_buffer and obj_start >= 0 and depth > 0:
            partial = text[obj_start:]
            # 尝试补全：关闭所有未闭合的括号
            for closing in ['"]', '}', '}}']:
                try:
                    fixed = partial + closing
                    obj = json.loads(fixed)
                    chars[key_buffer] = obj
                    break
                except (json.JSONDecodeError, ValueError):
                    continue
            # 如果还是失败，尝试截取到最后一个完整字段
            if key_buffer not in chars:
                # 找到最后一个完整的 "key": "value" 对
                last_complete = max(partial.rfind('",'), partial.rfind("'}"))
                if last_complete > 0:
                    truncated = partial[:last_complete+1] + '}'
                    try:
                        obj = json.loads(truncated)
                        chars[key_buffer] = obj
                    except (json.JSONDecodeError, ValueError):
                        pass
        
        return chars
    
    @staticmethod
    def _parse_json_response(response: str, default: Any, is_list: bool = False) -> Any:
        """解析AI返回的JSON — 多层回退，极度容错"""
        if not response or not isinstance(response, str):
            return default
        
        text = response.strip()
        marker = "[" if is_list else "{"
        end_marker = "]" if is_list else "}"
        
        # 策略列表（按优先级）
        strategies = []
        
        # Strategy 1: 直接查找标记提取
        start = text.find(marker)
        end = text.rfind(end_marker) + 1
        if start >= 0 and end > start:
            strategies.append(text[start:end])
        
        # Strategy 2: 清理 markdown 代码块后再提取
        clean = text.replace('```json', '').replace('```', '')
        start = clean.find(marker)
        end = clean.rfind(end_marker) + 1
        if start >= 0 and end > start:
            strategies.append(clean[start:end])
        
        # Strategy 3: 修复全角标点 + 各种常见 AI 错误
        for raw_text in list(strategies):
            fixed = raw_text
            # 全角标点 → 半角（必须在阵列修复前处理）
            fixed = fixed.replace('\uff1a', ':')
            fixed = fixed.replace('\uff0c', ',')
            fixed = fixed.replace('\u201c', "'").replace('\u201d', "'")
            fixed = fixed.replace('\u2018', "'").replace('\u2019', "'")
            # 连续冒号: "key":: → "key": (必须在阵列修复前处理)
            fixed = re.sub(r'("\w+")\s*:{2,}', r'\1:', fixed)
            # 字符串值中的数组误写: "goal":["a","b"] → "goal":"a; b"
            # 先处理有闭合]的
            fixed = re.sub(
                r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
                lambda m: m.group(1) + ': "' + '; '.join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
                fixed
            )
            # 处理未闭合的数组: "goal":[ "a", "b" ...无闭合]
            while True:
                m = re.search(r'"goal"\s*:\s*\[', fixed)
                if not m:
                    break
                pos = m.start()
                bstart = m.end() - 1
                depth = 0
                for j in range(bstart, len(fixed)):
                    if fixed[j] == '[': depth += 1
                    elif fixed[j] == ']':
                        depth -= 1
                        if depth == 0:
                            arr = fixed[bstart+1:j]
                            items = re.findall(r'"([^"]*)"', arr)
                            joined = '; '.join(items)
                            fixed = fixed[:pos] + f'"goal": "{joined}"' + fixed[j+1:]
                            break
                else:
                    break  # no closing ], skip
            strategies.append(fixed)
        
        # 依次尝试每个策略
        for s in strategies:
            try:
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                continue
        
        # Strategy 4: 尝试补全截断的JSON（逐步关闭括号）
        for s in strategies:
            # 先尝试关闭未闭合的字符串，再关闭括号
            for suffix in [
                '"}',       # 关闭字符串+对象
                '"}]',      # 关闭字符串+对象+数组
                '"}}',      # 关闭字符串+两层对象
                '"}]}}',    # 关闭字符串+对象+数组+两层对象
                '"]}}}',    # 关闭字符串+数组+三层对象
                '}}}',      # 关闭三层对象
                '"}\n}',    # 关闭字符串+对象(带换行)
                '"}\n}]',   # 关闭字符串+对象+数组(带换行)
            ]:
                try:
                    return json.loads(s + suffix)
                except (json.JSONDecodeError, ValueError):
                    continue
        
        # Strategy 5: 提取已完成的完整角色对象（逐个提取）
        for s in strategies:
            chars = {}
            # 找所有 "name": { ... } 模式
            for m in re.finditer(r'"([^"]+)"\s*:\s*\{', s):
                name = m.group(1)
                if name in ('raw', 'weapon', 'attributes', 'skill_suggestions'):
                    continue
                brace_start = m.end() - 1
                depth = 0
                for j in range(brace_start, len(s)):
                    if s[j] == '{': depth += 1
                    elif s[j] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads(s[brace_start:j+1])
                                chars[name] = obj
                            except (json.JSONDecodeError, ValueError):
                                pass
                            break
            if chars:
                # 🔧 BUG-5修复: is_list=True时返回list而非dict
                if is_list:
                    return list(chars.values())
                return chars
        
        return default
    
    def _generate_long_chapter(self, chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending="") -> str:
        """分段生成长章节 - 确保每章结尾完整自然"""
        seg_size = 2000
        part_count = max((word_count + seg_size - 1) // seg_size, 1)
        part_count = min(part_count, 8)
        
        # 标题处理
        clean_title = chapter_title or ""
        if clean_title.startswith("第") and "章" in clean_title[:6]:
            clean_title = f"第{chapter_num}章"
        else:
            clean_title = f"第{chapter_num}章：{clean_title}"
        title_line = f"# {clean_title}\n\n"
        
        parts = []
        for i in range(part_count):
            is_last = (i == part_count - 1)
            self.log(f"[Writer] 第{chapter_num}章 第{i+1}/{part_count}段...")
            
            prev_text = ''.join(parts)
            if i == 0:
                # 第一段：使用传入的前一章结尾（未被压缩）
                if not prev_ending and context and "【前一章" in str(context):
                    import re as _re
                    m = _re.search(r'【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)', str(context), _re.DOTALL)
                    if m:
                        prev_ending = m.group(1).strip()[-800:]
                if prev_ending:
                    part_prompt = f"【前一章结尾 — 必须紧接以下内容】\n{prev_ending}\n\n---\n\n创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文（必须紧接前文）："
                else:
                    part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文："
            elif is_last:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                part_prompt = f"紧接上文继续写。上文结尾：{last_200}\n这是本章最后一段，请推进剧情约{seg_size}字并给出自然完整的段落结尾。严禁重复。"
            else:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                part_prompt = f"紧接上文继续写。上文结尾：{last_200}\n要求：继续推进剧情约{seg_size}字，严禁重复。"
            
            for attempt in range(3):
                try:
                    # 🔒 读取锁定的主角名
                    protagonist = self.memory.get_meta("protagonist", "")
                    protagonist_hint = f"\n【重要】主角名为「{protagonist}」，禁止更换！" if protagonist else ""
                    
                    response = self.ai.chat(
                        [{"role": "user", "content": part_prompt}],
                        system=f"严密续写，绝不重复。每段给出自然结尾。禁止Markdown格式。{protagonist_hint}\n{context[:1500] if context else ''}", 
                        max_tokens=4096
                    )
                    if response and len(response) > 100:
                        # 去除AI生成的标题
                        lines = response.split('\n', 2)
                        clean = []
                        for line in lines:
                            stripped = line.strip()
                            if (stripped.startswith('#') or (stripped.startswith('第') and '章' in stripped[:10])) and not clean:
                                continue
                            clean.append(line)
                        response = '\n'.join(clean)
                        parts.append(response)
                        break
                except Exception as e:
                    self.log(f"[Writer] 第{chapter_num}章第{i+1}段 重试{attempt+1}: {e}")
                    if attempt == 2:
                        return title_line + ("\n\n".join(parts) if parts else "（生成失败）")
        
        result = title_line + ("\n\n".join(parts) if parts else "（生成失败）")
        
        # 末段完整性检查：如果结尾没有句号/感叹号/问号等，AI补全
        if parts and len(result) > 500:
            # 扩大检测范围：检查最后200字符，去除空白后判断
            last_text = result[-200:].strip()
            # 移除尾部空白、换行、引号等非实质字符
            last_meaningful = last_text.rstrip('\n\r \t\'\"》）」】')
            if last_meaningful:
                last_char = last_meaningful[-1]
                endings = {'。', '！', '？', '…', '"', '」', '】', '—', '.', '!', '?', '~', '…'}
                if last_char not in endings:
                    self.log(f"[Writer] 第{chapter_num}章末段不完整，尝试补全...")
                    try:
                        # 取最后500字作为上下文，让AI更好地理解语境
                        context = result[-500:]
                        completion = self.ai.chat(
                            [{"role": "user", "content": f"以下是一段未完成的小说段落，请补充一个自然的收尾（20-60字）：\n{context}"}],
                            system="你是作家。续写上面的段落，补充一个自然的收尾。只输出补全文字，不要重复已有内容。",
                            max_tokens=200
                        )
                        if completion and len(completion) > 5:
                            # 去重：检查补全内容是否与已有内容重复
                            completion = completion.strip()
                            # 移除可能的重复前缀
                            if completion[:10] in result[-50:]:
                                completion = completion[10:]
                            # 确保补全内容不为空且不重复
                            if completion and completion not in result:
                                result += completion
                    except Exception as e:
                        self.log(f"[长章节末段补全] 失败: {e}")
        
        return result
