"""
AI客户端模块 - 统一AI API接口
"""

from typing import Dict, List

import httpx

from .config import AppConfig


class AIClient:
    """统一AI客户端"""
    
    PROVIDERS = {
        "ollama": {
            "name": "Ollama (本地)",
            "base_url": "http://localhost:11434",
            "models": ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "deepseek-r1:14b", "glm4:9b"],
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-reasoner"],
        },
        "claude": {
            "name": "Claude",
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        },
        "custom": {
            "name": "自定义API",
            "base_url": "",
            "models": [],
        },
    }
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = None
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
                pass
        elif provider == "ollama":
            # Ollama不需要API密钥
            self.client = httpx.Client(base_url=base_url, timeout=300.0)
        elif api_key:
            self.client = httpx.Client(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=120.0,
            )
    
    def is_configured(self) -> bool:
        provider = self.config.get("api_provider", "ollama")
        if provider == "ollama":
            return self.client is not None
        return self.client is not None and self.config.get("api_key", "")
    
    def get_ollama_models(self) -> List[str]:
        """获取Ollama本地模型列表"""
        try:
            base_url = self.config.get("api_base", "http://localhost:11434")
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return [m["name"] for m in models]
        except Exception:
            pass
        return []
    
    def chat(self, messages: List[Dict], system: str = "", **kwargs) -> str:
        """发送聊天请求"""
        if not self.is_configured():
            raise Exception("AI API未配置，请在设置中配置API密钥")
        
        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 4096))
        temperature = kwargs.get("temperature", self.config.get("temperature", 0.8))
        
        if provider == "claude":
            return self._chat_claude(messages, system, model, max_tokens, temperature)
        elif provider == "ollama":
            return self._chat_ollama(messages, system, model, max_tokens, temperature)
        else:
            return self._chat_openai(messages, system, model, max_tokens, temperature)
    
    def _chat_openai(self, messages, system, model, max_tokens, temperature) -> str:
        """OpenAI兼容接口"""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        
        response = self.client.post("/chat/completions", json={
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    
    def _chat_ollama(self, messages, system, model, max_tokens, temperature) -> str:
        """Ollama本地模型接口"""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        
        response = self.client.post("/api/chat", json={
            "model": model,
            "messages": full_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        })
        response.raise_for_status()
        return response.json()["message"]["content"]
    
    def _chat_claude(self, messages, system, model, max_tokens, temperature) -> str:
        """Claude接口"""
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=messages,
        )
        return response.content[0].text
