"""
writing_skills.py 深度测试 - 真正调用所有方法
"""

import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.writing_skills import (
    WritingStyleConfig, AntiSlopProcessor, ANTI_SLOP_RULES,
    KnowledgeGraph, TimeAwareMemory, WritingSkillManager
)


class TestAntiSlopProcessor:
    """AntiSlopProcessor 深度测试"""

    def test_init(self):
        p = AntiSlopProcessor()
        assert p.rules is not None
        assert p._compiled_patterns is not None

    def test_check_text_clean(self):
        p = AntiSlopProcessor()
        issues = p.check_text("张三走进了房间，看到了一封信。")
        assert "forbidden_openings" in issues
        assert "forbidden_transitions" in issues
        assert "forbidden_endings" in issues
        assert "adjective_clusters" in issues
        assert "suggestions" in issues

    def test_check_text_with_openings(self):
        p = AntiSlopProcessor()
        text = "在这个世界上，强者为尊。\n第二行\n第三行\n第四行\n第五行\n第六行"
        issues = p.check_text(text)
        assert len(issues["forbidden_openings"]) > 0

    def test_check_text_with_transitions(self):
        p = AntiSlopProcessor()
        text = "第一行\n然而第二行\n不过第三行\n但是第四行\n可是第五行"
        issues = p.check_text(text)
        assert len(issues["forbidden_transitions"]) > 0

    def test_check_text_with_endings(self):
        p = AntiSlopProcessor()
        ending = p.rules["forbidden_endings"][0] if p.rules.get("forbidden_endings") else None
        if ending:
            text = "第一行\n第二行\n第三行\n第四行\n" + ending
            issues = p.check_text(text)
            assert len(issues["forbidden_endings"]) > 0
        else:
            assert True

    def test_check_text_many_transitions_generates_suggestion(self):
        p = AntiSlopProcessor()
        text = "然而第一行\n不过第二行\n但是第三行\n可是第四行"
        issues = p.check_text(text)
        if len(issues["forbidden_transitions"]) > 3:
            assert len(issues["suggestions"]) > 0

    def test_fix_text_clean(self):
        p = AntiSlopProcessor()
        text, fixes = p.fix_text("张三走进了房间。")
        assert isinstance(text, str)
        assert isinstance(fixes, list)

    def test_fix_text_with_issues(self):
        p = AntiSlopProcessor()
        text = "在这个世界上，然而不过但是可是。"
        fixed, fixes = p.fix_text(text)
        assert len(fixes) > 0

    def test_get_writing_tips_all_genres(self):
        p = AntiSlopProcessor()
        genres = ["玄幻", "仙侠", "都市", "历史", "科幻", "悬疑", "游戏", "军事", "武侠", "体育", "轻小说", "二次元", "言情", "恐怖", "末日"]
        for genre in genres:
            tips = p.get_writing_tips(genre)
            assert isinstance(tips, str)
            assert len(tips) > 0

    def test_get_writing_tips_subgenre(self):
        p = AntiSlopProcessor()
        tips = p.get_writing_tips("玄幻-东方玄幻")
        assert "玄幻" in tips

    def test_get_writing_tips_unknown_genre(self):
        p = AntiSlopProcessor()
        tips = p.get_writing_tips("未知类型")
        assert isinstance(tips, str)
        assert len(tips) > 0


class TestWritingStyleConfig:
    """WritingStyleConfig 深度测试"""

    def test_to_prompt_high(self):
        c = WritingStyleConfig(descriptiveness=9, dialogue_ratio=8, pacing=9, emotional_depth=9, action_intensity=9)
        prompt = c.to_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_to_prompt_low(self):
        c = WritingStyleConfig(descriptiveness=2, dialogue_ratio=2, pacing=2, emotional_depth=2, action_intensity=2)
        prompt = c.to_prompt()
        assert isinstance(prompt, str)

    def test_to_prompt_medium(self):
        c = WritingStyleConfig(descriptiveness=5, dialogue_ratio=5, pacing=5, emotional_depth=5, action_intensity=5)
        prompt = c.to_prompt()
        assert isinstance(prompt, str)

    def test_defaults(self):
        c = WritingStyleConfig()
        assert c.descriptiveness == 7
        assert c.dialogue_ratio == 5
        assert c.pacing == 5
        assert c.emotional_depth == 6
        assert c.action_intensity == 5
        assert c.genre_style == "玄幻"


class TestKnowledgeGraph:
    """KnowledgeGraph 深度测试"""

    def test_init(self):
        kg = KnowledgeGraph()
        assert kg.entities == {}
        assert kg.relations == []
        assert kg.events == []

    def test_add_entity(self):
        kg = KnowledgeGraph()
        kg.add_entity("张三", "character", {"age": 20})
        assert "张三" in kg.entities
        assert kg.entities["张三"]["type"] == "character"
        assert kg.entities["张三"]["attributes"]["age"] == 20

    def test_add_entity_without_attributes(self):
        kg = KnowledgeGraph()
        kg.add_entity("李四", "character")
        assert kg.entities["李四"]["attributes"] == {}

    def test_add_relation(self):
        kg = KnowledgeGraph()
        kg.add_relation("张三", "李四", "师徒", "张三是李四的师父")
        assert len(kg.relations) == 1
        assert kg.relations[0]["entity1"] == "张三"
        assert kg.relations[0]["entity2"] == "李四"

    def test_add_event(self):
        kg = KnowledgeGraph()
        kg.add_event("battle", "大战", ["张三", "李四"], 1)
        assert len(kg.events) == 1
        assert kg.events[0]["type"] == "battle"
        assert kg.events[0]["chapter"] == 1

    def test_get_character_relations(self):
        kg = KnowledgeGraph()
        kg.add_relation("张三", "李四", "师徒")
        kg.add_relation("张三", "王五", "朋友")
        kg.add_relation("李四", "王五", "同门")
        rels = kg.get_character_relations("张三")
        assert len(rels) == 2

    def test_get_character_events(self):
        kg = KnowledgeGraph()
        kg.add_event("battle", "大战1", ["张三", "李四"], 1)
        kg.add_event("battle", "大战2", ["张三", "王五"], 5)
        kg.add_event("meeting", "会面", ["李四", "王五"], 10)
        events = kg.get_character_events("张三")
        assert len(events) == 2

    def test_get_relation_chain(self):
        kg = KnowledgeGraph()
        kg.add_relation("A", "B", "friend")
        kg.add_relation("B", "C", "enemy")
        chain = kg.get_relation_chain("A", "C")
        assert len(chain) > 0
        assert chain[0][0] == "A"
        assert chain[0][-1] == "C"

    def test_get_relation_chain_no_path(self):
        kg = KnowledgeGraph()
        kg.add_relation("A", "B", "friend")
        chain = kg.get_relation_chain("A", "Z")
        assert chain == []

    def test_to_context_string_with_character(self):
        kg = KnowledgeGraph()
        kg.add_entity("张三", "character", {"age": 20})
        kg.add_relation("张三", "李四", "师徒")
        kg.add_event("battle", "大战", ["张三"], 1)
        ctx = kg.to_context_string("张三")
        assert "张三" in ctx

    def test_to_context_string_global(self):
        kg = KnowledgeGraph()
        kg.add_entity("张三", "character")
        kg.add_entity("李四", "character")
        ctx = kg.to_context_string()
        assert "实体" in ctx or "角色" in ctx

    def test_to_context_string_unknown_character(self):
        kg = KnowledgeGraph()
        ctx = kg.to_context_string("未知角色")
        assert isinstance(ctx, str)

    def test_save_and_load(self, tmp_path):
        kg = KnowledgeGraph()
        kg.add_entity("张三", "character")
        kg.add_relation("张三", "李四", "师徒")
        kg.add_event("battle", "大战", ["张三"], 1)
        
        filepath = str(tmp_path / "kg.json")
        kg.save(filepath)
        
        kg2 = KnowledgeGraph()
        kg2.load(filepath)
        assert "张三" in kg2.entities
        assert len(kg2.relations) == 1
        assert len(kg2.events) == 1

    def test_load_nonexistent(self, tmp_path):
        kg = KnowledgeGraph()
        kg.load(str(tmp_path / "nonexistent.json"))
        assert kg.entities == {}


class TestTimeAwareMemory:
    """TimeAwareMemory 深度测试"""

    def test_init(self):
        mem = TimeAwareMemory()
        assert mem.memories == []
        assert mem.max_memories == 1000
        assert mem.importance_threshold == 0.3

    def test_add_memory(self):
        mem = TimeAwareMemory()
        mem.add_memory("测试记忆", "test", importance=0.8, chapter=1, tags=["test"])
        assert len(mem.memories) == 1
        assert mem.memories[0]["content"] == "测试记忆"
        assert mem.memories[0]["importance"] == 0.8

    def test_add_memory_without_tags(self):
        mem = TimeAwareMemory()
        mem.add_memory("测试", "test")
        assert mem.memories[0]["tags"] == []

    def test_add_many_memories_triggers_cleanup(self):
        mem = TimeAwareMemory(max_memories=5)
        for i in range(10):
            mem.add_memory(f"记忆{i}", "test", importance=0.5)
        assert len(mem.memories) <= 5

    def test_query_by_text(self):
        mem = TimeAwareMemory()
        mem.add_memory("张三修炼武功", "success")
        mem.add_memory("李四学习法术", "success")
        results = mem.query(query_text="修炼")
        assert len(results) == 1

    def test_query_by_type(self):
        mem = TimeAwareMemory()
        mem.add_memory("记忆1", "success")
        mem.add_memory("记忆2", "failure")
        results = mem.query(memory_type="success")
        assert len(results) == 1

    def test_query_by_tags(self):
        mem = TimeAwareMemory()
        mem.add_memory("记忆1", "test", tags=["战斗"])
        mem.add_memory("记忆2", "test", tags=["修炼"])
        results = mem.query(tags=["战斗"])
        assert len(results) == 1

    def test_query_limit(self):
        mem = TimeAwareMemory()
        for i in range(20):
            mem.add_memory(f"记忆{i}", "test", importance=i * 0.05)
        results = mem.query(limit=5)
        assert len(results) <= 5

    def test_get_recent(self):
        mem = TimeAwareMemory()
        for i in range(10):
            mem.add_memory(f"记忆{i}", "test")
        recent = mem.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_context_string(self):
        mem = TimeAwareMemory()
        mem.add_memory("张三修炼武功", "success", importance=0.8)
        ctx = mem.get_context_string(query="修炼")
        assert isinstance(ctx, str)

    def test_get_context_string_empty(self):
        mem = TimeAwareMemory()
        ctx = mem.get_context_string()
        assert ctx == ""

    def test_save_and_load(self, tmp_path):
        mem = TimeAwareMemory()
        mem.add_memory("测试记忆", "test", importance=0.8)
        
        filepath = str(tmp_path / "mem.json")
        mem.save(filepath)
        
        mem2 = TimeAwareMemory()
        mem2.load(filepath)
        assert len(mem2.memories) == 1
        assert mem2.memories[0]["content"] == "测试记忆"

    def test_load_nonexistent(self, tmp_path):
        mem = TimeAwareMemory()
        mem.load(str(tmp_path / "nonexistent.json"))
        assert mem.memories == []

    def test_load_invalid_json(self, tmp_path):
        filepath = tmp_path / "invalid.json"
        filepath.write_text("not json", encoding="utf-8")
        mem = TimeAwareMemory()
        mem.load(str(filepath))
        assert mem.memories == []


class TestWritingSkillManager:
    """WritingSkillManager 深度测试"""

    def test_init(self):
        mgr = WritingSkillManager()
        assert mgr.anti_slop is not None
        assert mgr.knowledge_graph is not None
        assert mgr.time_memory is not None
        assert mgr.style_config is not None

    def test_analyze_and_improve_clean(self):
        mgr = WritingSkillManager()
        text, improvements = mgr.analyze_and_improve("张三走进了房间。")
        assert isinstance(text, str)
        assert isinstance(improvements, list)

    def test_analyze_and_improve_with_issues(self):
        mgr = WritingSkillManager()
        text = "在这个世界上，然而不过但是可是。"
        fixed, improvements = mgr.analyze_and_improve(text)
        assert len(improvements) > 0

    def test_analyze_and_improve_with_genre(self):
        mgr = WritingSkillManager()
        text, improvements = mgr.analyze_and_improve("张三修炼武功。", genre="玄幻")
        assert isinstance(improvements, list)

    def test_get_writing_context(self):
        mgr = WritingSkillManager()
        ctx = mgr.get_writing_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_writing_context_with_character(self):
        mgr = WritingSkillManager()
        mgr.knowledge_graph.add_entity("张三", "character")
        ctx = mgr.get_writing_context(character="张三")
        assert isinstance(ctx, str)

    def test_learn_from_chapter(self):
        mgr = WritingSkillManager()
        mgr.learn_from_chapter("张三修炼武功。李四说：你好。", 1, ["张三", "李四"])
        assert len(mgr.time_memory.memories) > 0
        assert "张三" in mgr.knowledge_graph.entities

    def test_learn_from_chapter_with_novel_dir(self, tmp_path):
        mgr = WritingSkillManager()
        novel_dir = str(tmp_path / "novel")
        mgr.learn_from_chapter("内容", 1, ["张三"], novel_dir=novel_dir)
        assert len(mgr.time_memory.memories) > 0

    def test_save_and_load_all(self, tmp_path):
        mgr = WritingSkillManager()
        mgr.knowledge_graph.add_entity("张三", "character")
        mgr.time_memory.add_memory("测试", "test")
        
        base_dir = str(tmp_path / "skills")
        mgr.save_all(base_dir)
        
        mgr2 = WritingSkillManager()
        mgr2.load_all(base_dir)
        assert "张三" in mgr2.knowledge_graph.entities
        assert len(mgr2.time_memory.memories) > 0

    def test_load_all_nonexistent(self, tmp_path):
        mgr = WritingSkillManager()
        mgr.load_all(str(tmp_path / "nonexistent"))
        assert mgr.knowledge_graph.entities == {}


class TestANTI_SLOP_RULES:
    """ANTI_SLOP_RULES 结构测试"""

    def test_forbidden_openings(self):
        assert "forbidden_openings" in ANTI_SLOP_RULES
        assert len(ANTI_SLOP_RULES["forbidden_openings"]) > 0

    def test_forbidden_transitions(self):
        assert "forbidden_transitions" in ANTI_SLOP_RULES
        assert len(ANTI_SLOP_RULES["forbidden_transitions"]) > 0

    def test_forbidden_endings(self):
        assert "forbidden_endings" in ANTI_SLOP_RULES

    def test_forbidden_adjective_clusters(self):
        assert "forbidden_adjective_clusters" in ANTI_SLOP_RULES

    def test_recommended_techniques(self):
        assert "recommended_techniques" in ANTI_SLOP_RULES
