"""余额查询适配（v3 §3.4）。

**第一原则：诚实。** 不是每家都有余额接口，UI 必须明说「该服务未提供余额接口」，
而不是报错、转圈或留空 —— 后者会让用户以为功能坏了。

| provider | 余额能力 | 说明 |
|---|---|---|
| DeepSeek | ✅ `GET /user/balance` | 返回现金/赠金余额与币种 |
| Kimi | ⚠️ 官方有余额接口，但**端点未内置** | 见下方「可配置」说明 |
| OpenAI | ❌ 无可用余额 API | `/v1/dashboard/billing/*` 需 session key，API Key 用不了 |
| GLM / Qwen / Anthropic / SiliconFlow / Together / Groq | ❌ 无公开余额 API | 明确标注不支持 |
| Ollama | N/A | 本地模型，无计费概念 |

**长期可用性的关键设计**：余额 URL 与 JSON 取值路径都是**可配置项**
（`balance_url` + `balance_json_path`，见 `BalanceProbe`）。某家改了接口或加了接口，
用户自己填上即可，不必等我们发版。

⚠️ 关于 Kimi：查证时确认官方有余额接口，但具体端点与字段名未能从权威文档逐字确认。
按本项目「不臆造接口」的准则，这里**不填**一个猜测的路径 —— 而是把该家标为
`configured=False`，返回「该服务余额接口需在设置中填写」。填错一个路径的结果是
用户拿到一个空的「零余额」，比明说未配置危险得多。
"""

from __future__ import annotations

import time

__all__ = [
    "BalanceProbe",
    "BalanceResult",
    "BALANCE_PROBES",
    "BalanceCache",
    "CACHE_TTL_SECONDS",
    "extract_path",
    "fetch_balance",
    "probe_for",
]

#: 余额缓存有效期（秒）。避免频繁请求触发限流。
CACHE_TTL_SECONDS = 60.0


def extract_path(data, path: str):
    """按 `"a.b.0.c"` 形式取值。

    支持：
    - 字典键：`balance_infos`
    - 列表下标（纯数字段）：`balance_infos.0.total_balance`

    取不到返回 `None`（调用方据此判断"接口变了"）。
    """
    if not path:
        return None
    node = data
    for part in str(path).split("."):
        if isinstance(node, dict):
            if part not in node:
                return None
            node = node[part]
        elif isinstance(node, (list, tuple)):
            if not part.isdigit():
                return None
            index = int(part)
            if index >= len(node):
                return None
            node = node[index]
        else:
            return None
    return node


class BalanceProbe:
    """某家 provider 的余额接口描述。

    `configured=False` 表示「这家没有余额接口，或端点未内置」——
    两者对用户是同一件事：现在拿不到余额，UI 应显示 `note`。
    """

    __slots__ = (
        "key", "path", "currency_path", "total_path", "granted_path",
        "topped_up_path", "configured", "source_url", "note",
    )

    def __init__(
        self,
        key: str,
        path: str = "",
        currency_path: str = "",
        total_path: str = "",
        granted_path: str = "",
        topped_up_path: str = "",
        configured: bool = True,
        source_url: str = "",
        note: str = "",
    ):
        self.key = key
        self.path = path
        self.currency_path = currency_path
        self.total_path = total_path
        self.granted_path = granted_path
        self.topped_up_path = topped_up_path
        self.configured = configured and bool(path)
        self.source_url = source_url
        self.note = note

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "path": self.path,
            "configured": self.configured,
            "source_url": self.source_url,
            "note": self.note,
        }


#: 余额探针表。**只收录已核实的**。
BALANCE_PROBES: dict[str, BalanceProbe] = {
    "deepseek": BalanceProbe(
        key="deepseek",
        path="/user/balance",
        currency_path="balance_infos.0.currency",
        total_path="balance_infos.0.total_balance",
        granted_path="balance_infos.0.granted_balance",
        topped_up_path="balance_infos.0.topped_up_balance",
        source_url="https://api-docs.deepseek.com/zh-cn/api/get-user-balance",
    ),
    "kimi": BalanceProbe(
        key="kimi",
        configured=False,
        note="该服务余额接口地址未内置，可在设置中填写余额 URL 与取值路径",
    ),
}

#: 明确「没有余额接口」的 provider → 给用户的说明文案
_NO_BALANCE_NOTE = {
    "ollama": "本地模型，无计费",
    "openai": "该服务未提供可用余额接口（官方 billing 接口需 session key，API Key 不可用）",
    "glm": "该服务未提供公开余额接口",
    "qwen": "该服务未提供公开余额接口",
    "dashscope": "该服务未提供公开余额接口",
    "claude": "该服务未提供公开余额接口",
    "siliconflow": "该服务未提供公开余额接口",
    "together": "该服务未提供公开余额接口",
    "groq": "该服务未提供公开余额接口",
    "mimo": "该服务未提供公开余额接口",
    "custom": "自定义 API 的余额接口未知，可在设置中填写",
}


class BalanceResult:
    """一次余额查询的结果。

    `supported=False` 时 UI 显示 `message`，**不是**显示成错误。
    """

    __slots__ = (
        "provider", "supported", "currency", "total", "granted",
        "topped_up", "fetched_at", "cached", "raw", "error", "message",
    )

    def __init__(
        self,
        provider: str = "",
        supported: bool = False,
        currency: str = "",
        total=None,
        granted=None,
        topped_up=None,
        fetched_at: float = 0.0,
        cached: bool = False,
        raw: dict = None,
        error: str = "",
        message: str = "",
    ):
        self.provider = provider
        self.supported = supported
        self.currency = currency
        self.total = total
        self.granted = granted
        self.topped_up = topped_up
        self.fetched_at = fetched_at
        self.cached = cached
        self.raw = raw or {}
        self.error = error
        self.message = message

    # ------------------------------------------------------------ 构造

    @classmethod
    def not_supported(cls, provider: str, message: str = "") -> "BalanceResult":
        return cls(
            provider=provider,
            supported=False,
            message=message or _NO_BALANCE_NOTE.get(provider, "该服务未提供余额接口"),
        )

    @classmethod
    def failed(cls, provider: str, error: str) -> "BalanceResult":
        """查询本身失败（网络/鉴权/接口变更）—— 与"不支持"分开表达。"""
        return cls(provider=provider, supported=True, error=error,
                   message=f"余额查询失败：{error}")

    # ------------------------------------------------------------ 展示

    @property
    def ok(self) -> bool:
        return self.supported and not self.error and self.total is not None

    def format_total(self) -> str:
        """给 UI 用的一行文本。"""
        if not self.supported:
            return self.message or "该服务未提供余额接口"
        if self.error:
            return f"余额查询失败：{self.error}"
        if self.total is None:
            return "已连接，但响应中未找到余额字段（接口可能已变更）"
        unit = self.currency or ""
        text = f"{self.total} {unit}".strip()
        if self.granted not in (None, "", 0):
            text += f"（含赠金 {self.granted}）"
        if self.cached:
            text += "（缓存）"
        return text

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "supported": self.supported,
            "currency": self.currency,
            "total": self.total,
            "granted": self.granted,
            "topped_up": self.topped_up,
            "fetched_at": self.fetched_at,
            "cached": self.cached,
            "error": self.error,
            "message": self.message,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"BalanceResult({self.provider!r}, supported={self.supported}, "
            f"total={self.total!r}, currency={self.currency!r}, error={self.error!r})"
        )


class BalanceCache:
    """余额结果缓存（默认 60s）。

    `now` 可注入，便于单测不依赖真实时间。
    """

    def __init__(self, ttl: float = CACHE_TTL_SECONDS):
        self.ttl = float(ttl)
        self._store: dict = {}

    @staticmethod
    def _key(provider: str, base_url: str, forced_url: str = "") -> tuple:
        return (provider, base_url or "", forced_url or "")

    def get(self, provider: str, base_url: str, forced_url: str = "",
            now: float | None = None) -> BalanceResult | None:
        entry = self._store.get(self._key(provider, base_url, forced_url))
        if not entry:
            return None
        stamp, result = entry
        current = time.time() if now is None else now
        if current - stamp > self.ttl:
            return None
        # 返回副本并标记 cached，避免调用方改到缓存里的对象
        copy = BalanceResult(**{k: v for k, v in result.as_dict().items()})
        copy.cached = True
        return copy

    def put(self, provider: str, base_url: str, result: BalanceResult,
            forced_url: str = "", now: float | None = None) -> None:
        # 失败结果不缓存 —— 否则一次网络抖动会让用户 60s 内看到同一个错误
        if result.error or not result.supported:
            return
        stamp = time.time() if now is None else now
        self._store[self._key(provider, base_url, forced_url)] = (stamp, result)

    def clear(self) -> None:
        self._store.clear()


def probe_for(provider: str, override_url: str = "", override_paths: dict = None):
    """取某家的探针；`override_*` 来自用户配置（可配置性的落点）。

    返回 `(probe, url_path)`；`probe.configured` 为 False 时 URL 不可用。
    """
    base = BALANCE_PROBES.get(provider)
    override_paths = override_paths or {}

    if override_url:
        # 用户显式填了余额 URL：即使内置没有，也可用（这正是「不必等发版」的落点）
        probe = BalanceProbe(
            key=provider,
            path=override_url,
            currency_path=override_paths.get("currency", ""),
            total_path=override_paths.get("total", ""),
            granted_path=override_paths.get("granted", ""),
            topped_up_path=override_paths.get("topped_up", ""),
        )
        return probe, override_url

    if base is None:
        return BalanceProbe(key=provider, configured=False,
                            note=_NO_BALANCE_NOTE.get(provider, "该服务未提供余额接口")), ""
    return base, base.path


def fetch_balance(
    spec,
    http_get,
    *,
    api_key: str = "",
    base_url: str = "",
    override_url: str = "",
    override_paths: dict = None,
    cache: BalanceCache | None = None,
    now: float | None = None,
) -> BalanceResult:
    """查询余额。

    参数
    ----
    spec : ProviderSpec
    http_get : 可调用对象 `(url, headers, timeout) -> httpx.Response`
        由 `AIClient` 注入，便于单测替换（不碰真实网络）。
    api_key / base_url : 生效的凭据与地址（base_url 为空则用 spec 默认）
    override_url / override_paths : 用户配置的余额 URL 与取值路径
    cache : 传入则启用缓存
    """
    provider = getattr(spec, "key", "")
    effective_base = (base_url or getattr(spec, "base_url", "") or "").rstrip("/")

    probe, probe_path = probe_for(provider, override_url, override_paths)

    if not probe.configured:
        return BalanceResult.not_supported(
            provider, probe.note or _NO_BALANCE_NOTE.get(provider, "")
        )

    if cache is not None:
        hit = cache.get(provider, effective_base, probe_path, now=now)
        if hit is not None:
            return hit

    if not effective_base:
        return BalanceResult.failed(provider, "未配置 API 地址")

    url = probe_path if probe_path.startswith("http") else effective_base + probe_path
    headers = dict(getattr(spec, "default_headers", {}) or {})
    if api_key and getattr(spec, "auth", "") == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = http_get(url, headers, getattr(spec, "timeout", 30.0))
    except Exception as exc:                      # noqa: BLE001 - 需要把任何异常转成可展示状态
        return BalanceResult.failed(provider, f"{type(exc).__name__}: {exc}")

    status = getattr(response, "status_code", 0)
    if status != 200:
        return BalanceResult.failed(provider, f"HTTP {status}")

    try:
        data = response.json()
    except Exception as exc:                      # noqa: BLE001
        return BalanceResult.failed(provider, f"响应不是合法 JSON：{exc}")

    result = BalanceResult(
        provider=provider,
        supported=True,
        currency=extract_path(data, probe.currency_path) or "",
        total=extract_path(data, probe.total_path),
        granted=extract_path(data, probe.granted_path),
        topped_up=extract_path(data, probe.topped_up_path),
        fetched_at=time.time() if now is None else now,
        raw=data if isinstance(data, dict) else {},
    )
    if cache is not None:
        cache.put(provider, effective_base, result, probe_path, now=now)
    return result
