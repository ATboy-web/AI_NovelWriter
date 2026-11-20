"""角色成长系统测试：经验升降 / 装备 / 技能 / 战斗 / 成就。

## 为什么这批测试之前是空白

`CharacterProfile.add_exp()` 到 `get_summary()` 约 170 行**从未被执行过**（覆盖率报告里
230–400 行连续未覆盖）。它是纯逻辑、不依赖 Tk 也不联网，本该是最好测的一块。

## 断言策略：不锁死随机数

`_on_level_up` / `_on_level_down` 里用 `random.randint` 决定属性增量。
测试**不去 mock 随机数**，而是断言三类不变量：

1. **方向**：升级后属性/血量只增不减；降级后不增。
2. **边界**：属性不超过 `DEFAULT_ATTRIBUTES[attr]["max"]`，不低于下限（5 / 100 / 50）。
3. **守恒**：`hp <= max_hp`、`mp <= max_mp` 恒成立。

锁死随机数（`random.seed`）能让断言更精确，但一旦实现调整区间，测试就假红。
断言不变量则对实现宽容、对**逻辑错误**敏感 —— 这正是这批函数需要的。
"""

from __future__ import annotations

import pytest

from app.character_system import CharacterProfile

#: 属性下限（`_on_level_down` 里的硬编码值）。
ATTR_FLOOR = 5
#: 血量/法力下限（同上）。
HP_FLOOR = 100
MP_FLOOR = 50


@pytest.fixture()
def hero() -> CharacterProfile:
    """一个 1 级角色。每次新建，避免用例间状态污染。"""
    return CharacterProfile("测试角色")


# ====================================================================== 经验与升降级


class TestAddExp:
    def test_level_up_once(self, hero: CharacterProfile):
        result = hero.add_exp(100)  # exp_to_next 初始 100
        assert result["leveled_up"] is True
        assert result["leveled_down"] is False
        assert result["levels_gained"] == 1
        assert result["current_level"] == 2

    def test_remainder_exp_is_kept(self, hero: CharacterProfile):
        """溢出部分必须保留 —— 否则连升两级时会把溢出经验丢掉。"""
        result = hero.add_exp(150)
        assert result["current_level"] == 2
        assert result["current_exp"] == 50

    def test_multi_level_up_in_one_call(self, hero: CharacterProfile):
        """一次给足经验要能连升多级（`while` 循环而不是 `if`）。"""
        result = hero.add_exp(100 + 150 + 225)
        assert result["levels_gained"] >= 3
        assert result["current_level"] >= 4

    def test_exp_to_next_grows(self, hero: CharacterProfile):
        before = hero.exp_to_next
        hero.add_exp(100)
        assert hero.exp_to_next > before, "升级后门槛必须变高，否则会无限升级"

    def test_level_cap_at_100(self, hero: CharacterProfile):
        """100 级封顶：再给经验也不能突破。"""
        hero.level = 100
        hero.exp = 0
        hero.exp_to_next = 100
        hero.add_exp(10_000)
        assert hero.level == 100

    def test_negative_exp_triggers_level_down(self, hero: CharacterProfile):
        hero.level = 3
        hero.exp = 0
        result = hero.add_exp(-1)
        assert result["leveled_down"] is True
        assert result["levels_lost"] >= 1
        assert result["current_level"] <= 2

    def test_level_never_below_one(self, hero: CharacterProfile):
        hero.exp = 0
        hero.add_exp(-100_000)
        assert hero.level >= 1
        assert hero.exp >= 0, "经验不允许是负数（最低保障）"

    def test_zero_amount_is_noop(self, hero: CharacterProfile):
        snapshot = (hero.level, hero.exp, hero.exp_to_next)
        result = hero.add_exp(0)
        assert (hero.level, hero.exp, hero.exp_to_next) == snapshot
        assert result["leveled_up"] is False and result["leveled_down"] is False


class TestLevelUpEffects:
    def test_attributes_never_decrease(self, hero: CharacterProfile):
        before = dict(hero.attributes)
        hero.add_exp(100)
        for attr, value in hero.attributes.items():
            assert value >= before[attr], f"{attr} 升级后反而下降了"

    def test_attributes_respect_max(self, hero: CharacterProfile):
        for _ in range(40):  # 连升很多级，撞上限
            hero.add_exp(hero.exp_to_next)
        for attr, value in hero.attributes.items():
            cap = CharacterProfile.DEFAULT_ATTRIBUTES[attr]["max"]
            assert value <= cap, f"{attr} 超过上限 {cap}"

    def test_hp_mp_refilled_on_level_up(self, hero: CharacterProfile):
        hero.hp = 1
        hero.mp = 1
        hero.add_exp(100)
        assert hero.hp == hero.max_hp
        assert hero.mp == hero.max_mp

    def test_max_hp_mp_grow(self, hero: CharacterProfile):
        hp_before, mp_before = hero.max_hp, hero.max_mp
        hero.add_exp(100)
        assert hero.max_hp >= hp_before
        assert hero.max_mp >= mp_before

    def test_peak_level_recorded(self, hero: CharacterProfile):
        hero.add_exp(100)
        peak = hero.level
        hero.add_exp(-10_000)  # 掉级
        assert hero.stats["最高等级"] == peak, "掉级后最高等级不能被覆盖"

    def test_hp_never_exceeds_max(self, hero: CharacterProfile):
        for _ in range(20):
            hero.add_exp(hero.exp_to_next)
            assert hero.hp <= hero.max_hp
            assert hero.mp <= hero.max_mp


class TestLevelDownEffects:
    def test_hp_mp_clamped_to_new_max(self, hero: CharacterProfile):
        hero.add_exp(200)  # 先升上去
        hero.hp = hero.max_hp
        hero.add_exp(-1_000)  # 再掉级
        assert hero.hp <= hero.max_hp
        assert hero.mp <= hero.max_mp

    def test_floors_are_respected(self, hero: CharacterProfile):
        """反复掉级不能把属性/血量压到地板以下。"""
        hero.add_exp(300)
        for _ in range(5):
            hero.add_exp(-1_000)
        for attr, value in hero.attributes.items():
            assert value >= ATTR_FLOOR, f"{attr} 跌破下限 {ATTR_FLOOR}"
        assert hero.max_hp >= HP_FLOOR
        assert hero.max_mp >= MP_FLOOR


class TestTitle:
    @pytest.mark.parametrize(
        "level,expected",
        [
            (1, "无名小卒"),
            (4, "无名小卒"),
            (5, "初出茅庐"),
            (10, "小有名气"),
            (20, "崭露头角"),
            (30, "名声大噪"),
            (50, "一方霸主"),
            (70, "威震四方"),
            (80, "天下无敌"),
            (90, "超凡入圣"),
            (100, "万古不朽"),
        ],
    )
    def test_title_thresholds(self, hero: CharacterProfile, level: int, expected: str):
        hero.level = level
        hero._update_title()
        assert hero.title == expected

    def test_title_is_monotonic(self, hero: CharacterProfile):
        """等级越高，称号不能往回退。"""
        titles, last_index = [], -1
        order = [
            "无名小卒",
            "初出茅庐",
            "小有名气",
            "崭露头角",
            "名声大噪",
            "一方霸主",
            "威震四方",
            "天下无敌",
            "超凡入圣",
            "万古不朽",
        ]
        for level in (1, 5, 10, 20, 30, 50, 70, 80, 90, 100):
            hero.level = level
            hero._update_title()
            index = order.index(hero.title)
            assert index >= last_index, f"等级 {level} 的称号倒退"
            last_index = index
            titles.append(hero.title)
        assert titles == order


# ====================================================================== 装备与技能


class TestEquipment:
    def test_equip_weapon_returns_old(self, hero: CharacterProfile):
        sword = {"name": "铁剑"}
        assert hero.equip_weapon(sword) is None, "首次装备没有旧武器"
        axe = {"name": "战斧"}
        assert hero.equip_weapon(axe) == sword
        assert hero.weapon == axe

    def test_equip_armor_returns_old(self, hero: CharacterProfile):
        assert hero.equip_armor({"name": "布甲"}) is None
        assert hero.equip_armor({"name": "锁甲"}) == {"name": "布甲"}

    def test_equip_accessory_returns_old(self, hero: CharacterProfile):
        assert hero.equip_accessory({"name": "玉佩"}) is None
        assert hero.equip_accessory({"name": "戒指"}) == {"name": "玉佩"}


class TestSkills:
    def test_learn_new_skill(self, hero: CharacterProfile):
        assert hero.learn_skill({"name": "斩击"}) is True
        assert len(hero.skills) == 1

    def test_duplicate_skill_rejected(self, hero: CharacterProfile):
        hero.learn_skill({"name": "斩击"})
        assert hero.learn_skill({"name": "斩击", "desc": "同样的名字"}) is False
        assert len(hero.skills) == 1, "同名技能不能重复学习"

    def test_forget_existing_skill(self, hero: CharacterProfile):
        hero.learn_skill({"name": "斩击"})
        assert hero.forget_skill("斩击") is True
        assert hero.skills == []

    def test_forget_missing_skill(self, hero: CharacterProfile):
        assert hero.forget_skill("不存在") is False


# ====================================================================== 战斗


class TestCombat:
    def test_damage_reduced_by_constitution(self, hero: CharacterProfile):
        """体质 10 → 减伤 5 → 100 点伤害实际扣 95。"""
        result = hero.take_damage(100)
        assert result["damage"] == 95
        assert result["remaining_hp"] == 5

    def test_minimum_one_damage(self, hero: CharacterProfile):
        """体质再高，也要掉血（否则高防角色无敌）。"""
        hero.attributes["体质"] = 999
        result = hero.take_damage(1)
        assert result["damage"] >= 1
        assert hero.hp < hero.max_hp

    def test_hp_never_negative(self, hero: CharacterProfile):
        result = hero.take_damage(100_000)
        assert hero.hp == 0
        assert result["is_dead"] is True

    def test_death_flag_only_at_zero(self, hero: CharacterProfile):
        result = hero.take_damage(10)
        assert hero.hp > 0
        assert result["is_dead"] is False

    def test_heal_capped_at_max(self, hero: CharacterProfile):
        hero.hp = 90
        result = hero.heal(1000)
        assert hero.hp == hero.max_hp
        assert result["healed"] == hero.max_hp - 90, "healed 要反映实际回复量，不是请求量"

    def test_heal_from_zero(self, hero: CharacterProfile):
        hero.hp = 0
        result = hero.heal(30)
        assert hero.hp == 30
        assert result["healed"] == 30

    def test_rest_restores_both(self, hero: CharacterProfile):
        hero.hp, hero.mp = 1, 2
        hero.rest()
        assert hero.hp == hero.max_hp
        assert hero.mp == hero.max_mp


class TestStatistics:
    def test_win_and_loss_counters(self, hero: CharacterProfile):
        hero.record_battle(won=True, damage_dealt=100, kills=2)
        hero.record_battle(won=False, damage_dealt=50)
        assert hero.stats["总战斗次数"] == 2
        assert hero.stats["胜利次数"] == 1
        assert hero.stats["失败次数"] == 1
        assert hero.stats["总伤害"] == 150
        assert hero.stats["击杀数"] == 2

    def test_creation_awards_exp(self, hero: CharacterProfile):
        """创作给经验：字数 // 10 + 章节 × 50。"""
        hero.record_creation(word_count=1000, chapters=2)
        assert hero.stats["创作字数"] == 1000
        assert hero.stats["生成章节数"] == 2
        # 100 + 100 = 200 经验 → 升 1 级（门槛 100），溢出 100
        assert hero.level == 2

    def test_creation_without_exp_gain(self, hero: CharacterProfile):
        """字数不足 10 且无章节 ⇒ 不给经验（不能靠刷空调用升级）。"""
        level_before = hero.level
        hero.record_creation(word_count=5)
        assert hero.level == level_before
        assert hero.stats["创作字数"] == 5


# ====================================================================== 成就


class TestAchievements:
    def test_unlock_new(self, hero: CharacterProfile):
        assert hero.unlock_achievement("初出茅庐", "完成第一章") is True
        assert hero.achievements[0]["name"] == "初出茅庐"
        assert hero.achievements[0]["desc"] == "完成第一章"
        assert "unlocked_at" in hero.achievements[0]

    def test_unlock_duplicate(self, hero: CharacterProfile):
        hero.unlock_achievement("初出茅庐")
        assert hero.unlock_achievement("初出茅庐") is False
        assert len(hero.achievements) == 1


# ====================================================================== 摘要与序列化


class TestSummary:
    def test_summary_contains_key_fields(self, hero: CharacterProfile):
        hero.personality = "沉稳"
        hero.backstory = "出身寒门，靠一把钝剑走到今天。" * 5
        hero.learn_skill({"name": "斩击"})
        hero.equip_weapon({"name": "铁剑"})
        text = hero.get_summary()
        assert "测试角色" in text
        assert "无名小卒" in text
        assert "性格: 沉稳" in text
        assert "背景:" in text
        assert "铁剑" in text
        assert "技能: 1个" in text

    def test_summary_without_equipment(self, hero: CharacterProfile):
        text = hero.get_summary()
        assert "武器: 无" in text
        assert "防具: 无" in text

    def test_summary_truncates_backstory(self, hero: CharacterProfile):
        hero.backstory = "长" * 200
        text = hero.get_summary()
        assert "..." in text
        assert "长" * 60 not in text, "背景应被截到 50 字"


class TestSerialization:
    def test_roundtrip_preserves_state(self, hero: CharacterProfile):
        hero.add_exp(150)
        hero.equip_weapon({"name": "铁剑"})
        hero.learn_skill({"name": "斩击"})
        hero.unlock_achievement("首胜")
        hero.category = "主角"
        hero.faction = "正派"

        clone = CharacterProfile("测试角色", data=hero.to_dict())
        assert clone.level == hero.level
        assert clone.exp == hero.exp
        assert clone.weapon == {"name": "铁剑"}
        assert clone.skills == [{"name": "斩击"}]
        assert clone.achievements == hero.achievements
        assert clone.category == "主角"
        assert clone.faction == "正派"

    def test_missing_fields_get_defaults(self):
        """老存档缺字段时不能崩（这是升级兼容的关键）。"""
        clone = CharacterProfile("老角色", data={"name": "老角色"})
        assert clone.level == 1
        assert clone.attributes["力量"] == 10
        assert clone.category == "无名小卒"

    def test_unknown_attribute_is_kept(self):
        """自定义属性不能被"补默认值"的逻辑删掉。"""
        clone = CharacterProfile("自定义", data={"attributes": {"魔力": 5, "力量": 20}})
        assert clone.attributes["魔力"] == 5
        assert clone.attributes["力量"] == 20
        assert "体质" in clone.attributes  # 缺失的默认属性被补上
