"""Provider 抽象层：能力声明、请求/响应数据结构、适配器接口（v3 §3.2）。

**设计原则（对应需求 4「为每种 API 设计各自适配的调用方法」）**：

> 不做"每家有各自一套散装代码"，而是 **统一接口 + 独立实现**。
> 接口统一才可维护，实现独立才够灵活。

| 层面 | 统一（所有 provider 共用） | 独立（每个 adapter 自己实现） |
|---|---|---|
| 入口 | `AIClient.chat()` / `chat_stream()` 签名不变 | — |
| 请求 | 重试/退避/超时/日志/用量归因框架 | `build_request()`：路径、鉴权头、请求体字段 |
| 响应 | 归因、持久化、统计、UI 展示 | `parse_response()`：取文本、reasoning、usage |
| 流式 | 分片循环、缓冲、错误处理 | `parse_stream_chunk()`：SSE 格式差异 |
| 错误 | 统一异常类型与用户提示 | `is_transient()`：哪类错误值得重试 |
| 能力 | 能力查询 API | `spec.supports`：声明式声明 |

本模块**不 import `ai_client`**（方向反过来：ai_client 依赖本包），
也不依赖任何 GUI —— 可被无界面环境导入与单测。
"""

from __future__ import annotations

import httpx

__all__ = [
    "AuthStyle",
    "Capabilities",
    "ProviderSpec",
    "ChatRequest",
    "PreparedRequest",
    "UsageData",
    "ChatResult",
    "StreamDelta",
    "ProviderAdapter",
    "is_transient_error",
    "join_url",
    "DEFAULT_TIMEOUT",
    "CONNECT_TIMEOUT",
]

#: 读超时（秒）。原先硬编码 600.0/300.0 于 ai_client，现为可配置默认值。
DEFAULT_TIMEOUT = 600.0
#: 连接超时（秒）
CONNECT_TIMEOUT = 10.0


def is_transient_error(exc: BaseException) -> bool:
    """判断异常是否属于「重试有意义」的瞬时故障。

    判据：httpx 传输层错误（超时/连接/读），或 HTTP 429 / 5xx。
    401/403/400 等客户端错误**不重试** —— 无差别重试既放大配额消耗又拖长等待。

    本函数即 `ai_client._is_transient_error` 的唯一实现（那里只是转发导入）。
    """
    if isinstance(exc, httpx.TransportError):
        # httpx 中 TimeoutException / ConnectError / ReadError 等均继承 TransportError
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return bool(status and (status == 429 or status >= 500))


def join_url(base_url: str, path: str, base_includes_v1: bool = False) -> str:
    """拼接最终请求 URL，并显式处理 `/v1` 重复问题（修 P2）。

    历史问题：有的 base 自带 `/v1`（openai/mimo/kimi），有的不带（deepseek/claude），
    而 `chat_path` 有时也写 `/v1/messages` —— 隐式拼接极易配错且报错难懂。
    现在由 `ProviderSpec.base_url_includes_v1` **显式声明**：
    若 base 已含 `/v1` 而 path 又以 `/v1/` 开头，则去掉 path 里的 `/v1`。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        return path
    if base_includes_v1 and path.startswith("/v1/"):
        path = path[len("/v1"):]
    return base + path


class AuthStyle:
    """鉴权头的构造方式。"""

    BEARER = "bearer"          # Authorization: Bearer <key>
    X_API_KEY = "x-api-key"    # Anthropic 风格
    NONE = "none"              # 本地模型（ollama）


class Capabilities:
    """provider 能力声明（UI 据此显隐控件，不靠 if provider == ...）。"""

    __slots__ = ("streaming", "thinking", "usage", "balance", "json_mode", "local")

    def __init__(
        self,
        streaming: bool = True,
        thinking: bool = False,
        usage: bool = True,
        balance: bool = False,
        json_mode: bool = False,
        local: bool = False,
    ):
        self.streaming = streaming
        self.thinking = thinking
        self.usage = usage
        self.balance = balance
        self.json_mode = json_mode
        self.local = local

    def as_dict(self) -> dict:
        return {
            "streaming": self.streaming,
            "thinking": self.thinking,
            "usage": self.usage,
            "balance": self.balance,
            "json_mode": self.json_mode,
            "local": self.local,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        flags = ", ".join(f"{k}={v}" for k, v in self.as_dict().items())
        return f"Capabilities({flags})"


class ProviderSpec:
    """一个 provider 的静态描述。

    `base_url_includes_v1` 与 `chat_path` 一起决定最终 URL，
    不再让调用方去猜"要不要补 /v1"。
    """

    __slots__ = (
        "key", "name", "base_url", "default_model", "models", "auth",
        "chat_path", "base_url_includes_v1", "supports", "default_headers",
        "extra_body", "thinking_style", "canonical_order", "note",
        "timeout", "connect_timeout",
    )

    def __init__(
        self,
        key: str,
        name: str,
        base_url: str,
        default_model: str = "",
        models=(),
        auth: str = AuthStyle.BEARER,
        chat_path: str = "/chat/completions",
        base_url_includes_v1: bool = False,
        supports: Capabilities = None,
        default_headers: dict = None,
        extra_body: dict = None,
        thinking_style: str = "",
        canonical_order: int = 100,
        note: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        connect_timeout: float = CONNECT_TIMEOUT,
    ):
        self.key = key
        self.name = name
        self.base_url = base_url
        self.default_model = default_model
        self.models = tuple(models)
        self.auth = auth
        self.chat_path = chat_path
        self.base_url_includes_v1 = base_url_includes_v1
        self.supports = supports or Capabilities()
        self.default_headers = dict(default_headers or {})
        self.extra_body = dict(extra_body or {})
        #: 思考模式参数风格（见 providers/reasoning.py）
        self.thinking_style = thinking_style
        self.canonical_order = canonical_order
        #: 给设置页显示的一句说明（如"无公开余额接口"）
        self.note = note
        #: 读超时。声明式表达，取代 ai_client 里 `if provider == "ollama"` 式的
        #: 硬编码特判（旧实现：claude/openai 600s、ollama 300s 写死在 _init_client）。
        self.timeout = float(timeout)
        self.connect_timeout = float(connect_timeout)

    def resolved_url(self, api_base: str = "") -> str:
        """返回最终请求 URL（配置为空则用默认 base）。"""
        return join_url(
            api_base or self.base_url, self.chat_path, self.base_url_includes_v1
        )

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "models": list(self.models),
            "auth": self.auth,
            "chat_path": self.chat_path,
            "base_url_includes_v1": self.base_url_includes_v1,
            "supports": self.supports.as_dict(),
            "thinking_style": self.thinking_style,
            "note": self.note,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ProviderSpec({self.key!r}, {self.chat_path!r}, v1={self.base_url_includes_v1})"


class ChatRequest:
    """一次对话请求的**统一**参数（各 adapter 负责翻译成自家字段名）。"""

    __slots__ = (
        "model", "messages", "system", "max_tokens", "temperature",
        "thinking_enabled", "reasoning_effort", "stream", "extra",
    )

    def __init__(
        self,
        model: str,
        messages,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.8,
        thinking_enabled: bool = False,
        reasoning_effort: str = "medium",
        stream: bool = False,
        extra: dict = None,
    ):
        self.model = model
        self.messages = list(messages or [])
        self.system = system or ""
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort
        self.stream = stream
        self.extra = dict(extra or {})

    def openai_messages(self) -> list:
        """把 system 作为首条 message 拼进去（OpenAI 兼容格式）。"""
        full = []
        if self.system:
            full.append({"role": "system", "content": self.system})
        full.extend(self.messages)
        return full

    def with_stream(self, stream: bool) -> "ChatRequest":
        clone = ChatRequest(
            self.model, self.messages, self.system, self.max_tokens, self.temperature,
            self.thinking_enabled, self.reasoning_effort, stream, self.extra,
        )
        return clone


class PreparedRequest:
    """adapter 产出、由统一执行层发出的请求。"""

    __slots__ = ("method", "path", "json_body", "headers", "timeout", "url_override")

    def __init__(
        self,
        path: str,
        json_body: dict,
        headers: dict = None,
        method: str = "POST",
        timeout: float = None,
        url_override: str = "",
    ):
        self.method = method
        #: 相对 base_url 的路径（httpx.Client 会拼接）
        self.path = path
        self.json_body = json_body
        self.headers = dict(headers or {})
        self.timeout = timeout
        #: 绝对 URL（余额查询等非 chat 场景用）
        self.url_override = url_override

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"PreparedRequest({self.method} {self.path})"


class UsageData:
    """一次调用的 token 用量。

    `estimated=True` 表示 provider 未返回 usage，由 `token_estimator` 估算 ——
    UI 必须区分"实测"与"估算"，成本计算也要对估算值加提示。
    """

    __slots__ = ("prompt_tokens", "completion_tokens", "total_tokens",
                 "cached_tokens", "estimated")

    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cached_tokens: int = 0,
        estimated: bool = False,
    ):
        self.prompt_tokens = int(prompt_tokens or 0)
        self.completion_tokens = int(completion_tokens or 0)
        self.total_tokens = int(total_tokens or 0) or (
            self.prompt_tokens + self.completion_tokens
        )
        self.cached_tokens = int(cached_tokens or 0)
        self.estimated = estimated

    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "estimated": self.estimated,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"UsageData(p={self.prompt_tokens}, c={self.completion_tokens}, "
            f"total={self.total_tokens}, estimated={self.estimated})"
        )


class ChatResult:
    """adapter 解析出的统一结果。"""

    __slots__ = ("text", "reasoning", "usage", "finish_reason", "raw")

    def __init__(
        self,
        text: str = "",
        reasoning: str = "",
        usage: UsageData = None,
        finish_reason: str = "",
        raw: dict = None,
    ):
        self.text = text or ""
        self.reasoning = reasoning or ""
        self.usage = usage or UsageData()
        self.finish_reason = finish_reason
        self.raw = raw or {}

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class StreamDelta:
    """流式分片。"""

    __slots__ = ("text", "reasoning", "usage", "done")

    def __init__(self, text: str = "", reasoning: str = "", usage: UsageData = None,
                 done: bool = False):
        self.text = text or ""
        self.reasoning = reasoning or ""
        self.usage = usage
        self.done = done


class ProviderAdapter:
    """适配器基类。

    子类至少要实现 `build_request` 与 `parse_response`；
    流式与余额有默认实现（不适合的 provider 直接声明不支持）。
    """

    #: 由子类覆盖
    spec: ProviderSpec = None

    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    # ------------------------------------------------------------ 请求

    def build_request(self, req: ChatRequest) -> PreparedRequest:
        raise NotImplementedError

    def auth_headers(self, api_key: str) -> dict:
        """按 `spec.auth` 构造鉴权头。"""
        if self.spec.auth == AuthStyle.BEARER and api_key:
            return {"Authorization": f"Bearer {api_key}"}
        if self.spec.auth == AuthStyle.X_API_KEY and api_key:
            return {"x-api-key": api_key}
        return {}

    # ------------------------------------------------------------ 响应

    def parse_response(self, data: dict) -> ChatResult:
        raise NotImplementedError

    def parse_stream_chunk(self, line: str) -> "StreamDelta | None":
        """解析一行 SSE。默认实现覆盖 OpenAI 兼容格式。"""
        if not line or not line.startswith("data: "):
            return None
        payload = line[6:].strip()
        if payload == "[DONE]":
            return StreamDelta(done=True)
        import json

        try:
            chunk = json.loads(payload)
        except (ValueError, TypeError):
            return None
        choices = chunk.get("choices") or [{}]
        delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
        usage = self._parse_usage(chunk.get("usage"))
        return StreamDelta(
            text=delta.get("content", "") or "",
            reasoning=delta.get("reasoning_content", "") or "",
            usage=usage,
        )

    # ------------------------------------------------------------ 工具

    def _parse_usage(self, usage) -> UsageData:
        """默认的 OpenAI 风格 usage 解析（各 adapter 可覆盖）。"""
        if not isinstance(usage, dict):
            return UsageData()
        return UsageData(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cached_tokens=(
                (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                if isinstance(usage.get("prompt_tokens_details"), dict)
                else usage.get("prompt_cache_hit_tokens", 0)
            ),
        )

    def is_transient(self, exc: BaseException) -> bool:
        """哪类错误值得重试（默认与全局判据一致）。"""
        return is_transient_error(exc)

    def query_balance(self, http_get, **kwargs) -> "object":
        """查询余额。

        默认实现即「查余额探针表」——所以 *没有余额接口的 provider 也无需各自写代码*，
        它们会得到一个 `supported=False` 的明确结果（UI 显示"该服务未提供余额接口"），
        而不是异常或空白。需要特殊逻辑的 provider 再覆盖本方法。

        `http_get` 是一个 `(url, headers, timeout) -> httpx.Response` 的可调用对象，
        由 AIClient 注入，便于单测替换。
        """
        from .balance import fetch_balance

        return fetch_balance(self.spec, http_get, **kwargs)
