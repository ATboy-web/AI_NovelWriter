"""解析器收敛回归测试（v3 A1/A2）。

改造前存在**两份独立实现**：
- `app/parsing.py`：`parse_json_response` / `parse_characters_payload`（纯函数，已单测）
- `app/novel_agent.py`：`_parse_json_response` / `_extract_characters_from_raw`（各约 60 / 80 行）

两份已经**漂移**，其中一处真实差异是：novel_agent 版在 Strategy 5 里把键名为
`raw` 的条目当"旧版载体"剔除 —— 于是一个**真的叫 `raw` 的角色被静默丢弃**，
而 parsing 版早已修掉（见 `parsing.py` 的 L10 说明）。

现在 novel_agent 侧只保留薄委托，实现单一来源。本文件锁定：

1. **行为等价性**：对同一批样本，委托版与 parsing 版输出完全一致；
2. `is_list` 类型语义不退化（调用方随后按序列遍历）；
3. **删掉的重复实现不得回来**（源码级断言，剔除注释与文档字符串）；
4. 收敛**不得损失能力**：截断响应的补救（末段对象补括号）必须仍有效。
"""

import ast
import inspect

import pytest

from app import novel_agent as novel_agent_module
from app.novel_agent import NovelAgent
from app.parsing import parse_characters_payload, parse_json_response

# 覆盖各种真实会遇到的脏响应
SAMPLES = [
    '{"key": "value"}',
    '```json\n{"key": "value"}\n```',
    '分析结果：{"key": "value"}',
    '{"a"：1，"b"：2}',
    '{"a": 1,}',
    '{"a" "b"}',
    '{“a”: “b”}',
    '{"a": "正文,}"}',
    '{"a": "时间 12::30"}',
    '{"a": "含 } 的正文", "b": 2}',
    '{"a": "x"\n  "b": "y"}',
    '{"张三": {"role": "主角"}, "李四": {"role": "配角"}',
    '{"key": "value", "key2": "value2"',
    '{"key1": "value1"} {"key2": "value2"}',
    '{"goal": ["a", "b"]}',
    '{"nested": {"key": "value"}}',
    '{"value": null}',
    '{}',
    'invalid json',
    '',
]

LIST_SAMPLES = [
    '[1, 2, 3]',
    '```json\n[1, 2, 3]\n```',
    'prefix [1, 2, 3] suffix',
    '[1, 2, 3',
    'invalid json',
    '[]',
    '{"a": 1}',
]


class TestDelegationIsBehaviourallyEquivalent:
    """委托版必须与 parsing 版**逐字节同结果**。"""

    @pytest.mark.parametrize("sample", SAMPLES)
    def test_dict_mode_matches(self, sample):
        assert NovelAgent._parse_json_response(sample, {}) == parse_json_response(sample, {})

    @pytest.mark.parametrize("sample", LIST_SAMPLES)
    def test_list_mode_matches(self, sample):
        assert NovelAgent._parse_json_response(sample, [], is_list=True) == parse_json_response(
            sample, [], is_list=True
        )

    def test_default_object_returned_identically(self):
        default = {"d": 1}
        assert NovelAgent._parse_json_response("not json", default) is default

    def test_non_string_returns_default(self):
        assert NovelAgent._parse_json_response(None, {"x": 1}) == {"x": 1}


class TestIsListSemantics:
    """`is_list=True` 只接受 list —— 否则 `for item in outline` 会遍历到键名。"""

    def test_returns_list_for_array(self):
        assert NovelAgent._parse_json_response('[1, 2, 3]', [], is_list=True) == [1, 2, 3]

    def test_empty_list(self):
        assert NovelAgent._parse_json_response('[]', [], is_list=True) == []

    def test_object_is_rejected_in_list_mode(self):
        """期望列表时解析出对象 → 回退默认值，而不是把 dict 返回给调用方。"""
        assert NovelAgent._parse_json_response('{"a": 1}', [0], is_list=True) == [0]

    def test_partial_objects_become_list_in_list_mode(self):
        raw = '{"甲": {"v": 1}, "乙": {"v": 2}'
        assert NovelAgent._parse_json_response(raw, [], is_list=True) == [{"v": 1}, {"v": 2}]

    def test_same_input_dict_mode_returns_dict(self):
        raw = '{"甲": {"v": 1}, "乙": {"v": 2}'
        assert NovelAgent._parse_json_response(raw, {}) == {"甲": {"v": 1}, "乙": {"v": 2}}


class TestCharacterExtractionConverged:
    """`_extract_characters_from_raw` ≡ `parsing.parse_characters_payload`。"""

    @pytest.mark.parametrize(
        "sample",
        [
            '{"张三": {"personality": "勇敢"}}',
            '```json\n{"张三": {"personality": "勇敢"}}\n```',
            '{"张三"：{"personality"："勇敢"}}',
            '{“张三”: {“personality”: “勇敢”}}',
            '{"张三": {"goal": ["a", "b"]}}',
            '{"张三": {"personality": "勇敢", "weapon": {"name": "剑"',
            "没有 JSON",
            "",
        ],
    )
    def test_matches_parsing_module(self, sample):
        assert NovelAgent._extract_characters_from_raw(sample) == parse_characters_payload(sample)

    @pytest.mark.parametrize("bad", [None, 123, [], 1.5])
    def test_non_string_input_is_safe(self, bad):
        assert NovelAgent._extract_characters_from_raw(bad) == {}

    def test_truncated_tail_object_is_recovered(self):
        """收敛后必须**保留**旧手写扫描的能力：末段对象补括号。"""
        raw = '{"张三": {"personality": "勇敢"}, "李四": {"personality": "聪明", "weapon": {"name": "剑"'
        result = NovelAgent._extract_characters_from_raw(raw)
        assert "张三" in result
        assert "李四" in result
        assert result["李四"]["personality"] == "聪明"

    def test_chinese_punctuation_in_values_is_preserved(self):
        """补救截断时不得顺手把值里的中文标点替换掉（朴素变体会，保真变体不会）。"""
        raw = '{"张三": {"口头禅": "他常说“算了”"'
        result = NovelAgent._extract_characters_from_raw(raw)
        assert result["张三"]["口头禅"] == "他常说“算了”"

    def test_character_named_raw_is_not_dropped(self):
        """⚠️ 这是收敛前 novel_agent 版**真实存在**的缺陷：名叫 raw 的角色被丢弃。"""
        raw = '{"raw": {"personality": "其实是一个角色"}, "张三": {"a": 1}}'
        result = NovelAgent._extract_characters_from_raw(raw)
        assert result == {"raw": {"personality": "其实是一个角色"}, "张三": {"a": 1}}

    def test_nested_subobjects_are_skipped_when_partially_extracted(self):
        """截断路径下，`weapon` / `attributes` 是角色的子对象，不作为角色提取。

        注：**完整** JSON 走的是整串 `json.loads`，顶层键一律视为角色
        （与收敛前的 `_extract_characters_from_raw` 一致）；
        只有"逐个提取子对象"的截断补救路径才应用子对象剔除表 ——
        否则 `{"张三": {..., "weapon": {...}` 这种截断会把 weapon 也当成一个角色。
        """
        raw = '{"张三": {"a": 1}, "weapon": {"name": "剑"'
        assert NovelAgent._extract_characters_from_raw(raw) == {"张三": {"a": 1}}

    def test_attributes_subobject_is_skipped_when_partially_extracted(self):
        raw = '{"李四": {"a": 2}, "attributes": {"力量": 80"'
        assert NovelAgent._extract_characters_from_raw(raw) == {"李四": {"a": 2}}

    def test_complete_json_keeps_top_level_dict_values(self):
        """完整 JSON：顶层 dict 值都算角色（保持收敛前的行为，不做语义加戏）。"""
        raw = '{"weapon": {"name": "剑"}, "张三": {"a": 1}}'
        assert NovelAgent._extract_characters_from_raw(raw) == {
            "weapon": {"name": "剑"},
            "张三": {"a": 1},
        }


def _delegation_body_lines(func) -> list:
    """取函数体里"有效语句"的源码（去掉 docstring，用于断言"只剩一行委托"）。

    `inspect.getsource` 对 `@staticmethod` 方法会**连装饰器一起**返回且带缩进，
    直接 `ast.parse` 会 `IndentationError`，所以先 `dedent`。
    """
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    node = tree.body[0]
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return [ast.unparse(stmt) for stmt in body]


class TestDuplicateImplementationStaysDeleted:
    """源码级断言：被删掉的重复实现不得回来。"""

    def test_parse_json_response_is_a_thin_delegation(self):
        body = _delegation_body_lines(NovelAgent._parse_json_response)
        assert len(body) == 1, f"应为单行委托，实际有 {len(body)} 条语句"
        assert body[0] == "return parse_json_response(response, default, is_list=is_list)"

    def test_extract_characters_is_a_thin_delegation(self):
        body = _delegation_body_lines(NovelAgent._extract_characters_from_raw)
        assert body == ["return parse_characters_payload(raw_text)"]

    def test_old_skip_tuple_is_gone(self):
        """旧的 `('raw', 'weapon', 'attributes', 'skill_suggestions')` 剔除表必须消失。"""
        source = _strip_comments_and_docstrings(
            inspect.getsource(novel_agent_module)
        )
        assert "('raw', 'weapon', 'attributes', 'skill_suggestions')" not in source
        assert '("raw", "weapon"' not in source

    def test_no_local_strategy_machinery_left_in_novel_agent(self):
        """Strategy 4 的补全后缀表只应存在于 parsing.py。"""
        source = _strip_comments_and_docstrings(inspect.getsource(novel_agent_module))
        assert '"}]}}"' not in source

    def test_parsing_module_is_the_single_source(self):
        """parsing 里必须仍然**带着**完整实现。"""
        from app import parsing

        body = _delegation_body_lines(parsing.parse_json_response)
        assert len(body) > 10, "parsing.parse_json_response 不应被改成委托"


def _strip_comments_and_docstrings(source: str) -> str:
    """剔除注释与文档字符串 —— 修复说明会提到"旧的 xxx"，不能算作仍在调用。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    doc_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    doc_ranges.append((first.lineno, first.end_lineno))
    lines = source.splitlines()
    for start, end in doc_ranges:
        for idx in range(start - 1, min(end, len(lines))):
            lines[idx] = ""
    return "\n".join(line.split("#", 1)[0] for line in lines)
