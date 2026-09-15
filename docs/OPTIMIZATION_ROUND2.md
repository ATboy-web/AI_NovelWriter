# 全项目优化（第二轮）：问题分析 · 方案 · 实施记录

- 日期：2026-09-16
- 范围：桌面端 `app/` + 根级模块 + 依赖声明 + 测试
- 前置约束（用户指定，最高优先级）：**角色管理器中已有角色名称不得删除，它们均为小说内容资产**
- 数据基线（改动前实测）：`~/.ai_novel_writer/novels/` 下 **1 部小说 / 286 个角色 / 1094 章**；
  `memory/characters.json` 49,086 B，sha256 `fdd2d44d1739`；`characters/` 目录 286 个 JSON。

---

## 1. 问题分析（均附代码证据）

### 1.1 健壮性 —— 角色数据存在多条真实丢失路径

| 编号 | 问题 | 证据 | 后果 |
|---|---|---|---|
| **R1** | **角色生成会整体覆盖既有角色集** | `app/novel_agent.py:1149` `chars = self._parse_json_response(response, None)`（仅本次 AI 生成的角色）→ `:1259` `self.memory.save_characters(chars)` | 对已有小说的角色做一次「AI 生成角色」，`memory/characters.json` 就被**整个替换成新批次**，既有角色名全部消失。这就是「已有角色名不可删除」所指向的风险 |
| **R2** | **写入非原子** | `app/memory_manager.py:687` `open(..., 'w')` 后 `json.dump`；`app/character_system.py:563` 同样 | 写入过程中崩溃/断电/磁盘满 → 文件被截断，286 个角色一次性不可读 |
| **R3** | **读取损坏无回退、且可能级联成空覆盖** | `memory_manager.py:690-694` `json.load` 无异常处理 | 文件损坏后若某调用方以 `{}` 兜底再回写，等于清空角色库 |
| **R4** | **读-改-写无并发保护（丢失更新）** | `memory_manager.py:696-709` `update_character` 无锁；`app/character_ui.py:326-330` 在后台线程读完 286 个角色、生成传记（可达 20 万字）后再整体回写 | 传记生成期间其它线程新增的角色，被这次回写**静默覆盖丢失** |
| **R5** | **重命名中途失败会丢角色** | `character_system.py:543-555`：先 `pop` + `unlink(旧文件)`，最后才 `save_character(新名)` | 删旧成功、写新失败 → 角色文件与内存条目双双消失 |
| **R6** | **损坏角色文件被静默跳过** | `character_system.py:403-410` `except Exception: pass` | 286 个文件里任何一个损坏，该角色在管理器中直接"消失"，且无任何日志 |
| **R7** | **原子写的临时文件名会碰撞** | `app/persistence_ui.py:117-122` `filepath.with_suffix('.tmp')` | `settings.json` 与 `settings.md` 同目录 → 都映射到 `settings.tmp`；并发写会互相破坏 |
| **R8** | 异常被静默吞掉 | `app/character_ui.py:569` `except Exception: pass`（成长日志渲染）；`persistence_ui.py:84/94/115` | 故障不可观测 |

### 1.2 结构 —— 分层与包边界

| 编号 | 问题 | 证据 |
|---|---|---|
| **S1** | 4 个业务模块游离在包外 | `character_system.py`(905)、`novel_toolkit.py`(650)、`format_converter.py`(512)、`cloud_storage.py`(821) 位于仓库根，而 `pyproject.toml:41-42` 只把 `app*` 声明为发行包 → `pip install` 出的包**缺少这 4 个被 `app/` 依赖的模块**。它们还出现在 `installer/novel_app.spec:54-57` 的 hiddenimports |
| **S2** | 同一份「AI JSON 清洗」逻辑三处重复且已漂移 | `app/character_ui.py:34-73` 与 `:92-126` 是两份近似实现；`app/parsing.py` 第三份。且两份都做 `replace('，', ',')` —— **会把角色性格里的中文逗号（"温和，善良"）改成半角**，属文本破坏 |
| **S3** | 原子写被实现 4 次 | `persistence_ui._atomic_write`、`_atomic_json_write`、`memory_manager.save_characters`、`character_system.save_character`、`novel_agent.py:1249` 各写一份 |

### 1.3 可达性 —— 已写好却点不到的能力

| 编号 | 问题 | 证据 |
|---|---|---|
| **A1** | 角色「详情」对话框零入口 | `character_ui.py:702 _show_char_detail`（76 行，含重命名/删除/休息恢复/故事线 4 个操作）在全仓**零调用**；`shell_ui.py:371-379` 只提供 新建/AI生成/传记 三个按钮 | 
| **A2** | 全屏写作 AI 开关零入口 | `app/fullscreen_writer.py:383 _toggle_ai` 零调用 |

### 1.4 死代码 / 依赖 / 工程

| 编号 | 问题 | 证据 |
|---|---|---|
| **D1** | `_show_image_prompt_dialog`（113 行）零调用 | `app/toolkit_ui.py:419` 定义；调用者 `_detect_and_prompt_image` 走的是另一条路径（`generation_ui.py:387/1688`） |
| **D2** | `_run_async`（17 行）零调用 | `app/shell_ui.py:23`；手工 `threading.Thread(` 仍有 42 处 → "公共线程执行器"从未落地 |
| **D3** | `_atomic_json_write` 零调用 | `app/persistence_ui.py:123` |
| **D4** | `chromadb` 是全部桌面用户的强制依赖，但桌面端零使用 | `pyproject.toml:19` 硬依赖；`installer/novel_app.spec:79` 反而把它列进 `excludes`；唯一使用者是 `backend/novel-service`（自带 requirements） |
| **D5** | 根 `test_generators.py` 被 git 跟踪却永不执行 | 它是 print 脚本，不在 `testpaths=["tests","backend/tests"]`；直接放进 `tests/` 会被 pytest 误收集（函数带参数），且导入路径会把后端 `app` 包遮蔽桌面 `app` 包 |

---

## 2. 优化方案

### P0 数据安全（优先，直接保护 286 个角色）

| 措施 | 对应问题 |
|---|---|
| 新增 `app/storage.py`：统一原子写原语（唯一临时名 = `name.pid.tid.uuid.tmp` → `os.replace`；`write_json` 自动轮转 `.bak`；`read_json_with_backup` 返回状态而非静默兜底） | R2 R7 S3 |
| `MemoryManager.save_characters`：原子写 + `.bak` + **非空守卫**（新集合为空而磁盘非空 → 拒绝覆盖并告警） | R2 R3 |
| `MemoryManager.get_characters`：主文件损坏 → 回退 `.bak`；两者皆坏 → 记录错误并置 `_characters_corrupt` 标记，**读侧降级为空、写侧禁止覆盖**（既不崩也不清库） | R3 |
| 新增 `MemoryManager.mutate_characters()`：`_lock` 内完成读-改-写；`update_character` 改用它 | R4 |
| `character_ui._generate_character_biography` 改用 `mutate_characters`（消除最长窗口的丢失更新） | R4 |
| `CharacterSystem.save_character` 原子写；`rename_character` 改为**先写新文件、成功后再删旧文件** | R2 R5 |
| `CharacterSystem._load_all` 损坏文件改为 `logger.warning` + 计数 | R6 |
| `novel_agent.generate_characters`：保存改为**并集合并**（既有角色保留、仅补缺失字段），不再整体覆盖 | **R1（最高危）** |
| `character_ui._display_char_details` 的静默 `except` 改为记录日志 | R8 |

### P1 可达性

| 措施 | 对应问题 |
|---|---|
| `shell_ui` 角色按钮区新增「详情」按钮 → 打开 `_show_char_detail`，使 重命名 / 休息恢复 / 故事线 可达 | A1 |
| **该对话框不提供删除角色入口**（遵守约束：角色名为小说内容资产）；`_delete_character` 保留但注明「刻意不接线」 | 用户约束 |

### P2 结构 / 可维护性

| 措施 | 对应问题 |
|---|---|
| 4 个根模块迁入 `app/`（`app/character_system.py` 等），同步更新 16 处导入 + spec hiddenimports + 文档 | S1 |
| `app/parsing.py` 新增 `clean_ai_json_text`（**字符串感知**的全角标点修复：只处理字符串之外的 `：`/`，`），两处角色同步逻辑统一调用 | S2 |
| 删除 `_show_image_prompt_dialog`(113) / `_run_async`(17) / `_atomic_json_write`；`_atomic_write` 委托给 `app/storage.py` | D1 D2 D3 S3 |
| 根 `test_generators.py` → `scripts/smoke_generators.py`（保留脚本能力，消除"假测试"误导） | D5 |

### P3 依赖 / 工程

| 措施 | 对应问题 |
|---|---|
| `chromadb` 从必需依赖移入可选 extra `[vector]` | D4 |
| 清理空目录（`backend/auth-service/`、`backend/payment-service/` 等） | 结构卫生 |

### P4 测试（新增）

| 措施 |
|---|
| `tests/test_storage.py`：原子性、唯一临时名、`.bak` 轮转、损坏回退、`os.replace` 语义 |
| `tests/test_character_data_integrity.py`：**286 角色场景**下的增量写入零丢失、并发 `mutate` 不丢更新、空集覆盖被拒、`rename` 不丢文件、损坏文件不静默丢弃、角色生成走并集合并、删除入口未接线（源码级断言） |

---

## 3. 实施记录

### 3.1 新增/修改的代码

| 文件 | 动作 | 内容 |
|---|---|---|
| `app/storage.py` | **新增** | 统一原子写原语：`atomic_write_text` / `atomic_write_json` / `backup_file` / `read_json_with_backup` / `safe_filename`。临时名唯一（`<name>.<pid>.<tid>.<uuid8>.tmp`）；`read_json_with_backup` 返回 4 态（ok/backup/missing/corrupt），让调用方能区分"不存在"与"损坏" |
| `app/memory_manager.py` | 改 | `save_characters` 原子写 + `.bak` + **非空守卫**；`get_characters` 损坏回退 `.bak` 并置 `_characters_corrupt`；新增 `mutate_characters`（锁内读-改-写）；`update_character` 改走它；新增 `CharacterDataGuardError` / `CharacterDataCorruptError` |
| `app/novel_agent.py` | 改 | `generate_characters` 落盘改为**并集合并**（同名按新数据优先合并、未出现者原样保留）；角色文件改原子写；文件名消毒改用 `safe_filename` |
| `app/character_system.py` | 迁移+改 | 由仓库根迁入 `app/`；`save_character` 原子写；`rename_character` 改为**先写新文件、成功后再删旧文件**，失败回滚内存态；`_load_all` 损坏文件不再静默跳过 |
| `app/parsing.py` | 改 | 新增 `clean_ai_json_text`（字符串感知）/ `repair_ai_json_text` / `strip_ai_json_fences` / `parse_characters_payload` / `extract_characters_payload`；`parse_json_response` 的策略 3 改为"保真优先、朴素兜底"双候选 |
| `app/character_ui.py` | 改 | 两份漂移的角色同步逻辑收敛为 `_load_chars_from_memory` + 纯函数；传记写回改 `mutate_characters`；`_write_char_files` 原子写；静默 `except` 改为记录日志；**移除"删除角色"按钮** |
| `app/shell_ui.py` | 改 | 角色区新增「详情」按钮（接线 `_show_char_detail`）；删除零调用的 `_run_async` |
| `app/toolkit_ui.py` | 改 | 删除零调用的 `_show_image_prompt_dialog`（113 行） |
| `app/persistence_ui.py` | 改 | `_atomic_write` 委托 `app.storage`；删除 `_atomic_json_write`；检查点写入改原子写；3 处静默 `except` 改为记录日志 |
| `app/format_converter.py` / `app/cloud_storage.py` / `app/novel_toolkit.py` | 迁移+改 | 由仓库根迁入 `app/`；`novel_toolkit._ai_adapt` 修复 NameError（`{name}` 未定义）；清理死变量与未使用导入 |
| `scripts/smoke_generators.py` | 迁移 | 原根 `test_generators.py`，补写用途说明（为何不能放进 `tests/`） |
| `pyproject.toml` | 改 | `chromadb` → 可选 extra `[vector]` |
| `installer/novel_app.spec` | 改 | hiddenimports 更新为 `app.*`，并补 `app.storage` |
| `.github/workflows/ci.yml` | 改 | ruff 检查范围加入 `scripts/` |

### 3.2 测试与验证结果

| 验证项 | 结果 |
|---|---|
| 新增测试文件 | `tests/test_storage.py`、`tests/test_character_data_integrity.py`；`tests/test_parsing.py` 扩充 |
| 全量测试（`tests/` + `backend/tests/`，`--basetemp` 指向项目外） | **1322 passed / 0 failed / 0 error，退出码 0**（优化前基线 1246 → 新增 76 项），耗时 194s |
| Lint（`ruff check app/ tests/ backend/ scripts/`） | **All checks passed**（迁移进 `app/` 的 4 个模块此前从未被 lint 覆盖，暴露并修复了 1 个真实 bug + 2 处死变量 + 21 项存量风格问题） |
| 真实角色数据零改动 | 优化前后 `memory/characters.json` sha256 均为 `fdd2d44d1739`；286 角色 / 286 个角色文件均未变 |
| 副本端到端验证 | 读取 286 → 合并新批次后 288，**既有角色丢失 0 个**；空集合覆盖被守卫拒绝；`.bak` 正常生成；单角色原子写无 `.tmp` 残留 |
| 桌面入口可导入 | `import novel_app` OK（版本 2.16.0） |

### 3.3 未被本轮覆盖（有意保留）

- `_delete_character` / `CharacterSystem.delete_character`：按用户约束**保留但不接线**（角色名为小说内容资产）。
- 12 个面板、惰性构造的引擎、`_atomic_write` 等 6 项"看似死代码"：经复核为正常，见 `FEATURE_VALUE_ASSESSMENT.md` §8。
- `mobile-app/webview-app`、后端双实现、前端 React 补齐：需产品决策，见 `FEATURE_VALUE_ASSESSMENT.md` §7。

### 3.4 复跑提示（本机沙箱）

pytest 在会话结束时会批量删除临时目录。若 `--basetemp` 落在**项目目录内**，沙箱 safe-delete 的批量守卫（阈值 50 个文件）会拦截并 `SystemExit(1)`，表现为大量 `ERROR at setup`、丢失 summary，**并非测试失败**。复跑请把 basetemp 指到项目外：

```bash
python -m pytest -q --basetemp="$TEMP/anw_pytest_ci"
```

