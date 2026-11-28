"""三个小模块的边角分支：`token_estimator` / `anthropic` / `ollama`。

## 为什么合在一起

它们都小、都属于"**估算或协议适配**"层，但错了的后果不小：

| 模块 | 错了会怎样 |
|---|---|
| `token_estimator` | 低估 ⇒ 请求超窗被服务端拒；高估 ⇒ 白白砍掉上下文 |
| `anthropic` | 多模态分片解析漏掉 ⇒ 返回空文本，用户以为模型没说话 |
| `ollama` | 流式分片判定错 ⇒ 一直等不到 `done`，界面永远转圈 |

三个模块都是"猜错不报错"的类型，所以判据落在**具体数值与返回值形状**上。
"""

from __future__ import annotations

import pytest

from app import token_estimator as te
from app.providers import ollama as ol
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ChatRequest, ProviderSpec, StreamDelta


def _spec(key: str, name: str, path: str, model: str) -> ProviderSpec:
    return ProviderSpec(
        key=key,
        name=name,
        base_url=f"https://{key}.example",
        default_model=model,
        models=[model],
        chat_path=path,
    )


SPEC = _spec("anthropic", "Anthropic", "/v1/messages", "claude-3")
OLLAMA_SPEC = _spec("ollama", "Ollama", "/api/chat", "qwen")


class TestTokenEstimatorFlatten:
    """多模态 content 压平 —— 图片不计 token 会严重低估。"""

    def test_none_becomes_empty(self):
        assert te._flatten_content(None) == ""

    def test_plain_string_passthrough(self):
        assert te._flatten_content("你好") == "你好"

    def test_text_blocks_are_joined(self):
        content = [{"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}]

        assert te._flatten_content(content) == "第一段\n第二段"

    def test_image_block_gets_conservative_weight(self):
        """非文本分片按固定 256 字符估 —— 完全不计会让长图对话超窗。"""
        flat = te._flatten_content([{"type": "image", "source": "..."}])

        assert len(flat) == 256

    def test_bare_string_items_are_included(self):
        assert te._flatten_content(["裸字符串"]) == "裸字符串"

    def test_unknown_item_types_ignored(self):
        assert te._flatten_content([123, None]) == ""

    def test_other_types_stringified(self):
        assert te._flatten_content(42) == "42"


class TestCharsForContextWindow:
    @pytest.mark.parametrize("tokens", ["不是数字", None, object()])
    def test_bad_tokens_return_zero(self, tokens):
        assert te.chars_for_context_window(tokens) == 0

    def test_zero_divisor_falls_back_to_default(self):
        """除数为 0 时用默认安全系数，而不是 ZeroDivisionError。"""
        result = te.chars_for_context_window(32000, safety_divisor=0)

        # 0 会被 `or` 吃掉 ⇒ 回落默认除数；返回值是"按安全系数折算后的 token 数"
        assert result == int(32000 / te.CONTEXT_SAFETY_DIVISOR)

    def test_normal(self):
        assert te.chars_for_context_window(32000) > 0


class TestAnthropicRequest:
    def _adapter(self):
        return AnthropicAdapter(SPEC)

    def test_stream_flag(self):
        req = ChatRequest(messages=[{"role": "user", "content": "hi"}], model="claude-3", max_tokens=64, stream=True)

        body = self._adapter().build_request(req).json_body

        assert body["stream"] is True

    def test_extra_merged_into_body(self):
        """`extra` 用于透传厂商参数（如 `top_k`），不合并就等于没传。"""
        req = ChatRequest(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-3",
            max_tokens=64,
            extra={"top_k": 5},
        )

        body = self._adapter().build_request(req).json_body

        assert body["top_k"] == 5

    def test_system_included(self):
        req = ChatRequest(
            messages=[{"role": "user", "content": "hi"}], model="claude-3", max_tokens=64, system="你是编辑"
        )

        assert self._adapter().build_request(req).json_body["system"] == "你是编辑"


class TestAnthropicStreamParse:
    def _adapter(self):
        return AnthropicAdapter(SPEC)

    @pytest.mark.parametrize("line", ["", "event: ping", "not-data", "data"])
    def test_non_data_lines_ignored(self, line):
        assert self._adapter().parse_stream_chunk(line) is None

    def test_done_marker(self):
        delta = self._adapter().parse_stream_chunk("data: [DONE]")

        assert isinstance(delta, StreamDelta)
        assert delta.done is True

    def test_invalid_json_returns_none(self):
        """坏分片只丢弃 —— 抛异常会让整个流中断。"""
        assert self._adapter().parse_stream_chunk("data: {不是json") is None


class TestAnthropicResponseBlocks:
    def _adapter(self):
        return AnthropicAdapter(SPEC)

    def test_no_text_block_falls_back_to_first(self):
        """全是非 text 块时退化成取第一块的内容，而不是返回空串。"""
        data = {
            "content": [{"type": "tool_use", "text": "备用内容"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "model": "claude-3",
            "stop_reason": "end_turn",
        }

        result = self._adapter().parse_response(data)

        assert "备用内容" in result.text

    def test_non_dict_first_block_is_safe(self):
        data = {
            "content": ["裸字符串"],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "model": "claude-3",
            "stop_reason": "end_turn",
        }

        result = self._adapter().parse_response(data)

        assert isinstance(result.text, str)


class TestOllama:
    """Ollama 的流式协议是 NDJSON（每行一个 JSON），与 OpenAI 的 `data:` 不同。"""

    def test_parse_stream_chunk_done(self):
        adapter = ol.OllamaAdapter(OLLAMA_SPEC)

        delta = adapter.parse_stream_chunk('{"done": true}')

        assert isinstance(delta, StreamDelta)
        assert delta.done is True

    def test_parse_stream_chunk_text(self):
        adapter = ol.OllamaAdapter(OLLAMA_SPEC)

        delta = adapter.parse_stream_chunk('{"message": {"content": "你好"}, "done": false}')

        assert delta is not None
        assert delta.text == "你好"

    @pytest.mark.parametrize("line", ["", "{坏", "null"])
    def test_parse_stream_chunk_garbage(self, line):
        adapter = ol.OllamaAdapter(OLLAMA_SPEC)

        assert adapter.parse_stream_chunk(line) is None
