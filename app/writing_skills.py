"""
写作技能模块 - 借鉴开源项目改进小说生成质量

参考项目：
- stop-slop: 去除AI写作痕迹
- taste-skill: 可调节的写作风格参数
- supermemory: 时间感知记忆系统
- codegraph: 知识图谱概念
"""

import json
import re
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WritingStyleConfig:
    """写作风格配置 - 借鉴taste-skill的旋钮概念"""
    # 风格旋钮 (1-10)
    descriptiveness: int = 7  # 描写细腻度：1=简洁，10=华丽
    dialogue_ratio: int = 5  # 对话比例：1=叙述为主，10=对话为主
    pacing: int = 5  # 节奏：1=缓慢铺垫，10=快节奏
    emotional_depth: int = 6  # 情感深度：1=表面，10=深入内心
    action_intensity: int = 5  # 动作强度：1=平淡，10=激烈
    
    # 类型偏好
    genre_style: str = "玄幻"  # 玄幻/都市/科幻/言情等
    
    def to_prompt(self) -> str:
        """转换为AI提示词"""
        return f"""写作风格要求：
- 描写细腻度: {self.descriptiveness}/10 {'华丽细腻' if self.descriptiveness > 7 else '简洁有力' if self.descriptiveness < 4 else '适中'}
- 对话比例: {self.dialogue_ratio}/10 {'对话驱动' if self.dialogue_ratio > 7 else '叙述为主' if self.dialogue_ratio < 4 else '平衡'}
- 节奏: {self.pacing}/10 {'快节奏' if self.pacing > 7 else '慢节奏铺垫' if self.pacing < 4 else '张弛有度'}
- 情感深度: {self.emotional_depth}/10 {'深入内心' if self.emotional_depth > 7 else '表面描写' if self.emotional_depth < 4 else '适度'}
- 动作强度: {self.action_intensity}/10 {'激烈热血' if self.action_intensity > 7 else '平淡克制' if self.action_intensity < 4 else '适度'}"""


# 去AI味规则 - 借鉴stop-slop项目
ANTI_SLOP_RULES = {
    # 禁止的AI写作模式
    "forbidden_openings": [
        "在这个",
        "在这个世界上",
        "在这个时代",
        "在当今社会",
        "随着科技的发展",
        "众所周知",
        "不可否认",
        "毫无疑问",
        "显然",
        "显然易见",
    ],
    
    # 禁止的过渡词
    "forbidden_transitions": [
        "然而",
        "不过",
        "但是",
        "尽管如此",
        "虽然如此",
        "即便如此",
        "话说回来",
        "言归正传",
        "总而言之",
        "综上所述",
        "归根结底",
        "说到底",
    ],
    
    # 禁止的结尾模式
    "forbidden_endings": [
        "这一切，才刚刚开始",
        "故事，才刚刚开始",
        "命运的齿轮，开始转动",
        "新的篇章，即将展开",
        "而这，只是个开始",
        "未来，还有更多的挑战等待着他",
    ],
    
    # 禁止的形容词堆砌
    "forbidden_adjective_clusters": [
        r"美丽.*?动人.*?可爱",
        r"强大.*?恐怖.*?可怕",
        r"聪明.*?机智.*?智慧",
        r"温柔.*?善良.*?体贴",
    ],
    
    # 推荐的写作技巧
    "recommended_techniques": {
        "show_dont_tell": "用动作和细节展示，而非直接告诉读者",
        "sensory_details": "调动五感描写：视觉、听觉、嗅觉、触觉、味觉",
        "specific_verbs": "使用具体动词替代模糊动词",
        "varied_sentence_length": "长短句交替，创造节奏感",
        "subtext": "对话要有潜台词，不要直白表达",
    }
}


class AntiSlopProcessor:
    """去AI味处理器 - 借鉴stop-slop"""
    
    def __init__(self):
        self.rules = ANTI_SLOP_RULES
        self._compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """预编译正则表达式"""
        patterns = {
            "adjective_clusters": [re.compile(p) for p in self.rules["forbidden_adjective_clusters"]]
        }
        return patterns
    
    def check_text(self, text: str) -> Dict[str, List[str]]:
        """检查文本中的AI写作痕迹"""
        issues = {
            "forbidden_openings": [],
            "forbidden_transitions": [],
            "forbidden_endings": [],
            "adjective_clusters": [],
            "suggestions": []
        }
        
        lines = text.split('\n')
        
        # 检查开头
        for line in lines[:5]:
            for opening in self.rules["forbidden_openings"]:
                if opening in line:
                    issues["forbidden_openings"].append(f"发现禁止开头: '{opening}'")
        
        # 检查过渡词
        for i, line in enumerate(lines):
            for transition in self.rules["forbidden_transitions"]:
                if transition in line:
                    issues["forbidden_transitions"].append(f"第{i+1}行: 过度使用过渡词 '{transition}'")
        
        # 检查结尾
        for line in lines[-5:]:
            for ending in self.rules["forbidden_endings"]:
                if ending in line:
                    issues["forbidden_endings"].append(f"发现AI式结尾: '{ending}'")
        
        # 检查形容词堆砌
        for i, line in enumerate(lines):
            for pattern in self._compiled_patterns["adjective_clusters"]:
                if pattern.search(line):
                    issues["adjective_clusters"].append(f"第{i+1}行: 形容词堆砌")
        
        # 生成建议
        if len(issues["forbidden_transitions"]) > 3:
            issues["suggestions"].append("过渡词使用过多，建议减少'然而'、'不过'等词的使用")
        
        if len(issues["adjective_clusters"]) > 0:
            issues["suggestions"].append("形容词堆砌，建议用具体细节替代多个形容词")
        
        return issues
    
    def fix_text(self, text: str) -> Tuple[str, List[str]]:
        """自动修复AI写作痕迹"""
        fixes = []
        fixed_text = text
        
        # 修复禁止的开头
        for opening in self.rules["forbidden_openings"]:
            if opening in fixed_text:
                # 不直接删除，而是标记建议
                fixes.append(f"建议修改开头 '{opening}'，使用更具体的场景描写")
        
        # 修复过度使用的过渡词
        transition_count = {}
        for transition in self.rules["forbidden_transitions"]:
            count = fixed_text.count(transition)
            if count > 2:
                transition_count[transition] = count
        
        if transition_count:
            fixes.append(f"过渡词使用过多: {transition_count}，建议减少使用")
        
        return fixed_text, fixes
    
    def get_writing_tips(self, genre: str = "玄幻") -> str:
        """获取写作技巧提示 - 支持所有小说类型"""
        # 提取主类型（如"玄幻-东方玄幻" -> "玄幻"）
        main_genre = genre.split('-')[0] if '-' in genre else genre
        
        tips = {
            "玄幻": """
玄幻小说写作技巧：
1. 战斗描写要有画面感，用具体的招式名称和动作
2. 修炼突破要有仪式感，描写身体变化和感悟
3. 世界观要通过角色视角自然展现，不要大段设定
4. 角色成长要有代价，不能轻易获得力量
5. 伏笔要自然埋设，不要太刻意
6. 力量体系要有明确的等级划分
7. 奇遇和机缘要合理，不能太随意
""",
            "仙侠": """
仙侠小说写作技巧：
1. 修仙体系要完整：炼气、筑基、金丹、元婴等
2. 法术描写要有仙气，用诗词般的语言
3. 天劫和突破要有仪式感
4. 道心和心境描写很重要
5. 法宝和丹药要有详细设定
6. 仙凡之别要体现出来
""",
            "都市": """
都市小说写作技巧：
1. 场景要有都市气息，描写现代化设施
2. 对话要口语化，符合人物身份
3. 职场描写要有专业感
4. 感情线要自然发展
5. 避免过度YY，保持真实感
6. 社会关系要真实可信
""",
            "历史": """
历史小说写作技巧：
1. 历史背景要准确，做好考证
2. 人物要符合时代特征
3. 政治斗争要有深度
4. 战争场面要有策略性
5. 语言要符合时代风格
6. 可以有艺术加工但不能违背历史大势
""",
            "科幻": """
科幻小说写作技巧：
1. 科技设定要有内在逻辑
2. 用具体细节展现未来世界
3. 探讨科技对人性的影响
4. 避免技术说明过多
5. 保持科学的基本严谨性
6. 硬科幻要注重科学原理
""",
            "悬疑": """
悬疑小说写作技巧：
1. 线索要埋设合理，前后呼应
2. 节奏要紧凑，保持悬念
3. 推理过程要逻辑严密
4. 反转要有铺垫，不能太突兀
5. 气氛营造很重要
6. 结局要出人意料又在情理之中
""",
            "游戏": """
游戏小说写作技巧：
1. 游戏系统要详细设定
2. 数值和等级要清晰
3. 团队配合要有策略性
4. PvP和PvE要有区别
5. 游戏内的社交要真实
6. 避免过度数据化影响阅读
""",
            "军事": """
军事小说写作技巧：
1. 军事术语要准确
2. 战术描写要专业
3. 战友情谊要真实
4. 武器装备要了解
5. 战争场面要有全局观
6. 军人的心理刻画很重要
""",
            "武侠": """
武侠小说写作技巧：
1. 武功招式要有特色
2. 江湖规矩和门派设定
3. 武德和侠义精神
4. 武打场面要有节奏感
5. 人物性格要鲜明
6. 恩怨情仇要复杂
""",
            "体育": """
体育小说写作技巧：
1. 体育项目要专业描写
2. 比赛场面要有紧张感
3. 运动员的成长要有挫折
4. 团队精神很重要
5. 竞技体育的残酷性
6. 荣耀背后的付出
""",
            "轻小说": """
轻小说写作技巧：
1. 文风要轻松有趣
2. 角色要有萌点
3. 对话要活泼
4. 插画感的场景描写
5. 适当加入吐槽
6. 节奏要轻快
""",
            "二次元": """
二次元小说写作技巧：
1. 要了解原作设定
2. 角色要符合原作性格
3. 可以加入原创元素
4. 要有二次元的氛围
5. 适当玩梗
6. 粉丝向内容要到位
""",
            "末日": """
末日小说写作技巧：
1. 生存压力要真实
2. 人性的考验
3. 资源争夺的残酷
4. 希望与绝望的交替
5. 末日设定要有特色
6. 团队合作的重要性
""",
            "古代言情": """
古代言情写作技巧：
1. 古代礼仪要准确
2. 服饰和场景描写要有古风
3. 对话要文雅但不晦涩
4. 宅斗和宫斗要有策略
5. 女主的成长要有智慧
6. 感情线要细腻
""",
            "现代言情": """
现代言情写作技巧：
1. 感情发展要自然
2. 误会和矛盾要合理
3. 男女主的性格要互补
4. 甜蜜和虐心要平衡
5. 配角要有存在感
6. 结局要圆满
""",
            "幻想言情": """
幻想言情写作技巧：
1. 奇幻设定要浪漫
2. 跨种族恋爱的冲突
3. 魔法和爱情的结合
4. 冒险中的感情升温
5. 世界观要服务于爱情
6. 要有独特的浪漫元素
""",
        }
        return tips.get(main_genre, tips["玄幻"])


class KnowledgeGraph:
    """知识图谱 - 借鉴codegraph概念，追踪角色关系和情节"""
    
    def __init__(self):
        self.entities: Dict[str, Dict] = {}  # 实体：角色、地点、物品
        self.relations: List[Dict] = []  # 关系
        self.events: List[Dict] = []  # 事件
    
    def add_entity(self, name: str, entity_type: str, attributes: Dict = None):
        """添加实体"""
        self.entities[name] = {
            "type": entity_type,
            "attributes": attributes or {},
            "first_appearance": datetime.now().isoformat(),
            "mentions": 0
        }
    
    def add_relation(self, entity1: str, entity2: str, relation_type: str, details: str = ""):
        """添加关系"""
        self.relations.append({
            "entity1": entity1,
            "entity2": entity2,
            "type": relation_type,
            "details": details,
            "created_at": datetime.now().isoformat()
        })
    
    def add_event(self, event_type: str, description: str, participants: List[str], chapter: int):
        """添加事件"""
        self.events.append({
            "type": event_type,
            "description": description,
            "participants": participants,
            "chapter": chapter,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_character_relations(self, character: str) -> List[Dict]:
        """获取角色的所有关系"""
        return [r for r in self.relations if r["entity1"] == character or r["entity2"] == character]
    
    def get_character_events(self, character: str) -> List[Dict]:
        """获取角色参与的所有事件"""
        return [e for e in self.events if character in e["participants"]]
    
    def get_relation_chain(self, entity1: str, entity2: str, max_depth: int = 3) -> List[List[str]]:
        """获取两个实体之间的关系链"""
        # BFS查找关系链
        visited = set()
        queue = [(entity1, [entity1])]
        
        while queue and len(visited) < 100:  # 限制搜索范围
            current, path = queue.pop(0)
            
            if current == entity2:
                return [path]
            
            if len(path) >= max_depth:
                continue
            
            if current in visited:
                continue
            visited.add(current)
            
            for rel in self.relations:
                next_entity = None
                if rel["entity1"] == current:
                    next_entity = rel["entity2"]
                elif rel["entity2"] == current:
                    next_entity = rel["entity1"]
                
                if next_entity and next_entity not in visited:
                    queue.append((next_entity, path + [next_entity]))
        
        return []
    
    def to_context_string(self, character: str = None) -> str:
        """转换为上下文字符串，供AI使用"""
        context_parts = []
        
        if character:
            # 角色相关上下文
            if character in self.entities:
                entity = self.entities[character]
                context_parts.append(f"【{character}】类型: {entity['type']}")
                if entity['attributes']:
                    for k, v in entity['attributes'].items():
                        context_parts.append(f"  {k}: {v}")
            
            # 角色关系
            relations = self.get_character_relations(character)
            if relations:
                context_parts.append(f"\n【{character}的关系】")
                for rel in relations[:10]:  # 限制数量
                    other = rel["entity2"] if rel["entity1"] == character else rel["entity1"]
                    context_parts.append(f"  - {other}: {rel['type']} ({rel['details']})")
            
            # 近期事件
            events = self.get_character_events(character)
            if events:
                context_parts.append(f"\n【{character}的近期事件】")
                for event in events[-5:]:  # 最近5个事件
                    context_parts.append(f"  - 第{event['chapter']}章: {event['description']}")
        else:
            # 全局上下文
            context_parts.append(f"【世界观】共{len(self.entities)}个实体，{len(self.relations)}个关系，{len(self.events)}个事件")
            
            # 主要角色
            characters = [name for name, e in self.entities.items() if e["type"] == "character"]
            if characters:
                context_parts.append(f"【主要角色】{', '.join(characters[:10])}")
        
        return '\n'.join(context_parts)
    
    def save(self, filepath: str):
        """保存到文件"""
        data = {
            "entities": self.entities,
            "relations": self.relations,
            "events": self.events
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self, filepath: str):
        """从文件加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.entities = data.get("entities", {})
            self.relations = data.get("relations", [])
            self.events = data.get("events", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"加载知识图谱失败: {e}")


class TimeAwareMemory:
    """时间感知记忆系统 - 借鉴supermemory概念"""
    
    def __init__(self, max_memories: int = 1000):
        self.memories: List[Dict] = []
        self.max_memories = max_memories
        self.importance_threshold = 0.3  # 重要性阈值
    
    def add_memory(self, content: str, memory_type: str, importance: float = 0.5, 
                   chapter: int = 0, tags: List[str] = None):
        """添加记忆"""
        memory = {
            "content": content,
            "type": memory_type,
            "importance": importance,
            "chapter": chapter,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "access_count": 0,
            "decay_factor": 1.0  # 衰减因子
        }
        self.memories.append(memory)
        
        # 超过上限时清理
        if len(self.memories) > self.max_memories:
            self._cleanup()
    
    def _cleanup(self):
        """清理过时或不重要的记忆"""
        now = datetime.now()
        
        # 计算每个记忆的综合分数
        scored_memories = []
        for memory in self.memories:
            # 时间衰减
            created = datetime.fromisoformat(memory["created_at"])
            days_old = (now - created).days
            time_decay = max(0.1, 1.0 - (days_old / 30))  # 30天衰减到0.1
            
            # 访问频率加成
            access_boost = min(2.0, 1.0 + memory["access_count"] * 0.1)
            
            # 综合分数
            score = memory["importance"] * time_decay * access_boost
            scored_memories.append((score, memory))
        
        # 排序并保留高分记忆
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        self.memories = [m for _, m in scored_memories[:self.max_memories]]
    
    def query(self, query_text: str = None, memory_type: str = None, 
              tags: List[str] = None, limit: int = 10) -> List[Dict]:
        """查询记忆"""
        results = []
        
        for memory in self.memories:
            # 类型过滤
            if memory_type and memory["type"] != memory_type:
                continue
            
            # 标签过滤
            if tags and not any(tag in memory["tags"] for tag in tags):
                continue
            
            # 文本匹配
            if query_text and query_text not in memory["content"]:
                continue
            
            # 更新访问信息
            memory["last_accessed"] = datetime.now().isoformat()
            memory["access_count"] += 1
            
            results.append(memory)
        
        # 按重要性排序
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results[:limit]
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """获取最近的记忆"""
        sorted_memories = sorted(self.memories, key=lambda x: x["created_at"], reverse=True)
        return sorted_memories[:limit]
    
    def get_context_string(self, query: str = None, limit: int = 5) -> str:
        """获取上下文字符串"""
        memories = self.query(query_text=query, limit=limit)
        
        if not memories:
            return ""
        
        context_parts = ["【相关记忆】"]
        for memory in memories:
            context_parts.append(f"- [{memory['type']}] {memory['content'][:100]}")
        
        return '\n'.join(context_parts)
    
    def save(self, filepath: str):
        """保存到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=2)
    
    def load(self, filepath: str):
        """从文件加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                self.memories = data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"加载时间记忆失败: {e}")


class WritingSkillManager:
    """写作技能管理器 - 借鉴hermes-agent的自我改进概念"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.anti_slop = AntiSlopProcessor()
        self.knowledge_graph = KnowledgeGraph()
        self.time_memory = TimeAwareMemory()
        self.style_config = WritingStyleConfig()
    
    def analyze_and_improve(self, text: str, genre: str = "玄幻") -> Tuple[str, List[str]]:
        """分析并改进文本"""
        improvements = []
        
        # 1. 去AI味检查
        issues = self.anti_slop.check_text(text)
        if any(issues.values()):
            improvements.append("发现AI写作痕迹:")
            for issue_type, issue_list in issues.items():
                if issue_list and issue_type != "suggestions":
                    improvements.extend([f"  - {i}" for i in issue_list[:3]])
            if issues["suggestions"]:
                improvements.extend([f"  建议: {s}" for s in issues["suggestions"]])
        
        # 2. 获取写作技巧
        tips = self.anti_slop.get_writing_tips(genre)
        improvements.append(f"\n{tips}")
        
        return text, improvements
    
    def get_writing_context(self, character: str = None, chapter: int = 0) -> str:
        """获取写作上下文"""
        context_parts = []
        
        # 风格配置
        context_parts.append(self.style_config.to_prompt())
        
        # 知识图谱上下文
        kg_context = self.knowledge_graph.to_context_string(character)
        if kg_context:
            context_parts.append(f"\n{kg_context}")
        
        # 时间感知记忆
        memory_context = self.time_memory.get_context_string(query=character)
        if memory_context:
            context_parts.append(f"\n{memory_context}")
        
        return '\n'.join(context_parts)
    
    def learn_from_chapter(self, chapter_content: str, chapter_num: int, 
                          characters: List[str], success: bool = True):
        """从章节学习，创建写作技能"""
        if success:
            # 提取成功的写作模式
            # 分析对话比例
            dialogue_lines = [l for l in chapter_content.split('\n') if '"' in l or '"' in l]
            dialogue_ratio = len(dialogue_lines) / max(1, len(chapter_content.split('\n')))
            
            # 记录到记忆
            self.time_memory.add_memory(
                content=f"第{chapter_num}章成功生成，对话比例{dialogue_ratio:.1%}",
                memory_type="success_pattern",
                importance=0.6,
                chapter=chapter_num,
                tags=["success", "dialogue"]
            )
            
            # 更新角色关系
            for char in characters:
                if char not in self.knowledge_graph.entities:
                    self.knowledge_graph.add_entity(char, "character")
                self.knowledge_graph.entities[char]["mentions"] = \
                    self.knowledge_graph.entities[char].get("mentions", 0) + 1
    
    def save_all(self, base_dir: str):
        """保存所有数据"""
        import os
        os.makedirs(base_dir, exist_ok=True)
        
        self.knowledge_graph.save(os.path.join(base_dir, "knowledge_graph.json"))
        self.time_memory.save(os.path.join(base_dir, "time_memory.json"))
        
        # 保存风格配置
        with open(os.path.join(base_dir, "style_config.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "descriptiveness": self.style_config.descriptiveness,
                "dialogue_ratio": self.style_config.dialogue_ratio,
                "pacing": self.style_config.pacing,
                "emotional_depth": self.style_config.emotional_depth,
                "action_intensity": self.style_config.action_intensity,
                "genre_style": self.style_config.genre_style
            }, f, ensure_ascii=False, indent=2)
    
    def load_all(self, base_dir: str):
        """加载所有数据"""
        import os
        
        kg_path = os.path.join(base_dir, "knowledge_graph.json")
        if os.path.exists(kg_path):
            self.knowledge_graph.load(kg_path)
        
        tm_path = os.path.join(base_dir, "time_memory.json")
        if os.path.exists(tm_path):
            self.time_memory.load(tm_path)
        
        sc_path = os.path.join(base_dir, "style_config.json")
        if os.path.exists(sc_path):
            try:
                with open(sc_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if isinstance(config, dict):
                    self.style_config.descriptiveness = config.get("descriptiveness", 7)
                    self.style_config.dialogue_ratio = config.get("dialogue_ratio", 5)
                    self.style_config.pacing = config.get("pacing", 5)
                    self.style_config.emotional_depth = config.get("emotional_depth", 6)
                    self.style_config.action_intensity = config.get("action_intensity", 5)
                    self.style_config.genre_style = config.get("genre_style", "玄幻")
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"加载风格配置失败: {e}")


# 全局实例
writing_skill_manager = WritingSkillManager()
