"""OpenAI 兼容适配器（覆盖 openai / deepseek / mimo / kimi / siliconflow /
together / groq / dashscope / custom）。

这类 provider 的请求体、响应体、流式格式**完全一致**，差异只有三处，
全部由 `ProviderSpec` 声明式表达，不需要各自写一份代码：

1. `chat_path` —— `/chat/completions`（绝大多数）
2. `base_url_includes_v1` —— base 是否自带 `/v1`
3. `auth` —— 都是 `Authorization: Bearer`

思考模式参数的差异较大（deepseek 用 `thinking`、qwen 用 `enable_thinking`…），
那部分交给 `providers/reasoning.py` 的 `ReasoningAdapter`。
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

__all__ = ["OpenAICompatAdapter"]


class OpenAICompatAdapter(ProviderAdapter):
    """OpenAI Chat Completions 兼容协议。"""

    #: 错误信息里的显示名（子类/实例可覆盖）
    label = "OpenAI兼容API"

    def build_request(self, req: ChatRequest) -> PreparedRequest:
        body = {
            "model": req.model,
            "messages": req.openai_messages(),
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.stream:
            body["stream"] = True
        # 声明式附加字段（如某些平台的固定参数）
        if self.spec.extra_body:
            for key, value in self.spec.extra_body.items():
                if key not in body:
                    body[key] = value
        if req.extra:
            body.update(req.extra)
        return PreparedRequest(
            path=self.spec.chat_path,
            json_body=body,
            headers=dict(self.spec.default_headers),
        )

    def parse_response(self, data: dict) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise Exception(f"{self.label}返回无choices: {json.dumps(data, ensure_ascii=False)[:200]}")

        message = choices[0].get("message", {}) or {}
        return ChatResult(
            text=message.get("content", "") or "",
            reasoning=message.get("reasoning_content", "") or "",
            usage=self._parse_usage(data.get("usage")),
            finish_reason=choices[0].get("finish_reason", "") or "",
            raw=data,
        )

    def _parse_usage(self, usage) -> UsageData:
        """OpenAI 系 usage。

        `cached_tokens` 有两种位置：OpenAI 用 `prompt_tokens_details.cached_tokens`，
        DeepSeek 用顶层 `prompt_cache_hit_tokens` —— 两者都读，缺失则为 0。
        """
        if not isinstance(usage, dict):
            return UsageData()
        details = usage.get("prompt_tokens_details")
        cached = 0
        if isinstance(details, dict):
            cached = details.get("cached_tokens", 0) or 0
        if not cached:
            cached = usage.get("prompt_cache_hit_tokens", 0) or 0
        return UsageData(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cached_tokens=cached,
        )
