"""长篇一致性校验 —— 用已有的角色档案/时间线，查本章有没有「说出与设定不同的事实」。

## 为什么这件事最值得做

长篇 AI 写作的头号杀手不是文笔，是**前后矛盾**：第 3 章说林默 18 岁，第 30 章
说他 24 岁却只过了三个月；第 10 章写他是剑宗弟子，第 40 章变成散修。

而项目里**数据早就有了**：`memory/characters.json`（286 个角色，含 age/gender/faction）、
`memory/timeline/*.json`（123 条事件）。缺的只是一个"比对器"。

## 三条硬原则

**1. 只报可定位的冲突，不做猜测。**
每条问题都要能给出「本章原句」与「记录值」。给不出原句的一律不报 ——
"感觉这段有点矛盾"对作者毫无用处，只会消耗信任。

**2. 保守阈值，宁可漏报不可误报。**
年龄差 5 岁以内不报（角色会成长、作者会四舍五入）；性别/阵营只在**明确表述**
（"是男性""是反派"）时才判，不靠"他/她"代词推断（代词指向经常是别人的）。

**3. 只提示，不阻断、不改稿。**
一致性判断最终要人来定 —— "他突然变成 40 岁"可能是回忆、是易容、是另一个人同名。
所以本模块产出 `ConsistencyIssue` 列表，由调用方决定怎么呈现。

## 做不到的部分（如实记录）

`settings.json` 目前的实际内容是 `{"raw": "<AI 原始输出>"}`，**没有结构化**，
所以「世界观规则是否被违反」这一类做不了。要做必须先让设定结构化
（把 raw 拆成 已知区域/规则/势力/历史 等字段），那是另一件事。
本模块只做**角色属性**与**时间线合理性**两类可机判项。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

__all__ = [
    "ConsistencyIssue",
    "SEVERITY_LABELS",
    "check_character_properties",
    "check_chapter",
    "check_timeline_sanity",
    "format_issues",
    "load_characters",
    "load_timeline",
]

#: 严重度：`high` 是"几乎确定冲突"，`low` 是"值得看一眼"。
SEVERITY_LABELS: Dict[str, str] = {
    "high": "疑似冲突",
    "low": "请核对",
}

#: 年龄允许的偏差（岁）。角色会成长，作者也会四舍五入 —— 差几岁不算矛盾。
AGE_TOLERANCE = 5

#: 中文数字 → 阿拉伯数字（只覆盖 1–99，够用于年龄）。
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

#: 明确的性别表述 → 归一化。
#:
#: ❗ **刻意不含**「少年 / 少女 / 男子 / 女子」：它们是**人物称谓**，不是该角色的
#: 性别属性。实测在真实作品上跑 1094 章，「少女」这一类造成了 118 条误报
#: （全部指向同一个男性角色：句子里出现了另一个少女，但被算在他头上）。
#: 只保留「男性 / 女性」这种**属性词**，且要求紧邻角色名（见 `_gender_issue`）。
_GENDER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("男性", "男"),
    ("女性", "女"),
)

#: 阵营表述 → 归一化。同样要求句式支撑（`<名>是/属于 <阵营>`）。
_FACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("反派", "反派"),
    ("正派", "正派"),
    ("中立", "中立"),
)

#: 归属动词：只有「是/为/属于/加入/投靠」后面的阵营词才算该角色的阵营。
_BELONG_VERBS = "是为属于加入投靠成为"


def _cn_to_int(text: str) -> Optional[int]:
    """把「十八」「二十四」「九」这类中文数字转成整数。失败返回 `None`。"""
    body = str(text or "").strip()
    if not body:
        return None
    if body.isdigit():
        return int(body)
    if "十" not in body:
        return _CN_DIGITS.get(body)
    head, _, tail = body.partition("十")
    tens = _CN_DIGITS.get(head, None) if head else 1
    ones = _CN_DIGITS.get(tail, None) if tail else 0
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


@dataclass
class ConsistencyIssue:
    """一条疑似冲突。**必须带 `evidence`（本章原句）才能构造**。"""

    kind: str
    character: str
    claimed: str
    recorded: str
    evidence: str
    severity: str = "high"
    chapter: int = 0
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "character": self.character,
            "claimed": self.claimed,
            "recorded": self.recorded,
            "evidence": self.evidence,
            "severity": self.severity,
            "chapter": self.chapter,
            "note": self.note,
        }


# ====================================================================== 数据读取


def load_characters(novel_dir: Any) -> Dict[str, Dict[str, Any]]:
    """读角色档案。文件缺失/损坏返回空字典（一致性校验是增强项）。"""
    if not novel_dir:
        return {}
    path = Path(novel_dir) / "memory" / "characters.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f"[一致性] 角色档案读取失败：{exc}")
        return {}
    return {name: info for name, info in data.items() if isinstance(info, dict)} if isinstance(data, dict) else {}


def load_timeline(novel_dir: Any) -> List[Dict[str, Any]]:
    """读全部时间线事件（跨分页合并）。"""
    if not novel_dir:
        return []
    base = Path(novel_dir) / "memory" / "timeline"
    if not base.is_dir():
        return []
    events: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"[一致性] 跳过损坏时间线 {path.name}：{exc}")
            continue
        if isinstance(data, list):
            events.extend(item for item in data if isinstance(item, dict))
    return events


# ====================================================================== 句子切分


def _sentences(text: str) -> List[str]:
    """按句末标点切句，保留原句用于举证。"""
    body = text or ""
    found: List[str] = []
    buffer: List[str] = []
    for char in body:
        if char in "\n\r":
            if buffer:
                found.append("".join(buffer).strip())
                buffer = []
            continue
        buffer.append(char)
        if char in "。！？!?":
            sentence = "".join(buffer).strip()
            if sentence:
                found.append(sentence)
            buffer = []
    if buffer:
        found.append("".join(buffer).strip())
    return [s for s in found if s]


# ====================================================================== 角色属性比对


#: 角色名与「岁」之间不得出现「的」——「看着四十岁的老人」里的岁数不是他的。
#: 角色名与「岁」之间不得出现「的」——「看着四十岁的老人」里的岁数不是他的；
#: 「岁」后面也不能紧跟「的」（"四十岁的老人"是定语，不是属性陈述）。
_AGE_RE_TEMPLATE = r"{name}[^。！？\n的]{{0,8}}?(\d{{1,3}}|{cn})\s*岁(?!\s*的)"

_CN_NUM = "[一二三四五六七八九十]{1,3}"


def check_character_properties(
    text: str,
    characters: Dict[str, Dict[str, Any]],
    chapter: int = 0,
) -> List[ConsistencyIssue]:
    """比对本章文本里的角色属性表述与角色档案。

    只做三类：**年龄 / 性别 / 阵营**。武器与属性数值在正文里极少被明确写出，
    强行抽取只会产生噪音，故不做。
    """
    issues: List[ConsistencyIssue] = []
    sentences = _sentences(text)

    for name, info in characters.items():
        if not name or len(name) < 2:
            # 单字名（"王"）在正文里会匹配到大量无关词，直接跳过
            continue
        for sentence in sentences:
            if name not in sentence:
                continue

            # 同句出现多个已知角色 ⇒ 性别/阵营这类"属性词"指向不确定，跳过。
            # 年龄不受影响：`<名>...N岁` 的句式约束已经足够强。
            others = sum(1 for other in characters if other != name and other in sentence)
            issue = _age_issue(name, info, sentence, chapter)
            if issue is None and others == 0:
                issue = _gender_issue(name, info, sentence, chapter)
            if issue is None and others == 0:
                issue = _faction_issue(name, info, sentence, chapter)
            if issue is not None:
                issues.append(issue)
    return issues


def _age_issue(name: str, info: Dict[str, Any], sentence: str, chapter: int) -> Optional[ConsistencyIssue]:
    recorded = info.get("age")
    if not isinstance(recorded, (int, float)) or recorded <= 0:
        return None
    pattern = _AGE_RE_TEMPLATE.format(name=re.escape(name), cn=_CN_NUM)
    match = re.search(pattern, sentence)
    if not match:
        return None
    claimed = _cn_to_int(match.group(1))
    if claimed is None:
        return None
    if abs(claimed - float(recorded)) <= AGE_TOLERANCE:
        return None
    return ConsistencyIssue(
        kind="年龄",
        character=name,
        claimed=f"{claimed} 岁",
        recorded=f"{recorded:g} 岁",
        evidence=sentence,
        severity="high",
        chapter=chapter,
        note=f"差值 {abs(claimed - float(recorded)):.0f} 岁，超出容忍 {AGE_TOLERANCE} 岁；若为回忆/易容/同名角色请忽略",
    )


def _gender_issue(name: str, info: Dict[str, Any], sentence: str, chapter: int) -> Optional[ConsistencyIssue]:
    recorded = str(info.get("gender", "") or "").strip()
    if recorded not in ("男", "女"):
        return None
    for token, gender in _GENDER_PATTERNS:
        if gender == recorded:
            continue
        # 句式约束：性别词必须**紧跟在角色名后**（可隔"是/为/，/"）。
        # 放宽成"句子里出现该词"会把"林风看着那个女性走过来"判成林风是女性。
        pattern = re.escape(name) + r"\s*[，,]?\s*[是为]?\s*" + re.escape(token)
        if re.search(pattern, sentence):
            return ConsistencyIssue(
                kind="性别",
                character=name,
                claimed=gender,
                recorded=recorded,
                evidence=sentence,
                severity="high",
                chapter=chapter,
                note=f"「{token}」与档案性别不一致",
            )
    return None


def _faction_issue(name: str, info: Dict[str, Any], sentence: str, chapter: int) -> Optional[ConsistencyIssue]:
    recorded = str(info.get("faction", "") or "").strip()
    if not recorded:
        return None
    for token, faction in _FACTION_PATTERNS:
        if faction == recorded:
            continue
        # 句式约束：`<名>是/属于/加入 <阵营>` —— "林风杀了反派"不算他的阵营
        pattern = re.escape(name) + r"[^。！？\n]{0,6}?[" + _BELONG_VERBS + r"]\s*[^。！？\n]{0,4}?" + re.escape(token)
        if re.search(pattern, sentence):
            return ConsistencyIssue(
                kind="阵营",
                character=name,
                claimed=faction,
                recorded=recorded,
                evidence=sentence,
                severity="low",
                chapter=chapter,
                note=f"「{token}」与档案阵营不一致（可能是有意转变，请核对）",
            )
    return None


# ====================================================================== 时间线合理性


def check_timeline_sanity(events: Sequence[Dict[str, Any]]) -> List[ConsistencyIssue]:
    """时间线的两类硬问题：章节号非正、事件完全重复。

    刻意**不做**"章节号必须递增"：插叙、回忆、补写都会让章节号回退，
    那是正常写法，不是错误。
    """
    issues: List[ConsistencyIssue] = []
    seen: set[tuple[int, str]] = set()

    for event in events:
        chapter = event.get("chapter")
        text = str(event.get("event", "") or "")
        if not isinstance(chapter, int):
            continue
        if chapter <= 0:
            issues.append(
                ConsistencyIssue(
                    kind="时间线",
                    character="",
                    claimed=f"第 {chapter} 章",
                    recorded="章节号应为正整数",
                    evidence=text or "(无事件描述)",
                    severity="low",
                    chapter=chapter,
                    note="章节号为 0 或负数，通常是自动记录时没拿到章号",
                )
            )
        key = (chapter, text)
        if text and key in seen:
            issues.append(
                ConsistencyIssue(
                    kind="时间线",
                    character="",
                    claimed="重复记录",
                    recorded="同一章同一事件只应记一次",
                    evidence=text,
                    severity="low",
                    chapter=chapter,
                    note="同一事件被写了两次，可能是重复生成导致",
                )
            )
        seen.add(key)
    return issues


# ====================================================================== 汇总入口


def check_chapter(novel_dir: Any, chapter: int, text: str) -> Dict[str, Any]:
    """对一章做完整的一致性检查。

    Returns:
        `{"ok", "chapter", "issues", "summary", "checked"}` —— `ok` 只表示
        **没有 high 级问题**；`low` 级不判不合格。
    """
    characters = load_characters(novel_dir)
    property_issues = check_character_properties(text, characters, chapter=chapter)

    events = load_timeline(novel_dir)
    # 时间线合理性是**整库**属性，与本章文本无关；但仍随每次检查一并报出，
    # 因为它只有在写新章时才容易被发现
    timeline_issues = check_timeline_sanity(events)

    issues = property_issues + timeline_issues
    high = [i for i in issues if i.severity == "high"]
    return {
        "ok": not high,
        "chapter": chapter,
        "issues": [i.as_dict() for i in issues],
        "summary": {
            "total": len(issues),
            "high": len(high),
            "low": len(issues) - len(high),
            "characters_checked": len(characters),
            "timeline_events": len(events),
        },
        "checked": {
            "characters": bool(characters),
            "timeline": bool(events),
            # 设定一致性做不了，显式说明，别让人以为"没报就是没问题"
            "settings": "未检查（settings.json 尚未结构化）",
        },
    }


def format_issues(result: Dict[str, Any]) -> str:
    """渲染成人读文本。"""
    summary = result.get("summary") or {}
    lines = [
        f"一致性检查 · 第 {result.get('chapter', 0)} 章",
        f"核对 {summary.get('characters_checked', 0)} 个角色 / {summary.get('timeline_events', 0)} 条时间线事件",
        f"结果：{summary.get('high', 0)} 条疑似冲突 / {summary.get('low', 0)} 条待核对",
    ]
    checked = result.get("checked") or {}
    if checked.get("settings"):
        lines.append(f"未覆盖：{checked['settings']}")

    issues = result.get("issues") or []
    if not issues:
        lines.append("")
        lines.append("✅ 未发现可定位的前后矛盾")
        return "\n".join(lines)

    for issue in issues:
        label = SEVERITY_LABELS.get(issue["severity"], issue["severity"])
        who = f"{issue['character']}：" if issue.get("character") else ""
        lines.append("")
        lines.append(f"[{label}] {issue['kind']} · {who}{issue['claimed']}（档案：{issue['recorded']}）")
        lines.append(f"    原句：{issue['evidence']}")
        if issue.get("note"):
            lines.append(f"    说明：{issue['note']}")
    return "\n".join(lines)
