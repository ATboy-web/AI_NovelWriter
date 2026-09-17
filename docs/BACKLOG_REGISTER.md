# 待办 / 遗留问题 / 已知缺陷 总登记册

> 生成日期：2026-09-17（第二十轮）
> 口径：**每条都必须带可复核的证据**（文件:行号 / 命令输出）。
> 凡文档写「未处理」但代码已修的，一律以代码为准并标注 **已修复(证据)**。
> 本文件是唯一登记册；`docs/` 下历史报告不改写，只在本文里记「与本文不一致之处」。

---

## 0. 结论速览

| 状态 | 条数 | 说明 |
|---|---|---|
| 已修复（文档仍标未处理） | 3 | F3、F1 基线章节维度、F5 ruff format |
| 确认未修复 | 6 | D3、D4、D5、D7、O4、P-04 |
| 需决策（无对错，要人选） | 3 | 六标签一提交、webview-app 归档、backend 定位 |
| 本轮新发现 | 5 | 6 处重复解析器、死代码 `CharacterSystem`、自学习读不到、AST 判据、守卫缺口 |

**核心判断**：项目的待办**不在代码注释里**——`app/` 全树 **0** 个 TODO/FIXME/HACK
（仅 1 个 `XXX`、4 个 `pass  #`、3 个合法抽象 `NotImplementedError`）。所有遗留都在
`docs/` 33 份文档里，且**部分文档已与代码漂移**。因此本轮采用
「文档考古 × 代码实测交叉验证」，而非信任文档。

---

## 1. 已修复（文档仍旧标为未处理）

| ID | 事项 | 文档说法 | 实测证据 | 结论 |
|---|---|---|---|---|
| F3 | `update_character_activity` 无生产调用 ⇒ `character_activity.json` 恒空 | `ROADMAP_V3_...` 列为遗留 | `memory_manager.py:441-458 _record_character_activity`，docstring 明确写了「曾无生产调用，本方法即为接线而加」，并已从 `add_event` 调用；外层 `try/except (OSError, TypeError, ValueError)` 记 warning | **已修复** |
| F1 | 基线缺少章节维度 | `ROADMAP_V3_...` 列为遗留 | S2 已完成（`docs/NEXT_STEPS.md` 记录 + 基线含章节维度） | **已修复** |
| F5 | `ruff format` 未覆盖 `scripts/` 而阻塞 CI | `NEXT_STEPS.md` 列为待办 | `ruff format --check app/ tests/ scripts/` 本地全绿 | **已修复** |

> ⚠️ 这三条在 `docs/` 里仍显示为"未处理"。**不改写历史文档**，以本表为准。

---

## 2. 确认未修复（带证据）

| ID | 事项 | 证据（本轮实测） | 影响 | 优先级 |
|---|---|---|---|---|
| **D3** | `FullscreenWriter._toggle_ai` 无调用方 | `fullscreen_writer.py:471 def _toggle_ai`；全仓 grep `_toggle_ai` **仅 1 命中 = 定义本身** | 全屏写作器里"切换 AI 面板"是死按钮/死方法；用户点不到 | P2 |
| **D4** | `UIStyle` 四个 `create_styled_*` 工厂仅定义未使用 | `ui_style.py:407/434/450/472`（`create_styled_button/entry/text/listbox`），生产与测试**均 0 调用** | 487 行模块里 4 个死方法；与 `panels/ui_kit.py` 职责重叠 | P3 |
| **D5** | `PerformanceMonitor.save_report` 无调用方 | `performance_monitor.py:210 def save_report`，**0 调用** | 性能报告从不落盘 ⇒ 观测能力缺失的一环 | P2 |
| **D7** | `mobile-app/webview-app` 定位不明 | 目录存在，无构建入口/无 CI 任务 | 仓库里躺着一个不参与任何流程的形态 | P3（需决策） |
| **O4** | 重复测试（同函数体多份） | 见 §3 精确计数 | 全量收集 2376 条里约 **96 条可删**，拖慢 CI、掩盖覆盖真相 | P2 |
| **P-04** | `learn_from_chapter` 的 `success` 恒为 `True` | `novel_agent.py:1696` 实参硬编码 `success=True`；而 `writing_skills.py:691 if success:` 包住**全部**学习逻辑 | **自我学习的"信号假"根源**：形参等于没有，负样本永远进不来 | **P0** |

---

## 3. 重复测试精确计数（修正 `FEATURE_VALUE_ASSESSMENT.md` D8）

方法：按**函数体哈希**分组（`ast` 取 body 源码），统计每组的多余份数。
⚠️ 注意：同名但**目标类不同**的用例（如 `TestAIClientGetModels::test_get_models_error`
vs `TestGetOllamaModels::test_get_models_error`）**函数体相同但测的不是同一件事**，
以下计数已把这类标为「候选，需人工复核」而非直接计入可删。

| 测试族 | 同体分组 | 可删用例 | 文件数 |
|---|---|---|---|
| `novel_agent` | 63 | **66** | 7 |
| `reading_manager` | 21 | **23** | 5 |
| `agent_orchestrator` | 4 | 4 | 2 |
| `ai_client` | 2 | 2（候选） | 4 |
| `note_manager` | 1 | 1 | 3 |
| `diagnostic_logger` | **0** | 0 | 3 |
| `memory_manager` | **0** | 0 | 3 |
| **合计** | | **≈96** | |

> ❗ **`FEATURE_VALUE_ASSESSMENT.md` 的 D8 写错了**：它点名 `diagnostic_logger` 与
> `memory_manager` 是重复重灾区，实测**两者都是 0**；真正的重复质量在
> **`novel_agent`（66）+ `reading_manager`（23）**。归档报告不改，此处记录修正。

---

## 4. 需决策（无客观对错，需人选）

| ID | 事项 | 选项 | 建议 |
|---|---|---|---|
| M1 | 六个历史标签同指 `0cf8c54`（`RELEASE_HISTORY_NOTES.md §3`） | A 保持原状只记录 / B 补建各自 Release / C 重做标签 | **A**（已发布过的标签指向是事实，改历史不如记教训） |
| M2 | `mobile-app/webview-app` 归档方式 | A 删除 / B 移到 `archive/` / C 保留并补 README 说明不维护 | B 或 C（删了就丢历史，留一个说明成本更低） |
| M3 | `backend/` 长期定位 | A 冻结（现状）/ B 继续投入 / C 拆分出仓 | **A**（已在内存中定为冻结，只接缺陷与安全补丁） |

---

## 5. 本轮新发现（尚未见于任何文档）

### 5.1 六处手写 JSON 解析器（最强的结构优化目标）

`app/parsing.py` 已是唯一权威（`parse_json_response` 含完整策略 1–5），但以下位置
**各自手写了一套**：

| # | 位置 | 行数 | 解析目标 | 替换语义 |
|---|---|---|---|---|
| 1 | `novel_agent._plot_designer_analyze` | `735-784` | dict | 可直接换（策略 1/2 对齐） |
| 2 | `novel_agent._update_character_progression` | `1790-1878` | dict | 可换 + 保留 `Strategy 4` 字段抽取 |
| 3 | `generation_ui._auto_detect_decisions` | `862-904` | dict（`decisions`） | 可直接换 |
| 4 | `generation_ui._auto_generate` / 内嵌 `run` | `1763-1773` | list | 需 `is_list=True` |
| 5 | `character_ui._auto_detect_characters` | `166-169` | **list[str]** | 需 `is_list=True` + `str` 过滤 |
| 6 | `character_system.ai_create_character` | `705-712` | dict | **最弱**：无 `try/except`、无尾逗号修复 |

- ⚠️ **#4 与 inner `run` 是同一处**（`run` 嵌套在 `_auto_generate` 内），
  早先的 AST 扫描把它重复计了一次——已更正为**六处**。
- **AST 可检测签名**：`json.loads()` **没有**配 `except json.JSONDecodeError` 的调用点，
  就是「手写解析器」。
- 合计 `novel_agent` + `generation_ui` ≈ **250 行重复的 JSON 修复机器**。
- 替换是**严格更优**的：当前每次解析失败都直接丢数据（`[角色成长] JSON解析失败` 就 skip），
  换成统一解析器只可能让**更多**本来失败的输入被接受，无行为倒退。
- ❗ 但 #5 **不能直接换**：它取的是 `[ "张三", "李四" ]` 字符串数组，
  裸换会让数组解析静默失效 —— 必须 `is_list=True` + 只保留 `str` 元素。

### 5.2 守卫缺口

`tests/test_parser_convergence.py` 的 `TestDuplicateImplementationStaysDeleted`（`:189-217`）
用 AST 钉住了 `NovelAgent._parse_json_response` 和 `_extract_characters_from_raw`
**不得退回实现体**。但**上述 6 处新位置全部无守卫** ⇒ 需要一个
`tests/test_parse_convergence_extended.py`，仿照现有模式。

### 5.3 自我学习的"读不到"断点已精确定位到行

| 断点 | 位置 | 事实 |
|---|---|---|
| 信号假 | `novel_agent.py:1696` | `success=True` 硬编码 |
| 内容贫 | `writing_skills.py:691-729` | 只写 `success_pattern`（`importance=0.6`），全 `app/` 树**只出现 1 次**（`:704`） |
| **读不到** | `writing_skills.py:672-689` | `get_writing_context` **完全忽略 `chapter` 形参**；`success_pattern` **无任何读取方** |
| 检索弱 | `writing_skills.py:579-606` | `query()` 是**纯子串匹配** + 只按 `importance` 排序，**无时间衰减** ⇒ 1000 条上限下，第 87 章写入的记忆在第 120 章不可达 |

### 5.4 疑似新增死代码

`character_system.CharacterSystem`（非 UI 类）本轮**未找到任何生产调用方**
（`character_ui.py:952` 调的是实例方法 `ai_create_character`，其宿主是否即该类需再核）。
按「零可观察面」标准需复核后再判定，**不先删**。

### 5.5 内部发散

`parsing.py:565 parse_exp_json` 是**第二个完整的 5 策略实现**（约 100 行），
**不委托** `parse_json_response`。因其带 `_normalize_exp_entries` / `_safe_exp_int`
（M12 的 `_MAX_ABS_EXP = 1_000_000` 钳制）专门语义，**裸替换有风险**，
列为观察项而非本轮改动。

---

## 6. 执行顺序（按"风险从低到高"）

1. `character_system.py:705-712` — 最小、最弱、无修复无捕获 → 换 + 守卫
2. `character_ui.py:166-169` — 需 `is_list=True` + `str` 过滤（**不能裸换**）
3. `novel_agent.py:735-784` — dict，策略对齐 → 换 + 守卫
4. `generation_ui.py:862-904` — dict → 换 + 守卫
5. `generation_ui.py:1763-1773` — list，需 `is_list=True` → 换 + 守卫
6. `novel_agent.py:1790-1878` — 保留字段抽取策略，仅收敛策略 1/2/3 → 换 + 守卫
7. `P-04`：把真信号（分数/轮次/问题列表）传进 `learn_from_chapter`，去掉硬编码 `True`
8. `writing_skills.py:672` 让 `get_writing_context` 用上 `chapter`；`query()` 加时间衰减
9. `D5` 接上 `save_report`；`D3` 接上 `_toggle_ai`（或明确删除）
10. `O4` 合并 96 条重复用例（按族分块做，每块单独验证）

> 每一步都必须：改前跑相关测试 → 改后跑同批 → 加守卫。

---

## 7. 验证方式

| 层次 | 命令 |
|---|---|
| 解析层 | `pytest tests/test_parsing.py tests/test_parser_convergence.py` |
| Agent 层 | `pytest tests/test_novel_agent_*.py`（分文件跑，避免删档守卫） |
| 学习层 | `pytest tests/test_writing_skills*.py` |
| 界面层（若动 D3/D4） | `pytest tests/test_panel_ui_quality.py` |
| 静态 | `ruff check app/ tests/ scripts/` + `ruff format --check app/ tests/ scripts/` |

⚠️ 沙箱删档守卫阈值 50 路径 / 整轮累计 ⇒ **大套件必须拆块，且越早跑越好**。
判据：堆栈含 `shim\sitecustomize.py` 或 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 即环境伪报。
