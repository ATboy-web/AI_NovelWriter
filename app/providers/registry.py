"""Provider 注册表：把「一家 API 的全部静态事实」集中到一张声明表（v3 §3.2）。

**为什么要有注册表**（修 P4 / P5）：

旧实现里「一家 provider」的信息散落在 4 个地方，且互相不一致：

| 位置 | 内容 | 与谁冲突 |
|---|---|---|
| `ai_client.PROVIDERS` | name / base_url / models | 只有 7 家 |
| `_detect_provider` | 会造出 `glm` / `qwen` / `kimi` | 这三家**不在** PROVIDERS 里 → 无默认 base_url |
| `lifecycle_ui` 的 provider 下拉 | 9 项 | 含 `siliconflow/together/groq/dashscope`，缺 `mimo/kimi` |
| `lifecycle_ui.API_PRESETS` | base_url | 与 PROVIDERS 手工重复维护 |

后果：用户把模型名填成 `qwen3-max` 而 provider 选的是 openai，`_detect_provider` 判定为
`qwen` 并发送 `enable_thinking` 参数 —— 但**地址仍是 openai 的**（P4）。现在每家都有
自己的 `base_url`，检测到哪家就发到哪家。

现在只保留**一张表** `DEFAULT_SPECS`，其余全部派生：UI 下拉、模型预设、URL 预览、
能力显隐、`AIClient.PROVIDERS` 都从这里读。新增一家 API 只需在下面加一个条目。
"""

from __future__ import annotations

from .anthropic import AnthropicAdapter
from .base import (
    AuthStyle,
    Capabilities,
    ProviderAdapter,
    ProviderSpec,
)
from .ollama import OllamaAdapter
from .openai_compat import OpenAICompatAdapter
from .reasoning import ReasoningAdapter

__all__ = [
    "DEFAULT_SPECS",
    "ProviderRegistry",
    "adapter_class_for",
    "default_registry",
    "get_spec",
    "specs_for_ui",
]


def _caps(**kwargs) -> Capabilities:
    """Capabilities 的简写构造（只传关心的开关，其余走默认）。"""
    return Capabilities(**kwargs)


#: 本地模型清单（Ollama 官方常见标签）
_OLLAMA_MODELS = (
    "qwen2.5:14b",
    "qwen2.5:32b",
    "qwen3:latest",
    "llama3.1:8b",
    "llama3.1:70b",
    "deepseek-r1:8b",
    "deepseek-r1:32b",
    "mistral:7b",
)

#: ⚠️ §9.10：内置模型名有 3 处已过时，本轮一并刷新
#:   - claude：`claude-sonnet-4-20250514` / `claude-3-5-sonnet-20241022` 属已退役世代
#:   - deepseek：`deepseek-chat` 已于 2026-07-24 弃用（对应 v4-flash 的非思考模式）
#:   - kimi：`moonshot-v1-128k` 属 V1 世代、官方标注 being retired
DEFAULT_SPECS: tuple[ProviderSpec, ...] = (
    # ------------------------------------------------------------ 本地
    ProviderSpec(
        key="ollama",
        name="Ollama (本地)",
        base_url="http://localhost:11434",
        default_model="qwen2.5:14b",
        models=_OLLAMA_MODELS,
        auth=AuthStyle.NONE,                 # 本地服务，无鉴权
        chat_path="/api/chat",
        supports=_caps(thinking=False, balance=False, json_mode=True, local=True),
        canonical_order=0,
        # 旧实现写死 300s（本地推理慢，但不必给到 600s）
        timeout=300.0,
        note="本地模型，无计费",
    ),
    # ------------------------------------------------------------ 国内
    ProviderSpec(
        key="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        models=("deepseek-v4-flash", "deepseek-v4-pro"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        # base 不含 /v1（deepseek 的 OpenAI 兼容端点在根路径下）
        base_url_includes_v1=False,
        supports=_caps(thinking=True, balance=True, json_mode=True),
        thinking_style="deepseek",
        canonical_order=10,
        note="余额：GET /user/balance",
    ),
    ProviderSpec(
        key="glm",
        name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5.2",
        models=("glm-5.3", "glm-5.3-flash", "glm-5.2", "glm-4.7-flash"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        # 智谱的 api/paas/v4 已含版本段，等同于「带 v1」的情形
        base_url_includes_v1=True,
        supports=_caps(thinking=True, json_mode=True),
        thinking_style="glm",
        canonical_order=20,
        note="官方未提供余额接口",
    ),
    ProviderSpec(
        key="qwen",
        name="通义千问 Qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3-max",
        models=("qwen3.7-max", "qwen3.6-max-preview", "qwen3-max", "qwen-plus", "qwq-plus"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(thinking=True, json_mode=True),
        thinking_style="qwen",
        canonical_order=30,
        note="阶梯计费；官方未提供余额接口",
    ),
    ProviderSpec(
        key="kimi",
        name="Kimi (月之暗面)",
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2.6",
        models=("kimi-k3", "kimi-k2.6", "kimi-k2.5", "kimi-k2.7-code"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(thinking=True, balance=True, json_mode=True),
        thinking_style="kimi",
        canonical_order=40,
        note="余额接口以上线时官方文档为准",
    ),
    ProviderSpec(
        key="mimo",
        name="小米 MiMo",
        base_url="https://api.xiaomimimo.com/v1",
        default_model="mimo-v2.5-pro",
        models=("mimo-v2.5-pro", "mimo-v2.5"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=50,
        note="国内外双币种计价",
    ),
    ProviderSpec(
        key="dashscope",
        name="阿里云百炼 (兼容模式)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        models=("qwen-max", "qwen-plus", "qwen-turbo"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=60,
        note="与通义千问同源，保留入口以兼容旧配置",
    ),
    # ------------------------------------------------------------ 国际
    ProviderSpec(
        key="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=70,
        note="官方无可用余额 API（/v1/dashboard/billing 需 session key）",
    ),
    ProviderSpec(
        key="claude",
        name="Claude (Anthropic)",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-5",
        models=("claude-sonnet-5", "claude-opus-5", "claude-sonnet-4-6", "claude-haiku-4-5"),
        auth=AuthStyle.X_API_KEY,             # x-api-key，不是 Bearer
        chat_path="/v1/messages",
        # path 自带 /v1，而 base 不带 —— 由 join_url 直接拼接
        base_url_includes_v1=False,
        supports=_caps(thinking=False, json_mode=False),
        default_headers={
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        canonical_order=80,
        note="max_tokens 必填；官方未提供余额接口",
    ),
    ProviderSpec(
        key="siliconflow",
        name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        default_model="deepseek-ai/DeepSeek-V4-Flash",
        models=(
            "deepseek-ai/DeepSeek-V4-Flash",
            "zai-org/GLM-5.3",
            "Qwen/Qwen2.5-72B-Instruct",
        ),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=90,
    ),
    ProviderSpec(
        key="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="Qwen/Qwen3.6-Plus",
        models=(
            "Qwen/Qwen3.6-Plus",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=100,
    ),
    ProviderSpec(
        key="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        models=(
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
        ),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=True,
        supports=_caps(json_mode=True),
        canonical_order=110,
    ),
    # ------------------------------------------------------------ 兜底
    ProviderSpec(
        key="custom",
        name="自定义 API",
        base_url="",                          # 必须由用户填写
        default_model="",
        models=(),
        auth=AuthStyle.BEARER,
        chat_path="/chat/completions",
        base_url_includes_v1=False,
        supports=_caps(json_mode=True),
        canonical_order=900,
        note="OpenAI 兼容协议；请自行填写地址与模型名",
    ),
)

#: 需要专属 adapter 的 provider（其余按规则推导）
_ADAPTER_OVERRIDES: dict[str, type[ProviderAdapter]] = {
    "ollama": OllamaAdapter,
    "claude": AnthropicAdapter,
}

#: adapter 基类的通用显示名（用于判断是否该换成真实 provider 名）
_GENERIC_LABEL = "OpenAI兼容API"


def adapter_class_for(spec: ProviderSpec) -> type[ProviderAdapter]:
    """决定某个 spec 由哪个 adapter 类服务。

    规则（显式覆盖优先，其余靠声明推导）：

    1. `key` 在 `_ADAPTER_OVERRIDES` 里 → 用指定的类
    2. 声明了 `thinking_style` → `ReasoningAdapter`（在 OpenAI 兼容体上叠加思考参数）
    3. 其余 → `OpenAICompatAdapter`

    这样"新增一家 OpenAI 兼容的 API"只需加一条 spec，不必新写 adapter；
    只有协议真正不同（Anthropic / Ollama）才需要新类。
    """
    override = _ADAPTER_OVERRIDES.get(spec.key)
    if override is not None:
        return override
    if spec.thinking_style:
        return ReasoningAdapter
    return OpenAICompatAdapter


class ProviderRegistry:
    """provider 的注册与查询。

    不是单例：测试可构造独立实例，互不污染。
    """

    def __init__(self, specs=()):
        self._specs: dict[str, ProviderSpec] = {}
        self._adapter_classes: dict[str, type[ProviderAdapter]] = {}
        self._adapters: dict[str, ProviderAdapter] = {}
        for spec in specs:
            self.register(spec)

    # ------------------------------------------------------------ 注册

    def register(
        self,
        spec: ProviderSpec,
        adapter_class: type[ProviderAdapter] | None = None,
    ) -> ProviderSpec:
        """注册（或覆盖）一家 provider。返回 spec 便于链式使用。"""
        self._specs[spec.key] = spec
        self._adapter_classes[spec.key] = adapter_class or adapter_class_for(spec)
        # 覆盖注册后旧 adapter 实例作废
        self._adapters.pop(spec.key, None)
        return spec

    # ------------------------------------------------------------ 查询

    def get(self, key: str) -> ProviderSpec | None:
        """按 key 取 spec；不存在返回 None。"""
        return self._specs.get(key)

    def resolve(self, key: str) -> ProviderSpec:
        """按 key 取 spec；未知 key 回落到 `custom`（而不是抛异常）。

        关键用途：`_detect_provider` 可能返回用户没配过的 provider，
        或配置里存着一个已被移除的 provider 名；此时应给出「可用的 custom 配置」
        让用户看到明确的报错与地址预览，而不是在构造阶段崩溃。
        """
        spec = self._specs.get(key)
        if spec is not None:
            return spec
        return self._specs["custom"]

    def adapter(self, key: str) -> ProviderAdapter:
        """取（并缓存）某 provider 的 adapter 实例。"""
        spec = self._specs.get(key)
        if spec is None:
            spec = self.resolve(key)
        if spec.key not in self._adapters:
            klass = self._adapter_classes.get(spec.key) or adapter_class_for(spec)
            adapter = klass(spec)
            # 报错信息带上真实 provider 名。
            # 只在 adapter 仍用基类默认名时才替换 —— AnthropicAdapter("Claude")、
            # OllamaAdapter("Ollama") 自有更贴切的 label，不该被 spec.name 覆盖成
            # "Claude (Anthropic)" 这类带括号的长名。
            if getattr(adapter, "label", "") == _GENERIC_LABEL and spec.name:
                adapter.label = spec.name
            self._adapters[spec.key] = adapter
        return self._adapters[spec.key]

    def keys(self) -> tuple[str, ...]:
        """全部 key，按 `canonical_order` 排序（UI 下拉直接用）。"""
        return tuple(s.key for s in self.specs())

    def specs(self) -> tuple[ProviderSpec, ...]:
        """全部 spec，按 `canonical_order` 排序。"""
        return tuple(sorted(self._specs.values(), key=lambda s: (s.canonical_order, s.key)))

    def as_providers_dict(self) -> dict:
        """派生旧版 `AIClient.PROVIDERS` 的字典结构（向后兼容）。"""
        return {
            spec.key: {
                "name": spec.name,
                "base_url": spec.base_url,
                "models": list(spec.models),
            }
            for spec in self.specs()
        }

    def __contains__(self, key: object) -> bool:
        return key in self._specs

    def __len__(self) -> int:
        return len(self._specs)


_DEFAULT_REGISTRY: ProviderRegistry | None = None


def default_registry() -> ProviderRegistry:
    """内置注册表（进程级缓存，只读使用）。"""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ProviderRegistry(DEFAULT_SPECS)
    return _DEFAULT_REGISTRY


def get_spec(key: str) -> ProviderSpec:
    """便捷函数：从内置注册表取 spec（未知 key 回落 custom）。"""
    return default_registry().resolve(key)


def specs_for_ui(registry: ProviderRegistry | None = None) -> list[dict]:
    """给设置页用的扁平结构：key / 显示名 / 默认地址 / 模型预设 / 能力 / 说明。

    设置页由此**自动生成**下拉与表单（修 P5：不再手工维护第二份清单）。
    """
    reg = registry or default_registry()
    out = []
    for spec in reg.specs():
        out.append({
            "key": spec.key,
            "name": f"{spec.name} ({spec.key})" if spec.key not in spec.name else spec.name,
            "base_url": spec.base_url,
            "models": list(spec.models),
            "default_model": spec.default_model,
            "supports": spec.supports.as_dict(),
            "note": spec.note,
        })
    return out
