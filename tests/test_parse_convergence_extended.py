"""解析器收敛回归测试（P2-7 扩展）。

第一轮（v3 A1/A2）收敛了 `novel_agent` 里两份重复实现，见 `test_parser_convergence.py`。
本轮（2026-09-17 第二十轮）继续收敛另外 **六处手写 JSON 解析器**：

| 位置 | 原实现 | 收敛后 |
|---|---|---|
| `character_system.ai_create_character` | `json.loads(response[a:b])`，**无 try/except、无尾逗号修复** | `parse_json_response` |
| `character_ui._auto_detect_characters` | `re.search(r"\\[[\\s\\S]*\\]")` + `json.loads`（字符串数组） | `parse_json_response(is_list=True)` + `str` 过滤 |
| `novel_agent._plot_designer_analyze` | 括号深度追踪 + 正则兜底 | `parse_json_response` |
| `generation_ui._auto_detect_decisions` | 括号追踪 + 去 markdown + `"decisions"` 正则 | `parse_json_response` + 保留 `"decisions"` 定点抽取 |
| `generation_ui._auto_generate`（内嵌 `run`） | `re.search(r"\\[[\\s\\S]*\\]")` + 修尾逗号 | `parse_json_response(is_list=True)` |
| `novel_agent._update_character_progression` | 括号追踪 ×2 + 去 markdown | `parse_json_response` + 保留逐字段抽取 |

本文件锁定两件事：

1. **行为等价性/不退化**：六处替换后，各自的典型输入（含脏输入）仍得到同样的结果，
   并把**实际新增的接受面**与**明确不支持的输入**都写成断言（不写想当然的结论）；
2. **删掉的重复实现不得回来**：源码级断言，剔除注释与文档字符串
   （修复说明里会写"旧实现是……"，不能算作仍在调用）。这一条与
   `test_parser_convergence.py::TestDuplicateImplementationStaysDeleted` 同一模式。
"""

import ast
import inspect

import pytest

from app import character_system as character_system_module
from app import generation_ui as generation_ui_module
from app import novel_agent as novel_agent_module
from app.parsing import parse_json_response


def _code_only(module) -> str:
    """模块源码，剔除注释与文档字符串。"""
    source = inspect.getsource(module)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    for idx in range(first.lineno - 1, min(first.end_lineno, len(lines))):
                        lines[idx] = ""
    return "\n".join(line.split("#", 1)[0] for line in lines)


# --------------------------------------------------------------------------
# 1. 行为：单引号 JSON 现在能解析（旧手写实现全部失败）
# --------------------------------------------------------------------------


class TestConvergenceWidensAcceptance:
    """收敛带来的**能力提升**（逐条实测，不写想当然的结论）。

    实测 `parse_json_response` 相对旧手写实现多覆盖的输入：

    | 输入 | 旧手写 `json.loads(切片)` | `parse_json_response` |
    |---|---|---|
    | `{"a"：1}` 全角冒号 | 失败（丢数据） | **成功** |
    | `{"a": 1,}` 尾逗号 | 视位置而定，`_plot_designer_analyze` 能救、`character_system` 不能 | **成功** |
    | `json.loads` 前带 markdown 围栏 | `_plot_designer_analyze` 不能 | **成功** |

    每一处的失败路径都是**丢数据**（跳角色成长 / 跳大纲批量更新 / 跳新角色识别），
    因此"能多解析出来"是严格改善，不是行为倒退。

    ⚠️ 明确**不覆盖**的：单引号 JSON（`{'a': 1}`）与缺逗号（`{"a" "b"}`）
    两种修复都不处理 —— 别把这条写成预期能力。
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('{"a"：1}', {"a": 1}),
            ('{"a": 1,}', {"a": 1}),
            ('{"a": 1, "b": 2,}', {"a": 1, "b": 2}),
        ],
    )
    def test_fullwidth_colon_and_trailing_comma(self, raw, expected):
        assert parse_json_response(raw, None) == expected

    def test_single_quote_is_NOT_supported(self):
        """把边界写清楚：单引号不在能力范围内（防止后人误当回归）。"""
        assert parse_json_response("{'a': 1}", None) is None


class TestTrailingCommaPriorityFix:
    """P2-7 修复：**修复版本必须紧跟自己的原文**，否则优先级失效。

    实测回归样本：`'{"type": "action", "pace": "fast", "foreshadowing": [],}'`
    期望 dict。旧顺序把全部修复版本追加到**所有**原文之后：

        [ `{...,}`(解析失败), `[]`(解析成功!) , 修复1(`{...}`), 修复2 ]

    于是返回了内嵌的空数组 `[]` —— 期望 dict 却拿到 list，调用方
    `parsed.get("type")` 直接 AttributeError 或遍键名成空。
    """

    RAW = '{"type": "action", "pace": "fast", "foreshadowing": [],}'

    def test_trailing_comma_dict_wins_over_nested_list(self):
        result = parse_json_response(self.RAW, None)
        assert isinstance(result, dict), f"应返回 dict，实际 {type(result).__name__}: {result!r}"
        assert result["type"] == "action"
        assert result["foreshadowing"] == []

    def test_markdown_fence_still_parses(self):
        fence = "`" * 3
        result = parse_json_response(fence + 'json\n{"a": 1}\n' + fence, None)
        assert result == {"a": 1}

    def test_nested_list_candidate_does_not_beat_outer_dict(self):
        """外层带尾逗号、内层数组合法 —— 必须拿到外层。"""
        raw = '{"decisions": [{"id": 1}],}'
        result = parse_json_response(raw, None)
        assert isinstance(result, dict) and result["decisions"] == [{"id": 1}]


# --------------------------------------------------------------------------
# 2. 源码级：六处重复实现不得回来
# --------------------------------------------------------------------------


class TestHandRolledParsersStayDeleted:
    """六个位置的旧手写解析机器必须消失（剔除注释后断言）。"""

    def test_character_system_slice_loads_gone(self):
        src = _code_only(character_system_module)
        assert 'response.find("{")' not in src
        assert 'response.rfind("}")' not in src

    def test_character_ui_array_regex_gone(self):
        src = _code_only(
            __import__("app.character_ui", fromlist=["x"]),
        )
        # `_auto_detect_characters` 里的 `re.search(r"\[[\s\S]*\]")` 已删
        assert r're.search(r"\[[\s\S]*\]"' not in src
        # 该模块已不再需要 re
        assert "import re" not in src

    def test_novel_agent_depth_tracking_gone(self):
        src = _code_only(novel_agent_module)
        # 括号深度追踪的典型写法：`end_idx = -1` + 手写 `depth` 循环
        assert "end_idx = -1" not in src
        # 旧的两处尾逗号正则修复（现已由 parsing 统一承担）
        assert r're.sub(r",\s*}", "}", json_str)' not in src

    def test_novel_agent_still_keeps_field_extraction_salvage(self):
        """逐字段抽取（原 Strategy 4）是 parsing 覆盖不到的，必须保留。"""
        src = _code_only(novel_agent_module)
        assert r'"updates"\s*:\s*\[([\s\S]*?)\]' in src

    def test_generation_ui_depth_tracking_gone(self):
        src = _code_only(generation_ui_module)
        assert "end_idx = -1" not in src

    def test_generation_ui_keeps_decisions_salvage(self):
        """`"decisions"` 定点抽取是 parsing 覆盖不到的，必须保留。"""
        src = _code_only(generation_ui_module)
        assert r'"decisions"\s*:\s*\[' in src


class TestParsingModuleStillHoldsTheImplementation:
    """收敛方向是"都往 parsing 走"，所以 parsing 必须仍是完整实现。"""

    def test_parse_json_response_is_not_a_delegation(self):
        tree = ast.parse(inspect.getsource(parse_json_response))
        body = tree.body[0].body
        assert len(body) > 10, "parsing.parse_json_response 不应被改成薄委托"

    def test_repair_helpers_exist(self):
        from app import parsing

        for name in ("_repair_json_preserving_strings", "_repair_json_naive", "_is_balanced"):
            assert hasattr(parsing, name), f"parsing.{name} 缺失"

    def test_repair_variants_are_interleaved_not_appended(self):
        """源码级钉住 P2-7 的修复：修复版本必须与原文交替，不能整体后置。"""
        src = inspect.getsource(parse_json_response)
        code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
        assert "for raw in list(strategies)" not in code, "旧的'整体后置'写法回来了"
        assert "_repair_json_preserving_strings(raw)" in code
