# 更新日志

> 版本号单一权威源为 `pyproject.toml`，`app.__version__` 与 README 均与之一致
> （由 `tests/test_version_consistency.py` 守护）。

## 未发布（候选版本 v3.2.0）

> 已进入 `main`，**尚未随发布打包**（最新发布仍是 v3.1.0 的 EXE）。
> 按仓库流程，打 `v3.2.0` 标签时本节即成为该版本的更新日志。

### 新增

**单章生成的段级耗时归因（可观测性打底）**
- `generate_with_collaboration` 现在给每个 Phase 打点，收尾发一条
  `CHAPTER/chNNNN/complete`，含 `total_ms` / `phases_ms`（各段毫秒）/
  `round_trips`（**只数真的出网的阶段**）/ `unaccounted_ms` / `revision_rounds`。
- 新增 `_PhaseTimer`（`app/novel_agent.py`）：同名阶段**累加**（审校跑 2 轮合成一段），
  `calls` 保留逐次明细。用 `time.perf_counter` 而非 `time.time`。
- **`round_trips` 不按 Agent 数量数**：`world_build` 与 `context` 都不出网
  （`_world_builder_build` 只读本地 settings 就返回）⇒ 单章实际 3–9 次往返。
  按"5 个 Agent"推断会直接误导优化方向，故把出网阶段提升为常量 `_NETWORK_PHASES`。
- 新增 `scripts/verify_chapter_timing.py`：用假 `AIClient` **注入已知延迟**，
  对账"日志记录值 vs 实际注入值"。实测四段偏差 ≤ 2 ms、未归因余量 0.12 ms。

**测试诊断日志与真实使用日志隔离**
- `DiagnosticLogger` 的目录此前**硬编码** `~/.ai_novel_writer/diagnostic_logs`，
  而 `ai_client`/`generation_ui`/`novel_agent` 都在**模块级**建单例
  ⇒ 测试与真实使用写进同一个文件。实测后果：连续 3 天 3126 条 `API_CALL`
  **全是同一份测试指纹**，而真实生成才会产生的 `CHAPTER` 事件 **0 条**。
- 新增 `resolve_log_dir()` 与环境变量 `AI_NOVEL_DIAGNOSTIC_DIR`；
  `tests/conftest.py` 在**模块级**（早于任何 `app.*` 导入）指向临时目录。
- `shell_ui`（性能报告）与 `toolkit_ui`（面板注册记录）两处**各自硬编码**的目录
  一并收口到 `resolve_log_dir()` —— 否则隔离只对 `.jsonl` 生效，这两处仍会漏回真实目录。
- 新增 `reset_logger()`：单例一旦建立就忽略后续 `log_dir`，切目录必须显式重置。

**面板布局可配置：分栏与停靠记忆**
- 选择器末行新增「布局」控件：**单栏 / 分栏**切换 + **右栏**面板选择。
  分栏后内容区左右各放一个面板，分隔条可拖动。
- **停靠记忆**：布局（模式、两个栏各放谁、分隔条比例、哪些面板已脱出为独立窗口）
  记忆到 `~/.ai_novel_writer/panel_layout.json`，下次启动自动恢复。
- 进入分栏时自动挑一个右栏面板，**优先同分组**（并排看的通常是同一类工作，
  如"世界线与时间线 + 角色传记"）。
- 三种形态共用同一份外壳代码：面板可以**在栏里、在独立窗口里、或单栏显示**，
  面包屑/状态栏/快捷键始终一致。

**自我学习的"信号"从假变真**
- 「自我学习」此前实测是 **L0（只写不读）**，三个断点各有明确位置：
  **信号假**（`finalize_chapter` 的 `success=True` 硬编码，而 `if success:` 包住全部学习逻辑
  ⇒ 形参等于没有，负样本永远进不来）、**内容贫**（只写 `success_pattern`、权重恒 0.6）、
  **读不到**（`get_writing_context` 完全忽略自己的 `chapter` 形参；`query()` 无时间维度）。
- `finalize_chapter` / `learn_from_chapter` 新增 `quality` 形参：评审得到的真实分数
  经实例属性 `last_chapter_quality` 传入并按 `QUALITY_THRESHOLD` 判定 `success`，
  **权重随评分浮动**（60 分→0.5，100 分→0.9）。
  未拿到评分时（编辑器 / 全屏写作两条定稿路径）行为与旧版一致，按成功处理。
- `success_pattern` 从"写完全仓无人读"变为**真的被回灌**：`get_writing_context`
  新增「近期成功模式」段，按章节窗口取最近的高分经验。
- `TimeAwareMemory.query` 新增 `chapter` / `chapter_window`：可按"距今章节数"过滤与排序
  （未标注章节的旧数据**不参与过滤**，避免静默清空）。

**待办与缺陷登记册与三项决策结案**
- 新增 `docs/BACKLOG_REGISTER.md`：把散在 33 份文档里的遗留项按
  **每条带可复核证据**（文件:行号）重新登记，分「已修复(文档仍标未处理)」
  「确认未修复」「需决策」三类，并记明与旧文档不一致之处
  （例：`FEATURE_VALUE_ASSESSMENT.md` 说 `diagnostic_logger`/`memory_manager`
  是重复测试重灾区，实测**两者都是 0**，真正的重复量在 `novel_agent` 66 条 + `reading_manager` 23 条）。
- 三项待决策**全部结案**（详见该文件 §4）：**M1** 六个历史标签保持原状只记录
  （它们发布过，按仓库纪律不满足重指条件；重指理由见 `RELEASE_HISTORY_NOTES.md §3.1`）；
  **M2** `mobile-app/webview-app` 保留并补归档 README（不删除）；
  **M3** `backend/` 冻结 —— 只接缺陷与安全补丁，附可执行的边界表与解冻条件。

### 变更

**弹窗调用统一收口到 `app/dialogs.py`**
- `app/` 下 **215 处** `messagebox.*` 调用（散落在 25 个文件、每个文件各自
  `from tkinter import messagebox`）全部改走 `app/dialogs.py`。
- 新增与 `messagebox` **同签名**的一层（`showinfo` / `showwarning` / `showerror` / `askyesno`），
  迁移因此是"只换前缀"的等值替换；另提供语义化的 `info` / `warn` / `error` / `confirm`。
- 新增**静默开关** `dialogs.set_silent(True)` / `dialogs.silent_modals()`：
  自动化脚本不必再 monkeypatch `tkinter.messagebox` 的内部属性
  （实测漏打一个 `askinteger` 就被模态弹窗卡住 14 分钟）。
- 门禁：`tests/test_dialogs.py` 断言业务代码**不得**再直接调用 `messagebox`
  （用 tokenize 判定，不误伤 docstring 里的政策说明）。

### 修复

**JSON 解析器全面收敛（6 处手写实现 → 单一权威）**
- `app/parsing.py` 的 `parse_json_response` 本就是唯一实现，但另有 **6 处各自手写解析**：
  `character_system.ai_create_character`（**最弱**：`json.loads(切片)` 无 try/except、无尾逗号修复）、
  `character_ui._auto_detect_characters`（字符串数组）、
  `novel_agent._plot_designer_analyze`、`generation_ui._auto_detect_decisions`、
  `generation_ui._auto_generate`（列表）、`novel_agent._update_character_progression`。
  `novel_agent` + `generation_ui` 合计约 250 行重复的 JSON 修复机器。
- 收敛后**每处解析失败都少丢一次数据**：旧实现拿到带全角冒号（`{"a"：1}`）或
  尾逗号、markdown 围栏的响应会直接放弃（跳角色成长 / 跳大纲批量更新 / 跳新角色识别）。
- `generation_ui._auto_generate` 顺手修掉一个**潜在 `UnboundLocalError`**：
  旧写法在 `re.search` 未命中时不会给 `new_batch` 赋值，而紧接着就 `if new_batch:`。
- 两处**统一解析器覆盖不到**的策略有意保留：`"decisions"` 数组定点抽取、
  `"updates"` 逐字段抽取（针对"AI 返回大段思考文本 + 夹着不合法数组"的极端情况）。

**`parse_json_response` 的候选优先级缺陷（本轮由收敛暴露）**
- 旧实现把"修复版本"**整体追加到所有原文之后**，使优先级失效。实测回归：
  `{"type":"action",...,"foreshadowing":[],}`（尾逗号）期望 dict 时，候选顺序是
  `[{..,}(失败), [](成功!), 修复1, 修复2]` ⇒ **返回了内嵌的空数组**，
  而调用方按 dict 使用。现改为"每个原文紧跟自己的两个修复版本"。
- 同一修复顺带解决 markdown 围栏响应返回 `None` 的问题。

**"注册即遗忘"三处（功能建好却没人调用）**
- **D3**：`FullscreenWriter._toggle_ai` 一直存在且正确，`ai_assist_enabled`
  也有三处消费（决定是否给提示、状态栏、配置持久化），但**没有任何控件能改它**
  ⇒ 开关永远停在 `True`。工具栏按"打字机"同款补上「AI辅助」复选框，
  并在读回配置时同步复选框状态（否则界面显示与实际生效值不符）。
- **D4**：删除 `UIStyle.create_styled_button/entry/text/listbox` 四个工厂 ——
  `app/`、`tests/`、`scripts/`、`installer/`、`backend/` 五处共 **0 引用**，
  且它们是**第二套视觉来源**（项目已定 `panels/ui_kit.py` 为唯一来源）、
  还绕过字体令牌门禁（用 `(family, size)` 拼字面量）。随之移除不再使用的 `import tkinter`。
- **D5**：`PerformanceMonitor` 一直在 `ai_client` 里**记录**指标，
  但 `save_report()` 全仓零调用 ⇒ 数据只活在内存、进程一退就没。
  现退出时写 `~/.ai_novel_writer/diagnostic_logs/performance-<时间戳>.json`
  （与面板诊断日志同目录）；零请求时不写空文件；保存失败只记日志、不阻止退出。

- `PanedWindow` 的选项集与 `Frame` 不同（没有 `highlightthickness`），
  分栏容器按实际支持的选项构造。
- **比例应用不再用 `after_idle` 自重排**：窗口尚未映射时宽度恒为 1，
  自重排会变成永不结束的空闲循环，`update()` 直接卡死（实测挂住 7 分钟）。
  改为由 `<Configure>` 在拿到真实尺寸时应用**一次**（也避免与用户拖动打架）。
- `scripts/smoke_generators.py` 的仓库根解析：文件在 `scripts/` 下却按
  `Path(__file__).parent / "backend" / ...` 找模块（指向不存在的 `scripts/backend/`）
  ⇒ 自搬入 `scripts/` 起就 `ModuleNotFoundError`，从未跑通过。改为先定位仓库根，现 15/15 通过。

### 工程

**打包产物的依赖完整性校验（新增 `scripts/check_bundle.py`）**
- 背景是本仓库的一个已知陷阱：`app/__init__` 对导入失败**降级为 `_ImportStub`** 而非崩溃，
  于是**缺依赖的 EXE 不报错、只静默丢功能**（发布史上真发生过——release 作业只装
  `pyinstaller loguru`，EXE 里缺 httpx/Pillow/cryptography，程序照常启动）。
  **"构建成功"不等于"功能齐全"**，此前没有任何检查。
- 新脚本解析 `Analysis-00.toc` 核对实际打包内容。判据刻意分三类，因为三者来源不同：
  **直接 import**（从源码推导）/ **传递依赖**（`lxml` 由 python-docx 需要）/
  **声明但未用**（`markdown`、`bs4` 在 `pyproject` 声明但 `app/` 零 import）。
- ❗ 两个踩过的判据陷阱已写进脚本注释：**① 不能用字符串匹配** —— PyInstaller 的 TOC
  typecode 里有一个就叫 `PIL`，会把"有 PIL 这个**标签**"误当成"有 PIL 这个**包**"；
  **② 不能把 `pyproject` 声明当"代码用到"** —— 会把"声明了"报成假缺口。
- 新增 `tests/test_bundle_manifest.py`（13 条）**从源码重新推导清单并对账**，
  清单过期即变红。写它当场就抓出两处错误：`lxml` 被误分类成直接 import、
  `beautifulsoup4` 用发行名当键（会让断言空转）。已验证 `bs4` 是被 lxml 的
  **可选** `html.soupparser` 带进来的。

**「观测能力建了一半」：`duration_ms` 一直存在，但没人记章节分段**
- 排查"运行卡顿"时发现：`DiagnosticLogger.log()` / `api_call()` **都接受 `duration_ms`**，
  `ai_client` 的出口记录也**一直在传**。真正的缺口是 ① 生成主流程从不调用
  `chapter_event()`（全仓唯一调用者是 `generation_ui` 的 **EXP 降级分支**）
  ② 测试日志污染真实日志。**原先登记的缺陷描述是错的，已修正**（见 §5.6 R3）。
- 教训：登记缺陷必须带**可验证的判据**（"跑一次生成，能否查到分段耗时"），
  而不是给一个印象 —— 凭印象登记会造出一批不需要的改动，同时漏掉真正该改的地方。

**测试日志污染：修隔离要连"另外两处硬编码"一起改**
- `shell_ui._flush_performance_report` 与 `toolkit_ui._record_panel_registry`
  **各自**拼了一遍 `~/.ai_novel_writer/diagnostic_logs`。只改 `diagnostic_logger`
  的话，隔离对 `.jsonl` 生效而这两处仍写真实目录 —— 又一处"同一事实写两处必然漂移"。
  已收口到 `resolve_log_dir()`，并加 AST 门禁禁止 `app/` 下再次出现该字面量。
- 门禁初版用**关键字扫描**，把 docstring 里的路径说明误判成硬编码；
  已改为 AST 取"代码中"的字符串字面量，并补两条反证用例（能抓真硬编码、不误报注释）。

**`_emit_chapter_timing` 的异常处理里踩了自己的坑**
- 初版把诊断 logger 绑定到局部名 `logger`，然后异常分支里写 `logger.debug(...)`
  —— `DiagnosticLogger` **没有 `.debug`**，于是"日志失败"被升级成"整章生成失败"。
  这正是要防的那类故障，被自己的守卫测试抓住。已改回模块级 loguru `logger`。

**弹窗静默开关的嵌套语义缺陷**
- `dialogs.silent_modals()` 用 `_silent_depth` 计数，`__exit__` 在深度归零时**无条件**
  `set_silent(False)`。后果：外层已经 `set_silent(True)` 时，内层退出会把**外层也解开**
  —— 自动化脚本的"全局静默"会在第一个 `with` 块结束时失效，后面的模态弹窗真的会弹出来。
- 改为进入时**记住进入前的状态**、退出时**恢复该状态**（而非硬编码 `False`）。
  反证验证：退回旧实现，新加的守卫测试确实失败；恢复后通过。

**自我学习：失败样本整条链路缺失**
- `learn_from_chapter` 只有 `if success:` 分支 —— `success=False` 时**什么都不写**。
  而 `QUALITY_THRESHOLD = 75` 确实可达，等于"写砸的章节从不进入记忆"，
  下回开写时也就没有任何"这里容易翻车"的提示。
- 现补齐 `else` 分支写入 `memory_type="failure_pattern"`，权重随评分下降而上升
  （`max(0.5, min(0.9, 0.5 + (75 - quality) / 100))`，60 分 → 0.65，75 分 → 0.5）。
- `get_writing_context` 相应新增「近期未达标章节（应避开同类问题）」段，
  按章节窗口取最近 3 条回灌 —— 否则写了仍然没人读，等于回到"只写不读"。
- **空/纯空白章节文本**原先会写出 3 条垃圾记忆（实测 `0 → 3`），现在提前 return。
- 角色提及计数原本被包在 `if success:` 里，**失败章节提及的角色不计入** —— 已移出，
  因为"这章写了谁"与"这章写得好不好"无关。
- 注意：记忆条目里存分数的键是 `"type"` 而非 `"memory_type"`（自学习测试写错一次后修正）。

**解析器类型契约：守卫写在所有使用之后**
- 收敛后 `parse_json_response` 的语义是**单向**的：`is_list=True` 拒绝 dict，
  而 `is_list=False` 只**偏好** `{`、**不拒绝**顶层数组。当模型只回一个 JSON 数组时，
  期望 dict 的调用方会拿到 `list`。
- 实测三处受影响：`novel_agent._world_builder_build`（`save_settings(list)` → 崩）、
  `novel_agent.analyze_style`（按 dict 取键）、`_format_settings_md`
  （`settings.items()` → `AttributeError: 'list' object has no attribute 'items'`）。
- 最值得记的是 `novel_agent.generate_with_collaboration`：**守卫存在**，
  但位置在**所有使用点之后**（第 748 行，首次使用在第 695 行）—— 光看 grep 会以为没问题。
  现改为拿到 `review` 后立刻规范化。
- 新增 `tests/test_parse_type_contract.py`（31 条）钉住这些契约，含上述全域元守卫。

**重复测试合并（O4，净删 738 行）**
- 实测普查：`tests/` 里 **81 组函数体完全相同**的用例重复（`novel_agent` 57 组 +
  `reading_manager` 20 组 + `agent_orchestrator` 2 组 + `ai_client` 2 组），
  成因是历次"补覆盖率"时以复制粘贴增文件（`*_mock.py` → `*_deep.py` → `*_full.py` → `*_final.py`）。
- 合并后 **2420 → 2338** 条（删 82 条真重复 + 16 个随之空掉的测试类），12 个文件净删 738 行。
- **判据分三层，只删"删掉后不可能少测任何东西"的份数**：
  ① 同体 + **同类名** + 同函数名（17 组）自动删除；
  ② 同体 + **异类名**但 `setUp` 绑定同一被测目标（64 组）复核后删除；
  ③ **同体 + 异类名 + 绑定不同目标（1 组）⇒ 保留**。
- 第 ③ 类实例：`test_novel_toolkit.py` 里 `TestElementLibrary` / `TestBridgeLibrary` /
  `TestDescriptionLibrary` 三个类的 `test_get_categories` **一字不差**，
  但 `self.lib` 分别是三个不同的库 —— 同体纯属巧合，删了就真丢覆盖。
  已写入合并脚本的 `KNOWN_FALSE_POSITIVES` 白名单，重跑时会**主动跳过并打印**。
- 新增三个脚本：`scripts/dup_test_census.py`（普查）、
  `scripts/review_dup_candidates.py`（候选复核报告，对比各类 `setUp` 绑定的目标）、
  `scripts/dedup_tests.py`（执行合并，带语法自检与假重复白名单）。

- 新增测试：`tests/test_panel_layout.py`（43 条）、`tests/test_dialogs.py`（23 条）、
  `tests/test_parse_convergence_extended.py`（16 条）、`tests/test_self_learning_loop.py`（20 条）、
  `tests/test_parse_type_contract.py`（31 条）、`tests/test_wiring_guards.py`（12 条）。
- 新增的收敛/接线守卫沿用既有模式：**剔除注释与文档字符串后**做源码级断言，
  并**排除测试文件自身**（本文件列举了被删方法名，直接扫原文必然自报假阳性）。
- 总计 **2483 条测试**（桌面端 2355 + 后端 128）→ 合并前为 2548；差额即本轮删除的重复。

**六轮「测试 → 发现 → 修复 → 回归」迭代（R21）**
- 用四个探针脚本（`scripts/boundary_probe.py`、`iteration_probe2.py`、`iteration_probe3.py`、
  `scripts/dup_test_census.py`）反复打主要路径与边界，**每轮都真的抓到了缺陷**：
  | 轮次 | 抓到的缺陷 | 性质 |
  |---|---|---|
  | 1–3 | 重复合并脚本自身三处错误 | 工具缺陷（已回滚重做 + 加语法自检） |
  | 4 | `dialogs.silent_modals` 退出时**丢掉外层的静默状态** | 真缺陷（嵌套静默被内层解开） |
  | 5 | 自学习：**失败章节什么都不写**、空文本**写入垃圾记忆** | 真缺陷（学习回路断一半） |
  | 5 | 解析器**类型契约**：3 处调用方收到 `list` 会崩或静默丢数据 | 真缺陷（其中 1 处是"守卫写在所有使用之后"） |
  | 6 | 事件总线 / 布局往返 / 弹窗门禁 / 版本权威 / 根文档 / 字体门禁 | 全部通过，无新缺陷 |
- **每处真缺陷都用「反证」验证过**：临时把修复退回去，确认守卫测试**确实转红**，再恢复。
  否则无法排除"测试恒绿、其实什么都没测"。
- 新增 `tests/test_parse_type_contract.py` 的**全域元守卫**：它扫描 `parse_json_response`
  的**每一个**调用点，要求"要么旁边有 `isinstance` 守卫、要么是薄转发、要么立刻 return"。
  价值在于它会拦住**将来新加的**未守卫调用点 —— 这是一条测试，胜过 N 条逐点测试。
- 6 轮结束后全量回归：桌面端 **2348 通过 / 0 失败**，后端 **128 通过**，
  `ruff check` 与 `ruff format --check`（178 文件）全绿。

- 截图：`docs/ui_review/after_12_single_mode.png` → `after_15_back_to_single.png`
  （分栏前 → 分栏 → 调整比例与右栏 → 收回；**收回后的截图与分栏前字节完全相同**）。

**覆盖率阈值门禁（此前覆盖率可任意下降而无人拦截）**
- 缺口有两处，任一处都足以让"覆盖率"沦为没人看的报告：
  ① `[tool.coverage.report]` **没有 `fail_under`**；
  ② CI 的 codecov 步骤写了 `fail_ci_if_error: false` —— 连上传失败都不拦。
- 新增 `scripts/check_coverage.py` 承担判定。**阈值只在 `pyproject.toml` 定义一处**，
  脚本与 CI 都从那里读（不在 workflow 里再写一个数字 —— 否则就是"同一事实写两处"，本项目已踩三次）。
  门禁本身有一条守卫测试：CI 中**不得**出现 `--cov-fail-under`（它会绕过 pyproject 制造第二个真相源）。
- 阈值是**双向**的：低于 `fail_under` 失败（防下滑）；高于 `fail_under + 2` 也失败并提示收紧
  （防"真实覆盖率涨了但阈值不动"，那样门禁会慢慢退化成橡皮图章）。
  `--no-ratchet` 只关上限、不关下限；`--update` 可把当前实测值直接写回 `pyproject.toml`。
- **基线必须单进程测**：`pytest tests/ backend/tests/ --cov=app` 实测 **74.56%**
  （9384 语句 / 2387 未覆盖）。⚠️ 本项目常用的**分块跑**（沙箱删档守卫所迫）只测出 **40.7%**，
  是严重低估 —— 因为分块跑只能统计"被跑到的模块"。**阈值取 73**，留约 1.5 个百分点缓冲。
  （先取 72，随即被 ratchet 反向检查提示"涨了该收紧"，于是上调 —— 这条检查自证有效。）
- ❗ 过程中踩到 `coverage report` **没有 `-q` 选项**：误加会得到 `no such option: -q`
  且退出码为 1，**看起来像"门禁失败"实际是"命令没跑"**。这也是不用
  `--fail-under` 裸判定、而改为读 JSON 报告的原因之一（失败时还能打印差值与拖累文件）。
- 新增 `tests/test_coverage_gate.py`（12 条）：覆盖正反两向判定、`--no-ratchet` 语义、
  以及**三条异常路径必须明确报错而非静默放行**（报告缺失 / 阈值缺失 / 报告无 totals）。
  反证已做：阈值高于实测 ⇒ exit 1；阈值远低于实测 ⇒ exit 1；`--no-ratchet` ⇒ 放行上限但下限仍拦。

**`docs/BACKLOG_REGISTER.md` 文档漂移收口（登记册落后代码整整两轮）**
- **症状**：该文件 §2 标题是「确认未修复（带证据）」，表里列着 D3 / D4 / D5 / O4 / P-04 ——
  但这 5 条在第二十、二十一轮**就全部修完了**。于是出现最坏的情况：
  **读登记册的人会以为还有 5 个未修缺陷，而实际一个都没有**。
- **不采用"逐条加『已修复』标记"的修法**：那只是让漂移再延后一轮。改为**把该表直接改写成结案表**，
  每条给「当时判断 → 现在实测」两列并附 `文件:行号`，让差异落在哪一行代码上一眼可见。
  标题同步改为「已结案（第二十二轮复核：原『确认未修复』6 条全部落地）」。
- **逐条实测证据**（均可 grep 复核）：
  D3 → `fullscreen_writer.py:171` 有 `command=self._toggle_ai`；
  D4 → `ui_style.py:407` 注释记录四个工厂**已删除**（改"删除"而非"接线"）；
  D5 → `shell_ui.py:1205` 调用 `monitor.save_report(...)`；
  D7 → `mobile-app/webview-app/README.md` 首行即「已归档（不再维护）」；
  O4 → 实删 82 条 + 16 空壳类（2420 → 2338）；
  P-04 → `novel_agent.py:1716-1718` 用真实评分判 `success`（不再硬编码 `True`）。
- §5.1–5.4 补落地证据（六处解析器收敛逐处列出**保底策略是否保留**；
  §5.2 的守卫缺口已由 `tests/test_parse_convergence_extended.py` 补齐，含两条**反向**断言
  「保底策略必须仍在」—— 它拦的是"有人顺手把保底删了"这种不会让测试变红的静默退化）。
- §5.4 复核结论**推翻原判**：`CharacterSystem` **不是死代码**。
  当时只 grep 了方法名，没注意到 `character_ui.py` 有五处 `CharacterSystem(...)` 实例化、
  `timeline_ui.py:702` 的分支角色读取也走它。**教训：判死代码必须同时搜类名 / 属性名 / 方法名。**
- §5.5（`parse_exp_json` 内部发散）**维持观察项**：它带 `_normalize_exp_entries` /
  `_safe_exp_int` 专门语义，与 `parse_json_response` **职责不同**，不属"同一件事写六遍"，
  不收敛是正确的。
- §6「执行顺序」10 步全部标注为已执行并补「实际落地位置」；
  §7 增加覆盖率门禁与接线层两道验证命令；新增 **§8 覆盖率口径**，
  明确「分块跑 40.7% 是低估、单进程 74.56% 才是权威」，并列出当前最大缺口 Top 3。
- **新登记 2 条**（本轮唯一开着的项）：
  **C1** `app/cloud_storage.py` **零测试覆盖**（404 行未覆盖 / 17.4%，占全仓未覆盖行的 16.9%；
  全仓测试目录 grep 该模块名 **0 命中**）。定 P1 —— 其余低覆盖文件是**逻辑正确性**风险，
  而它含 `_require_secure_url`（拒绝非 loopback 的 `http://`）、`_safe_error`（脱敏密钥）、
  加密凭据存取，属**安全边界**风险：**一个从未被执行过的拒绝分支，与"没有这个分支"在可观测层面无法区分**。
  本轮**不实施**（需为五个网盘 provider 补一整套 mock，工作量与风险都远超"收口文档"）。
  **R1** 记忆淘汰按**自然日**（`_cleanup`）、检索按**章节距离**（`query`），两套时间尺度并存，
  长期不写作但章节推进快的项目里记忆可能先被按天数淘汰 ⇒ 章节窗口形同虚设；改动会变更数据行为，单独立项。

**硬件加速方案调研（`docs/HARDWARE_ACCELERATION_PLAN.md`，新增）**

- 起因：用户反馈「应用卡顿、优化较差」，考虑调用主机 GPU/CPU。调研结论是
  **先否定了"上 GPU"这个前提** —— 实测单章生成链只有 3 段出网且严格串行，
  本地计算占比极低，GPU 对主流程几乎无收益。
- **硬件实测**：i5-12490F（12 逻辑核）+ **RTX 3080（10240 MiB，驱动 610.47）**；
  Ollama 已装 3 个模型共 **27 GB**（`darkidol-8b` 16.07 / `qwen3.6-35b` 11.66 / `qwen3.6-35b-vision` 12.56）。
  ❗ **三个模型没有一个能装进 10 GB 显存** ⇒ 直接切 Ollama 会溢出到内存，**比云端更慢**。
- **AST 实测各段出网次数**（`novel_agent.py`）：`_plot_designer_analyze` 1 次、
  `_writer_generate` 1 次、`_reviewer_evaluate` 1 次（每轮必发）、`_writer_revise` 1 次（不达标才发）；
  而 **`_world_builder_build` 与 `_build_context` 均为 0 次**（不发网络请求）。
  ⇒ 单章实际 **3–9 次往返**（`MAX_REVISION_ROUNDS = 3` / `QUALITY_THRESHOLD = 75`），
  **不是"5 个 Agent 各一次"**。
- 🔴 **本方案推翻了自身的一个结论**：原以为 PlotDesigner 与 WorldBuilder 可并发省一次往返。
  AST 实测 `_world_builder_build`（`:790-799`）**根本不发请求**（只读本地 settings 就返回，
  且收着的 `plot_analysis` 形参从未被使用），出网 3 段严格串行 ⇒ **无可并行项，该方案作废**。
  教训：判"哪几段出网/能否并行"**不能看方法名或 Agent 数量**，必须用 AST 数调用点。
- **真正该先做的两件（都不需要 GPU）**：
  **R3** 给 `API_CALL` 事件补 `duration_ms` —— 当前诊断日志**完全没有耗时字段**，
  卡顿无法归因，不做这一步后续优化全是猜；
  **R2** 把已实现但**生产零调用**的 `chat_stream()`（`ai_client.py:1223`，含多厂商 SSE 适配）
  接到主流程 —— 33 个调用点全走阻塞 `chat()`，这是"卡顿"体感的最大来源。
  ⚠️ 诚实说明：流式**不减少总耗时**，改的是**感知延迟**（首字 秒级 → <1 s + 可中断），
  而对"卡顿"这类抱怨，感知延迟往往才是主因。
- **明确不建议**：装 torch（本项目无本地张量计算可加速）、用 GPU 加速 Tk 界面
  （Tk 走 CPU 绘制，界面卡顿根因是主线程被网络 I/O 阻塞）、多进程替代多线程
  （瓶颈是网络等待不是 CPU）。GPU 唯一合理位置是 **T5 混合路由** ——
  低价值高频辅助任务（摘要/角色名抽取/格式转换）走本地 7–8B Q4，正文创作仍用云端大模型。
- 登记 **R2 / R3 / R4** 到 `BACKLOG_REGISTER.md §5.6`。

## v3.1.0 (2026-09-17)

**本次发布的定位**：P5（样式与对话框收敛）收尾 + 面板可脱离为独立窗口。
产品行为**向后兼容**，故为 MINOR 版本。

### 新增

**面板脱离为独立窗口（P5 收尾）**
- 任何面板都可以离开宿主区、放进自己的窗口：面包屑右上角「独立窗口」按钮；
  宿主区改为显示说明与「收回面板」入口（`PanelHost.pop_out` / `pop_in` / `toggle_pop_out`）。
- 关闭那个窗口即自动收回面板；重复弹出复用既有窗口（不会开出两个）。
- 窗口里的面板**照常刷新**：`F5` / 刷新按钮在窗口内重建，不会被搬回主界面。
- 切换作品时，已脱离的面板**同步重建** —— 它们不走 `select()`，不单独处理会一直显示上一本书的数据。
- 退出应用时统一关闭这些窗口：独立顶层窗口不随主窗口销毁，漏关会把进程拖在后台。
- 形态说明：Tk 控件不能改父，因此"换容器"实现为**销毁 + 重建**（与 `refresh()` 同一套动作），
  由此保证同一面板**同时只活在一个容器**里，不会出现两份控件争同一份状态。

### 变更

**字体令牌化收尾（P5）**
- `app/` 下 **385 处硬编码字体元组、25 个文件全部迁移**到 `UIStyle.font(<角色>)`，
  `HARDCODED_FONT_BASELINE` 清空，棘轮收紧为「全仓不得再有字面量」。
  之所以能机械完成：385 处只对应 **21 种取值**，其中 15 种已有令牌（覆盖 375 处），
  补齐 6 个角色后剩余替换全部是**等值替换**（逐条断言令牌值 == 原字面量）。
- **零视觉变化已实证**：把迁移暂存/恢复、在同一显示状态下对两版代码截图，**逐像素 MAD = 0.000**。
- `ruff format --check` 的检查范围从 `app/ tests/` 扩到包含 `scripts/`。

### 修复

- **导入环**：`app/fullscreen_writer.py` 里的 `from app import UIStyle` 与 `app/__init__` 的
  早导入构成循环，而 `app/__init__` 对导入失败是**降级为导入桩而非崩溃** ⇒ 该类会静默失去
  字体角色能力。改为从 `app.ui_style` 直接导入。新增 `tests/test_import_health.py`（81 条）
  断言所有子模块可干净导入、且没有任何名字被降级成桩。
- 迁移脚本自身的第一版曾把 25 个文件全部写坏（`ast` 的 `col_offset` 是 **UTF-8 字节偏移**，
  按字符切片会在含中文的行上切错位），已回退重写。

### 文档与仓库

- `CHANGELOG.md` 补记 **v2.13.2 / v2.12.1 / v2.7.0** 三个版本的条目（此前有标签无条目），
  每条均标注为补记且只写标签提交可核实的内容。
- 新增 `docs/RELEASE_HISTORY_NOTES.md`：如实记录早年打标签的事故
  （多个标签指向同一提交等），说明为什么**不做**历史重写。
- `docs/NEXT_STEPS.md`：结清 `chapter_analysis` 面板「构建失败」的旧记录
  ——真相是该 key 不存在（面板登记为 `chapters`），面板本身正常，是截图脚本用错了 key。

## v3.0.0 (2026-09-17)

**本次发布的定位**：v3「面板化 · 多 API · 去重」主线的首个正式版本。
条目范围**仅覆盖 v3 主线新增内容**——巨石拆分、安全修复、CI 合并等已在 v2.16.0 条目内记录，
此处不重复（那些提交虽在 `v2.16.0..v3.0.0` 区间内，但 `v2.16.0` 标签创建于 2026-07-03，
条目后来补记了 9 月的工作）。

### 新增

**面板框架与事件总线（P4a / P4b）**
- 新增 `app/panels/`：`base`（面板契约）· `registry`（注册表）· `legacy`（v2 面板迁移适配器）·
  `host`（容器与生命周期）· `ui_kit`（统一视觉组件库）。
- 新增 `app/events/`：线程感知事件总线（9 个主题 + 通配订阅），事件**只在写盘成功后**广播。
- 12 个 v2 功能面板一次性迁移到新框架，**且新增面板从"改 12 处"缩减为"注册表加 1 行"**：
  `toolkit_ui` 的 12 路 `elif` 与 `shell_ui` 的 12 个单选钮已删除，改由注册表渲染。
- 新增三个一等面板：
  - **世界线与时间线**：章节轴 / 世界线·分支 / 人物轨迹 / 跨代编年史四视图；
  - **角色传记**：结构化传记（分段 / 故事线 / 来源 / 模型 / token 归因）+ 导出；
  - **世代传承**：代际树、继承计划、未解伏笔继承报告。

**多 API 底座（P2 / P3）**
- 新增 `app/providers/`：Provider 注册表 + 适配器（`openai_compat` / `anthropic` / `ollama`）+
  `pricing`（分档价目表）· `balance`（余额查询）· `reasoning`（推理模型适配）。
- 新增 `app/usage_tracker.py` · `app/token_estimator.py` · `app/async_runner.py` · `app/usage_ui.py`：
  token 归因与持久化、成本估算（汉字 ×1.6 + 非汉字 ÷4，带 `estimated` 标记）、用量面板。
- 新增多套 API Profile 配置（`app/ai_settings_ui.py`），支持按 provider 独立保存密钥与地址。

**数据与存储**
- 新增 `app/timeline_store.py`：时间线**统一存储**，读取按文件指纹缓存、`os.scandir` 枚举、
  `snapshot()` 一次取数返回四视图。实测（1094 章 / 300 角色）：刷新 48 → **14** 次读盘、68 → **22.6** ms。
- 新增 `app/lineage.py`：世代传承与**子代只读父代**护栏（`guard_child_path` 为唯一强制点）。
- 新增 `app/novel_store.py` · `app/storage.py` · `app/biography.py` · `app/character_system.py` ·
  `app/live_data.py` · `app/format_converter.py` · `app/dialogs.py`。

**分支子项目**
- `timelines/branch_%03d/` 此前"只写不读"：现在分支进**代际树**、可**双击作为作品打开**，
  并补齐 `meta.json` 的 `title` / `lineage`。分支与父代**属同一代**（另一条世界线），
  但 `child_scope=readonly_parent` 依然成立——写入分支内部允许、**逃逸到父代被拒**。

### 变更

**面板 UI/UX 系统化改造**
- 调色板：`text_muted` 对比度 2.68:1 → **4.54:1**；新增 `accent_text / success_text / info_text /
  error_text / warning_text` 文字变体（基色保留为填充色，避免白字按钮失效）。
- 宿主统一外壳：每个面板自动获得**面包屑 + 刷新按钮 + 状态栏 + F5 / Ctrl+F / Esc**。
- 表格统一 `Panel.Treeview`：28px 行高、斑马纹、表头点击排序、Enter 等效双击。
- 迁移面板统一 `polish_legacy` 换肤（只改外观、不动布局，有测试守 `pack_info` 不变）。
- 实测：最差文字对比度 2.68 → **4.51**；对比度违规 15/15 面板 → **0**；统一外壳 0 → **15/15**；
  表格统一样式 0/7 → **7/7**；F5 绑定 0 → **15/15**。

**样式与工程治理**
- 新增字体角色令牌 `UIStyle.FONT_ROLES` 与**棘轮测试**（`test_font_token_ratchet.py`），
  把 385 处硬编码字体的迁移从"大爆炸"改为"只减不增"。
- 全仓一次性 `ruff format`（151 文件达标），并把格式检查转为 CI **阻断项**。
- 新增数据护栏基线（`test_data_safety_baseline.py`）与面板 UI 质量门禁
  （`test_panel_ui_quality.py`，35 条）。

### 修复

- **面板重复渲染**：`refresh()` 重建外壳前未销毁旧子控件，导致打开/切换小说或按 F5 时
  面包屑与内容叠成两份 → 现先 `destroy` 再重建（顺带自愈半成品外壳）。
- **KPI 卡片永远显示占位符**：数值 Label 靠 `cget("font")` 比对定位，而它返回 Tcl 字体名，
  与元组永不相等 → 改为由 `kpi_row` 直接交出数值 Label。
- **迁移面板切走再切回"掉皮"**：v2 的 `on_show()` 会重建内容而润色只跑一次 →
  现于 `on_show` 后为迁移面板重跑 `polish_legacy`。
- **大片米色控件**：`tk.Listbox` / `tk.Scrollbar` 未配色、v2 的 ttk 控件未指定 style
  （退回 clam 默认浅色）→ 统一映射到深色风格；Combobox 弹出列表经 option 数据库着色。
- **面板模块导入失败静默**：windowed EXE 无控制台，失败此前完全不可见 →
  记入 `registry.LOAD_FAILURES` 并写入磁盘诊断日志，可事后核对。
- 修复 `ttk.Combobox` 被 `tk.Entry` 分支截胡（继承链 `Combobox → ttk.Entry → tk.Entry`）导致换肤不生效。
- 修复 `websearch_panel` / `story_flow_panel` 读取不存在的颜色键 `C['input_bg']`（点了没反应）。

### 安全

- 面板注册诊断**不得**从分发层读取原生面板清单（既有守卫拦截），失败清单由注册表自己维护。
- 角色数据三道防线：损坏拒绝覆盖（`force=True` 也先留档）、禁止空集覆盖、锁内读-改-写。
- 传记面板**无任何删除角色入口**（源码级测试守护）；`apply_age_progression` / `apply_death_status`
  绝不删除角色（死亡转 `status=deceased`）。

### 已知限制

- **P5 样式收敛未清零**：`app/` 下仍有 385 处硬编码字体元组待角色化替换（棘轮已就位，可增量推进）；
  `dialogs.py` 抽取与面板"独立窗口"尚未落地。
- `chapter_analysis` 面板在离屏自动化环境中构建失败，需在真实应用内验证。
- Android 版沿用 v4.0.1 构建，本次未重新打包。

### 工程

- 测试规模：**2250 收集**；本次发布前回归 456（面板/UI）+ 162（基础/约束）全绿，
  `ruff check` 全绿、`ruff format` 全部达标。
- 新增 `tests/test_version_consistency.py`：断言 `pyproject.toml` / `app.__version__` /
  `_FALLBACK_VERSION` / README 版本信息相互一致。
- 文档：README 重写为单一权威中文主文档，新增英文 `README_EN.md`，`docs/README.md` 索引更新。

## v2.16.0 (2026-07-03 首发；发布附件于 2026-09-15 重建)

### 架构重构
- **拆分 `novel_app.py` 巨石**：8394 行单类 → **130 行薄编排层** + 12 个功能域 Mixin
  （shell_ui / lifecycle_ui / generation_ui / character_ui / outline_ui / chapter_ui /
  editor_ui / reader_ui / timeline_ui / toolkit_ui / persistence_ui / note_ui）。
  方法体按 AST span 逐字节复制：139 个迁移方法中 137 个字节完全一致，
  类属性集合 186→186 不变。
- **抽取可测纯函数**：新增 `app/parsing.py`（`parse_json_response` / `parse_exp_json`）
  及其 18 个单元测试；`generation_ui` 改为薄委托调用。

### 修复
- 10 处错误弹窗静默失效：`except ... as e` 的 `e` 在 except 块结束即被删除（PEP 3110），
  而 `lambda` 由 `after()` 延迟执行 → NameError。改为默认参数绑定。
- 分支小说生成功能整体失效（嵌套函数遮蔽 `context_text` → UnboundLocalError）。
- 「关于」对话框版本号硬编码为 `v2.0`，与 `app.__version__` 不一致。
- 名场面选景：精心编写的 8 条选景标准（`system`，18 行）从未被使用，
  实际传入的是硬编码的一行简化版 → 已改为使用完整标准。
- 插图提示词文件被同名重复写入，后一次覆盖前一次并**丢失角色描述**。
- 12 个类型测试为恒真断言（`assert len(<测试内自造列表>) > 0`，与产品代码无关），
  且测试构造 `NovelAgent` 时第二参数误传 `Path`（应为 memory 对象）。
  已改写为参数化测试，验证类型字符串真正进入 `AIClient.chat` 的提示词。
- `ai_client` 流式解析的异常分支引用了未定义的 `logger`（该模块用 `_diag_logger`）。
- PDF 依赖错配：代码 `import PyPDF2`，而 `pyproject.toml` 声明的是 `pypdf`。

### 工程治理
- **Git 历史瘦身**：`.git` 830 MB → 12.2 MB（`filter-repo --strip-blobs-bigger-than 500K`），
  229 个提交 / 24 个标签全部保留。
- CI 合并为单一 `ci.yml`；删除与之重叠且必然失败的 `build.yml` / `ci-cd.yml`。
- 修复 `pip install -e ".[dev]"` 失败：`pyproject.toml` 缺 `[build-system]` 与包发现配置，
  flat-layout 下因「Multiple top-level packages discovered」拒绝构建，
  并被 CI 的 `2>/dev/null || <精简安装>` 静默掩盖。
- 清空 3485 项 lint 违规（含 13 处 F821 未定义名称、34 处 F841、94 处 F401）。
- 死代码清理：5 个被主类完全覆盖的 Mixin、`plugin_system` / `ai_drawing` / `collaboration`。
- 全量测试 **1138 passed**。

## v2.15.0 (2026-06-25)

### 新增
- **写作技能系统**：从已完成章节中提取写作模式，形成可复用的写作技能。
- **Token 统计**：按模型与调用维度统计 Token 消耗。

### 修复
- 角色成长 JSON 解析增加 Strategy 4 回退，并补充诊断日志。
- 手机版默认模型改为 `deepseek-v4-flash`。

## v2.14.3 (2026-06-22)

### 修复
- 代码审计问题全面修复。
- 手机版全面代码审查修复。

## v2.14.2 (2026-06-22)

### 修复
- **WorldBuilder输出丢弃修复**: WorldBuilder构建的场景描写现已正确注入Writer上下文
- **finalize_chapter崩溃修复**: AI返回None时kw.split()不再崩溃
- **_parse_json_response类型修复**: Strategy5在is_list=True时正确返回list而非dict

### 代码质量
- 全面代码审查，发现并修复10+逻辑缺陷、2处资源泄漏、5处死代码

## v2.14.1 (2026-06-22)

### 修复
- **角色空壳修复**: 当_parse_json_response返回部分角色(3/5)时，回退提取逻辑现在会触发补充缺失角色
- 新增正则模式匹配，从截断JSON中提取角色名创建基础角色模板

## v2.14.0 (2026-06-21)

### 修复
- **致命BUG: ContextOptimizer静默丢弃全部上下文**: _build_context传递{"内容":...}但optimize()遍历COMPRESSION_RATIOS键不匹配，导致所有上下文被返回为空字符串。Writer/Reviewer/所有Agent之前收到空上下文
- **max_tokens不足修复**: _generate_overall_outline 2000→4096，_generate_story_outlines 3000→4096
- **_generate_story_outlines降级方案动态化**: 使用concept+genre构造，不再硬编码"阴阳岛"

## v2.13.2 (2026-06-21)

> 本条目为**补记**（2026-09-17）：早年发布说明的正文因编码问题不可读，
> 此处仅依据标签提交（`0cf8c54`）与发布附件说明复原**可核实**的内容。

### 修复
- 对话框尺寸与字体优化：窗口加宽至 480px、字号缩至 9pt，长文字自动换行，避免按钮被遮挡。

### 变更
- 以 `--windowed` 模式重新构建（无终端窗口）。

## v2.13.0 (2026-06-21)

### 修复
- **上下文连贯性致命Bug**: glob模式只匹配1个文件而非最近3章 → 改为遍历全部章节文件取最近3章
- **故事大纲AI返回空**: 增加重试和更好的错误处理
- **角色生成增强**: Strategy 5回退从截断JSON提取角色名

### 改动
- EXE从console模式改为windowed模式（无终端窗口）
- PlotDesigner日志消息修正

## v2.12.3 (2026-06-21)

### 新增
- **API设置中心**: 独立设置页面，支持直连AI API / 桌面版后端两种模式
- API端点URL、密钥、模型名称配置
- 一键测试连接，设置自动保存
- 未配置API时智能引导

## v2.12.2 (2026-06-21)

### 修复
- **APK白屏 → 纯HTML重构**: Expo Web的React Native bundle在Android WebView中无法渲染，用纯HTML/CSS/JS重建移动端
- APK大小从7.64MB降至2.4MB

## v2.12.1 (2026-06-21)

> 本条目为**补记**（2026-09-17）：该版本为 **Android APK** 发布，发布说明正文因编码问题
> 仅部分可读；以下只保留能确认的部分（v2.12.2 随即改用纯 HTML 重构，见下条）。

### 修复
- **APK 资源丢失**：aapt 默认忽略以下划线开头的目录，`_expo` 目录连同其中的 JS bundle
  一起被排除在打包结果之外。

### 变更
- Web 资源改放到 `expo_assets`，并保留 `index.html` 入口。
- APK 体积约 7.64MB（其中 JS bundle 约 6.3MB）。

## v2.11.0 (2026-06-19)

### 新增功能
- **世界线/时间线分支系统**: 支持多分支世界线独立创作
  - 决策点每章自动检测，主线完结后生成分支
  - 分支线拥有完整系统（MemoryManager + CharacterSystem）
  - 分支世界线独立创作（独立大纲/角色/摘要）
  - 世界线面板直接浏览决策点
- **Hello-Agents架构升级 v3.0**: 5Agent协作流程
  - PlotDesigner → WorldBuilder → Writer → Reviewer → Editor
  - 智能上下文分配（根据写作阶段动态分配token）
  - 多轮迭代修订，质量阈值自动判定
- **AI封面生成器**: 自动生成封面提示词和HTML预览
- **故事连贯性重构**: 
  - 完结收束逻辑（最后N章自动提示收尾）
  - 续写功能（基于已有章节延续创作）
  - 上下文注入前3章完整内容
- **大纲系统完善**: 
  - 整体大纲和故事大纲注入所有生成流程（自动创作/全屏写作/手动生成/重新创作/续写）
  - 大纲待规划时动态生成后续章节大纲
- **GitHub CI/CD自动化**: 自动测试+构建流水线

### 修复
- 修复8处潜在None崩溃点
- 章节标题混乱+内容截断修复
- 角色从memory同步到characters目录
- 禁止Markdown格式+上章结尾注入上下文
- APK Android16兼容配置（3轮迭代）
- 新建小说面板放大+章节数显示修复
- 双标题显示修复
- 分段续写重复第一段内容修复
- 分支生成使用正确选中项

### 优化
- 代码健康检查通过
- APK Gradle缓存清理

---

## v2.10.0 (2026-06-18)

### 新增功能
- **首次生成章数选项**: 新建小说时可指定先生成N章体验
- **章节回顾(F12)**: 一键查看最近章节摘要
- **角色成长日志**: 面板显示每个角色的属性变化/物品得失/技能领悟
- **角色成长检测**: 每章自动检测所有角色（主角/配角/反派）的成长变化
- **关系变化追踪**: 盟友/敌人关系自动记录
- **技能领悟**: 配角也能学新技能

### 修复
- 修复倒计时递归导致程序崩溃
- 修复分段续写重复第一段内容
- 修复130章仅10个摘要文件
- 修复名场面检测垃圾场景过多
- 修复角色面板不更新
- 修复章节标题丢失
- 修复AI调用超时
- 修复角色文件更新后面板不刷新

---

## v2.9.2 (2026-06-13)

### 新增
- 新建小说支持用户输入想法
- 每章字数默认改为10000字
- 可选字数增加到20000字

### 修复
- 修复新建小说对话框排版问题
- 优化大量章节生成的稳定性

### 新增功能
- **小说模板系统**: 5种快速模板（穿越异世/重生归来/系统流/都市异能/修仙问道）
- **智能内容插入**: AI润色使上下文衔接更自然，不再生硬
- **文档导入分析**: 支持TXT/DOCX/MD导入，AI分析给出创作建议
- **风格优化**: 一键优化章节文学性和可读性
- **多类型大纲**: 整体大纲/章节大纲/故事大纲三种类型
- **角色故事线**: 为每个角色添加独立故事线
- **断点续写**: 自动跳过已完成章节，从未完成处继续
- **章节导航**: 上一章/下一章快速切换，自动保存
- **UI设计系统**: 全新深色主题，更舒适的创作环境

### Bug修复
- 修复重复点击自动创作按钮导致重复任务
- 修复'index_file'属性缺失错误
- 修复自动创作失败后停止不继续
- 修复角色只显示1个的问题
- 修复新建小说面板重复UI元素

### 优化
- 智能体流程重新分组（基础设置/章节创作/导入分析）
- 防重复点击保护
- 代码质量全面提升（30+处print转logger）

---

## v2.7.0 (2026-06-09)

> 本条目为**补记**（2026-09-17）：该版本早于 CHANGELOG 建档，原发布说明正文因编码问题
> 仅部分可读；此处只保留能从残留文本与提交 `788ab9c` 确认的内容。

### 新增
- **AI 工程化升级**：`AIClient v2.0`、`PromptManager`（提示词管理）、
  `AgentOrchestrator`（智能体编排）、`ContextOptimizer`（上下文优化）。

### 修复
- 多项缺陷修复（细节不可考，未作推测）。

## v2.5.0 (2026-06-03)

### 新增功能
- **小说类型扩展**: 从5种扩展到15种小说类型
  - 基础类型: 科幻、悬疑推理、言情、奇幻、都市
  - 新增类型: 历史、武侠、仙侠、恐怖、军事、游戏、体育、穿越、系统流、末日
- **通用生成器架构**: 创建 GenericNovelGenerator 基类，新增类型只需几行代码
- **插件系统完善**: 支持从URL/ZIP/本地目录安装插件，支持GitHub仓库直接安装
- **书签导入/导出**: 阅读管理器支持书签的导入和导出功能

### Bug修复
- 修复新建小说后笔记系统不工作的bug
- 修复打开小说后笔记系统不更新的bug
- 修复图片预览会清空编辑区内容的bug
- 清理未使用的代码导入

### 优化
- 后端服务添加Dockerfile (ai-service + novel-service)
- 优化代码结构，移除冗余导入
- 全面测试15种小说类型生成器，全部通过

### 技术改进
- 所有15种生成器支持独立的元数据、大纲、章节、人物、风格分析
- 工厂模式支持动态创建任意类型的生成器
- API路由同步更新支持所有新类型

---

## v2.4.0 (2026-05-30)

### 新增功能
- 云端存储同步功能 (WebDAV/百度网盘/夸克/迅雷/阿里云盘)
- 基于AutoGen的多智能体协作 (Writer/Reviewer/Editor)
- 基于Supermemory的RAG上下文记忆系统
- 全面优化创作工具 (22类160+元素、18类80+模板、18类150+关键词)

---

## v2.3.0 (2026-05-28)

### 新增功能
- 角色成长系统 (属性/等级/武器/技能/成就)
- 格式转换 (TXT/HTML/MD/EPUB/PDF/DOCX)
- 章节文件浏览 + 智能推荐

---

## v2.2.0 (2026-05-25)

### 新增功能
- 联网搜索热点改编功能
- 故事流推演 (正向/反向/插值/分支)
- 风格转换 (10种风格模板)
- 情景对话推演

---

## v2.1.0 (2026-05-22)

### 新增功能
- 全屏沉浸式写作模式
- Markdown编辑支持
- 笔记系统 (文档/项目/便笺)
- 创作工具集 (元素库/桥段库/描写库)

---

## v2.0.0 (2026-05-20)

### 重大更新
- 桌面版GUI重构 (tkinter)
- AI API集成 (Ollama/OpenAI/DeepSeek/Claude)
- 长上下文记忆系统
- 智能体机制
- 阅读管理器

---

## v1.0.0 (2026-05-15)

### 初始版本
- 基础小说生成功能
- Docker部署支持
- Web前端界面
