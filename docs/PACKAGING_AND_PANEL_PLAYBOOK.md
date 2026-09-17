# 打包与面板开发 · 操作手册

> 本文件收纳「改 spec / 发版 / 新增面板」时必须照做的步骤与已知陷阱。
> 项目长期内存 `~/.workbuddy` 的 MEMORY.md 只保留索引与不变式，细节在这里。
> 相关：`scripts/check_bundle.py`（打包内容核对）、`tests/test_bundle_manifest.py`（其守卫）、
> `tests/test_p4b_panels.py` / `tests/test_image_and_local_model.py`（面板守卫）。

---

## 1. 构建 DESKTOP EXE

```bash
cd installer
<Python311> -m PyInstaller novel_app.spec --noconfirm \
    --distpath "%TEMP%\anw_dist_x" --workpath "%TEMP%\anw_work_x"
```

- 解释器固定用 `…\Programs\Python\Python311\python.exe`（3.11.9 + PyInstaller + tkinter）。
  ⚠️ `.workbuddy\…\3.13.12\python.exe` 是**空环境** —— **必须探测 import，不能只看文件存在**。
- 耗时约 19 秒。产物约 26 MB。

### 🔴 `--distpath` 必须带

spec 里写的是 `name='../AI_NovelWriter'`。**不带 `--distpath`** 时它会解析到
**仓库根目录**，于是根目录出现一个 `AI_NovelWriter.exe` —— 这正是一处
「旧构建被误当新版」的来源（实测真的发生过）。

### 🔴 "构建成功" ≠ "功能齐全"

`app/__init__` 对导入失败的处理是**降级为 `_ImportStub`**，而不是抛异常。
这是刻意的容错设计，副作用是：**缺依赖的 EXE 不报错、只静默丢功能**。

真实事故：release 作业只装了 `pyinstaller loguru`，EXE 里缺
httpx / Pillow / cryptography，程序照常启动、界面照常出现，直到用户点了某个功能才发现。

**所以构建前先确认 `pyproject.toml` 的依赖都装了。** 实测曾缺：
python-docx / pypdf / ebooklib / markdown / beautifulsoup4 / **fpdf2**。

### ✅ 构建后必须核对打包内容

```bash
python scripts/check_bundle.py "%TEMP%\anw_work_x\novel_app\Analysis-00.toc"
```

判据分三类（来源不同，不能混）：
| 类别 | 判据来源 | 例 |
|---|---|---|
| 必需（代码直接 import） | 源码里的 import 语句 | httpx / loguru / tkinter / docx / ebooklib / pypdf |
| 必需（传递依赖） | 直接依赖的 Requires-Dist | lxml（python-docx 需要） |
| 声明但未用 | `pyproject` 有、`app/` 零 import | markdown / bs4 |

**两个踩过的判据陷阱**：
1. **不能用字符串匹配** —— PyInstaller 的 TOC typecode 里有一个就叫 `PIL`
   （用于 Pillow 图像资源），字符串搜 `"PIL"` 会把"有这个**标签**"误当成"有这个**包**"。
2. **不能把 `pyproject` 声明当"代码用到"** —— 会报出假缺口。

---

## 2. 分发与验证

### 🔴 分发旧文件**不要保留可执行扩展名**

曾把旧 EXE 留在桌面为 `AI_NovelWriter.bak-<时间戳>.exe` —— 与正式文件只差一个后缀，
**且仍可双击运行**。用户双击了它，整整一轮 10 分钟的功能验证全部跑在旧构建上、
结论全废。

**备份应为 `*.exe.old-<时间戳>` 这类不可双击的形式。**

### 分发动作

- 用 `shutil.copyfile`（截断写），**不要**用 `Copy-Item -Force`
  （目标被占用时可能留下半截文件而不报错）。
- 分发后**核对源与目标的 sha256**，不能只看"文件存在"。

### EXE 冒烟

onefile 应见**双进程**（引导 + 应用），窗口标题非空（`AI小说创作工坊 vX.Y.Z`）。
启动后查诊断日志的 `SYSTEM/panel_registry` 事件：

- **应为 16 面板 / 5 分组**
- **`load_failures` 必须为 `[]`**

探针脚本模板 `%TEMP%\smoke_exe.py`（`Popen` + Win32 `EnumWindows` 读标题）。
⚠️ `Start-Process` 拉起 GUI 被本沙箱约束；`WM_CLOSE` 可能不生效
⇒ 退出路径（性能报告落盘）难以自动验证，需人工双击确认。

### 🔴 判定"那次运行的是哪个构建"

不要靠猜。两个可靠手段：

1. **看诊断日志里"只在新版出现的字段/事件"是否存在** ——
   例如本轮用 `panel_registry` 是否含 `log_dir` 字段、有无 `CHAPTER/*/complete`。
   这是最省事的判据。
2. `tasklist` / `wmic` 取运行进程的 `ExecutablePath`，把 **PID** 与诊断日志里的
   `session`（形如 `20260917-181335-25168`，末段就是 PID）对齐。

反编译取证的两个坑（都踩过）：
- **别对 `.pyz` 做二进制字符串搜索** —— 里面每个模块都是 zlib 压缩的，搜不到是**假阴性**；
- PyInstaller onefile **不把 PYZ 解包到磁盘**（只解 DLL/数据），要读归档得用
  `CArchiveReader` 打开 EXE 本身。

---

## 3. 残留清理

| 目标 | 说明 |
|---|---|
| `%TEMP%\_MEI*` | onefile 每次运行的解包目录，**实测积到 1079 MB** |
| `installer/build` | PyInstaller 缓存，可再生 |
| 各处旧 `.exe` | 桌面、仓库根、`installer/dist/` |

**清理前先确认无进程占用**：`tasklist` 查进程 + **逐个文件以写模式试开**。
删除用 Python 的 `shutil.rmtree` / `os.remove`（沙箱会重定向到回收站，可回滚），
不要用 `Remove-Item` / `Shell.Application`（易被策略拦）。

> `installer/dist/AI_NovelService.exe` 与 `NovelGenerator.exe` 是
> `installer.nsi` 打包安装程序时需要的产物；删掉后需先跑 `build.bat app` 再打 NSIS。

---

## 4. 新增一个原生面板

**三处改动**：

1. 新建 `app/panels/xxx_panel.py`，继承 `BasePanel`，声明
   `key` / `title` / `category`（取值见 `registry.CATEGORY_ORDER`）/ `order` /
   `description` / `topics_of_interest`，并实现 `build(parent) -> Widget`。
2. `app/panels/registry.py` 的 **`NATIVE_PANEL_MODULES` 加一行**。
3. `installer/novel_app.spec` 的 **`hiddenimports` 加一行**
   —— 原生面板是按**字符串**动态导入的，不列就会在打包后少一块。

分发层（`toolkit_ui` / `shell_ui`）**零改动** —— 它们只读注册表。

### 两个易漏点

- ❗ **`build()` 末尾必须 `self.mark_built(True)`**。
  宿主的 `is_built` 靠它判断走"复用"还是"重建"，漏了会被**重复构建**。
  （其它三个原生面板都有这一行。）
- ❗ **面板总数写进了内存与文档**（现 **16 面板 / 5 分组**），新增面板要同步。

### `ui_kit` 的两个反直觉点

- **`pretty_tree()` 返回的是 dict**（`{"frame","tree","scrollbar","sort_by"}`），
  不是 `ttk.Treeview` —— 拿控件要 `holder["tree"]`。
  且 `columns` 是**列名序列**（`["文件"]`），宽度另传 `widths=[240]`；
  返回的 `frame` **还要自行 pack**。
- **`toolbar()` 只返回三块 Frame**（`{"bar","left","right"}`），**不自行 pack**
  —— 忘记 pack `bar["bar"]` 会得到一个不可见的工具条。

### 其它既有约定

- **`ui_kit.py` 是唯一视觉来源**；4px 刻度、颜色全走令牌。
  `accent/success/info/error` 是**填充色**，当文字用不达标 ⇒ 用 `*_text` 变体。
- **外壳由宿主统一加**（`PanelHost._build_with_chrome`）；面板不自己加标题栏。
- ⚠️ **重建前必须 destroy 容器子控件**（外壳与内容同一 frame，不销毁会叠两份）。
- ❗ **面板不得依赖 `PIL`**：spec **有意排除 `PIL`**，
  凡用到 PIL 的地方都要 `except ImportError` 降级（否则打包后功能消失）。
- **生成/网络动作不得阻塞 UI 线程**：走 `app/async_runner.BackgroundRunner`
  回主线程后再碰控件（Tk 非线程安全）。
