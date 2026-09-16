"""Provider 适配层单测（v3 P2）。

覆盖四件事：

1. **注册表**：声明表派生出的 UI 清单、adapter 映射规则、未知 key 回落
2. **各 adapter 的独立实现**（需求 4）：请求体构造、响应解析、流式分片、usage
3. **P1–P6 六个真实缺陷确实被修掉**（每个都有一条对应断言，防止回归）
4. **余额的诚实性**：没有接口的 provider 必须返回 `supported=False`，而不是抛错或空白
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest

from app.providers import (
    AnthropicAdapter,
    AuthStyle,
    BalanceCache,
    BalanceResult,
    ChatRequest,
    OllamaAdapter,
    OpenAICompatAdapter,
    ProviderRegistry,
    ProviderSpec,
    ReasoningAdapter,
    adapter_class_for,
    default_registry,
    estimate_cost,
    extract_path,
    fetch_balance,
    join_url,
    lookup,
    specs_for_ui,
)

# ==================================================================== 工具


class FakeConfig:
    """最小配置替身（`get(key, default)` 即可满足 AIClient 的读取面）。"""

    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def req(**kwargs) -> ChatRequest:
    base = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
        "system": "sys",
        "max_tokens": 4096,
        "temperature": 0.7,
    }
    base.update(kwargs)
    return ChatRequest(**base)


def adapter_for(key: str):
    return default_registry().adapter(key)


# ==================================================================== 注册表


class TestProviderRegistry:
    def test_all_builtin_providers_are_registered(self):
        """P4：v2 的「伪 provider」（glm/qwen/kimi）必须有真实条目。"""
        reg = default_registry()
        for key in (
            "ollama",
            "openai",
            "deepseek",
            "claude",
            "glm",
            "qwen",
            "kimi",
            "mimo",
            "siliconflow",
            "together",
            "groq",
            "dashscope",
            "custom",
        ):
            assert key in reg, f"{key} 未注册"

    def test_every_provider_has_a_base_url_except_custom(self):
        """P4 的根因断言：除 custom（需用户填写）外，每家必须有默认地址。

        v2 里 glm/qwen/kimi 没有 base_url，导致「检测到 qwen，参数却发到 openai」。
        """
        for spec in default_registry().specs():
            if spec.key == "custom":
                assert spec.base_url == ""
                continue
            assert spec.base_url.startswith(("http://", "https://")), spec.key

    def test_keys_are_ordered_by_canonical_order(self):
        keys = default_registry().keys()
        assert keys[0] == "ollama"  # 本地排最前
        assert keys[-1] == "custom"  # 兜底排最后

    def test_unknown_key_falls_back_to_custom(self):
        reg = default_registry()
        assert reg.resolve("no_such_provider").key == "custom"
        assert reg.get("no_such_provider") is None

    def test_adapter_class_mapping_rules(self):
        reg = default_registry()
        assert isinstance(reg.adapter("ollama"), OllamaAdapter)
        assert isinstance(reg.adapter("claude"), AnthropicAdapter)
        # 声明了 thinking_style 的走 ReasoningAdapter
        for key in ("deepseek", "glm", "qwen", "kimi"):
            assert isinstance(reg.adapter(key), ReasoningAdapter), key
        # 其余走通用 OpenAI 兼容
        for key in ("openai", "mimo", "siliconflow", "together", "groq"):
            assert isinstance(reg.adapter(key), OpenAICompatAdapter), key
            assert not isinstance(reg.adapter(key), ReasoningAdapter), key

    def test_adapter_instances_are_cached(self):
        reg = default_registry()
        assert reg.adapter("deepseek") is reg.adapter("deepseek")

    def test_labels_are_provider_specific(self):
        """报错信息要能看出是哪一家，而不是笼统的「OpenAI兼容API」。"""
        reg = default_registry()
        assert reg.adapter("deepseek").label == "DeepSeek"
        assert reg.adapter("openai").label == "OpenAI"
        # 自有 label 不被覆盖
        assert reg.adapter("claude").label == "Claude"
        assert reg.adapter("ollama").label == "Ollama"

    def test_auth_styles(self):
        reg = default_registry()
        assert reg.get("claude").auth == AuthStyle.X_API_KEY
        assert reg.get("ollama").auth == AuthStyle.NONE
        assert reg.get("deepseek").auth == AuthStyle.BEARER

    def test_capability_flags_are_declarative(self):
        reg = default_registry()
        assert reg.get("ollama").supports.local is True
        assert reg.get("ollama").supports.balance is False
        assert reg.get("deepseek").supports.balance is True
        assert reg.get("deepseek").supports.thinking is True
        assert reg.get("openai").supports.thinking is False

    def test_providers_dict_is_derived_from_registry(self):
        """`AIClient.PROVIDERS` 不该是手工维护的第二份清单。"""
        from app.ai_client import AIClient

        reg = default_registry()
        assert set(AIClient.PROVIDERS) == set(reg.keys())
        assert AIClient.PROVIDERS["openai"]["models"] == list(reg.get("openai").models)

    def test_specs_for_ui_exposes_what_settings_page_needs(self):
        """P5：设置页下拉由这里自动生成，不再手工维护。"""
        items = specs_for_ui()
        keys = [item["key"] for item in items]
        assert keys == list(default_registry().keys())
        first = items[0]
        for field in ("key", "name", "base_url", "models", "default_model", "supports", "note"):
            assert field in first

    def test_registry_register_is_extensible(self):
        reg = ProviderRegistry()
        spec = ProviderSpec(key="myapi", name="My API", base_url="https://x.example.com/v1", base_url_includes_v1=True)
        reg.register(spec)
        assert reg.get("myapi") is spec
        assert isinstance(reg.adapter("myapi"), OpenAICompatAdapter)

    def test_adapter_class_for_respects_override(self):
        spec = ProviderSpec(key="ollama", name="x", base_url="http://localhost:11434")
        assert adapter_class_for(spec) is OllamaAdapter


class TestDeprecatedModelNamesRefreshed:
    """§9.10：内置模型清单里的 3 处过时项已刷新。"""

    def test_claude_models_are_current_generation(self):
        models = default_registry().get("claude").models
        assert "claude-sonnet-5" in models
        # 已退役世代不应再作为内置推荐
        assert not any("3-5-sonnet" in m for m in models)
        assert not any("20250514" in m for m in models)

    def test_deepseek_deprecated_model_not_advertised(self):
        models = default_registry().get("deepseek").models
        assert "deepseek-chat" not in models
        assert "deepseek-v4-flash" in models

    def test_kimi_v1_generation_removed(self):
        models = default_registry().get("kimi").models
        assert "moonshot-v1-128k" not in models
        assert "kimi-k2.6" in models

    def test_old_names_still_have_a_fallback_target(self):
        """老配置里的旧模型名不该直接失效，至少能降级到在售模型。"""
        from app.ai_client import AIClient

        assert AIClient.FALLBACK_CHAIN["claude-sonnet-4-20250514"] == "claude-sonnet-5"
        assert AIClient.FALLBACK_CHAIN["deepseek-chat"] == "deepseek-v4-flash"


# ==================================================================== URL 拼接


class TestJoinUrl:
    """P2：`/v1` 拼接必须显式，不再靠隐式行为。"""

    def test_base_with_v1_plus_plain_path(self):
        assert (
            join_url("https://api.openai.com/v1", "/chat/completions", True)
            == "https://api.openai.com/v1/chat/completions"
        )

    def test_v1_is_not_duplicated(self):
        """这是 P2 的核心：base 有 /v1 且 path 也有 /v1 时只保留一个。"""
        assert (
            join_url("https://x.example.com/v1", "/v1/chat/completions", True)
            == "https://x.example.com/v1/chat/completions"
        )

    def test_base_without_v1_keeps_path_v1(self):
        assert join_url("https://api.anthropic.com", "/v1/messages", False) == "https://api.anthropic.com/v1/messages"

    def test_trailing_slash_on_base_is_normalised(self):
        assert (
            join_url("https://api.deepseek.com/", "/chat/completions", False)
            == "https://api.deepseek.com/chat/completions"
        )

    def test_empty_base_returns_path(self):
        assert join_url("", "/chat/completions") == "/chat/completions"

    def test_resolved_url_uses_spec_defaults_when_config_empty(self):
        assert default_registry().get("deepseek").resolved_url("") == "https://api.deepseek.com/chat/completions"

    def test_resolved_url_prefers_configured_base(self):
        spec = default_registry().get("claude")
        assert spec.resolved_url("https://my-proxy.example.com") == "https://my-proxy.example.com/v1/messages"


# ================================================== OpenAI 兼容 adapter


class TestOpenAICompatAdapter:
    def test_build_request_body(self):
        prepared = adapter_for("openai").build_request(req())
        assert prepared.path == "/chat/completions"
        assert prepared.method == "POST"
        body = prepared.json_body
        assert body["model"] == "test-model"
        assert body["max_tokens"] == 4096
        assert body["temperature"] == 0.7
        # system 作为首条 message
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["messages"][1]["role"] == "user"

    def test_stream_flag_only_when_requested(self):
        assert "stream" not in adapter_for("openai").build_request(req()).json_body
        assert adapter_for("openai").build_request(req(stream=True)).json_body["stream"] is True

    def test_extra_body_is_merged(self):
        spec = ProviderSpec(key="x", name="x", base_url="https://x.example.com", extra_body={"top_p": 0.9})
        adapter = OpenAICompatAdapter(spec)
        assert adapter.build_request(req()).json_body["top_p"] == 0.9

    def test_extra_body_does_not_override_explicit_fields(self):
        spec = ProviderSpec(key="x", name="x", base_url="https://x.example.com", extra_body={"model": "hijacked"})
        adapter = OpenAICompatAdapter(spec)
        assert adapter.build_request(req()).json_body["model"] == "test-model"

    def test_request_extra_overrides(self):
        prepared = adapter_for("openai").build_request(req(extra={"top_p": 0.5}))
        assert prepared.json_body["top_p"] == 0.5

    def test_parse_response(self):
        result = adapter_for("openai").parse_response(
            {
                "choices": [{"message": {"content": "hello", "reasoning_content": "think"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }
        )
        assert result.text == "hello"
        assert result.reasoning == "think"
        assert result.finish_reason == "stop"
        assert result.usage.total_tokens == 30
        assert result.usage.estimated is False

    def test_parse_response_without_choices_raises(self):
        with pytest.raises(Exception, match="无choices"):
            adapter_for("deepseek").parse_response({"choices": []})

    def test_parse_response_error_mentions_provider(self):
        with pytest.raises(Exception, match="DeepSeek"):
            adapter_for("deepseek").parse_response({})

    def test_usage_reads_openai_cached_tokens(self):
        usage = adapter_for("openai")._parse_usage(
            {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": 64}}
        )
        assert usage.cached_tokens == 64

    def test_usage_reads_deepseek_cached_tokens(self):
        """DeepSeek 把缓存命中放在顶层 `prompt_cache_hit_tokens`。"""
        usage = adapter_for("deepseek")._parse_usage(
            {"prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 32}
        )
        assert usage.cached_tokens == 32

    def test_usage_total_is_derived_when_absent(self):
        usage = adapter_for("openai")._parse_usage({"prompt_tokens": 7, "completion_tokens": 3})
        assert usage.total_tokens == 10

    def test_usage_of_none_is_empty(self):
        assert adapter_for("openai")._parse_usage(None).is_empty

    def test_stream_chunk_parses_content(self):
        delta = adapter_for("openai").parse_stream_chunk('data: {"choices": [{"delta": {"content": "Hi"}}]}')
        assert delta.text == "Hi"
        assert delta.done is False

    def test_stream_chunk_parses_reasoning(self):
        delta = adapter_for("deepseek").parse_stream_chunk(
            'data: {"choices": [{"delta": {"reasoning_content": "hmm"}}]}'
        )
        assert delta.reasoning == "hmm"

    def test_stream_chunk_done_marker(self):
        assert adapter_for("openai").parse_stream_chunk("data: [DONE]").done is True

    def test_stream_chunk_ignores_non_data_lines(self):
        adapter = adapter_for("openai")
        assert adapter.parse_stream_chunk("") is None
        assert adapter.parse_stream_chunk("event: ping") is None

    def test_stream_chunk_tolerates_broken_json(self):
        assert adapter_for("openai").parse_stream_chunk("data: {not json") is None

    def test_auth_headers_bearer(self):
        assert adapter_for("openai").auth_headers("k") == {"Authorization": "Bearer k"}

    def test_auth_headers_no_key_is_empty(self):
        assert adapter_for("openai").auth_headers("") == {}


# ================================================== 思考模式 adapter


class TestReasoningAdapter:
    def test_deepseek_thinking_adds_params_and_drops_temperature(self):
        body = adapter_for("deepseek").build_request(req(thinking_enabled=True)).json_body
        assert body["thinking"] == {"type": "enabled"}
        assert body["reasoning_effort"] == "medium"
        assert "temperature" not in body

    def test_deepseek_without_thinking_keeps_temperature(self):
        body = adapter_for("deepseek").build_request(req(thinking_enabled=False)).json_body
        assert "thinking" not in body
        assert body["temperature"] == 0.7

    def test_small_request_disables_thinking(self):
        """v2 的保护必须保留：小请求开思考会把预算耗光，content 为空。"""
        for key in ("deepseek", "glm", "qwen", "kimi"):
            body = adapter_for(key).build_request(req(thinking_enabled=True, max_tokens=500)).json_body
            assert "thinking" not in body, key
            assert "enable_thinking" not in body, key

    def test_threshold_boundary(self):
        body = adapter_for("deepseek").build_request(req(thinking_enabled=True, max_tokens=1000)).json_body
        assert body["thinking"] == {"type": "enabled"}

    def test_glm_forces_temperature_to_one(self):
        body = adapter_for("glm").build_request(req(thinking_enabled=True, model="glm-5.2")).json_body
        assert body["temperature"] == 1.0
        assert body["thinking"] == {"type": "enabled"}

    def test_glm_reasoning_effort_only_for_newer_generations(self):
        new = adapter_for("glm").build_request(req(thinking_enabled=True, model="glm-5.2")).json_body
        old = adapter_for("glm").build_request(req(thinking_enabled=True, model="glm-4.7-flash")).json_body
        assert "reasoning_effort" in new
        assert "reasoning_effort" not in old

    def test_qwen_uses_enable_thinking_and_budget(self):
        body = adapter_for("qwen").build_request(req(thinking_enabled=True, max_tokens=4000)).json_body
        assert body["enable_thinking"] is True
        assert body["thinking_budget"] == 2000

    def test_kimi_sets_keep_all_and_drops_temperature(self):
        body = adapter_for("kimi").build_request(req(thinking_enabled=True, model="kimi-k2.6")).json_body
        assert body["thinking"] == {"type": "enabled", "keep": "all"}
        assert "temperature" not in body

    def test_kimi_k27_rejects_thinking_param(self):
        """kimi-k2.7-code 始终思考，不接受 thinking 参数。"""
        body = adapter_for("kimi").build_request(req(thinking_enabled=True, model="kimi-k2.7-code")).json_body
        assert "thinking" not in body

    def test_non_reasoning_provider_never_gets_thinking_fields(self):
        """openai 声明 supports.thinking=False，即使 UI 打开了也不能发未定义字段。"""
        body = adapter_for("openai").build_request(req(thinking_enabled=True)).json_body
        for field in ("thinking", "enable_thinking", "thinking_budget", "reasoning_effort"):
            assert field not in body


# ================================================== Anthropic adapter


class TestAnthropicAdapter:
    def test_path_is_messages_not_chat_completions(self):
        assert adapter_for("claude").build_request(req()).path == "/v1/messages"

    def test_system_is_top_level_not_in_messages(self):
        body = adapter_for("claude").build_request(req()).json_body
        assert body["system"] == "sys"
        assert all(m["role"] != "system" for m in body["messages"])
        assert body["messages"] == [{"role": "user", "content": "hi"}]

    def test_max_tokens_is_sent(self):
        """Anthropic 的 max_tokens 是必填项。"""
        assert adapter_for("claude").build_request(req(max_tokens=1234)).json_body["max_tokens"] == 1234

    def test_auth_is_x_api_key_not_bearer(self):
        headers = adapter_for("claude").auth_headers("secret")
        assert headers == {"x-api-key": "secret"}
        assert "Authorization" not in headers

    def test_default_headers_carry_anthropic_version(self):
        prepared = adapter_for("claude").build_request(req())
        assert prepared.headers.get("anthropic-version") == "2023-06-01"

    def test_parse_response_skips_non_text_blocks(self):
        """v2 硬取 content[0]；首块是 thinking 时会返回空字符串。"""
        result = adapter_for("claude").parse_response(
            {
                "content": [
                    {"type": "thinking", "thinking": "internal"},
                    {"type": "text", "text": "answer"},
                ]
            }
        )
        assert result.text == "answer"

    def test_parse_response_joins_multiple_text_blocks(self):
        result = adapter_for("claude").parse_response(
            {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
        )
        assert result.text == "ab"

    def test_parse_response_without_content_raises(self):
        with pytest.raises(Exception, match="无内容"):
            adapter_for("claude").parse_response({"content": []})

    def test_usage_uses_input_output_names(self):
        """P6：Claude 的 usage 在 v2 里完全没被解析。"""
        usage = adapter_for("claude")._parse_usage(
            {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 20}
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.cached_tokens == 20

    def test_stream_chunk_content_block_delta(self):
        delta = adapter_for("claude").parse_stream_chunk(
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}}'
        )
        assert delta.text == "x"

    def test_stream_chunk_message_delta_carries_usage(self):
        delta = adapter_for("claude").parse_stream_chunk(
            'data: {"type": "message_delta", "usage": {"output_tokens": 5}}'
        )
        assert delta.usage.completion_tokens == 5
        assert delta.text == ""

    def test_stream_chunk_message_stop_is_done(self):
        assert adapter_for("claude").parse_stream_chunk('data: {"type": "message_stop"}').done is True

    def test_stream_chunk_ignores_unknown_events(self):
        assert adapter_for("claude").parse_stream_chunk('data: {"type": "ping"}') is None


# ================================================== Ollama adapter


class TestOllamaAdapter:
    def test_path_and_options_shape(self):
        prepared = adapter_for("ollama").build_request(req(temperature=0.3, max_tokens=2048))
        assert prepared.path == "/api/chat"
        assert prepared.json_body["options"] == {"temperature": 0.3, "num_predict": 2048}

    def test_stream_flag_is_explicit_false_by_default(self):
        assert adapter_for("ollama").build_request(req()).json_body["stream"] is False

    def test_no_auth_header(self):
        assert adapter_for("ollama").auth_headers("whatever") == {}

    def test_parse_response(self):
        result = adapter_for("ollama").parse_response({"message": {"content": "hi"}})
        assert result.text == "hi"

    def test_usage_reads_top_level_counters(self):
        """P6：v2 完全没解析这两个字段。"""
        result = adapter_for("ollama").parse_response(
            {"message": {"content": "x"}, "prompt_eval_count": 12, "eval_count": 34}
        )
        assert result.usage.prompt_tokens == 12
        assert result.usage.completion_tokens == 34
        assert result.usage.total_tokens == 46

    def test_stream_chunk_bare_json_without_data_prefix(self):
        """Ollama 流式是裸 JSON 行，与 OpenAI / Anthropic 都不同。"""
        delta = adapter_for("ollama").parse_stream_chunk('{"message": {"content": "Hi"}}')
        assert delta.text == "Hi"
        # 带 data: 前缀反而不该被解析
        assert adapter_for("ollama").parse_stream_chunk('data: {"message": {"content": "Hi"}}') is None

    def test_stream_chunk_final_chunk_carries_usage(self):
        delta = adapter_for("ollama").parse_stream_chunk('{"done": true, "prompt_eval_count": 5, "eval_count": 6}')
        assert delta.done is True
        assert delta.usage.total_tokens == 11


# ================================================== 余额


class TestExtractPath:
    def test_nested_dict_and_list(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "110.00"}]}
        assert extract_path(data, "balance_infos.0.currency") == "CNY"
        assert extract_path(data, "balance_infos.0.total_balance") == "110.00"

    def test_missing_path_returns_none(self):
        assert extract_path({}, "a.b") is None
        assert extract_path({"a": 1}, "a.b") is None

    def test_out_of_range_index_returns_none(self):
        assert extract_path({"a": []}, "a.0") is None

    def test_empty_path_returns_none(self):
        assert extract_path({"a": 1}, "") is None


class TestBalanceResultHonesty:
    """没有余额接口时必须明说，不能报错或空白。"""

    def test_unsupported_has_a_message_not_an_error(self):
        result = BalanceResult.not_supported("glm")
        assert result.supported is False
        assert result.error == ""
        assert "未提供公开余额接口" in result.format_total()

    def test_openai_explains_why(self):
        text = BalanceResult.not_supported("openai").format_total()
        assert "session key" in text

    def test_ollama_says_local_no_billing(self):
        assert "本地模型" in BalanceResult.not_supported("ollama").format_total()

    def test_failure_is_distinct_from_unsupported(self):
        failed = BalanceResult.failed("deepseek", "HTTP 500")
        assert failed.supported is True
        assert failed.ok is False
        assert "500" in failed.format_total()

    def test_ok_result_formats_with_currency_and_grant(self):
        result = BalanceResult(provider="deepseek", supported=True, currency="CNY", total="110.00", granted="10.00")
        text = result.format_total()
        assert "110.00" in text and "CNY" in text and "赠金" in text

    def test_ok_requires_total(self):
        assert BalanceResult(provider="x", supported=True).ok is False


class TestFetchBalance:
    def _deepseek_payload(self):
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "110.00",
                    "granted_balance": "10.00",
                    "topped_up_balance": "100.00",
                }
            ],
        }

    def test_deepseek_probe_parses_fields(self):
        def http_get(url, headers, timeout):
            assert url == "https://api.deepseek.com/user/balance"
            assert headers["Authorization"] == "Bearer k"
            return httpx.Response(200, json=self._deepseek_payload())

        result = fetch_balance(
            default_registry().get("deepseek"),
            http_get,
            api_key="k",
            base_url="https://api.deepseek.com",
        )
        assert result.ok is True
        assert result.currency == "CNY"
        assert result.total == "110.00"
        assert result.granted == "10.00"
        assert result.topped_up == "100.00"

    def test_provider_without_endpoint_never_calls_http(self):
        called = []

        def http_get(url, headers, timeout):
            called.append(url)
            return httpx.Response(200, json={})

        result = fetch_balance(default_registry().get("glm"), http_get, api_key="k")
        assert result.supported is False
        assert called == []

    def test_kimi_is_honest_about_unconfigured_endpoint(self):
        """不臆造端点：未内置就明说"需在设置中填写"。"""
        result = fetch_balance(default_registry().get("kimi"), lambda *a: None, api_key="k")
        assert result.supported is False
        assert "设置" in result.format_total()

    def test_user_can_supply_balance_url(self):
        def http_get(url, headers, timeout):
            assert url == "https://custom.example.com/bal"
            return httpx.Response(200, json={"data": {"amount": 42, "unit": "USD"}})

        result = fetch_balance(
            default_registry().get("kimi"),
            http_get,
            api_key="k",
            override_url="https://custom.example.com/bal",
            override_paths={"total": "data.amount", "currency": "data.unit"},
        )
        assert result.ok is True
        assert result.total == 42
        assert result.currency == "USD"

    def test_http_error_becomes_failure_not_exception(self):
        def http_get(url, headers, timeout):
            return httpx.Response(401)

        result = fetch_balance(
            default_registry().get("deepseek"), http_get, api_key="k", base_url="https://api.deepseek.com"
        )
        assert result.error == "HTTP 401"

    def test_network_exception_becomes_failure(self):
        def http_get(url, headers, timeout):
            raise httpx.ConnectError("boom")

        result = fetch_balance(
            default_registry().get("deepseek"), http_get, api_key="k", base_url="https://api.deepseek.com"
        )
        assert "ConnectError" in result.error

    def test_changed_api_shape_is_reported_not_silently_zero(self):
        """接口改了字段名时，必须说"未找到余额字段"，而不是显示余额为 0。"""

        def http_get(url, headers, timeout):
            return httpx.Response(200, json={"unexpected": True})

        result = fetch_balance(
            default_registry().get("deepseek"), http_get, api_key="k", base_url="https://api.deepseek.com"
        )
        assert result.supported is True
        assert result.total is None
        assert "未找到余额字段" in result.format_total()


class TestBalanceCache:
    def test_cache_hit_avoids_second_request(self):
        calls = []

        def http_get(url, headers, timeout):
            calls.append(url)
            return httpx.Response(200, json={"balance_infos": [{"total_balance": "5"}]})

        cache = BalanceCache(ttl=60)
        spec = default_registry().get("deepseek")
        for _ in range(3):
            fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache)
        assert len(calls) == 1

    def test_expired_cache_refetches(self):
        calls = []

        def http_get(url, headers, timeout):
            calls.append(url)
            return httpx.Response(200, json={"balance_infos": [{"total_balance": "5"}]})

        cache = BalanceCache(ttl=60)
        spec = default_registry().get("deepseek")
        fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache, now=1000.0)
        fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache, now=1100.0)
        assert len(calls) == 2

    def test_cached_result_is_marked(self):
        def http_get(url, headers, timeout):
            return httpx.Response(200, json={"balance_infos": [{"total_balance": "5"}]})

        cache = BalanceCache(ttl=60)
        spec = default_registry().get("deepseek")
        fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache, now=1.0)
        second = fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache, now=2.0)
        assert second.cached is True
        assert "缓存" in second.format_total()

    def test_failures_are_not_cached(self):
        """一次网络抖动不该让用户 60s 内反复看到同一个错误。"""
        calls = []

        def http_get(url, headers, timeout):
            calls.append(url)
            return httpx.Response(500)

        cache = BalanceCache(ttl=60)
        spec = default_registry().get("deepseek")
        for _ in range(2):
            fetch_balance(spec, http_get, api_key="k", base_url="https://api.deepseek.com", cache=cache)
        assert len(calls) == 2


# ================================================== 价目表


class TestPricingTiers:
    """§9.9 约束 2：Qwen 阶梯计费，扁平二元组表达不了。"""

    def test_tier_selected_by_input_size(self):
        price = lookup("qwen", "qwen3-max")
        assert price.tier_for(10_000).input == 2.5
        assert price.tier_for(64_000).input == 4
        assert price.tier_for(200_000).input == 7
        assert price.tier_for(999_999).output == 28

    def test_whole_request_billed_at_selected_tier(self):
        # 200k 输入落在 ≤256K 档（7/28），而非分段累加
        est = estimate_cost("qwen", "qwen3-max", 200_000, 5_000)
        expected = (200_000 * 7 + 5_000 * 28) / 1_000_000
        assert est.cost == pytest.approx(expected)
        assert est.currency == "CNY"

    def test_tier_note_is_emitted(self):
        est = estimate_cost("qwen", "qwen3-max", 200_000, 100)
        assert any("阶梯" in note for note in est.notes)

    def test_single_tier_model(self):
        est = estimate_cost("qwen", "qwen-plus", 1_000, 1_000)
        assert est.cost == pytest.approx((1_000 * 0.8 + 1_000 * 2) / 1_000_000)


class TestPricingCached:
    """§9.9 约束 1：缓存价独立，价差可达 50 倍。"""

    def test_cached_tokens_use_cached_rate(self):
        est = estimate_cost("deepseek", "deepseek-v4-pro", 1_000_000, 1_000_000, cached_tokens=500_000)
        expected = (500_000 * 3 + 500_000 * 0.025 + 1_000_000 * 6) / 1_000_000
        assert est.cost == pytest.approx(expected)

    def test_without_cached_rate_falls_back_to_input_rate(self):
        est = estimate_cost("openai", "gpt-4o", 1_000_000, 0, cached_tokens=500_000)
        assert est.cost == pytest.approx(2.50)

    def test_cached_tokens_cannot_exceed_prompt(self):
        est = estimate_cost("openai", "gpt-4o", 100, 0, cached_tokens=999_999)
        assert est.cost == pytest.approx(100 * 2.50 / 1_000_000)


class TestPricingCurrenciesAndRegions:
    """§9.9 约束 3、4：币种与区域不能混为一谈。"""

    def test_currency_differs_by_provider(self):
        assert lookup("deepseek", "deepseek-v4-pro").currency == "CNY"
        assert lookup("claude", "claude-sonnet-5").currency == "USD"

    def test_region_specific_price(self):
        cn = lookup("mimo", "mimo-v2.5-pro", "cn")
        intl = lookup("mimo", "mimo-v2.5-pro", "international")
        assert cn.currency == "CNY"
        assert intl.currency == "USD"
        assert cn.input != intl.input

    def test_unknown_region_falls_back_to_any_region_of_same_model(self):
        assert lookup("mimo", "mimo-v2.5-pro", "default") is not None

    def test_free_model_costs_zero_without_note(self):
        est = estimate_cost("glm", "glm-4.7-flash", 1_000_000, 1_000_000)
        assert est.cost == 0.0
        assert est.currency == "CNY"
        assert est.reliable is True

    def test_local_model_is_free(self):
        est = estimate_cost("ollama", "qwen2.5:14b", 10_000, 10_000)
        assert est.cost == 0.0


class TestPricingHonesty:
    """价格会变，UI 必须能看出置信度与查证时间。"""

    def test_unknown_model_is_not_silently_free(self):
        est = estimate_cost("openai", "gpt-9-ultra", 1_000_000, 1_000_000)
        assert est.priced is False
        assert est.currency == ""
        assert "无内置价目" in est.format()

    def test_aggregate_confidence_is_flagged(self):
        est = estimate_cost("kimi", "kimi-k2.6", 1_000_000, 0, region="international")
        assert any("aggregate" in note for note in est.notes)
        assert est.reliable is False

    def test_official_price_is_reliable(self):
        est = estimate_cost("deepseek", "deepseek-v4-flash", 1_000_000, 0)
        assert est.reliable is True
        assert est.notes == []

    def test_estimated_usage_is_flagged(self):
        est = estimate_cost("deepseek", "deepseek-v4-flash", 1000, 1000, estimated=True)
        assert any("估算" in note for note in est.notes)
        assert est.reliable is False

    def test_every_price_carries_provenance(self):
        """每条价都必须能追溯：查证日期 + 来源或说明 + 可编辑。

        「可编辑」是刚需 —— 价格会变，用户得能自己改，不能等发版。
        """
        from app.providers import PRICING

        for price in PRICING:
            assert price.verified_at, price
            assert price.editable is True, price
            assert price.confidence in ("official", "aggregate", "unverified"), price
            if price.is_free:
                # 零价不是"报价"，而是"这家不计费"这一事实，没有定价页可引；
                # 但必须写清原因，否则用户会怀疑是漏填。
                assert price.note, price
                continue
            # 官方价必须有出处；聚合价至少要有说明，别让用户以为它同样可靠
            assert price.source_url or price.note, price
            if price.confidence == "official":
                assert price.source_url, price

    def test_cost_estimate_serialises_for_ui(self):
        data = estimate_cost("deepseek", "deepseek-v4-flash", 100, 100).as_dict()
        for field in ("cost", "currency", "priced", "reliable", "notes", "price"):
            assert field in data


# ================================================== 端到端：端点解析（P1/P2/P4）


class TestEndpointResolutionFixes:
    """用 `preview_url` 直接验证 P1 / P2 / P4 三处缺陷已修。

    选 `preview_url` 而不是发真请求：它算的正是 `_resolve_endpoint` 的最终 URL，
    即这三处缺陷的判定依据本身。
    """

    def _client(self, **values):
        from app.ai_client import AIClient

        values.setdefault("api_provider", "ollama")
        values.setdefault("api_key", "")
        values.setdefault("api_base", "")
        values.setdefault("model", "")
        return AIClient(FakeConfig(**values))

    def test_p1_claude_respects_configured_api_base(self):
        """P1：v2 对 claude 硬编码 api.anthropic.com，用户无法用中转地址。"""
        client = self._client(
            api_provider="claude",
            api_key="sk-1234567890",
            api_base="https://my-proxy.example.com",
            model="claude-sonnet-5",
        )
        assert client.preview_url() == "https://my-proxy.example.com/v1/messages"

    def test_claude_falls_back_to_default_when_unset(self):
        client = self._client(api_provider="claude", api_key="sk-1234567890", model="claude-sonnet-5")
        assert client.preview_url() == "https://api.anthropic.com/v1/messages"

    def test_p2_no_v1_duplication_anywhere(self):
        """P2：遍历全部 provider，任何组合都不该出现 /v1/v1。"""
        reg = default_registry()
        for spec in reg.specs():
            if not spec.base_url:
                continue
            url = spec.resolved_url(spec.base_url)
            assert "/v1/v1" not in url, spec.key
            assert "//chat" not in url, spec.key

    def test_p4_qwen_model_while_openai_selected_goes_to_qwen(self):
        """P4 的核心场景：填了 qwen 模型名却选了 openai，参数不该发到 openai。"""
        client = self._client(
            api_provider="openai", api_key="sk-1234567890", api_base="https://api.openai.com/v1", model="qwen3-max"
        )
        assert client.preview_url() == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def test_p4_glm_and_kimi_also_route_correctly(self):
        openai_base = "https://api.openai.com/v1"
        glm = self._client(api_provider="openai", api_key="sk-1234567890", api_base=openai_base, model="glm-5.2")
        kimi = self._client(api_provider="openai", api_key="sk-1234567890", api_base=openai_base, model="kimi-k2.6")
        assert "bigmodel.cn" in glm.preview_url()
        assert "moonshot.cn" in kimi.preview_url()

    def test_same_provider_still_honours_user_base(self):
        """检测结果与配置一致时，用户的代理地址必须照常生效。"""
        client = self._client(
            api_provider="deepseek",
            api_key="sk-1234567890",
            api_base="https://my-relay.example.com",
            model="deepseek-v4-pro",
        )
        assert client.preview_url() == "https://my-relay.example.com/chat/completions"

    def test_preview_reports_configuration_error_instead_of_raising(self):
        """把地址改成明文 HTTP 后，预览应回一句人话而不是抛异常。

        构造时用的是合法 https 地址（否则 `_init_client` 的 S7 校验会先抛），
        之后再把配置改成不合法值 —— 这时预览必须仍然可用。
        """
        client = self._client(
            api_provider="deepseek",
            api_key="sk-1234567890",
            api_base="https://api.deepseek.com",
            model="deepseek-v4-pro",
        )
        client.config.values["api_base"] = "http://api.deepseek.com"
        assert "配置有误" in client.preview_url()

    def test_custom_provider_without_base_says_unconfigured(self):
        client = self._client(api_provider="custom", api_key="sk-1234567890", model="m")
        assert "未配置" in client.preview_url()

    def test_capabilities_are_queryable(self):
        assert self._client(api_provider="deepseek").capabilities()["balance"] is True
        assert self._client(api_provider="openai").capabilities()["balance"] is False


class TestClientConfiguredByCapability:
    """是否需要密钥由 spec.auth 决定，而不是按 provider 名硬编码。"""

    def _client(self, **values):
        from app.ai_client import AIClient

        values.setdefault("api_key", "")
        values.setdefault("api_base", "")
        values.setdefault("model", "")
        return AIClient(FakeConfig(**values))

    def test_local_provider_needs_no_key(self):
        assert self._client(api_provider="ollama", api_base="http://localhost:11434").is_configured() is True

    def test_remote_provider_without_key_is_unconfigured(self):
        assert self._client(api_provider="deepseek", api_base="https://api.deepseek.com").is_configured() is False

    def test_remote_provider_with_key_is_configured(self):
        assert (
            self._client(
                api_provider="deepseek", api_key="sk-1234567890", api_base="https://api.deepseek.com"
            ).is_configured()
            is True
        )

    def test_unknown_provider_falls_back_to_custom_and_is_unconfigured(self):
        assert self._client(api_provider="nope").is_configured() is False

    def test_plaintext_http_to_remote_is_still_rejected(self):
        with pytest.raises(ValueError, match="明文 HTTP"):
            self._client(api_provider="deepseek", api_key="sk-1234567890", api_base="http://api.deepseek.com")
