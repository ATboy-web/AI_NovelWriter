"""思考模式适配器：glm / qwen / kimi / deepseek 的特殊 thinking 参数（v3 §3.2）。

这些 provider 在**协议上**都是 OpenAI 兼容（chat_path、鉴权、响应结构都一样），
唯一差异是"如何开启思考模式"以及"开启后是否允许 temperature"。
把这部分抽成 `THINKING_STYLES` 里的一串构造函数，就避免为每家写一份 adapter：

| 风格 | provider | 请求体差异 |
|---|---|---|
| `deepseek` | DeepSeek | `thinking={"type":"enabled"}` + `reasoning_effort`；思考时**移除** `temperature` |
| `glm` | 智谱 GLM | `thinking={"type":"enabled"}`；`reasoning_effort` 仅 5.2/5.1 支持；思考时 `temperature` **强制 1.0** |
| `qwen` | 通义千问 | `enable_thinking=True` + `thinking_budget`（默认取 max_tokens 的一半） |
| `kimi` | Kimi | `thinking={"type":"enabled","keep":"all"}`；思考时移除 `temperature`；`k2.7` **不接受** thinking 参数 |
| `""` | openai 等 | 无思考模式（即使 UI 打开也不发送未定义字段） |

⚠️ 关键约定：**小于 1000 max_tokens 时一律关闭思考** —— 否则思考过程会把
本就不多的 token 预算耗尽，`content` 为空（旧实现已有的保护，必须保留）。
"""

from __future__ import annotations

from .base import ChatRequest
from .openai_compat import OpenAICompatAdapter

__all__ = ["ReasoningAdapter", "THINKING_STYLES", "apply_thinking_style"]

#: 低于该 max_tokens 时禁用思考模式
THINKING_MIN_TOKENS = 1000


def _style_deepseek(body: dict, req: ChatRequest) -> None:
    body["thinking"] = {"type": "enabled"}
    body["reasoning_effort"] = req.reasoning_effort
    # 思考模式下不支持 temperature
    body.pop("temperature", None)


def _style_glm(body: dict, req: ChatRequest) -> None:
    body["thinking"] = {"type": "enabled"}
    # 仅 GLM-5.2 及以上支持 reasoning_effort
    model_lower = (req.model or "").lower()
    if any(version in model_lower for version in ("5.2", "5.1")):
        body["reasoning_effort"] = req.reasoning_effort
    # GLM 思考模式下 temperature 必须为 1.0
    body["temperature"] = 1.0


def _style_qwen(body: dict, req: ChatRequest) -> None:
    body["enable_thinking"] = True
    # 思考 token 预算默认取 max_tokens 的一半
    body["thinking_budget"] = req.max_tokens // 2


def _style_kimi(body: dict, req: ChatRequest) -> None:
    # kimi-k2.7-code 始终思考，不接受 thinking 参数
    if "k2.7" in (req.model or "").lower():
        return
    body["thinking"] = {"type": "enabled", "keep": "all"}
    body.pop("temperature", None)


THINKING_STYLES = {
    "deepseek": _style_deepseek,
    "glm": _style_glm,
    "qwen": _style_qwen,
    "kimi": _style_kimi,
}


def apply_thinking_style(style: str, body: dict, req: ChatRequest) -> dict:
    """按风格名就地修改请求体，返回同一个 dict（便于链式使用）。"""
    builder = THINKING_STYLES.get(style)
    if builder is None:
        return body
    builder(body, req)
    return body


class ReasoningAdapter(OpenAICompatAdapter):
    """在 OpenAI 兼容请求体上叠加思考模式参数。"""

    def build_request(self, req: ChatRequest):
        # 小请求禁用思考（避免思考过程耗尽 token 导致 content 为空）
        thinking = req.thinking_enabled
        if thinking and req.max_tokens < THINKING_MIN_TOKENS:
            thinking = False

        request = req if thinking == req.thinking_enabled else _clone_with_thinking(req, thinking)
        prepared = super().build_request(request)
        if thinking:
            apply_thinking_style(self.spec.thinking_style, prepared.json_body, request)
        return prepared


def _clone_with_thinking(req: ChatRequest, thinking: bool) -> ChatRequest:
    return ChatRequest(
        req.model, req.messages, req.system, req.max_tokens, req.temperature,
        thinking, req.reasoning_effort, req.stream, req.extra,
    )
