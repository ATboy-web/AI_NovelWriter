# `mobile-app/webview-app` — 已归档（不再维护）

> **状态：ARCHIVED / 只读留档**
> 决策日期：2026-09-17 · 决策：**保留 + 补本说明**（不删除）
> 登记处：`docs/BACKLOG_REGISTER.md` §4（M2）

## 这是什么

一个 **Android WebView 壳应用**：Kotlin/Java 只做三件事 ——

1. 用 `WebView` 加载打包进 `assets/` 的单页应用（`index.html` + `app.js` + `style.css`）；
2. 暴露一个 `NovelFS` 的 `JavascriptInterface`，把手机端文件读写映射到
   `getExternalFilesDir()/AI_NovelWriter/`；
3. 暴露 `startAsyncHttp`，由原生侧发起 HTTP 请求以绕过 WebView 的 CORS 限制。

界面逻辑全部在那份**已经打包压缩过的 `app.js`（63 KB）**里。

## 为什么不再维护

它在同一份仓库里被**同一个形态的更新实现取代了两次**：

| | `webview-app`（本目录） | `novel-app`（现行） |
|---|---|---|
| 形态 | WebView 壳 + 打包后的 HTML/JS | Kotlin + Jetpack Compose 原生 |
| `versionName` | `3.0.1` | `4.0.1` |
| CI 构建 | ❌ 无任何 CI 任务引用 | ✅ `ci.yml` 的 `android` 作业 |
| 发布产物 | 无 | `mobile-app/AI_NovelWriter_v4.0.1.apk` |
| 引入方式 | 源码内**仅** `CONTRIBUTING.md:191` 一处目录树列举 | `README` / 发布说明均有 |

因此本目录**不参与任何构建、测试、发布流程**，也没有任何自动化会因它变化而失败。
保留而不删除，理由见下。

## 保留的理由（而非删除）

1. **它不是垃圾，是一次真实的架构取舍留档。** WebView 壳方案的失败点（`loadDataWithBaseURL`
   对本地资源的解析、打包后 JS 无法调试、CORS 需要原生侧代发请求）是后来选择
   Compose 原生重写的直接依据。删掉代码就只剩结论，没有证据。
2. **删不删都不影响正确性，但删除了就不可逆。** 保留的成本只有 522 KB 与一次目录列举。
3. **git 历史里它本来就还在**，所以"留档"不需要额外动作 —— 本文件的作用是
   **让下一个人不必再去 git log 里考古**，并且**明确告诉他不该动它**。

## 已知的技术债（仅记录，不修）

| 项 | 说明 |
|---|---|
| 构建产物入库 | `app/src/main/assets/assets/app.js`（63 KB）与 `style.css`（8 KB）是**压缩后的产物**，却被提交进了仓库。属「构建产物入库」反模式；现行 `novel-app` 不再这样。 |
| 无构建入口 | 无 CI 任务、无构建脚本；`gradlew` 保留但从未在 CI 跑过。 |
| 文件系统接口的路径校验 | `NovelFileInterface.getSafeFile` 用字符串替换去除 `..`，虽然之后有 `getCanonicalPath().startsWith(...)` 兜底，但仍是先净化后校验的顺序。属**已归档代码的历史写法**，不修。 |

## 如果你确实需要它重新可用

请**不要在这里改**。正确做法是：

1. 明确它与 `novel-app` 的关系（是替代掉 Compose 版，还是作为"低端机降级通道"并存）；
2. 若是并存，需要先补上未打包的 JS/TS 源码，并把构建纳入 `ci.yml` ——
   否则无法维护（现在只有压缩产物，改不了）；
3. 更新 `CONTRIBUTING.md:191` 的目录树说明，去掉"WebView 应用"这个中性描述，
   改为写明维护状态。

以上都完成后，把本文件删掉、并把 `docs/BACKLOG_REGISTER.md` §4 的 M2 改为"已重启维护"。
