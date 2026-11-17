"""评审结果的持久化与趋势 —— 让「这本小说在变好还是变差」变得可回答。

## 为什么必须落盘

`_reviewer_evaluate()` 原来评完就把结果返回给调用方，**全仓没有任何写盘**
（实测 `grep -n "review" app/novel_agent.py | grep -i "save\\|write\\|json"` 无命中）。
后果是三个问题都无法回答：

| 问题 | 为什么答不了 |
|---|---|
| 这本书第 10 章开始质量下滑了吗 | 每章分数评完即丢，没有序列 |
| 我改了 3 版，真的变好了吗 | 只有"当前"一次的结果，没有基线 |
| 门禁阈值该不该调 | `scripts/calibrate_presets.py` 要「合格稿」语料，没有采集来源 |

## 三个设计决定

**1. 一章一个文件，不建大索引。**
`memory/reviews/chapter_001.json` 一个文件一章。理由：单章写盘是原子的（不会
因为写第 50 章失败而毁掉前 49 章），删改单章也只需动一个文件。100 章也就 100 个
小文件，扫描代价可忽略。

**2. 失败要留痕，且 `overall` 允许 `None`。**
AI 返回的不是 JSON 时，旧代码给 `overall_score: 70` —— 一个"看起来合格"的分数。
`None` + `error` 才能让上层走"人工确认"分支，而不是把失败伪装成及格。

**3. 记 `rules_version`（规则指纹）。**
分数只有"同一把尺"之间才可比。规则更新后，旧分与新分不能画在同一条曲线上 ——
指纹就是用来判断"这条曲线换过尺没有"的。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from .storage import atomic_write_json

__all__ = [
    "DIMENSIONS",
    "ReviewRecord",
    "list_reviews",
    "load_review",
    "normalize_review",
    "reviews_dir",
    "rules_version",
    "save_review",
    "score_trend",
    "summarize_novel",
    "format_trend",
]

#: 六维度字段名 → 中文名。与 `_reviewer_evaluate` 的输出 JSON 一一对应。
DIMENSIONS: Dict[str, str] = {
    "character_consistency": "角色一致性",
    "plot_logic": "情节逻辑",
    "writing_quality": "文笔质量",
    "emotional_impact": "情感冲击",
    "pacing": "叙事节奏",
}

#: 分数合法区间。超出即视为 AI 返回异常（不是"给高了"，是"格式错"）。
_SCORE_MIN, _SCORE_MAX = 0, 100


def reviews_dir(novel_dir: Any) -> Optional[Path]:
    """评审目录：`<作品>/memory/reviews/`。

    只接受**真实路径**（`str` / `Path`）。传进来 `None`、Mock、或其它对象时返回
    `None` —— 落盘是增强动作，调用方即便给了奇怪的东西也只该"存不下来"，
    不该在评审主流程里抛异常。
    """
    if not isinstance(novel_dir, (str, Path)):
        return None
    return Path(novel_dir) / "memory" / "reviews"


def rules_version() -> str:
    """当前评审判据的指纹（技能库规则标题的 sha1 前 12 位）。

    规则没变 ⇒ 指纹不变 ⇒ 新旧分数可比。规则变了指纹就变，
    趋势曲线据此可以提示"跨版本不可直接比较"。
    """
    try:
        from .writing_presets import _library_rules

        titles = sorted(str(getattr(rule, "title", "") or "") for rule in _library_rules())
    except Exception:  # noqa: BLE001 - 取不到就当空规则集
        titles = []
    if not titles:
        return "builtin"
    digest = hashlib.sha1("\n".join(titles).encode("utf-8")).hexdigest()
    return digest[:12]


# ====================================================================== 数据模型


@dataclass
class ReviewRecord:
    """一次评审的完整记录。**`overall` 为 `None` 表示评审本身失败**。"""

    chapter: int
    overall: Optional[float] = None
    dimensions: Dict[str, Optional[float]] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    is_acceptable: Optional[bool] = None
    #: 非空表示「评审没跑成功」，此时 `overall` 必须是 `None`。
    error: str = ""
    rules_version: str = ""
    model: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def ok(self) -> bool:
        """评审本身是否成功完成（不代表内容合格）。"""
        return self.overall is not None and not self.error

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chapter": self.chapter,
            "overall": self.overall,
            # 兼容别名：`Editor` 裁定与 `generation_ui` 读的是 `overall_score`。
            # 由 `overall` **派生**（同一个值，一处生成），不是第二个真相源。
            "overall_score": self.overall,
            "dimensions": dict(self.dimensions),
            "strengths": list(self.strengths),
            "issues": list(self.issues),
            "suggestions": list(self.suggestions),
            "is_acceptable": self.is_acceptable,
            "ok": self.ok,
            "error": self.error,
            "rules_version": self.rules_version,
            "model": self.model,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewRecord":
        return cls(
            chapter=int(data.get("chapter", 0) or 0),
            overall=_as_score(data.get("overall")),
            dimensions={
                key: _as_score((data.get("dimensions") or {}).get(key))
                for key in DIMENSIONS
                if (data.get("dimensions") or {}).get(key) is not None
            },
            strengths=_as_list(data.get("strengths")),
            issues=_as_list(data.get("issues")),
            suggestions=_as_list(data.get("suggestions")),
            is_acceptable=data.get("is_acceptable") if isinstance(data.get("is_acceptable"), bool) else None,
            error=str(data.get("error", "") or ""),
            rules_version=str(data.get("rules_version", "") or ""),
            model=str(data.get("model", "") or ""),
            created_at=str(data.get("created_at", "") or ""),
        )


def _as_score(value: Any) -> Optional[float]:
    """把任意输入收敛成合法分数或 `None`。

    越界（负数 / >100）与不可解析**都返回 `None`**：这不是"数据清洗"，
    而是"这份结果不可用"的信号 —— 强行 clamp 会把格式错误伪装成低分。
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if number < _SCORE_MIN or number > _SCORE_MAX:
        return None
    return round(number, 1)


def _as_list(value: Any) -> List[str]:
    """字符串列表归一化：容忍单个字符串、None、含非字符串的列表。"""
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_review(raw: Any, chapter: int, model: str = "") -> ReviewRecord:
    """把 AI 返回的原始结果归一化成 `ReviewRecord`。

    🔴 核心约定：**拿不到合法 `overall_score` ⇒ `overall=None` + `error` 说明原因**。
    旧实现回落成 `{"overall_score": 70}`，等于"评审失败"被记成"70 分"，
    而 70 分通常就在及格线附近 —— 失败被伪装成通过。

    这也与项目里修过的同类错误一致：`upload_novel` 曾在失败时返回 `True`，
    界面提示"同步成功"，用户以为数据上云了。
    """
    if not isinstance(raw, dict):
        return ReviewRecord(
            chapter=chapter,
            error=f"评审返回结构异常（{type(raw).__name__}），需人工确认",
            rules_version=rules_version(),
            model=model,
        )

    overall = _as_score(raw.get("overall_score"))
    dimensions = {key: _as_score(raw.get(key)) for key in DIMENSIONS if raw.get(key) is not None}
    error = str(raw.get("error", "") or "")
    if overall is None and not error:
        error = "评审未返回合法 overall_score（AI 输出可能不是 JSON），需人工确认"

    return ReviewRecord(
        chapter=chapter,
        overall=overall,
        dimensions={k: v for k, v in dimensions.items() if v is not None},
        strengths=_as_list(raw.get("strengths")),
        issues=_as_list(raw.get("issues")),
        suggestions=_as_list(raw.get("suggestions")),
        is_acceptable=raw.get("is_acceptable") if isinstance(raw.get("is_acceptable"), bool) else None,
        error=error,
        rules_version=rules_version(),
        # 强制转 str：调用方可能传 Mock / None，让 JSON 落盘炸在这里不值得
        model=str(model or ""),
    )


# ====================================================================== 读写


def _review_path(novel_dir: Any, chapter: int) -> Optional[Path]:
    base = reviews_dir(novel_dir)
    if base is None:
        return None
    return base / f"chapter_{int(chapter):03d}.json"


def save_review(novel_dir: Any, record: ReviewRecord) -> bool:
    """保存一章的评审结果。返回是否成功（失败不抛，评审不该阻断写作）。"""
    path = _review_path(novel_dir, record.chapter)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, record.as_dict(), indent=2)
        return True
    except OSError as exc:
        logger.warning(f"[评审] 保存失败（第 {record.chapter} 章）：{exc}")
        return False


def load_review(novel_dir: Any, chapter: int) -> Optional[ReviewRecord]:
    """读取一章的评审结果。文件不存在或损坏返回 `None`。"""
    path = _review_path(novel_dir, chapter)
    if path is None or not path.is_file():
        return None
    try:
        return ReviewRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        logger.warning(f"[评审] 读取失败（第 {chapter} 章）：{exc}")
        return None


def list_reviews(novel_dir: Any) -> List[ReviewRecord]:
    """按章节号升序返回全部评审记录。"""
    base = reviews_dir(novel_dir)
    if base is None or not base.is_dir():
        return []
    records: List[ReviewRecord] = []
    for path in sorted(base.glob("chapter_*.json")):
        try:
            records.append(ReviewRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            logger.warning(f"[评审] 跳过损坏文件 {path.name}：{exc}")
    records.sort(key=lambda r: r.chapter)
    return records


# ====================================================================== 趋势


def score_trend(novel_dir: Any) -> List[Dict[str, Any]]:
    """分数序列：`[{"chapter", "overall", "ok", "created_at"}, ...]`。

    失败的评审也保留（`ok=False`、`overall=None`），这样"第 12 章评审失败"
    在曲线上是一个**缺口**，而不是被悄悄跳过留下的假平滑。
    """
    return [
        {
            "chapter": record.chapter,
            "overall": record.overall,
            "ok": record.ok,
            "created_at": record.created_at,
        }
        for record in list_reviews(novel_dir)
    ]


def _mean(values: Sequence[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def summarize_novel(novel_dir: Any) -> Dict[str, Any]:
    """整本小说的评审概况：均值、最高/最低章、趋势方向、失败章清单。

    `trend` 用**后半段均值 - 前半段均值**判断走向，而不是首末两章相减 ——
    单章波动很可能是"这一章本来就难写"，两段均值更能反映实际趋势。
    """
    records = list_reviews(novel_dir)
    ok_records = [r for r in records if r.ok]
    scores = [r.overall for r in ok_records if r.overall is not None]

    trend = "unknown"
    if len(scores) >= 4:
        mid = len(scores) // 2
        early = _mean(scores[:mid]) or 0.0
        late = _mean(scores[mid:]) or 0.0
        delta = late - early
        if delta >= 3:
            trend = "up"
        elif delta <= -3:
            trend = "down"
        else:
            trend = "flat"

    lowest = min(ok_records, key=lambda r: r.overall) if ok_records else None
    highest = max(ok_records, key=lambda r: r.overall) if ok_records else None

    versions = {r.rules_version for r in records if r.rules_version}
    return {
        "chapters_reviewed": len(records),
        "chapters_ok": len(ok_records),
        "chapters_failed": len(records) - len(ok_records),
        "failed_chapters": [r.chapter for r in records if not r.ok],
        "average": _mean(scores),
        "lowest": {"chapter": lowest.chapter, "overall": lowest.overall} if lowest else None,
        "highest": {"chapter": highest.chapter, "overall": highest.overall} if highest else None,
        "trend": trend,
        # 一条曲线换过尺就不能直接比 —— 把这件事显式暴露给界面
        "rules_versions": sorted(versions),
        "comparable": len(versions) <= 1,
    }


def format_trend(novel_dir: Any) -> str:
    """把概况渲染成人读文本（面板用）。"""
    summary = summarize_novel(novel_dir)
    if not summary["chapters_reviewed"]:
        return "还没有评审记录。生成章节后点「审校」即可开始积累。"

    lines = [
        f"已评审 {summary['chapters_reviewed']} 章"
        f"（成功 {summary['chapters_ok']} / 失败 {summary['chapters_failed']}）",
        f"平均分：{summary['average']}",
    ]
    if summary["highest"]:
        lines.append(f"最高：第 {summary['highest']['chapter']} 章 {summary['highest']['overall']} 分")
    if summary["lowest"]:
        lines.append(f"最低：第 {summary['lowest']['chapter']} 章 {summary['lowest']['overall']} 分")

    trend_text = {"up": "↑ 上升", "down": "↓ 下降", "flat": "→ 持平", "unknown": "样本不足"}
    lines.append(f"趋势：{trend_text.get(summary['trend'], '未知')}")

    if summary["failed_chapters"]:
        lines.append(f"⚠️ 评审失败的章节：{summary['failed_chapters']}（这些章没有可用分数）")
    if not summary["comparable"]:
        lines.append(f"⚠️ 期间换过评审判据（{len(summary['rules_versions'])} 个版本），跨版本的分数不可直接比较")
    return "\n".join(lines)
