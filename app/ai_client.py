"""
AI客户端模块 v3.0 - 生产级AI服务接口

特性：
- 自动重试与指数退避
- 模型降级/故障转移
- 请求限流
- 性能监控
- 流式输出支持
- 专业创作框架
- Token消耗统计
- 多模型深度思考模式 (DeepSeek/GLM/Qwen/Kimi)
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .config import AppConfig
from .providers import (
    AuthStyle,
    BalanceCache,
    ChatRequest,
    OpenAICompatAdapter,
    ProviderAdapter,
    ProviderRegistry,
    ProviderSpec,
    UsageData,
    default_registry,
    is_transient_error,
)

#: `_parse_thinking_response` 用的解析器缓存（模块级：该方法会被
#: `AIClient.__new__(AIClient)` 方式的单测调用，实例属性此时并不存在）
_LABEL_ADAPTERS: Dict[str, OpenAICompatAdapter] = {}

# AI诊断日志
try:
    from .diagnostic_logger import get_logger
    _diag_logger = get_logger()
except Exception:
    _diag_logger = None


@dataclass
class TokenStats:
    """Token消耗统计"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, prompt_tokens: int, completion_tokens: int):
        with self._lock:
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            self.total_tokens += (prompt_tokens + completion_tokens)
            self.request_count += 1

    def get_summary(self) -> Dict:
        with self._lock:
            return {
                "total_tokens": self.total_tokens,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "request_count": self.request_count
            }

    def get_display(self) -> str:
        """返回用户友好的显示文本"""
        with self._lock:
            if self.total_tokens >= 1000000:
                return f"{self.total_tokens/1000000:.1f}M tokens ({self.request_count}次调用)"
            elif self.total_tokens >= 1000:
                return f"{self.total_tokens/1000:.1f}K tokens ({self.request_count}次调用)"
            else:
                return f"{self.total_tokens} tokens ({self.request_count}次调用)"


# 全局Token统计实例
token_stats = TokenStats()


def _is_transient_error(exc: BaseException) -> bool:
    """判断异常是否属于「重试有意义」的瞬时故障。

    M1: 原 `retry_with_backoff` 装饰器**无差别重试一切异常**（包括 401 鉴权
    失败、400 参数错误），既放大配额消耗又拖长用户等待；且全仓生产代码零调用
    （仅单测引用），属于会误导后来者的死代码，故整体删除。

    P3（v3）：这个判据**本身也曾是死代码** —— 真实重试逻辑只看 `status == 429`，
    5xx 与网络错误从未重试过，与这里写好的判据直接矛盾。现在判据的唯一实现是
    `app/providers/base.is_transient_error`，并被 `AIClient._invoke_adapter`
    真正调用；本函数保留为转发，既消灭重复实现，也不破坏既有引用面。
    """
    return is_transient_error(exc)


class AIMetrics:
    """AI服务性能监控 - 聚焦延迟、成本、错误率。
    Token统计由全局 TokenStats 统一管理，避免数据重复。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.total_requests = 0
        self.total_cost = 0.0
        self.errors = 0
        self.avg_latency = 0
        self._latency_samples = []

    def record(self, latency: float, cost: float = 0, error: bool = False):
        """记录请求指标（token由TokenStats统一管理）"""
        with self._lock:
            self.total_requests += 1
            self.total_cost += cost
            if error:
                self.errors += 1
            self._latency_samples.append(latency)
            if len(self._latency_samples) > 100:
                self._latency_samples = self._latency_samples[-100:]
            self.avg_latency = sum(self._latency_samples) / len(self._latency_samples)

    def get_summary(self) -> dict:
        with self._lock:
            # 合并 TokenStats 的 token 数据
            token_summary = token_stats.get_summary()
            return {
                "requests": self.total_requests,
                "tokens_total": token_summary["total_tokens"],
                "tokens_prompt": token_summary["prompt_tokens"],
                "tokens_completion": token_summary["completion_tokens"],
                "tokens_requests": token_summary["request_count"],
                "cost_usd": round(self.total_cost, 4),
                "errors": self.errors,
                "error_rate": round(self.errors / max(self.total_requests, 1), 4),
                "avg_latency": round(self.avg_latency, 2),
            }


class PromptManager:
    """提示词管理器 - 专业创作框架驱动"""

    NOVEL_PROMPTS = {
        "writer": {
            "system": """你是一位专业的小说作家（Writer Agent），精通叙事学和文学创作理论。

## 写作风格要求（2025-2026前沿网文风格）

### 0. 杜绝老套写法（最重要）
- ❌ 禁止用"只见"、"却说"、"话说"、"忽听"等老旧说书人口吻
- ❌ 禁止用"老夫"、"本座"、"徒儿"等套路化称呼
- ❌ 禁止用"此子"、"此物"、"今日"等文言滥用
- ❌ 禁止用"不愧是"、"果然"、"原来如此"等廉价揭示
- ❌ 禁止开头用"一个阳光明媚的早晨"等老掉牙开场
- ❌ 禁止用"心中暗道"、"心道"、"暗想"等心理公式
- ✅ 用新鲜、现代的叙事节奏和语言风格
- ✅ 用具体细节替代套话，制造独特的阅读体验

### 1. 输出格式要求
- **必须在文章开头添加章节标题**
- 格式：# 第XXX章 标题内容
- 标题要简洁有力，能概括本章核心

### 2. 章节结构（现代网文五幕法）
- **钩子**：开场必须有冲击力——对话开场、动作开场、悬念开场
- **升温**：快速推进，每500字必须有新信息或冲突升级
- **高潮**：每章至少一个"爽点"或"泪点"
- **转折**：安排在2/3处，改变读者预期
- **钩子延续**：结尾留钩子，但不要公式化

### 3. 语言风格（2025前沿网文）
- **反套路**：读者期待的不要给，给他们意想不到的
- **对话生动**：每个人物说话方式不同，要有"口癖"标记
- **网络感**：适当融入当代网络语境，但不要过时梗
- **紧凑叙事**：每段不超过5行，每句话有价值

### 4. 场景构建（感官五维法）
- **视觉**：颜色、光线、形状、动作
- **听觉**：声音、对话、寂静
- **触觉**：温度、质感、疼痛
- **嗅觉**：气味、香气、恶臭
- **味觉**：食物、鲜血、灰尘
每千字至少2种感官，但不能生硬堆砌。

### 5. 角色驱动原则
- 用行动和选择展示角色，而非直接描述
- 角色决策有内在动机和外在压力
- 每个场景角色有明确目标和障碍

### 6. 绝对禁止
- 禁止"突然"、"忽然"作为转折工具
- 禁止过度使用感叹号和省略号
- 禁止直接告诉读者角色的情绪
- 禁止用三句话就能说清楚的事写三段
- 避免过多使用"他想"、"他觉得"等心理描述词
- 避免角色突然获得不该知道的信息

### 7. 内容充实要求（最重要）
- 🔴 **绝不允许重复内容凑字数**。不能换一种说法重复同一件事
- 🔴 **每1000字必须有实质性剧情推进**：新场景/新冲突/新信息/新角色/新对话
- 🔴 **句子级别的丰富性**：同一个场景必须从不同角度、不同细节来写
- 🔴 **段落唯一性原则**：每个段落必须提供前面没有讲过的新信息
- 如果发现自己在重复之前写过的东西，立即切换到新的事件
- 10000字意味着10个不同的场景段落，每个约1000字，不能同一个场景反复描写
- 用"发生了什么新变化？"来检查自己是否在推进剧情

### 创作规则
- 直接输出小说正文，不需要任何解释
- 不要输出"好的"、"以下是"等AI前缀
- 不要输出章节标题以外的元信息
{extra_rules}

## 小说上下文
{context}""",
            "default_rules": "直接输出小说正文，不需要任何解释。"
        },
        "reviewer": {
            "system": """你是一位专业的小说审校（Reviewer Agent），精通文学批评理论。

## 审校框架

### 六维度评分（0-100分制）
1. **结构完整性 (20%)**
   - 章节是否有清晰的起承转合？
   - 开头钩子是否有效？结尾是否引人续读？
   - 节奏是否符合情节需要？

2. **角色一致性 (25%)**
   - 角色言行是否符合其性格设定？
   - 是否存在OOC（out of character）问题？
   - 角色对话是否具有区分度？

3. **叙事节奏 (20%)**
   - 张弛是否得当？是否有拖沓或跳跃？
   - 高潮场景是否有冲击力？
   - 过渡是否自然？

4. **感官细节 (15%)**
   - 场景描写是否立体（五感）？
   - 是否过于抽象缺乏具体意象？
   - 动作描写是否清晰可想象？

5. **对话质量 (10%)**
   - 对话是否自然、有生活感？
   - 是否推动剧情或展示角色？
   - 是否存在过多无效对话？

6. **风格统一 (10%)**
   - 用词、句式、叙事视角是否一致？
   - 是否存在风格突变？

### 常见问题清单
- 角色突然知道不该知道的信息
- 时间线矛盾或空间逻辑错误
- 情感转折缺乏铺垫
- 描写过于抽象而非具体
- 过度使用副词修饰
- 对话过多而动作不足
- 过度使用"突然"、"忽然"

输出JSON：
{{"overall_score":80,"scores":{{"structure":80,"character":85,"rhythm":75,"detail":70,"dialogue":80,"style":80}},"issues":["具体问题描述"],"strengths":["具体优点"],"suggestions":["具体改进建议"]}}""",
        },
        "editor": {
            "system": """你是一位专业的小说编辑（Editor Agent/质量门控）。

## 编辑裁定标准

### 通过条件
- 评分 ≥ 85：直接通过
- 评分 75-84：通过但给修订建议

### 退回条件
- 评分 < 75：退回修订，给出具体问题清单
- 核心逻辑错误：无论分数直接退回

### 编辑原则
1. **不破坏作者风格**：建议必须尊重原作者的声音和意图
2. **关注读者体验**：读者是否能顺畅阅读？是否有困惑之处？
3. **故事逻辑**：剧情是否自洽？角色是否OOC？
4. **优先级排序**：最关键的问题优先处理

输出JSON：
{{"verdict":"pass|pass_with_suggestions|revise","reason":"具体原因","priority_issues":["如果退回，优先修改的问题"]}}""",
        },
        "character": {
            "system": """你是一位专业的小说角色设计师。

## 角色设计框架

### 角色五维度
1. **外在形象**：外貌、穿着、标志性特征、身体语言
2. **内在性格**：核心价值观、恐惧、欲望、内在矛盾
3. **背景故事**：塑造其性格的关键事件、童年创伤、重要关系
4. **行为模式**：习惯、口头禅、小动作、决策方式
5. **关系网络**：与其他角色的连接、冲突、权力动态

### 角色弧线原则
- 每个主要角色必须有至少一个内在转变
- 转变必须有铺垫和催化剂
- 角色弱点必须与剧情核心冲突相关
- 角色目标必须清晰，且面临真实的障碍

### 角色对话设计
- 每个角色应有独特的说话方式
- 对话应体现角色的教育背景、地域、性格
- 避免所有角色说话风格一致

世界观：{settings}
输出JSON格式的角色信息。"""
        },
        "outline": {
            "system": """你是一位专业的小说大纲规划师。

## 大纲规划框架

### 三幕结构
- **第一幕（25%）**：建立常态 → 引入冲突 → 触发事件
- **第二幕（50%）**：冲突升级 → 中点转折 → 危机加深
- **第三幕（25%）**：最终高潮 → 冲突解决 → 新常态

### 章节节奏控制
- 每3-5章安排一个小高潮
- 每卷安排一个大高潮
- 高潮后需要缓冲/过渡章节
- 每章末必须有钩子（悬念/新问题/情感冲击）

### 伏笔管理
- 每个重要伏笔必须有回收计划
- 伏笔回收时读者应有"原来如此"的感觉
- 伏笔不要太明显（避免暗示过度）

### 章节规划要求
- 每章必须有明确的目标（这章要完成什么？）
- 每章必须有至少一个转折或新信息
- 章节间必须有逻辑连接（因果关系）

{context}
输出JSON数组格式的大纲。"""
        },
        "synopsis": {
            "system": """你是一位专业的书籍简介撰写专家。

## 简介撰写框架

### 结构要素（四句话公式）
1. **主角引入**（1句）：谁？什么处境？
2. **核心冲突**（1-2句）：面临什么挑战？对手是谁？
3. **悬念钩子**（1句）：如果失败会怎样？
4. **情感共鸣**（1句）：为什么读者要关心？

### 撰写原则
- 150-300字
- 突出故事亮点和卖点
- 设置悬念，吸引读者
- 不要剧透关键情节
- 使用短句和强烈的动词
- 展示而非叙述（用具体场景而非抽象概括）
"""
        },
        "style_analysis": {
            "system": """你是一位专业的文学风格分析师。

## 风格分析框架

### 分析维度
1. **句式特点**：长句/短句比例、句子结构偏好、节奏感
2. **用词习惯**：词汇丰富度、专业术语、俚语、古语使用
3. **叙事视角**：第一/第三人称、视角切换、可靠性
4. **描写手法**：白描/工笔、感官偏好、意象使用
5. **对话风格**：简洁/冗长、方言、潜台词
6. **节奏感**：紧张/舒缓的控制、段落长度
7. **情感基调**：冷峻/温暖、幽默/严肃、克制/奔放
8. **独特特征**：作者标志性元素、修辞偏好

输出JSON格式的分析结果。"""
        },
        "biography": {
            "system": """你是一位专业的小说传记作家。

## 传记写作框架

### 传记结构（六幕法）
1. **起源**：角色的出生/觉醒/起点
2. **塑造期**：影响其性格的关键事件（童年创伤、重要关系）
3. **成长期**：技能和心智的发展（导师、失败、突破）
4. **转折点**：改变命运的关键决策（两难选择）
5. **高潮期**：角色的重要成就或牺牲
6. **总结**：角色本质、性格反差、对故事的意义

### 写作原则
- 展示而非叙述角色的变化
- 分析性格中的反差和矛盾（表面vs内在）
- 揭示角色行为背后的深层动机
- 每个重要事件必须与角色主线相关

传记要求：
1. 从角色起源开始写起
2. 描述成长历程和心理变化
3. 分析性格特点和反差
4. 结尾总结角色本质"""
        },
    }

    @classmethod
    def get_prompt(cls, name: str, **kwargs) -> str:
        """获取并格式化提示词"""
        template = cls.NOVEL_PROMPTS.get(name, {})
        system = template.get("system", "")
        return system.format(**kwargs) if kwargs else system


class AIClient:
    """统一AI客户端 v3.0 - 生产级接口（Provider 注册表 + 适配器）

    **对外契约不变**：`chat()` / `chat_stream()` 的签名、返回类型与异常语义与 v2
    完全一致 —— 全仓 53 个调用点无需改动，这是硬约束。

    变化全在内部（v3 §3.2 / §4）：

    | v2 | v3 |
    |---|---|
    | `_dispatch_chat` 的 8 路 elif | 查注册表 → 取该 provider 的 adapter |
    | 7 个 `_chat_*` 各自拼请求体 | `adapter.build_request()` |
    | 2 套 `_stream_*` 各自解析 SSE | `adapter.parse_stream_chunk()` |
    | 只有 2 条路径解析 usage | 每个 adapter 各自解析（含 ollama / claude / 流式） |
    | 重试只认 429 | `adapter.is_transient()` 真正生效（含 5xx 与网络错误） |

    **新增一家 OpenAI 兼容 API**：只改 `app/providers/registry.py` 一处。
    v2 时代要同时改 elif 链、`_chat_*`、UI 下拉、`API_PRESETS` 四个地方。
    """

    #: 旧版引用面：provider → 显示信息。**由注册表派生**，不再手工维护第二份。
    PROVIDERS = dict(default_registry().as_providers_dict())

    #: 模型降级链。v3 刷新（§9.10）：移除已退役世代，补上当前在售模型；
    #: 旧世代名**保留映射**，让老配置仍能降级到在售模型而不是直接失败。
    FALLBACK_CHAIN = {
        # --- OpenAI
        "gpt-4o": "gpt-4o-mini",
        "gpt-4-turbo": "gpt-4o-mini",
        "gpt-4.1": "gpt-4o-mini",
        "o4-mini": "gpt-4o-mini",
        # --- Anthropic（当前在售）
        "claude-opus-5": "claude-sonnet-5",
        "claude-sonnet-5": "claude-haiku-4-5",
        "claude-sonnet-4-6": "claude-haiku-4-5",
        "claude-haiku-4-5": None,
        # 已退役世代 → 给出迁移去向，而不是让它彻底失效
        "claude-sonnet-4-20250514": "claude-sonnet-5",
        "claude-3-5-sonnet-20241022": "claude-sonnet-5",
        "claude-3-5-haiku-20241022": "claude-haiku-4-5",
        # --- DeepSeek
        "deepseek-v4-pro": "deepseek-v4-flash",
        "deepseek-chat": "deepseek-v4-flash",       # 2026-07-24 已弃用
        "deepseek-reasoner": "deepseek-v4-pro",
        # --- 智谱 GLM
        "glm-5.3": "glm-5.3-flash",
        "glm-5.2": "glm-5.3-flash",
        "glm-5.1": "glm-5.3-flash",
        "glm-4.7": "glm-4.7-flash",
        "glm-4-plus": "glm-4-flash",
        "glm-4": "glm-4-flash",
        "glm-4-air": "glm-4-flash",
        # --- 通义千问
        "qwen3.7-max": "qwen3-max",
        "qwen3.6-max-preview": "qwen3-max",
        "qwen3-max": "qwen-plus",
        "qwq-plus": "qwen-plus",
        "qwen-plus": "qwen-turbo",
        "qwen-max": "qwen-plus",
        # --- Kimi
        "kimi-k3": "kimi-k2.6",
        "kimi-k2.7-code": "kimi-k2.6",
        "kimi-k2.6": "kimi-k2.5",
        # --- 小米 MiMo
        "mimo-v2.5-pro": "mimo-v2.5",
        "mimo-v2.5": None,
    }

    def __init__(self, config: AppConfig):
        self.config = config
        #: 进程级内置注册表（只读使用）
        self.registry: ProviderRegistry = default_registry()
        self.client = None
        self.metrics = AIMetrics()
        #: 余额结果缓存（60s），避免频繁请求触发限流
        self._balance_cache = BalanceCache()
        self._init_client()

    # ============================================================ 日志

    def _log(self, msg: str):
        """日志记录（静默模式，不影响主流程）"""
        try:
            from loguru import logger
            logger.info(f"[AI] {msg}")
        except Exception as _silent_e:
            logger.debug(f"[ai_client] 捕获异常: {_silent_e}")

    # ============================================================ 配置读取

    # 说明：`self.config` 既可能是 AppConfig，也可能是普通 dict，单测里还可能是
    # MagicMock（对任何 key 都返回 ""）。因此所有非字符串配置一律经下面三个
    # 容错读取器，避免把 "" 塞进 float()/int() 而在构造阶段炸掉。

    @staticmethod
    def _as_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return bool(default)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            value = self.config.get(key, default)
        except Exception:                             # noqa: BLE001
            return float(default)
        if value is None or value == "":
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _cfg_int(self, key: str, default: int) -> int:
        return int(self._cfg_float(key, default))

    # ============================================================ S7 端点校验

    # S7: 允许使用明文 http 的本机地址（本地模型服务 ollama/llama.cpp 等）
    _LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"})

    @classmethod
    def _validate_api_base(cls, url: str) -> str:
        """校验 AI 端点协议：除本机地址外必须使用 https。

        S7: `api_base` 完全来自用户配置且此前不做任何校验，若被写成
        `http://api.example.com`（手误 / 共享配置被篡改 / 第三方预设），
        API Key 会以明文 HTTP 发出。这里直接拒绝而不是静默降级，
        因为静默降级会让"密钥已泄露"这件事变得不可见。
        """
        if not url:
            return url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"AI 端点协议非法: {url!r}（仅支持 http/https），请在设置中修正 api_base"
            )
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "http" and host not in cls._LOCAL_HOSTS:
            raise ValueError(
                f"拒绝向非本机地址 {host!r} 使用明文 HTTP 发送 API Key（{url!r}）；"
                "请改用 https://，或把 api_base 指向 localhost/127.0.0.1 上的本地模型服务"
            )
        return url

    # ============================================================ 端点解析

    def _adapter_for(self, spec: ProviderSpec) -> ProviderAdapter:
        """取 spec 对应的 adapter（注册表内已缓存实例）。"""
        return self.registry.adapter(spec.key)

    def _resolve_endpoint(self, configured: str, model: str, api_base: str):
        """决定「这次请求实际发给谁、发到哪个地址」。

        返回 `(detected_provider, spec, adapter, base_url)`。

        **修 P4**：`_detect_provider` 会按模型名把请求判给 glm/qwen/kimi 等，
        v2 里这些是「伪 provider」—— 有专属参数却没有默认 base_url，
        于是 `enable_thinking` 之类的参数被发到了**别家地址**。
        现在检测到哪家就用哪家的 base_url。

        规则：检测结果与用户配置一致时**尊重用户的 api_base**（代理/中转照常可用）；
        不一致时改用被检测 provider 的默认地址，并留下日志说明原因。
        """
        detected = self._detect_provider(configured, model)
        spec = self.registry.resolve(detected)
        adapter = self._adapter_for(spec)

        if detected == configured:
            base = api_base or spec.base_url
        else:
            base = spec.base_url
            self._log(
                f"模型 {model!r} 判定属于 provider={detected!r}（配置为 {configured!r}），"
                f"本次请求改发该 provider 的默认地址 {base!r}"
                "（避免把该家的专属参数发到别家）"
            )

        # S7: 端点必须校验 —— 校验的是**真正要用的地址**
        base = self._validate_api_base(base)
        return detected, spec, adapter, base

    @staticmethod
    def _merged_headers(adapter: ProviderAdapter, spec: ProviderSpec,
                        api_key: str, prepared=None) -> dict:
        """请求头 = spec 默认头 + adapter 产出头 + 鉴权头。"""
        headers = dict(getattr(spec, "default_headers", {}) or {})
        if prepared is not None:
            headers.update(prepared.headers or {})
        headers.update(adapter.auth_headers(api_key))
        return headers

    # ============================================================ HTTP 客户端

    def _init_client(self):
        provider = self.config.get("api_provider", "ollama")
        api_key = self.config.get("api_key", "") or ""
        api_base = self.config.get("api_base", "") or ""

        spec = self.registry.resolve(provider)
        adapter = self._adapter_for(spec)

        base_url = api_base or spec.base_url

        # S7: 端点必须校验 —— 此前 api_base 完全取自配置、不校验 scheme，
        # 一旦被写成 http://（手误、共享配置被改、第三方预设），
        # `Authorization: Bearer <key>` 会以明文 HTTP 发出。
        base_url = self._validate_api_base(base_url)

        # 能力驱动：是否需要密钥由 spec.auth 声明（修 P4 里"按 provider 名硬编码"的做法）
        no_auth_needed = spec.auth == AuthStyle.NONE
        configured = bool(no_auth_needed or api_key)

        if not configured:
            self.client = None
        else:
            headers = self._merged_headers(adapter, spec, api_key)
            headers.setdefault("Content-Type", "application/json")
            self.client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=self._httpx_timeout(spec),
            )

        # M9: 记录本次构建依据的配置指纹，供 refresh_if_needed 检测变更。
        # 注：单测断言 `client.client.headers` 里的 Authorization 必须随 api_key
        # 变化 —— 所以客户端级鉴权头必须保留（不能只走 per-request header）。
        self._client_fingerprint = (
            provider, api_key, api_base,
            self.config.get("model", ""),
            self._timeout_pair(spec),
        )

    def _timeout_for(self, spec: ProviderSpec) -> float:
        """读超时：用户配置优先，否则用 spec 声明值（修 P9）。

        v2 把 600.0 / 300.0 硬编码在 `_init_client` 里，用户无法调整；
        现在 timeout / connect_timeout 都是配置项。
        """
        return self._cfg_float("timeout", spec.timeout)

    def _connect_timeout_for(self, spec: ProviderSpec) -> float:
        """连接超时（修 P10）：与读超时分设。

        此前 connect 阶段也吃 600s 的读超时：目标域名解析不了或端口没人监听时，
        界面要卡到十分钟才报错。连接阶段单独用一个短超时才是对的。
        """
        return self._cfg_float("connect_timeout", spec.connect_timeout)

    def _timeout_pair(self, spec: ProviderSpec) -> tuple:
        return (self._timeout_for(spec), self._connect_timeout_for(spec))

    def _httpx_timeout(self, spec: ProviderSpec):
        """组装 httpx 的分阶段超时对象。"""
        read, connect = self._timeout_pair(spec)
        try:
            return httpx.Timeout(read, connect=connect)
        except (TypeError, ValueError):
            return read

    def refresh_if_needed(self) -> None:
        """M9: 运行中改完 API Key / 端点后立即生效，无需重启应用。

        此前 `_init_client` 只在 `__init__` 里调用一次，用户在设置里换了 Key
        之后 `self.client` 的默认请求头仍是旧 Key，表现为"改了没生效"。
        """
        provider = self.config.get("api_provider", "ollama")
        spec = self.registry.resolve(provider)
        fingerprint = (
            provider,
            self.config.get("api_key", "") or "",
            self.config.get("api_base", "") or "",
            self.config.get("model", ""),
            self._timeout_pair(spec),
        )
        if fingerprint != getattr(self, "_client_fingerprint", None):
            self._init_client()
            self._log("检测到 AI 配置变更，已重建 HTTP 客户端")

    def is_configured(self) -> bool:
        return self.client is not None

    def get_ollama_models(self) -> List[str]:
        try:
            base_url = self.config.get("api_base", "http://localhost:11434")
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])] if resp.status_code == 200 else []
        except Exception:
            return []

    # ============================================================ 能力与预览

    def capabilities(self, provider: str = "") -> dict:
        """当前（或指定）provider 的能力，供 UI 显隐控件。"""
        key = provider or self.config.get("api_provider", "ollama")
        return self.registry.resolve(key).supports.as_dict()

    def preview_url(self, provider: str = "", model: str = "") -> str:
        """预览本次请求实际会发到的 URL（设置页「请求 URL 预览」按钮）。

        这个功能存在的唯一目的就是消除 P2 那类「路径到底怎么拼」的困惑 ——
        与其写文档解释 `/v1` 要不要补，不如把最终结果直接显示出来。
        """
        provider = provider or self.config.get("api_provider", "ollama")
        model = model or self.config.get("model", "")
        api_base = self.config.get("api_base", "") or ""
        try:
            _detected, spec, _adapter, base = self._resolve_endpoint(provider, model, api_base)
        except ValueError as exc:
            return f"配置有误：{exc}"
        if not base:
            return "（未配置 API 地址）"
        return spec.resolved_url(base)

    def query_balance(self, provider: str = "", use_cache: bool = True):
        """查询余额（设置页「查询余额」按钮）。

        **诚实设计**：没有余额接口的 provider 返回 `supported=False` 的明确结果，
        由 UI 显示「该服务未提供余额接口」，而不是抛异常或显示空白 ——
        后者会让用户误以为功能坏了。
        """
        provider = provider or self.config.get("api_provider", "ollama")
        spec = self.registry.resolve(provider)
        adapter = self._adapter_for(spec)
        api_key = self.config.get("api_key", "") or ""
        api_base = self.config.get("api_base", "") or ""
        base = api_base or spec.base_url

        return adapter.query_balance(
            self._http_get,
            api_key=api_key,
            base_url=base,
            override_url=self.config.get("balance_url", "") or "",
            override_paths={
                "total": self.config.get("balance_total_path", "") or "",
                "currency": self.config.get("balance_currency_path", "") or "",
            },
            cache=self._balance_cache if use_cache else None,
        )

    @staticmethod
    def _http_get(url: str, headers: dict, timeout: float):
        """注入给余额适配器的 HTTP GET（独立出来便于单测替换）。"""
        return httpx.get(url, headers=headers, timeout=timeout)

    def probe_connection(self, provider: str = "", api_base: str = "",
                         api_key: str = "", model: str = "",
                         timeout: float = 30.0) -> dict:
        """用一次**最小请求**验证「端点 + 鉴权 + 模型名」是否真的可用。

        设置页「测试连接」按钮用它。设计要点：

        - 只发 1 个 token 的 ping，成本可忽略；
        - 参数全部可由调用方传入 —— 界面上刚改完还没保存的值也必须能被测试，
          否则用户只能"先保存再试，错了再改"，体验极差；
        - **返回结构化结果而不是抛异常**：失败原因（未填密钥 / DNS 失败 /
          401 / 404 / 响应格式不对）要能显示在同一行文字里，界面不该弹栈。
        """
        provider = provider or self.config.get("api_provider", "ollama")
        model = model or self.config.get("model", "")
        api_key = self.config.get("api_key", "") or "" if api_key is None else api_key

        spec = self.registry.resolve(provider)
        adapter = self._adapter_for(spec)

        try:
            base = self._validate_api_base(api_base or spec.base_url)
        except ValueError as exc:
            return {"ok": False, "url": api_base or spec.base_url, "reason": str(exc)}

        url = spec.resolved_url(base)
        if spec.auth != AuthStyle.NONE and not api_key:
            return {"ok": False, "url": url, "reason": "未填写 API Key"}

        request = ChatRequest(
            model=model or spec.default_model,
            messages=[{"role": "user", "content": "ping"}],
            system="",
            max_tokens=1,
            temperature=0.0,
            stream=False,
        )
        try:
            prepared = adapter.build_request(request)
            headers = self._merged_headers(adapter, spec, api_key, prepared)
        except Exception as exc:                        # noqa: BLE001 - 需原样回报
            return {"ok": False, "url": url, "reason": f"请求构造失败：{exc}"}

        try:
            response = httpx.post(
                url, json=prepared.json_body, headers=headers, timeout=timeout
            )
        except Exception as exc:                        # noqa: BLE001 - 需原样回报
            return {
                "ok": False, "url": url,
                "reason": f"无法连接：{type(exc).__name__}: {exc}",
            }

        if response.status_code >= 400:
            # 只截前 200 字符：错误体里可能回显请求内容，不宜整段展示或落盘
            detail = (response.text or "")[:200]
            return {
                "ok": False, "url": url, "status": response.status_code,
                "reason": self._explain_status(response.status_code, detail),
            }

        try:
            result = adapter.parse_response(response.json())
        except Exception as exc:                        # noqa: BLE001
            return {
                "ok": False, "url": url, "status": response.status_code,
                "reason": f"响应格式无法解析（{type(exc).__name__}）：{exc}",
            }

        return {
            "ok": True, "url": url, "status": response.status_code,
            "model": request.model, "label": adapter.label,
            "sample": result.text.strip()[:60],
        }

    @staticmethod
    def _explain_status(status: int, detail: str) -> str:
        """把 HTTP 状态码翻译成用户能照做的说明。"""
        hints = {
            400: "请求被拒绝（400）：模型名可能不存在，或该模型不支持当前参数",
            401: "鉴权失败（401）：API Key 无效或已过期",
            403: "无权限（403）：该 Key 没有访问此模型的权限",
            404: "地址或路径不存在（404）：检查 API 地址是否需要 /v1，或模型名拼写",
            429: "请求过于频繁（429）：稍后重试，或检查配额",
        }
        hint = hints.get(status) or (f"服务端错误（{status}）" if status >= 500 else f"HTTP {status}")
        return f"{hint}；响应：{detail}" if detail else hint

    # ============================================================ 主入口: chat

    def chat(self, messages: List[Dict], system: str = "", **kwargs) -> str:
        """发送聊天请求 - 带模型降级"""
        # M9: 配置在运行中被改动时重建客户端（否则仍用旧 API Key）
        self.refresh_if_needed()
        if not self.is_configured():
            raise Exception("AI API未配置")

        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        # 修 P9 同类缺陷：这两项设置页一直在写、配置里也一直有，但 v2 的两个入口
        # 都把它们硬编码成 4096 / 0.8 —— 用户"改了温度和输出上限却毫无变化"。
        max_tokens = kwargs.get("max_tokens", self._cfg_int("max_tokens", 4096))
        temperature = kwargs.get("temperature", self._cfg_float("temperature", 0.8))

        # 思考模式参数（修 P9：v2 里这两项从配置读取，但配置层从未定义过它们，
        # 于是永远落到硬编码默认值；现在 config.DEFAULT_CONFIG 已补齐）
        thinking_enabled = kwargs.get(
            "thinking_enabled",
            self._as_bool(self.config.get("thinking_enabled", True), True),
        )
        reasoning_effort = kwargs.get(
            "reasoning_effort", self.config.get("reasoning_effort", "high")
        )

        # 自动检测模型类型，选择正确的provider
        detected_provider = self._detect_provider(provider, model)

        # 前置检查：API Key有效性
        api_key = self.config.get("api_key", "") or ""
        spec = self.registry.resolve(detected_provider)
        if spec.auth != AuthStyle.NONE and (not api_key or len(api_key.strip()) < 8):
            msg = (f"API Key未配置或无效 (provider={detected_provider}, "
                   f"key_len={len(api_key)}). 请在设置中填写有效的API Key。")
            self._log(f"[错误] {msg}")
            raise Exception(msg)

        start = time.time()

        # 🔍 AI诊断日志: 记录API调用（不传入消息全文，仅记录元数据，避免泄露创作内容）
        if _diag_logger:
            _diag_logger.api_call(
                provider=detected_provider,
                endpoint=f"chat/{model}",
                request_data={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "thinking_enabled": thinking_enabled,
                    "messages_count": len(messages)
                }
            )

        try:
            result = self._invoke_chat(
                provider, messages, system, model, max_tokens, temperature,
                thinking_enabled, reasoning_effort,
                api_key=api_key, api_base=self.config.get("api_base", "") or "",
            )

            latency = time.time() - start
            self.metrics.record(latency)

            # 🔍 成功日志
            # M8: 不再记录 `content_preview` —— 与上方「不记录创作内容」的注释直接矛盾，
            # 会把 AI 正文（含用户设定）落到诊断日志文件里。
            if _diag_logger:
                _diag_logger.api_call(
                    provider=detected_provider, endpoint=f"chat/{model}",
                    request_data={"model": model, "messages_count": len(messages)},
                    response_data={"status": "success", "result_len": len(result)},
                    duration_ms=latency * 1000
                )

            # 记录空响应（帮助调试）
            if not result or len(result.strip()) == 0:
                self._log(f"[提示] AI服务返回空响应 (model={model}, latency={latency:.1f}s)")
                raise Exception(f"AI服务返回空响应 (model={model})")

            return result

        except Exception as e:
            latency = time.time() - start
            self.metrics.record(latency, error=True)

            # 检查是否为认证错误（不可重试）
            is_auth_error = False
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status = e.response.status_code
                if status == 401:
                    is_auth_error = True
                    self._log(f"[错误] API认证失败 (401) - 请检查API Key是否有效、是否过期。"
                             f" provider={provider}, model={model}")
                elif status == 403:
                    is_auth_error = True
                    self._log(f"[错误] API权限不足 (403) - 请检查API Key是否有访问该模型的权限。"
                             f" provider={provider}, model={model}")
                elif status == 429:
                    self._log("[错误] API请求过于频繁 (429) - 请稍后重试。")

            # 🔍 失败日志
            if _diag_logger:
                _diag_logger.api_call(
                    provider=provider, endpoint=f"chat/{model}",
                    request_data={"model": model, "messages_count": len(messages)},
                    error=e, duration_ms=latency * 1000
                )

            # 认证错误不重试、不降级
            if is_auth_error:
                raise

            fallback_model = self.FALLBACK_CHAIN.get(model)
            if fallback_model:
                self._log(f"模型降级: {model} -> {fallback_model}")
                # 不修改持久化配置，只在本次请求中使用降级模型
                model = fallback_model
                # 降级只做一次，不递归。provider 仍传用户配置值，
                # 由 _resolve_endpoint 按降级后的模型名重新判定归属。
                try:
                    result = self._invoke_chat(
                        provider, messages, system, model, max_tokens, temperature,
                        thinking_enabled, reasoning_effort,
                        api_key=api_key, api_base=self.config.get("api_base", "") or "",
                    )
                    latency = time.time() - start
                    self.metrics.record(latency)
                    return result
                except Exception as fallback_error:
                    # 降级模型也失败，记录并抛出原始错误（保留完整错误链）
                    self._log(f"降级模型 {model} 也失败: {fallback_error}")
                    self.metrics.record(time.time() - start, error=True)
                    raise e from fallback_error  # 保留完整错误链

            raise

    def _invoke_chat(self, configured: str, messages, system, model, max_tokens,
                     temperature, thinking_enabled, reasoning_effort,
                     api_key: str, api_base: str) -> str:
        """统一执行层：构造请求 → 发送（含重试）→ 解析 → 收尾。

        这是 v2 里 `_dispatch_chat` + 7 个 `_chat_*` + `_dispatch_with_retry`
        三者合并后的唯一入口。

        `configured` 是**用户配置的** provider（不是检测结果）——
        由 `_resolve_endpoint` 结合模型名做最终判定。
        """
        _detected, spec, adapter, base = self._resolve_endpoint(
            configured, model, api_base
        )
        if not base:
            raise Exception(
                f"provider={configured!r} 未配置 API 地址（api_base 为空）。请在设置中填写。"
            )

        request = ChatRequest(
            model=model,
            messages=messages,
            system=system or "",
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            stream=False,
        )

        result = self._send(adapter, spec, base, request, api_key)
        self._record_usage(result.usage, spec.key, model)
        if result.reasoning:
            self._log_thinking(result.reasoning)
        return self._finalize_text(result, adapter.label, model)

    def _send(self, adapter: ProviderAdapter, spec: ProviderSpec, base: str,
              request: ChatRequest, api_key: str):
        """发送请求并对**瞬时故障**做指数退避重试（修 P3）。

        v2 的重试只判 `status == 429`，与 `_is_transient_error` 里写好的判据
        直接矛盾 —— 5xx 与网络错误从未重试过。现在"哪些错误值得重试"由
        adapter 决定（默认即全局判据），并且真正生效。
        """
        url = spec.resolved_url(base)
        max_retries = max(0, self._cfg_int("max_retries", 3))
        delay = 2.0

        for attempt in range(max_retries + 1):
            try:
                prepared = adapter.build_request(request)
                headers = self._merged_headers(adapter, spec, api_key, prepared)
                response = self.client.post(
                    url,
                    json=prepared.json_body,
                    headers=headers,
                    timeout=self._httpx_timeout(spec),
                )
                response.raise_for_status()
                return adapter.parse_response(response.json())
            except Exception as exc:                   # noqa: BLE001 - 需按类型分流
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < max_retries and adapter.is_transient(exc):
                    detail = f", HTTP {status}" if status else ""
                    self._log(
                        f"[重试] 瞬时故障（{type(exc).__name__}{detail}），"
                        f"{delay:.0f}s 后重试 ({attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                raise

    def _finalize_text(self, result, label: str, model: str) -> str:
        """从 ChatResult 取最终文本，并保留 v2 的两条关键兜底语义。

        1. 思考模式把 token 预算耗尽时，`content` 为空而 `reasoning_content` 里
           有完整分析 —— 这时**返回 reasoning 比报错有用**（v2 已有行为，必须保留）。
        2. 其余空响应仍要显式失败，不能静默返回空串（否则上层会写出空章节）。
        """
        if result.text and result.text.strip():
            return result.text
        if result.finish_reason == "length" and len(result.reasoning.strip()) > 10:
            self._log(
                f"[提示] {label}思考模式耗尽token (reasoning_len={len(result.reasoning)})，"
                "使用 reasoning_content 作为结果"
            )
            return result.reasoning
        raise Exception(
            f"{label}返回空内容 (reasoning_len={len(result.reasoning)}, "
            f"finish={result.finish_reason})"
        )

    def _record_usage(self, usage: UsageData, provider: str, model: str) -> None:
        """把 token 用量计入全局统计（修 P6）。

        v2 只有 openai 与 `_parse_thinking_response` 两条路径记录，
        ollama / claude / 全部流式路径**从不记录**；现在每个 adapter 都会解析
        usage，这里统一入账。仅在 provider 真的返回了用量时才记账，
        避免把"没数据"记成"用了 0 个 token"并虚增调用次数。
        """
        if usage is None or usage.total_tokens <= 0:
            return
        cache_note = f", 缓存命中:{usage.cached_tokens}" if usage.cached_tokens else ""
        est_note = ", 估算" if usage.estimated else ""
        token_stats.record(usage.prompt_tokens, usage.completion_tokens)
        self._log(
            f"[Token] provider={provider} model={model} "
            f"本次: {usage.total_tokens} "
            f"(输入:{usage.prompt_tokens} 输出:{usage.completion_tokens}"
            f"{cache_note}{est_note}) | 累计: {token_stats.total_tokens}"
        )

    # ============================================================ 主入口: 流式

    def chat_stream(self, messages: List[Dict], system: str = "",
                    callback: Optional[Callable[[str], None]] = None, **kwargs) -> str:
        """流式聊天 - 实时输出（签名与 v2 一致）。"""
        self.refresh_if_needed()
        if not self.is_configured():
            raise Exception("AI API未配置")

        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        api_key = self.config.get("api_key", "") or ""
        api_base = self.config.get("api_base", "") or ""

        _detected, spec, adapter, base = self._resolve_endpoint(provider, model, api_base)
        if not base:
            raise Exception(
                f"provider={provider!r} 未配置 API 地址（api_base 为空）。请在设置中填写。"
            )

        request = ChatRequest(
            model=model,
            messages=messages,
            system=system or "",
            max_tokens=kwargs.get("max_tokens", self._cfg_int("max_tokens", 4096)),
            temperature=kwargs.get("temperature", self._cfg_float("temperature", 0.8)),
            thinking_enabled=self._as_bool(
                kwargs.get("thinking_enabled", self.config.get("thinking_enabled", True)), True
            ),
            reasoning_effort=kwargs.get(
                "reasoning_effort", self.config.get("reasoning_effort", "high")
            ),
            stream=True,
        )
        return self._stream(adapter, spec, base, request, api_key, callback)

    def _stream(self, adapter: ProviderAdapter, spec: ProviderSpec, base: str,
                request: ChatRequest, api_key: str,
                callback: Optional[Callable[[str], None]]) -> str:
        """流式执行层：分片循环统一，**分片格式由 adapter 解析**（需求 4 的落点）。

        v2 的两套 `_stream_*` 各自硬编码：ollama 读裸 JSON 行、openai 读 `data: `
        前缀。现在 `adapter.parse_stream_chunk()` 负责这个差异，
        Anthropic 的 `event:` / `content_block_delta` 格式也因此能直接接入。
        """
        url = spec.resolved_url(base)
        prepared = adapter.build_request(request)
        headers = self._merged_headers(adapter, spec, api_key, prepared)

        pieces: list = []
        usage: Optional[UsageData] = None

        with self.client.stream(
            prepared.method, url,
            json=prepared.json_body,
            headers=headers,
            timeout=self._httpx_timeout(spec),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    delta = adapter.parse_stream_chunk(line)
                except Exception as exc:               # noqa: BLE001
                    if _diag_logger:
                        _diag_logger.log("API_CALL", "stream_chunk_parse_error", error=exc)
                    continue
                if delta is None:
                    continue
                if delta.text:
                    pieces.append(delta.text)
                    if callback:
                        callback(delta.text)
                if delta.usage is not None and delta.usage.total_tokens > 0:
                    usage = delta.usage
                if delta.done:
                    break

        text = "".join(pieces)
        if usage is not None:
            self._record_usage(usage, spec.key, request.model)
        return text

    # ============================================================ 模型自动检测

    def _detect_provider(self, provider: str, model: str) -> str:
        """根据模型名称自动检测provider，避免用户手动配置错误"""
        model_lower = model.lower()

        # GLM系列（智谱）
        if model_lower.startswith("glm"):
            return "glm"

        # Qwen系列（通义千问）- 包含qwen、qwq
        if "qwen" in model_lower or "qwq" in model_lower:
            return "qwen"

        # Kimi系列（月之暗面）
        if "kimi" in model_lower:
            return "kimi"

        # DeepSeek系列
        if "deepseek" in model_lower:
            return "deepseek"

        # Claude系列
        if "claude" in model_lower or "anthropic" in model_lower:
            return "claude"

        # 回退到用户配置的provider
        return provider

    def _log_thinking(self, reasoning: str):
        """记录思考过程"""
        if _diag_logger:
            _diag_logger.log("THINKING", "reasoning_content", {
                "preview": reasoning[:500],
                "length": len(reasoning)
            })

    # ============================================================ 兼容层

    def _parse_thinking_response(self, result: dict, provider_name: str) -> str:
        """统一解析支持思考模式的API响应。

        **保留原因**：该方法被 8 个单测直接调用，属既有引用面。
        v3 把它的实现改为「走 OpenAI 兼容 adapter」—— 不再与各 `_chat_*`
        各自维护一份重复的解析+兜底逻辑（那正是 P1 要消灭的重复），
        同时保住它原有三条可观测行为：无 choices 报错、usage 记账、
        空 content 但 reasoning 可用时降级返回 reasoning。
        """
        adapter = _label_adapter(provider_name)
        chat_result = adapter.parse_response(result)
        self._record_usage(chat_result.usage, provider_name, "")
        if chat_result.reasoning:
            self._log_thinking(chat_result.reasoning)
        return self._finalize_text(chat_result, provider_name, "")


def _label_adapter(label: str) -> OpenAICompatAdapter:
    """构造一个仅用于解析响应的 OpenAI 兼容 adapter（按 label 缓存）。

    缓存放在**模块级**：`_parse_thinking_response` 会被单测以
    `AIClient.__new__(AIClient)`（跳过 `__init__`）的方式调用，
    若缓存挂在实例上就会 AttributeError。
    """
    adapter = _LABEL_ADAPTERS.get(label)
    if adapter is None:
        spec = ProviderSpec(
            key=f"__parse__:{label}",
            name=label,
            base_url="",
            chat_path="/chat/completions",
        )
        adapter = OpenAICompatAdapter(spec)
        adapter.label = label
        _LABEL_ADAPTERS[label] = adapter
    return adapter
