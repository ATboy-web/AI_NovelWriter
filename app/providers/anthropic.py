"""Anthropic Claude 适配器。

与 OpenAI 系的差异（需求 4 的典型场景）：
- 路径是 `/v1/messages`（不是 `/chat/completions`）
- 鉴权是 `x-api-key` + `anthropic-version` 头（不是 `Authorization: Bearer`）
- **`system` 是顶层字段**，不能放进 messages
- **`max_tokens` 必填**
- 响应是 `content: [{type, text}, ...]` 块数组（不是 `choices`）
- usage 字段名是 `input_tokens` / `output_tokens`

⚠️ 修 P1：旧实现在 `_init_client` 里对 claude 分支**硬编码**
`base_url="https://api.anthropic.com"`，把用户配置的 `api_base` 整个丢弃 ——
用户无法为 Claude 配置中转/代理地址。现在 base_url 与其他 provider 一视同仁，
由 `spec.base_url` / 用户配置决定。
"""

from __future__ import annotations

import json

from .base import (
    ChatRequest,
    ChatResult,
    PreparedRequest,
    ProviderAdapter,
    UsageData,
)

__all__ = ["AnthropicAdapter"]


class AnthropicAdapter(ProviderAdapter):
    """Anthropic Messages API。"""

    label = "Claude"

    def build_request(self, req: ChatRequest) -> PreparedRequest:
        # Anthropic 的 messages 里不能有 system 角色
        messages = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in req.messages
        ]
        body = {
            "model": req.model,
            "max_tokens": req.max_tokens,   # 必填
            "system": req.system or "",
            "messages": messages,
            "temperature": req.temperature,
        }
        if req.stream:
            body["stream"] = True
        if req.extra:
            body.update(req.extra)
        return PreparedRequest(
            path=self.spec.chat_path,
            json_body=body,
            headers=dict(self.spec.default_headers),
        )

    def parse_response(self, data: dict) -> ChatResult:
        blocks = data.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise Exception(
                f"{self.label}返回无内容: {json.dumps(data, ensure_ascii=False)[:200]}"
            )

        # 只取 text 块：content 里可能混有 thinking / tool_use 块，
        # 旧实现硬取 blocks[0] —— 若首块是 thinking 就会返回空字符串。
        texts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type", "text") == "text"
        ]
        if not texts:
            texts = [blocks[0].get("text", "")] if isinstance(blocks[0], dict) else [""]

        return ChatResult(
            text="".join(texts),
            usage=self._parse_usage(data.get("usage")),
            finish_reason=data.get("stop_reason", "") or "",
            raw=data,
        )

    def _parse_usage(self, usage) -> UsageData:
        """P6：Claude 的 usage 此前**完全没被解析**（token 统计缺一条路径）。"""
        if not isinstance(usage, dict):
            return UsageData()
        return UsageData(
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=0,  # 由基类按 input+output 求和
            cached_tokens=usage.get("cache_read_input_tokens", 0) or 0,
        )

    def parse_stream_chunk(self, line: str):
        """Anthropic SSE：`event: ...\\ndata: {...}`，分片在 `content_block_delta`。

        与 OpenAI 的 `data: {...}` 单行格式不同，因此必须独立实现。
        """
        if not line or not line.startswith("data: "):
            return None
        payload = line[6:].strip()
        if payload == "[DONE]":
            from .base import StreamDelta

            return StreamDelta(done=True)
        try:
            chunk = json.loads(payload)
        except (ValueError, TypeError):
            return None

        from .base import StreamDelta

        chunk_type = chunk.get("type", "")
        if chunk_type == "content_block_delta":
            delta = chunk.get("delta", {}) or {}
            return StreamDelta(text=delta.get("text", "") or "")
        if chunk_type == "message_delta":
            usage = chunk.get("usage") or {}
            return StreamDelta(
                usage=UsageData(
                    completion_tokens=usage.get("output_tokens", 0),
                )
            )
        if chunk_type == "message_stop":
            return StreamDelta(done=True)
        return None
