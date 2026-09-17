"""Provider 适配层：统一接口 + 独立实现（v3 §3.2 / §4）。

对外只暴露两件事：**注册表**（有哪些 provider、各自怎么调用）与**数据结构**。
上层（`app/ai_client.py`）依赖本包，本包**不依赖**上层，也不依赖任何 GUI ——
因此可在无界面环境下导入与单测。

新增一家 OpenAI 兼容的 API：在 `registry.DEFAULT_SPECS` 加一条即可。
协议真正不同的（Anthropic / Ollama）才需要新写 adapter 文件。
"""

from __future__ import annotations

from .anthropic import AnthropicAdapter
from .balance import (
    BALANCE_FALLBACK_PROVIDER,
    BALANCE_PROBES,
    DEEPSEEK_BALANCE_URL,
    BalanceCache,
    BalanceProbe,
    BalanceResult,
    extract_path,
    fetch_balance,
    has_builtin_probe,
)
from .base import (
    CONNECT_TIMEOUT,
    DEFAULT_TIMEOUT,
    AuthStyle,
    Capabilities,
    ChatRequest,
    ChatResult,
    PreparedRequest,
    ProviderAdapter,
    ProviderSpec,
    StreamDelta,
    UsageData,
    is_transient_error,
    join_url,
)
from .ollama import OllamaAdapter
from .openai_compat import OpenAICompatAdapter
from .pricing import (
    PRICE_TABLE_VERIFIED_AT,
    PRICING,
    CostEstimate,
    ModelPrice,
    PriceTier,
    all_prices,
    estimate_cost,
    free_price,
    lookup,
    providers_with_pricing,
)
from .reasoning import THINKING_STYLES, ReasoningAdapter, apply_thinking_style
from .registry import (
    DEFAULT_SPECS,
    ProviderRegistry,
    adapter_class_for,
    default_registry,
    get_spec,
    specs_for_ui,
)

__all__ = [
    # 数据结构
    "AuthStyle",
    "Capabilities",
    "ProviderSpec",
    "ChatRequest",
    "PreparedRequest",
    "UsageData",
    "ChatResult",
    "StreamDelta",
    # 适配器
    "ProviderAdapter",
    "OpenAICompatAdapter",
    "ReasoningAdapter",
    "AnthropicAdapter",
    "OllamaAdapter",
    "THINKING_STYLES",
    "apply_thinking_style",
    # 注册表
    "ProviderRegistry",
    "DEFAULT_SPECS",
    "default_registry",
    "get_spec",
    "adapter_class_for",
    "specs_for_ui",
    # 余额
    "BalanceResult",
    "BalanceProbe",
    "BalanceCache",
    "BALANCE_PROBES",
    "BALANCE_FALLBACK_PROVIDER",
    "DEEPSEEK_BALANCE_URL",
    "has_builtin_probe",
    "fetch_balance",
    "extract_path",
    # 价目
    "ModelPrice",
    "PriceTier",
    "CostEstimate",
    "PRICING",
    "PRICE_TABLE_VERIFIED_AT",
    "lookup",
    "estimate_cost",
    "all_prices",
    "providers_with_pricing",
    "free_price",
    # 工具
    "join_url",
    "is_transient_error",
    "DEFAULT_TIMEOUT",
    "CONNECT_TIMEOUT",
]
