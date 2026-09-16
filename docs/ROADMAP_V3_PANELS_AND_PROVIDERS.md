# AI_NovelWriter v3 改造方案：面板化 · 多 API 适配 · 模块整合

> 版本基线：`62bb854`（v2.16.0）｜测试基线：**1391 passed / 0 failed**｜ruff 全绿
> 角色数据基线：286 个角色，`memory/characters.json` sha256 `fdd2d44d…2db056`（49048 B）
> 本文所有事实均带 `文件:行号` 证据，来自对 `app/` 全部 50 个模块的实测勘察。

---

## 0. 先说三条会改变方案方向的勘察结论

**① 需求 4「为每种 API 设计各自的调用方法」——功能上已经存在，缺的是规范化。**
`ai_client.py` 里已有 7 个独立适配方法：

| provider | 方法 | 行号 | 请求路径 | 请求体特征 |
|---|---|---|---|---|
| 默认（openai 系） | `_chat_openai` | 722 | `/chat/completions` | 标准 OpenAI 体 |
| ollama | `_chat_ollama` | 763 | `/api/chat` | `options:{temperature,num_predict}` |
| claude | `_chat_claude` | 778 | `/v1/messages` | `system` 顶层字段、`max_tokens` 必填 |
| deepseek | `_chat_deepseek` | 801 | `/chat/completions` | `thinking:{type:enabled}` |
| glm | `_chat_glm` | 943 | `/chat/completions` | `thinking`，强制 `temperature=1.0` |
| qwen | `_chat_qwen` | 983 | `/chat/completions` | `enable_thinking:true` |
| kimi | `_chat_kimi` | 1019 | `/chat/completions` | `thinking:{type,keep}` |

所以本项**不是从零设计，而是把 7 个分支升级为「注册表 + 适配器接口」**。收益见 §4。

**② 「世界线/时间线」也已存在，且可达。**
`timeline_ui._open_timeline`（`timeline_ui.py:20`）弹窗标题就是「世界线 / 时间线」，
入口在 `shell_ui.py:213-217` 按钮，数据在 `novels/<名>/timelines/main.json`，已支持多世界线、分支、分支小说独立创作。
本项是**改造升级**（Toplevel → 面板、双存储打通、补地点/故事内时间），不是新建。

**③ 「合并模块」要克制——已有分层是清晰的，过度合并会破坏它。**
勘察确认 `toolkit_ui.py`（路由）→ `app/panels/*`（UI）→ `novel_toolkit.py`（引擎）是三层正确分层，
`grep "def _build_.*_tool"` 无重复定义。**这三层不应合并。** 真正的重复在别处（§1 有实证清单）。

---

## 1. 支柱一：模块整合与去重（有证据的清单）

### 1.1 真实重复项（建议合并/删除）

| # | 重复项 | 证据 | 处置 | 风险 |
|---|---|---|---|---|
| A1 | **AI JSON 解析双实现** | `parsing.py:396 parse_json_response` vs `novel_agent.py:1919-2036 _parse_json_response`（Strategy 1~5 结构雷同）；后者 `:2015` 还保留 parsing 已修掉的「剔除键含 raw」旧缺陷 | 删 novel_agent 版，6 处调用点（`860,1065,1150,1393,1434,1786`）改调 parsing | 中（核心链路） |
| A2 | **角色原始文本解析双实现** | `parsing.py:332 extract_characters_payload` vs `novel_agent.py:1836-1917 _extract_characters_from_raw`，后者被 `character_ui.py:66` 调用 | 同上收敛 | 中 |
| A3 | **设计令牌两套** | `design_tokens.py:12 DesignTokens.COLORS` 与 `ui_style.py:18 UIStyle.COLORS` 同值异名；`DesignTokens` 在 `app/` 内**零调用**，仅 `tests/test_design_tokens.py` 引用 | 合并为单一源（保留 `UIStyle` 命名空间），`design_tokens` 改为从 `UIStyle` 派生以不破坏既有 import | 低 |
| A4 | **UI 样式绕过令牌** | `font=('微软雅黑'` 硬编码 **372 处 / 23 个文件**（`lifecycle_ui.py:69`、`shell_ui.py:68`、`character_ui.py:54`…）；走令牌的仅 `ui_style.py:4` 处 | 新增 `UIStyle.font(size_key)` + 脚本批量替换，分文件推进 | 低（量大） |
| A5 | **`create_styled_*` 零调用** | `ui_style.py:326/353/369/391` 四个工厂方法全仓仅定义处命中 | **接线**（作为 A4 的落地载体），不删 | 低 |
| A6 | **线程执行器缺失** | 手工 `threading.Thread(` **40 处 / 17 文件**；`agent_orchestrator.py:5,18` 另用 `ThreadPoolExecutor` | 新增 `app/async_runner.py` 统一 | 中高（见 §5 风险） |
| A7 | **原子写被绕过** | 单入口 `storage.py` 已建成，但约 20 文件仍裸写。最危险的是**同一文件被三处各自裸写**：`outline.json` / `meta.json` ← `outline_ui.py:75/93/229/309/354`、`generation_ui.py:99/1404/1429/1611/1848/1859`、`timeline_ui.py:45/402/477/651` | 新增 `NovelStore` 领域级读写层，全部走 storage 原子写 | 中（数据一致性） |
| A8 | **同构对话框 36 处** | `Toplevel(` 36 处，归纳为三类同构：输入框+确定取消 / 列表+编辑 / 只读文本展示 | 抽 `app/dialogs.py` 三个helper | 低 |

### 1.2 死代码（已用 Grep 复核现状）

| 项 | 结论 | 证据 |
|---|---|---|
| `_atomic_json_write` | 已删除 ✅ | 仅 `tests/test_storage.py:196` 断言其不存在 |
| `_show_image_prompt_dialog` | 已删除 ✅ | app/ 零命中 |
| `_toggle_ai` | **仍存在、零调用** | 仅 `fullscreen_writer.py:383` 定义处 |
| `_run_async` | 从未实现 | 仅 `docs/TEAM_IMPROVEMENT_PLAN.md:185` 草案 |
| `performance_monitor.py` **整模块** | **app/ 内零调用** | 仅 `tests/test_performance_monitor.py` 引用 |
| `character_system.py` 约 25 个方法 | 零调用 | `mark_death:511`、`promote_character:529`、`simulate_battle:909`、`CharacterProfile.take_damage:318` 等 |

> 💡 **`performance_monitor.py` 不要删，要接线**：它已实现 HTTP 层耗时/百分位统计，
> 正好是 §3.4 用量统计里缺的「耗时」维度。复用它 = 一次同时完成「减少重复」和「增强功能」。

### 1.3 「看似重复实则不同」——不要合并

| 组合 | 判定 |
|---|---|
| `reader_ui.py` ↔ `fullscreen_writer.py` | 只读阅读 vs 可编辑写作，职责不同 |
| `note_ui.py` ↔ `memory_manager.py` | 用户便签 vs AI 摘要/世界观，数据源不同 |
| `panels/summary_mgmt_panel.py` ↔ `memory_manager.py` | 面板是 memory 的视图层，非重复实现 |
| `toolkit_ui.py` ↔ `panels/*` ↔ `novel_toolkit.py` | 路由/UI/引擎三层，**分层的正确形态** |

**唯一确认的「同一职责两实现」**：`editor_ui.py` ↔ `fullscreen_writer.py` 的正文编辑逻辑
（各自一套 Text 编辑 + 字数统计 + 保存 + 右键菜单）→ 抽 `app/text_editor.py` 共用组件。

---

## 2. 支柱二：面板框架 + 主面板联动

### 2.1 现状（决定了改造必须渐进）

- 12 个面板是**无基类的 Mixin**，唯一约定是方法名 `_build_<key>_tool(self)`（`elements_panel.py:7-10` 等）
- 无 `BasePanel`、无 `build()/render()`、**无生命周期钩子**、**无事件总线**（全仓零 `event_generate` / `subscribe` / `_listeners`）
- 分发靠 `toolkit_ui.py:26-49` 的 **12 路 `elif` 链**；UI 靠 `shell_ui.py:577-586` 的 12 个 Radiobutton
- 通信完全靠 MRO 共享同一个 `self`；跨面板联动只有两种土办法：
  `toolkit_ui.py:53-107 _insert_to_chapter(text_widget)` 回写主编辑器、`toolkit_ui.py:118 notebook.select(2)` 跳 tab
- **新增一个面板要改 5 处**：新建文件 + `panels/__init__.py` + `novel_app.py`（import + 继承列表）+ `shell_ui.py:577` + `toolkit_ui.py:26`

### 2.2 目标框架

```
app/panels/base.py          BasePanel 抽象基类 + @register_panel 装饰器
app/panels/registry.py      PANEL_REGISTRY: dict[str, type[BasePanel]]
app/panels/legacy.py        LegacyPanelAdapter —— 把既有 _build_<key>_tool 包装成 BasePanel
app/events/bus.py           EventBus（主题订阅/发布，主线程派发）
```

```python
class BasePanel:
    key: str            # "timeline"
    title: str          # "世界线与时间线"
    category: str       # 分组：创作素材 / 结构分析 / 记忆与摘要 / 世界与世代 / 运维
    order: int = 100

    def __init__(self, app): self.app = app

    # 关键技巧：让既有 12 个面板「一行不改」即可迁移
    def __getattr__(self, name):          # 仅在实例属性找不到时触发
        return getattr(self.app, name)

    def build(self, parent: tk.Widget) -> tk.Widget: ...   # 首次构建
    def on_show(self) -> None: ...                          # 每次显示（替代手工 refresh 调用）
    def on_hide(self) -> None: ...
    def on_event(self, topic: str, payload) -> None: ...     # 联动入口
    def detach(self) -> None: ...                            # 脱离为独立 Toplevel
```

**`__getattr__` 代理是迁移的关键**：既有面板大量直接用 `self.memory` / `self.ai_client` / `self.current_novel_dir`
（如 `memory_viz_panel.py:27`、`bridges_panel.py:51`、`memory_viz_panel.py:18`）。
有了代理，`LegacyPanelAdapter` 可以把它们包成 `BasePanel` 而**完全不改面板内的代码**，
`toolkit_ui.py:26-49` 的 12 路 `elif` 链即可删除，改为查注册表。

### 2.3 事件总线（联动的技术底座）

现有机制无法支撑「面板 ↔ 主面板联动」，必须新建。设计要点：

```python
class EventBus:
    def subscribe(self, topic: str, handler) -> Callable[[], None]: ...   # 返回取消订阅
    def publish(self, topic: str, payload=None) -> None: ...              # 要求在主线程
    def publish_threadsafe(self, topic, payload=None) -> None: ...         # 内部走 root.after(0, ...)
```

**主题用领域事件命名（而非 UI 事件）**：

| 主题 | 触发点 | 联动效果 |
|---|---|---|
| `novel.opened` / `novel.closed` | `lifecycle_ui` 打开/关闭 | 全部面板刷新到新小说 |
| `chapter.saved` | `chapter_ui` 保存、`finalize_chapter` | 时间线抽事件、用量面板更新该章 token、角色面板刷新出现章、记忆可视化刷新 |
| `outline.changed` | `NovelStore.write_outline` | 大纲类面板刷新 |
| `character.changed` | `memory_manager.save_characters` 成功后 | 角色/传记/时间线面板刷新 |
| `timeline.changed` | `memory_manager.add_event` 后 | 时间线面板增量追加 |
| `biography.generated` | 传记生成完成 | 角色卡片显示「已生成传记」徽标 |
| `ai.usage` | adapter 解析到 usage | 用量面板 + 状态栏 |
| `config.changed` | 设置保存 | `ai_client` 重建客户端 |

⚠️ **`publish` 必须在主线程**：Tk 非线程安全，而本仓 40 处 `threading.Thread` 都在子线程里干活。
故提供 `publish_threadsafe`，内部统一 `self.root.after(0, ...)`——与既有做法（`bridges_panel.py:74`）一致。

### 2.4 三个新面板的具体设计

#### ① 世界线与时间线面板（改造 `timeline_ui`）

**现状**：`timeline_ui.py:20 _open_timeline` Toplevel 弹窗；数据 `timelines/main.json`
`{"name":"主线","events":[],"chapters":[],"branches":[]}`（`:44`）；
分支项 `{chapter,decision,chosen,alternative,story}`（`generation_ui.py:813-819`）；
成章后由 `generation_ui._auto_detect_decisions:708` 自动写入。

**❗ 关键缺陷：两套时间线存储互不关联**
- `novels/<名>/timelines/main.json`（世界线/分支，`timeline_ui.py:39`）
- `novels/<名>/memory/timeline/timeline_%03d.json`（事件流，`memory_manager.py:116,689`）

**改造方案**：
1. 新增 `app/timeline_store.py` 作为**唯一权威**：以 `memory/timeline/` 为事件源，
   合并重建 `timelines/main.json` 的 `events`；`add_event` 后 publish `timeline.changed` 触发增量同步
2. 事件补字段：`location`（地点）、`story_time`（故事内时间）、`arc`、`source`（auto/manual）、`confidence`
   —— 现在 `add_event`（`memory_manager.py:676`）只有 `chapter + timestamp + characters`，**无地点与故事内时间**
3. 从正文抽取事件：复用 `scene_detector.py:191 detect(content)` 的分句能力 + 新增抽取 prompt
   （注意 `scene_detector` 现为配图服务，输出 `text,keyword,type,prompt,...`，需另加事件抽取函数，不要污染它）
4. 四视图：章节轴 / 世界线分支图 / **人物轨迹泳道**（复用 `memory/character_activity.json`）/ 跨代编年史
5. 联动：点击事件 → 主编辑器跳到该章并高亮；点击人物 → 打开传记面板；
   分支节点 → 打开 `timelines/branch_%03d/` 分支项目（`:461-477`）

#### ② 角色传记面板

**现状**：`character_ui.py:219 _generate_character_biography`
→ 字数对话框（`:257-267`）→ 组装 system（角色 1000 字 + 世界观 500 字，`:300-322`）
→ prompt 仅带 `outline[:5]`（`:324`）→ `ai_client.chat`（`:328`）
→ 写 `biographies/<名>_传记.txt`（`:338-341`）
→ `memory.mutate_characters` 回写 `biography`（**截断 500 字**）+ `biography_file`（`:350-357`）

**三处可提升**：
1. **输入太薄**：只用 `char_info` + `outline[:5]`，**完全没用已写的章节正文**。
   改为接入 `memory.retrieve_relevant(角色名)`（`memory_manager.py:392`，倒排索引 RAG）
   + `memory/character_activity.json` 的出现章列表 + 时间线事件
2. **无结构**：只有 txt + 截断 500 字的字段。新增 `biographies/<名>.json`：
   `{name, version, generated_at, provider, model, tokens, sections:[{id,title,content}], arcs:[], sources:{chapters:[], timeline_events:[]}}`
   → 文本文件保留用于导出，JSON 作为结构化源
3. **与 `character_stories/<名>.json` 脱节**（`:862-866` 手工故事线，无 AI）
   → 面板内并列展示「AI 传记」与「手工故事线」，支持把 AI 生成的分段一键转成 story_arcs

**面板形态**：左列角色树（**286 个角色必须支持搜索/筛选**，复用 `category`/`faction`/`importance` 字段）+ 右区传记正文可编辑 + 素材侧栏显示「引用了几章 / 几个事件」
**联动**：订阅 `character.changed` / `timeline.changed`；生成完 publish `biography.generated`

#### ③ 世代传承面板（"小说续写第二代"）

**现状**：`lifecycle_ui.py:674 _create_sequel` 建第二部目录，**只复制 `memory/settings.json` + `characters/`**（`:775-794`）；
meta 记 `is_sequel / original_novel / original_title`（`:758-771`）；另有 `_create_spinoff:815` 同人分支。

**缺失（勘察确认）**：不继承 `arcs/`、`volumes/`、`outline.json`、`timelines/`、`chunks/`；续集起点只有 `sequel_concept.txt`；`original_novel` 仅记录不参与上下文；**无「代」的层级模型**。

**改造方案**：
1. meta 增 `lineage`：
   ```json
   {"generation": 2, "parent_novel": "<dir>", "parent_title": "…",
    "era_gap_years": 20, "inherited": {"characters":true,"settings":true,
    "outline":true,"timeline":true,"memory":true,"plots":true},
    "child_scope": "readonly_parent"}
   ```
2. **继承策略（可勾选，默认全继承）**：
   | 维度 | 现状 | 方案 |
   |---|---|---|
   | 角色 | 复制 | 复制 + 年龄推进（`age += era_gap_years`）；**死亡角色转「已故/传说」状态而非删除** |
   | 世界观 | 复制 | 保持 |
   | 大纲 | ❌ 不继承 | 以父代 `outline.json` 末尾若干章 + `overall.json` 生成续集起点 |
   | 时间线 | ❌ 不继承 | 父代 `timelines/main.json` 作为「前代史」导入，标 `generation: N-1`、**只读** |
   | 记忆 | 仅 settings | 增 `global_summary.txt` + 最后 N 章摘要 + `arcs/` |
   | 伏笔 | 关键词抽取（`novel_agent.py:463-491`） | 结构化继承未回收伏笔清单，作为续集必处理项 |
3. **代际树视图**：第1代 → 第2代 → 同人分支，点击切换当前小说
4. **联动**：切换代 → publish `novel.opened` → 全部面板刷新；时间线面板显示跨代编年史（父代事件灰显）

> 🚨 **硬护栏**：子代**只读**父代目录。`child_scope: readonly_parent` 配合路径白名单，
> 并写测试断言「子代任何写操作不落在父代目录」。这是本次改造中数据风险最高的一处。

---

## 3. 支柱三：多 API 适配 · 配置完善 · 余额查询 · Token 统计

### 3.1 现状与真实缺陷（必须在重构中一并修掉）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| P1 | **claude 分支忽略配置的 `api_base`** | `ai_client.py:489-497` 硬编码 `https://api.anthropic.com` | 用户**无法**用中转/代理地址 |
| P2 | **路径拼接隐式且不一致** | deepseek base=`https://api.deepseek.com` → 拼出 `/chat/completions`（无 `/v1`）；openai/mimo/kimi 的 base 自带 `/v1` | 极易配错，且报错难懂 |
| P3 | **`_is_transient_error` 是死代码** | `ai_client.py:74-86`（判据含 `TransportError` 与 `status >= 500`）；真实重试在 `_dispatch_with_retry:918-939`，`:933` 判据**内联**为 `status == 429` | 5xx 与网络错误**不重试**，仅交给既有模型降级链（`FALLBACK_CHAIN:417-432`）；该函数写好的判据从未生效 |
| P4 | **伪 provider 无默认 base_url** | `_detect_provider:864-889` 造出 `glm/qwen/kimi`，但它们**不在** `PROVIDERS`(407-415) 里 | 用户填 qwen 模型名 → 特殊参数发到**别家地址** |
| P5 | **UI 下拉与 PROVIDERS 不一致** | `lifecycle_ui.py:1015` 列表含 `siliconflow/together/groq/dashscope`（无 PROVIDERS 条目，靠 `API_PRESETS:1032-1042` 补），却缺 `mimo/kimi` | 两处手工维护，必然漂移 |
| P6 | **usage 只在 2 条路径解析** | 有：`_chat_openai:740-746`、`_parse_thinking_response:1071-1077`；**无**：`_chat_ollama:763-776`、`_chat_claude:778-799`、全部 `_stream_*` | token 统计缺失 |
| P7 | **无 402/余额/配额概念** | 全仓无 `402`/`balance`/`quota` 分支 | 余额不足时只报一个通用 HTTP 错 |
| P8 | **成本恒为 0** | `AIMetrics:89-128` 有 cost 字段，`chat` 里 `metrics.record(latency)` **未传 cost** | 成本统计形同虚设 |
| P9 | **配置层缺 6 个关键项** | `config.py:9-27` 仅 17 项，**无** `timeout`（超时硬编码 `600.0`/`300.0` 于 `ai_client.py:496,499,504`）/`max_retries`/`thinking_enabled`/`reasoning_effort`；`max_tokens` **UI 不可编辑** | 超时/重试/思考模式全部硬编码 |
| P10 | **`api_key/base/model` 是全局单份** | `DEFAULT_CONFIG` 只有一组 | 切 provider 必须重填密钥，无法并存 |
| P11 | 温度控件重复定义 | `lifecycle_ui.py:1075-1077` 与 `1079-1081`，后者覆盖前者 | 前者永远无效 |

### 3.2 目标架构：Provider 注册表 + 适配器（同时解决需求 3 与 4）

```
app/providers/
├── __init__.py         ProviderRegistry: register / get / list_all / specs()
├── base.py             ProviderSpec(dataclass) + ProviderAdapter(ABC) + Capabilities
├── openai_compat.py    OpenAI 兼容通用适配器（覆盖 openai / deepseek / mimo / kimi /
│                       siliconflow / together / groq / dashscope / custom）
├── anthropic.py        claude（/v1/messages + x-api-key）
├── ollama.py           ollama（/api/chat + prompt_eval_count）
├── reasoning.py        glm / qwen / kimi-thinking 等特殊 thinking 参数
├── balance.py          余额查询适配（按 provider）
└── pricing.py          价目表（可配置，用于成本估算）
```

```python
class AuthStyle(Enum):
    BEARER = "bearer"; X_API_KEY = "x-api-key"; NONE = "none"; CUSTOM = "custom"

@dataclass(frozen=True)
class ProviderSpec:
    key: str; name: str
    base_url: str; default_model: str; models: tuple[str, ...]
    auth: AuthStyle
    chat_path: str                      # "/chat/completions" | "/v1/messages" | "/api/chat"
    base_url_includes_v1: bool          # 显式声明，修掉 P2 的隐式拼接
    supports: Capabilities              # streaming / thinking / usage / balance / json_mode
    default_headers: Mapping[str, str]
    extra_body: Mapping[str, Any]

class ProviderAdapter(ABC):
    spec: ProviderSpec
    def build_request(self, req: ChatRequest) -> PreparedRequest: ...   # 需求 4 的核心
    def parse_response(self, data: dict) -> ChatResult: ...             # text/reasoning/usage
    def parse_stream_chunk(self, line: str) -> StreamDelta | None: ...
    def is_transient(self, exc: Exception) -> bool: ...                 # 修 P3
    def query_balance(self, client) -> BalanceResult: ...               # 默认 NotSupported
```

**收敛工作量**：`_dispatch_chat` 的 elif 链（`900-916`）+ 7 个 `_chat_*`（`722/763/778/801/943/983/1019`）
+ 2 套 `_stream_*`（`678/699`）→ 「查注册表 → 调 adapter」。
`chat()`（`:541`）与 `chat_stream()`（`:664`）**对外签名不变**，53 个调用点无需改动。

**新增一家 API 的成本**：现在要改 4 处（`elif` + `_chat_*` + UI 下拉 + `API_PRESETS`）
→ 之后只需**新建一个 adapter 文件**。

### 3.3 配置项完善（分层 + 多 Profile）

```jsonc
{
  "ai": {
    "active_profile": "deepseek",
    "profiles": {
      "deepseek": {
        "api_key": "<Fernet 密文>", "api_base": "https://api.deepseek.com",
        "model": "deepseek-chat", "max_tokens": 4096, "temperature": 0.8,
        "timeout": 60, "max_retries": 3, "connect_timeout": 10,
        "thinking_enabled": true, "reasoning_effort": "medium",
        "extra_headers": {}, "extra_body": {}
      }
    },
    "context_window": 32000, "usage_tracking": true
  }
}
```

- **修 P9/P10**：补齐 `timeout / max_retries / connect_timeout / thinking_enabled / reasoning_effort`；
  每个 provider 独立保存密钥与模型（切 provider 不再重填）
- **修 P5**：设置页 provider 下拉**从注册表自动生成**；表单按 `spec.supports` 显隐
  （ollama 隐藏 api_key 与余额按钮；claude 提示 `max_tokens` 必填）
- 新增三个按钮：**测试连接** / **查询余额** / **请求 URL 预览**（预览直接消除 P2 那类配置困惑）
- 顺手修 P11（删重复的温度控件）
- **迁移必须幂等 + 先备份**：旧扁平字段 → 生成 `profiles[旧provider]` → 写回；
  旧键**保留只读**一段时间以便回滚
- 密钥继续走 `secure_config`（Fernet + DPAPI，字段级加密 `secure_config.py:251-278`），
  但加密字段白名单需支持 `ai.profiles.*.api_key` 通配 → **必须加「落盘无明文」断言测试**

### 3.4 余额查询（需求 3）—— 必须诚实：**不是每家都有余额接口**

| provider | 余额能力 | 说明 |
|---|---|---|
| **DeepSeek** | ✅ `GET /user/balance` | 返回现金/赠金余额与币种 |
| **Moonshot / Kimi** | ✅ 有余额接口 | 以上线时官方文档为准 |
| **OpenAI** | ❌ 无可用余额 API | 原 `/v1/dashboard/billing/*` 需 session key，不可用于 PAT/API Key。退化为「本会话消耗统计」 |
| **智谱 GLM** | ❌ 无公开余额 API | 显示「该服务未提供余额接口」 |
| **Anthropic** | ❌ 无公开余额 API | 同上 |
| **Ollama** | N/A | 显示「本地模型，无计费」 |
| **siliconflow / together / groq / dashscope** | ⚠️ 多数无 | 逐家核实 |

**设计**：`BalanceResult = {supported, currency, total, granted, topped_up, fetched_at, raw, error}`
- 不支持时 UI **明确显示「该服务未提供余额接口」**，而不是报错或空白（避免用户误以为功能坏了）
- **把余额 URL 与 JSON 取值路径做成可配置项**（`balance_url` + `balance_json_path`）：
  这样即使某家改了接口，用户也能自己填，不必等我们发版 —— 这是本功能长期可用性的关键
- 加 60s 缓存，避免频繁请求触发限流

### 3.5 每章 Token 消耗统计（需求 3）

**现状**：`TokenStats`（`ai_client.py:34-71`，含锁 + `get_summary` + `get_display`）是**全局内存累计**；
只在 2 条路径记录（P6）；`shell_ui.py:655-658` 在状态栏显示。
**缺**：按章归因、持久化（重启即失）、估算兜底、成本、耗时关联。

**方案**：

**(1) 归因机制** —— 用 `contextvars.ContextVar`，避免侵入 53 个调用点：
```python
_ctx = ContextVar("anw_usage_ctx", default=None)   # {novel_dir, chapter, task, generation}
```
由 `novel_agent.generate_chapter` 设置 `chapter=N`，UI 面板设置 `task="biography"` 等；
adapter 解析到 usage 时读取该上下文完成归因。

> ⚠️ **必须注意的真实坑**：`contextvars` 在 `threading.Thread` 里**不会继承**父上下文
> （与 asyncio 不同）。本仓有 **40 处手工线程** → 必须写成
> `ctx = contextvars.copy_context(); Thread(target=ctx.run, args=(fn,))`。
> **这正好与 §1.1 A6 的 `async_runner` 合并解决**——统一执行器内做好 `copy_context`，
> 40 处调用点自动获得正确的归因上下文。一次改造同时完成「减少重复」与「统计可用」。

**(2) 持久化**：
```
novels/<名>/usage/usage.jsonl     # 追加式明细，每行一条调用记录
novels/<名>/usage/summary.json    # 聚合（走 storage 原子写）
```
记录字段：`{ts, provider, model, chapter, generation, task, prompt_tokens, completion_tokens,
total_tokens, estimated, latency_ms, cost, cost_currency}`

**(3) 估算兜底**（P6 的 provider 不返回 usage 时）：
新增 `app/token_estimator.py`。现状只有 `len(context)//2`（`agent_orchestrator.py:122`）+ `context_window//3`（`novel_agent.py:293`），
过于粗糙（中文场景 `len//2` 会明显低估）。
改进：**汉字数 × 1.6 + 非汉字字符数 ÷ 4**（中英混排更准），并**统一**上述三处散落估算。
**不建议引入 tiktoken**：只覆盖 OpenAI 系、会增大打包体积（当前 EXE 19MB，spec 里已 `excludes` numpy 等）。
用估算 + `estimated: true` 标记，UI 上区分「实测/估算」，成本计算对估算值降权提示。

**(4) 成本（修 P8）**：`app/providers/pricing.py` 价目表（**用户可编辑**，UI 标注「默认价目可能过期」），
`cost = prompt_tokens × in_price + completion_tokens × out_price`，接回 `AIMetrics`。

**(5) 展示**：新增「用量统计」面板
- 按章表格：章号 / 实测·估算 / prompt·completion / 模型 / 耗时 / 成本
- 按 provider、按任务类型（大纲 / 正文 / 审校 / 传记 / 摘要）分布
- 章节列表每章旁显示 token 徽标
- 导出 CSV

**(6) 复用 `performance_monitor`**：把零调用的 `performance_monitor.py` 接入 AI 调用链补「耗时/百分位」维度（见 §1.2）。

---

## 4. 支柱四：每种 API 各自的调用方法（落地形态）

**核心结论：不做"每家有各自一套代码"的散装实现，而是「统一接口 + 独立实现」——接口统一才可维护，实现独立才够灵活。**

| 层面 | 统一（所有 provider 共用） | 独立（每个 adapter 自己实现） |
|---|---|---|
| 入口 | `AIClient.chat()` / `chat_stream()` 签名不变 | — |
| 请求 | 重试/退避/超时/日志/用量归因框架 | `build_request()`：URL 路径、鉴权头、请求体字段、参数改名 |
| 响应 | 归因、持久化、统计、UI 展示 | `parse_response()`：取文本、取 reasoning、取 usage |
| 流式 | 分片循环、缓冲、错误处理 | `parse_stream_chunk()`：SSE 格式差异 |
| 错误 | 统一异常类型与用户提示 | `is_transient()`：哪类错误值得重试 |
| 能力 | 能力查询 API | `spec.supports`：声明式声明 |

**7 家迁移对照（现有 → 目标）**：

| provider | 现有实现 | 目标 adapter | 迁移中要修的 |
|---|---|---|---|
| openai 系 | `_chat_openai:722` | `OpenAICompatAdapter` | 路径显式化（P2） |
| deepseek | `_chat_deepseek:801` | `OpenAICompatAdapter` + `extra_body` | 补 `/v1` 语义（P2） |
| mimo / kimi | 无专属方法（走默认） | `OpenAICompatAdapter` | 纳入注册表（P4） |
| siliconflow / together / groq / dashscope | 仅 `API_PRESETS:1032` | `OpenAICompatAdapter` | 从 UI 常量升为注册表条目（P5） |
| claude | `_chat_claude:778` | `AnthropicAdapter` | **尊重 `api_base`（P1）** + 解析 usage（P6） |
| ollama | `_chat_ollama:763` | `OllamaAdapter` | 解析 `prompt_eval_count`/`eval_count`（P6） |
| glm | `_chat_glm:943` | `ReasoningAdapter(glm)` | 纳入注册表（P4） |
| qwen | `_chat_qwen:983` | `ReasoningAdapter(qwen)` | 纳入注册表（P4） |
| kimi-thinking | `_chat_kimi:1019` | `ReasoningAdapter(kimi)` | 与 `kimi` 统一为一家多模式 |

---

## 5. 实施路线图（5 期，每期独立可交付、可回滚）

| 期 | 内容 | 交付物 | 验收标准 | 风险 |
|---|---|---|---|---|
| **P0** 护栏先行 | 固化基线；新增数据安全测试 | 基线脚本 + 角色 sha256 断言 + 跨代只读断言 | 基线可一键复跑 | 无（不改代码） |
| **P1** 去重 | A1 A2 A3 A7(最小集) A8 | 删除双解析、统一 outline/meta 写盘、令牌单一源 | 1391 全绿 + ruff + 角色 sha256 **不变** | 中 |
| **P2** 多 API 底座 | §3.2 注册表 + 7 家迁移 + §3.3 配置分层 | `app/providers/` + 配置迁移器 + 设置页重构 | 每个 adapter 有单测；打包成功；**修掉 P1–P5、P9–P11** | 中高 |
| **P3** 用量与余额 | §3.4 + §3.5 + `async_runner`(A6) | usage.jsonl + 估算器 + 价格表 + 用量面板 + 余额适配 + 接入 performance_monitor | 真实跑一次生成 → `usage.jsonl` 有该章记录；实测/估算标记正确 | 中 |
| **P4** 面板框架与联动 | §2.2 + §2.3 + §2.4 三个新面板 | BasePanel/注册表/EventBus + 12 老面板迁移 + 3 新面板 | 新增面板**只需 1 处改动**；联动场景测试通过 | 中高 |
| **P5** 样式与对话框收敛 | A4 A5 A7(余下) + 面板 detach | 字体令牌化、`create_styled_*` 接线、dialogs.py、独立窗口 | 无字面 `font=` 断言；UI 冒烟通过 | 低 |

**建议顺序理由**：P1 先做——它降低后续所有改动的心智负担且风险低；P2/P3 同属 AI 层，一起做可避免两次改动 `ai_client.py`；P4 最后做，因为它依赖 P3 产出的用量数据来展示联动效果。

---

## 6. 风险与护栏

### 🚨 数据安全（最高优先级）

| 风险 | 护栏 |
|---|---|
| **角色名被删除**（项目硬约束） | 所有新面板**不提供删除角色名的入口**；跨代继承中死亡角色转 `status=deceased` 而非删除；一切角色写操作走 `mutate_characters`（`memory_manager.py:845`，锁内读-改-写）；新增 sha256 回归测试 |
| **子代污染父代** | `child_scope: readonly_parent` + 路径白名单 + 测试断言「子代写操作不落在父代目录」 |
| **角色闸门被绕过** | 三道闸门（`memory_manager.py:756-791`）与 V4 抛错（`novel_agent.py:1283-1287`）不动；新功能若走 `save_characters` 必须理解闸门语义 |
| **配置迁移丢密钥** | 迁移前备份 `.config`；幂等；旧键保留读取可回滚；加「落盘无明文」断言 |
| **大纲/元数据并发覆盖** | A7 统一到 `NovelStore` 原子写 + 版本号 |

### ⚠️ 技术风险

1. **40 处线程改造**（A6）：4 类行为差异（`generation_ui.py:392/416/1924` 弹窗 / `toolkit_ui.py:105` 仅日志 / 静默 / 进度回调形态各异）
   → **先在 3 个低风险文件试点**，再批量。
   ❗ `fullscreen_writer.py:338/529` **在子线程内直接操作 Tk 组件**才 `after` —— 这是真实的线程安全 bug，
   改造中应修正，但**会改变行为**，需单独评估与回归。
2. **`contextvars` 不跨线程**：必须 `copy_context()`（§3.5），否则 40 处线程内的用量全部归因失败。
3. **打包**：新增 `app/providers/`、`app/events/`、`app/dialogs.py` 需同步更新
   `installer/novel_app.spec` 的 `hiddenimports`；`build.bat` 已可自动探测解释器（`62bb854`）；
   不引入 tiktoken 等重依赖以免 EXE 膨胀。
4. **1391 个测试**是本次改造最重要的安全网 —— 每期结束必须全绿，且 `ruff` 无新增告警。
5. **UI 回归**：面板框架改造涉及 `shell_ui.py:577` / `toolkit_ui.py:26` 两个高频路径，
   需人工冒烟（12 个老面板逐个点开）。

---

## 7. 测试策略

| 层次 | 内容 |
|---|---|
| **Adapter 单测** | 每个 provider：请求 URL 与鉴权头正确、请求体字段符合该家规范、响应解析（文本/reasoning/usage）、流式分片、`is_transient` 判据、余额能力声明 |
| **行为等价性** | A1/A2 解析器迁移用「同一批真实 AI 返回样本 → 新老实现输出逐字节相同」验证（延续项目既有的 AST/逐字节比对思路） |
| **数据安全** | 角色 sha256 不变、跨代只读、配置迁移幂等、密钥不明文、子代不写父代 |
| **事件总线** | 订阅/取消订阅、主线程派发、`publish_threadsafe` 在子线程调用后 UI 正确更新 |
| **用量统计** | 归因到正确章/任务、估算标记、usage.jsonl 追加与聚合一致性、重启后不丢失 |
| **端到端** | 一次「生成章节 → 保存 → 联动更新（时间线/用量/角色/记忆面板）」完整链路 |

---

## 8. 需要你决策的 5 个点

1. **P4 面板容器形态**：15+ 面板下，保持左侧 Radiobutton 列表（按 category 分组），
   还是升级为二级 `Notebook`？（推荐前者，改动小且与现有 `tool_content_frame` 兼容）
2. **「续写第二代」的继承默认值**：默认全继承（角色+世界观+大纲+时间线+记忆+伏笔），还是只继承角色+世界观（更接近现状）？
3. **`max_tokens` 是否放开给用户编辑**：放开会有「填过大导致请求失败/费用飙升」的风险，建议放开但加范围校验与提示。
4. **价目表来源**：内置一份默认价目（可能过期），还是留空让用户第一次使用时填写？（推荐内置 + 明确标注可编辑）
5. **是否接受删除 §1.2 的死代码**：`fullscreen_writer._toggle_ai`、`character_system.py` 约 25 个零调用方法。
   （`performance_monitor.py` 建议**保留并接线**，见 §1.2）

---

## 附：一页速览

```
需求①整合去重 ──→ §1：8 项真实重复（含 outline/meta 三处裸写、40 处手工线程、双 JSON 解析）
                  + 明确「哪些看似重复实则不同、不要合并」

需求②面板联动 ──→ §2：BasePanel + 注册表 + __getattr__ 代理（老面板零改动迁移）
                  + EventBus 领域事件（现完全不存在，是联动的必要前提）
                  + 3 个新面板：世界线时间线（改造 timeline_ui，打通两套存储）
                                角色传记（接入 RAG 与时间线，结构化 JSON）
                                世代传承（补齐大纲/时间线/记忆/伏笔继承 + 只读父代护栏）

需求③适配/配置/余额/用量 ──→ §3：注册表替代 elif 链；配置分层多 Profile；
                  余额能力矩阵（诚实标注哪些家没有接口）+ URL 可配置；
                  token 归因（contextvars + copy_context）+ usage.jsonl + 估算 + 成本

需求④各 API 独立调用方法 ──→ §4：已存在 7 个 _chat_*，本项是「统一接口 + 独立实现」的规范化，
                  新增一家 API 从改 4 处 → 新建 1 个文件
```
