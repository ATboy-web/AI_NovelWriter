"""正文生成的三道闸：关闭思考 / 拒收规划文字 / 拒绝 reasoning 兜底。

## 事故回顾（这些用例存在的全部理由）

一次 10 章自动创作，第 1、2 章落盘后正文里混进了模型的工作笔记：

    用户希望我继续写这个故事。让我回顾一下上下文：
    秦纵是主角——表面温顺寡言…
    让我起草：--- （正文草稿）… 嗯，这大概有1300字。我得写到2000字左右。

成因是**三个缺陷叠加**：

1. 写手没关思考，而模型是 `deepseek-flash` + `reasoning_effort=max`，
   分段生成只给 4096 token ⇒ 预算被推理吃光 ⇒ `content` 为空；
2. `_finalize_text` 在这种情况下**用 reasoning 兜底返回** —— 那是"给分析类调用救急"的
   遗留语义，用在正文上就把工作笔记当正文；
3. 字数闸门把 reasoning 也算进"字数" ⇒ 8029/4000 "达标" ⇒ 质量门形同虚设。

三道闸分别对应这三条。任一道生效，坏章节都进不了书。
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.ai_client import AIClient
from app.generation_ui import coerce_chapter_no
from app.novel_agent import _looks_like_planning
from app.providers.base import ChatResult

REPO = pathlib.Path(__file__).resolve().parent.parent


# ====================================================================== 闸 2：规划检测


class TestPlanningDetection:
    """真实事故样本必须判 True，正常正文与对白必须判 False。"""

    #: 摘自事故章节（保留原样，这是最有价值的回归样本）
    POLLUTION_1 = """用户希望我继续写这个故事。让我回顾一下上下文：

秦纵是主角——表面温顺寡言，习惯低头、替人打杂跑腿。
姜雪辞是关键人物——天之骄女，仪态无懈可击，说话轻声细语。

让我起草：

---

秦纵把珠子拿了起来。

嗯，这大概有1300字。我得写到2000字左右。"""

    POLLUTION_2 = """用户要求续写玄幻小说第00002章，大约2000字。需要推进实质剧情。

当前情节点：秦纵答应去拿炉砖。

让我想想更好的：元阳珠是从灶灰里筛出来的。

或者更直接：秦纵在路上被截住——但那样要引入角色。

具体设计：
- 秦纵离开姜雪辞处，先回杂役房。
- 他往旧窑去。"""

    STAGE_DIRECTIONS = """（他先回杂役房。他住的地方，七个人一间，夜里都睡死了。）
（往后山旧窑去。路上巡夜的灯笼从坡上过，他蹲在柴垛后头等。）
（旧窑到了。窑口塌了一半。里面砖堆三层。）"""

    PROSE = """秦纵蹲在井台边搓洗衣裳，木盆里的水换了三遍，指尖泡得发白。

“秦纵！后厨的柴劈了没有？”

“劈了。”他头也没抬，“卯时前就劈完了，堆在西墙底下。”"""

    DIALOGUE = """他皱着眉，半晌没说话。

“让我想想。”秦纵把手搁在膝上，“这话不能这么答。”"""

    @pytest.mark.parametrize("sample", [POLLUTION_1, POLLUTION_2, STAGE_DIRECTIONS], ids=["规划1", "规划2", "括号提纲"])
    def test_planning_is_detected(self, sample):
        assert _looks_like_planning(sample) is True

    @pytest.mark.parametrize("sample", [PROSE, DIALOGUE], ids=["正常正文", "对白含让我想想"])
    def test_prose_is_not_flagged(self, sample):
        assert _looks_like_planning(sample) is False

    def test_single_weak_marker_does_not_fire(self):
        """单个弱特征词（如对白里的「让我想想」）不能触发 —— 否则会误杀正常章节。"""
        assert _looks_like_planning("“让我想想。”他很慢地说。") is False

    def test_empty_is_not_planning(self):
        assert _looks_like_planning("") is False
        assert _looks_like_planning("   ") is False

    def test_two_weak_markers_fire(self):
        assert _looks_like_planning("让我想想。或者更好，换个写法。") is True


# ====================================================================== 闸 1：关闭思考


class TestProseCallsAreHardened:
    """**产出正文**的调用必须关思考 + 禁 reasoning 兜底。

    判据是"这个函数的输出会不会被当成小说正文落盘"，不是"函数在哪"：

    | 函数 | 输出 | 是否必须加固 |
    |---|---|---|
    | `_writer_generate` | 正文（单发） | 是 |
    | `_generate_long_chapter` | 正文（分段 + 补全） | 是 |
    | `_writer_revise` | 正文（**覆盖**原文） | 是 |
    | `generate_chapter` | 正文（整章重生成） | 是 |
    | `generate_with_style` / `blend_styles` | 正文 | 是 |
    | `_reviewer_evaluate` | JSON（失败即无分数） | 是（思考吃光预算就出不来 JSON） |
    | `generate_settings` / `generate_characters` / `_plan_story_arcs` 等 | 结构化数据 | 否（思考有价值，下游有解析兜底） |
    """

    PROSE_FUNCTIONS = {
        "_writer_generate",
        "_generate_long_chapter",
        "_writer_revise",
        "generate_chapter",
        "generate_with_style",
        "blend_styles",
        "_reviewer_evaluate",
    }

    @classmethod
    def _calls(cls):
        """产出 `(行号, 所属函数名, 关键字参数集合)`。"""
        source = (REPO / "app" / "novel_agent.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = [
            (node.lineno, node.end_lineno, node.name)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        rows = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "chat"):
                continue
            owner = next((f for f in funcs if f[0] <= node.lineno <= f[1]), None)
            rows.append((node.lineno, owner[2] if owner else "?", {kw.arg for kw in node.keywords}))
        return rows

    def test_prose_calls_disable_thinking_and_fallback(self):
        offenders = []
        for line, func, kwargs in self._calls():
            if func not in self.PROSE_FUNCTIONS:
                continue
            if "thinking_enabled" not in kwargs:
                offenders.append(f"行 {line} ({func}): 未传 thinking_enabled")
            if "allow_reasoning_fallback" not in kwargs:
                offenders.append(f"行 {line} ({func}): 未传 allow_reasoning_fallback")
        assert not offenders, "以下正文类调用缺少闸门（会被 reasoning 工作笔记顶替）：\n  " + "\n  ".join(offenders)

    def test_critical_paths_covered(self):
        """确认这些函数确实被扫到了 —— 防止函数改名后守卫静默失效。"""
        found = {func for _line, func, _kw in self._calls()}
        missing = self.PROSE_FUNCTIONS - found
        assert not missing, f"这些函数在源码里找不到 chat 调用，守卫可能已失效：{missing}"


# ====================================================================== 闸 3：字数闸门不得被独白喂饱


class TestQualityGateRejectsPlanning:
    """字数闸门必须能识别"这是工作笔记"。

    事故里它把 4760 字独白算进字数 ⇒ 8029/4000 "达标" ⇒ 坏章通过。
    字数统计本身无法分辨正文与独白，只能靠规划检测在这里拦。
    """

    @staticmethod
    def _gate():
        from app.novel_agent import NovelAgent

        agent = NovelAgent.__new__(NovelAgent)
        agent.log = lambda _m: None
        return agent

    def test_planning_content_is_rejected_regardless_of_length(self):
        """内容足够长（远超目标字数）也必须判不合格 —— 长度不能成为豁免理由。"""
        polluted = TestPlanningDetection.POLLUTION_1 * 60
        has_rep, words = self._gate()._has_excessive_repetition(polluted, 4000)
        assert has_rep is True, "规划文字被字数掩盖了"
        assert words > 4000, "样本应长于目标字数，否则测不出'长度豁免'这个漏洞"

    def test_normal_prose_passes(self):
        """对照：正常正文不得被这道检查误伤。"""
        paragraphs = [
            f"第{i}段，秦纵把第{i}块炉砖码好，抬头看了看窑口的烟。风从北麓来，带着焦土味。" for i in range(40)
        ]
        content = "\n\n".join(paragraphs)
        has_rep, _words = self._gate()._has_excessive_repetition(content, 1000)
        assert has_rep is False, "正常正文被判为不合格（会触发无谓重写）"

    # ====================================================================== 闸 3：拒绝 reasoning 兜底class TestFinalizeTextContract:
    @staticmethod
    def _client() -> AIClient:
        # 只测 _finalize_text 这个纯函数，不发起网络请求
        return AIClient.__new__(AIClient)

    def _result(self, text: str = "", reasoning: str = "", finish: str = "") -> ChatResult:
        return ChatResult(text=text, reasoning=reasoning, finish_reason=finish)

    def test_normal_text_passes_through(self):
        client = self._client()
        assert client._finalize_text(self._result(text="正文"), "T", "m") == "正文"

    def test_reasoning_fallback_allowed_by_default(self):
        """v2 语义保留：分析类调用拿不到 content 时，返回 reasoning 比报错有用。"""
        client = self._client()
        out = client._finalize_text(self._result(reasoning="分析过程" * 5, finish="length"), "T", "m")
        assert out.startswith("分析过程")

    def test_reasoning_fallback_can_be_refused(self):
        """🔴 正文/评审：宁可报错，也不把工作笔记当成品。"""
        client = self._client()
        with pytest.raises(Exception) as exc:
            client._finalize_text(
                self._result(reasoning="用户希望我继续写" * 3, finish="length"),
                "T",
                "m",
                allow_reasoning_fallback=False,
            )
        message = str(exc.value)
        assert "思考模式耗尽" in message
        assert "reasoning_len" in message, "报错要带可诊断的数字"
        assert "max_tokens" in message, "报错要给出可操作的下一步"

    def test_empty_without_reasoning_still_raises(self):
        client = self._client()
        with pytest.raises(Exception):
            client._finalize_text(self._result(), "T", "m")


# ====================================================================== 大纲章号容错


class TestChapterNoCoercion:
    """`coerce_chapter_no`：AI 把章号返回成字符串是常态。"""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (1, 1),
            ("1", 1),
            (" 3 ", 3),
            ("第7章", 7),
            ("12.", 12),
            (2.0, 2),
            (None, None),
            ("", None),
            ("abc", None),
            (0, None),
            (-2, None),
            (True, None),
        ],
    )
    def test_coercion(self, value, expected):
        assert coerce_chapter_no(value) == expected

    @staticmethod
    def _code_without_comments_and_docstrings(rel: str) -> str:
        """取源码但**剔除注释与 docstring**。

        ❗ 这一步不能省：`coerce_chapter_no` 的说明文字里为解释原因引用了
        `item["chapter"] - 1`，直接正则匹配会把它当真实代码（实测误报过）。
        """
        source = (REPO / rel).read_text(encoding="utf-8")
        source = re.sub(r'"""[\s\S]*?"""', "", source)  # 去三引号块（含 docstring）
        kept = [line for line in source.splitlines() if not line.strip().startswith("#")]
        return "\n".join(kept)

    def test_outline_code_uses_coercion(self):
        """守卫：不得再出现 `item["chapter"] - 1` 这种裸算。

        它就是"大纲永不落盘、每章重建一次"的根因 ——
        字符串减整数抛 TypeError，被外层 except 吞掉，`write_outline` 从未执行。
        """
        code = self._code_without_comments_and_docstrings("app/generation_ui.py")
        assert 'item["chapter"] - 1' not in code, "出现了裸减：字符串章号会让整块落盘逻辑中断"
        assert "coerce_chapter_no(" in code

    def test_outline_persists_even_when_partially_applied(self):
        """`applied` 计数存在 ⇒ 只要有一条成功就落盘。"""
        code = self._code_without_comments_and_docstrings("app/generation_ui.py")
        assert "applied = 0" in code and "if applied:" in code
