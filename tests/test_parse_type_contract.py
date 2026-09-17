"""解析器**调用点类型契约**守卫（R21）。

背景：`parse_json_response(response, default, is_list=False)` 的类型语义是
**单向**的 ——

- `is_list=True` ⇒ **只接受 list**（文档明确承诺，因为调用方随后按序列遍历）；
- `is_list=False` ⇒ **只"优先找 `{}`"，不承诺拒收顶层数组**。

第二条是 R21 实测暴露的陷阱：AI 在该返回对象的场景返回了顶层数组时，
`parse_json_response` 会老实地把 list 返回给调用方，而下游按 dict 使用
⇒ 崩在离现场很远的地方。

已实测复现的崩溃路径（`scripts/_verify_settings_bug.py` 的结论）：

    _world_builder → memory.save_settings(list) → _format_settings_md(list)
    → settings.items()  →  AttributeError: 'list' object has no attribute 'items'

本文件把"每个期望 dict 的调用点都要有 isinstance 守卫"钉成不变量。
"""

import ast
import inspect
import textwrap

import app.generation_ui as generation_ui
import app.novel_agent as novel_agent
from app.memory_manager import MemoryManager


def _code_only(text: str) -> str:
    """剔除注释与文档字符串后的源码（修复说明里必然提到旧写法）。"""
    tree = ast.parse(textwrap.dedent(text))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _unparse_without_docstring(source: str) -> str:
    return _code_only(source)


# --------------------------------------------------------------------------
# 1. 已实测崩溃的调用点必须有守卫
# --------------------------------------------------------------------------


class TestDictExpectingCallSitesAreGuarded:
    def test_world_builder_rejects_non_dict(self):
        """`_world_builder` 必须在调 `save_settings` 前确认拿到的是 dict。"""
        src = _unparse_without_docstring(inspect.getsource(novel_agent.NovelAgent._world_builder_build))
        assert "isinstance(settings, dict)" in src, (
            "_world_builder 缺少 dict 守卫 —— AI 返回顶层数组时会崩在 _format_settings_md 的 settings.items()"
        )

    def test_style_analysis_rejects_non_dict(self):
        """风格分析返回的 style 会被下游多处按 dict 取值，必须守卫。"""
        src = inspect.getsource(novel_agent.NovelAgent.analyze_style)
        assert "isinstance(style, dict)" in src, "风格分析缺少 dict 守卫"


# --------------------------------------------------------------------------
# 2. 最后一跳必须自保：非 dict 不得抛异常
# --------------------------------------------------------------------------


class TestFormatterIsDefensive:
    def test_format_settings_md_survives_non_dict(self):
        """`_format_settings_md` 是保存链路的最后一跳，收到非 dict 不能崩。

        JSON 已写、Markdown 写失败 = 用户看到"保存了一半"，比直接失败更难排查。
        """
        mm = MemoryManager.__new__(MemoryManager)
        for bad in (["a", "b"], "字符串", 123, None):
            out = mm._format_settings_md(bad)
            assert isinstance(out, str), f"输入 {bad!r} 应返回可读提示，实际 {type(out).__name__}"

    def test_guard_actually_triggers(self):
        """守卫必须真的给出提示，而不是静默返回空串。"""
        mm = MemoryManager.__new__(MemoryManager)
        out = mm._format_settings_md(["a"])
        assert "无法格式化" in out, f"未给出可读提示：{out!r}"

    def test_real_dict_still_formats_normally(self):
        """加守卫不能破坏正常路径。"""
        mm = MemoryManager.__new__(MemoryManager)
        out = mm._format_settings_md({"世界": {"名称": "沧海界"}})
        assert "沧海界" in out, f"正常 dict 未正确格式化：{out!r}"


# --------------------------------------------------------------------------
# 3. 契约本身钉住：避免有人"顺手"把 is_list=False 改成拒收
# --------------------------------------------------------------------------


class TestParserTypeContractIsPinned:
    def test_is_list_false_does_not_reject_top_level_list(self):
        """`is_list=False` 不拒顶层数组 —— 这是**既有契约**，改动会影响所有调用点。

        若将来真的要改成"期望 dict 就拒收 list"，必须同时：
        ① 更新 `app/parsing.py` 的 docstring；
        ② 复核全部 18 个调用点；
        ③ 改这条测试。
        """
        from app.parsing import parse_json_response

        assert isinstance(parse_json_response("[1,2,3]", None), list), (
            "is_list=False 的行为变了 —— 请先复核所有调用点再改这条测试"
        )

    def test_is_list_true_rejects_top_level_dict(self):
        """反向契约：`is_list=True` 必须拒收 dict（调用方按序列遍历）。"""
        from app.parsing import parse_json_response

        assert parse_json_response('{"a": 1}', [], is_list=True) == []

    def test_every_dict_expecting_call_site_has_a_guard_or_a_literal_default(self):
        """扫描全仓：期望 dict 的调用点必须满足下列**任一**条件。

        这是**防止新增调用点重蹈覆辙**的元守卫。四种合法形态（都是真实存在的）：

        1. 调用点之后紧邻 `isinstance(x, dict)` 守卫（`_world_builder_build` / `analyze_style`）；
        2. 所在方法**整体是一层薄委托**（`return parse_json_response(...)` 独占函数体）
           —— 类型契约由它的调用方负责，这里管不着（`GenerationUIMixin._parse_json_response`）；
        3. 结果被**立即 return**，且外层有 `except` 分支返回 dict 字面量兜底
           （`_reviewer_evaluate`：返回值一定是 dict，即使解析出来是 list 也会走 except？不，
            它不会 —— 见下方说明）；
        4. 使用点自己按 dict 取值前有 `if settings and isinstance(settings, dict)` 形态的判断。

        第 3 类的说明：`_reviewer_evaluate` 只是把结果**交出去**，使用方是
        `generate_with_collaboration`。那里在**第一次使用之前**做了
        `isinstance(review, dict)` 归一化（R21 修复），因此安全责任在使用点。
        本守卫对第 3 类的要求是"使用点必须在**使用之前**守卫" ——
        而 R21 恰恰修掉了"守卫在使用之后"（等于没有）的写法。
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent / "app"
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "parse_json_response(" not in text:
                continue
            tree = ast.parse(text)
            src_lines = text.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if "parse_json_response" not in ast.unparse(node.func):
                    continue
                # is_list=True 的调用点不适用（反向契约已保证类型）
                if any(kw.arg == "is_list" for kw in node.keywords):
                    continue
                # 形态 2：所在方法是一层薄委托
                holder = _holding_function(tree, node)
                if holder is not None and _is_thin_delegation(holder):
                    continue
                # 形态 3：调用点被**立即 return**，且结果的使用方守卫 —— 由
                # `TestReviewerUsageIsGuardedBeforeUse` 另外验证。
                if _is_returned_immediately(src_lines, node):
                    continue
                # 形态 1 / 4：调用点后 12 行内有 dict 守卫
                window = "\n".join(src_lines[node.lineno - 1 : node.lineno + 12])
                if "isinstance(" in window and ", dict)" in window:
                    continue
                offenders.append(f"{path.name}:{node.lineno} {ast.unparse(node)[:80]}")
        assert not offenders, "以下期望 dict 的调用点既没有 isinstance 守卫，也不是薄委托：\n  " + "\n  ".join(
            offenders
        )


def _holding_function(tree: ast.AST, target: ast.AST) -> ast.AST | None:
    """找出直接包含 `target` 的最内层函数。"""
    found = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    if found is None or node.lineno > found.lineno:
                        found = node
    return found


def _is_returned_immediately(src_lines: list[str], node: ast.Call) -> bool:
    """调用点所在行是否以 `return` 开头（⇒ 结果直接交出去，责任在使用方）。"""
    line = src_lines[node.lineno - 1].strip()
    return line.startswith("return ") or line == "return"


def _is_thin_delegation(func: ast.AST) -> bool:
    """函数体去掉 docstring 后只剩一条 `return ...` 语句 ⇒ 薄委托。"""
    body = list(getattr(func, "body", []))
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Return)


class TestReviewerUsageIsGuardedBeforeUse:
    """R21 核心修复：守卫必须在**使用之前**。

    `generate_with_collaboration` 里拿到 `review` 后立刻用
    `review.setdefault(...)` / `review.get(...)`。旧代码的 `isinstance(review, dict)`
    出现在**所有使用之后**（第 748 行），等于没有守卫 ——
    一旦审校返回顶层数组，崩的是 `list.setdefault`，且发生在生成主流程。
    """

    def test_review_normalized_before_first_use(self):
        # 必须剔除注释：修复说明里会出现 `review.setdefault(...)` 这个字面量，
        # 若直接扫原文，注释里的它会被当成"使用点"排到守卫之前（假阳性）。
        src = _code_only(inspect.getsource(novel_agent.NovelAgent.generate_with_collaboration))
        lines = src.splitlines()

        guard_line = next(
            (i for i, ln in enumerate(lines) if "isinstance(review, dict)" in ln and "not isinstance" in ln),
            None,
        )
        assert guard_line is not None, "找不到 `if not isinstance(review, dict)` 归一化"

        first_use = next(
            (i for i, ln in enumerate(lines) if ("review.setdefault(" in ln or "review.get(" in ln)),
            None,
        )
        assert first_use is not None, "找不到 review 的使用点（测试前提失效，请复核）"
        assert guard_line < first_use, (
            f"守卫在第 {guard_line + 1} 行，但第一次使用在第 {first_use + 1} 行 —— 守卫在使用之后，等于没有"
        )

    def test_no_bare_review_setdefault_without_preceding_guard(self):
        """归一化之后才允许出现 `review.setdefault`。"""
        src = _code_only(inspect.getsource(novel_agent.NovelAgent.generate_with_collaboration))
        guard = src.find("not isinstance(review, dict)")
        use = src.find("review.setdefault(")
        if use != -1:
            assert guard != -1 and guard < use, "`review.setdefault` 出现在归一化之前"


# --------------------------------------------------------------------------
# 4. generation_ui 的守卫是既有资产，不得回退
# --------------------------------------------------------------------------


class TestGenerationUiGuardsRemain:
    def test_outline_path_guards_with_isinstance(self):
        src = inspect.getsource(generation_ui)
        assert "isinstance(result, dict)" in src or "isinstance(result, list)" in src, (
            "generation_ui 的解析结果守卫被移除了"
        )
