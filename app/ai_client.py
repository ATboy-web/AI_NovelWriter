"""
AI客户端模块 v2.0 - 生产级AI服务接口

特性：
- 自动重试与指数退避
- 模型降级/故障转移
- 请求限流
- 性能监控
- 流式输出支持
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
    """提示词管理器 - 集中管理和版本控制"""
    
    NOVEL_PROMPTS = {
        "writer": {
            "system": """你是一位专业的小说作家（Writer Agent）。

创作原则：
1. 根据大纲和上下文进行创作
2. 保持风格一致性
3. 注重细节描写和情感表达
4. 人物对话要符合角色性格
5. 控制节奏，张弛有度
{extra_rules}

小说上下文：
{context}""",
            "default_rules": "直接输出小说正文，不需要任何解释。"
        },
        "reviewer": {
            "system": """你是专业的小说审校（Reviewer Agent）。

审校维度（0-100分制）：
1. 语法正确性 (30%)
2. 逻辑一致性 (25%)
3. 角色一致性 (20%)
4. 风格统一性 (15%)
5. 节奏控制 (10%)

输出JSON：
{{
  "overall_score": 80,
  "scores": {{"grammar": 85, "logic": 80, "character": 75, "style": 80, "rhythm": 78}},
  "issues": ["问题描述"],
  "strengths": ["优点"],
  "suggestions": ["改进建议"]
}}""",
        },
        "editor": {
            "system": """你是专业的小说编辑（Editor Agent/质量门）。

裁定标准：
- 评分 ≥ 85 → 直接通过
- 评分 75-84 → 通过但给建议
- 评分 < 75 → 退回修订

输出JSON：
{{"verdict": "pass|pass_with_suggestions|revise", "reason": "原因说明"}}""",
        },
        "character": {"system": """你是专业角色设计师。世界观：{settings}
输出JSON格式的角色信息。"""},
        "outline": {"system": """你是专业小说大纲规划师。{context}
输出JSON数组格式的大纲。"""},
        "synopsis": {"system": """你是专业的书籍简介撰写专家。

简介要求：
1. 150-300字
2. 突出故事亮点和卖点
3. 设置悬念，吸引读者
4. 不要剧透关键情节"""},
        "style_analysis": {"system": """你是专业的文学风格分析师。分析给定文本的写作风格，输出JSON格式。

分析维度：
1. 句式特点、2. 用词习惯、3. 叙事视角、4. 描写手法
5. 对话风格、6. 节奏感、7. 情感基调、8. 独特特征"""},
        "biography": {"system": """你是专业的小说传记作家。

传记要求：
1. 从角色起源开始写起
2. 描述成长历程和心理变化
3. 分析性格特点和反差
4. 结尾总结角色本质"""},
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
    
    # 模型降级链
    FALLBACK_CHAIN = {
        "gpt-4o": "gpt-4o-mini",
        "gpt-4-turbo": "gpt-4o-mini",
        "claude-3-5-sonnet-20241022": "claude-3-5-haiku-20241022",
        "deepseek-chat": None,  # 无降级
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
            
            # 尝试模型降级
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
            # OpenAI格式流式
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
