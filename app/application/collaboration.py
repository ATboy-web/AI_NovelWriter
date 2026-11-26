"""5Agent 协作编排：PlotDesigner → WorldBuilder → Writer → Reviewer → Editor。

## 这是整个产品的主链路

一次调用串五个阶段、最多三轮"审校 → 修订"，收尾时把段级耗时落盘。
它原先写在 `NovelAgent` 里，与角色生成、大纲生成、定稿学习挤在同一个文件 ——
结果是"编排本身"几乎没法单独验证（必须先造一个能跑的 Agent）。

## 依赖显式化后的好处

给一组假协作者（记录调用、返回预置文本）就能跑完整五阶段：不必联网、不必落盘。
`tests/test_novel_agent_five_stage_contract.py` 就是这么做的 ——
mock 只到 `ai.chat` 一层，五个阶段全真跑。

## 🔴 两条不能丢的降级

1. **评审抛异常不得让整章作废**（2026-11-19 事故）：正文成本最高，评审只是质量门。
   异常在这里就地降级为"无评分"，而不是让已写好的整章丢掉。
2. **评审失败不给假分数**：`overall_score` 为 `None` 时既不能"当合格通过"，
   也不能"无脑修订"，而是交给人工确认。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from loguru import logger

from app.application.phase_timer import (
    PHASE_CONTEXT,
    PHASE_PLOT,
    PHASE_REVIEW,
    PHASE_REVISE,
    PHASE_WORLD,
    PHASE_WRITE,
    PhaseTimer,
)

__all__ = ["CollaborationDeps", "GenerateWithCollaboration", "emit_chapter_timing"]


def get_diagnostic_logger():
    """取当前诊断日志实例。

    ❗ **不要缓存**：测试隔离（`reset_logger()`）会换掉全局单例，
    缓存的快照会指向旧目录 —— 现象是"日志该写却没写"，且只在跑测试时出现。
    """
    try:
        from app.diagnostic_logger import get_logger

        return get_logger()
    except Exception:  # noqa: BLE001 - 诊断不可用不该影响生成
        return None


@dataclass
class CollaborationDeps:
    """编排需要的全部协作者。

    刻意全部用 callable：编排不该知道这些阶段是"类的方法"还是"独立函数"。
    """

    log: Callable[[str], None]
    record_conversation: Callable[[str, str, str], None]
    reset_conversation: Callable[[], None]
    analyze_plot: Callable[..., Dict]
    build_context: Callable[..., str]
    world_builder: Callable[..., str]
    writer_generate: Callable[..., str]
    writer_revise: Callable[..., str]
    reviewer_evaluate: Callable[..., Dict]
    call_anti_slop_check: Callable[..., list]
    call_tool: Callable[..., Any]
    #: 段级耗时落盘。做成可注入是为了让上层能在收尾处观察/替换（例如测试断言
    #: "五个阶段的耗时都被记下来"），而不必去改诊断日志的落盘实现。
    emit_timing: Callable[..., None]
    revision_memory: List[Dict] = field(default_factory=list)
    log_lock: Any = None
    quality_threshold: int = 75
    max_rounds: int = 3


def emit_chapter_timing(chapter_num: int, timer: PhaseTimer, review: Any, content: str, threshold: int) -> None:
    """把一章的段级耗时写进诊断日志。

    为什么值得单独一个方法：这段逻辑要"绝不因为日志失败而影响生成"，
    而 `generate_with_collaboration` 已经在收尾阶段、任何异常都会让**整章**白写。
    所以异常在这里就地吞掉并降级为 debug 日志。

    记录内容刻意做成可机读的形状（`phases_ms` 是 `{阶段: 毫秒}`），
    这样"近 30 天哪个阶段最慢"可以纯靠 jq/脚本统计，不需要人来读日志。
    """
    diag = get_diagnostic_logger()
    if diag is None:
        return
    try:
        summary = timer.summary()
        score = review.get("overall_score") if isinstance(review, dict) else None
        diag.chapter_event(
            chapter_num,
            "complete",
            {
                "chars": len(content),
                "quality": score,
                "threshold": threshold,
                "revision_rounds": sum(1 for c in summary["calls"] if c["phase"] == PHASE_REVISE),
                **summary,
            },
            duration_ms=summary["total_ms"],
        )
    except Exception as e:  # noqa: BLE001 - 计时/落盘失败绝不能影响生成结果
        # ⚠️ 这里必须用模块级的 loguru `logger`，不能写成上面那个 `diag`
        # （`DiagnosticLogger` 没有 `.debug`，一写就在异常处理里再抛一次，
        # 反而把"日志失败"升级成"整章生成失败"）。测试已钉住这条。
        logger.debug(f"[collaboration] 章节耗时归因落盘失败（忽略）: {e}")


class GenerateWithCollaboration:
    """跑一遍五阶段协作，返回成稿正文。"""

    def __init__(self, deps: CollaborationDeps) -> None:
        self.deps = deps
        #: 本轮真实评分（评审失败为 `None`）。Agent 读走后写入自身状态，
        #: 供 `finalize_chapter` 当学习信号 —— 此前这个分数算完就被丢掉了。
        self.last_quality: int | None = None

    def execute(
        self, chapter_num: int, chapter_title: str, chapter_outline: str, word_count: int = 3000, prev_context: str = ""
    ) -> str:
        """多智能体协作生成章节 v3.0 - 5Agent协作

        Hello-Agents参考流程: PlotDesigner→WorldBuilder→Writer→Reviewer→Editor
        """
        self.deps.reset_conversation()
        self.deps.log(f"[编排器] 5Agent协作启动: 第{chapter_num}章「{chapter_title}」")

        # 📊 段级耗时归因：全程只建一个计时器，每个 Phase 结束记一笔。
        # 收尾时统一发一条 `CHAPTER/.../complete`，含总时长与各段明细。
        timer = PhaseTimer()

        # 🔑 提取前一章结尾（在压缩前保存，确保不丢失）
        prev_ending = ""
        if prev_context and "【前一章" in str(prev_context):
            import re as _re

            m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n---|\n【|\Z)", str(prev_context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-1200:]

        # Phase 1: PlotDesigner - 分析大纲，管理伏笔
        self.deps.log("[PlotDesigner] 分析大纲与伏笔...")
        self.deps.record_conversation("PlotDesigner", "analyze", f"分析第{chapter_num}章大纲")
        _t = time.perf_counter()
        plot_analysis = self.deps.analyze_plot(chapter_num, chapter_title, chapter_outline)
        timer.phase(PHASE_PLOT, _t)

        # 注入前几章内容上下文
        plot_type = plot_analysis.get("type", "writing")
        _t = time.perf_counter()
        context = self.deps.build_context(chapter_num, prev_context, writing_phase=plot_type)
        timer.phase(PHASE_CONTEXT, _t)
        self.deps.log(f"[PlotDesigner] 情节类型: {plot_type}, 上下文已注入(全局摘要+卷摘要+角色+近期章节+创作指引)")

        # Phase 2: WorldBuilder - 场景与世界一致性
        self.deps.log("[WorldBuilder] 构建场景描写...")
        self.deps.record_conversation("WorldBuilder", "build", f"构建第{chapter_num}章场景")
        _t = time.perf_counter()
        world_context = self.deps.world_builder(chapter_num, plot_analysis)
        timer.phase(PHASE_WORLD, _t)

        # 🔧 BUG-1修复: 将WorldBuilder输出注入Writer上下文
        if world_context:
            context = f"【场景描写 - WorldBuilder输出】\n{world_context}\n\n{context}"

        # Phase 3: Writer - 创作内容
        self.deps.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self.deps.record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        _t = time.perf_counter()
        content = self.deps.writer_generate(
            chapter_num, chapter_title, chapter_outline, word_count, context=context, prev_ending=prev_ending
        )
        timer.phase(PHASE_WRITE, _t)

        # Phase 4-5: Reviewer → Editor 迭代修订
        prev_feedback = ""
        review: Dict = {}  # P-04：显式初始化，供结尾记录评分（循环至少跑一轮）
        for round_num in range(1, self.deps.max_rounds + 1):
            self.deps.log(f"[Reviewer] 审校第{chapter_num}章（第{round_num}轮）...")
            self.deps.record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            _t = time.perf_counter()
            # 🔴 评审失败**不得让整章作废**（2026-11-19 修正的回归）。
            #
            # 上一版给正文/评审都加了 `allow_reasoning_fallback=False`（对的方向：
            # 不拿工作笔记当成品），但评审这条调用**没有异常兜底**，于是
            # `_finalize_text` 在思考耗尽预算时抛出的异常直接穿透到
            # `generate_chapter` —— 一次"审校没跑成"把**已经写好的整章**丢掉了。
            # 日志实录：第 3 章 `Exception: DeepSeek思考模式耗尽 token`，
            # 正文其实已生成，却因为评审抛错而整章失败。
            #
            # 评审是**质量门**，不是正文的前置条件：拿不到分数时正确行为是
            # "记 warning → 按无评分处理 → 交给人工确认"（下面的 `score is None`
            # 分支本来就是这么设计的），而不是让本章失败。
            try:
                review = self.deps.reviewer_evaluate(chapter_num, content, previous_feedback=prev_feedback)
            except Exception as review_error:  # noqa: BLE001 - 评审故障必须降级，不能拖垮出稿
                self.deps.log(f"[Reviewer] ⚠️ 审校调用失败（{review_error}），本章按「无评分」继续，正文保留")
                self.deps.record_conversation("Reviewer", "error", f"审校调用失败: {review_error}")
                review = {"overall_score": None, "issues": [], "suggestions": []}
            finally:
                timer.phase(PHASE_REVIEW, _t)
            # R21 修复：这里紧接着就用 `review.setdefault(...)` / `review.get(...)`，
            # 而 `_reviewer_evaluate` 的解析结果**可能是 list**
            # （`parse_json_response` 在期望 dict 但 AI 返回顶层数组时会返回 list）。
            # 旧代码的守卫在第 748 行 —— **在所有使用之后**，等于没有；
            # 一旦命中，崩的是 `list.setdefault`（`AttributeError`），
            # 而且是在生成主流程里，整章生成失败。归一化必须在使用之前。
            if not isinstance(review, dict):
                self.deps.log("[Editor] ⚠️ 审校返回的不是 JSON 对象，本轮按「评审失败」处理")
                review = {"overall_score": None, "issues": [], "suggestions": []}

            # 工具调用: 一致性检查
            self.deps.call_tool("check_consistency", content=content[:500])

            # 调用写作技能: 去AI味检查
            slop_issues = self.deps.call_anti_slop_check(content)
            if slop_issues:
                review.setdefault("issues", []).extend(slop_issues)
                current = review.get("overall_score")
                # 评审失败（None）时不要用扣分把 None 变成数字 —— 那又是"伪装"
                if current is not None:
                    review["overall_score"] = max(0, current - len(slop_issues) * 2)
                self.deps.log(f"[写作技能] 发现{len(slop_issues)}个可扣分的AI写作痕迹")

            self.deps.log(f"[Editor] 质量裁定：{review.get('overall_score', 0)}分")
            self.deps.record_conversation(
                "Editor", "judge", f"评分{review.get('overall_score', 0)}，阈值{self.deps.quality_threshold}"
            )

            score = review.get("overall_score")
            if score is None:
                # 评审没给出可用分数 ≠ 合格。不自动通过，也不无脑修订 —— 交给人工。
                self.deps.log("[Editor] ⚠️ 本章评审未完成，无法裁定质量，跳过自动判定（请人工确认）")
                self.deps.record_conversation("Editor", "manual", "评审未完成，需人工确认")
                break

            if score >= self.deps.quality_threshold:
                self.deps.log("[Editor] ✅ 通过！质量达标。")
                self.deps.record_conversation("Editor", "approve", "质量达标，通过")
                break

            suggestions = review.get("suggestions", [])
            issues = review.get("issues", [])
            prev_feedback = f"上轮问题: {'; '.join(issues[:5])}" if issues else ""
            self.deps.log(
                f"[Editor] ⚠️ 质量不达标（{review.get('overall_score', 0)}/{self.deps.quality_threshold}），"
                f"触发第{round_num}轮修订..."
            )

            with self.deps.log_lock:
                self.deps.revision_memory.append(
                    {
                        "chapter": chapter_num,
                        "round": round_num,
                        "issues": issues,
                        "suggestions": suggestions,
                    }
                )

            self.deps.log("[Writer] 正在根据审校意见修订...")
            self.deps.record_conversation("Writer", "revise", f"第{round_num}轮修订")
            _t = time.perf_counter()
            content = self.deps.writer_revise(
                chapter_num, content, review, chapter_outline, context=context, prev_ending=prev_ending
            )
            timer.phase(PHASE_REVISE, _t)

        self.deps.log(f"[编排器] 第{chapter_num}章5Agent协作完成 ({len(content)}字)")

        # 📊 段级耗时归因落盘。放在这里而不是 `finally` 里：
        # 生成中途抛异常时**不该**报一个"看起来正常"的总时长 —— 失败的耗时
        # 由调用方的异常处理各自记录，两处混在一起会互相掩盖。
        self.deps.emit_timing(chapter_num, timer, review, content)

        # P-04：把本轮真实评分记在实例上，供 `finalize_chapter` 作为学习信号。
        # 此前这个分数在生成流程里算出来、写进对话日志、然后**被丢掉**：
        # 定稿学习时只能硬编码 `success=True`，无论这一章是 92 分还是 41 分。
        # 这里不直接把分数传给 finalize_chapter，是因为定稿有 4 个调用点
        # （生成流程 / 编辑器 / 全屏写作），只有本流程拿得到评分；
        # 记在实例上让"有评分时用评分、没有时按未知处理"成为统一行为。
        self.last_quality = review.get("overall_score") if isinstance(review, dict) else None
        return content
