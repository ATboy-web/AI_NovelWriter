"""app/parsing.py 纯函数单元测试。

P2-6：这两个函数原先深埋在 NovelWriterApp 的巨型方法里、无法单独测试；
抽取为模块级纯函数后补上本测试，锁定其容错解析行为。
"""

import pytest

from app.parsing import parse_exp_json, parse_json_response


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
