"""段级耗时归因：一章生成到底慢在哪个 Agent。

## 为什么值得单独一个模块

单章生成要发 **3–9 次网络往返**（plot 1 次、write 1 次、review 每轮 1 次、
revise 不达标才发），而本地计算量与这些往返相比可以忽略。于是"这一章慢"
**必定**能拆成"哪个 Agent 慢"，但没有分段数据就只能猜 —— 这也是先做观测、
后做优化的原因。

## 刻意不做的事

不 import `ai_client`、不读全局状态、不抛异常。它只做算术，
唯一输出是给 `chapter_event` 的一组数字。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

__all__ = [
    "NETWORK_PHASES",
    "PHASE_CONTEXT",
    "PHASE_PLOT",
    "PHASE_REVIEW",
    "PHASE_REVISE",
    "PHASE_WRITE",
    "PHASE_WORLD",
    "PhaseTimer",
    "_NETWORK_PHASES",
    "_PhaseTimer",
]

PHASE_PLOT = "plot_design"
PHASE_CONTEXT = "context"
PHASE_WORLD = "world_build"
PHASE_WRITE = "write"
PHASE_REVIEW = "review"
PHASE_REVISE = "revise"

#: 真正**会发网络请求**的阶段。数错这个数会直接误导"该优化哪里"。
#: 实测依据（AST 静态统计 `ai.chat()` 调用点）：
#:   plot_design / write / review / revise 各 1 次；`world_build` **0 次**
#:   （`_world_builder_build` 只读本地 settings 就返回，连 `ai` 都不碰）；
#:   `context` 也是纯本地组装。
#: 这正是"5 个 Agent"听起来像 5 次往返、实际不是的原因 —— 别按 Agent 数量推断。
_NETWORK_PHASES = frozenset({PHASE_PLOT, PHASE_WRITE, PHASE_REVIEW, PHASE_REVISE})


class PhaseTimer:
    """单章生成的段级耗时归因。

    为什么需要它：单章生成要发 **3–9 次网络往返**（`_plot_designer_analyze` 1 次、
    `_writer_generate` 1 次、`_reviewer_evaluate` 每轮 1 次、`_writer_revise` 不达标才发），
    而本地计算量与这些往返相比可以忽略。于是"这一章慢"**必定**能拆成"哪个 Agent 慢"，
    但没有分段数据就只能猜 —— 这也是先做观测、后做优化的原因。

    用累加而不是记录每次调用，是因为"第 2 轮审校"单独看没有意义，
    有用的是"审校总共占了这一章的多少毫秒"。逐轮明细另外记在 `calls` 里备查。

    ⚠️ 刻意不做的事：不 import `ai_client` / 不读全局状态 / 不抛异常。
    它只做算术，唯一的输出是给 `chapter_event` 的一组数字。
    """

    __slots__ = ("_t0", "total_ms", "phases", "calls")

    def __init__(self):
        self._t0 = time.perf_counter()
        self.total_ms = 0.0
        self.phases: Dict[str, float] = {}
        self.calls: List[Dict[str, Any]] = []

    def phase(self, name: str, started_at: float) -> float:
        """记录一段耗时（毫秒）并累加进同名阶段。

        用 `perf_counter` 而非 `time.time`：后者会被系统时钟调整影响，
        而我们要的是"这一段实际过了多久"。
        """
        elapsed = (time.perf_counter() - started_at) * 1000
        self.phases[name] = self.phases.get(name, 0.0) + elapsed
        self.calls.append({"phase": name, "ms": round(elapsed, 2)})
        return elapsed

    def breakdown(self) -> Dict[str, float]:
        """各阶段耗时（毫秒，四舍五入到 0.01）。"""
        return {k: round(v, 2) for k, v in self.phases.items()}

    def summary(self) -> Dict[str, Any]:
        """可日志化的汇总：总时长 + 各段 + 网络往返次数 + 未归因余量。"""
        self.total_ms = (time.perf_counter() - self._t0) * 1000
        accounted = sum(self.phases.values())
        return {
            "total_ms": round(self.total_ms, 2),
            "phases_ms": self.breakdown(),
            "round_trips": sum(1 for c in self.calls if c["phase"] in _NETWORK_PHASES),
            "unaccounted_ms": round(self.total_ms - accounted, 2),
            "calls": self.calls,
        }


_PhaseTimer = PhaseTimer
NETWORK_PHASES = _NETWORK_PHASES
