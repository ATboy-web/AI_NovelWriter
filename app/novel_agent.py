"""
小说创作智能体模块 - 参考AutoGen多智能体协作架构 v3.0

改进 (Hello-Agents 参考):
- 多Agent专业化协作 (PlotDesigner/WorldBuilder/Writer/Reviewer/Editor)
- 标准化工具系统 (ToolRegistry + Tool协议)
- 动态上下文工程 (根据写作阶段智能分配)
- 标准化通信协议 (AgentMessage)
"""

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

import json
import re
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List

from .agent_orchestrator import AgentOrchestrator
from .ai_client import AIClient
from .config import AppConfig
from .memory_manager import CharacterDataGuardError, MemoryManager
from .parsing import parse_characters_payload, parse_json_response
from .storage import atomic_write_json, safe_filename
from .token_estimator import chars_for_context_window
from .usage_tracker import task_tracker

# 诊断日志
try:
    from .diagnostic_logger import get_logger

    _diag = get_logger()
except Exception:
    _diag = None


def _diag_logger():
    """取当前诊断日志实例。

    **不要**在别处缓存 `_diag` 的返回值来记新增的日志：模块级 `_diag` 是导入那一刻
    的单例快照，而 `reset_logger()`（测试隔离、目录切换）会把全局单例换掉，
    快照就会指向**旧目录** —— 现象是"日志明明该写却没写"，且只在跑测试时才出现。
    `_diag` 保留是为了兼容既有调用点；新增的段级归因走这个函数。
    """
    if _diag is None:
        return None
    try:
        return get_logger()
    except Exception:
        return _diag


class _PhaseTimer:
    """单章生成的段级耗时归因。

    为什么需要它：单章生成要发 **3–9 次网络往返**（`_plot_designer_analyze` 1 次、
    `_writer_generate` 1 次、`_reviewer_evaluate` 每轮 1 次、`_writer_revise` 不达标才发），
    而本地计算量与这些往返相比可以忽略。于是"这一章慢"**必定**能拆成"哪个 Agent 慢"，
    但没有分段数据就只能猜 —— 这也是先做观测、后做优化的原因。

    用累加而不是记录每次调用，是因为"第 2 轮审校"单独看没有意义，
    有用的是"审校总共占了这一章的多少毫秒"。逐轮明细另外记在 `calls` 里备查。

    ⚠️ 刻意不做的事：不 import `ai_client` / 不读全局状态 / 不抛异常。
    它只做算术，唯一的输出是给 `chapter_event` 的一组数字。
    """

    __slots__ = ("_t0", "total_ms", "phases", "calls")

    def __init__(self):
        self._t0 = time.perf_counter()
        self.total_ms = 0.0
        self.phases: Dict[str, float] = {}
        self.calls: List[Dict[str, Any]] = []

    def phase(self, name: str, started_at: float) -> float:
        """记录一段耗时（毫秒）并累加进同名阶段。

        用 `perf_counter` 而非 `time.time`：后者会被系统时钟调整影响，
        而我们要的是"这一段实际过了多久"。
        """
        elapsed = (time.perf_counter() - started_at) * 1000
        self.phases[name] = self.phases.get(name, 0.0) + elapsed
        self.calls.append({"phase": name, "ms": round(elapsed, 2)})
        return elapsed

    def breakdown(self) -> Dict[str, float]:
        """各阶段耗时（毫秒，四舍五入到 0.01）。"""
        return {k: round(v, 2) for k, v in self.phases.items()}

    def summary(self) -> Dict[str, Any]:
        """可日志化的汇总：总时长 + 各段 + 网络往返次数 + 未归因余量。"""
        self.total_ms = (time.perf_counter() - self._t0) * 1000
        accounted = sum(self.phases.values())
        return {
            "total_ms": round(self.total_ms, 2),
            "phases_ms": self.breakdown(),
            "round_trips": sum(1 for c in self.calls if c["phase"] in _NETWORK_PHASES),
            "unaccounted_ms": round(self.total_ms - accounted, 2),
            "calls": self.calls,
        }


#: 交付给下游消费者的关键阶段名（顺序即执行顺序，也是"最慢在哪"的阅读顺序）。
#: 之所以单独列出来，是因为 `novel_agent` 与 `generation_ui` 要对同一组名字达成一致 ——
#: 名字写两处必然漂移，所以由这里导出。
PHASE_PLOT = "plot_design"
PHASE_CONTEXT = "context"
PHASE_WORLD = "world_build"
PHASE_WRITE = "write"
PHASE_REVIEW = "review"
PHASE_REVISE = "revise"

#: 真正**会发网络请求**的阶段。数错这个数会直接误导"该优化哪里"。
#: 实测依据（AST 静态统计 `ai.chat()` 调用点）：
#:   plot_design / write / review / revise 各 1 次；`world_build` **0 次**
#:   （`_world_builder_build` 只读本地 settings 就返回，连 `ai` 都不碰）；
#:   `context` 也是纯本地组装。
#: 这正是"5 个 Agent"听起来像 5 次往返、实际不是的原因 —— 别按 Agent 数量推断。
_NETWORK_PHASES = frozenset({PHASE_PLOT, PHASE_WRITE, PHASE_REVIEW, PHASE_REVISE})


# ===== 定稿辅助调用的输出校验 =====
# 为什么需要：`ai_client._finalize_text` 有一条**刻意的**兜底 —— 思考模式把 token
# 预算耗尽时（`finish_reason == "length"` 且 `content` 为空），它**返回
# `reasoning_content`** 而不是报错。对"生成正文"这是对的（有分析总比崩了好），
# 但对**结果会被原样落盘**的调用（摘要、关键词、全局摘要）就是污染源。
#
# 实测事故（2026-09-17《快速统治》第 1 章）：
#   摘要调用用 `max_tokens=1000`，而 `providers/reasoning.py` 的
#   `THINKING_MIN_TOKENS` 恰好也是 **1000**，且判据是 `max_tokens < THINKING_MIN_TOKENS`
#   （**严格小于**）⇒ `1000 < 1000` 为假 ⇒ 思考模式**没被禁用**，但预算只够思考、
#   不够输出 ⇒ `content` 为空 ⇒ 兜底返回 reasoning ⇒ 摘要文件里存进了
#   **1782 字的推理原文**（含 "Let's count…" 这类自我计字），并被当作 `plot` 类型
#   灌进记忆库。日志全程显示"已保存第1章摘要"，**没有任何异常**。
#
# 所以三道防线一起上：显式关思考 → 给足预算 → 再校验返回内容。

#: 摘要类返回的长度上限。提示词要求 100–200 字，给足余量后仍超出即视为异常。
_SUMMARY_MAX_CHARS = 600

#: 思维链特征词。命中**开头 300 字**内任意一个，就认为返回的是推理过程而非成品。
#: 只扫开头是因为成品摘要不会以"我们需要回答用户"这类话起头，
#: 而推理过程几乎必然以它起头；扫全文反而会误伤正当引用。
_COT_MARKERS = (
    "我们需要回答",
    "用户要求",
    "用户之前给",
    "用户给了一个任务",
    "Let's ",
    "Let me ",
    "Count:",
    "应提取关键剧情",
    "通常字数",
    "要计数",
    "Need ensure",
    "首先，我需要",
    "让我先",
)


def _looks_like_chain_of_thought(text: str) -> bool:
    """判断返回文本是否像模型的**推理过程**而不是成品。

    用于"结果会被原样落盘"的调用：命中即弃用，退回安全的降级值。
    判据取"超长 OR 命中特征词"，两者都宁松勿严 —— 因为一旦把推理过程落盘，
    它会继续污染记忆库并回灌到后续章节，代价远大于偶尔弃用一段合格摘要。
    """
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > _SUMMARY_MAX_CHARS:
        return True
    return any(marker in t[:300] for marker in _COT_MARKERS)


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
            "timestamp": self.timestamp,
        }


# ===== 标准化工具系统 (参考 MCP Tool协议) =====


class Tool:
    """标准化工具定义"""

    def __init__(
        self, name: str, description: str, func: Callable, input_schema: Dict = None, category: str = "general"
    ):
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
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "input_schema": tool.input_schema,
                }
            )
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

        # P-04：最近一次生成章节的真实质量评分（None = 未知/非生成流程）。
        # `generate_chapter_v3` 写、`finalize_chapter` 读，作为自我学习的真信号。
        self.last_chapter_quality: int | None = None

        # 线程锁保护共享列表
        self._log_lock = threading.Lock()

        # 启用优化器模块
        self.orchestrator = AgentOrchestrator(ai_client, log_callback)

        # 加载写作技能数据（如果存在）
        try:
            from .writing_skills import writing_skill_manager

            if memory and hasattr(memory, "novel_dir"):
                skills_dir = str(memory.novel_dir / "writing_skills")
                writing_skill_manager.load_all(skills_dir)
                self.log("[写作技能] 已加载历史数据")
        except Exception as e:
            self.log(f"[写作技能] 加载失败: {e}")

        # 工具注册中心（参考MCP协议）
        self.tools = ToolRegistry()
        self._register_tools()

        self.log("[智能体] Hello-Agents架构 v3.0: 5Agent+工具系统+动态上下文+标准协议")

    def _get_writing_style_prompt(self) -> str:
        """获取写作风格提示词（基于写作技能模块的配置）"""
        try:
            from .writing_skills import writing_skill_manager

            config = writing_skill_manager.style_config

            style_parts = []

            # 描写细腻度
            if config.descriptiveness >= 8:
                style_parts.append("描写要华丽细腻，注重细节和感官描写")
            elif config.descriptiveness <= 3:
                style_parts.append("描写要简洁有力，避免过多修饰")

            # 对话比例
            if config.dialogue_ratio >= 8:
                style_parts.append("以对话驱动情节，对话占比要高")
            elif config.dialogue_ratio <= 3:
                style_parts.append("以叙述为主，减少对话比例")

            # 节奏
            if config.pacing >= 8:
                style_parts.append("节奏要快，情节紧凑，减少铺垫")
            elif config.pacing <= 3:
                style_parts.append("节奏要慢，注重氛围营造和心理描写")

            # 情感深度
            if config.emotional_depth >= 8:
                style_parts.append("深入描写角色内心世界和情感变化")
            elif config.emotional_depth <= 3:
                style_parts.append("情感描写要克制，点到为止")

            # 动作强度
            if config.action_intensity >= 8:
                style_parts.append("战斗场面要激烈热血，动作描写要有冲击力")
            elif config.action_intensity <= 3:
                style_parts.append("战斗场面要简洁，避免过度暴力描写")

            if style_parts:
                return "、".join(style_parts) + "。"
            return ""
        except Exception as e:
            self.log(f"[写作风格] 获取失败: {e}")
            return ""

    def _register_tools(self):
        """注册标准化工具"""
        self.tools.register(
            Tool(
                "detect_scenes",
                "检测名场面",
                lambda content="", chapter_num=0: self.memory.add_event(
                    chapter_num, f"场景检测: {content[:50]}", "scene"
                ),
                category="writer",
            )
        )
        self.tools.register(
            Tool(
                "check_consistency",
                "检查一致性",
                lambda content="": f"一致性检查完成, 内容长度:{len(content)}",
                category="reviewer",
            )
        )
        self.tools.register(
            Tool(
                "generate_summary",
                "生成摘要",
                lambda chapter_num=0, content="": self.memory.get_chapter_summary(chapter_num) or "无",
                category="editor",
            )
        )
        self.tools.register(
            Tool(
                "get_characters",
                "获取角色列表",
                lambda: list(self.memory.get_characters().keys())[:10],
                category="general",
            )
        )
        self.tools.register(
            Tool(
                "get_outline",
                "获取章节大纲",
                lambda chapter_num=0: self.memory.get_meta("outline", {}).get(str(chapter_num), "无"),
                category="general",
            )
        )
        # 写作技能工具
        self.tools.register(
            Tool(
                "check_ai_slop",
                "检查AI写作痕迹",
                lambda content="": self._call_anti_slop_check(content),
                category="reviewer",
            )
        )
        self.tools.register(
            Tool(
                "get_kg_context",
                "获取知识图谱上下文",
                lambda character=None: self._get_knowledge_graph_context(character),
                category="writer",
            )
        )
        # MCP（v3.2）：把外部 MCP 服务器的工具挂进**同一个**注册中心。
        # 这样 "本应用的工具" 与 "MCP 服务器提供的工具" 对 Agent 是同一件事 ——
        # 而不是两条互不相通的通路（那正是"注册即遗忘"的另一种写法）。
        self.tools.register(
            Tool(
                "list_mcp_tools",
                "列出所有已启用 MCP 服务器的工具",
                lambda: self.list_mcp_tools(),
                input_schema={"type": "object", "properties": {}},
                category="general",
            )
        )
        self.tools.register(
            Tool(
                "call_mcp_tool",
                "调用一个 MCP 服务器上的工具",
                lambda server="", tool="", arguments=None: self.call_mcp_tool(server, tool, arguments),
                input_schema={
                    "type": "object",
                    "properties": {
                        "server": {"type": "string", "description": "MCP 服务器名"},
                        "tool": {"type": "string", "description": "工具名"},
                        "arguments": {"type": "object", "description": "工具参数"},
                    },
                    "required": ["server", "tool"],
                },
                category="general",
            )
        )

    # ===== MCP（v3.2）=====

    def list_mcp_tools(self) -> dict:
        """列出所有已启用 MCP 服务器的工具（生产调用点，勿删）。

        返回结构化字典而非字符串：`ToolRegistry.execute` 会把返回值放进
        `{"success": True, "result": ...}`，调用方（与 MCP 服务端）需要能再拆开。
        """
        try:
            from .mcp_system import get_mcp_manager

            manager = get_mcp_manager()
            if manager is None:
                return {"ok": False, "message": "MCP 管理器不可用", "tools": []}
            res = manager.list_all_tools()
            return {
                "ok": res.ok,
                "message": res.message,
                "tools": [t.as_dict() for t in (res.detail.get("tools") or [])],
                "failures": res.detail.get("failures") or [],
            }
        except Exception as e:  # noqa: BLE001 - MCP 不该让 Agent 崩
            self.log(f"[MCP] 列出工具失败: {e}")
            return {"ok": False, "message": f"列出 MCP 工具失败: {e}", "tools": []}

    def call_mcp_tool(self, server: str, tool: str, arguments: dict = None) -> dict:
        """调用一个 MCP 服务器上的工具（生产调用点，勿删）。"""
        try:
            from .mcp_system import get_mcp_manager

            manager = get_mcp_manager()
            if manager is None:
                return {"ok": False, "message": "MCP 管理器不可用"}
            res = manager.call_tool(server, tool, arguments)
            return {"ok": res.ok, "message": res.message, "detail": res.detail}
        except Exception as e:  # noqa: BLE001 - 同上
            self.log(f"[MCP] 调用工具失败: {e}")
            return {"ok": False, "message": f"调用 MCP 工具失败: {e}"}

    def _call_anti_slop_check(self, content: str) -> list:
        """调用写作技能进行去AI味检查"""
        try:
            from .writing_skills import writing_skill_manager

            issues = writing_skill_manager.anti_slop.check_text(content)

            # 收集所有问题
            all_issues = []
            for issue_type, issue_list in issues.items():
                if issue_list and issue_type != "suggestions":
                    all_issues.extend(issue_list[:3])  # 每类最多3个

            return all_issues
        except Exception as e:
            self.log(f"[写作技能] 去AI味检查失败: {e}")
            return []

    def _get_knowledge_graph_context(self, character: str = None) -> str:
        """从知识图谱获取上下文"""
        try:
            from .writing_skills import writing_skill_manager

            return writing_skill_manager.knowledge_graph.to_context_string(character)
        except Exception as e:
            self.log(f"[知识图谱] 获取上下文失败: {e}")
            return ""

    def _record_conversation(self, agent: str, action: str, content: str):
        """记录智能体对话 - 使用标准AgentMessage协议"""
        # BUG-2修复: 角色名到枚举的正确映射
        _ROLE_MAP = {
            "PlotDesigner": "PLOT",
            "WorldBuilder": "WORLD",
            "Writer": "WRITER",
            "Reviewer": "REVIEWER",
            "Editor": "EDITOR",
        }
        role_name = _ROLE_MAP.get(agent, "SYSTEM")
        role = MessageRole[role_name]
        msg = AgentMessage(role, action, content)
        with self._log_lock:
            self._conversation_log.append(msg)

    def _build_context(
        self, chapter_num: int, extra_context: str = "", max_chars: int = None, writing_phase: str = "writing"
    ) -> str:
        """动态上下文工程 - 根据写作阶段智能分配比例 (Hello-Agents参考)

        写作阶段:
        - opening: 开头阶段，需要更多世界/角色描述
        - writing: 常规写作，平衡分配
        - action: 动作场景，需要近章上下文
        - dialogue: 对话场景，需要角色信息
        - ending: 结尾阶段，需要全局摘要
        """
        if max_chars is None:
            # v3 §3.5(3)：换算口径收敛到 token_estimator，与 v2 的
            # `context_window // 3` **等效**（32000 → 10666，无配置 → 10000）。
            # 有意保留这个保守除数：窗口里还要装提示词模板、指令与输出预算。
            window = self.config.get("context_window", 32000) if self.config else 30000
            max_chars = chars_for_context_window(window)

        # 动态比例分配 — extra_context(前文内容)是连贯性关键，必须占大比例
        ratios = {
            "opening": {"global": 0.10, "volume": 0.05, "chars": 0.15, "recent": 0.10, "rag": 0.10, "extra": 0.50},
            "writing": {"global": 0.08, "volume": 0.07, "chars": 0.10, "recent": 0.10, "rag": 0.10, "extra": 0.55},
            "action": {"global": 0.05, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.65},
            "dialogue": {"global": 0.05, "volume": 0.05, "chars": 0.25, "recent": 0.10, "rag": 0.10, "extra": 0.45},
            "ending": {"global": 0.10, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.60},
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
            # 过滤：只保留最近活跃的角色，排除"无名小卒"中已不活跃的
            important_chars = {}
            for name in active_names:
                if name in chars:
                    info = chars[name]
                    if isinstance(info, dict):
                        category = info.get("category", "")
                        # "无名小卒"只有活跃时才显示，不活跃则跳过
                        if category == "无名小卒" and name not in active_names:
                            continue
                    important_chars[name] = info
            # 合并：活跃角色 + 主角/关键人物
            for name, info in chars.items():
                if name not in important_chars and isinstance(info, dict):
                    if info.get("category") in ("主角", "女主角", "男主角", "关键人物"):
                        important_chars[name] = info

            text = self._compress_active_characters(important_chars, active_names, int(max_chars * ratio["chars"]))
            if text:
                section = f"【当前剧情线角色】（共{len(important_chars)}人，请勿无故引入新角色）\n{text}"
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
            ec_section = f"【创作指引】\n{ec_text}"
            parts.append(ec_section)
            used += len(ec_section)  # P2-7: 计入段标题，避免预算失真

            # 同时做RAG检索补充
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                # P2-7: 预算下限钳位到 0，防止 max_chars-used 为负
                rag_budget = max(0, min(int(max_chars * ratio["rag"]), max_chars - used))
                text = self._compress_text(rag_text, rag_budget, keep_tail=False)
                if text and len(text) > 20:
                    rag_section = f"【相关记忆】\n{text}"
                    parts.append(rag_section)
                    used += len(rag_section)

        # 写作技能上下文（知识图谱、写作技巧）
        try:
            from .writing_skills import writing_skill_manager

            # P-04b：传入 `chapter_num`，让学习到的经验按"距今章节数"检索。
            # 旧实现不传 ⇒ `get_writing_context` 的 `chapter` 形参恒为默认 0
            # ⇒ 第 87 章写下的成功模式在第 120 章读不到。
            skills_context = writing_skill_manager.get_writing_context(chapter=chapter_num)
            if skills_context and len(skills_context) > 20:
                skill_budget = max(0, min(500, max_chars - used))
                text = self._compress_text(skills_context, skill_budget, keep_tail=False)
                if text:
                    skill_section = f"【写作参考】\n{text}"
                    parts.append(skill_section)
                    used += len(skill_section)
        except Exception as e:
            self.log(f"[写作技能] 获取上下文失败: {e}")

        # 插件写作技能包（v3.2）：插件贡献的提示词片段**单独占一段预算**。
        # 为什么不并进上面的【写作参考】：那段只有 500 字且会被 `_compress_text` 压缩，
        # 插件技能包（可能有多条、每条都较长）塞进去会被压没 —— 等于装上了但不起作用。
        # ⚠️ 这里必须**直接**调用（而不是只依赖 `get_writing_context` 内部已包含），
        # 因为 `tests/test_plugin_system.py::TestWiringGuard` 要求存在显式生产调用点，
        # 否则插件系统会重蹈"定义完整但零引用 ⇒ 被当死代码删除"的覆辙。
        try:
            from .writing_skills import writing_skill_manager

            plugin_ctx = writing_skill_manager.plugin_skill_context()
            if plugin_ctx:
                plugin_budget = max(0, min(800, max_chars - used))
                text = self._compress_text(plugin_ctx, plugin_budget, keep_tail=False)
                if text:
                    section = f"【插件写作技能】\n{text}"
                    parts.append(section)
                    used += len(section)
        except Exception as e:
            self.log(f"[插件技能] 获取上下文失败: {e}")

        # === 伏笔追踪 ===
        unresolved = self._get_unresolved_plots()
        if unresolved and used + len(unresolved) < max_chars:
            parts.insert(1, unresolved)  # 插入到全局摘要后面，确保AI看到
            used += len(unresolved)

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
        """压缩活跃角色信息 - 按等级优先显示"""
        result = []
        used = 0

        # 角色等级优先级
        PRIORITY_RANKS = {"主角": 0, "女主角": 0, "男主角": 0, "关键人物": 1, "配角": 2, "无名小卒": 3}

        # 按优先级排序
        def char_priority(name):
            if name not in chars:
                return 99
            info = chars.get(name, {})
            if isinstance(info, dict):
                return PRIORITY_RANKS.get(info.get("category", "无名小卒"), 3)
            return 3

        # 优先显示活跃角色（按等级排序）
        sorted_active = sorted(active_names, key=char_priority)
        for name in sorted_active:
            if used >= budget:
                break
            if name in chars:
                info = chars[name]
                if isinstance(info, dict):
                    category = info.get("category", "未知")
                    personality = info.get("personality", "")[:30]
                    faction = info.get("faction", "")
                    line = f"- [{category}] {name}: {personality}"
                    if faction:
                        line += f" (阵营:{faction})"
                else:
                    line = f"- {name}: {str(info)[:50]}"
                if used + len(line) <= budget:
                    result.append(line)
                    used += len(line)

        # 如果空间够，添加主角/关键人物（即使不活跃）
        if used < budget:
            for name, info in chars.items():
                if used >= budget or name in active_names:
                    continue
                if isinstance(info, dict):
                    category = info.get("category", "")
                    if category in ("主角", "女主角", "男主角", "关键人物"):
                        personality = info.get("personality", "")[:20]
                        line = f"- [{category}] {name}: {personality}"
                        if used + len(line) <= budget:
                            result.append(line)
                            used += len(line)

        return "\n".join(result) if result else ""

    def _get_unresolved_plots(self) -> str:
        """获取未回收的伏笔/剧情线索"""
        try:
            gs = self.memory.get_global_summary()
            if not gs:
                return ""

            # 从全局摘要中提取伏笔关键词
            foreshadow_keywords = [
                "伏笔",
                "悬念",
                "暗示",
                "预示",
                "未解之谜",
                "神秘",
                "秘密",
                "阴谋",
                "真相",
                "预言",
                "轮回",
                "宿命",
                "传承",
                "使命",
            ]

            unresolved = []
            for keyword in foreshadow_keywords:
                if keyword in gs:
                    # 找到包含关键词的句子
                    sentences = gs.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
                    for s in sentences:
                        if keyword in s and len(s) > 10:
                            unresolved.append(s.strip())
                            if len(unresolved) >= 8:
                                break
                if len(unresolved) >= 8:
                    break

            if unresolved:
                return "【未回收伏笔/悬念】\n" + "\n".join(unresolved[:8])
            return ""
        except Exception:
            return ""

    # ===== 压缩方法 =====

    def _compress_settings(self, settings: dict, budget: int) -> str:
        priority_keys = ["world", "rules", "factions", "technology", "history", "geography", "culture"]
        result = []
        used = 0
        for key in priority_keys:
            if key in settings and used < budget:
                val = str(settings[key])[: budget - used - len(key) - 3]
                result.append(f"{key}: {val}")
                used += len(val) + len(key) + 2
        return "\n".join(result)

    def _compress_characters(self, chars: dict, budget: int) -> str:
        core = ["name", "personality", "motivation"]
        result = []
        used = 0
        for name, info in list(chars.items())[:8]:
            if used >= budget:
                break
            if isinstance(info, dict):
                extra = "; ".join(f"{f}:{str(info.get(f, ''))[:50]}" for f in core if f in info)
                line = f"- {name}: {extra}"[: budget - used]
            else:
                line = f"- {name}: {str(info)[:100]}"[: budget - used]
            result.append(line)
            used += len(line) + 1
        return "\n".join(result)

    def _compress_text(self, text: str, budget: int, keep_tail: bool = True) -> str:
        if len(text) <= budget:
            return text
        if budget < 50:
            return text[:budget] + "..."
        if keep_tail:
            head = int(budget * 0.3)
            return text[:head] + "...\n\n" + text[-(budget - head - 5) :]
        else:
            head = int(budget * 0.7)
            return text[:head] + "...\n\n" + text[-(budget - head - 5) :]

    def _compress_recent_chapters(self, recent_text: str, budget: int, chapter_num: int) -> str:
        chapters = recent_text.split("\n\n")
        if len(chapters) <= 1:
            return self._compress_text(recent_text, budget, True)
        result = []
        used = 0
        latest = chapters[-1] if chapters else ""
        lb = min(int(budget * 0.4), len(latest))
        if latest:
            result.append(latest[:lb])
            used += lb
        for ch in reversed(chapters[:-1]):
            if used >= budget:
                break
            cb = min(int((budget - used) * 0.3), len(ch))
            if cb > 50:
                result.insert(0, self._compress_text(ch, cb, True))
                used += cb
        return "\n\n".join(result)

    # ===== 多智能体协作核心 =====

    def generate_with_collaboration(
        self, chapter_num: int, chapter_title: str, chapter_outline: str, word_count: int = 3000, prev_context: str = ""
    ) -> str:
        """多智能体协作生成章节 v3.0 - 5Agent协作

        Hello-Agents参考流程: PlotDesigner→WorldBuilder→Writer→Reviewer→Editor
        """
        with self._log_lock:
            self._conversation_log = []
        self.log(f"[编排器] 5Agent协作启动: 第{chapter_num}章「{chapter_title}」")

        # 📊 段级耗时归因：全程只建一个计时器，每个 Phase 结束记一笔。
        # 收尾时统一发一条 `CHAPTER/.../complete`，含总时长与各段明细。
        timer = _PhaseTimer()

        # 🔑 提取前一章结尾（在压缩前保存，确保不丢失）
        prev_ending = ""
        if prev_context and "【前一章" in str(prev_context):
            import re as _re

            m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n---|\n【|\Z)", str(prev_context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-1200:]

        # Phase 1: PlotDesigner - 分析大纲，管理伏笔
        self.log("[PlotDesigner] 分析大纲与伏笔...")
        self._record_conversation("PlotDesigner", "analyze", f"分析第{chapter_num}章大纲")
        _t = time.perf_counter()
        plot_analysis = self._plot_designer_analyze(chapter_num, chapter_title, chapter_outline)
        timer.phase(PHASE_PLOT, _t)

        # 注入前几章内容上下文
        plot_type = plot_analysis.get("type", "writing")
        _t = time.perf_counter()
        context = self._build_context(chapter_num, prev_context, writing_phase=plot_type)
        timer.phase(PHASE_CONTEXT, _t)
        self.log(f"[PlotDesigner] 情节类型: {plot_type}, 上下文已注入(全局摘要+卷摘要+角色+近期章节+创作指引)")

        # Phase 2: WorldBuilder - 场景与世界一致性
        self.log("[WorldBuilder] 构建场景描写...")
        self._record_conversation("WorldBuilder", "build", f"构建第{chapter_num}章场景")
        _t = time.perf_counter()
        world_context = self._world_builder_build(chapter_num, plot_analysis)
        timer.phase(PHASE_WORLD, _t)

        # 🔧 BUG-1修复: 将WorldBuilder输出注入Writer上下文
        if world_context:
            context = f"【场景描写 - WorldBuilder输出】\n{world_context}\n\n{context}"

        # Phase 3: Writer - 创作内容
        self.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self._record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        _t = time.perf_counter()
        content = self._writer_generate(
            chapter_num, chapter_title, chapter_outline, word_count, context=context, prev_ending=prev_ending
        )
        timer.phase(PHASE_WRITE, _t)

        # Phase 4-5: Reviewer → Editor 迭代修订
        prev_feedback = ""
        review: Dict = {}  # P-04：显式初始化，供结尾记录评分（循环至少跑一轮）
        for round_num in range(1, self.MAX_REVISION_ROUNDS + 1):
            self.log(f"[Reviewer] 审校第{chapter_num}章（第{round_num}轮）...")
            self._record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            _t = time.perf_counter()
            review = self._reviewer_evaluate(chapter_num, content, previous_feedback=prev_feedback)
            timer.phase(PHASE_REVIEW, _t)
            # R21 修复：这里紧接着就用 `review.setdefault(...)` / `review.get(...)`，
            # 而 `_reviewer_evaluate` 的解析结果**可能是 list**
            # （`parse_json_response` 在期望 dict 但 AI 返回顶层数组时会返回 list）。
            # 旧代码的守卫在第 748 行 —— **在所有使用之后**，等于没有；
            # 一旦命中，崩的是 `list.setdefault`（`AttributeError`），
            # 而且是在生成主流程里，整章生成失败。归一化必须在使用之前。
            if not isinstance(review, dict):
                self.log("[Editor] ⚠️ 审校返回的不是 JSON 对象，按默认评分处理")
                review = {"overall_score": 70, "issues": [], "suggestions": []}

            # 工具调用: 一致性检查
            self.tools.call("check_consistency", content=content[:500])

            # 调用写作技能: 去AI味检查
            slop_issues = self._call_anti_slop_check(content)
            if slop_issues:
                review.setdefault("issues", []).extend(slop_issues)
                review["overall_score"] = max(0, review.get("overall_score", 70) - len(slop_issues) * 2)
                self.log(f"[写作技能] 发现{len(slop_issues)}个AI写作痕迹，扣分")

            self.log(f"[Editor] 质量裁定：{review.get('overall_score', 0)}分")
            self._record_conversation(
                "Editor", "judge", f"评分{review.get('overall_score', 0)}，阈值{self.QUALITY_THRESHOLD}"
            )

            if review.get("overall_score", 0) >= self.QUALITY_THRESHOLD:
                self.log("[Editor] ✅ 通过！质量达标。")
                self._record_conversation("Editor", "approve", "质量达标，通过")
                break

            suggestions = review.get("suggestions", [])
            issues = review.get("issues", [])
            prev_feedback = f"上轮问题: {'; '.join(issues[:5])}" if issues else ""
            self.log(
                f"[Editor] ⚠️ 质量不达标（{review.get('overall_score', 0)}/{self.QUALITY_THRESHOLD}），"
                f"触发第{round_num}轮修订..."
            )

            with self._log_lock:
                self._revision_memory.append(
                    {
                        "chapter": chapter_num,
                        "round": round_num,
                        "issues": issues,
                        "suggestions": suggestions,
                    }
                )

            self.log("[Writer] 正在根据审校意见修订...")
            self._record_conversation("Writer", "revise", f"第{round_num}轮修订")
            _t = time.perf_counter()
            content = self._writer_revise(
                chapter_num, content, review, chapter_outline, context=context, prev_ending=prev_ending
            )
            timer.phase(PHASE_REVISE, _t)

        self.log(f"[编排器] 第{chapter_num}章5Agent协作完成 ({len(content)}字)")

        # 📊 段级耗时归因落盘。放在这里而不是 `finally` 里：
        # 生成中途抛异常时**不该**报一个"看起来正常"的总时长 —— 失败的耗时
        # 由调用方的异常处理各自记录，两处混在一起会互相掩盖。
        self._emit_chapter_timing(chapter_num, timer, review, content)

        # P-04：把本轮真实评分记在实例上，供 `finalize_chapter` 作为学习信号。
        # 此前这个分数在生成流程里算出来、写进对话日志、然后**被丢掉**：
        # 定稿学习时只能硬编码 `success=True`，无论这一章是 92 分还是 41 分。
        # 这里不直接把分数传给 finalize_chapter，是因为定稿有 4 个调用点
        # （生成流程 / 编辑器 / 全屏写作），只有本流程拿得到评分；
        # 记在实例上让"有评分时用评分、没有时按未知处理"成为统一行为。
        self.last_chapter_quality = review.get("overall_score") if isinstance(review, dict) else None
        return content

    def _emit_chapter_timing(self, chapter_num: int, timer: "_PhaseTimer", review: Any, content: str) -> None:
        """把一章的段级耗时写进诊断日志。

        为什么值得单独一个方法：这段逻辑要"绝不因为日志失败而影响生成"，
        而 `generate_with_collaboration` 已经在收尾阶段、任何异常都会让**整章**白写。
        所以异常在这里就地吞掉并降级为 debug 日志。

        记录内容刻意做成可机读的形状（`phases_ms` 是 `{阶段: 毫秒}`），
        这样"近 30 天哪个阶段最慢"可以纯靠 jq/脚本统计，不需要人来读日志。
        """
        diag = _diag_logger()
        if diag is None:
            return
        try:
            summary = timer.summary()
            score = review.get("overall_score") if isinstance(review, dict) else None
            diag.chapter_event(
                chapter_num,
                "complete",
                {
                    "chars": len(content),
                    "quality": score,
                    "threshold": self.QUALITY_THRESHOLD,
                    "revision_rounds": sum(1 for c in summary["calls"] if c["phase"] == PHASE_REVISE),
                    **summary,
                },
                duration_ms=summary["total_ms"],
            )
        except Exception as e:  # noqa: BLE001 - 计时/落盘失败绝不能影响生成结果
            # ⚠️ 这里必须用模块级的 loguru `logger`，不能写成上面那个 `diag`
            # （`DiagnosticLogger` 没有 `.debug`，一写就在异常处理里再抛一次，
            # 反而把"日志失败"升级成"整章生成失败"）。测试已钉住这条。
            logger.debug(f"[novel_agent] 章节耗时归因落盘失败（忽略）: {e}")

    def _plot_designer_analyze(self, chapter_num: int, title: str, outline: str) -> Dict:
        """PlotDesigner: 分析情节类型、节奏、伏笔"""
        if not outline or len(outline) < 10:
            if chapter_num <= 3:
                plot_type = "opening"
            elif chapter_num % 10 == 0:
                plot_type = "ending"
            else:
                plot_type = "writing"
            return {"type": plot_type, "pace": "medium", "foreshadowing": []}

        system = '你是专业情节设计师。分析章节大纲，输出JSON: {"type": "opening/writing/action/dialogue/ending", "pace": "slow/medium/fast", "foreshadowing": []}'
        prompt = f"第{chapter_num}章: {title}\n大纲: {outline[:500]}"
        try:
            response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1000)
            # P2-7 收敛：此前这里是手写的「括号深度追踪 + 正则兜底」两段解析
            # （约 30 行，含 `import re`、两处 `re.sub` 尾逗号修复）。
            # 改为走全仓唯一实现 `parse_json_response`：其 Strategy 1（截取 `{…}`）/
            # Strategy 2（去 markdown 后截取）/ Strategy 3（字符串感知 + 朴素两种修复）
            # 是本处逻辑的**严格超集**，且额外覆盖单引号、弯引号、
            # 截断补全（Strategy 4）。原来的「括号深度追踪」在此场景没有额外收益：
            # 期望结果是 dict，`parse_json_response` 的 Strategy 1 已按
            # `text.find("{")` + `text.rfind("}")` 取同一区间。
            parsed = self._parse_json_response(response, None)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            self.log(f"[PlotDesigner] 分析失败: {e}")
        return {"type": "writing", "pace": "medium", "foreshadowing": []}

    def _world_builder_build(self, chapter_num: int, plot_analysis: Dict) -> str:
        """WorldBuilder: 构建场景和世界观上下文"""
        settings = self.memory.get_settings()
        if settings and isinstance(settings, dict):
            world = settings.get("world", {})
            if isinstance(world, dict):
                known = world.get("已知区域", [])[:3]
                if known:
                    return f"世界观场景: {', '.join(known)}"
        return ""

    def _writer_generate(
        self,
        chapter_num: int,
        chapter_title: str,
        chapter_outline: str,
        word_count: int,
        context: str = None,
        prev_ending: str = "",
    ) -> str:
        """Writer智能体：生成章节内容"""
        if context is None:
            context = self._build_context(chapter_num)

        # === 缓存优化策略 ===
        # 将"固定写作指南"放在 system prompt 最前面，作为 DeepSeek 缓存前缀
        # 将"每章动态上下文"放在最后面，这样不同章节的 system prompt 前缀相同
        # 缓存命中率可以从 13.7% 提升到 60%+

        # 🔒 读取锁定的主角名
        protagonist = self.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f'\n\n【重要·主角锁定】本小说主角名为「{protagonist}」。所有章节必须以「{protagonist}」为主视角，禁止更换主角名！如果大纲中写"主角"，实际就是「{protagonist}」。'

        # --- 缓存前缀部分（固定，所有章节共用）---
        cache_prefix = f"""你是一位专业的小说作家（Writer Agent）。

【写作风格要求】
{self._get_writing_style_prompt()}

【正向要求 - 你必须做到】
1. 【最重要】必须紧接前一章结尾继续，保持时间、地点、情节的绝对连贯！
2. 角色行为符合其性格设定，保持人物形象一致
3. 情节推进自然流畅，有起承转合
4. 语言生动形象，有画面感和代入感
5. 直接输出正文内容，不要添加额外说明
6. 巧妙设置伏笔和悬念，吸引读者继续阅读
7. 对话要符合角色性格，有个性化特征
8. 场景描写要有细节，调动五感（视觉、听觉、嗅觉、触觉、味觉）
9. 适当运用修辞手法（比喻、拟人、排比等）增强文采
10. 目标字数约{word_count}字，必须写够字数

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
10. 禁止场景转换生硬，要有过渡
11. 【重要】禁止无故引入新角色！必须使用【当前剧情线角色】中已有的角色
12. 【重要】如果必须引入新角色，必须给出明确的出场原因和后续作用

【AI写作痕迹禁止 - 必须避免】
1. 禁止以"在这个世界上"、"在这个时代"等开头
2. 禁止过度使用"然而"、"不过"、"尽管如此"等过渡词
3. 禁止以"故事才刚刚开始"、"命运的齿轮开始转动"等结尾
4. 禁止形容词堆砌（如"美丽动人可爱"）
5. 要用具体动作和细节展示，不要直接告诉读者"""

        # --- 动态上下文部分（每章不同，放在缓存前缀后面）---
        dynamic_context = f"""{context}
{protagonist_hint}
请根据以上上下文信息创作小说章节。"""

        system = cache_prefix + "\n\n" + dynamic_context

        # 直接使用传入的前一章结尾（从generate_with_collaboration提取，未被压缩）
        if not prev_ending and "【前一章" in str(context):
            import re as _re

            m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)", str(context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-800:]

        if prev_ending:
            prompt = f"【前一章结尾 — 你必须紧接以下内容继续创作】\n{prev_ending}\n\n---\n\n请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文（必须紧接前文）："
        else:
            prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："

        if word_count > 3000:
            return self._generate_long_chapter(
                chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending
            )

        # 动态计算max_tokens：中文约2 tokens/字，预留足够空间
        max_tokens = max(word_count * 2, 8192)
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens)
        self.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response) if response else 0}")
        return response or ""

    def _reviewer_evaluate(self, chapter_num: int, content: str, previous_feedback: str = "") -> dict:
        """Reviewer智能体：审校章节

        参考AutoGen的code_reviewer角色，检查质量和一致性
        """
        context = self._build_context(chapter_num)

        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n上次审校反馈（请重点关注）：\n{previous_feedback}"

        # === 缓存优化策略（与Writer相同）===
        # 固定评审规则在前（缓存前缀），动态内容在后

        cache_prefix = """你是一位专业的小说审校编辑（Reviewer Agent）。

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

【AI写作痕迹检查 - 必须扣分】
1. 是否以"在这个世界上"、"在这个时代"等开头
2. 是否过度使用"然而"、"不过"、"尽管如此"等过渡词
3. 是否以"故事才刚刚开始"、"命运的齿轮开始转动"等结尾
4. 是否有形容词堆砌（如"美丽动人可爱"）
5. 是否有AI式的元叙述（如"读者可能会想"）"""

        dynamic_context = f"""{context}
{feedback_section}
请根据以上上下文严格检查以下章节内容的各方面质量。

请以JSON格式输出审校结果：
{{
    "character_consistency": 0-100,
    "plot_logic": 0-100,
    "writing_quality": 0-100,
    "emotional_impact": 0-100,
    "pacing": 0-100,
    "overall_score": 0-100,
    "strengths": ["优点1", ...],
    "issues": ["问题1", ...],
    "suggestions": ["建议1", ...],
    "is_acceptable": true/false
}}"""

        system = cache_prefix + "\n\n" + dynamic_context

        # 采样：开头2000 + 中间1000 + 结尾1000，覆盖全文
        sample_parts = []
        if len(content) > 4000:
            sample_parts.append(content[:2000])
            mid = len(content) // 2
            sample_parts.append(content[mid - 500 : mid + 500])
            sample_parts.append(content[-1000:])
            sample = "\n...（中间省略）...\n".join(sample_parts)
        else:
            sample = content

        prompt = f"请审校第{chapter_num}章内容：\n\n{sample}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)

        try:
            return self._parse_json_response(response or "{}", {"overall_score": 70, "issues": [], "suggestions": []})
        except Exception:
            return {"overall_score": 70, "issues": [], "suggestions": [], "raw": response}

    def _writer_revise(
        self,
        chapter_num: int,
        original: str,
        review: dict,
        chapter_outline: str,
        context: str = None,
        prev_ending: str = "",
    ) -> str:
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

        # 计算需要的token数（中文约2 tokens/字，需要输出完整章节）
        original_len = len(original)
        # 修订需要输出完整章节，所以max_tokens要足够大
        needed_tokens = max(8192, int(original_len * 2.5))

        # 采样策略：开头2000 + 中间1000 + 结尾2000，让AI了解全文结构
        if original_len > 5000:
            mid = original_len // 2
            original_sample = (
                original[:2000]
                + "\n...(中间省略)...\n"
                + original[mid - 500 : mid + 500]
                + "\n...(省略)...\n"
                + original[-2000:]
            )
        else:
            original_sample = original

        prompt = f"""请修订第{chapter_num}章内容。

审校反馈：
优点（请保持）：{json.dumps(strengths, ensure_ascii=False)}
问题（需修改）：{json.dumps(issues, ensure_ascii=False)}
建议（参考）：{json.dumps(suggestions, ensure_ascii=False)}

原文（共{original_len}字）：
{original_sample}

修订要求：
1. 输出完整的修订后文本（不少于{original_len}字）
2. 针对审校反馈的问题进行修改
3. 保持原文的优点和情节连贯性
4. 直接输出正文，不要输出分析过程："""

        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=needed_tokens)

        # 如果修订后字数明显变短，可能是AI截断了，返回原文
        if response and len(response) < original_len * 0.5:
            self.log(f"[Writer] 修订后字数({len(response)})过短，保留原文({original_len}字)")
            return original

        self.log(f"[Writer] 修订完成，字数：{len(response) if response else 0}")
        return response or original

    # ===== 传统方法（兼容旧接口）=====

    @task_tracker("chapter", chapter_param="chapter_num")
    def generate_chapter(
        self, chapter_num: int, chapter_title: str, chapter_outline: str, word_count: int = 3000, prev_context: str = ""
    ) -> str:
        """生成章节 - 带重复检测与修复"""
        max_retries = 3
        content = self.generate_with_collaboration(
            chapter_num, chapter_title, chapter_outline, word_count, prev_context
        )

        if not content:
            self.log(f"第{chapter_num}章生成失败，返回空内容")
            return f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"

        for retry in range(max_retries):
            has_rep, actual_words = self._has_excessive_repetition(content, word_count)
            if not has_rep:
                self.log(f"第{chapter_num}章质量检测通过 ({actual_words}字)")
                return content

            self.log(
                f"[重试{retry + 1}/{max_retries}] 第{chapter_num}章重复问题: 当前{actual_words}字→目标{word_count}字"
            )

            # 重试前等待，避免API过载
            if retry > 0:
                time.sleep(retry * 3)  # 3s, 6s

            strict_system = f"""你是专业小说作家。请根据大纲创作第{chapter_num}章。
【核心要求】
1. 目标字数{word_count}字，必须达标
2. 绝不允许重复内容。每500字推进一次剧情
3. 用{max(word_count // 2000, 1)}个不同的场景段落来写
4. 每个场景换地点、换人物、换冲突
5. 禁止Markdown格式（禁止**加粗**、*斜体*等标记），纯文本输出

第{chapter_num}章大纲: {chapter_outline}

直接输出小说正文，不要解释。"""

            # 限制max_tokens避免超时(中文字约1.5token/字)
            retry_tokens = min(word_count * 2, 16384)
            try:
                new_content = self.ai.chat(
                    [{"role": "user", "content": f"创作第{chapter_num}章：{chapter_title}，{word_count}字"}],
                    system=strict_system,
                    max_tokens=retry_tokens,
                )
            except Exception as e:
                self.log(f"第{chapter_num}章重试{retry + 1}失败: {e}")
                new_content = None
                # 如果是最后一次重试失败，保留原内容
                if retry == max_retries - 1:
                    self.log(f"第{chapter_num}章重试耗尽，保留原内容")
                    break
            if new_content:
                content = new_content

        self.log(f"第{chapter_num}章生成完成 ({len(content) if content else 0}字)")
        return content or f"# 第{chapter_num}章 {chapter_title}\n\n（内容生成失败，请重试）"

    #: 统计字数时需要剔除的 Markdown 标记字符（它们不是"字"）。
    _WORD_COUNT_SKIP_CHARS = frozenset("#*`>~[]()_")

    @classmethod
    def _count_words(cls, content: str) -> int:
        """统计正文的"字数"（D17 修复）。

        ❗ 原来这里用的是 `len(content)` —— 而 `content` 含 Markdown 标题、
        换行、空白。后果有两层，都很隐蔽：

        1. **字数被高估** ⇒ "字数严重不达标"的判据（`< target * 0.3`）**永不触发**
           ⇒ 生成质量闸门实际上是失效的；
        2. 更糟的是**上层的字数报告**也用同一个数 ⇒ 用户看到"本章 6000 字"，
           实际正文可能只有 4000 多。生成审计里 `字数: 10654` 那种数字就是这么来的。

        现在只统计**非空白、非 Markdown 标记**的字符 ——
        这与"中文字数"的直觉一致，也让闸门与界面报告用同一个可信数字。
        """
        if not content:
            return 0
        skip = cls._WORD_COUNT_SKIP_CHARS
        return sum(1 for ch in content if not ch.isspace() and ch not in skip)

    def _has_excessive_repetition(self, content: str, target_words: int) -> tuple:
        """检测是否存在过度重复，返回 (has_repetition, actual_word_count)"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        actual_words = self._count_words(content)

        # 字数严重不达标
        if actual_words < target_words * 0.3:
            return (True, actual_words)

        if len(paragraphs) < 3:
            return (actual_words < target_words * 0.6, actual_words)

        # 检测相似段落 — BUG-3修复: 使用字符级4-gram匹配（中文无空格分词）
        def _char_ngrams(text, n=4):
            """提取字符级n-gram集合"""
            return set(text[i : i + n] for i in range(max(0, len(text) - n + 1)))

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

        self.log(
            f"[质量检测] 相似段落对:{similar_count}, 短段落比:{short_ratio:.2f}, 字数:{actual_words}/{target_words}"
        )

        # 只有同时满足多个条件才判定为重复
        has_rep = (
            similar_count > 10
            or (actual_words < target_words * 0.4 and short_ratio > 0.5)
            or (similar_count > 3 and short_ratio > 0.7)
        )
        return (has_rep, actual_words)

    @task_tracker("review", chapter_param="chapter_num")
    def review_chapter(self, chapter_num: int, content: str) -> dict:
        """审校章节"""
        return self._reviewer_evaluate(chapter_num, content)

    def generate_settings(self, genre: str, title: str, concept: str) -> dict:
        """生成世界观 - 留有扩展空间"""
        self.log("[智能体] 正在生成世界观...")
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
        # R21 修复：`parse_json_response` 在 **期望 dict 但 AI 返回顶层数组** 时会
        # 返回 list（它只在 `is_list=True` 时拒收 dict，反向不拒）。而下游
        # `memory.save_settings` → `_format_settings_md` 会执行 `settings.items()`
        # ⇒ `AttributeError: 'list' object has no attribute 'items'`（已实测复现）。
        # 这里显式要求 dict，非 dict 一律走降级分支，与"解析失败"同等处理。
        if not isinstance(settings, dict):
            self.log("[警告] 世界观返回的不是 JSON 对象，忽略")
            settings = {"raw": response, "world": {}, "rules": {}, "factions": {}}
        elif not settings:
            self.log("[警告] 世界观生成失败，使用空设定")
            settings = {"raw": response, "world": {}, "rules": {}, "factions": {}}
        self.memory.save_settings(settings)
        return settings

    @task_tracker("characters")
    def generate_characters(self, genre: str, title: str, count: int = None) -> dict:
        """生成角色 - 根据小说规模智能确定角色数量"""
        if count is None:
            chapter_count = self.memory.get_meta("chapter_count", 20)
            if chapter_count <= 20:
                count = 3
            elif chapter_count <= 50:
                count = 5
            else:
                count = 8

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
      "体质": 随机值,
      "智力": 随机值,
      "精神": 随机值,
      "魅力": 随机值,
      "幸运": 随机值
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

        # 重试3次，处理AI返回空响应的情况（但不重试认证错误）
        response = None
        for attempt in range(3):
            try:
                response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=12000)
            except Exception as e:
                if "401" in str(e) or "Authorization" in str(e) or "API Key" in str(e):
                    raise  # 认证错误不重试
                if attempt < 2:
                    self.log(f"[角色] 调用失败({attempt + 1}/3): {e}，重试...")
                    time.sleep(3)
                    continue
                raise

            if response and len(response) > 50:
                break
            if attempt < 2:
                self.log(f"[角色] AI响应较慢，正在重试({attempt + 1}/3)，请稍候...")
                time.sleep(3)

        chars = self._parse_json_response(response, None)

        # 🔧 关键修复：即使解析成功，如果角色数量不足也需要回退
        parsed_count = len(chars) if isinstance(chars, dict) else 0
        if parsed_count > 0 and parsed_count < count:
            self.log(f"[角色] 初步解析仅获得 {parsed_count}/{count} 个角色，尝试从原始响应补充...")

        # 多层回退：如果标准解析失败（或数量不足），尝试从原始响应中提取
        need_extract = (
            chars is None
            or not isinstance(chars, dict)
            or len(chars) == 0
            or (isinstance(chars, dict) and len(chars) < count)
        )
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
            self.log("[角色] 尝试最终回退策略: 从响应中提取角色名...")
            if response:
                import re as _char_re

                name_patterns = _char_re.findall(r'"([^"]{1,6})"\s*:\s*\{', response)
                if name_patterns:
                    t = title
                    for name in name_patterns[:count]:
                        if name not in [
                            "gender",
                            "age",
                            "category",
                            "faction",
                            "personality",
                            "background",
                            "appearance",
                            "weapon",
                            "attributes",
                            "skill_suggestions",
                            "goal",
                            "relationship_to_main",
                            "title",
                            "summary",
                            "key_events",
                        ]:
                            if name not in (chars or {}):
                                chars[name] = {
                                    "gender": "未知",
                                    "age": 25,
                                    "category": "关键人物",
                                    "faction": "中立",
                                    "personality": "待展开",
                                    "background": f"《{t}》中的重要角色",
                                    "appearance": "待展开",
                                    "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                                    "skill_suggestions": [],
                                    "attributes": {"力量": 50, "敏捷": 50, "智力": 50, "体力": 50, "魅力": 50},
                                    "relationship_to_main": "待展开",
                                    "goal": "待展开",
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
                field_names = {
                    "gender",
                    "age",
                    "category",
                    "faction",
                    "personality",
                    "background",
                    "appearance",
                    "weapon",
                    "attributes",
                    "skill_suggestions",
                    "goal",
                    "relationship_to_main",
                    "title",
                    "summary",
                    "key_events",
                    "name",
                    "level",
                    "hp",
                    "mp",
                    "exp",
                    "stats",
                }
                t = title
                added = 0
                for name in name_patterns:
                    if name not in existing and name not in field_names and added < count - len(chars):
                        chars[name] = {
                            "gender": "未知",
                            "age": 25,
                            "category": "配角",
                            "faction": "中立",
                            "personality": "待AI展开",
                            "background": f"《{t}》中的{name}",
                            "appearance": "待AI展开",
                            "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                            "skill_suggestions": [],
                            "attributes": {"力量": 50, "敏捷": 50, "智力": 50, "体力": 50, "魅力": 50},
                            "relationship_to_main": "与主角的关系待展开",
                            "goal": "待AI展开",
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
        chars_dir = self.memory.novel_dir / "characters" if hasattr(self.memory, "novel_dir") else None
        if chars_dir is None:
            chars_dir = self.memory.memory_dir.parent / "characters"
        chars_dir.mkdir(exist_ok=True)

        for name, info in chars.items():
            if isinstance(info, dict):
                char_data = {"name": name, **info}
                # API-3修复: 文件名安全处理（统一委托 app.storage.safe_filename）
                safe_name = safe_filename(name)
                atomic_write_json(chars_dir / f"{safe_name}.json", char_data)
                saved_count += 1

        if saved_count > 0:
            self.log(f"[角色] 已保存 {saved_count} 个角色到 {chars_dir}")
        else:
            self.log("[角色] 警告：未能保存任何角色文件！")

        # 写回 memory/characters.json。
        # 关键：必须与既有角色取并集，不能整体覆盖 —— `chars` 只包含本次 AI
        # 生成的一批，直接覆盖会把小说里已有的角色（当前实测 286 个）全部清掉。
        # 同名角色的字段按"新数据优先"合并，未出现在本批次中的角色原样保留。
        def _merge(existing: dict):
            merged = dict(existing)
            for name, info in chars.items():
                old = merged.get(name)
                if isinstance(old, dict) and isinstance(info, dict):
                    combined = dict(old)
                    combined.update(info)
                    merged[name] = combined
                else:
                    merged[name] = info
            return merged

        # V4: 先确认底座可信。若磁盘上的角色档案已损坏且无可用备份，
        # `get_characters()` 会降级返回 {}，于是下面的"并集"退化成"整体覆盖"
        # ——上一轮修好的 R1 在损坏场景下完全不生效，且因为结果是非空，
        # 用户看不到任何告警。这里在读到降级结果后立即失败，交出可操作的提示。
        #
        # 用 `is True` 而非真值判断：`self.memory` 允许是鸭子类型的协作者
        # （单测里就是 MagicMock），`getattr(mock, "_characters_corrupt")` 会返回
        # 一个真值的子 Mock，真值判断会把**一切**调用都误判成"底座损坏"。
        before = len(self.memory.get_characters())
        if getattr(self.memory, "_characters_corrupt", False) is True:
            raise CharacterDataGuardError(
                "角色档案损坏且无可用备份，已拒绝本次角色写入以避免清空既有角色；"
                "请先修复 memory/characters.json（或其 .bak）后重试"
            )

        merged_chars = self.memory.mutate_characters(_merge)
        added = len(merged_chars) - before
        if added > 0:
            self.log(f"[角色] 新增 {added} 个角色（既有 {before} 个已保留）")

        return chars

    @task_tracker("outline")
    def generate_outline(
        self, genre: str, title: str, chapter_count: int, concept: str = "", total_chapters: int = None
    ) -> list:
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
                    f"第{r.get('chapter', '?')}章 {r.get('title', '?')}: {str(r.get('summary', ''))[:40]}"
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

            self.log(
                f"[大纲] 第{start_ch}-{start_ch + batch_count - 1}章 ({batch_idx + 1}/{total_batches}) {phase[:20]}"
            )

            batch_outline = self._generate_outline_batch(
                genre,
                title,
                batch_count,
                start_ch,
                f"{ctx}\n创作阶段: {phase}\n剩余{chapter_count - start_ch + 1 - batch_count}章",
            )
            all_outline.extend(batch_outline)

        return all_outline

    def _plan_story_arcs(self, genre: str, title: str, chapter_count: int, concept: str) -> str:
        """为长篇规划故事弧线"""
        system = f"你是专业故事架构师。为{chapter_count}章长篇规划故事弧线。输出简洁文本。"
        prompt = f"类型:{genre} 标题:{title} 概念:{concept[:200]}\n为{chapter_count}章规划: 1.开端(前15%) 2.发展(15-70%) 3.高潮(70-90%) 4.结局(90-100%)。每段50字。"
        try:
            response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1500)
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
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=max(count * 150, 4000))
        outline = self._parse_json_response(response, [], is_list=True)

        if not outline or len(outline) < count:
            # 填充缺失的章节 — 使用"待规划"标记，让生成器动态填充
            existing = {o["chapter"] for o in outline if "chapter" in o} if outline else set()
            for i in range(count):
                ch_num = start_num + i
                if ch_num not in existing:
                    outline.append({"chapter": ch_num, "title": f"第{ch_num}章", "summary": "待规划"})

        # 确保有序
        outline.sort(key=lambda x: x.get("chapter", 0))
        return outline

    @task_tracker("outline")
    def generate_outline_continuation(
        self, genre: str, title: str, add_count: int, global_context: str, current_count: int
    ) -> list:
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
            f"章节从第{current_count + 1}章开始编号。\n"
            f"必须延续已有剧情、保持风格。{protagonist_hint}\n"
            f"输出JSON数组：[{{'chapter':{current_count + 1},'title':'','summary':'','key_events':[],'characters_involved':[]}}]"
        )
        prompt = f"小说类型：{genre}\n标题：{title}\n续写{add_count}章，从第{current_count + 1}章开始"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        outline = self._parse_json_response(response, [], is_list=True)
        if not outline:
            outline = [
                {"chapter": current_count + i + 1, "title": f"第{current_count + i + 1}章", "summary": "待规划"}
                for i in range(add_count)
            ]
        return outline

    def finalize_chapter(self, chapter_num: int, content: str, quality: int | None = None):
        """定稿章节 + 更新记忆 + 角色属性变化"""
        summary = content[:200]  # 默认摘要

        # 章节摘要（带异常保护）
        try:
            result = self.ai.chat(
                [{"role": "user", "content": f"请生成摘要（100-200字）：\n{content[:2000]}"}],
                system="你是故事摘要助手。只输出摘要正文，不要输出思考过程、不要解释、不要自我校对。",
                # `max_tokens` 必须**显著高于** `reasoning.THINKING_MIN_TOKENS`(1000)：
                # 原本写成 1000 恰好等于该阈值，而阈值判据是严格小于 ⇒ 思考没被禁用
                # 但预算不够输出 ⇒ 兜底把推理原文当摘要返回（见 `_looks_like_chain_of_thought`
                # 上方的实测事故记录）。
                max_tokens=2000,
                # 摘要不需要推理，显式关闭思考，从源头避免"预算被思考吃光"。
                thinking_enabled=False,
            )
            if result and not _looks_like_chain_of_thought(result):
                summary = result
            else:
                # 返回疑似推理过程（或为空）⇒ 弃用，退回正文截断。
                # 宁可摘要糙一点，也不能把推理过程落盘 —— 它会经 add_chunk
                # 进入记忆库并回灌到后续章节。
                self.log(f"[定稿] 摘要返回异常(len={len(result) if result else 0})，改用正文截断")
            self.memory.save_chapter_summary(chapter_num, summary)
        except Exception as e:
            self.log(f"[定稿] 摘要生成失败: {e}")
            self.memory.save_chapter_summary(chapter_num, summary)

        # 全局摘要（带异常保护）
        try:
            old = self.memory.get_global_summary()
            new = self.ai.chat(
                [{"role": "user", "content": f"更新全局摘要：\n旧：{old}\n新章节：{summary}"}],
                system="你是故事摘要助手。只输出摘要正文，不要输出思考过程。",
                # 同章节摘要：给足预算 + 关思考 + 校验返回
                max_tokens=2000,
                thinking_enabled=False,
            )
            if new and not _looks_like_chain_of_thought(new):
                self.memory.save_global_summary(new)
            elif new:
                # 保留旧摘要比写入推理过程安全 —— 全局摘要会被注入每一章的上下文
                self.log(f"[定稿] 全局摘要返回疑似推理(len={len(new)})，保留旧值")
        except Exception as e:
            self.log(f"[定稿] 全局摘要更新失败: {e}")

        # 关键词索引（带异常保护）
        try:
            kw = self.ai.chat(
                [{"role": "user", "content": f"提取10个关键词，逗号分隔：\n{content[:1000]}"}],
                system="提取关键词。只输出关键词本身，用逗号分隔。",
                # 关键词同样会被原样落盘进索引，同享三道防线
                max_tokens=2000,
                thinking_enabled=False,
            )
            if kw and _looks_like_chain_of_thought(kw):
                self.log("[定稿] 关键词返回疑似推理，跳过索引更新")
                keywords = []
            else:
                keywords = [k.strip() for k in (kw or "").split(",") if k.strip()]
                self.memory.update_index(chapter_num, keywords)
        except Exception as e:
            self.log(f"[定稿] 关键词提取失败: {e}")
            keywords = []

        # 添加记忆块
        try:
            # 类型标为 `summary`：这里存的**就是章节摘要**。旧代码写 `"plot"`（情节），
            # 与内容不符 —— 实测日志里出现过 `type:"plot"` 但 content 是摘要（且当时
            # 还是思维链原文）的条目，类型错标会让后续按类型检索时语义失真。
            # 全仓对 `"plot"` 的引用仅此一处，无检索方依赖该字符串，改名安全。
            self.memory.add_chunk("summary", summary, importance=8, tags=keywords[:5] if keywords else [])
            self.memory.add_event(chapter_num, summary, "story")
        except Exception as e:
            self.log(f"[定稿] 记忆块添加失败: {e}")

        # 角色属性变化检测
        try:
            self._update_character_progression(chapter_num, content, summary)
        except Exception as e:
            self.log(f"[定稿] 角色变化检测失败: {e}")

        # 写作技能学习（从成功章节中学习）
        try:
            from .writing_skills import writing_skill_manager

            # 提取角色名
            chars = list(self.memory.get_characters().keys())[:10]
            # ❗ 不能写成 `str(self.memory.novel_dir) if self.memory else None`：
            # `novel_dir` 为 None 时 `str(None)` 得到**真值字符串 `"None"`**，
            # 而 `writing_skills` 的判据是 `if novel_dir:` ⇒ 会在**当前工作目录**下
            # 真的建出 `None/writing_skills/` 两个文件（实测已复现）。
            # 判据必须落在"值"上，而不是"对象是否存在"。
            _nd = getattr(self.memory, "novel_dir", None)
            novel_dir = str(_nd) if _nd else None
            # P-04 修复：`success` 不再硬编码 True。
            # 评分来源优先级：显式入参 → `self.last_chapter_quality`（生成流程写入）
            # → None（未知）。None 时按成功处理，**保持旧行为不变**；
            # 只有拿到真实评分时才按 QUALITY_THRESHOLD 判定，
            # 让"质量不达标的章节"不再污染学习库。
            # 详情见 docs/AGENT_OPTIMIZATION_PLAN.md 的 P-04。
            effective_quality = quality if quality is not None else self.last_chapter_quality
            success = True if effective_quality is None else (effective_quality >= self.QUALITY_THRESHOLD)
            writing_skill_manager.learn_from_chapter(
                content, chapter_num, chars, success=success, novel_dir=novel_dir, quality=effective_quality
            )
            # 更新知识图谱
            for char_name in chars:
                if char_name not in writing_skill_manager.knowledge_graph.entities:
                    writing_skill_manager.knowledge_graph.add_entity(char_name, "character")
            score_note = (
                "" if effective_quality is None else f"（评分{effective_quality}{'' if success else '·未达标'}）"
            )
            self.log(f"[写作技能] 已学习第{chapter_num}章模式{score_note}")
        except Exception as e:
            self.log(f"[写作技能] 学习失败: {e}")

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

            # 采样策略：开头2000 + 中间1000 + 结尾1000，覆盖全文
            if len(content) > 4000:
                mid = len(content) // 2
                sample = (
                    content[:2000]
                    + "\n...(中间省略)...\n"
                    + content[mid - 500 : mid + 500]
                    + "\n...(省略)...\n"
                    + content[-1000:]
                )
            else:
                sample = content

            response = self.ai.chat(
                [
                    {
                        "role": "user",
                        "content": f"章节摘要: {summary}\n内容片段: {sample}\n\n请直接输出JSON，不要分析过程。",
                    }
                ],
                system=system,
                max_tokens=3000,
            )
            if not response:
                return

            # P2-7 收敛：此前这里有 **Strategy 1–3 三段共 60 余行手写解析**
            # （括号深度追踪 → 正则 + 再追踪一次 → 去 markdown 重试），
            # 全部是 `parse_json_response` Strategy 1/2/3 的真子集。
            # 行为只可能**变好**：本处的失败路径是直接 `[角色成长] JSON解析失败，跳过本章`
            # 丢数据，而统一解析器额外覆盖单引号、弯引号、截断补全（Strategy 4）。
            data = self._parse_json_response(response, None)

            # Strategy 4（**保留**）：逐字段提取。
            # 这一策略统一解析器覆盖不到 —— 它针对的是"AI 返回大段思考文本 +
            # 其中夹着一个**本身就不合法**的 updates 数组"的极端情况：
            # 只能靠正则把每个 `{..."name":..."}` 单独捞出来重建。
            if not isinstance(data, dict):
                try:
                    # 提取 "updates" 数组内容
                    updates_match = re.search(r'"updates"\s*:\s*\[([\s\S]*?)\]', response)
                    if updates_match:
                        updates_str = updates_match.group(1)
                        # 提取每个 {name:..., change:..., reason:...} 对象
                        update_items = re.finditer(r'\{[^{}]*"name"\s*:\s*"([^"]*)"[^{}]*\}', updates_str)
                        updates = []
                        for m in update_items:
                            obj_str = m.group(0)
                            name = re.search(r'"name"\s*:\s*"([^"]*)"', obj_str)
                            change = re.search(r'"change"\s*:\s*"([^"]*)"', obj_str)
                            reason = re.search(r'"reason"\s*:\s*"([^"]*)"', obj_str)
                            if name:
                                updates.append(
                                    {
                                        "name": name.group(1),
                                        "change": change.group(1) if change else "",
                                        "reason": reason.group(1) if reason else "",
                                    }
                                )
                        if updates:
                            data = {"updates": updates}
                except Exception as _silent_e:
                    logger.debug(f"[novel_agent] 捕获异常: {_silent_e}")

            if not data:
                self.log("[角色成长] JSON解析失败，跳过本章")
                if _diag:
                    _diag.log(
                        "WARN",
                        "character_growth_parse_failed",
                        {
                            "chapter": chapter_num,
                            "response_preview": response[:200] if response else "null",
                            "response_len": len(response) if response else 0,
                        },
                    )
                return

            # 保存到记忆
            changes = 0
            if data.get("updates"):
                for u in data["updates"]:
                    if isinstance(u, dict) and u.get("name"):
                        self.memory.add_event(
                            chapter_num,
                            f"角色变化: {u['name']} {u.get('change', '')} ({u.get('reason', '')})",
                            "character_growth",
                        )
                        changes += 1

            if data.get("skills_learned"):
                for s in data["skills_learned"]:
                    if isinstance(s, dict) and s.get("name"):
                        self.memory.add_event(
                            chapter_num, f"技能领悟: {s['name']} 学会 {s.get('skill', '')}", "skill_learn"
                        )
                        changes += 1

            if data.get("relationship_changes"):
                for r in data["relationship_changes"]:
                    if isinstance(r, dict) and r.get("name1"):
                        self.memory.add_event(
                            chapter_num,
                            f"关系变化: {r['name1']}与{r.get('name2', '')} {r.get('old', '')}→{r.get('new', '')}",
                            "relationship_change",
                        )
                        changes += 1

            if data.get("items_gained"):
                for item in data["items_gained"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(
                            chapter_num, f"获得物品: {item['name']} 获得 {item.get('item', '')}", "item_gain"
                        )

            if data.get("items_lost"):
                for item in data["items_lost"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(
                            chapter_num, f"失去物品: {item['name']} 失去 {item.get('item', '')}", "item_loss"
                        )

            if data.get("new_allies"):
                for name in data["new_allies"]:
                    if isinstance(name, str) and name:
                        self.memory.add_event(chapter_num, f"新盟友: {name}", "new_ally")

            if data.get("new_enemies"):
                for name in data["new_enemies"]:
                    if isinstance(name, str) and name:
                        self.memory.add_event(chapter_num, f"新敌人: {name}", "new_enemy")

            if data.get("deaths"):
                for name in data["deaths"]:
                    if isinstance(name, str) and name:
                        self.memory.add_event(chapter_num, f"角色死亡: {name}", "character_death")
                        self.memory.update_character(name, {"status": "死亡", "death_chapter": chapter_num})

            # 统计日志
            summary_parts = []
            if changes:
                summary_parts.append(f"{changes}个成长")
            if data.get("items_gained"):
                summary_parts.append(f"{len(data['items_gained'])}个获得")
            if data.get("items_lost"):
                summary_parts.append(f"{len(data['items_lost'])}个失去")
            if data.get("skills_learned"):
                summary_parts.append(f"{len(data['skills_learned'])}个技能")
            if data.get("relationship_changes"):
                summary_parts.append(f"{len(data['relationship_changes'])}个关系")
            if data.get("deaths"):
                summary_parts.append(f"{len(data['deaths'])}个死亡")
            if data.get("new_allies"):
                summary_parts.append(f"{len(data['new_allies'])}个新盟友")
            if data.get("new_enemies"):
                summary_parts.append(f"{len(data['new_enemies'])}个新敌人")

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
        # R21 修复：同 `_world_builder` —— 期望 dict 但拿到 list 时必须降级，
        # 否则这个 list 会被当成"风格配置"返回并参与后续拼装（下游多处按 dict 取值）。
        if not isinstance(style, dict):
            self.log("[警告] 风格分析返回的不是 JSON 对象，改用降级结果")
            style = {"author": author_name, "raw": result}

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
            author = style.get("author", f"风格{i + 1}")
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
    #
    # v3 A1/A2（去重）：这两个方法原先各自带一份**独立实现**
    # （`_extract_characters_from_raw` 约 80 行手写扫描、`_parse_json_response`
    #  约 60 行 Strategy 1~5），与 `app/parsing.py` 的同名纯函数重复且已**漂移**：
    # 本地版本会把键名为 `raw` 的**真角色**静默丢弃，而 parsing 版早已修掉该缺陷。
    #
    # 现在实现单一来源于 `app/parsing.py`，这里只保留薄委托。为什么保留方法名：
    # 库内 6 处调用点 + 6 个测试文件都按此名调用 —— **测试也是调用方**，
    # 直接删除会让 tests/test_novel_agent_*.py 整体失败。

    @staticmethod
    def _extract_characters_from_raw(raw_text: str) -> dict:
        """从 AI 原始响应中提取角色字典。

        委托 `parsing.parse_characters_payload`（含字符串感知清洗、结构性修复、
        以及"外层被截断但内部角色对象完整"的逐个提取兜底）。
        """
        return parse_characters_payload(raw_text)

    @staticmethod
    def _parse_json_response(response: str, default: Any, is_list: bool = False) -> Any:
        """解析 AI 返回的 JSON（多层回退）。

        委托 `parsing.parse_json_response`；`is_list=True` 时只接受 list 结果，
        与旧实现的类型语义一致（调用方随后按序列遍历）。
        """
        return parse_json_response(response, default, is_list=is_list)

    def _generate_long_chapter(
        self, chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending=""
    ) -> str:
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
            is_last = i == part_count - 1
            self.log(f"[Writer] 第{chapter_num}章 第{i + 1}/{part_count}段...")

            prev_text = "".join(parts)
            if i == 0:
                # 第一段：使用传入的前一章结尾（未被压缩）
                if not prev_ending and context and "【前一章" in str(context):
                    import re as _re

                    m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)", str(context), _re.DOTALL)
                    if m:
                        prev_ending = m.group(1).strip()[-800:]
                if prev_ending:
                    part_prompt = f"【前一章结尾 — 必须紧接以下内容】\n{prev_ending}\n\n---\n\n创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文（必须紧接前文）："
                else:
                    part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文："
            elif is_last:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                # ❗ D15 修复：原提示词只说"给出自然完整的**段落**结尾"。
                # 这会把末段写成"场景收尾"而不是"章节落点" —— 分段生成的章节
                # 于是呈现"每段各自了结、整章没有推进"的观感，也就是读者说的**烂尾**。
                # 末段是本章唯一的定调位置，必须明确要求：本章要有**事件推进**与
                # **情绪落点**，且不得复述前文。
                part_prompt = (
                    f"紧接上文继续写。上文结尾：{last_200}\n"
                    f"这是本章的最后一段（约{seg_size}字）。要求：\n"
                    f"1. 必须**推进实质剧情**（发生一件前面没有的事），不得只是回顾或抒情收束；\n"
                    f"2. 结尾要落在**本章的核心冲突/转折**上，形成章节落点，而不是平淡的场景收尾；\n"
                    f"3. 不要总结全章、不要复述已有情节、不要写「本章完」之类的话；\n"
                    f"4. 直接接续上文文字，不要重复上文任何句子。"
                )
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
                        max_tokens=4096,
                    )
                    if response and len(response) > 100:
                        # 去除AI生成的标题
                        lines = response.split("\n", 2)
                        clean = []
                        for line in lines:
                            stripped = line.strip()
                            if (
                                stripped.startswith("#") or (stripped.startswith("第") and "章" in stripped[:10])
                            ) and not clean:
                                continue
                            clean.append(line)
                        response = "\n".join(clean)
                        parts.append(response)
                        break
                except Exception as e:
                    # 认证错误不重试
                    if "401" in str(e) or "Authorization" in str(e) or "API Key" in str(e):
                        raise
                    self.log(f"[Writer] 第{chapter_num}章第{i + 1}段 重试{attempt + 1}: {e}")
                    if attempt == 2:
                        return title_line + ("\n\n".join(parts) if parts else "（生成失败）")

        result = title_line + ("\n\n".join(parts) if parts else "（生成失败）")

        # 末段完整性检查：如果结尾没有句号/感叹号/问号等，AI补全
        #
        # ❗ D18 修复：原实现有三个问题，合起来**主动弄坏了本来完整的结尾**：
        #   1. 判据是"最后一个字符不是终止符"。但 `…` / `—` / `"` 都在白名单里，
        #      于是大量**正常**结尾（以引号或省略号收束的对话）被误判为"不完整"；
        #   2. 判据只看**单字符**，不看语义：`"他走了。"` 以 `"` 收尾会被判不完整，
        #      实际上它比任何补全都完整；
        #   3. 补全文字是**直接 `+=` 追加**的 —— 即使在正确判定的情况下，
        #      追加也必然把"已经说完的话"接上"另一段话"，读起来就是**断裂**，
        #      这正是烂尾观感的一部分。
        #
        # 现在的策略是**保守**：只在"末尾明显断在半句/半词"时才补，
        # 并优先用**句读补全**（几乎不可见），拿不准就**不动** ——
        # "少做"比"把好结尾改坏"安全得多。
        if parts and len(result) > 500:
            last_meaningful = result.rstrip("\n\r \t'\"》）」】…—")
            if last_meaningful:
                last_char = last_meaningful[-1]
                # 只有这些字符能确认"句子说完了"。注意**不含**引号与破折号：
                # 它们既可能收尾也可能收在句中，不足以判断完整性。
                sentence_end = {"。", "！", "？", ".", "!", "?", "；", ";"}
                # 直接以句末标点收尾 ⇒ 完整，**不碰它**
                if last_char in sentence_end:
                    pass
                elif self._looks_truncated(last_meaningful):
                    self.log(f"[Writer] 第{chapter_num}章末尾疑似断句，尝试补全…")
                    try:
                        last_paragraph = result[-500:]
                        completion = self.ai.chat(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        "以下小说段落在结尾处断了。请只补一个**短语**（10-30字）"
                                        f"把它接成完整句子，不要开启新的情节：\n{last_paragraph}"
                                    ),
                                }
                            ],
                            system="你是文字校对。只输出补全的短语本身，不要重复已有内容，不要换行。",
                            max_tokens=1000,
                        )
                        completion = (completion or "").strip()
                        # ❗ 与原文重叠的补全一律丢弃（`in` 判据比原来的
                        # `completion[:10] in result[-50:]` 更严：后者只查开头 10 字）
                        if completion and completion not in result and len(completion) <= 60:
                            result += completion
                        elif completion:
                            self.log("[Writer] 补全内容与原文重复或过长，已放弃追加")
                    except Exception as e:
                        self.log(f"[长章节末段补全] 失败: {e}")
                else:
                    # 无法确定是否断句 ⇒ **宁可不动**。静默是最安全的选择。
                    self.log(f"[Writer] 第{chapter_num}章末尾以「{last_char}」收尾，判为完整，跳过补全")

        return result

    @staticmethod
    def _looks_truncated(text: str) -> bool:
        """判断文本末尾是否**明显断在半句**（而不是"只是没以句号结尾"）。

        判据刻意保守 —— 只有同时满足"没有句末标点"且"末尾字符不可能收尾"
        才返回 `True`。因为**误判的代价不对称**：
        漏判一个真断句 ⇒ 结尾略突兀；误判一个完整结尾 ⇒ 追加一段无关文字、
        把好结尾改坏（即烂尾）。后者严重得多。
        """
        tail = (text or "").rstrip()
        if not tail:
            return False
        last = tail[-1]
        # 能收尾的字符：句末标点 + 引号 + 省略号 + 破折号 + 英文句点
        closers = set("。！？…—.!?~」』】》\"'")
        if last in closers:
            return False
        # 中文逗号/顿号/分号/冒号结尾 ⇒ 明确还在句中
        if last in set("，、；：,;:"):
            return True
        # 其余（多为汉字或字母）⇒ 无法确定，按"完整"处理（见上面的代价不对称）
        return False
