# 功能实用性与使用价值评估 · 保留 / 优化 / 删除清单

> 评估基准：HEAD `232c36a`（2026-09-16），CI 全绿。
> 方法：**基于代码事实**（引用计数、调用链追踪、可达性分析），非主观印象。
> 本文只做评估与建议，**未执行任何删除**。

---

## 0. 结论摘要

| 结论 | 数量 | 说明 |
|---|---|---|
| ✅ **保留**（核心价值，方向正确） | 16 项 | 桌面端完整创作闭环 + 移动端 + 发布链路 |
| 🔧 **优化**（有价值但实现有缺陷） | 11 项 | 含 1 个功能性入口丢失、3 处重复实现、1 处依赖错配 |
| 🗑️ **删除**（冗余 / 零调用 / 已被取代） | 10 项 | 约 1,100+ 行代码 + 2 个空服务 + 1 套废弃移动端 |
| ⚠️ **冻结待处置**（不做删除，先降级定位） | 1 组 | 后端 6,794 行与桌面端功能重叠 |

**最重要的一条结论**：项目的问题**不是"功能太多"**，而是——

> **有一条已经写好、且用户明确需要的能力，因为漏绑一个按钮而完全用不了**
> （详见 §4 缺陷 D1：角色重命名 / 删除 / 休息恢复 / 故事线编辑**全部不可达**）。

真正的冗余集中在**工程卫生层面**（死方法、重复测试、空目录、错配依赖），
而不是产品功能层面。

---

## 1. 评估方法与严谨性说明

采用的手段：

| 手段 | 目的 |
|---|---|
| 模块引用计数（自建脚本，151 个 .py 全仓扫描） | 找出零引用模块 |
| 方法级调用链追踪（497 个方法，匹配 `self.X`/`app.X` 调用点） | 找出孤儿方法 |
| **UI 可达性分析**（菜单项 → notebook 标签页 → 按钮回调逐层回溯） | 判断功能用户能否点到 |
| 空目录递归扫描 | 找出占位残留 |
| 依赖声明 vs 实际 import 比对 | 找出依赖错配 |
| 代码规模统计（分模块统计行数） | 量化维护成本 |

### ⚠️ 关于两处「我最初的误判」——已修正，记录在此以免误导

| 初次结论 | 实际情况 | 修正原因 |
|---|---|---|
| `app/panels/` 下 12 个面板**零引用**，疑似死代码 | **全部可达** | 我的正则未覆盖 `from .X import` 的包内相对导入；实际由 `app/panels/__init__.py` 汇总 → `novel_app.py:46-51` 引入 MRO → `toolkit_ui.py:27-49` 分支分发 → `shell_ui.py:590-599` 12 个单选钮触发 |
| `nginx/`、`models/`、`shared/` 三目录为**空** | `nginx/` 有 2 个 .conf，`models/` 有子目录 | 我的扩展名白名单未含 `.conf`；`shared/` 确实是空的 |

> 这也是本报告的一条方法论主张：**"零引用"不等于"死功能"**，必须回溯到 UI 入口才能下结论。
> 凡下"删除"结论者，本文均已回溯到调用链末端。

---

## 2. 功能面全景

### 2.1 桌面端可达入口（主线交付形态）

| 入口 | 内容 |
|---|---|
| **菜单（4 个）** | 文件（新建/打开/续写/第二部/衍生同人/导出TXT/退出）、创作（仿写风格/角色传记/书籍简介）、设置（AI配置）、帮助（使用说明/关于） |
| **标签页（7 个）** | 章节内容 · 运行日志&角色 · 审校结果 · 笔记 · 创作工具 · 阅读管理器 · 写作技能 |
| **创作工具（12 项单选钮）** | 元素库 · 桥段库 · 描写库 · 对话推演 · 故事流 · 风格转换 · 智能改编 · 热点改编 · 章节分析 · 记忆可视化 · 摘要管理 · 批量操作 |
| **左侧面板** | 章节列表 · 大纲列表 · 角色卡片（新建 / AI生成 / 传记） |
| **快捷键** | Ctrl+S 保存 · Ctrl+N 新建 · Ctrl+O 打开 · F11 全屏写作 |

### 2.2 代码规模（维护成本视角）

| 部分 | 文件 | 行数 | 定位 |
|---|---|---|---|
| `app/`（桌面端业务） | 45 | **18,595** | ✅ 主线 |
| `novel_app.py` | 1 | 154 | ✅ 薄编排层 |
| 根目录游离模块（4 个） | 4 | **2,888** | 🔧 需归位 |
| `tests/` | 42 | 10,155 | ✅ 但重复严重 |
| `backend/`（AI+小说+shared+tests） | 53 | **11,130** | ⚠️ 与桌面端重叠 |
| `frontend-react/`（src 仅 658 行） | 14 | 3,627 | 🗑️ 演示级 |
| `mobile-app/novel-app`（Compose 现役） | 16 kt | 3,503 | ✅ 主线移动端 |
| `mobile-app/webview-app`（旧 v3.0.1） | — | 214 | 🗑️ 已废弃 |

---

## 3. 逐项评估

### 3.1 ✅ 保留：桌面端核心链路

这些是项目的**真实价值所在**，功能完整、闭环可用、无外部硬依赖。

| # | 功能 | 实用性判断 | 证据 |
|---|---|---|---|
| K1 | **5-Agent 生成流水线** | 核心卖点 | `app/novel_agent.py`（9 处引用，测试覆盖最厚） |
| K2 | **分层记忆系统**（全局/卷/弧线/章节 + 倒排索引，支持 5000 章） | 长篇小说刚需，且是差异化壁垒 | `app/memory_manager.py` |
| K3 | **小说生命周期**（新建/打开/续写/第二部/衍生同人/导出） | 完整作品生产流程 | `navigation.py:22-31` + `lifecycle_ui.py` |
| K4 | **章节编辑 + 全屏写作**（F11 + AI 辅助） | 高频刚需 | `editor_ui.py` / `fullscreen_writer.py` |
| K5 | **三级大纲**（章节/整体/故事）+ 世界观注入 | 直接决定生成质量 | `outline_ui.py` |
| K6 | **一致性审校 + 定稿** | 长篇质量保障 | `generation_ui.py` + 审校标签页 |
| K7 | **角色系统**（卡片/EXP 成长/传记/装备技能） | 有吸引力，**但入口缺失，见 D1** | `character_ui.py` + `character_system.py` |
| K8 | **内容型创作工具**：元素库/桥段库/描写库 | **零外部依赖、开箱即用**，是本组工具中价值最高的一档 | `novel_toolkit.py` + 3 个 panel |
| K9 | **阅读管理器**（TXT/EPUB/PDF/DOCX/MD + 书库/书签/全文搜索） | 可独立成立的功能，价值清晰 | `reading_manager.py`（6 处引用） |
| K10 | **写作技能 / 去AI味**（AntiSlop + 知识图谱 + 时间感知记忆） | **差异化最强**的一项，且已被生成流程自动调用 | `writing_skills.py`，`shell_ui.py:620-622` 有独立标签页 |
| K11 | **时间线与分支小说** | 玩法型功能，成本已沉没 | `timeline_ui.py` |
| K12 | **持久化**（备份/检查点/断电恢复） | 长篇小说必需，实际可靠 | `persistence_ui.py`（`_atomic_write` 有真实调用） |
| K13 | **笔记系统** | 轻量辅助，成本极低 | `note_ui.py` / `note_manager.py` |
| K14 | **打包发布链路**（PyInstaller + NSIS + GH Release + GitHub Actions CI） | 产品化关键，且刚修至全绿 | `installer/`、`.github/workflows/ci.yml` |
| K15 | **移动端 Compose（v4.0.1）** | 已交付、CI 构建、Release 分发 | `mobile-app/novel-app`（16 kt / 3,503 行） |
| K16 | **格式转换 + 插图/封面** | 输出环节需要，但依赖外部 API（见 O11） | `format_converter.py`(512) + `image_generator.py` |

### 3.2 🔧 优化：有价值但存在缺陷

| # | 项 | 问题（含证据） | 影响 | 建议 | 替代方案 |
|---|---|---|---|---|---|
| **O1** | **角色管理入口** | `_show_char_detail`（`character_ui.py:702`，76 行完整对话框）**零调用**；其 4 个子操作 `_rename_character`/`_delete_character`/`_rest_character`/`_edit_character_story` **仅被该对话框引用**。主界面只提供「新建/AI生成/传记」3 个按钮（`shell_ui.py:371-379`） | **用户无法重命名、删除角色，也无法使用"休息恢复"与"故事线编辑"** —— 已实现的功能等于不存在 | 在角色卡片或列表框右键/双击菜单中挂上 `_show_char_detail`（1 处 `command=` 或 `bind` 即可救活 150+ 行） | 若判定对话框过重，则把 4 个操作直接做成卡片上的小按钮 |
| **O2** | **公共线程执行器 `_run_async`** | `shell_ui.py:23` 定义，**零调用**；同时全仓手工 `threading.Thread(` **42 处**（generation_ui 14 / toolkit_ui 5 / 各 panel 15 …） | 文档宣称的「P1 抽取公共线程执行器」**从未落地**；42 处重复的线程创建 = 42 处异常处理逻辑各自为政 | 要么真落地（分批替换，先替换 `app/panels/*` 15 处），要么**删除该函数**消除"已优化"的假象 | 若不做替换，则应把 `_run_async` 删除并在文档更正 |
| **O3** | **原子写三份实现** | `_atomic_write`（有调用）、`_atomic_json_write`（**零调用**）、`_save_checkpoint` 内联第三套相同逻辑（`persistence_ui.py:79-83`） | 三份重复，改一处漏两处；`_atomic_json_write` 纯冗余 | 统一为 `_atomic_write` 一个实现，`_save_checkpoint` 改为复用 | 无需替代方案，属合并 |
| **O4** | **`tests/` 重复测试文件** | 同模块多份：`novel_agent` **7 份**（mock/coverage/deep/outline/final/full/generate）、`reading_manager` **5 份**、`ai_client` **4 份**、`note_manager` 3、`diagnostic_logger` 3、`memory_manager` 3 | 覆盖率冲刺的遗留物，维护与重构成本高（42 文件 10,155 行） | 合并为每模块 1–2 个内聚文件（如 `test_novel_agent.py` + `test_novel_agent_edge.py`） | 保留 `conftest.py` 共享夹具 |
| **O5** | **`chromadb` 依赖错配** | `pyproject.toml:19` 将其列为**发行包强制依赖**；但全仓仅 `backend/novel-service/app/vector_store/vector_manager.py:31-32` 一处使用，且是 `try/except` 可选导入。桌面端 `app/` 内 **0 处** chroma 引用 | 每个桌面用户/CI 都安装了桌面端**永不使用**的重型依赖（未在本机安装，未实测体积；其传递依赖较重） | 从 `[project].dependencies` 移出，改为 backend 专属依赖（如 `[project.optional-dependencies].backend` 或 backend 独立 requirements） | backend Dockerfile 单独安装 |
| **O6** | **根目录游离模块** | `character_system.py`(905) / `cloud_storage.py`(821) / `novel_toolkit.py`(650) / `format_converter.py`(512) 位于仓库根，被 `novel_app.py:38-39` 与 `toolkit_ui.py:12` 直接 `import`；而同类模块都在 `app/` 包内 | 架构不一致，`[tool.setuptools.packages.find]` 需 include 白名单绕开（`pyproject.toml:41-42`）；新贡献者不知该放哪 | 迁入 `app/` 并修正导入（一次性机械改动） | 若担心打包路径变化，可先保留但加注释说明 |
| **O7** | **创作工具 12 项排布** | `shell_ui.py:590-599` 把 12 个工具做成**单行 12 个 Radiobutton**（`side=tk.LEFT, padx=8`），窗口最小宽度 1100px | 12 个中文标签横排易挤压/换行错乱，且**无分组**（内容型 vs AI型 vs 管理型混在一起），新用户难发现 | 改为 2 行网格或左侧 Listbox，并按「素材库 / AI 工具 / 作品管理」分组 | 至少加 `wraplength` + 分组分隔 |
| **O8** | **空目录与文档失实** | 16 个递归空目录；其中根 `shared/`（3 层：`shared/`、`shared/python/`、`shared/types/`）为空，但 `README_CN.md` 架构图列出 `├── shared/  # 共享库`（真正共享代码在 `backend/shared/`） | 误导贡献者；与已修正的 auth-service 属同类问题 | 删除空目录；README 架构图中的 `shared/` 标注为 `backend/shared/` | — |
| **O9** | **`frontend-react` 参数与空按钮** | `Home.tsx:37` 硬编码 `http://localhost:8002`，`Editor.tsx:23` 硬编码 `8001`，**无视** compose 注入的 `REACT_APP_API_URL`；`Tools.tsx:142-145` 四个按钮**完全没有 onClick**；`Tools.tsx` 全部分类为硬编码字面量、自定义项只存 React state（刷新即丢） | 容器化部署下前端连不上后端；界面上有"看着能点其实没反应"的按钮 | 若保留：抽 `api.ts` 统一基址（读 env）、给空按钮补实现或**删掉按钮**、自定义项落 localStorage | 若不打算继续投入，见 D8 |
| **O10** | **静态 API Key 无轮换机制** | `API_KEYS` 为环境变量字符串，改 key 需重启服务 | 运维摩擦（低危） | 文档中明确"改 key = 重启"这一事实即可，无需建设 | — |
| **O11** | **强外部依赖功能的"未配置"体验** | 云同步（`cloud_storage.py` 821 行）、文生图/封面、热点改编均依赖外部配置；未配置时云同步对话框提示"未配置云存储"（`toolkit_ui.py:551-553`），文生图按钮按 `is_configured()` 隐藏 | 功能本身没问题，但用户在"为什么点不动"上无指引 | 在 USAGE.md 明确每项功能的**前置条件表**（是否需要 API/授权） | — |

### 3.3 ⚠️ 冻结待处置：后端集群与桌面端功能重叠

后端 `novel-service`（6,794 行）与桌面端存在**成对的同名实现**：

| 后端模块 | 行数 | 桌面端对应实现 | 关系 |
|---|---|---|---|
| `consistency_checker/` | 657 | `novel_agent.py` 的 `check_consistency` 工具 | 双实现 |
| `finalization/` | 460 | `novel_agent.py:1407 finalize_chapter` | 双实现 |
| `bridge_library/` | 692 | `novel_toolkit.py` 的 `BridgeLibrary` | 双实现 |
| `description_library/` | 564 | `novel_toolkit.py` 的 `DescriptionLibrary` | 双实现 |
| `dialogue/` | 465 | 桌面 `dialogue_panel` + `DialogueEngine` | 双实现 |
| `story_flow/` | 607 | 桌面 `story_flow_panel` + `StoryFlowEngine` | 双实现 |
| `style_transfer/` | 488 | 桌面 `style_panel` + `StyleTransferEngine` | 双实现 |
| `generators/` | 544 | 桌面 `novel_agent.py` 生成流水线 | 双实现 |
| `vector_store/` | 429 | **无对应**（桌面端不用向量库） | 后端独有 |

**判断**：
- 后端**不是"冗余功能"**（它是另一种交付形态），但**没有任何一方消费者**：`frontend-react` 只有 2 处真实调用，移动端与桌面端都不走后端。
- `ARCHITECTURE_BOUNDARY.md` 已明确「后端冻结，新业务只在桌面端」。
- **建议：不删除，但降级定位**——在 README/docs 明确"后端为**未验证的可选部署形态**，当前无生产使用者"，并停止对其做功能投入。若将来确认永不部署，再整目录归档（-11,130 行）。
- **不建议现在删**，因为：①它是唯一含 ChromaDB 向量检索的实现，删掉等于放弃"语义检索"这条技术路线；②删除 11k 行属产品决策，不应由代码审计单方面决定。

### 3.4 🗑️ 删除：零调用 / 已被取代 / 纯冗余

| # | 项 | 位置 | 规模 | 删除理由（证据） | 影响 | 替代方案 |
|---|---|---|---|---|---|---|
| **D1** | `_show_image_prompt_dialog` | `toolkit_ui.py:419-531` | **113 行** | 零调用。功能已被 `_detect_and_prompt_image`（同文件 357-418）取代，后者直接写提示词文件、不再弹电影级对话框。**两套实现并存**，保留旧对话框只会让后续维护者改错地方 | 无（无入口即无行为变化）。仅"名场面插图对话框"这一交互形式消失，而该形式本就不可达 | 若想要回对话框体验，应把 `_detect_and_prompt_image` 的落盘逻辑接回该对话框，而不是保留双份 |
| **D2** | `_atomic_json_write` | `persistence_ui.py:123-128` | 6 行 | 零调用；与 `_atomic_write` 逻辑重复（仅多了 `json.dump`），且 `_save_checkpoint` 已内联第三份 | 无 | 统一用 `_atomic_write`（见 O3） |
| **D3** | `_toggle_ai` | `fullscreen_writer.py:383` | 小 | 零调用。全屏写作的「AI 开关」无任何绑定 | 无（该按钮/开关本就点不到） | 若要保留能力，在 `fullscreen_writer` 的工具栏接线；否则删除 |
| **D4** | `ui_style.create_styled_button` / `create_styled_entry` / `create_styled_listbox` / `create_styled_text` | `app/ui_style.py` | 4 个函数 | 全部零调用。项目实际到处手写 `tk.Button(...)`（42 处线程 + 大量控件直建），这 4 个封装从未被采用 | 无。**但需注意**：它们是"成体系但未落地"的样式 API，若团队打算统一 UI 风格则应**接线而非删除** | 二选一：接线到实际控件创建，或删除以消除死 API |
| **D5** | `performance_monitor.save_report` / `wrapper` / `__call__` | `app/performance_monitor.py` | 小 | 零调用。该模块仅被 `backend/*/app/main.py` 使用，而这 3 个方法在其中未被调用 | 无 | 若确需落盘报告，在服务关停钩子里调用 |
| **D6** | 根目录 `test_generators.py` | 仓库根 | **113 行** | **被 git 跟踪，但永远不会被执行**：`pyproject.toml:45` 的 `testpaths = ["tests", "backend/tests"]`，且 CI 显式 `pytest tests/ backend/tests/`。`tests/test_novel_genres.py` 已覆盖同一主题 | 无。删除后测试数不变（本就不参与统计） | 若其中有独有用例，先合并进 `tests/test_novel_genres.py` 再删 |
| **D7** | `mobile-app/webview-app`（整目录） | 移动端 | 214 行 + 提交的构建产物 | ①CI 只构建 `mobile-app/novel-app`（`ci.yml:125`）；②已被 Compose 版 v4.0.1 取代；③**把压缩后的 `app.js`(61.8 KB) / `style.css`(7.8 KB) 提交进了仓库**，属"构建产物入库"反模式；④全仓仅 `CONTRIBUTING.md:191` 一处提及 | 无功能影响。丢失的是**已被取代的历史实现**（git 历史仍可追溯） | 若想留档，把 `app/src/main/assets` 的 HTML/JS 归档到 `docs/archive/` 并删除整个 Gradle 工程 |
| **D8** | `backend/auth-service/`、`backend/payment-service/` | 后端 | **2 个空目录** | 0 文件、未被 compose 引用、代码零引用。已由 `docs/AUTH_PAYMENT_SERVICES_EVALUATION.md` 定论**暂不立项** | 无。`README_CN.md` 已标注「规划中，未实现」 | 若担心丢失"规划意图"，保留那份评估文档即可（文档已含 G1–G5 决策门与分期草案） |
| **D9** | 根目录 `shared/`（`shared/`、`shared/python/`、`shared/types/`） | 仓库根 | 3 个空目录 | 递归零文件；真正的共享层在 `backend/shared/`（992 行，已抽取）；`pyproject.toml:40` 注释也确认「shared/ 由服务各自引用」 | 无 | 删除并在 README 架构图中把 `shared/` 改为 `backend/shared/` |
| **D10** | 空日志/模型占位目录 | `backend/novel-service/logs/`、`installer/logs/`、`installer/models/`、`installer/models/local/`、根 `models/{configs,local}` | 6 个空目录 | 递归零文件。git 本就不跟踪空目录，说明它们**从未进入版本库**，只是本机运行时残留 | 无（运行时按需自动重建） | 无需替代；如需保留占位可加 `.gitkeep` |

**删除项合计**：约 **1,100+ 行**代码、**2 个空服务目录**、**1 套废弃移动端工程**、**11 个空目录**。

---

## 4. ❗ 本次发现的"不是冗余、而是坏掉"的问题

这一节的问题**不属于"低价值功能"**，而是**已实现的能力因缺陷而不可用**，优先级高于任何删除动作：

| 编号 | 问题 | 严重度 | 说明 |
|---|---|---|---|
| **F1** | **角色重命名 / 删除 / 休息恢复 / 故事线编辑 全部不可达** | 🔴 高 | 5 个方法（~150 行）由 `_show_char_detail` 串联，但该对话框无任何入口。用户**没有删除角色的手段**。修法极廉（挂一个 `command=` 或 `bind`） |
| **F2** | **`_run_async` 声称的线程统一从未落地** | 🟡 中 | 42 处手工 `threading.Thread` 仍是现状；文档/日志中的"已抽取公共线程执行器"与事实不符，会误导后续维护 |
| **F3** | **`test_generators.py` 被跟踪但永不执行** | 🟡 中 | 给出"有测试覆盖"的错觉；实际该文件不参与 CI |
| **F4** | **`chromadb` 强制依赖所有用户** | 🟡 中 | 桌面端零使用，仅 backend 一处可选导入 |
| **F5** | **`frontend-react` 空按钮与硬编码地址** | 🟡 中 | 4 个"快速操作"按钮无响应；容器部署下无法连通 |
| **F6** | **文档宣称的"原子写"实为三份实现且一份是死的** | 🟢 低 | 不影响正确性（在用那份是对的），但维护风险 |

---

## 5. 清单总表

### ✅ 保留（16 项）

K1 5-Agent 生成流水线 · K2 分层记忆系统 · K3 小说生命周期 · K4 章节编辑+全屏写作 ·
K5 三级大纲+世界观注入 · K6 一致性审校+定稿 · K7 角色系统（**待修入口**） ·
K8 元素库/桥段库/描写库 · K9 阅读管理器 · K10 写作技能/去AI味 · K11 时间线+分支小说 ·
K12 持久化（备份/恢复） · K13 笔记系统 · K14 打包发布+CI · K15 移动端 Compose v4.0.1 ·
K16 格式转换+插图封面

### 🔧 优化（11 项）

O1 角色入口接线 · O2 落地或删除 `_run_async` · O3 原子写统一为一处 ·
O4 合并 `tests/` 重复文件 · O5 `chromadb` 移出桌面依赖 · O6 根目录 4 个模块归入 `app/` ·
O7 创作工具分组排布 · O8 清空目录+修正 README `shared/` · O9 前端基址参数化+空按钮处理 ·
O10 文档说明 API Key 轮换方式 · O11 补"功能前置条件表"

### 🗑️ 删除（10 项）

D1 `_show_image_prompt_dialog`(113 行) · D2 `_atomic_json_write` · D3 `_toggle_ai` ·
D4 `ui_style` 4 个死封装 · D5 `performance_monitor` 3 个死方法 · D6 根 `test_generators.py`(113 行) ·
D7 `mobile-app/webview-app` 整目录 · D8 2 个空服务目录 · D9 根 `shared/`(3 层空) ·
D10 6 个空占位目录

### ⚠️ 冻结待处置（1 组）

后端 `backend/`（11,130 行，含 8 个与桌面端成对的实现）——**降级定位、停止投入、不删除**

---

## 6. 建议执行顺序

按「收益 / 风险」排序，**先修坏的，再删死的，最后谈架构**：

| 阶段 | 动作 | 理由 |
|---|---|---|
| **P0（立刻，改动极小）** | F1 角色入口接线、O5 `chromadb` 移出桌面依赖 | F1 是"已付费的能力用不上"，一行代码救活 150 行；O5 直接降低所有用户的安装成本 |
| **P1（低风险清理）** | D1–D6、D9、D10 删除；F3 合并测试后删除 | 全部为零调用/零文件，删除无行为影响，且让代码库可读 |
| **P2（需小改动）** | O1（若未在 P0 完成）、O2 决策、O3 合并、O7 工具分组、O8 文档修正 | 涉及接线或重构，需回归测试 |
| **P3（需较大投入）** | O4 合并测试文件、O6 模块归位、O9 前端补齐、O11 文档 | 机械但量大 |
| **P4（产品决策）** | 后端定位（保留/归档）、`mobile-app/webview-app` 归档方式 | 需产品侧拍板，不宜由技术审计单方面决定 |

---

## 7. 附：本次评估中"看起来像死代码、经核实其实正常"的项

列出以免后续误删：

| 项 | 为何看起来可疑 | 核实结论 |
|---|---|---|
| `app/panels/` 12 个面板 | 模块引用计数为 0 | ✅ 经 `__init__.py` → MRO → `toolkit_ui` 分发 → 12 个单选钮，全部可达 |
| `dialogue_engine` / `story_flow_engine` / `style_engine` / `adapt_engine` / `web_search_engine` | `__init__` 中初始化为 `None`，疑似未实现 | ✅ 均在各 panel 内惰性构造（`dialogue_panel.py:37` 等） |
| `WritingSkillsPanelMixin` | 不在 `_refresh_toolkit` 的 12 个分支内 | ✅ 它是独立**标签页**（`shell_ui.py:620-622`），不走工具分发 |
| `_atomic_write` | 与 `_atomic_json_write` 高度相似 | ✅ **在用**，是持久化的真实实现；冗余的是后者 |
| `nginx/`、`models/` 目录 | 我的首个脚本报 0 文件 | ✅ 分别含 2 个 `.conf` 与子目录，正常 |
| `app/fullscreen_writer.py` 等 UI 胶水模块 | coverage `omit` 列表排除了它们，看似"免测" | ✅ 有意为之（`pyproject.toml:78-99` 注明：UI 粘合层难单测，可测逻辑已抽到 `app/parsing.py`） |

---

*本文档为功能价值评估报告，**未执行任何删除**。所有"零调用"结论均可由文中给出的文件:行号复核。*
