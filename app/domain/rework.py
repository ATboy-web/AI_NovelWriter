"""回炉判定的**领域规则**：什么章节该打回重写。

## 为什么从 `rework.scan` 里抽出来

`scan`（81 行）把三件事焊在一起：遍历章节文件、读正文、**三档判定**。
其中判定部分是纯规则 —— 但想验证"标题是占位符时只报 bad_title、不再报质检阻断"，
必须先造一套 `chapters/` 目录并跑完整扫描。

抽出来之后，判定可以直接喂字符串穷举；`scan` 只剩"遍历 + 读 + 按顺序问判定"。

## 三档的互斥关系（这是最容易写错的地方）

    标题硬伤 (bad_title)  ──有──▶ 报它，**不再跑质检**
            │无
            ▼
    质检阻断 (qc_blocker) ──有──▶ 报它，**不再看评分**
            │无
            ▼
    评审低分 (low_score)  ──有──▶ 报它

三条必须**只报一条**：同一章报多条会让回炉队列里出现重复项，用户以为有两个问题。
另外「没有评审记录」**不算低分** —— 未评不等于差。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence

__all__ = [
    "REASON_BAD_TITLE",
    "REASON_LOW_SCORE",
    "REASON_QC_BLOCKER",
    "TITLE_PLACEHOLDER_PATTERNS",
    "judge_low_score",
    "judge_static",
    "title_is_placeholder",
]

#: 原因代码（面板与统计按它分组，改名会破坏历史数据）
REASON_BAD_TITLE = "bad_title"
REASON_QC_BLOCKER = "qc_blocker"
REASON_LOW_SCORE = "low_score"

#: 视为"占位符"的标题形态
TITLE_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"章节标题"),
    re.compile(r"标题\s*[(（]?\d+\s*字"),
    re.compile(r"^\s*第\s*\d+\s*章\s*[:：]?\s*$"),
    re.compile(r"^\s*Untitled\s*$", re.IGNORECASE),
    re.compile(r"第\s*\d+\s*章\s*[:：]\s*$"),
)


def title_is_placeholder(title: str) -> bool:
    """该标题是否为「缺失 / 占位符」。"""
    body = (title or "").strip()
    if not body:
        return True
    return any(pattern.search(body) for pattern in TITLE_PLACEHOLDER_PATTERNS)


def judge_static(
    chapter: int,
    text: str,
    *,
    split_title: Callable[[str], tuple[str, str]],
    blocker_evidence: Callable[[str], Mapping[str, Any] | None],
) -> dict | None:
    """前两档判定（标题硬伤 / 质检阻断），互斥且**只报一条**。

    两个依赖用注入而不是 import：
    - `split_title` 在 `parsing` / `bulk_rewrite` 各有一份，属于上层
    - `blocker_evidence` 要跑 `writing_presets.qc_report`，属于上层

    注入之后本函数保持纯：同一份 `text` 永远得到同一个结论。
    """
    title, _body = split_title(text)

    if title_is_placeholder(title):
        return {
            "chapter": chapter,
            "reason_code": REASON_BAD_TITLE,
            "reason_text": "标题缺失或为占位符",
            "evidence": {"title": title[:40]},
        }

    info = blocker_evidence(text)
    if info:
        return {
            "chapter": chapter,
            "reason_code": REASON_QC_BLOCKER,
            "reason_text": info["summary"],
            "evidence": dict(info),
        }
    return None


def judge_low_score(
    chapter: int,
    *,
    ok: bool,
    overall: float | None,
    threshold: float,
    issues: Sequence[str] = (),
) -> dict | None:
    """第三档：评审分数低于阈值。

    三种情况**都不算低分**（宁缺毋滥，避免把"未评"当"差"）：
    - 没有评审记录（调用方传 `ok=False` / `overall=None`）
    - 评审本身失败（`ok=False`）
    - 分数 >= 阈值
    """
    if not ok or overall is None:
        return None
    if overall >= threshold:
        return None
    return {
        "chapter": chapter,
        "reason_code": REASON_LOW_SCORE,
        "reason_text": f"评审 {overall:g} 分，低于阈值 {threshold:g}",
        "evidence": {"overall": overall, "issues": list(issues)[:5]},
    }
