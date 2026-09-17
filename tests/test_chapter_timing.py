"""单章生成「段级耗时归因」门禁。

## 背景

`HARDWARE_ACCELERATION_PLAN.md` 的结论是：**瓶颈是等待，不是算力**。
单章生成要发 3–9 次网络往返，本地计算量可以忽略 —— 所以"这一章慢"必定能拆成
"哪个 Agent 慢"。但没有分段数据时，任何优化都只能靠猜。

尴尬的是：`DiagnosticLogger.chapter_event()` 早就存在（`diagnostic_logger.py:213`），
`duration_ms` 字段也早就支持，**却从来没有人从生成主流程里调用它** ——
全仓唯一的使用者是 `generation_ui.py` 里 **EXP 相关的降级分支**
（`EXP_NO_RESPONSE` / `EXP_JSON_PARSE_FAILED` / `EXP_NO_ACTION`）。
于是日志里能看到"角色成长又失败了"，却看不到"这一章生成花了多久"。

本文件钉住这四件事：
1. `_PhaseTimer` 累加语义正确（同名阶段累加、`calls` 保留逐次明细）；
2. `round_trips` **只数真的出网的阶段** —— 按 Agent 数量推断是错的；
3. 生成链确实把计时喂进了 `chapter_event`，且形如 `chNNNN/complete`；
4. 计时/落盘失败**绝不影响**生成结果（这是唯一不可退让的性质）。
"""

import json
import threading
import time
from pathlib import Path

import pytest

from app import novel_agent as na
from app.novel_agent import (
    _NETWORK_PHASES,
    PHASE_CONTEXT,
    PHASE_PLOT,
    PHASE_REVIEW,
    PHASE_REVISE,
    PHASE_WORLD,
    PHASE_WRITE,
    _PhaseTimer,
)


class TestPhaseTimerArithmetic:
    """计时器只做算术，所以算术必须精确。"""

    def test_single_phase_accumulates(self):
        t = _PhaseTimer()
        start = time.perf_counter()
        time.sleep(0.05)
        t.phase("x", start)
        assert t.phases["x"] == pytest.approx(50, abs=40)

    def test_same_phase_accumulates_across_calls(self):
        """审校跑 2 轮 → 应当累加成一段，而不是只留最后一轮。"""
        t = _PhaseTimer()
        for _ in range(2):
            start = time.perf_counter()
            time.sleep(0.03)
            t.phase("review", start)
        assert t.phases["review"] == pytest.approx(60, abs=40)
        assert len([c for c in t.calls if c["phase"] == "review"]) == 2, "逐次明细丢了，无法区分轮次"

    def test_different_phases_stay_separate(self):
        t = _PhaseTimer()
        for name, ms in (("a", 20), ("b", 40)):
            start = time.perf_counter()
            time.sleep(ms / 1000)
            t.phase(name, start)
        assert t.phases["a"] == pytest.approx(20, abs=30)
        assert t.phases["b"] == pytest.approx(40, abs=30)

    def test_first_phase_call_does_not_need_prior_state(self):
        """`time()` 必须能在初始化后立刻调用（第一段就是第一个 Phase）。"""
        t = _PhaseTimer()
        t.phase("first", time.perf_counter())
        assert "first" in t.phases

    def test_breakdown_rounds_to_two_decimals(self):
        t = _PhaseTimer()
        t.phases["x"] = 12.34567
        assert t.breakdown()["x"] == 12.35

    def test_calls_record_phase_and_ms(self):
        t = _PhaseTimer()
        t.phase("write", time.perf_counter())
        assert set(t.calls[0]) == {"phase", "ms"}
        assert t.calls[0]["phase"] == "write"


class TestRoundTripCounting:
    """`round_trips` 是给人看"该优化哪"的数字，数错比不数更糟。"""

    def test_world_build_is_not_a_round_trip(self):
        """`_world_builder_build` **不发网络请求**（只读本地 settings 就返回）。

        这条来自 AST 静态统计 `ai.chat()` 调用点，不是推测：
        按"5 个 Agent = 5 次往返"来数会直接误导优化方向。
        """
        assert PHASE_WORLD not in _NETWORK_PHASES

    def test_context_assembly_is_not_a_round_trip(self):
        assert PHASE_CONTEXT not in _NETWORK_PHASES

    def test_network_phases_are_exactly_the_four_ai_callers(self):
        assert _NETWORK_PHASES == frozenset({PHASE_PLOT, PHASE_WRITE, PHASE_REVIEW, PHASE_REVISE})

    def test_summary_counts_only_network_phases(self):
        t = _PhaseTimer()
        for name in (PHASE_PLOT, PHASE_CONTEXT, PHASE_WORLD, PHASE_WRITE, PHASE_REVIEW, PHASE_REVIEW, PHASE_REVISE):
            t.phase(name, time.perf_counter())
        summary = t.summary()
        # plot1 + write1 + review2 + revise1 = 5；context 与 world_build 不计
        assert summary["round_trips"] == 5

    def test_summary_reports_unaccounted_gap(self):
        """未归因余量 = 总时长 - 各段之和；用于发现"还有别的东西在耗时"。"""
        t = _PhaseTimer()
        t.phase(PHASE_WRITE, time.perf_counter())
        summary = t.summary()
        assert summary["unaccounted_ms"] >= 0
        assert summary["total_ms"] >= sum(summary["phases_ms"].values()) - 1

    def test_summary_contains_all_contract_fields(self):
        t = _PhaseTimer()
        t.phase(PHASE_WRITE, time.perf_counter())
        summary = t.summary()
        assert {"total_ms", "phases_ms", "round_trips", "unaccounted_ms", "calls"} <= set(summary)


def _minimal_agent(monkeypatch, *, sleep_ms=0, score_seq=(90,), raise_in=None):
    """造一个剥离了外部依赖的 NovelAgent，只保留生成链的骨架。

    `sleep_ms` 让每个 Phase 睡固定时长，便于验证"记录值 ≈ 实际值"。
    """
    agent = na.NovelAgent.__new__(na.NovelAgent)
    agent._log_lock = threading.Lock()
    agent._conversation_log = []
    agent._revision_memory = []
    agent.tools = type("T", (), {"call": staticmethod(lambda *a, **k: None)})()
    agent.memory = type("M", (), {"get_settings": staticmethod(lambda: {})})()
    agent.last_chapter_quality = None

    def _nap():
        if sleep_ms:
            time.sleep(sleep_ms / 1000)

    def _plot(cn, title, outline):
        _nap()
        if raise_in == "plot":
            raise RuntimeError("boom-plot")
        return {"type": "writing"}

    agent._plot_designer_analyze = _plot
    agent._build_context = lambda cn, pc, writing_phase=None: "ctx"
    agent._world_builder_build = lambda cn, pa: ""
    agent._writer_generate = lambda cn, t, o, wc, context="", prev_ending="": (_nap(), "正文" * 100)[1]

    calls = {"n": 0}

    def _review(cn, content, previous_feedback=""):
        _nap()
        idx = min(calls["n"], len(score_seq) - 1)
        calls["n"] += 1
        return {"overall_score": score_seq[idx], "issues": [], "suggestions": []}

    agent._reviewer_evaluate = _review
    agent._writer_revise = lambda cn, c, r, o, context="", prev_ending="": (_nap(), c + "改")[1]
    agent._call_anti_slop_check = lambda content: []
    agent._record_conversation = lambda *a, **k: None
    agent.log = lambda *a, **k: None
    return agent


class TestGenerationChainWiring:
    """生成链必须**真的**把计时喂给诊断日志 —— 否则只是加了个没人用的类。"""

    def test_emits_complete_event_with_phases(self, diagnostic_log_dir):
        agent = _minimal_agent(None, sleep_ms=5)
        agent.generate_with_collaboration(7, "第七章", "大纲" * 10, word_count=500)

        entries = _read(diagnostic_log_dir)
        complete = [e for e in entries if e.get("event") == "ch0007/complete"]
        assert complete, f"没有 ch0007/complete 事件，实际事件：{sorted({e.get('event') for e in entries})}"

        data = complete[-1]["data"]
        assert "phases_ms" in data
        assert data["phases_ms"].get(PHASE_WRITE, 0) > 0, "写作段耗时为 0，计时没接上"

    def test_complete_event_carries_duration_ms(self, diagnostic_log_dir):
        """`duration_ms` 必须在**顶层**（`log()` 的约定），不是塞在 data 里。"""
        agent = _minimal_agent(None, sleep_ms=5)
        agent.generate_with_collaboration(3, "第三章", "大纲" * 10, word_count=500)

        complete = [e for e in _read(diagnostic_log_dir) if e.get("event") == "ch0003/complete"]
        assert complete and "duration_ms" in complete[-1]
        assert complete[-1]["duration_ms"] > 0

    def test_event_name_is_zero_padded(self, diagnostic_log_dir):
        """`ch0007/complete` 的补零格式让日志可以按章节号字典序排序。"""
        agent = _minimal_agent(None)
        agent.generate_with_collaboration(42, "x", "大纲" * 10, word_count=500)
        events = [e.get("event") for e in _read(diagnostic_log_dir)]
        assert "ch0042/complete" in events

    def test_records_revision_round_count(self, diagnostic_log_dir):
        """第 1 轮不达标、第 2 轮达标 ⇒ 恰好修订 1 次。"""
        agent = _minimal_agent(None, score_seq=(10, 99))
        agent.generate_with_collaboration(1, "x", "大纲" * 10, word_count=500)
        data = [e for e in _read(diagnostic_log_dir) if e.get("event") == "ch0001/complete"][-1]["data"]
        assert data["revision_rounds"] == 1

    def test_no_revision_when_first_round_passes(self, diagnostic_log_dir):
        agent = _minimal_agent(None, score_seq=(99,))
        agent.generate_with_collaboration(2, "x", "大纲" * 10, word_count=500)
        data = [e for e in _read(diagnostic_log_dir) if e.get("event") == "ch0002/complete"][-1]["data"]
        assert data["revision_rounds"] == 0
        assert PHASE_REVISE not in data["phases_ms"]

    def test_phases_mapping_is_json_serialisable(self, diagnostic_log_dir):
        agent = _minimal_agent(None)
        agent.generate_with_collaboration(5, "x", "大纲" * 10, word_count=500)
        data = [e for e in _read(diagnostic_log_dir) if e.get("event") == "ch0005/complete"][-1]["data"]
        # 能把 data 原样 dump 回去，才算真的可机读
        assert json.loads(json.dumps(data["phases_ms"]))


class TestTimingNeverBreaksGeneration:
    """计时是观测手段，**绝不允许**成为新的故障源。"""

    def test_emit_failure_does_not_raise(self, monkeypatch):
        """诊断日志整体炸掉时，`_emit_chapter_timing` 必须静默降级。"""
        timer = _PhaseTimer()
        timer.phase(PHASE_WRITE, time.perf_counter())

        class _Exploding:
            def chapter_event(self, *a, **k):
                raise RuntimeError("log backend down")

        monkeypatch.setattr(na, "_diag", _Exploding(), raising=False)
        monkeypatch.setattr(na, "_diag_logger", lambda: _Exploding())
        agent = _minimal_agent(None)
        # 不抛异常即通过
        agent._emit_chapter_timing(1, timer, {"overall_score": 80}, "正文")

    def test_emit_noop_when_diag_is_none(self, monkeypatch):
        """诊断不可用时是静默 no-op（返回 None），不是 AttributeError。"""
        monkeypatch.setattr(na, "_diag", None, raising=False)
        monkeypatch.setattr(na, "_diag_logger", lambda: None)
        agent = _minimal_agent(None)
        assert agent._emit_chapter_timing(1, _PhaseTimer(), {}, "正文") is None

    def test_generation_result_unaffected_by_log_failure(self, monkeypatch):
        """最关键的一条：日志后端炸了，正文仍必须完整返回。"""

        class _Exploding:
            def chapter_event(self, *a, **k):
                raise RuntimeError("log backend down")

        monkeypatch.setattr(na, "_diag_logger", lambda: _Exploding())
        agent = _minimal_agent(None)
        content = agent.generate_with_collaboration(9, "x", "大纲" * 10, word_count=500)
        assert content and len(content) > 100, "日志失败竟导致正文丢失/截断"

    def test_timer_arithmetic_failure_is_contained(self, monkeypatch):
        """连 `summary()` 都坏掉时也要降级，而不是把异常抛回生成主流程。

        注意 `_PhaseTimer` 用了 `__slots__`，`monkeypatch.setattr(instance, ...)`
        会因其没有 `__dict__` 而报 read-only —— 所以这里造一个坏掉的子类替身。
        """

        class _BrokenTimer(_PhaseTimer):
            __slots__ = ()

            def summary(self):
                raise ValueError("bad timer")

        agent = _minimal_agent(None)
        agent._emit_chapter_timing(1, _BrokenTimer(), {}, "正文")

    def test_diag_logger_helper_falls_back_to_cached_instance(self, monkeypatch):
        """`get_logger()` 自身抛错时要退回模块级快照，而不是让归因整体失效。"""
        sentinel = object()
        monkeypatch.setattr(na, "_diag", sentinel, raising=False)
        monkeypatch.setattr(na, "get_logger", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        assert na._diag_logger() is sentinel

    def test_diag_logger_returns_live_singleton(self, monkeypatch):
        """正常情况下必须返回**当前**单例（而不是导入时的快照）。

        否则 `reset_logger()` 换了目录后，归因会继续往旧目录写。
        """
        live = object()
        monkeypatch.setattr(na, "_diag", object(), raising=False)
        monkeypatch.setattr(na, "get_logger", lambda: live)
        assert na._diag_logger() is live


def _read(log_dir: Path):
    entries = []
    for f in sorted(Path(log_dir).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries
