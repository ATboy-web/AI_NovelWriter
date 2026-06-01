"""
AI小说创作工具集
包含：元素库、桥段库、描写库、对话推演、故事流推演、风格转换、智能改编
所有功能模块可联动
"""

import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


# ==================== 小说元素库 ====================

class ElementLibrary:
    """小说元素库 - 预设大量小说元素，可组合生成背景设定"""
    
    CATEGORIES = {
        "前端情节流": {
            "desc": "网文开头的经典情节模式",
            "items": [
                {"name": "重生回到过去", "tags": ["重生", "都市", "逆袭"], "template": "主角{name}在{event}后意外重生回到{time}，这一次他决定{goal}。"},
                {"name": "系统觉醒", "tags": ["系统", "金手指", "升级"], "template": "在{moment}，{name}脑海中响起冰冷的机械声：'叮，{system_name}已绑定宿主。'"},
                {"name": "被退婚", "tags": ["打脸", "逆袭", "爽文"], "template": "'你不过是个废物，也配娶我？'{female}当着所有人的面撕毁婚约。{name}冷笑：'三年后，你会后悔的。'"},
                {"name": "意外获得传承", "tags": ["传承", "金手指", "修仙"], "template": "{name}在{place}意外触碰了{artifact}，一道金光没入他的眉心，无数信息涌入脑海..."},
                {"name": "末日降临", "tags": ["末日", "生存", "异能"], "template": "2024年12月21日，天空裂开一道血红色的缝隙。从那一刻起，世界变了。{name}发现自己获得了{ability}。"},
                {"name": "穿越异世界", "tags": ["穿越", "异世界", "冒险"], "template": "一道白光闪过，{name}发现自己站在一个完全陌生的地方。空气中弥漫着{smell}，远处传来{sound}。"},
                {"name": "被赶出家族", "tags": ["家族", "逆袭", "打脸"], "template": "'从今天起，你不再是{family}的人！'家主冷冷地扔下一块令牌。{name}捡起令牌，转身离去。"},
                {"name": "捡到神器", "tags": ["神器", "金手指", "冒险"], "template": "在{place}的角落里，{name}发现了一个散发微光的{item}。当他触碰的瞬间，整个世界都变了。"},
            ]
        },
        "短篇故事流": {
            "desc": "短篇故事的核心情节模式",
            "items": [
                {"name": "一封信改变命运", "template": "那封信躺在信箱里，看起来普普通通。但当{name}打开它的时候，他的人生从此改变。"},
                {"name": "最后一天", "template": "如果今天是你生命的最后一天，你会做什么？{name}从来没想过这个问题，直到医生说出了那个数字。"},
                {"name": "重逢", "template": "十年后的重逢，她还是那个笑容，只是眼角多了些细纹。'{name}，好久不见。'"},
                {"name": "秘密", "template": "每个人都有秘密。{name}的秘密是{secret}。他以为这辈子都不会有人知道。"},
            ]
        },
        "世界布局": {
            "desc": "世界的整体架构和分布",
            "items": [
                {"name": "九天十地", "template": "九天之上，仙宫林立；十地之下，万族争霸。天地之间，是一片无尽的{region}。"},
                {"name": "三界六道", "template": "三界：人界、仙界、神界。六道：天道、人道、阿修罗道、畜生道、饿鬼道、地狱道。"},
                {"name": "星辰大海", "template": "银河系只是起点。在{distance}光年之外，有一个名为{name}的星系，那里{feature}。"},
                {"name": "大陆板块", "template": "这片大陆被分为{count}个板块：{regions}。每个板块都有独特的{feature}。"},
            ]
        },
        "势力结构": {
            "desc": "世界中的各种势力和组织",
            "items": [
                {"name": "四大宗门", "template": "大陆上最强的四大宗门：{name1}（擅长{skill1}）、{name2}（擅长{skill2}）、{name3}（擅长{skill3}）、{name4}（擅长{skill4}）。"},
                {"name": "帝国争霸", "template": "大陆上有{count}个强大帝国：{empires}。他们之间{relationship}，表面{peace}，实则暗流涌动。"},
                {"name": "地下势力", "template": "在光明的背后，有一个庞大的地下组织——{name}。他们{purpose}，成员遍布{area}。"},
                {"name": "学院体系", "template": "{name}学院是大陆最顶尖的学府，分为{count}个院系：{departments}。只有天才中的天才才能入学。"},
            ]
        },
        "人物设定": {
            "desc": "角色的基础设定模板",
            "items": [
                {"name": "天才主角", "template": "{name}，{age}岁，{appearance}。性格{personality}，拥有{talent}，却被所有人认为是{label}。"},
                {"name": "反派BOSS", "template": "{name}，{title}，实力{level}。外表{appearance}，内心{inner}。他的目标是{goal}，手段{method}。"},
                {"name": "红颜知己", "template": "{name}，{age}岁，{identity}。容貌{beauty}，性格{personality}。与主角的关系是{relation}。"},
                {"name": "忠心跟班", "template": "{name}，主角的{relation}。外表{appearance}，能力{ability}。对主角{attitude}，愿意为他{sacrifice}。"},
            ]
        },
        "修炼体系": {
            "desc": "力量等级和修炼系统",
            "items": [
                {"name": "九重天体系", "template": "修炼境界：{levels}。每突破一重天，{effect}。九重天之上，是传说中的{ultimate}。"},
                {"name": "五行体系", "template": "五行：金、木、水、火、土。修炼者需{method}，突破{barrier}，最终{goal}。"},
                {"name": "科技修炼", "template": "在这个世界，修炼与科技融合。通过{device}，可以{effect}。等级：{levels}。"},
                {"name": "血脉体系", "template": "血脉决定一切。{level1}血脉→{level2}→{level3}→{ultimate}。主角拥有{special}血脉。"},
            ]
        },
        "灭世场景": {
            "desc": "世界级的灾难和危机",
            "items": [
                {"name": "天地大劫", "template": "每隔{years}年，天地会降临一次大劫。{effect}，只有{condition}才能存活。"},
                {"name": "魔族入侵", "template": "封印千年的魔族再次降临。天空{sky}，大地{earth}，无数{creature}涌入人间。"},
                {"name": "天道崩塌", "template": "天道崩塌，规则混乱。{effect1}，{effect2}，整个世界陷入{state}。"},
            ]
        },
        "特殊地理": {
            "desc": "特殊的地形和场所",
            "items": [
                {"name": "禁地", "template": "{name}禁地，位于{location}。进入者{danger}，但据说里面有{treasure}。"},
                {"name": "秘境", "template": "每{years}年开启一次的{name}秘境。内部{environment}，产出{resource}。"},
                {"name": "险地", "template": "{name}，大陆最危险的地方之一。{danger}，但也是{opportunity}的圣地。"},
            ]
        },
        "特定种族": {
            "desc": "非人类种族设定",
            "items": [
                {"name": "龙族", "template": "龙族，{origin}。寿命{lifespan}，天赋{talent}，性格{personality}。与人类{relation}。"},
                {"name": "精灵族", "template": "精灵族，居住在{location}。外貌{appearance}，擅长{skill}，信仰{belief}。"},
                {"name": "机械族", "template": "机械族，由{origin}创造。身体{body}，核心{core}，目标{goal}。"},
            ]
        },
        "神秘遗迹": {
            "desc": "古代遗迹和秘密",
            "items": [
                {"name": "上古遗迹", "template": "{name}遗迹，据说是{civilization}留下的。内部{structure}，藏有{secret}。"},
                {"name": "远古战场", "template": "远古时期，{side1}与{side2}在此大战。至今残留{residue}，偶尔会有{phenomenon}。"},
            ]
        },
        "世界规则": {
            "desc": "世界的底层规则",
            "items": [
                {"name": "天道规则", "template": "天道规则：{rule1}。违反者{punishment}。但主角发现了{loophole}。"},
                {"name": "因果法则", "template": "在这个世界，{cause}必然导致{effect}。善有善报，恶有恶报，只是时间问题。"},
            ]
        },
        "诅咒": {
            "desc": "各种诅咒设定",
            "items": [
                {"name": "血脉诅咒", "template": "{family}家族世代受到诅咒：{effect}。据说只有{condition}才能解除。"},
                {"name": "地域诅咒", "template": "踏入{place}的人会受到诅咒：{effect}。至今无人能解。"},
            ]
        },
        "语言": {
            "desc": "特殊语言和文字",
            "items": [
                {"name": "上古文字", "template": "上古文字，{civilization}所创。能读懂的人可以{power}，但大多数人看到的只是{normal}。"},
                {"name": "龙语", "template": "龙语，龙族的专属语言。说出的每个字都蕴含{power}，普通人听到只会感到{effect}。"},
            ]
        },
        "武器设定": {
            "desc": "各种武器和法宝",
            "items": [
                {"name": "神兵利器", "template": "{name}，{rank}级神兵。由{material}打造，蕴含{power}。持有者可{ability}。"},
                {"name": "法宝", "template": "{name}，{type}法宝。功能{function}，威力{power}。需要{condition}才能催动。"},
            ]
        },
        "城镇描写": {
            "desc": "城镇和建筑描写",
            "items": [
                {"name": "繁华都城", "template": "{name}城，大陆最繁华的都城。城墙{wall}，街道{street}，人口{population}。这里有{feature}。"},
                {"name": "边陲小镇", "template": "{name}镇，位于{location}。虽然{small}，但{feature}。镇上最出名的是{special}。"},
            ]
        },
    }
    
    def __init__(self, novel_dir: Optional[Path] = None):
        self.novel_dir = novel_dir
        self.custom_dir = None
        if novel_dir:
            self.custom_dir = novel_dir / "elements"
            self.custom_dir.mkdir(exist_ok=True)
    
    def get_categories(self) -> List[Dict]:
        """获取所有类别"""
        cats = [{"name": k, "desc": v["desc"], "count": len(v["items"])} for k, v in self.CATEGORIES.items()]
        # 添加自定义类别
        if self.custom_dir:
            for f in self.custom_dir.glob("*.json"):
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                cats.append({"name": f.stem, "desc": data.get("desc", ""), "count": len(data.get("items", []))})
        return cats
    
    def get_items(self, category: str) -> List[Dict]:
        """获取某类别的所有元素"""
        if category in self.CATEGORIES:
            return self.CATEGORIES[category]["items"]
        # 尝试从自定义加载
        if self.custom_dir:
            f = self.custom_dir / f"{category}.json"
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fp:
                    return json.load(fp).get("items", [])
        return []
    
    def add_custom_item(self, category: str, item: Dict):
        """添加自定义元素"""
        if not self.custom_dir:
            return
        f = self.custom_dir / f"{category}.json"
        data = {"desc": "", "items": []}
        if f.exists():
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
        data["items"].append(item)
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
    
    def generate_background(self, ai_client, selected_elements: List[Dict], novel_type: str, title: str) -> str:
        """根据选中的元素组合生成背景设定"""
        elements_desc = []
        for elem in selected_elements:
            elements_desc.append(f"- {elem.get('name', '')}: {elem.get('template', '')}")
        
        prompt = f"""请根据以下小说元素，组合生成一个完整的小说背景设定。

小说类型：{novel_type}
小说标题：{title}

选中的元素：
{chr(10).join(elements_desc)}

请生成一个完整的背景设定，包括：
1. 世界观概述
2. 主要势力
3. 核心冲突
4. 主角定位

直接输出设定内容，不要添加额外说明。"""
        
        return ai_client.chat([{"role": "user", "content": prompt}], 
                             system="你是一位专业的小说世界观设定师。", max_tokens=2000)


# ==================== 角色桥段库 ====================

class BridgeLibrary:
    """角色互动桥段库 - 经典网文桥段模板"""
    
    BRIDGES = {
        "角色对战": {
            "desc": "角色之间的战斗场面",
            "templates": [
                "{char1}冷冷地看着{char2}，缓缓拔出{weapon}。'今天，就让你见识一下，什么叫真正的{skill}。'",
                "两道身影在{place}上空交错，每一次碰撞都引发惊天动地的轰鸣。{char1}的{attack1}与{char2}的{attack2}激烈对撞...",
                "'你以为你赢了？'{char2}擦去嘴角的血迹，眼中闪过疯狂的光芒，'真正的战斗，现在才开始！'",
            ]
        },
        "能力效果": {
            "desc": "特殊能力的施展描写",
            "templates": [
                "{char}双手结印，口中低喝：'{technique}！'刹那间，{effect}。",
                "一道{color}光芒从{char}体内爆发而出，{effect}。周围的人纷纷后退，脸上露出惊骇之色。",
                "{char}睁开双眼，瞳孔已变成{color}。'这就是{power}的力量吗？'他喃喃自语。",
            ]
        },
        "角色追逐": {
            "desc": "追逐场面",
            "templates": [
                "{char1}在前方狂奔，{char2}紧追不舍。'你逃不掉的！'{char2}的声音从身后传来。",
                "两道身影在{place}之间穿梭，{char1}不断变换方向，但{char2}始终如影随形。",
                "'停下！'{char2}一掌拍出，{char1}侧身躲过，借力跃上{obstacle}。",
            ]
        },
        "角色登场": {
            "desc": "重要角色的出场",
            "templates": [
                "就在{crisis}之际，一道{color}身影从天而降。'{dialogue}'所有人的目光都聚焦在这个突然出现的人身上。",
                "'谁？！'众人抬头望去，只见{appearance}的人负手而立，周身{aura}。",
                "大门缓缓打开，{appearance}的{char}缓步走入。整个大厅瞬间安静下来。",
            ]
        },
        "角色退场": {
            "desc": "角色的离开或死亡",
            "templates": [
                "{char}望着{place}的方向，轻叹一声。'是时候离开了。'转身走入雨幕中，背影渐行渐远。",
                "'记住我。'{char}最后看了{target}一眼，身体化作点点光芒，消散在天地间。",
                "{char}跪倒在地，鲜血染红了衣襟。'对不起...我...食言了...'声音渐弱，最终归于沉寂。",
            ]
        },
        "角色修炼": {
            "desc": "修炼突破的描写",
            "templates": [
                "{char}盘膝而坐，体内{energy}运转。{time}后，他猛地睁开双眼——突破了！{effect}。",
                "天地灵气疯狂涌入{char}体内，他的气势节节攀升。'破！'{char}大喝一声，{barrier}应声而碎。",
                "在{place}中，{char}已经闭关了{time}。今日，终于{result}。",
            ]
        },
        "情侣购物": {
            "desc": "情侣逛街购物",
            "templates": [
                "'这件好看吗？'{female}换了一身{clothing}，在{char}面前转了一圈。{char}看呆了：'好...好看...'",
                "{char}手里已经提了{n}个袋子，{female}还在前面兴高采烈地逛着。'老公，快来！这家店有{item}！'",
                "'太贵了吧？'{char}看着价格标签倒吸一口凉气。{female}撅起嘴：'你到底爱不爱我？'",
            ]
        },
        "情侣看电影": {
            "desc": "情侣一起看电影",
            "templates": [
                "电影院里，{female}靠在{char}肩上，手里抱着爆米花。银幕上的光影映在她脸上，格外动人。",
                "看到感人的情节，{female}悄悄抹眼泪。{char}假装没看见，却把她的手握得更紧了。",
                "'这个结局我不喜欢。'{female}走出影院还在嘟囔。{char}笑道：'那我们来改写结局？'",
            ]
        },
        "角色诱惑": {
            "desc": "诱惑场景",
            "templates": [
                "{char1}靠近{char2}，气息喷洒在耳边：'你确定...要拒绝我？'{char2}的呼吸明显急促起来。",
                "'你知道你在做什么吗？'{char2}努力保持冷静。{char1}轻笑：'当然知道。而且...我很清醒。'",
                "月光下，{char1}的侧脸美得不真实。{char2}移开目光，却发现心跳已经乱了节奏。",
            ]
        },
        "角色苦肉计": {
            "desc": "故意受伤博取同情",
            "templates": [
                "{char}故意挡在{target}身前，硬接了{enemy}一击。鲜血飞溅，{target}惊呼：'{name}！'",
                "'没关系...'{char}捂着伤口，勉强露出笑容：'只要你没事...'",
                "{target}抱着受伤的{char}，泪水夺眶而出。'你这个傻子...为什么要这么做...'",
            ]
        },
        "角色挑衅": {
            "desc": "言语挑衅和激怒",
            "templates": [
                "'就这？'{char}轻蔑地笑了，'我还以为{name}有多厉害，不过如此。'",
                "'你说完了？'{char}不为所动，'那轮到我了。'",
                "'你知道你在跟谁说话吗？'{enemy}脸色铁青。{char}耸肩：'一个马上要输的人。'",
            ]
        },
        "情侣情话": {
            "desc": "甜蜜的情话",
            "templates": [
                "'我有没有说过，你笑起来真好看？'{char}认真地看着{female}。{female}脸红：'你每天都说...'",
                "'如果有一天我变老了变丑了，你还会喜欢我吗？'{female}问。{char}：'我也会变老变丑啊，我们一起。'",
                "'你知道我最喜欢什么吗？'{char}神秘兮兮。{female}好奇：'什么？''你。'",
            ]
        },
        "情侣暧昧": {
            "desc": "暧昧的互动",
            "templates": [
                "两人靠得很近，能感受到彼此的呼吸。{char}低头，{female}抬头，目光交汇的瞬间，空气仿佛凝固了。",
                "'你...你离我太近了...'{female}后退一步，却被{char}揽住腰：'这样呢？'",
                "雨中，{char}把外套披在{female}肩上。{female}抬头，雨水模糊了视线，却看清了他的笑容。",
            ]
        },
        "撞见起床": {
            "desc": "撞见角色刚起床",
            "templates": [
                "{char1}推开门，愣住了。{char2}正揉着眼睛从床上坐起来，头发乱糟糟的，衣服...好像没穿好。'啊！！！'",
                "'你怎么不敲门！'{char2}手忙脚乱地拉被子。{char1}已经石化在门口，脑子里一片空白。",
                "{char2}打了个哈欠，完全没注意到门口有人。等反应过来，尖叫声差点掀翻屋顶。",
            ]
        },
    }
    
    def __init__(self, novel_dir: Optional[Path] = None):
        self.novel_dir = novel_dir
        self.custom_dir = None
        if novel_dir:
            self.custom_dir = novel_dir / "bridges"
            self.custom_dir.mkdir(exist_ok=True)
    
    def get_categories(self) -> List[Dict]:
        cats = [{"name": k, "desc": v["desc"], "count": len(v["templates"])} for k, v in self.BRIDGES.items()]
        if self.custom_dir:
            for f in self.custom_dir.glob("*.json"):
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                cats.append({"name": f.stem, "desc": data.get("desc", ""), "count": len(data.get("templates", []))})
        return cats
    
    def get_templates(self, category: str) -> List[str]:
        if category in self.BRIDGES:
            return self.BRIDGES[category]["templates"]
        if self.custom_dir:
            f = self.custom_dir / f"{category}.json"
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fp:
                    return json.load(fp).get("templates", [])
        return []
    
    def generate_bridge(self, ai_client, category: str, characters: Dict[str, str], setting: str) -> str:
        """根据模板和角色信息生成桥段"""
        templates = self.get_templates(category)
        template_text = "\n".join(templates[:3]) if templates else ""
        
        chars_desc = "\n".join([f"- {k}: {v}" for k, v in characters.items()])
        
        prompt = f"""请根据以下桥段模板和角色信息，生成一段完整的小说桥段。

桥段类型：{category}
参考模板：
{template_text}

角色信息：
{chars_desc}

场景设定：{setting}

请生成一段300-500字的桥段，要求：
1. 符合桥段类型的特点
2. 角色性格鲜明
3. 对话自然生动
4. 描写细腻

直接输出桥段内容。"""
        
        return ai_client.chat([{"role": "user", "content": prompt}],
                             system="你是一位专业的小说桥段作家。", max_tokens=1500)


# ==================== 情景对话推演 ====================

class DialogueEngine:
    """情景对话流推演引擎"""
    
    def __init__(self, ai_client):
        self.ai = ai_client
        self.dialogue_history: List[Dict] = []
    
    def start_dialogue(self, scenario: str, characters: List[Dict], style: str = "日常") -> List[Dict]:
        """开始一段对话推演"""
        self.dialogue_history = []
        
        chars_desc = "\n".join([f"- {c['name']}: {c.get('personality', '')}, 说话风格: {c.get('style', '')}" 
                                for c in characters])
        
        prompt = f"""请根据以下场景和角色信息，生成3-5轮对话。

场景：{scenario}
对话风格：{style}

角色信息：
{chars_desc}

要求：
1. 每轮对话包含角色名和对话内容
2. 可以包含简短的动作描写（括号内）
3. 对话要符合角色性格
4. 情节要有推进

请以JSON数组格式输出：
[{{"speaker": "角色名", "action": "动作（可选）", "content": "对话内容"}}, ...]"""
        
        response = self.ai.chat([{"role": "user", "content": prompt}],
                               system="你是一位专业的剧本对话作家。", max_tokens=2000)
        
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                self.dialogue_history = json.loads(json_match.group())
        except:
            self.dialogue_history = [{"speaker": "旁白", "content": response}]
        
        return self.dialogue_history
    
    def continue_dialogue(self, hint: str = "", count: int = 3) -> List[Dict]:
        """继续对话推演"""
        history_text = "\n".join([f"{d['speaker']}: {d.get('action', '')} {d['content']}" 
                                  for d in self.dialogue_history[-10:]])
        
        prompt = f"""请继续以下对话，生成{count}轮新的对话。

已有对话：
{history_text}

{f'继续方向：{hint}' if hint else ''}

请以JSON数组格式输出新对话。"""
        
        response = self.ai.chat([{"role": "user", "content": prompt}],
                               system="你是一位专业的剧本对话作家。", max_tokens=1500)
        
        new_dialogue = []
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                new_dialogue = json.loads(json_match.group())
        except:
            pass
        
        self.dialogue_history.extend(new_dialogue)
        return new_dialogue
    
    def get_history(self) -> List[Dict]:
        return self.dialogue_history
    
    def export_text(self) -> str:
        """导出为文本格式"""
        lines = []
        for d in self.dialogue_history:
            action = f"（{d['action']}）" if d.get('action') else ""
            lines.append(f"{d['speaker']}{action}：{d['content']}")
        return "\n".join(lines)


# ==================== 故事流推演 ====================

class StoryFlowEngine:
    """故事流推演引擎 - 两种模式"""
    
    def __init__(self, ai_client):
        self.ai = ai_client
    
    def mode1_forward(self, background: str, characters: str, events: str, count: int = 5) -> str:
        """模式1：基于背景、人物、事件推演过程"""
        prompt = f"""请根据以下信息，推演故事的发展过程。

故事背景：{background}
主要人物：{characters}
后续事件：{events}

请推演{count}个关键节点，每个节点包含：
1. 场景描写
2. 角色行为
3. 对话（如有）
4. 情节转折

要求：逻辑连贯，情节紧凑，描写生动。

直接输出故事内容。"""
        
        return self.ai.chat([{"role": "user", "content": prompt}],
                           system="你是一位专业的小说故事流推演师。", max_tokens=3000)
    
    def mode2_bridge(self, beginning: str, ending: str, count: int = 5) -> str:
        """模式2：基于开端与结局推演中间流程"""
        prompt = f"""请根据开端和结局，推演中间的故事流程。

开端：{beginning}
结局：{ending}

请生成{count}个中间环节，使故事从开端自然过渡到结局。每个环节包含：
1. 场景描写
2. 关键事件
3. 角色反应
4. 情节推进

要求：逻辑合理，过渡自然，有起承转合。

直接输出故事内容。"""
        
        return self.ai.chat([{"role": "user", "content": prompt}],
                           system="你是一位专业的小说故事流推演师。", max_tokens=3000)
    
    def extract_flow(self, novel_text: str, mode: int = 4) -> str:
        """小说转故事流/叙事
        
        mode=4: 对话内容与细节融合
        mode=10: 保留原小说格式
        """
        if mode == 4:
            system = "你是一位专业的叙事提取师。请将小说内容转换为精炼的叙事结构，保留对话和关键细节。"
            prompt = f"""请将以下小说内容转换为精炼的叙事结构。

要求：
1. 保留所有对话内容
2. 保留关键细节
3. 去除冗余描写
4. 保持故事完整性
5. 对话与细节融合

原文：
{novel_text[:3000]}

请输出精炼的叙事结构。"""
        else:  # mode == 10
            system = "你是一位专业的叙事提取师。请保留原小说的格式进行精炼。"
            prompt = f"""请将以下小说内容进行精炼，保留原有格式。

要求：
1. 保留原文格式（段落、对话格式等）
2. 去除冗余内容
3. 保留核心情节
4. 大幅缩短篇幅

原文：
{novel_text[:3000]}

请输出精炼后的内容。"""
        
        return self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)


# ==================== 风格转换引擎 ====================

class StyleTransferEngine:
    """风格转换引擎 - 网文转网文，仿写、改写"""
    
    STYLES = {
        "热血爽文": "节奏快，爽点密集，打脸频繁，主角无敌",
        "细腻情感": "情感描写细腻，心理活动丰富，节奏舒缓",
        "幽默搞笑": "语言幽默，情节轻松，笑点多",
        "暗黑阴郁": "氛围压抑，情节沉重，人性阴暗面",
        "古风仙侠": "语言古朴，意境悠远，仙气飘飘",
        "都市现实": "贴近现实，语言口语化，社会百态",
        "悬疑紧张": "节奏紧凑，悬念迭起，气氛紧张",
    }
    
    def __init__(self, ai_client):
        self.ai = ai_client
    
    def get_styles(self) -> Dict[str, str]:
        return self.STYLES
    
    def convert_style(self, text: str, target_style: str, keep_plot: bool = True) -> str:
        """风格转换"""
        style_desc = self.STYLES.get(target_style, target_style)
        
        prompt = f"""请将以下文本转换为指定风格。

目标风格：{target_style}（{style_desc}）
保持情节：{'是' if keep_plot else '否'}

原文：
{text[:2000]}

要求：
1. 保持原文的核心情节和人物
2. 调整语言风格以匹配目标风格
3. 修改叙事节奏和表达方式
4. 确保转换后自然流畅

直接输出转换后的文本。"""
        
        return self.ai.chat([{"role": "user", "content": prompt}],
                           system="你是一位专业的风格转换师。", max_tokens=3000)
    
    def imitate_style(self, text: str, sample_text: str) -> str:
        """仿写 - 根据样本风格改写"""
        prompt = f"""请根据样本的风格，改写目标文本。

样本（参考风格）：
{sample_text[:1000]}

目标文本：
{text[:2000]}

要求：
1. 分析样本的语言特点、句式、用词
2. 用样本的风格改写目标文本
3. 保持目标文本的情节内容
4. 风格转换要自然

直接输出改写后的文本。"""
        
        return self.ai.chat([{"role": "user", "content": prompt}],
                           system="你是一位专业的风格仿写师。", max_tokens=3000)


# ==================== 智能改编引擎 ====================

class AdaptEngine:
    """智能改编引擎 - 圈定截取改编，匹配率"""
    
    def __init__(self, ai_client):
        self.ai = ai_client
        self.adapt_history: List[Dict] = []
    
    def adapt_segment(self, original: str, instruction: str, target_type: str = "") -> Dict:
        """改编片段"""
        prompt = f"""请根据指示改编以下文本片段。

原文：
{original[:1500]}

改编指示：{instruction}
{f'目标类型：{target_type}' if target_type else ''}

要求：
1. 保留原文的核心框架
2. 根据指示进行改编
3. 保持逻辑连贯
4. 输出改编后的内容

直接输出改编内容。"""
        
        response = self.ai.chat([{"role": "user", "content": prompt}],
                               system="你是一位专业的小说改编师。", max_tokens=2000)
        
        # 计算匹配率（简化版）
        match_rate = self._calculate_match_rate(original, response)
        
        result = {
            "original": original,
            "adapted": response,
            "instruction": instruction,
            "target_type": target_type,
            "match_rate": match_rate,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.adapt_history.append(result)
        return result
    
    def batch_adapt(self, segments: List[str], instruction: str) -> List[Dict]:
        """批量改编"""
        results = []
        for seg in segments:
            result = self.adapt_segment(seg, instruction)
            results.append(result)
        return results
    
    def random_adapt(self, text: str, count: int = 3) -> List[Dict]:
        """随机抽取片段改编"""
        # 将文本分段
        paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]
        
        if not paragraphs:
            paragraphs = [text[i:i+500] for i in range(0, len(text), 500)]
        
        # 随机选择
        import random
        selected = random.sample(paragraphs, min(count, len(paragraphs)))
        
        results = []
        for seg in selected:
            instructions = [
                "将这段改写为更紧张的氛围",
                "增加更多对话",
                "改为第一人称视角",
                "加入更多细节描写",
                "改写为更幽默的风格",
            ]
            instruction = random.choice(instructions)
            result = self.adapt_segment(seg, instruction)
            results.append(result)
        
        return results
    
    def _calculate_match_rate(self, original: str, adapted: str) -> float:
        """计算匹配率（简化版 - 基于关键词重叠）"""
        # 提取关键词
        def extract_keywords(text):
            # 简单的中文分词（按标点和空格分割）
            words = re.findall(r'[\u4e00-\u9fff]+', text)
            return set(w for w in words if len(w) >= 2)
        
        orig_kw = extract_keywords(original)
        adapt_kw = extract_keywords(adapted)
        
        if not orig_kw:
            return 0.0
        
        overlap = orig_kw & adapt_kw
        return round(len(overlap) / len(orig_kw) * 100, 1)
    
    def get_history(self) -> List[Dict]:
        return self.adapt_history


# ==================== 事物描写库 ====================

class DescriptionLibrary:
    """事物描写库 - 管理和生成描写"""
    
    CATEGORIES = {
        "自然景观": ["日出", "月夜", "暴风雨", "雪山", "沙漠", "森林", "海洋", "星空"],
        "建筑": ["宫殿", "古堡", "高楼", "庙宇", "废墟", "桥梁", "城墙"],
        "人物外貌": ["英俊男子", "美丽女子", "老人", "孩童", "武者", "仙人"],
        "情感": ["愤怒", "悲伤", "喜悦", "恐惧", "惊讶", "厌恶", "期待"],
        "动作": ["战斗", "奔跑", "跳跃", "飞翔", "施法", "修炼"],
        "天气": ["晴天", "阴天", "雨天", "雪天", "风暴", "雾霾"],
        "食物": ["美酒", "佳肴", "毒药", "丹药", "灵果"],
        "服饰": ["铠甲", "长袍", "战衣", "礼服", "破衣"],
        "武器": ["剑", "刀", "枪", "弓", "法杖", "暗器"],
        "魔法/异能": ["火系", "水系", "风系", "雷系", "空间", "时间"],
    }
    
    def __init__(self, novel_dir: Optional[Path] = None):
        self.novel_dir = novel_dir
        self.local_library: Dict[str, List[Dict]] = {}
        if novel_dir:
            lib_file = novel_dir / "descriptions.json"
            if lib_file.exists():
                with open(lib_file, 'r', encoding='utf-8') as f:
                    self.local_library = json.load(f)
    
    def get_categories(self) -> List[str]:
        return list(self.CATEGORIES.keys())
    
    def get_items(self, category: str) -> List[str]:
        return self.CATEGORIES.get(category, [])
    
    def generate_description(self, ai_client, subject: str, category: str, 
                           style: str = "详细", context: str = "") -> str:
        """生成描写"""
        prompt = f"""请生成一段关于"{subject}"的描写。

类别：{category}
描写风格：{style}
{f'上下文：{context}' if context else ''}

要求：
1. 语言生动，有画面感
2. 运用多种感官描写
3. 使用修辞手法
4. 字数200-400字

直接输出描写内容。"""
        
        return ai_client.chat([{"role": "user", "content": prompt}],
                             system="你是一位专业的事物描写作家。", max_tokens=1500)
    
    def add_to_library(self, category: str, name: str, content: str):
        """添加到本地库"""
        if category not in self.local_library:
            self.local_library[category] = []
        self.local_library[category].append({"name": name, "content": content})
        self._save()
    
    def search(self, keyword: str) -> List[Dict]:
        """搜索本地库"""
        results = []
        for cat, items in self.local_library.items():
            for item in items:
                if keyword in item.get("name", "") or keyword in item.get("content", ""):
                    results.append({**item, "category": cat})
        return results
    
    def _save(self):
        if self.novel_dir:
            with open(self.novel_dir / "descriptions.json", 'w', encoding='utf-8') as f:
                json.dump(self.local_library, f, indent=2, ensure_ascii=False)
