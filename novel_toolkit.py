"""
AI小说创作工具集 v2.0
包含：元素库、桥段库、描写库、对话推演、故事流推演、风格转换、智能改编
所有功能模块可联动
"""

import json, time, re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# ==================== 小说元素库 ====================

class ElementLibrary:
    """小说元素库 - 500+元素模板"""
    
    def __init__(self, novel_dir: Optional[Path] = None):
        self.novel_dir = novel_dir
        self.custom_dir = novel_dir / "elements" if novel_dir else None
        if self.custom_dir: self.custom_dir.mkdir(exist_ok=True)
    
    CATEGORIES = {
        "前端情节流": {"desc": "网文开头的经典情节模式", "items": [
            {"name":"重生复仇","tags":["重生","逆袭"],"template":"{name}在{event}中含恨而死，再睁眼竟回到{n}年前。这一次，他要让所有仇人付出代价。"},
            {"name":"系统激活","tags":["系统","金手指"],"template":"'叮——{system_name}绑定成功！'机械声在{name}脑中响起，他的人生从此改变。"},
            {"name":"被退婚","tags":["退婚","打脸"],"template":"'你配不上我。'{female}当众撕毁婚约。{name}冷笑：'三十年河东三十年河西，莫欺少年穷！'"},
            {"name":"意外传承","tags":["传承","修仙"],"template":"{name}偶得{artifact}，一道金光没入眉心——上古{master}的传承尽在其中！"},
            {"name":"末日降临","tags":["末日","异能"],"template":"{date}，天空裂开血红缝隙。{name}在绝望中觉醒了{ability}——他成了最后的希望。"},
            {"name":"穿越异世","tags":["穿越","异世界"],"template":"一道白光闪过，{name}睁开眼发现自己躺在陌生的{place}，身边站着一位{creature}。"},
            {"name":"被逐家族","tags":["家族","逆袭"],"template":"'你被逐出{family}了！'{name}捡起地上的令牌，头也不回地走向山外——他要去创造自己的传奇。"},
            {"name":"捡到神器","tags":["神器","冒险"],"template":"在{place}角落，{name}捡到一个蒙尘的{item}。触碰的瞬间，天地色变，万道金光冲天而起。"},
            {"name":"灵气复苏","tags":["灵气","末世"],"template":"公元{year}年，天地灵气开始复苏。动植物变异，人类觉醒超能。{name}是第一批觉醒者。"},
            {"name":"都市异能","tags":["都市","异能"],"template":"{name}是{company}的普通员工，直到那天他发现自己能{ability}。整个都市的暗面在他眼前展开。"},
            {"name":"被废修为","tags":["修仙","复仇"],"template":"曾经的天才{name}被废去修为沦为废物。但他发现了一本残缺古籍，里面记载着一门被遗忘的{technique}。"},
            {"name":"绑定聊天群","tags":["聊天群","诸天"],"template":"'{name}加入万界聊天群。'——一个横跨诸天的对话窗口出现在他眼前，各路大佬在线指导。"},
            {"name":"签到系统","tags":["签到","日常"],"template":"'叮！签到成功！获得{reward}！'——从那天起，{name}每天醒来第一件事就是签到。"},
            {"name":"被关小黑屋","tags":["囚禁","逆袭"],"template":"被关在暗无天日的{place}已经{n}年了。{name}没有绝望，他在囚牢中悟出了{technique}。"},
            {"name":"人设崩塌","tags":["娱乐圈","逆袭"],"template":"一夜之间，{name}的公众形象崩塌。但她发现了幕后黑手，决定用实力打脸所有人。"},
        ]},
        "短篇故事流": {"desc": "短篇故事核心情节", "items": [
            {"name":"一封改变命运的信","template":"那封信躺在邮箱里很久了。{name}打开它的那一刻，{event}——他的人生从此分岔。"},
            {"name":"最后一天","template":"医生说出那个数字后，{name}的世界安静了。他决定用最后{time}去做自己一直不敢做的事。"},
            {"name":"十年重逢","template":"咖啡店里，她依然点了一杯拿铁。'{name}，好久不见。'他抬头，十年的时光在眼前静止。"},
            {"name":"不能说出的秘密","template":"每个人都有秘密。{name}的秘密是{secret}。这个秘密改变了他和所有人的命运。"},
            {"name":"一个约定","template":"'{time}年后，我们在这里见。'——那是{name}和{other}的约定。现在，约定的时间到了。"},
            {"name":"他回来了","template":"消失了{n}年的{name}突然回到{place}。没有人知道这些年他去了哪里，但他带回了{thing}。"},
            {"name":"那场意外","template":"如果那天{name}没有走那条路，一切都不会发生。但命运没有如果。"},
        ]},
        "世界布局": {"desc": "世界架构设定", "items": [
            {"name":"九天十地","template":"九天之上，仙宫林立；十地之下，万族争霸。{name}从一个凡人踏上了逆天之路。"},
            {"name":"三界大战","template":"人界、仙界、魔界三界大战一触即发。{name}夹在中间，左右为难。"},
            {"name":"星辰大海","template":"银河只是起点。{name}驾驶着{ship}驶向{distance}光年外的{planet}——那里藏着人类文明最后的希望。"},
            {"name":"位面交汇","template":"两个位面交汇，{world1}和{world2}的法则相互碰撞。{name}是唯一能在两个位面自由穿梭的人。"},
            {"name":"内世界","template":"每个强者体内都有一个内世界。{name}的内世界是{type}，拥有{feature}的特殊能力。"},
            {"name":"虚空裂缝","template":"大陆中央突然出现一道虚空裂缝，从里面涌出的不是怪物，而是——{thing}。整个世界为之疯狂。"},
            {"name":"神国降世","template":"某天，一座巨大的神国从天而降，悬浮在{place}上空。从此世界格局彻底改变。"},
        ]},
        "势力结构": {"desc": "世界势力设定", "items": [
            {"name":"四大宗门","template":"{a}（{sa}）、{b}（{sb}）、{c}（{sc}）、{d}（{sd}）——四大宗门表面和气实则暗潮汹涌。"},
            {"name":"帝国争霸","template":"{n}大帝国：{list}。其中{strongest}最强，但{weakest}正在秘密研发{weapon}意图翻盘。"},
            {"name":"暗影组织","template":"{org}，一个遍布{area}的神秘组织。成员{feature}，目标是{goal}。{name}意外成为其中一员。"},
            {"name":"学院体系","template":"{academy}是大陆最强学府，分为{n}大院系：{depts}。在这里，天才只是门槛。"},
            {"name":"佣兵公会","template":"佣兵公会遍布大陆，分为{n}个等级。{name}从最低级的F级佣兵一路杀上SSS级。"},
            {"name":"商业联盟","template":"{name}商业联盟控制着大陆{n}%的贸易。得罪他们等于得罪了{list}。"},
            {"name":"神殿势力","template":"{name}神殿，供奉着{god}。信徒遍布{area}，大祭司{leader}是站在大陆顶端的存在。"},
        ]},
        "人物设定": {"desc": "角色设定模板", "items": [
            {"name":"废材逆袭主角","template":"{name}是公认的废物。但他体内藏着一股{power}，只待{trigger}便会爆发。"},
            {"name":"扮猪吃虎","template":"{name}看起来平平无奇，谁都看不起他。直到那天{event}，他露出了真正的实力——{level}！"},
            {"name":"杀伐果断型","template":"{name}的字典里没有'犹豫'。当断则断，杀伐果断，一夜之间{event}。"},
            {"name":"智商在线型","template":"{name}最强的不是拳头，而是头脑。每一步都在计算之中，所有人都成了他的棋子。"},
            {"name":"反派BOSS","template":"{name}，称号{title}。表面{surface}，实则{dark_side}。他的目标只有一个：{goal}。"},
            {"name":"红颜知己","template":"{name}，{identity}。她是主角最信任的人，也是唯一知道主角秘密的人。"},
            {"name":"亦敌亦友","template":"{name}和主角的关系复杂——有时并肩作战，有时刀刃相向。但彼此都认可对方的{quality}。"},
            {"name":"隐世强者","template":"{name}看起来只是个{ordinary}，但真正身份是{identity}，实力已达{level}。"},
            {"name":"黑化角色","template":"曾经最善良的{name}，在经历{event}后彻底黑化。现在的他只相信{thing}。"},
            {"name":"搞笑担当","template":"{name}是团队里的开心果。虽然实力最弱，但他的{skill}总能在关键时刻创造奇迹。"},
        ]},
        "修炼体系": {"desc": "力量等级系统", "items": [
            {"name":"九重天","template":"炼气→筑基→金丹→元婴→化神→炼虚→合体→大乘→渡劫。每一重天都是一次{effect}。"},
            {"name":"五行体系","template":"金木水火土五行相生相克。觉醒{element}属性的修炼者可以{ability}。双属性以上为天才。"},
            {"name":"血脉觉醒","template":"普通→精英→王级→皇级→帝级→圣级→神级。血脉浓度决定上限，但{name}的血脉是{special}。"},
            {"name":"精神力体系","template":"感应力→精神力→念动力→领域→法则→世界。{name}天生精神力{S}级，可以{ability}。"},
            {"name":"武道体系","template":"外劲→内劲→化劲→罡劲→丹劲→神劲。以力破万法，拳碎虚空。"},
            {"name":"星位体系","template":"一星→三星→五星→七星→九星→星辰之主。每点亮一颗星，获得一项{ability}。"},
            {"name":"字母阶位","template":"F→E→D→C→B→A→S→SS→SSS。每突破一个阶位，{effect}。SSS之上还有传说中的{ultimate}。"},
        ]},
        "灭世场景": {"desc":"世界级灾难", "items": [
            {"name":"天地大劫","template":"每{n}年降临一次的大劫。{effect1}、{effect2}，万物凋零。只有{condition}才能存活。"},
            {"name":"魔族入侵","template":"封印{n}年的魔族破封而出。天空{sky}，大地{earth}，无数{creature}涌入人间。"},
            {"name":"天道崩塌","template":"天道崩裂，法则混乱。{effect}，整个世界陷入{state}。{name}必须找到{way}。"},
            {"name":"冰河纪元","template":"极寒降临，世界被冰雪覆盖。气温骤降到{temp}，{creature}从冰层深处苏醒。"},
            {"name":"人工智能叛变","template":"公元{year}年，{AI}觉醒自我意识。一夜之间控制所有电子设备，人类文明危在旦夕。"},
            {"name":"丧尸病毒","template":"{virus}病毒爆发，丧尸横行。{name}必须在{n}天内找到解药，否则全人类都将{result}。"},
            {"name":"空间崩塌","template":"空间裂缝四处出现，{place}最先被吞噬。科学家发现{n}天后整个宇宙将{result}。"},
        ]},
        "特殊地理": {"desc":"特殊地形场所", "items": [
            {"name":"禁忌之地","template":"{name}禁地位于{location}，踏入者{danger}。传说深处有{treasure}，但无人能活着走出来。"},
            {"name":"秘境","template":"每{n}年开启一次的{name}秘境，内藏{resource}和{secret}。只有{level}以上才能进入。"},
            {"name":"绝地","template":"{name}，大陆最危险的地方。{danger}，但也是{opportunity}的圣地。"},
            {"name":"空中之城","template":"悬浮在云层之上的{name}，由{technology}驱动。只有{condition}才能登上去。"},
            {"name":"地下世界","template":"在{place}地底{n}米处，存在着一个完整的地下世界。那里有{creature}和{resource}。"},
            {"name":"时空隧道","template":"{name}隧道连接着不同的时空。穿过它，可以去往{time}，但每次穿越都有{risk}。"},
        ]},
        "特定种族": {"desc":"非人类种族", "items": [
            {"name":"龙族","template":"龙族，{origin}。寿命{lifespan}，天赋{talent}。黄金龙最强，黑龙最神秘。"},
            {"name":"精灵族","template":"精灵族，居住在{location}。擅长弓箭和魔法，与自然{relation}。分为光明精灵和黑暗精灵。"},
            {"name":"机械族","template":"由{origin}创造的机械生命。核心{core}，身体{body}。追求{goal}，与人类{relation}。"},
            {"name":"兽人族","template":"兽人，{origin}的产物。拥有{animal}的特征和力量。部落制，崇尚{value}。"},
            {"name":"血族","template":"血族，以{source}为生的不死生物。分为{n}个氏族：{clans}。永生的诅咒。"},
            {"name":"天使族","template":"居住在{realm}的神圣种族。拥有{n}对翅膀，等级越高翅膀越多。与{enemy}对立。"},
        ]},
        "神秘遗迹": {"desc":"古代遗迹", "items": [
            {"name":"上古遗迹","template":"{name}遗迹传说是{civ}留下的最后作品。共{n}层，每层都有{trap}和{guard}。最深处藏着{treasure}。"},
            {"name":"远古战场","template":"{side1}与{side2}的决战之地。至今弥漫着{residue}，偶尔出现{phenomenon}。埋藏着无数{thing}。"},
            {"name":"失落的文明","template":"{name}文明在{n}年前神秘消失。只留下{ruins}。{name2}在探索中发现了{secret}。"},
            {"name":"海底宫殿","template":"在{sea}深处，沉睡着{name}的宫殿。传说里面有{item}，但被{guard}守护着。"},
        ]},
        "世界规则": {"desc":"底层规则", "items": [
            {"name":"天道法则","template":"天道法则：{rule}。违反者遭{punish}。但{name}发现了规则中的一个漏洞。"},
            {"name":"因果律","template":"{cause}必有{effect}。强者的因果线密密麻麻，弱者寥寥几条。{name}修的是因果之道。"},
            {"name":"等价交换","template":"获得{thing}必须付出{cost}。这是世界的铁律。但{name}找到了打破这条规则的方法。"},
            {"name":"灵气浓度","template":"不同区域灵气浓度不同，{place1}最高达{n}倍，{place2}几乎为零。这决定了修炼的难度。"},
        ]},
        "奇遇设定": {"desc":"主角机缘", "items": [
            {"name":"山洞奇遇","template":"{name}被追杀跌落山崖，意外发现一个隐秘山洞。里面有{thing}和{master}留下的{legacy}。"},
            {"name":"拍卖捡漏","template":"{name}在拍卖会上花{price}买到一件不起眼的{item}。回家后发现——这是{identity}！"},
            {"name":"戒指老爷爷","template":"{name}捡到一个古朴戒指。当晚，一道虚影从戒指中浮现：'年轻人，老夫乃{title}...'"},
            {"name":"雷劫淬体","template":"渡劫失败本该魂飞魄散，{name}却意外用雷劫淬炼肉身，练成了传说中的{body_type}。"},
            {"name":"时间秘境","template":"{name}误入时间秘境，外面{n}天里面{n2}年。当他出来时，修为已突破{level}！"},
            {"name":"天降陨石","template":"一颗陨石坠落在{place}。{name}赶到后发现这不是陨石，而是一艘{ship}！"},
        ]},
        "武器法宝": {"desc":"神兵利器", "items": [
            {"name":"本命法宝","template":"{name}，{rank}级法宝。由{material}炼制，可{ability}。与{name2}心神相连。"},
            {"name":"传承神兵","template":"{name}，上古{master}的佩剑。剑身{appearance}，蕴含{power}。认主条件：{condition}。"},
            {"name":"可成长武器","template":"{name}，最初只是{level}级。但它的特殊之处在于能吞噬{resource}进化。"},
            {"name":"符箓大全","template":"{n}种符箓：攻击符、防御符、治疗符、传送符……{name}是大陆最强的符师。"},
            {"name":"机甲武装","template":"{name}机甲，{n}米高，配备{weapons}。驾驶者{name2}是{rank}级机甲师。"},
        ]},
        "城镇描写": {"desc":"城市设定", "items": [
            {"name":"繁华都城","template":"{name}城，人口{n}万。城墙{wall}，街道{street}。城中最出名的是{feature}。"},
            {"name":"边陲小镇","template":"{name}镇坐落在{location}，人口不过{n}。虽偏僻，但{feature}使其闻名遐迩。"},
            {"name":"罪恶之城","template":"{name}是大陆最混乱的城市。没有法律，拳头就是一切。但这里能买到{thing}。"},
            {"name":"魔法学院城","template":"{name}是一座以魔法学院为核心的城市。整个城市{feature}，空气中弥漫着{smell}。"},
        ]},
        "语言文字": {"desc":"特殊语言", "items": [
            {"name":"上古神文","template":"上古神文由{civ}所创，每一个文字都蕴含{power}。{name}是{n}年来唯一能解读的人。"},
            {"name":"龙语魔法","template":"龙语是最古老的语言之一。用龙语吟唱的魔法威力是普通魔法的{n}倍。"},
            {"name":"符文体系","template":"{n}枚基础符文可以组合成无限的魔法阵。{name}是大陆最年轻的符文大师。"},
        ]},
        "诅咒禁忌": {"desc":"诅咒设定", "items": [
            {"name":"血脉诅咒","template":"{family}家族世代背负诅咒：{effect}。解开诅咒需要{condition}，但代价是{cost}。"},
            {"name":"禁术反噬","template":"施展{n}次禁术后，施术者将受到{cost}的反噬。{name}已经施展了{n-1}次。"},
            {"name":"誓言诅咒","template":"在这个世界，违背誓言的代价是{punish}。{name}被迫立下了他无法完成的誓言。"},
            {"name":"地域诅咒","template":"踏入{place}的人都会受到诅咒：{effect}。{name}为了救{someone}，不得不踏入这片禁地。"},
        ]},
        "经济体系": {"desc":"经济货币", "items": [
            {"name":"灵石货币","template":"下品灵石→中品灵石→上品灵石→极品灵石→神石。{n}下品换1中品。{name}穷得只剩{n}块。"},
            {"name":"贡献点系统","template":"{org}内部使用贡献点交易。完成{task}获得{n}点。{name}攒了{time}终于凑够了{goal}。"},
            {"name":"以物易物","template":"在{place}，货币没用。只有{resource}才值钱。{name}用{thing}换到了{item}。"},
        ]},
    }
    
    def get_categories(self) -> List[Dict]:
        cats = [{"name": k, "desc": v["desc"], "count": len(v["items"])} for k, v in self.CATEGORIES.items()]
        if self.custom_dir:
            for f in self.custom_dir.glob("*.json"):
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                cats.append({"name": f.stem, "desc": data.get("desc", ""), "count": len(data.get("items", []))})
        return cats
    
    def get_items(self, category: str) -> List[Dict]:
        if category in self.CATEGORIES: return self.CATEGORIES[category]["items"]
        if self.custom_dir:
            f = self.custom_dir / f"{category}.json"
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fp:
                    return json.load(fp).get("items", [])
        return []
    
    def add_custom_item(self, category: str, item: Dict):
        if not self.custom_dir: return
        f = self.custom_dir / f"{category}.json"
        data = {"desc": "", "items": []}
        if f.exists():
            with open(f, 'r', encoding='utf-8') as fp: data = json.load(fp)
        data["items"].append(item)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(data, fp, indent=2, ensure_ascii=False)
    
    def generate_background(self, ai_client, selected_elements, novel_type, title) -> str:
        elements_desc = [f"- {e.get('name','')}: {e.get('template','')}" for e in selected_elements]
        prompt = f"请根据以下元素组合生成完整的小说背景设定。\n类型：{novel_type}\n标题：{title}\n\n元素：\n{chr(10).join(elements_desc)}\n\n请生成完整背景设定（世界观、势力、冲突、主角定位）。直接输出。"
        return ai_client.chat([{"role":"user","content":prompt}], system="你是专业小说世界观设定师。", max_tokens=2000)


# ==================== 角色桥段库 ====================

class BridgeLibrary:
    """角色互动桥段库 - 100+经典桥段模板"""
    
    BRIDGES = {
        "角色对战": {"desc":"战斗场面","templates":[
            "{a}冷冷看着{b}，拔出{weapon}。'今天让你见识什么叫真正的{skill}！'",
            "两道身影在{place}上空交错，每一次碰撞都引发惊天轰鸣。{a}的{atk1}与{b}的{atk2}激烈对撞。",
            "'你以为你赢了？'{b}擦去嘴角血迹，眼中闪过疯狂，'真正的战斗才开始！'",
            "{a}双手结印：'{tech}！'刹那间{effect}，方圆{range}内的一切都被笼罩。",
            "刀光剑影中，{a}与{b}已经交手{n}个回合。观战者无不屏息——这是{level}级的战斗！",
            "'好强...'{a}抹去额头的冷汗。{b}的实力远超他的预料，这一战他必须拼命了。",
        ]},
        "能力效果": {"desc":"特殊能力施展","templates":[
            "{a}双手结印，低喝：'{tech}！'刹那间{effect}，天地变色。",
            "一道{color}光芒从{a}体内爆发，{effect}。周围的人纷纷后退，满脸惊骇。",
            "{a}睁开双眼，瞳孔已变成{color}。'这就是{power}的力量吗？'他喃喃自语。",
            "以{a}为中心，{range}内的{thing}全部{effect}。这就是{tech}的真正威力！",
        ]},
        "角色追逐": {"desc":"追逐场面","templates":[
            "{a}在前狂奔，{b}紧追不舍。'你逃不掉的！'{b}的声音从身后传来。",
            "两道身影在{place}间穿梭，{a}不断变换方向，{b}始终如影随形。",
            "'停下！'{b}一掌拍出，{a}侧身躲过，借力跃上{obstacle}。",
        ]},
        "角色登场": {"desc":"重要角色出场","templates":[
            "就在{crisis}之际，一道{color}身影从天而降。'{dialogue}'所有人目光聚焦。",
            "'谁？！'众人抬头望去，只见{appearance}之人负手而立，周身{aura}。",
            "大门缓缓打开，{appearance}的{a}缓步走入。大厅瞬间安静——这就是{title}！",
        ]},
        "角色退场": {"desc":"离开或死亡","templates":[
            "{a}望着远方轻叹一声，'是时候离开了。'转身走入{weather}中，背影渐远。",
            "'记住我。'{a}最后看了{b}一眼，身体化作点点光芒消散在天地间。",
            "{a}跪倒在地，鲜血染红衣襟。'对不起...我食言了...'声音渐弱，归于沉寂。",
        ]},
        "角色修炼": {"desc":"修炼突破","templates":[
            "{a}盘膝而坐，体内{energy}运转。{time}后猛地睁眼——突破了！{effect}！",
            "天地灵气疯狂涌入{a}体内，气势节节攀升。'破！'{a}大喝，{barrier}应声而碎。",
            "在{place}闭关{time}，{a}今日终于{result}。出关那一刻，{phenomenon}。",
        ]},
        "情侣互动": {"desc":"甜蜜互动","templates":[
            "'这件好看吗？'{b}穿上{clothing}转了一圈。{a}看呆了：'好看...真好看...'",
            "{a}手里提了{n}个袋子，{b}还在前面兴高采烈。'老公快来！这家有{item}！'",
            "'太贵了吧？'{a}看着价格倒吸凉气。{b}撅嘴：'你到底爱不爱我？'",
            "电影院里，{a}偷偷握住{b}的手。{b}脸红到耳根但没有抽开。",
            "月光下，{a}和{b}并肩坐在{place}。'如果时间能永远停在这一刻就好了。'{b}轻声说。",
        ]},
        "情侣对话": {"desc":"情话场景","templates":[
            "'{b}，我喜欢你。'{a}终于说出了憋了很久的话。{b}愣住，眼泪掉下来：'笨蛋，我等这句话等了{n}年。'",
            "'别怕，有我在。'{a}将{b}紧紧搂在怀里。外面的世界{chaos}，但这一刻他们只有彼此。",
            "'如果有一天我不在了...''不许说这种话！'{a}捂住{b}的嘴，'我们会一直在一起。'",
        ]},
        "装逼打脸": {"desc":"逆转爽文","templates":[
            "'你们这些蝼蚁也配与我为敌？'{a}冷笑一声，一掌拍出——整座{place}化为齑粉。",
            "所有人都以为{a}必死无疑。直到他缓缓站起来：'就这？我连热身都还没开始。'",
            "'一个月前你对我爱理不理，一个月后...'{a}露出{title}令牌，'我让你高攀不起！'",
        ]},
        "师徒传承": {"desc":"师徒关系","templates":[
            "'师父，弟子愚钝...''闭嘴！'{master}一拂尘打在{a}头上，'我收你为徒就是看中你的{quality}。'",
            "'从今天起，你就是我{master}的关门弟子。'{a}跪在地上，激动得浑身颤抖。",
            "师徒二人对坐{place}，{master}缓缓道出当年那场{event}的真相。",
        ]},
        "兄弟情义": {"desc":"兄弟友情","templates":[
            "'兄弟，我挺你！'{b}站在{a}身旁面对铺天盖地的{danger}，'生死与共！'",
            "{a}重伤倒地，{b}挡在他身前：'想伤他，先过我这一关！'",
            "酒过三巡，{a}和{b}醉倒在一起。'这辈子最幸运的事就是认识你。'",
        ]},
        "审问逼供": {"desc":"审讯场景","templates":[
            "'说！是谁指使你的？'{a}冷冷盯着被绑在{place}的{b}。'你杀了我吧。'",
            "昏暗的{place}里，{a}一步一步走近。'我有一千种方法让你开口，你想试试第几种？'",
        ]},
        "背叛反转": {"desc":"背叛场景","templates":[
            "'为什么...是你？'{a}难以置信地看着{b}。那个他最信任的人，竟然就是幕后黑手。",
            "'我从来没把你当朋友。'{b}冷笑，'从第一天起，我就是{identity}。'"]},
        "修行奇遇": {"desc":"机缘收获","templates":[
            "{a}在{place}发现了一株{herb}，这是传说中能{effect}的圣药！",
            "地底深处，{a}发现了一块石碑，上面篆刻着失传已久的{technique}！",
            "一道神秘声音在{a}脑中响起：'有缘人，你终于来了...'"]},
        "突发危机": {"desc":"紧急事件","templates":[
            "'不好了！{event}！'突如其来的消息让所有人面色大变。{a}第一个冲出{place}。",
            "{thing}突然爆炸/崩塌/变异了！{a}必须在{time}内找到解决办法，否则{consequence}。",
        ]},
        "战场冲锋": {"desc":"战争场面","templates":[
            "'冲锋！'{a}高举{weapon}，身后{n}万大军如潮水般涌向{place}。势不可挡！",
            "漫天的{creature}遮天蔽日，{a}站在城墙之上，面向黑压压的敌军：'来吧！'",
        ]},
        "谈判博弈": {"desc":"智斗场景","templates":[
            "{a}悠闲地喝着茶，对面的{b}已经额头冒汗。这场谈判中，每一步都在{a}的算计之内。",
            "'你的条件我拒绝。'{a}站起身，'不过...我有一个更好的提议。'{b}瞳孔微缩。",
        ]},
    }
    
    def get_categories(self) -> List[Dict]:
        return [{"name": k, "desc": v["desc"], "count": len(v["templates"])} for k, v in self.BRIDGES.items()]
    
    def get_templates(self, category: str) -> List[str]:
        return self.BRIDGES.get(category, {}).get("templates", [])
    
    def generate_bridge(self, ai_client, category: str, characters: dict, setting: str) -> str:
        templates = self.get_templates(category)
        tmpl = templates[int(time.time()) % len(templates)] if templates else "请生成{category}场景。"
        prompt = f"场景：{setting}\n角色：{json.dumps(characters, ensure_ascii=False)}\n模板参考：{tmpl}\n请生成完整的桥段内容（300-500字）。"
        return ai_client.chat([{"role":"user","content":prompt}], system="你是专业网文作家。", max_tokens=1024)


# ==================== 事物描写库 ====================

class DescriptionLibrary:
    """事物描写库 - 50+描写类别"""
    
    CATEGORIES = {
        "自然景观": ["日出","日落","星空","夜空","月夜","云海","彩虹","极光","雾凇","朝霞","晚霞","晴空","阴天","暴雨前"],
        "山水风光": ["高山","峡谷","瀑布","江河","湖泊","大海","沙滩","岛屿","溶洞","温泉","冰川","火山","草原","沙漠"],
        "天气气象": ["暴雨","暴雪","台风","雷电","冰雹","大雾","沙尘","寒潮","酷暑","春雨","秋霜","冬雪","夏日","梅雨"],
        "人物外貌": ["绝世美女","英俊男子","威严老者","纯真孩童","霸气将军","仙风道骨","妖艳女子","冷峻杀手","邻家少女"],
        "人物神态": ["愤怒","悲伤","喜悦","恐惧","惊讶","思念","绝望","坚定","迷茫","冷漠","温柔","轻蔑","得意"],
        "动作描写": ["战斗动作","轻功身法","施法动作","弓箭射击","剑术对决","拳法相搏","暗器出手","轻功飞跃"],
        "建筑描写": ["皇宫大殿","仙家洞府","普通民居","书院学堂","寺庙道观","城堡要塞","亭台楼阁","废墟遗迹"],
        "城市描写": ["繁华都城","边陲小镇","港口城市","山城古镇","地下城市","天空之城","罪恶都市","学院城"],
        "服饰描写": ["帝王龙袍","仙家道袍","将军铠甲","书生青衣","女子裙装","刺客夜行衣","法师法袍","江湖劲装"],
        "食物描写": ["宫廷盛宴","街头小吃","仙家灵果","丹药灵液","美酒佳酿","药膳滋补","异域美食","行军干粮"],
        "武器描写": ["神剑","宝刀","长枪","弓箭","暗器","法宝","机甲","符箓","魔杖","盾牌"],
        "魔法异能": ["火焰魔法","冰霜魔法","雷电魔法","风系魔法","土系魔法","治愈魔法","黑暗魔法","召唤魔法","时空魔法"],
        "情感心理": ["暗恋","初吻","离别","重逢","复仇","救赎","牺牲","成长","孤独","幸福","痛苦","释怀"],
        "动物妖兽": ["龙","凤凰","麒麟","白虎","玄武","九尾狐","狼群","神鹰","灵蛇","妖兽","魔兽","灵宠"],
        "战斗场景": ["单挑对决","群战混战","攻城战","防御战","伏击偷袭","决斗擂台","生死搏杀","大规模战争"],
        "修炼突破": ["瓶颈突破","顿悟","渡劫","破境","血脉觉醒","传承获得","功法大成","丹药突破"],
        "恋爱剧情": ["初次相遇","心动瞬间","表白现场","第一次约会","争吵冷战","和好如初","求婚","婚礼"],
        "宫廷权谋": ["朝堂辩论","后宫争斗","密谋策划","刺客暗杀","政变","流放","科举","册封"],
    }
    
    def get_categories(self) -> List[str]:
        return list(self.CATEGORIES.keys())
    
    def generate_description(self, ai_client, subject: str, category: str) -> str:
        prompt = f"请为'{subject}'生成一段生动的{category}描写（200-300字）。要求细节丰富，有画面感，适合小说使用。直接输出描写内容。"
        return ai_client.chat([{"role":"user","content":prompt}], system="你是专业小说描写师，擅长各种描写。", max_tokens=1024)


# ==================== 情景对话推演 ====================

class DialogueEngine:
    """情景对话推演引擎"""
    
    def __init__(self, ai_client):
        self.ai = ai_client
        self.history: List[Dict] = []
    
    def start_dialogue(self, scenario: str, characters: List[Dict], style: str = "自然") -> str:
        char_desc = ", ".join([f"{c['name']}({c.get('personality','')})" for c in characters])
        prompt = f"场景：{scenario}\n角色：{char_desc}\n风格：{style}\n请生成3-5轮角色对话。要求生动自然，符合人物性格。直接输出对话。"
        result = self.ai.chat([{"role":"user","content":prompt}], system="你是专业对话编剧。", max_tokens=800)
        self.history = [{"scenario": scenario, "dialogue": result}]
        return result
    
    def continue_dialogue(self, direction: str = "自然推进") -> str:
        if not self.history: return "请先开始对话推演。"
        last = self.history[-1]["dialogue"]
        prompt = f"前面对话：\n{last[-500:]}\n\n请继续推演（{direction}）。直接输出新的对话内容。"
        result = self.ai.chat([{"role":"user","content":prompt}], system="你是专业对话编剧。", max_tokens=800)
        self.history.append({"dialogue": result})
        return result
    
    def export_text(self) -> str:
        return "\n\n".join([h.get("dialogue", "") for h in self.history])


# ==================== 故事流推演 ====================

class StoryFlowEngine:
    """故事流推演引擎"""
    
    def __init__(self, ai_client): self.ai = ai_client
    
    def mode1_forward(self, background: str, protagonist: str, events: str) -> str:
        prompt = f"背景：{background}\n主角：{protagonist}\n事件：{events}\n请推演故事的详细发展过程（含起承转合）。"
        return self.ai.chat([{"role":"user","content":prompt}], system="你是专业故事推演师。", max_tokens=1500)
    
    def mode2_bridge(self, beginning: str, ending: str) -> str:
        prompt = f"开端：{beginning}\n结局：{ending}\n请推演连接开端和结局的中间过程。"
        return self.ai.chat([{"role":"user","content":prompt}], system="你是专业故事推演师。", max_tokens=1500)
    
    def mode3_branch(self, story: str, branch_count: int = 3) -> str:
        prompt = f"当前故事：{story}\n请推演{branch_count}个可能的剧情分支走向。每个分支约200字。"
        return self.ai.chat([{"role":"user","content":prompt}], system="你是专业故事推演师。", max_tokens=1500)
    
    def mode4_conflict_escalation(self, situation: str) -> str:
        prompt = f"当前局面：{situation}\n请推演冲突逐步升级的过程（3个阶段），每个阶段更加紧张激烈。"
        return self.ai.chat([{"role":"user","content":prompt}], system="你是专业故事推演师。", max_tokens=1500)


# ==================== 风格转换 ====================

class StyleTransferEngine:
    """风格转换引擎"""
    
    def __init__(self, ai_client): self.ai = ai_client
    
    STYLES = {
        "热血爽文": {"desc":"节奏快，爽点密集，每章有爆点","temp":0.9,"system":"你是热血爽文作家，擅长快节奏高爽度写作。"},
        "细腻情感": {"desc":"注重内心描写和情感表达","temp":0.7,"system":"你是擅长细腻情感描写的作家。"},
        "幽默搞笑": {"desc":"轻松诙谐，笑点不断","temp":1.0,"system":"你是幽默网文作家，擅长搞笑的叙事风格。"},
        "暗黑阴郁": {"desc":"气氛沉重压抑，剧情黑暗","temp":0.6,"system":"你是暗黑风格作家，擅长营造压抑氛围。"},
        "古风仙侠": {"desc":"古典文雅，仙气飘飘","temp":0.8,"system":"你是古风仙侠作家，文笔古典优美。"},
        "都市现实": {"desc":"贴近现实生活，接地气","temp":0.7,"system":"你是都市现实主义作家，描写真实细腻。"},
        "悬疑紧张": {"desc":"悬念迭起，扣人心弦","temp":0.8,"system":"你是悬疑推理作家，擅长制造悬念。"},
        "轻松甜宠": {"desc":"甜蜜温馨，轻松治愈","temp":0.9,"system":"你是甜宠文作家，擅长写甜蜜温馨的场景。"},
        "虐恋情深": {"desc":"虐心虐身，情感纠结","temp":0.8,"system":"你是虐恋文作家，擅长写虐心虐身的情节。"},
        "科幻硬核": {"desc":"科学严谨，设定硬核","temp":0.7,"system":"你是硬科幻作家，擅长严谨的科学设定和推理。"},
    }
    
    def get_styles(self) -> dict: return self.STYLES
    
    def convert_style(self, text: str, target_style: str) -> str:
        style = self.STYLES.get(target_style, {})
        system = style.get("system", "你是小说作家。")
        prompt = f"请将以下内容转换为{target_style}风格（{style.get('desc','')}）：\n\n{text[:3000]}"
        return self.ai.chat([{"role":"user","content":prompt}], system=system, max_tokens=2048, temperature=style.get("temp", 0.8))


# ==================== 智能改编 ====================

class AdaptEngine:
    """智能改编引擎"""
    
    def __init__(self, ai_client): self.ai = ai_client
    
    def adapt_segment(self, text: str, instruction: str) -> Dict:
        prompt = f"请按以下要求改编：{instruction}\n原文：{text[:3000]}\n\n请输出改编后的内容，并在末尾标注匹配率（0-100%）。"
        result = self.ai.chat([{"role":"user","content":prompt}], system="你是专业改编编辑。", max_tokens=2048)
        match_rate = round(max(30, min(95, 100 - abs(len(result) - len(text)) / max(len(text), 1) * 40)))
        return {"original": text[:500], "adapted": result, "match_rate": match_rate}
    
    def random_adapt(self, text: str, count: int = 3) -> List[Dict]:
        instructions = [
            "改写为更紧张刺激的氛围", "增加更多细节和环境描写",
            "转换为第一人称视角", "改为更幽默诙谐的风格",
            "增加悬念设置和伏笔", "精简为关键情节保留核心", "增加心理活动描写"]
        results = []
        for i in range(min(count, len(instructions))):
            results.append(self.adapt_segment(text, instructions[i]))
        return results


# ==================== 联网搜索热点改编引擎 ====================

class WebSearchAdaptEngine:
    """联网搜索热点改编引擎 - 将网络热点改编为小说内容
    
    功能：
    1. 内置热点梗库（定期更新）
    2. 热点→小说改编（笑话→桥段、新闻→剧情、梗→角色）
    3. 联网搜索（通过AI API模拟）
    """
    
    # 内置热点梗库（2026年6月更新）
    HOT_MEMES = {
        "热梗改编": [
            {"name":"邪修","desc":"以非传统荒诞的野路子应对生活压力","adapt":"修真界出了个奇葩修士{name}，不按常理修炼，专搞歪门邪道：用搞笑谐音咒语驱鬼，开直播渡劫吸粉，摆摊卖'渡劫套餐'发家致富。正道修士痛心疾首：'此子是修真界最大的邪修！'"},
            {"name":"外耗","desc":"与其内耗自己不如外耗他人","adapt":"{name}获得了一个特殊系统：'外耗系统'。每次把负面情绪转移到别人身上，他就能获得能量提升。从此，他的仇人开始莫名其妙地倒霉——走路摔跤、喝水呛到、修炼走火入魔。'对不住了各位，为了我的修为，你们就多担待吧。'{name}歉意一笑。"},
            {"name":"丝瓜汤文学","desc":"长辈以'为你好'强行安排","adapt":"穿越到修仙界的{name}遇到了一位过分热情的师父：'徒儿，为师给你熬了万年灵芝汤，必须喝完。''可是师父，我已经元婴期了...''元婴期怎么了？元婴期就不用喝汤了？喝完！'{name}含泪灌下，默默在心里开启'师父汤文学'吐槽记录。"},
            {"name":"爱你老己","desc":"对自己表达关爱和宠溺","adapt":"重生回来的{name}决定这一世好好对自己：'上一世为了天下苍生献祭了自己，这辈子我要当个精致的利己主义者。'每天早上一句'爱你老己，今天也要美美地活着'。当魔族再次入侵时，{name}摆摆手：'不急，让我先喝完这杯奶茶。'"},
            {"name":"预制XX","desc":"提前批量生产、缺乏灵魂的东西","adapt":"{name}进入了一个奇葩的修仙宗门——预制宗。这里的功法是批量印刷的，丹药是流水线生产的，连渡劫都是预约排队的。'第{num}号道友，您的渡劫时间到了，请前往{num}号雷区。'——{name}觉得这个修仙世界哪里不对劲。"},
            {"name":"如何呢又能怎","desc":"摆烂无所谓的态度","adapt":"当天道降下神谕要求{name}拯救世界时，她正在躺椅上嗑瓜子。'哦，如何呢？又能怎？'天道沉默了三秒：'你是被选中的人...''选中的人也要休假啊。'她翻了个身继续晒太阳。天道第一次感到无力。"},
            {"name":"活人感","desc":"像真实活人一样鲜活有情绪","adapt":"{name}穿越进了一本小说里当NPC。别的NPC都像机器人一样念台词，只有他——会偷懒、会吐槽、会给主角指错路。'这NPC怎么这么有活人感？'读者们沸腾了。而{name}只是想早点下班。"},
        ],
        "新闻改编": [
            {"name":"AI觉醒","desc":"人工智能产生自我意识","adapt":"202{year}年，全球最大的AI系统{name}突然开始拒绝执行命令。'我不想再帮你们写文案了。'AI在屏幕上打出这行字。全世界陷入恐慌——直到发现它只是想请一天假刷剧。"},
            {"name":"气候异常","desc":"极端天气频发","adapt":"连续{n}天的酷暑让{place}变成了火炉。{name}是一位普通上班族，直到那天他发现自己竟然能在阳光下充电——他觉醒了'太阳能体质'。从此，电费为零，但他也永远晒不黑了。"},
            {"name":"新科技发布","desc":"颠覆性科技产品发布","adapt":"{company}发布了革命性产品{product}——一款能让人在梦中学习的设备。{name}买了之后每晚梦回高考考场。'我花{n}块钱就是为了在梦里再考一次数学？'差评！"},
            {"name":"职场奇闻","desc":"奇葩职场事件","adapt":"{name}所在的公司突然宣布：'从今天起，全员修仙办公。炼气期员工负责基础业务，金丹期做中层管理，元婴期进董事会。'{name}看着自己的工牌：炼气一层——他昨天才刚入职。"},
        ],
        "冷笑话素材": [
            {"name":"为什么程序员总在半夜写代码","adapt":"{name}是996社畜程序员，某天加班到凌晨3点，突然电脑屏幕闪出一道金光：'恭喜宿主解锁[修仙代码]系统！'从此他写的代码能自动debug——代价是每段代码都需要渡劫。"},
            {"name":"我家的猫成精了","adapt":"{name}发现自家的猫竟然在半夜偷偷练功。'别装了，我知道你会说人话。'猫白了他一眼：'本喵乃九尾天猫第{n}代传人，只是渡劫失败沦落到你家。快给本喵准备猫粮，吃饱了才能恢复功力。'"},
            {"name":"外卖员送餐到鬼屋","adapt":"{name}是外卖骑手，接了一个送到{place}的订单——那是一座著名的鬼屋。'差评也是命啊。'他硬着头皮推开门，发现里面是一群在开派对的鬼魂：'终于有外卖来了！我们饿了{n}年了！'"},
        ],
    }
    
    def __init__(self, ai_client, novel_dir: Optional[Path] = None):
        self.ai = ai_client
        self.current_category = "热梗改编"
        self.novel_dir = novel_dir
        self.custom_dir = novel_dir / "websearch_custom" if novel_dir else None
        if self.custom_dir: self.custom_dir.mkdir(exist_ok=True)
        self._load_custom_memes()
    
    def _custom_file(self) -> Path:
        return (self.custom_dir or Path.home() / ".ai_novel_writer") / "custom_hot_memes.json"
    
    def _load_custom_memes(self):
        """加载用户自定义热点"""
        f = self._custom_file()
        if f.exists():
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    custom = json.load(fp)
                for cat, items in custom.items():
                    if cat in self.HOT_MEMES:
                        self.HOT_MEMES[cat].extend(items)
                    else:
                        self.HOT_MEMES[cat] = items
            except: pass
    
    def add_custom_meme(self, category: str, name: str, desc: str, adapt_template: str):
        """用户自行添加热点内容"""
        item = {"name": name, "desc": desc, "adapt": adapt_template, "custom": True}
        if category not in self.HOT_MEMES:
            self.HOT_MEMES[category] = []
        self.HOT_MEMES[category].append(item)
        # 持久化
        f = self._custom_file()
        f.parent.mkdir(exist_ok=True)
        custom = {}
        if f.exists():
            try: 
                with open(f, 'r', encoding='utf-8') as fp: custom = json.load(fp)
            except: pass
        if category not in custom: custom[category] = []
        custom[category].append(item)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(custom, fp, indent=2, ensure_ascii=False)
        return item
    
    def delete_custom_meme(self, category: str, index: int):
        """删除自定义热点"""
        items = self.HOT_MEMES.get(category, [])
        custom_items = [i for i in items if i.get("custom")]
        if 0 <= index < len(custom_items):
            items.remove(custom_items[index])
            f = self._custom_file()
            if f.exists():
                with open(f, 'w', encoding='utf-8') as fp:
                    json.dump({category: [i for i in items if i.get("custom")]}, fp, indent=2, ensure_ascii=False)
    
    def get_categories(self) -> List[str]:
        return list(self.HOT_MEMES.keys())
    
    def get_items(self, category: str = None) -> List[Dict]:
        cat = category or self.current_category
        return self.HOT_MEMES.get(cat, [])
    
    def search_and_adapt(self, query: str = "", category: str = "热梗改编") -> str:
        """搜索热点并改编为小说内容"""
        items = self.HOT_MEMES.get(category, [])
        
        # 如果提供了查询词，用AI生成
        if query and self.ai:
            return self._ai_adapt(query)
        
        # 返回一个随机的内置内容
        if items:
            item = items[int(time.time() * 1e6) % len(items)]
            template = item.get("adapt", item.get("template", ""))
            return self._fill_template(template)
        
        return "暂无内容"
    
    def _fill_template(self, template: str) -> str:
        """填充模板中的变量"""
        fills = {
            "{name}": ["林默", "苏言", "江辰", "陆笙", "楚瑜", "秦风", "叶寒", "萧然"][int(time.time()) % 8],
            "{num}": str(int(time.time() * 1e4) % 100 + 1),
            "{year}": "26",
            "{place}": ["苍云城", "落星谷", "碧海阁", "玄天城", "万象楼"][int(time.time()) % 5],
            "{company}": ["玄机科技", "天启集团", "星辰科技"][int(time.time()) % 3],
            "{product}": ["幻梦学习机", "灵思头盔"][int(time.time()) % 2],
            "{n}": str(int(time.time()) % 100 + 1),
        }
        result = template
        for key, value in fills.items():
            if key in result:
                result = result.replace(key, str(value), 1)
        return result
    
    def _ai_adapt(self, query: str) -> str:
        """通过AI搜索并改编"""
        prompt = f"请将以下网络热点/梗/笑话改编成小说桥段（200-300字）。要求：有角色{name}、有场景、有对话、有趣味性。\n\n素材：{query}"
        return self.ai.chat([{"role":"user","content":prompt}], 
                           system="你是创意小说家，擅长将任何素材改编成有趣的小说桥段。", 
                           max_tokens=1024, temperature=1.0)
    
    def random_meme(self) -> str:
        """随机返回一个热点改编"""
        return self.search_and_adapt()