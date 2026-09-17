# 全项目一致性审计（2026-09-17）

> **审计范围**：配置项 ↔ 代码使用、依赖声明 ↔ 实际 import ↔ 已安装版本、
> 跨文件重复定义、以及"声明了却不生效"的功能。
> **方法**：AST 静态扫描 + 运行时版本核对 + 全仓 grep（含入口文件，不只 `app/`）。
> **前置**：旧实例已关闭、桌面两个 EXE 已删除、残留清理完成（见 §0）。

---

## 0. 前置：残留与冲突清理结果

| 项目 | 结果 |
|---|---|
| 旧实例进程 | ✅ 无（`tasklist`/`wmic` 双查） |
| 桌面 EXE | ✅ 已删除（用户操作） |
| 仓库内旧 EXE | ✅ 删除 3 个（`AI_NovelWriter.exe` 根目录 / `installer/dist/` 两个）——均为 v3.1.0 构建（sha `7b793b80…`） |
| `%TEMP%\_MEI*` 解包残留 | ✅ 清理 **32 个 = 1079.4 MB** |
| `installer/build` 构建缓存 | ✅ 清理 28 MB（14 个文件） |
| 文件锁 | ✅ **12365 个文件逐一以写模式试开，无一被占用** |
| 端口占用 | ✅ 8000/8001/8002/5000/7860/8080/8888/11434 **均无监听** |
| 版本一致性门禁 | ✅ `test_version_consistency.py` 16 条通过 |
| 仓库工作区 | ✅ 干净 |

> **为什么"删 EXE"是必要的**：`AI_NovelWriter.exe` 会出现在**仓库根目录**，
> 因为 `installer/novel_app.spec` 里的 `name='../AI_NovelWriter'` 在**不带 `--distpath`**
> 构建时会解析到仓库根。本地构建务必带 `--distpath "%TEMP%\anx_dist_x"`
> （见 `docs/HARDWARE_ACCELERATION_PLAN.md` 与项目内存的打包章节）。

---

## 1. 配置项 ↔ 代码使用

### 1.1 🔴 声明了却**完全无效**的键（已处理）

| 键 | 原状 | 处理 |
|---|---|---|
| `img_width` / `img_height` | `ImageGenerator.generate()` 的默认值**写死 1024**；设置页**也没有宽高输入框** ⇒ 键既不可编辑也不被读取 | ✅ **两端接通**：`generate()` 从配置取（`_dimension()` 防御性转换），设置页新增宽/高输入框并在保存时校验（正整数且 8 的倍数） |
| `theme` | 全仓**无主题选择控件**；`UIStyle.apply_theme` 里 `theme_use("clam")` 写死，只有一套主题 | ✅ **移除**（留着只会让"设置里改了没用"变成一次无声的失望） |
| `auto_save` | 章节保存**无条件执行**，没有任何分支读这个键 ⇒ 既不能开也不能关 | ✅ **移除** |

### 1.2 🔴 敏感字段**重复定义**（已修）

```
app/config.py:84          SENSITIVE_CONFIG_FIELDS = ("api_key", "img_api_key", "secret_key")
      ↑ 注释：「单一来源：SecureConfig 与本模块共用，避免两处定义漂移」
app/secure_config.py:38   _SENSITIVE_FIELDS = ("api_key", "img_api_key", "secret_key")
      ↑ 注释：「与 AppConfig 共用同一定义」
```
**两份注释都声称"共用同一定义"，但 `secure_config` 既没 import 它、也没有测试锁定两者相等**
——是实实在在的第二份字面量副本。后果是安全性的：任一处改动都会静默漂移，
变成"某个密钥该加密却以明文落盘"（或反之），**且不会报错**。
这是本项目第 5 次撞上「同一事实写两处必然漂移」。

✅ 已改为 `from .config import SENSITIVE_CONFIG_FIELDS` + 别名（不动调用点），
并加守卫：全仓除 `config.py` 外不得再出现该清单的**字面量**。

### 1.3 🟠 声明为敏感但**从未被读取**的字段

| 字段 | 状况 |
|---|---|
| `img_api_key` | 在敏感清单里、`secure_config` 也给它兜了默认值，但 `app/` **零读取** ⇒ 需要密钥的图片服务商无法鉴权 |
| `secret_key` | 同上，零读取 ⇒ 完全未被使用的遗留字段 |

> 二者不构成安全漏洞（不会被误存），但属"注册即遗忘"：
> 清单纯粹是历史遗留，会让人误以为"这两个字段是活的"。

---

## 2. 依赖：声明 ↔ 安装 ↔ 实际 import

### 2.1 🔴 PDF 导出依赖缺失（已修）

`app/format_converter.py:333` 的 `_to_pdf` 用 `from fpdf import FPDF`（**fpdf2** 包），
**既没在 `pyproject.toml` 声明、环境里也没安装**。它的降级分支是
`except ImportError: return self._to_txt(...)` ⇒ **用户选"导出 PDF"会得到一个 .txt，
而且不报错**。这正是本仓记过的"静默丢功能"。

✅ 已在 `pyproject.toml` 声明 `fpdf2>=2.7.0` 并安装（2.8.8）。
⚠️ 注意包名 `fpdf2` 与 import 名 `fpdf` **不同名**，写错就白装。

### 2.2 声明了但 `app/` 零 import（冗余声明）

| 包 | 说明 |
|---|---|
| `markdown` | 声明了，`app/` 无 `import markdown`（`_to_markdown` 是自己拼 md 文本） |
| `beautifulsoup4` | 声明了，`app/` 无 `import bs4`；被打包是被 lxml 的可选 `html.soupparser` 带进来的 |

**未处理**：删除声明会改变依赖集，属产品决策。当前影响仅为 EXE 体积。

### 2.3 `app/` import 了但未声明

| 符号 | 判定 |
|---|---|
| `fpdf` | 🔴 **真缺口**，已修（见 2.1） |
| `PyPDF2` | ✅ 误报：`reading_manager.py:31-36` 是 `pypdf` → `PyPDF2` → `None` 的三级降级，且 `pypdf` 已声明 |
| `novel_app` | ✅ 误报：是本仓根目录的 `novel_app.py`（第一方模块） |
| `PIL` | ✅ 误报：`Pillow` 已声明（大小写归一化所致） |

### 2.4 跨文件版本约束

| 包 | 桌面端 `pyproject.toml` | 后端两个 `requirements.txt` |
|---|---|---|
| `httpx` | `>=0.24`（实装 0.28.1） | `==0.25.2` |
| `loguru` | `>=0.7.0`（实装 0.7.3） | `==0.7.2` |

两者是**独立部署**（后端有自己的镜像），不构成硬冲突：`0.25.2` 满足 `>=0.24`。
真正的隐患是**桌面端约束过宽**：`httpx>=0.24` 跨了 0.25→0.28 的破坏性变更
（`proxies`→`proxy` 等）。当前 0.28.1 下测试全绿，但干净环境重装若拉到更晚的
版本可能出问题。**建议**：桌面端把 `httpx` 收紧到 `>=0.24,<0.29`。

---

## 3. 跨文件重复定义扫描

扫描全部模块级 / 类级常量（含**元组与列表**、含**下划线开头的私有名**），
按"值 + 名字"分组找跨文件重复。结果：

| 值 | 出现处 | 判定 |
|---|---|---|
| `('api_key','img_api_key','secret_key')` | `config.py:84` / `secure_config.py:38` | 🔴 **真重复**，已修（§1.2） |
| `()` | `async_runner._ISSUED` / `registry.LOAD_FAILURES` | ✅ 巧合同为空容器 |
| `1000000` | `parsing._MAX_ABS_EXP` / `pricing.UNIT_TOKENS` | ✅ 不同概念 |
| `600` | `novel_agent._SUMMARY_MAX_CHARS` / `base.DEFAULT_TIMEOUT` | ✅ 不同概念 |

> ❗ **扫描器本身踩了两次坑**（留档，避免下次重犯）：
> 1. **只收 `ast.Constant`** ⇒ 元组型常量全被漏掉，而真重复恰好是元组 ⇒ 报"无重复"（**假阴性**）。
>    必须同时处理 `ast.Tuple/List/Set/frozenset`。
> 2. **正则写成 `^[A-Z]`** ⇒ 漏掉下划线开头的私有常量 `_SENSITIVE_FIELDS`
>    —— 真重复的其中一半就在那里。
> 3. 修正后仍需**自检**：打印"共收集到多少常量"（137 个），确认扫描非空转。

---

## 4. 余额查询：默认走 DeepSeek 官方接口

### 4.1 现状核查（结论：端点本身是对的）

`BALANCE_PROBES["deepseek"]` 早已内置官方端点，`source_url` 正是
`https://api-docs.deepseek.com/zh-cn/api/get-user-balance`。
**但发现一个真实缺陷**：

🔴 **`api_base` 带 `/v1` 会让余额地址变成 404。**
探针拼装规则是 `url = path if path.startswith("http") else base + path`，
而 `base` 会取用户配置的 `api_base`。用户把地址填成
`https://api.deepseek.com/v1`（很常见）时，拼出
`https://api.deepseek.com/v1/user/balance` —— 而官方余额接口**不在 `/v1` 之下**。

### 4.2 已实施的改动

| 改动 | 说明 |
|---|---|
| 新增 `DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"` | **绝对 URL，单一来源**。既修掉上面的 404，也让"官方接口是哪个"只有一处定义 |
| probe 的 `path` 改用该常量 | 绝对地址 ⇒ 直接生效，不受 `api_base` 影响 |
| 新增 `BALANCE_FALLBACK_PROVIDER = "deepseek"` + `has_builtin_probe()` | 回退机制 |
| `AIClient.query_balance` 增加回退 | 当前服务商**无内置探针**且用户**未自定义地址**时，改用 DeepSeek 官方接口（并用 DeepSeek 的 base_url，不沿用当前服务商的） |
| `BalanceResult` 新增 `note` 字段，并在 `format_total()` 里展示 | **必须讲清"这是谁的余额"**：GLM 用户看到一串金额会以为是自己的 GLM 余额 |

⚠️ **两处诚实边界**（已写进代码注释与 UI 文案）：
1. 回退查的是 **DeepSeek 的账户余额**，不是当前服务商的；
2. 凭据仍是当前 Profile 的 API Key。密钥在本仓是**按 Profile 存**的
   （不是按服务商），所以无法判断"有没有 DeepSeek Key"——若不是 DeepSeek 的 Key，
   接口会返回 401，note 里已提前说明需要 DeepSeek Key。

### 4.3 守卫

`tests/test_config_consistency.py` 钉住：
- 常量等于官方 URL；probe 使用它；
- **`api_base="…/v1"` 时解析出的 URL 仍是官方地址**（针对 404 的回归）；
- `glm`/`ollama` 等无探针服务商会回退；`deepseek` 自己查询**不**回退；
- 用户自定义 `balance_url` **优先于**回退；
- 回退结果的 `note` 会出现在 `format_total()` 里。

---

## 5. 🔴 未修的重大发现：文生图能力**不可达**

**`ImageGenerator.generate()` 全仓零调用。**

| 证据 | 位置 |
|---|---|
| 实例被创建 | `lifecycle_ui.py:1822` `self.image_gen = ImageGenerator(self.config)` |
| 唯一使用 | `shell_ui.py:1041` —— 只为状态栏拼字符串：`" + 文生图" if self.image_gen.is_configured()` |
| `generate(` 调用 | **无** |

后果：
1. **"文生图"这个功能从界面无法触发** —— 只有"生成图片提示词"（`editor_ui`），
   提示词存到 `scene_prompts/`，但没有把它变成图片的入口；
2. **状态栏会显示「+ 文生图」**，这是**虚假承诺**：它只反映"后端配置看起来可用"，
   而实际没有任何代码路径会用这个后端；
3. `img_provider` / `img_api_base` / `img_model` / `img_width` / `img_height` /
   `img_api_key` 这一整组配置，全部喂给一个没人调用的对象。

**未处理原因**：补一个图片生成入口属于**新增功能**，不在"审计 + 一致性修复"范围内，
需要单独确认产品意图（是做"章节配图"按钮，还是在名场面面板里给每个提示词配一个"生成"按钮）。

**已登记**：`docs/BACKLOG_REGISTER.md §5.7` 的 **D10**。

---

## 6. 结论与后续建议

### 已修（本轮）

| # | 问题 | 位置 |
|---|---|---|
| 1 | 敏感字段清单重复定义（安全类，静默漂移） | `config.py` / `secure_config.py` |
| 2 | `fpdf2` 未声明 ⇒ PDF 导出静默变 TXT | `pyproject.toml` |
| 3 | `img_width`/`img_height` 两端都没接通 | `image_generator.py` / `lifecycle_ui.py` |
| 4 | `theme` / `auto_save` 声明但无功能 | `config.py`（移除） |
| 5 | DeepSeek 余额地址在 `api_base` 带 `/v1` 时 404 | `balance.py` |
| 6 | 余额查询未回退到 DeepSeek 官方接口 | `balance.py` / `ai_client.py` |
| 7 | 回退结果不说明"这是谁的余额"（会误导） | `BalanceResult.note` |

### 建议后续处理（按优先级）

| 优先级 | 事项 | 说明 |
|---|---|---|
| **P1** | **决定文生图去留**（§5） | 要么补入口让它可达，要么移除该配置组与状态栏文案。现状是"配置看起来能用、实际无处触发"，最容易误导用户 |
| **P2** | 收紧桌面端 `httpx` 约束 | `>=0.24` 跨破坏性变更；建议 `>=0.24,<0.29` |
| **P2** | 处理冗余声明 `markdown` / `beautifulsoup4` | 删除可减 EXE 体积；属产品决策 |
| **P3** | 清理 `img_api_key` / `secret_key` | 二者零读取；若确认不用，从敏感清单移除；若要用，需补读取路径 |
| **P3** | 本地构建固定加 `--distpath` | 否则 EXE 会落到仓库根目录（§0 已说明成因） |

### 一句话总结

**依赖与余额接口两处是"真缺陷已修"**（PDF 静默降级、余额 404 + 未回退）；
**配置层是"声明与实现脱节"**（4 个键无效、1 处安全类重复定义）；
**最大的遗留是文生图整体不可达** —— 它不是配置问题，而是功能缺口，
需要产品决策后单独实施。
