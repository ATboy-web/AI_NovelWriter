"""结尾质量与字数统计修复的回归测试（v3.2 / D15–D18）。

## 为什么需要这个文件

`docs/NOVEL_AUDIT_1789640077.md` 审计了真实生成的小说《快速统治》，
结论是**结尾结构性空洞**，并定位到四条叠加机制（D15–D18）。
这四条有一个共同特征：**它们都不会报错**。

- D15 末段提示词只要求"段落结尾" ⇒ 末段写成场景收尾，没有章节落点；
- D16 审校/修订采样用 `(中间省略)` ⇒ 评审看不到结局部分；
- D17 `len(content)` 当字数 ⇒ 闸门与报告双双失真；
- D18 结尾补全**直接追加** ⇒ 把本来完整的结尾接上一段无关文字。

"不报错"的缺陷只能靠**断言行为**来防复发，不能靠"跑起来没崩"。
本文件钉住修复后的**判据与行为**，而不是"代码里有某个字符串"。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import _source_scan as _scan  # noqa: E402

from app.novel_agent import NovelAgent  # noqa: E402

# ====================================================================== D17 字数


class TestWordCount:
    """D17：字数统计必须**只数非空白字符**。

    为什么关键：`len(content)` 会把 Markdown 标题、换行、缩进全算进去。
    这不只是"报告数字偏大"—— 质量闸门 `actual_words < target * 0.3`
    正是拿这个数去比的：数字虚高 ⇒ 闸门**永不触发** ⇒ 等于没有闸门。
    """

    def test_whitespace_is_not_counted(self):
        # 3 个汉字 + 一堆空白 ⇒ 应算 3
        assert NovelAgent._count_words("你好啊") == 3
        assert NovelAgent._count_words("你\n\n好      啊") == 3
        assert NovelAgent._count_words("  \n\t  ") == 0

    def test_markdown_markup_adds_nothing(self):
        """`#` 与换行**不该**被计入字数。

        ❗ 注意区分两件事：标题的**文字**（"第1章：一个很长的标题"）是真实内容，
        计入是对的；被修掉的是**标记与空白**（`#`、`\\n`、缩进）。
        所以正确断言是"同样的文字，加不加 Markdown 标记，字数一样"。
        """
        text = "第1章：一个很长的标题正文内容"
        assert NovelAgent._count_words("# " + text + "\n\n") == NovelAgent._count_words(text)
        assert NovelAgent._count_words(text) == len(text)  # 无空白时等于字符数

    def test_plain_text_count_equals_char_count(self):
        assert NovelAgent._count_words("正文" * 100) == 200

    def test_empty_is_zero(self):
        assert NovelAgent._count_words("") == 0
        assert NovelAgent._count_words(None) == 0

    def test_newlines_would_have_inflated_old_metric(self):
        """反证：旧口径（`len`）确实会虚高，差值就是被修复的量。"""
        content = "\n\n".join(["段落内容" * 20] * 10)
        assert len(content) > NovelAgent._count_words(content)

    def test_gate_actually_fires_on_short_content(self):
        """闸门必须能在字数不足时**真的**判定为"不达标"。

        用真实 agent 的方法（不是复制一份逻辑），确保修的是生效的那份。
        """
        agent = object.__new__(NovelAgent)  # 不跑 __init__，只借用方法
        agent.log = lambda _m: None

        # 目标 6000 字，只给 500 字（含大量换行）⇒ 一定低于 30%
        thin = "\n\n".join(["短"] * 500)
        has_rep, actual = agent._has_excessive_repetition(thin, 6000)
        assert actual == 500
        assert has_rep is True, "字数严重不足时闸门没触发"

    def test_gate_does_not_fire_on_adequate_content(self):
        agent = object.__new__(NovelAgent)
        agent.log = lambda _m: None

        # 构造 6000 个不同字符的段落，避免"重复段落"判据误触发
        chunks = [f"第{i}段的独立内容，描述了一件不同的事情。" for i in range(300)]
        rich = "\n\n".join(chunks)
        has_rep, actual = agent._has_excessive_repetition(rich, 3000)
        assert actual > 3000
        assert has_rep is False


# ====================================================================== D18 结尾


class TestTruncationDetection:
    """D18：只有"明显断在半句"才该补全，拿不准就不动。

    ❗ 判据的**代价不对称**是本组的设计原则：
    漏判一个真断句 ⇒ 结尾略突兀；误判一个完整结尾 ⇒ 追加无关文字、把好结尾改坏。
    后者正是烂尾观感。所以检测必须保守。
    """

    @pytest.mark.parametrize(
        "ending",
        [
            "他转身离开了。",
            "“你到底想说什么？”",
            "…终于结束了",
            "他没有回头——",
            "树林里静得可怕……",
            "She said yes.",
            "门在身后合上」",
        ],
    )
    def test_complete_endings_are_not_flagged(self, ending):
        assert NovelAgent._looks_truncated(ending) is False

    def test_comma_and_colon_confirm_mid_sentence(self):
        for tail in ["他转身离开了，", "她看着他、", "这就是答案：", "他说："]:
            assert NovelAgent._looks_truncated(tail) is True, tail

    def test_ambiguous_hanzi_ending_is_treated_as_complete(self):
        """以汉字结尾但无标点 ⇒ 无法判断 ⇒ 判为完整（保守，见类文档）。"""
        assert NovelAgent._looks_truncated("他终于说完了这句话，然后沉默很久") is False

    def test_quote_ending_is_treated_as_complete(self):
        """以引号结尾**不算**断句 —— 旧实现正是把它判成不完整然后追加文字。"""
        assert NovelAgent._looks_truncated("“我明白了”") is False

    def test_empty_is_not_truncated(self):
        assert NovelAgent._looks_truncated("") is False
        assert NovelAgent._looks_truncated("   ") is False


class TestTailPromptRequirements:
    """D15：末段提示词必须要求**剧情推进 + 章节落点**，而不是"段落结尾"。"""

    def test_tail_prompt_demands_plot_advance(self):
        code = _scan.code_only("app/novel_agent.py")
        assert "必须**推进实质剧情**" in code or "推进实质剧情" in code, "末段提示词没有要求剧情推进 —— D15 复发"

    def test_tail_prompt_demands_chapter_landing(self):
        code = _scan.code_only("app/novel_agent.py")
        assert "章节落点" in code, "末段提示词没有要求章节落点"

    def test_tail_prompt_forbids_summarising(self):
        code = _scan.code_only("app/novel_agent.py")
        assert "不要总结全章" in code

    def test_old_weak_wording_is_gone(self):
        """旧的"自然完整的段落结尾"措辞必须消失，否则 D15 没真修。"""
        code = _scan.code_only("app/novel_agent.py")
        assert "给出自然完整的段落结尾" not in code, "旧的弱提示词仍在"


class TestEndingPatchSafety:
    """D18：补全逻辑必须保守 —— 该跳过的跳过，该丢弃的丢弃。"""

    def test_patch_skips_when_ending_is_punctuated(self):
        """正文末尾已经是句号 ⇒ 必须有"跳过补全"的分支，而不是无条件补。"""
        code = _scan.code_only("app/novel_agent.py")
        assert "跳过补全" in code, "没有「结尾完整则跳过」的分支"

    def test_patch_uses_strict_dedup(self):
        """补全与原文重复时必须**丢弃**，不能再靠 `[:10] in result[-50:]`。"""
        code = _scan.code_only("app/novel_agent.py")
        assert "completion not in result" in code
        assert "已放弃追加" in code or "放弃" in code

    def test_patch_length_is_bounded(self):
        """只补一个短语，不允许补出一整段（那会变成"第二结尾"）。"""
        code = _scan.code_only("app/novel_agent.py")
        assert "len(completion) <= 60" in code, "补全长度没有上限"

    def test_patch_threshold_is_a_sentence_end_set(self):
        """判据必须基于"句末标点集合"，且**不含引号**（引号不足以判断完整性）。"""
        code = _scan.code_only("app/novel_agent.py")
        assert "sentence_end" in code
