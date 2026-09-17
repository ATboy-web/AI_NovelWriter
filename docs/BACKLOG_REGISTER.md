# 待办 / 遗留问题 / 已知缺陷 总登记册

> 生成日期：2026-09-17（第二十轮）
> 口径：**每条都必须带可复核的证据**（文件:行号 / 命令输出）。
> 凡文档写「未处理」但代码已修的，一律以代码为准并标注 **已修复(证据)**。
> 本文件是唯一登记册；`docs/` 下历史报告不改写，只在本文里记「与本文不一致之处」。

---

## 0. 结论速览

> **执行状态（第二十一轮，2026-09-17）**：
> §2「确认未修复」中的 **D3 / D4 / D5 / P-04** 已于第二十轮修复并加守卫测试；
> **O4**（重复测试合并）保留待做；**D7** 已在 §4 随 M2 一同结案；
> **M1 / M2 / M3** 三项决策事项已**全部采用建议并落地**（见 §4，含 M3 冻结契约）。
> 第 5 节「新发现」的 5.1（六处解析器收敛）与 5.3（自学习断点）均已落地。

| 状态 | 条数 | 说明 |
|---|---|---|
| 已修复（文档仍标未处理） | 3 | F3、F1 基线章节维度、F5 ruff format |
| 已修复（第二十轮） | 4 | D3、D4、D5、P-04（含 P-04b 自学习读不到） |
| **已决（第二十一轮，采用建议）** | **3** | M1 保持原状只记录 / M2 保留+补 README / M3 冻结 |
| **已修复（第二十一轮）** | **1** | **O4 重复测试合并（实删 82 条 + 16 个空壳类）** |
| 本轮新发现 | 5 | 6 处重复解析器（已收敛）、死代码 `CharacterSystem`、自学习读不到（已修）、AST 判据、守卫缺口（已补） |

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

> **✅ 已执行（第二十一轮）**：本节原口径为"约 96 条可删"，实测**确认可删 82 条 + 16 个空壳类**。
> 差异说明见 §3.2。执行工具：`scripts/dup_test_census.py`（普查）、
> `scripts/review_dup_candidates.py`（候选复核）、`scripts/dedup_tests.py`（执行合并）。

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

### 3.1 执行结果（第二十一轮）

| 项 | 数值 |
|---|---|
| 改动前 `tests/` 收集数 | 2420 |
| 改动后 `tests/` 收集数 | **2338** |
| 实删用例 | **82** |
| 顺带删除的空壳测试类 | 16 |
| 删除行数 | 738（12 个文件） |
| 回归结果 | 全绿（见 §3.3） |

**判定分层**（这是本轮最重要的方法论）：

| 层 | 判据 | 数量 | 处理 |
|---|---|---|---|
| 确定重复 | **同函数体 + 同类名 + 同函数名** | 17 | 自动删除多余份 |
| 确认重复 | **同函数体 + 异类名，但 setUp 绑定同一目标** | 64 | 复核后删除多余份 |
| **假重复** | 同函数体 + 异类名，**setUp 绑定不同目标** | **1** | **保留**（见 §3.4） |

### 3.2 为什么是 82 而不是 96

原估算 96 把三类东西混在一起算：(a) 真重复 81；(b) 计数口径不一致产生的重叠；
(c) 未扣除"同体但测不同目标"的假重复。实测口径更严：**只删"删掉后不可能少测任何东西"
的份数**。差额是**保守**方向，符合"宁留勿删"。

### 3.3 回归证据

```
tests/            2338 collected
pytest tests/     → 全部通过（含 6 skip）
ruff check        → All checks passed!
ruff format --check app/ tests/ scripts/ → 174 files already formatted
```

### 3.4 捕到的假重复（**必须保留**，这是判据自检的证据）

`tests/test_novel_toolkit.py` 里有三个**函数体完全相同**的用例：

```python
class TestElementLibrary:      # setUp: self.lib = ElementLibrary()
    def test_get_categories(self):
        cats = self.lib.get_categories()
        self.assertTrue(len(cats) > 0)

class TestBridgeLibrary:       # setUp: self.lib = BridgeLibrary()
    def test_get_categories(self):   # ← 一字不差
        ...

class TestDescriptionLibrary:  # setUp: self.lib = DescriptionLibrary()
    def test_get_categories(self):   # ← 一字不差
        ...
```

**它们测的是三个不同的类**，同体纯属巧合 ⇒ **删掉会真丢覆盖**。
已登记进 `scripts/dedup_tests.py` 的 `KNOWN_FALSE_POSITIVES` 常量（键 `f64eea5cb9052efa`），
脚本会**主动跳过并打印**，防止未来重跑时误删。

> 这条正是"验证判据本身要先自检"的实例：如果只看函数体哈希就动手，这里就错了。

---

## 4. 决策登记（原「需决策」→ **已决，均采用建议**）

> **决于 2026-09-17（第二十一轮）**。三项均为"无客观对错、需人选"的事项，
> 现统一采用下列建议并落地；本条起 §4 由「待决策」改为**决策登记（append-only，
> 旧决策不删除、只追加变更记录）**。

| ID | 事项 | 选项 | **决策** | 落地动作 |
|---|---|---|---|---|
| M1 | 六个历史标签同指 `0cf8c54`（`RELEASE_HISTORY_NOTES.md §3`） | A 保持原状只记录 / B 补建各自 Release / C 重做标签 | **采用 A**：保持原状，只记录 | `RELEASE_HISTORY_NOTES.md` §3 标题改为「已决」并新增 §3.1 决策与三条理由；**无代码 / 无 Git 操作** |
| M2 | `mobile-app/webview-app` 归档方式 | A 删除 / B 移到 `archive/` / C 保留并补 README 说明不维护 | **采用 C**：保留 + 补 README | 新增 `mobile-app/webview-app/README.md`（定位 / 为何不维护 / 已知技术债 / 如何重启）；`CONTRIBUTING.md:191` 目录树补注「已归档，不再维护」 |
| M3 | `backend/` 长期定位 | A 冻结（现状）/ B 继续投入 / C 拆分出仓 | **采用 A**：冻结 | 见下方 §4.1「冻结契约」；本文件与 `docs/NEXT_STEPS.md` 同步记明 |

### 4.1 M3 决策详情：`backend/` 冻结契约

**决策**：`backend/`（`ai-service` + `novel-service`）进入**冻结期**，
**只接缺陷修复与安全补丁，不接新功能**。

**为什么不是"继续投入"**：`FEATURE_VALUE_ASSESSMENT.md` 与本轮 §3 的实测都指向同一结论 ——
`backend/` 与桌面端 `app/` 存在**大面积功能重复**，而后者才是唯一有真实用户路径的形态
（EXE / APK）。在两条路径上并行演进同一批功能，是本项目已被反复证实的
「同一事实写两处必然漂移」根源。

**为什么不是"拆分出仓"**：拆分需要先确定它的独立价值与维护者，而这两点现在都不成立；
在没有结论前拆走，只会把问题藏进另一个仓库。**冻结是可逆的，拆分不是。**

**冻结期的具体边界（可执行）**：

| 允许 | 不允许 |
|---|---|
| 修 bug（含崩溃、数据错误） | 新增端点 / 新增业务能力 |
| 安全补丁（依赖升级、漏洞修复） | 为对齐桌面端新功能而改后端 |
| 随 CI 要求的测试与 lint 修正 | 重构（除非重构是修 bug 的必要手段） |
| `backend/tests/` 的既有用例维护 | 扩充覆盖率目标 |

**⚠️ 冻结期必须继续遵守的不变量**（违反会直接破坏 CI，见 `tests/_app_authority.py`）：

- `backend/*/app` 这两个同名包**不得**排到仓库根 `app/` 之前。
  `backend/tests/test_generators.py` 会把 `backend/novel-service` 插入 `sys.path[0]`，
  因此 `pyproject.toml` 的 `testpaths` 顺序（`["tests", "backend/tests"]`）**不可调换**。
- `backend/tests` **不能排在 `tests/` 之前**运行（同上原因）。
- 改 `backend/` 下任何带 `print` 的脚本时，仍须走 `scripts/_console_utf8.py`。

**解冻条件**（满足其一即可重新评估）：

1. 出现**只有后端形态能满足**的明确需求（如多端同步、账号体系、服务端渲染）；
2. 桌面端的某个能力被证明**不适合本地运行**（算力 / 数据量 / 合规要求）；
3. 有明确的维护者与独立的发布节奏。

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
