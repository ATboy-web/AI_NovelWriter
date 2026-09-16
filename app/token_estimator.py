"""Token 估算（v3 §3.5(3)）。

## 为什么需要它

provider 不一定返回 `usage`（本地模型、部分聚合平台、异常中断的流式响应）。
v2 在这些场景下干脆**不记账**，于是「用了多少 token」这件事在部分链路上是盲区。
现在统一用估算兜底，并打上 `estimated=True` —— UI 必须把「实测」与「估算」区分开。

## 为什么不用 tiktoken

`tiktoken` 只覆盖 OpenAI 系（对 DeepSeek / GLM / Qwen / Claude 都是近似），
且带一份 BPE 词表 + Rust 扩展，会明显增大打包体积（当前 EXE 约 19MB，
`installer/novel_app.spec` 里已经在 `excludes` 掉 numpy 一类重依赖）。
投入产出比不支持。

## 公式

    tokens ≈ 汉字数 × 1.6 + 非汉字字符数 ÷ 4

- 汉字（含 CJK 标点、假名、谚文）按 **1.6 字/token**：主流分词器对中文
  大致是 1 字 → 1.5~1.7 token。
- 其余字符按 **4 字符/token**：这是英文 BPE 的经验值。

对照 v2 两处散落实现：`agent_orchestrator.py` 的 `len(context)//2` 对中文
**明显低估**（实测偏差可达 40%+），`novel_agent.py` 的 `context_window//3`
则是另一个毫无关系的口径。本模块是这两处（以及后续所有新增调用点）的**唯一实现**。
"""

from __future__ import annotations

import re

__all__ = [
    "HAN_RATIO",
    "OTHER_RATIO",
    "MESSAGE_OVERHEAD_TOKENS",
    "CONTEXT_SAFETY_DIVISOR",
    "count_han",
    "estimate_tokens",
    "estimate_messages_tokens",
    "chars_for_tokens",
    "chars_for_context_window",
    "truncate_to_tokens",
    "format_tokens",
]

#: 汉字（CJK 表意文字 + 假名 + 谚文 + 全角标点）每字符折算的 token 数。
HAN_RATIO = 1.6

#: 非汉字字符（ASCII 字母/数字/空白/半角标点）每字符折算的 token 数。
OTHER_RATIO = 0.25            # 即 4 字符 / token

#: 每条消息的角色/分隔符开销（对齐 OpenAI 的 "每消息 +4 tokens" 经验值）。
MESSAGE_OVERHEAD_TOKENS = 4

#: 「模型上下文窗口 token 数 → 可注入字符数」的保守除数。
#:
#: 纯按 `HAN_RATIO` 换算会得到「32000 token ≈ 20000 汉字」，但窗口里还要装
#: 提示词模板、写作指令、角色/世界观设定**以及输出预算**。v2 在
#: `novel_agent._build_context_by_phase` 里用的是 `context_window // 3`
#: （32000 → 10666 字符）。本常量把那处口径**原样搬到这里**，只做单一来源化，
#: **不改变既有取值** —— 无端放宽会推高 prompt 体积、成本与超限风险。
CONTEXT_SAFETY_DIVISOR = 3.0

# 汉字的判定范围：
#   U+2E80-U+303F  CJK 部首补充 / 标点（含 《》「」、。等全角标点）
#   U+3040-U+30FF  日文假名
#   U+3130-U+318F  谚文字母
#   U+3400-U+4DBF  CJK 扩展 A
#   U+4E00-U+9FFF  CJK 基本区
#   U+F900-U+FAFF  CJK 兼容表意文字
#   U+AC00-U+D7AF  谚文音节
#   U+FF00-U+FFEF  全角形式（全角字母/数字/标点）
_HAN_RE = re.compile(
    "["
    "\u2e80-\u303f"
    "\u3040-\u30ff"
    "\u3130-\u318f"
    "\u3400-\u4dbf"
    "\u4e00-\u9fff"
    "\uf900-\ufaff"
    "\uac00-\ud7af"
    "\uff00-\uffef"
    "]"
)


def count_han(text) -> int:
    """统计字符串中的汉字/全角字符个数。"""
    if not text:
        return 0
    return len(_HAN_RE.findall(str(text)))


def estimate_tokens(text) -> int:
    """估算一段文本的 token 数（向上取整到整数）。

    `None` / 空串 → 0。非字符串输入先 `str()` 化，避免调用方到处判类型。
    """
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    han = count_han(text)
    other = len(text) - han
    # 用 int(x + 0.5) 而不是 round()：round() 是银行家舍入，0.5 → 0 会低估。
    return int(han * HAN_RATIO + other * OTHER_RATIO + 0.5)


def estimate_messages_tokens(messages, system: str = "") -> int:
    """估算一组 chat messages 的输入 token 数（含每条消息的固定开销）。

    `messages` 为 `[{"role": ..., "content": ...}, ...]`；`content` 可能是
    字符串，也可能是 OpenAI 多模态数组（只统计其中 `text` 字段）。
    """
    total = estimate_tokens(system)
    for message in messages or []:
        if not isinstance(message, dict):
            total += estimate_tokens(message) + MESSAGE_OVERHEAD_TOKENS
            continue
        total += estimate_tokens(_flatten_content(message.get("content")))
        total += estimate_tokens(message.get("role", ""))
        total += MESSAGE_OVERHEAD_TOKENS
    return total


def _flatten_content(content) -> str:
    """把多模态 message content 压成纯文本（非文本分片按固定权重粗估）。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") and item.get("type") != "text":
                    # 图片等非文本分片：给一个保守的固定估算，避免完全不计
                    parts.append("x" * 256)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def format_tokens(value) -> str:
    """把 token 数格式化成 UI 友好的短串（1.2K / 3.4M）。"""
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)


def chars_for_tokens(tokens) -> int:
    """给定 token 预算，返回**保守**的可容纳字符数。

    用 `HAN_RATIO`（1.6）作为除数，对纯 ASCII 文本会更保守
    （英文实际 4 字符/token，这里只给 0.625 字符/token 的额度），
    宁可少放内容也不冒超限的风险。
    """
    try:
        return max(0, int(float(tokens or 0) / HAN_RATIO))
    except (TypeError, ValueError):
        return 0


def chars_for_context_window(tokens, safety_divisor: float = CONTEXT_SAFETY_DIVISOR) -> int:
    """把模型的 token 上下文窗口折算为「本章可注入的字符数」预算。

    与 v2 `novel_agent` 里 `context_window // 3` 等效（32000 → 10666），
    只是把口径收敛到本模块，避免每个调用方各自发明一个除数。
    """
    try:
        window = float(tokens or 0)
        divisor = float(safety_divisor) or CONTEXT_SAFETY_DIVISOR
    except (TypeError, ValueError):
        return 0
    return max(0, int(window / divisor))


def truncate_to_tokens(text, tokens) -> str:
    """把文本截断到不超过 `tokens` 的保守长度。"""
    if not text:
        return ""
    limit = chars_for_tokens(tokens)
    if limit <= 0:
        return ""
    return text[:limit]

