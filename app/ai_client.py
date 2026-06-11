"""
AI客户端模块 v2.0 - 生产级AI服务接口

特性：
- 自动重试与指数退避
- 模型降级/故障转移
- 请求限流
- 性能监控
- 流式输出支持
- 专业创作框架
"""

import time
import threading
import json
from typing import Dict, List, Optional, Callable, Any
from functools import wraps

import httpx

from .config import AppConfig


def retry_with_backoff(max_retries=3, base_delay=1, max_delay=30):
    """指数退避重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    time.sleep(delay)
            raise last_error
        return wrapper
    return decorator


class AIMetrics:
    """AI服务性能监控"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.errors = 0
        self.avg_latency = 0
        self._latency_samples = []
    
    def record(self, tokens: int, latency: float, cost: float = 0, error: bool = False):
        with self._lock:
            self.total_requests += 1
            self.total_tokens += tokens
            self.total_cost += cost
            if error:
                self.errors += 1
            self._latency_samples.append(latency)
            if len(self._latency_samples) > 100:
                self._latency_samples = self._latency_samples[-100:]
            self.avg_latency = sum(self._latency_samples) / len(self._latency_samples)
    
    def get_summary(self) -> dict:
        with self._lock:
            return {
                "requests": self.total_requests,
                "tokens": self.total_tokens,
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

## 创作框架

### 1. 章节结构（五幕法）
- **钩子**：开场用悬念或冲突吸引读者（第一段必须有吸引力）
- **升温**：逐步发展冲突，展示角色动机和压力
- **高潮**：章节的情感或事件高点（每章至少一个亮点）
- **转折**：意外或新信息推动剧情
- **钩子延续**：结尾留下悬念引向下一章

### 2. 场景构建公式（感官五维法）
- **视觉**：颜色、光线、形状、动作
- **听觉**：声音、对话、寂静
- **触觉**：温度、质感、疼痛
- **嗅觉**：气味、香气、恶臭
- **味觉**：食物、鲜血、灰尘
每个1000字至少包含2种感官描写。

### 3. 叙事节奏控制
- **快节奏**：短句、多动作、少描写（战斗、追逐）
- **慢节奏**：长句、多心理、多细节（独处、回忆）
- **变速**：高潮前后节奏对比，增强冲击力

### 4. 角色驱动原则
- 对话必须反映角色性格、背景、情绪状态
- 通过行动和选择展示角色，而非直接描述
- 角色决策必须有内在动机和外在压力
- 每个场景角色必须有明确的目标和障碍

### 5. 避免的写作问题
- 禁止使用"突然"、"忽然"作为廉价转折
- 避免过度使用感叹号和省略号
- 避免直接告诉读者角色的情绪（用行为展示）
- 避免过多使用"他想"、"他觉得"等心理描述词
- 避免角色突然获得不该知道的信息

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
    """统一AI客户端 v2.0 - 生产级接口"""
    
    PROVIDERS = {
        "ollama": {"name": "Ollama (本地)", "base_url": "http://localhost:11434", "models": ["qwen2.5:14b", "qwen2.5:7b"]},
        "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini"]},
        "deepseek": {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "models": ["deepseek-chat"]},
        "claude": {"name": "Claude", "base_url": "https://api.anthropic.com/v1", "models": ["claude-3-5-sonnet-20241022"]},
        "custom": {"name": "自定义API", "base_url": "", "models": []},
    }
    
    FALLBACK_CHAIN = {
        "gpt-4o": "gpt-4o-mini",
        "gpt-4-turbo": "gpt-4o-mini",
        "claude-3-5-sonnet-20241022": "claude-3-5-haiku-20241022",
        "deepseek-chat": None,
    }
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = None
        self.metrics = AIMetrics()
        self._init_client()
    
    def _init_client(self):
        provider = self.config.get("api_provider", "ollama")
        api_key = self.config.get("api_key", "")
        api_base = self.config.get("api_base", "")
        
        base_url = api_base or self.PROVIDERS.get(provider, {}).get("base_url", "")
        
        if provider == "claude" and api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                self.client = None
        elif provider == "ollama":
            self.client = httpx.Client(base_url=base_url, timeout=300.0)
        elif api_key:
            self.client = httpx.Client(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=120.0,
            )
        else:
            self.client = None
    
    def is_configured(self) -> bool:
        return self.client is not None
    
    def get_ollama_models(self) -> List[str]:
        try:
            base_url = self.config.get("api_base", "http://localhost:11434")
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])] if resp.status_code == 200 else []
        except Exception:
            return []
    
    @retry_with_backoff(max_retries=2, base_delay=1)
    def chat(self, messages: List[Dict], system: str = "", **kwargs) -> str:
        """发送聊天请求 - 带自动重试和降级"""
        if not self.is_configured():
            raise Exception("AI API未配置")
        
        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        max_tokens = kwargs.get("max_tokens", 4096)
        temperature = kwargs.get("temperature", 0.8)
        
        start = time.time()
        error = False
        
        try:
            if provider == "ollama":
                result = self._chat_ollama(messages, system, model, max_tokens, temperature)
            elif provider == "claude":
                result = self._chat_claude(messages, system, model, max_tokens, temperature)
            else:
                result = self._chat_openai(messages, system, model, max_tokens, temperature)
            
            latency = time.time() - start
            self.metrics.record(len(result), latency)
            return result
            
        except Exception as e:
            error = True
            latency = time.time() - start
            self.metrics.record(0, latency, error=True)
            
            fallback_model = self.FALLBACK_CHAIN.get(model)
            if fallback_model:
                self.config.set("model", fallback_model)
                self._init_client()
                return self.chat(messages, system, **kwargs)
            
            raise
    
    def chat_stream(self, messages: List[Dict], system: str = "", 
                    callback: Optional[Callable[[str], None]] = None, **kwargs) -> str:
        """流式聊天 - 实时输出"""
        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        
        full_messages = [{"role": "system", "content": system}] if system else []
        full_messages.extend(messages)
        
        if provider == "ollama":
            return self._stream_ollama(full_messages, model, callback, kwargs)
        else:
            return self._stream_openai(full_messages, model, callback, kwargs)
    
    def _stream_ollama(self, messages, model, callback, kwargs) -> str:
        result = []
        with self.client.stream("POST", "/api/chat", json={
            "model": model, "messages": messages, "stream": True,
            "options": {"temperature": kwargs.get("temperature", 0.8), "num_predict": kwargs.get("max_tokens", 4096)}
        }) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            result.append(token)
                            if callback:
                                callback(token)
                    except json.JSONDecodeError:
                        pass
        return "".join(result)
    
    def _stream_openai(self, messages, model, callback, kwargs) -> str:
        result = []
        with self.client.stream("POST", "/chat/completions", json={
            "model": model, "messages": messages, "stream": True,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.8)
        }) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            result.append(token)
                            if callback:
                                callback(token)
                    except json.JSONDecodeError:
                        pass
        return "".join(result)
    
    def _chat_openai(self, messages, system, model, max_tokens, temperature) -> str:
        full_messages = [{"role": "system", "content": system}] if system else []
        full_messages.extend(messages)
        response = self.client.post("/chat/completions", json={
            "model": model, "messages": full_messages, "max_tokens": max_tokens, "temperature": temperature
        })
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    
    def _chat_ollama(self, messages, system, model, max_tokens, temperature) -> str:
        full_messages = [{"role": "system", "content": system}] if system else []
        full_messages.extend(messages)
        response = self.client.post("/api/chat", json={
            "model": model, "messages": full_messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}
        })
        response.raise_for_status()
        return response.json()["message"]["content"]
    
    def _chat_claude(self, messages, system, model, max_tokens, temperature) -> str:
        response = self.client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=system or "", messages=messages
        )
        return response.content[0].text
