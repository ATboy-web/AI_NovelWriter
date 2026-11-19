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

🔴 **「关闭」必须是显式的**（2026-11-19 修正，踩过一次）：
DeepSeek 文档写明「省略 `thinking` 或传 `null` 时，模式由 `reasoning_effort` 决定；
两者都未提供 ⇒ **默认开启思考**」。所以"不发送开启参数"**不等于**关闭 ——
必须发送 `thinking={"type":"disabled"}`（qwen 为 `enable_thinking=false`）。
上一版只做了"不发送 enabled"，结果正文分段与评审仍被思考吃光预算
（实测 `reasoning_len=5948/6086`，`finish=length`，`content` 为空）。
"""

from __future__ import annotations

from .base import ChatRequest
from .openai_compat import OpenAICompatAdapter

__all__ = [
    "ReasoningAdapter",
    "THINKING_DISABLERS",
    "THINKING_STYLES",
    "apply_thinking_disable",
    "apply_thinking_style",
]

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


def _disable_deepseek(body: dict, req: ChatRequest) -> None:
    # 显式关闭：省略该字段会被服务端当作"默认开启"
    body["thinking"] = {"type": "disabled"}
    # reasoning_effort 在 disabled 下会被忽略，但仍移除以免个别网关按它判定
    body.pop("reasoning_effort", None)


def _disable_glm(body: dict, req: ChatRequest) -> None:
    body["thinking"] = {"type": "disabled"}
    body.pop("reasoning_effort", None)


def _disable_qwen(body: dict, req: ChatRequest) -> None:
    # 通义的开关是布尔字段，没有 type 子结构
    body["enable_thinking"] = False
    body.pop("thinking_budget", None)


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


#: 关闭思考的写法。**凡 `THINKING_STYLES` 里有的风格都必须在这里出现**，
#: 否则该家的"关闭"仍然是空操作（向服务端默认值投降）。
THINKING_DISABLERS = {
    "deepseek": _disable_deepseek,
    "glm": _disable_glm,
    "qwen": _disable_qwen,
    "kimi": _disable_glm,  # kimi 与 glm 同为 thinking.type 结构
}


def apply_thinking_disable(style: str, body: dict, req: ChatRequest) -> dict:
    """就地写入"关闭思考"参数，返回同一个 dict。"""
    disable = THINKING_DISABLERS.get(style)
    if disable is not None:
        disable(body, req)
    return body


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
        style = self.spec.thinking_style
        if thinking:
            apply_thinking_style(style, prepared.json_body, request)
        else:
            # 🔴 必须显式禁用：省略 thinking 字段会被服务端按 reasoning_effort
            # 或"默认开启"处理（DeepSeek 文档明文如此）。这里覆盖两种情况：
            #   - 调用方本来就要求关闭；
            #   - max_tokens 太小被上面强制关闭。
            apply_thinking_disable(style, prepared.json_body, request)
        return prepared


def _clone_with_thinking(req: ChatRequest, thinking: bool) -> ChatRequest:
    return ChatRequest(
        req.model,
        req.messages,
        req.system,
        req.max_tokens,
        req.temperature,
        thinking,
        req.reasoning_effort,
        req.stream,
        req.extra,
    )
