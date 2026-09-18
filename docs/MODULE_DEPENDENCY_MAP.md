# 模块依赖关系图（自动生成）

> ⚠️ **本文件由 `scripts/module_graph.py` 从源码现算生成，请勿手工编辑。**
> 手工维护的依赖图必然漂移（本仓「同一事实写两处」已踩过 5 次）。
> 重新生成：`python scripts/module_graph.py`

## 1. 总览

| 指标 | 值 |
|---|---|
| 内部模块数 | 89 |
| 依赖边数 | 250 |
| 其中函数内延迟导入 | 42 |
| 循环依赖环数 | 2（**会真炸的：0**） |
| 语法错误文件 | 0 |

> **口径说明**：`if TYPE_CHECKING:` 里的 import **不计入** —— 运行时根本不执行。
> 把类型标注当依赖会凭空造出循环（实测误报过 `writing_skills_panel <-> novel_app`）。

## 2. 循环依赖

环分两类，**处置优先级完全不同**：

| 类型 | 判据 | 含义 |
|---|---|---|
| 🔴 **hard** | 环上**每条边都是模块级 import** | 导入期就会互相等待 ⇒ 真的会 `ImportError` |
| 🟡 **latent** | 环上**至少有一条延迟导入** | 当前不会炸，但结构脆弱：有人把那条延迟导入提到模块级，立刻变 hard |

### 🟡 环 1 · latent（3 个模块）

- `panels.base`
- `panels.legacy`
- `panels.registry`

| 边 | 种类 |
|---|---|
| `panels.base` → `panels.registry` | 🟡 延迟（函数内） |
| `panels.legacy` → `panels.base` | 🔴 模块级 |
| `panels.legacy` → `panels.registry` | 🔴 模块级 |
| `panels.registry` → `panels.base` | 🟡 延迟（函数内） |
| `panels.registry` → `panels.legacy` | 🟡 延迟（函数内） |

### 🟡 环 2 · latent（2 个模块）

- `config`
- `secure_config`

| 边 | 种类 |
|---|---|
| `config` → `secure_config` | 🟡 延迟（函数内） |
| `secure_config` → `config` | 🔴 模块级 |

## 3. 被依赖最多的模块（改动风险最高）

| 模块 | 被引用次数 |
|---|---|
| `app` | 30 |
| `dialogs` | 27 |
| `storage` | 19 |
| `ui_style` | 17 |
| `events` | 12 |
| `panels` | 11 |
| `panels.base` | 9 |
| `config` | 8 |
| `panels.ui_kit` | 8 |
| `async_runner` | 6 |
| `novel_toolkit` | 6 |
| `ai_client` | 5 |
| `diagnostic_logger` | 5 |
| `memory_manager` | 5 |
| `providers.base` | 5 |
| `token_estimator` | 5 |
| `panels.registry` | 4 |
| `parsing` | 4 |
| `usage_tracker` | 4 |
| `lineage` | 3 |

> 这些模块被最多人依赖 ⇒ 改它们的破坏面最大，应当优先保证测试覆盖。

## 4. 孤儿模块（无生产代码引用）

> ❗ 本仓最高频失效模式「注册即遗忘」的第一道筛查。
> 但要人工确认：**面板、入口脚本、按字符串加载的模块会正常出现在这里**。

- `design_tokens`
- `events.bus`
- `fullscreen_writer`
- `live_data`
- `note_manager`
- `novel_agent`
- `providers.registry`
- `reading_manager`
- `scene_detector`

## 5. 完整依赖表

| 模块 | 依赖（🔴=模块级 / ⚪=延迟） |
|---|---|
| `app` | — |
| `agent_orchestrator` | 🔴`ai_client`, 🔴`token_estimator` |
| `ai_client` | 🔴`config`, ⚪`diagnostic_logger`, ⚪`performance_monitor`, 🔴`providers`, 🔴`token_estimator`, 🔴`usage_tracker` |
| `ai_settings_ui` | 🔴`app`, ⚪`ai_client`, ⚪`async_runner`, 🔴`config`, 🔴`dialogs`, 🔴`providers` |
| `async_runner` | ⚪`app`, ⚪`dialogs` |
| `biography` | 🔴`storage` |
| `chapter_ui` | 🔴`app`, 🔴`dialogs`, 🔴`events` |
| `character_system` | 🔴`parsing`, 🔴`storage` |
| `character_ui` | 🔴`app`, 🔴`biography`, 🔴`character_system`, 🔴`dialogs`, 🔴`format_converter`, 🔴`memory_manager`, 🔴`parsing`, 🔴`storage`, 🔴`timeline_store` |
| `cloud_storage` | ⚪`secure_config` |
| `config` | ⚪`secure_config`, 🔴`storage` |
| `design_tokens` | 🔴`ui_style` |
| `diagnostic_logger` | — |
| `dialogs` | 🔴`ui_style` |
| `editor_ui` | 🔴`app`, 🔴`dialogs` |
| `events` | — |
| `events.bus` | — |
| `format_converter` | — |
| `fullscreen_writer` | 🔴`ai_client`, 🔴`config`, 🔴`ui_style` |
| `generation_ui` | 🔴`app`, ⚪`async_runner`, 🔴`diagnostic_logger`, 🔴`dialogs`, 🔴`parsing` |
| `genres` | 🔴`genres_data`, ⚪`storage` |
| `genres_data` | — |
| `image_generator` | 🔴`config` |
| `lifecycle_ui` | 🔴`app`, 🔴`dialogs`, 🔴`events`, 🔴`genres`, 🔴`storage` |
| `lineage` | 🔴`storage` |
| `live_data` | — |
| `mcp_system` | — |
| `memory_manager` | 🔴`events`, 🔴`storage` |
| `navigation` | — |
| `note_manager` | 🔴`config` |
| `note_ui` | 🔴`app`, 🔴`dialogs` |
| `novel_agent` | 🔴`agent_orchestrator`, 🔴`ai_client`, 🔴`config`, ⚪`diagnostic_logger`, ⚪`mcp_system`, 🔴`memory_manager`, 🔴`parsing`, 🔴`storage`, 🔴`token_estimator`, 🔴`usage_tracker`, ⚪`writing_skills` |
| `novel_store` | 🔴`storage` |
| `novel_toolkit` | — |
| `outline_ui` | 🔴`app`, 🔴`dialogs`, 🔴`token_estimator` |
| `panels` | — |
| `panels.adapt_panel` | 🔴`app`, 🔴`dialogs`, 🔴`novel_toolkit` |
| `panels.base` | ⚪`events`, ⚪`panels`, ⚪`panels.registry`, ⚪`panels.ui_kit` |
| `panels.batch_ops_panel` | 🔴`app`, 🔴`dialogs`, 🔴`ui_style` |
| `panels.biography_panel` | 🔴`biography`, 🔴`events`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, 🔴`storage`, 🔴`timeline_store`, 🔴`ui_style` |
| `panels.bridges_panel` | 🔴`app`, 🔴`dialogs` |
| `panels.chapter_analysis_panel` | 🔴`app`, 🔴`dialogs`, 🔴`ui_style` |
| `panels.descriptions_panel` | 🔴`app`, 🔴`dialogs` |
| `panels.dialogue_panel` | 🔴`app`, 🔴`dialogs`, 🔴`novel_toolkit` |
| `panels.elements_panel` | 🔴`app`, 🔴`dialogs` |
| `panels.host` | ⚪`app`, ⚪`events`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.layout`, 🔴`panels.registry`, ⚪`panels.ui_kit` |
| `panels.illustration_panel` | 🔴`async_runner`, 🔴`events`, ⚪`image_generator`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, 🔴`ui_style` |
| `panels.layout` | ⚪`storage` |
| `panels.legacy` | 🔴`panels.base`, 🔴`panels.registry` |
| `panels.lineage_panel` | 🔴`app`, 🔴`lineage`, ⚪`novel_store`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, 🔴`storage`, 🔴`ui_style` |
| `panels.mcp_panel` | 🔴`app`, 🔴`async_runner`, 🔴`dialogs`, 🔴`mcp_system`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, 🔴`ui_style` |
| `panels.memory_viz_panel` | 🔴`ui_style` |
| `panels.plugin_panel` | 🔴`app`, 🔴`async_runner`, 🔴`dialogs`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, 🔴`plugin_system`, 🔴`ui_style` |
| `panels.registry` | ⚪`panels`, ⚪`panels.base`, ⚪`panels.legacy` |
| `panels.story_flow_panel` | 🔴`app`, 🔴`dialogs`, 🔴`novel_toolkit`, 🔴`ui_style` |
| `panels.style_panel` | 🔴`app`, 🔴`dialogs`, 🔴`novel_toolkit` |
| `panels.summary_mgmt_panel` | 🔴`ui_style` |
| `panels.timeline_panel` | 🔴`events`, ⚪`memory_manager`, 🔴`panels`, 🔴`panels.base`, 🔴`panels.ui_kit`, ⚪`storage`, 🔴`timeline_store`, 🔴`ui_style` |
| `panels.ui_kit` | 🔴`ui_style` |
| `panels.websearch_panel` | 🔴`app`, 🔴`dialogs`, 🔴`novel_toolkit`, 🔴`ui_style` |
| `parsing` | — |
| `performance_monitor` | — |
| `persistence_ui` | 🔴`novel_store`, 🔴`storage` |
| `plugin_system` | — |
| `providers` | — |
| `providers.anthropic` | 🔴`providers.base` |
| `providers.balance` | — |
| `providers.base` | ⚪`providers.balance` |
| `providers.ollama` | 🔴`providers.base` |
| `providers.openai_compat` | 🔴`providers.base` |
| `providers.pricing` | — |
| `providers.reasoning` | 🔴`providers.base`, 🔴`providers.openai_compat` |
| `providers.registry` | 🔴`providers.anthropic`, 🔴`providers.base`, 🔴`providers.ollama`, 🔴`providers.openai_compat`, 🔴`providers.reasoning` |
| `reader_ui` | 🔴`app`, 🔴`dialogs` |
| `reading_manager` | 🔴`config` |
| `scene_detector` | — |
| `secure_config` | 🔴`config`, 🔴`storage` |
| `shell_ui` | 🔴`app`, ⚪`ai_client`, ⚪`diagnostic_logger`, 🔴`dialogs`, ⚪`performance_monitor` |
| `storage` | — |
| `timeline_store` | ⚪`events`, ⚪`lineage`, ⚪`memory_manager`, 🔴`storage` |
| `timeline_ui` | 🔴`app`, ⚪`character_system`, 🔴`dialogs`, 🔴`lineage`, ⚪`memory_manager`, 🔴`storage` |
| `token_estimator` | — |
| `toolkit_ui` | 🔴`app`, ⚪`diagnostic_logger`, 🔴`dialogs`, 🔴`format_converter`, 🔴`panels`, 🔴`panels.layout`, 🔴`panels.registry` |
| `ui_style` | — |
| `usage_tracker` | 🔴`events`, ⚪`providers.pricing`, 🔴`storage` |
| `usage_ui` | 🔴`app`, 🔴`async_runner`, 🔴`dialogs`, 🔴`events`, 🔴`providers`, 🔴`providers.balance`, 🔴`providers.pricing`, 🔴`token_estimator`, 🔴`usage_tracker` |
| `writing_skills` | ⚪`plugin_system` |
| `writing_skills_panel` | 🔴`app`, 🔴`dialogs`, ⚪`ui_style`, ⚪`writing_skills` |
| `novel_app` | 🔴`app`, 🔴`ai_settings_ui`, 🔴`chapter_ui`, 🔴`character_ui`, 🔴`cloud_storage`, 🔴`editor_ui`, 🔴`events`, 🔴`generation_ui`, 🔴`lifecycle_ui`, 🔴`navigation`, 🔴`note_ui`, 🔴`novel_toolkit`, 🔴`outline_ui`, 🔴`panels`, 🔴`persistence_ui`, 🔴`reader_ui`, 🔴`shell_ui`, 🔴`timeline_ui`, 🔴`toolkit_ui`, 🔴`usage_tracker`, 🔴`usage_ui`, 🔴`writing_skills_panel` |

## 6. 动态加载说明

（由 registry/legacy 按字符串加载，静态图看不到这条边）

受影响的模块：

- `panels.adapt_panel`
- `panels.base`
- `panels.batch_ops_panel`
- `panels.biography_panel`
- `panels.bridges_panel`
- `panels.chapter_analysis_panel`
- `panels.descriptions_panel`
- `panels.dialogue_panel`
- `panels.elements_panel`
- `panels.host`
- `panels.illustration_panel`
- `panels.layout`
- `panels.legacy`
- `panels.lineage_panel`
- `panels.mcp_panel`
- `panels.memory_viz_panel`
- `panels.plugin_panel`
- `panels.registry`
- `panels.story_flow_panel`
- `panels.style_panel`
- `panels.summary_mgmt_panel`
- `panels.timeline_panel`
- `panels.ui_kit`
- `panels.websearch_panel`
