"""Ollama 本地模型适配器。

与 OpenAI 系的差异：
- 路径 `/api/chat`（不是 `/chat/completions`），默认端口 `11434`
- **无鉴权**（本地服务）
- 采样参数放在 `options` 里：`temperature` / `num_predict`（=`max_tokens`）
- 响应是 `{"message": {"content": ...}}`（不是 `choices`）
- usage 字段是 `prompt_eval_count` / `eval_count` ——
  ⚠️ 修 P6：旧实现**完全没有解析**这两个字段，本地模型的 token 消耗既不计入统计、
  也不参与成本计算（本地无计费，但"消耗量"对上下文预算仍有用）。
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

__all__ = ["OllamaAdapter"]


class OllamaAdapter(ProviderAdapter):
    """Ollama `/api/chat`。"""

    label = "Ollama"

    def build_request(self, req: ChatRequest) -> PreparedRequest:
        body = {
            "model": req.model,
            "messages": req.openai_messages(),
            "stream": bool(req.stream),
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
        }
        if req.extra:
            body.update(req.extra)
        return PreparedRequest(
            path=self.spec.chat_path,
            json_body=body,
            headers=dict(self.spec.default_headers),
        )

    def parse_response(self, data: dict) -> ChatResult:
        message = data.get("message") or {}
        if not isinstance(message, dict):
            message = {}
        return ChatResult(
            text=message.get("content", "") or "",
            reasoning=message.get("thinking", "") or "",
            usage=self._parse_usage(data),
            finish_reason=data.get("done_reason", "") or "",
            raw=data,
        )

    def _parse_usage(self, data: dict) -> UsageData:
        """Ollama 把计数放在**响应顶层**，不在 `usage` 对象里。"""
        prompt = data.get("prompt_eval_count", 0) or 0
        completion = data.get("eval_count", 0) or 0
        return UsageData(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    def parse_stream_chunk(self, line: str):
        """Ollama 流式是**裸 JSON 行**（不带 `data: ` 前缀）。

        与 OpenAI / Anthropic 的 SSE 都不同 —— 这是"各家实现独立"的又一个例子。
        """
        if not line:
            return None
        try:
            chunk = json.loads(line)
        except (ValueError, TypeError):
            return None
        if not isinstance(chunk, dict):
            return None

        from .base import StreamDelta

        message = chunk.get("message") or {}
        delta = StreamDelta(
            text=(message.get("content", "") if isinstance(message, dict) else "") or "",
            done=bool(chunk.get("done")),
        )
        if chunk.get("done"):
            delta.usage = self._parse_usage(chunk)
        return delta
