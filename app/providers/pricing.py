"""内置价目表与成本估算（v3 §9）。

**为什么不是简单的「输入价 / 输出价」两列**（§9.9 的四条硬约束）：

1. **缓存价独立** —— DeepSeek / Anthropic / GLM / MiMo / SiliconFlow 都区分
   cache-hit 与 cache-miss，价差可达 50 倍（DeepSeek 0.02 vs 1 元/百万）。
2. **阶梯计费** —— Qwen 按**单次请求的输入 token 总量**分档，且该请求的
   *全部* token 按该档结算。扁平二元组表达不了。
3. **币种混用** —— CNY（DeepSeek/GLM/Qwen/MiMo 国内）与 USD（OpenAI/Anthropic/
   Kimi 国际/SiliconFlow/Groq）不能相加。
4. **部署区域** —— 同一模型不同区域价格不同（Kimi 国内/国际、MiMo 国内/海外、
   Qwen 中国内地/全球/国际/欧盟）。

⚠️ **价格会变，且本表是快照。** 每条都带 `source_url` / `verified_at` / `confidence`，
UI 必须呈现这三项并允许用户编辑（`editable=True`）—— 用户自行判断是否过期，
比我们悄悄用旧价算出错误的钱要好。`confidence != "official"` 或用量为估算值时，
成本必须带提示标记。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "PriceTier",
    "ModelPrice",
    "CostEstimate",
    "PRICING",
    "PRICE_TABLE_VERIFIED_AT",
    "free_price",
    "lookup",
    "estimate_cost",
    "all_prices",
    "providers_with_pricing",
]

#: 本表的查证日期（§9 联网查证）
PRICE_TABLE_VERIFIED_AT = "2026-09-16"

#: 所有单价均为「每百万 tokens」
UNIT_TOKENS = 1_000_000


@dataclass(frozen=True)
class PriceTier:
    """阶梯计费的一档。`max_input_tokens=None` 表示最后一档（无上限）。"""

    max_input_tokens: int | None
    input: float
    output: float


@dataclass(frozen=True)
class ModelPrice:
    """一个（provider, model, region）的定价。"""

    provider: str
    model: str
    currency: str  # "CNY" | "USD"
    input: float  # 未命中缓存的输入价
    output: float
    cached_input: float | None = None  # 命中缓存的输入价
    tiers: tuple = ()  # 阶梯（Qwen 类）；非空时忽略 input/output
    region: str = "default"  # cn / international / eu / default
    source_url: str = ""
    verified_at: str = PRICE_TABLE_VERIFIED_AT
    confidence: str = "official"  # official | aggregate | unverified
    editable: bool = True
    note: str = ""

    # ------------------------------------------------------------ 查询

    def tier_for(self, input_tokens: int) -> PriceTier | None:
        """按输入 token 总量选档（阶梯计费的核心）。"""
        if not self.tiers:
            return None
        ordered = sorted(
            self.tiers,
            key=lambda t: (t.max_input_tokens is None, t.max_input_tokens or 0),
        )
        for tier in ordered:
            if tier.max_input_tokens is None or input_tokens <= tier.max_input_tokens:
                return tier
        return ordered[-1]

    def rates_for(self, input_tokens: int) -> tuple:
        """返回 `(input_rate, output_rate)`；阶梯价会覆盖基础价。"""
        tier = self.tier_for(input_tokens)
        if tier is None:
            return self.input, self.output
        return tier.input, tier.output

    @property
    def is_free(self) -> bool:
        if self.tiers:
            return all(t.input == 0 and t.output == 0 for t in self.tiers)
        return self.input == 0 and self.output == 0

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "currency": self.currency,
            "input": self.input,
            "output": self.output,
            "cached_input": self.cached_input,
            "tiers": [
                {"max_input_tokens": t.max_input_tokens, "input": t.input, "output": t.output} for t in self.tiers
            ],
            "region": self.region,
            "source_url": self.source_url,
            "verified_at": self.verified_at,
            "confidence": self.confidence,
            "editable": self.editable,
            "note": self.note,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ModelPrice({self.provider}/{self.model}@{self.region} {self.input}/{self.output} {self.currency})"


@dataclass
class CostEstimate:
    """一次成本估算的结果。

    `currency=""` 表示币种未确定（混合币种或未知模型）——
    此时 `cost` 绝不能被当成可累加的金额。
    """

    cost: float = 0.0
    currency: str = ""
    price: ModelPrice | None = None
    notes: list = field(default_factory=list)

    @property
    def priced(self) -> bool:
        return self.price is not None and bool(self.currency)

    @property
    def reliable(self) -> bool:
        """是否可信（官方价 + 未用到估算用量）。"""
        return self.priced and self.price.confidence == "official" and not self.notes

    def format(self) -> str:
        if not self.priced:
            # 未定价时**更要**把原因说出来：用户看到 "¥0.000000" 会以为真的免费。
            base = "无价目（按 0 计）" if self.price is None else "价格未知"
        else:
            symbol = "¥" if self.currency == "CNY" else "$"
            base = f"{symbol}{self.cost:.6f}"
        if self.notes:
            base += " ⚠ " + "；".join(self.notes)
        return base

    def as_dict(self) -> dict:
        return {
            "cost": self.cost,
            "currency": self.currency,
            "priced": self.priced,
            "reliable": self.reliable,
            "notes": list(self.notes),
            "price": self.price.as_dict() if self.price else None,
        }


def _p(
    provider,
    model,
    currency,
    input_,
    output,
    *,
    cached=None,
    region="default",
    source="",
    confidence="official",
    tiers=(),
    note="",
) -> ModelPrice:
    return ModelPrice(
        provider=provider,
        model=model,
        currency=currency,
        input=input_,
        output=output,
        cached_input=cached,
        region=region,
        source_url=source,
        confidence=confidence,
        tiers=tuple(tiers),
        note=note,
    )


#: 内置价目表。**只收录查证到的**；未收录的模型 → 成本按 0 计并提示「无价目」。
PRICING: tuple[ModelPrice, ...] = (
    # ------------------------------------------------------------ §9.1 DeepSeek (CNY)
    _p(
        "deepseek",
        "deepseek-v4-flash",
        "CNY",
        1,
        2,
        cached=0.02,
        source="https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
    ),
    _p(
        "deepseek",
        "deepseek-v4-pro",
        "CNY",
        3,
        6,
        cached=0.025,
        source="https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
        note="deepseek-chat/deepseek-reasoner 已于 2026-07-24 弃用",
    ),
    # ------------------------------------------------------------ §9.2 OpenAI (USD, 聚合)
    _p("openai", "gpt-4o", "USD", 2.50, 10.00, source="https://help.openai.com/", confidence="aggregate"),
    _p("openai", "gpt-4o-mini", "USD", 0.15, 0.60, source="https://help.openai.com/", confidence="aggregate"),
    _p("openai", "gpt-4.1", "USD", 2.00, 8.00, source="https://help.openai.com/", confidence="aggregate"),
    _p("openai", "o4-mini", "USD", 1.10, 4.40, source="https://help.openai.com/", confidence="aggregate"),
    # ------------------------------------------------------------ §9.3 Anthropic (USD)
    _p(
        "claude",
        "claude-sonnet-5",
        "USD",
        2,
        10,
        cached=0.20,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
        note="原限时价已转为标准价，原定 9/1 涨价取消",
    ),
    _p(
        "claude",
        "claude-opus-5",
        "USD",
        5,
        25,
        cached=0.50,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
    ),
    _p(
        "claude",
        "claude-sonnet-4-6",
        "USD",
        3,
        15,
        cached=0.30,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
    ),
    _p(
        "claude",
        "claude-haiku-4-5",
        "USD",
        1,
        5,
        cached=0.10,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
    ),
    _p(
        "claude",
        "claude-fable-5",
        "USD",
        10,
        50,
        cached=1.00,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
    ),
    _p(
        "claude",
        "claude-mythos-5",
        "USD",
        10,
        50,
        cached=1.00,
        source="https://platform.claude.com/docs/en/about-claude/pricing",
    ),
    # ------------------------------------------------------------ §9.4 Moonshot Kimi (USD 国际站)
    _p("kimi", "kimi-k3", "USD", 3, 15, cached=0.30, region="international", source="https://api.moonshot.ai/"),
    _p(
        "kimi",
        "kimi-k2.6",
        "USD",
        0.95,
        4,
        region="international",
        source="https://api.moonshot.ai/",
        confidence="aggregate",
        note="存在来源冲突（另有聚合站报 $0.60/$2.50）；国内站为 CNY 且价格不同",
    ),
    _p(
        "kimi",
        "kimi-k2.5",
        "USD",
        0.60,
        3,
        region="international",
        source="https://api.moonshot.ai/",
        confidence="aggregate",
    ),
    # ------------------------------------------------------------ §9.5 智谱 GLM (CNY)
    _p("glm", "glm-5.3", "CNY", 8, 28, cached=2, source="https://docs.bigmodel.cn/cn/guide/start/pricing"),
    _p("glm", "glm-5.3-flash", "CNY", 0.8, 2.8, cached=0.23, source="https://docs.bigmodel.cn/cn/guide/start/pricing"),
    _p("glm", "glm-5.2", "CNY", 8, 28, cached=2, source="https://docs.bigmodel.cn/cn/guide/start/pricing"),
    _p(
        "glm",
        "glm-4.7-flash",
        "CNY",
        0,
        0,
        cached=0,
        source="https://docs.bigmodel.cn/cn/guide/start/pricing",
        note="免费模型",
    ),
    # ------------------------------------------------------------ §9.6 阿里云百炼 Qwen (CNY, 阶梯)
    _p(
        "qwen",
        "qwen3.7-max",
        "CNY",
        12,
        36,
        source="https://help.aliyun.com/zh/model-studio/model-pricing",
        tiers=(PriceTier(1_000_000, 12, 36),),
        note="按单次请求输入总量分档",
    ),
    _p(
        "qwen",
        "qwen3-max",
        "CNY",
        2.5,
        10,
        source="https://help.aliyun.com/zh/model-studio/model-pricing",
        tiers=(PriceTier(32_000, 2.5, 10), PriceTier(128_000, 4, 16), PriceTier(256_000, 7, 28)),
        note="阶梯计费：全部 token 按所选档位结算",
    ),
    _p(
        "qwen",
        "qwen3.7-plus",
        "CNY",
        2,
        8,
        source="https://help.aliyun.com/zh/model-studio/model-pricing",
        tiers=(PriceTier(256_000, 2, 8),),
    ),
    _p(
        "qwen",
        "qwen-plus",
        "CNY",
        0.8,
        2,
        source="https://help.aliyun.com/zh/model-studio/model-pricing",
        tiers=(PriceTier(128_000, 0.8, 2),),
    ),
    # ------------------------------------------------------------ §9.7 小米 MiMo（双区域双币种）
    _p(
        "mimo",
        "mimo-v2.5-pro",
        "CNY",
        3,
        6,
        region="cn",
        source="https://platform.xiaomimimo.com/docs/zh-CN/price/pay-as-you-go",
    ),
    _p(
        "mimo",
        "mimo-v2.5-pro",
        "USD",
        0.435,
        0.87,
        region="international",
        source="https://platform.xiaomimimo.com/docs/zh-CN/price/pay-as-you-go",
    ),
    _p(
        "mimo",
        "mimo-v2.5",
        "CNY",
        1,
        2,
        region="cn",
        source="https://platform.xiaomimimo.com/docs/zh-CN/price/pay-as-you-go",
    ),
    _p(
        "mimo",
        "mimo-v2.5",
        "USD",
        0.14,
        0.28,
        region="international",
        source="https://platform.xiaomimimo.com/docs/zh-CN/price/pay-as-you-go",
    ),
    # ------------------------------------------------------------ §9.8 聚合/托管平台
    _p(
        "siliconflow",
        "deepseek-ai/DeepSeek-V4-Flash",
        "USD",
        0.13,
        0.28,
        cached=0.028,
        source="https://www.siliconflow.cn/",
    ),
    _p("siliconflow", "zai-org/GLM-5.3", "USD", 1.40, 4.40, cached=0.26, source="https://www.siliconflow.cn/"),
    _p("groq", "openai/gpt-oss-120b", "USD", 0.15, 0.60, source="https://console.groq.com/docs/models"),
    _p("groq", "openai/gpt-oss-20b", "USD", 0.075, 0.30, cached=0.0375, source="https://console.groq.com/docs/models"),
    _p("groq", "qwen/qwen3.6-27b", "USD", 0.60, 3.00, source="https://console.groq.com/docs/models"),
    _p("groq", "llama-3.3-70b-versatile", "USD", 0.59, 0.79, source="https://console.groq.com/docs/models"),
    _p(
        "together", "Qwen/Qwen3.6-Plus", "USD", 0.50, 3.00, source="", confidence="aggregate", note="聚合来源，置信度低"
    ),
    # ------------------------------------------------------------ 本地：无计费
    _p("ollama", "*", "CNY", 0, 0, source="", note="本地模型，无计费"),
)


def _index() -> dict:
    table = {}
    for price in PRICING:
        table[(price.provider, price.model, price.region)] = price
    return table


_INDEX = _index()


def all_prices() -> tuple:
    return PRICING


def providers_with_pricing() -> tuple:
    return tuple(sorted({p.provider for p in PRICING}))


def free_price(provider: str, model: str = "*") -> ModelPrice:
    """本地/免费模型的零价（让成本路径统一，不必到处判 None）。"""
    return ModelPrice(
        provider=provider,
        model=model,
        currency="CNY",
        input=0,
        output=0,
        source_url="",
        confidence="official",
        note="无计费",
    )


def lookup(provider: str, model: str, region: str = "default") -> ModelPrice | None:
    """查价。匹配顺序：精确 region → default → 该 provider 的任意 region → 通配 `*`。

    最后一步的 `*` 让「本地模型无计费」这类整家规则不必逐个模型列举。
    """
    model = model or ""
    exact = _INDEX.get((provider, model, region))
    if exact is not None:
        return exact
    if region != "default":
        fallback = _INDEX.get((provider, model, "default"))
        if fallback is not None:
            return fallback
    # 同 provider 同模型的其它区域（如只配了 cn 而请求 default）
    for (p, m, _r), price in _INDEX.items():
        if p == provider and m == model:
            return price
    wildcard = _INDEX.get((provider, "*", region)) or _INDEX.get((provider, "*", "default"))
    if wildcard is not None and wildcard.is_free:
        return wildcard
    return None


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    *,
    cached_tokens: int = 0,
    estimated: bool = False,
    region: str = "default",
    extra_note: str = "",
) -> CostEstimate:
    """估算一次调用的成本。

    参数
    ----
    prompt_tokens / completion_tokens : 输入输出 token 数
    cached_tokens : 命中提示缓存的输入 token 数（会按 `cached_input` 计价）
    estimated : 用量是否为估算值 —— 为真时必须带提示（成本是估算的估算）
    """
    price = lookup(provider, model, region)
    notes = []
    if price is None:
        notes.append(f"无内置价目（{provider}/{model or '未指定模型'}），成本按 0 计")
        return CostEstimate(cost=0.0, currency="", price=None, notes=notes)

    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    cached_tokens = max(0, min(int(cached_tokens or 0), prompt_tokens))

    in_rate, out_rate = price.rates_for(prompt_tokens)
    if price.tiers:
        tier = price.tier_for(prompt_tokens)
        if tier is not None:
            notes.append(f"按阶梯档位 ≤{tier.max_input_tokens or '∞'} 计价")

    billable_input = prompt_tokens - cached_tokens
    cost = (
        billable_input * in_rate
        + cached_tokens * (price.cached_input if price.cached_input is not None else in_rate)
        + completion_tokens * out_rate
    ) / UNIT_TOKENS

    if price.confidence != "official":
        notes.append(f"价目来源为 {price.confidence}，可能不准确")
    if estimated:
        notes.append("用量为估算值（provider 未返回 usage）")
    if extra_note:
        notes.append(extra_note)

    return CostEstimate(cost=cost, currency=price.currency, price=price, notes=notes)
