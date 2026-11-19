"""空壳角色的人设补全。

## 为什么需要

`_auto_detect_characters` 从章节里认出新人名后，只写骨架：

    {"first_appearance": N, "category": "无名小卒", "faction": "中立", "auto_created": True}

**没有 background / personality / goal**。而后续章节的上下文注入读的正是这些字段 ——
于是模型对这个人物的行为没有任何约束，容易出现性格前后不一。

实测：《配种的强大之处》里苏清寒在正文出现 **65 次**（戏份仅次于主角），
角色卡却是空壳、分类"无名小卒"。

## 设计取舍

**一次调用补全多个角色**，不是一人一次：每章可能冒出 2-3 个新人，
一人一次会让单章往返数翻倍。批量一次控制成本，且模型能看到同批角色、
关系描写更连贯。

**只填空字段**，绝不覆盖：用户可能已经手写过人设，补全只补缺的。
"""

from __future__ import annotations

from typing import Callable

__all__ = [
    "EMPTY_FIELDS",
    "build_enrich_prompt",
    "is_empty_character",
    "parse_enrichment",
]

#: 判定"空壳"看这几个字段：全空才需要补
EMPTY_FIELDS = ("backstory", "background", "personality", "appearance")


def is_empty_character(data: dict) -> bool:
    """角色是否"只有名字"。

    同时认 `backstory` 与 `background` —— 角色卡用前者、memory 用后者，
    只看一个会漏判（本项目踩过：memory 有内容、角色卡为空）。
    """
    if not isinstance(data, dict):
        return False
    return not any(str(data.get(field) or "").strip() for field in EMPTY_FIELDS)


def build_enrich_prompt(names: list[str], context: str = "") -> tuple[str, str]:
    """构造补全用的 (system, prompt)。

    `context` 传小说标题/类型与已知角色，让补出来的人设贴合已有世界，
    而不是每次从零发明一套设定。
    """
    wanted = ", ".join(names)
    system = (
        "你是小说角色设定师。为给定角色补写人设，使其与已有世界和人物关系自洽。\n"
        "只输出 JSON 对象，键为角色名，值为该角色的人设：\n"
        "{\n"
        '  "角色名": {\n'
        '    "backstory": "背景故事（80-150字，含出身、经历、动机）",\n'
        '    "personality": "性格特点（40-80字，要具体到行为习惯，不要形容词堆砌）",\n'
        '    "appearance": "外貌描述（30-60字）",\n'
        '    "goal": "核心目标（一句话）",\n'
        '    "relationship_to_main": "与主角的关系（一句话）",\n'
        '    "skill_suggestions": ["技能1", "技能2"]\n'
        "  }\n"
        "}\n"
        "要求：\n"
        "1. 只输出 JSON，不要解释、不要 Markdown 围栏；\n"
        "2. 必须涵盖这些角色：" + wanted + "\n"
        "3. 人设要与下文给出的既有设定一致，不得改变已有角色关系；\n"
        "4. 不要编造与其他角色冲突的身份。"
    )
    prompt = f"需要补写人设的角色：{wanted}"
    if context:
        prompt = f"{context[:1200]}\n\n{prompt}"
    return system, prompt


def parse_enrichment(
    response: str,
    names: list[str],
    parse_json: Callable[..., object],
) -> dict[str, dict]:
    """把模型响应解析成 `{角色名: 人设字段}`。

    - 只保留**请求过的**角色名（模型偶尔会顺手多写几个，那些不落盘）；
    - 只保留认识的字段，且值必须是非空字符串/列表；
    - 解析失败返回 `{}` —— 调用方按"没补到"处理，不得抛异常。

    `parse_json` 传全仓唯一的 `parse_json_response`（不要在这里手写解析）。
    """
    if not response:
        return {}
    try:
        data = parse_json(response, None)
    except Exception:  # noqa: BLE001 - 解析器自身异常也不该影响主流程
        return {}
    if not isinstance(data, dict):
        return {}

    allowed = {
        "backstory",
        "personality",
        "appearance",
        "goal",
        "relationship_to_main",
        "skill_suggestions",
    }
    wanted = set(names)
    result: dict[str, dict] = {}
    for name, fields in data.items():
        if name not in wanted or not isinstance(fields, dict):
            continue
        cleaned: dict = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if isinstance(value, str):
                text = value.strip()
                if text:
                    cleaned[key] = text
            elif isinstance(value, (list, tuple)):
                items = [str(item).strip() for item in value if str(item).strip()]
                if items:
                    cleaned[key] = items
        # 至少要有背景或性格才算补到东西
        if {"backstory", "personality"} & set(cleaned):
            result[name] = cleaned
    return result
