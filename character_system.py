"""
角色成长系统 - 管理主角的等级、属性、武器、法宝、技能、数值
"""

import json
import time
import random
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class CharacterProfile:
    """角色档案 - 包含完整的成长数据"""
    
    # 默认属性模板
    DEFAULT_ATTRIBUTES = {
        "力量": {"value": 10, "max": 999, "desc": "物理攻击力"},
        "敏捷": {"value": 10, "max": 999, "desc": "速度与闪避"},
        "体质": {"value": 10, "max": 999, "desc": "生命值与防御"},
        "智力": {"value": 10, "max": 999, "desc": "法术强度"},
        "精神": {"value": 10, "max": 999, "desc": "法力值与抗性"},
        "魅力": {"value": 10, "max": 999, "desc": "社交与领导"},
        "幸运": {"value": 10, "max": 999, "desc": "暴击与掉落"},
    }
    
    # 品质等级
    QUALITY_LEVELS = {
        "凡品": {"color": "#94a3b8", "multiplier": 1.0},
        "灵品": {"color": "#3b82f6", "multiplier": 1.5},
        "宝品": {"color": "#8b5cf6", "multiplier": 2.0},
        "仙品": {"color": "#f59e0b", "multiplier": 3.0},
        "神品": {"color": "#ef4444", "multiplier": 5.0},
        "超神": {"color": "#ec4899", "multiplier": 10.0},
    }
    
    def __init__(self, name: str = "无名", data: Dict = None):
        self.name = name
        self.created_at = datetime.now().isoformat()
        
        if data:
            self._load_from_dict(data)
        else:
            self._init_default()
    
    def _init_default(self):
        """初始化默认角色"""
        # 基础信息
        self.title = "无名小卒"
        self.level = 1
        self.exp = 0
        self.exp_to_next = 100
        self.hp = 100
        self.max_hp = 100
        self.mp = 50
        self.max_mp = 50
        
        # 属性
        self.attributes = {k: v["value"] for k, v in self.DEFAULT_ATTRIBUTES.items()}
        
        # 武器/法宝
        self.weapon = None
        self.armor = None
        self.accessory = None
        
        # 技能列表
        self.skills = []
        
        # 背包
        self.inventory = []
        
        # 成就
        self.achievements = []
        
        # 战斗统计
        self.stats = {
            "总战斗次数": 0,
            "胜利次数": 0,
            "失败次数": 0,
            "总伤害": 0,
            "总治疗": 0,
            "击杀数": 0,
            "最高等级": 1,
            "创作字数": 0,
            "生成章节数": 0,
        }
    
    def _load_from_dict(self, data: Dict):
        """从字典加载"""
        self.name = data.get("name", "无名")
        self.title = data.get("title", "无名小卒")
        self.level = data.get("level", 1)
        self.exp = data.get("exp", 0)
        self.exp_to_next = data.get("exp_to_next", 100)
        self.hp = data.get("hp", 100)
        self.max_hp = data.get("max_hp", 100)
        self.mp = data.get("mp", 50)
        self.max_mp = data.get("max_mp", 50)
        self.attributes = data.get("attributes", {k: v["value"] for k, v in self.DEFAULT_ATTRIBUTES.items()})
        self.weapon = data.get("weapon")
        self.armor = data.get("armor")
        self.accessory = data.get("accessory")
        self.skills = data.get("skills", [])
        self.inventory = data.get("inventory", [])
        self.achievements = data.get("achievements", [])
        self.stats = data.get("stats", {})
        self.created_at = data.get("created_at", datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """转为字典"""
        return {
            "name": self.name,
            "title": self.title,
            "level": self.level,
            "exp": self.exp,
            "exp_to_next": self.exp_to_next,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "attributes": self.attributes,
            "weapon": self.weapon,
            "armor": self.armor,
            "accessory": self.accessory,
            "skills": self.skills,
            "inventory": self.inventory,
            "achievements": self.achievements,
            "stats": self.stats,
            "created_at": self.created_at,
        }
    
    # ===== 等级和经验 =====
    
    def add_exp(self, amount: int) -> Dict:
        """增加经验值，返回升级信息"""
        self.exp += amount
        leveled_up = False
        levels_gained = 0
        
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            levels_gained += 1
            leveled_up = True
            
            # 升级奖励
            self._on_level_up()
        
        return {
            "leveled_up": leveled_up,
            "levels_gained": levels_gained,
            "current_level": self.level,
            "current_exp": self.exp,
            "exp_to_next": self.exp_to_next,
        }
    
    def _on_level_up(self):
        """升级时的属性提升"""
        # 经验需求增长
        self.exp_to_next = int(self.exp_to_next * 1.5)
        
        # 属性提升
        for attr in self.attributes:
            gain = random.randint(1, 3)
            self.attributes[attr] = min(self.attributes[attr] + gain, 
                                       self.DEFAULT_ATTRIBUTES[attr]["max"])
        
        # HP/MP提升
        hp_gain = random.randint(20, 50)
        mp_gain = random.randint(10, 30)
        self.max_hp += hp_gain
        self.max_mp += mp_gain
        self.hp = self.max_hp  # 升级回满
        self.mp = self.max_mp
        
        # 更新称号
        self._update_title()
        
        # 更新统计
        self.stats["最高等级"] = max(self.stats.get("最高等级", 1), self.level)
    
    def _update_title(self):
        """根据等级更新称号"""
        titles = {
            1: "无名小卒", 5: "初出茅庐", 10: "小有名气",
            20: "崭露头角", 30: "名声大噪", 50: "一方霸主",
            70: "威震四方", 80: "天下无敌", 90: "超凡入圣",
            100: "万古不朽",
        }
        for level_req in sorted(titles.keys(), reverse=True):
            if self.level >= level_req:
                self.title = titles[level_req]
                break
    
    # ===== 武器/法宝系统 =====
    
    def equip_weapon(self, weapon: Dict) -> Optional[Dict]:
        """装备武器，返回被替换的武器"""
        old = self.weapon
        self.weapon = weapon
        self._recalculate_stats()
        return old
    
    def equip_armor(self, armor: Dict) -> Optional[Dict]:
        """装备防具"""
        old = self.armor
        self.armor = armor
        self._recalculate_stats()
        return old
    
    def equip_accessory(self, accessory: Dict) -> Optional[Dict]:
        """装备饰品"""
        old = self.accessory
        self.accessory = accessory
        self._recalculate_stats()
        return old
    
    def _recalculate_stats(self):
        """重新计算装备加成后的属性"""
        # 基础属性（不含装备）
        base_attrs = {k: v for k, v in self.attributes.items()}
        
        # 应用装备加成
        for equip in [self.weapon, self.armor, self.accessory]:
            if equip and "attributes" in equip:
                for attr, bonus in equip["attributes"].items():
                    if attr in self.attributes:
                        self.attributes[attr] = base_attrs.get(attr, 0) + bonus
    
    # ===== 技能系统 =====
    
    def learn_skill(self, skill: Dict) -> bool:
        """学习技能"""
        # 检查是否已学会
        for s in self.skills:
            if s.get("name") == skill.get("name"):
                return False
        
        self.skills.append(skill)
        return True
    
    def forget_skill(self, skill_name: str) -> bool:
        """遗忘技能"""
        for i, s in enumerate(self.skills):
            if s.get("name") == skill_name:
                self.skills.pop(i)
                return True
        return False
    
    def get_skills_by_type(self, skill_type: str) -> List[Dict]:
        """按类型获取技能"""
        return [s for s in self.skills if s.get("type") == skill_type]
    
    # ===== 背包系统 =====
    
    def add_item(self, item: Dict):
        """添加物品到背包"""
        # 检查是否已存在（可堆叠）
        for inv_item in self.inventory:
            if inv_item.get("name") == item.get("name") and inv_item.get("stackable", False):
                inv_item["count"] = inv_item.get("count", 1) + item.get("count", 1)
                return
        
        self.inventory.append(item)
    
    def remove_item(self, item_name: str, count: int = 1) -> bool:
        """移除物品"""
        for i, item in enumerate(self.inventory):
            if item.get("name") == item_name:
                if item.get("count", 1) > count:
                    item["count"] = item.get("count", 1) - count
                else:
                    self.inventory.pop(i)
                return True
        return False
    
    # ===== 战斗系统 =====
    
    def take_damage(self, damage: int) -> Dict:
        """受到伤害"""
        # 计算防御减免
        defense = self.attributes.get("体质", 0)
        actual_damage = max(1, damage - defense // 2)
        
        self.hp = max(0, self.hp - actual_damage)
        
        return {
            "damage": actual_damage,
            "remaining_hp": self.hp,
            "is_dead": self.hp <= 0,
        }
    
    def heal(self, amount: int) -> Dict:
        """治疗"""
        old_hp = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        healed = self.hp - old_hp
        
        return {
            "healed": healed,
            "current_hp": self.hp,
        }
    
    def use_mp(self, amount: int) -> bool:
        """使用法力"""
        if self.mp >= amount:
            self.mp -= amount
            return True
        return False
    
    def rest(self):
        """休息恢复"""
        self.hp = self.max_hp
        self.mp = self.max_mp
    
    # ===== 统计 =====
    
    def record_battle(self, won: bool, damage_dealt: int = 0, damage_taken: int = 0, kills: int = 0):
        """记录战斗结果"""
        self.stats["总战斗次数"] = self.stats.get("总战斗次数", 0) + 1
        if won:
            self.stats["胜利次数"] = self.stats.get("胜利次数", 0) + 1
        else:
            self.stats["失败次数"] = self.stats.get("失败次数", 0) + 1
        self.stats["总伤害"] = self.stats.get("总伤害", 0) + damage_dealt
        self.stats["总治疗"] = self.stats.get("总治疗", 0) + 0
        self.stats["击杀数"] = self.stats.get("击杀数", 0) + kills
    
    def record_creation(self, word_count: int = 0, chapters: int = 0):
        """记录创作统计"""
        self.stats["创作字数"] = self.stats.get("创作字数", 0) + word_count
        self.stats["生成章节数"] = self.stats.get("生成章节数", 0) + chapters
        
        # 创作获得经验
        exp_gain = word_count // 10 + chapters * 50
        if exp_gain > 0:
            self.add_exp(exp_gain)
    
    # ===== 成就系统 =====
    
    def unlock_achievement(self, name: str, desc: str = ""):
        """解锁成就"""
        for a in self.achievements:
            if a.get("name") == name:
                return False
        
        self.achievements.append({
            "name": name,
            "desc": desc,
            "unlocked_at": datetime.now().isoformat(),
        })
        return True
    
    # ===== 显示 =====
    
    def get_summary(self) -> str:
        """获取角色摘要"""
        lines = [
            f"═══ {self.name} ═══",
            f"称号: {self.title}",
            f"等级: {self.level} (经验: {self.exp}/{self.exp_to_next})",
            f"生命: {self.hp}/{self.max_hp}  法力: {self.mp}/{self.max_mp}",
            "",
            "─── 属性 ───",
        ]
        
        for attr, value in self.attributes.items():
            desc = self.DEFAULT_ATTRIBUTES[attr]["desc"]
            bar = "█" * (value // 10) + "░" * (10 - value // 10)
            lines.append(f"{attr}: {bar} {value} ({desc})")
        
        lines.append("")
        lines.append("─── 装备 ───")
        lines.append(f"武器: {self.weapon.get('name', '无') if self.weapon else '无'}")
        lines.append(f"防具: {self.armor.get('name', '无') if self.armor else '无'}")
        lines.append(f"饰品: {self.accessory.get('name', '无') if self.accessory else '无'}")
        
        if self.skills:
            lines.append("")
            lines.append("─── 技能 ───")
            for skill in self.skills:
                lines.append(f"• {skill.get('name', '')}: {skill.get('desc', '')}")
        
        return "\n".join(lines)


class CharacterSystem:
    """角色系统管理器"""
    
    def __init__(self, novel_dir: Path = None):
        self.novel_dir = novel_dir
        self.save_file = novel_dir / "character_profile.json" if novel_dir else None
        self.character: Optional[CharacterProfile] = None
        
        # 内置武器库
        self.weapon_library = self._init_weapon_library()
        # 内置技能库
        self.skill_library = self._init_skill_library()
    
    def _init_weapon_library(self) -> Dict[str, List[Dict]]:
        """初始化武器库"""
        return {
            "剑": [
                {"name": "铁剑", "quality": "凡品", "desc": "普通铁剑", "attributes": {"力量": 5}},
                {"name": "青锋剑", "quality": "灵品", "desc": "削铁如泥", "attributes": {"力量": 15, "敏捷": 5}},
                {"name": "龙渊剑", "quality": "宝品", "desc": "龙族神兵", "attributes": {"力量": 30, "体质": 10}},
                {"name": "轩辕剑", "quality": "仙品", "desc": "上古神剑", "attributes": {"力量": 50, "智力": 20, "魅力": 15}},
                {"name": "诛仙剑", "quality": "神品", "desc": "斩仙灭神", "attributes": {"力量": 100, "智力": 50, "幸运": 30}},
            ],
            "刀": [
                {"name": "朴刀", "quality": "凡品", "desc": "朴素战刀", "attributes": {"力量": 6}},
                {"name": "雁翎刀", "quality": "灵品", "desc": "轻灵锋利", "attributes": {"力量": 12, "敏捷": 8}},
                {"name": "屠龙刀", "quality": "宝品", "desc": "屠龙宝刀", "attributes": {"力量": 35, "体质": 15}},
            ],
            "枪": [
                {"name": "长枪", "quality": "凡品", "desc": "普通长枪", "attributes": {"力量": 7, "敏捷": 3}},
                {"name": "龙胆亮银枪", "quality": "宝品", "desc": "赵云之枪", "attributes": {"力量": 25, "敏捷": 20, "幸运": 10}},
            ],
            "弓": [
                {"name": "猎弓", "quality": "凡品", "desc": "猎人之弓", "attributes": {"敏捷": 8, "幸运": 3}},
                {"name": "落日弓", "quality": "宝品", "desc": "射日神弓", "attributes": {"敏捷": 30, "力量": 15, "幸运": 20}},
            ],
            "法杖": [
                {"name": "木杖", "quality": "凡品", "desc": "普通法杖", "attributes": {"智力": 5}},
                {"name": "星月法杖", "quality": "灵品", "desc": "星辰之力", "attributes": {"智力": 20, "精神": 15}},
                {"name": "盘古幡", "quality": "神品", "desc": "开天辟地", "attributes": {"智力": 100, "精神": 80, "力量": 50}},
            ],
            "法宝": [
                {"name": "聚宝盆", "quality": "灵品", "desc": "聚财之宝", "attributes": {"幸运": 25}},
                {"name": "乾坤袋", "quality": "宝品", "desc": "收纳万物", "attributes": {"体质": 20, "幸运": 15}},
                {"name": "玲珑塔", "quality": "仙品", "desc": "镇压万物", "attributes": {"体质": 40, "智力": 30, "精神": 25}},
                {"name": "混沌珠", "quality": "超神", "desc": "混沌之力", "attributes": {"力量": 80, "智力": 80, "体质": 80, "精神": 80}},
            ],
        }
    
    def _init_skill_library(self) -> Dict[str, List[Dict]]:
        """初始化技能库"""
        return {
            "攻击": [
                {"name": "斩击", "type": "攻击", "desc": "基础斩击", "mp_cost": 0, "damage": 10},
                {"name": "烈焰斩", "type": "攻击", "desc": "附带火焰伤害", "mp_cost": 15, "damage": 30},
                {"name": "雷霆万钧", "type": "攻击", "desc": "雷电攻击", "mp_cost": 30, "damage": 60},
                {"name": "天地一刀", "type": "攻击", "desc": "最强斩击", "mp_cost": 80, "damage": 200},
            ],
            "防御": [
                {"name": "铁壁", "type": "防御", "desc": "提升防御", "mp_cost": 10, "defense_bonus": 20},
                {"name": "金刚不坏", "type": "防御", "desc": "免疫伤害", "mp_cost": 50, "defense_bonus": 100},
            ],
            "治疗": [
                {"name": "治愈术", "type": "治疗", "desc": "恢复生命", "mp_cost": 20, "heal": 50},
                {"name": "回春术", "type": "治疗", "desc": "持续恢复", "mp_cost": 40, "heal": 100},
            ],
            "辅助": [
                {"name": "疾风步", "type": "辅助", "desc": "提升速度", "mp_cost": 15, "effect": "speed_up"},
                {"name": "洞察", "type": "辅助", "desc": "提升暴击", "mp_cost": 10, "effect": "crit_up"},
            ],
            "特殊": [
                {"name": "时间暂停", "type": "特殊", "desc": "暂停时间", "mp_cost": 100, "effect": "time_stop"},
                {"name": "复活", "type": "特殊", "desc": "复活一次", "mp_cost": 200, "effect": "revive"},
            ],
        }
    
    # ===== 存档管理 =====
    
    def save(self):
        """保存角色数据"""
        if self.character and self.save_file:
            with open(self.save_file, 'w', encoding='utf-8') as f:
                json.dump(self.character.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load(self) -> bool:
        """加载角色数据"""
        if self.save_file and self.save_file.exists():
            with open(self.save_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.character = CharacterProfile(data=data)
            return True
        return False
    
    def create_character(self, name: str) -> CharacterProfile:
        """创建新角色"""
        self.character = CharacterProfile(name)
        self.save()
        return self.character
    
    # ===== 武器/技能获取 =====
    
    def get_weapon_categories(self) -> List[str]:
        return list(self.weapon_library.keys())
    
    def get_weapons(self, category: str) -> List[Dict]:
        return self.weapon_library.get(category, [])
    
    def get_skill_categories(self) -> List[str]:
        return list(self.skill_library.keys())
    
    def get_skills(self, category: str) -> List[Dict]:
        return self.skill_library.get(category, [])
    
    def random_weapon(self, quality: str = None) -> Dict:
        """随机获取武器"""
        all_weapons = []
        for weapons in self.weapon_library.values():
            all_weapons.extend(weapons)
        
        if quality:
            filtered = [w for w in all_weapons if w.get("quality") == quality]
            if filtered:
                return random.choice(filtered)
        
        return random.choice(all_weapons) if all_weapons else {}
    
    def random_skill(self, category: str = None) -> Dict:
        """随机获取技能"""
        if category:
            skills = self.skill_library.get(category, [])
            return random.choice(skills) if skills else {}
        
        all_skills = []
        for skills in self.skill_library.values():
            all_skills.extend(skills)
        return random.choice(all_skills) if all_skills else {}
    
    # ===== 战斗模拟 =====
    
    def simulate_battle(self, enemy: Dict) -> Dict:
        """模拟战斗"""
        if not self.character:
            return {"error": "未创建角色"}
        
        enemy_hp = enemy.get("hp", 100)
        enemy_atk = enemy.get("attack", 10)
        enemy_def = enemy.get("defense", 5)
        
        round_count = 0
        battle_log = []
        
        while self.character.hp > 0 and enemy_hp > 0 and round_count < 20:
            round_count += 1
            
            # 玩家攻击
            player_atk = self.character.attributes.get("力量", 10)
            damage = max(1, player_atk - enemy_def)
            
            # 暴击判定
            luck = self.character.attributes.get("幸运", 10)
            crit = random.randint(1, 100) <= luck
            if crit:
                damage *= 2
            
            enemy_hp -= damage
            battle_log.append(f"第{round_count}回合: {self.character.name}攻击{enemy.get('name', '敌人')}，造成{damage}伤害{'（暴击！）' if crit else ''}")
            
            # 敌人攻击
            if enemy_hp > 0:
                player_def = self.character.attributes.get("体质", 10)
                enemy_damage = max(1, enemy_atk - player_def // 2)
                result = self.character.take_damage(enemy_damage)
                battle_log.append(f"  {enemy.get('name', '敌人')}反击，造成{enemy_damage}伤害")
                
                if result["is_dead"]:
                    break
        
        won = enemy_hp <= 0
        self.character.record_battle(won, damage_dealt=enemy.get("hp", 100) - max(0, enemy_hp))
        
        if won:
            exp_gain = enemy.get("exp_reward", 50)
            level_result = self.character.add_exp(exp_gain)
            battle_log.append(f"胜利！获得{exp_gain}经验")
            if level_result["leveled_up"]:
                battle_log.append(f"升级！达到{level_result['current_level']}级！")
        
        self.save()
        
        return {
            "won": won,
            "rounds": round_count,
            "remaining_hp": self.character.hp,
            "log": battle_log,
        }
    
    # ===== 显示 =====
    
    def get_character_summary(self) -> str:
        if self.character:
            return self.character.get_summary()
        return "未创建角色"
    
    def get_stats_display(self) -> str:
        """获取统计数据"""
        if not self.character:
            return "未创建角色"
        
        stats = self.character.stats
        lines = [
            "═══ 战斗统计 ═══",
            f"总战斗次数: {stats.get('总战斗次数', 0)}",
            f"胜利/失败: {stats.get('胜利次数', 0)}/{stats.get('失败次数', 0)}",
            f"胜率: {stats.get('胜利次数', 0) / max(stats.get('总战斗次数', 1), 1) * 100:.1f}%",
            f"总伤害: {stats.get('总伤害', 0):,}",
            f"击杀数: {stats.get('击杀数', 0)}",
            "",
            "═══ 创作统计 ═══",
            f"创作字数: {stats.get('创作字数', 0):,}",
            f"生成章节数: {stats.get('生成章节数', 0)}",
            "",
            "═══ 成就 ═══",
        ]
        
        for a in self.character.achievements:
            lines.append(f"🏆 {a.get('name', '')}: {a.get('desc', '')}")
        
        if not self.character.achievements:
            lines.append("暂无成就")
        
        return "\n".join(lines)
