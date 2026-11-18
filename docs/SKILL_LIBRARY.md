# 技能库（Skill Library）· 设计说明与验收记录

> 把外部 `SKILL.md` 技能包解析成**结构化、可检索、可注入**的写作能力。
> 首个落地的技能：[Lieflat · Less AI Tone（去 AI 味）](#真实技能验收lieflat-less-ai-tone)。

## 1. 它做什么 / 不做什么

| 做 | 不做 |
|---|---|
| 解析 YAML frontmatter（名称 / 说明 / 版本 / 授权） | **不执行**技能包里的 `scripts/*.py` |
| 按 Markdown 标题切分规则，并推断分级 | 不做第三方代码沙箱（那是插件系统的边界） |
| 抽 `add_argument` 与命令行示例里的调用参数 | 不联网下载技能（导入本地目录 / ZIP） |
| 识别适用场景与触发词 | 不自动替用户启用技能 |
| 导入 / 登记 / 启停 / 卸载 / 全文检索 | 不修改技能包原文 |
| 按当前稿件**自动匹配**技能 | 不用模型给技能打分（匹配是可解释的加权命中） |
| 装配成提示词并注入章节生成 | 不把 X / H 级规则注入 |

> 🔴 **为什么坚决不跑脚本**：技能包与主程序同等权限，无法沙箱化。
> `plugin_system.audit_plugin()` 的结论已经写明这一点（拦截既不可靠又会产生虚假安全感），
> 所以技能库只把脚本当**数据**读 —— 抽参数、列清单、在导入时提示"含可执行脚本"。
> 需要运行脚本时，由用户自己在本机终端确认后执行。

## 2. 文件与职责

| 文件 | 职责 |
|---|---|
| `app/skill_library.py` | 解析（纯函数）+ `SkillLibrary` 管理器 + 匹配 + 提示词装配 |
| `app/panels/skill_library_panel.py` | 第 19 个面板「技能库」（运维分组） |
| `app/panels/registry.py` | `NATIVE_PANEL_MODULES` 加一行（面板按字符串动态导入） |
| `installer/novel_app.spec` | `hiddenimports` 加 `app.panels.skill_library_panel` / `app.skill_library` |
| `app/novel_agent.py` | 唯一注入点：`【技能库规则】` 段 |
| `tests/test_skill_library.py` | 解析 / 安全 / 状态 / 匹配 / 注入 / 接线守卫（72 条） |
| `tests/test_skill_library_panel.py` | 渲染纯函数 + 真实 Tk 构建（10 条） |
| `tests/test_panel_controls_mounted.py` | 新面板纳入"控件必须被挂载"的守门清单 |

## 3. 解析契约

### 3.1 frontmatter

只支持技能包实际在用的两种写法，**不依赖 PyYAML**
（`pyyaml` 不在 `pyproject.toml` 依赖里，PyInstaller 也不会自动带）：

```yaml
---
name: demo-tone                 # 必填，缺省退化为目录名
description: 三层去 AI 味……      # 触发词与场景从这句话里抽
version: 1.2.0                  # 可选
author: 某某                    # 可选
description: >                  # 折叠块（多行）
  第一行
  第二行
---
```

- 带 BOM、`\r\n`、引号包裹的值都能处理；
- 解析失败**不抛异常**，写进 `warnings` 并在面板上显示。

### 3.2 规则切分与分级

按 `##` / `###` / `####` 切章节，然后：

| 判定 | 规则 |
|---|---|
| `workflow` | 标题形如 `第一步：…` / `第 1.5 步：…`，**不进规则集** |
| `rule` | 标题带编号（`1. 翻案腔`）、或含「规则 / 原则 / 清单 / 人审 / 验收 / 指纹 / 不改」 |
| `meta` | 其余（"豆包适配""商业授权提示"等） |
| **容器** | 二级/三级标题、无编号、正文不足 3 行且无列表 ⇒ 视为"前言"，**直接丢弃** |

分级（`RULE_LEVELS`，新增一级只改注册表一处）：

| 级别 | 含义 | 注入提示词 |
|---|---|---|
| `A` | 机械改（删掉/换成，不碰语义） | ✅ |
| `B` | 建议改（需句式重组） | ✅ |
| `C` | 只报告（整篇结构指标） | ✅（作为提示） |
| `F` | 单模型指纹 | ✅ |
| `H` | 人审区（模型判不准贴切度） | ❌ |
| `X` | 已否决（实测不是 AI 味） | ❌ **反向点名"禁止改动"** |
| `""` | 结构性章节（改写原则 / 不改的情况 / 最终验收） | ✅ |

分级来源写进 `level_source`：`explicit`（标题写明）/ `heuristic`（按"删掉/换成"等机械替换措辞推断）
/ `default`（结构章节）。**界面不把推断伪装成原文标注** —— 这一字段就是为此存在的。

### 3.3 调用参数

两个来源，**脚本优先**：

1. `add_argument("--flag", default=..., help=..., action="store_true")` —— 权威；
2. Markdown 代码块里出现的 `--flag` —— 补缺（技能常只在文档里写命令）。

`store_true` 的参数不带值，`signature()` 会渲染成 `--json` 而不是 `--json <值>`。

### 3.4 场景 / 触发词 / 示例

- **触发词**：`description` 中 `「…」` 包裹的短语（技能包的触发约定只有这一种写法）；
- **场景**：`description` 中含「适用于 / 用于 / 场景 / 时也用 / 触发」的句子；
- **示例**：规则正文里的 `> ❌ …` / `> ✅ …` 成对提取 —— 直接作为"效果预览"素材，
  不编造示例。

## 4. 目录与状态

| 路径 | 内容 |
|---|---|
| `~/.ai_novel_writer/skills/<key>/` | 导入的技能**内容**（`copy` 模式） |
| `~/.ai_novel_writer/skills.json` | 启用状态、模式（copy/ref）、来源、导入时间 |

两者**刻意分离**：删状态文件不丢技能，删技能目录也不留幽灵条目。
状态写入走 `storage.atomic_write_json(backup=True)`（原子替换 + `.bak` 轮转）。

- **导入（install）**：复制目录 / 解压 ZIP 进技能库；**先解析、后落盘**
  （解析不出 `SKILL.md` 立刻失败，不在库里留空目录）。
- **登记（register）**：只记录外部路径，不复制文件 —— 适合边改边看。
  目录被移走时，`reload()` 把失效登记记进 `load_failures` 而不是静默丢弃。
- **卸载**：`copy` 删目录，`ref` 只删登记。删除前校验
  `target.resolve().is_relative_to(skills_dir.resolve())` —— 状态文件可被手改，
  一个 `../..` 就能删到别处。

## 5. 提示词装配

```python
library.prompt_context(budget=900, text=当前正文或空)
```

顺序：`【技能名】` → 用途（预算 < 320 字时省略）→ **禁止改动（X 级条目）** →
可注入规则（`- [级别] 标题：改法`）。

三条硬约定：

1. **按规则边界截断**，绝不切在句子中间 —— 截半条规则比少一条更糟；
2. 截断必须**显式说明**"另有 N 条未注入"，否则用户会以为启用了却"没生效"；
3. 预算极小（标题已超）时才硬截，保证 `len(prompt) <= budget` 的契约成立。

注入点只有 `app/novel_agent.py` 一处（`【技能库规则】`，独立预算 ≤ 900 字）。
**不存在第二个注入点** —— 同一份规则注入两次会既浪费上下文又互相干扰。

> 顺带发现（未在本轮改动）：`plugin_skill_context()` 目前**被注入了两次** ——
> `WritingSkillManager.get_writing_context()` 内部一次、`novel_agent` 显式一次。
> 技能库刻意不复制这个形状；插件段是否收敛另行评估（会动既有行为与覆盖率）。

## 6. 面板（第 19 个 / 运维分组）

| 能力 | 位置 |
|---|---|
| 导入（目录 / ZIP）、登记目录、重新扫描 | 工具条 |
| 搜索（名称 / 说明 / 场景 / 规则正文） | 搜索框（Ctrl+F 可聚焦） |
| 浏览规则分级、场景、触发词、参数、文件清单 | 右侧详情 |
| **一键应用**（启用 + 立刻预览注入效果） | 详情按钮 |
| **预览注入**（原文 + 字数 + token + 作者自带 ❌/✅ 对照） | 详情按钮 |
| **匹配当前稿件**（相关度排序 + 命中理由） | 详情按钮 |
| 停用 / 卸载（`ref` 模式明确提示"不会删文件"） | 详情按钮 |
| 生效证据：已启用技能实际注入多少字 | 底栏 |

❗ 所有按钮都显式 `.pack()` —— `ui_kit.button / badge / section_title / hint`
**只创建控件不挂载**，漏了会静默不可见（见 `PACKAGING_AND_PANEL_PLAYBOOK` §4）。

## 7. 真实技能验收：`lieflat-less-ai-tone`

来源：`【刺客边风】Lieflat Less AI Tone`（豆包版，v2）。离线解析、未执行任何脚本。

| 项 | 结果 |
|---|---|
| 技能定位 | `find_skill_root()` 穿透「外层文件夹 / `-豆包版` / 技能目录」三层 |
| key / 名称 | `lieflat-less-ai-tone` |
| 授权 | frontmatter 无 → 自动识别 `LICENSE` 文件，显示"见 LICENSE 文件" |
| 规则 | **19 条**：A 4 / B 7 / F 2 / H 2 / X 1 / 结构 3 |
| 触发词 | 6 个：去AI味 / 加点人味 / AI味太重 / 读着像机器人写的 / 润色成真人语气 / 改稿别那么AI |
| 场景 | 2 条（"适用于写作完成后的成稿清理"等） |
| 调用参数 | **9 个**（`--max-hits` / `--json-out` / `--candidates` / `--out` / `--format` …） |
| 文件 | 25 个：脚本 5 · 参考 1 · 示例 9 · 素材 2 · 文档 6 · 其它 2 |
| 示例对照 | **11 组** `❌ / ✅` |
| X 级条目 | 9 个（序数词小标题、「这意味着」复述、空转句引列表…）→ 只用于"禁止改动" |
| 注入（budget=900） | 787 字 / 约 1000 tokens，可注入规则按预算顺序装入 |
| 匹配自检 | 输入"读着像机器人写的、AI味太重" → 命中 2 条触发词，相关度 0.44 |

解析警告为空；`warnings` 仅在缺 frontmatter / 缺 description / 入口过大 / 无规则时出现。

## 8. 安全边界

| 风险 | 处置 |
|---|---|
| 技能包带 `scripts/*.py` | **不执行**；导入时弹模态提示"含可执行脚本" |
| ZIP Slip（`../../x`） | 复用 `plugin_system.safe_extract()`（`is_relative_to` 校验），有测试 |
| key 带路径分隔符 | `sanitize_skill_key()` 清洗；`..` 直接拒绝 |
| 卸载越界 | 删除前 `is_relative_to(skills_dir)` 二次校验，有测试 |
| 超大入口文件 | `MAX_ENTRY_BYTES = 2 MiB`，超限拒绝解析 |
| 文件数爆炸（node_modules） | `MAX_SKILL_FILES = 500` + 目录黑名单 |
| 编码损坏 | 一律 `errors="replace"`，永不因解码失败中断加载 |
| 单个坏包 | 记 `load_failures`，不拖垮整库（`parse_skill` 不抛异常） |

## 9. 验证方式

```bash
# 1) 单元与接线守卫（72 + 10 条）
python -m pytest tests/test_skill_library.py tests/test_skill_library_panel.py -q

# 2) 控件挂载守卫（新面板已在 EXPECTED 清单里）
python -m pytest tests/test_panel_controls_mounted.py -q

# 3) 相关回归
python -m pytest tests/test_plugin_system.py tests/test_panel_framework.py \
    tests/test_panel_events.py tests/test_wiring_guards.py tests/test_mcp_system.py -q

# 4) 手工验收：面板 → 导入该技能目录 → 一键应用 → 预览注入
```

EXE 冒烟判据同步为 **20 面板 / 5 分组 / `load_failures=[]`**。

## 10. 已知边界

- 只认 `SKILL.md` 这一种入口（不支持 `skill.yaml` / `plugin.json` 形态的旧技能）；
- 规则分级是**启发式**：标题写明的一律照原文，其余按编号与措辞推断，
  `level_source` 会标出来；不同技能包的措辞差异可能导致 A/B 判定偏移；
- 不做增量索引：每次 `reload()` 重新解析（技能包是几十 KB 级文本，成本可忽略）；
- 匹配基于词面命中，不做语义向量 —— 换来的是"可解释"，代价是同义说法匹配不到。
