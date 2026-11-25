"""技能包解析的领域规则。

## 抽出来的原因

`skill_library.parse_skill` 本身已经是"读一次 + 纯解析"（`parse_frontmatter` 早就是纯函数），
但**"按优先级找入口文件"这段逻辑重复了三处**（`parse_skill`、扫子目录、`discover`）：

    for name in _ENTRY_NAMES:
        if (root / name).is_file():
            ...

三份拷贝意味着"优先级顺序"有三个定义点 —— 哪天想把 `SKILL.MD` 提到最前面，
得记住改三处。收敛成一个函数，顺序只在一处。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

__all__ = [
    "ENTRY_NAMES",
    "LEVEL_LABELS",
    "RULE_LEVELS",
    "SECTION_KINDS",
    "SkillRule",
    "classify_level",
    "classify_section",
    "extract_rules",
    "extract_sections",
    "first_entry_name",
]

#: 入口文件的候选名，**按优先级**排列（大写优先，兼容社区包的写法）
ENTRY_NAMES: tuple[str, ...] = ("SKILL.md", "skill.md", "Skill.md", "SKILL.MD")


def first_entry_name(candidates: Sequence[str], is_file: Callable[[str], bool]) -> str | None:
    """按优先级返回第一个存在的入口文件名；都不存在返回 `None`。

    `is_file` 注入而不是直接 `Path.is_file()`：调用方各自有基准目录，
    传入 `lambda n: (base / n).is_file()` 即可；这样本函数保持纯，可穷举测试。
    """
    for name in candidates:
        if is_file(name):
            return name
    return None


RULE_LEVELS: dict[str, str] = {
    "A": "机械改",
    "B": "建议改",
    "C": "只报告",
    "F": "指纹",
    "H": "人审",
    "X": "已否决",
}


LEVEL_LABELS: dict[str, str] = {**RULE_LEVELS, "": "通用"}


SECTION_KINDS: dict[str, str] = {
    "rule": "规则",
    "workflow": "流程",
    "meta": "说明",
}


_HEADING_RE = re.compile(r"^(?P<hashes>#{2,4})[ \t]+(?P<title>.+?)[ \t]*$", re.M)

_RULE_TITLE_RE = re.compile(
    r"^(?:\d+[.、]\s*|第\s*[0-9一二三四五六七八九十]+\s*[条步])"
    r"|规则|原则|清单|人审|验收|指纹|不改|永不改|禁区"
)


_NUMBERED_TITLE_RE = re.compile(r"^\d+[.、]\s*")


_STEP_TITLE_RE = re.compile(r"^第\s*[0-9.一二三四五六七八九十]+\s*步")


_LEVEL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("X", ("X 级", "永不改", "已否决", "防误改")),
    ("H", ("人审", "不碰")),
    ("F", ("指纹",)),
)


_MECHANICAL_HINTS = ("删掉", "删除", "直接写", "换成", "去掉", "只换标点")


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
                # ⚠️ 不判 `if not cells`：`"x".split("|")` 永远至少返回一个元素，
                # 那个分支不可达（曾经存在，覆盖率扫出来是死代码，已删）。
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
