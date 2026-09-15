# AI_NovelWriter 代码安全审计报告

**审计日期**：2026-09-07  
**审计范围**：`C:\Users\Administrator\WorkBuddy\2026-05-30-16-50-56\ai-novel-writer` 全部代码文件  
**审计方式**：静态代码分析（含关键发现交叉验证）

---

## 一、功能概述

### 1.1 项目定位
AI 自动写小说系统，产品级完整应用。采用「桌面客户端 + 后端微服务 + 移动端」三层架构。

### 1.2 主要功能模块

#### 桌面端（`app/` + 根目录）
| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 主程序 | `novel_app.py`（420KB） | tkinter GUI 主框架，整合所有功能 |
| AI 客户端 | `app/ai_client.py` | 多 Provider 调用（DeepSeek/OpenAI/Claude/Ollama/Kimi/GLM/Qwen/自定义），深度思考模式，模型降级链 |
| 小说智能体 | `app/novel_agent.py` | 5-Agent 协作（PlotDesigner→WorldBuilder→Writer→Reviewer→Editor），大纲/章节/人物生成 |
| 记忆管理 | `app/memory_manager.py` | 分层摘要、倒排索引、时间线、角色活跃度追踪、向量检索 |
| 写作技能 | `app/writing_skills.py` | 知识图谱、时间感知记忆、AI 痕迹检测（AntiSlop） |
| 场景检测 | `app/scene_detector.py` | 名场面识别、电影级提示词生成 |
| 阅读管理 | `app/reading_manager.py`/`reader_manager.py` | TXT/EPUB/PDF/DOCX 多格式阅读、书签、书库 |
| 角色系统 | `app/character_manager.py`/`character_system.py` | 角色 CRUD、成长追踪 |
| 配置管理 | `app/config.py`/`secure_config.py` | 明文+Fernet 加密配置 |
| 插件系统 | `plugin_system.py` | 支持 URL/ZIP/本地目录安装插件 |
| 云存储 | `cloud_storage.py` | WebDAV、百度网盘、夸克、迅雷、阿里云盘 |
| 协作 | `collaboration.py` | 多人协作、章节分配、锁 |
| 文生图 | `ai_drawing.py`/`image_generator.py` | ComfyUI/SD WebUI 集成 |

#### 后端微服务（`backend/`）
| 服务 | 目录 | 端口 | 职责 |
|------|------|------|------|
| AI 服务 | `ai-service/` | 8001 | LLM 推理（本地/云端），15 个端点 |
| 小说服务 | `novel-service/` | 8002 | 小说生成业务逻辑，36 个端点 |
| 中间件 | `*/app/middleware/` | - | 限流、认证、日志 |

> 注：`auth-service/`、`payment-service/` 为**规划占位目录**（0 个文件，未被容器编排与代码引用；
> 该两个空目录已于 2026-09-16 移除），
> 认证与支付逻辑均未实现。立项定论见
> [AUTH_PAYMENT_SERVICES_EVALUATION.md](AUTH_PAYMENT_SERVICES_EVALUATION.md)（结论：暂不立项）。

#### 移动端
- `mobile-app/`（APK，React+TypeScript 重构）

### 1.3 核心业务逻辑
```
用户配置 → 世界观/角色/大纲生成 → 5-Agent协作逐章创作 → 审校定稿 → 记忆更新
   ↓                                          ↓
 文生图配图 ← 场景检测                     分层摘要/向量检索
```

---

## 二、漏洞列表

### 🔴 高危漏洞（7 项）

#### H1. 插件系统任意代码执行（RCE）
- **位置**：`plugin_system.py:49-53`、`203-315`
- **漏洞类型**：不安全的动态代码执行
- **代码**：
```python
spec = importlib.util.spec_from_file_location(f"plugin_{...}", str(entry_file))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)   # 直接执行插件目录任意 Python 文件
```
- **触发条件**：安装来自 URL/ZIP 的插件（`_install_from_url`/`_install_from_zip`），无签名校验、无沙箱、无用户确认。
- **影响范围**：以应用进程权限执行任意代码，可窃取 API Key、读写任意文件、植入后门。

#### H2. 插件安装 Zip Slip + 目录穿越
- **位置**：`plugin_system.py:248-249`（`extractall` 未校验成员路径）、`264-279`（`plugin.json` 的 `name` 未消毒拼接路径）
- **漏洞类型**：路径遍历 / 不安全文件操作
- **代码**：
```python
zip_ref.extractall(str(temp_path))           # 恶意 ../ 可穿越解压
plugin_name = config.get("name", ...)        # 未消毒
dest_dir = self.plugins_dir / plugin_name
shutil.rmtree(str(dest_dir))                 # 可删除任意目录
```
- **影响范围**：任意文件写入与删除（含 `rmtree` 删除父目录）。

#### H3. 后端认证完全失效（认证中间件未启用）
- **位置**：`backend/ai-service/app/main.py:55-56`、`backend/novel-service/app/main.py:59-60`
- **漏洞类型**：认证缺失
- **代码**：
```python
if settings.ENABLE_AUTH:
    app.add_middleware(AuthMiddleware, ...)
```
- **触发条件**：`ENABLE_AUTH` 在两个服务的 `core/config.py` 中**均未定义**，中间件永不挂载，所有 `/generate`、`/models`、`/api/v1/*` 端点匿名可访问。
- **影响范围**：LLM 推理资源被匿名滥用，云 API 费用失控。

#### H4. 硬编码 JWT 密钥 + API Key
- **位置**：`backend/*/app/middleware/auth.py:26`（`SECRET_KEY = "your-secret-key-change-in-production"`）、`250-257`（`test-api-key` 硬编码）
- **漏洞类型**：敏感信息泄露 / 认证绕过
- **触发条件**：攻击者用公开密钥伪造任意身份 Token，或用 `test-api-key` 直接通过认证。
- **影响范围**：认证体系整体失效。

#### H5. SSRF（`ai_service_url` 用户可控）
- **位置**：`backend/novel-service/app/main.py:74/92/109/124`、`generators/novel_generator.py:66-80`
- **漏洞类型**：服务端请求伪造
- **代码**：
```python
ai_service_url: str = Field("http://localhost:8001", ...)  # 任意字符串
await client.post(f"{self.ai_service_url}{endpoint}", ...)
```
- **触发条件**：请求体注入 `http://169.254.169.254/...`（云元数据）或任意内网地址。
- **影响范围**：内网探测、云元数据窃取、以服务为跳板攻击内部资源。

#### H6. 数值参数无边界校验（资源耗尽）
- **位置**：`backend/ai-service/app/main.py:81-85`、`api/routes.py:47/67`、`backend/novel-service/app/main.py:73/92`
- **漏洞类型**：输入验证缺失
- **代码**：
```python
max_tokens: int = Field(1000, ...)   # 无 ge/le 上限
chapter_count: int = Field(1, ...)   # 无上限
```
- **触发条件**：提交 `max_tokens=1000000` 或 `chapter_count=10000`。
- **影响范围**：单请求触发海量推理，费用与资源耗尽。

#### H7. 限流默认关闭
- **位置**：`backend/*/app/middleware/rate_limiter.py:19`（`ENABLED = False`）、`198-200`
- **漏洞类型**：滥用防护缺失
- **触发条件**：默认配置下 `dispatch` 直接放行，不限流。
- **影响范围**：匿名客户端无限调用生成接口，GPU/CPU 与费用失控。

---

### 🟡 中危漏洞（8 项）

#### M1. 加密密钥与密文同目录（加密形同虚设）
- **位置**：`app/secure_config.py:25/33-44`
- **问题**：`.config_key` 与 `config.json` 同目录，Windows 上 `chmod 0o600` 是空操作，本地进程可读密钥解密 API Key。

#### M2. 解密降级（明文敏感配置被静默接受）
- **位置**：`app/secure_config.py:52-68`
- **问题**：非 `gAAAAA` 前缀的旧格式/被篡改值直接按明文返回，无强制告警。

#### M3. 明文/加密配置共用同一文件
- **位置**：`app/config.py:37-41/52-60`
- **问题**：`AppConfig` 明文 `json.dump` 与 `SecureConfig` 加密写同一 `config.json`，任一路径触发明文保存即泄露 Key。

#### M4. 云存储凭据明文 + Token 走 URL
- **位置**：`cloud_storage.py:662-666`、`155/170/194/...`（access_token 放 query）
- **问题**：用户名/密码/token/cookie 明文落盘，token 经 URL 参数易被日志/Referer 泄露。

#### M5. `shell=True` 命令注入
- **位置**：`novel_app.py:6841`
- **代码**：`subprocess.Popen(['start', result], shell=True)`
- **问题**：`result` 为文件路径，若含 `&`/`|` 等 shell 元字符可执行任意命令。

#### M6. Prompt 注入
- **位置**：`backend/ai-service/app/api/routes.py:154-177`、`core/inference_engine.py:307-332`、`novel-service/generators/novel_generator.py:178-191`
- **问题**：用户可控的 `title`/`synopsis`/`chapter_outline` 直接拼进系统提示词，可注入指令操纵模型或诱导泄露。

#### M7. 错误信息泄露内部细节
- **位置**：两个服务所有异常处理（`raise HTTPException(status_code=500, detail=f"...{str(e)}")`）
- **问题**：原始异常信息（文件路径、库版本、内部实现）直接回显给客户端。

#### M8. 限流客户端标识可伪造
- **位置**：`backend/*/app/middleware/rate_limiter.py:177-194`
- **问题**：直接信任 `X-Forwarded-For`、`X-User-Id` 头，随机化即可绕过限流。

---

### 🟢 低危漏洞（5 项）

| 编号 | 位置 | 问题 |
|------|------|------|
| L1 | `app/ai_client.py:516-527`、`diagnostic_logger.py` | 诊断日志明文落盘小说正文与请求内容 |
| L2 | `backend/*/middleware/auth.py:127-138` | `decode_token_without_verification` 不验签（当前未用于鉴权，属隐患） |
| L3 | `character_system.py:525/539-540` | 角色删除/重命名用原始 name 拼路径（正常流程已消毒，被篡改配置可遍历） |
| L4 | `.env.example`、`docker-compose.prod.yml` | 占位符密码/弱口令兜底（`DB_PASSWORD`/`REDIS_PASSWORD` 无默认） |
| L5 | `backend/ai-service/app/main.py:6/309-310` | 未导入 `Request` 却在 `get_rate_limit_info` 注解引用，服务启动时 `NameError` |

---

## 三、风险等级汇总

| 风险等级 | 数量 | 编号 |
|----------|------|------|
| 🔴 高危 | 7 | H1~H7 |
| 🟡 中危 | 8 | M1~M8 |
| 🟢 低危 | 5 | L1~L5 |
| **合计** | **20** | - |

### 关键洞察
1. **最严重的是插件系统 RCE（H1/H2）**——桌面应用直接执行外部代码，无任何防护，是最高优先修复项。
2. **后端认证"全裸"（H3/H4/H5）**——认证开关未定义、密钥硬编码、SSRF，三项叠加使后端在暴露到公网时完全不设防。
3. **反序列化与 SQL 注入做得较好**——全项目仅 `json.loads`，无 `pickle`/`eval`/`exec`/`yaml.load`，无 SQL 字符串拼接，值得肯定。

---

## 四、修复建议（按优先级）

### P0 立即修复（高危）

| 序号 | 建议 | 对应漏洞 |
|------|------|----------|
| 1 | 插件系统加沙箱+签名校验：安装前要求用户确认，校验插件来源与哈希，禁止 `exec_module` 直接执行，改用受限子进程或清单白名单 | H1、H2 |
| 2 | `extractall` 改为逐成员校验路径（防 `../`），`plugin_name` 白名单消毒（只允许 `[A-Za-z0-9_-]`） | H2 |
| 3 | 在 `Settings` 补充 `ENABLE_AUTH` 字段并**默认启用**认证，接入真实密钥与数据库 API Key 校验 | H3、H4 |
| 4 | `SECRET_KEY`/API Key 改为环境变量注入，删除 `test-api-key` 硬编码 | H4 |
| 5 | `ai_service_url` 做严格白名单校验（仅内网固定主机，禁 IP/元数据地址/任意协议） | H5 |
| 6 | 为 `max_tokens`/`chapter_count`/`temperature` 增加 `ge/le` 边界，真正执行 `MAX_CHAPTERS`/`MAX_CHAPTER_LENGTH` | H6 |
| 7 | 限流 `ENABLED = True`，移除对 `X-Forwarded-For`/`X-User-Id` 的信任，改由网关层限流 | H7、M8 |

### P1 尽快修复（中危）

| 序号 | 建议 | 对应漏洞 |
|------|------|----------|
| 8 | 密钥改用 Windows DPAPI / keyring 托管，而非与密文同目录明文 `.config_key` | M1 |
| 9 | 移除解密降级逻辑，未加密旧配置强制重新加密 | M2、M3 |
| 10 | 云存储凭据加密存储，Token 改放 Header 而非 URL query | M4 |
| 11 | 去掉 `shell=True`，改用 `os.startfile` 或 `subprocess.run(list)` | M5 |
| 12 | 对用户输入做 Prompt 注入防护（转义/指令边界标记/输出约束） | M6 |
| 13 | 异常响应改为通用错误提示，`str(e)` 仅记录服务端日志 | M7 |

### P2 计划修复（低危）

| 序号 | 建议 | 对应漏洞 |
|------|------|----------|
| 14 | 诊断日志脱敏（不落小说正文，或加访问控制） | L1 |
| 15 | 删除或隔离 `decode_token_without_verification` 调试函数 | L2 |
| 16 | 角色删除/重命名也做文件名消毒 | L3 |
| 17 | `docker-compose.prod.yml` 增加强密码默认校验，部署时强制替换 `.env.example` 占位符 | L4 |
| 18 | `ai-service/main.py` 导入 `Request`，修复启动崩溃 | L5 |

---

*报告结束*
