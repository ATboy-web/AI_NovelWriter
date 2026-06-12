"""
角色成长系统 v2.0 - 多角色管理、自定义武器/技能、AI创建角色
"""

import json
import time
import random
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class CharacterProfile:
    """角色档案"""
    
    # 角色分类系统
    CATEGORIES = {
        # 核心角色
        "主角": {"color": "#f59e0b", "priority": 10, "desc": "故事的核心人物"},
        "女主": {"color": "#ec4899", "priority": 10, "desc": "女主角"},
        "第二主角": {"color": "#f97316", "priority": 9, "desc": "重要的第二主角"},
        
        # 关键人物
        "关键人物": {"color": "#8b5cf6", "priority": 8, "desc": "对剧情有重大影响"},
        "导师": {"color": "#6366f1", "priority": 8, "desc": "主角的老师或引路人"},
        "宿敌": {"color": "#ef4444", "priority": 8, "desc": "主角的主要对手"},
        "大反派": {"color": "#dc2626", "priority": 8, "desc": "最终BOSS"},
        
        # 重要配角
        "主角朋友": {"color": "#3b82f6", "priority": 7, "desc": "主角的好友"},
        "主角女友": {"color": "#ec4899", "priority": 7, "desc": "主角的恋人"},
        "主角妻子": {"color": "#db2777", "priority": 7, "desc": "主角的妻子"},
        "红颜知己": {"color": "#f472b6", "priority": 7, "desc": "理解主角的女性"},
        "兄弟": {"color": "#2563eb", "priority": 7, "desc": "主角的结拜兄弟"},
        "姐妹": {"color": "#a855f7", "priority": 7, "desc": "主角的姐妹"},
        
        # 反派阵营
        "反派": {"color": "#ef4444", "priority": 6, "desc": "反派角色"},
        "反派手下": {"color": "#b91c1c", "priority": 5, "desc": "反派的部下"},
        "叛徒": {"color": "#991b1b", "priority": 6, "desc": "背叛者"},
        "阴谋家": {"color": "#7f1d1d", "priority": 6, "desc": "幕后策划者"},
        
        # 势力人物
        "宗主": {"color": "#d97706", "priority": 7, "desc": "宗门领袖"},
        "长老": {"color": "#b45309", "priority": 6, "desc": "宗门长老"},
        "门主": {"color": "#92400e", "priority": 6, "desc": "门派掌门"},
        "国王": {"color": "#f59e0b", "priority": 7, "desc": "国家统治者"},
        "将军": {"color": "#78350f", "priority": 6, "desc": "军事领袖"},
        "城主": {"color": "#a16207", "priority": 5, "desc": "城市管理者"},
        
        # 特殊身份
        "天才": {"color": "#10b981", "priority": 6, "desc": "天赋异禀之人"},
        "神秘人": {"color": "#6b7280", "priority": 6, "desc": "身份不明"},
        "转世者": {"color": "#8b5cf6", "priority": 7, "desc": "转世重生"},
        "穿越者": {"color": "#7c3aed", "priority": 7, "desc": "穿越而来"},
        "系统持有者": {"color": "#2563eb", "priority": 7, "desc": "拥有系统"},
        
        # 普通角色
        "同门": {"color": "#6b7280", "priority": 4, "desc": "同门师兄弟"},
        "商人": {"color": "#9ca3af", "priority": 3, "desc": "商人"},
        "村民": {"color": "#9ca3af", "priority": 2, "desc": "普通村民"},
        "仆人": {"color": "#d1d5db", "priority": 2, "desc": "仆从"},
        "士兵": {"color": "#6b7280", "priority": 3, "desc": "普通士兵"},
        "路人": {"color": "#9ca3af", "priority": 1, "desc": "路人甲乙丙"},
        
        # 无名小卒
        "无名小卒": {"color": "#4b5563", "priority": 1, "desc": "不重要的小角色"},
        "炮灰": {"color": "#374151", "priority": 1, "desc": "即将领便当"},
    }
    
    # 阵营系统 - 基于立场而非正邪
    FACTIONS = {
        "中立": {"color": "#6b7280", "desc": "不偏不倚"},
        "主角阵营": {"color": "#3b82f6", "desc": "站在主角一方"},
        "敌对阵营": {"color": "#ef4444", "desc": "与主角对立"},
        "第三方势力": {"color": "#f59e0b", "desc": "独立的第三方"},
        "亦敌亦友": {"color": "#8b5cf6", "desc": "时敌时友"},
        "隐藏势力": {"color": "#4b5563", "desc": "暗中活动的势力"},
        "已灭亡": {"color": "#1f2937", "desc": "势力已不存在"},
    }
    
    # 状态系统
    STATUSES = {
        "存活": {"color": "#10b981", "desc": "正常存活"},
        "死亡": {"color": "#ef4444", "desc": "已死亡"},
        "失踪": {"color": "#f59e0b", "desc": "下落不明"},
        "复活": {"color": "#8b5cf6", "desc": "已复活"},
        "重伤": {"color": "#f97316", "desc": "重伤状态"},
        "被俘": {"color": "#dc2626", "desc": "被敌人俘虏"},
        "隐居": {"color": "#6b7280", "desc": "隐居状态"},
        "转世": {"color": "#7c3aed", "desc": "已转世"},
        "化尸": {"color": "#4b5563", "desc": "尸体被操控"},
    }
    
    DEFAULT_ATTRIBUTES = {
        "力量": {"value": 10, "max": 999, "desc": "物理攻击力"},
        "敏捷": {"value": 10, "max": 999, "desc": "速度与闪避"},
        "体质": {"value": 10, "max": 999, "desc": "生命值与防御"},
        "智力": {"value": 10, "max": 999, "desc": "法术强度"},
        "精神": {"value": 10, "max": 999, "desc": "法力值与抗性"},
        "魅力": {"value": 10, "max": 999, "desc": "社交与领导"},
        "幸运": {"value": 10, "max": 999, "desc": "暴击与掉落"},
    }
    
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
        self.title = "无名小卒"
        self.level = 1
        self.exp = 0
        self.exp_to_next = 100
        self.hp = 100
        self.max_hp = 100
        self.mp = 50
        self.max_mp = 50
        self.attributes = {k: v["value"] for k, v in self.DEFAULT_ATTRIBUTES.items()}
        self.weapon = None
        self.armor = None
        self.accessory = None
        self.skills = []
        self.inventory = []
        self.achievements = []
        self.backstory = ""  # 角色背景故事
        self.personality = ""  # 性格特点
        self.appearance = ""  # 外貌描述
        self.stats = {
            "总战斗次数": 0, "胜利次数": 0, "失败次数": 0,
            "总伤害": 0, "总治疗": 0, "击杀数": 0,
            "最高等级": 1, "创作字数": 0, "生成章节数": 0,
        }
        # 新增字段
        self.category = "无名小卒"  # 分类：无名小卒、关键人物、主角朋友、女友、反派等
        self.status = "存活"  # 状态：存活、死亡、失踪、复活
        self.faction = "中立"  # 阵营：正派、反派、中立
        self.importance = 1  # 重要性：1-10
        self.first_appearance = 0  # 首次出现章节
        self.death_chapter = 0  # 死亡章节
        self.revival_chapter = 0  # 复活章节
    
    def _load_from_dict(self, data: Dict):
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
        self.backstory = data.get("backstory", "")
        self.personality = data.get("personality", "")
        self.appearance = data.get("appearance", "")
        self.stats = data.get("stats", {})
        self.created_at = data.get("created_at", datetime.now().isoformat())
        # 新增字段
        self.category = data.get("category", "无名小卒")
        self.status = data.get("status", "存活")
        self.faction = data.get("faction", "中立")
        self.importance = data.get("importance", 1)
        self.first_appearance = data.get("first_appearance", 0)
        self.death_chapter = data.get("death_chapter", 0)
        self.revival_chapter = data.get("revival_chapter", 0)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name, "title": self.title, "level": self.level,
            "exp": self.exp, "exp_to_next": self.exp_to_next,
            "hp": self.hp, "max_hp": self.max_hp, "mp": self.mp, "max_mp": self.max_mp,
            "attributes": self.attributes,
            "weapon": self.weapon, "armor": self.armor, "accessory": self.accessory,
            "skills": self.skills, "inventory": self.inventory, "achievements": self.achievements,
            "backstory": self.backstory, "personality": self.personality, "appearance": self.appearance,
            "stats": self.stats, "created_at": self.created_at,
            "category": self.category, "status": self.status, "faction": self.faction,
            "importance": self.importance, "first_appearance": self.first_appearance,
            "death_chapter": self.death_chapter, "revival_chapter": self.revival_chapter,
        }
    
    def add_exp(self, amount: int) -> Dict:
        self.exp += amount
        leveled_up = False
        levels_gained = 0
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            levels_gained += 1
            leveled_up = True
            self._on_level_up()
        return {"leveled_up": leveled_up, "levels_gained": levels_gained,
                "current_level": self.level, "current_exp": self.exp, "exp_to_next": self.exp_to_next}
    
    def _on_level_up(self):
        self.exp_to_next = int(self.exp_to_next * 1.5)
        for attr in self.attributes:
            self.attributes[attr] = min(self.attributes[attr] + random.randint(1, 3),
                                       self.DEFAULT_ATTRIBUTES[attr]["max"])
        self.max_hp += random.randint(20, 50)
        self.max_mp += random.randint(10, 30)
        self.hp = self.max_hp
        self.mp = self.max_mp
        self._update_title()
        self.stats["最高等级"] = max(self.stats.get("最高等级", 1), self.level)
    
    def _update_title(self):
        titles = {1: "无名小卒", 5: "初出茅庐", 10: "小有名气", 20: "崭露头角",
                  30: "名声大噪", 50: "一方霸主", 70: "威震四方", 80: "天下无敌",
                  90: "超凡入圣", 100: "万古不朽"}
        for level_req in sorted(titles.keys(), reverse=True):
            if self.level >= level_req:
                self.title = titles[level_req]
                break
    
    def equip_weapon(self, weapon: Dict) -> Optional[Dict]:
        old = self.weapon
        self.weapon = weapon
        return old
    
    def equip_armor(self, armor: Dict) -> Optional[Dict]:
        old = self.armor
        self.armor = armor
        return old
    
    def equip_accessory(self, accessory: Dict) -> Optional[Dict]:
        old = self.accessory
        self.accessory = accessory
        return old
    
    def learn_skill(self, skill: Dict) -> bool:
        for s in self.skills:
            if s.get("name") == skill.get("name"):
                return False
        self.skills.append(skill)
        return True
    
    def forget_skill(self, skill_name: str) -> bool:
        for i, s in enumerate(self.skills):
            if s.get("name") == skill_name:
                self.skills.pop(i)
                return True
        return False
    
    def add_item(self, item: Dict):
        for inv_item in self.inventory:
            if inv_item.get("name") == item.get("name") and inv_item.get("stackable", False):
                inv_item["count"] = inv_item.get("count", 1) + item.get("count", 1)
                return
        self.inventory.append(item)
    
    def take_damage(self, damage: int) -> Dict:
        defense = self.attributes.get("体质", 0)
        actual_damage = max(1, damage - defense // 2)
        self.hp = max(0, self.hp - actual_damage)
        return {"damage": actual_damage, "remaining_hp": self.hp, "is_dead": self.hp <= 0}
    
    def heal(self, amount: int) -> Dict:
        old_hp = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return {"healed": self.hp - old_hp, "current_hp": self.hp}
    
    def rest(self):
        self.hp = self.max_hp
        self.mp = self.max_mp
    
    def record_battle(self, won: bool, damage_dealt: int = 0, kills: int = 0):
        self.stats["总战斗次数"] = self.stats.get("总战斗次数", 0) + 1
        if won:
            self.stats["胜利次数"] = self.stats.get("胜利次数", 0) + 1
        else:
            self.stats["失败次数"] = self.stats.get("失败次数", 0) + 1
        self.stats["总伤害"] = self.stats.get("总伤害", 0) + damage_dealt
        self.stats["击杀数"] = self.stats.get("击杀数", 0) + kills
    
    def record_creation(self, word_count: int = 0, chapters: int = 0):
        self.stats["创作字数"] = self.stats.get("创作字数", 0) + word_count
        self.stats["生成章节数"] = self.stats.get("生成章节数", 0) + chapters
        exp_gain = word_count // 10 + chapters * 50
        if exp_gain > 0:
            self.add_exp(exp_gain)
    
    def unlock_achievement(self, name: str, desc: str = ""):
        for a in self.achievements:
            if a.get("name") == name:
                return False
        self.achievements.append({"name": name, "desc": desc, "unlocked_at": datetime.now().isoformat()})
        return True
    
    def get_summary(self) -> str:
        lines = [
            f"═══ {self.name} ═══",
            f"称号: {self.title} | 等级: {self.level}",
            f"经验: {self.exp}/{self.exp_to_next}",
            f"生命: {self.hp}/{self.max_hp} | 法力: {self.mp}/{self.max_mp}",
        ]
        if self.personality:
            lines.append(f"性格: {self.personality}")
        if self.backstory:
            lines.append(f"背景: {self.backstory[:50]}...")
        lines.append("")
        lines.append("─── 属性 ───")
        for attr, value in self.attributes.items():
            lines.append(f"  {attr}: {value}")
        lines.append("")
        w = self.weapon.get('name', '无') if self.weapon else '无'
        a = self.armor.get('name', '无') if self.armor else '无'
        lines.append(f"武器: {w} | 防具: {a}")
        lines.append(f"技能: {len(self.skills)}个")
        return "\n".join(lines)


class CharacterSystem:
    """角色系统管理器 - 支持多角色"""
    
    def __init__(self, novel_dir: Path = None):
        self.novel_dir = novel_dir
        self.save_dir = novel_dir / "characters" if novel_dir else None
        if self.save_dir:
            self.save_dir.mkdir(exist_ok=True)
        
        self.characters: Dict[str, CharacterProfile] = {}
        self.active_name: Optional[str] = None
        
        # 内置库
        self.weapon_library = self._init_weapon_library()
        self.skill_library = self._init_skill_library()
        
        # 自定义库文件
        self.custom_file = novel_dir / "custom_equipment.json" if novel_dir else None
        self.custom_weapons: List[Dict] = []
        self.custom_skills: List[Dict] = []
        self._load_custom()
        
        # 加载已有角色
        self._load_all()
    
    # ===== 多角色管理 =====
    
    def _load_all(self):
        """加载所有角色"""
        if not self.save_dir:
            return
        for f in self.save_dir.glob("*.json"):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                name = data.get("name", f.stem)
                self.characters[name] = CharacterProfile(data=data)
            except Exception:
                pass
        
        # 兼容旧版单文件
        old_file = self.novel_dir / "character_profile.json" if self.novel_dir else None
        if old_file and old_file.exists():
            try:
                with open(old_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get("name", "主角")
                if name not in self.characters:
                    self.characters[name] = CharacterProfile(data=data)
                    self.save_character(name)
                old_file.unlink()  # 删除旧文件
            except Exception:
                pass
        
        # 设置活跃角色
        if self.characters and not self.active_name:
            self.active_name = list(self.characters.keys())[0]
    
    @property
    def character(self) -> Optional[CharacterProfile]:
        if self.active_name and self.active_name in self.characters:
            return self.characters[self.active_name]
        return None
    
    def get_character_names(self) -> List[str]:
        return list(self.characters.keys())
    
    def get_character(self, name: str) -> Optional[CharacterProfile]:
        """获取指定名称的角色"""
        return self.characters.get(name)
    
    def set_active(self, name: str) -> bool:
        if name in self.characters:
            self.active_name = name
            return True
        return False
    
    def create_character(self, name: str, backstory: str = "", personality: str = "", 
                        appearance: str = "", category: str = "无名小卒", 
                        faction: str = "中立", importance: int = 1,
                        first_appearance: int = 0) -> CharacterProfile:
        char = CharacterProfile(name)
        char.backstory = backstory
        char.personality = personality
        char.appearance = appearance
        char.category = category
        char.faction = faction
        char.importance = importance
        char.first_appearance = first_appearance
        self.characters[name] = char
        self.active_name = name
        self.save_character(name)
        return char
    
    def mark_death(self, name: str, chapter: int) -> bool:
        """标记角色死亡"""
        if name in self.characters:
            self.characters[name].status = "死亡"
            self.characters[name].death_chapter = chapter
            self.save_character(name)
            return True
        return False
    
    def mark_revival(self, name: str, chapter: int) -> bool:
        """标记角色复活"""
        if name in self.characters:
            self.characters[name].status = "存活"
            self.characters[name].revival_chapter = chapter
            self.save_character(name)
            return True
        return False
    
    def promote_character(self, name: str, new_category: str, new_importance: int = None) -> bool:
        """提升角色分类"""
        if name in self.characters:
            self.characters[name].category = new_category
            if new_importance:
                self.characters[name].importance = new_importance
            self.save_character(name)
            return True
        return False
    
    def get_characters_by_category(self, category: str) -> List[str]:
        """按分类获取角色"""
        return [name for name, char in self.characters.items() if char.category == category]
    
    def get_alive_characters(self) -> List[str]:
        """获取存活角色"""
        return [name for name, char in self.characters.items() if char.status == "存活"]
    
    def get_dead_characters(self) -> List[str]:
        """获取死亡角色"""
        return [name for name, char in self.characters.items() if char.status == "死亡"]
    
    def get_characters_by_faction(self, faction: str) -> List[str]:
        """按阵营获取角色"""
        return [name for name, char in self.characters.items() if char.faction == faction]
    
    def random_promote_minor(self, chapter: int) -> Optional[str]:
        """随机提升一个无名小卒为关键人物"""
        minors = [name for name, char in self.characters.items() 
                 if char.category == "无名小卒" and char.status == "存活"]
        if minors:
            name = random.choice(minors)
            self.promote_character(name, "关键人物", importance=5)
            self.characters[name].faction = random.choice(["正派", "反派"])
            return name
        return None
    
    def delete_character(self, name: str) -> bool:
        if name in self.characters:
            del self.characters[name]
            if self.save_dir:
                f = self.save_dir / f"{name}.json"
                if f.exists():
                    f.unlink()
            if self.active_name == name:
                self.active_name = list(self.characters.keys())[0] if self.characters else None
            return True
        return False
    
    def rename_character(self, old_name: str, new_name: str) -> bool:
        if old_name in self.characters and new_name not in self.characters:
            char = self.characters.pop(old_name)
            char.name = new_name
            self.characters[new_name] = char
            if self.save_dir:
                old_file = self.save_dir / f"{old_name}.json"
                if old_file.exists():
                    old_file.unlink()
            if self.active_name == old_name:
                self.active_name = new_name
            self.save_character(new_name)
            return True
        return False
    
    def save_character(self, name: str = None):
        name = name or self.active_name
        if name and name in self.characters and self.save_dir:
            f = self.save_dir / f"{name}.json"
            with open(f, 'w', encoding='utf-8') as fp:
                json.dump(self.characters[name].to_dict(), fp, indent=2, ensure_ascii=False)
    
    def save_all(self):
        for name in self.characters:
            self.save_character(name)
    
    def load(self) -> bool:
        """兼容旧接口"""
        self._load_all()
        return bool(self.characters)
    
    # ===== AI创建角色 =====
    
    def ai_create_character(self, ai_client, novel_context: str = "", 
                           role: str = "主角") -> Dict:
        """通过AI自动创建角色"""
        system = """你是专业的游戏角色设计师。请根据提供的信息创建一个详细的角色档案。
输出JSON格式：
{
    "name": "角色名",
    "title": "称号",
    "personality": "性格特点",
    "appearance": "外貌描述",
    "backstory": "背景故事（50-100字）",
    "attributes": {"力量": 数值, "敏捷": 数值, "体质": 数值, "智力": 数值, "精神": 数值, "魅力": 数值, "幸运": 数值},
    "weapon_suggestion": "建议武器名",
    "skill_suggestions": ["技能1", "技能2"]
}
属性范围1-50，主角偏强(20-40)，配角偏弱(10-25)。"""
        
        prompt = f"角色类型: {role}\n"
        if novel_context:
            prompt += f"小说背景: {novel_context[:500]}\n"
        prompt += "\n请创建一个有趣的角色。"
        
        try:
            response = ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1000)
            
            # 解析JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                
                # 创建角色
                char = self.create_character(
                    name=data.get("name", "未命名"),
                    backstory=data.get("backstory", ""),
                    personality=data.get("personality", ""),
                    appearance=data.get("appearance", ""),
                )
                char.title = data.get("title", char.title)
                
                # 设置属性
                if "attributes" in data:
                    for attr, val in data["attributes"].items():
                        if attr in char.attributes:
                            char.attributes[attr] = max(1, min(999, int(val)))
                
                # 设置初始HP/MP
                char.max_hp = char.attributes.get("体质", 10) * 10
                char.hp = char.max_hp
                char.max_mp = char.attributes.get("精神", 10) * 5
                char.mp = char.max_mp
                
                self.save_character()
                
                return {
                    "success": True,
                    "character": char,
                    "weapon_suggestion": data.get("weapon_suggestion", ""),
                    "skill_suggestions": data.get("skill_suggestions", []),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "AI返回格式错误"}
    
    # ===== 自定义武器/技能 =====
    
    def _load_custom(self):
        if self.custom_file and self.custom_file.exists():
            try:
                with open(self.custom_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.custom_weapons = data.get("weapons", [])
                self.custom_skills = data.get("skills", [])
            except Exception:
                pass
    
    def _save_custom(self):
        if self.custom_file:
            with open(self.custom_file, 'w', encoding='utf-8') as f:
                json.dump({"weapons": self.custom_weapons, "skills": self.custom_skills}, 
                         f, indent=2, ensure_ascii=False)
    
    def add_custom_weapon(self, name: str, category: str, quality: str, 
                         desc: str, attributes: Dict) -> Dict:
        """添加自定义武器"""
        weapon = {"name": name, "quality": quality, "desc": desc, 
                 "attributes": attributes, "category": category, "custom": True}
        self.custom_weapons.append(weapon)
        self._save_custom()
        return weapon
    
    def add_custom_skill(self, name: str, skill_type: str, desc: str, 
                        mp_cost: int = 0, **kwargs) -> Dict:
        """添加自定义技能"""
        skill = {"name": name, "type": skill_type, "desc": desc, 
                "mp_cost": mp_cost, "custom": True, **kwargs}
        self.custom_skills.append(skill)
        self._save_custom()
        return skill
    
    def delete_custom_weapon(self, index: int) -> bool:
        if 0 <= index < len(self.custom_weapons):
            self.custom_weapons.pop(index)
            self._save_custom()
            return True
        return False
    
    def delete_custom_skill(self, index: int) -> bool:
        if 0 <= index < len(self.custom_skills):
            self.custom_skills.pop(index)
            self._save_custom()
            return True
        return False
    
    # ===== 武器/技能库 =====
    
    def _init_weapon_library(self) -> Dict[str, List[Dict]]:
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
                {"name": "天魔刀", "quality": "仙品", "desc": "魔族至宝", "attributes": {"力量": 60, "精神": -10, "幸运": 20}},
            ],
            "枪": [
                {"name": "长枪", "quality": "凡品", "desc": "普通长枪", "attributes": {"力量": 7, "敏捷": 3}},
                {"name": "龙胆亮银枪", "quality": "宝品", "desc": "赵云之枪", "attributes": {"力量": 25, "敏捷": 20, "幸运": 10}},
                {"name": "霸王枪", "quality": "仙品", "desc": "西楚霸王", "attributes": {"力量": 55, "体质": 25}},
            ],
            "弓": [
                {"name": "猎弓", "quality": "凡品", "desc": "猎人之弓", "attributes": {"敏捷": 8, "幸运": 3}},
                {"name": "落日弓", "quality": "宝品", "desc": "射日神弓", "attributes": {"敏捷": 30, "力量": 15, "幸运": 20}},
                {"name": "后羿弓", "quality": "神品", "desc": "射日神器", "attributes": {"敏捷": 80, "力量": 40, "幸运": 50}},
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
            "暗器": [
                {"name": "飞镖", "quality": "凡品", "desc": "暗器入门", "attributes": {"敏捷": 6, "幸运": 5}},
                {"name": "暴雨梨花针", "quality": "宝品", "desc": "暗器之王", "attributes": {"敏捷": 35, "幸运": 25}},
            ],
            "琴": [
                {"name": "焦尾琴", "quality": "灵品", "desc": "音律之宝", "attributes": {"智力": 15, "魅力": 20}},
                {"name": "伏羲琴", "quality": "神品", "desc": "上古神器", "attributes": {"智力": 60, "魅力": 50, "精神": 40}},
            ],
        }
    
    def _init_skill_library(self) -> Dict[str, List[Dict]]:
        return {
            "攻击": [
                {"name": "斩击", "type": "攻击", "desc": "基础斩击", "mp_cost": 0, "damage": 10},
                {"name": "烈焰斩", "type": "攻击", "desc": "附带火焰伤害", "mp_cost": 15, "damage": 30},
                {"name": "雷霆万钧", "type": "攻击", "desc": "雷电攻击", "mp_cost": 30, "damage": 60},
                {"name": "天地一刀", "type": "攻击", "desc": "最强斩击", "mp_cost": 80, "damage": 200},
                {"name": "万剑归宗", "type": "攻击", "desc": "剑气化万千", "mp_cost": 60, "damage": 150},
                {"name": "灭世之炎", "type": "攻击", "desc": "焚尽万物", "mp_cost": 100, "damage": 300},
            ],
            "防御": [
                {"name": "铁壁", "type": "防御", "desc": "提升防御", "mp_cost": 10, "defense_bonus": 20},
                {"name": "金刚不坏", "type": "防御", "desc": "免疫伤害", "mp_cost": 50, "defense_bonus": 100},
                {"name": "太极护体", "type": "防御", "desc": "以柔克刚", "mp_cost": 30, "defense_bonus": 50},
            ],
            "治疗": [
                {"name": "治愈术", "type": "治疗", "desc": "恢复生命", "mp_cost": 20, "heal": 50},
                {"name": "回春术", "type": "治疗", "desc": "持续恢复", "mp_cost": 40, "heal": 100},
                {"name": "圣光洗礼", "type": "治疗", "desc": "群体治疗", "mp_cost": 80, "heal": 200},
            ],
            "辅助": [
                {"name": "疾风步", "type": "辅助", "desc": "提升速度", "mp_cost": 15, "effect": "speed_up"},
                {"name": "洞察", "type": "辅助", "desc": "提升暴击", "mp_cost": 10, "effect": "crit_up"},
                {"name": "战意昂扬", "type": "辅助", "desc": "提升攻击", "mp_cost": 20, "effect": "atk_up"},
                {"name": "灵力涌动", "type": "辅助", "desc": "恢复法力", "mp_cost": 0, "effect": "mp_regen"},
            ],
            "特殊": [
                {"name": "时间暂停", "type": "特殊", "desc": "暂停时间", "mp_cost": 100, "effect": "time_stop"},
                {"name": "复活", "type": "特殊", "desc": "复活一次", "mp_cost": 200, "effect": "revive"},
                {"name": "空间跳跃", "type": "特殊", "desc": "瞬移", "mp_cost": 60, "effect": "teleport"},
                {"name": "命运改写", "type": "特殊", "desc": "改变因果", "mp_cost": 150, "effect": "rewrite"},
            ],
            "禁术": [
                {"name": "焚血术", "type": "禁术", "desc": "燃烧生命换取力量", "mp_cost": 0, "damage": 500, "self_damage": 100},
                {"name": "同归于尽", "type": "禁术", "desc": "与敌人玉石俱焚", "mp_cost": 0, "damage": 9999, "self_damage": 9999},
            ],
        }
    
    def get_weapon_categories(self) -> List[str]:
        cats = list(self.weapon_library.keys())
        # 添加自定义武器的类别
        for w in self.custom_weapons:
            cat = w.get("category", "自定义")
            if cat not in cats:
                cats.append(cat)
        return cats
    
    def get_weapons(self, category: str) -> List[Dict]:
        weapons = self.weapon_library.get(category, [])
        # 添加自定义武器
        for w in self.custom_weapons:
            if w.get("category") == category:
                weapons.append(w)
        return weapons
    
    def get_all_weapons(self) -> List[Dict]:
        all_w = []
        for weapons in self.weapon_library.values():
            all_w.extend(weapons)
        all_w.extend(self.custom_weapons)
        return all_w
    
    def get_skill_categories(self) -> List[str]:
        cats = list(self.skill_library.keys())
        for s in self.custom_skills:
            cat = s.get("type", "自定义")
            if cat not in cats:
                cats.append(cat)
        return cats
    
    def get_skills(self, category: str) -> List[Dict]:
        skills = self.skill_library.get(category, [])
        for s in self.custom_skills:
            if s.get("type") == category:
                skills.append(s)
        return skills
    
    def get_all_skills(self) -> List[Dict]:
        all_s = []
        for skills in self.skill_library.values():
            all_s.extend(skills)
        all_s.extend(self.custom_skills)
        return all_s
    
    def random_weapon(self, quality: str = None) -> Dict:
        all_w = self.get_all_weapons()
        if quality:
            filtered = [w for w in all_w if w.get("quality") == quality]
            return random.choice(filtered) if filtered else random.choice(all_w) if all_w else {}
        return random.choice(all_w) if all_w else {}
    
    def random_skill(self, category: str = None) -> Dict:
        if category:
            skills = self.get_skills(category)
            return random.choice(skills) if skills else {}
        all_s = self.get_all_skills()
        return random.choice(all_s) if all_s else {}
    
    # ===== 战斗模拟 =====
    
    def simulate_battle(self, enemy: Dict) -> Dict:
        if not self.character:
            return {"error": "未创建角色"}
        
        enemy_hp = enemy.get("hp", 100)
        enemy_atk = enemy.get("attack", 10)
        enemy_def = enemy.get("defense", 5)
        round_count = 0
        battle_log = []
        
        while self.character.hp > 0 and enemy_hp > 0 and round_count < 20:
            round_count += 1
            player_atk = self.character.attributes.get("力量", 10)
            damage = max(1, player_atk - enemy_def)
            luck = self.character.attributes.get("幸运", 10)
            crit = random.randint(1, 100) <= luck
            if crit:
                damage *= 2
            enemy_hp -= damage
            battle_log.append(f"第{round_count}回合: {self.character.name}造成{damage}伤害{'（暴击！）' if crit else ''}")
            
            if enemy_hp > 0:
                player_def = self.character.attributes.get("体质", 10)
                enemy_damage = max(1, enemy_atk - player_def // 2)
                result = self.character.take_damage(enemy_damage)
                battle_log.append(f"  {enemy.get('name', '敌人')}反击{enemy_damage}伤害")
                if result["is_dead"]:
                    break
        
        won = enemy_hp <= 0
        self.character.record_battle(won, damage_dealt=enemy.get("hp", 100) - max(0, enemy_hp))
        
        if won:
            exp_gain = enemy.get("exp_reward", 50)
            level_result = self.character.add_exp(exp_gain)
            battle_log.append(f"胜利！+{exp_gain}经验")
            if level_result["leveled_up"]:
                battle_log.append(f"★ 升级！→ Lv.{level_result['current_level']}")
        
        self.save_character()
        return {"won": won, "rounds": round_count, "remaining_hp": self.character.hp, "log": battle_log}
    
    # ===== 显示 =====
    
    def get_character_summary(self) -> str:
        return self.character.get_summary() if self.character else "未创建角色"
    
    def get_stats_display(self) -> str:
        if not self.character:
            return "未创建角色"
        stats = self.character.stats
        win_rate = stats.get('胜利次数', 0) / max(stats.get('总战斗次数', 1), 1) * 100
        lines = [
            f"═══ {self.character.name} 战斗统计 ═══",
            f"战斗: {stats.get('总战斗次数', 0)}次 | 胜率: {win_rate:.1f}%",
            f"总伤害: {stats.get('总伤害', 0):,} | 击杀: {stats.get('击杀数', 0)}",
            "",
            "═══ 创作统计 ═══",
            f"字数: {stats.get('创作字数', 0):,} | 章节: {stats.get('生成章节数', 0)}",
        ]
        if self.character.achievements:
            lines.append("")
            lines.append("═══ 成就 ═══")
            for a in self.character.achievements:
                lines.append(f"🏆 {a.get('name', '')}")
        return "\n".join(lines)
