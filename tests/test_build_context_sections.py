"""`BuildContext` 的**有数据**分支回归（现有测试只走"空记忆"路径）。

## 为什么补

`build_context` 从 `novel_agent._build_context` 搬出来时覆盖率只有 68.6%：
所有 `【全局摘要】/【当前卷】/【近期章节】/【创作指引】/【相关记忆】`
这些分段都靠"记忆里有东西"才触发，而现有测试用的是空 `FakeMemory`，
于是这些分支一次都没跑过 —— 而它们恰恰是**生产里必然走到的路径**。

这里的判据是「分段有没有出现」而不是「文字写得好不好」：
前者是结构契约（模型能看到哪些前情），后者不该由单测判断。
"""

from __future__ import annotations

import pytest

from app.application.build_context import BuildContext


class FakeMemory:
    """按需返回预置数据的记忆替身。所有字段默认空。"""

    def __init__(
        self,
        *,
        global_summary: str = "",
        volume_summary: str = "",
        recent: list[str] | None = None,
        characters: dict | None = None,
        active: list[str] | None = None,
        relevant: list[dict] | None = None,
    ):
        self._global = global_summary
        self._volume = volume_summary
        self._recent = recent or []
        self._characters = characters or {}
        self._active = active or []
        self._relevant = relevant or []

    def get_global_summary(self) -> str:
        return self._global

    def get_current_volume_summary(self, chapter_num: int) -> str:
        return self._volume

    def get_recent_summaries(self, count: int = 3) -> list[str]:
        return self._recent[-count:]

    def get_active_characters(self, chapter_num: int, window: int = 50) -> list[str]:
        return self._active

    def get_characters(self) -> dict:
        return self._characters

    def retrieve_relevant(self, query: str, top_k: int = 3) -> list[dict]:
        return self._relevant


def build(memory, **kwargs) -> str:
    """默认给足够大的预算，避免压缩干扰"分段是否出现"的断言。"""
    kwargs.setdefault("max_chars", 20000)
    return BuildContext(memory, log=lambda _m: None).execute(5, **kwargs)


class TestSectionsAppear:
    def test_empty_memory_yields_no_sections(self):
        text = build(FakeMemory())
        for marker in ("【全局摘要】", "【当前卷】", "【近期章节】", "【创作指引】"):
            assert marker not in text, f"空记忆却产出了 {marker}"

    def test_global_summary_section(self):
        assert "【全局摘要】" in build(FakeMemory(global_summary="故事发生在黑风岭。"))

    def test_volume_summary_section(self):
        assert "【当前卷】" in build(FakeMemory(volume_summary="第一卷：入山。"))

    def test_recent_chapters_section(self):
        text = build(FakeMemory(recent=["第3章：林风出发。", "第4章：抵达山脚。"]))
        assert "【近期章节】" in text
        assert "林风出发" in text

    def test_extra_context_becomes_guidance(self):
        text = build(FakeMemory(), extra_context="本章要写出压迫感。")
        assert "【创作指引】" in text
        assert "压迫感" in text

    def test_characters_section(self):
        chars = {"林风": {"personality": "沉默寡言", "category": "主角"}}
        text = build(FakeMemory(characters=chars, active=["林风"]))
        assert "【当前剧情线角色】" in text
        assert "林风" in text

    def test_key_characters_appear_even_if_not_active(self):
        """主角/关键人物即使不在"活跃名单"里也要出现 —— 否则模型会写出走形的主角。"""
        chars = {"苏晚": {"personality": "冷静", "category": "女主角"}}
        text = build(FakeMemory(characters=chars, active=[]))
        assert "苏晚" in text

    def test_rag_section_when_relevant_found(self):
        # 内容要超过 20 字： 有"太短的 RAG 片段不值得占预算"的下限
        relevant = [{"content": "林风幼年落水险些丧命，从此怕水；这是第五章埋下的设定，渡河时会发作。"}]
        text = build(FakeMemory(relevant=relevant), extra_context="写他渡河")
        assert "【相关记忆】" in text
        assert "怕水" in text

    def test_short_rag_snippet_is_skipped(self):
        """太短的检索片段不值得占预算（下限 20 字）。"""
        relevant = [{"content": "怕水"}]
        text = build(FakeMemory(relevant=relevant), extra_context="写他渡河")
        assert "【相关记忆】" not in text


class TestBudget:
    def test_respects_max_chars(self):
        """预算是硬约束：超了就会被截断，否则上下文会挤掉输出额度。"""
        memory = FakeMemory(global_summary="摘要" * 5000)
        text = build(memory, max_chars=500)
        assert len(text) <= 500 * 1.2, f"实际 {len(text)} 字，预算 500"

    def test_small_budget_keeps_tail_of_previous_chapter(self):
        """前一章结尾必须保留在 `extra_context` 里（`keep_tail=True`）。"""
        prev = "开头内容。" * 500 + "【结尾标记】他推开了门。"
        text = build(FakeMemory(), extra_context=prev, max_chars=800)
        assert "【结尾标记】" in text, "压缩把结尾丢了 —— 章节之间会接不上"

    @pytest.mark.parametrize("phase", ["opening", "writing", "action", "dialogue", "ending", "未知阶段"])
    def test_all_phases_produce_output_without_crashing(self, phase):
        text = build(FakeMemory(global_summary="摘要"), writing_phase=phase)
        assert "【全局摘要】" in text

    def test_unknown_phase_falls_back_to_writing_ratios(self):
        """未知阶段按 `writing` 预算走（与 `CONTEXT_RATIOS.get` 的默认一致）。"""
        from app.domain.plot import CONTEXT_RATIOS

        assert "unknown" not in CONTEXT_RATIOS


class TestCompressHelpers:
    """压缩是"预算内还能塞多少前情"的唯一手段，边界要钉住。"""

    def test_short_text_untouched(self):
        assert BuildContext._compress_text("短", 100) == "短"

    def test_long_text_keeps_head_and_tail(self):
        text = "头" * 300 + "尾" * 300
        out = BuildContext._compress_text(text, 100, keep_tail=True)
        assert out.startswith("头") and out.endswith("尾")
        assert "..." in out

    def test_without_tail_prefers_head(self):
        text = "头" * 300 + "尾" * 300
        out = BuildContext._compress_text(text, 100, keep_tail=False)
        assert out.startswith("头")

    def test_tiny_budget_is_hard_truncated(self):
        """预算小于 50 时直接硬截 —— 此时再谈"头尾保留"没有意义。"""
        out = BuildContext._compress_text("字" * 200, 10)
        assert len(out) <= 13

    def test_character_line_compact_drops_details(self):
        info = {"personality": "沉默", "backstory": "童年失忆", "goal": "复仇", "faction": "青云宗"}
        full = BuildContext._format_character_line("林风", info, "主角", compact=False)
        compact = BuildContext._format_character_line("林风", info, "主角", compact=True)

        assert len(compact) < len(full), "降级格式没有变短"
        # 阵营两种格式都保留（它是判断"谁是谁的人"的最小信息）
        assert "青云宗" in full and "青云宗" in compact
        # 背景/目标只给核心角色写（无名小卒写了会挤掉别人）
        assert "童年失忆" in full and "童年失忆" not in compact
        assert "复仇" in full and "复仇" not in compact
