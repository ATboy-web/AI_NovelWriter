"""散文质量规则（纯函数，只读参数）。

## 为什么在 domain

这些判断与"用哪个模型""存到哪"无关，是**文本本身的性质**：
一句结尾到底算不算断在半句，是可以在纸面上判定的。
放进 domain 之后，它可以在任何上下文里被穷举测试（不需要 Agent、不需要网络）。
"""

from __future__ import annotations

__all__ = ["PLANNING_STRONG", "PLANNING_WEAK", "looks_like_planning", "looks_truncated"]


def looks_truncated(text: str) -> bool:
    """判断文本末尾是否**明显断在半句**（而不是"只是没以句号结尾"）。

    判据刻意保守 —— 只有同时满足"没有句末标点"且"末尾字符不可能收尾"
    才返回 `True`。因为**误判的代价不对称**：
    漏判一个真断句 ⇒ 结尾略突兀；误判一个完整结尾 ⇒ 追加一段无关文字、
    把好结尾改坏（即烂尾）。后者严重得多。
    """
    tail = (text or "").rstrip()
    if not tail:
        return False
    last = tail[-1]
    # 能收尾的字符：句末标点 + 引号 + 省略号 + 破折号 + 英文句点
    closers = set("。！？…—.!?~」』】》\"'")
    if last in closers:
        return False
    # 中文逗号/顿号/分号/冒号结尾 ⇒ 明确还在句中
    if last in set("，、；：,;:"):
        return True
    # 其余（多为汉字或字母）⇒ 无法确定，按"完整"处理（见上面的代价不对称）
    return False


PLANNING_STRONG = (
    "用户希望我",
    "用户要求续写",
    "用户要求我",
    "字数控制",
    "正文开始",
    "让我起草",
    "这个感觉方向",
    "我倾向于：",
    "具体设计：",
    "字数控制在",
)
PLANNING_WEAK = (
    "让我想想",
    "让我再想",
    "让我回顾",
    "让我理一下",
    "让我构思",
    "或者更好",
    "或者更直接",
    "那我尽量",
    "这就悬了",
    "嗯，这",
    "好，我这样写",
    "我需要写约",
    "让我写一个更自然",
)


def looks_like_planning(text: str) -> bool:
    """判断文本是否是模型的**创作规划/内心独白**，而不是小说正文。

    为什么不能只看长度或只看一个词：
    - 正文里可以有 `"让我想想。"`（角色对白）——单命中会误杀；
    - 规划文字的特征是**成片出现**的元话语（"用户希望我…""或者更好…""字数控制…"）。

    因此判据：
    1. 任一强特征词出现 ⇒ 是规划；
    2. 弱特征词命中 ≥2 个 ⇒ 是规划；
    3. ≥3 行以全角括号包裹（`（他先回杂役房…）` 这类舞台说明）⇒ 是规划。
    """
    body = text or ""
    if not body.strip():
        return False
    if any(marker in body for marker in PLANNING_STRONG):
        return True
    weak_hits = sum(1 for marker in PLANNING_WEAK if marker in body)
    if weak_hits >= 2:
        return True
    bracket_lines = sum(
        1 for line in body.splitlines() if line.strip().startswith("（") and line.strip().endswith("）")
    )
    return bracket_lines >= 3
