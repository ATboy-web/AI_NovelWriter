"""世代传承的**领域层**：代际记录、继承维度、角色推进与伏笔抽取。

## 为什么从 `app/lineage.py` 搬到这里

原 `lineage.py`（821 行）把四类东西装在同一个文件里：

1. **领域规则** —— 「子代只读父代」的路径判定、年龄推进、死亡标记、伏笔抽取
2. **文件读写** —— 读 `meta.json`、遍历 `timelines/branch_*`、拷贝目录
3. **用例编排** —— 代际树、继承计划
4. **表现形态** —— 给面板用的 dict

其中第 1 类**完全不需要磁盘**（`is_within` 用的是 `Path.resolve()` 纯计算），
却因为和 IO 混在一起，只能靠"造目录"来测。搬出来之后可以穷举边界。

## 边界

本模块**只允许标准库**（`dataclasses` / `pathlib` / `typing` / `re`）。
`tests/test_architecture_layers.py` 会扫源码断言这一点 —— 一旦 import 了
`app.storage` 或任何上层模块，测试立刻变红。

文件读写仍留在 `app/lineage.py`（它现在同时充当兼容层）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "LINEAGE_KEY",
    "SCOPE_READONLY_PARENT",
    "KIND_NOVEL",
    "KIND_BRANCH",
    "INHERIT_DIMENSIONS",
    "DIMENSION_SOURCES",
    "DEFAULT_INHERITED",
    "LineageRecord",
    "InheritancePlan",
    "apply_age_progression",
    "apply_death_status",
    "extract_unresolved_plots",
    "unresolved_plot_keywords",
    "describe_plan_items",
    "make_character_transform",
    "dedupe_preserve_order",
    "is_within",
]

#: 从文件名/字符串里提取全部数字段（`chapter_0001` → ["0001"]）
_DIGITS_RE = re.compile(r"\d+")

#: `meta.json` 里存放代际信息的键
LINEAGE_KEY = "lineage"

#: 子代对父代的唯一合法关系：**只读**
SCOPE_READONLY_PARENT = "readonly_parent"

#: 节点类型：一本独立作品 / 一个分支子项目（同一部作品的另一条世界线）
KIND_NOVEL = "novel"
KIND_BRANCH = "branch"

#: 分支子项目在父代作品里的存放位置：`<父代>/timelines/branch_%03d/`
BRANCH_PARENT_REL = "timelines"
BRANCH_PREFIX = "branch_"

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


@dataclass
class LineageRecord:
    """一本小说在世代链上的位置（对应 `meta.json` 的 `lineage` 字段）。

    `kind` 区分两种节点：
    - `novel`（默认）—— 一部独立作品，`generation` 表示"第几代"；
    - `branch` —— **同一代里的另一条世界线**（`timelines/branch_%03d/`）。
      它不是"下一代"，因此 `generation` 与父代**相同**，靠 `branch_of` / `branch_id` 定位。
    """

    generation: int = 1
    parent_novel: str = ""
    parent_title: str = ""
    era_gap_years: int = 0
    inherited: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_INHERITED))
    child_scope: str = SCOPE_READONLY_PARENT
    #: `novel` | `branch`
    kind: str = KIND_NOVEL
    #: 分支编号（`branch_003` → `"003"`）；非分支为空
    branch_id: str = ""
    #: 分支从第几章分叉
    origin_chapter: int = 0

    @property
    def is_root(self) -> bool:
        """第 1 代 = 没有父代。"""
        return self.generation <= 1 or not self.parent_novel

    @property
    def is_branch(self) -> bool:
        return self.kind == KIND_BRANCH

    def as_dict(self) -> dict:
        return {
            "generation": int(self.generation),
            "parent_novel": str(self.parent_novel or ""),
            "parent_title": str(self.parent_title or ""),
            "era_gap_years": int(self.era_gap_years or 0),
            "inherited": {k: bool(v) for k, v in (self.inherited or {}).items()},
            "child_scope": str(self.child_scope or SCOPE_READONLY_PARENT),
            "kind": str(self.kind or KIND_NOVEL),
            "branch_id": str(self.branch_id or ""),
            "origin_chapter": int(self.origin_chapter or 0),
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

        kind = str(raw.get("kind", KIND_NOVEL) or KIND_NOVEL)
        if kind not in (KIND_NOVEL, KIND_BRANCH):
            kind = KIND_NOVEL
        try:
            origin_chapter = int(raw.get("origin_chapter", 0) or 0)
        except (TypeError, ValueError):
            origin_chapter = 0

        return cls(
            generation=max(generation, 1),
            parent_novel=str(raw.get("parent_novel", "") or ""),
            parent_title=str(raw.get("parent_title", "") or ""),
            era_gap_years=gap,
            inherited=inherited,
            child_scope=str(raw.get("child_scope", SCOPE_READONLY_PARENT) or SCOPE_READONLY_PARENT),
            kind=kind,
            branch_id=str(raw.get("branch_id", "") or ""),
            origin_chapter=origin_chapter,
        )


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
            projected = age + years
            # 年代差为负（往更早的年代推）时可能算出负年龄 —— 那是数据不成立，
            # 不是"角色回到出生前"。夹到 0 并在说明里写明推算值，便于人工核对。
            if projected < 0:
                notes.append(f"{name}：{age} → 0 岁（按 {years:+d} 年推算为 {projected}，已夹到 0）")
                projected = 0
            else:
                notes.append(f"{name}：{age} → {projected} 岁")
            info["age"] = projected
        else:
            info["age"] = age
        out[str(name)] = info
    return out, notes


def apply_death_status(characters: Mapping[str, Any], last_chapter: int) -> tuple[dict, list[str]]:
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


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    """去重但保留首次出现顺序。

    单独抽成函数而不是写 `[x for x in xs if not (x in seen or seen.add(x))]` ——
    那个技巧虽然能跑，但 mypy 会（正确地）报「set.add 不返回值」，
    而且下次读代码的人要停下来想一遍。
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
