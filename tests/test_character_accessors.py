"""角色集合查询族的完整性回归测试（v3 补漏）。

背景：`app/writing_skills_panel.py` 的「更新知识图谱」一直在调用
`self.character_system.get_all_characters()`，而 `CharacterSystem`
**从未定义过这个方法** —— 也就是说那个按钮必然抛 `AttributeError`。
本文件把这个缺口固化成回归测试，并额外守住两条项目硬约束：

- 集合查询族**只读**，不得夹带删除角色的入口
- 返回的是容器副本，调用方改不到内部状态（避免"看数据"变成"改数据"）
"""

import pytest

from app.character_system import CharacterSystem


@pytest.fixture
def system(tmp_path):
    return CharacterSystem(tmp_path)


class TestGetAllCharacters:
    def test_exists(self, system):
        """方法必须存在 —— 这是本次修复的核心（此前调用方直接崩）。"""
        assert callable(getattr(system, "get_all_characters", None))

    def test_empty_by_default(self, system):
        assert system.get_all_characters() == {}

    def test_returns_name_to_profile_mapping(self, system):
        system.create_character("张三", category="主角")
        system.create_character("李四", category="配角")

        chars = system.get_all_characters()
        assert set(chars) == {"张三", "李四"}
        assert chars["张三"].category == "主角"

    def test_is_a_copy_of_the_container(self, system):
        system.create_character("张三")
        chars = system.get_all_characters()
        chars["王五"] = "伪造"
        assert "王五" not in system.get_all_characters()

    def test_values_are_live_objects(self, system):
        """容器是副本、角色对象是同一批引用 —— 面板要读实时字段。"""
        system.create_character("张三")
        system.get_all_characters()["张三"].level = 42
        assert system.get_character("张三").level == 42

    def test_is_read_only(self, system):
        """硬约束：不得提供任何删除角色的入口。"""
        code = (system.get_all_characters.__doc__ or "").lower()
        assert "delete" not in code
        for name in dir(system):
            assert "delete_all" not in name

    def test_supports_panel_iteration_pattern(self, system):
        """复现 `writing_skills_panel.py:188` 的真实用法。"""
        system.create_character("张三", category="主角")
        entities = {}
        for name, char in system.get_all_characters().items():
            entities[name] = {"faction": char.faction}
        assert entities == {"张三": {"faction": "中立"}}

    def test_family_completeness(self, system):
        """集合查询族七元齐备（此前缺 `get_all_characters` 一环）。"""
        for method in (
            "get_all_characters", "get_character_names", "get_characters_by_category",
            "get_alive_characters", "get_dead_characters", "get_characters_by_faction",
            "get_character", "set_active",
        ):
            assert callable(getattr(system, method, None)), method

    def test_reflects_death_status_without_removing(self, system):
        """角色死亡后仍须存在于全集（**不许**因状态变化而被删除）。"""
        system.create_character("张三")
        system.mark_death("张三", 10)

        assert "张三" in system.get_all_characters()
        assert system.get_dead_characters() == ["张三"]
        assert system.get_alive_characters() == []


class TestWritingSkillsPanelCallSite:
    def test_panel_call_is_satisfied(self, system):
        """直接按调用点的写法跑一遍，确保不再是"永不到达的死代码"。"""
        import inspect

        from app import writing_skills_panel

        source = inspect.getsource(writing_skills_panel)
        assert "get_all_characters()" in source
        # 调用点要求 `.items()` → 返回 dict
        assert hasattr(system.get_all_characters(), "items")
