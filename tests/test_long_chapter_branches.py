"""`GenerateLongChapter` 的分支回归。

## 为什么这个模块值得写细

它负责把"一次写 6000 字"拆成多段，而用户的差评集中在**烂尾**：
末段被 max_tokens 截断、或者草草收场。代码里有三道闸门与一套**保守的**补全策略，
但此前 19 行关键分支一次都没跑过（77.1%）：

| 分支 | 未覆盖的后果 |
|---|---|
| 规划检测 raise → 重试 | 工作笔记被当正文写进书里 |
| 认证错误不重试 | 白烧三次配额 |
| 末段补全（D18 全套） | 要么把好结尾改坏，要么断句没接上 |
| 标题已带「第X章」 | 章节标题变成「第5章：第5章 初入山门」 |

## D18 的设计意图（判据要保护它）

补全只允许在"**看似断在半句**"时触发，且：
- 已有句末标点 ⇒ **不碰**（`pass`）
- 拿不准 ⇒ **不动**（宁可少做）
- 与原文重叠 / 超过 60 字 ⇒ **丢弃**

误判的代价不对称：漏判只让结尾略突兀，误判会**主动把完整的结尾改坏**。
"""

from __future__ import annotations

import pytest

from app.application.long_chapter import GenerateLongChapter


class FakeMemory:
    def __init__(self, protagonist: str = ""):
        self._protagonist = protagonist

    def get_meta(self, key: str, default=""):
        if key == "protagonist":
            return self._protagonist
        return default


class ScriptedAI:
    """按顺序返回预置响应；`exc` 优先（用于异常用例）。"""

    def __init__(self, *replies, exc: Exception | None = None):
        self._replies = list(replies)
        self._exc = exc
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self._exc is not None:
            raise self._exc
        index = min(len(self.calls) - 1, len(self._replies) - 1)
        return self._replies[index]


def body(n: int = 600, head: str = "正文") -> str:
    """造一段足够长（>100 字）且以句号收尾的正文。"""
    return head + "他走过山谷，风声在耳边掠过。" * (n // 14)


@pytest.fixture
def run():
    def _run(
        ai, *, chapter_num=5, title="初入山门", outline="林风拜入青云宗", word_count=2000, context="", prev_ending=""
    ):
        agent = GenerateLongChapter(ai, FakeMemory(), log=lambda _m: None)
        return agent.execute(chapter_num, title, outline, word_count, context, prev_ending)

    return _run


class TestTitleHandling:
    def test_title_without_chapter_prefix_gets_one(self, run):
        result = run(ScriptedAI(body()))

        assert result.startswith("# 第5章：初入山门")

    @pytest.mark.parametrize("title", ["第5章 初入山门", "第五章", "第12章：拜师"])
    def test_title_already_numbered_is_not_doubled(self, run, title):
        """标题已带章号时不能拼成「第5章：第5章 …」。"""
        result = run(ScriptedAI(body()), title=title)

        first_line = result.splitlines()[0]
        assert first_line == "# 第5章", f"标题重复了：{first_line}"

    def test_empty_title_still_produces_heading(self, run):
        result = run(ScriptedAI(body()), title="")

        assert result.startswith("# 第5章：")

    def test_ai_generated_heading_is_stripped(self, run):
        """模型常自作主张加 `# 第5章` 或 `第5章 …` 开头，会和外层标题重复。"""
        reply = "# 第5章 初入山门\n\n" + body()

        result = run(ScriptedAI(reply))
        content = result.split("\n\n", 1)[1]

        assert not content.startswith("#"), "AI 加的标题没被去掉"

    def test_body_without_heading_is_kept(self, run):
        reply = body()
        result = run(ScriptedAI(reply))

        assert body() in result


class TestSegmentCount:
    @pytest.mark.parametrize(
        ("word_count", "expected"), [(1000, 1), (2000, 1), (2001, 2), (6000, 3), (16000, 8), (40000, 8)]
    )
    def test_segment_count_follows_word_count_and_is_capped(self, run, word_count, expected):
        """每段 2000 字，**最多 8 段** —— 再多就不是"长章"而是另一本书了。"""
        ai = ScriptedAI(body())
        run(ai, word_count=word_count)

        assert len(ai.calls) == expected


class TestPreviousEnding:
    def test_explicit_prev_ending_reaches_first_segment_prompt(self, run):
        ai = ScriptedAI(body())
        run(ai, prev_ending="他推开门，看见满屋的血。")

        first_prompt = ai.calls[0]["messages"][0]["content"]
        assert "他推开门，看见满屋的血。" in first_prompt
        assert "必须紧接前文" in first_prompt

    def test_prev_ending_extracted_from_context(self, run):
        """未显式传入时，从 `context` 里抠出「前一章结尾」。"""
        context = "【前一章·第4章结尾】\n他推开门，看见满屋的血。\n---\n【其他上下文】"
        ai = ScriptedAI(body())
        run(ai, context=context)

        first_prompt = ai.calls[0]["messages"][0]["content"]
        assert "他推开门，看见满屋的血。" in first_prompt

    def test_no_prev_ending_uses_plain_prompt(self, run):
        ai = ScriptedAI(body())
        run(ai, context="普通的上下文，没有前一章标记")

        first_prompt = ai.calls[0]["messages"][0]["content"]
        assert "必须紧接前文" not in first_prompt

    def test_only_first_segment_carries_prev_ending(self, run):
        """后续段接的是**上一段**的结尾，不该再塞前一章结尾。"""
        ai = ScriptedAI(body())
        run(ai, word_count=4000, prev_ending="他推开门，看见满屋的血。")

        second_prompt = ai.calls[1]["messages"][0]["content"]
        assert "他推开门，看见满屋的血。" not in second_prompt
        assert "继续写" in second_prompt or "紧接上文" in second_prompt


class TestTailPrompt:
    """末段提示词必须要求"实质推进 + 章节落点" —— D15 的修复点。"""

    def test_last_segment_demands_plot_advance(self, run):
        ai = ScriptedAI(body())
        run(ai, word_count=4000)

        last_prompt = ai.calls[-1]["messages"][0]["content"]
        assert "推进实质剧情" in last_prompt
        assert "章节落点" in last_prompt
        assert "不要总结全章" in last_prompt

    def test_middle_segment_is_plain_continuation(self, run):
        ai = ScriptedAI(body())
        run(ai, word_count=6000)

        middle_prompt = ai.calls[1]["messages"][0]["content"]
        assert "推进实质剧情" not in middle_prompt
        assert "紧接上文" in middle_prompt


class TestGatesAndRetries:
    def test_planning_text_triggers_retry(self, run):
        """🔴 规划文字（"用户希望我…"）绝不能落盘 —— 命中即重试。"""
        planning = "用户希望我继续写这个故事。让我回顾一下上下文：" + "分析" * 100
        ai = ScriptedAI(planning, body())

        result = run(ai)

        assert len(ai.calls) == 2, "规划文字没有触发重试"
        assert "用户希望我" not in result

    def test_three_planning_replies_yield_failure_marker(self, run):
        """三次都返回规划文字 ⇒ 明确报「生成失败」，而不是把笔记当正文。"""
        planning = "用户希望我继续写这个故事。让我回顾一下上下文：" + "分析" * 100
        result = run(ScriptedAI(planning))

        assert "（生成失败）" in result
        assert "用户希望我" not in result

    def test_short_response_triggers_retry(self, run):
        ai = ScriptedAI("太短了", body())
        result = run(ai)

        assert len(ai.calls) == 2
        assert len(result) > 200

    @pytest.mark.parametrize("message", ["401 Unauthorized", "Authorization failed", "API Key 无效"])
    def test_auth_error_is_not_retried(self, run, message):
        ai = ScriptedAI(exc=RuntimeError(message))

        with pytest.raises(RuntimeError):
            run(ai)

        assert len(ai.calls) == 1, f"认证错误被重试了 {len(ai.calls)} 次"

    def test_transient_error_retried_then_partial_result(self, run):
        """中间段连续失败时保留已生成段落 —— 不能因为一段失败丢掉整章。"""
        ai = ScriptedAI(exc=RuntimeError("连接超时"))

        result = run(ai, word_count=2000)

        assert "（生成失败）" in result
        assert len(ai.calls) == 3

    def test_body_generation_never_allows_reasoning_fallback(self, run):
        """正文的 reasoning 兜底会把工作笔记写进书里 —— 必须显式关闭。"""
        ai = ScriptedAI(body())
        run(ai)

        for call in ai.calls:
            assert call["kwargs"]["thinking_enabled"] is False
            assert call["kwargs"]["allow_reasoning_fallback"] is False

    def test_protagonist_lock_reaches_system_prompt(self, run):
        ai = ScriptedAI(body())
        agent = GenerateLongChapter(ai, FakeMemory(protagonist="林风"), log=lambda _m: None)
        agent.execute(1, "标题", "大纲", 2000, "")

        assert "林风" in ai.calls[0]["kwargs"]["system"]


class TestTailCompletion:
    """D18：末段补全的**保守**策略。

    误判代价不对称 —— 漏判只让结尾略突兀，误判会把完整的结尾**主动改坏**。
    所以这里的判据大多是"**不该发生什么**"。
    """

    def test_punctuated_ending_is_not_touched(self, run):
        """以句末标点收尾 ⇒ 一次补全请求都不该发。"""
        ending = body() + "他转身离去。"
        ai = ScriptedAI(ending)
        result = run(ai)

        assert len(ai.calls) == 1, "完整结尾却发起了补全"
        assert result.rstrip().endswith("他转身离去。")

    def test_quoted_ending_is_not_touched(self, run):
        """以引号收尾的对话是**完整**的（D18 的原始事故之一）。"""
        ending = body() + '「你终于来了。」"'
        ai = ScriptedAI(ending)
        result = run(ai)

        assert len(ai.calls) == 1, "引号收尾被误判为不完整"
        assert result.rstrip().endswith('"'), "结尾被改动了"

    def test_semicolon_ending_is_treated_as_complete(self, run):
        """分号收尾**不能**触发补全。

        这一条专门保护 `sentence_end` 那支判据：`looks_truncated` 把
        `，、；：,;:` 一律当成"还在句中"（对**章节末尾**来说这个判断是错的）——
        没有这层前置判断，一个以分号收束的排比句会被补上多余的话。
        句号/叹号/问号本来就由 `looks_truncated` 兜住，分号才会漏。
        """
        for ending in ("他转身离去；", "他转身离去;", "他转身离去！", "他转身离去？"):
            ai = ScriptedAI(body() + ending)
            result = run(ai)

            assert len(ai.calls) == 1, f"以「{ending[-1]}」收尾却发起了补全"
            assert result.rstrip().endswith(ending[-1])

    def test_truncated_ending_gets_short_completion(self, run):
        """断在逗号上 ⇒ 补一个短语接上。"""
        truncated = body() + "他推开门，"
        ai = ScriptedAI(truncated, "看见满屋的血。")
        result = run(ai)

        assert len(ai.calls) == 2, "断句没有被补全"
        assert result.endswith("看见满屋的血。")

    def test_completion_duplicating_original_is_discarded(self, run):
        truncated = body() + "他推开门，"
        ai = ScriptedAI(truncated, truncated[-40:])  # 与原文重叠
        result = run(ai)

        assert result.count(truncated[-40:]) == 1, "重复内容被追加了"

    def test_overlong_completion_is_discarded(self, run):
        """补全只允许 10–30 字的短语；补出一整段就变成"第二结尾"。"""
        truncated = body() + "他推开门，"
        ai = ScriptedAI(truncated, "新的情节" * 40)
        result = run(ai)

        assert len(result) < len(truncated) + 100, "超长补全被追加了"

    def test_empty_completion_leaves_result_unchanged(self, run):
        truncated = body() + "他推开门，"
        ai = ScriptedAI(truncated, "")
        result = run(ai)

        assert result.rstrip().endswith("他推开门，")

    def test_completion_error_is_swallowed(self, run):
        """补全本身失败只记日志 —— 正文已经生成好了，不能因为补全崩掉。"""
        truncated = body() + "他推开门，"

        class BoomAI:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return truncated
                raise RuntimeError("补全调用失败")

        ai = BoomAI()
        agent = GenerateLongChapter(ai, FakeMemory(), log=lambda _m: None)
        result = agent.execute(1, "标题", "大纲", 2000, "")

        assert "他推开门，" in result

    def test_undeterminable_ending_is_left_alone(self, run):
        """以普通汉字收尾 ⇒ 判不出来 ⇒ **不动**（宁可少做）。"""
        ending = body() + "他就这样站在门前"
        ai = ScriptedAI(ending)
        result = run(ai)

        assert len(ai.calls) == 1, "判不出是否断句却发起了补全"
        assert result.rstrip().endswith("他就这样站在门前")

    def test_short_result_skips_completion(self, run):
        """总长不足 500 字时不进补全流程 —— 短文本的"结尾"本来就没意义。"""
        short = "很短的一段。" * 20  # 140 字
        ai = ScriptedAI(short)
        result = run(ai, word_count=1000)

        assert len(ai.calls) == 1
        assert result.rstrip().endswith("。")
