# 运行时审计：小说《快速统治》（2026-09-17 18:13–18:24）

> **审计对象**：`%USERPROFILE%\.ai_novel_writer\novels\快速统治_1789640077\`
> **依据**：应用导出的 UI 日志（`Desktop\AI_NovelWriter_日志_20260917_182408.log`）
> + 真实诊断日志 `diagnostic-2026-09-17.jsonl`（会话 `20260917-181335-25168`，80 条）
> + 落盘文件的结构与内容交叉核对。
>
> **一句话结论**：**本次运行的是 v3.1.0 发布版，不是本轮新构建** —— 所有新功能与
> 「候选 v3.2.0」的改进均未参与验证；同时发现 **6 处与构建版本无关的数据一致性缺陷**
> （当前 HEAD 仍在，其中 1 处会持续破坏已存数据）。

---

## 0. 首要结论：验证跑在了错误的构建上

| 判据 | 结果 | 说明 |
|---|---|---|
| 运行中的进程路径 | `Desktop\AI_NovelWriter.bak-20260917-175800.exe` | `tasklist` + `wmic` 实证，PID **25168** 与日志会话 `20260917-181335-25168` 一对一 |
| 该文件 sha256 | `7b793b80c1bcb99cf9510cdd84907cb26ce6f4d83030d2bb3d3159dcf0d39782` | 与 `docs` 记录的 **v3.1.0 发布资产完全一致**（25,934,290 B） |
| `panel_registry` 事件字段 | `['total','by_category','native','legacy','load_failures']` | **缺** `log_dir`（本轮新增字段）；对照我 17:58 的冒烟测试为 `['log_dir','total',…]` |
| `CHAPTER/ch0001/complete` | **0 条** | 本轮新增的段级耗时归因从未触发 |

**成因**：我在分发新 EXE 时，把旧文件留在桌面为
`AI_NovelWriter.bak-20260917-175800.exe`。它与正式文件只差一个后缀，**且仍可双击运行**
—— 这是**命名设计失误**，不是使用者的问题。

**连带影响**：v3.1.0 之后的全部工作都不在本次验证范围内，包括但不限于
自学习信号修复（`success` / `importance` 随评分浮动）、面板布局与停靠记忆、
以及本轮新增的段级耗时归因 + 诊断日志隔离。

> 旁证：`writing_skills/time_memory.json` 里 `type: "success_pattern"`、`importance: 0.6`
> 正是 v3.1.0 的**旧行为**（`success` 硬编码为真、权重恒 0.6）。评分 66 分的情况下
> 应当写成 `failure_pattern`。这条同时印证了"跑的是旧构建"。

---

## 1. 目录、文件与命名：结构与命名核对

```
快速统治_1789640077/
├── meta.json                     1141 B   (另有 meta.json.bak 384 B)
├── outline.json                   493 B   章节大纲（1 章）
├── outlines/overall.json         4748 B   整体大纲（8 项）
├── outlines/stories.json         2242 B   故事大纲（2 条线）
├── characters/                    4 个   陆昭·赵无咎·黎照霜·苏倾颜
├── chapters/chapter_0001.txt    31360 B  ← 4 位补零
├── summaries/                    2 个    ← 两份摘要，两种补零
├── memory/
│   ├── chapters/chapter_00001.txt 3149 B ← 5 位补零
│   ├── characters.json           8691 B  权威角色存储（+ .bak 8554 B）
│   ├── settings.json / .md       3540/3326 B
│   ├── global_summary.txt         420 B
│   ├── index.json                 135 B
│   ├── chunks/page_0000.json     3479 B
│   └── timeline/timeline_000.json 3389 B
├── timelines/main.json            355 B
├── usage/summary.json + usage.jsonl   25 次调用
├── writing_skills/knowledge_graph.json · time_memory.json
└── scene_prompts/ch0001_epic_scene_{1,2}_prompt.txt
```

### 1.1 集合对应性：✅ 正确

| 核对项 | 结果 |
|---|---|
| `characters/*.json` ↔ `memory/characters.json` | **同一 4 个角色，无缺失、无多余** |
| 章节正文 ↔ 章节摘要 ↔ 记忆章节 | 都存在，章节号 1 可对应 |
| 日志声明的产物 ↔ 实际文件 | 世界观/角色/大纲/正文/摘要/世界线/名场面/用量 **均有对应文件** |

### 1.2 命名一致性：❌ 有两套补零位数

| 位置 | 位数 | 写入点 |
|---|---|---|
| `chapters/chapter_0001.txt` | 4 位 | `app/chapter_ui.py:85` |
| `memory/chapters/chapter_00001.txt` | 5 位 | `app/memory_manager.py:372` |
| `summaries/chapter_0001_summary.txt` | **4 位** | `app/chapter_ui.py:63` |
| `summaries/chapter_00001_summary.txt` | **5 位** | `app/memory_manager.py:378` |

**`summaries/` 目录里同一章有两份文件**，因为有两个写入点用不同命名写同一逻辑内容。
`app/generation_ui.py:1950` 的"章节回顾"只读 **5 位**，因此它读到的与用户在文件管理器里
先看到的（4 位）不是同一份。

---

## 2. 与构建版本无关的缺陷（当前 HEAD 仍在）

### 🔴 D1 主角名被"整份覆盖"抹掉（最严重，会持续破坏数据）

**位置**：`app/generation_ui.py`，`_auto_generate()`

| 行号 | 代码 | 作用 |
|---|---|---|
| 1481 | `meta = self._get_meta()` | **只读一次**，此副本**不含** protagonist |
| 1537 | `self._novel_store().update_meta({"protagonist": protagonist})` | 把主角写进 `meta.json`（日志打印"主角已锁定: 陆昭"） |
| 1566 | `self._novel_store().write_meta(meta)` | **用 1481 的旧副本整份覆盖** ⇒ 主角名被抹掉 |

**铁证**（`meta.json` vs `meta.json.bak`，`atomic_write_json(..., backup=True)` 在覆盖前留档）：

```
meta.json      keys: [... , 'template']                        ← 无 protagonist
meta.json.bak  keys: [... , 'template', 'protagonist']          ← protagonist = "陆昭"
唯一差异字段：protagonist
```

**后果（两条）**：

1. **三个大纲主角各不相同** —— `_generate_overall_outline(meta, …)`（`:1591`）与
   `_generate_story_outlines(meta, …)`（`:1600`）读的是 `meta.get("protagonist", "")`
   （`:133`）。该副本不含主角 ⇒ `protagonist_hint` 为空（`:150-152`）⇒ 两个提示词
   **完全没有主角约束**：

   | 文件 | 主角 | 女主角/对手 |
   |---|---|---|
   | `outline.json`（章节大纲，走 `novel_agent` 从磁盘读） | **陆昭** | 苏倾颜 |
   | `outlines/overall.json`（整体大纲） | **苏妩** | 九州帝君 |
   | `outlines/stories.json`（故事大纲） | **沈夜** | 姜姒 |
   | `characters/`（实际角色） | **陆昭** | 苏倾颜 |

   正文最终写的是**陆昭**（83 次），说明章节大纲与角色是生效的，
   而**整体大纲与故事大纲是"孤儿数据"**——生成了、落了盘，但描述的是另一个故事。

2. **磁盘上的 protagonist 永久丢失** —— `novel_agent.py:962`（写作）、
   `:1142`（修订）、`:1373/:1414`（章节大纲重生成）都走
   `self.memory.get_meta("protagonist", "")`，即**从磁盘读**。`meta.json` 的覆盖发生在
   18:15:52，而 Writer 在 18:16:24 之后运行 —— 即 **Writer 的提示词里已经没有主角锁定了**。
   第 1 章之所以仍写对（陆昭 83 次），是因为**章节大纲 `outline.json` 本身点名了陆昭**
   （它生成于覆盖之前），Writer 是照着大纲写的。
   但从第 2 章起，章节大纲生成（`:1727`）也读不到主角 ⇒ 大纲可能不再点名
   ⇒ Writer 两个来源都失去约束，**主角漂移风险由此产生**。
   这是一个会持续恶化的数据缺陷。

> **验证方式**：删除 `meta.json` 后从 `meta.json.bak` 恢复即可看到 protagonist 回到文件里。
> **未登记**：`docs/BACKLOG_REGISTER.md` 中查无此项。

### 🔴 D2 摘要把模型的思维链原文当了摘要

**产物**：`summaries/chapter_00001_summary.txt`（1789 字符）
开头为 `第1章摘要\n\n我们需要回答用户："请生成摘要（100-200字）："…`
—— 是模型的**推理过程**（含 "Let's count…" 之类的自我计字），不是摘要。

**根因链（三处咬合）**：

| 位置 | 内容 |
|---|---|
| `app/novel_agent.py:1792-1795` | 摘要调用 `self.ai.chat(..., max_tokens=1000)`，且 **`summary = result` 直接用原始返回**，无剥离、无长度校验 |
| `app/providers/reasoning.py:27` | `THINKING_MIN_TOKENS = 1000` |
| `app/providers/reasoning.py:84` | `if thinking and req.max_tokens < THINKING_MIN_TOKENS: thinking = False` ← **严格小于** |
| `app/ai_client.py:1124` | 兜底：`finish_reason == "length"` 且 `content` 空时 **返回 `reasoning`** |

**`max_tokens=1000` 恰好等于阈值** ⇒ `1000 < 1000` 为假 ⇒ 思考模式**未被禁用**，
但预算只够思考、不够输出 ⇒ `content` 为空 ⇒ 兜底把 reasoning 当结果返回 ⇒ 落盘成摘要。

**诊断日志实证**（会话 `20260917-181335-25168`）：
```
10:22:19  API_CALL  max_tokens=1000            ← 摘要调用入口
10:22:23  API_CALL  result_len=1782  duration_ms=4500.85   ← 出口
```
落盘文件 1789 字符 = `第1章摘要\n\n`（7 字符）+ **1782** —— 完全吻合。

### 🔴 D3 同一份思维链污染了记忆库

`memory/chunks/page_0000.json` 的条目 `id: "plot_1789640553243"`, `type: "plot"`，
`content` 就是 D2 那段思维链。**类型标为 `plot`（情节）也与实际内容不符**。
后续检索会把这段推理当成剧情片段回灌。

### 🟠 D4 另一份"摘要"其实是正文截断

`summaries/chapter_0001_summary.txt`（535 字符）内容为
`章节: 第1章 … / 字数: 10654 / 摘要:` + **正文前 500 字**。

**位置**：`app/chapter_ui.py:57-65`
```python
summary_text = content[:500]          # ← 直接截正文，没有生成摘要
if len(content) > 500: summary_text += "..."
summary_content = f"章节: …\n字数: …\n\n摘要:\n{summary_text}"
```
它与 D2 的文件**同名章号、不同补零**，且都自称"摘要"。

### 🟠 D5 世界线记录的是提示词里的示例文本

`timelines/main.json`：
```json
"events":   ["第1章: 当时的情况 → 选择了「主角选择了什么」"],
"branches": [{"decision": "当时的情况", "chosen": "主角选择了什么",
              "alternative": "可能的另一种选择"}]
```
这三句话并非剧情，而是 `app/generation_ui.py:842` 提示词中的 **few-shot 示例**：
```
{"decisions": [{"desc": "当时的情况", "chosen": "主角选择了什么", "alternative": "可能的另一种选择"}]}
```
模型把示例原样当结果返回，落盘时未做"是否等于示例"的校验。
日志的「[世界线] 第1章 记录1个决策点」因此是**假成功**。

### 🟠 D6 角色数据存在两套 schema

| 角色 | schema | 字段数 | 关键字段 |
|---|---|---|---|
| 陆昭 / 赵无咎 / 黎照霜 | AI 档案 | 13 | `personality`/`background`/`appearance`/`weapon`/`goal` |
| 苏倾颜 | RPG | 28 | `level`/`exp`/`hp`/`stats`，**属性全为默认 10、`personality`/`appearance`/`backstory` 皆空** |

苏倾颜由 `[角色] 自动创建1个新角色: 苏倾颜`（18:22:59）创建，走
`CharacterSystem` 的 RPG 模板，**没有档案信息**。同一目录下两种结构混存，
读取方必须同时兼容，否则要么丢档案要么丢等级。

### 🟡 D7 知识图谱漏角色、关系为空

`writing_skills/knowledge_graph.json`：`entities` 只有 **陆昭 / 黎照霜 / 赵无咎** 3 个
（**缺苏倾颜**），且 `relations: []`、`events: []`、`attributes: {}`、
每个实体 `mentions: 1`。而 `characters/` 有 4 个角色、角色档案里明确写了
"陆昭 ↔ 赵无咎"的从属关系。该文件当前的信息量接近于空壳。

### 🟡 D8 世界观与三份大纲各说各话

- `memory/settings.json`：世界 = **玄元界**（中州/东荒/南疆/北原/西海 + 七大境界 + 共鸣双修）
- `characters/*.json`：陆昭出自**中州天枢城**、赵无咎出自**东荒**、黎照霜出自**南疆** ✅ 与设定一致
- `outline.json` + 正文：**九州 / 帝印 / 九霄宗 / 九幽魔渊** ❌ 与设定不一致
- 正文首句 `玄元界，中州。` 之后大量出现「九州」（18 次），**同一篇里混用两套地理**

---

## 3. 逐项核对：优化项是否真的被调用

| 优化 / 功能 | 是否生效 | 证据 |
|---|---|---|
| 面板框架（15 面板 / 5 分组） | ✅ | `panel_registry`：`total=15`、5 个分组、**`load_failures=[]`** |
| 多 API Provider 注册表 | ✅ | 实际走 `deepseek::chat/deepseek-flash` |
| 用量统计与持久化 | ✅ | `usage/summary.json`：25 次调用 / 134,930 tokens / `by_chapter` / `tasks=[chapter,characters,outline]`；`usage.jsonl` 25 行 |
| 角色档案生成 | ✅ | 3 个角色档案完整（各 13 字段），与 `memory/characters.json` 集合一致 |
| 章节大纲 + 主角锁定（章节层面） | ✅ | `outline.json` 主角为陆昭，正文主角 83 次命中 |
| 世界观生成 | ✅ | `settings.json` 内容完整、自洽 |
| 名场面抽取 + 提示词落盘 | ✅ | 2 个 `scene_prompts/*.txt` |
| 记忆分层（全局摘要/索引/分块/时间线） | ✅ 落盘 | 5 个文件均生成；但内容受 D2/D3 污染 |
| 擦边模式 | ✅ | `meta.concept` 含「💡 擦边内容模式 - 已启用」，与日志 `擦边:开` 一致 |
| **段级耗时归因（本轮新增）** | ❌ **未生效** | 无 `CHAPTER/ch0001/complete`；构建版本不符 |
| **诊断日志测试隔离（本轮新增）** | ⚠️ 不适用 | 该功能只作用于测试进程 |
| 自我学习·信号修复（v3.2.0） | ❌ **未生效** | `success_pattern` + `importance=0.6` = v3.1.0 旧行为 |
| 面板布局与停靠记忆（v3.2.0） | ❌ 未验证 | 构建版本不符 |
| 世界线决策点 | ⚠️ **假成功** | 日志报"记录1个决策点"，实际写入的是提示词示例（D5） |
| 角色 EXP | ⚠️ 部分 | `add_exp` 与落盘被调用；1 级时被地板钳制为 0，但 UI 仍显示「-30EXP」 |

---

## 4. 结论

1. **本次验证无效，但不是因为功能没做** —— 跑的是 v3.1.0 发布版，
   新功能根本没有机会执行。**必须先换构建再验证**，否则后续所有观察都不可信。
2. **落盘结构整体是健康的**：集合一一对应、无缺失无多余、时间线与生成顺序完全吻合。
3. **但内容层面有 6 处真实缺陷**，其中 **D1（主角名被覆盖）会持续破坏数据**，
   **D2/D3（思维链当摘要并污染记忆）会让后续章节"越写越偏"**。
   这两条与构建版本无关，**当前 HEAD 仍在**。
4. **D5 暴露了一类共性风险**：把提示词里的 few-shot 示例当结果落盘，
   且日志报"成功"。同类写法值得全仓排查。

---

## 5. 后续处理建议（按优先级）

| 优先级 | 动作 | 具体位置 |
|---|---|---|
| **P0** | 修正桌面备份文件的命名，改用**不可双击执行**的形式（如 `AI_NovelWriter.exe.old-<时间戳>`），并在分发脚本里固化 | 分发流程（本轮用的是临时脚本） |
| **P0** | 关闭旧实例，改用 `Desktop\AI_NovelWriter.exe`（sha `e82520f2…`）重新验证 | — |
| **P0** | 修 D1：把 `:1566` 的 `write_meta(meta)` 改为 `update_meta({"chapter_count": outline_count})`，并让 `_generate_overall_outline` / `_generate_story_outlines` 从**磁盘**取 protagonist | `app/generation_ui.py:1481/1566/1591/1600` |
| **P1** | 修 D2：摘要调用把 `max_tokens` 提到阈值以上（如 2000）；并对"返回内容像思维链"做校验（长度上限 + 特征词） | `app/novel_agent.py:1795`；可考虑把 `reasoning.py:84` 的 `<` 改为 `<=` |
| **P1** | 修 D4：删除 `chapter_ui._save_chapter_summary` 的"截正文"实现，统一改调 `memory.save_chapter_summary`（顺带解决命名不一致 D-命名） | `app/chapter_ui.py:47-69` |
| **P1** | 修 D5：解析 `decisions` 后过滤掉与提示词示例完全相同的项；日志区分"记录成功/记录到示例" | `app/generation_ui.py:842` 附近 |
| **P2** | 统一章节/摘要补零位数为 5 位（`04d` → `05d`），并加一条"同一章只允许一份摘要"的门禁 | `chapter_ui.py:63/85`、`generation_ui.py:1950`、`timeline_ui.py:747` |
| **P2** | 自动创建的角色补齐档案字段（或统一到一种 schema） | 角色自动创建路径 |
| **P2** | 知识图谱抽取覆盖全部角色，并落 `relations` | `writing_skills` 落盘路径 |
| **P3** | 大纲/正文统一世界观：既然设定是「玄元界」，章节大纲不应产出"九州" | 章节大纲提示词 |
| **P3** | 1 级角色的负向 EXP 提示改为"已到下限"，避免报「-30EXP」却无变化 | `app/generation_ui.py:1175` |

> **建议顺序**：先做 P0 的第 1、2 条（换构建重新验证）—— 因为
> 目前无法区分"新功能没生效"与"新功能有 bug"。换构建后 D1/D2 仍可复现，
> 说明它们是独立的真实缺陷，与构建无关。
