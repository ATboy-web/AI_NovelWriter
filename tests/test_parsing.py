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

    def test_curly_delimiters_are_handled_by_the_compat_variant(self):
        """用弯引号当 JSON 分隔符的极端格式由兼容变体救回。

        保真变体在字符串内部一律保留字符，因此对 ``{“a”: “b”}`` 这种
        "整篇都是弯引号"的写法无能为力 —— 这是有意的取舍，由
        `parse_characters_payload` / `parse_json_response` 的候选链兜底。
        """
        src = '{“a”: “b”}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(clean_ai_json_text(src))
        assert json.loads(repair_ai_json_text(src)) == {"a": "b"}

    def test_escaped_quote_does_not_end_string(self):
        src = '{"a": "he said \\"hi\\", ok"}'
        assert clean_ai_json_text(src) == src
        assert json.loads(clean_ai_json_text(src))["a"] == 'he said "hi", ok'

    def test_naive_variant_still_replaces_everything(self):
        assert repair_ai_json_text('{"性格": "温和，善良"}') == '{"性格": "温和,善良"}'


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


class TestStripAiJsonFences:
    def test_strips_fence_and_fullwidth_space(self):
        assert strip_ai_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_non_string_returns_empty(self):
        assert strip_ai_json_fences(None) == ""
