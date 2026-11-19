"""空壳角色补全器的契约。

## 背景

`_auto_detect_characters` 只落骨架（`category`/`faction`/`first_appearance`），
不写 background/personality —— 而后续章节的上下文注入读的正是这些字段。
实测《配种的强大之处》里苏清寒出场 65 次却无人设。

补全器本身是纯逻辑（构造 prompt + 解析响应），落盘由调用方负责，
所以这里只测"该补谁 / prompt 长什么样 / 解析得对不对 / 会不会误伤"。
"""

from __future__ import annotations

from app.character_enrichment import (
    EMPTY_FIELDS,
    build_enrich_prompt,
    is_empty_character,
    parse_enrichment,
)
from app.parsing import parse_json_response


class TestIsEmptyCharacter:
    def test_skeleton_is_empty(self):
        """自动创建的角色就是这种骨架。"""
        assert is_empty_character({"category": "无名小卒", "faction": "中立", "auto_created": True}) is True

    def test_with_backstory_is_not_empty(self):
        assert is_empty_character({"backstory": "某个来历"}) is False

    def test_with_background_is_not_empty(self):
        """memory 层用 `background`，只看 `backstory` 会误判为空。"""
        assert is_empty_character({"background": "某个来历"}) is False

    def test_whitespace_only_counts_as_empty(self):
        assert is_empty_character({"backstory": "   ", "personality": "\n"}) is True

    def test_non_dict_is_not_empty(self):
        """脏数据不该被当成"需要补全"然后被覆盖。"""
        assert is_empty_character(None) is False
        assert is_empty_character("张三") is False

    def test_empty_fields_cover_both_key_names(self):
        assert "backstory" in EMPTY_FIELDS and "background" in EMPTY_FIELDS


class TestBuildPrompt:
    def test_names_are_listed(self):
        system, prompt = build_enrich_prompt(["苏清寒", "何婆子"], "")
        assert "苏清寒" in system and "何婆子" in system
        assert "苏清寒" in prompt

    def test_context_is_carried(self):
        system, prompt = build_enrich_prompt(["甲"], "书名：《某书》\n已有人物：乙、丙")
        assert "某书" in prompt
        assert "已有人物" in prompt

    def test_requires_json_only(self):
        system, _ = build_enrich_prompt(["甲"])
        assert "只输出 JSON" in system or "只输出JSON" in system
        assert "backstory" in system and "personality" in system


class TestParseEnrichment:
    RESPONSE = """```json
{"苏清寒": {"backstory": "灵药宗三师姐，管药庐。", "personality": "话少，声音淡。",
 "appearance": "冷眉", "goal": "守住药庐", "relationship_to_main": "同门师姐",
 "skill_suggestions": ["辨药", "缝合"]}}
```"""

    def test_parses_all_fields(self):
        result = parse_enrichment(self.RESPONSE, ["苏清寒"], parse_json_response)
        assert "苏清寒" in result
        assert result["苏清寒"]["backstory"].startswith("灵药宗三师姐")
        assert result["苏清寒"]["skill_suggestions"] == ["辨药", "缝合"]

    def test_ignores_unrequested_names(self):
        """模型偶尔会顺手多写几个，那些不该落盘。"""
        response = '{"苏清寒": {"backstory": "甲"}, "路人甲": {"backstory": "乙"}}'
        result = parse_enrichment(response, ["苏清寒"], parse_json_response)
        assert "路人甲" not in result

    def test_ignores_unknown_fields(self):
        response = '{"甲": {"backstory": "x", "死亡章节": 3, "hp": 999}}'
        result = parse_enrichment(response, ["甲"], parse_json_response)
        assert set(result["甲"]) == {"backstory"}

    def test_rejects_blank_values(self):
        response = '{"甲": {"backstory": "   ", "personality": ""}}'
        assert parse_enrichment(response, ["甲"], parse_json_response) == {}

    def test_requires_backstory_or_personality(self):
        """只有 goal 不算补到东西 —— 至少要有一句人设，否则不如不写。"""
        response = '{"甲": {"goal": "变强"}}'
        assert parse_enrichment(response, ["甲"], parse_json_response) == {}

    def test_garbage_returns_empty_not_raise(self):
        for bad in ("", "完全不是 JSON", "[1,2,3]", None):
            assert parse_enrichment(bad, ["甲"], parse_json_response) == {}

    def test_parser_exception_is_swallowed(self):
        def boom(*_a, **_k):
            raise ValueError("解析器炸了")

        assert parse_enrichment("{}", ["甲"], boom) == {}

    def test_skill_suggestions_must_be_list_of_strings(self):
        response = '{"甲": {"backstory": "x", "skill_suggestions": ["A", "", 3, "B"]}}'
        result = parse_enrichment(response, ["甲"], parse_json_response)
        assert result["甲"]["skill_suggestions"] == ["A", "3", "B"]


# ====================================================================== 落到 UI 层


class _FakeAI:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    def chat(self, messages, system="", **kwargs):
        self.calls.append({"messages": messages, "system": system, **kwargs})
        return self.response


class _FakeMemory:
    def __init__(self, characters: dict):
        self._characters = characters
        self.mutated = 0

    def get_characters(self):
        return self._characters

    def mutate_characters(self, fn):
        self.mutated += 1
        fn(self._characters)


class _FakeCharacter:
    def __init__(self, name):
        self.name = name
        self.backstory = ""
        self.personality = ""
        self.appearance = ""
        self.goal = ""
        self.relationship_to_main = ""
        self.skill_suggestions = []


class _FakeSystem:
    def __init__(self, names):
        self._chars = {n: _FakeCharacter(n) for n in names}
        self.saved: list[str] = []

    def get_character(self, name):
        return self._chars.get(name)

    def save_character(self, name):
        self.saved.append(name)


def _mixin(ai, memory, system, meta=None):
    """造一个只带必要属性的 CharacterUIMixin 实例（不建窗口、不联网）。"""
    from app.character_ui import CharacterUIMixin

    obj = CharacterUIMixin.__new__(CharacterUIMixin)
    obj.ai_client = ai
    obj.memory = memory
    obj.character_system = system
    obj.current_novel_dir = None
    obj._log = lambda *_a, **_k: None
    obj._get_meta = lambda: (meta or {})
    return obj


RESPONSE = '{"苏清寒": {"backstory": "灵药宗三师姐。", "personality": "话少。", "goal": "守药庐", "skill_suggestions": ["辨药"]}}'


class TestSilentEnrichment:
    """自动创建后的静默补全：只补空壳、写两处、失败不抛。"""

    def test_fills_skeleton_and_writes_both_stores(self):
        memory = _FakeMemory({"苏清寒": {"category": "无名小卒"}})
        system = _FakeSystem(["苏清寒"])
        obj = _mixin(_FakeAI(RESPONSE), memory, system)

        obj._enrich_characters_silently(["苏清寒"])

        # memory 侧用 background，角色卡侧用 backstory —— 两处都要有
        assert memory._characters["苏清寒"]["background"] == "灵药宗三师姐。"
        assert system._chars["苏清寒"].backstory == "灵药宗三师姐。"
        assert system.saved == ["苏清寒"]

    def test_does_not_touch_characters_with_content(self):
        memory = _FakeMemory({"秦种玉": {"background": "已有背景"}})
        ai = _FakeAI(RESPONSE)
        obj = _mixin(ai, memory, _FakeSystem(["秦种玉"]))

        obj._enrich_characters_silently(["秦种玉"])

        assert ai.calls == [], "已有人设的角色不该再调 AI"
        assert memory._characters["秦种玉"]["background"] == "已有背景"

    def test_disables_thinking(self):
        memory = _FakeMemory({"甲": {}})
        ai = _FakeAI('{"甲": {"backstory": "x"}}')
        _mixin(ai, memory, _FakeSystem(["甲"]))._enrich_characters_silently(["甲"])
        assert ai.calls[0]["thinking_enabled"] is False, "补人设只有 2000 token，思考会吃光"

    def test_ai_failure_is_swallowed(self):
        class Boom(_FakeAI):
            def chat(self, *a, **k):
                raise RuntimeError("网络炸了")

        memory = _FakeMemory({"甲": {}})
        # 不抛异常即通过
        _mixin(Boom(""), memory, _FakeSystem(["甲"]))._enrich_characters_silently(["甲"])
        assert memory._characters["甲"] == {}, "失败时不该留下半截字段"

    def test_empty_names_is_noop(self):
        ai = _FakeAI(RESPONSE)
        _mixin(ai, _FakeMemory({}), _FakeSystem([]))._enrich_characters_silently([])
        assert ai.calls == []


class TestEnrichContext:
    def test_includes_meta_and_known_names(self):
        obj = _mixin(_FakeAI(""), _FakeMemory({}), _FakeSystem([]), meta={"title": "某书", "genre": "仙侠"})
        text = obj._enrich_context(["甲", "乙"])
        assert "某书" in text and "仙侠" in text
        assert "甲" in text and "乙" in text

    def test_survives_missing_meta(self):
        obj = _mixin(_FakeAI(""), _FakeMemory({}), _FakeSystem([]))
        obj._get_meta = lambda: (_ for _ in ()).throw(RuntimeError("meta 坏了"))
        assert obj._enrich_context(["甲"]) == "" or "甲" in obj._enrich_context(["甲"])
