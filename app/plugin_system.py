"""插件系统（v3.2 重新启用 + 改良）。

## 为什么它曾经消失

`plugin_system.py`（根目录，539 行）在 `ec8a545` 被完整实现，
又在 `34ce8b1` 被当作"全仓无引用的死模块"删除。删除理由本身是**正确的**
（当时确实零 import），但它暴露了一个更根本的问题：

> **实现得再完整，"没有任何调用方"就等于不存在。**

这正是本仓最高频的失效模式「注册即遗忘」的第 N 次实例化。
所以本次"重新启用"的目标**不是把文件搬回来**，而是把**两端都建起来**：

| 端 | 本次补的东西 |
|---|---|
| **写** | `PluginManager`（发现 / 校验 / 安装 / 启停 / 卸载） |
| **读** | 4 个真实消费点：`writing_skills`（写作技能包）/ `novel_toolkit`（素材库）/ 导出器 / AI 提供商占位 |
| **看** | `app/panels/plugin_panel.py`（插件中心面板，第 17 个面板） |
| **钉** | `tests/test_plugin_system.py`（含"守卫必须双向"：功能被删要变红） |

## 与旧实现的差异（改良点）

1. **注册表驱动，而非硬编码分支** —— 「新增一类插件只改注册表一处」，
   与 `app/providers/registry.py`、`IMAGE_BACKENDS` 同构。
2. **结构化结果对象** `PluginResult`（`ok` / `message` / `as_dict()`），
   仿 `BalanceResult` / `ImageGenResult` —— 界面能直接展示"为什么失败"。
3. **安全默认更严**：
   - 插件**默认不启用**（旧实现 `enabled=True` 是危险的默认值）—— 装完必须显式启用；
   - 启用状态**持久化**到 `~/.ai_novel_writer/plugins.json`（旧实现只在内存里）；
   - 安装前做**入口文件静态体检**（`audit_plugin`）：列出它会 import 什么、
     是否触碰 `os.system` / `subprocess` / `eval` / `socket` 等高危符号，
     把"这个插件能干什么"**在启用前**摆给用户看；
   - 沿用并加固旧实现的 `_sanitize_plugin_name` + `_safe_extract`（Zip Slip）。
4. **不阻塞界面** —— 安装要下载/解压，走 `BackgroundRunner`。

## 安全边界（明确写清楚，不做虚假承诺）

插件是**以本应用同等权限运行的 Python 代码**。它能读写用户的文件、发起网络请求。
本模块能做的只有：**限制安装路径、拒绝危险名称、在启用前把风险摆出来**。
它**不能**沙箱化插件代码 —— 任何声称"安全沙箱"的实现都是误导。
因此本模块的定位是：**降低误装风险 + 让风险可见**，而不是"让不可信代码变安全"。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from loguru import logger

__all__ = [
    "PLUGIN_TYPES",
    "PLUGIN_TYPE_LABELS",
    "DANGEROUS_SYMBOLS",
    "Plugin",
    "PluginAudit",
    "PluginManager",
    "PluginResult",
    "audit_plugin",
    "default_plugins_dir",
    "sanitize_plugin_name",
    "safe_extract",
]

#: 插件类型 → 消费者的注册表（「新增一类插件只改这里一处」）。
#: 值为该类型插件会贡献的能力名（供 UI 与统计使用）。
PLUGIN_TYPES: dict[str, str] = {
    "writing_skill": "写作技能包",
    "library": "素材库扩充",
    "exporter": "导出格式",
    "ai_provider": "AI 服务",
    "tool": "创作工具",
}

PLUGIN_TYPE_LABELS: dict[str, str] = dict(PLUGIN_TYPES)

#: 静态体检关注的高危符号。**只用于"告知"，不做拦截** ——
#: 拦截既不可靠（可以绕）又会产生虚假安全感，正确做法是把风险摆到启用前。
DANGEROUS_SYMBOLS: dict[str, str] = {
    "os.system": "执行系统命令",
    "os.popen": "执行系统命令并读取输出",
    "subprocess": "启动外部进程",
    "eval": "执行动态代码",
    "exec": "执行动态代码",
    "compile": "编译动态代码",
    "__import__": "动态导入",
    "socket": "原始网络访问",
    "pickle": "反序列化任意对象（可执行代码）",
    "ctypes": "直接调用本地动态库",
    "shutil.rmtree": "递归删除目录",
    "os.remove": "删除文件",
    "os.unlink": "删除文件",
    "open": "读写本地文件",
}

#: 插件名白名单：字母 / 数字 / 中文 / 下划线 / 连字符 / 点，**外加常见中文标点**。
#: 拒绝路径分隔符与目录穿越字符。
#:
#: ❗ 为什么必须带上 `·`（U+00B7，间隔号）：中文插件名写「作者·插件」是常态，
#: 而 `\w` **不匹配**它 —— 最初只允许 `\w\u4e00-\u9fff.\-` 时，
#: 一个名字里带间隔号的合法插件会被判"非法名"直接装不上（实测踩到）。
#: 同理 `（）` `「」` `：` `•` 等在中文命名里都属正常字符，
#: 而它们**都不构成路径风险** —— 真正的风险字符只有 `/` `\` `:`(裸冒号) `..`。
#: 所以判据从"尽量少放行"改为"只拦真正危险的"，才符合"名字是给人看的"这一事实。
_PLUGIN_NAME_PATTERN = re.compile(
    r"^[\w\u4e00-\u9fff"
    r"\u00b7\u2022"  # 间隔号 · / 项目符号 •
    r"\u3001\u3002"  # 顿号 、 / 句号 。
    r"\u300a\u300b\u300c\u300d\u300e\u300f"  # 《》「」『』
    r"\uff08\uff09\uff1a"  # （）： 全角括号与冒号
    r".\-"
    r"]+$"
)

#: 额外的**结构**校验（比字符白名单更准确的风险判据）：
#: 名字不得包含路径分隔符、不得是 `.` / `..`、不得以 `.` 开头。
_PLUGIN_NAME_FORBIDDEN = ("/", "\\", "\x00")

#: 单个插件入口文件的大小上限（防止把巨型文件塞进插件目录拖垮解析）。
_MAX_ENTRY_BYTES = 2 * 1024 * 1024


def default_plugins_dir() -> Path:
    """插件根目录（唯一来源 —— 别在别处再拼一次这个路径）。"""
    return Path.home() / ".ai_novel_writer" / "plugins"


def default_state_file() -> Path:
    """插件启用状态的文件（唯一来源）。"""
    return Path.home() / ".ai_novel_writer" / "plugins.json"


# ====================================================================== 结果对象


@dataclass
class PluginResult:
    """一次插件操作的结果（仿 `BalanceResult` / `ImageGenResult`）。

    为什么用对象而不是 `dict`：调用方（面板）需要区分
    "装成功了但有安全提示" / "失败且原因是名字非法" / "失败且原因是网络"，
    这些用 bool 表达不了，用裸 dict 又会各处写出不同的键名。
    """

    ok: bool
    message: str
    plugin_name: str = ""
    security_warning: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "plugin_name": self.plugin_name,
            "security_warning": self.security_warning,
            **self.detail,
        }


# ====================================================================== 静态体检


@dataclass
class PluginAudit:
    """插件入口文件的静态体检结果（**告知用途**，非沙箱）。"""

    imports: list[str] = field(default_factory=list)
    dangerous: list[tuple[str, str]] = field(default_factory=list)
    syntax_error: str = ""

    @property
    def risk_level(self) -> str:
        """`safe` / `notice` / `high` —— 供界面标色。

        判据刻意保守：出现任一高危符号即 `high`；仅普通 import 为 `safe`。
        """
        if self.syntax_error:
            return "high"
        if self.dangerous:
            return "high"
        return "safe"

    def summary(self) -> str:
        if self.syntax_error:
            return f"无法解析入口文件：{self.syntax_error}"
        if not self.dangerous:
            return "未发现高危调用"
        seen: list[str] = []
        for name, why in self.dangerous:
            item = f"{name}（{why}）"
            if item not in seen:
                seen.append(item)
        return "触及：" + "、".join(seen[:8])

    def as_dict(self) -> dict[str, Any]:
        return {
            "imports": list(self.imports),
            "dangerous": [list(d) for d in self.dangerous],
            "risk_level": self.risk_level,
            "summary": self.summary(),
        }


def audit_plugin(entry_file: Path) -> PluginAudit:
    """静态体检一个插件入口文件：它 import 什么、用到哪些高危符号。

    ❗ 这是**告知机制**，不是安全边界。插件代码仍以应用同等权限运行。
    它的价值在于：让"启用"这个动作发生在**用户已看到风险**之后。
    """
    audit = PluginAudit()
    try:
        raw = entry_file.read_bytes()
    except OSError as exc:
        audit.syntax_error = f"读取失败：{exc}"
        return audit
    if len(raw) > _MAX_ENTRY_BYTES:
        audit.syntax_error = f"入口文件过大（{len(raw)} 字节，上限 {_MAX_ENTRY_BYTES}）"
        return audit
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        audit.syntax_error = f"{type(exc).__name__}: {exc}"
        return audit

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    audit.imports = sorted(set(imports))

    # 高危符号分两类收集 —— 只看其中一类会漏：
    #   ① **属性访问**：`os.system` / `shutil.rmtree` / `eval` 这类要点号才能识别；
    #   ② **裸 import**：`import socket` / `import subprocess` 不产生属性访问节点，
    #      只看 ① 会把"直接 import socket 开原始连接"判成 safe（实测漏报过）。
    hit_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            hit_names.add(f"{node.value.id}.{node.attr}")
        elif isinstance(node, ast.Name):
            hit_names.add(node.id)
    # 顶层包名也算命中（`import socket` / `from socket import ...`）
    hit_names.update(name.split(".")[0] for name in audit.imports)

    for symbol, why in DANGEROUS_SYMBOLS.items():
        if symbol in hit_names:
            audit.dangerous.append((symbol, why))
    # `open` 在插件里极常见且多为读配置，单独降噪：只有出现在调用位置才算
    if ("open", "读写本地文件") in audit.dangerous:
        called = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open" for n in ast.walk(tree)
        )
        if not called:
            audit.dangerous = [d for d in audit.dangerous if d[0] != "open"]
    return audit


# ====================================================================== 路径安全


def sanitize_plugin_name(name: str) -> Optional[str]:
    """消毒插件名，防止目录穿越 / Zip Slip。

    允许字母、数字、中文、下划线、连字符、点，以及常见中文标点（含间隔号 `·`）。
    拒绝空名、超长、路径分隔符、`..`、隐藏目录（以点开头）。

    ❗ 判据的演进：起初用窄白名单（`\\w` + 中文 + `.` + `-`），
    结果「示例插件·去油文风」这种**完全正常**的中文名被判非法。
    现在改为"白名单放宽到所有非危险字符 + 结构校验兜底" ——
    安全性靠 `_PLUGIN_NAME_FORBIDDEN` / `..` / 前导点来保证，
    而不是靠"能放行的字符尽量少"。
    """
    if not name:
        return None
    name = name.strip()
    if not name or len(name) > 64:
        return None
    if any(ch in name for ch in _PLUGIN_NAME_FORBIDDEN):
        return None
    if not _PLUGIN_NAME_PATTERN.match(name):
        return None
    if name.startswith(".") or ".." in name:
        return None
    return name


def safe_extract(zip_ref: zipfile.ZipFile, dest: Path) -> None:
    """安全解压 ZIP，防止 Zip Slip（路径穿越）。

    逐个成员校验解析后的绝对路径仍在目标目录内；越界即抛 `ValueError`。
    ❗ 用 `is_relative_to` 而不是字符串 `startswith` —— 后者会被
    `/tmp/plugin_evil` 这种"前缀相同但并非子目录"的路径绕过。
    """
    dest = dest.resolve()
    for member in zip_ref.infolist():
        target = (dest / member.filename).resolve()
        if not target.is_relative_to(dest):
            raise ValueError(f"检测到不安全的 ZIP 路径: {member.filename}")
    zip_ref.extractall(str(dest))


# ====================================================================== 插件对象


class Plugin:
    """一个已加载的插件。"""

    def __init__(self, plugin_dir: Path, enabled: bool = False):
        self.plugin_dir = plugin_dir
        self.config = self._load_config()
        self.name = self.config.get("name", plugin_dir.name)
        self.version = str(self.config.get("version", "1.0.0"))
        self.author = self.config.get("author", "未知")
        self.description = self.config.get("description", "")
        self.plugin_type = self.config.get("type", "tool")
        self.entry = self.config.get("entry", "main.py")
        # 🔴 默认**不启用**：装完必须显式启用（旧实现默认 True 是危险默认值）。
        # 启用状态由 PluginManager 从状态文件回填。
        self.enabled = enabled
        self.module: Any = None
        self.load_error = ""
        self.audit = audit_plugin(self.plugin_dir / self.entry)
        self._load_module()

    def _load_config(self) -> dict:
        config_file = self.plugin_dir / "plugin.json"
        if not config_file.exists():
            return {}
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[插件] 读取 {config_file} 失败：{exc}")
            return {}

    def _load_module(self) -> None:
        entry_file = self.plugin_dir / self.entry
        if not entry_file.exists():
            self.load_error = f"入口文件不存在：{self.entry}"
            return
        try:
            # 模块名带上插件目录名，避免不同插件的 `main` 互相覆盖 sys.modules
            module_name = f"anw_plugin_{abs(hash(str(self.plugin_dir.resolve())))}"
            spec = importlib.util.spec_from_file_location(module_name, str(entry_file))
            if spec is None or spec.loader is None:
                self.load_error = "无法为该入口文件建立导入规格"
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            self.module = module
        except Exception as exc:  # noqa: BLE001 - 坏插件不该拖垮应用启动
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.error(f"[插件] 加载 {self.name} 失败：{self.load_error}")

    # ---- 各类型能力（统一返回"可能为空"的容器，调用方无需判 None）

    def _collect(self, func_name: str, default: Any) -> Any:
        if self.module is None or not hasattr(self.module, func_name):
            return default
        try:
            return getattr(self.module, func_name)() or default
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[插件] {self.name}.{func_name}() 失败：{type(exc).__name__}: {exc}")
            return default

    def get_writing_skills(self) -> list[dict]:
        """写作技能包：`[{name, description, prompt, rules[]}]`。

        这是本次"引入 Agent skill for beautiful"的落点 ——
        插件用**纯数据**（提示词片段 + 禁用词规则）增强写作，
        不要求插件作者理解本仓的 Agent 内部结构。
        """
        return self._collect("get_writing_skills", [])

    def get_library(self) -> Optional[dict]:
        return self._collect("get_library", None)

    def get_exporters(self) -> list[dict]:
        return self._collect("get_exporters", [])

    def get_ai_providers(self) -> list[dict]:
        return self._collect("get_ai_providers", [])

    def get_tools(self) -> list[dict]:
        return self._collect("get_tools", [])

    # ---- 展示

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "type": self.plugin_type,
            "type_label": PLUGIN_TYPE_LABELS.get(self.plugin_type, self.plugin_type),
            "enabled": self.enabled,
            "plugin_dir": str(self.plugin_dir),
            "load_error": self.load_error,
            "capabilities": self.capabilities(),
            "risk_level": self.audit.risk_level,
            "risk_summary": self.audit.summary(),
        }

    def capabilities(self) -> list[str]:
        """本插件实际提供了哪几类能力（按注册表顺序，稳定的展示顺序）。"""
        found: list[str] = []
        if self.get_writing_skills():
            found.append("writing_skill")
        if self.get_library():
            found.append("library")
        if self.get_exporters():
            found.append("exporter")
        if self.get_ai_providers():
            found.append("ai_provider")
        if self.get_tools():
            found.append("tool")
        return found


# ====================================================================== 管理器


class PluginManager:
    """插件管理器：发现 / 安装 / 启停 / 卸载 / 汇总能力。

    状态持久化到 `plugins.json`（`{"enabled": ["插件名", ...]}`）。
    """

    def __init__(self, plugins_dir: Path | None = None, state_file: Path | None = None):
        self.plugins_dir = Path(plugins_dir) if plugins_dir else default_plugins_dir()
        self.state_file = Path(state_file) if state_file else default_state_file()
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.plugins: dict[str, Plugin] = {}
        self._enabled_names: set[str] = self._load_state()
        self.reload()

    # ---- 状态文件

    def _load_state(self) -> set[str]:
        if not self.state_file.exists():
            return set()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return set(data.get("enabled", []) or [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[插件] 读取状态文件失败，按全部未启用处理：{exc}")
            return set()

    def _save_state(self) -> PluginResult:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"enabled": sorted(self._enabled_names)}
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return PluginResult(True, "已保存插件启用状态")
        except OSError as exc:
            return PluginResult(False, f"保存插件状态失败：{exc}")

    def reload(self) -> list[Plugin]:
        """重新扫描插件目录。**加载失败的插件也会被保留**（带 `load_error`），

        这样用户能在面板上看到"这个插件坏了、坏在哪"，
        而不是它默默消失（旧实现 `if plugin.module:` 直接丢弃，属于静默失败）。
        """
        self.plugins.clear()
        if not self.plugins_dir.is_dir():
            return []
        for child in sorted(self.plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            plugin = Plugin(child, enabled=child.name in self._enabled_names)
            self.plugins[plugin.name] = plugin
        return list(self.plugins.values())

    # ---- 查询

    def get(self, name: str) -> Optional[Plugin]:
        return self.plugins.get(name)

    def all_plugins(self) -> list[Plugin]:
        return list(self.plugins.values())

    def enabled_plugins(self) -> list[Plugin]:
        """已启用**且加载成功**的插件。"""
        return [p for p in self.plugins.values() if p.enabled and p.module is not None]

    def list_plugins(self) -> list[dict[str, Any]]:
        return [p.info() for p in self.plugins.values()]

    # ---- 启停

    def enable(self, name: str) -> PluginResult:
        plugin = self.plugins.get(name)
        if plugin is None:
            return PluginResult(False, f"插件不存在：{name}", name)
        if plugin.module is None:
            return PluginResult(False, f"插件加载失败，无法启用：{plugin.load_error}", name)
        plugin.enabled = True
        self._enabled_names.add(name)
        self._save_state()
        warning = ""
        if plugin.audit.risk_level == "high":
            warning = f"该插件{plugin.audit.summary()}；插件代码以应用同等权限运行，请确认来源可信。"
        return PluginResult(True, f"已启用「{name}」", name, security_warning=warning)

    def disable(self, name: str) -> PluginResult:
        plugin = self.plugins.get(name)
        if plugin is None:
            return PluginResult(False, f"插件不存在：{name}", name)
        plugin.enabled = False
        self._enabled_names.discard(name)
        self._save_state()
        return PluginResult(True, f"已停用「{name}」", name)

    # ---- 能力汇总（真实消费点从这里取数据）

    def all_writing_skills(self) -> list[dict]:
        """汇总所有已启用插件提供的写作技能包（每项带上来源插件名）。"""
        out: list[dict] = []
        for plugin in self.enabled_plugins():
            for skill in plugin.get_writing_skills():
                if not isinstance(skill, dict):
                    continue
                item = dict(skill)
                item["plugin"] = plugin.name
                out.append(item)
        return out

    def all_libraries(self) -> dict[str, list[dict]]:
        """`{库类型: [{plugin, category, items}]}`。"""
        out: dict[str, list[dict]] = {}
        for plugin in self.enabled_plugins():
            lib = plugin.get_library()
            if not isinstance(lib, dict):
                continue
            lib_type = str(lib.get("type", "unknown"))
            out.setdefault(lib_type, []).append(
                {
                    "plugin": plugin.name,
                    "category": lib.get("category", ""),
                    "items": lib.get("items", []) or [],
                }
            )
        return out

    def all_exporters(self) -> list[dict]:
        out: list[dict] = []
        for plugin in self.enabled_plugins():
            for exporter in plugin.get_exporters():
                if isinstance(exporter, dict):
                    out.append({**exporter, "plugin": plugin.name})
        return out

    def all_ai_providers(self) -> list[dict]:
        out: list[dict] = []
        for plugin in self.enabled_plugins():
            for provider in plugin.get_ai_providers():
                if isinstance(provider, dict):
                    out.append({**provider, "plugin": plugin.name})
        return out

    def all_tools(self) -> list[dict]:
        out: list[dict] = []
        for plugin in self.enabled_plugins():
            for tool in plugin.get_tools():
                if isinstance(tool, dict):
                    out.append({**tool, "plugin": plugin.name})
        return out

    # ---- 安装

    def install(self, source: str) -> PluginResult:
        """安装插件。`source` 支持本地目录 / ZIP 文件 / http(s) URL。"""
        source = (source or "").strip()
        if not source:
            return PluginResult(False, "请提供插件来源（目录、ZIP 文件或 URL）")
        try:
            parsed = urlparse(source)
            if parsed.scheme in ("http", "https"):
                return self._install_from_url(source)
            if source.lower().endswith(".zip"):
                return self._install_from_zip(Path(source))
            return self._install_from_directory(Path(source))
        except Exception as exc:  # noqa: BLE001 - 统一收敛成结果对象
            return PluginResult(False, f"安装失败：{type(exc).__name__}: {exc}")

    def _install_from_url(self, url: str) -> PluginResult:
        import urllib.request

        parsed = urlparse(url)
        # GitHub 仓库页 → 归档下载地址
        if parsed.netloc.endswith("github.com") and not url.lower().endswith(".zip"):
            url = url.rstrip("/") + "/archive/refs/heads/main.zip"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = Path(temp_dir) / "plugin.zip"
                urllib.request.urlretrieve(url, str(zip_path))  # noqa: S310 - 用户显式提供的 URL
                return self._install_from_zip(zip_path)
        except Exception as exc:  # noqa: BLE001
            return PluginResult(False, f"下载失败：{type(exc).__name__}: {exc}")

    def _install_from_zip(self, zip_path: Path) -> PluginResult:
        if not zip_path.exists():
            return PluginResult(False, f"ZIP 文件不存在：{zip_path}")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            try:
                # 用 `zipfile.is_zipfile` 先判断，避免把坏文件当 ZIP 解（会抛 BadZipFile）
                if not zipfile.is_zipfile(str(zip_path)):
                    return PluginResult(False, "不是有效的 ZIP 文件")
                with zipfile.ZipFile(str(zip_path), "r") as zip_ref:
                    safe_extract(zip_ref, temp_path)
            except ValueError as exc:
                return PluginResult(False, str(exc))
            except zipfile.BadZipFile:
                return PluginResult(False, "ZIP 文件已损坏")
            plugin_dir = self._find_plugin_dir(temp_path)
            if plugin_dir is None:
                return PluginResult(False, "ZIP 中未找到有效插件（缺少 plugin.json）")
            return self._install_into_store(plugin_dir)

    def _install_from_directory(self, source_dir: Path) -> PluginResult:
        if not source_dir.exists():
            return PluginResult(False, f"目录不存在：{source_dir}")
        if not source_dir.is_dir():
            return PluginResult(False, f"不是目录：{source_dir}")
        if not (source_dir / "plugin.json").exists():
            return PluginResult(False, "目录中缺少 plugin.json")
        # 防止把插件目录**安装到自己内部**（会递归复制到磁盘写满）
        try:
            if source_dir.resolve() == self.plugins_dir.resolve():
                return PluginResult(False, "源目录就是插件根目录，无需安装")
            if self.plugins_dir.resolve().is_relative_to(source_dir.resolve()):
                return PluginResult(False, "源目录包含了插件根目录，会造成递归复制")
        except OSError:
            pass
        return self._install_into_store(source_dir)

    def _install_into_store(self, plugin_src: Path) -> PluginResult:
        """把已定位到的插件目录复制进插件根目录并加载。"""
        raw_name = self._read_plugin_name(plugin_src)
        plugin_name = sanitize_plugin_name(raw_name)
        if not plugin_name:
            return PluginResult(
                False,
                f"插件名「{raw_name}」非法：仅允许字母、数字、中文、下划线、连字符、点",
            )
        if plugin_name in self.plugins:
            return PluginResult(False, f"插件「{plugin_name}」已存在，请先卸载", plugin_name)

        dest_dir = self.plugins_dir / plugin_name
        try:
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(plugin_src, dest_dir)
        except OSError as exc:
            return PluginResult(False, f"复制插件失败：{exc}", plugin_name)

        plugin = Plugin(dest_dir, enabled=False)  # 🔴 装完不自动启用
        if plugin.module is None:
            # 加载失败 ⇒ 不留半成品目录（否则目录里躺着一个永远启不起来的插件）
            shutil.rmtree(dest_dir, ignore_errors=True)
            return PluginResult(False, f"插件加载失败，已回滚安装：{plugin.load_error}", plugin_name)

        self.plugins[plugin.name] = plugin
        warning = "插件代码将以应用同等权限运行，可读写本地文件、发起网络请求。请确认来源可信后再启用。"
        if plugin.audit.risk_level == "high":
            warning += f" 静态体检：{plugin.audit.summary()}"
        return PluginResult(
            True,
            f"插件「{plugin.name}」安装成功，尚未启用",
            plugin.name,
            security_warning=warning,
            detail={"plugin_info": plugin.info()},
        )

    @staticmethod
    def _read_plugin_name(plugin_dir: Path) -> str:
        config_file = plugin_dir / "plugin.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f) or {}
                if config.get("name"):
                    return str(config["name"])
            except (json.JSONDecodeError, OSError):
                pass
        return plugin_dir.name

    @staticmethod
    def _find_plugin_dir(search_path: Path) -> Optional[Path]:
        """在解压目录里找到含 `plugin.json` 的那一层（兼容 GitHub 归档的多一层目录）。"""
        if (search_path / "plugin.json").exists():
            return search_path
        for sub in sorted(search_path.iterdir()):
            if sub.is_dir() and (sub / "plugin.json").exists():
                return sub
        return None

    # ---- 卸载

    def uninstall(self, name: str) -> PluginResult:
        plugin = self.plugins.get(name)
        if plugin is None:
            return PluginResult(False, f"插件不存在：{name}", name)
        # 只允许删插件根目录下的子目录 —— 防止配置被改成 `..` 后误删上层目录
        target = plugin.plugin_dir
        try:
            if not target.resolve().is_relative_to(self.plugins_dir.resolve()):
                return PluginResult(False, f"拒绝删除插件根目录之外的路径：{target}", name)
        except OSError as exc:
            return PluginResult(False, f"路径校验失败：{exc}", name)
        try:
            shutil.rmtree(target)
        except OSError as exc:
            return PluginResult(False, f"删除插件目录失败：{exc}", name)
        self.plugins.pop(name, None)
        self._enabled_names.discard(name)
        self._save_state()
        return PluginResult(True, f"已卸载「{name}」", name)


# ====================================================================== 全局单例


_manager: Optional[PluginManager] = None


def get_plugin_manager() -> Optional[PluginManager]:
    """取全局插件管理器（**懒建**，构造失败返回 None 而不是抛错）。

    为什么懒建 + 容错：插件目录可能因为权限、磁盘异常而不可用，
    而它只是**增强功能**，不该因此让整个创作工坊起不来。
    返回 None 时调用方（`writing_skills` / 面板）按"没有插件"处理。
    """
    global _manager
    if _manager is None:
        try:
            _manager = PluginManager()
        except Exception as exc:  # noqa: BLE001 - 插件不可用不该阻断启动
            logger.error(f"[插件] 初始化失败，插件功能本次不可用：{type(exc).__name__}: {exc}")
            return None
    return _manager


def reset_plugin_manager() -> None:
    """清空全局单例（**仅供测试**：让每个用例用独立的目录与状态文件）。"""
    global _manager
    _manager = None
