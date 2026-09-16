"""传记的纯逻辑（v3 §2.4 ②）—— 与界面无关，可单测、可被多处复用。

## 为什么单独成模块

这些函数原本长在 `app/panels/biography_panel.py` 里，于是出现了两个问题：

1. **核心 UI 要复用就得反向依赖面板层**（`character_ui` → `app.panels.*`），
   分层方向上说不通；
2. **同一件事有两份实现**：`character_ui._generate_character_biography` 的提示词
   只用 `char_info + outline[:5]`（完全不用已写正文），而面板用的是接入 RAG 与时间线的版本 ——
   同一个功能，两个入口，两种质量。

现在这里是**唯一来源**：面板与 `character_ui` 都从这里取提示词与结构化落盘逻辑。
面板模块仍把名字再导出一份，既有导入路径（含测试）不受影响。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.storage import read_json_with_backup, safe_filename

BIOGRAPHIES_DIR = "biographies"
#: 手工故事线目录（与 `character_ui._edit_character_story` 一致）
STORIES_DIR = "character_stories"
#: 生成字数上限对应的 token 上限（ROADMAP §8 决策 3：传记建议区间 8192~16384）
MAX_BIO_TOKENS = 8192
#: 回写角色档案时的截断长度（与既有实现保持一致，避免两处口径分叉）
PROFILE_BIOGRAPHY_LIMIT = 500


# ====================================================================== 纯函数（可单测）


def filter_characters(
    characters: Mapping[str, Any],
    keyword: str = "",
    category: str = "",
    faction: str = "",
    only_with_biography: bool = False,
) -> dict[str, dict]:
    """按关键词 / 分类 / 阵营筛选角色。

    286 个角色必须有搜索能力，否则左列没法用。关键词同时匹配**角色名**与
    `background`/`personality` 摘要 —— 只匹配名字会漏掉"记得设定但记不得名字"的场景。
    """
    kw = (keyword or "").strip().lower()
    out: dict[str, dict] = {}
    for name, raw in (characters or {}).items():
        info = raw if isinstance(raw, dict) else {}
        if category and str(info.get("category", "")) != category:
            continue
        if faction and str(info.get("faction", "")) != faction:
            continue
        if only_with_biography and not (info.get("biography") or info.get("biography_file")):
            continue
        if kw:
            haystack = " ".join(
                str(info.get(field, "") or "")
                for field in ("name", "personality", "background", "goal", "relationship_to_main")
            ).lower()
            if kw not in str(name).lower() and kw not in haystack:
                continue
        out[str(name)] = info
    return out


def character_rows(characters: Mapping[str, Any]) -> list[tuple[str, tuple]]:
    """角色 → Treeview 行。列：角色 / 分类 / 阵营 / 重要度 / 传记。

    `iid` 用 `ch{角色名}`；角色名可能含空格但不会是 `#`，故与分支行不冲突。
    """
    rows: list[tuple[str, tuple]] = []
    for name in sorted(
        characters,
        key=lambda n: (-int((characters[n] or {}).get("importance", 5) or 5), str(n)),
    ):
        info = characters.get(name) or {}
        has_bio = "✓" if (info.get("biography") or info.get("biography_file")) else "—"
        rows.append(
            (
                f"ch{name}",
                (
                    str(name),
                    str(info.get("category", "") or "—"),
                    str(info.get("faction", "") or "—"),
                    str(info.get("importance", 5) or 5),
                    has_bio,
                ),
            )
        )
    return rows


def material_summary(
    chapters: Iterable[int],
    events: Iterable[Any],
    anchors: Iterable[Mapping[str, Any]] = (),
    story_arcs: Iterable[Mapping[str, Any]] = (),
) -> str:
    """素材侧栏文本：让作者看清"这次生成引用了什么"。"""
    chapter_list = sorted({int(c) for c in chapters if int(c) > 0})
    event_list = list(events)
    anchor_list = list(anchors)
    arc_list = list(story_arcs)
    if not chapter_list and not event_list and not anchor_list and not arc_list:
        return "素材：无（该角色尚未在任何章节或事件中出现，生成结果会偏泛）"
    parts = [
        f"出场章节 {len(chapter_list)} 章" + (f"（{_range_text(chapter_list)}）" if chapter_list else ""),
        f"相关事件 {len(event_list)} 条",
        f"记忆检索命中 {len(anchor_list)} 段",
    ]
    if arc_list:
        parts.append(f"手工故事线 {len(arc_list)} 段")
    return "素材：" + " / ".join(parts)


def _range_text(numbers: list[int], head: int = 8) -> str:
    shown = "、".join(str(n) for n in numbers[:head])
    return shown + ("…" if len(numbers) > head else "")


def build_biography_prompt(
    name: str,
    info: Mapping[str, Any] | None,
    word_count: int = 1500,
    anchors: Iterable[Mapping[str, Any]] = (),
    events: Iterable[Any] = (),
    story_arcs: Iterable[Mapping[str, Any]] = (),
) -> str:
    """构造传记提示词（**纯函数**）。

    相比既有实现多喂三类材料（这正是"输入太薄"的修法）：
    记忆检索命中的正文片段、时间线事件、作者手写的故事线。
    同时明确要求输出**分段**，因为分段才能转成 `story_arcs`。
    """
    info = info or {}
    lines = [
        f"请为小说角色「{name}」撰写一篇约 {int(word_count)} 字的传记。",
        "",
        "【角色档案】",
    ]
    for field, label in (
        ("gender", "性别"),
        ("age", "年龄"),
        ("category", "分类"),
        ("faction", "阵营"),
        ("importance", "重要度"),
        ("personality", "性格"),
        ("appearance", "外貌"),
        ("background", "背景"),
        ("relationship_to_main", "与主角关系"),
        ("goal", "目标"),
        ("status", "状态"),
    ):
        value = info.get(field)
        if value:
            lines.append(f"- {label}：{value}")
    weapon = info.get("weapon")
    if isinstance(weapon, Mapping) and weapon.get("name"):
        lines.append(f"- 武器：{weapon.get('name')}（{weapon.get('quality', '')}）")

    event_list = list(events)
    if event_list:
        lines += ["", "【该角色参与的时间线事件（按章）】"]
        for event in event_list[:60]:
            chapter = getattr(event, "chapter", event.get("chapter", "") if isinstance(event, Mapping) else "")
            text = getattr(event, "event", event.get("event", "") if isinstance(event, Mapping) else "")
            lines.append(f"- 第{chapter}章：{text}")

    arc_list = [a for a in story_arcs if isinstance(a, Mapping)]
    if arc_list:
        lines += ["", "【作者手写的既有故事线（须保持一致，不要与之矛盾）】"]
        for arc in arc_list[:20]:
            lines.append(f"- {arc.get('title', '')}：{str(arc.get('content', ''))[:200]}")

    anchor_list = [a for a in anchors if isinstance(a, Mapping)]
    if anchor_list:
        lines += ["", "【从已写正文检索到的片段（作为事实依据）】"]
        for anchor in anchor_list[:12]:
            content = str(anchor.get("content", ""))[:600]
            lines.append(f"- {content}")

    lines += [
        "",
        "【写作要求】",
        "1. 只依据上面提供的材料，**不要编造**未出现过的重大事件；材料不足时宁可写得概括；",
        "2. 用分段小标题组织（如「出身」「转折」「关系」「结局」），每段一个 `## 标题`；",
        "3. 段落之间不要重复；总字数接近目标字数；",
        "4. 直接输出传记正文，不要任何前后缀说明。",
    ]
    return "\n".join(lines)


def split_sections(text: str) -> list[dict]:
    """把 `## 标题` 形式的传记正文切成 `[{id,title,content}]`（结构化源用）。

    没有小标题时整篇作为一段 —— 不硬造标题。
    """
    body = (text or "").strip()
    if not body:
        return []
    sections: list[dict] = []
    current_title = "正文"
    buffer: list[str] = []

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if content:
            sections.append({"id": f"sec{len(sections) + 1}", "title": current_title, "content": content})

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            buffer = []
            current_title = stripped.lstrip("#").strip() or "正文"
            continue
        buffer.append(line)
    flush()
    return sections


def story_arcs_from_sections(sections: Iterable[Mapping[str, Any]]) -> list[dict]:
    """把传记分段转成 `character_stories` 的 `story_arcs` 结构（一键转换）。"""
    return [
        {"title": str(s.get("title", "") or ""), "content": str(s.get("content", "") or "")}
        for s in sections
        if str(s.get("content", "") or "").strip()
    ]


def structured_biography(
    name: str,
    sections: list[dict],
    sources: Mapping[str, Any] | None = None,
    provider: str = "",
    model: str = "",
    tokens: int = 0,
    generated_at: str = "",
    version: int = 1,
) -> dict:
    """构造 `biographies/<名>.json` 的结构（对应 ROADMAP §2.4 ② 的字段表）。"""
    return {
        "name": str(name),
        "version": int(version),
        "generated_at": str(generated_at),
        "provider": str(provider),
        "model": str(model),
        "tokens": int(tokens),
        "sections": [dict(s) for s in sections],
        "arcs": [str(a) for a in ((sources or {}).get("arcs") or [])],
        "sources": {
            "chapters": list((sources or {}).get("chapters") or []),
            "timeline_events": list((sources or {}).get("timeline_events") or []),
            "anchors": list((sources or {}).get("anchors") or []),
        },
    }


def read_story_arcs(novel_dir: Any, name: str) -> dict:
    """读手工故事线文件；不存在或损坏时返回空结构。"""
    if not novel_dir or not name:
        return {"name": str(name), "story_arcs": [], "notes": ""}
    path = novel_dir / STORIES_DIR / f"{safe_filename(name)}.json"
    data, status = read_json_with_backup(path, default=None)
    if status == "corrupt" or not isinstance(data, dict):
        return {"name": str(name), "story_arcs": [], "notes": ""}
    data.setdefault("name", str(name))
    data.setdefault("story_arcs", [])
    data.setdefault("notes", "")
    return data


def load_biography_json(novel_dir: Any, name: str) -> dict | None:
    """读取结构化传记（`_read_biography_text` 与其它调用方共用）。缺失或损坏返回 None。"""
    if not novel_dir or not name:
        return None
    path = novel_dir / BIOGRAPHIES_DIR / f"{safe_filename(name)}.json"
    data, status = read_json_with_backup(path, default=None)
    if status == "corrupt" or not isinstance(data, dict):
        return None
    return data
