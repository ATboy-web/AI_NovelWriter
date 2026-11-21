"""语义层候选抽取 —— 把「要模型判读的东西」先抽出来，而不是让它凭印象找。

## 为什么需要这一步

预设里有 5 条语义层规则（同义重命名 / 衔接连环 / 结论冒号 / 相邻句同构 /
高度同构三连）。它们**不能用正则判**：判「优化」和「提升」指的是不是同一件事，
只能理解句意。

但"不能用正则判"不等于"什么都不做"。技能包的实测结论是：
**脚本先抽候选，模型只对候选逐条打标**。这样做的价值是：

| 只有规则文本 | 有候选抽取 |
|---|---|
| 模型通读全文，凭印象挑几处 | 候选有固定清单，漏了能看出来 |
| 不知道有没有漏 | 抽了 40 条，判了 40 条，可对账 |
| 每篇标准不一 | 判据是封闭标签集，逐条独立判 |

所以本模块**只做抽取，不做判定**：输出 `候选 + 上下文定位 + 判读说明`，
`label` / `confidence` / `reason` 三个字段留给模型填。

## 抽什么、为什么这样抽

| 项 | 抽法 | 为什么不做得更"智能" |
|---|---|---|
| 同义重命名 | 段内命中 **2 个以上不同近义族** | 真同义判断需要世界知识；抽"段"是可靠的，抽"同义词"不可靠 |
| 衔接连环 | 段首承接词连续 ≥6 | 承接词本身可数；"是不是零跳转"要看语义 |
| 结论冒号 | 冒号前 ≤20 字的句子全抽 | 冒号总量人类更多，只有"结论提示"类是信号，需模型分类 |
| 相邻句同构 / 三连 | 句结构签名连续相同 | 宽口径排比无区分力，只抽"高度同构"（长度桶+标点骨架一致） |

## 判读纪律（写在数据里，不只写在文档里）

43 万次打标的教训被固化成 `JUDGE_RULES`：只按判据判、每条独立判、
拿不准选兜底标签、禁止自造标签。模型拿到候选 JSON 时这段也会一起给它 ——
否则"判据"只存在于技能包的 md 里，模型未必去读。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger

__all__ = [
    "JUDGE_LABELS",
    "JUDGE_RULES",
    "SYNONYM_FAMILIES",
    "SemanticCandidates",
    "extract_candidates",
    "format_candidates",
    "load_candidates",
    "semantic_summary",
    "split_paragraphs",
    "split_sentences",
    "write_candidates",
]

#: 五类候选 → 展示名（与 `writing_presets.SEMANTIC_CHECKS` 的 key 对齐）。
JUDGE_LABELS: Dict[str, str] = {
    "rename": "同义重命名（段级）",
    "cohesion": "衔接连环过长",
    "colon_judge": "结论提示冒号",
    "iso_pair": "相邻句结构同款",
    "iso3": "高度同构三连",
}

#: 允许的判读标签（**封闭集**，禁止自造）。空串 = 未判读。
JUDGE_LABELS_VALUES: Tuple[str, ...] = ("hit", "miss", "unsure")

#: 判读纪律（附在候选 JSON 里一起交给模型）。
JUDGE_RULES: Tuple[str, ...] = (
    "只按判据判，不按整体感觉打分 —— 整体印象会带上你自己的写作偏好",
    "每条独立判断，不看全文 —— 看过全文会产生『这篇就是 AI 味重』的先验",
    "拿不准一律选 unsure（兜底），不要猜 hit 也不要猜 miss",
    "禁止自造标签：只能用 hit / miss / unsure",
    "判 miss 也要留 reason —— 阴性判读同样是证据，要计入『原始候选→有效命中』的差额",
)

#: 近义族：同一族内是「同一个概念的不同说法」。
#:
#: 刻意**小而硬**：只收实测高频、且替换后语义不变的族。族越大越容易误报
#: （"提升"和"提高"可互换，但"提升"和"改善"在部分语境下不等价）。
SYNONYM_FAMILIES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("提升", ("提升", "提高", "增强", "强化", "加强")),
    ("优化", ("优化", "改进", "改善", "完善")),
    ("实现", ("实现", "达成", "完成", "落地")),
    ("导致", ("导致", "造成", "引发", "带来", "引起")),
    ("关键", ("关键", "核心", "重点", "要害")),
    ("能力", ("能力", "实力", "本领")),
    ("方案", ("方案", "策略", "办法", "路径")),
    ("问题", ("问题", "痛点", "难点", "瓶颈")),
    ("团队", ("团队", "小组", "班组", "队伍")),
    ("项目", ("版图", "基地", "项目", "节点")),
)

#: 段首承接词（判"衔接连环"用）。命中即算一个"明确承接"接口。
#:
#: ❗ 这是**下界估计**：真正的"是否承接上一段"要读语义，词表只能覆盖显式标记。
#: 因此宁可漏、不可滥 —— 漏了只是候选少一条；误报会让用户去改本来就通顺的衔接。
#: 表内按"从长到短"排列，避免短词抢匹配（`这也意味着` 不该被 `这` 吃掉）。
_COHESION_OPENERS = (
    "这也解释了为什么",
    "这也解释了",
    "这也是为什么",
    "这也意味着",
    "这也说明",
    "这意味着",
    "这说明",
    "这正是",
    "这就是为什么",
    "这就是",
    "这就是为什么说",
    "从这个角度看",
    "从这个角度",
    "在这个意义上",
    "在这种意义上",
    "换句话说",
    "也就是说",
    "换句话说就是",
    "在此基础上",
    "与此同时",
    "更重要的是",
    "另一方面",
    "具体来说",
    "归根结底",
    "由此看来",
    "由此",
    "因此",
    "所以",
    "于是",
    "那么",
    "接下来",
    "同样的道理",
    "相应地",
    "进一步说",
    "结果是",
)

#: 连环达到这个长度才成为候选（技能包口径：连续 ≥6 个明确承接）。
COHESION_THRESHOLD = 6

#: 冒号句的"提示语"最大长度（冒号前的字数）。超过就不像"一句话总结"。
COLON_PREFIX_MAX = 20

#: 结构签名的长度分桶宽度（字）。桶越窄，同构判定越严。
_LEN_BUCKET = 8

#: 单类候选的上限 —— 防止长文把候选撑到几百条淹没判读。
MAX_PER_KIND = 80


# ====================================================================== 切分


def split_paragraphs(text: str) -> List[str]:
    """委托 `app.parsing.split_paragraphs`（与 `writing_presets.structure_metrics` 同口径）。"""
    from .parsing import split_paragraphs as _split_paragraphs

    return _split_paragraphs(text, merge_lines=True)


#: 句子的最小字数。低于它视为碎片（"好。"），不参与切分统计。
_MIN_SENTENCE_CHARS = 2

#: 同构判定时的句子最小字数。
#:
#: 只排除 2–3 字的碎片（"他来了。"）—— 技能包的真实反例
#: 「叫什么名字？／承载什么功能？／嵌入哪个生态？」只有 5–6 字，
#: 却是最典型的高度同构三连，门槛不能把它们挡掉。
_MIN_ISO_CHARS = 4


def split_sentences(paragraph: str) -> List[str]:
    """把一段切成句子（按中文句末标点）。纯空白句与碎片丢弃。"""
    sentences: List[str] = []
    for piece in re.split(r"[。！？!?]+", paragraph or ""):
        stripped = piece.strip("　 	，,；;：:")
        if len(re.sub(r"\s", "", stripped)) >= _MIN_SENTENCE_CHARS:
            sentences.append(stripped)
    return sentences


# ====================================================================== 候选结构


@dataclass
class SemanticCandidates:
    """一次抽取的全部候选。每项都带 `label`/`reason` 空位，等模型填。"""

    items: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    paragraphs: int = 0
    hanzi: int = 0
    #: 分布统计（不属"候选"，但汇总口径要用）。
    #: 典型：`{"cohesion_streaks": [...], "max_chain": 4}` —— 最长连环必须来自
    #: **全部连环**，只数 ≥6 的候选会让"这篇有 4 连环"永远显示成 0。
    extra: Dict[str, Any] = field(default_factory=dict)

    def add(self, kind: str, payload: Dict[str, Any]) -> None:
        if len(self.items.get(kind, [])) >= MAX_PER_KIND:
            return
        payload.setdefault("label", "")
        payload.setdefault("reason", "")
        self.items.setdefault(kind, []).append(payload)

    def get(self, kind: str) -> List[Dict[str, Any]]:
        return self.items.get(kind, [])

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.items.values())

    @property
    def judged(self) -> int:
        """已填 label 的条数（用于"抽了多少 / 判了多少"对账）。"""
        return sum(1 for v in self.items.values() for item in v if item.get("label"))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "meta": {
                "paragraphs": self.paragraphs,
                "hanzi": self.hanzi,
                "total": self.total,
                "judged": self.judged,
            },
            "extra": dict(self.extra),
            "judge_rules": list(JUDGE_RULES),
            "allowed_labels": list(JUDGE_LABELS_VALUES),
            "candidates": {kind: list(items) for kind, items in self.items.items()},
        }


# ====================================================================== 抽取


def _preview(text: str, limit: int = 60) -> str:
    body = re.sub(r"\s+", " ", text or "").strip()
    return body[:limit] + ("…" if len(body) > limit else "")


def _find_rename(paragraphs: Sequence[str]) -> List[Dict[str, Any]]:
    """同义重命名候选：**同一近义族内**出现 2 个以上不同词。

    ❗ 判据只在族内，不在族间。实测踩过的误报：把「方案」与「问题」各出现一次
    判成"重命名"—— 可它们是两个不同概念，读者不需要做「X 就是 Y」的连接。
    真正的信号是「优化…提升…增强」这种**同一个意思换着说**，即同族内多词并存。

    只抽"段"不抽"词对"：判断「这两个词指同一件事」需要理解句意，
    而"这一段里同族多词并存"是可以数的 —— 后者正是候选的用途。
    """
    found: List[Dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs, 1):
        hits: List[Dict[str, Any]] = []
        for family, words in SYNONYM_FAMILIES:
            matched = [word for word in words if word in paragraph]
            if len(matched) >= 2:
                hits.append({"family": family, "words": matched})
        if not hits:
            continue
        found.append(
            {
                "kind": "rename",
                "paragraph": index,
                "families": hits,
                "preview": _preview(paragraph, 80),
                "criterion": "同一概念在段内换了实义说法（同族 ≥2 词并存）",
            }
        )
    return found


def _find_cohesion(
    paragraphs: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """衔接连环候选：段首承接词连续出现 ≥ `COHESION_THRESHOLD` 段。

    Returns:
        `(候选, 全部连环)` —— 后者用于报告"最长连环"这个汇总数。
    """
    flags: List[str] = []
    for paragraph in paragraphs:
        opener = ""
        for candidate in _COHESION_OPENERS:
            if paragraph.startswith(candidate):
                opener = candidate
                break
        flags.append(opener)

    runs: List[List[int]] = []
    run: List[int] = []
    for index, opener in enumerate(flags):
        if opener:
            run.append(index)
            continue
        if run:
            runs.append(run)
        run = []
    if run:
        runs.append(run)

    # 候选只收 ≥ 门槛的；但**全部**连环都进 extra，供"最长连环"统计
    candidates = [_cohesion_item(paragraphs, r, flags) for r in runs if len(r) >= COHESION_THRESHOLD]
    streaks = [{"start": r[0] + 1, "end": r[-1] + 1, "length": len(r)} for r in runs]
    return candidates, streaks


def _cohesion_item(paragraphs: Sequence[str], run: List[int], flags: Sequence[str]) -> Dict[str, Any]:
    return {
        "kind": "cohesion",
        "start": run[0] + 1,
        "end": run[-1] + 1,
        "length": len(run),
        "openers": [flags[i] for i in run],
        "criterion": f"连续 ≥{COHESION_THRESHOLD} 段用明确承接开头；真正问题是零跳转",
    }


def _find_colon(paragraphs: Sequence[str], offset: int = 0) -> List[Dict[str, Any]]:
    """结论提示冒号候选：冒号前是短提示语（≤`COLON_PREFIX_MAX` 字）的句子。

    冒号总量人类反而更多，所以**不能见冒号就算命中** ——
    这里只把"冒号前很短"的句子作为候选，让模型按判据分「结论提示」与「普通引入」。
    """
    found: List[Dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs, 1):
        for sentence in split_sentences(paragraph):
            position = sentence.find("：")
            if position < 0:
                continue
            prefix = sentence[:position].strip()
            if not prefix or len(prefix) > COLON_PREFIX_MAX:
                continue
            found.append(
                {
                    "kind": "colon_judge",
                    "paragraph": index,
                    "prefix": prefix,
                    "preview": _preview(sentence, 80),
                    "criterion": "冒号前是独立结论判断、冒号后展开论证",
                }
            )
            if len(found) >= MAX_PER_KIND:
                return found
    return found


def _sentences_with_ending(paragraph: str) -> List[Tuple[str, str]]:
    """切句并**保留句末标点**（`[(文本, 标点)]`）。

    ❗ 句末标点是"骨架"的重要组成：「叫什么名字？」连着三句都是疑问，
    与"陈述三连"是两种不同结构。旧实现切句时把标点丢了，于是所有句子
    的签名都以「。」或空结尾，疑问三连被判成普通三连（甚至判不出）。
    """
    found: List[Tuple[str, str]] = []
    pattern = re.compile(r"([^。！？!?]+)([。！？!?])?")
    for match in pattern.finditer(paragraph or ""):
        body = match.group(1).strip("　 	，,；;：:")
        ending = match.group(2) or "。"
        if len(re.sub(r"\s", "", body)) >= _MIN_SENTENCE_CHARS:
            found.append((body, ending))
    return found


def _signature(sentence: str, ending: str = "。") -> Tuple[int, str, int]:
    """句子骨架签名：`(长度桶, 句末标点, 逗号数)`。

    只取这三项是刻意的：**宽口径排比没有区分力**（人类本来就爱排比），
    只有"长度、停顿、收尾都一致"这种高度同构才是信号。
    """
    body = re.sub(r"\s", "", sentence)
    bucket = len(body) // _LEN_BUCKET
    tail = ending if ending in "。！？!?" else "。"
    commas = body.count("，") + body.count(",")
    return bucket, tail, commas


def _isomorphic(a: Tuple[int, str, int], b: Tuple[int, str, int]) -> bool:
    """两个签名是否算"同构"。

    长度允许**跨一个桶**：绝对相等会把 7 字与 8 字的句子判成不同（它们只差
    一个字，骨架几乎一样），而桶宽是人为切的，边界不该产生语义差异。
    标点与逗号数仍然**严格相等** —— 那是骨架的直接证据。
    """
    return abs(a[0] - b[0]) <= 1 and a[1] == b[1] and a[2] == b[2]


def _find_isomorphic(paragraphs: Sequence[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """相邻句同构（2 连）与高度同构三连（3 连）。

    返回 `(pairs, triples)`。三连是二连的子集情形，但要分别报 ——
    技能包把它们当成两条不同规则（6 与 13），门槛也不同。
    """
    pairs: List[Dict[str, Any]] = []
    triples: List[Dict[str, Any]] = []

    for p_index, paragraph in enumerate(paragraphs, 1):
        # 用带标点的切分：句末标点是骨架的一部分（疑问三连 ≠ 陈述三连）
        pairs_with_ending = [
            (body, ending)
            for body, ending in _sentences_with_ending(paragraph)
            if len(re.sub(r"\s", "", body)) >= _MIN_ISO_CHARS
        ]
        if len(pairs_with_ending) < 2:
            continue
        sentences = [body for body, _ending in pairs_with_ending]
        signatures = [_signature(body, ending) for body, ending in pairs_with_ending]

        run_start = 0
        for i in range(1, len(signatures) + 1):
            same = i < len(signatures) and _isomorphic(signatures[i], signatures[i - 1])
            if same:
                continue
            run_len = i - run_start
            if run_len >= 2:
                sample = [_preview(sentences[j], 40) for j in range(run_start, min(i, run_start + 3))]
                payload = {
                    "kind": "iso_pair",
                    "paragraph": p_index,
                    "start_sentence": run_start + 1,
                    "length": run_len,
                    "signature": {
                        "len_bucket": signatures[run_start][0],
                        "ending": signatures[run_start][1],
                        "commas": signatures[run_start][2],
                    },
                    "sentences": sample,
                    "criterion": "相邻句逗号位置、成分顺序、收尾一致；只改句内不动段序",
                }
                pairs.append(payload)
                if run_len >= 3:
                    triples.append({**payload, "kind": "iso3", "criterion": "连续三句骨架逐字复刻"})
            run_start = i
    return pairs, triples


def extract_candidates(text: str) -> SemanticCandidates:
    """抽取全部五类语义层候选。

    返回的对象里每条候选都预留了 `label` / `reason`，
    判读后原样写回即可（`write_candidates`），形成可对账的逐条结果。
    """
    from .text_stats import count_hanzi

    paragraphs = split_paragraphs(text)
    result = SemanticCandidates(paragraphs=len(paragraphs), hanzi=count_hanzi(text))

    for item in _find_rename(paragraphs):
        result.add("rename", item)
    cohesion_candidates, streaks = _find_cohesion(paragraphs)
    for item in cohesion_candidates:
        result.add("cohesion", item)
    result.extra["cohesion_streaks"] = streaks
    result.extra["max_chain"] = max((s["length"] for s in streaks), default=0)
    for item in _find_colon(paragraphs):
        result.add("colon_judge", item)
    pairs, triples = _find_isomorphic(paragraphs)
    for item in pairs:
        result.add("iso_pair", item)
    for item in triples:
        result.add("iso3", item)
    return result


# ====================================================================== 汇总


def semantic_summary(candidates: SemanticCandidates) -> Dict[str, Any]:
    """按技能包口径算四个汇总数。

    - 重命名：次/段（**含阴性判读**才准 —— 未判读时按候选数计，并标注）
    - 最长连环
    - 结论冒号占比
    - 高度同构三连数
    """
    paragraphs = max(1, candidates.paragraphs)
    rename = candidates.get("rename")
    cohesion = candidates.get("cohesion")
    colon = candidates.get("colon_judge")
    triples = candidates.get("iso3")

    def _hits(items: Sequence[Dict[str, Any]]) -> int:
        """已判读时只数 hit；未判读时退回候选数并标注口径。"""
        judged = [i for i in items if i.get("label")]
        if judged:
            return sum(1 for i in judged if i["label"] == "hit")
        return len(items)

    # 最长连环取**全部连环**的最大值（不只候选）；缺失时退回候选里的最大值
    longest = int(candidates.extra.get("max_chain", 0) or 0)
    if not longest:
        longest = max((int(i.get("length", 0)) for i in cohesion), default=0)
    return {
        "rename_per_paragraph": round(_hits(rename) / paragraphs, 2),
        "rename_count": _hits(rename),
        "longest_chain": longest,
        "colon_candidates": len(colon),
        "colon_hits": _hits(colon),
        "iso3_count": _hits(triples),
        "judged": candidates.judged,
        "total": candidates.total,
        # 口径提示：未判读时数字是"候选数"，不等于命中数
        "basis": "judged" if candidates.judged else "candidates",
    }


# ====================================================================== 读写与展示


def write_candidates(candidates: SemanticCandidates, path: Any) -> Tuple[bool, str]:
    """把候选（含判读结果）写成 UTF-8 JSON。目录不存在会自动建。"""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(candidates.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True, f"已写入 {target}"
    except OSError as exc:
        logger.warning(f"[语义候选] 写入失败：{exc}")
        return False, f"写入失败：{exc}"


def load_candidates(path: Any) -> Optional[SemanticCandidates]:
    """读回候选 JSON（判读后回填的场景）。格式不对返回 `None`。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f"[语义候选] 读取失败：{exc}")
        return None
    if not isinstance(data, dict):
        return None
    meta = data.get("meta") or {}
    candidates = SemanticCandidates(
        paragraphs=int(meta.get("paragraphs", 0) or 0),
        hanzi=int(meta.get("hanzi", 0) or 0),
    )
    for kind, items in (data.get("candidates") or {}).items():
        if isinstance(items, list):
            candidates.items[str(kind)] = [i for i in items if isinstance(i, dict)]
    return candidates


def format_candidates(candidates: SemanticCandidates, limit: int = 3) -> str:
    """人读摘要：每类给条数与几个例子（完整清单在 JSON 里）。"""
    summary = semantic_summary(candidates)
    lines = [
        f"候选总量 {summary['total']} 条（已判读 {summary['judged']} 条）",
        f"口径：{summary['basis']} —— "
        + ("按判读结果统计" if summary["basis"] == "judged" else "尚未判读，以下为候选数、非命中数"),
        "",
    ]
    for kind, label in JUDGE_LABELS.items():
        items = candidates.get(kind)
        lines.append(f"{label}：{len(items)} 条")
        for item in items[:limit]:
            if kind == "cohesion":
                lines.append(
                    f"    · 第 {item['start']}–{item['end']} 段（{item['length']} 连环）："
                    f"{'、'.join(item['openers'][:4])}"
                )
            elif kind == "rename":
                families = "、".join(f"{f['family']}({'/'.join(f['words'])})" for f in item["families"][:2])
                lines.append(f"    · 第 {item['paragraph']} 段：{families}")
            elif kind == "colon_judge":
                lines.append(f"    · 第 {item['paragraph']} 段「{item['prefix']}：…」")
            else:
                lines.append(f"    · 第 {item['paragraph']} 段 {item['length']} 连：{item['sentences'][0]}…")
    lines.append("")
    lines.append("判读纪律：")
    lines.extend(f"- {rule}" for rule in JUDGE_RULES)
    return "\n".join(lines)
