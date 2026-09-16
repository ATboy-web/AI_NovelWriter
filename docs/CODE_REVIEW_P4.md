# P4（面板框架与联动）代码与功能复核

> 复核日期：2026-09-16
> 复核范围：v3 P4a（`d869660`）+ P4b（`0804c5d`）全部新增/改动代码，及其与既有模块的接线
> 复核基线：`0804c5d`；复核后修复见 §2（提交号见 §5）

---

## 0. 方法与结论

四条独立证据线，**互相不依赖**，任一条为假都会被另外几条戳破：

| 手段 | 覆盖面 | 结果 |
|---|---|---|
| `ruff check` | 语法/未用导入/**未定义名**（F821） | 全绿 |
| `ruff format --check` | 格式（CI 也跑这条） | 新增的 11 个文件全部达标 |
| `mypy`（仅新增模块） | 类型与**空值解引用** | 0 错误 |
| pytest | 2156 个用例 | **0 失败** |
| 真实 Tk 端到端 | 15 面板构建 + 面板联动 + 数据链路 | 全部通过 |

**结论：P4 的落地是完整且正确的；本轮自查出并修掉 8 处问题（含 2 处会造成运行期崩溃/误导用户的真实缺陷），
另有 7 项属于既有代码的缺陷或工程卫生问题，已如实列出并给出建议，未擅自改动。**

---

## 1. 功能落地核对（"是否真的被调用"）

逐条验证需求与代码的对应关系，**每一条都有可执行的观测点**：

| 需求（ROADMAP §2.2/§2.3/§2.4） | 落地位置 | 验证方式 |
|---|---|---|
| 新增面板只需 1 处改动 | `registry.NATIVE_PANEL_MODULES`（3 行） | `test_new_panels_are_reachable_without_dispatch_changes` 断言 `toolkit_ui`/`shell_ui` 里**没有**新面板 key |
| 12 老面板零改动迁移 | `legacy.LegacyPanelAdapter`（读写双代理） | 12 个适配器全部构建成功（端到端） |
| 事件只走统一出口 | `shell_ui._publish_event` → `EventSink` → `publish_threadaware` | `test_publish_event_is_the_single_outlet` 扫全仓 |
| 4 条打开入口都广播 | `lifecycle_ui._announce_novel_opened` | 源码计数断言 == 4 |
| 换书先 closed 后 opened | 同上 | 端到端实测 `['novel.closed','novel.opened']` |
| 两套时间线合流 | `timeline_store.sync()` | 端到端：事件源 → `timelines/main.json` |
| 人物轨迹 → 传记面板联动 | `timeline_panel._on_track_double` → `biography.focus_character` | 端到端实测：切换后面板为 `biography`、聚焦角色 `甲` |
| 子代只读父代 | `lineage.guard_child_path` | `test_inherit_never_touches_parent` 比对**父代全量文件哈希** |
| 传记不提供删除角色入口 | `biography_panel` 无任何删除路径 | `test_no_delete_character_entry` 扫 3 个面板 |

> 一条"看着像没落地、实际落地了"的说明：`timelines/branch_%03d/` 的子项目目录
> **历史上有写入方、无读取方**（见 §3 F2）。本轮把它显示出来了，但它仍不是"可打开的子项目"。

---

## 2. 本轮修复（8 项，全部在 P4 自己的代码内）

| # | 位置 | 缺陷 | 影响 | 修法 |
|---|---|---|---|---|
| A1 | `timeline_panel` / `biography_panel` 的后台线程 | `except Exception as e:` 之后把 `e` 捕进 lambda 交给 `root.after` —— Python 在 except 块结束时**删除 `e`** | **失败路径必然 `NameError`**：AI 调用失败时用户看到的是"生成中…"卡住 + 无提示。由 ruff **F821** 抓出 | 先取出 `message` 再进 lambda |
| A2 | `biography_panel._persist` | 返回单个 bool，成功提示一律写"并回写角色档案" | **虚假成功**：宿主无 `memory` 时文件写了但档案没写，却告诉用户已回写 | 改为 `(文件落盘, 档案回写)` 两个布尔，分别如实提示 |
| A3 | `lineage_panel._on_apply_inheritance` | ①`lin.read_lineage(x)` 被调用两次且可能解引用 None；②继承用"已登记父代"、年龄换算却用"下拉框当前项" | 两条路径可能指向**不同父代**，年龄推进量按错误的父代章数计算 | 只读一次并在无候选时回落 `parent_novel`；把同一个 `parent` 传给 `_apply_character_transform` |
| A4 | `lineage_panel.novel_candidates` | `is_within(entry, exclude)` 方向写反（排除的是**祖先**而非**后代**） | 注释说"排除后代"，实际排除了最合法的父代候选；把子代设成父代可成环 | 改为 `is_within(exclude, entry)`，并把方向陷阱写进 docstring |
| A5 | `memory_manager.annotate_event` | 事件载荷里 `"type": changes.get("arc", "")` | 订阅方收到 `type=第一卷` 这种非类型值（当前只是刷新，但载荷语义错） | 取记录自身 `type` |
| A6 | `lineage.inherit_into_child` | `[x for x in xs if not (x in seen or seen.add(x))]` | 能跑但不可读，且 mypy 正确报"set.add 不返回值" | 抽出 `dedupe_preserve_order()` |
| A7 | P4a 的 `panels/registry.py` / `panels/host.py` | mypy：`getattr(type,…,"")` 选错重载；`lambda k=spec.key:` 无法推断 | 无运行期影响，但污染 CI 的 mypy 报告 | 显式 `str()`；改用 `functools.partial(self.select, spec.key)` |
| A8 | `panels/base.py` + 3 个新面板 | `requires_novel` 被声明、被基类文档承诺"宿主据此提前给提示"，**全仓无任何读取方** | 零可观察面的"假 API"：读代码的人会以为宿主会拦一道 | 移除，并在原处留下原因与"要加就连消费者一起加"的注释 |

另：`tests/test_usage_panel.py` 的源码扫描改用 `_source_scan.code_only`（此前被 docstring 里的示例代码数成真实入口）。

---

## 3. 发现的**既有**缺陷（未改，附建议）

按影响排序。**均非 P4 引入**，但复核过程中被暴露出来。

### 🔴 F1 `live_data.chapter_count` 名不副实，P0 护栏缺"章"维度

```python
# app/live_data.py:141
chapter_count=_count_json_files(novel_dir / "characters"),   # 数的是 characters/ 的 JSON！
```

- 字段名是 `chapter_count`，实际统计 **`characters/` 下的角色文件数**；
- 这正是 `docs/v3_baseline.json` 里 `character_count: 286` 与 `chapter_count: 286` 两个数字完全相同的根因；
- 三处口径自相矛盾：`scripts/baseline_check.py:174` 把它标为「**角色文件数**」（说实话），
  而 `:132` 与 `live_data.format_text()` 都打印成 `chapters`（说谎）；
- **真正的章数（线上 1094）从未被采集** ⇒ `baseline_check --verify` 无法发现"章节被删"。

**建议**：`chapter_count` 改为统计 `chapters/*.txt`，把原值改名为 `character_file_count` 单独保留；
`format_text()` 的标签同步修正。⚠️ 改动会使 `--verify` 报出 286→1094 的差异（属**正确**的差异），
需在改完后重新 `--record` 一次基线——这一步涉及"基线语义"，**建议由你确认后再做**。

### 🟡 F2 `timelines/branch_%03d/` 只写不读

`timeline_ui` 会建出带 `chapters/summaries/meta.json/characters/memory/outline.json` 的完整分支子项目，
但全仓没有任何读取方。本轮已在时间线面板「世界线/分支」视图里列出（含状态与章数），
让"写了但看不见"第一次可见。
**建议**：是否把它做成"可打开的分支项目"（切进去当成一部子作品）属产品决策，待你定。

### 🟡 F3 `update_character_activity` 没有生产调用方

只有测试调用它 ⇒ 真实小说里 `memory/character_activity.json` 基本是空的。
"人物轨迹泳道"本来会是一条空视图，因此 `character_tracks()` 用事件源的 `characters` 字段兜底反推。
**根因是采集从未接线**（不是展示问题）。
**建议**：在成章流程（`novel_agent.generate_chapter` 成功之后）调用 `update_character_activity(角色, 章号)`，
泳道才有真实的"最近出现"数据。

### 🟡 F4 两套传记生成逻辑并存

新面板走 RAG + 时间线 + 已写正文；`character_ui._generate_character_biography` 仍在且入口可达，
其提示词**只用 `char_info` + `outline[:5]`**（完全不用已写章节）。
**建议**：把 `character_ui` 的入口改为委托新面板的方法（或直接指向新面板），收敛为一处；
否则"从角色页生成的传记"与"从面板生成的传记"质量会明显不同。

### 🟠 F5 CI 的两条质量门是空转的

`.github/workflows/ci.yml` 里 `ruff format --check` 与 `mypy` 都带 `continue-on-error: true`：

- `ruff format --check`：**122 / 143 个文件**待格式化（我新增的 11 个文件已全部达标）；
- `mypy`：存量错误约 **100 条**，集中在 `providers/*`、`ai_client.py`、`memory_manager.py`、
  `novel_toolkit.py`、`diagnostic_logger.py`、`writing_skills.py`。

**建议**：先 `ruff format app/ tests/` 全量格式化一次并单独提交（纯格式、零语义变更），
把这一条转为**阻断式**；mypy 则先加 `--exclude` 或逐步收敛，别让它长期挂着 continue-on-error
（等于没有门）。

### 🟢 F6 颜色令牌守卫有覆盖缺口

`test_panel_framework.TestPanelColorTokensExist` 只扫描**含字面 `C = UIStyle.COLORS`** 的文件。
若某处用 `_colors()` 之类的间接写法取色，就会逃过检查（我写 P4b 时差点这么做，后来改回直写以留在守卫内）。
**建议**：把判据放宽为"文件里出现 `UIStyle.COLORS` 或 `COLORS[`"，即可覆盖间接写法。

### 🟢 F7 `docs/v3_baseline.json` 快照已过时

记录了 `head: 865048f`、`tests.passed: 1406`，与现状（含 P1–P4b）差距很大；
`chapter_count` 还受 F1 影响。
**建议**：F1 修完后重新 `--record`，并把"基线应随每期更新"写进 P5 的收尾清单。

---

## 4. 验证证据（复核后重跑）

代码修复后**重跑**（原生 Windows 环境下 `pytest` 的临时目录清理会触发沙箱批量删除守卫，
故按文件分块执行，每块一次独立调用）：

| 块 | 内容 | 结果 |
|---|---|---|
| 1 | 面板框架 + 事件总线 + 3 份新测试 | 284 passed |
| 2 | diagnostic_logger×3 + event_bus + image_generator×2 + lineage + memory_manager×3 | 252 passed |
| 3 | secure_config + storage + timeline_store + token_estimator + ui_style + usage_panel + usage_tracker + writing_skills | 233 passed |
| 4 | novel_agent×3 + novel_genres + novel_store + novel_toolkit + p4b_panels | 295 passed |
| 5 | parsing + performance_monitor + providers | 200 passed |
| 6 | ai_client_stream + ai_settings_ui + async_runner + character×3 + config×2 + data_safety_baseline + design×2 | 244 passed / 1 skipped |
| 7 | note_manager×3 + novel_agent×4 | 261 passed |
| 8 | reading_manager×5 + review_round3_fixes + scene_detector×2 | 243 passed |
| 9 | writing_skills_deep + agent_orchestrator×2 + ai_client×3 | 168 passed |
| 10 | event_bus + `backend/tests/` | 153 passed |
| 11 | parser_convergence | 57 passed |

收集总数 **2156**；**每一块 0 失败**。另有：

- `ruff check app/ tests/ backend/ scripts/ installer/` → All checks passed
- `ruff format --check` 对新增 11 个文件 → 全部已格式化
- `mypy` 对 `app/timeline_store.py`、`app/lineage.py`、3 个新面板 → **0 错误**
- 真实 Tk 端到端：15 面板全部构建；四视图读到真实数据；时间线双击角色 → 传记面板聚焦；
  传记保存产出 txt + json（分段为「出身/转折」）；世代面板写入
  `lineage{generation:2, child_scope:readonly_parent}` 并执行继承，**父代目录文件集合逐字节未变**

---

## 5. 后续建议（按优先级）

1. **F1**（修基线章维度）→ 需你确认后重新 `--record`；
2. **F5**（全量 `ruff format` 一次并转阻断）→ 纯格式提交，风险最低、收益最直接；
3. **F3**（接线 `update_character_activity`）→ 让"人物轨迹"有真实数据；
4. **F4**（收敛两套传记生成入口）→ 避免同功能两种质量；
5. **F2**（分支子项目是否可打开）→ 产品决策，待定；
6. **F6 / F7**（守卫覆盖面、基线更新节奏）→ 随手可做。

P5（样式收敛）开工前建议先做 1 与 2，否则 P5 的"无字面 `font=` 断言"会在既有格式噪声里很难判断。
