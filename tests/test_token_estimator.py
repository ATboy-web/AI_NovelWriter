"""token 估算器测试（v3 §3.5(3)）。

要点：估算器是**单一口径**，所以这里既测公式本身，也测"两处旧散落实现
已被收敛到本模块"——后者是本次改造的实质目标，只测公式会漏掉它。
"""

import sys
from pathlib import Path

import pytest

from app.token_estimator import (
    CONTEXT_SAFETY_DIVISOR,
    HAN_RATIO,
    MESSAGE_OVERHEAD_TOKENS,
    chars_for_context_window,
    chars_for_tokens,
    count_han,
    estimate_messages_tokens,
    estimate_tokens,
    format_tokens,
    truncate_to_tokens,
)

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402


class TestCountHan:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("", 0),
            (None, 0),
            ("abc123", 0),
            ("你好", 2),
            ("你好，世界！", 6),  # 全角标点也计入汉字
            ("中文abc混合", 4),
            ("あいう", 3),  # 假名
            ("한글", 2),  # 谚文
            ("（全角括号）", 6),
        ],
    )
    def test_counts(self, text, expected):
        assert count_han(text) == expected


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_pure_chinese_uses_han_ratio(self):
        assert estimate_tokens("中" * 100) == int(100 * HAN_RATIO + 0.5)

    def test_pure_ascii_uses_other_ratio(self):
        assert estimate_tokens("a" * 400) == 100

    def test_mixed_text_is_between(self):
        mixed = "中文" * 50 + "x" * 400
        assert estimate_tokens(mixed) == int(100 * HAN_RATIO + 400 * 0.25 + 0.5)

    def test_not_undercounting_chinese_like_v2(self):
        """v2 的 `len//2` 对中文低估近 70%；本估算器必须显著高于它。

        这是本次替换的**判据**：如果估算值和旧口径差不多，说明改了个寂寞。
        """
        text = "这是一段中文内容。" * 20
        old_estimate = len(text) // 2
        assert estimate_tokens(text) > old_estimate * 2

    def test_non_string_input(self):
        assert estimate_tokens(12345) > 0

    def test_monotonic(self):
        assert estimate_tokens("中" * 10) < estimate_tokens("中" * 11)


class TestEstimateMessages:
    def test_system_only(self):
        assert estimate_messages_tokens([], "系统提示") == estimate_tokens("系统提示")

    def test_includes_per_message_overhead(self):
        messages = [{"role": "user", "content": "内容"}]
        expected = estimate_tokens("内容") + estimate_tokens("user") + MESSAGE_OVERHEAD_TOKENS
        assert estimate_messages_tokens(messages) == expected

    def test_multimodal_content_counts_text(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "描述"},
                    {"type": "image_url", "image_url": {"url": "http://x/y.png"}},
                ],
            }
        ]
        assert estimate_messages_tokens(messages) > estimate_tokens("描述")

    def test_non_dict_message_falls_back(self):
        assert estimate_messages_tokens(["裸字符串"]) > 0


class TestCharBudget:
    def test_chars_for_tokens_conservative(self):
        assert chars_for_tokens(160) == 100
        assert chars_for_tokens(0) == 0
        assert chars_for_tokens(-5) == 0
        assert chars_for_tokens("bad") == 0

    def test_chars_for_context_window_matches_v2_divisor(self):
        """必须与 v2 `context_window // 3` **等效**（不得暗中放宽预算）。"""
        for window in (32000, 128000, 8000):
            assert chars_for_context_window(window) == window // 3
        assert chars_for_context_window(32000) == 10666
        assert CONTEXT_SAFETY_DIVISOR == 3.0

    def test_truncate_to_tokens(self):
        assert truncate_to_tokens("中" * 1000, 160) == "中" * 100
        assert truncate_to_tokens("abc", 0) == ""
        assert truncate_to_tokens("", 100) == ""


class TestFormatTokens:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "0"),
            (999, "999"),
            (1000, "1.0K"),
            (12345, "12.3K"),
            (1_500_000, "1.5M"),
            (None, "0"),
            ("bad", "0"),
        ],
    )
    def test_format(self, value, expected):
        assert format_tokens(value) == expected


class TestSingleSourceOfTruth:
    """两条旧估算路径必须已改调本模块（源码级断言）。"""

    def test_orchestrator_no_longer_uses_len_half(self):
        code = _scan.code_only("app/agent_orchestrator.py")
        assert "len(context) // 2" not in code
        assert "len(base_prompt) // 2" not in code
        assert "estimate_tokens" in code
        assert "truncate_to_tokens" in code

    def test_novel_agent_delegates_window_conversion(self):
        code = _scan.code_only("app/novel_agent.py")
        assert "chars_for_context_window" in code
        assert '"context_window", 32000) // 3' not in code

    def test_no_third_implementation_creates_a_divisor(self):
        """除了 token_estimator，其它模块不得再自行换算 token。"""
        offenders = []
        for path in (REPO_ROOT / "app").rglob("*.py"):
            if path.name == "token_estimator.py":
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            code = _scan.code_only(rel)
            if "tokens = len(" in code:
                offenders.append(path.name)
        assert offenders == []
