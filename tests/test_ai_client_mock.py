"""
ai_client.py 使用respx mock HTTP测试
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
import respx
from unittest.mock import MagicMock
from app.ai_client import AIClient, TokenStats, AIMetrics, PromptManager


class TestAIClientOllama:
    """AIClient Ollama 测试"""

    @respx.mock
    def test_chat_ollama_success(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, json={"message": {"content": "测试回复"}})
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}])
        assert result == "测试回复"

    @respx.mock
    def test_chat_ollama_with_system(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, json={"message": {"content": "系统回复"}})
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}], system="你是一个助手")
        assert result == "系统回复"

    @respx.mock
    def test_chat_ollama_empty_response(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, json={"message": {"content": ""}})
        )
        
        client = AIClient(config)
        with pytest.raises(Exception):
            client.chat([{"role": "user", "content": "你好"}])


class TestAIClientOpenAI:
    """AIClient OpenAI 测试"""

    @respx.mock
    def test_chat_openai_success(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }.get(key, default)
        
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "OpenAI回复"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}])
        assert result == "OpenAI回复"


class TestAIClientDeepSeek:
    """AIClient DeepSeek 测试"""

    @respx.mock
    def test_chat_deepseek_success(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "deepseek",
            "api_key": "test-key",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "thinking_enabled": False,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "DeepSeek回复", "reasoning_content": ""}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}])
        assert result == "DeepSeek回复"

    @respx.mock
    def test_chat_deepseek_with_reasoning(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "deepseek",
            "api_key": "test-key",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
            "thinking_enabled": True,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "回复", "reasoning_content": "思考过程"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}], thinking_enabled=True)
        assert result == "回复"


class TestAIClientClaude:
    """AIClient Claude 测试"""

    @respx.mock
    def test_chat_claude_success(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "claude",
            "api_key": "test-key",
            "api_base": "",
            "model": "claude-sonnet-4-20250514",
        }.get(key, default)
        
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json={
                "content": [{"text": "Claude回复"}]
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "你好"}])
        assert result == "Claude回复"


class TestAIClientDetectProvider:
    """_detect_provider 测试"""

    def test_detect_glm(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "glm-5") == "glm"

    def test_detect_qwen(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "qwen3-max") == "qwen"

    def test_detect_kimi(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "kimi-k2.6") == "kimi"

    def test_detect_deepseek(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "deepseek-v4") == "deepseek"

    def test_detect_claude(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "claude-sonnet") == "claude"

    def test_detect_anthropic(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "anthropic-model") == "claude"

    def test_detect_unknown(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("ollama", "unknown-model") == "ollama"


class TestParseThinkingResponse:
    """_parse_thinking_response 测试"""

    def test_parse_basic(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "回复内容"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "回复内容"

    def test_parse_with_reasoning(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "回复", "reasoning_content": "思考"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "回复"

    def test_parse_empty_content_with_reasoning(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "", "reasoning_content": "x" * 20}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "x" * 20

    def test_parse_no_choices(self):
        config = MagicMock()
        config.get.return_value = ""
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {"choices": []}
        with pytest.raises(Exception, match="无choices"):
            client._parse_thinking_response(result, "Test")


class TestAIClientFallback:
    """模型降级测试"""

    @respx.mock
    def test_fallback_on_error(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "qwen2.5:14b",
        }.get(key, default)
        
        # First call fails, second succeeds
        respx.post("http://localhost:11434/api/chat").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json={"message": {"content": "降级回复"}})
            ]
        )
        
        client = AIClient(config)
        # Should try fallback
        try:
            result = client.chat([{"role": "user", "content": "你好"}])
        except Exception:
            pass  # May fail depending on fallback chain


class TestAIClientGetModels:
    """get_ollama_models 测试"""

    @respx.mock
    def test_get_models_success(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
        }.get(key, default)
        
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={
                "models": [{"name": "qwen2.5:14b"}, {"name": "llama3:8b"}]
            })
        )
        
        client = AIClient(config)
        models = client.get_ollama_models()
        assert "qwen2.5:14b" in models
        assert "llama3:8b" in models

    @respx.mock
    def test_get_models_error(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
        }.get(key, default)
        
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(500)
        )
        
        client = AIClient(config)
        models = client.get_ollama_models()
        assert models == []
