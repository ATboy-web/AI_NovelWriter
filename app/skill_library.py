"""技能库（Skill Library）—— 把外部 `SKILL.md` 技能包变成**结构化、可检索、可注入**的写作能力。

## 为什么需要它

`SKILL.md` 是 agent 技能的事实标准（YAML frontmatter + Markdown 正文 + `scripts/` 脚本）。
但一个 Markdown 文件对人可读、对程序**不可算**：程序既不知道"这套技能能干什么"，
也不知道"它有哪几条规则、哪些是永不改的禁区、该传什么参数"。

本模块做的是**解析与登记**，不是执行：

| 做 | 不做 |
|---|---|
| 读 frontmatter、切分规则、抽调用参数、识别场景 | **不执行**技能自带的脚本 |
| 登记 / 启停 / 检索 / 匹配 / 装配提示词 | 不沙箱化第三方代码（那是插件系统的职责） |

> 🔴 **为什么坚决不执行 `scripts/*.py`**：技能包来自网络，与主程序同等权限。
> `plugin_system.audit_plugin()` 的结论已经写明"同等权限的 Python 不能沙箱化"，
> 所以本模块只把它当**数据**读。需要跑脚本时，由用户自己在本机终端执行。

## 三层结构（沿用本仓的既有形态）

1. **注册表**：`RULE_LEVELS` / `SECTION_KINDS` —— 新增一种规则分级只改这里一处。
2. **纯解析函数**：`parse_frontmatter` / `extract_sections` / `extract_rules` /
   `extract_params` / `extract_triggers` —— 全部接收字符串、返回数据，可脱离文件单测。
3. **结构化结果对象**：`SkillResult`（`ok` / `message` / `as_dict()`），
   让面板能区分"成功但有警告"与"失败且原因是格式不对"。

## 解析出来的东西长什么样

```text
Skill
├── meta        name / description / version / author / license
├── scenarios   使用场景（"适用于写作完成后的成稿清理"）
├── triggers    触发词（用户说「去AI味」「加点人味」时）
├── rules       规则（含分级 A/B/C/F/H/X + 标题 + 正文 + 改法）
├── params      调用参数（从 add_argument / 命令行代码块抽取）
├── files       资源清单（script / reference / example / asset / doc）
└── warnings    解析期发现的问题（不阻断，但要在界面上说出来）
```
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from loguru import logger

from .domain.skill import ENTRY_NAMES, first_entry_name
from .storage import atomic_write_json, read_json
from .token_estimator import estimate_tokens

__all__ = [
    "LEVEL_LABELS",
    "MAX_ENTRY_BYTES",
    "RULE_LEVELS",
    "SECTION_KINDS",
    "MatchResult",
    "Skill",
    "SkillFile",
    "SkillLibrary",
    "SkillParam",
    "SkillResult",
    "SkillRule",
    "default_registry_file",
    "default_skills_dir",
    "extract_params",
    "extract_rules",
    "extract_scenarios",
    "extract_sections",
    "extract_triggers",
    "find_skill_root",
    "get_skill_library",
    "parse_frontmatter",
    "parse_skill",
    "reset_skill_library",
    "sanitize_skill_key",
]


# ====================================================================== 注册表


#: 规则分级 → 含义（与技能包的 DETECT.md 口径一致）。
#: 新增一级只改这里一处：面板的徽章、预览统计、提示词装配都会自动跟上。
RULE_LEVELS: dict[str, str] = {
    "A": "机械改",
    "B": "建议改",
    "C": "只报告",
    "F": "指纹",
    "H": "人审",
    "X": "已否决",
}

#: 未分级的规则（如「改写原则」）统一落在这里。
LEVEL_LABELS: dict[str, str] = {**RULE_LEVELS, "": "通用"}

#: 章节类型。`rule` 进提示词，`workflow` 只做展示，`meta` 不进提示词。
SECTION_KINDS: dict[str, str] = {
    "rule": "规则",
    "workflow": "流程",
    "meta": "说明",
}

#: 单个技能入口文件的大小上限。技能包是**文本**，超过这个量级基本可以确定
#: 不是 `SKILL.md`（曾见把整本 PDF 转成 md 塞进 frontmatter 的写法）。
MAX_ENTRY_BYTES = 2 * 1024 * 1024

#: 扫描技能目录时最多记录多少个文件（防"技能包里塞了一个 node_modules"）。
MAX_SKILL_FILES = 500

#: 入口文件候选名（大小写敏感的文件系统上都要能找到）。
_ENTRY_NAMES = ENTRY_NAMES  # 顺序定义在 domain.skill，三处调用共用同一份

#: 需要跳过的目录（不属于技能内容，且体量可能极大）。
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode"}

_FRONTMATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(?P<meta>.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)

_HEADING_RE = re.compile(r"^(?P<hashes>#{2,4})[ \t]+(?P<title>.+?)[ \t]*$", re.M)

#: 规则标题：`1. 翻案腔` / `第 3 条` / 或明确含"规则/清单/原则/人审/验收/指纹/不改"。
_RULE_TITLE_RE = re.compile(
    r"^(?:\d+[.、]\s*|第\s*[0-9一二三四五六七八九十]+\s*[条步])"
    r"|规则|原则|清单|人审|验收|指纹|不改|永不改|禁区"
)

#: 带编号的规则（`1. 翻案腔`）。只有这类才按 A/B 推断分级 ——
#: 「改写原则」「不改的情况」这类结构性章节不是单条可执行规则，
#: 硬给 A/B 会让统计看起来"有 12 条建议改"，实际用户要改的是那 13 条编号规则。
_NUMBERED_TITLE_RE = re.compile(r"^\d+[.、]\s*")

#: 流程标题：`第一步：脚本检测` / `第 1.5 步：语义层判读`
_STEP_TITLE_RE = re.compile(r"^第\s*[0-9.一二三四五六七八九十]+\s*步")

#: 分级关键词 → 级别。**顺序即优先级**（先判 X，再判 H，最后 F）。
#: 判据只看标题，不猜正文 —— 猜正文会把"这条规则说明了为什么另一些特征永不改"
#: 误判成规则本身也是 X 级。
_LEVEL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("X", ("X 级", "永不改", "已否决", "防误改")),
    ("H", ("人审", "不碰")),
    ("F", ("指纹",)),
)

#: A 级的判据：改动不触碰语义的机械替换。命中这些词说明规则本身是"删掉/换成"。
_MECHANICAL_HINTS = ("删掉", "删除", "直接写", "换成", "去掉", "只换标点")

#: 不允许出现在技能 key 里的字符（key 会当目录名用）。
_KEY_BAD_CHARS = re.compile(r"[^\w\u4e00-\u9fff.\-]+")

_PARAM_RE = re.compile(
    r"add_argument\(\s*[rRuUbB]?[\"'](?P<flag>--?[\w-]+)[\"'](?P<rest>[^)]*)",
    re.S,
)
_DEFAULT_RE = re.compile(r"default\s*=\s*([^,\)]+)")
_HELP_RE = re.compile(r"help\s*=\s*[rRuUbB]?[\"'](?P<help>[^\"']*)[\"']")
_STORE_TRUE_RE = re.compile(r"action\s*=\s*[\"']store_true[\"']")
_FLAG_IN_TEXT_RE = re.compile(r"(?<![\w-])(--[a-z][\w-]*)")

_TRIGGER_RE = re.compile(r"「([^」\n]{1,30})」")

#: 场景句判据：技能包的 description 里通常写「适用于…」「用户说…时也用这个技能」。
_SCENARIO_HINTS = ("适用于", "用于", "场景", "时也用", "触发", "适合")


# ====================================================================== 数据模型


@dataclass(frozen=True)
class SkillParam:
    """技能脚本的一个调用参数（从代码里抽出来的，不是猜的）。"""

    flag: str
    help: str = ""
    default: str = ""
    takes_value: bool = True
    source: str = "script"  # script = add_argument 抽取；docs = 代码块里出现

    def as_dict(self) -> dict[str, Any]:
        return {
            "flag": self.flag,
            "help": self.help,
            "default": self.default,
            "takes_value": self.takes_value,
            "source": self.source,
        }

    def signature(self) -> str:
        """`--max-hits <值>` / `--json` 这种人读形式。"""
        return f"{self.flag} <值>" if self.takes_value else self.flag


@dataclass
class SkillFile:
    """技能包内的一个文件（只记录元数据，**不读二进制内容**）。"""

    path: str
    role: str
    size: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "role": self.role, "size": self.size}


@dataclass
class SkillRule:
    """一条可执行的规则。

    `level` 决定它是否进提示词：`X`（已否决）/`H`（人审）**永不注入** ——
    这不是过滤得严，而是技能包本身写明了"永不改、防误改"，
    把 X 级规则注入提示词等于让模型去做规则明令禁止的事。
    """

    level: str
    title: str
    body: str
    order: int = 0
    kind: str = "rule"
    level_source: str = "heuristic"  # explicit = 标题写明；heuristic = 依关键词推断

    # ------------------------------------------------------------------ 派生

    @property
    def level_label(self) -> str:
        return LEVEL_LABELS.get(self.level, "通用")

    @property
    def injectable(self) -> bool:
        """是否允许进入写作提示词。"""
        return self.level not in ("X", "H")

    def revision(self) -> str:
        """抽出"改法"部分：优先含「改法」的段落，其次编号条目，否则正文首段。"""
        blocks = [b.strip() for b in re.split(r"\n\s*\n", self.body) if b.strip()]
        for text in blocks:
            if "改法" in text or "改写方向" in text:
                return _one_line(text)
        # 「改写原则」这类章节每条原则自成一段，取首条比取整章前言有用
        for text in blocks:
            if re.match(r"^\*\*\d+[.、]", text):
                return _one_line(text)
        return _one_line(blocks[0]) if blocks else ""

    def items(self) -> list[str]:
        """把表格首列 / 列表项抽成条目名。

        为什么需要它：`## X 级清单` 的价值在**条目**（序数词小标题、「这意味着」复述…），
        而 `body` 首行是表头。直接把整张表注进提示词既超长又没重点。
        """
        found: list[str] = []
        for raw in self.body.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if not cells:
                    continue
                first = cells[0]
                if not first or set(first) <= {"-", ":", " "}:
                    continue
                if first in ("特征", "规则", "项目", "条目"):
                    continue
                first = first.replace("**", "").strip()
                if first and first not in found:
                    found.append(first)
                continue
            match = re.match(r"^(?:[-*]|\d+[.、])\s+(.+)$", line)
            if match:
                text = match.group(1).replace("**", "").strip()
                # `**比喻贴切度**：说明…` → 只取冒号前的条目名
                head = re.split(r"[：:]", text, maxsplit=1)[0].strip()
                if head and len(head) <= 24 and head not in found:
                    found.append(head)
        return found

    def summary(self, limit: int = 140) -> str:
        text = self.revision()
        if len(text) > limit:
            text = text[: limit - 1].rstrip() + "…"
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "level_label": self.level_label,
            "title": self.title,
            "body": self.body,
            "order": self.order,
            "kind": self.kind,
            "level_source": self.level_source,
            "injectable": self.injectable,
            "summary": self.summary(),
        }


@dataclass
class SkillResult:
    """一次技能操作的结果（与 `PluginResult` 同形，便于面板统一处理）。"""

    ok: bool
    message: str
    skill_key: str = ""
    security_warning: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "skill_key": self.skill_key,
            "security_warning": self.security_warning,
            **self.detail,
        }


@dataclass(frozen=True)
class MatchResult:
    """技能与一段文本的匹配结果（`score` 0–1，`reasons` 给出**为什么**）。"""

    key: str
    score: float
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "score": round(self.score, 3), "reasons": list(self.reasons)}


@dataclass
class Skill:
    """一个解析完成的技能。构造只由 `parse_skill()` 负责。"""

    key: str
    name: str
    description: str = ""
    version: str = ""
    author: str = ""
    license: str = ""
    root: Path = field(default_factory=Path)
    entry: Optional[Path] = None
    rules: list[SkillRule] = field(default_factory=list)
    params: list[SkillParam] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    files: list[SkillFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    enabled: bool = False
    mode: str = "copy"  # copy = 已复制进技能库；ref = 仅登记外部目录
    source: str = ""

    # ------------------------------------------------------------------ 派生

    @property
    def prompt_rules(self) -> list[SkillRule]:
        """可注入的规则（X / H 级已被排除）。"""
        return [r for r in self.rules if r.injectable]

    def rules_by_level(self) -> dict[str, list[SkillRule]]:
        """按级别分组，供面板统计与预览。顺序跟随 `RULE_LEVELS`，保证稳定。"""
        grouped: dict[str, list[SkillRule]] = {level: [] for level in RULE_LEVELS}
        grouped[""] = []
        for rule in self.rules:
            grouped.setdefault(rule.level, []).append(rule)
        return grouped

    def level_stats(self) -> dict[str, int]:
        """`{"A": 3, "B": 2, "X": 1}`；只返回非零项，便于直接展示。"""
        stats: dict[str, int] = {}
        for rule in self.rules:
            stats[rule.level] = stats.get(rule.level, 0) + 1
        return stats

    def file_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        for item in self.files:
            stats[item.role] = stats.get(item.role, 0) + 1
        return stats

    def one_line(self, limit: int = 160) -> str:
        text = " ".join(self.description.split())
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    # ------------------------------------------------------------------ 提示词

    def to_prompt(self, max_chars: int = 800) -> str:
        """装配可直接注入写作提示词的一段文本。

        **按规则边界截断**，绝不切在句子中间：截半条规则比少一条更糟 ——
        模型会按半句话去改稿。截断时明确写出"另有 N 条未注入"，
        让用户知道提示词不是全量（否则会出现"启用了却没生效"的错觉）。
        """
        if max_chars <= 0:
            return ""
        # 预算极小时先砍"用途"：它是最长、最不影响执行的一段。
        compact = max_chars < 320
        lines: list[str] = [f"【技能：{self.name}】"]
        if self.description and not compact:
            lines.append(f"用途：{self.one_line(120)}")

        injectable = self.prompt_rules
        if not injectable:
            lines.append("（该技能没有可注入的规则）")
            return "\n".join(lines)

        # X / H 级不进正文，但**要明确告诉模型"不许做"** —— 这部分恰恰是防误改的关键。
        forbidden = [r for r in self.rules if r.level == "X"]
        if forbidden:
            names: list[str] = []
            for rule in forbidden:
                names.extend(rule.items() or [rule.title])
            if names:
                keep = 3 if compact else 8
                lines.append(f"禁止改动（已否决特征，实测不是 AI 味）：{'、'.join(names[:keep])}")

        used = len("\n".join(lines))
        # 预留尾部"另有 N 条未注入"的说明空间：不留会稳定超预算十几个字，
        # 而调用方是按上限切预算的（超了就会被上一层的 _compress_text 截断，
        # 反而把最后一条规则切成半句）。
        limit = max_chars - 56
        emitted = 0
        for rule in injectable:
            prefix = f"- [{rule.level or '通用'}] " if rule.level else "- "
            block = f"{prefix}{rule.title}：{rule.summary(120)}"
            if used + len(block) + 1 > limit:
                break
            lines.append(block)
            used += len(block) + 1
            emitted += 1
        pending = len(injectable) - emitted
        if pending:
            lines.append(f"（另有 {pending} 条规则因长度限制未注入，改稿时请一并遵循原技能文档）")
        text = "\n".join(lines)
        if len(text) > max_chars:
            # 极小预算（标题+禁止项已超）时只能硬截：**保证调用方的预算契约成立**。
            # 常规预算下不会走到这里 —— 上面按规则边界截断已足够。
            text = text[: max(0, max_chars - 1)].rstrip() + "…"
        return text

    def preview(self, max_chars: int = 800) -> dict[str, Any]:
        """效果预览：注入文本 + 分级统计 + 作者自带的 ❌/✅ 对照。"""
        prompt = self.to_prompt(max_chars=max_chars)
        return {
            "key": self.key,
            "name": self.name,
            "prompt": prompt,
            "chars": len(prompt),
            "tokens": estimate_tokens(prompt),
            "rules_total": len(self.rules),
            "rules_injected": sum(1 for r in self.prompt_rules if r.injectable),
            "level_stats": self.level_stats(),
            "examples": [{"before": b, "after": a} for b, a in self.examples()][:6],
        }

    def examples(self) -> list[tuple[str, str]]:
        """从规则正文里抽作者自带的 `❌ … / ✅ …` 对照（**效果预览**的素材）。

        只做行级提取，不做推断：技能包没写对照就返回空，不用模型"编一个更好的例子"。
        """
        pairs: list[tuple[str, str]] = []
        for rule in self.rules:
            before = ""
            for raw in rule.body.splitlines():
                line = raw.strip()
                if line.startswith(">"):
                    line = line.lstrip("> ").strip()
                if line.startswith("❌"):
                    before = line.lstrip("❌ ").strip()
                elif line.startswith("✅") and before:
                    pairs.append((before, line.lstrip("✅ ").strip()))
                    before = ""
        return pairs

    # ------------------------------------------------------------------ 序列化

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "root": str(self.root),
            "entry": str(self.entry) if self.entry else "",
            "enabled": self.enabled,
            "mode": self.mode,
            "source": self.source,
            "scenarios": list(self.scenarios),
            "triggers": list(self.triggers),
            "rules": [r.as_dict() for r in self.rules],
            "params": [p.as_dict() for p in self.params],
            "files": [f.as_dict() for f in self.files],
            "warnings": list(self.warnings),
            "level_stats": self.level_stats(),
            "file_stats": self.file_stats(),
        }


# ====================================================================== 纯解析


def _one_line(text: str) -> str:
    """把多行压成一行：去掉引用符号与多余空白。"""
    parts: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        line = line.replace("**", "")
        parts.append(line)
    return " ".join(parts)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    """拆分 YAML frontmatter 与正文，返回 `(meta, body, warnings)`。

    ❗ **不 import yaml**：`pyyaml` 不在 `pyproject.toml` 的依赖里，
    PyInstaller 也不会自动带上。技能包的 frontmatter 只有两种写法
    （`key: value` 与 `key: >` / `key: |` 折叠块），自己解析 40 行就够，
    比多一个"打包后 ImportError 静默丢功能"的风险划算。
    """
    warnings: list[str] = []
    if not text:
        return {}, "", ["内容为空"]

    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, ["未找到 YAML frontmatter（--- 包裹的头部）"]

    raw_meta = match.group("meta")
    body = text[match.end() :]
    meta: dict[str, str] = {}
    key = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal key, buffer
        if key:
            value = "\n".join(buffer).strip() if buffer else ""
            meta[key] = value
        key, buffer = "", []

    for line in raw_meta.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # 折叠块 / 字面块：`description: >` 之后是缩进内容
        if key and (line.startswith((" ", "\t")) or not line.strip()):
            buffer.append(line.strip())
            continue
        if ":" not in line:
            warnings.append(f"frontmatter 行无法解析：{line[:60]}")
            continue
        trimmed = line.strip()
        if key:
            flush()
        name, _, value = trimmed.partition(":")
        key = name.strip().lower()
        value = value.strip()
        if value in (">", "|", ">-", "|-"):
            buffer = []
        else:
            buffer = [value]
            flush()
    if key:
        flush()

    # 去引号 + 简单内联列表
    cleaned: dict[str, str] = {}
    for name, value in meta.items():
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        cleaned[name] = value.strip()
    return cleaned, body.lstrip("\n"), warnings


def extract_sections(text: str) -> list[dict[str, Any]]:
    """按 `##` / `###` / `####` 切分章节，返回 `[{level,title,body,line}]`。

    只切到 4 级：再深的标题通常是规则内部的强调，切成章节会把规则切碎。
    """
    matches = list(_HEADING_RE.finditer(text))
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        level = len(match.group("hashes"))
        title = match.group("title").strip()
        sections.append(
            {
                "level": level,
                "title": title,
                "body": text[start:end].strip("\n"),
                "line": text[: match.start()].count("\n") + 1,
            }
        )
    return sections


def classify_section(title: str, level: int) -> str:
    """章节类型判定：`rule` / `workflow` / `meta`。"""
    if _STEP_TITLE_RE.search(title):
        return "workflow"
    if _RULE_TITLE_RE.search(title):
        return "rule"
    # `## 改写规则（按优先级排序）` 这类父标题本身也是规则容器
    if level == 2 and ("改写" in title or "去 AI" in title):
        return "rule"
    return "meta"


def classify_level(title: str, body: str) -> tuple[str, str]:
    """推断规则分级，返回 `(level, level_source)`。

    优先级：标题明确的 > 编号规则的机械替换特征 > 结构章节记为通用。
    `level_source` 会写进结构化数据，界面据此标注"推断"而不是伪装成原文标注。
    """
    for level, keywords in _LEVEL_KEYWORDS:
        if any(word in title for word in keywords):
            return level, "explicit"
    if not _NUMBERED_TITLE_RE.match(title):
        # 「改写原则」「不改的情况」「最终验收」这类是**结构性章节**，
        # 不是单条可执行规则；给它们 A/B 会让分级统计虚高。
        return "", "default"
    head = body[:600]
    if any(word in head for word in _MECHANICAL_HINTS):
        return "A", "heuristic"
    return "B", "heuristic"


def _is_container(title: str, level: int, body: str) -> bool:
    """识别"小标题式容器"——只说明下面有规则，本身不含可执行内容。

    例：`## 改写规则（按优先级排序）` 的正文只有一句"数字来自两轮实测"。
    把它当规则注入提示词，模型会收到一句没有约束力的旁白。
    """
    if level not in (2, 3) or _NUMBERED_TITLE_RE.match(title):
        return False
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    has_list = any(ln.startswith(("- ", "* ", "|", "1.", "2.")) or ln[:2].isdigit() for ln in lines)
    return len(lines) < 3 and not has_list


def extract_rules(text: str) -> tuple[list[SkillRule], list[dict[str, Any]]]:
    """抽取规则与流程章节，返回 `(rules, workflows)`。"""
    rules: list[SkillRule] = []
    workflows: list[dict[str, Any]] = []
    order = 0
    for section in extract_sections(text):
        kind = classify_section(section["title"], section["level"])
        if kind == "workflow":
            workflows.append(section)
            continue
        if kind != "rule":
            continue
        if _is_container(section["title"], section["level"], section["body"]):
            continue
        level, source = classify_level(section["title"], section["body"])
        order += 1
        rules.append(
            SkillRule(
                level=level,
                title=section["title"],
                body=section["body"],
                order=order,
                kind=kind,
                level_source=source,
            )
        )
    return rules, workflows


def extract_triggers(description: str) -> list[str]:
    """抽触发词：`用户说「去AI味」「加点人味」时也用这个技能` → 两个词。

    只收**含「」且在 description 里**的短语：技能包的触发约定就是这一种写法，
    从正文里乱抓引号会把示例也当成触发词。
    """
    if not description:
        return []
    triggers: list[str] = []
    for match in _TRIGGER_RE.finditer(description):
        word = match.group(1).strip()
        if word and word not in triggers:
            triggers.append(word)
    return triggers


def extract_scenarios(description: str, sections: Iterable[dict[str, Any]] = ()) -> list[str]:
    """抽使用场景：description 里带「适用于/用于/场景」的句子 + 场景类章节标题。"""
    scenarios: list[str] = []
    if description:
        # 中英文句号、分号都可能断句；保留句子本身的完整语义
        for sentence in re.split(r"[。；;\n]", description):
            text = sentence.strip()
            if text and any(hint in text for hint in _SCENARIO_HINTS):
                if text not in scenarios:
                    scenarios.append(text)
    for section in sections:
        title = str(section.get("title", ""))
        if any(hint in title for hint in ("适用", "场景", "触发", "何时使用")):
            if title not in scenarios:
                scenarios.append(title)
    return scenarios


def extract_params(text: str) -> list[SkillParam]:
    """抽调用参数。两个来源：

    1. `scripts/*.py` 里的 `ap.add_argument("--flag", help=..., default=...)` —— 权威；
    2. Markdown 代码块里出现的 `--flag` —— 补充（技能包常只在文档里写命令）。

    同一 flag 以脚本来源为准，文档来源只补缺，避免"文档写错了却覆盖代码"。
    """
    params: dict[str, SkillParam] = {}

    for match in _PARAM_RE.finditer(text):
        flag = match.group("flag")
        rest = match.group("rest")
        help_text = ""
        help_match = _HELP_RE.search(rest)
        if help_match:
            help_text = help_match.group("help").strip()
        default = ""
        default_match = _DEFAULT_RE.search(rest)
        if default_match:
            default = default_match.group(1).strip().strip("\"'")
        takes_value = not _STORE_TRUE_RE.search(rest)
        params[flag] = SkillParam(
            flag=flag,
            help=help_text,
            default=default,
            takes_value=takes_value,
            source="script",
        )

    for flag in _FLAG_IN_TEXT_RE.findall(text):
        if flag in params:
            continue
        params[flag] = SkillParam(flag=flag, source="docs")
    return list(params.values())


def find_skill_root(path: Path) -> Optional[Path]:
    """在一个目录里定位技能根（含 `SKILL.md` 的那一层）。

    支持三种常见压缩包布局：
    - `zip → SKILL.md`（根就是技能）
    - `zip → demo-skill/SKILL.md`
    - `zip → 外层包装/demo-skill/SKILL.md`（最多下探 3 层）
    """
    path = Path(path)
    if not path.is_dir():
        return None
    for name in _ENTRY_NAMES:
        if (path / name).is_file():
            return path
    # 广度优先下探，避免"压缩包多包了一层"直接判失败
    queue: list[tuple[Path, int]] = [(path, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth >= 3:
            continue
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if child.name in _SKIP_DIRS:
                continue
            for name in _ENTRY_NAMES:
                if (child / name).is_file():
                    return child
            queue.append((child, depth + 1))
    return None


def sanitize_skill_key(name: str) -> Optional[str]:
    """把技能名变成安全的目录名；非法时返回 `None`。

    允许中文：技能名是给人看的，而中文**不构成路径风险**（风险字符只有
    `/` `\\` `:` `..`），这与 `plugin_system.sanitize_plugin_name` 的判据一致。
    """
    if not name:
        return None
    key = name.strip().replace(" ", "-")
    key = _KEY_BAD_CHARS.sub("-", key).strip("-.")
    if not key or key in (".", ".."):
        return None
    if len(key) > 64:
        key = key[:64].rstrip("-.")
    return key or None


def _classify_file(rel: Path, size: int) -> SkillFile:
    """按所在目录判定资源角色（不读内容，只看路径与大小）。"""
    parts = [p.lower() for p in rel.parts]
    if not parts:
        return SkillFile(path=rel.as_posix(), role="other", size=size)
    head = parts[0]
    if head in ("scripts", "script", "bin"):
        role = "script"
    elif head in ("references", "reference", "docs"):
        role = "reference"
    elif head in ("examples", "example", "samples"):
        role = "example"
    elif head in ("assets", "images", "img"):
        role = "asset"
    elif len(parts) == 1 and rel.suffix.lower() in (".md", ".txt"):
        role = "doc"
    else:
        role = "other"
    return SkillFile(path=rel.as_posix(), role=role, size=size)


def _scan_files(root: Path, warnings: list[str]) -> list[SkillFile]:
    files: list[SkillFile] = []
    for current, _dirnames, filenames in _walk(root):
        for filename in filenames:
            full = current / filename
            try:
                size = full.stat().st_size
            except OSError:
                continue
            files.append(_classify_file(full.relative_to(root), size))
            if len(files) >= MAX_SKILL_FILES:
                warnings.append(f"文件数超过 {MAX_SKILL_FILES}，后续未记录")
                return files
    return files


def _walk(root: Path):
    """遍历目录，**在生成器内部**过滤黑名单目录。

    ❗ 过滤必须写在这里：曾经写在使用方（`dirnames[:] = [...]`），
    但 `_walk` 在 yield 之前就已经把子目录压进栈了 —— 使用方改的是一份
    "已经用过的副本"，过滤**完全无效**，于是 `__pycache__` / `node_modules`
    照样被遍历，文件清单与统计被污染。
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        dirnames = [p for p in entries if p.is_dir() and p.name not in _SKIP_DIRS]
        filenames = [p.name for p in entries if p.is_file()]
        yield current, dirnames, filenames
        stack.extend(reversed(dirnames))


# ====================================================================== 解析入口


def parse_skill(root: Path, warnings: Optional[list[str]] = None) -> Skill:
    """把一个技能目录解析成 `Skill`。

    **永不抛异常**：坏技能应该变成"界面上一条带原因的空技能"，
    而不是让整个技能库加载失败（一个坏包不该拖垮其它技能）。
    """
    root = Path(root)
    collected: list[str] = list(warnings or [])
    result = Skill(key="", name=root.name, root=root)

    picked = first_entry_name(_ENTRY_NAMES, lambda n: (root / n).is_file())
    entry: Optional[Path] = (root / picked) if picked else None
    if entry is None:
        result.warnings = collected + ["未找到 SKILL.md"]
        return result

    try:
        size = entry.stat().st_size
        if size > MAX_ENTRY_BYTES:
            result.warnings = collected + [f"SKILL.md 过大（{size} 字节），拒绝解析"]
            return result
        text = entry.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.warnings = collected + [f"读取 SKILL.md 失败：{exc}"]
        return result

    meta, body, warnings = parse_frontmatter(text)
    collected.extend(warnings)

    name = meta.get("name") or meta.get("title") or root.name
    result.entry = entry
    result.name = name
    result.description = meta.get("description", "")
    result.version = meta.get("version", "")
    result.author = meta.get("author", "")
    result.license = meta.get("license", "")
    if not result.license and (root / "LICENSE").is_file():
        # 许多技能包把授权写在 LICENSE 文件而不是 frontmatter；这里只**指出存在**，
        # 不解析授权条款（解析错的授权信息比没有更危险）。
        result.license = "见 LICENSE 文件"
    result.key = sanitize_skill_key(name) or sanitize_skill_key(root.name) or root.name
    if not meta:
        collected.append("frontmatter 为空，名称与说明将退化为目录名")

    rules, workflows = extract_rules(body)
    result.rules = rules
    result.scenarios = extract_scenarios(result.description, workflows)
    result.triggers = extract_triggers(result.description)

    # 参数：脚本优先，文档补缺
    script_text = ""
    for current, _dirnames, filenames in _walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            try:
                script_text += "\n" + (current / filename).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    result.params = extract_params((script_text or "") + "\n" + body)

    result.files = _scan_files(root, collected)

    if not rules:
        collected.append("未解析出任何规则（正文可能没有 Markdown 标题）")
    if not result.description:
        collected.append("frontmatter 缺少 description，自动匹配与检索会退化")

    result.warnings = collected
    return result


# ====================================================================== 匹配


def _match_terms(skill: Skill) -> list[tuple[str, float]]:
    """匹配词表：`(词, 权重)`。触发词权重最高（它们是作者明写的入口）。"""
    terms: list[tuple[str, float]] = []
    for word in skill.triggers:
        terms.append((word, 3.0))
    for scenario in skill.scenarios:
        # 场景里太长的句子不适合做包含匹配，抽关键词
        for token in re.split(r"[，,、（）()：:。；;]", scenario):
            token = token.strip()
            if 2 <= len(token) <= 12:
                terms.append((token, 1.5))
    for rule in skill.rules:
        title = re.sub(r"^[\d.、\s]+", "", rule.title)
        if 2 <= len(title) <= 12:
            terms.append((title, 1.0))
    # 去重，保留最高权重
    best: dict[str, float] = {}
    for word, weight in terms:
        if word and weight > best.get(word, 0):
            best[word] = weight
    return list(best.items())


def match_skill(skill: Skill, text: str) -> MatchResult:
    """计算技能与一段文本的相关度（0–1），并给出命中理由。

    刻意做成**可解释的加权命中率**而不是黑盒模型：
    面板要显示"为什么推荐它"，用户才敢点"一键应用"。
    """
    terms = _match_terms(skill)
    if not terms or not text:
        return MatchResult(key=skill.key, score=0.0)
    total = sum(weight for _word, weight in terms) or 1.0
    hits: list[str] = []
    score = 0.0
    for word, weight in terms:
        if word in text:
            score += weight
            hits.append(word)
    # 归一化后再开方：命中少数几个强触发词就应给高分，
    # 线性归一会被"规则标题很多"的技能稀释。
    normalized = min(1.0, (score / total) ** 0.5)
    return MatchResult(key=skill.key, score=normalized, reasons=tuple(hits[:8]))


# ====================================================================== 管理器


def default_skills_dir() -> Path:
    """技能库目录（**唯一来源**，别在别处再拼一次）。"""
    return Path.home() / ".ai_novel_writer" / "skills"


def default_registry_file() -> Path:
    """技能登记与启用状态（**唯一来源**）。"""
    return Path.home() / ".ai_novel_writer" / "skills.json"


class SkillLibrary:
    """技能库：扫描 / 导入 / 登记 / 启停 / 检索 / 匹配 / 装配提示词。

    状态文件与技能目录分离：技能目录只放**内容**，`skills.json` 只放**元状态**。
    这样"删掉状态文件"不会丢技能，"删掉技能目录"也不会留下幽灵条目。
    """

    def __init__(self, skills_dir: Optional[Path] = None, registry_file: Optional[Path] = None) -> None:
        self.skills_dir = Path(skills_dir) if skills_dir else default_skills_dir()
        self.registry_file = Path(registry_file) if registry_file else default_registry_file()
        self._skills: dict[str, Skill] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self.load_failures: list[tuple[str, str]] = []
        self._loaded = False

    # ------------------------------------------------------------------ 状态

    def _read_state(self) -> dict[str, dict[str, Any]]:
        try:
            raw = read_json(self.registry_file)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug(f"[技能库] 状态文件损坏，按空状态处理：{exc}")
            return {}
        if not isinstance(raw, dict):
            return {}
        skills = raw.get("skills", raw)
        if not isinstance(skills, dict):
            return {}
        return {str(k): v for k, v in skills.items() if isinstance(v, dict)}

    def _write_state(self) -> None:
        payload = {"schema": 1, "skills": self._state}
        atomic_write_json(self.registry_file, payload, backup=True)
        # 状态变了 ⇒ 缓存里的 enabled/mode/source 也要跟着变，否则面板显示旧值
        for key, info in self._state.items():
            skill = self._skills.get(key)
            if skill is not None:
                skill.enabled = bool(info.get("enabled"))
                skill.mode = str(info.get("mode", "copy"))
                skill.source = str(info.get("source", ""))

    # ------------------------------------------------------------------ 扫描

    def reload(self) -> list[Skill]:
        """重新扫描技能目录 + 登记过的外部目录。"""
        self._state = self._read_state()
        found: dict[str, Skill] = {}
        self.load_failures = []

        roots: list[tuple[Path, str]] = []
        if self.skills_dir.is_dir():
            for child in sorted(self.skills_dir.iterdir()):
                if child.is_dir() and child.name not in _SKIP_DIRS:
                    roots.append((child, "copy"))
        for key, info in self._state.items():
            if str(info.get("mode")) != "ref":
                continue
            source = Path(str(info.get("source", "")))
            if source.is_dir():
                roots.append((source, "ref"))
            else:
                self.load_failures.append((key, f"登记路径已不存在：{source}"))

        for path, mode in roots:
            try:
                skill = parse_skill(path)
            except Exception as exc:  # noqa: BLE001 - 一个坏包不该拖垮整库
                self.load_failures.append((path.name, f"解析异常：{exc}"))
                continue
            if not skill.entry:
                self.load_failures.append((path.name, "；".join(skill.warnings) or "未找到 SKILL.md"))
                continue
            key = skill.key
            if key in found:
                # 同一 key 在库内与登记目录都存在时，**库内副本优先**（用户显式导入的）
                if mode == "ref":
                    continue
                self.load_failures.append((path.name, f"key 与已有技能重复：{key}，已跳过"))
                continue
            info = self._state.get(key, {})
            skill.enabled = bool(info.get("enabled", False))
            skill.mode = mode
            skill.source = str(info.get("source", "")) or str(path)
            found[key] = skill

        self._skills = found
        self._loaded = True
        return list(found.values())

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    # ------------------------------------------------------------------ 查询

    def get(self, key: str) -> Optional[Skill]:
        self._ensure_loaded()
        return self._skills.get(key)

    def all_skills(self) -> list[Skill]:
        self._ensure_loaded()
        return sorted(self._skills.values(), key=lambda s: s.key)

    def enabled_skills(self) -> list[Skill]:
        return [s for s in self.all_skills() if s.enabled]

    def list_skills(self) -> list[dict[str, Any]]:
        """面板用的扁平结构（与 `PluginManager.list_plugins()` 同形）。"""
        return [s.as_dict() for s in self.all_skills()]

    def search(self, query: str) -> list[Skill]:
        """全文检索：名称 / 说明 / 场景 / 触发词 / 规则标题与正文。

        全部小写比较：技能名多为英文 slug，用户不会记得大小写。
        """
        text = (query or "").strip().lower()
        if not text:
            return self.all_skills()
        hits: list[Skill] = []
        for skill in self.all_skills():
            haystack = " ".join(
                [
                    skill.key,
                    skill.name,
                    skill.description,
                    " ".join(skill.scenarios),
                    " ".join(skill.triggers),
                    " ".join(r.title + " " + r.body for r in skill.rules),
                ]
            ).lower()
            if text in haystack:
                hits.append(skill)
        return hits

    def match(self, text: str, limit: int = 3, threshold: float = 0.15) -> list[MatchResult]:
        """按一段文本给技能排序（**技能自动匹配**）。"""
        results = [match_skill(skill, text) for skill in self.all_skills()]
        ranked = sorted(
            (r for r in results if r.score >= threshold),
            key=lambda r: (-r.score, r.key),
        )
        return ranked[: max(1, limit)]

    # ------------------------------------------------------------------ 启停

    def set_enabled(self, key: str, enabled: bool) -> SkillResult:
        skill = self.get(key)
        if skill is None:
            return SkillResult(ok=False, message=f"技能不存在：{key}", skill_key=key)
        info = self._state.setdefault(key, {})
        info["enabled"] = bool(enabled)
        info.setdefault("mode", skill.mode)
        info.setdefault("source", skill.source or str(skill.root))
        info.setdefault("installed_at", _now())
        try:
            self._write_state()
        except OSError as exc:
            return SkillResult(ok=False, message=f"保存状态失败：{exc}", skill_key=key)
        action = "已启用" if enabled else "已停用"
        return SkillResult(
            ok=True,
            message=f"{action}「{skill.name}」" + ("，下次生成立即生效" if enabled else ""),
            skill_key=key,
        )

    def enable(self, key: str) -> SkillResult:
        return self.set_enabled(key, True)

    def disable(self, key: str) -> SkillResult:
        return self.set_enabled(key, False)

    # ------------------------------------------------------------------ 导入

    def install(self, source: str) -> SkillResult:
        """导入技能：本地目录或 ZIP。

        **先解析、后落盘**：解析不出 SKILL.md 就立刻失败，避免在技能库里
        留下一堆"看着装了、其实空的"目录。
        """
        raw = (source or "").strip().strip('"')
        if not raw:
            return SkillResult(ok=False, message="来源为空")
        self._ensure_loaded()  # 未加载时去重会失效（`_skills` 为空 ⇒ 允许重名）
        path = Path(raw).expanduser()
        if not path.exists():
            return SkillResult(ok=False, message=f"路径不存在：{path}")

        if path.is_dir():
            return self._install_from_dir(path)

        if path.is_file() and zipfile.is_zipfile(path):
            return self._install_from_zip(path)

        return SkillResult(ok=False, message=f"不支持的来源（需要目录或 ZIP）：{path}")

    def _install_from_dir(self, source_dir: Path) -> SkillResult:
        root = find_skill_root(source_dir)
        if root is None:
            return SkillResult(ok=False, message=f"目录里找不到 SKILL.md：{source_dir}")
        skill = parse_skill(root)
        if not skill.entry:
            return SkillResult(ok=False, message="；".join(skill.warnings) or "无法解析技能")
        key = skill.key
        target = self.skills_dir / key
        if target.exists():
            return SkillResult(
                ok=False,
                message=f"技能库里已有同名技能「{key}」，请先卸载或改名",
                skill_key=key,
            )
        try:
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, target)
        except OSError as exc:
            return SkillResult(ok=False, message=f"复制技能失败：{exc}", skill_key=key)
        self._state[key] = {
            "enabled": False,
            "mode": "copy",
            "source": str(root),
            "installed_at": _now(),
        }
        try:
            self._write_state()
        except OSError as exc:
            return SkillResult(ok=False, message=f"已复制但保存状态失败：{exc}", skill_key=key)
        self.reload()
        warning = ""
        if any(f.role == "script" for f in skill.files):
            warning = (
                "该技能包含可执行脚本。本软件**不会执行**它们，只解析其中的规则与参数；"
                "如需运行脚本，请自行在本机终端确认后执行。"
            )
        return SkillResult(
            ok=True,
            message=f"已导入「{skill.name}」：{len(skill.rules)} 条规则 / {len(skill.files)} 个文件",
            skill_key=key,
            security_warning=warning,
        )

    def _install_from_zip(self, zip_path: Path) -> SkillResult:
        temp_dir = Path(tempfile.mkdtemp(prefix="anw_skill_"))
        try:
            # 复用插件系统的安全解压（防 Zip Slip），**不复制一份实现** ——
            # 「同一事实写两处必然漂移」在本仓已踩过 5 次。
            from .plugin_system import safe_extract

            with zipfile.ZipFile(zip_path) as archive:
                safe_extract(archive, temp_dir)
            root = find_skill_root(temp_dir)
            if root is None:
                return SkillResult(ok=False, message="压缩包里找不到 SKILL.md")
            return self._install_from_dir(root)
        except (ValueError, zipfile.BadZipFile, OSError) as exc:
            return SkillResult(ok=False, message=f"解压失败：{exc}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def register(self, source: str) -> SkillResult:
        """登记一个**外部**技能目录（不复制）。

        适合"技能仓库就在本机、想边改边看"的场景；代价是移动目录后条目失效，
        所以 `reload()` 会把失效登记记进 `load_failures` 而不是静默丢掉。
        """
        raw = (source or "").strip().strip('"')
        path = Path(raw).expanduser()
        self._ensure_loaded()  # 同上：未加载时 `key in self._skills` 恒为假
        root = find_skill_root(path) if path.is_dir() else None
        if root is None:
            return SkillResult(ok=False, message=f"目录里找不到 SKILL.md：{path}")
        skill = parse_skill(root)
        if not skill.entry:
            return SkillResult(ok=False, message="；".join(skill.warnings) or "无法解析技能")
        key = skill.key
        if key in self._skills:
            return SkillResult(ok=False, message=f"技能「{key}」已存在", skill_key=key)
        self._state[key] = {
            "enabled": False,
            "mode": "ref",
            "source": str(root.resolve()),
            "installed_at": _now(),
        }
        try:
            self._write_state()
        except OSError as exc:
            return SkillResult(ok=False, message=f"保存状态失败：{exc}", skill_key=key)
        self.reload()
        return SkillResult(
            ok=True,
            message=f"已登记「{skill.name}」（引用模式，不复制文件）",
            skill_key=key,
        )

    def uninstall(self, key: str) -> SkillResult:
        """卸载：库内副本删除目录，引用模式只删登记。

        🔴 删除前必须确认目标**真的在技能目录内**：`key` 来自状态文件，
        状态文件是可被用户手改的 —— 一个 `../../` 就能删到别处。
        """
        skill = self.get(key)
        if skill is None:
            return SkillResult(ok=False, message=f"技能不存在：{key}", skill_key=key)
        if skill.mode == "copy":
            target = (self.skills_dir / key).resolve()
            base = self.skills_dir.resolve()
            if not target.is_relative_to(base) or target == base:
                return SkillResult(ok=False, message="拒绝删除：目标不在技能目录内", skill_key=key)
            if target.exists():
                try:
                    shutil.rmtree(target)
                except OSError as exc:
                    return SkillResult(ok=False, message=f"删除失败：{exc}", skill_key=key)
        self._state.pop(key, None)
        try:
            self._write_state()
        except OSError as exc:
            return SkillResult(ok=False, message=f"已删除文件但保存状态失败：{exc}", skill_key=key)
        self.reload()
        return SkillResult(ok=True, message=f"已卸载「{skill.name}」", skill_key=key)

    # ------------------------------------------------------------------ 装配

    def prompt_context(self, budget: int = 900, text: str = "") -> str:
        """把**已启用**的技能装配成提示词段落。

        `text`（可选）：传入当前稿件时按相关度排序，让"自动匹配"在生成时
        也能起作用 —— 但仍只注入**已启用**的技能，不会偷偷替用户开技能。
        """
        skills = self.enabled_skills()
        if not skills:
            return ""
        if text:
            scores = {r.key: r.score for r in (match_skill(s, text) for s in skills)}
            skills.sort(key=lambda s: (-scores.get(s.key, 0.0), s.key))
        blocks: list[str] = []
        remaining = budget
        for skill in skills:
            if remaining <= 80:  # 少于一行规则的空间，不再硬塞
                break
            block = skill.to_prompt(max_chars=remaining)
            if not block:
                continue
            blocks.append(block)
            remaining -= len(block) + 2
        return "\n\n".join(blocks)

    def preview(self, key: str, budget: int = 900) -> dict[str, Any]:
        skill = self.get(key)
        if skill is None:
            return {"ok": False, "message": f"技能不存在：{key}"}
        data = skill.preview(max_chars=budget)
        data["ok"] = True
        data["warnings"] = list(skill.warnings)
        return data


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ====================================================================== 单例


_library: Optional[SkillLibrary] = None


def get_skill_library() -> Optional[SkillLibrary]:
    """获取技能库单例；目录不可用时返回 `None`（**增强项不该让主流程挂掉**）。"""
    global _library
    if _library is not None:
        return _library
    try:
        library = SkillLibrary()
        library.reload()
    except Exception as exc:  # noqa: BLE001 - 技能库是加分项，不是前置依赖
        logger.debug(f"[技能库] 初始化失败：{exc}")
        return None
    _library = library
    return _library


def reset_skill_library() -> None:
    """清空单例（测试用）。"""
    global _library
    _library = None
