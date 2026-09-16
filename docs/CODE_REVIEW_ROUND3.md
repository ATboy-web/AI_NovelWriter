# 代码复查报告（第三轮）：安全漏洞 · 逻辑缺陷 · 边界问题

- 日期：2026-09-16
- 复查对象：`ai-novel-writer` 桌面端 `app/`（21,855 行 / 50 文件）、`backend/`、`installer/`、部署编排
- 方法：逐段阅读实际代码 + 全仓模式扫描 + **可执行核验**（可疑点一律写脚本实跑，避免误报）
- 复查基线：HEAD `2bc4e68`
- 说明：本报告只做**识别与定位**，未修改任何代码；**修复落实与验证结果见 §7**

---

## 0. 结论概览

| 严重度 | 数量 | 代表问题 |
|---|---|---|
| 🔴 严重 | 4 | 角色库可被清空（2 条路径）、Redis/Postgres/API 端口全网暴露、日志泄露凭据 |
| 🟠 高 | 6 | `.bak` 被损坏内容覆盖、生产校验形同虚设、鉴权开启即不可用、写入非原子 |
| 🟡 中 | 9 | 字符串感知修复实为「半感知」、Windows 设备名未中和、子进程管道不排空 |
| 🔵 低 | 8 | 死常量、死装饰器、静默 no-op、性能退化 |

**核验中被推翻的 2 个怀疑**：见 §4（`ctypes` 缓冲区生命周期、`rename_character` 大小写改名致文件丢失）。
两者经实跑证明**不是缺陷**，特此记录以免后续被误改。

---

## 1. 🔴 严重：角色数据可被清空（这正是用户约束所保护的资产）

上一轮已修复 `novel_agent.generate_characters` 的整体覆盖，但**同类路径仍存在 2 条**，且都绕过了新加的守卫。

### V1 空集守卫只在「新集合为空」时生效，防不住「既有集合被读成空」

- **位置**：`app/memory_manager.py:704-737`（`save_characters`）+ `app/memory_manager.py:754-778`（`get_characters`）
- **成因**：守卫条件是 `if not characters and not allow_empty`（第 718 行），只检查**入参**是否为空。但真正危险的方向相反——**入参非空、却被建在一个空的底座上**：

  ```
  get_characters()  # 主文件损坏 → 返回 {}   （第 762-770 行，不抛错）
      ↓
  在上面 +2 个新角色 → 非空字典
      ↓
  save_characters(非空) → 守卫被跳过 → 整体覆盖
  ```
- **旁证**：`__init__.py:130` 的注释声称「读侧降级为空，**写侧据此拒绝覆盖**」，`get_characters` 也确实置了 `self._characters_corrupt = True`（第 765 行）。但全仓 grep 显示 **`_characters_corrupt` 只被写、从未被读**（仅测试断言它）。**注释描述的防护并未实现**。
- **影响**：磁盘上 286 个角色 → 只剩本次新增的几个。且此时 `atomic_write_json(..., backup=True)` 会把**损坏的主文件复制成 `.bak`**，把最后一份可用备份也毁掉（见 V2），**不可恢复**。

### V2 `backup=True` 用「当前主文件」轮转 `.bak`，会把好备份覆盖成坏内容

- **位置**：`app/storage.py:111-128`（`atomic_write_json`）→ `app/storage.py:101-108`（`backup_file`）
- **成因**：`backup_file` 无条件 `shutil.copy2(path, path+'.bak')`（第 107 行），不校验源文件是否可解析。调用方传 `backup=True` 时，若主文件此刻**已损坏**，则 `.bak` 被损坏内容覆盖——而 `.bak` 的存在意义正是「主文件坏了还能回退」。
- **影响**：数据恢复链断路。`read_json_with_backup` 的四态设计（`storage.py:137-168`）在第一次坏写之后就永久退化为 `STATUS_CORRUPT`。
- **附带**：`shutil.copy2` 非原子，复制中途崩溃 → `.bak` 半截。

### V3 `_auto_detect_characters` 是 V1 的现成触发点，且未走锁

- **位置**：`app/character_ui.py:139`（`existing = self.memory.get_characters()`）→ `:174`（`self.memory.save_characters(characters)`）
- **成因**：
  1. 第 139 行读到 `{}`（损坏/权限错误/竞态）→ 第 161 行 `characters = existing.copy() if existing else {}` = `{}` → 第 174 行直接 `save_characters` 落盘。
  2. 这条路径**调用的是 `save_characters` 而不是 `mutate_characters`**，因此既无锁、也无读-改-写保护。上一轮的 R4 修复只覆盖了 `novel_agent` 与传记两条路径。
- **影响**：章节生成时自动建角色（默认开启）即可清空角色库；与传记后台线程并发时还会丢更新。

### V4 `novel_agent` 的并集合并同样退化为整体覆盖

- **位置**：`app/novel_agent.py:1274-1276`
- **成因**：`before = len(self.memory.get_characters())` 在锁外且不感知损坏。主文件损坏时 `get_characters()` 返回 `{}` → `_merge({})` 的底座是空 → 合并结果只含本批次 → 非空 → 守卫放行 → 覆盖 + 毁 `.bak`。
- **影响**：上一轮「修好」的 R1 在损坏场景下**完全没有生效**；并且因为结果是「非空」，用户不会看到任何告警。

> **根因归纳**：整套防护假设「空 == 危险」，但真实事故形态是「**底座空、增量非空**」。正确做法是让 `save_characters` 读取并信任 `_characters_corrupt` 标记（该标记已存在），在标记为真时拒绝写入，除非显式 `force=True`。

---

## 2. 🔴/🟠 严重：凭据泄露与网络暴露

### S1 请求日志把 `?token=` / `?api_key=` 原文写进日志

- **位置**：`backend/shared/middleware/logging.py:112`（`"query": str(request.query_params)`）
- **成因**：`AuthMiddleware._extract_token` **接受查询参数里的 token**（`backend/shared/middleware/auth.py:238-241`），`_extract_api_key` 同样接受 `?api_key=`（`:257-260`）。而日志中间件把 `query_params` **原样**写入 `request_log` 并 `logger.info(..., **request_log)`（`:126`）。
- **同一文件内部自相矛盾**：JSON body 有 `_sanitize_body` 按 `SENSITIVE_FIELDS`（含 `token`/`api_key`，`:35-41`）打码，**查询串完全没有对应处理**。
- **影响**：任何用 `?token=` 认证的请求，其有效 JWT 会明文落到服务日志（并随日志采集进 Loki）。日志通常比凭据本体留存更久、可见范围更广。

### S2 日志打码不递归列表，嵌套凭据漏出

- **位置**：`backend/shared/middleware/logging.py:58-68`
- **成因**：`_sanitize_body` 只对 `dict` 递归（第 64-65 行），其余一律原样保留（第 67 行）。`list` 属于「其余」，因此 `{"items": [{"api_key": "sk-..."}]}` 中的密钥**不会被替换为 `***`**。
- **影响**：批量类接口（batch_ops）的日志会泄出凭据。

### S3 `docker-compose.yml` 把数据库/Redis/API/监控全部发布到 0.0.0.0，且默认关闭鉴权

- **位置**：`docker-compose.yml` 第 18（`5432:5432`）、41（`6379:6379`）、66（`8001:8001`）、98（`8002:8002`）、133/154/155、180/199/214/230/249/274/290/315（监控栈）
- **成因**：
  - Compose 的 `"5432:5432"` 等价于 `0.0.0.0:5432`（绑定回环需显式写 `127.0.0.1:5432:5432`）。发布端口会**绕过 Docker 网络隔离**。
  - 第 104 行 `ENABLE_AUTH=${ENABLE_AUTH:-false}` → **默认关闭鉴权**，而 `8001/8002` 又直接发布，等于把 AI 生成接口裸奔在公网。
  - 第 39 行 `redis-server ... --requirepass ${REDIS_PASSWORD:-}` → **密码默认空**，同时 6379 已发布。未授权 Redis 是经典 RCE 链（`CONFIG SET dir` + `SAVE` 写文件）。
  - 监控栈（Prometheus 9090 / Alertmanager 9093 / Grafana 3001 / cAdvisor 8080 / Loki 3100 / 各类 exporter）均无前置鉴权，Grafana 首次登录为默认口令。
- **影响**：在有公网 IP 的机器上执行一次 `docker compose up`，即暴露一个**无鉴权的文本生成 API + 无口令 Redis + 可读内部指标的监控面**。这是本报告最高危项。
- **旁证（相对良性）**：`docker-compose.prod.yml` 只发布 80/443，且通过 `${JWT_SECRET:?...}` 强制提供密钥；`Settings.ENABLE_AUTH` 默认 `True`（`backend/*/app/core/config.py:77` / `:63`）→ 生产编排下鉴权是开的。风险集中在开发用 compose 文件。

### S4 生产环境安全校验只打日志、不阻止启动

- **位置**：`backend/ai-service/app/core/config.py:114-142`（`validate_settings` + 模块级调用）
- **成因**：函数把问题收进 `errors` 列表后返回；调用处只是

  ```python
  validation_errors = validate_settings()
  if validation_errors:
      for error in validation_errors:
          logger.error(f"配置错误: {error}")
  ```

  **没有 `raise`、没有 `sys.exit`**。
- **影响**：所有生产校验（`CORS_ORIGINS` 不得为 `["*"]`、`DATABASE_URL` 必填、`SECRET_KEY` 必填）全部是「建议」性质。服务会带着 `allow_origins=["*"] + allow_credentials=True`（`backend/*/app/main.py` 的 CORS 配置）正常启动。同类问题在 `novel-service/app/core/config.py:113-114` 重复。

### S5 鉴权开启即不可用，反向逼迫运维关闭鉴权

- **位置**：`backend/shared/middleware/auth.py:117-169`（`create_access_token` / `create_refresh_token`）
- **成因**：全仓 grep 确认这两个方法**只在 `backend/tests/` 被调用，生产代码零调用点**，也没有任何 `/login`、`/token` 路由。而 `ENABLE_AUTH` 默认 `True`；开发环境无 `SECRET_KEY` 时用 `secrets.token_urlsafe(32)` 生成**每进程随机**密钥（`backend/*/app/core/config.py:95`）。
- **影响**：
  1. 默认配置下所有非公开端点返回 401，**且没有任何官方途径拿到 token** —— 唯一的变通是配 `API_KEYS` 或**把 `ENABLE_AUTH` 改成 false**。安全默认值把用户推向不安全配置。
  2. 随机密钥 + 多 worker：A worker 签发的 token 在 B worker 验签失败 → 间歇性 401，且重启即全部失效。

### S6 百度网盘 access_token 走 URL 查询串，异常信息会把它打到 stdout

- **位置**：`app/cloud_storage.py:151/166/203/260/271`（`params={"access_token": ...}`）+ `:217`（`print(f"百度网盘上传失败: {e}")`）
- **成因**：`httpx` 的 `HTTPStatusError.__str__` 会带上完整请求 URL。URL 里含 `access_token`，因此一次失败的上传就会把长期令牌写进 stdout。
- **放大因素**：`installer/launcher.py` 用 `stdout=subprocess.PIPE` 启动服务却**从不读取该管道**（见 L8），输出会滞留在管道缓冲。
- **旁证**：同文件 `:657` 定义了 `_SENSITIVE_FIELDS = {"password","access_token","refresh_token","cookie","token"}` 用于展示脱敏，但上述 `print` 走的是异常文本，**绕过了脱敏**。

### S7 AI API Key 可被发往任意明文端点

- **位置**：`app/ai_client.py:453-480`（`_init_client`）
- **成因**：`api_base` 完全来自配置，代码不校验 scheme、不做域名白名单。非 Claude 分支一旦有 key 就构造 `Authorization: Bearer <key>`。若 `api_base` 被写成 `http://...`（配置手误、被篡改的共享配置、第三方预设），**密钥以明文 HTTP 发出**。
- **同类**：`app/cloud_storage.py:64-73` 的 WebDAV 以 `auth=(user, password)` 走 `base_url`，同样不限制 scheme。
- 交叉验证：全仓无 `verify=False`，TLS 本身未被关闭，问题只在 scheme/主机选择。

### S8 `X-User-Id` 响应头泄露 API Key 前 8 位

- **位置**：`backend/shared/middleware/auth.py:96`（`"user_id": f"apikey-{key[:8]}"`）→ `:327`（`response.headers["X-User-Id"] = user_id`）
- **成因**：把密钥前缀当成用户标识，并回写到响应头。
- **影响**：密钥前 8 位（如 `sk-abc12`）进入浏览器/代理/日志可见范围，降低暴力破解空间；对短密钥可能是实质泄露。

---

## 3. 🟠/🟡 数据完整性与逻辑缺陷（桌面端）

### L1 `_fix_common_json_defects` 是「字符串不感知」的正则，会改写正文

- **位置**：`app/parsing.py:121-130`（`re.sub(r",\s*([\]}])", r"\1", text)`，第 129 行）
- **实测**（`_verify_issues.py`）：
  ```
  raw   : {"林风": {"personality": "他常说,}不要放弃", "age": 20}}
  fixed : {"林风": {"personality": "他常说}不要放弃", "age": 20}}
  ```
  **字符串里的 `,` 被删掉**，且解析成功 → 静默改写角色性格文本。
- **成因**：正则跨越了字符串字面量边界，没有复用 `clean_ai_json_text` 的状态机。
- **影响**：`parse_characters_payload` 在 `json.loads` **之前**调用它（`app/parsing.py:153`），因此凡是含 `,}` / `,]` 的角色描述都会被静默篡改。**这正是上一轮 S2 声称已消灭的缺陷类别**，只是换了位置。

### L2 名为「保真修复」的函数，一半正则并不保真

- **位置**：`app/parsing.py:187-197`（`_repair_json_preserving_strings`）
- **成因**：第 189 行确实走了字符串感知的 `clean_ai_json_text`，但紧接着第 194 行 `re.sub(r',\s*([\]}])', ...)` 与第 196 行 `re.sub(r'"\s*\n(\s*")', ...)` **又是跨字符串边界的全量正则**。
- **影响**：函数名与 docstring 承诺「只动字符串之外」，实际不成立；`parse_json_response` 的策略 3 优先选它（第 246 行），使保真候选同样可能改坏文案。

### L3 `clean_ai_json_text` 的引号状态机不对称

- **位置**：`app/parsing.py:76-92`
- **实测**：`{"name": "张三", "title": “剑客”}` → `{"name": "张三", "title": "剑客”}` → `JSONDecodeError`
- **成因**：字符串**外**遇到 `“` 会 `in_string = True` 并输出 `"`（第 80-82 行）；但进入字符串后，**只有 ASCII `"` 能结束**（第 72-73 行）。于是配对的 `”` 被当作字符串内容原样输出，且状态一直停在「字符串中」，后续所有 `,`/`:` 也都不再转换 → 该候选必然解析失败。
- **缓解**：`parse_characters_payload` 会退到 `repair_ai_json_text`，实测数据能正确救回，故**当前不致命**。
- **影响**：保真候选在「字符串以弯引号开头」时**100% 失效**，白跑一轮；且这种失效是静默的。

### L4 `safe_filename` 不中和 Windows 保留设备名

- **位置**：`app/storage.py:46-55`
- **实测**：`CON`/`NUL`/`PRN`/`AUX`/`COM1`/`LPT1` 全部**原样返回**。
- **成因**：只过滤 `[<>:"/\\|?*]` 并把 `..` 替换为 `_`，没有保留名表。
- **影响**：Windows 上 `CON.json`、`NUL.json` 等仍指向**设备**而非文件（保留名在第一个点之前生效）。名为「CON」的角色会导致写入异常或写到控制台；`os.replace` 行为不可预期。

### L5 `safe_filename` 无长度上限，空名回落会撞名

- **位置**：`app/storage.py:46-55`
- **实测**：300 个字符的名字 → 300 字符文件名（NTFS 单文件名上限 255）。`''` / `'   '` → 统一变成 `'unnamed'`。
- **影响**：
  - 超长名 → `OSError`。`_write_char_files` 逐条 catch 并 `continue`（`app/character_ui.py:87-91`），但 `save_character` **不 catch**（`app/character_system.py:601-607`），异常会向上冒泡中断流程。
  - 多个全非法字符的名字共用 `unnamed.json` → 互相覆盖。

### L6 `character_system._load_all` 仍在无条件 `unlink()`，且异常被静默吞掉

- **位置**：`app/character_system.py:432-443`
- **成因**：
  ```
  if name not in self.characters:      # 已存在则跳过导入
      ...
      self.save_character(name)
  old_file.unlink()                    # 与上面的 if 同级 → 无论是否导入都删
  ```
  若 `name` 已在内存（第 438 行条件为假），旧文件**未被读取导入就已删除**。第 442 行仍是 `except Exception: pass`，与本文件其它处新加的 `logger.warning` 风格不一致。
- **影响**：`load()` 每次都无提示地删除 `character_profile.json`；对该文件与内存不一致的用户，等于静默丢弃最后一次迁移机会。这是**用户「不可删除」约束之外仅存的一处 `unlink`**。

### L7 凭据配置读取失败 → 默认值 → 下次保存覆盖，密钥/设置永久丢失

- **位置**：`app/secure_config.py:158-176`（`_load`）+ `:201-218`（`save`）
- **成因**：`json.load` 失败 → `except Exception` → 返回 `_default_config()`（第 174-176 行）。此后任何一次 `set()` 都会 `save()` 整个 config（第 226-227 行），**把用户配置连同已加密的 api_key 一起写成默认值**。同理 `_decrypt` 失败返回 `""`（第 156 行），该空值会被 `save` 再加密写回 → 密钥被静默抹掉。
- **附带**：`save()` 用 `open(...,'w')` + `json.dump`，**非原子**（第 211-212 行）——正是 `app/storage.py` 要解决的那类缺陷，本模块未迁移过去。

### L8 启动器创建子进程管道却从不排空

- **位置**：`installer/launcher.py:114-121`、`:154-161`、`:218-223`
- **成因**：`stdout=subprocess.PIPE, stderr=subprocess.PIPE`，但全文件搜索 `communicate` / `.read(` **零命中**。
- **影响**：管道缓冲（Windows 约 4–8 KB）写满后，子进程 `write()` 阻塞 → **服务假死**。FastAPI/uvicorn 的启动与访问日志很容易超过该阈值，属高概率触发。

### L9 传记生成无输入校验与返回校验

- **位置**：`app/character_ui.py:250`（`int(word_var.get())`）、`:292`（`max_tokens=word_count * 2`）、`:305-312`（`_attach_bio`）
- **成因与影响**：
  - `word_var` 绑定的是**可编辑** Combobox（`:232-235`）。输入非数字 → `int()` 抛 `ValueError`，发生在 `word_dialog.destroy()` **之前**（`:251`），异常逃逸到 Tk 回调 → 只打栈、无用户提示、对话框不关。
  - `word_count` 可选到 200000 → `max_tokens=400000`，远超主流 API 上限（通常 8K–16K）→ 必然 400/截断，用户以为在生成 20 万字传记。
  - `_attach_bio` 里 `characters.get(char_name)` 为 `None` 时直接跳过（`:307-310`），**无任何提示**；界面仍显示「生成完成」。

### L10 旧版 `raw` 字段与「名为 raw 的角色」互相干扰

- **位置**：`app/parsing.py:30`、`:166-183`
- **成因**：`_RESERVED_CHARACTER_KEYS = {"raw"}` 让 `extract_characters_payload` 把顶层 `raw` 当作旧版 AI 原文（第 176-180 行）。若现行格式里真有一个角色叫「raw」（或其值为 dict），它会被当成载体去解析；同时 `parse_json_response` 策略 5 也会跳过 `raw`（第 269 行）。
- **影响**：名为 `raw` 的角色被静默丢弃；`parse_characters_payload` 还会顺带丢掉所有值非 dict 的条目（第 159-160 行）。

---

## 4. ✅ 经实跑核验、**不是**缺陷的项（避免后续误改）

| 怀疑 | 核验方式 | 结论 |
|---|---|---|
| `secure_config._to_blob` 局部缓冲区可能被 GC，导致 DPAPI 读已释放内存（use-after-free） | 复刻该函数，返回 `_DATA_BLOB` 后 `gc.collect()`，再用裸指针读回；并连做 3 次 DPAPI 加解密往返 | **不成立**。`blob._objects` 非空 —— ctypes 通过指针持有缓冲区引用。数据完好，往返正确（密文 262 B） |
| `rename_character("Alice","alice")` 在 Windows 上会把刚写好的文件删掉 | 实跑 `CharacterSystem.rename_character`，检查目录内容 | **不成立**。`Path` 在 Windows 上是 `PureWindowsPath`，`__eq__` **大小写不敏感** → `old_file != new_file` 为假 → 正确地跳过了 `unlink`。目录仍为 `['alice.json']`，无丢失 |
| DPAPI 临时密钥是硬编码字符串 | 读 `config.py:95` | **不成立**，用的是 `secrets.token_urlsafe(32)`（问题在「每进程随机」，见 S5） |
| 后端存在三份重复的 `auth.py` | 逐文件 sha256 | **不成立**。`backend/*/app/middleware/auth.py` 均为 378 B 的薄转发（`from shared.middleware.auth import *`），实体只有一份 |

---

## 5. 🟡/🔵 其余问题（简表）

| 编号 | 位置 | 问题 | 影响 |
|---|---|---|---|
| M1 | `app/ai_client.py:74-91` | `retry_with_backoff` 重试**所有**异常（含 401/400），且**生产零调用**（仅 8 个单测引用，grep 确认） | 死代码；其「无差别重试」逻辑若被启用会放大配额与延迟。上轮「因为有测试所以保留」的判据不成立 |
| M2 | `app/parsing.py:32-37` | `_CHARACTER_FIELD_NAMES` 定义后全仓零引用 | 死常量，误导读者以为字段名已被过滤 |
| M3 | `app/parsing.py:264-285` | 策略 5 对每个匹配都向后扫全串，最坏 O(n²) | 大响应（200 KB）可能卡住 UI 线程 |
| M4 | `app/parsing.py:256-262` | 策略 4 给任意截断串追加 `'"}}'` 等后缀再 `json.loads` | 可能「解析成功」但得到语义错误的对象，把失败伪装成成功 |
| M5 | `app/memory_manager.py:175-176`、`:186-187`、`:195-198` 等 | 倒排索引 / 活跃度 / 卷摘要仍用非原子 `write_text` | 写坏后 `_load_inverted_index` 吞掉异常返回 `{}` → 下次落盘把空索引写回 → **检索索引永久清零**。与 V1 同构的「读空→写空」 |
| M6 | `app/memory_manager.py:88` | 类级 `_KW_CACHE` 跨线程无锁读写 | 并发下可能读到半构造缓存/竞态计数 |
| M7 | `app/secure_config.py:242-247` | `get_secure_config()` 单例非线程安全；`set()` 无锁 | 首次并发构造可能各生成一把 Fernet key，其中一个永远解不开已加密数据 |
| M8 | `app/ai_client.py:548` | 诊断日志写 `content_preview: result[:200]` | 与第 520 行「不记录创作内容」的注释直接矛盾，正文本会落盘 |
| M9 | `app/ai_client.py:453-480` | `_init_client` 只在 `__init__` 调用 | 运行中改 API Key 后 `self.client` 头部仍是旧 key，需重启才生效 |
| M10 | `app/cloud_storage.py:81/91/104/217/338/451/571/761/787/815` | 一律 `print(f"...{e}")`，绕过 `_SENSITIVE_FIELDS` 脱敏 | 见 S6 |
| M11 | `docker-compose.yml:47` | 健康检查 `redis-cli -a "${REDIS_PASSWORD}"` | 口令出现在容器进程列表，`docker inspect`/`ps` 可直接读到 |
| M12 | `app/number→int` 边界 | `parse_exp_json` 的 `int(...)` 对超大数值无上限（如 `9`×100 位） | 下游若用于计算可能溢出/异常；建议钳位 |

---

## 6. 建议修复顺序

**P0（数据/凭据，先止血）**
1. `save_characters` 读取 `_characters_corrupt`：标记为真时一律拒绝写入（除非 `force=True`）→ 一次性堵住 V1/V3/V4。
2. `_auto_detect_characters` 改走 `memory.mutate_characters`（与 `novel_agent`/传记一致）。
3. `atomic_write_json` 的 `backup` 改为「**仅当主文件可解析时**才轮转 `.bak`」；`backup_file` 改用原子写。
4. 日志中间件的 `query` 走脱敏（并按 key 名匹配 `token|api_key|...`）；`_sanitize_body` 递归 `list`。

**P1（部署面）**

5. `docker-compose.yml`：`ENABLE_AUTH` 默认改 `true`；`5432/6379/8001/8002` 与监控栈全部改绑 `127.0.0.1:`；Redis 强制 `--requirepass`（去掉 `:-` 默认空）。
6. `validate_settings()` 在生产环境 `raise`（或 `sys.exit`），让校验真正生效。
7. 补一个签发端点或明确声明「仅支持静态 API Key」，消除 S5 的「开启即不可用」。

**P2（正确性）**

8. `_fix_common_json_defects` / `_repair_json_preserving_strings` 内的正则改为复用字符串感知状态机（消除 L1/L2）。
9. `clean_ai_json_text` 让 `“` 能被配对的 `”` 关闭（消除 L3）。
10. `safe_filename` 增加：Windows 保留名表、长度截断（含哈希后缀）、尾点/尾空格剥离（消除 L4/L5）。
11. `secure_config.save` 迁到 `atomic_write_json`；`_load` 失败时**不得**返回默认值覆盖策略（改为只读降级 + 显式报错）（消除 L7）。
12. `launcher.py` 子进程改用 `DEVNULL` 或起线程排空管道（消除 L8）。
13. 传记生成：`word_count` 加 `try/except` + 上限钳位（如 ≤ 16000）；`chat()` 返回 `None` 时提前报错（消除 L9）。

**P3（清理）**

14. 删除 `retry_with_backoff`、`_CHARACTER_FIELD_NAMES`；`_load_all` 的 `unlink` 改为显式确认或保留文件（消除 M1/M2/L6）。
15. `memory_manager` 的索引/活跃度/摘要落盘统一到 `app/storage.py`（消除 M5）。

---

## 7. 修复落实与验证（收尾补写）

> §1–§6 保持「识别与定位」原貌以便对照；本节记录**已落地的修改**与**验证方式**。

### 7.1 逐项落实状态

| 编号 | 状态 | 修复位置 | 关键改动 |
|---|---|---|---|
| V1 | ✅ | `app/memory_manager.py` `save_characters` | 新增「降级读之后禁止盲写」闸门：`_characters_corrupt` 为真时**即使入参非空也拒绝**写入；`force=True` 才放行，且**放行也会先留档**损坏文件 |
| V2 | ✅ | `app/storage.py` | `backup_file(validate=True)` + `atomic_write_json` 默认带 `validate=True`：主文件不可解析时**跳过轮转**，保住既有 `.bak` |
| V3 | ✅ | `app/character_ui.py` `_auto_detect_characters` | 改走 `memory.mutate_characters`（锁内读-改-写），并捕获闸门异常提示「已阻止一次可能清空角色库的写入」 |
| V4 | ✅ | `app/novel_agent.py` `generate_characters` | 合并前校验底座可信，损坏即抛 `CharacterDataGuardError`。判据用 `is True` 而非真值判断 —— `self.memory` 允许是鸭子类型协作者（单测即 MagicMock），真值判断会把一切调用误判为损坏 |
| S1 | ✅ | `backend/shared/middleware/logging.py` | 新增 `_sanitize_query`，查询串中的敏感键按名打码 |
| S2 | ✅ | 同上 | `_sanitize_value` 递归处理 `dict` / `list` / `tuple` |
| S3 | ✅ | `docker-compose.yml` | 仅 `frontend`、`nginx` 绑 `0.0.0.0`；`postgres/redis/ai-service/novel-service` 与整个监控栈全部改绑 `127.0.0.1` |
| S4 | ✅ | `backend/ai-service/app/core/config.py` | `validate_settings` 在生产环境 `raise ValueError`（缺 `DATABASE_URL`、CORS 为 `*`） |
| S5 | ✅ | `backend/shared/middleware/auth.py` | 模块文档 + 503 文案明确「开箱仅支持静态 API Key，无签发端点」，消除「开启即不可用」的误导 |
| S6 | ✅ | `app/cloud_storage.py` | 新增 `_safe_error(...)`，对 URL 中的 token 与错误文本统一脱敏；10 处 `print(f"…{e}")` 全部替换 |
| S7 | ✅ | `app/ai_client.py`、`app/cloud_storage.py` | `AIClient._validate_api_base` 与 `WebDAVProvider` 的 `_require_secure_url` 拒绝向非本机地址发送明文 HTTP / 非 http(s) 协议 |
| S8 | ✅ | `backend/shared/middleware/auth.py` | `X-User-Id` 改为 `apikey-<sha256 前 12 位>`，不再泄露 Key 原文片段 |
| L1/L2 | ✅ | `app/parsing.py` | 结构修复只作用于**字符串外**片段（`_iter_segments` + `_repair_outside_strings`），不再改写正文 |
| L3 | ✅ | `app/parsing.py` `clean_ai_json_text` | 弯引号改为对称状态机：记录 opener，`“` 只能被配对的 `”` 关闭 |
| L4/L5 | ✅ | `app/storage.py` `safe_filename` | 中和 Windows 保留设备名；超长名截断并追加 sha1 前 8 位；剥离尾点/尾空格 |
| L6 | ✅ | `app/character_system.py` `_load_all` | 旧单文件一律 `rename` 为 `.migrated`（同名带时间戳去重）；失败改为显式告警，`unlink` 彻底移除 |
| L7 | ✅ | `app/secure_config.py` | 读盘失败时留档 + 置 `_load_failed`；解不开的密文记入 `_undecryptable` 并在下次 `save` 原样写回，不再被空值覆盖 |
| L8 | ✅ | `installer/launcher.py` | 子进程输出重定向到 `logs/<name>.log`，创建失败退回 `subprocess.DEVNULL`；句柄在 `stop_all_services` 统一关闭 |
| L9 | ✅ | `app/character_ui.py` `start_generate` / `run` | 字数先 `try/except` 解析 + 范围校验，**通过后才** `destroy()` 对话框；`max_tokens` 按 `MAX_BIO_TOKENS` 钳位；空返回抛 `RuntimeError`；传记未挂到角色时明确提示 |
| L10 | ✅ | `app/parsing.py` `extract_characters_payload` | `raw` 仅在**确为字符串**时按旧版载体处理，否则与顶层字典合并，避免与「名为 raw 的角色」冲突 |
| M1 | ✅ | `app/ai_client.py` | 删除 `retry_with_backoff`；新增 `_is_transient_error`（仅 `httpx.TransportError` 与 429/5xx 才重试） |
| M2 | ✅ | `app/parsing.py` | 删除死常量 `_CHARACTER_FIELD_NAMES` |
| M3 | ✅ | `app/parsing.py` | `_pair_braces` 改为 O(n) 配对，替代最坏 O(n²) 的反向扫描 |
| M4 | ✅ | `app/parsing.py` | 策略 4/5 增加 `_is_balanced` + 顶层类型校验，杜绝「补后缀强行解析成功」 |
| M5 | ✅ | `app/memory_manager.py` | 倒排索引/角色活跃度/卷摘要/设置/meta 落盘全部走 `atomic_write_json` / `atomic_write_text`（已无裸 `write_text`） |
| M6 | ✅ | `app/memory_manager.py` | 类级 `_KW_CACHE` 增配 `_KW_CACHE_LOCK`，读写全部加锁 |
| M7 | ✅ | `app/secure_config.py` | 单例改为双重检查锁；`get`/`set`/`save` 走实例级 `RLock` |
| M8 | ✅ | `app/ai_client.py` | 诊断日志移除 `content_preview`，正文不再落盘 |
| M9 | ✅ | `app/ai_client.py` | 新增 `refresh_if_needed()`（按配置指纹比对重建客户端），`chat()` 调用前先刷新 |
| M10 | ✅ | `app/cloud_storage.py` | 见 S6：10 处直接 `print` 全部改为脱敏输出 |
| M11 | ✅ | `docker-compose.yml` | 健康检查改用 `REDISCLI_AUTH` 环境变量，口令不再出现在 `argv`；`--requirepass` 去掉「不配即空口令」的默认值 |
| M12 | ✅ | `app/parsing.py` | 新增 `_safe_exp_int`，钳位 ±1,000,000，兼容超长数字串 |

### 7.2 验证方式

| 验证项 | 命令 / 方法 | 结果 |
|---|---|---|
| 全量测试 | `python -m pytest -q`（`testpaths = tests, backend/tests`） | **1391 passed / 0 failed** |
| 本轮专项回归 | `python -m pytest tests/test_review_round3_fixes.py` | **47 passed** |
| 静态检查 | `python -m ruff check app/ tests/ backend/ scripts/ installer/` | **All checks passed!** |
| 角色资产未受影响 | 对线上 `memory/characters.json` 计算摘要 | **286 个角色**，sha256 `fdd2d44d…2db056`，49,086 字节（原文误记为 49048，2026-09-16 复核更正）；未出现在 `git status` 变更列表中 |
| 改动范围 | `git diff --stat` | 仅 19 个源码/测试/配置/文档文件，**无任何数据文件** |

### 7.3 新增回归测试（`tests/test_review_round3_fixes.py`）

按缺陷编号组织，逐条锁定行为，共 47 条：

- **V1/V4**：降级读后写非空集合必须被拒且不触碰磁盘；拒绝时留档损坏文件；286 规模库在损坏下不丢失；`force=True` 可放行且**仍先留档**；同一秒内多次留档各自独立；`mutate_characters` 同样被闸门拦住；主文件坏但 `.bak` 可解析属正常降级、不误伤写路径。
- **V3**：`_auto_detect_characters` 必须走 `mutate_characters`，且把闸门异常暴露给用户。
- **L6**：旧单文件导入后必须存在 `.migrated` 归档；同名时不静默丢弃；迁移块内不得出现 `unlink`。
- **L7**：配置损坏留档并置标记；解不开的密文在 `save` 后被原样保留；原子写不留临时文件；单例并发只构造一次。
- **L8**：不得创建永不排空的 `PIPE`；输出必须重定向到日志（失败退回 `DEVNULL`）；停止时关闭句柄。
- **L9**：字数解析有守卫与提示；校验失败不关对话框；`max_tokens` 有钳位；空返回被拒；角色未挂上时明确提示。
- **M6**：缓存锁存在；并发抽取无异常且缓存有界。
- **M8/M9/S7**：远程明文 HTTP 被拒、非 http(s) 协议被拒、本机 HTTP 放行；改 Key 后客户端立即重建；`content_preview` 已消失。
- **S3/M11/S4**：仅边缘服务对外；内部服务均绑 `127.0.0.1`；Redis 口令必填且不进 `argv`；`ENABLE_AUTH` 默认 `true`；生产校验真正 `raise`。

> 源码扫描型断言统一经 `_strip_noise()` 处理：修复说明本身会以注释/文档字符串提到「旧的 `xxx` 写法」，不过滤会让断言被自己的说明文字推翻。

### 7.4 已知遗留（未在本轮处理）

- `backend/` 系列的「用户认证服务 / 支付服务 / 前端 React 重构」仍为规划状态，与本轮安全修复无关。
- `M5` 覆盖了 `memory_manager` 的落盘路径；`app/` 下若还有其它模块直接 `write_text` 写结构化数据，属后续统一项。
