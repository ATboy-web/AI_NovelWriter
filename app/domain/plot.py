"""情节类型与上下文预算（纯规则）。

## 为什么在 domain

两件东西必须**同源**：`PLOT_TYPES`（哪些情节类型合法）与 `CONTEXT_RATIOS`
（每种类型怎么分配上下文预算）。`type` 会被当作这张预算表的键来查，
两处各写一遍必然漂移 —— 表现出来不报错，只是某一阶段的章节质量莫名变差。

`normalize_plot_analysis` 则是这条规则的**入口守卫**：PlotDesigner 的输出来自模型，
形状不可信。模型返回 `{"type": {...}}` 时，dict 不可哈希，`CONTEXT_RATIOS.get(dict)`
会抛 `TypeError`，把整章生成带崩（实测过）。
"""

from __future__ import annotations

from typing import Dict

__all__ = [
    "CONTEXT_RATIOS",
    "PLOT_TYPES",
    "normalize_plot_analysis",
]

#: 上下文预算分配表：`情节类型 → 各部分占比`。**唯一来源**。
#:
#: `extra`（前文内容）占比最高：章节之间的连贯性比"多给点世界观"重要得多。
CONTEXT_RATIOS: Dict[str, Dict[str, float]] = {
    "opening": {"global": 0.10, "volume": 0.05, "chars": 0.15, "recent": 0.10, "rag": 0.10, "extra": 0.50},
    "writing": {"global": 0.08, "volume": 0.07, "chars": 0.10, "recent": 0.10, "rag": 0.10, "extra": 0.55},
    "action": {"global": 0.05, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.65},
    "dialogue": {"global": 0.05, "volume": 0.05, "chars": 0.25, "recent": 0.10, "rag": 0.10, "extra": 0.45},
    "ending": {"global": 0.10, "volume": 0.05, "chars": 0.05, "recent": 0.10, "rag": 0.10, "extra": 0.60},
}

#: 合法情节类型 —— **从预算表派生**，不单独维护。
PLOT_TYPES: tuple[str, ...] = tuple(CONTEXT_RATIOS)


def normalize_plot_analysis(raw: Dict) -> Dict:
    """把 PlotDesigner 的模型输出归一成下游**可安全使用**的形状。

    契约只有一条：`type` 必须是 `PLOT_TYPES` 里的字符串。

    枚举外的值（如 `"climax"`）原本也是回落到 `writing` 预算，这里提前归一，
    让"输出形状"可以被断言。`pace` / `foreshadowing` 目前无下游消费者，原样保留。
    """
    result = dict(raw)
    plot_type = result.get("type")
    if not isinstance(plot_type, str) or plot_type not in PLOT_TYPES:
        result["type"] = "writing"
    return result
