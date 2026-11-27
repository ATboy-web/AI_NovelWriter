"""`UpdateCharacterProgression` 的分支回归。

## 为什么这个模块值得单独写用例

它是**唯一会自动修改角色属性**的路径，而失败方式极其隐蔽：

- 把"死亡"记成"重伤"—— 世界线就不自洽了，但**不会报错**
- 解析失败 → 直接 `跳过本章` —— 角色永远不成长，也不会报错
- 事件写进 `add_event` 但类型写错（如 `character_growth` vs `character_death`）——
  面板按类型过滤，于是"这一章死了三个人"在时间线上完全看不见

所以判据必须细到**事件类型**与**写回字段**，不能只看"有没有调用"。

## 覆盖的 8 类变化

`updates` / `skills_learned` / `relationship_changes` / `items_gained` /
`items_lost` / `new_allies` / `new_enemies` / `deaths` ——
每类一条，缺一条就意味着那类变化在真实章节里会被静默丢掉。
"""

from __future__ import annotations

import json

import pytest

from app.application import character_progression as mod
from app.application.character_progression import UpdateCharacterProgression


class FakeMemory:
    """记录事件与角色写回的记忆替身。"""

    def __init__(self, characters=None, *, fail_event_with: Exception | None = None):
        self._chars = characters if characters is not None else {"林风": {"personality": "沉默"}}
        self.events: list[tuple[int, str, str]] = []
        self.character_updates: list[tuple[str, dict]] = []
        self._fail = fail_event_with

    def get_characters(self) -> dict:
        return self._chars

    def add_event(self, chapter: int, text: str, kind: str) -> None:
        if self._fail is not None:
            raise self._fail
        self.events.append((chapter, text, kind))

    def update_character(self, name: str, fields: dict) -> None:
        self.character_updates.append((name, fields))


class FakeAI:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.reply


def run(reply, *, memory=None, content="林风在山谷中突破，斩杀了宿敌。", summary="突破与激战"):
    memory = memory or FakeMemory()
    ai = FakeAI(reply)
    agent = UpdateCharacterProgression(ai, memory, log=lambda _m: None)
    agent.execute(7, content, summary)
    return ai, memory


def payload(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


class TestPreconditions:
    def test_no_characters_skips_ai_call(self):
        """角色表为空时不发请求 —— 这一章没人可长，发了也是白花一次往返。"""
        ai, memory = run(payload(updates=[]), memory=FakeMemory(characters={}))

        assert ai.calls == []
        assert memory.events == []

    def test_empty_response_writes_nothing(self):
        _ai, memory = run("")
        assert memory.events == []

    def test_thinking_is_disabled(self):
        """成长检测是结构化抽取，不需要思考；开着会吃掉 output 预算。"""
        ai, _memory = run(payload(updates=[]))
        assert ai.calls[0]["kwargs"]["thinking_enabled"] is False


class TestContentSampling:
    def test_long_content_is_sampled_not_truncated(self):
        """超长章节取「开头 + 中间 + 结尾」——只取开头会漏掉章末的死亡/转折。"""
        # 采样取的是**正文真中点** ±500，所以中间标记要放在正中
        content = "开头标记" + "甲" * 3500 + "中间标记" + "乙" * 3500 + "结尾标记"
        ai, _memory = run(payload(updates=[]), content=content)

        prompt = ai.calls[0]["messages"][0]["content"]
        assert "开头标记" in prompt
        assert "中间标记" in prompt, "中间被丢了 —— 中段发生的成长会漏检"
        assert "结尾标记" in prompt
        assert "中间省略" in prompt

    def test_short_content_is_sent_whole(self):
        content = "短内容：林风变强了。"
        ai, _memory = run(payload(updates=[]), content=content)

        prompt = ai.calls[0]["messages"][0]["content"]
        assert content in prompt
        assert "中间省略" not in prompt


class TestEightChangeKinds:
    """八类变化各一条 —— 每类都必须落到 `add_event` 且类型正确。

    ❗ 类型（`character_growth` / `character_death` / …）是面板与时间线的过滤键，
    写错就等于"这件事没发生过"。
    """

    def test_updates(self):
        _ai, memory = run(payload(updates=[{"name": "林风", "change": "突破炼气", "reason": "苦修"}]))

        assert len(memory.events) == 1
        chapter, text, kind = memory.events[0]
        assert chapter == 7
        assert kind == "character_growth"
        assert "林风" in text and "突破炼气" in text and "苦修" in text

    def test_skills_learned(self):
        _ai, memory = run(payload(skills_learned=[{"name": "林风", "skill": "御风步"}]))

        assert memory.events[0][2] == "skill_learn"
        assert "御风步" in memory.events[0][1]

    def test_relationship_changes(self):
        _ai, memory = run(
            payload(relationship_changes=[{"name1": "林风", "name2": "苏晚", "old": "陌生", "new": "盟友"}])
        )

        assert memory.events[0][2] == "relationship_change"
        assert "林风" in memory.events[0][1] and "盟友" in memory.events[0][1]

    def test_items_gained(self):
        _ai, memory = run(payload(items_gained=[{"name": "林风", "item": "玄铁剑"}]))

        assert memory.events[0][2] == "item_gain"
        assert "玄铁剑" in memory.events[0][1]

    def test_items_lost(self):
        _ai, memory = run(payload(items_lost=[{"name": "林风", "item": "旧刀"}]))

        assert memory.events[0][2] == "item_loss"
        assert "旧刀" in memory.events[0][1]

    def test_new_allies(self):
        _ai, memory = run(payload(new_allies=["苏晚"]))

        assert memory.events[0][2] == "new_ally"
        assert "苏晚" in memory.events[0][1]

    def test_new_enemies(self):
        _ai, memory = run(payload(new_enemies=["黑袍人"]))

        assert memory.events[0][2] == "new_enemy"
        assert "黑袍人" in memory.events[0][1]


class TestDeathHandling:
    """🔴 死亡是全流程里**唯一会改角色状态**的分支，写错会毁世界线。"""

    def test_death_marks_status_and_chapter(self):
        _ai, memory = run(payload(deaths=["苏晚"]))

        assert memory.events[0][2] == "character_death"
        assert "苏晚" in memory.events[0][1]
        assert memory.character_updates == [("苏晚", {"status": "死亡", "death_chapter": 7})], (
            "死亡状态或章号写错了 —— 后续章节会把这个角色当活人写"
        )

    def test_multiple_deaths_all_recorded(self):
        _ai, memory = run(payload(deaths=["甲", "乙", "丙"]))

        assert [name for name, _f in memory.character_updates] == ["甲", "乙", "丙"]
        assert all(kind == "character_death" for _c, _t, kind in memory.events)

    def test_non_string_death_entries_are_skipped(self):
        """模型可能把 `deaths` 写成 `[{"name": "甲"}]` —— 不能把 dict 当名字写进档案。"""
        _ai, memory = run(payload(deaths=[{"name": "甲"}, "", "乙"]))

        assert [name for name, _f in memory.character_updates] == ["乙"]

    def test_blank_name_does_not_create_ghost_character(self):
        _ai, memory = run(payload(new_allies=["", "  "], new_enemies=[""]))

        assert memory.events == [], "空名字造出了幽灵角色"

    def test_whitespace_death_name_is_ignored(self):
        """纯空格写在 deaths 里时**不能**产生死亡记录 ——
        否则角色档案里会多出一条 status=死亡 的空白角色。"""
        _ai, memory = run(payload(deaths=["  ", "乙"]))

        assert [name for name, _f in memory.character_updates] == ["乙"]


class TestMalformedPayloads:
    def test_non_dict_entries_are_skipped(self):
        """`updates` 里混进字符串/数字时只跳过那一条，不整批丢。"""
        _ai, memory = run(payload(updates=["不是对象", 42, {"name": "林风", "change": "变强"}]))

        assert len(memory.events) == 1
        assert "林风" in memory.events[0][1]

    def test_entries_without_name_are_skipped(self):
        _ai, memory = run(payload(updates=[{"change": "无人认领的变化"}]))

        assert memory.events == []

    def test_parse_failure_logs_and_writes_nothing(self):
        """解析失败 = 跳过本章（不猜、不写半截数据）。"""
        logs: list[str] = []
        memory = FakeMemory()
        agent = UpdateCharacterProgression(FakeAI("完全不是 JSON 的一段分析文字"), memory, log=logs.append)

        agent.execute(7, "正文", "摘要")

        assert memory.events == []
        assert any("JSON解析失败" in line for line in logs)

    def test_parse_failure_emits_diagnostic_event(self, monkeypatch):
        got: dict = {}

        class Diag:
            def log(self, level, event, payload, **_kw):
                got.update({"level": level, "event": event, "payload": payload})

        monkeypatch.setattr(mod, "_diag_logger", lambda: Diag())
        run("不是 JSON")

        assert got["level"] == "WARN"
        assert got["event"] == "character_growth_parse_failed"
        assert got["payload"]["chapter"] == 7
        assert got["payload"]["response_len"] > 0

    def test_parse_failure_without_diagnostic_logger_is_silent(self, monkeypatch):
        """诊断器不可用时不能因此崩掉。

        真实的失败方式是 `get_logger()` 抛异常 —— `_diag_logger` 自己吞掉并返回
        `None`，调用方再走 `if diag:` 的假分支。所以这里从**底层**注入，
        而不是把 `_diag_logger` 换成会抛异常的函数（那测的是另一种契约）。
        """
        import app.diagnostic_logger as diag_mod

        def boom(*_a, **_kw):
            raise RuntimeError("诊断目录不可写")

        monkeypatch.setattr(diag_mod, "get_logger", boom)
        memory = FakeMemory()
        agent = UpdateCharacterProgression(FakeAI("不是 JSON"), memory, log=lambda _m: None)

        agent.execute(7, "正文", "摘要")  # 不抛即通过
        assert memory.events == []


class TestStrategy4Salvage:
    """Strategy 4：统一解析器失败时，用正则逐字段捞。

    这一层是 `parse_json_response` 覆盖不到的 —— 针对"大段思考文本里夹着
    一个**本身就不合法**的 `updates` 数组"的极端情况。
    """

    def test_field_extraction_recovers_updates(self, monkeypatch):
        # 强制让统一解析器失败，模拟"整体不合法但字段可捞"
        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)

        response = (
            "我先看看这一章发生了什么。\n"
            '{"updates": [{"name": "林风", "change": "觉醒血脉", "reason": "生死一线"}, '
            '{"name": "苏晚", "change": "受伤", "reason": "挡剑"}], "broken": \n'
        )
        _ai, memory = run(response)

        assert len(memory.events) == 2
        assert "觉醒血脉" in memory.events[0][1]
        assert "受伤" in memory.events[1][1]

    def test_field_extraction_tolerates_missing_optional_fields(self, monkeypatch):
        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)
        _ai, memory = run('{"updates": [{"name": "林风"}]')

        assert len(memory.events) == 1
        assert "林风" in memory.events[0][1]

    def test_no_salvage_when_no_updates_array(self, monkeypatch):
        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)
        _ai, memory = run("纯文字，没有任何字段可捞。")

        assert memory.events == []


class TestNeverBreaksTheChapter:
    def test_memory_error_is_swallowed(self):
        """记忆层报错时只能跳过本章 —— 绝不能让它把整章生成流程带崩。

        这条对应 `except (json.JSONDecodeError, KeyError, TypeError, ValueError)`：
        它在**写完正文之后**执行，抛出去就等于"稿子写好了但流程失败"。
        """
        memory = FakeMemory(fail_event_with=KeyError("characters.json 缺键"))
        agent = UpdateCharacterProgression(
            FakeAI(payload(updates=[{"name": "林风", "change": "变强"}])), memory, log=lambda _m: None
        )

        agent.execute(7, "正文", "摘要")  # 不抛即通过

    def test_return_value_is_none(self):
        """接口契约：这是"副作用型"用例，不返回任何东西。"""
        memory = FakeMemory()
        agent = UpdateCharacterProgression(FakeAI(payload(updates=[])), memory, log=lambda _m: None)

        assert agent.execute(7, "正文", "摘要") is None


class TestSummaryLog:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("updates", "1个成长"),
            ("skills_learned", "1个技能"),
            ("relationship_changes", "1个关系"),
            ("deaths", "1个死亡"),
            ("new_allies", "1个新盟友"),
            ("new_enemies", "1个新敌人"),
        ],
    )
    def test_summary_mentions_each_kind(self, field, expected):
        """一行摘要日志是"这一章角色到底动没动"的唯一人读凭据。"""
        values = {
            "updates": [{"name": "甲", "change": "x"}],
            "skills_learned": [{"name": "甲", "skill": "y"}],
            "relationship_changes": [{"name1": "甲", "name2": "乙"}],
            "deaths": ["甲"],
            "new_allies": ["乙"],
            "new_enemies": ["丙"],
        }
        logs: list[str] = []
        memory = FakeMemory()
        agent = UpdateCharacterProgression(FakeAI(payload(**{field: values[field]})), memory, log=logs.append)

        agent.execute(7, "正文", "摘要")

        assert any(expected in line for line in logs), f"摘要里没提到 {expected}：{logs}"


class TestCharacterListInPrompt:
    """提示词里要带上"当前有哪些角色"，否则模型会漏检或编造。"""

    def test_dict_info_renders_role_and_faction(self):
        memory = FakeMemory(characters={"林风": {"category": "主角", "faction": "主角阵营"}})
        ai, _mem = run(payload(updates=[]), memory=memory)

        assert "林风(主角/主角阵营)" in ai.calls[0]["kwargs"]["system"]

    def test_missing_role_and_faction_render_as_unknown(self):
        """字段缺失时写「未知」而不是崩在 KeyError —— 旧存档普遍没有这两个字段。"""
        ai, _memory = run(payload(updates=[]))

        assert "林风(未知/未知)" in ai.calls[0]["kwargs"]["system"]

    def test_non_dict_info_falls_back_to_name_only(self):
        """旧版存档里角色值可能是字符串 —— 仍要列进提示词，不能整条丢掉。"""
        memory = FakeMemory(characters={"林风": "旧格式的字符串信息"})
        ai, _mem = run(payload(updates=[]), memory=memory)

        assert "林风" in ai.calls[0]["kwargs"]["system"]

    def test_prompt_lists_at_most_twenty_characters(self):
        """角色表可能有 286 个 —— 全塞进提示词只挤掉真正要看的内容。"""
        many = {f"角色{i:02d}": {"category": "配角", "faction": "中立"} for i in range(40)}
        ai, _mem = run(payload(updates=[]), memory=FakeMemory(characters=many))
        system = ai.calls[0]["kwargs"]["system"]

        assert "角色00" in system
        assert "角色20" not in system, "超过了 20 人上限"


class TestStrategy4InternalFailure:
    def test_error_inside_salvage_is_swallowed(self, monkeypatch):
        """第 4 层内部的异常只能降级为 debug 日志 —— 它在写正文之后执行，
        抛出去等于"稿子写好了但流程失败"。"""

        class BrokenRe:
            def search(self, *a, **kw):
                raise RuntimeError("正则引擎异常")

            def finditer(self, *a, **kw):
                raise RuntimeError("正则引擎异常")

        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)
        monkeypatch.setattr(mod, "re", BrokenRe())

        memory = FakeMemory()
        agent = UpdateCharacterProgression(FakeAI('{"updates": [{"name": "林风"}]}'), memory, log=lambda _m: None)
        agent.execute(7, "正文", "摘要")  # 不抛即通过

        assert memory.events == []
