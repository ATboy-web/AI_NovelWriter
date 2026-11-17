"""风格 DNA —— 把「作者本人的写法」变成**可读取、可比对**的数据。

## 它解决的问题

预设里有一条规范："有风格文档先读文档，冲突以风格文档为准 —— 那个作者本来就爱用
破折号，就不按指纹规则删。" 这句话在 v1 里只是**一段文字**，完全靠模型自觉：

- 模型看不到文档（没有被注入），等于没生效；
- 模型看到了，也无法判断"这篇是不是偏离了作者风格"；
- 更糟的是，质检仍会按通用门禁把破折号标成超标，**和规范直接打架**。

本模块做三件事，缺一不可：

1. **读**：把 `风格DNA.json` 解析成结构化指纹（不是让人再读一遍散文）；
2. **注入**：把指纹压成一小段提示词，明确告诉模型"这些是你的特征，不要按通用规则删"；
3. **比对**：`style_drift()` 给出人称一致性、句长偏离、爱用标点、禁词的**数字**，
   让质检能回答"这篇偏离了作者多少"，而不是"感觉不太像"。

## 为什么是 JSON 而不是 Markdown

已有的写法是 `语言DNA.md` 这类散文文档。散文对模型友好，对**程序**不友好：
要拿它做门禁，就得再写一个"从散文里猜规则"的解析器（猜错没人发现）。
JSON 则可以被测试钉住、被工具校准、被版本控制 diff。

两者不冲突：`load_style_dna()` 允许同目录存在 `语言DNA.md` 等散文文档，
并把它的**存在**与路径带进提示词（"参考文档在 X，冲突以它为准"）——
但**机器判据只认 JSON**。这是"人读的归文档、机判的归数据"的明确分工。

## 与预设门禁的关系（关键）

DNA 里声明 `favorite_marks` 含 `——` 时，质检**自动把破折号项从 review 降为
style_allowed**：它不再是"未达项"，而是"作者特征"。这正是"冲突以风格文档为准"
的代码化 —— 否则用户永远会看到一条自己决定过、却被系统反复提示的红字。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .storage import atomic_write_json

__all__ = [
    "DRIFT_LABELS",
    "PRONOUN_GROUPS",
    "StyleDNA",
    "StyleDrift",
    "default_dna_filename",
    "find_dna_file",
    "load_style_dna",
    "parse_style_dna",
    "save_dna_template",
    "style_prompt",
]

#: 风格 DNA 的标准文件名（唯一来源）。
_DNA_FILENAMES = ("风格DNA.json", "style_dna.json", "语言DNA.json")

#: 同目录下的散文风格文档（只用于提示词里的"请参考"，不参与机判）。
_PROSE_FILENAMES = ("语言DNA.md", "风格DNA.md", "写作风格指南.md", "STYLE.md")

#: 人称代词分组。用于检测"同一篇里人称混用"。
PRONOUN_GROUPS: Dict[str, Tuple[str, ...]] = {
    "第一人称": ("我们", "我"),
    "第二人称": ("你们", "你"),
    "第三人称": ("他们", "她们", "它们", "他", "她", "它"),
}

#: 漂移项的展示名。
DRIFT_LABELS: Dict[str, str] = {
    "person": "人称一致性",
    "sentence": "句长偏离",
    "marks": "爱用标点",
    "banned": "禁词",
}

#: 句长偏离的容忍带宽（相对均值）。超出即视为偏离。
_SENTENCE_TOLERANCE = 0.25

#: 单次注入的 DNA 提示词上限（它必须短 —— 预算要留给规则）。
_DNA_PROMPT_BUDGET = 260


# ====================================================================== 数据模型


@dataclass(frozen=True)
class StyleDNA:
    """一份风格指纹。

    字段刻意少而硬：每个字段都必须能**驱动一个判断**，否则就是装饰。
    """

    name: str = ""
    person: str = ""
    tone: str = ""
    #: 句长偏好：`mean` 为目标均值（汉字数），`cv` 为可接受离散度。
    sentence_mean: float = 0.0
    sentence_cv: float = 0.0
    #: 作者爱用的标点。命中这些标点**不按 AI 指纹处理**。
    favorite_marks: Tuple[str, ...] = ()
    #: 禁词（作者明确不用 / 团队规范禁用）。
    banned_words: Tuple[str, ...] = ()
    #: 散文参考文档的路径（存在才填）。只进提示词，不参与机判。
    prose_reference: str = ""
    notes: str = ""
    #: 解析时遇到的问题（缺字段、类型不对）。**不抛异常**，由调用方决定怎么展示。
    warnings: Tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """没有任何可用指纹 ⇒ 视为"未配置"，不注入、不比对。"""
        return not any(
            (
                self.person,
                self.tone,
                self.sentence_mean,
                self.favorite_marks,
                self.banned_words,
            )
        )

    def allows_mark(self, mark: str) -> bool:
        """该标点是否为作者特征（质检据此放行）。"""
        return any(mark == item or mark in item for item in self.favorite_marks)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "person": self.person,
            "tone": self.tone,
            "sentence": {"mean": self.sentence_mean, "cv": self.sentence_cv},
            "favorite_marks": list(self.favorite_marks),
            "banned_words": list(self.banned_words),
            "prose_reference": self.prose_reference,
            "notes": self.notes,
        }


@dataclass
class StyleDrift:
    """一次风格比对的结果。

    `ok` 只汇总**确定性偏离**（人称混用、禁词命中）；
    句长与标点密度属于统计项，`ok` 不看它们 —— 与技能包"不为节奏改句长"一致。
    """

    person: Dict[str, Any] = field(default_factory=dict)
    sentence: Dict[str, Any] = field(default_factory=dict)
    marks: Dict[str, Any] = field(default_factory=dict)
    banned: Dict[str, Any] = field(default_factory=dict)
    #: 人称是否作为**硬约束**。只对虚构叙事成立：
    #: 技术文章里"我"（作者自称）与"你"（泛指读者）并存是正常写法，
    #: 拿小说的标准去判它，会把合格稿判成硬伤。
    person_strict: bool = False

    @property
    def ok(self) -> bool:
        person_ok = self.person.get("ok", True) if self.person_strict else True
        banned_ok = self.banned.get("ok", True)
        return bool(person_ok and banned_ok)

    @property
    def issues(self) -> List[str]:
        found: List[str] = []
        if self.person_strict and not self.person.get("ok", True):
            found.append(f"人称混用：{self.person.get('detail', '')}")
        if not self.banned.get("ok", True):
            words = "、".join(self.banned.get("hits", [])[:5])
            found.append(f"命中禁词：{words}")
        return found

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": self.issues,
            "person_strict": self.person_strict,
            "person": self.person,
            "sentence": self.sentence,
            "marks": self.marks,
            "banned": self.banned,
        }


# ====================================================================== 解析


def default_dna_filename() -> str:
    """标准文件名（写模板时用）。"""
    return _DNA_FILENAMES[0]


def find_dna_file(novel_dir: Any) -> Optional[Path]:
    """在作品目录里找风格 DNA。返回第一个命中的 JSON 文件。"""
    if not novel_dir:
        return None
    base = Path(novel_dir)
    for name in _DNA_FILENAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def _find_prose_reference(novel_dir: Any) -> str:
    """找同目录的散文风格文档（只记路径，供提示词引用）。"""
    if not novel_dir:
        return ""
    base = Path(novel_dir)
    for name in _PROSE_FILENAMES:
        candidate = base / name
        if candidate.is_file():
            return str(candidate)
    return ""


def _as_tuple(value: Any) -> Tuple[str, ...]:
    """把任意输入收敛成字符串元组（容忍单字符串 / 列表 / None）。"""
    if value is None:
        return ()
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[,，、\s]+", value) if part.strip()]
        return tuple(items)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_style_dna(data: Any, prose_reference: str = "") -> StyleDNA:
    """把 JSON 数据解析成 `StyleDNA`。**永不抛异常**。

    容错策略：类型不对的字段丢弃并记 `warnings`，
    因为一份写坏的 DNA 不应该让整篇生成失败 —— 但也不能静默当"没配置"，
    否则用户以为自己设了禁词、实际一个字都没生效。
    """
    warnings: List[str] = []
    if not isinstance(data, dict):
        return StyleDNA(prose_reference=prose_reference, warnings=("风格 DNA 根节点不是对象",))

    name = str(data.get("name", "") or "").strip()
    person = str(data.get("person", "") or data.get("人称", "") or "").strip()
    tone = str(data.get("tone", "") or data.get("语气", "") or "").strip()

    sentence = data.get("sentence") or data.get("句长") or {}
    if isinstance(sentence, dict):
        mean = _as_float(sentence.get("mean", sentence.get("均值", 0)))
        cv = _as_float(sentence.get("cv", sentence.get("离散度", 0)))
    else:
        mean, cv = _as_float(sentence), 0.0
        if sentence:
            warnings.append("sentence 应为对象（含 mean / cv），已按数字解释")

    marks = _as_tuple(data.get("favorite_marks") or data.get("爱用标点"))
    banned = _as_tuple(data.get("banned_words") or data.get("禁词"))

    if not marks and data.get("favorite_marks") is not None:
        warnings.append("favorite_marks 为空或类型无法识别")
    if not banned and data.get("banned_words") is not None:
        warnings.append("banned_words 为空或类型无法识别")

    # 人称必须是"可判"的：认不出就警告（否则一致性检查无从下手）
    if person and not any(group in person for group in PRONOUN_GROUPS):
        warnings.append(f"person「{person}」不在已知人称分组内，人称一致性检查将跳过")

    return StyleDNA(
        name=name,
        person=person,
        tone=tone,
        sentence_mean=mean,
        sentence_cv=cv,
        favorite_marks=marks,
        banned_words=banned,
        prose_reference=prose_reference or str(data.get("prose_reference", "") or ""),
        notes=str(data.get("notes", "") or data.get("备注", "") or "").strip(),
        warnings=tuple(warnings),
    )


def load_style_dna(novel_dir: Any) -> Optional[StyleDNA]:
    """读取作品的风格 DNA。未配置或读取失败时返回 `None`（调用方按"无 DNA"处理）。

    ❗ 只在**真的存在文件**时返回对象：让"未配置"与"配置了但全空"走不同分支，
    否则每个作品都会莫名其妙带上一个空 DNA 的警告。
    """
    path = find_dna_file(novel_dir)
    prose = _find_prose_reference(novel_dir)
    if path is None:
        if prose:
            # 只有散文文档：给一份"仅参考"的 DNA，让提示词能引用它
            return StyleDNA(prose_reference=prose)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f"[风格DNA] 读取失败（{path.name}）：{exc}")
        return StyleDNA(prose_reference=prose, warnings=(f"读取失败：{exc}",))
    return parse_style_dna(data, prose_reference=prose)


def save_dna_template(novel_dir: Any, overwrite: bool = False) -> Tuple[bool, str]:
    """在作品目录写一份**带注释的模板**（不覆盖已有文件，除非显式要求）。"""
    base = Path(novel_dir) if novel_dir else None
    if base is None:
        return False, "没有打开的作品"
    target = base / default_dna_filename()
    if target.exists() and not overwrite:
        return False, f"已存在 {target.name}，未覆盖"
    template = {
        "name": "（示例）作者的写作指纹",
        "person": "第三人称限知",
        "tone": "冷静克制，少用形容词",
        "sentence": {"mean": 22, "cv": 0.45},
        "favorite_marks": ["——", "……"],
        "banned_words": ["赋能", "闭环", "抓手"],
        "notes": "破折号是我本人的习惯，不要按 AI 指纹规则删除。",
    }
    try:
        atomic_write_json(target, template, indent=2)
    except OSError as exc:
        return False, f"写入失败：{exc}"
    return True, f"已写入 {target.name}"


# ====================================================================== 注入


def style_prompt(dna: Optional[StyleDNA], budget: int = _DNA_PROMPT_BUDGET) -> str:
    """把 DNA 压成一小段提示词。**没有可用指纹时不返回任何内容**。

    措辞刻意都是"约束"而非"建议"：模型对"建议"的服从度远低于"不得"。
    """
    if dna is None or (dna.is_empty and not dna.prose_reference):
        return ""
    lines: List[str] = ["【作者风格 DNA】"]
    if dna.name:
        lines.append(f"指纹：{dna.name}")
    if dna.person:
        lines.append(f"人称：{dna.person}（全篇不得中途换人）")
    if dna.tone:
        lines.append(f"语气：{dna.tone}")
    if dna.sentence_mean:
        cv = f"，离散度约 {dna.sentence_cv:g}" if dna.sentence_cv else ""
        lines.append(f"句长：均值约 {dna.sentence_mean:g} 汉字{cv}（保持自己的节奏，不刻意参差）")
    if dna.favorite_marks:
        marks = "、".join(dna.favorite_marks)
        lines.append(f"爱用标点：{marks} —— **这是作者特征，不按 AI 指纹规则删改**")
    if dna.banned_words:
        words = "、".join(dna.banned_words)
        lines.append(f"禁词（不得出现）：{words}")
    if dna.prose_reference:
        lines.append(f"参考文档：{Path(dna.prose_reference).name}（冲突时以文档为准）")
    if dna.notes:
        lines.append(f"备注：{dna.notes}")

    text = "\n".join(lines)
    if len(text) > budget:
        text = text[: max(0, budget - 1)].rstrip() + "…"
    return text


# ====================================================================== 比对


def _split_sentences(text: str) -> List[str]:
    """按行切句。刻意不用 `re.split` 带换行转义（避免转义坑），逐行处理。"""
    sentences: List[str] = []
    for line in (text or "").splitlines():
        for piece in re.split(r"[。！？!?]+", line):
            stripped = piece.strip()
            if len(re.sub(r"\s", "", stripped)) >= 2:
                sentences.append(stripped)
    return sentences


def _count_pronouns(text: str) -> Dict[str, int]:
    """数各人称代词的出现次数（长词优先，避免"我们"被算成"我"）。"""
    body = text or ""
    counts: Dict[str, int] = {}
    for group, words in PRONOUN_GROUPS.items():
        total = 0
        remaining = body
        for word in words:  # PRONOUN_GROUPS 内已按长词在前排列
            total += remaining.count(word)
            remaining = remaining.replace(word, "")
        counts[group] = total
    return counts


def style_drift(text: str, dna: Optional[StyleDNA], person_strict: bool = False) -> Optional[StyleDrift]:
    """比对文本与风格 DNA。`dna` 为空时返回 `None`（没有基准就没有偏离）。

    Args:
        person_strict: 人称混用是否算硬偏离。**只应由虚构叙事预设传 True**
            （见 `StyleDrift.person_strict` 的说明）。
    """
    if dna is None or dna.is_empty:
        return None

    # ---- 1) 人称一致性：以 DNA 指定的人称为主，出现别的人称占比过高即混用
    person_info: Dict[str, Any] = {"ok": True, "detail": ""}
    counts = _count_pronouns(text)
    if dna.person:
        target = next((g for g in PRONOUN_GROUPS if g in dna.person), "")
        if target:
            total = sum(counts.values())
            present = [g for g, n in counts.items() if n > 0]
            if total and len(present) > 1:
                minority = [g for g in present if g != target]
                minority_total = sum(counts[g] for g in minority)
                ratio = minority_total / total
                # 少量"我"出现在对话里是正常的：只有占比 >20% 才判混用
                if ratio > 0.20:
                    person_info = {
                        "ok": False,
                        "detail": (
                            f"设定为{dna.person}，但其它人称占 {ratio:.0%}（{('、'.join(minority))}）；若非对话需统一"
                        ),
                        "ratio": round(ratio, 3),
                        "counts": counts,
                    }
    # ---- 2) 句长偏离：只看均值出界，不看离散度（技能包明确"不为参差改句长"）
    sentence_info: Dict[str, Any] = {"ok": True, "detail": ""}
    if dna.sentence_mean:
        lengths = [len(re.sub(r"\s", "", s)) for s in _split_sentences(text)]
        if lengths:
            mean = sum(lengths) / len(lengths)
            low = dna.sentence_mean * (1 - _SENTENCE_TOLERANCE)
            high = dna.sentence_mean * (1 + _SENTENCE_TOLERANCE)
            out_of_band = not (low <= mean <= high)
            sentence_info = {
                "ok": not out_of_band,
                "mean": round(mean, 1),
                "expected": dna.sentence_mean,
                "band": [round(low, 1), round(high, 1)],
                "detail": (f"实测 {mean:.1f} 字，目标 {dna.sentence_mean:g} 字（容许 {low:.1f}–{high:.1f}）"),
            }

    # ---- 3) 爱用标点：作者特征是否出现（缺失只提示，不判不合格）
    marks_info: Dict[str, Any] = {"ok": True, "detail": "", "counts": {}}
    if dna.favorite_marks:
        counts_marks = {mark: (text or "").count(mark) for mark in dna.favorite_marks}
        marks_info = {
            "ok": any(counts_marks.values()),
            "detail": "、".join(f"{k}×{v}" for k, v in counts_marks.items()),
            "counts": counts_marks,
            # 缺失不是错：可能这篇本身不需要破折号。只在报告里显示数字。
            "advisory": not any(counts_marks.values()),
        }

    # ---- 4) 禁词：硬约束
    banned_hits = [word for word in dna.banned_words if word and word in (text or "")]
    banned_info: Dict[str, Any] = {
        "ok": not banned_hits,
        "hits": banned_hits,
        "detail": "" if not banned_hits else f"出现 {len(banned_hits)} 个禁词",
    }

    return StyleDrift(
        person=person_info,
        sentence=sentence_info,
        marks=marks_info,
        banned=banned_info,
        person_strict=person_strict,
    )


def format_drift(drift: Optional[StyleDrift]) -> str:
    """把漂移结果渲染成人读文本（质检报告的一段）。"""
    if drift is None:
        return ""
    lines = ["──────── 风格 DNA 比对 ────────"]
    if drift.person.get("detail"):
        if drift.person.get("ok", True):
            mark = "✅"
        else:
            # 非叙事体裁里人称混用只提示，不算硬伤
            mark = "❌" if drift.person_strict else "⚠️"
        lines.append(f"{mark} 人称：{drift.person['detail']}")
    if drift.sentence.get("detail"):
        mark = "✅" if drift.sentence.get("ok", True) else "⚠️"
        lines.append(f"{mark} 句长：{drift.sentence['detail']}")
    if drift.marks.get("detail"):
        mark = "·" if drift.marks.get("advisory") else "✅"
        lines.append(f"{mark} 爱用标点：{drift.marks['detail']}（作者特征，不算 AI 味）")
    if drift.banned.get("hits"):
        lines.append(f"❌ 禁词：{'、'.join(drift.banned['hits'])}")
    elif drift.banned:
        lines.append("✅ 禁词：无")
    return "\n".join(lines)
