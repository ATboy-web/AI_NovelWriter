"""自我学习闭环回归测试（P-04 / P-04b）。

背景（见 `docs/AGENT_OPTIMIZATION_PLAN.md`）：项目自称有自我学习，实测为
**L0（只写不读）**，三个断点：

| 断点 | 位置 | 现象 |
|---|---|---|
| **信号假** | `novel_agent.finalize_chapter` | `success=True` 硬编码 ⇒ `if success:` 包住全部学习逻辑 ⇒ 形参等于没有，负样本永远进不来 |
| **内容贫** | `writing_skills.learn_from_chapter` | 只写 `success_pattern`、`importance` 恒 0.6，且该类型**全仓无读取方** |
| **读不到** | `writing_skills.get_writing_context` | 完全忽略 `chapter` 形参；`query()` 纯子串匹配 + 只按 importance 排序，无时间维度 |

本文件锁定这三处的修复不被回退。
"""

import inspect

from app.novel_agent import NovelAgent
from app.writing_skills import TimeAwareMemory, WritingSkillManager


def _code_only(func) -> str:
    """函数源码剔除注释行（修复说明里会提到旧写法）。"""
    src = inspect.getsource(func)
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


# --------------------------------------------------------------------------
# 信号假：success 必须来自真实评分
# --------------------------------------------------------------------------


class TestSuccessSignalIsReal:
    def test_no_hardcoded_success_true_in_finalize(self):
        """`finalize_chapter` 里不得再有 `success=True` 字面量。"""
        src = _code_only(NovelAgent.finalize_chapter)
        assert "success=True" not in src, "success 又被硬编码了 —— P-04 回退"

    def test_quality_parameter_exists(self):
        sig = inspect.signature(NovelAgent.finalize_chapter)
        assert "quality" in sig.parameters, "finalize_chapter 缺少 quality 形参"
        assert sig.parameters["quality"].default is None

    def test_instance_holds_last_quality(self):
        """生成流程把评分记在实例上（4 个定稿调用点里只有生成流程拿得到分数）。"""
        assert "last_chapter_quality" in inspect.getsource(NovelAgent.__init__), "未在 __init__ 初始化"

    def test_generate_flow_records_review_score(self):
        src = inspect.getsource(NovelAgent.generate_with_collaboration)
        assert "last_chapter_quality" in src, "生成流程没把评分写回实例"

    def test_learn_from_chapter_accepts_quality(self):
        sig = inspect.signature(WritingSkillManager.learn_from_chapter)
        assert "quality" in sig.parameters, "learn_from_chapter 缺少 quality 形参"
        assert sig.parameters["quality"].default is None


class TestQualityAffectsImportance:
    """评分必须真的改变写入结果，而不是只多存一个字段。"""

    def _mgr(self):
        return WritingSkillManager()

    def test_higher_score_gives_higher_importance(self):
        low, high = self._mgr(), self._mgr()
        low.learn_from_chapter("内容", 1, [], success=True, quality=60)
        high.learn_from_chapter("内容", 1, [], success=True, quality=100)
        low_imp = low.time_memory.memories[0]["importance"]
        high_imp = high.time_memory.memories[0]["importance"]
        assert high_imp > low_imp, f"评分 100({high_imp}) 应比 60({low_imp}) 权重更高"

    def test_unknown_quality_keeps_legacy_weight(self):
        """quality=None 时必须保持旧的 0.6 —— 不改变既有行为。"""
        mgr = self._mgr()
        mgr.learn_from_chapter("内容", 1, [], success=True, quality=None)
        assert mgr.time_memory.memories[0]["importance"] == 0.6

    def test_failure_is_recorded_as_failure_pattern(self):
        """R21 变更：未达标章节**不再什么都不做**。

        旧契约（`test_failure_records_nothing`）认为"不写入"就是对的，但那只把
        "信号假"从"假装成功"换成了"假装学了" —— 调用点会打印
        "已学习第N章模式（评分60·未达标）"，实际一条都没写，**负样本仍然进不来**。
        新契约：成败分开存放，成功进 `success_pattern`（用于照做），
        失败进 `failure_pattern`（用于避开）。
        """
        mgr = self._mgr()
        mgr.learn_from_chapter("内容", 1, [], success=False, quality=10)
        types = [m["type"] for m in mgr.time_memory.memories]
        assert types == ["failure_pattern"], f"未达标章节应记为 failure_pattern，实际 {types}"

    def test_failure_not_mixed_into_success_pattern(self):
        """负样本绝不能混进成功库，否则"照做"会照做错的。"""
        mgr = self._mgr()
        mgr.learn_from_chapter("好内容", 1, [], success=True, quality=90)
        mgr.learn_from_chapter("差内容", 2, [], success=False, quality=30)
        wins = mgr.time_memory.query(memory_type="success_pattern", limit=10)
        assert all("第2章" not in m["content"] for m in wins), "失败章节混进了 success_pattern"

    def test_failure_weight_rises_as_score_drops(self):
        """分数越低越该被记住（权重反向浮动）。"""
        bad, worse = self._mgr(), self._mgr()
        bad.learn_from_chapter("内容", 1, [], success=False, quality=70)
        worse.learn_from_chapter("内容", 1, [], success=False, quality=10)
        b = bad.time_memory.memories[0]["importance"]
        w = worse.time_memory.memories[0]["importance"]
        assert w > b, f"10 分({w}) 应比 70 分({b}) 更该被记住"

    def test_empty_content_writes_nothing(self):
        """R21：空/空白正文不产生学习价值，不得写入脏记忆。"""
        mgr = self._mgr()
        for bad in ("", "   ", "\n\n"):
            mgr.learn_from_chapter(bad, 1, [], success=True, quality=90)
        assert mgr.time_memory.memories == [], f"空正文写入了 {len(mgr.time_memory.memories)} 条脏记忆"

    def test_characters_counted_even_on_failure(self):
        """角色提及与成败无关 —— 旧实现把它放在 `if success:` 里，失败章节不计。"""
        mgr = self._mgr()
        mgr.learn_from_chapter("内容", 1, ["张三"], success=False, quality=10)
        assert "张三" in mgr.knowledge_graph.entities, "失败章节也应记录角色提及"

    def test_score_recorded_in_content_and_tags(self):
        mgr = self._mgr()
        mgr.learn_from_chapter("内容", 7, [], success=True, quality=88)
        mem = mgr.time_memory.memories[0]
        assert "88" in mem["content"]
        assert "score:88" in mem["tags"]


# --------------------------------------------------------------------------
# 读不到：chapter 必须真的参与检索
# --------------------------------------------------------------------------


class TestChapterIsUsedInRetrieval:
    def test_get_writing_context_uses_chapter(self):
        src = _code_only(WritingSkillManager.get_writing_context)
        assert "chapter" in src, "get_writing_context 又忽略了 chapter 形参"

    def test_query_signature_has_chapter(self):
        sig = inspect.signature(TimeAwareMemory.query)
        assert "chapter" in sig.parameters
        assert "chapter_window" in sig.parameters

    def test_distant_chapter_memory_is_filtered_out(self):
        mem = TimeAwareMemory()
        for ch in (3, 87, 120):
            mem.add_memory(f"第{ch}章经验", "success_pattern", importance=0.6, chapter=ch)
        near = mem.query(chapter=120, chapter_window=50)
        chapters = {m["chapter"] for m in near}
        assert chapters == {87, 120}, f"窗口=50 应排除第 3 章，实际 {chapters}"

    def test_unannotated_memory_is_not_filtered(self):
        """`chapter=0`（未标注）的记忆不得被窗口过滤掉 —— 避免静默清空旧数据。"""
        mem = TimeAwareMemory()
        mem.add_memory("无章节经验的规则", "style_rule", importance=0.6)
        mem.add_memory("第200章经验", "success_pattern", importance=0.6, chapter=200)
        got = mem.query(chapter=1, chapter_window=10)
        assert any(m["content"] == "无章节经验的规则" for m in got), "未标注章节的记忆被误过滤"

    def test_no_chapter_means_no_filtering(self):
        """不传 chapter 时行为与旧版一致（全量 + 按 importance）。"""
        mem = TimeAwareMemory()
        mem.add_memory("第3章", "success_pattern", importance=0.6, chapter=3)
        mem.add_memory("第900章", "success_pattern", importance=0.6, chapter=900)
        assert len(mem.query()) == 2

    def test_success_pattern_is_actually_read_back(self):
        """P-04b 关键：`success_pattern` 必须有读取方（旧实现写入后无人读）。"""
        src = _code_only(WritingSkillManager.get_writing_context)
        assert "success_pattern" in src, "success_pattern 又没有读取方了"
        assert "【近期成功模式】" in src


class TestRetrievalWiring:
    def test_agent_passes_chapter_to_get_writing_context(self):
        """`_build_context` 必须把 chapter_num 传下去。"""
        src = inspect.getsource(NovelAgent._build_context)
        assert "get_writing_context(chapter=chapter_num)" in src, "chapter 又没传"
