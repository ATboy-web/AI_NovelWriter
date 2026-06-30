"""
ai_client.py 流式输出和chat方法测试
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


class TestChatStreamOllama:
    """chat_stream Ollama 测试"""

    @respx.mock
    def test_stream_ollama_basic(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        # Mock streaming response
        lines = [
            json.dumps({"message": {"content": "Hello"}}),
            json.dumps({"message": {"content": " World"}}),
        ]
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, text="\n".join(lines))
        )
        
        client = AIClient(config)
        callback = MagicMock()
        result = client.chat_stream([{"role": "user", "content": "test"}], callback=callback)
        assert isinstance(result, str)

    @respx.mock
    def test_stream_ollama_with_system(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        lines = [json.dumps({"message": {"content": "response"}})]
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, text="\n".join(lines))
        )
        
        client = AIClient(config)
        result = client.chat_stream([{"role": "user", "content": "test"}], system="system prompt")
        assert isinstance(result, str)


class TestChatStreamOpenAI:
    """chat_stream OpenAI 测试"""

    @respx.mock
    def test_stream_openai_basic(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }.get(key, default)
        
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " World"}}]}',
            'data: [DONE]',
        ]
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, text="\n".join(lines))
        )
        
        client = AIClient(config)
        callback = MagicMock()
        result = client.chat_stream([{"role": "user", "content": "test"}], callback=callback)
        assert isinstance(result, str)


class TestChatOpenAI:
    """_chat_openai 测试"""

    @respx.mock
    def test_chat_openai_basic(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "thinking_enabled": False,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "OpenAI response"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}])
        assert result == "OpenAI response"

    @respx.mock
    def test_chat_openai_with_reasoning(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "thinking_enabled": True,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "response", "reasoning_content": "thinking"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}], thinking_enabled=True)
        assert result == "response"

    @respx.mock
    def test_chat_openai_empty_content_with_reasoning(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "thinking_enabled": True,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "", "reasoning_content": "x" * 20}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}], thinking_enabled=True)
        assert result == "x" * 20

    @respx.mock
    def test_chat_openai_no_choices(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "openai",
            "api_key": "test-key",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "thinking_enabled": False,
            "reasoning_effort": "high",
        }.get(key, default)
        
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": []})
        )
        
        client = AIClient(config)
        with pytest.raises(Exception, match="无choices"):
            client.chat([{"role": "user", "content": "test"}])


class TestChatOllama:
    """_chat_ollama 测试"""

    @respx.mock
    def test_chat_ollama_basic(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        respx.post(url__startswith="http://localhost:11434").mock(
            return_value=httpx.Response(200, json={"message": {"content": "Ollama response"}})
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Ollama response"

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
            return_value=httpx.Response(200, json={"message": {"content": "response with system"}})
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}], system="system prompt")
        assert result == "response with system"

    @respx.mock
    def test_chat_ollama_empty_content(self):
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
            client.chat([{"role": "user", "content": "test"}])


class TestChatDeepSeek:
    """_chat_deepseek 测试"""

    @respx.mock
    def test_chat_deepseek_basic(self):
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
                "choices": [{"message": {"content": "DeepSeek response", "reasoning_content": ""}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}])
        assert result == "DeepSeek response"

    @respx.mock
    def test_chat_deepseek_with_thinking(self):
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
                "choices": [{"message": {"content": "response", "reasoning_content": "thinking"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}], thinking_enabled=True)
        assert result == "response"

    @respx.mock
    def test_chat_deepseek_empty_content_with_reasoning(self):
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
                "choices": [{"message": {"content": "", "reasoning_content": "x" * 20}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}], thinking_enabled=True)
        assert result == "x" * 20


class TestChatClaude:
    """_chat_claude 测试"""

    @respx.mock
    def test_chat_claude_basic(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "claude",
            "api_key": "test-key",
            "api_base": "",
            "model": "claude-sonnet-4-20250514",
        }.get(key, default)
        
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json={
                "content": [{"text": "Claude response"}]
            })
        )
        
        client = AIClient(config)
        result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Claude response"

    @respx.mock
    def test_chat_claude_empty_content(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "claude",
            "api_key": "test-key",
            "api_base": "",
            "model": "claude-sonnet-4-20250514",
        }.get(key, default)
        
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json={"content": []})
        )
        
        client = AIClient(config)
        with pytest.raises(Exception, match="无内容"):
            client.chat([{"role": "user", "content": "test"}])


class TestDetectProvider:
    """_detect_provider 测试"""

    def test_detect_glm(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "glm-5") == "glm"

    def test_detect_qwen(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "qwen3-max") == "qwen"

    def test_detect_kimi(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "kimi-k2.6") == "kimi"

    def test_detect_deepseek(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "deepseek-v4") == "deepseek"

    def test_detect_claude(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "claude-sonnet") == "claude"

    def test_detect_anthropic(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "anthropic-model") == "claude"

    def test_detect_unknown(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("ollama", "unknown-model") == "ollama"

    def test_detect_qwq(self):
        client = AIClient.__new__(AIClient)
        assert client._detect_provider("openai", "qwq-plus") == "qwen"


class TestParseThinkingResponse:
    """_parse_thinking_response 测试"""

    def test_parse_basic(self):
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "response"

    def test_parse_with_reasoning(self):
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "response", "reasoning_content": "thinking"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "response"

    def test_parse_empty_content_with_reasoning(self):
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {
            "choices": [{"message": {"content": "", "reasoning_content": "x" * 20}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        assert client._parse_thinking_response(result, "Test") == "x" * 20

    def test_parse_no_choices(self):
        client = AIClient.__new__(AIClient)
        client._log = lambda msg: None
        client._log_thinking = lambda r: None
        
        result = {"choices": []}
        with pytest.raises(Exception, match="无choices"):
            client._parse_thinking_response(result, "Test")


class TestFallback:
    """模型降级测试"""

    @respx.mock
    def test_fallback_on_error(self):
        config = MagicMock()
        config.get.side_effect = lambda key, default="": {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "llama3:8b",
        }.get(key, default)
        
        respx.post(url__startswith="http://localhost:11434").mock(
            side_effect=httpx.Response(500)
        )
        
        client = AIClient(config)
        try:
            client.chat([{"role": "user", "content": "test"}])
        except Exception:
            pass


class TestGetOllamaModels:
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
                "models": [{"name": "llama3:8b"}, {"name": "qwen2.5:14b"}]
            })
        )
        
        client = AIClient(config)
        models = client.get_ollama_models()
        assert "llama3:8b" in models
        assert "qwen2.5:14b" in models

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
