"""世代传承（v3 §2.4 ③）—— 数据与护栏层。

## 现状缺口（勘察确认）

`lifecycle_ui._create_sequel` 建第二部目录时**只复制两样东西**：
`memory/settings.json` 与 `characters/` 整个目录。不继承 `outline.json`、
`timelines/`、`memory/`（摘要/弧线/卷）与伏笔线索；`original_novel` 只被写进
`meta.json` 而**不参与任何逻辑**；也没有"第几代"的层级模型。

结果是"续写第二代"实际退化成"新建一本带同样角色的书"：读者看不到前代史，
作者要自己把大纲和伏笔再抄一遍。

## 🚨 本模块的第一职责是护栏，不是搬运

子代读父代的数据、又要写自己的目录 —— 这是整个 v3 改造里**数据风险最高**的一处：
一次路径拼接错误就会把父代的书改掉（父代往往已经写完、甚至已发布）。

因此本模块**所有**写操作都必须经过 `guard_child_path(child_dir, target)`：
它把目标解析成绝对路径，并要求它**落在子代目录之内**，否则抛 `ValueError`。
`child_scope = "readonly_parent"` 是记录在 `meta.lineage` 里的契约值，
配套测试把它固化为断言（见 `tests/test_lineage.py`）。

## 纯逻辑，无 GUI 无网络

所有函数只吃路径与字典、只吐字典，便于单测把"年龄推进""死亡转状态""继承清单"
这些规则逐条钉住。
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from loguru import logger

from app.storage import atomic_write_text, read_json_with_backup

#: 从文件名/字符串里提取全部数字段（`chapter_0001` → ["0001"]）
_DIGITS_RE = re.compile(r"\d+")

__all__ = [
    "LINEAGE_KEY",
    "SCOPE_READONLY_PARENT",
    "INHERIT_DIMENSIONS",
    "DIMENSION_SOURCES",
    "DEFAULT_INHERITED",
    "LineageRecord",
    "InheritancePlan",
    "read_lineage",
    "build_lineage_record",
    "generation_tree",
    "plan_inheritance",
    "apply_age_progression",
    "apply_death_status",
    "extract_unresolved_plots",
    "unresolved_plot_keywords",
    "inherited_plot_report",
    "describe_plan_items",
    "parent_last_chapter",
    "make_character_transform",
    "inherit_into_child",
    "is_within",
    "guard_child_path",
    "copy_into_child",
]

#: `meta.json` 里存放代际信息的键
LINEAGE_KEY = "lineage"

#: 子代对父代的唯一合法关系：**只读**
SCOPE_READONLY_PARENT = "readonly_parent"

#: 可勾选的继承维度（顺序即面板展示顺序）
INHERIT_DIMENSIONS: tuple[str, ...] = (
    "characters",
    "settings",
    "outline",
    "timeline",
    "memory",
    "plots",
)

#: 维度 → 该维度要继承的**相对路径**（文件或目录）。
#: 全部以父代小说目录为根，逐条都有真实读方（不是凭空造的目录名）。
DIMENSION_SOURCES: dict[str, tuple[str, ...]] = {
    "characters": ("characters", "memory/characters.json"),
    "settings": ("memory/settings.json",),
    "outline": ("outline.json",),
    "timeline": ("timelines", "memory/timeline"),
    "memory": (
        "memory/global_summary.txt",
        "memory/arcs",
        "memory/volumes",
        "memory/chapters",
    ),
    # 伏笔不复制文件，而是从父代全局摘要里抽成一份待办清单写进子代
    "plots": ("memory/global_summary.txt",),
}

#: 默认全继承（用户 2026-09-16 决策 2）
DEFAULT_INHERITED: dict[str, bool] = {name: True for name in INHERIT_DIMENSIONS}


# ====================================================================== 代际记录


@dataclass
class LineageRecord:
    """一本小说在世代链上的位置（对应 `meta.json` 的 `lineage` 字段）。"""

    generation: int = 1
    parent_novel: str = ""
    parent_title: str = ""
    era_gap_years: int = 0
    inherited: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_INHERITED))
    child_scope: str = SCOPE_READONLY_PARENT

    @property
    def is_root(self) -> bool:
        """第 1 代 = 没有父代。"""
        return self.generation <= 1 or not self.parent_novel

    def as_dict(self) -> dict:
        return {
            "generation": int(self.generation),
            "parent_novel": str(self.parent_novel or ""),
            "parent_title": str(self.parent_title or ""),
            "era_gap_years": int(self.era_gap_years or 0),
            "inherited": {k: bool(v) for k, v in (self.inherited or {}).items()},
            "child_scope": str(self.child_scope or SCOPE_READONLY_PARENT),
        }

    @classmethod
    def from_meta(cls, meta: Mapping[str, Any] | None) -> "LineageRecord | None":
        """从 `meta.json` 解析。**没有 `lineage` 键时返回 `None`**（= 第 1 代）。

        这样"老小说没有这个字段"与"解析失败"能区分开：前者是正常的历史状态，
        后者才需要告警。
        """
        if not isinstance(meta, Mapping):
            return None
        raw = meta.get(LINEAGE_KEY)
        if not isinstance(raw, Mapping):
            return None

        inherited = dict(DEFAULT_INHERITED)
        stored = raw.get("inherited")
        if isinstance(stored, Mapping):
            for key in INHERIT_DIMENSIONS:
                if key in stored:
                    inherited[key] = bool(stored[key])
        try:
            generation = int(raw.get("generation", 1) or 1)
        except (TypeError, ValueError):
            generation = 1
        try:
            gap = int(raw.get("era_gap_years", 0) or 0)
        except (TypeError, ValueError):
            gap = 0

        return cls(
            generation=max(generation, 1),
            parent_novel=str(raw.get("parent_novel", "") or ""),
            parent_title=str(raw.get("parent_title", "") or ""),
            era_gap_years=gap,
            inherited=inherited,
            child_scope=str(raw.get("child_scope", SCOPE_READONLY_PARENT) or SCOPE_READONLY_PARENT),
        )


def read_lineage(novel_dir: Any) -> LineageRecord | None:
    """读某本小说的代际记录；无 `lineage` 或文件损坏时返回 `None`。"""
    if not novel_dir:
        return None
    meta, status = read_json_with_backup(Path(novel_dir) / "meta.json", default=None)
    if status == "corrupt":
        logger.warning(f"[lineage] meta.json 损坏，按无代际信息处理: {novel_dir}")
        return None
    return LineageRecord.from_meta(meta)


def build_lineage_record(
    parent_dir: Any,
    generation: int | None = None,
    era_gap_years: int = 0,
    inherited: Mapping[str, bool] | None = None,
) -> LineageRecord:
    """按父代目录构造一条代际记录（`generation` 不传则自动 = 父代 + 1）。"""
    parent_path = Path(parent_dir) if parent_dir else None
    parent_record = read_lineage(parent_path) if parent_path else None
    parent_title = ""
    if parent_path:
        meta, _status = read_json_with_backup(parent_path / "meta.json", default=None)
        if isinstance(meta, Mapping):
            parent_title = str(meta.get("title") or meta.get("original_title") or "")

    if generation is None:
        generation = (parent_record.generation + 1) if parent_record else 2

    merged = dict(DEFAULT_INHERITED)
    if inherited:
        for key in INHERIT_DIMENSIONS:
            if key in inherited:
                merged[key] = bool(inherited[key])

    return LineageRecord(
        generation=max(int(generation), 1),
        parent_novel=str(parent_path) if parent_path else "",
        parent_title=parent_title,
        era_gap_years=int(era_gap_years or 0),
        inherited=merged,
        child_scope=SCOPE_READONLY_PARENT,
    )


def generation_tree(novel_dir: Any, max_depth: int = 8) -> list[dict]:
    """沿 `parent_novel` 向上回溯，返回**从最新一代往前**的代际链（含自身）。

    每一行 `{generation, novel_dir, title, is_current, readonly, missing}`。
    `missing=True` 表示父代目录已不存在（被移动/删除）—— 面板应灰显而不是崩。
    `readonly` 对除自身以外的所有祖先恒为 True（子代只读父代）。
    """
    rows: list[dict] = []
    current = Path(novel_dir) if novel_dir else None
    if current is None:
        return rows

    seen: set[str] = set()
    node: Path | None = current
    for depth in range(max_depth):
        if node is None:
            break
        key = str(node)
        if key in seen:  # 环状 lineage 保护（手改 meta 可能造成）
            logger.warning(f"[lineage] 代际链出现环，已截断: {key}")
            break
        seen.add(key)

        exists = node.exists()
        meta, status = read_json_with_backup(node / "meta.json", default=None)
        meta = meta if isinstance(meta, Mapping) else {}
        record = LineageRecord.from_meta(meta)
        rows.append(
            {
                "generation": record.generation if record else 1,
                "novel_dir": key,
                "title": str(meta.get("title") or node.name),
                "is_current": depth == 0,
                "readonly": depth > 0,
                "missing": not exists or status == "corrupt",
            }
        )
        node = Path(record.parent_novel) if (record and record.parent_novel) else None
    return rows


# ====================================================================== 护栏


def is_within(root: Any, target: Any) -> bool:
    """`target` 是否落在 `root` **之内**（root 自身不算"之内"）。

    用 `Path.resolve()` 归一化后再比：`..` 与符号链接都不会让比较出错。
    Windows 上大小写不敏感，故比较 `os.path.normcase` 后的结果。
    """
    if not root or not target:
        return False
    try:
        root_p = Path(root).resolve()
        target_p = Path(target).resolve()
    except (OSError, RuntimeError):
        return False

    root_s = os.path.normcase(str(root_p))
    target_s = os.path.normcase(str(target_p))
    if target_s == root_s:
        return False
    return target_s.startswith(root_s + os.sep)


def guard_child_path(child_dir: Any, target: Any) -> Path:
    """🚨 **子代写操作的唯一入口**：目标必须落在子代目录之内，否则拒绝。

    这是「子代不得污染父代」护栏的强制点。任何要往子代拷文件/写 JSON 的代码
    都必须先过这一关 —— 而不是各自拼接路径（拼接错了没有第二次机会，
    父代可能已经发布）。

    Raises:
        ValueError: `child_dir` 为空、或 `target` 不在 `child_dir` 之内。
    """
    if not child_dir:
        raise ValueError("子代目录为空，拒绝写入")
    child_p = Path(child_dir).resolve()
    if not is_within(child_p, target):
        raise ValueError(
            f"护栏拒绝：目标 {target!r} 不在子代目录 {child_p} 之内（子代只读父代，禁止越界写入）"
        )
    return Path(target)


def copy_into_child(child_dir: Any, source: Any, relative: str | None = None) -> Path | None:
    """把父代的文件/目录复制进子代。**每一步都过护栏**。

    `relative` 不传时用 `source` 相对 `child_dir` 的路径（即保持同名同位置）；
    调用方要改名就显式传 `relative`。

    Returns:
        子代侧的最终路径；源不存在时返回 `None`（不抛错 —— 缺某类历史数据是正常的）。
    """
    src = Path(source)
    if not src.exists():
        return None

    rel = relative if relative is not None else src.name
    dst = guard_child_path(child_dir, Path(child_dir) / rel)

    if src.is_dir():
        # dirs_exist_ok：子代可能已经有 characters/（续集流程先建过），
        # 合并而不是抛 FileExistsError。
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return dst


# ====================================================================== 继承计划


@dataclass
class InheritancePlan:
    """`plan_inheritance` 的结果：每个维度"有什么可继承、会拷到哪"。"""

    parent_dir: str = ""
    inherited: dict[str, bool] = field(default_factory=dict)
    items: dict[str, dict] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        """勾选了但父代没有的路径（面板应提示，避免"以为继承了其实没有"）。"""
        out: list[str] = []
        for entry in self.items.values():
            out.extend(entry.get("missing") or [])
        return out

    def describe(self) -> str:
        on = [k for k, v in self.inherited.items() if v]
        off = [k for k, v in self.inherited.items() if not v]
        parts = [f"继承 {len(on)} 项：{'、'.join(on) or '无'}"]
        if off:
            parts.append(f"不继承：{'、'.join(off)}")
        if self.missing:
            parts.append(f"父代缺失 {len(self.missing)} 项")
        return "；".join(parts)


def plan_inheritance(
    parent_dir: Any, inherited: Mapping[str, bool] | None = None
) -> InheritancePlan:
    """算出"勾选的维度各要拷哪些路径、哪些不存在"。**不复制任何文件**。

    先算后做，是为了让面板能在用户点"创建"之前就把"父代缺大纲/缺时间线"
    如实说出来 —— 续集最常见的失望就是"以为继承了其实没有"。
    """
    parent_p = Path(parent_dir) if parent_dir else None
    want = dict(DEFAULT_INHERITED)
    if inherited:
        for key in INHERIT_DIMENSIONS:
            if key in inherited:
                want[key] = bool(inherited[key])

    plan = InheritancePlan(parent_dir=str(parent_p) if parent_p else "", inherited=want)
    for dim in INHERIT_DIMENSIONS:
        entry = {"copy": [], "missing": [], "skipped": not want.get(dim, False)}
        if not entry["skipped"] and parent_p is not None:
            for rel in DIMENSION_SOURCES[dim]:
                if (parent_p / rel).exists():
                    entry["copy"].append(rel)
                else:
                    entry["missing"].append(rel)
        plan.items[dim] = entry
    return plan


# ====================================================================== 代际数据换算


def _as_int(value: Any) -> int | None:
    """把 `age` 这类字段转成整数；"不明"/"?" 等非数字返回 None（**不改动**）。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def apply_age_progression(characters: Mapping[str, Any], years: int) -> tuple[dict, list[str]]:
    """角色年龄推进 `years` 年（`era_gap_years`）。

    规则（对应 ROADMAP §2.4 ③ 的继承策略表）：
    - `age` 是数字/含数字的字符串 → 加上年差；
    - 非数字（"不明"、"?"、空）→ **原样保留**，并在说明里记一笔
      （不要伪造年龄，也不要删字段）；
    - **绝不删除任何角色** —— 这是项目硬约束。

    Returns:
        (新的角色字典, 人类可读的变更说明列表)
    """
    out: dict[str, Any] = {}
    notes: list[str] = []
    years = int(years or 0)
    for name, raw in (characters or {}).items():
        if not isinstance(raw, Mapping):
            out[str(name)] = raw
            continue
        info = dict(raw)
        age = _as_int(info.get("age"))
        if age is None:
            if info.get("age"):
                notes.append(f"{name}：年龄「{info.get('age')}」非数字，保持不变")
        elif years:
            info["age"] = age + years
            notes.append(f"{name}：{age} → {age + years} 岁")
        else:
            info["age"] = age
        out[str(name)] = info
    return out, notes


def apply_death_status(
    characters: Mapping[str, Any], last_chapter: int
) -> tuple[dict, list[str]]:
    """把"在父代范围内已死亡"的角色显式标为 `deceased`，**而不是删除**。

    判据：`death_chapter` 是数字且 `<= last_chapter`，且当前没有 `status`。
    已有 `status` 的角色不动（可能已经是 "deceased" 或作者手写的其他状态）。

    这条规则的意义：续集里"上一代人物的结局"必须仍然可查 ——
    删掉他们就等于把前代史抹了。
    """
    out: dict[str, Any] = {}
    notes: list[str] = []
    last_chapter = int(last_chapter or 0)
    for name, raw in (characters or {}).items():
        if not isinstance(raw, Mapping):
            out[str(name)] = raw
            continue
        info = dict(raw)
        death = _as_int(info.get("death_chapter"))
        if death is not None and 0 < death <= last_chapter and not info.get("status"):
            info["status"] = "deceased"
            notes.append(f"{name}：第 {death} 章已故 → 标记为 deceased（保留档案）")
        out[str(name)] = info
    return out, notes


# ====================================================================== 伏笔


def unresolved_plot_keywords() -> tuple[str, ...]:
    """识别"未回收伏笔/悬念"的关键词表。

    与 `novel_agent._get_unresolved_plots` 的判据保持一致（那边是实例方法、
    依赖整个 Agent；这里抽成纯函数以便单测与复用）。
    """
    return (
        "未解",
        "悬而未决",
        "谜团",
        "伏笔",
        "待揭晓",
        "尚未",
        "未知",
        "秘密",
        "真相",
        "遗留",
    )


def extract_unresolved_plots(text: str, limit: int = 8) -> list[str]:
    """从全局摘要里抽"未回收伏笔"候选行（**保序、去重、限量**）。

    逐行扫描即可：`novel_agent` 的摘要本身就是分行写的，按行比按句更贴合数据形态。
    """
    if not text:
        return []
    keywords = unresolved_plot_keywords()
    out: list[str] = []
    for line in str(text).splitlines():
        stripped = line.strip().lstrip("-*•0123456789. ").strip()
        if not stripped or len(stripped) < 4:
            continue
        if not any(k in stripped for k in keywords):
            continue
        if stripped in out:
            continue
        out.append(stripped)
        if len(out) >= limit:
            break
    return out


def inherited_plot_report(parent_dir: Any, limit: int = 8) -> str:
    """把父代未回收伏笔整理成一份 Markdown 待办（供写入子代）。"""
    if not parent_dir:
        return ""
    path = Path(parent_dir) / "memory" / "global_summary.txt"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"[lineage] 读取父代全局摘要失败（已跳过伏笔继承）: {e}")
        return ""
    items = extract_unresolved_plots(text, limit=limit)
    if not items:
        return ""
    lines = ["# 前代未回收伏笔（自父代全局摘要抽取，供续集处理）", ""]
    lines.extend(f"- [ ] {item}" for item in items)
    return "\n".join(lines) + "\n"


def describe_plan_items(plan: InheritancePlan) -> Iterable[str]:
    """把继承计划摊平成可逐行显示的文本（面板用）。"""
    for dim in INHERIT_DIMENSIONS:
        entry = plan.items.get(dim) or {}
        if entry.get("skipped"):
            yield f"✗ {dim}：不继承"
            continue
        copies = entry.get("copy") or []
        missing = entry.get("missing") or []
        detail = f"复制 {len(copies)} 项" if copies else "无可复制项"
        if missing:
            detail += f"，父代缺失：{'、'.join(missing)}"
        yield f"✓ {dim}：{detail}"


# ====================================================================== 执行继承


def parent_last_chapter(parent_dir: Any) -> int:
    """父代的"最后一章"章号：优先 `meta.chapter_count`，否则数 `chapters/` 下的文件。

    用于判断"哪些角色在父代范围内已经死亡"（见 `apply_death_status`）。
    """
    if not parent_dir:
        return 0
    root = Path(parent_dir)
    meta, status = read_json_with_backup(root / "meta.json", default=None)
    if status != "corrupt" and isinstance(meta, Mapping):
        for key in ("chapter_count", "total_chapters"):
            value = _as_int(meta.get(key))
            if value:
                return value
    chapters_dir = root / "chapters"
    if not chapters_dir.exists():
        return 0
    numbers = []
    for path in chapters_dir.glob("*.txt"):
        # 章节文件命名是 `chapter_0001.txt`：取**最后一段**数字，
        # 不能取第一段（`chapter` 后面才是章号）。
        found = _DIGITS_RE.findall(path.stem)
        if found:
            numbers.append(int(found[-1]))
    return max(numbers) if numbers else 0


def make_character_transform(
    era_gap_years: int = 0,
    last_chapter: int = 0,
    notes: list[str] | None = None,
) -> Callable[[Mapping[str, Any]], dict]:
    """造一个「年龄推进 + 死亡转状态」的变换函数，**专供 `mutate_characters` 使用**。

    为什么不直接返回结果字典：角色写盘必须走 `MemoryManager.mutate_characters`
    （锁内读-改-写 + 三道闸门），任何绕过它的写法都可能把 286 个角色覆盖掉。
    这里只产出"纯变换"，由调用方交给 `mutate_characters` 执行。
    """
    sink = notes if notes is not None else []

    def transform(characters: Mapping[str, Any]) -> dict:
        aged, age_notes = apply_age_progression(characters, era_gap_years)
        final, death_notes = apply_death_status(aged, last_chapter)
        sink.extend(age_notes)
        sink.extend(death_notes)
        return final

    return transform


def inherit_into_child(
    child_dir: Any,
    parent_dir: Any,
    inherited: Mapping[str, bool] | None = None,
    plots_filename: str = "inherited_plots.md",
) -> dict:
    """按继承计划把父代数据搬进子代。**每一次写入都过 `guard_child_path`**。

    角色年龄/状态**不在这里改**：那必须走 `MemoryManager.mutate_characters`
    （见 `make_character_transform`）。本函数只做文件复制与伏笔清单落盘。

    Returns:
        `{copied: [...], missing: [...], plots_file: str|None, plan: InheritancePlan}`
    """
    if not child_dir or not parent_dir:
        return {"copied": [], "missing": [], "plots_file": None, "plan": None}

    plan = plan_inheritance(parent_dir, inherited)
    parent_p = Path(parent_dir)
    copied: list[str] = []
    missing: list[str] = []

    for dim in INHERIT_DIMENSIONS:
        entry = plan.items.get(dim) or {}
        if entry.get("skipped"):
            continue
        for rel in DIMENSION_SOURCES[dim]:
            if rel not in (entry.get("copy") or []):
                missing.append(rel)
                continue
            try:
                dst = copy_into_child(child_dir, parent_p / rel, rel)
            except (OSError, ValueError) as e:
                # 护栏拒绝或磁盘错误：如实记录，绝不"绕过护栏再试一次"
                logger.error(f"[lineage] 继承 {rel} 失败: {type(e).__name__}: {e}")
                missing.append(rel)
                continue
            if dst is not None:
                copied.append(rel)

    plots_file: str | None = None
    if plan.inherited.get("plots"):
        report = inherited_plot_report(parent_dir)
        if report:
            target = Path(child_dir) / plots_filename
            try:
                guard_child_path(child_dir, target)
                atomic_write_text(target, report)
                plots_file = plots_filename
            except (OSError, ValueError) as e:
                logger.error(f"[lineage] 写入伏笔清单失败: {type(e).__name__}: {e}")

    # 去重但保序
    seen: set[str] = set()
    copied = [x for x in copied if not (x in seen or seen.add(x))]
    seen = set()
    missing = [x for x in missing if not (x in seen or seen.add(x))]

    return {"copied": copied, "missing": missing, "plots_file": plots_file, "plan": plan}

