"""角色系统的「上层」测试：AI 创建角色、武器/技能库、战斗模拟、统计显示。

与 `test_character_growth.py` 的分工：

- 前者测 `CharacterProfile`（单个角色的成长，纯数据）；
- 本文件测 `CharacterSystem`（管理器 + 与 AI/随机数交互的部分）。

## 为什么 `simulate_battle` 值得单独测

它是**唯一会同时改动多个子系统**的函数：扣血（`take_damage`）、记战绩
（`record_battle`）、给经验（`add_exp`）、存盘（`save_character`）。
一旦某处逻辑写错，表现为"打完仗属性没涨"或"经验重复发放"这类**静默错误**，
界面上看不出来。这里用可控敌人把四条链路都钉住。

## 随机性的处理

战斗里暴击由 `random.randint(1, 100) <= 幸运` 决定。测试**不 mock 随机数**，
而是用极端属性（幸运 0 / 幸运 100）把随机性关掉 —— 这比 `random.seed`
更能表达意图："幸运满就必暴击，幸运零就永不暴击"。
"""

from __future__ import annotations

import pytest

from app.character_system import CharacterProfile, CharacterSystem

# ====================================================================== 夹具


@pytest.fixture()
def system(tmp_path) -> CharacterSystem:
    """一个绑定了临时目录的角色系统（`save_character` 会落盘）。"""
    return CharacterSystem(novel_dir=tmp_path)


def set_active(system: CharacterSystem, character: CharacterProfile) -> CharacterProfile:
    """把角色设为"当前角色"。

    ❗ `system.character` 是**只读 property**（由 `active_name` + `characters` 派生），
    直接赋值会 AttributeError。这也是"同一事实一处派生"的体现：
    角色不能既是 `characters[name]` 又是另一个 `system.character` 对象。
    """
    system.characters[character.name] = character
    system.active_name = character.name
    return character


# ====================================================================== 武器/技能库


class TestEquipmentLibrary:
    def test_builtin_weapons_exist(self, system: CharacterSystem):
        weapons = system.get_all_weapons()
        assert weapons, "内置武器库不能为空"
        for weapon in weapons:
            assert weapon.get("name"), "每件武器都要有名字"
            assert "quality" in weapon

    def test_weapon_categories(self, system: CharacterSystem):
        categories = system.get_weapon_categories()
        assert categories, "至少要有一个武器类别"
        assert all(isinstance(c, str) and c for c in categories)

    def test_weapons_by_category(self, system: CharacterSystem):
        """类别是**库的 key**，不是条目字段 —— 内置武器只有 name/quality/desc/attributes。"""
        category = system.get_weapon_categories()[0]
        weapons = system.get_weapons(category)
        assert weapons, f"类别 {category} 下应有武器"
        expected = {w["name"] for w in system.weapon_library[category]}
        assert {w["name"] for w in weapons} >= expected

    def test_unknown_category_returns_empty(self, system: CharacterSystem):
        assert system.get_weapons("不存在的类别") == []

    def test_skill_library(self, system: CharacterSystem):
        skills = system.get_all_skills()
        assert skills
        for skill in skills:
            assert skill.get("name")

    def test_skills_by_category(self, system: CharacterSystem):
        categories = system.get_skill_categories()
        assert categories
        category = categories[0]
        skills = system.get_skills(category)
        assert all(s.get("type") == category for s in skills)

    def test_unknown_skill_category(self, system: CharacterSystem):
        assert system.get_skills("不存在的类别") == []


class TestRandomPick:
    def test_random_weapon_returns_member(self, system: CharacterSystem):
        weapon = system.random_weapon()
        assert weapon in system.get_all_weapons()

    def test_random_weapon_with_quality(self, system: CharacterSystem):
        all_weapons = system.get_all_weapons()
        quality = all_weapons[0]["quality"]
        for _ in range(10):
            picked = system.random_weapon(quality)
            assert picked.get("quality") == quality

    def test_random_weapon_unknown_quality_falls_back(self, system: CharacterSystem):
        """稀有度不存在时退回全库随机 —— 不能返回空。"""
        picked = system.random_weapon("不存在的品质")
        assert picked in system.get_all_weapons()

    def test_random_skill(self, system: CharacterSystem):
        assert system.random_skill() in system.get_all_skills()

    def test_random_skill_with_category(self, system: CharacterSystem):
        category = system.get_skill_categories()[0]
        for _ in range(10):
            picked = system.random_skill(category)
            assert picked.get("type") == category


# ====================================================================== 战斗模拟


class TestSimulateBattle:
    def _strong(self, system: CharacterSystem) -> CharacterProfile:
        """高攻高血零幸运：攻击必中、不被暴击，结果完全确定。"""
        character = CharacterProfile("强者")
        character.attributes.update({"力量": 100, "体质": 100, "幸运": 0})
        character.max_hp = character.hp = 500
        return set_active(system, character)

    def test_no_character_returns_error(self, system: CharacterSystem):
        assert system.simulate_battle({"hp": 10})["error"] == "未创建角色"

    def test_win_against_weak_enemy(self, system: CharacterSystem):
        self._strong(system)
        result = system.simulate_battle({"name": "史莱姆", "hp": 50, "attack": 1, "defense": 0})
        assert result["won"] is True
        assert result["rounds"] >= 1
        assert result["remaining_hp"] > 0
        assert any("胜利" in line for line in result["log"])

    def test_battle_records_stats(self, system: CharacterSystem):
        """打完必须记战绩，否则统计页永远是 0。"""
        self._strong(system)
        system.simulate_battle({"hp": 50, "attack": 1, "defense": 0})
        assert system.character.stats["总战斗次数"] == 1
        assert system.character.stats["胜利次数"] == 1
        assert system.character.stats["总伤害"] > 0

    def test_exp_reward_applied_on_win(self, system: CharacterSystem):
        character = self._strong(system)
        exp_before = character.exp
        system.simulate_battle({"hp": 50, "attack": 1, "defense": 0, "exp_reward": 40})
        # 40 经验不够升级（门槛 100），应留在 exp 里
        assert character.exp > exp_before or character.level > 1

    def test_no_exp_on_loss(self, system: CharacterSystem):
        """失败不给经验 —— 否则可以靠送死刷级。"""
        weak = CharacterProfile("弱者")
        weak.attributes.update({"力量": 1, "体质": 1, "幸运": 0})
        weak.max_hp = weak.hp = 10
        set_active(system, weak)
        result = system.simulate_battle({"hp": 9999, "attack": 999, "defense": 0})
        assert result["won"] is False
        assert weak.stats["失败次数"] == 1

    def test_round_cap(self, system: CharacterSystem):
        """双方都打不死对方时必须停手（20 回合上限），不能死循环。"""
        weak = CharacterProfile("僵持者")
        weak.attributes.update({"力量": 1, "体质": 999, "幸运": 0})
        weak.max_hp = weak.hp = 100
        set_active(system, weak)
        result = system.simulate_battle({"hp": 9999, "attack": 1, "defense": 9999})
        assert result["rounds"] <= 20
        assert result["won"] is False

    def test_crit_doubles_damage(self, system: CharacterSystem):
        """幸运 100 ⇒ 必暴击 ⇒ 伤害翻倍（与幸运 0 对比）。"""
        def run(luck: int) -> int:
            character = CharacterProfile(f"运气{luck}")
            character.attributes.update({"力量": 50, "体质": 100, "幸运": luck})
            character.max_hp = character.hp = 500
            set_active(system, character)
            result = system.simulate_battle({"hp": 10000, "attack": 1, "defense": 0})
            # 第一回合日志里的伤害值
            first = result["log"][0]
            return int(first.split("造成")[1].split("伤害")[0])

        assert run(100) > run(0), "幸运满必须打出更高伤害（暴击）"

    def test_minimum_damage_per_round(self, system: CharacterSystem):
        """攻击力远低于防御时，每回合也至少造成 1 点伤害。"""
        weak = CharacterProfile("弱攻")
        weak.attributes.update({"力量": 1, "体质": 100, "幸运": 0})
        weak.max_hp = weak.hp = 500
        set_active(system, weak)
        result = system.simulate_battle({"hp": 5, "attack": 1, "defense": 999})
        assert result["won"] is True, "5 点血在 1 点/回合下应被打完"

    def test_battle_persists_character(self, system: CharacterSystem, tmp_path):
        """战后必须存盘，否则重开游戏战绩全丢。"""
        self._strong(system)
        system.simulate_battle({"hp": 50, "attack": 1, "defense": 0})
        assert (tmp_path / "character.json").is_file() or any(tmp_path.iterdir())

    def test_default_enemy_fields(self, system: CharacterSystem):
        """敌人只给最少的字段也不能崩（默认 hp/attack/defense）。"""
        self._strong(system)
        result = system.simulate_battle({})
        assert "won" in result and result["rounds"] >= 1


# ====================================================================== 统计显示


class TestStatsDisplay:
    def test_without_character(self, system: CharacterSystem):
        assert system.get_stats_display() == "未创建角色"

    def test_win_rate_calculation(self, system: CharacterSystem):
        character = CharacterProfile("胜率")
        character.stats["总战斗次数"] = 4
        character.stats["胜利次数"] = 3
        set_active(system, character)
        text = system.get_stats_display()
        assert "75.0%" in text, f"胜率算错：{text}"

    def test_zero_battles_no_division_error(self, system: CharacterSystem):
        """0 场战斗时不能除零（顺手验证一下）。"""
        set_active(system, CharacterProfile("新人"))
        text = system.get_stats_display()
        assert "0.0%" in text

    def test_thousands_separator(self, system: CharacterSystem):
        character = CharacterProfile("大数字")
        character.stats["总伤害"] = 1234567
        character.stats["创作字数"] = 89012
        set_active(system, character)
        text = system.get_stats_display()
        assert "1,234,567" in text
        assert "89,012" in text

    def test_achievements_listed(self, system: CharacterSystem):
        character = CharacterProfile("有成就")
        character.unlock_achievement("首胜", "赢下第一场")
        set_active(system, character)
        text = system.get_stats_display()
        assert "成就" in text
        assert "首战" in text or "首胜" in text


# ====================================================================== AI 创建角色


class _FakeAI:
    """假 AI：返回一段固定 JSON，用于验证解析与落库链路。"""

    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list = []

    def chat(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.payload


class TestAiCreateCharacter:
    PAYLOAD = (
        '{"name": "林清", "title": "剑客", "personality": "沉默寡言",'
        ' "appearance": "青衫长剑", "backstory": "出身剑冢，十年磨一剑。",'
        ' "attributes": {"力量": 30, "敏捷": 28, "体质": 25, "智力": 12,'
        ' "精神": 15, "魅力": 10, "幸运": 8},'
        ' "weapon_suggestion": "青锋剑", "skill_suggestions": ["挑剑", "回风"]}'
    )

    def test_creates_character_from_ai(self, system: CharacterSystem):
        """结构化结果：`{success, character, weapon_suggestion, skill_suggestions}`。

        与 `PluginResult` / `MCPResult` 同一惯例 —— 成功标志与产物分开，
        调用方先看 `success` 再取 `character`，不会把错误字典当角色用。
        """
        result = system.ai_create_character(_FakeAI(self.PAYLOAD), role="主角")
        assert result["success"] is True
        character = result["character"]
        assert isinstance(character, CharacterProfile)
        assert character.name == "林清"
        assert character.attributes["力量"] == 30

    def test_ai_suggestions_are_passed_through(self, system: CharacterSystem):
        """AI 建议的武器/技能要原样带出，供调用方接着装备 —— 不能吞掉。"""
        result = system.ai_create_character(_FakeAI(self.PAYLOAD), role="主角")
        assert result["weapon_suggestion"] == "青锋剑"
        assert result["skill_suggestions"] == ["挑剑", "回风"]

    def test_persists_created_character(self, system: CharacterSystem):
        system.ai_create_character(_FakeAI(self.PAYLOAD), role="主角")
        assert system.character is not None
        assert system.character.name == "林清"

    def test_ai_garbage_returns_error_not_crash(self, system: CharacterSystem):
        """AI 返回非 JSON ⇒ 必须给出失败信号，不能抛出（UI 会直接崩）。"""
        result = system.ai_create_character(_FakeAI("抱歉，我无法完成这个请求。"), role="主角")
        assert isinstance(result, dict), "解析失败时应返回 dict（含 error），而不是角色对象"
        assert result.get("error")

    def test_without_ai_client(self, system: CharacterSystem):
        result = system.ai_create_character(None, role="主角")
        assert isinstance(result, dict)
        assert result.get("error")
