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
    "MAX_ATTEMPTS",
    "REWORK_STATUSES",
    "STATUS_LABELS",
    "TRANSITIONS",
    "check_enqueue",
    "judge_low_score",
    "status_label",
    "validate_transition",
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


# ═══════════════════════════════════════════════════════════════════
# 回炉队列的状态机（纯规则）
# ═══════════════════════════════════════════════════════════════════
#
# 这段原本在 `ReworkStore` 里，与"读写队列文件"混在一起。抽出来之后，
# 「什么状态能去什么状态」「什么情况下不能入炉」可以穷举验证，不必造 store。

#: 同一章最多回炉几次（超过需强制）
MAX_ATTEMPTS = 3

#: 状态 → 中文名。**顺序即工作流顺序**（面板按它排序）。
STATUS_LABELS: dict[str, str] = {
    "draft": "正常",
    "pending_rework": "待重写",
    "reworking": "重写中",
    "pending_review": "待审核",
    "approved": "已通过",
    "published": "已定稿",
    "discarded": "已废弃",
}

#: 全部合法状态
REWORK_STATUSES: tuple[str, ...] = tuple(STATUS_LABELS)

#: 状态流转表 —— **唯一来源**。新增状态必须在这里登记允许的去路。
#:
#: 两条刻意的禁区：
#: - 不允许 `draft → published`：那等于跳过重写与审核
#: - 不允许 `discarded → *`：废弃是终点，要恢复就重新入炉（留痕）
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("pending_rework",),
    "pending_rework": ("reworking", "discarded", "draft"),
    "reworking": ("pending_review", "pending_rework", "discarded"),
    "pending_review": ("approved", "reworking", "discarded"),
    "approved": ("published", "draft"),
    "published": ("draft",),
    "discarded": (),
}

#: 处于这些状态时不能重复入炉（正在进行中）
BUSY_STATUSES: tuple[str, ...] = ("reworking", "pending_review")


def status_label(status: str) -> str:
    """状态的中文名；未知状态原样返回（不让展示层因为新状态崩掉）。"""
    return STATUS_LABELS.get(status, status)


def check_enqueue(
    chapter: int,
    *,
    has_novel: bool = True,
    has_text: bool = True,
    status: str | None = None,
    attempts: int = 0,
    force: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
) -> tuple[bool, str]:
    """能否入炉。返回 `(是否允许, 原因说明)`；允许时原因为空串。

    纯判定：正文与队列记录由调用方读好后传入。这样"什么情况下不能入炉"
    可以逐条穷举 —— 而不必先造一部作品、写一章、再建一个 store。

    四条拒绝理由（顺序即报错优先级，先报最能说明问题的）：
    1. 没有打开的作品
    2. 空章（无从重写）
    3. 正在流转中（`reworking` / `pending_review`）—— 防重复入炉
    4. 已定稿 / 超次数 —— `force` 可越过
    """
    if not has_novel:
        return False, "没有打开的作品"
    if not has_text:
        return False, f"第 {chapter} 章没有正文（空章无从重写）"

    if status is None:
        return True, ""
    if status in BUSY_STATUSES:
        return False, f"该章正在{status_label(status)}，不能重复入炉"
    if status == "published" and not force:
        return False, "已定稿的章节需先设为正常（或强制）才能回炉"
    if attempts >= max_attempts and not force:
        return False, f"已回炉 {attempts} 次（上限 {max_attempts}），需人工确认后强制"
    return True, ""


def validate_transition(current: str, target: str) -> str | None:
    """校验状态流转；合法返回 `None`，非法返回**可直接展示**的说明。

    用"返回错误说明"而不是抛异常：调用方（`ReworkStore.transition`）要把它
    包成 `ReworkError`，而领域层不该依赖那个异常类型。
    """
    if target not in REWORK_STATUSES:
        return f"未知状态：{target}"

    allowed = TRANSITIONS.get(current, ())
    if target in allowed:
        return None

    if allowed:
        options = "、".join(STATUS_LABELS[s] for s in allowed)
    else:
        options = "无（终点状态）"
    return f"不能从「{status_label(current)}」直接变为「{STATUS_LABELS[target]}」；允许的去向：{options}"
