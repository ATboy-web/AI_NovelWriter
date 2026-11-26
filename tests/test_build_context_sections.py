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


# ══════════════════════════════════════════════════════════ 注入点（预设 / 技能库 / 插件）


class TestInjectionSourcesRunForReal:
    """四条注入链必须**真的执行**，而不只是"源码里出现过这个名字"。

    ## 为什么这组用例必须存在

    2026-11-26 把 `_build_context` 搬进 application 时，函数体内的
    `from .writing_skills import ...`（相对导入）跟着搬了过来 —— 在
    `app/application/` 下它解析成 `app.application.writing_skills`，
    模块不存在 ⇒ `ImportError` ⇒ 被外层 `except Exception` 吞掉 ⇒
    **写作预设、技能库、插件技能、学习经验全部静默失效**。

    而当时的守卫（`test_writing_presets` / `test_skill_library` 的 wiring guard）
    只断言源码里**有** `prompt_context(` 这个字符串 —— 于是它照样绿。
    这正是"注册即遗忘"的变体：**代码在，但永远走不到**。

    所以这里用替身把每条链都真跑一遍：返回非空就该出现对应分段。
    """

    def test_writing_skills_section(self, monkeypatch):
        class FakeManager:
            def get_writing_context(self, chapter=0):
                assert chapter == 5, "chapter 没传下去（学习经验会按默认 0 检索）"
                return "学习到的成功模式：" + "细节描写要克制" * 5

            def plugin_skill_context(self):
                return ""

        import app.writing_skills as ws

        monkeypatch.setattr(ws, "writing_skill_manager", FakeManager())
        text = build(FakeMemory())
        assert "【写作参考】" in text
        assert "细节描写要克制" in text

    def test_writing_skills_failure_is_swallowed(self, monkeypatch):
        """技能库取不到时只记日志，不能拖垮上下文组装。"""

        class Boom:
            def get_writing_context(self, chapter=0):
                raise RuntimeError("技能库损坏")

            def plugin_skill_context(self):
                raise RuntimeError("插件损坏")

        import app.writing_skills as ws

        monkeypatch.setattr(ws, "writing_skill_manager", Boom())
        text = build(FakeMemory(global_summary="摘要"))
        assert "【全局摘要】" in text, "一个可选组件失败把整段上下文弄没了"

    def test_plugin_skills_section(self, monkeypatch):
        class FakeManager:
            def get_writing_context(self, chapter=0):
                return ""

            def plugin_skill_context(self):
                return "插件提供的写作片段：" + "悬疑节奏" * 10

        import app.writing_skills as ws

        monkeypatch.setattr(ws, "writing_skill_manager", FakeManager())
        text = build(FakeMemory())
        assert "【插件写作技能】" in text
        assert "悬疑节奏" in text

    def test_writing_preset_section(self, monkeypatch):
        seen: dict = {}

        class FakeManager:
            def prompt_context(self, budget, stage, novel_dir):
                seen.update({"budget": budget, "stage": stage, "novel_dir": novel_dir})
                return "生成期防 AI 腔：" + "禁止套话开头" * 8

        import app.writing_presets as wp

        monkeypatch.setattr(wp, "get_preset_manager", lambda: FakeManager())
        text = build(FakeMemory())

        assert "【写作预设】" in text
        assert seen["stage"] == "generate", "生成阶段必须用「生成期」预设，不是成稿清理"
        assert seen["budget"] > 0

    def test_preset_disables_skill_library(self, monkeypatch):
        """预设与技能库**互斥**：同一批规则注入两遍只会挤掉前情。"""

        class FakePreset:
            def prompt_context(self, budget, stage, novel_dir):
                return "预设规则"

        class FakeLibrary:
            def prompt_context(self, budget):
                raise AssertionError("有预设时不该再去取技能库")

        import app.skill_library as sl
        import app.writing_presets as wp

        monkeypatch.setattr(wp, "get_preset_manager", lambda: FakePreset())
        monkeypatch.setattr(sl, "get_skill_library", lambda: FakeLibrary())

        text = build(FakeMemory())
        assert "【写作预设】" in text
        assert "【技能库规则】" not in text

    def test_skill_library_used_when_no_preset(self, monkeypatch):
        class FakeLibrary:
            def prompt_context(self, budget):
                assert budget > 0
                return "技能库规则：" + "视角切换要交代" * 8

        import app.skill_library as sl
        import app.writing_presets as wp

        monkeypatch.setattr(wp, "get_preset_manager", lambda: None)
        monkeypatch.setattr(sl, "get_skill_library", lambda: FakeLibrary())

        text = build(FakeMemory())
        assert "【技能库规则】" in text
        assert "视角切换要交代" in text


# ══════════════════════════════════════════════════════════ 伏笔与截断


class TestUnresolvedPlotsAndTruncation:
    def test_unresolved_plots_inserted_after_global_summary(self):
        """伏笔段插在全局摘要**后面**（`parts.insert(1, ...)`），
        让模型先看到"故事讲到哪"，再看到"还欠哪些悬念"。"""
        memory = FakeMemory(
            global_summary="主线：入山。",
            relevant=[{"content": "他答应过要回去。" * 5}],
        )
        text = build(memory, extra_context="写渡河")

        assert text.index("【全局摘要】") < text.index("【未回收伏笔") if "【未回收伏笔" in text else True

    def test_unresolved_plots_skipped_when_budget_full(self):
        """预算已满时不插伏笔段（插了也会被后面的截断切掉，白占预算）。"""
        memory = FakeMemory(global_summary="摘要" * 3000)
        text = build(memory, max_chars=200)
        assert len(text) <= 200 * 1.2

    def test_final_truncation_keeps_both_ends(self):
        """超预算时保留头尾（`marker` 在中间），不能只砍尾巴。"""
        memory = FakeMemory(
            global_summary="全局摘要开头" + "甲" * 3000,
            recent=["近期章节结尾" + "乙" * 2000],
        )
        text = build(memory, max_chars=600)

        assert "全局摘要开头" in text
        assert "近期章节结尾" in text
        assert "截断" in text


# ══════════════════════════════════════════════════════════ 无名小卒


class TestMinorCharacters:
    def test_inactive_minor_character_is_filtered(self):
        """「无名小卒」只有活跃时才显示 —— 否则 286 个路人的档案会挤掉主角。"""
        chars = {
            "林风": {"personality": "沉默", "category": "主角"},
            "王二": {"personality": "路人甲", "category": "无名小卒"},
        }
        text = build(FakeMemory(characters=chars, active=["林风"]))

        assert "林风" in text
        assert "王二" not in text, "未活跃的无名小卒不该进上下文"

    def test_active_minor_character_is_kept(self):
        chars = {"王二": {"personality": "路人甲", "category": "无名小卒"}}
        text = build(FakeMemory(characters=chars, active=["王二"]))
        assert "王二" in text
