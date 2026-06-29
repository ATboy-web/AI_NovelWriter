# AI_NovelWriter API 文档

本文档描述了 AI_NovelWriter 项目的核心模块和 API 接口。

## 目录

- [AI客户端](#ai客户端)
- [记忆管理器](#记忆管理器)
- [小说工具包](#小说工具包)
- [安全配置](#安全配置)
- [角色系统](#角色系统)

---

## AI客户端

### 模块位置

```python
from app.ai_client import AIClient, TokenStats, retry_with_backoff
```

### TokenStats

Token 消耗统计类，用于跟踪 API 调用的 token 使用情况。

```python
@dataclass
class TokenStats:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0
```

#### 方法

##### `record(prompt_tokens: int, completion_tokens: int)`

记录一次 API 调用的 token 消耗。

```python
stats = TokenStats()
stats.record(100, 50)  # 记录 100 prompt tokens + 50 completion tokens
```

##### `get_summary() -> Dict`

获取统计摘要。

```python
summary = stats.get_summary()
# {
#     "total_tokens": 150,
#     "prompt_tokens": 100,
#     "completion_tokens": 50,
#     "request_count": 1
# }
```

##### `get_display() -> str`

获取用户友好的显示文本。

```python
stats.record(1000, 500)
print(stats.get_display())  # "1.5K tokens (1次调用)"
```

#### 特性

- **线程安全**: 使用 `threading.Lock` 保护共享状态
- **自动格式化**: 根据数值大小自动选择 K/M 单位

---

### retry_with_backoff

指数退避重试装饰器。

```python
@retry_with_backoff(max_retries=3, base_delay=1, max_delay=30)
def api_call():
    # 可能失败的 API 调用
    pass
```

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_retries` | int | 3 | 最大重试次数 |
| `base_delay` | float | 1 | 基础延迟（秒） |
| `max_delay` | float | 30 | 最大延迟（秒） |

#### 退避策略

- 第 1 次重试：等待 `base_delay` 秒
- 第 2 次重试：等待 `base_delay * 2` 秒
- 第 3 次重试：等待 `base_delay * 4` 秒
- 延迟不超过 `max_delay`

#### 示例

```python
import time

@retry_with_backoff(max_retries=3, base_delay=0.1)
def unstable_api():
    if random.random() < 0.7:
        raise ConnectionError("连接失败")
    return "成功"

try:
    result = unstable_api()
except ConnectionError:
    print("重试3次后仍然失败")
```

---

## 记忆管理器

### 模块位置

```python
from app.memory_manager import MemoryManager
```

### MemoryManager

分层记忆管理系统，支持 5000 章小说的记忆管理。

```python
class MemoryManager:
    def __init__(self, novel_dir: Path):
        """
        初始化记忆管理器
        
        Args:
            novel_dir: 小说目录路径
        """
```

#### 层级结构

```
全局摘要
├── 卷级摘要（每100章）
│   ├── 弧线摘要
│   │   └── 章节摘要
│   └── 角色活跃度
└── 倒排索引
```

#### 核心方法

##### 卷级摘要

```python
# 保存卷级摘要
mm.save_volume_summary(volume_num=1, summary="第1卷摘要：主角觉醒")

# 获取卷级摘要
summary = mm.get_volume_summary(volume_num=1)

# 获取当前卷摘要（根据章节号自动计算）
summary = mm.get_current_volume_summary(chapter_num=50)
```

##### 弧线摘要

```python
# 保存弧线摘要
mm.save_arc_summary(
    arc_name="修炼弧",
    summary="主角从凡人修炼到筑基",
    chapters=[1, 2, 3, 4, 5]
)

# 获取弧线摘要
summary = mm.get_arc_summary(arc_name="修炼弧")

# 获取所有弧线
arcs = mm.get_all_arcs()
# [{"name": "修炼弧", "summary": "...", "chapters": [1,2,3,4,5]}]
```

##### 章节摘要

```python
# 保存章节摘要
mm.save_chapter_summary(chapter_num=1, summary="第1章：主角出场")

# 获取章节摘要
summary = mm.get_chapter_summary(chapter_num=1)

# 获取最近N章摘要
recent = mm.get_recent_summaries(n=5)

# 获取章节范围摘要
range_summary = mm.get_chapter_range_summary(start=1, end=10)
```

##### 角色活跃度

```python
# 更新角色活跃度
mm.update_character_activity(character_name="张三", chapter_num=1)

# 获取活跃角色列表
active_chars = mm.get_active_characters(
    current_chapter=100,
    window=50  # 最近50章内出现的角色
)
```

##### 全局摘要

```python
# 保存全局摘要
mm.save_global_summary(summary="这是一个关于修炼的故事")

# 获取全局摘要
summary = mm.get_global_summary()
```

##### 检索相关记忆

```python
# 基于关键词检索相关记忆
results = mm.retrieve_relevant(query="张三修炼", top_k=5)
# [{"doc_id": "...", "content": "...", "score": 0.85}]
```

##### 健康检查

```python
report = mm.health_check()
# {
#     "total_chapters": 100,
#     "total_volumes": 1,
#     "total_arcs": 5,
#     "recommendations": ["建议清理旧的弧线摘要"]
# }
```

#### 特性

- **分层存储**: 全局 → 卷 → 弧线 → 章节
- **倒排索引**: 支持快速关键词检索
- **活跃度追踪**: 自动记录角色出场章节
- **分页存储**: 每100个 chunks 一页，支持大文件

---

## 小说工具包

### 模块位置

```python
from novel_toolkit import (
    ElementLibrary,      # 事物描写库
    BridgeLibrary,       # 角色桥段库
    DescriptionLibrary,  # 描写库
    DialogueEngine,      # 情景对话引擎
    StoryFlowEngine,     # 故事流引擎
    StyleTransferEngine, # 风格转换引擎
    AdaptEngine,         # 改编引擎
    WebSearchAdaptEngine # 搜索改编引擎
)
```

### ElementLibrary

事物描写库，提供 10 种描写类别。

```python
lib = ElementLibrary()

# 获取所有类别
categories = lib.get_categories()
# [{"name": "自然景观", "description": "..."}, ...]

# 获取类别下的元素
items = lib.get_items(category="自然景观")
# [{"name": "日出", "template": "..."}, ...]

# 添加自定义元素
lib.add_custom_item(
    category="自然景观",
    item={"name": "极光", "template": "绚丽的极光在夜空中舞动..."}
)
```

#### 类别列表

| 类别 | 说明 |
|------|------|
| 自然景观 | 日出、日落、山川、河流等 |
| 建筑场景 | 宫殿、城堡、村庄等 |
| 战斗场面 | 武侠打斗、魔法战斗等 |
| 情感描写 | 喜怒哀乐、爱恨情仇等 |
| 人物外貌 | 相貌、服饰、气质等 |
| 美食描写 | 菜肴、饮品、食材等 |
| 天气气候 | 晴天、雨天、雪天等 |
| 器物道具 | 武器、法宝、工具等 |
| 动物植物 | 灵兽、灵草、花卉等 |
| 社会场景 | 集市、酒楼、战场等 |

---

### BridgeLibrary

角色桥段库，提供 10 种桥段类别和 6 种桥段基调。

```python
lib = BridgeLibrary()

# 获取类别
categories = lib.get_categories()

# 获取桥段模板
templates = lib.get_templates(category="英雄救美")
# ["主角在危急时刻出现，救下被困的女主..."]

# 添加自定义桥段
lib.add_custom_item(
    category="英雄救美",
    template="主角从天而降，一剑斩断锁链..."
)
```

#### 桥段类别

- 英雄救美
- 身世揭秘
- 师徒传承
- 误会冲突
- 三角恋情
- 复仇雪恨
- 背叛反转
- 牺牲奉献
- 重逢团聚
- 决战巅峰

#### 桥段基调

- 热血
- 悲情
- 搞笑
- 温馨
- 悬疑
- 史诗

---

### DialogueEngine

情景对话推演引擎。

```python
client = AIClient(config)
engine = DialogueEngine(client)

# 开始对话
dialogue = engine.start_dialogue(
    scenario="酒馆偶遇",
    characters=[
        {"name": "张三", "personality": "豪爽"},
        {"name": "李四", "personality": "谨慎"}
    ],
    style="自然"
)

# 继续对话
next_part = engine.continue_dialogue(direction="引入冲突")

# 导出对话文本
text = engine.export_text()
```

---

### StoryFlowEngine

故事流推演引擎，支持 4 种推演模式。

```python
client = AIClient(config)
engine = StoryFlowEngine(client)

# 模式1：正向推演
story = engine.mode1_forward(
    background="修仙世界",
    protagonist="张三",
    events="获得传承，开始修炼"
)

# 模式2：桥接推演
story = engine.mode2_bridge(
    beginning="主角获得传承",
    ending="主角成为强者"
)

# 模式3：分支推演
branches = engine.mode3_branch(
    story="主角面临选择",
    branch_count=3
)

# 模式4：冲突升级
escalated = engine.mode4_conflict_escalation(
    situation="主角被敌人包围"
)
```

---

### StyleTransferEngine

风格转换引擎，支持 7 种风格模板。

```python
client = AIClient(config)
engine = StyleTransferEngine(client)

# 获取支持的风格
styles = engine.get_styles()
# {
#     "热血爽文": "节奏快，打斗多，升级爽...",
#     "文艺清新": "文笔优美，情感细腻...",
#     ...
# }

# 转换风格
converted = engine.convert_style(
    text="张三挥剑斩向敌人...",
    target_style="文艺清新"
)
```

#### 支持的风格

1. 热血爽文
2. 文艺清新
3. 悬疑惊悚
4. 轻松幽默
5. 史诗宏大
6. 古风典雅
7. 现代都市

---

## 安全配置

### 模块位置

```python
from app.secure_config import SecureConfig, get_secure_config
```

### SecureConfig

安全配置管理器，使用 Fernet 加密保护敏感数据。

```python
class SecureConfig:
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化安全配置管理器
        
        Args:
            config_dir: 配置目录路径，默认 ~/.ai_novel_writer
        """
```

#### 核心方法

##### 获取和设置配置

```python
config = SecureConfig()

# 获取配置
api_key = config.get("api_key")
model = config.get("model", "gpt-4")  # 带默认值

# 设置配置
config.set("api_key", "sk-xxx")
config.set("model", "gpt-4")
```

##### API 密钥管理

```python
# 获取 API 密钥（自动解密）
api_key = config.get_api_key()

# 设置 API 密钥（自动加密）
config.set_api_key("sk-xxx")
```

#### 加密机制

- **算法**: Fernet (AES-128-CBC)
- **密钥存储**: `~/.ai_novel_writer/.config_key`
- **加密字段**: `api_key`, `img_api_key`, `secret_key`
- **向后兼容**: 自动识别未加密的旧配置

#### 示例

```python
from app.secure_config import get_secure_config

# 获取全局实例
config = get_secure_config()

# 保存 API 密钥
config.set_api_key("sk-xxx")

# 读取 API 密钥
key = config.get_api_key()  # "sk-xxx"

# 查看原始文件（密钥已加密）
# ~/.ai_novel_writer/config.json 中的 api_key 是加密的
```

---

## 角色系统

### 模块位置

```python
from app.character_manager import CharacterManager
```

### CharacterManager

角色管理系统，支持角色的五维度信息。

```python
class CharacterManager:
    def __init__(self, novel_dir: Path):
        """
        初始化角色管理器
        
        Args:
            novel_dir: 小说目录路径
        """
```

#### 角色维度

| 维度 | 说明 | 示例 |
|------|------|------|
| 属性 | 基本信息 | 姓名、年龄、性别 |
| 武器 | 装备武器 | 剑、法杖、弓箭 |
| 技能 | 能力技能 | 剑法、魔法、医术 |
| 性格 | 性格特征 | 勇敢、谨慎、幽默 |
| 背景 | 背景故事 | 出身、经历、目标 |

#### 核心方法

```python
manager = CharacterManager(novel_dir)

# 创建角色
character = manager.create_character(
    name="张三",
    role="主角",
    age=25,
    gender="男",
    personality="勇敢、聪明",
    background="普通大学生，意外获得传承"
)

# 获取角色
char = manager.get_character("张三")

# 更新角色
manager.update_character(
    name="张三",
    updates={"age": 26, "skills": ["剑法", "轻功"]}
)

# 删除角色
manager.delete_character("张三")

# 获取所有角色
characters = manager.get_all_characters()

# 获取主角
protagonist = manager.get_protagonist()
```

---

## 后端服务 API

### AI 模型服务

端口：8001

#### 健康检查

```http
GET /health
```

响应：
```json
{
    "status": "healthy",
    "service": "ai-model-service",
    "version": "1.0.0"
}
```

#### 聊天补全

```http
POST /v1/chat/completions
Content-Type: application/json

{
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "你是一个小说创作助手"},
        {"role": "user", "content": "帮我写一个科幻小说的大纲"}
    ],
    "temperature": 0.8,
    "max_tokens": 2000
}
```

响应：
```json
{
    "id": "chatcmpl-xxx",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "大纲内容..."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 50,
        "completion_tokens": 500,
        "total_tokens": 550
    }
}
```

### 小说生成服务

端口：8002

#### 生成章节

```http
POST /api/generate/chapter
Content-Type: application/json

{
    "novel_id": "novel_123",
    "chapter_num": 1,
    "outline": "第一章大纲...",
    "style": "热血爽文"
}
```

响应：
```json
{
    "success": true,
    "chapter": {
        "chapter_num": 1,
        "title": "第一章：觉醒",
        "content": "章节内容...",
        "word_count": 3000
    }
}
```

---

## 错误处理

### 错误响应格式

```json
{
    "error": {
        "code": "INVALID_REQUEST",
        "message": "请求参数错误",
        "details": {
            "field": "model",
            "reason": "不支持的模型类型"
        }
    }
}
```

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| `INVALID_REQUEST` | 请求参数错误 |
| `UNAUTHORIZED` | 未授权（API 密钥无效） |
| `RATE_LIMITED` | 请求频率超限 |
| `INTERNAL_ERROR` | 服务器内部错误 |
| `MODEL_NOT_FOUND` | 模型不存在 |
| `INSUFFICIENT_QUOTA` | 配额不足 |

---

## 版本历史

- **v2.14.2** (当前版本)
  - 添加安全配置模块
  - 改进记忆管理系统
  - 支持 15 种小说类型

- **v2.14.0**
  - 添加角色桥段库
  - 添加事物描写库
  - 改进风格转换引擎

- **v2.13.0**
  - 添加情景对话推演
  - 添加故事流推演
  - 改进 AI 客户端
