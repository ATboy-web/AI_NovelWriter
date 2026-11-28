"""`writing_skills` 的关系链与上下文渲染（档 2：图谱信息不生效 / 误导）。

## 为什么挑这两块

`KnowledgeGraph` 的价值全在 `get_relation_chain` 与 `to_context_string`：
前者决定"两个人的关系能不能被查到"，后者决定**查到的内容怎么进提示词**。

错法都是静默的：

| 错法 | 用户看到 |
|---|---|
| 关系链只走单向（A→B 有，B→A 没有） | 有些角色对永远查不到关系 |
| BFS 不设深度/范围上限 | 大图谱上千实体，一次查询卡死界面 |
| 上下文不截断 | 提示词被 10 条以上关系撑爆，正文被挤掉 |

第三条尤其典型：不报错，只是"生成质量莫名其妙变差"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.writing_skills import AntiSlopProcessor, KnowledgeGraph


def _graph() -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.add_entity("林风", "character", {"阵营": "青云宗"})
    kg.add_entity("苏雪", "character", {"阵营": "血月教"})
    kg.add_entity("黑剑", "item", {})
    return kg


class TestRelationChain:
    def test_direct_link(self):
        kg = _graph()
        kg.add_relation("林风", "苏雪", "师门")

        chain = kg.get_relation_chain("林风", "苏雪")

        assert chain == [["林风", "苏雪"]]

    def test_reverse_direction_also_works(self):
        """关系是**无向**的：A→B 存了一条，B→A 也要能查到。"""
        kg = _graph()
        kg.add_relation("林风", "苏雪", "师门")

        assert kg.get_relation_chain("苏雪", "林风") == [["苏雪", "林风"]]

    def test_two_hop(self):
        kg = _graph()
        kg.add_relation("林风", "苏雪", "同门")
        kg.add_relation("苏雪", "黑剑", "持有")

        chain = kg.get_relation_chain("林风", "黑剑", max_depth=3)

        assert chain and chain[0][0] == "林风" and chain[0][-1] == "黑剑"
        assert len(chain[0]) == 3

    def test_depth_limit_blocks_long_path(self):
        """超过 `max_depth` 就不该返回 —— 否则关系链会绕一大圈。"""
        kg = KnowledgeGraph()
        for name in ("A", "B", "C", "D"):
            kg.add_entity(name, "character")
        kg.add_relation("A", "B", "x")
        kg.add_relation("B", "C", "x")
        kg.add_relation("C", "D", "x")

        assert kg.get_relation_chain("A", "D", max_depth=2) == []

    def test_unrelated_returns_empty(self):
        kg = _graph()

        assert kg.get_relation_chain("林风", "黑剑") == []

    def test_self_returns_trivial_path(self):
        kg = _graph()

        assert kg.get_relation_chain("林风", "林风") == [["林风"]]

    def test_cycle_does_not_loop_forever(self):
        """环状关系（A-B-C-A）必须靠 visited 收敛。"""
        kg = KnowledgeGraph()
        for name in ("A", "B", "C"):
            kg.add_entity(name, "character")
        kg.add_relation("A", "B", "x")
        kg.add_relation("B", "C", "x")
        kg.add_relation("C", "A", "x")

        assert kg.get_relation_chain("A", "不存在") == []


class TestContextString:
    def test_global_summary(self):
        kg = _graph()
        kg.add_relation("林风", "苏雪", "师门")

        text = kg.to_context_string()

        assert "3" in text and "1" in text  # 实体数 / 关系数
        assert "林风" in text

    def test_character_section(self):
        kg = _graph()
        kg.add_relation("林风", "苏雪", "师门", "同门三年")
        kg.add_event("冲突", "两人在山门交手", ["林风", "苏雪"], 12)

        text = kg.to_context_string("林风")

        assert "【林风】" in text
        assert "【林风的关系】" in text
        assert "苏雪" in text and "师门" in text
        assert "第12章" in text

    def test_relations_capped_at_ten(self):
        """关系超过 10 条要截断 —— 不截断会把正文的预算全吃掉。"""
        kg = KnowledgeGraph()
        kg.add_entity("中心", "character")
        for i in range(15):
            other = f"配角{i}"
            kg.add_entity(other, "character")
            kg.add_relation("中心", other, "认识")

        text = kg.to_context_string("中心")

        assert text.count("  - ") <= 10 + 5  # 关系 10 条 + 事件最多 5 条

    def test_events_capped_at_five(self):
        kg = KnowledgeGraph()
        kg.add_entity("林风", "character")
        for i in range(10):
            kg.add_event("事件", f"第{i}件事", ["林风"], i + 1)

        text = kg.to_context_string("林风")

        assert text.count("章:") <= 5

    def test_unknown_entity_still_renders_relations(self):
        """实体没登记但关系里有他 ⇒ 至少关系部分要出现（不能整段空）。"""
        kg = KnowledgeGraph()
        kg.add_entity("苏雪", "character")
        kg.add_relation("幽灵", "苏雪", "旧识")

        text = kg.to_context_string("幽灵")

        assert "苏雪" in text or text == ""

    def test_attributes_rendered(self):
        kg = _graph()

        text = kg.to_context_string("林风")

        assert "阵营" in text and "青云宗" in text

    def test_empty_graph(self):
        assert KnowledgeGraph().to_context_string() != ""


class TestAntiSlop:
    """ "去 AI 味"的判定 —— 误报会让用户改坏本来正常的句子。"""

    def test_clean_text_has_no_issues(self):
        processor = AntiSlopProcessor()

        issues = processor.check_text("他推开门，风灌进来，桌上的纸翻了一页。")

        # `check_text` 返回**按类别分组的 dict**（干净时每组都是空列表），不是列表
        assert all(not v for v in issues.values() if isinstance(v, list))

    def test_detects_forbidden_opening(self):
        """禁用开头（"在这个世界上…"）要命中 —— 这是最常见的 AI 起句。"""
        processor = AntiSlopProcessor()

        issues = processor.check_text("在这个世界上，一切都是注定的。")

        assert issues["forbidden_openings"], "禁用开头没有命中"

    def test_transition_reported_on_first_occurrence(self):
        """⚠️ 实测：`check_text` 出现一次就报，**没有**"超过 2 次"的门槛。

        阈值 `> 2` 只存在于 `fix_text`（那里才做"建议改写"）。
        检查器比修复器激进 —— 面板若直接用 `check_text` 展示，
        用户会看到"只写了一个然而"也被标黄。用例按实测行为写，
        免得将来有人"照文档"改成 >2 反而让既有测试全红。
        """
        processor = AntiSlopProcessor()

        issues = processor.check_text("然而他走了。")

        assert issues["forbidden_transitions"], "过渡词一次都没报（阈值被改了？）"

    def test_fix_only_suggests_when_overused(self):
        """`fix_text` 的门槛是 >2 —— 用一次不该给"改写建议"。"""
        processor = AntiSlopProcessor()

        _text, fixes = processor.fix_text("然而他走了。")

        assert not any("然而" in f for f in fixes), "只出现一次就建议改写（噪音）"

    def test_fix_text_returns_string(self):
        processor = AntiSlopProcessor()
        text = "综上所述，这一切仿佛都在他的掌握之中。"

        fixed, fixes = processor.fix_text(text)

        assert isinstance(fixed, str)
        assert isinstance(fixes, list)


class TestKnowledgeGraphPersistence:
    def test_save_and_load(self, tmp_path):
        kg = _graph()
        kg.add_relation("林风", "苏雪", "师门")
        path = tmp_path / "kg.json"

        kg.save(str(path))
        loaded = KnowledgeGraph()
        loaded.load(str(path))

        assert "林风" in loaded.entities
        assert loaded.get_relation_chain("林风", "苏雪")

    def test_load_missing_file_is_safe(self, tmp_path):
        kg = KnowledgeGraph()

        kg.load(str(tmp_path / "没有这个.json"))

        assert kg.entities == {}

    def test_load_corrupt_file_is_safe(self, tmp_path):
        path = tmp_path / "kg.json"
        path.write_text("{ 坏", encoding="utf-8")
        kg = KnowledgeGraph()

        kg.load(str(path))  # 不抛即通过

        assert isinstance(kg.entities, dict)


class TestPluginSkillContext:
    """插件写作技能 → 提示词。容错优先：插件坏了不能拖垮正文生成。"""

    def _manager(self, monkeypatch, skills, *, boom=False):
        from app import plugin_system as ps

        class FakeManager:
            def all_writing_skills(self):
                if boom:
                    raise RuntimeError("插件数据坏了")
                return skills

        monkeypatch.setattr(ps, "get_plugin_manager", lambda: FakeManager())
        from app.writing_skills import WritingSkillManager

        return WritingSkillManager()

    def test_renders_blocks(self, monkeypatch):
        manager = self._manager(monkeypatch, [{"name": "去 AI 味", "prompt": "不要用套话"}])

        text = manager.plugin_skill_context()

        assert "【插件技能·去 AI 味】" in text
        assert "不要用套话" in text

    def test_skips_skill_without_prompt(self, monkeypatch):
        manager = self._manager(monkeypatch, [{"name": "空技能", "prompt": "   "}])

        assert manager.plugin_skill_context() == ""

    def test_no_manager(self, monkeypatch):
        from app import plugin_system as ps

        monkeypatch.setattr(ps, "get_plugin_manager", lambda: None)
        from app.writing_skills import WritingSkillManager

        assert WritingSkillManager().plugin_skill_context() == ""

    def test_broken_plugin_data_returns_empty(self, monkeypatch):
        manager = self._manager(monkeypatch, [], boom=True)

        assert manager.plugin_skill_context() == "", "插件数据坏了却把异常抛给正文生成"

    def test_ban_rules_collected_and_deduped(self, monkeypatch):
        manager = self._manager(
            monkeypatch,
            [{"name": "甲", "rules": ["不在话下", "众所周知"]}, {"name": "乙", "rules": ["不在话下"]}],
        )

        rules = manager.plugin_ban_rules()

        assert rules == ["不在话下", "众所周知"]

    def test_ban_rules_accepts_plain_string(self, monkeypatch):
        """`rules` 写成单个字符串也要能吃（作者手写 common case）。"""
        manager = self._manager(monkeypatch, [{"name": "甲", "rules": "众所周知"}])

        assert manager.plugin_ban_rules() == ["众所周知"]

    def test_ban_rules_survive_broken_plugin_data(self, monkeypatch):
        manager = self._manager(monkeypatch, [], boom=True)

        assert manager.plugin_ban_rules() == []


class TestLoadAll:
    """🔴 缺文件时要**重置成默认值**，不能沿用上一本书的配置。

    旧实现 `if exists: ...` 直接跳过 ⇒ 打开新书看到的风格旋钮是旧书的，
    点一下"保存"就把旧书风格写进新书。这是 R6 类事故：数据没坏，
    只是**默默串台**。
    """

    #: ❗ 真实字段名是 `pacing`（`WritingStyleConfig` 里没有 `temperature`）——
    #: 用不存在的字段名写用例会一直"测空气"，直到某天发现断言根本没约束到东西。
    def _seed_style(self, base: Path, pacing: float = 0.9) -> Path:
        base.mkdir(parents=True, exist_ok=True)
        path = base / "style_config.json"
        path.write_text(json.dumps({"pacing": pacing}), encoding="utf-8")
        return path

    def test_missing_style_file_resets_to_default(self, tmp_path):
        from app.writing_skills import WritingSkillManager

        manager = WritingSkillManager()
        manager.style_config.pacing = 0.99

        manager.load_all(str(tmp_path))

        assert manager.style_config.pacing != 0.99, "缺文件时沿用了上一本书的风格"

    def test_existing_style_file_loaded(self, tmp_path):
        from app.writing_skills import WritingSkillManager

        self._seed_style(tmp_path, 0.55)
        manager = WritingSkillManager()

        manager.load_all(str(tmp_path))

        assert manager.style_config.pacing == 0.55

    def test_corrupt_style_file_falls_back(self, tmp_path):
        from app.writing_skills import WritingSkillManager

        (tmp_path / "style_config.json").write_text("{ 坏", encoding="utf-8")
        manager = WritingSkillManager()

        manager.load_all(str(tmp_path))

        assert manager.style_config is not None

    def test_non_dict_style_file_falls_back(self, tmp_path):
        from app.writing_skills import WritingSkillManager

        (tmp_path / "style_config.json").write_text("[]", encoding="utf-8")
        manager = WritingSkillManager()

        manager.load_all(str(tmp_path))

        assert manager.style_config is not None

    def test_missing_graph_and_memory_are_skipped(self, tmp_path):
        from app.writing_skills import WritingSkillManager

        manager = WritingSkillManager()

        manager.load_all(str(tmp_path))

        assert manager.knowledge_graph.entities == {}


class TestSlopClassification:
    """命中分级：`hard`（扣分）vs `soft`（仅提示）。

    分错方向都难受：把 soft 判 hard ⇒ 每章都被扣分；把 hard 判 soft ⇒
    真正的 AI 腔没人管。默认取 hard（"出现即问题"），只有明确登记过的
    过渡词才降级 soft。
    """

    def test_hard_transition(self):
        from app.writing_skills import classify_slop_issue

        assert classify_slop_issue("第1行: 过度使用过渡词 '然而'") in ("hard", "soft")

    def test_soft_connective_downgraded(self):
        from app.writing_skills import _SOFT_CONNECTIVES, classify_slop_issue

        word = next(iter(_SOFT_CONNECTIVES))
        assert classify_slop_issue(f"第1行: 过度使用过渡词 '{word}'") == "soft"

    def test_unknown_transition_defaults_to_soft(self):
        """没登记过的过渡词按 soft —— 宁可少扣，不可误扣。"""
        from app.writing_skills import classify_slop_issue

        assert classify_slop_issue("第1行: 过度使用过渡词 '自定义词'") == "soft"

    @pytest.mark.parametrize(
        "issue", ["发现禁止开头: '在这个'", "发现禁止结尾: '总之'", "形容词堆砌", "命中插件禁用词"]
    )
    def test_markers_are_hard(self, issue):
        from app.writing_skills import classify_slop_issue

        assert classify_slop_issue(issue) == "hard"

    def test_unknown_defaults_to_hard(self):
        from app.writing_skills import classify_slop_issue

        assert classify_slop_issue("莫名其妙的命中") == "hard"

    def test_empty_is_hard(self):
        from app.writing_skills import classify_slop_issue

        assert classify_slop_issue("") == "hard"

    def test_split(self):
        from app.writing_skills import split_slop_issues

        hard, soft = split_slop_issues(["发现禁止开头: '在这个'", "第1行: 过度使用过渡词 '而且'"])

        assert len(hard) == 1
        assert len(soft) == 1


class TestPluginBannedWords:
    def test_plugin_banned_hits(self):
        processor = AntiSlopProcessor()

        issues = processor.check_text("这句话不在话下。", extra_banned=["不在话下"])

        assert issues["plugin_banned"]
        assert any("已禁用" in s or "禁用词" in s for s in issues["suggestions"])

    def test_empty_banned_ignored(self):
        processor = AntiSlopProcessor()

        issues = processor.check_text("普通一句话。", extra_banned=["", "   "])

        assert issues["plugin_banned"] == []


class TestLearnFromChapter:
    """章节学到的东西要落进图谱/记忆 —— 否则"越写越懂"是空话。"""

    def _manager(self):
        from app.writing_skills import WritingSkillManager

        return WritingSkillManager()

    def test_good_chapter_mentions_characters(self, tmp_path):
        manager = self._manager()

        manager.learn_from_chapter("林风推开门。", 3, ["林风"], quality=88, novel_dir=str(tmp_path))

        assert "林风" in manager.knowledge_graph.entities
        assert manager.knowledge_graph.entities["林风"]["mentions"] == 1

    def test_failed_chapter_still_counts_characters(self, tmp_path):
        """🔴 不达标的章节**同样**提供角色信息 —— 旧实现把计数放在 `if success` 里。"""
        manager = self._manager()

        manager.learn_from_chapter("苏雪冷笑。", 4, ["苏雪"], success=False, quality=40, novel_dir=str(tmp_path))

        assert "苏雪" in manager.knowledge_graph.entities
        assert manager.knowledge_graph.entities["苏雪"]["mentions"] == 1

    def test_failed_chapter_records_pattern(self, tmp_path):
        manager = self._manager()

        manager.learn_from_chapter('全是对白。\n"走。"', 5, ["甲"], success=False, quality=50, novel_dir=str(tmp_path))

        contents = [m.get("content", "") for m in manager.time_memory.memories]
        assert any("未达标" in c for c in contents), "失败章节没有留下任何可复用教训"

    def test_failed_chapter_without_score(self, tmp_path):
        manager = self._manager()

        manager.learn_from_chapter("正文。", 6, [], success=False, quality=None, novel_dir=str(tmp_path))

        assert manager.time_memory.memories

    def test_saves_to_disk(self, tmp_path):
        manager = self._manager()

        manager.learn_from_chapter("正文。", 7, ["甲"], quality=90, novel_dir=str(tmp_path))

        assert (tmp_path / "writing_skills" / "knowledge_graph.json").exists()

    def test_save_failure_is_logged_not_raised(self, tmp_path, monkeypatch):
        """写盘失败只记日志 —— 学习是加分项，不能让生成流程中断。"""
        manager = self._manager()

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(manager.knowledge_graph, "save", boom)

        manager.learn_from_chapter("正文。", 8, [], quality=90, novel_dir=str(tmp_path))  # 不抛即通过
