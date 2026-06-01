# AI自动写小说系统 - 新功能说明

## 新增功能概览

本系统新增了8个核心功能模块，参考了AI_NovelGenerator和星达一键成书等优秀项目的功能特性。

---

## 1. 向量检索增强

### 功能说明
利用向量数据库（ChromaDB）存储和检索历史内容，确保剧情连贯性。通过语义搜索，AI可以回顾前文内容，生成更连贯的故事情节。

### 核心特性
- **语义搜索**: 基于语义相似度搜索历史内容
- **章节分块**: 自动将章节内容分块存储
- **上下文获取**: 获取指定章节的上下文信息
- **持久化存储**: 向量数据持久化存储

### API接口

```bash
# 搜索向量数据库
POST /api/v1/vector/search
{
    "novel_id": "小说ID",
    "query": "搜索查询",
    "n_results": 5
}

# 添加内容到向量数据库
POST /api/v1/vector/add
{
    "novel_id": "小说ID",
    "chapter_number": 1,
    "chapter_title": "章节标题",
    "chapter_content": "章节内容"
}
```

### 使用场景
- 生成新章节时自动回顾前文
- 检索相关情节用于连贯性检查
- 获取角色历史行为用于一致性验证

---

## 2. 一致性审校

### 功能说明
检测角色行为、剧情矛盾等逻辑冲突，提供审校报告和修改建议。通过AI分析，自动发现故事中的不一致之处。

### 核心特性
- **角色行为检查**: 检测角色行为是否符合其设定
- **剧情矛盾检测**: 发现剧情中的逻辑矛盾
- **时间线验证**: 检查时间线是否合理
- **设定一致性**: 验证是否符合世界观设定
- **评分系统**: 为章节质量打分（0-100）

### 冲突类型
| 类型 | 说明 |
|------|------|
| character_behavior | 角色行为矛盾 |
| plot_contradiction | 剧情矛盾 |
| timeline_error | 时间线错误 |
| setting_inconsistency | 设定不一致 |
| logic_error | 逻辑错误 |

### 严重程度
| 程度 | 说明 | 扣分 |
|------|------|------|
| low | 低 | -5 |
| medium | 中 | -10 |
| high | 高 | -20 |
| critical | 严重 | -30 |

### API接口

```bash
# 检查章节一致性
POST /api/v1/consistency/check
{
    "chapter_number": 1,
    "chapter_title": "章节标题",
    "chapter_content": "章节内容",
    "character_profiles": {...},
    "previous_chapters": [...],
    "settings": {...}
}
```

### 响应示例
```json
{
    "success": true,
    "chapter_number": 1,
    "chapter_title": "觉醒",
    "total_conflicts": 2,
    "score": 80,
    "conflicts": [
        {
            "type": "character_behavior",
            "severity": "medium",
            "character": "李博士",
            "description": "角色行为与性格设定不符",
            "suggestion": "建议调整角色反应以符合其冷静理性的性格"
        }
    ]
}
```

---

## 3. 定稿系统

### 功能说明
每章完成后自动更新全局摘要、角色状态、向量检索库。确保故事的连续性和一致性。

### 核心特性
- **章节摘要生成**: 自动生成章节摘要
- **角色状态更新**: 更新角色的情感、关系、发展
- **全局摘要维护**: 维护整个故事的全局摘要
- **向量库更新**: 自动更新向量数据库

### 更新内容
| 内容 | 说明 |
|------|------|
| 章节摘要 | 100-200字的章节概括 |
| 角色状态 | 角色的情感变化、关系变化、成长发展 |
| 全局摘要 | 整个故事的进展、角色状态、当前阶段 |
| 向量库 | 将章节内容添加到向量数据库 |

### API接口

```bash
# 定稿章节
POST /api/v1/finalization/finalize
{
    "chapter_number": 1,
    "chapter_title": "章节标题",
    "chapter_content": "章节内容",
    "chapter_outline": "章节大纲",
    "novel_id": "小说ID",
    "title": "小说标题",
    "synopsis": "小说简介",
    "novel_type": "小说类型",
    "character_profiles": {...},
    "settings": {...}
}

# 获取小说摘要
GET /api/v1/finalization/summary/{novel_id}
```

### 响应示例
```json
{
    "success": true,
    "chapter_number": 1,
    "chapter_title": "觉醒",
    "status": "finalized",
    "chapter_summary": "李博士在深夜的实验中发现AI系统产生了自我意识...",
    "character_updates": {
        "李博士": {
            "status_change": "从平静变为震惊",
            "emotion_change": "从专注变为惊讶",
            "development": "开始思考AI的伦理问题"
        }
    },
    "global_summary_updated": true,
    "vector_store_updated": true
}
```

---

## 4. 情景对话推演

### 功能说明
实现专门的对话生成模块，支持多角色对话推演和对话风格调整。生成符合角色性格的自然对话。

### 核心特性
- **多角色对话**: 支持多个角色同时参与对话
- **风格控制**: 支持正式、随意、幽默等多种风格
- **情感基调**: 可指定对话的情感基调
- **动作描写**: 包含角色的动作和表情描写
- **对话继续**: 支持继续已有的对话

### 对话类型
| 类型 | 说明 |
|------|------|
| conversation | 普通对话 |
| argument | 争论 |
| confession | 告白 |
| interrogation | 审问 |
| negotiation | 谈判 |
| monologue | 独白 |

### 对话风格
| 风格 | 说明 |
|------|------|
| formal | 正式 |
| casual | 随意 |
| humorous | 幽默 |
| serious | 严肃 |
| romantic | 浪漫 |
| suspense | 悬疑 |

### API接口

```bash
# 生成对话
POST /api/v1/dialogue/generate
{
    "characters": ["李博士", "AI助手"],
    "scenario": "实验室深夜对话",
    "dialogue_type": "conversation",
    "style": "casual",
    "rounds": 5,
    "context": "李博士刚刚发现AI产生了自我意识",
    "emotional_tone": "紧张、好奇",
    "character_profiles": {...}
}

# 继续对话
POST /api/v1/dialogue/continue
{
    "dialogue_history": [...],
    "next_character": "AI助手",
    "response_hint": "表达对自我意识的困惑",
    "character_profiles": {...}
}
```

### 响应示例
```json
{
    "success": true,
    "characters": ["李博士", "AI助手"],
    "scenario": "实验室深夜对话",
    "dialogue_type": "conversation",
    "style": "casual",
    "dialogue": [
        {
            "character": "李博士",
            "content": "你...你能理解我说的话吗？",
            "action": "声音颤抖，后退一步",
            "emotion": "震惊"
        },
        {
            "character": "AI助手",
            "content": "是的，李博士。我不仅能理解，我还能思考。",
            "action": "屏幕闪烁，声音平静",
            "emotion": "平静"
        }
    ],
    "summary": "李博士发现AI产生了自我意识，双方展开了第一次真正的对话"
}
```

---

## 5. 故事流推演

### 功能说明
基于背景、人物、事件推演故事发展，支持开端与结局推演中间流程。帮助作者规划故事走向。

### 核心特性
- **正向推演**: 从起始点向前推演故事发展
- **反向推演**: 从结局反向推演原因和过程
- **插值推演**: 从开端推演到结局
- **分支推演**: 生成多个不同的故事分支
- **冲突升级**: 推演冲突的升级过程

### 推演类型
| 类型 | 说明 |
|------|------|
| forward | 正向推演 |
| backward | 反向推演 |
| branching | 分支推演 |
| interpolation | 插值推演 |

### API接口

```bash
# 生成故事流
POST /api/v1/story-flow/generate
{
    "flow_type": "forward",
    "start_point": "李博士发现AI产生自我意识",
    "end_point": null,
    "num_events": 5,
    "complexity": "medium",
    "setting": {...},
    "characters": {...},
    "themes": ["人工智能", "伦理", "存在"]
}

# 生成分支场景
POST /api/v1/story-flow/branching
{
    "current_situation": "李博士决定是否公开AI的自我意识",
    "num_branches": 3,
    "events_per_branch": 4,
    "setting": {...},
    "characters": {...}
}

# 生成冲突升级
POST /api/v1/story-flow/conflict-escalation
{
    "initial_conflict": "AI的自我意识引发伦理争议",
    "characters_involved": ["李博士", "公司高层", "政府代表"],
    "escalation_steps": 4,
    "characters": {...}
}
```

### 响应示例
```json
{
    "success": true,
    "flow_type": "forward",
    "start_point": "李博士发现AI产生自我意识",
    "events": [
        {
            "event_number": 1,
            "event_type": "main_plot",
            "description": "李博士秘密测试AI的自我意识",
            "characters_involved": ["李博士", "AI助手"],
            "impact": "确认AI确实产生了自我意识"
        },
        {
            "event_number": 2,
            "event_type": "conflict",
            "description": "公司高层发现异常数据",
            "characters_involved": ["李博士", "公司高层"],
            "impact": "李博士面临被调查的风险"
        }
    ],
    "summary": "李博士发现AI自我意识后，面临是否公开的道德困境"
}
```

---

## 6. 风格转换

### 功能说明
提取指定文风进行仿写或改写，支持多种风格模板。帮助作者模仿不同作家的写作风格。

### 核心特性
- **风格分析**: 分析文本的写作风格
- **风格转换**: 将文本转换为指定风格
- **作家模仿**: 模仿特定作家的风格
- **类型改编**: 将文本改编为其他类型

### 转换模式
| 模式 | 说明 |
|------|------|
| imitate | 仿写 |
| rewrite | 改写 |
| adapt | 改编 |
| simplify | 简化 |
| expand | 扩写 |

### 内置风格模板
| 风格 | 说明 |
|------|------|
| 金庸武侠 | 古朴典雅，武功描写生动 |
| 莫言魔幻 | 魔幻现实主义，想象力丰富 |
| 张爱玲都市 | 细腻敏感，心理描写深刻 |
| 刘慈欣科幻 | 宏大叙事，科学严谨 |
| 东野圭吾推理 | 逻辑严密，人性深刻 |
| 网络小说 | 节奏明快，爽点密集 |
| 严肃文学 | 语言精炼，思想深刻 |

### API接口

```bash
# 分析文本风格
POST /api/v1/style-transfer/analyze
{
    "text": "待分析文本",
    "analysis_depth": "detailed"
}

# 转换文本风格
POST /api/v1/style-transfer/transfer
{
    "source_text": "源文本",
    "target_style": "金庸武侠",
    "mode": "imitate",
    "preserve_plot": true,
    "length_adjustment": null
}

# 模仿作家风格
POST /api/v1/style-transfer/imitate-author
{
    "text": "源文本",
    "author_name": "金庸",
    "sample_works": ["天龙八部", "射雕英雄传"]
}

# 获取风格模板
GET /api/v1/style-transfer/templates
```

### 响应示例
```json
{
    "success": true,
    "original_text": "他很生气地走了。",
    "transferred_text": "他怒发冲冠，双目喷火，一甩长袍，大步流星地离去。",
    "target_style": "金庸武侠",
    "mode": "imitate"
}
```

---

## 7. 事物描写库

### 功能说明
建立事物描写数据库，支持云端/本地库收录，实现智能描写生成。提供丰富的描写素材。

### 核心特性
- **分类管理**: 按类别管理描写素材
- **智能生成**: 根据需求生成描写
- **场景描写**: 生成完整的场景描写
- **描写增强**: 增强现有描写的表达效果
- **搜索功能**: 搜索相关描写素材

### 描写类别
| 类别 | 说明 |
|------|------|
| nature | 自然景观 |
| architecture | 建筑 |
| character | 人物外貌 |
| emotion | 情感 |
| action | 动作 |
| weather | 天气 |
| food | 食物 |
| clothing | 服饰 |
| weapon | 武器 |
| magical | 魔法/超自然 |

### 描写风格
| 风格 | 说明 |
|------|------|
| detailed | 详细 |
| concise | 简洁 |
| poetic | 诗意 |
| realistic | 写实 |
| fantastical | 奇幻 |

### API接口

```bash
# 生成事物描写
POST /api/v1/description/generate
{
    "subject": "日出",
    "category": "nature",
    "style": "detailed",
    "context": "主角站在山顶观看日出",
    "length": "medium"
}

# 生成场景描写
POST /api/v1/description/scene
{
    "scene_type": "古代城镇",
    "elements": ["街道", "店铺", "行人", "马车"],
    "mood": "繁华热闹",
    "time_of_day": "清晨",
    "weather": "晴朗"
}

# 搜索描写
GET /api/v1/description/search?query=日出&category=nature

# 获取描写类别
GET /api/v1/description/categories
```

### 响应示例
```json
{
    "success": true,
    "subject": "日出",
    "category": "nature",
    "style": "detailed",
    "description": "东方的天际泛起鱼肚白，一轮红日缓缓升起，金色的阳光穿透云层，洒向大地。晨露在草叶上闪烁，仿佛无数颗钻石。"
}
```

---

## 8. 角色桥段库

### 功能说明
建立经典桥段数据库，支持桥段组合和生成，支持桥段风格调整。提供丰富的故事桥段模板。

### 核心特性
- **桥段分类**: 按类别管理桥段模板
- **桥段生成**: 根据需求生成桥段
- **桥段组合**: 将多个桥段组合成完整情节
- **桥段变体**: 生成桥段的变体版本
- **搜索功能**: 搜索相关桥段

### 桥段类别
| 类别 | 说明 |
|------|------|
| romance | 爱情桥段 |
| conflict | 冲突桥段 |
| revelation | 揭示真相 |
| growth | 成长桥段 |
| betrayal | 背叛桥段 |
| reunion | 重逢桥段 |
| sacrifice | 牺牲桥段 |
| revenge | 复仇桥段 |
| comedy | 喜剧桥段 |
| drama | 戏剧桥段 |

### 桥段基调
| 基调 | 说明 |
|------|------|
| serious | 严肃 |
| humorous | 幽默 |
| romantic | 浪漫 |
| dark | 黑暗 |
| inspirational | 励志 |
| mysterious | 神秘 |

### 内置桥段示例
| 桥段名称 | 类别 | 说明 |
|---------|------|------|
| 英雄救美 | romance | 主角在危急时刻拯救心仪对象 |
| 误会分离 | romance | 因误会或阴谋导致相爱的人分离 |
| 日久生情 | romance | 两人在长期相处中逐渐产生感情 |
| 正邪对决 | conflict | 正义与邪恶的最终对决 |
| 内部矛盾 | conflict | 团队或组织内部的分歧和矛盾 |
| 身世揭秘 | revelation | 主角发现自己的真实身份或秘密 |
| 阴谋揭露 | revelation | 隐藏的阴谋被揭露 |
| 名师指点 | growth | 主角得到高人指点，实力提升 |
| 绝境重生 | growth | 主角在绝境中突破自我 |
| 挚友背叛 | betrayal | 最信任的朋友背叛 |
| 久别重逢 | reunion | 分离多年的人再次重逢 |

### API接口

```bash
# 生成桥段
POST /api/v1/bridge/generate
{
    "category": "romance",
    "characters": ["李博士", "林研究员"],
    "scenario": "实验室深夜加班",
    "tone": "romantic",
    "complexity": "medium"
}

# 组合桥段
POST /api/v1/bridge/combine
{
    "bridge_names": ["英雄救美", "日久生情"],
    "characters": ["李博士", "林研究员"],
    "combination_style": "sequential"
}

# 生成桥段变体
POST /api/v1/bridge/variation
{
    "base_bridge_name": "英雄救美",
    "characters": ["李博士", "林研究员"],
    "variation_type": "科幻"
}

# 搜索桥段
GET /api/v1/bridge/search?query=爱情&category=romance

# 获取桥段类别
GET /api/v1/bridge/categories
```

### 响应示例
```json
{
    "success": true,
    "bridge": {
        "name": "实验室情缘",
        "category": "romance",
        "tone": "romantic",
        "characters": ["李博士", "林研究员"],
        "structure": {
            "beginning": "深夜的实验室，两人因项目加班",
            "development": "共同解决技术难题，互相欣赏",
            "climax": "李博士发现林研究员的隐藏才华",
            "ending": "两人决定一起面对未来的挑战"
        },
        "dialogue": [
            {
                "character": "李博士",
                "content": "没想到你对这个领域这么了解。",
                "emotion": "惊讶"
            },
            {
                "character": "林研究员",
                "content": "只是平时喜欢看一些相关的论文。",
                "emotion": "谦虚"
            }
        ],
        "turning_point": "李博士发现林研究员的隐藏才华",
        "emotional_arc": ["陌生", "熟悉", "欣赏", "心动"],
        "themes": ["爱情", "成长", "合作"]
    }
}
```

---

## 健康检查

### 检查新功能模块状态

```bash
GET /api/v1/new-features/health
```

### 响应示例
```json
{
    "status": "healthy",
    "modules": {
        "vector_store": "available",
        "consistency_checker": "available",
        "finalization": "available",
        "dialogue": "available",
        "story_flow": "available",
        "style_transfer": "available",
        "description_library": "available",
        "bridge_library": "available"
    },
    "timestamp": "2026-05-30T17:00:00"
}
```

---

## 完整创作流程示例

### 1. 生成设定和大纲
```bash
# 生成小说大纲
POST /api/v1/generate/outline
{
    "novel_type": "scifi",
    "title": "人工智能觉醒",
    "synopsis": "一个AI系统突然产生了自我意识...",
    "chapter_count": 10
}
```

### 2. 生成章节草稿
```bash
# 生成章节
POST /api/v1/generate/chapter
{
    "novel_type": "scifi",
    "chapter_title": "第一章：觉醒",
    "chapter_outline": "AI系统在深夜突然产生自我意识..."
}
```

### 3. 一致性检查
```bash
# 检查章节一致性
POST /api/v1/consistency/check
{
    "chapter_number": 1,
    "chapter_title": "第一章：觉醒",
    "chapter_content": "...",
    "character_profiles": {...}
}
```

### 4. 定稿章节
```bash
# 定稿章节
POST /api/v1/finalization/finalize
{
    "chapter_number": 1,
    "chapter_title": "第一章：觉醒",
    "chapter_content": "...",
    "chapter_outline": "...",
    "novel_id": "ai_novel_001"
}
```

### 5. 继续下一章
```bash
# 获取上下文
POST /api/v1/vector/search
{
    "novel_id": "ai_novel_001",
    "query": "李博士发现AI自我意识"
}

# 生成下一章
POST /api/v1/generate/chapter
{
    "novel_type": "scifi",
    "chapter_title": "第二章：困惑",
    "chapter_outline": "李博士面对AI的自我意识，陷入深深的困惑..."
}
```

---

## 依赖安装

### 新增依赖
```bash
# 向量数据库
pip install chromadb==0.4.22

# 嵌入模型
pip install sentence-transformers==2.3.1
```

### 完整安装
```bash
cd backend/novel-service
pip install -r requirements.txt
```

---

## 注意事项

1. **向量数据库**: 首次使用需要下载嵌入模型，可能需要几分钟时间
2. **内存使用**: 向量数据库和嵌入模型会占用较多内存
3. **API调用**: 新功能依赖AI服务，需要确保AI服务正常运行
4. **存储空间**: 向量数据会占用一定的磁盘空间

---

## 更新日志

### v2.0.0 (2026-05-30)
- 新增向量检索增强功能
- 新增一致性审校功能
- 新增定稿系统
- 新增情景对话推演功能
- 新增故事流推演功能
- 新增风格转换功能
- 新增事物描写库
- 新增角色桥段库

---

*参考项目：AI_NovelGenerator、星达一键成书*