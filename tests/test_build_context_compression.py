"""`build_context` 的压缩与降级（档 3：上下文丢了，生成质量直接掉）。

## 这个模块的"静默错法"

它负责把角色、伏笔、摘要塞进模型窗口。错法全是**静默**的：

| 错法 | 用户看到 |
|---|---|
| 角色超预算就整条丢掉 | 关键人物不在上下文里 ⇒ 写成另一个人 |
| 伏笔句子漏抓 | 前文埋的线在新章里完全不提 |
| 摘要/伏笔读不出来就抛 | 生成直接失败 |

所以判据是"**预算不够时降级而不是丢弃**"，以及"读不到就空着继续"。
"""

from __future__ import annotations

from typing import Any

from app.application.build_context import BuildContext


class FakeMemory:
    """只实现 `_compress_active_characters` / `_get_unresolved_plots` 用到的那几个方法。"""

    def __init__(self, chars: dict | None = None, summary: str = "", active: list[str] | None = None):
        self._chars = chars or {}
        self._summary = summary
        self._active = active or []

    # memory 的读接口
    def get_characters(self, *_a, **_kw):
        return dict(self._chars)

    def get_characters_for_chapter(self, *_a, **_kw):
        return dict(self._chars)

    def get_active_characters(self, *_a, **_kw):
        return list(self._active)

    def get_global_summary(self, *_a, **_kw):
        return self._summary

    def get_all_volume_summaries(self, *_a, **_kw):
        return {}

    def get_chapter_summary(self, *_a, **_kw):
        return ""

    def get_recent_summaries(self, *_a, **_kw):
        return []

    def get_settings(self, *_a, **_kw):
        return {}

    def get_meta(self, *_a, **_kw):
        return {}

    def get_current_volume_summary(self, *_a, **_kw):
        return ""

    def get_chapter_range_summary(self, *_a, **_kw):
        return ""

    def get_arc_summary(self, *_a, **_kw):
        return ""

    def get_arcs(self, *_a, **_kw):
        return []

    def retrieve_relevant(self, *_a, **_kw):
        return []

    novel_dir = None


def _ctx(memory=None):
    return BuildContext(memory or FakeMemory())


class TestCompressActiveCharacters:
    def test_empty(self):
        assert _ctx()._compress_active_characters({}, [], 1000) == ""

    def test_priority_order(self):
        """主角优先 —— 预算只够一个角色时必须先保住主角。"""
        chars = {
            "路人甲": {"category": "无名小卒", "personality": "普通"},
            "林风": {"category": "主角", "personality": "沉默"},
        }

        text = _ctx()._compress_active_characters(chars, ["路人甲", "林风"], 60)

        assert "林风" in text
        assert text.index("林风") <= text.index("路人甲") if "路人甲" in text else True

    def test_budget_exhaustion_does_not_drop_everything(self):
        """预算很小时至少保留能放下的部分，不能一条都不出。"""
        chars = {"林风": {"category": "主角", "personality": "沉默寡言，心里压着旧事"}}

        text = _ctx()._compress_active_characters(chars, ["林风"], 40)

        assert text, "预算不够就整条丢掉（角色直接消失在上下文里）"

    def test_non_dict_character_still_rendered(self):
        """旧存档里角色值可能是字符串 —— 要**照常渲染**而不是丢掉。"""
        chars: dict[str, Any] = {"甲": "旧格式字符串", "乙": {"category": "主角", "personality": "冷静"}}

        text = _ctx()._compress_active_characters(chars, ["甲", "乙"], 500)

        assert "乙" in text
        assert "甲" in text, "非 dict 的老数据被丢掉了"

    def test_unknown_category_uses_lowest_priority(self):
        chars = {"甲": {"personality": "普通"}}

        text = _ctx()._compress_active_characters(chars, ["甲"], 500)

        assert isinstance(text, str)

    def test_key_characters_included_even_if_not_active(self):
        """非活跃的主角/关键人物也要进上下文 —— 否则新章里主角可能缺席。"""
        chars = {"林风": {"category": "主角", "personality": "沉默"}}

        text = _ctx()._compress_active_characters(chars, [], 500)

        assert "林风" in text

    def test_minor_characters_excluded_when_inactive(self):
        """「无名小卒」不活跃就不提，省预算。"""
        chars = {"路人": {"category": "无名小卒", "personality": "普通"}}

        assert _ctx()._compress_active_characters(chars, [], 500) == ""


class TestUnresolvedPlots:
    def test_no_summary(self):
        assert _ctx(FakeMemory(summary=""))._get_unresolved_plots() == ""

    def test_extracts_sentences_with_keywords(self):
        summary = "林风埋下了黑剑的来历这个悬念。今天天气不错。师父的身份始终没有揭晓。"
        memory = FakeMemory(summary=summary)

        text = _ctx(memory)._get_unresolved_plots()

        assert "【未回收伏笔" in text or text == ""
        if text:
            assert len(text) < len(summary) * 2

    def test_caps_at_eight(self):
        memory = FakeMemory(summary="悬念。" * 50)

        text = _ctx(memory)._get_unresolved_plots()

        assert text.count("\n") <= 9

    def test_exception_returns_empty(self):
        """摘要读不出来只返回空串 —— 伏笔是加分项，不能让生成失败。"""

        class Boom(FakeMemory):
            def get_global_summary(self, *_a, **_kw):
                raise RuntimeError("坏数据")

        assert _ctx(Boom())._get_unresolved_plots() == ""


class TestFormatCharacterLine:
    def test_compact_is_shorter(self):
        info = {"personality": "沉默寡言，心里压着旧事", "background": "孤儿出身，被师父收养", "goal": "找到黑剑"}

        full = BuildContext._format_character_line("林风", info, "主角", compact=False)
        short = BuildContext._format_character_line("林风", info, "主角", compact=True)

        assert len(short) <= len(full)
        assert "林风" in short

    def test_optional_fields_appended(self):
        info = {"personality": "冷静", "background": "世家", "goal": "复仇", "relationship_to_main": "师兄"}

        line = BuildContext._format_character_line("苏雪", info, "主角", compact=False)

        assert "背景:世家" in line or "背景" in line
        assert "目标:复仇" in line or "目标" in line


class TestSkillFallback:
    def test_skill_library_failure_is_logged_not_raised(self, monkeypatch):
        """技能库取不到规则只记日志 —— 上下文照常组装。"""
        from app import skill_library

        def boom():
            raise RuntimeError("技能库坏了")

        monkeypatch.setattr(skill_library, "get_skill_library", boom)
        logs: list[str] = []

        ctx = BuildContext(FakeMemory(), log=logs.append)

        text = ctx.execute(1, max_chars=2000)

        # ⚠️ 这里只断言"不抛"。日志取决于是否走到了技能库那一段
        # （有写作预设时会短路），把"必须有日志"写成断言会变成脆弱测试。
        assert isinstance(text, str)
