"""段级耗时归因的验证探针（不是测试，是人工核验脚本）。

跑法：
    python scripts/verify_chapter_timing.py

它用 **假的 AIClient** 驱动真实的 `generate_with_collaboration`：
每个 Agent 方法都被注入已知的人为延迟（PlotDesigner 120ms / Writer 900ms /
Reviewer 250ms / Revise 300ms），于是"日志里记的毫秒数对不对"可以直接跟
"我们故意让它睡多久"对账 —— 这比断言"日志里有 duration_ms 字段"强得多，
因为字段存在不代表数值正确。

零网络、零真实 API key：`AIClient` 整体被替身顶掉。
"""

import os
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# 隔离诊断日志，避免核验脚本污染真实使用数据
_LOG_DIR = Path(tempfile.mkdtemp(prefix="verify-timing-"))
os.environ["AI_NOVEL_DIAGNOSTIC_DIR"] = str(_LOG_DIR)

#: 各阶段的人为延迟（毫秒）。改这里就能验证"日志是否忠实反映实际耗时"。
INJECTED_MS = {
    "plot_design": 120,
    "write": 900,
    "review": 250,
    "revise": 300,
}

#: 允许的误差（毫秒）。Windows 上 `time.sleep` 的调度粒度较粗，不能卡太死。
TOLERANCE_MS = 60


class _FakeMemory:
    def get_settings(self):
        return {"world": {"已知区域": ["测试城"]}}


class _FakeTools:
    def call(self, *_a, **_k):
        return None


def _build_agent():
    """构造一个只替换了外部依赖的 NovelAgent。

    `_plot_designer_analyze` / `_writer_generate` / `_reviewer_evaluate` /
    `_writer_revise` 全部被替身覆盖 —— 我们验证的是**计时与落盘**，
    不是 Agent 的提示词质量，所以这些方法的内容无关紧要。
    """
    import app.novel_agent as na

    agent = na.NovelAgent.__new__(na.NovelAgent)
    agent._log_lock = __import__("threading").Lock()
    agent._conversation_log = []
    agent._revision_memory = []
    agent.memory = _FakeMemory()
    agent.tools = _FakeTools()
    agent.last_chapter_quality = None

    def _sleep(ms):
        time.sleep(ms / 1000.0)

    def _plot(chapter_num, title, outline):
        _sleep(INJECTED_MS["plot_design"])
        return {"type": "writing", "pace": "medium", "foreshadowing": []}

    def _ctx(chapter_num, prev_context, writing_phase=None):
        return "（测试上下文）"

    def _world(chapter_num, plot_analysis):
        return ""  # 刻意返回空，模拟"WorldBuilder 不出网也不产出"

    def _write(chapter_num, title, outline, word_count, context="", prev_ending=""):
        _sleep(INJECTED_MS["write"])
        return "初稿内容" * 200

    _review_calls = {"n": 0}

    def _review(chapter_num, content, previous_feedback=""):
        _sleep(INJECTED_MS["review"])
        _review_calls["n"] += 1
        # 第 1 轮不达标触发修订，第 2 轮达标 —— 于是 revise 恰好跑 1 次
        return {"overall_score": 60 if _review_calls["n"] == 1 else 90, "issues": ["x"], "suggestions": ["y"]}

    def _revise(chapter_num, content, review, outline, context="", prev_ending=""):
        _sleep(INJECTED_MS["revise"])
        return content + "（修订后）"

    def _anti_slop(content):
        return []

    def _record(*_a, **_k):
        return None

    def _log(*_a, **_k):
        return None

    agent._plot_designer_analyze = _plot
    agent._build_context = _ctx
    agent._world_builder_build = _world
    agent._writer_generate = _write
    agent._reviewer_evaluate = _review
    agent._writer_revise = _revise
    agent._call_anti_slop_check = _anti_slop
    agent._record_conversation = _record
    agent.log = _log
    return agent


def main() -> int:
    import json

    agent = _build_agent()
    t0 = time.perf_counter()
    content = agent.generate_with_collaboration(1, "第一章：测试", "测试大纲" * 5, word_count=2000)
    wall_ms = (time.perf_counter() - t0) * 1000

    print("=" * 62)
    print(f"生成完成：{len(content)} 字，墙钟耗时 {wall_ms:.1f} ms")
    print("=" * 62)

    files = sorted(_LOG_DIR.glob("*.jsonl"))
    if not files:
        print("❌ 没有产生诊断日志文件 —— 归因根本没落盘")
        return 1

    entries = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))

    complete = [e for e in entries if e.get("category") == "CHAPTER" and e.get("event", "").endswith("/complete")]
    if not complete:
        print("❌ 没有 CHAPTER/complete 事件 —— 归因没写出来")
        print("   现有事件：", sorted({e.get("event") for e in entries}))
        return 1

    entry = complete[-1]
    data = entry.get("data", {})
    phases = data.get("phases_ms", {})
    print(f"\n记录到 {len(complete)} 条完成事件，明细：\n")
    print(f"  {'阶段':<14}{'注入(ms)':>10}{'记录(ms)':>12}{'偏差':>10}  {'判定':>6}")
    print("  " + "-" * 56)

    ok = True
    # review 期望 2 轮（每轮注入 250），revise 期望 1 轮（注入 300）
    expected = {
        "plot_design": INJECTED_MS["plot_design"],
        "write": INJECTED_MS["write"],
        "review": INJECTED_MS["review"] * 2,
        "revise": INJECTED_MS["revise"] * 1,
    }
    for name, exp in expected.items():
        got = phases.get(name)
        if got is None:
            print(f"  {name:<14}{exp:>10}{'缺失':>12}{'-':>10}  {'❌':>6}")
            ok = False
            continue
        delta = got - exp
        verdict = "✅" if abs(delta) <= TOLERANCE_MS else "❌"
        if abs(delta) > TOLERANCE_MS:
            ok = False
        print(f"  {name:<14}{exp:>10}{got:>12.1f}{delta:>+10.1f}  {verdict:>6}")

    print("\n  汇总字段：")
    for key in ("total_ms", "round_trips", "unaccounted_ms", "chars", "quality", "revision_rounds"):
        print(f"    {key:<16} = {data.get(key)}")

    # 关键结构性断言：往返次数只数**真的出网**的阶段。
    # plot(1) + write(1) + review×2 + revise×1 = 5；`world_build` 与 `context` 不出网，不计。
    rt = data.get("round_trips")
    rt_expected = 1 + 1 + 2 + 1
    print(f"\n  网络往返次数：记录 {rt}，期望 {rt_expected} ", "✅" if rt == rt_expected else "❌")
    if rt != rt_expected:
        print("    （注意：世界构建与上下文组装不出网，不该被计入 —— 见 novel_agent._NETWORK_PHASES 注释）")
        ok = False

    # 未归因余量应当很小（只有上下文组装等本地计算）
    unacc = data.get("unaccounted_ms", 0)
    print(f"  未归因余量：{unacc} ms ", "✅" if unacc < 500 else "⚠️ 偏大")

    print("\n" + ("✅ 段级耗时归因验证通过" if ok else "❌ 段级耗时归因验证失败"))
    print(f"（日志目录：{_LOG_DIR}）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
