# 待办 / 遗留问题 / 已知缺陷 总登记册

> 生成日期：2026-09-17（第二十轮）
> **最后校对：2026-09-17（第二十二轮）—— §2 已全部结案，本节由「确认未修复」改为「已结案」**
> 口径：**每条都必须带可复核的证据**（文件:行号 / 命令输出）。
> 凡文档写「未处理」但代码已修的，一律以代码为准并标注 **已修复(证据)**。
> 本文件是唯一登记册；`docs/` 下历史报告不改写，只在本文里记「与本文不一致之处」。

---

## 0. 结论速览

> **执行状态（第二十二轮，2026-09-17）**：
> **§2「确认未修复」现已空表 —— 该节 6 条全部结案**（D3 / D4 / D5 / O4 / P-04 / D7）。
> 其中 D3 / D4 / D5 / P-04 于第二十轮修复，O4 于第二十一轮执行，D7 随 §4 的 M2 一并归档；
> 本节（第二十二轮）的工作是**把 §2 与代码实测对齐**（此前 §2 仍列着 5 条已修项，属文档漂移）。
> **M1 / M2 / M3** 三项决策事项已**全部采用建议并落地**（见 §4，含 M3 冻结契约）。
> 第 5 节「新发现」的 5.1（六处解析器收敛）、5.2（守卫缺口）、5.3（自学习断点）、5.4（死代码复核）
> **均已落地**；仅 5.5（`parse_exp_json` 内部发散）按原判**保留为观察项**，本轮复核结论不变。
> 本轮**新登记 1 条待办**：`app/cloud_storage.py` 零测试覆盖（见 §2.1）—— 这是当前唯一新开的条目。

| 状态 | 条数 | 说明 |
|---|---|---|
| 已修复（文档仍标未处理） | 3 | F3、F1 基线章节维度、F5 ruff format |
| 已修复（第二十轮） | 4 | D3、D4、D5、P-04（含 P-04b 自学习读不到） |
| **已决（第二十一轮，采用建议）** | **3** | M1 保持原状只记录 / M2 保留+补 README / M3 冻结 |
| **已修复（第二十一轮）** | **1** | **O4 重复测试合并（实删 82 条 + 16 个空壳类）** |
| **已结案（第二十二轮复核）** | **6** | **§2 全部 6 条：D3 / D4 / D5 / O4 / P-04 / D7** |
| **已建立（第二十二轮）** | **1** | **覆盖率阈值门禁 `scripts/check_coverage.py`（双向 ratchet）** |
| **新登记（第二十二轮）** | **1** | **`app/cloud_storage.py` 零测试覆盖（404 行未覆盖，占全仓 16.9%）** |
| 本轮校对结论 | — | §5 的 5.1–5.4 已全部落地，5.5 维持观察项；无其他遗留 |

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

## 2. 已结案（第二十二轮复核：原「确认未修复」6 条全部落地）

> **本节在第二十二轮完成收口。** 此前它叫「确认未修复（带证据）」，但表里列的
> D3 / D4 / D5 / O4 / P-04 在第二十、二十一轮就已修复 —— **文档比代码慢了整整两轮**，
> 这正是本项目反复吃亏的「同一事实写两处必然漂移」。本轮不再补写"已修复"标记，
> 而是**直接把该表改成结案表**：每条给出「当时判断 → 现在实测」两列，
> 让读的人一眼看出差异落在哪一行代码上。

| ID | 当时判断（第二十轮） | 现在实测证据 | 结论 | 守卫 |
|---|---|---|---|---|
| **D3** | `FullscreenWriter._toggle_ai` 无调用方（"全仓 grep 仅 1 命中 = 定义本身"） | `fullscreen_writer.py:171` **`command=self._toggle_ai`** —— 工具栏已补 `AI辅助` 复选框；`:158` 保留注释记录此前的"零调用"事实 | ✅ 已修复 | `tests/test_wiring_guards.py:52`（有入口控件）、`:61`（复选框状态同步） |
| **D4** | `UIStyle` 四个 `create_styled_*` 工厂仅定义未使用 | `ui_style.py:407` 注释记录**已删除**这四个工厂；全仓 grep 仅在守卫白名单里出现名字 | ✅ 已修复（**改为删除**，而非接线） | `tests/test_wiring_guards.py:75-78`（断言符号为 0） |
| **D5** | `PerformanceMonitor.save_report` 全仓 0 调用 ⇒ 指标从不落盘 | `shell_ui.py:1205` **`monitor.save_report(str(out_dir / f"performance-{stamp}.json"))`**；`:1185` 注释记录此前的"零调用"事实 | ✅ 已修复 | `tests/test_wiring_guards.py:127`（断言调用存在） |
| **D7** | `mobile-app/webview-app` 定位不明（无构建入口/无 CI 任务） | 新增 `mobile-app/webview-app/README.md`（3405 B）**首行即 `# mobile-app/webview-app — 已归档（不再维护）`**，含定位 / 为何不维护 / 已知技术债 / 如何重启；`CONTRIBUTING.md` 目录树同步加注 | ✅ 已决策并落地（§4 的 M2，采用"保留 + 补 README"） | 文档级，无代码守卫（符合其性质） |
| **O4** | 重复测试（同函数体多份），当时估「约 96 条可删」 | 实删 **82 条 + 16 个空壳类**，`tests/` 收集数 **2420 → 2338**，删 738 行 / 12 文件；见 §3.1 精确计数与 §3.2 差额解释 | ✅ 已执行 | `scripts/dedup_tests.py` 的 `KNOWN_FALSE_POSITIVES`（防误删，见 §3.4） |
| **P-04** | `learn_from_chapter` 的 `success` 恒为 `True`（自学习"信号假"根源） | `novel_agent.py:1716-1718` 改为 **`effective_quality = quality if quality is not None else self.last_chapter_quality`**，再按 `QUALITY_THRESHOLD` 判定；`:759` 生成流程把真实评分记进 `self.last_chapter_quality` | ✅ 已修复（含 P-04b「读不到」、P-04c「负样本写不进」） | `tests/test_writing_skills*.py`（分文件跑，见 §7） |

### 2.1 新登记（第二十二轮，唯一未结项）

| ID | 事项 | 证据 | 影响 | 优先级 |
|---|---|---|---|---|
| **C1** | `app/cloud_storage.py` **零测试覆盖** | 单进程全量跑 `pytest tests/ backend/tests/ --cov=app`：该文件 **404 行未覆盖 / 覆盖率 17.4%**，是**单个文件里最大的覆盖缺口**（占全仓 2387 未覆盖行的 **16.9%**）；全仓 `grep -rn cloud_storage tests/ backend/tests/` **命中 0 次** —— 没有任何测试文件引用它 | 该模块含**安全相关逻辑**：`_require_secure_url`（拒绝非 loopback 的 `http://`）、`_safe_error`（脱敏密钥）、`SecureConfig`（`_SENSITIVE_FIELDS` 加密存取）。这些分支**从未被执行过**，等于"写了但没人验证过它真的拦得住" | **P1** |

> **为什么登记为 P1 而不是 P2**：其余低覆盖文件（`character_system.py` 46.4%、`ai_settings_ui.py` 13.0%）
> 属于**逻辑正确性**风险，而 C1 属于**安全边界**风险 —— 一个从未被跑过的 `http://` 拒绝分支，
> 与"没有这个分支"在可观测层面无法区分。**但本轮不实施**：它需要新写一整套 provider mock
> （五个网盘 provider + 网络层），工作量与风险都远超"收口文档"，单独立项更合适。
> ⚠️ 另注：本项目**分块跑**覆盖率时该文件会显示为更低（见 §8 的阈值说明），
> 以**单进程**数值为准。

> **§2 已无"未修复"条目。** 若未来又发现新的未修项，**追加到 §2.1**，
> 不要复活 §2 原表 —— 结案表的价值就在于它能被信任。

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
| **合计** | | **≈96（估算口径）** | |

> ⚠️ **上表是"普查估算"，不是最终执行值。** 实际删除 **82 条**（差额原因见 §3.2）。
> 保留此表是为了留下"估算 vs 实删"的对照 —— 它本身就是"估算不可直接当执行依据"的证据。
> **需要权威数字时看 §3.1，不要用本表。**

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

> **收口状态（第二十二轮复核）**：5.1 / 5.2 / 5.3 / 5.4 **四条全部落地**；
> **5.5 按原判保留为观察项**（复核后结论不变）。逐条实测证据见各小节末尾。

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

**✅ 已落地（第二十二轮逐处复核）**：

| # | 位置 | 现状实测 | 保底策略是否保留 |
|---|---|---|---|
| 1 | `novel_agent._plot_designer_analyze` | `:1816` 改调 `self._parse_json_response(response, None)`（`:771+`） | — |
| 2 | `novel_agent._update_character_progression` | `:1816` 统一解析 | ✅ **保留** `:1818-1821` 的 Strategy 4 逐字段提取（正则捞 `"updates"` 内每个 `{...}`） |
| 3 | `generation_ui._auto_detect_decisions` | `:854` 统一解析 | ✅ **保留** `:856-869` 的 `"decisions"` 定点抽取 |
| 4 | `generation_ui._auto_generate`（内嵌 `run`） | `:1732` 改调 `_parse_json_response(resp, [], is_list=True)` | — |
| 5 | `character_ui._auto_detect_characters` | `:170` 走 `parse_json_response(response, [], is_list=True)` + `:171` `isinstance(n, str)` 过滤 | — |
| 6 | `character_system.ai_create_character` | `:714` 走 `parse_json_response(response, None)` | — |

> ✅ **意外收获（#4）**：收敛顺带修掉一个**潜在 `UnboundLocalError`** ——
> 旧写法在 `re.search` 未命中时不给 `new_batch` 赋值，紧接着就 `if new_batch:`
> 直接抛异常（见 `generation_ui.py:1727-1731` 的注释记录）。
> 这不是"重构引入的等价替换"，而是一次**真 bug 修复**。
>
> ❗ 复核确认：`app/` 下其余 `json.loads`（`memory_manager` / `live_data` / `lifecycle_ui` 等
> 约 15 处）都是**读本地 JSON 文件**，不是解析 AI 响应 ⇒ **不属本项，不应收敛**。
> 判据（`json.loads` 无 `except json.JSONDecodeError` 保护）只适用于 AI 响应文本。

### 5.2 守卫缺口

`tests/test_parser_convergence.py` 的 `TestDuplicateImplementationStaysDeleted`（`:189-217`）
用 AST 钉住了 `NovelAgent._parse_json_response` 和 `_extract_characters_from_raw`
**不得退回实现体**。但**上述 6 处新位置全部无守卫** ⇒ 需要一个
`tests/test_parse_convergence_extended.py`，仿照现有模式。

**✅ 已落地**：`tests/test_parse_convergence_extended.py`（8915 B）已建立，
覆盖 6 处的"旧签名已消失"断言 + "保底策略仍在"断言：

| 守卫用例 | 钉住的事实 |
|---|---|
| `:135 test_character_system_slice_loads_gone` | #6 的 `response[a:b]` 切片解析不得回流 |
| `:140 test_character_ui_array_regex_gone` | #5 的 `re.search(r"\[[\s\S]*\]")` 不得回流 |
| `:149 test_novel_agent_depth_tracking_gone` | #1 的括号深度追踪不得回流 |
| `:156 test_novel_agent_still_keeps_field_extraction_salvage` | #2 的 Strategy 4 **必须仍在** |
| `:161 test_generation_ui_depth_tracking_gone` | #3 的括号追踪不得回流 |
| `:165 test_generation_ui_keeps_decisions_salvage` | #3 的 `"decisions"` 定点抽取**必须仍在** |

> 注意后两条是**反向**断言（"必须仍在"）—— 守卫不能只拦"代码重写回来"，
> 还要拦"有人顺手把保底策略删了"。这类删除不会让测试变红，只会让解析成功率静默下降。

### 5.3 自我学习的"读不到"断点已精确定位到行

| 断点 | 位置 | 事实 |
|---|---|---|
| 信号假 | `novel_agent.py:1696` | `success=True` 硬编码 |
| 内容贫 | `writing_skills.py:691-729` | 只写 `success_pattern`（`importance=0.6`），全 `app/` 树**只出现 1 次**（`:704`） |
| **读不到** | `writing_skills.py:672-689` | `get_writing_context` **完全忽略 `chapter` 形参**；`success_pattern` **无任何读取方** |
| 检索弱 | `writing_skills.py:579-606` | `query()` 是**纯子串匹配** + 只按 `importance` 排序，**无时间衰减** ⇒ 1000 条上限下，第 87 章写入的记忆在第 120 章不可达 |

**✅ 已落地（四个断点逐条确认）**：

| 断点 | 现状实测 | 说明 |
|---|---|---|
| 信号假 | `novel_agent.py:1716-1718` | `effective_quality = quality if quality is not None else self.last_chapter_quality`，再按 `QUALITY_THRESHOLD` 判 `success`。**并保留旧行为**：`effective_quality is None` 时仍按成功处理，避免无评分路径行为倒退 |
| 内容贫 | `writing_skills.py:785-797` | `importance` 随评分浮动：`max(0.5, min(0.9, 0.5 + (quality-60)/100))`，不再是恒定 0.6 |
| **读不到** | `writing_skills.py:722` + `:729` + `:738` | `get_writing_context` 已透传 `chapter`；**并新增两个读取方**：`success_pattern` 取最近 3 条（`chapter_window=50`）→「近期成功模式」；`failure_pattern` 同样取回 →「近期未达标章节（应避开同类问题）」 |
| 检索弱 | `writing_skills.py:612-633` | `query()` 新增 `chapter` + `chapter_window`（默认 200）：超窗记忆被过滤；排序改为 `(importance, -章节距离)` ⇒ 同分时**近章优先** |

> ⚠️ **本轮复核发现一处尚未处理的细节**：`_cleanup()`（`writing_skills.py:556-577`）
> 仍用**自然日**衰减（`days_old / 30`），而新加的窗口过滤用**章节距离**。
> 两套时间尺度并存 ⇒ 长期不写作但章节推进快的项目里，
> 记忆可能**先被 `_cleanup` 按天数淘汰**，导致章节窗口形同虚设。
> **本轮不改**（会动淘汰语义，需单独评估），**登记为观察项 R1**，见 §2.1 之后。

### 5.4 疑似新增死代码

`character_system.CharacterSystem`（非 UI 类）本轮**未找到任何生产调用方**
（`character_ui.py:952` 调的是实例方法 `ai_create_character`，其宿主是否即该类需再核）。
按「零可观察面」标准需复核后再判定，**不先删**。

**✅ 已复核结案：不是死代码，判定不删。** 复核证据：

| 来源 | 命中 |
|---|---|
| 生产代码 | `character_ui.py:115 / :211 / :513 / :902 / :954` 五处 `CharacterSystem(self.current_novel_dir)` |
| 生产代码（跨面板） | `timeline_ui.py:702` `branch_chars = CharacterSystem(branch_dir)` —— **分支世代读取角色也走它** |
| 测试 | `tests/test_character_accessors.py:19`、`tests/test_character_data_integrity.py:239 / :256 / :266` |

> **当时的判断失误在于只搜了"被调用的方法名"而没搜"类名实例化"。**
> `character_ui.py:952` 调的是 `self.character_system.ai_create_character(...)` ——
> `self.character_system` 正是本类的实例，只是**中间隔了一层属性赋值**，
> 单纯 grep 方法名看不见。**教训：判"死代码"必须同时搜类名、属性名、方法名三种形态。**
> 本类还承担 `timeline_ui` 的分支角色读取，删除会直接打断世代功能。

### 5.5 内部发散

`parsing.py:565 parse_exp_json` 是**第二个完整的 5 策略实现**（约 100 行），
**不委托** `parse_json_response`。因其带 `_normalize_exp_entries` / `_safe_exp_int`
（M12 的 `_MAX_ABS_EXP = 1_000_000` 钳制）专门语义，**裸替换有风险**，
列为观察项而非本轮改动。

**⏸ 复核后维持原判（仍为观察项）**：`app/parsing.py:577 def parse_exp_json(response)` 结构未变，
仍是独立的 Strategy 1–5 实现。复核确认**替换收益低于风险**：
- 它的输出要经 `_normalize_exp_entries` + `_safe_exp_int`（`_MAX_ABS_EXP` 钳制）两道专门处理，
  这两道是 `parse_json_response` 不具备的语义；
- 其调用方 `generation_ui.py:18` 明确 `from app.parsing import parse_exp_json, parse_json_response`
  —— **两者被同时导入并分别使用**，说明作者是有意区分而非疏漏。

> **判定标准**：`parse_json_response` 管"把 AI 响应变成 Python 对象"，
> `parse_exp_json` 管"把 AI 响应变成合法的 EXP 条目"——**职责不同**，
> 不属于 §5.1 那种"同一件事写六遍"。**不收敛是正确的。**

### 5.7 运行时审计新发现（2026-09-17，来自《快速统治》实跑）

> **完整报告**：`docs/RUNTIME_AUDIT_20260917.md`（含每条的证据与验证方式）。
> **共同前提**：本次实跑用的是 **v3.1.0 发布版**（非本轮新构建），
> 因此"新功能未生效"属预期；但下列缺陷**与构建版本无关，当前 HEAD 仍在**。
>
> ### 修复状态（同日稍晚）
> | 已修 | 未修 |
> |---|---|
> | **D1**（主角名被覆盖）、**D2**（摘要存思维链）、**D3**（记忆块类型改 `summary`，源头随 D2 消失）、**D4**（删除截正文冒充摘要）、**D5**（过滤示例回声）、附带发现（`str(None)` 建目录） | **D6**（角色双 schema）、**D7**（知识图谱近空）、**D8**（世界观不一致）、**D9**（EXP 提示误导）、**D-命名**（`chapters/`(4) 与 `memory/chapters/`(5) 分属不同存储且各自自洽，未改） |
>
> 守卫：`tests/test_finalize_integrity.py`（45 条）。已用**退回修复 ⇒ 测试变红**反证 D1/D2 有效。
> ⚠️ **D3 已落盘的污染数据**（`memory/chunks/page_0000.json` 里那条 `type:"plot"` 的思维链）
> 属用户作品数据，**未自动清理** —— 需单独确认。

| ID | 事项 | 位置 | 严重度 / 说明 |
|---|---|---|---|
| **D1** | **主角名被"整份覆盖"抹掉** —— `_auto_generate` 在 `:1481` 只读一次 `meta`，`:1537` 用 `update_meta` 写入 `protagonist`，`:1566` 又用**那份不含 protagonist 的旧副本** `write_meta` 整份覆盖 | `generation_ui.py:1481 / 1537 / 1566`（读取方 `:133`、`novel_agent.py:962/1142/1373`） | 🔴 **最高**。铁证：`meta.json.bak` 有 `protagonist:"陆昭"`，`meta.json` 没有，唯一差异即此字段。后果① 整体大纲/故事大纲读不到主角 ⇒ 各自编出「苏妩」「沈夜/姜姒」（三份大纲主角全不同）；后果② **磁盘上再无该字段 ⇒ 第 2 章起写作/修订全部失去主角锁定**，缺陷会持续恶化 |
| **D2** | **摘要把模型思维链当了摘要** —— `max_tokens=1000` 恰好等于 `THINKING_MIN_TOKENS`，而判据是严格小于 ⇒ 思考模式未被禁用但预算不够输出 ⇒ `content` 空 ⇒ `_finalize_text` 兜底返回 `reasoning` ⇒ 原始推理落盘为摘要 | 写入 `novel_agent.py:1795`；咬合 `providers/reasoning.py:27/84`、`ai_client.py:1124` | 🔴 高。产物 `summaries/chapter_00001_summary.txt` 1789 字符即思维链。诊断日志实证：入口 `max_tokens=1000` → 出口 `result_len=1782`，与文件 1789（含 7 字符前缀）完全吻合 |
| **D3** | **同一段思维链污染记忆库** —— `memory/chunks/page_0000.json` 里 `type:"plot"` 的条目内容就是 D2 的思维链，类型标注也与内容不符 | 记忆分块落盘路径 | 🟠 中高。后续检索会把推理当剧情片段回灌 |
| **D4** | **"摘要"实为正文截断** —— `content[:500]` 直接当摘要，且用了 **4 位**补零，与 D2 的 5 位文件同名章号 | `chapter_ui.py:57-65`（另 `:85` 写 4 位章节） | 🟠 中。`summaries/` 因此同章两份文件、两种命名 |
| **D5** | **世界线记录的是提示词示例** —— 落盘内容 `"当时的情况"/"主角选择了什么"/"可能的另一种选择"` 就是 `:842` 提示词里的 few-shot 示例，模型原样返回且未校验，日志却报"记录1个决策点"（**假成功**） | `generation_ui.py:842` 附近 | 🟠 中。同类"示例泄漏成结果"值得全仓排查 |
| **D6** | **角色双 schema** —— 3 个 AI 档案（13 字段）vs 自动创建的苏倾颜 RPG 模板（28 字段，属性全默认 10、`personality`/`appearance`/`backstory` 皆空） | 角色自动创建路径 | 🟡 中。同目录两种结构，读取方须同时兼容 |
| **D7** | **知识图谱信息量近空** —— `entities` 只有 3 个角色（**缺苏倾颜**），`relations`/`events` 皆空，`attributes` 皆空，每实体 `mentions:1`；而角色档案里明确有"陆昭↔赵无咎"的从属关系 | `writing_skills/knowledge_graph.json` 落盘路径 | 🟡 中 |
| **D8** | **世界观与三份大纲各说各话** —— 设定是「玄元界」（`settings.json`），而 `outline.json`、`overall.json`、`stories.json` 及正文都写「九州/帝印/九霄宗」；正文首句「玄元界，中州。」之后「九州」出现 18 次，**同篇混用两套地理** | 章节大纲提示词 | 🟡 中 |
| **D9** | **1 级角色负向 EXP 提示误导** —— `add_exp` 有"最低保障 `exp>=0`"地板（注释明确），故 `-30` 在 1 级无任何变化，但日志仍打印「-30EXP」，看起来像已扣减 | `generation_ui.py:1175`、`character_system.py:255-259` | 🟢 低。行为正确，仅提示误导 |

### 5.8 一致性审计新发现（2026-09-17，全项目扫描）

> **完整报告**：`docs/CONSISTENCY_AUDIT_20260917.md`。守卫 `tests/test_config_consistency.py`（25 条）。

**已修**（本轮）：敏感字段清单重复定义（安全类）· `fpdf2` 未声明致 PDF 导出静默变 TXT ·
`img_width/img_height` 两端未接通 · `theme/auto_save` 声明但无效 · DeepSeek 余额地址在
`api_base` 带 `/v1` 时 404 · 余额查询未回退 DeepSeek 官方接口 · 回退结果不说明归属。

| ID | 事项 | 位置 | 严重度 / 说明 |
|---|---|---|---|
| **D10** | ~~🔴 **文生图能力完全不可达**~~ → **✅ 已解决**（2026-09-17）：新增**插图工坊面板** `app/panels/illustration_panel.py`（16 面板 / 5 分组），把 `scene_prompts/*.txt` 接到 `ImageGenerator`，并补齐后端注册表、健康探测、模型列表、`img_api_key` 鉴权、结构化结果与 `last_error`。守卫 `tests/test_image_and_local_model.py`（76 条，含真实 Tk 构建）。~~原状：`ImageGenerator.generate()` **全仓零调用**，实例只在 `lifecycle_ui.py:1822` 创建，唯一使用是 `shell_ui.py:1041` 拼状态栏——**虚假承诺**~~ | `app/panels/illustration_panel.py`、`app/image_generator.py` | ✅ **已解决** |
| **D15** | ✅ **已补全**：本地模型"列出已装模型 / 服务健康 / 拉取模型"三个接口此前**只有 `get_ollama_models()` 一处且全仓零界面调用** ⇒ 用户只能手打模型名；模型候选来自注册表里的**静态建议表**，与机器实际安装无关。现新增 `OLLAMA_PATHS` / `LocalModel` / `parse_tags` / `parse_version` / `parse_pull_progress` 与 `AIClient.list_local_models` / `check_local_service` / `pull_local_model` / `can_list_local_models`，并在设置页接入（显隐由能力位 `local` 驱动） | `app/providers/ollama.py`、`app/ai_client.py`、`app/ai_settings_ui.py` | ✅ **已补全** |
| **D11** | `img_api_key` / `secret_key` 在敏感字段清单里，但 `app/` **零读取** ⇒ 需要密钥的图片服务商无法鉴权；`secret_key` 完全是遗留 | `config.py:84` | 🟡 中。不构成安全漏洞（不会被误存），但会让人误以为"这两个字段是活的" |
| **D12** | 桌面端 `httpx>=0.24` 约束**过宽** —— 跨 0.25→0.28 的破坏性变更（`proxies`→`proxy` 等）。当前实装 0.28.1 测试全绿，但干净环境重装拉到更晚版本可能出问题 | `pyproject.toml` | 🟡 中。建议收紧为 `>=0.24,<0.29`（后端 `requirements.txt` 钉的是 `==0.25.2`，两者独立部署故非硬冲突） |
| **D13** | `markdown` / `beautifulsoup4` 声明了但 `app/` 零 import（`bs4` 是被 lxml 的可选 `html.soupparser` 带进包的）。删除可减 EXE 体积 | `pyproject.toml` | 🟢 低。属产品决策 |
| **D14** | 本地不带 `--distpath` 构建时，EXE 会落到**仓库根目录**（`novel_app.spec` 的 `name='../AI_NovelWriter'`）⇒ 又一处"旧构建被误当新版"的来源 | `installer/novel_app.spec:116` | 🟢 低。已在内存与审计报告写明：构建必须带 `--distpath "%TEMP%\…"` |

> **D-命名**（可与 D4 合并处理）：章节/摘要补零位数不统一 —— `chapters/` 用 4 位
> （`chapter_ui.py:85`）、`memory/chapters/` 与 `memory_manager.py:378` 用 5 位、
> `summaries/` **两种并存**；`generation_ui.py:1950` 只读 5 位 ⇒ 与用户先看到的 4 位文件不是同一份。

### 5.6 观察项登记（本轮新增）

| ID | 事项 | 位置 | 为何本轮不动 | 何时该动 |
|---|---|---|---|---|
| **R1** | 记忆淘汰用**自然日**（`days_old/30`），检索过滤用**章节距离** —— 两套时间尺度并存 | `writing_skills.py:556-577`（`_cleanup`）vs `:612-633`（`query`） | 改淘汰语义会让**现存数据**被不同方式清理，属数据行为变更，须单独评估 | 当出现"章节推进快但写作间隔长"的真实使用场景，或 `time_memory.json` 达到 `max_memories=1000` 上限时 |
| **R2** | **流式 API 已实现但生产零调用** —— 33 个调用点全走阻塞 `chat()` | `ai_client.py:1223`（`chat_stream` 定义，含多厂商 SSE 适配）vs 全仓 `ai.chat(` 33 处 | 改动面涉及 UI 线程模型（Tk 非线程安全，须经 `async_runner` 回主线程），应作为独立任务 | **立即** —— 这是当前"卡顿"体感的最大来源，详见 `docs/HARDWARE_ACCELERATION_PLAN.md` §3 T2 |
| **R3** | ~~诊断日志不记录 API 耗时~~ → **已修正并实施**：`duration_ms` 字段**一直存在**（`diagnostic_logger.py:130`），出口记录也一直在传（`ai_client.py:945`）。真缺口是 ① **无章节级归因**（`chapter_event()` 存在但生成主流程从不调用，唯一调用者是 EXP 降级分支）② **测试污染真实日志** | `novel_agent.py`（新增 `_PhaseTimer` + `_emit_chapter_timing`）；`diagnostic_logger.py`（新增 `resolve_log_dir()` / `AI_NOVEL_DIAGNOSTIC_DIR` / `reset_logger()`） | ✅ **已完成**：`CHAPTER/chNNNN/complete` 携带 `phases_ms`/`round_trips`/`unaccounted_ms`；测试实现在临时目录 | 已达成的验收：`scripts/verify_chapter_timing.py`（注入延迟对账，实测偏差 ≤ 2 ms） |
| **R5** | **真实生成基线尚未采集** —— 观测能力已就绪，但还没有一份真实章节的段耗时样本 | 诊断日志 `CHAPTER/*/complete` | 需要用户实际跑一次生成（本会话无法代跑真实 API） | **立即** —— 跑 1 章后即可回答"这一章慢在哪"，也是 T2 流式改造的前后对比基准 |
| **R4** | `agent_orchestrator` 的 `ThreadPoolExecutor(max_workers=3)` 是否正确/必要**未验证** | `agent_orchestrator.py:19` | 它与 `novel_agent.generate_with_collaboration` 是**两条不同入口**，本轮未厘清二者关系 | 需要梳理 Agent 编排入口时 |

> **R2–R4 来自 2026-09-17 的硬件加速方案调研**（`docs/HARDWARE_ACCELERATION_PLAN.md`）。
> 该调研的一个副产物是**否定了"给本项目上 GPU 加速"这一前提**：实测单章生成链
> 只有 3 段出网且严格串行，本地计算占比极低 ⇒ **GPU 对主流程几乎无收益**。
> 真正该先做的是 R3（补耗时观测）+ R2（流式上主流程），两者都不需要 GPU。
>
> **R3 的修正值得单独记一笔**：本文件原先写的是"日志里没有耗时字段，要在 `ai_client`
> 铺垫计时"。实施时读源码发现**字段和调用都早就有了**，只是记的不是我们需要的粒度。
> 凭印象登记缺陷会造出一批不需要的改动，同时漏掉真正该改的地方 ——
> 登记缺陷时也要给出**可验证的判据**（"跑一次生成，日志里能否查到分段耗时"），
> 而不是给出一个印象。

---

## 6. 执行顺序（按"风险从低到高"）

> **✅ 全部 10 步已执行完毕（截至第二十二轮）。** 原表保留作为**执行档案**，
> 每步补记"实际落地位置"。**不要把它当待办清单看** —— 待办请只看 §2.1 与 §5.6。

| # | 事项 | 状态 | 实际落地 |
|---|---|---|---|
| 1 | `character_system.py:705-712` — 最小、最弱、无修复无捕获 → 换 + 守卫 | ✅ | `character_system.py:714` → `parse_json_response(response, None)`；守卫 `test_parse_convergence_extended.py:135` |
| 2 | `character_ui.py:166-169` — 需 `is_list=True` + `str` 过滤（**不能裸换**） | ✅ | `character_ui.py:170-171`；守卫 `:140` |
| 3 | `novel_agent.py:735-784` — dict，策略对齐 → 换 + 守卫 | ✅ | `novel_agent.py:1816`（`_plot_designer_analyze`）；守卫 `:149` |
| 4 | `generation_ui.py:862-904` — dict → 换 + 守卫 | ✅ | `generation_ui.py:854`，**保留** `:856-869` decisions 定点抽取；守卫 `:161` + `:165` |
| 5 | `generation_ui.py:1763-1773` — list，需 `is_list=True` → 换 + 守卫 | ✅ | `generation_ui.py:1732`，**顺带修掉 `UnboundLocalError`** |
| 6 | `novel_agent.py:1790-1878` — 保留字段抽取策略，仅收敛策略 1/2/3 → 换 + 守卫 | ✅ | `novel_agent.py:1816` + **保留** `:1818-1821` Strategy 4；守卫 `:156` |
| 7 | `P-04`：把真信号传进 `learn_from_chapter`，去掉硬编码 `True` | ✅ | `novel_agent.py:1716-1718`；另修 P-04b / P-04c |
| 8 | `writing_skills.py:672` 让 `get_writing_context` 用上 `chapter`；`query()` 加时间衰减 | ✅ | `writing_skills.py:722 / :729 / :738 / :612-633`；**遗留 R1 见 §5.6** |
| 9 | `D5` 接上 `save_report`；`D3` 接上 `_toggle_ai`（或明确删除） | ✅ | `shell_ui.py:1205`（接上）；`fullscreen_writer.py:171`（接上）；D4 改为**删除**而非接线 |
| 10 | `O4` 合并重复用例（按族分块做，每块单独验证） | ✅ | **实删 82 条 + 16 空壳类**（非估算的 96），见 §3.1 / §3.2 |

> 每一步都已遵守：改前跑相关测试 → 改后跑同批 → 加守卫。

### 6.1 第二十二轮新增（已执行）

| # | 事项 | 产出 | 验证 |
|---|---|---|---|
| 11 | **覆盖率阈值门禁**（此前覆盖率可任意下降而无人拦截） | `scripts/check_coverage.py`；阈值唯一权威 = `pyproject.toml` 的 `fail_under = 73`；CI 增加阻断式 `Coverage gate` 步骤 | `tests/test_coverage_gate.py`（12 条）；反证三例：阈值 90 ⇒ exit 1 / 阈值 10 ⇒ ratchet 触发 exit 1 / 阈值 10 + `--no-ratchet` ⇒ exit 0 |
| 12 | **`BACKLOG_REGISTER.md` 文档漂移收口**（本文件） | §2 由"确认未修复"改为"已结案"；§5.1–5.4 补落地证据；§5.5 维持观察项；新增 §2.1（C1）、§5.6（R1） | 全部条目附 `文件:行号`，可 grep 复核 |

---

## 7. 验证方式

| 层次 | 命令 |
|---|---|
| 解析层 | `pytest tests/test_parsing.py tests/test_parser_convergence.py tests/test_parse_convergence_extended.py` |
| Agent 层 | `pytest tests/test_novel_agent_*.py`（分文件跑，避免删档守卫） |
| 学习层 | `pytest tests/test_writing_skills*.py` |
| 界面层（若动 D3/D4） | `pytest tests/test_panel_ui_quality.py` |
| 接线层（D3/D4/D5） | `pytest tests/test_wiring_guards.py` |
| **覆盖率门禁** | `pytest tests/ backend/tests/ --cov=app --cov-report=json && python scripts/check_coverage.py` |
| 静态 | `ruff check app/ tests/ scripts/` + `ruff format --check app/ tests/ scripts/` |

⚠️ 沙箱删档守卫阈值 50 路径 / 整轮累计 ⇒ **大套件必须拆块，且越早跑越好**。
判据：堆栈含 `shim\sitecustomize.py` 或 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 即环境伪报。

---

## 8. 覆盖率口径（第二十二轮新增，**数字有疑问时只看这一节**）

| 跑法 | 实测 | 可信度 |
|---|---|---|
| **单进程全量**：`pytest tests/ backend/tests/ --cov=app` | **74.56%**（9384 语句 / 2387 未覆盖） | ✅ **唯一权威**，阈值 `fail_under = 73` 由此而定 |
| 分块跑（沙箱删档守卫所迫，被迫拆多次） | 40.7% | ❌ **严重低估**，只因**分块跑只统计"被 import 过的模块"** |

> ❗ **先前的 40.7% 曾被误当作真实值。** 它不是"覆盖率低"，而是"没被测到的模块根本没进分母"。
> 任何引用覆盖率数字的讨论，**必须以单进程结果为准**；分块跑只能用于"测试是否通过"，
> **不能用于"覆盖率是多少"**。这条差异已写进 `pyproject.toml` 的注释与 `CHANGELOG.md`。

**当前最大覆盖缺口 Top 3**（单进程口径，供 C1 之外的工作参考）：

| 文件 | 未覆盖行 | 覆盖率 |
|---|---|---|
| `app/cloud_storage.py` | **404** | 17.4% ← 已登记为 **C1**（§2.1） |
| `app/character_system.py` | 288 | 46.4% |
| `app/ai_settings_ui.py` | 280 | 13.0% |
