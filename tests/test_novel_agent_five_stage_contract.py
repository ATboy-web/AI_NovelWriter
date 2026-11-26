"""novel_agent 五阶段产出的**契约回归**（mock 只到 AI 层，五阶段真跑）。

## 为什么单独一个文件

`test_novel_agent_coverage.py` / `test_novel_agent_deep.py` 里的协作测试是这么写的：

    agent._plot_designer_analyze = MagicMock(return_value={"type": "writing"})
    agent._writer_generate = MagicMock(return_value="章节内容")

于是它们验的是**编排接线**（"调了没有"），而下面三件事一条都没被验过：

1. **每个阶段的产出形状**是否满足下游的假设
   （`world_context` 是 `str` 还是 `None`？评审失败时分数是 `None` 还是 70？）
2. **阶段之间的传递保真**（WorldBuilder 写出来的场景，真的进了 Writer 的 prompt 吗？）
3. **降级路径**（评审抛异常时，已经写好的正文还能不能留下来）

本文件把 mock 下沉到 `ai.chat`，五个阶段**全部真跑**。

## AI 替身按 system prompt 分派，不按调用顺序

顺序会随修订轮次变化（一轮审校可能不触发修订）。按顺序断言的测试
"改一次流程红一次"，最后要么被删、要么被改成永远通过 —— 那就失去了回归意义。

## 三条最值钱的判据（缺了它们本文件是空转）

| 判据 | 防的问题 |
|---|---|
| 评审失败时 `overall_score is None` | 回落成 70 分会让"评审没跑成"看起来像"及格" |
| 评审抛异常后正文仍在 | 2026-11-19 真实事故：评审报错把整章丢了 |
| 修订稿过短时返回原文 | 模型截断输出会覆盖掉完整正文 |
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.novel_agent import NovelAgent

# ══════════════════════════════════════════════════════════ 替身


class FakeMemory:
    """够用的记忆替身：`_build_context` 需要的 6 个方法 + 元数据 + 设置。

    刻意**不用** `MagicMock()`：裸 MagicMock 的每个方法都返回真值对象，
    `_build_context` 会把它当字符串去 `len()`/切片，报出一堆与业务无关的错。
    显式给出"空"的返回值，测试失败时才指向真正的问题。
    """

    def __init__(self, novel_dir: Path | None = None, *, settings=None, meta=None):
        self.novel_dir = novel_dir
        self._settings = settings or {}
        self._meta = meta or {}
        self.summaries: list[tuple[int, str]] = []

    # ---- _build_context 用到的 ----
    def get_global_summary(self) -> str:
        return ""

    def get_current_volume_summary(self, chapter_num: int) -> str:
        return ""

    def get_recent_summaries(self, count: int = 3):
        return [t for _n, t in self.summaries[-count:]]

    def get_active_characters(self, chapter_num: int, window: int = 50):
        return []

    def get_characters(self) -> dict:
        return {}

    def retrieve_relevant(self, query: str, top_k: int = 3):
        return []

    # ---- 写作 / 修订 / 世界观用到的 ----
    def get_meta(self, key: str, default=""):
        return self._meta.get(key, default)

    def get_settings(self):
        return self._settings

    def save_chapter_summary(self, chapter_num: int, summary: str) -> None:
        self.summaries.append((chapter_num, summary))


class ScriptedAI:
    """按 system prompt 分派返回值的 AI 替身，并记录每次真实调用。

    四个阶段的 system prompt 首句互不相同，是最稳的辨识依据：
    - PlotDesigner: "你是专业情节设计师"
    - Writer:       "你是一位专业的小说作家（Writer Agent）。"
    - Reviewer:     "你是一位专业的小说审校编辑（Reviewer Agent）。"
    - Reviser:      "...正在修订自己的作品"
    （Writer 与 Reviser 前缀重叠，所以"正在修订"必须先判。）
    """

    def __init__(self, *, plot="{}", writer="正文内容", reviewer="{}", reviser="修订稿", metrics=None):
        self.plot = plot
        self.writer = writer
        self.reviewer = reviewer
        self.reviser = reviser
        self.metrics = metrics
        self.calls: list[dict] = []

    # ---- 分派 ----
    def _phase_of(self, system: str) -> str:
        if "正在修订" in system:
            return "revise"
        if "小说审校编辑" in system:
            return "review"
        if "情节设计师" in system:
            return "plot"
        if "小说作家（Writer Agent）" in system:
            return "write"
        raise AssertionError(f"未识别的阶段（system 首 120 字）：{system[:120]!r}")

    def _next(self, phase: str, index: int):
        value = {"plot": self.plot, "write": self.writer, "review": self.reviewer, "revise": self.reviser}[phase]
        if callable(value):
            return value(index)
        return value

    def chat(self, messages, system="", **kwargs):
        phase = self._phase_of(system)
        seen = sum(1 for c in self.calls if c["phase"] == phase)
        self.calls.append(
            {
                "phase": phase,
                "system": system,
                "user": messages[-1]["content"] if messages else "",
                "kwargs": kwargs,
            }
        )
        return self._next(phase, seen)

    # ---- 断言辅助 ----
    def of(self, phase: str) -> list[dict]:
        return [c for c in self.calls if c["phase"] == phase]

    def phases(self) -> list[str]:
        return [c["phase"] for c in self.calls]


@pytest.fixture
def make_agent(tmp_path):
    """造一个五阶段可真跑的 NovelAgent（config=None 走默认预算）。"""
    made: list[NovelAgent] = []

    def _make(ai=None, *, settings=None, meta=None, memory=None, max_rounds=2, threshold=60):
        ai = ai or ScriptedAI()
        mem = memory or FakeMemory(tmp_path, settings=settings, meta=meta)
        agent = NovelAgent(ai, mem, log_callback=lambda _m: None)
        agent.MAX_REVISION_ROUNDS = max_rounds
        agent.QUALITY_THRESHOLD = threshold
        agent._call_anti_slop_check = lambda _content: []  # 评分干扰项默认关掉，单独测
        made.append(agent)
        return agent

    yield _make

    for agent in made:
        agent.orchestrator.shutdown(wait=False)


def _review_json(score, *, issues=None, suggestions=None, strengths=None) -> str:
    import json

    return json.dumps(
        {
            "overall_score": score,
            "issues": issues or [],
            "suggestions": suggestions or [],
            "strengths": strengths or [],
            "dimensions": {},
        },
        ensure_ascii=False,
    )


# ══════════════════════════════════════════════════════════ 一、PlotDesigner


class TestPlotDesignerOutput:
    def test_short_outline_does_not_call_ai(self, make_agent):
        """大纲太短时不值得发一次网络往返 —— 必须走本地推断。"""
        agent = make_agent()
        agent._plot_designer_analyze(5, "第5章", "")

        assert agent.ai.of("plot") == [], "短大纲竟然发出了 AI 调用（白花一次往返）"

    @pytest.mark.parametrize(
        ("chapter", "expected"),
        [(1, "opening"), (3, "opening"), (4, "writing"), (9, "writing"), (10, "ending"), (20, "ending")],
    )
    def test_local_inference_rules(self, make_agent, chapter, expected):
        """前三章 = opening、整十章 = ending、其余 = writing。"""
        agent = make_agent()
        assert agent._plot_designer_analyze(chapter, "标题", "")["type"] == expected

    def test_output_always_has_a_usable_type(self, make_agent):
        """契约：`type` 必须是 `PLOT_TYPES` 里的字符串。

        它会被当作字典键（`ratios.get(writing_phase)`）使用，
        所以"缺键"和"给个 dict"都必须被归一掉。"""
        from app.novel_agent import PLOT_TYPES

        agent = make_agent(ai=ScriptedAI(plot='{"pace": "fast"}'))
        result = agent._plot_designer_analyze(5, "标题", "这是一段足够长的大纲内容，超过十个字。")

        assert isinstance(result, dict)
        assert result["type"] in PLOT_TYPES
        assert result["pace"] == "fast", "归一不该丢掉无下游消费者的字段"

    @pytest.mark.parametrize("bad_type", ['{"name": "action"}', "5", "null", '["action"]'])
    def test_non_string_type_does_not_crash_generation(self, make_agent, bad_type):
        """🔴 真缺陷回归（2026-11-26 实测崩溃）。

        `ratios.get(writing_phase)` 收到 dict ⇒ `TypeError: unhashable type`，
        异常一路穿透到 `generate_chapter`，**整章生成失败**。
        模型输出不可信，这类形状必须在下游使用之前归一。
        """
        agent = make_agent(ai=ScriptedAI(plot=f'{{"type": {bad_type}}}', reviewer=_review_json(90)))
        content = agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 500)

        assert isinstance(content, str)

    def test_unknown_type_falls_back_to_writing(self, make_agent):
        """枚举外的值（模型自由发挥）提前归一，让输出可断言。"""
        agent = make_agent(ai=ScriptedAI(plot='{"type": "climax"}'))
        assert agent._plot_designer_analyze(5, "标题", "这是一段足够长的大纲内容，超过十个字。")["type"] == "writing"

    @pytest.mark.parametrize(
        "bad_reply",
        ["不是 JSON", "", "[]", "null", '{"unclosed": ', "好的，我来分析一下：情节应该是紧张型"],
    )
    def test_bad_ai_reply_falls_back(self, make_agent, bad_reply):
        """模型返回任何非 dict 都不能抛，也不能把字符串当成 dict 用。"""
        agent = make_agent(ai=ScriptedAI(plot=bad_reply))
        result = agent._plot_designer_analyze(5, "标题", "这是一段足够长的大纲内容，超过十个字。")

        assert isinstance(result, dict)
        assert result["type"] == "writing"

    def test_ai_exception_falls_back_without_raising(self, make_agent):
        agent = make_agent()

        def boom(_msgs, system="", **_kw):
            raise RuntimeError("模型超时")

        agent.ai.chat = boom
        result = agent._plot_designer_analyze(5, "标题", "这是一段足够长的大纲内容，超过十个字。")

        assert result == {"type": "writing", "pace": "medium", "foreshadowing": []}

    def test_parses_json_wrapped_in_chatter(self, make_agent):
        """模型常在 JSON 前后加解释 —— 解析器要能抠出来（这是最常见的真实形态）。"""
        agent = make_agent(ai=ScriptedAI(plot='好的，分析如下：\n{"type": "action", "pace": "fast"}\n以上。'))
        result = agent._plot_designer_analyze(5, "标题", "这是一段足够长的大纲内容，超过十个字。")

        assert result["type"] == "action"
        assert result["pace"] == "fast"


# ══════════════════════════════════════════════════════════ 二、WorldBuilder


class TestWorldBuilderOutput:
    def test_no_settings_yields_empty_string(self, make_agent):
        """编排里写的是 `if world_context:` —— 必须是 `""` 而不是 `None`/`"None"`。"""
        agent = make_agent()
        out = agent._world_builder_build(1, {"type": "writing"})

        assert out == ""
        assert isinstance(out, str)

    def test_settings_with_known_regions(self, make_agent):
        agent = make_agent(settings={"world": {"已知区域": ["黑风岭", "青石镇", "断魂谷", "第四处"]}})
        out = agent._world_builder_build(1, {"type": "writing"})

        assert "黑风岭" in out and "青石镇" in out
        assert "第四处" not in out, "只取前三处（提示词预算有限）"

    @pytest.mark.parametrize(
        "bad_settings",
        [
            {"world": None},
            {"world": "不是字典"},
            {"world": {"已知区域": {"黑风岭": 1}}},
            {"world": {"已知区域": 42}},
            {"world": {"已知区域": []}},
            {},
        ],
    )
    def test_malformed_settings_never_raise(self, make_agent, bad_settings):
        """设置是用户/旧版本写的 JSON，形状不可信 —— 必须静默降级成空串。"""
        agent = make_agent(settings=bad_settings)
        assert agent._world_builder_build(1, {}) == ""

    def test_string_region_is_one_region_not_characters(self, make_agent):
        """🔴 真缺陷回归：`', '.join("黑风岭")` 会逐字拆成「黑, 风, 岭」。

        用户手写 settings.json 时写成字符串是很容易发生的事，
        而"逐字拆开"不会报错，只是把垃圾写进了提示词。
        """
        agent = make_agent(settings={"world": {"已知区域": "黑风岭"}})
        out = agent._world_builder_build(1, {})

        assert "黑风岭" in out
        assert "黑, 风, 岭" not in out, "字符串被逐字拆开了"

    def test_does_not_call_ai(self, make_agent):
        """WorldBuilder 目前是**纯记忆查询**（不发请求）—— 这是性能事实，
        不该被误当成"它能生成场景"。将来若改成发请求，这条会红，提醒同步耗时归因。"""
        agent = make_agent(settings={"world": {"已知区域": ["甲"]}})
        agent._world_builder_build(1, {})
        assert agent.ai.calls == []


# ══════════════════════════════════════════════════════════ 三、Writer


class TestWriterOutput:
    def test_none_reply_becomes_empty_string(self, make_agent):
        """`response or ""` 的意义：None 不能变成字符串 "None" 写进书里。"""
        agent = make_agent(ai=ScriptedAI(writer=None))
        assert agent._writer_generate(1, "标题", "大纲", 100) == ""

    def test_protagonist_lock_is_injected(self, make_agent):
        agent = make_agent(meta={"protagonist": "林风"})
        agent._writer_generate(1, "标题", "大纲", 100)

        prompt = agent.ai.of("write")[0]
        blob = prompt["system"] + prompt["user"]
        assert "林风" in blob, "锁定主角名没进提示词（会写出换主角的章节）"
        assert "禁止更换主角名" in blob

    def test_context_reaches_prompt(self, make_agent):
        agent = make_agent()
        agent._writer_generate(1, "标题", "大纲", 100, context="【特别标记的上下文】")

        blob = agent.ai.of("write")[0]["system"] + agent.ai.of("write")[0]["user"]
        assert "【特别标记的上下文】" in blob

    def test_prev_ending_reaches_prompt(self, make_agent):
        agent = make_agent()
        agent._writer_generate(2, "标题", "大纲", 100, context="ctx", prev_ending="他推开了那扇门")

        blob = "".join(c["system"] + c["user"] for c in agent.ai.of("write"))
        assert "他推开了那扇门" in blob, "前一章结尾没注入（章节之间会接不上）"

    def test_thinking_disabled_and_no_reasoning_fallback(self, make_agent):
        """正文不许兜底：思考笔记会被当成正文写进书里。"""
        agent = make_agent()
        agent._writer_generate(1, "标题", "大纲", 100, context="ctx")

        kwargs = agent.ai.of("write")[0]["kwargs"]
        assert kwargs["thinking_enabled"] is False
        assert kwargs.get("allow_reasoning_fallback") is False


# ══════════════════════════════════════════════════════════ 四、Reviewer


class TestReviewerOutput:
    def test_score_appears_under_both_names(self, make_agent, tmp_path):
        """`overall` 与 `overall_score` 必须是**同一个值**（派生别名，不是两个真相源）。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(82)), memory=FakeMemory(tmp_path))
        result = agent._reviewer_evaluate(1, "正文内容" * 100)

        assert result["overall"] == result["overall_score"] == 82

    def test_review_is_persisted(self, make_agent, tmp_path):
        """评审结果必须落盘 —— 否则"上次评审"面板永远是空的。"""
        from app.review_store import load_review

        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(77)), memory=FakeMemory(tmp_path))
        agent._reviewer_evaluate(3, "正文内容" * 100)

        record = load_review(tmp_path, 3)
        assert record is not None and record.overall == 77

    @pytest.mark.parametrize("bad_reply", ["不是 JSON", "", "[]", '{"issues": []}', "null"])
    def test_failure_is_not_disguised_as_a_score(self, make_agent, tmp_path, bad_reply):
        """🔴 核心契约：评审没跑成时 `overall_score` 必须是 `None`。

        旧实现回落到 `{"overall_score": 70}`，而 70 分通常就在及格线附近 ——
        "评审失败"被记成了"通过"，这正是本契约要钉住的历史事故。
        """
        agent = make_agent(ai=ScriptedAI(reviewer=bad_reply), memory=FakeMemory(tmp_path))
        result = agent._reviewer_evaluate(1, "正文内容" * 100)

        assert result["overall_score"] is None, f"评审失败却给出了分数：{result['overall_score']}"
        assert result["ok"] is False
        assert result["error"], "评审失败必须带原因，否则用户无从排查"

    def test_top_level_array_is_normalized(self, make_agent, tmp_path):
        """模型把评审结果写成顶层数组时不能崩（`list.setdefault` 曾导致整章失败）。

        用**多元素**数组：单元素数组会被解析器合理地拆包成那个对象，
        那不构成"类型异常"，验不到这条路径。
        """
        agent = make_agent(ai=ScriptedAI(reviewer='[{"overall_score": 90}, {"overall_score": 20}]'))
        agent.memory = FakeMemory(tmp_path)
        result = agent._reviewer_evaluate(1, "正文" * 100)

        assert isinstance(result, dict)
        assert result["overall_score"] is None, "结构不对应按失败处理，不能挑一个分数用"

    def test_previous_feedback_reaches_prompt(self, make_agent, tmp_path):
        """上一轮的问题必须回灌给评审 —— 否则每轮都从零开始挑毛病。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(80)), memory=FakeMemory(tmp_path))
        agent._reviewer_evaluate(1, "正文" * 100, previous_feedback="上轮问题: 节奏拖沓")

        call = agent.ai.of("review")[0]
        assert "节奏拖沓" in call["system"] + call["user"]

    def test_long_content_is_sampled_not_truncated(self, make_agent, tmp_path):
        """超长章节取「开头+中间+结尾」，不能只取开头（结尾常有质量问题）。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(80)), memory=FakeMemory(tmp_path))
        content = "开头标记" + "中" * 6000 + "结尾标记"
        agent._reviewer_evaluate(1, content)

        user = agent.ai.of("review")[0]["user"]
        assert "开头标记" in user and "结尾标记" in user
        assert "中间省略" in user


# ══════════════════════════════════════════════════════════ 五、Editor/Revise


class TestReviserOutput:
    def test_short_revision_falls_back_to_original(self, make_agent):
        """🔴 修订稿不足原文一半 ⇒ 保留原文。

        模型截断续写时会返回半截内容，而"覆盖"是无提示的 ——
        用户第二天打开发现正文少了一半，是这套流程里最伤数据的一种失败。
        """
        agent = make_agent(ai=ScriptedAI(reviser="太短了"))
        original = "完整正文" * 500
        out = agent._writer_revise(1, original, {"issues": [], "suggestions": [], "strengths": []}, "大纲")

        assert out == original

    def test_empty_revision_falls_back_to_original(self, make_agent):
        agent = make_agent(ai=ScriptedAI(reviser=None))
        original = "完整正文" * 100
        assert agent._writer_revise(1, original, {"issues": [], "suggestions": []}, "大纲") == original

    def test_good_revision_replaces_content(self, make_agent):
        revised = "修订后的正文" * 200
        agent = make_agent(ai=ScriptedAI(reviser=revised))
        original = "原正文" * 100

        assert agent._writer_revise(1, original, {"issues": [], "suggestions": []}, "大纲") == revised

    def test_review_items_reach_prompt(self, make_agent):
        agent = make_agent()
        agent._writer_revise(
            1,
            "原正文" * 100,
            {"issues": ["节奏拖沓", "对话生硬"], "suggestions": ["压缩过渡段"], "strengths": ["画面感强"]},
            "大纲",
        )

        prompt = agent.ai.of("revise")[0]
        blob = prompt["system"] + prompt["user"]
        for text in ("节奏拖沓", "对话生硬", "压缩过渡段", "画面感强"):
            assert text in blob, f"评审项「{text}」没进修订提示词"

    def test_thinking_disabled_for_revision(self, make_agent):
        """修订稿会覆盖正文，绝不能让"让我想想"当成品。"""
        agent = make_agent()
        agent._writer_revise(1, "原正文" * 100, {"issues": [], "suggestions": []}, "大纲")

        kwargs = agent.ai.of("revise")[0]["kwargs"]
        assert kwargs["thinking_enabled"] is False
        assert kwargs.get("allow_reasoning_fallback") is False


# ══════════════════════════════════════════════════════════ 六、阶段间传递


class TestFiveStageHandoff:
    """五阶段真跑，验证**上一阶段的产出真的进了下一阶段的输入**。

    这类断言用 MagicMock 的方法级替身做不到 —— 替身返回什么，
    "传递"就成了替身自己的事。必须让真实代码去拼 prompt。
    """

    def test_world_scene_reaches_writer_prompt(self, make_agent):
        agent = make_agent(
            ai=ScriptedAI(reviewer=_review_json(90)),
            settings={"world": {"已知区域": ["黑风岭"]}},
        )
        agent.generate_with_collaboration(1, "初入黑风岭", "林风踏入黑风岭，遇到山匪。", 800)

        writer_prompt = agent.ai.of("write")[0]
        blob = writer_prompt["system"] + writer_prompt["user"]
        assert "黑风岭" in blob, "WorldBuilder 的场景没进 Writer 的提示词（BUG-1 回归）"
        assert "WorldBuilder输出" in blob

    def test_plot_type_drives_context_allocation(self, make_agent):
        """PlotDesigner 判定的阶段必须传给 `_build_context`。

        阶段决定的是**上下文预算分配**（opening 多给世界观、action 多给近章），
        传错就等于用错预算 —— 而输出看起来仍然"正常"，只是效果变差。
        """
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(90)))
        seen: list[str] = []
        real = agent._build_context

        def spy(chapter_num, extra_context="", max_chars=None, writing_phase="writing"):
            seen.append(writing_phase)
            return real(chapter_num, extra_context, max_chars, writing_phase)

        agent._build_context = spy
        agent.generate_with_collaboration(1, "第1章", "", 800)  # 空大纲 ⇒ 本地推断 opening

        assert "opening" in seen, f"PlotDesigner 的阶段没有传给上下文构建：{seen}"

    def test_unknown_plot_type_does_not_crash(self, make_agent):
        """模型可能吐出枚举外的 type（如 "climax"）—— 必须回落到默认预算。"""
        agent = make_agent(ai=ScriptedAI(plot='{"type": "climax"}', reviewer=_review_json(90)))
        content = agent.generate_with_collaboration(5, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert isinstance(content, str)

    def test_previous_round_issues_feed_next_review(self, make_agent):
        """第 1 轮不达标 ⇒ 第 2 轮评审必须看到第 1 轮的问题。"""
        agent = make_agent(
            ai=ScriptedAI(
                reviewer=lambda i: _review_json(40, issues=["节奏拖沓"]) if i == 0 else _review_json(90),
                reviser="修订后的正文" * 200,
            ),
            max_rounds=2,
        )
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        reviews = agent.ai.of("review")
        assert len(reviews) == 2, f"应当审校两轮，实际 {len(reviews)}"
        second = reviews[1]["system"] + reviews[1]["user"]
        assert "上轮问题" in second
        assert "节奏拖沓" in second

    def test_full_five_stage_order(self, make_agent):
        """一次达标的生成 = plot → write → review，**不该有 revise**。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert agent.ai.phases() == ["plot", "write", "review"]

    def test_revision_round_adds_revise_phase(self, make_agent):
        agent = make_agent(
            ai=ScriptedAI(reviewer=lambda i: _review_json(30) if i == 0 else _review_json(95), reviser="改后" * 500),
            max_rounds=2,
        )
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert agent.ai.phases() == ["plot", "write", "review", "revise", "review"]


# ══════════════════════════════════════════════════════════ 七、降级路径


class TestDegradationPaths:
    def test_review_exception_keeps_the_chapter(self, make_agent):
        """🔴 2026-11-19 事故回归：评审抛异常不得让整章作废。

        正文已经生成（成本最高的一步），评审只是**质量门**。
        旧实现在这里让异常穿透，用户丢掉了一整章。
        """
        calls = {"n": 0}

        def chat(messages, system="", **kwargs):
            if "小说审校编辑" in system:
                calls["n"] += 1
                raise RuntimeError("DeepSeek思考模式耗尽 token")
            if "情节设计师" in system:
                return "{}"
            return "这是已经写好的正文" * 50

        agent = make_agent()
        agent.ai.chat = chat
        content = agent.generate_with_collaboration(3, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert content.startswith("这是已经写好的正文"), "评审失败把正文丢了"
        assert calls["n"] == 1, "评审失败后不该继续重试（预算已耗尽）"

    def test_review_failure_does_not_trigger_revision(self, make_agent, tmp_path):
        """评分 None 时既不能"当合格通过"，也不能"无脑修订" —— 应交给人工。"""
        agent = make_agent(ai=ScriptedAI(reviewer="不是 JSON"), memory=FakeMemory(tmp_path))
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert agent.ai.of("revise") == [], "评审没跑成却触发了修订（在盲改）"
        assert len(agent.ai.of("review")) == 1, "评审没跑成后不该反复重试"

    def test_review_returns_list_is_normalized(self, make_agent, tmp_path):
        agent = make_agent(ai=ScriptedAI(reviewer="[1, 2, 3]"), memory=FakeMemory(tmp_path))
        content = agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert isinstance(content, str) and content

    def test_empty_writer_output_gives_placeholder_not_crash(self, make_agent, tmp_path):
        """正文为空时 `generate_chapter` 应返回占位提示，而不是抛异常或返回空串。"""
        agent = make_agent(ai=ScriptedAI(writer="", reviewer="不是 JSON"), memory=FakeMemory(tmp_path))
        out = agent.generate_chapter(1, "标题", "大纲", 500)

        assert "内容生成失败" in out
        assert "第1章" in out

    def test_quality_below_threshold_triggers_revision(self, make_agent):
        agent = make_agent(
            ai=ScriptedAI(reviewer=lambda i: _review_json(50) if i == 0 else _review_json(90), reviser="改后" * 500),
            max_rounds=2,
            threshold=60,
        )
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert len(agent.ai.of("revise")) == 1

    def test_max_rounds_bounds_the_loop(self, make_agent):
        """连续不达标时必须停下 —— 否则会无限烧 API。

        ❗ 当前行为：`max_rounds=2` 会发 **2 次评审 + 2 次修订**，
        最后一次修订**不会再被评审**（循环到轮数上限就结束了）。
        这条刻意钉住现状而不是"修正"它：最后那版改稿仍然进了正文，
        对用户是有价值的；只是它的质量未知。将来若决定省掉这一次调用，
        本用例会红，提醒同步更新"最后一次修订无评分"的语义。
        """
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(10), reviser="改后" * 500), max_rounds=2)
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert len(agent.ai.of("review")) == 2
        assert len(agent.ai.of("revise")) == 2, "每轮不达标都会修订（含最后一轮，不再被评审）"
        assert agent.last_chapter_quality == 10, "终态评分来自最后一轮评审"


# ══════════════════════════════════════════════════════════ 八、终态输出


class TestTerminalOutputs:
    def test_last_chapter_quality_records_real_score(self, make_agent):
        """定稿学习要用真实评分：此前算出来写进日志后就丢了，只能硬编码 success=True。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(88)))
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert agent.last_chapter_quality == 88

    def test_last_chapter_quality_is_none_when_review_failed(self, make_agent, tmp_path):
        """评审失败必须记 None，**不能记 0 或 70** —— 那会把"未知"学成"很差"。"""
        agent = make_agent(ai=ScriptedAI(reviewer="不是 JSON"), memory=FakeMemory(tmp_path))
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert agent.last_chapter_quality is None

    def test_conversation_log_covers_all_agents(self, make_agent):
        """对话日志是面板上"Agent 协作过程"的唯一数据源。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        roles = {getattr(m.role, "name", str(m.role)) for m in agent._conversation_log}
        assert {"PLOT", "WORLD", "WRITER", "REVIEWER", "EDITOR"} <= roles, f"缺少阶段：{roles}"

    def test_timing_failure_does_not_break_generation(self, make_agent, monkeypatch):
        """耗时归因落盘失败绝不能影响出稿（它已在收尾阶段，异常会毁掉整章）。"""
        import app.novel_agent as mod

        class BrokenDiag:
            def chapter_event(self, *_a, **_kw):
                raise RuntimeError("磁盘满了")

        monkeypatch.setattr(mod, "_diag_logger", lambda: BrokenDiag())
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))

        content = agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)
        assert content


# ══════════════════════════════════════════════════════════ 九、评分与去AI味交互


class TestSlopScoreInteraction:
    """`_call_anti_slop_check` 的命中会扣分 —— 这条链路的两个边界都要钉住。"""

    def test_slop_issues_lower_a_real_score(self, make_agent):
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(72)))
        agent._call_anti_slop_check = lambda _c: ["套话开头", "形容词堆砌"]

        agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        # 72 - 2*2 = 68 < 70(默认阈值 60 已改) —— 这里只验"扣了分"这件事，
        # 通过第 2 轮用 95 分收尾
        assert agent.last_chapter_quality is not None

    def test_slop_issues_do_not_turn_none_into_a_number(self, make_agent, tmp_path):
        """评分是 None 时扣分必须跳过 —— 否则 `None - 4` 会被写成"负分"或"0 分"。"""
        agent = make_agent(ai=ScriptedAI(reviewer="不是 JSON"), memory=FakeMemory(tmp_path))
        agent._call_anti_slop_check = lambda _c: ["套话开头", "形容词堆砌"]

        result = agent.generate_with_collaboration(1, "标题", "一段足够长的大纲内容用于触发AI。", 800)

        assert isinstance(result, str)
        assert agent.last_chapter_quality is None, "评审失败被扣分逻辑「洗」成了数字"


# ══════════════════════════════════════════════════════════ 十、元：契约不能两处维护


class TestContractSourcesDoNotDrift:
    """`PLOT_TYPES` 与上下文预算表必须**同源**。

    `type` 是那张预算表的键。两处各写一遍"有哪些情节类型"，
    迟早出现"归一放行了一个没有预算的 type"—— 表现是上下文配额失衡，
    但不会报错，只会让某一阶段的章节质量莫名变差。
    """

    def test_plot_types_derive_from_context_ratios(self):
        from app.novel_agent import CONTEXT_RATIOS, PLOT_TYPES

        assert PLOT_TYPES == tuple(CONTEXT_RATIOS), "PLOT_TYPES 不再是派生值（被硬编码了？）"

    def test_every_plot_type_has_a_ratio_entry(self):
        from app.novel_agent import CONTEXT_RATIOS, PLOT_TYPES

        for plot_type in PLOT_TYPES:
            assert plot_type in CONTEXT_RATIOS

    def test_ratios_sum_to_one(self):
        """各段占比之和应为 1（否则预算会凭空多出或丢掉一截）。"""
        from app.novel_agent import CONTEXT_RATIOS

        for plot_type, parts in CONTEXT_RATIOS.items():
            total = sum(parts.values())
            assert abs(total - 1.0) < 1e-9, f"{plot_type} 的占比之和为 {total}"

    def test_normalize_keeps_valid_type(self):
        from app.novel_agent import PLOT_TYPES, normalize_plot_analysis

        for plot_type in PLOT_TYPES:
            assert normalize_plot_analysis({"type": plot_type})["type"] == plot_type

    def test_normalize_does_not_mutate_input(self):
        """归一必须返回新字典 —— 原地改会把调用方持有的对象一起改掉。"""
        from app.novel_agent import normalize_plot_analysis

        original = {"type": {"bad": 1}}
        normalize_plot_analysis(original)
        assert original == {"type": {"bad": 1}}


# ══════════════════════════════════════════════════════════ 十一、编排本身（五阶段）


class TestOrchestrationFiveStages:
    """`generate_with_collaboration` 作为**编排者**的契约。

    上一组验的是「每个阶段的产出对不对」，这一组验「编排有没有把它们串对」：
    阶段顺序、耗时归因、事件载荷、上下文回灌、工具调用、修订记忆。
    """

    def _run(
        self,
        agent,
        *,
        chapter_num=1,
        title="第1章",
        outline="一段足够长的大纲内容用于触发AI。",
        word_count=800,
        prev_context="",
    ):
        return agent.generate_with_collaboration(chapter_num, title, outline, word_count, prev_context=prev_context)

    # ---- 阶段顺序与耗时归因 ----

    def test_phase_names_cover_all_five_stages(self, make_agent):
        """五阶段的耗时都应该被**分段记录**。

        漏记某个 phase 不会报错，只是那段时间变成 `unaccounted_ms` ——
        而「这一章为什么慢」就永远归因不到具体 Agent。
        """
        from app.novel_agent import PHASE_CONTEXT, PHASE_PLOT, PHASE_REVIEW, PHASE_WORLD, PHASE_WRITE

        expected = {PHASE_PLOT, PHASE_CONTEXT, PHASE_WORLD, PHASE_WRITE, PHASE_REVIEW}
        captured: dict = {}
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        agent._emit_chapter_timing = lambda _c, timer, _r, _ct: captured.update(timer.summary())
        self._run(agent)

        missing = expected - set(captured["phases_ms"])
        assert not missing, f"耗时归因缺阶段：{missing}"

    def test_revise_phase_absent_when_first_round_passes(self, make_agent):
        from app.novel_agent import PHASE_REVISE

        captured: dict = {}
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        agent._emit_chapter_timing = lambda _c, timer, _r, _ct: captured.update(timer.summary())
        self._run(agent)

        assert PHASE_REVISE not in captured["phases_ms"], "首轮通过却记了修订耗时"

    def test_network_round_trips_counted(self, make_agent):
        """网络往返次数是「这一章到底发了几个请求」的唯一可信来源。"""
        captured: dict = {}
        agent = make_agent(ai=ScriptedAI(reviewer=lambda i: _review_json(30) if i == 0 else _review_json(95)))
        agent._emit_chapter_timing = lambda _c, timer, _r, _ct: captured.update(timer.summary())
        self._run(agent)

        # plot + write + review + revise + review
        assert captured["round_trips"] == 5, captured["phases_ms"]

    # ---- 事件载荷 ----

    def test_timing_event_payload_shape(self, make_agent, monkeypatch):
        """`chapter_event` 的载荷是面板与 jq 统计的共同输入，键不能丢。"""
        got: dict = {}

        class Diag:
            def chapter_event(self, chapter, event, payload, duration_ms=None):
                got.update({"chapter": chapter, "event": event, "payload": payload, "duration_ms": duration_ms})

        # 耗时落盘已搬到 application.collaboration（2026-11-26），
        # 所以要替它自己的诊断器取用点，而不是 novel_agent 的。
        import app.application.collaboration as mod

        monkeypatch.setattr(mod, "get_diagnostic_logger", lambda: Diag())
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(88)))
        self._run(agent)

        assert got["event"] == "complete"
        assert got["chapter"] == 1
        payload = got["payload"]
        assert payload["chars"] > 0
        assert payload["quality"] == 88
        assert payload["threshold"] == agent.QUALITY_THRESHOLD
        assert payload["revision_rounds"] == 0
        assert "phases_ms" in payload and "round_trips" in payload
        assert got["duration_ms"] is not None

    # ---- 上下文回灌 ----

    def test_prev_chapter_ending_is_extracted_and_injected(self, make_agent):
        """`prev_context` 里的「前一章结尾」必须进 Writer 的提示词。

        上下文整体会被压缩，而结尾那 1200 字是**刻意保留**的 ——
        章节之间接不接得上全靠它。

        ⚠️ 这里验的是**行为**：两条路径都能满足 —— 编排主动提取后传入，
        或阶段内部从 context 回退提取。下一条件才专门钉住「编排这一层不许退化」。
        """
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        prev = "【前一章·第1章结尾（已压缩）】\n他推开门，看见满屋的血。\n---\n【其他上下文】"

        self._run(agent, chapter_num=2, prev_context=prev)

        blob = "".join(c["system"] + c["user"] for c in agent.ai.of("write"))
        assert "他推开门，看见满屋的血。" in blob

    def test_orchestrator_passes_prev_ending_explicitly(self, make_agent):
        """钉住**编排这一层**：结尾必须作为 `prev_ending` 参数传给 Writer。

        为什么单独一条：阶段内部还有一层回退提取（`GenerateDraft` 里那段 regex），
        所以只删编排那层，上面那条行为用例**仍然通过**（反向验证实测过）。
        两层都要有，但退化要能各自被发现 —— 编排层没了意味着
        「上下文一压缩，结尾就丢」。
        """
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        seen: dict = {}
        real = agent._writer_generate

        def spy(chapter_num, chapter_title, chapter_outline, word_count, context=None, prev_ending=""):
            seen["prev_ending"] = prev_ending
            return real(chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending)

        agent._writer_generate = spy
        prev = "【前一章·第1章结尾（已压缩）】\n他推开门，看见满屋的血。\n---\n【其他上下文】"
        self._run(agent, chapter_num=2, prev_context=prev)

        assert "他推开门，看见满屋的血。" in seen.get("prev_ending", ""), (
            f"编排没有把结尾传给 Writer，实际：{seen.get('prev_ending')!r}"
        )

    def test_empty_world_context_does_not_inject_empty_section(self, make_agent):
        """WorldBuilder 返回空串时，不能往上下文里塞一个空的「场景描写」段。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))  # settings 为空
        self._run(agent)

        blob = "".join(c["system"] + c["user"] for c in agent.ai.of("write"))
        assert "WorldBuilder输出" not in blob, "注入了空的场景段（会污染提示词）"

    # ---- 工具与记忆 ----

    def test_consistency_tool_called_every_round(self, make_agent):
        """每轮审校后都跑一次一致性检查 —— 它是「改完有没有改坏」的唯一自动判据。"""
        agent = make_agent(ai=ScriptedAI(reviewer=lambda i: _review_json(30) if i == 0 else _review_json(95)))
        from unittest.mock import MagicMock

        real_call = agent.tools.call
        agent.tools.call = MagicMock(side_effect=lambda name, **kw: real_call(name, **kw))
        self._run(agent)

        called = [c.args[0] if c.args else None for c in agent.tools.call.call_args_list]
        assert called.count("check_consistency") == 2, f"实际调用：{called}"

    def test_revision_memory_records_each_failed_round(self, make_agent):
        """修订记忆是「这一章为什么改了三次」的唯一记录，面板要用它。"""
        agent = make_agent(
            ai=ScriptedAI(
                reviewer=lambda i: (
                    _review_json(40, issues=["节奏拖沓"], suggestions=["压缩"]) if i == 0 else _review_json(95)
                )
            )
        )
        self._run(agent)

        assert len(agent._revision_memory) == 1
        entry = agent._revision_memory[0]
        assert entry["chapter"] == 1
        assert entry["round"] == 1
        assert entry["issues"] == ["节奏拖沓"]
        assert entry["suggestions"] == ["压缩"]

    def test_passing_first_round_leaves_no_revision_memory(self, make_agent):
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        self._run(agent)

        assert agent._revision_memory == []

    # ---- 对话日志 ----

    def test_conversation_log_follows_stage_order(self, make_agent):
        """面板上的「协作过程」按这个顺序展示，顺序错会让过程看起来不合逻辑。"""
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        self._run(agent)

        first_seen: list[str] = []
        for msg in agent._conversation_log:
            role = getattr(msg.role, "name", str(msg.role))
            if role not in first_seen:
                first_seen.append(role)
        assert first_seen == ["PLOT", "WORLD", "WRITER", "REVIEWER", "EDITOR"], first_seen

    def test_log_callback_receives_stage_markers(self, make_agent):
        """日志里必须能看到每个阶段，否则「卡在哪一步」只能靠猜。"""
        lines: list[str] = []
        agent = make_agent(ai=ScriptedAI(reviewer=_review_json(95)))
        agent.log = lines.append
        self._run(agent)

        joined = "\n".join(lines)
        for marker in ("PlotDesigner", "WorldBuilder", "Writer", "Reviewer", "Editor", "5Agent协作完成"):
            assert marker in joined, f"日志缺少阶段标记：{marker}"
