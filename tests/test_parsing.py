"""app/parsing.py 纯函数单元测试。

P2-6：这两个函数原先深埋在 NovelWriterApp 的巨型方法里、无法单独测试；
抽取为模块级纯函数后补上本测试，锁定其容错解析行为。
"""

import json

import pytest

from app.parsing import (
    clean_ai_json_text,
    extract_characters_payload,
    parse_characters_payload,
    parse_exp_json,
    parse_json_response,
    repair_ai_json_text,
    strip_ai_json_fences,
)


class TestParseJsonResponse:
    """AI 通用 JSON 响应解析（多层修复）。"""

    def test_plain_object(self):
        assert parse_json_response('{"a": 1}', None) == {"a": 1}

    def test_object_embedded_in_prose(self):
        assert parse_json_response('好的，结果是：{"title": "x"} 希望有帮助', None) == {"title": "x"}

    def test_array_embedded(self):
        assert parse_json_response('prefix [1, 2, 3] suffix', None) == [1, 2, 3]

    def test_markdown_fence(self):
        assert parse_json_response('```json\n{"a": 1}\n```', None) == {"a": 1}

    def test_fullwidth_punctuation_repaired(self):
        # 全角冒号/逗号应被修正为半角
        assert parse_json_response('{"a"：1，"b"：2}', None) == {"a": 1, "b": 2}

    def test_trailing_comma_repaired(self):
        assert parse_json_response('{"a": 1,}', None) == {"a": 1}

    def test_missing_closing_brace_returns_default(self):
        # 已知局限：完全没有闭合 } 时无法用 { ... } 提取，返回默认值
        assert parse_json_response('{"a": "hello', "DEFAULT") == "DEFAULT"

    def test_partial_objects_extracted(self):
        # Strategy 5：逐个提取完整子对象
        raw = '{"张三": {"role": "主角"}, "李四": {"role": "配角"}'
        assert parse_json_response(raw, None) == {
            "张三": {"role": "主角"},
            "李四": {"role": "配角"},
        }

    @pytest.mark.parametrize("bad", ["", None, "没有JSON内容"])
    def test_invalid_returns_default(self, bad):
        assert parse_json_response(bad, "D") == "D"

    def test_default_object_returned_identically(self):
        d = {"d": 1}
        assert parse_json_response("not json", d) is d


class TestParseExpJson:
    """EXP 分析响应解析（增强容错）。"""

    def test_clean_json(self):
        r = parse_exp_json('{"张三": {"action": "突破", "exp": 50, "detail": "闭关成功"}}')
        assert r["张三"] == {"action": "突破", "exp": 50, "detail": "闭关成功"}

    def test_markdown_fence(self):
        r = parse_exp_json('```json\n{"李四": {"action":"练功","exp": -5, "detail":"偷懒"}}\n```')
        assert r["李四"]["exp"] == -5

    def test_truncated_json_completed(self):
        r = parse_exp_json('{"王五": {"action": "战斗", "exp": 30, "detail": "险胜"')
        assert r["王五"]["action"] == "战斗"
        assert r["王五"]["exp"] == 30

    def test_exp_can_be_negative(self):
        r = parse_exp_json('{"甲": {"action": "堕落", "exp": -20, "detail": "x"}}')
        assert r["甲"]["exp"] == -20

    @pytest.mark.parametrize("bad", ["", "no json here"])
    def test_empty_result_when_unparseable(self, bad):
        assert parse_exp_json(bad) == {}

    # --- M12：EXP 数值必须安全转换并钳位 ---

    def test_huge_exp_is_clamped(self):
        """超长数字串既不能抛异常，也不能原样透出。"""
        huge = "9" * 5000
        r = parse_exp_json('{"甲": {"action": "x", "exp": ' + huge + ', "detail": "d"}}')
        assert r["甲"]["exp"] == 1_000_000

    def test_negative_huge_exp_is_clamped(self):
        huge = "9" * 5000
        r = parse_exp_json('{"甲": {"action": "x", "exp": -' + huge + ', "detail": "d"}}')
        assert r["甲"]["exp"] == -1_000_000

    def test_non_numeric_exp_falls_back_to_zero(self):
        # 用截断串走到 Strategy 5 的补全分支，该分支必须安全转换 exp
        r = parse_exp_json('{"甲": {"action": "x", "exp": "很多", "detail": "d"')
        assert r["甲"]["exp"] == 0

    def test_normal_exp_untouched(self):
        r = parse_exp_json('{"甲": {"action": "x", "exp": 37, "detail": "d"}}')
        assert r["甲"]["exp"] == 37


class TestCleanAiJsonText:
    """字符串感知清洗：只修字符串之外的标点（第二轮优化新增）。"""

    def test_repairs_structural_fullwidth_punctuation(self):
        assert clean_ai_json_text('{"a"：1，"b"：2}') == '{"a":1,"b":2}'

    def test_preserves_chinese_comma_inside_string(self):
        """角色性格里的中文逗号必须原样保留。

        旧实现无条件 `replace('，', ',')`，会把 "温和，善良" 改写成
        "温和,善良" —— 这是对小说内容的实际篡改。
        """
        src = '{"性格": "温和，善良"}'
        assert clean_ai_json_text(src) == src

    def test_preserves_fullwidth_colon_inside_string(self):
        src = '{"备注": "提示：注意"}'
        assert clean_ai_json_text(src) == src

    def test_preserves_curly_quotes_inside_string(self):
        src = '{"口头禅": "他常说“我不在乎”"}'
        cleaned = clean_ai_json_text(src)
        assert cleaned == src
        assert json.loads(cleaned)["口头禅"] == "他常说“我不在乎”"

    def test_curly_delimiters_are_normalized_symmetrically(self):
        """L3：弯引号状态机必须对称 —— `“` 开启、`”` 关闭。

        第三轮修复前，字符串**外**的 `“` 与 `”` 都会把状态置为"在字符串内"，
        于是 ``{“a”: “b”}`` 被解析成连续开两次、永远关不上，保真变体只能失败。
        现在保真变体可直接救回，兼容变体仍作为兜底。
        """
        src = '{“a”: “b”}'
        assert json.loads(clean_ai_json_text(src)) == {"a": "b"}
        assert json.loads(repair_ai_json_text(src)) == {"a": "b"}

    def test_curly_opened_string_keeps_straight_quote_as_literal(self):
        """由 `“` 开启的字符串内部出现直引号时，转义保留而不是提前闭合。"""
        cleaned = clean_ai_json_text('{“口头禅”: “他说"算了"”}')
        assert json.loads(cleaned)["口头禅"] == '他说"算了"'

    def test_escaped_quote_does_not_end_string(self):
        src = '{"a": "he said \\"hi\\", ok"}'
        assert clean_ai_json_text(src) == src
        assert json.loads(clean_ai_json_text(src))["a"] == 'he said "hi", ok'

    def test_naive_variant_still_replaces_everything(self):
        assert repair_ai_json_text('{"性格": "温和，善良"}') == '{"性格": "温和,善良"}'


class TestStructuralRepairIsStringAware:
    """L1/L2：结构性修复不得改写字符串正文。"""

    def test_trailing_comma_inside_string_value_is_preserved(self):
        """`{"a": "正文,}"}` 里的 `,}` 是正文，不能被当作尾随逗号删掉。"""
        raw = '{"a": "正文,}"}'
        assert parse_json_response(raw, None) == {"a": "正文,}"}

    def test_structural_trailing_comma_is_still_repaired(self):
        assert parse_json_response('{"a": 1, "b": 2,}', None) == {"a": 1, "b": 2}

    def test_consecutive_colons_repaired_outside_strings(self):
        assert parse_json_response('{"a"::1}', None) == {"a": 1}

    def test_double_colon_inside_string_is_preserved(self):
        raw = '{"a": "时间 12::30"}'
        assert parse_json_response(raw, None) == {"a": "时间 12::30"}

    def test_brace_inside_string_does_not_confuse_deep_repair(self):
        raw = '{"a": "含 } 的正文", "b": 2}'
        assert parse_json_response(raw, None) == {"a": "含 } 的正文", "b": 2}

    def test_missing_comma_between_strings_is_inserted(self):
        raw = '{"a": "x"\n  "b": "y"}'
        assert parse_json_response(raw, None) == {"a": "x", "b": "y"}

    def test_repair_does_not_touch_chinese_punctuation_in_values(self):
        raw = '{"性格": "温和，善良", "备注": "提示：注意"}'
        parsed = parse_json_response(raw, None)
        assert parsed["性格"] == "温和，善良"
        assert parsed["备注"] == "提示：注意"


class TestParseCharactersPayload:
    def test_plain_dict_body(self):
        raw = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明"}}'
        assert parse_characters_payload(raw) == {
            "张三": {"personality": "勇敢"},
            "李四": {"personality": "聪明"},
        }

    def test_accepts_dict_input(self):
        assert parse_characters_payload({"张三": {"a": 1}}) == {"张三": {"a": 1}}

    def test_drops_raw_key_and_non_dict_values(self):
        assert parse_characters_payload({"raw": "x", "张三": {"a": 1}, "李四": "不是字典"}) == {
            "张三": {"a": 1}
        }

    def test_markdown_fence_and_goal_array_repaired(self):
        raw = '```json\n{"张三": {"goal": ["a", "b"], "personality": "x"}}\n```'
        parsed = parse_characters_payload(raw)
        assert parsed["张三"]["goal"] == "a; b"

    def test_fullwidth_structural_punctuation_repaired(self):
        raw = '{"张三"：{"personality"："勇敢"}}'
        assert parse_characters_payload(raw)["张三"]["personality"] == "勇敢"

    def test_curly_quote_delimiters_repaired(self):
        raw = '{“张三”: {“personality”: “勇敢”}}'
        assert parse_characters_payload(raw)["张三"]["personality"] == "勇敢"

    def test_preserves_chinese_punctuation_in_values(self):
        raw = '{"张三": {"personality": "温和，善良", "口头禅": "“随便”"}}'
        info = parse_characters_payload(raw)["张三"]
        assert info["personality"] == "温和，善良"
        assert info["口头禅"] == "“随便”"

    @pytest.mark.parametrize("bad", ["", "   ", "没有 JSON", None, 123])
    def test_unparseable_returns_empty(self, bad):
        assert parse_characters_payload(bad) == {}


class TestExtractCharactersPayload:
    def test_current_format(self):
        assert extract_characters_payload({"张三": {"a": 1}}) == {"张三": {"a": 1}}

    def test_legacy_raw_format(self):
        data = {"raw": '{"张三": {"a": 1}}'}
        assert extract_characters_payload(data) == {"张三": {"a": 1}}

    def test_legacy_raw_unparseable_falls_back_to_top_level_dict(self):
        data = {"raw": "坏数据", "张三": {"a": 1}}
        assert extract_characters_payload(data) == {"张三": {"a": 1}}

    def test_non_dict_returns_empty(self):
        assert extract_characters_payload(["x"]) == {}

    # --- L10：名为 raw 的角色不再被静默丢弃 ---

    def test_character_named_raw_is_kept(self):
        data = {"raw": {"personality": "其实是一个角色"}, "张三": {"a": 1}}
        assert extract_characters_payload(data) == {
            "raw": {"personality": "其实是一个角色"},
            "张三": {"a": 1},
        }

    def test_legacy_raw_and_current_entries_are_merged(self):
        """旧版 raw 载荷与顶层条目必须并集返回，而不是提前返回丢掉后者。"""
        data = {"raw": '{"甲": {"a": 1}}', "乙": {"b": 2}}
        assert extract_characters_payload(data) == {"甲": {"a": 1}, "乙": {"b": 2}}

    def test_dict_valued_raw_character_survives_reparse(self):
        """往返：写出去再读回来，名为 raw 的角色仍在。"""
        original = {"raw": {"category": "配角"}, "主角甲": {"category": "主角"}}
        assert extract_characters_payload(original) == original


class TestStripAiJsonFences:
    def test_strips_fence_and_fullwidth_space(self):
        assert strip_ai_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_non_string_returns_empty(self):
        assert strip_ai_json_fences(None) == ""
