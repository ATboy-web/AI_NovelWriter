"""世界线事件的领域规则：抽取提示词、解析模型输出、角色名去重。

## 为什么从 `timeline_store.py` 搬过来

`timeline_store.py`（983 行）里 `TimelineStore` 占 670 行 —— 读事件、合并、同步、
构建分支树，全要碰磁盘。但文件末尾这三个函数是**纯文本变换**：
拼提示词、解析模型返回的 JSON、角色名去重。

搬出来之后，`parse_extraction_result` 可以直接喂"模型可能吐出的各种坏 JSON"，
不必先造一部作品和 timelines 目录。

## 解析的容错口径

`parse_extraction_result` **永不抛异常**：模型输出不可信，坏 JSON、缺字段、
类型不对都应降级成"这一条跳过"，而不是让整条时间线同步失败。
"""

from __future__ import annotations

import json
from typing import Iterable, Sequence

__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "EXTRACTION_SCHEMA_HINT",
    "SOURCE_AUTO",
    "SOURCE_MANUAL",
    "char_list_unique",
    "extraction_prompt",
    "parse_extraction_result",
]

#: 事件来源标记：`auto` = 从正文/流程自动记录，`manual` = 作者手工添加
SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"

#: 置信度：`auto` 抽取出来的默认低置信，人工确认后升为 high
CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"

EXTRACTION_SCHEMA_HINT = (
    "只输出 JSON 数组，不要任何解释文字。每项形如："
    '{"chapter": 12, "event": "一句话事件", "type": "story", '
    '"characters": ["角色A"], "location": "地点", "story_time": "故事内时间", '
    '"arc": "所属弧线", "confidence": "high"}'
)


def extraction_prompt(
    chapter_num: int,
    text: str,
    known_characters: Iterable[str] = (),
    max_events: int = 12,
    max_chars: int = 6000,
) -> str:
    """构造"从正文抽取事件"的提示词（**纯函数**，便于单测）。

    为什么单独抽出来：抽取本身要调 AI（不可单测、有网络依赖），
    而"提示词是否把章节号、角色白名单、输出契约交代清楚"是**可以单测**的，
    也是这类功能最容易出错的地方（模型返回散文、返回错章节号、自造角色名）。

    正文超过 `max_chars` 时**只取头尾**：开头交代场景与人物，结尾是结果与悬念，
    中间过程对"发生了什么"贡献最小。
    """
    body = (text or "").strip()
    if len(body) > max_chars:
        head = body[: max_chars * 2 // 3]
        tail = body[-max_chars // 3 :]
        body = f"{head}\n……（中间省略）……\n{tail}"

    names = [str(n) for n in known_characters if str(n).strip()]
    roster = (
        "已知角色（**只能**从中选取 characters，不要自造名字）：" + "、".join(names[:120])
        if names
        else "本作尚未登记角色，characters 可留空数组。"
    )

    return (
        f"你在为长篇小说维护时间线。请从下面第 {chapter_num} 章的正文中抽取关键事件"
        f"（最多 {max_events} 条，只抽推进情节或改变人物关系的事件，不要抽景物描写）。\n\n"
        f"{roster}\n\n"
        f"硬性要求：\n"
        f"1. 每条事件的 `chapter` 必须是 {chapter_num}（不要写别的章号）；\n"
        f"2. `event` 是一句话，不要抄原文长句；\n"
        f"3. 判断不了 `location` / `story_time` 时留空字符串，不要编造；\n"
        f'4. `confidence` 只在事件明确写到时才用 "high"，否则 "low"；\n'
        f"5. {EXTRACTION_SCHEMA_HINT}\n\n"
        f"【第 {chapter_num} 章正文】\n{body}"
    )


def parse_extraction_result(raw: str, chapter_num: int, known_characters: Iterable[str] = ()) -> list[dict]:
    """解析模型返回的 JSON，并**修正**明显不可信的结果。

    三处纠正（都是实测里最容易出的问题）：
    - 章号被模型写成别的值 → 强制改回 `chapter_num`；
    - `characters` 里出现未登记的名字 → 丢弃该名字（避免污染角色库）；
    - 返回的不是数组/无法解析 → 返回空列表（调用方据此报"没抽到"，而不是崩）。
    """
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        text = text.rstrip("`").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []

    allowed = {str(n) for n in known_characters}
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event", "") or "").strip()
        if not event:
            continue
        chars = item.get("characters") or []
        if isinstance(chars, str):
            chars = [chars]
        chars = [str(c).strip() for c in chars if str(c).strip()]
        if allowed:
            chars = [c for c in chars if c in allowed]
        confidence = str(item.get("confidence", "") or "").strip().lower()
        out.append(
            {
                "chapter": int(chapter_num),
                "event": event,
                "type": str(item.get("type", "story") or "story"),
                "characters": char_list_unique(chars),
                "location": str(item.get("location", "") or "").strip(),
                "story_time": str(item.get("story_time", "") or "").strip(),
                "arc": str(item.get("arc", "") or "").strip(),
                "source": SOURCE_AUTO,
                "confidence": CONFIDENCE_HIGH if confidence == CONFIDENCE_HIGH else CONFIDENCE_LOW,
            }
        )
    return out


def char_list_unique(names: Sequence[str]) -> list[str]:
    """保序去重（`characters` 里同一个角色只留一次）。

    ⚠️ 同时过滤**纯空白**：模型偶尔会吐出 `"  "` 这种"看起来有值"的占位符。
    旧实现只判 `if name`，于是空格名会被当成一个角色写进事件，
    在面板上表现为一个点不开的空白条目。
    """
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        cleaned = (name or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out
