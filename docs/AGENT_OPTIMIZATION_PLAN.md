# AI Agent 全面优化方案（Harness 对齐 · 自我学习强化）

> 版本基准：`v3.1.0` / HEAD `f6caafa` · 编制日期：2026-09-17
> 关联文档：`docs/ROADMAP_V3_PANELS_AND_PROVIDERS.md`、`docs/NEXT_STEPS.md`、`docs/RELEASE_HISTORY_NOTES.md`
>
> **本文所有问题点均基于代码实测**，每一条标注了 `文件:行号` 或可复现的检索命令。
> 未实测的推测一律不写入。

---

## 一、优化目标、适用范围与约束条件

### 1.1 优化目标

| 编号 | 目标 | 可验收的终态 |
|---|---|---|
| G1 | **让"Agent"名实相符** | 5 个角色全部真实调用 LLM；工具系统被主流程实际调用；README 宣称与代码一致 |
| G2 | **对齐 Harness 六支柱** | 验证/停止/状态/恢复/隔离/可观测 六项各有对应实现且可测试 |
| G3 | **把自我学习从"只写不读"改为闭环** | 学习产物进入下一章生成上下文，且改动可回滚、可量化 |
| G4 | **参数与提示词可版本化** | 提示词与阈值脱离硬编码，支持 A/B 与回滚 |
| G5 | **建立可复现的评估基线** | 有固定评测集与指标，任何"改进"都能用数字证明不是退步 |

**G3 是本轮的核心**——用户明确指出"现有自我学习功能表现不足"，实测证实其**结构性失效**（见 §2.5）。

### 1.2 适用范围

**纳入范围（桌面端主线）**：

| 模块 | 文件 | 行数 |
|---|---|---|
| 智能体协作 | `app/novel_agent.py` | 2201 |
| 编排 | `app/agent_orchestrator.py` | 128 |
| 技能与自我学习 | `app/writing_skills.py` / `writing_skills_panel.py` | 785 / 250 |
| 工具引擎 | `app/novel_toolkit.py` | 1273 |
| 模型接入 | `app/ai_client.py` + `app/providers/` | 1394 + 9 文件 |
| 可观测 | `app/diagnostic_logger.py` | 353 |
| 检查点/恢复 | `app/persistence_ui.py`（相关部分） | — |
| 上下文压缩 | `app/token_estimator.py` | — |

**明确不纳入**：
- `backend/`（ai-service / novel-service）—— 已冻结，只接缺陷与安全补丁
- `mobile-app/novel-app`（Compose）—— 与本次 Agent 改造无交集
- `frontend-react` —— 仅 2 处 fetch 调用后端，非 Agent 链路
- `app/panels/` 的 15 个面板 UI —— 除 G2/可观测需要的 1 个新面板外不动

### 1.3 约束条件

| 类型 | 约束 | 来源 |
|---|---|---|
| **兼容** | `AIClient.chat()` / `chat_stream()` 签名与异常语义不变 | `ai_client.py:426` 注释明示"53 个调用点无需改动，这是硬约束" |
| **数据** | 已有角色名不可删除；角色档案只走 `mutate_characters` | 项目硬约束，`memory_manager` 三道防线 |
| **世代** | `lineage.guard_child_path` 是"子代只读父代"唯一强制点，不可绕过 | 有测试用父代全量哈希断言 |
| **测试** | 不得让影子目录排到仓库根之前（三个 `app` 包问题） | `tests/_app_authority.py` 有断言 |
| **发布** | 版本号只改 `pyproject.toml` + `app/__init__._FALLBACK_VERSION` 两处 | `tests/test_version_consistency.py` 16 条门禁 |
| **文字** | 全仓提示词不得再有硬编码字面量（迁移后需棘轮门禁） | 沿用字体令牌迁移的既有方法论 |
| **界面** | 面板不得直调 `messagebox`；需走 `app/dialogs.py` | `tests/test_dialogs.py` 门禁 |
| **环境** | 本沙箱 safe-delete 阈值 50 路径 / `scope=turn` ⇒ 测试须拆小块、越早跑越好 | `shim/sitecustomize.py` 实测 |
| **依赖** | 不引入重量级新依赖（`chromadb` 已在可选 extra，不默认启用） | 保持 EXE 体积与 CI 时长 |
| **冻结** | 后端与移动端不因本方案改动 | 项目章程 |

---

## 二、当前主要问题（按维度分类，含影响程度与优先级）

### 2.0 问题总览

| ID | 维度 | 问题 | 影响 | 优先级 |
|---|---|---|---|---|
| P-01 | 正确性 | WorldBuilder 仅 11 行、不调 AI | 高 | **P0** |
| P-02 | 正确性 | Editor 无独立实现，且忽略 AI 的 `is_acceptable` | 高 | **P0** |
| P-03 | 正确性 | `add_relation` 生产零调用 ⇒ 知识图谱关系恒空 | 高 | **P0** |
| P-04 | 正确性 | 学习写入 `success=True` 硬编码，且只记对话比例 | 高 | **P0** |
| P-05 | 正确性 | `PromptManager` 274 行提示词完全未被使用 | 中高 | P1 |
| P-06 | 性能 | `run_parallel` 死代码，协作流程串行 | 中高 | P1 |
| P-07 | 性能 | Reviewer 只采样 4000 字，长章后半段失检 | 中 | P1 |
| P-08 | 性能 | `_get_unresolved_plots` 每次重建句子列表 | 低 | P3 |
| P-09 | 可读性 | `novel_agent.py` 单文件 2201 行 / 74 个提示词块 | 中高 | P1 |
| P-10 | 可读性 | 提示词内联在方法体，无法独立审阅 | 中 | P1 |
| P-11 | 可读性 | `cache_prefix` 变量名掩盖了"这是 system prompt" | 低 | P3 |
| P-12 | 可维护性 | 阈值/轮次硬编码为类常量，无法按作品调节 | 中高 | P1 |
| P-13 | 可维护性 | 工具注册 7 个、实际调用 1 个且是桩 | 高 | **P0** |
| P-14 | 可维护性 | `ToolRegistry` 无调用审计，无法发现"注册即遗忘" | 中高 | P1 |
| P-15 | 可维护性 | 知识图谱被 `min(500, ...)` 预算截断 | 中 | P2 |
| P-16 | 可维护性 | `_conversation_log` / `_revision_memory` 无外部读取面 | 中高 | P1 |
| P-17 | 正确性 | 无向量检索，"RAG" 实为关键词倒排 | 中 | P2 |
| P-18 | 正确性 | `chat_stream` 在 `app/` 内零调用 | 中 | P2 |
| P-19 | 可维护性 | 无质量回归门禁，"改进"无法证伪 | 高 | **P0** |
| P-20 | 正确性 | 自我学习无回滚机制，写入即生效 | 高 | **P0** |

### 2.1 正确性（Correctness）

**P-01｜WorldBuilder 是空壳 —— 影响：高 ｜ 优先级：P0**

- 证据：`app/novel_agent.py:786-797`，方法体 **11 行**，只读 `settings["world"]["已知区域"][:3]` 拼字符串，**全程不调用 `self.ai.chat()`**。
- 后果：五角色流程中，第 2 个角色对生成质量的贡献恒定为常数（最多拼出 `"世界观场景: A, B, C"`）。README `:37` 宣称的"5 Agent 协作"实际是 **3 个真 Agent + 1 个字符串拼接 + 1 个 if 判断**。
- 影响面：所有走协作流程的章节生成。

**P-02｜Editor 无独立实现，且丢掉了 AI 的判断 —— 影响：高 ｜ 优先级：P0**

- 证据：`novel_agent.py:703` `if review.get("overall_score", 0) >= self.QUALITY_THRESHOLD:`；全仓无 `_editor_judge` 之类函数（`grep -n "def _editor"` 零命中）。
- 同时：`Reviewer` 的 JSON schema 明确要求返回 `is_acceptable`（`novel_agent.py:951`，仅出现在提示词的 schema 字符串里），但**该字段从未被读取**——裁定只看 `overall_score`。
- 后果：① "Editor" 不是 Agent，只是阈值比较；② AI 已经给出的接受/拒绝判断被丢弃，"AI 说了不算"；③ 无法实现"评分够但 AI 明确认为不可接受"这类真实场景。
- 影响面：全部质量闸门。

**P-03｜知识图谱关系/事件写入零调用 —— 影响：高 ｜ 优先级：P0**

- 证据（关键）：
  ```
  add_relation  调用点 9 处，全部在 tests/test_writing_skills_deep.py
  add_event(kg) 无生产调用
  ```
  即 `KnowledgeGraph.add_relation()` 与 `add_event()` **实现完整、有单测、但生产代码从不调用**。
- 直接后果：`get_character_relations()` 恒返回空 ⇒ `to_context_string(character)` 里"【X 的关系】"段落**永远不出现**。
- 根因：`learn_from_chapter`（`writing_skills.py:691-728`）只做 `add_entity` + `mentions += 1`，从不抽取关系与事件。
- 影响面：所有"角色关系"相关的上下文供给。

**P-04｜学习信号是假的 —— 影响：高 ｜ 优先级：P0**

- 证据：`novel_agent.py:1696` 唯一生产调用点为
  `learn_from_chapter(content, chapter_num, chars, success=True, novel_dir=novel_dir)`
  —— **`success=True` 是硬编码常量**。
- 而 `learn_from_chapter` 内部 `if success:` 包住全部学习逻辑（`writing_skills.py:696`）⇒ 这个形参是**永远为真的开关**，等于没有。
- 同时学习内容极贫：只记录一句 `f"第{n}章成功生成，对话比例{x:.1%}"`。而此刻流程**已经知道**审校分数、修订轮次、命中的问题列表、AI 痕迹数量——这些高价值信号**全部被丢弃**。
- 影响面：整个自我学习能力。

**P-05｜274 行提示词全面闲置 —— 影响：中高 ｜ 优先级：P1**

- 证据：`ai_client.py:150-430` 的 `PromptManager.NOVEL_PROMPTS`（274 行、8 个条目、含大量专业网文写作理论），全仓检索 `PromptManager` **只有类定义 1 处命中**，`get_prompt` 零调用。
- 同时 `novel_agent.py` 有 **74 个三引号块**（内联提示词），Writer/Reviewer 的提示词各约 50 行硬编码在方法体内（`novel_agent.py:822-868`、`:909-945`）。
- 后果："一份信息写两处"——而且**旧的那份（更专业的）完全没被用**。

**P-17｜无向量检索 —— 影响：中 ｜ 优先级：P2**

- 证据：`grep -rn "embedding|向量|vector" app/` **零命中**。`memory_manager.retrieve_relevant()`（`:490`）用倒排索引 + 关键词集交集。
- 附加缺陷：调用处（`novel_agent.py:430`）只传 `extra_context`（上一章正文/大纲），**不含本章 `chapter_outline`** ⇒ 大纲短时召回质量差。

**P-18｜流式能力闲置 —— 影响：中 ｜ 优先级：P2**

- 证据：`grep -rn "chat_stream" --include=*.py app/` 只命中 `ai_client.py` 的定义与 `providers/base.py` 的文档注释；**生产零调用**。
- 后果：长章节生成时用户只能等，无法看到流式输出。

**P-20｜学习产物无回滚 —— 影响：高 ｜ 优先级：P0**

- 证据：`learn_from_chapter` 直接 `knowledge_graph.save()` / `time_memory.save()` 覆盖式写入（`writing_skills.py:720-727`），无版本、无备份、无校验。
- 后果：一旦学习写出坏数据（如错误关系），**无法回退**；与项目在角色数据上建立的三道防线（`.bak` 轮转 + `validate=True`）形成鲜明反差。
- 这正是 Harness 综述点名的 **"奖励黑客"** 风险面：信号一旦被优化，污染会持久化。

### 2.2 性能（Performance）

**P-06｜并行编排是死代码 —— 影响：中高 ｜ 优先级：P1**

- 证据：`grep -rn "run_parallel"` 全仓 16 处命中**全部在 `tests/`**。`AgentOrchestrator.__init__` 建的 `ThreadPoolExecutor(max_workers=3)` 从不执行任何任务。
- 后果：协作流程 `generate_with_collaboration`（`novel_agent.py:683`）是**串行 `for round_num`**。PlotDesigner 与 WorldBuilder 之间**无数据依赖**（P-01 证实 WorldBuilder 只读 settings），却顺序执行。

**P-07｜Reviewer 采样盲区 —— 影响：中 ｜ 优先级：P1**

- 证据：`novel_agent.py:957-966`，`len(content) > 4000` 时只取"开头 2000 + 中间 1000 + 结尾 1000"。
- 后果：5000 字章节有约 20% 内容不被审校；8000 字章节接近 50% 失检。若 `_generate_long_chapter` 产出万字体量，盲区更大。

**P-08｜伏笔抽取每次重建 —— 影响：低 ｜ 优先级：P3**

- 证据：`novel_agent.py:547-560`，对 14 个关键词各做一次全文 `gs.replace()` 构造句表（最多 14 次全串扫描）。
- 后果：单次开销小，但它在 `_build_context` 内、每章每轮修订都调用。

### 2.3 可读性（Readability）

**P-09｜单文件 2201 行 —— 影响：中高 ｜ 优先级：P1**

- 证据：`wc -l app/novel_agent.py` = 2201。含 `NovelAgent` 一个类约 30 个方法，横跨"协作流程 / 上下文工程 / 压缩 / 设定生成 / 角色生成 / 大纲 / 定稿 / 风格 / 长章" 九个职能。
- 对照：项目此前已完成 `novel_app.py` 巨石拆分（P2-1），`app/*_ui.py` 分域 Mixin 是既有范式——**`novel_agent.py` 是唯一未拆的大文件**。

**P-10｜提示词内联不可审阅 —— 影响：中 ｜ 优先级：P1**

- 证据：`novel_agent.py` 74 个三引号块，Writer 的 `cache_prefix`（`:822-868`）约 47 行、Reviewer 的（`:909-945`）约 37 行，均嵌在方法体里。
- 后果：改提示词要读方法逻辑；无法 diff / 无法 A/B / 无法回滚；与 P-05 叠加成"提示词散落三处"。

**P-11｜`cache_prefix` 变量名误导 —— 影响：低 ｜ 优先级：P3**

- 证据：`novel_agent.py:822` `cache_prefix = f"""你是一位专业的小说作家（Writer Agent）...`，随后 `system = cache_prefix + "\n\n" + dynamic_context`。
- 命名突出"缓存优化"这个实现细节，掩盖了"这是 system prompt 主体"的语义。

### 2.4 可维护性（Maintainability）

**P-12｜关键参数不可配置 —— 影响：中高 ｜ 优先级：P1**

- 证据：`novel_agent.py:150-151` `QUALITY_THRESHOLD = 75` / `MAX_REVISION_ROUNDS = 3`（类常量）；`agent_orchestrator.py:69-77` `MAX_CONTEXT_CHARS = 8000` + `COMPRESSION_RATIOS`（类常量）。
- 后果：不同题材/篇幅对质量阈值与修订轮次的合理值不同（短篇与 100 万字长篇、快节奏爽文与慢热文学），但用户**无法调节**；也无法依数据调优。

**P-13｜工具系统注册即遗忘 —— 影响：高 ｜ 优先级：P0**

- 证据：`_register_tools`（`novel_agent.py:234-293`）注册 **7 个**工具；`grep "self.tools"` 全仓只有 `:183`（构造）、`:236-287`（注册）、**`:689`（唯一一次 `call`）**。
- 且 `:689` 调用的 `check_consistency`，其 lambda 是 `f"一致性检查完成, 内容长度:{len(content)}"` —— **纯桩，返回值被丢弃**（`novel_agent.py:250`）。
- 更关键：`list_tools()` 在**生产代码零调用**（仅 4 处测试调用：`test_novel_agent_coverage.py:783`、`test_novel_agent_full.py:206`、`test_novel_agent_deep.py:126/132/140`）⇒ LLM 从未被告知可用工具 ⇒ **"Agent 自主选择工具"这一层根本不存在**。
- 影响：`detect_scenes` / `generate_summary` / `get_characters` / `get_outline` / `check_ai_slop` / `get_kg_context` 六个工具，注册后无人使用（后两者是"先有函数、后包一层 Tool"的包装）。

**P-14｜无调用审计 —— 影响：中高 ｜ 优先级：P1**

- 现状：`ToolRegistry.call` 失败时返回 `{"success": False, ...}`（`:124-128`），但**调用方不检查返回值**（`:689`），且无任何计数/日志。
- 后果：P-13 这类"注册即遗忘"缺陷**可以静默存在很久**——没有机制会发现它。这正是本轮评估要靠人工 grep 才能发现的原因。

**P-15｜知识图谱被截到 500 字 —— 影响：中 ｜ 优先级：P2**

- 证据：`novel_agent.py:443-453`，`skill_budget = max(0, min(500, max_chars - used))`。
- 后果：`max_chars` 通常约 10000（`chars_for_context_window`），角色/前文动辄数千字预算，而**唯一承载"跨章结构化知识"的图谱只有 500 字**——投入产出严重失衡。

**P-16｜协作过程不可观测 —— 影响：中高 ｜ 优先级：P1**

- 证据：`_conversation_log`（`:160`）与 `_revision_memory`（`:163`）只在类内 `append`；全仓 `grep` 无外部读取点；`AgentMessage.to_dict()` **零调用**。
- 后果：用户看不到"哪个 Agent 判了不过、理由是什么、改了什么"。唯一的可见面是 `self.log()` 文本流。协作系统的**调试与信任成本**因此极高。

**P-19｜无质量回归门禁 —— 影响：高 ｜ 优先级：P0**

- 证据：现有 2376 条测试**全部是"代码正确性"测试**（函数输入输出、边界、异常），**没有一条"生成质量"测试**。
- 后果：任何对提示词、阈值、上下文的改动，**无法证明是改进还是退步**。这正是 Harness 综述点名的首要瓶颈——**"弱且模糊的评估器"**。没有它，G3（自我学习闭环）和"自我进化"都无从谈起，因为**进化的方向无法被验证**。

### 2.5 自我学习能力的专项诊断（用户重点关注）

**现状实测**：三个组件构成 `WritingSkillManager`，调用面如下：

| 组件 | 设计意图 | 实际状态 |
|---|---|---|
| `AntiSlopProcessor` | 检测 AI 写作痕迹 | ✅ **真实工作**（47 行规则 + 编译正则），已接入协作流程扣分 |
| `TimeAwareMemory` | 时间感知的长期记忆 | ⚠️ **只写不读**：`add_memory` 生产仅 `learn_from_chapter` 1 处；`get_context_string` 仅被 `get_writing_context` 调用，而后者只进 500 字预算段 |
| `KnowledgeGraph` | 角色/关系/事件图谱 | ❌ **半残**：只有实体表（`add_entity`），关系与事件恒空（P-03） |

**闭环断裂的三处断点**：

```
【断点 1】学习信号 → 假
  finalize_chapter 里 success=True 硬编码（novel_agent.py:1696）
  ⇒ 失败章节与成功章节学习结果完全相同
  ⇒ 实际上"审校分数/修订轮次/问题列表"这些真信号在此刻全部可用，却未传入

【断点 2】学习内容 → 贫
  只记录"第N章成功生成，对话比例 x%"
  ⇒ 不记录：哪些问题反复出现、哪些建议被采纳后分数提升、哪些 AI 痕迹最常犯
  ⇒ 学不到任何"可操作的改进"

【断点 3】学习产物 → 读不到
  产物仅经 get_writing_context() 进入 500 字预算段（P-15）
  且 KnowledgeGraph 关系恒空、TimeAwareMemory 的 query 结果无差异化消费
  ⇒ 学到的东西对下一章生成几乎无影响
```

**结论**：当前"自我学习"的实际能力等级是 **L0（记录行为）**，而非其自称的 L5。它做了"写日志"的动作，但**没有"改变行为"的效果**——按 Harness 综述的定义（"能够自主将运行经验转化为能力增强"），**尚不构成自我学习**。

---

## 三、优化方案、修改要点与思路说明

### 3.1 P0 组 —— 正确性与闭环修复（必须先做）

#### 方案 P-01：WorldBuilder 接入 LLM

**修改要点**：`app/novel_agent.py:786-797`

```python
# 改造前（11 行，无 AI）
def _world_builder_build(self, chapter_num, plot_analysis):
    settings = self.memory.get_settings()
    if settings and isinstance(settings, dict):
        world = settings.get("world", {})
        if isinstance(world, dict):
            known = world.get("已知区域", [])[:3]
            if known:
                return f"世界观场景: {', '.join(known)}"
    return ""

# 改造后（真 Agent：检索设定 + LLM 生成场景指导）
def _world_builder_build(self, chapter_num, plot_analysis, outline=""):
    settings = self.memory.get_settings() or {}
    world = settings.get("world", {}) if isinstance(settings, dict) else {}
    scene_hint = plot_analysis.get("scene") or plot_analysis.get("type", "")
    prompt = f"""第{chapter_num}章场景构建。
已知区域: {', '.join(world.get('已知区域', [])[:8]) or '未设定'}
势力: {', '.join(world.get('factions', [])[:5]) or '未设定'}
规则: {self._compress_settings(world.get('rules', {}), 600)}
本章大纲: {outline[:400]}
输出要求（80-150字，直接给写作指导，不要复述设定）：
1. 本章场景应落在哪个已知区域（不得新造地名）
2. 该区域的氛围与感官细节要点
3. 与本章情节相关的世界观约束（规则/势力立场）"""
    try:
        return self.ai.chat([{"role": "user", "content": prompt}],
                            system="你是世界观架构师，负责确保场景与既有设定完全一致。",
                            max_tokens=500) or ""
    except Exception as e:
        self.log(f"[WorldBuilder] 构建失败: {e}")
        return ""
```

**思路说明**：三个要点——① **沿用 PlotDesigner 的既有模式**（同构、同错误处理风格），降低认知成本；② 提示词**显式禁止新造地名**，与 Writer 提示词里"禁止无故引入新角色"的既有约束同源；③ `except` 返回空串**保持降级能力**（WorldBuilder 失败不应阻断生成），与现有 `_build_context` 的容错哲学一致。
**顺带修复**：WorldBuilder 输出已在 `:673-675` 注入 Writer 上下文（BUG-1 修复过），接上 AI 后该通路才真正有意义。

#### 方案 P-02：Editor 独立化 + 采纳 `is_acceptable`

**修改要点**：新增 `_editor_judge()`，替换 `:703` 的单行比较。

```python
def _editor_judge(self, review: dict, round_num: int) -> Dict:
    """Editor：综合裁定。分数达标是必要条件，非充分条件。"""
    score = review.get("overall_score", 0)
    acceptable = review.get("is_acceptable", True)     # ← AI 的判断终于被采纳
    issues = review.get("issues", []) or []
    blocking = [i for i in issues if isinstance(i, str) and
                any(k in i for k in ("矛盾", "逻辑", "崩坏", "断裂", "重复"))]

    # 裁定规则（显式、可测、可配置）
    score_ok = score >= self.threshold
    passed = bool(score_ok and acceptable and not blocking)
    reason = ("质量达标" if passed else
              f"分数{score}<{self.threshold}" if not score_ok else
              "AI 判定不可接受" if not acceptable else
              f"存在阻断性问题{len(blocking)}项")
    return {"passed": passed, "score": score, "blocking": blocking,
            "round": round_num, "reason": reason}
```

调用处（`novel_agent.py:683-730`）改为：

```python
verdict = self._editor_judge(review, round_num)
self._record_conversation("Editor", "judge", verdict["reason"])
if verdict["passed"]:
    self.log(f"[Editor] ✅ 通过：{verdict['reason']}")
    break
```

**思路说明**：① 把"阈值 + AI 判断 + 阻断性关键词"三层合成一个显式判决，`reason` 可读可记；② **保留 `score` 作为必要条件**，不推翻既有行为，只**补上被忽略的维度**——风险最低的改法；③ 返回值结构化，直接成为 P-16 观测面板与 P-19 评测的数据源。

#### 方案 P-03：补全知识图谱写入

**修改要点**：在 `finalize_chapter` 中新增关系与事件抽取（一次 LLM 调用，复用既有 JSON 解析）。

```python
# novel_agent.py finalize_chapter 内，_update_character_progression 之后
def _extract_relations(self, chapter_num: int, content: str, chars: List[str]) -> None:
    """从本章抽取角色关系与关键事件，写入知识图谱。"""
    if not chars:
        return
    prompt = f"""分析以下章节，抽取角色关系与关键事件。
本章出场角色: {'、'.join(chars[:15])}

输出 JSON（只输出 JSON）：
{{
  "relations": [{{"a": "角色甲", "b": "角色乙", "type": "师徒/敌对/恋人/盟友/亲属", "detail": "20字内"}}],
  "events": [{{"type": "战斗/结盟/背叛/突破/死亡", "desc": "30字内", "participants": ["角色甲"]}}]
}}
规则：只报告本章**新出现或发生实质变化**的关系；无变化则给空数组。"""
    try:
        raw = self.ai.chat([{"role": "user", "content": prompt}],
                           system="你是角色关系抽取器，只输出JSON。", max_tokens=1500)
        data = parse_json_response(raw or "{}", {"relations": [], "events": []})
        kg = writing_skill_manager.knowledge_graph
        for rel in data.get("relations", [])[:20]:
            a, b, t = rel.get("a"), rel.get("b"), rel.get("type")
            if a and b and t:
                kg.add_relation(a, b, t, rel.get("detail", ""))
        for ev in data.get("events", [])[:20]:
            kg.add_event(ev.get("type", "plot"), ev.get("desc", ""),
                         ev.get("participants", []), chapter_num)
    except Exception as e:
        self.log(f"[知识图谱] 关系抽取失败: {e}")
```

**思路说明**：① **只在定稿时调用**（每章 1 次），不进入生成循环，成本可控；② 提示词强调"只报告新变化"，避免每章重复灌入同一批关系导致图谱膨胀；③ 复用 `parsing.parse_json_response`（项目唯一 JSON 解析实现，`parsing.py:449` 注释已声明"本函数是唯一实现"），不新增解析逻辑。

#### 方案 P-04：让学习信号为真

**修改要点**：把 `finalize_chapter` 已知的真实信号传进去。

```python
# 调用处（novel_agent.py:1696）：传入真实信号
writing_skill_manager.learn_from_chapter(
    content=content,
    chapter_num=chapter_num,
    characters=chars,
    success=self._last_quality_score >= self.threshold,   # ← 真信号
    quality_score=self._last_quality_score,
    revision_rounds=self._last_revision_rounds,
    issues=self._last_review_issues,
    slop_count=self._last_slop_count,
    novel_dir=novel_dir,
)
```

```python
# writing_skills.py learn_from_chapter 改造：失败也学习
def learn_from_chapter(self, content, chapter_num, characters, success=True,
                       quality_score=None, revision_rounds=0, issues=None,
                       slop_count=0, novel_dir=None):
    """从章节学习。**失败样本同样有价值**——记录"什么做法导致低分"。"""
    record = {
        "chapter": chapter_num,
        "success": bool(success),
        "quality": quality_score,
        "rounds": revision_rounds,
        "issues": (issues or [])[:5],
        "slop": slop_count,
        "dialogue_ratio": self._dialogue_ratio(content),
        "length": len(content),
    }
    self.time_memory.add_memory(
        content=json.dumps(record, ensure_ascii=False),
        memory_type="success_pattern" if success else "failure_pattern",
        importance=0.6 if success else 0.8,     # 失败样本更重要（Harness：负面结果最有价值）
        chapter=chapter_num,
        tags=["success" if success else "failure", "dialogue"],
    )
    # 关系与事件在图谱侧由 novel_agent 负责（P-03），此处只维护实体
    for char in characters:
        entity = self.knowledge_graph.entities.get(char)
        if entity is None:
            self.knowledge_graph.add_entity(char, "character")
        else:
            entity["mentions"] = entity.get("mentions", 0) + 1
    ...
```

**思路说明**：① **`success` 从形参变成真值**，修复 P-04 的假开关；② **失败样本重要性加权到 0.8 > 成功的 0.6** —— 呼应 Harness 综述明确指出的"负面结果是最佳搜索空间缩小手段"；③ 结构化 JSON 入记忆，为后续消费（P-04b）与统计（P-19）提供可解析的数据形态，而非散文。

#### 方案 P-04b：把学到的"问题模式"回灌到下一章

**修改要点**：新增 `get_learned_constraints()`，注入 Writer 的 system prompt。

```python
# writing_skills.py
def get_learned_constraints(self, limit: int = 3) -> str:
    """从历史失败样本中提炼反复出现的问题，转成"本章禁止"清单。"""
    failures = [m for m in self.time_memory.memories
                if m.get("memory_type") == "failure_pattern"]
    if not failures:
        return ""
    counter = Counter()
    for f in failures[-50:]:                      # 最近 50 章
        for issue in (f.get("issues") or [])[:5]:
            counter[issue.strip()[:30]] += 1
    top = [i for i, n in counter.most_common(limit) if n >= 2]   # 只保留复现 ≥2 次的
    if not top:
        return ""
    return "【本章特别禁止 — 源自近期反复出现的问题】\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(top))
```

注入点（`novel_agent.py:_writer_generate`，追加到 `cache_prefix` **之后**的 `dynamic_context` —— 因为它每章不同，不能进缓存前缀）：

```python
learned = writing_skill_manager.get_learned_constraints()
if learned:
    dynamic_context += f"\n\n{learned}"
```

**思路说明**：这是**闭环的关键一环**——学到的内容**必须改变下一次生成**，否则仍属 L0。三个设计取舍：① 阈值 `n >= 2` 只保留**复现**的问题，避免单次偶发噪音污染；② 取最近 50 章，让约束随时间自然漂移（老问题被解决后自动退出）；③ 放进 `dynamic_context` 而非 `cache_prefix`，**不破坏 DeepSeek 的缓存前缀命中**（`novel_agent.py:810-816` 注释已说明缓存优化策略）。

#### 方案 P-13/P-14：工具系统激活 + 调用审计

**修改要点**：两步走。

**第一步：把真工具接进流程，并为每个工具补审计。**

```python
# novel_agent.py 新增
def _call_tool(self, name: str, **kwargs) -> Any:
    """统一工具调用入口：审计 + 失败不阻断 + 返回值可用。"""
    result = self.tools.call(name, **kwargs)
    self._tool_audit.append({"tool": name, "ok": result.get("success"),
                             "chapter": kwargs.get("chapter_num"),
                             "ts": time.time()})
    if not result.get("success"):
        self.log(f"[工具] {name} 调用失败: {result.get('error')}")
    return result.get("result")
```

接入点（替换纯桩 lambda）：

| 工具 | 接入位置 | 用途 |
|---|---|---|
| `get_kg_context` | `_writer_generate` | 取本章角色关系上下文，替代恒空的关系段 |
| `check_ai_slop` | 已在协作流程 | 保留（但改为经 `_call_tool` 走审计） |
| `detect_scenes` | `finalize_chapter` | 名场面写入事件（替代只写一句摘要） |
| `get_outline` | `_plot_designer_analyze` | 大纲兜底（当前只吃入参） |
| `check_consistency` | 改为真实实现 | 见下方第二步 |

**第二步：`check_consistency` 从桩变真。**

```python
def _check_consistency_real(self, content: str, chapter_num: int) -> str:
    """真一致性检查：与角色库和前章摘要交叉核对。"""
    chars = self.memory.get_characters()
    alive = [n for n, i in chars.items() if isinstance(i, dict) and i.get("status") != "deceased"]
    recent = self.memory.get_recent_summaries(2)
    prompt = f"""检查以下章节与既有设定是否矛盾。
【在世角色】{'、'.join(alive[:20])}
【前情摘要】{recent[:1200]}
【本章内容】{content[:3000]}
输出 JSON: {{"consistent": true/false, "conflicts": ["矛盾点"], "missing_characters": ["应出现却缺席的角色"]}}"""
    ...
```

**思路说明**：① `_call_tool` 作为**唯一入口**，让审计成为不变量而非纪律——直接回应 P-14"缺陷可静默存在"；② 每个工具都绑定到**具体流程位置**，避免再次出现"注册即遗忘"；③ `list_tools()` 仍不接给 LLM（**有意为之**）——当前架构是固定流水线，让 LLM 自由选工具需要 ReAct 循环，属 §3.4 的渐进目标，**本轮不做**。

#### 方案 P-19：建立质量评测基线（Harness「验证」支柱）

**修改要点**：新建 `tests/quality/` 目录，含固定评测集与指标计算。

**结构**：
```
tests/quality/
├── corpus/                      # 固定评测输入（不可随意改）
│   ├── outlines_short.json      # 短篇大纲 10 条
│   ├── outlines_long.json       # 长篇大纲 10 条
│   └── characters_basic.json    # 角色设定 5 组
├── metrics.py                   # 指标实现（纯函数，可单测）
└── test_quality_baseline.py     # 门禁（默认 skip，需显式 --run-quality）
```

**指标定义**（全部**可离线计算、无需人工评分**）：

| 指标 | 计算方式 | 基线目标 |
|---|---|---|
| `slop_density` | `AntiSlopProcessor` 命中数 / 千字 | 不高于基线 |
| `word_count_accuracy` | `len(content) / target_words` | 0.9 - 1.15 |
| `repetition_ratio` | 相邻段落相似度 > 0.8 的对数 / 总对数 | 不高于基线 |
| `character_consistency` | 文中出现的角色名 ∈ 角色库的比例 | ≥ 0.95 |
| `revision_efficiency` | 平均修订轮次 | 不高于基线 |
| `kg_coverage` | 有关系的角色数 / 总角色数 | ≥ 0.5（P-03 后应显著上升） |
| `pass_rate` | 首轮通过率 | 上升 |

**门禁实现**：
```python
# tests/quality/test_quality_baseline.py
BASELINE = json.loads((Path(__file__).parent / "baseline_v1.json").read_text("utf-8"))

@pytest.mark.skipif(not os.getenv("RUN_QUALITY"), reason="需要真实 API，默认跳过")
def test_quality_no_regression():
    scores = run_corpus()            # 跑固定评测集
    for key, base in BASELINE.items():
        assert scores[key] >= base * 0.95, f"{key} 退步: {scores[key]} < {base}"
```

**思路说明**：① **默认 skip** —— CI 无 API Key，不阻断 PR；用环境变量显式开启，与 `scripts/smoke_generators.py` 的"非 pytest 烟测"定位互补；② 指标**全部离线可算**，不依赖人工打分——直接回应 Harness 综述"弱且模糊的评估器"这一首要瓶颈；③ `baseline_v1.json` 是**可回滚的基准**：改提示词后跑一次，数字涨了才合并——这使 G3/G5 可验证。

#### 方案 P-20：学习产物可回滚

**修改要点**：让学习写入走项目已有的防御范式。

```python
# writing_skills.py
def _save_versioned(self, data: dict, path: str, keep: int = 5):
    """带版本轮转的写入 —— 复用项目 .bak + validate 的既有范式。"""
    p = Path(path)
    if p.exists():
        try:
            json.loads(p.read_text(encoding="utf-8"))       # 写入前校验旧文件可解析
        except (json.JSONDecodeError, OSError) as e:
            print(f"[写作技能] 旧文件损坏，跳过备份: {e}")
        else:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copy2(p, p.with_suffix(f".{stamp}.bak"))
            baks = sorted(p.parent.glob(f"{p.stem}.*.bak"))
            for old in baks[:-keep]:                        # 只留最近 keep 份
                old.unlink(missing_ok=True)
    save_json_atomic(p, data)                               # 原子写
```

**思路说明**：① **与 `memory_manager` 的 `.bak` 轮转 + `validate=True` 同构**——项目已在角色数据上验证过这套范式，复用成本最低、风险最小；② **写入前校验旧文件**——避免把好文件覆盖成坏文件；③ 保留 5 份，用户可在面板上加"回滚"按钮（属 UX 增强，非本轮必需）。

### 3.2 P1 组 —— 性能与结构

#### 方案 P-05/P-09/P-10/P-11：提示词集中化 + 文件拆分

**修改要点**：三步。

**第一步：新建 `app/prompts/` —— 提示词单一来源。**

```
app/prompts/
├── __init__.py
├── writer.py       # WRITER_SYSTEM（原 cache_prefix）
├── reviewer.py     # REVIEWER_SYSTEM
├── plot.py         # PLOT_DESIGNER_SYSTEM
├── world.py        # WORLD_BUILDER_SYSTEM
├── editor.py       # EDITOR_JUDGE_SYSTEM
├── extraction.py   # EXP / 关系 / 摘要 / 关键词
└── registry.py     # PROMPTS: dict[str, PromptSpec] + 版本号 + 指纹
```

`PromptSpec` 设计（关键：**带版本与指纹**）：
```python
@dataclass(frozen=True)
class PromptSpec:
    key: str
    version: int
    template: str
    def render(self, **kw) -> str: ...
    def fingerprint(self) -> str:      # sha256(template)[:12]
        return hashlib.sha256(self.template.encode()).hexdigest()[:12]
```

**第二步：`novel_agent.py` 改调用。**

```python
from .prompts import PROMPTS
system = PROMPTS["writer"].render(word_count=word_count, style=self._get_writing_style_prompt()) \
         + "\n\n" + dynamic_context
```

**第三步：清理 P-05 的 274 行闲置。**

`PromptManager.NOVEL_PROMPTS` 中的专业写作理论**择优并入** `app/prompts/`（它是更专业的一版，尤其"杜绝老套写法"章节有独立价值），随后删除 `PromptManager` 类——消除"一份信息写两处"。

**思路说明**：① **指纹是自我进化的前提**——每次生成记录用了哪个 prompt 版本，才能在 P-19 评测里归因"是提示词改动导致的分数变化"；② 沿用项目已验证的"单一来源 + 派生"原则（MEMORY.md 明载"同一事实写两处必然漂移，踩过 3 次"）；③ **不引入 jinja2** 等模板引擎，用 `str.format` + 显式命名参数，保持零新依赖。

**文件拆分**（`novel_agent.py` 2201 → 目标 ≤ 800）：
```
app/agent/
├── __init__.py
├── collaboration.py   # generate_with_collaboration + 5 个角色方法（约 500 行）
├── context.py         # _build_context + 全部 _compress_*（约 300 行）
└── generation.py      # 设定/角色/大纲/风格/长章（约 700 行）
```
`app/novel_agent.py` 保留 `NovelAgent` 门面类，Mixin 组合——**与 `app/*_ui.py` 的既有范式完全一致**。

#### 方案 P-06：启用并行编排

**修改要点**：`generate_with_collaboration` 中把无依赖的两步并行。

```python
from concurrent.futures import ThreadPoolExecutor

# PlotDesigner 与 WorldBuilder：WorldBuilder 只依赖 settings + plot_analysis 的 type
# plot_type 在无大纲时有确定性兜底（novel_agent.py:739-748），故可并行
with ThreadPoolExecutor(max_workers=2) as ex:
    f_plot = ex.submit(self._plot_designer_analyze, chapter_num, title, outline)
    f_world = ex.submit(self._world_builder_build, chapter_num,
                        {"type": self._quick_plot_type(chapter_num, outline)}, outline)
    plot_analysis = f_plot.result()
    world_context = f_world.result()
```

**思路说明**：① 只在**已验证无依赖**的两步并行（P-01 证实 WorldBuilder 只读 settings）；② **不全面并行化**——Writer → Reviewer → 修订是**真串行依赖**，强行并行会破坏质量闭环；③ Reviewer 与修订之间保持串行，因为修订依赖审校结果。
**风险与回退**：若 `world_context` 因 `plot_analysis` 未就绪而不准确，可退回串行（用一个 feature flag 控制）。**建议先做 P-01，观察 WorldBuilder 是否真的开始依赖 `plot_analysis`，再决定是否并行**——若不依赖，此方案收益稳定；若依赖，则放弃并行。

#### 方案 P-07：Reviewer 全章覆盖

**修改要点**：把现有 `_reviewer_evaluate`（`novel_agent.py:896-966`）的方法体**原样抽成 `_review_once`**（新增私有方法，仅多一个 `part` 形参用于提示词标注分片序号），再由 `_reviewer_evaluate` 负责分派与合并。**抽取过程不改动任何提示词内容**，保证行为等价。

```python
def _reviewer_evaluate(self, chapter_num, content, previous_feedback=""):
    if len(content) <= 6000:
        return self._review_once(chapter_num, content, previous_feedback)
    # 长章分片：每片 4000 字、重叠 500 字（保证跨片上下文连续）
    chunks = [content[i:i+4000] for i in range(0, len(content), 3500)]
    reviews = [self._review_once(chapter_num, c, previous_feedback, part=(i+1, len(chunks)))
               for i, c in enumerate(chunks)]
    return self._merge_reviews(reviews)   # 分数取加权均值、issues/suggestions 取并集

def _merge_reviews(self, reviews: list) -> dict:
    """合并分片审校结果：最低分主导，问题全收集。"""
    if not reviews:
        return {"overall_score": 70, "issues": [], "suggestions": []}
    merged = {
        "overall_score": min(r.get("overall_score", 70) for r in reviews),   # 短板主导
        "issues": [i for r in reviews for i in r.get("issues", [])][:20],
        "suggestions": [s for r in reviews for s in r.get("suggestions", [])][:20],
        "is_acceptable": all(r.get("is_acceptable", True) for r in reviews),
    }
    for k in ("character_consistency", "plot_logic", "writing_quality",
              "emotional_impact", "pacing"):
        vals = [r[k] for r in reviews if isinstance(r.get(k), (int, float))]
        if vals:
            merged[k] = round(sum(vals) / len(vals))
    return merged
```

**思路说明**：① **分数用 `min` 而非均值**——短板主导符合"木桶效应"，一个片段的严重问题不应被其他片段的优秀稀释；② 分片带 500 字重叠，避免把连贯情节从中间切断导致误报；③ **覆盖率提升**：5000 字章节从 80% → 100%；④ 成本：长章审校 token 约增 1.5 倍，但审校远小于生成，可接受。

#### 方案 P-12：参数可配置

**修改要点**：把类常量迁到配置，带默认值保持兼容。

```python
# app/config.py DEFAULT_CONFIG 增补
"agent_quality_threshold": 75,
"agent_max_revision_rounds": 3,
"agent_context_max_chars": None,          # None = 按 context_window 自动
"agent_kg_budget": 2000,                  # 原固定 500
"agent_reviewer_chunk_size": 4000,
"agent_enable_parallel_roles": True,

# novel_agent.py
@property
def threshold(self) -> int:
    return int(self.config.get("agent_quality_threshold", 75)) if self.config else 75

@property
def max_rounds(self) -> int:
    return int(self.config.get("agent_max_revision_rounds", 3)) if self.config else 3
```

**思路说明**：① **保留类常量为 fallback**（`self.config` 允许为 None，`__init__` 签名明示），保证既有单测不破；② 用 `@property` 而非实例属性——配置可在运行时改变（`refresh_if_needed` 已有此语义）；③ 全部走 `config.get(k, default)` 模式，与 `ai_client` 的既有取法一致。

#### 方案 P-15：知识图谱预算提升

`novel_agent.py:443-453`：`min(500, ...)` → 按 `max_chars` 比例分配，默认 2000。

```python
kg_budget = int(self.config.get("agent_kg_budget", 2000)) if self.config else 2000
kg_budget = max(0, min(kg_budget, int(max_chars * 0.15), max_chars - used))
```

**思路说明**：15% 上限避免图谱挤压"前文连贯性"这个更关键的预算（`extra` 占 0.55）。**前提是 P-03 先做完**——否则关系恒空，加预算也只是给空字符串留位置。

#### 方案 P-16：新增「智能体协作」观测面板

**修改要点**：新建 `app/panels/agent_panel.py`，注册到 `结构分析` 分组。

**展示内容**（数据全部现成）：
| 区块 | 数据源 | 渲染方式 |
|---|---|---|
| 协作时间线 | `_conversation_log`（`AgentMessage.to_dict()` 终于有用了） | `ui_kit.pretty_tree` 按角色分组 |
| 修订记录 | `_revision_memory` | 表格：轮次 / 分数 / issues / 是否采纳 |
| 工具调用审计 | P-14 的 `_tool_audit` | 计数 + 失败明细 |
| 学习面板 | `time_memory` 的 success/failure pattern | 高频问题 TOP10 |
| 当前参数 | P-12 的 threshold / rounds | 只读展示 + 编辑入口 |

**同时**：`NovelAgent` 需暴露只读访问器（当前是私有属性）：
```python
def conversation_trace(self) -> List[Dict]:
    with self._log_lock:
        return [m.to_dict() for m in self._conversation_log]
def revision_trace(self) -> List[Dict]:
    with self._log_lock:
        return list(self._revision_memory)
```
**思路说明**：① 面板是**可观测支柱的最直接落地**——Harness 综述明确要求"每个动作记录 trace"；② `to_dict()` 零调用这个事实说明**当初设计就是为观测准备的，只是没接**；③ 用 `ui_kit` 既有组件（`pretty_tree` / `card` / `badge`），无新视觉代码，**自动满足界面质量门禁**。

### 3.3 自我学习与自我进化 —— 能力目标、改进方向与衡量标准

这是用户明确要求重点强化的部分。基于 §2.5 的诊断（当前 **L0**），设计如下阶梯。

#### 3.3.1 能力目标（定义"做到什么算达标"）

| 等级 | 名称 | 能力定义 | 本项目对应 |
|---|---|---|---|
| **L0** | 记录 | 把运行结果写入存储 | **当前状态** |
| **L1** | 温故 | 学到的内容**进入下一次生成的上下文** | 方案 P-04b |
| **L2** | 择优 | 同一问题有多种应对时，**依历史效果选择**更好的 | 方案 P-19 指标 + A/B |
| **L3** | 自省 | 从失败轨迹中**归纳出新的规则**（非人工预设） | 新增方案 S-L3 |
| **L4** | 自适应 | 自动调参（阈值/轮次/预算）并**经回归验证后固化** | 新增方案 S-L4 |
| **L5** | 自我进化 | Agent 修改**自身 harness 代码**，隔离评测后合并 | 明确**不追求**（见 §3.3.4） |

**本轮目标：L0 → L2**（L1 靠 P-04b，L2 靠 P-19）。L3 给出设计但不实施。

#### 3.3.2 改进方向（五条，按依赖顺序）

**方向 1｜信号真实化**（依赖 P-04）
输入信号从"成功/失败布尔"扩展为**结构化质量向量**：
```
{quality_score, revision_rounds, issues[], slop_count, dialogue_ratio, length}
```
**理由**：没有真信号，后面全是空转。

**方向 2｜失败优先**（依赖 P-04）
失败样本 importance `0.8` > 成功 `0.6`，且 `failure_pattern` 独立存储。
**理由**：Harness 综述"负面结果"是首要瓶颈之一，且失败样本信息量高于成功样本。

**方向 3｜闭环回灌**（方案 P-04b）
`get_learned_constraints()` 产出"本章禁止"清单，注入 `dynamic_context`。
**理由**：这是 L0 → L1 的**唯一判据**——学到的必须改变行为。

**方向 4｜结构化沉淀**（依赖 P-03）
知识图谱补全 relation/event；`TimeAwareMemory` 的查询结果按角色差异化消费（而非只进 500 字段）。
**理由**：从"扁平日志"升级为"可查询结构"。

**方向 5｜自我批判**（方案 S-L3，设计不实施）
每 N 章触发一次"回顾"：把最近 N 章的 `failure_pattern` 交给 LLM，**让它归纳新规则**，输出的规则写入 `learned_rules.json`，经 P-19 评测验证后启用。
```
输入: 最近 20 章的 failure patterns + 对应 quality_score
输出: [{"rule": "在本作品设定下，X 做法导致分数下降", "confidence": 0.7, "evidence": [12, 15, 18]}]
门禁: 启用新规则后跑 P-19 评测，任一指标退步 >5% 则拒绝
```
**理由**：这是 L2 → L3 的路径，但**必须先有 L2 的评测能力**，否则无法验证归纳出的规则是否有效。

#### 3.3.3 衡量标准（可量化、可证伪）

| 指标 | 定义 | 当前 | L1 目标 | L2 目标 | 测量方式 |
|---|---|---|---|---|---|
| **闭环率** | 学习产物被下一章实际引用的比例 | **0%** | ≥ 60% | ≥ 80% | 统计 `get_learned_constraints()` 非空且注入的次数 / 总章数 |
| **首轮通过率** | `round_num==1` 即达标的章节占比 | 基线待测 | +5% | +10% | P-19 评测集 |
| **平均修订轮次** | 每章平均修订次数 | 基线待测 | -10% | -20% | 协作流程日志 |
| **问题复现率** | 同类 issue 在相邻 3 章内复现的比例 | 基线待测 | -20% | -35% | `failure_pattern` 统计 |
| **图谱覆盖率** | 有 ≥1 条关系的角色 / 总角色 | **0%**（P-03 前恒 0） | ≥ 40% | ≥ 50% | `knowledge_graph.relations` |
| **AI 痕迹密度** | 命中数 / 千字 | 基线待测 | -15% | -25% | `AntiSlopProcessor` |
| **学习回滚可用** | 能否一键回到上一版 | **否** | 是 | 是 | 测试断言 `.bak` 存在且可加载 |

**基线采集步骤**（P-19 完成后立即执行）：
```bash
RUN_QUALITY=1 pytest tests/quality/ -v --collect-baseline
# 产出 baseline_v1.json，作为后续所有对比的锚点
```

#### 3.3.4 明确不追求的（防止范围蔓延）

**L5（Agent 修改自身代码）明确不做**，理由是 Harness 综述给出的四条硬约束在本项目全部成立：
1. **评估器太弱** —— 小说质量无法像 SWE-bench 那样自动判定通过/失败（这正是 P-19 要解决的，但只能做到**代理指标**，够不上"可自动判定"）；
2. **奖励黑客** —— 若用 `slop_density` 作奖励，Agent 会学会规避检测器而非真的写好；综述明言"评估器应位于进化循环之外"，而本项目评估器（`AntiSlopProcessor`）**就在循环内**；
3. **可编辑面过大** —— Agent 能改 `novel_agent.py` 就能改角色数据保护、世代护栏（`guard_child_path`），**与项目硬约束直接冲突**；
4. **能力前提** —— STOP 论文实测：弱模型上递归改进会**退化**。

**结论**：本项目应把 L5 明确列为**不支持的演进方向**，写入文档，避免后续被当作"缺失功能"反复提案。

### 3.4 实施顺序（依赖图）

```
第一批（P0 · 正确性与闭环）
  P-01 WorldBuilder ──┐
  P-02 Editor ────────┤
  P-03 图谱写入 ──────┼──→ P-15 图谱预算（依赖 P-03）
  P-04 真信号 ────────┤
  P-04b 闭环回灌 ─────┤（依赖 P-04）
  P-13/14 工具激活 ───┤
  P-20 学习可回滚 ────┘
                        ↓
第二批（P1 · 可验证性，是自我进化的前提）
  P-19 评测基线 ←── 必须在此采集 baseline_v1.json
                        ↓
第三批（P1 · 结构）
  P-05/09/10/11 提示词集中化 + 文件拆分（依赖 P-19 保证重构不改变行为）
  P-12 参数可配置
  P-16 观测面板（依赖 P-14 的审计数据）
                        ↓
第四批（P1/P2 · 性能）
  P-06 并行（建议在 P-01 后观察依赖再决定）
  P-07 Reviewer 分片
  P-17 检索改进（可选）
  P-18 流式（可选）
```

**关键排序理由**：**P-19 必须早于所有"改进生成质量"的改动**。否则改提示词/阈值/上下文之后，无法区分"变好"与"变坏"——这正是当前项目最大的方法论缺口（§2.4 P-19）。

### 3.5 Harness 对齐说明

| Harness 支柱 | 本项目现状 | 本方案落点 |
|---|---|---|
| **验证（Verification）** | ❌ 无质量门禁（P-19） | P-19 评测集 + 代理指标 + 基线文件 |
| **停止（Stop）** | ⚠️ 有 `MAX_REVISION_ROUNDS=3`，但无 token/成本/连续无进展停止条件 | P-12 参数化 + 新增"连续 2 轮分数无提升即停止" |
| **状态（State）** | ✅ **已有** `persistence_ui._save_checkpoint` → `checkpoint.json`（原子写） | 保持；扩展记录 `revision_rounds` 与 `last_score` |
| **恢复（Recovery）** | ✅ **已有** `_check_recovery` 断电恢复 + `FALLBACK_CHAIN` 模型降级 + 401 立即停止批次 | 保持 |
| **隔离（Isolation）** | ⚠️ 无沙箱；但**学习写入路径**可加隔离 | P-20 版本化写入 + 写入前校验 |
| **可观测（Observability）** | ⚠️ `diagnostic_logger` 有 12 类事件，但**协作过程不可见**（P-16） | P-16 观测面板 + P-14 工具审计 |

**诚实评价**：六支柱中 **状态/恢复已有真实实现**（这部分做得比预期好），**验证与可观测是主要缺口**，隔离是部分缺口。本方案对六项均有落点，**不宣称"完全对齐"**——沙箱隔离（Isolation）在本项目语境下意义有限（本地桌面应用，用户自己的机器），**建议明确降级为"数据隔离"（学习产物可回滚 + 图谱写入校验）**，而非假装提供进程沙箱。

---

## 四、预期效果与验证方式

### 4.1 预期效果

| 维度 | 现状 | 优化后 |
|---|---|---|
| 角色真实性 | 3 真 + 1 空壳 + 1 个 if | 5 个角色全部真实调用 LLM |
| 工具系统 | 注册 7、调用 1（且是桩） | 5 个工具接入具体流程 + 全部调用可审计 |
| 自我学习等级 | **L0**（只写不读） | **L2**（择优）——学到的改变下一章生成 |
| 知识图谱 | 仅实体表，关系恒空 | 实体 + 关系 + 事件，覆盖率 ≥ 40% |
| 质量可验证性 | 2376 条测试**全为代码正确性** | 增加 7 项生成质量指标 + 基线门禁 |
| 参数可调 | 类常量硬编码 | 配置文件，支持按作品调节 |
| 过程可观测 | 仅文本日志 | 专用面板（时间线/修订/工具/学习） |
| 提示词 | 3 处散落、274 行闲置 | 单一来源 + 版本号 + 指纹 |
| `novel_agent.py` | 2201 行 | ≤ 800 行（门面类 + 3 个 Mixin） |
| 学习可回滚 | 否 | 是（保留 5 份 `.bak`） |
| Reviewer 覆盖 | 5000 字章节约 80% | 100%（分片，重叠 500 字） |

### 4.2 验证方式（分层）

**第 1 层｜单元测试**（快速、无 API）

| 验证项 | 测试文件 | 断言要点 |
|---|---|---|
| `learn_from_chapter` 接受真信号 | `tests/test_writing_skills_deep.py`（扩展） | `success=False` 时写入 `failure_pattern` |
| `get_learned_constraints` 过滤逻辑 | 新增 | 复现 1 次不入选、≥2 次入选、超 50 章不入选 |
| `_editor_judge` 三层裁定 | 新增 | four cases：分数不足 / `is_acceptable=False` / 有阻断问题 / 全通过 |
| `_merge_reviews` 合并 | 新增 | `score` 取 `min`；`is_acceptable` 取 `all`；分项取均值 |
| 版本化写入 | 新增 | `.bak` 生成、超 5 份轮转、旧文件损坏时跳过备份 |
| `_call_tool` 审计 | 新增 | 失败入审计且不抛异常 |
| 提示词指纹稳定性 | 新增 | 相同模板 → 相同指纹；改动 → 指纹变化 |

**第 2 层｜集成测试**（真实 Tk、无 API）

| 验证项 | 方式 |
|---|---|
| 协作流程 5 角色全被调用 | mock `ai_client.chat`，断言调用次数与角色对应 |
| 工具被实际调用 | 断言 `_tool_audit` 覆盖 ≥5 个工具 |
| 观测面板渲染 | `dialogs.set_silent(True)` + 实际建面板 + `_ui_metrics` 校验 |
| 参数生效 | 改 `config["agent_quality_threshold"]=90`，断言行为改变 |

**第 3 层｜质量回归**（需 API，手动触发）

```bash
RUN_QUALITY=1 pytest tests/quality/ -v
```
对比 `baseline_v1.json`，任一指标退步 >5% 即失败。

**第 4 层｜门禁（Hard gate，进 CI）**

```bash
ruff check app/ tests/ scripts/
ruff format --check app/ tests/ scripts/
pytest tests/ -x -q                    # 全量（拆块跑）
pytest tests/test_version_consistency.py tests/test_dialogs.py \
       tests/test_panel_ui_quality.py tests/test_font_token_ratchet.py
```
新增两条门禁：
- **提示词不得内联**（仿字体令牌棘轮的 tokenize 扫描）：`app/agent/` 下不得出现 ≥200 字符的三引号字符串字面量；
- **工具必须被调用**：`tests/test_tool_activation.py` 断言 7 个工具中**至少 5 个**在 `app/` 内存在调用点（防回归到"注册即遗忘"）。

**第 5 层｜人工核对（不可自动化部分）**

| 项 | 方式 |
|---|---|
| WorldBuilder 输出是否有价值 | 抽 5 章对比改造前后，人工判断是否含"新造地名" |
| 学到的约束是否真在影响生成 | 读 10 组 prompt，确认"本章禁止"清单存在且具体 |
| 面板信息是否够用 | 截图评审（沿用 `docs/ui_review/` 的既有流程） |

### 4.3 风险与回退

| 风险 | 概率 | 影响 | 回退方案 |
|---|---|---|---|
| P-01 接入后 WorldBuilder 消耗 token 但质量无提升 | 中 | 中 | 用 `agent_enable_world_builder` 开关关闭，退回 11 行版本 |
| P-04b 学到错误约束导致质量下降 | 中 | **高** | `n>=2` 阈值 + 可回滚（P-20）+ P-19 门禁三重防护 |
| P-06 并行引入竞态 | 中 | 中 | 先做 P-01 观察依赖；有疑问则**放弃并行**（收益非关键） |
| P-07 分片导致审校不一致 | 低 | 中 | 分片带重叠；`min` 聚合；可在配置里调 `chunk_size` |
| P-09 拆分引入回归 | 中 | **高** | **AST 等价性验证**（项目已验证的手法：逐文件 `ast.dump` 比对）+ P-19 基线 |
| P-05 弃用 `PromptManager` 丢失有价值提示词 | 中 | 中 | 先**并入再删**，不直接删 |
| P-19 评测集过拟合 | 中 | 中 | 评测集**不随提示词改动而更新**；分 held-in / held-out 两组 |

---

## 五、「主 Agent + 大量小 Agent」架构评估

### 5.1 优势

| 优势 | 说明 | 本项目对应证据 |
|---|---|---|
| **上下文隔离** | 每个子 Agent 只带自己需要的上下文，避免单窗口过载 | 现在 5 个角色的提示词已分离（PlotDesigner 1000 token / Writer 47 行 system） |
| **职责单一、可独立评测** | 每个子 Agent 可单独做质量指标 | P-19 可按角色分测（如只测 Reviewer 的判定准确率） |
| **并行潜力** | 无依赖的子任务可并发 | `ThreadPoolExecutor(max_workers=3)` 已建好（虽未用） |
| **专业化提示词** | 不同角色用不同 system prompt，比"一个万能 prompt"效果好 | Writer/Reviewer 的 system 差异显著（正向要求 vs 检查清单） |
| **失败可局部化** | 单个子 Agent 失败可降级，不影响全局 | `_world_builder_build` 的 `except → ""` 与 `_build_context` 的多层 try |
| **可观测粒度细** | 每个 Agent 的动作可分别记录 | `AgentMessage` + `MessageRole` 枚举已定义 |

### 5.2 潜在风险

| 风险 | 严重度 | 说明 | 本项目现状 |
|---|---|---|---|
| **协调开销超过收益** | **高** | 5 个 Agent 意味着 5 倍调用、更长的串行链；若子任务本身很小，纯属浪费 | ⚠️ **已发生**：WorldBuilder 11 行、Editor 一个 if —— "拆了但没内容" |
| **错误累积/放大** | **高** | PlotDesigner 的误判会污染 WorldBuilder → Writer → Reviewer 全链 | ⚠️ 存在：`plot_type` 影响上下文预算分配 |
| **上下文传递损耗** | 中高 | Agent 间靠自然语言传递，信息在交接处丢失 | ⚠️ 存在：`world_context` 曾因 BUG-1 未注入（已修） |
| **状态一致性** | 中高 | 多个 Agent 读写共享状态（memory / knowledge_graph）易竞态 | ⚠️ `writing_skill_manager` 是全局单例，`_lock` 只护 `_conversation_log` |
| **成本线性增长** | 中 | 每章 5+ 次 LLM 调用 | 已存在（PlotDesigner + Writer + N×Reviewer + N×Writer + Editor） |
| **观测与调试困难** | 中高 | 出错时难定位是哪个 Agent 的问题 | ⚠️ **严重**：P-16 过程完全不可见 |
| **评估难度指数上升** | **高** | N 个 Agent 的质量归因需 N 倍评测设计 | ⚠️ 当前连单 Agent 质量都测不了（P-19） |
| **过度工程** | 中 | 拆得太细导致"为了架构而架构" | ⚠️ **已发生**：7 个工具注册、1 个被调且是桩 |
| **奖励黑客面扩大** | 中高 | 每个子 Agent 都可能过拟合自己收到的信号 | 见 §3.3.4 |

### 5.3 适用场景判断

**适合**：
- 子任务**职责边界清晰**且**各自需要不同上下文/提示词**（如"写"与"审"确实对立）
- 子任务**有独立可验证的产出**（代码生成 → 测试通过；数据抽取 → schema 校验）
- 需要**并行**且子任务间**真无依赖**
- 子任务**复杂度足以支撑**独立 Agent 的开销（不能是 11 行函数）

**不适合**：
- 子任务**极简**（该合并进调用方，而非拆成 Agent）— **本项目 WorldBuilder/Editor 正是此例**
- **强串行依赖**（拆开只增加交接损耗）— Writer→Reviewer→修订 本质串行
- **验证信号弱**（无法判断单个子 Agent 好坏）— 小说质量正是如此（P-19）
- **上下文高度共享**（拆开就要反复传递同一批数据）

**对本项目的具体结论**：

| 角色 | 评估 | 建议 |
|---|---|---|
| PlotDesigner | 51 行，独立产出（plot_type/pace/foreshadowing），**符合** | **保留** |
| WorldBuilder | 11 行、无 AI、无独立产出，**不符合** | **P-01 补齐后保留；若不补齐，应合并进 PlotDesigner** |
| Writer | 94 行，核心产出，**完全符合** | **保留** |
| Reviewer | 84 行，与 Writer 对立（生成 vs 批判），**完全符合** | **保留** |
| Editor | 无独立实现，**完全不符合** | **P-02 补齐；否则应降级为 Reviewer 的输出字段** |

即：**当前 5 个 Agent 中有 2 个不满足"值得独立成 Agent"的门槛**。这正是本方案把 P-01/P-02 列为 P0 的原因——**要么补齐，要么合并，不能保持"名义上 5 个、实质上 3 个"的中间态**。

### 5.4 与自我学习、自我进化目标的关系

**正向关系（架构支撑自学习）**：

1. **子 Agent 是学习信号的天然分界** —— "哪个环节出问题"比"整章质量差"信息量大得多。5 个角色分别记录 → 自我学习能定位到"是情节设计弱"还是"文笔差"，这是**粒度优势**。
2. **专业化 Agent 让规则可归因** —— 学到的"本章禁止"清单可绑定到特定角色（给 Writer 的禁忌 vs 给 PlotDesigner 的禁忌），避免规则互相干扰。
3. **可观测粒度是自省的前提** —— L3（从失败轨迹归纳规则）需要**完整轨迹**；`AgentMessage` 的多角色结构正好提供这个数据结构。

**负向关系（架构放大自学习风险）**：

1. **并行 = 学习顺序不确定** —— 若 P-06 并行，多个子 Agent 同时写共享状态，学习记录可能乱序，**破坏"因果可追溯"**，而因果正是 L3 的基础。**这是 P-06 需要谨慎的深层理由**。
2. **多 Agent 使奖励黑客面扩大** —— 每个子 Agent 都可能过拟合自己那部分指标（Reviewer 学会"给高分"而非"审得准"），**且互相掩盖**。这是 L5 明确不做的又一理由。
3. **拆得过细 → 信号被稀释** —— 5 个 Agent 各记一份日志，若不合并成结构化质量向量（P-04），学习素材反而更碎。**所以 P-04 必须先于任何多 Agent 扩张**。

**结论**：`主 Agent + 大量小 Agent` 与自我学习是**双向放大**的关系——架构对了（职责清晰、产出可验证）能让自学习更精准；架构虚了（空壳 Agent、桩工具）则让自学习更难做且有更大风险。
**因此本项目的正确顺序是：先把现有 5 个 Agent 做"实"（P-01/P-02），再建立验证能力（P-19），然后才谈自学习升级（L1→L2）。在验证能力建立之前扩张 Agent 数量，是本方案明确反对的方向。**

---

## 附录 A：本轮评估的证据索引

| 结论 | 验证命令 |
|---|---|
| WorldBuilder 11 行且无 AI | `awk` 按 `^    def ` 划界，或读 `novel_agent.py:786-797` |
| Editor 无独立函数 | `grep -n "def _editor" app/novel_agent.py` → 零命中 |
| `is_acceptable` 被忽略 | `grep -n "is_acceptable" app/novel_agent.py` → 仅 `:951`（提示词 schema 内） |
| `add_relation` 生产零调用 | `grep -rn "add_relation(" app/ tests/` → 全在 `tests/` |
| `success=True` 硬编码 | `grep -n "learn_from_chapter" app/novel_agent.py` → `:1696` |
| `PromptManager` 闲置 | `grep -rn "PromptManager" app/` → 仅 `ai_client.py:150` 定义 |
| `run_parallel` 死代码 | `grep -rn "run_parallel"` → 16 处全在 `tests/` |
| 工具调用仅 1 次 | `grep -n "self.tools" app/novel_agent.py` → 注册 + `:689` |
| `list_tools` 生产零调用 | `grep -rn "list_tools"` → 生产零命中，仅 4 处测试 |
| `chat_stream` 零调用 | `grep -rn "chat_stream" app/` → 仅定义与文档 |
| 无向量检索 | `grep -rn "embedding\|向量\|vector" app/` → 零命中 |
| 图谱预算 500 | 读 `novel_agent.py:443-453` |
| 观测数据无出口 | `grep -rn "_conversation_log"` → 仅类内；`to_dict` 零调用 |
| 阈值硬编码 | `grep -n "QUALITY_THRESHOLD" app/novel_agent.py` → `:150` |
| `novel_agent.py` 2201 行 / 74 提示词块 | `wc -l` / `grep -c '"""'` |
| 有检查点机制 | `app/persistence_ui.py:82-115` |
| 有诊断日志 | `app/diagnostic_logger.py`（353 行，12 类事件） |

## 附录 B：既有资产复用清单（不要重造）

| 既有资产 | 位置 | 本方案用途 |
|---|---|---|
| `parse_json_response`（唯一 JSON 解析实现） | `app/parsing.py:449` | P-03/P-04 复用，不新增解析 |
| `atomic_write_json` | `app/storage.py` | P-20 原子写 |
| `.bak` 轮转 + `validate=True` 范式 | `app/memory_manager.py` | P-20 同构复用 |
| `ui_kit`（pretty_tree/card/badge） | `app/panels/ui_kit.py` | P-16 面板，零新视觉代码 |
| `dialogs.set_silent` | `app/dialogs.py` | 所有界面测试 |
| `_ui_metrics` + 质量门禁 | `tests/_ui_metrics.py` | P-16 验证 |
| `token_estimator` | `app/token_estimator.py` | P-07 分片预算、P-15 预算计算 |
| `_source_scan.code_only` | `tests/_source_scan.py` | 新增两条门禁的扫描基础 |
| AST 等价性验证手法 | MEMORY.md「可复用的验证手法」 | P-09 拆分验证 |
| 棘轮（ratchet）方法论 | 字体令牌迁移实践 | 提示词内联清理 |
| `diagnostic_logger` 12 类事件 | `app/diagnostic_logger.py` | P-16 数据补充源 |
| 检查点/恢复机制 | `app/persistence_ui.py` | Harness State/Recovery 支柱（已具备） |
