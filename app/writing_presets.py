"""写作预设 —— 把技能库的规则装配成**可复用、可验收**的写作能力单元。

## 为什么需要这一层（而不是直接注入技能规则）

`skill_library.py` 解决的是「把 SKILL.md 变成结构化规则」，但它注入的是
**整个技能的规则集**。这在真实写作里有两个问题：

1. **体裁不分**：小说正文里删「说白了」「不是A而是B」是对的，但删破折号、
   删顿号、把冒号改成句号会把叙事改坏（技能自己也写着「文学性表达按原风格判断」）。
   一份规则集全量注入，等于让模型在小说里执行非虚构的清理标准。
2. **阶段不分**：**生成前**需要的是"别写出这些句式"，**成稿后**需要的是
   "先报告再改写"。两者规则重叠但**执行方式完全不同**，混在一起会让模型
   一边写一边自我审查，产出反而更僵。

所以预设 = 「规则子集 + 执行阶段 + 质检口径」的显式组合。**正交**是硬要求：
任意两个预设不能只是"规则多一点少一点"，必须是**不同的写作场景**，
否则用户面对选择只会困惑，模型也会收到自相矛盾的约束。

## 五个预设（按维度正交，不按规则多少切）

| 预设 | 维度 | 触发 | 执行阶段 |
|---|---|---|---|
| `gen-guard` 生成期防 AI 腔 | 阶段 = 写之前 | 生成章节前自动 | 约束（不提"改写"） |
| `deai-full` 成稿去 AI 味 | 阶段 = 写之后 | 非虚构成稿 / 明确说"去AI味" | 两段式：先报告后改写 |
| `novel-voice` 小说叙事 | 体裁 = 虚构 | 检测到叙事特征 | 局部清理，禁碰文学性 |
| `shortcopy` 短文案 | 长度 < 500 汉字 | 短文本 | 手工规则，脚本不适用 |
| `qc-gate` 输出质检 | 只验收 | 从不自动 | 只出报告，不改稿 |

> `qc-gate` 刻意**不参与自动匹配**：质检是"最后一道闸门"，
> 由用户显式触发，才不会和"生成期约束"抢同一份提示词预算。

## 三层分工（与技能包口径一致，不自己发明）

质检**只自动化脚本能判的部分**：

- **脚本层**（本模块 `DETECTORS`）：正则/密度可数的 —— 翻案腔、提示语冒号、
  起手式、过长定语、顿号密度、破折号密度、分号密度；
- **语义层**（本模块只**列候选**，不下结论）：同义重命名、衔接连环、结论冒号、
  高度同构三连 —— 判据在技能包的 `references/semantic-criteria.md`；
- **人审层**（永不自动判）：比喻贴切度、暗喻、拟人化喻体。

为什么不在应用里跑技能自带的 `detect.py`：那是**执行第三方代码**，
与本项目"技能库不执行技能脚本"的安全边界冲突（见 `skill_library` 模块文档）。
本模块用**自研的等价比子集**覆盖脚本层，宁可少判几条，也不打破边界。

## 与技能库的注入关系（防重复）

❗ 预设存在时**只注入预设**，不再注入原始技能规则 —— 两者内容重叠，
同时注入会把同一批规则说两遍，既浪费预算又让模型以为是两组不同要求。
`novel_agent` 里是"预设优先、技能兜底"的单选逻辑，不是叠加。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from .storage import atomic_write_json

__all__ = [
    "DETECTORS",
    "PRESETS",
    "Preset",
    "PresetManager",
    "QcFinding",
    "QC_LEVELS",
    "SEMANTIC_CHECKS",
    "build_preset_context",
    "count_hanzi",
    "default_presets_file",
    "detect_text",
    "get_preset_manager",
    "match_preset",
    "qc_report",
    "reset_preset_manager",
    "resolve_preset",
]

#: 质检项严重度 → 含义。`blocker` 必须清零才可交付；`warn` 需给理由；`info` 只记录。
QC_LEVELS: Dict[str, str] = {
    "blocker": "必须处理（可定位、可安全改写）",
    "warn": "需给保留理由",
    "info": "仅记录（整篇分布 / 指纹方向）",
}


# ====================================================================== 文本工具


_HANZI_RE = re.compile(r"[\u4e00-\u9fff]")


def count_hanzi(text: str) -> int:
    """汉字个数（与技能包 `detect.py` 的口径一致：只数汉字，不算标点与英文）。"""
    return len(_HANZI_RE.findall(text or ""))


def _per_ktx(count: int, hanzi: int) -> float:
    """每千汉字密度。`hanzi=0` 时返回 0（短文本不参与密度判定）。"""
    if hanzi <= 0:
        return 0.0
    return count * 1000.0 / hanzi


# ====================================================================== 脚本层检测器


@dataclass(frozen=True)
class Detector:
    """一个**可数**的 AI 痕迹检测器（脚本层）。

    `patterns` / `human_ref` **逐字取自技能包 `scripts/detect.py` 的 `REGEX_HITS`**
    （只读源码取判据，不执行它的脚本 —— 执行第三方代码越过本项目的安全边界）。

    为什么不自己写正则：实测自研版本在技能包自带的示例稿上
    **提示语冒号漏检 3 处、过长定语误报 10 倍**。检测器与本技能共用同一套判据，
    质检报告才能和技能包的数值对得上；否则用户拿到两份互相矛盾的结论。
    """

    key: str
    label: str
    rule: str
    patterns: Tuple[str, ...]
    unit: str = "density"  # count | density
    human_ref: Optional[float] = None
    note: str = ""
    flags: int = 0
    #: 门禁性质。**这是质检能不能闭环的关键**：
    #: - `blocker`：A 级机械替换，有效命中就该清零；残留即交付阻断。
    #: - `review`：脚本只能粗筛，命中里混着合法写法（标题冒号、清单内顿号、
    #:   作者本人的破折号）。超限只提示复核，**不得据此判不合格**。
    #: 判据来自技能包自己的复测结论：它的合格改稿里仍是「提示语冒号 2 处、
    #: 破折号 8 处」，因为那 2 处是标题/引入句、破折号是 F 级指纹。
    #: 若把 review 项当阻断，技能包自己的成稿都过不了自己的门禁。
    gate_class: str = "review"

    def find(self, text: str) -> List[str]:
        hits: List[str] = []
        for pattern in self.patterns:
            hits.extend(m.group(0) for m in re.finditer(pattern, text or "", self.flags))
        return hits


#: 脚本层检测器表。**新增一条只改这里** —— 预设的 `gates` 按 key 引用。
#:
#: `human_ref` 是技能包实测的**人类参考密度**（次/千汉字）。预设门禁由它推导，
#: 这样「合格」有客观出处，而不是随手定的数字。
DETECTORS: Dict[str, Detector] = {
    "fanan": Detector(
        key="fanan",
        label="翻案腔（不是A而是B）",
        rule="技能规则 1",
        patterns=(r"(?:不是|并非|不在于|与其说)[^，。！？\n]{1,20}[，]?(?:而是|而在于|不如说)",),
        human_ref=0.22,
        gate_class="blocker",
        note="最强的纯写作信号（两轮实测同向）；改法是直接正面下判断",
    ),
    "colon_prompt": Detector(
        key="colon_prompt",
        label="提示语冒号（一句话总结：）",
        rule="技能规则 2 / 12",
        patterns=(
            r"(?:一句话(?:总结|说|概括)|简单说|说白了|总结|小结|结论|核心(?:是|在于|观点)?"
            r"|关键(?:是|在于)?|重点(?:是)?|原因(?:如下|有|在于)?|问题(?:是|在于)?"
            r"|答案(?:是)?|本质(?:是|上)?|具体(?:来说|如下|包括)?"
            r"|举例(?:来说)?|换句话说|也就是说|我的(?:观点|判断|结论)|建议(?:是)?)[：:]",
        ),
        human_ref=0.08,
        note="冒号前是替读者宣告结论的提示语；冒号总量人类反而更多（别乱删）",
    ),
    "starter": Detector(
        key="starter",
        label="起手式（说白了，）",
        rule="技能规则 3",
        patterns=(r"(?:说白了|说穿了|先说结论)[，,]",),
        human_ref=0.008,
        gate_class="blocker",
    ),
    "dang_shi": Detector(
        key="dang_shi",
        label="「当……时」前置从句",
        rule="技能规则 4（翻译腔）",
        patterns=(r"当[^，。\n]{2,20}(?<!的时候)时，",),
        note="删「当」和「时」；确实需要标示时点的不改",
    ),
    "topic_shell": Detector(
        key="topic_shell",
        label="前置话题壳（对于……来说）",
        rule="技能规则 4（翻译腔）",
        patterns=(r"(?:对于[^，。\n]{2,15}来说|对[^，。\n]{2,15}而言|就[^，。\n]{2,15}而言|在[^，。\n]{2,12}方面)",),
        note="对象直接放到主语位，删壳子",
    ),
    "connector": Detector(
        key="connector",
        label="句首连接词（然而，）",
        rule="技能规则 4（翻译腔）",
        patterns=(r"(?:^|\n)\s{0,3}(?:然而|因此|此外|与此同时|换言之|总而言之)[，、]",),
        flags=re.M,
        note="移到主语后，或换「不过」「其实」；论证确实需要路标时不改",
    ),
    "dunhao": Detector(
        key="dunhao",
        label="顿号并列≥3",
        rule="技能规则 5",
        patterns=(r"[^，。！？；：、\n]{1,14}、[^，。！？；：、\n]{1,14}、[^，。！？；、\n]{1,14}",),
        human_ref=1.78,
        note="句内排比（提升效率，降低成本）人类用得不比 AI 少，不在本条范围",
    ),
    "long_attr": Detector(
        key="long_attr",
        label="过长前置定语",
        rule="技能规则 4（翻译腔）",
        patterns=(r"(?:一个|一种|一套|这种|这个)[^，。、；：！？\n]{15,}的[一-鿿]{2,5}",),
        human_ref=0.1,
        note="拆成两个分句；❌ 不用「的…的」宽口径 —— 实测在正常中文里误报约 10 倍",
    ),
    "dash": Detector(
        key="dash",
        label="破折号",
        rule="技能规则 8（F 级指纹）",
        patterns=(r"——",),
        human_ref=0.8,
        note=">2/千字才优先处理；低于人类参考值的文本不因「缺少」而补写",
    ),
    "semicolon": Detector(
        key="semicolon",
        label="分号",
        rule="F 级指纹",
        patterns=(r"；",),
        note="逐处看能否安全拆成句号；有并列层级则保留",
    ),
}


def detect_text(text: str) -> Dict[str, int]:
    """对文本跑全部脚本层检测器，返回 `{key: 命中次数}`。"""
    return {key: len(det.find(text)) for key, det in DETECTORS.items()}


#: **技能包官方分级**（取自 `scripts/detect.py` 的 `REGEX_HITS` 首字段 + `SKILL.md` 分级标题）。
#:
#: 为什么需要它：`skill_library` 的 A/B 是**启发式推断**（按"删掉/换成"等措辞猜），
#: 实测把「翻案腔」判成 B，而技能包官方判 A（机械级、可直接改）。
#: 预设要给用户看"这条属于必须改还是建议改"，必须用官方口径 ——
#: 否则同一条规则在规则列表里显示 B、在质检门禁里按 blocker 处理，自相矛盾。
OFFICIAL_LEVELS: Dict[str, str] = {
    "翻案腔": "A",
    "提示语冒号": "A",
    "起手式": "A",
    "当…时从句": "A",
    "前置话题壳": "A",
    "句首连接词": "A",
    "顿号并列": "B",
    "过长前置定语": "B",
    "相邻句结构同款": "B",
    "拟人化喻体": "H",
    "破折号": "F",
}


def official_level(title: str) -> str:
    """按标题查官方分级；查不到返回空串（表示沿用技能库的分级）。"""
    text = str(title or "")
    for key, level in OFFICIAL_LEVELS.items():
        if key in text:
            return level
    return ""


#: 语义层检查项：**本模块只列候选，不下结论**（判据在技能包，需模型/人判读）。
SEMANTIC_CHECKS: Tuple[Tuple[str, str, str], ...] = (
    ("rename", "同义重命名（段级，规则 10）", "同一实体在一段内换实义说法；判据见 semantic-criteria.md"),
    ("cohesion", "衔接连环过长（规则 11）", "连续「明确承接」接口 ≥6；真正问题是零跳转"),
    ("colon_judge", "结论提示冒号（规则 12）", "冒号前是独立结论判断、冒号后展开论证"),
    ("iso_pair", "相邻句结构同款（规则 6）", "相邻两句逗号位置、成分顺序、收尾一致；只改句内不动段序"),
    ("iso3", "高度同构三连（规则 13）", "连续三句骨架逐字复刻；宽口径排比无区分力"),
)


# ====================================================================== 预设模型


@dataclass(frozen=True)
class Preset:
    """一个可复用的写作预设。

    `rule_ids` 用**技能包的规则编号**而不是重抄一遍规则文本 —— 技能更新时
    预设自动跟上（"同一事实写两处必然漂移"）。
    """

    key: str
    name: str
    dimension: str
    summary: str
    stage: str
    triggers: Tuple[str, ...] = ()
    trigger_patterns: Tuple[str, ...] = ()
    rule_ids: Tuple[int, ...] = ()
    include_levels: Tuple[str, ...] = ()
    exclude_note: Tuple[str, ...] = ()
    norms: Tuple[str, ...] = ()
    self_check: Tuple[str, ...] = ()
    gates: Tuple[Tuple[str, float], ...] = ()
    budget: int = 900
    auto: bool = True

    # ------------------------------------------------------------------ 装配

    def gate_map(self) -> Dict[str, float]:
        return dict(self.gates)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "dimension": self.dimension,
            "summary": self.summary,
            "stage": self.stage,
            "triggers": list(self.triggers),
            "rule_ids": list(self.rule_ids),
            "levels": list(self.include_levels),
            "gates": [{"detector": d, "limit": v} for d, v in self.gates],
            "auto": self.auto,
        }

    def to_prompt(self, rules: Optional[Sequence[Any]] = None, budget: int = 900) -> str:
        """装配成提示词段落。**按规则边界截断**，并说明还有多少条未注入。"""
        lines = [
            f"【写作预设：{self.name}】",
            f"阶段：{self.stage} —— {self.summary}",
        ]
        if self.include_levels:
            lines.append(f"可处理级别：{'/'.join(self.include_levels)}（X 级已否决、H 级人审，均不得改动）")

        norms = list(self.norms)
        if norms:
            lines.append("写作规范：")
            lines.extend(f"- {item}" for item in norms)

        if self.exclude_note:
            lines.append("本预设的边界：")
            lines.extend(f"- {item}" for item in self.exclude_note)

        if self.self_check:
            lines.append("交付前自检：")
            lines.extend(f"- {item}" for item in self.self_check)

        selected = _select_rules(rules or [], self)
        used = len("\n".join(lines))
        emitted = 0
        if selected:
            lines.append("适用规则：")
            for rule in selected:
                title = getattr(rule, "title", "")
                level = official_level(title) or getattr(rule, "level", "") or "通用"
                text = f"- [{level}] {title}"
                summary = _rule_summary(rule, 60)
                if summary:
                    text += f"：{summary}"
                if used + len(text) + 1 > budget - 60:
                    break
                lines.append(text)
                used += len(text) + 1
                emitted += 1
            pending = len(selected) - emitted
            if pending > 0:
                lines.append(f"（另有 {pending} 条适用规则因长度未注入，按同一规范执行）")

        text = "\n".join(lines)
        if len(text) > budget:
            text = text[: max(0, budget - 1)].rstrip() + "…"
        return text


def _rule_summary(rule: Any, limit: int) -> str:
    """优先取「改法」；没有就取摘要。规则对象来自 `skill_library.SkillRule`。"""
    for name in ("revision", "summary"):
        func = getattr(rule, name, None)
        if callable(func):
            try:
                value = func(limit) if name == "summary" else func()
            except TypeError:
                value = func()
            except Exception:  # noqa: BLE001 - 摘要失败不该中断装配
                continue
            if value:
                text = str(value).strip().replace("\n", " ")
                return text[:limit]
    return ""


def _select_rules(rules: Sequence[Any], preset: Preset) -> List[Any]:
    """按规则编号 + 级别筛出该预设适用的规则。

    编号优先：技能里编号是稳定的（`1. 翻案腔`），比标题匹配可靠。
    """
    picked: List[Any] = []
    for rule in rules:
        level = str(getattr(rule, "level", "") or "")
        if level in ("X", "H"):
            continue  # 永不注入
        number = _rule_number(getattr(rule, "title", ""))
        if preset.rule_ids:
            if number in preset.rule_ids:
                picked.append(rule)
            continue
        if preset.include_levels and level in preset.include_levels:
            picked.append(rule)
    return picked


_RULE_NUM_RE = re.compile(r"^\s*(\d+)[.、]\s*")


def _rule_number(title: str) -> Optional[int]:
    match = _RULE_NUM_RE.match(str(title or ""))
    return int(match.group(1)) if match else None


# ====================================================================== 预设定义


PRESETS: Dict[str, Preset] = {
    # ---------------------------------------------------------------- 生成期
    "gen-guard": Preset(
        key="gen-guard",
        name="生成期防 AI 腔",
        dimension="阶段：写之前",
        summary="在生成章节时**直接不产出**高置信度的 AI 句式，而不是写完再改",
        stage="生成前约束",
        triggers=("生成章节", "续写", "扩写", "新章"),
        trigger_patterns=(r"生成|续写|扩写|接着写|写一章",),
        rule_ids=(1, 3, 4, 6, 10, 13),
        include_levels=("A", "B"),
        exclude_note=(
            "不注入顿号（规则 5）与破折号（规则 8）：生成期刻意「避开某个标点」会形成另一种机械感，"
            "这两个只在成稿清理时逐处判断",
            "不注入 C 级整篇分布指标：边写边控制句长方差会写出忽长忽短的假参差",
            "不做「改写」动作：本预设只约束本次生成，不改动已有正文",
        ),
        norms=(
            "最小改动：约束只作用于本次新写的文字，不回头润色既有段落",
            "信息守恒：观点、事实、限定词（可能/通常/多数）不得为了「像人」而加强或抹掉",
            "不制造参差：不刻意拆句、不为了节奏把段落打散",
            "结构不动：标题层级、段落顺序、列表与引文位置保持既定大纲",
        ),
        self_check=(
            "本章有没有出现「不是…而是…」「与其说…不如说」式对举（规则 1）",
            "有没有用「说白了」「说穿了」起句（规则 3）",
            "有没有「一句话总结：」「关键在于：」式提示语冒号（规则 2）",
            "同一实体在一段内是否换了多个说法（规则 10）",
        ),
        gates=(("fanan", 0.50), ("colon_prompt", 0.20), ("starter", 0.03)),
        budget=900,
    ),
    # ---------------------------------------------------------------- 成稿清理
    "deai-full": Preset(
        key="deai-full",
        name="成稿去 AI 味",
        dimension="阶段：写之后",
        summary="先出检测报告（指标 + 例句 + 改法），等用户确认后再改，改完复测",
        stage="成稿后清理（两段式）",
        triggers=("去AI味", "AI味太重", "加点人味", "读着像机器人", "润色成真人语气"),
        trigger_patterns=(r"去\s*AI\s*味|AI\s*味|机器人写|人味|真人语气",),
        rule_ids=(1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 13),
        include_levels=("A", "B", "F"),
        exclude_note=(
            "X 级永不改：序数词小标题、「这意味着」复述、空转句引列表、概括替代 —— 配对复测方向反转，改了反而更不像人",
            "H 级不判：比喻贴切度、暗喻、拟人化喻体只列不评级",
            "C 级只报告：句长/段长方差是整篇属性，逐句改必然过度",
        ),
        norms=(
            "最小改动：一处命中只改解决该问题所必需的部分，不顺便润色",
            "信息守恒：姓名、数字、日期、引语、因果必须能在原文指出出处",
            "不制造参差：不为节奏改句长、不拆段",
            "结构不动：标题层级、段落顺序、列表表格引用代码块位置原样保留",
            "有风格文档先读文档，冲突以风格文档为准（作者本来就爱用破折号就不删）",
        ),
        self_check=(
            "每处改动都能指出对应规则编号，指不出就撤销",
            "实词都有出处，限定词没被加强",
            "X 级四条没被误删",
            "复测后 A/B 清零，C 级指标没有大幅摆动",
        ),
        gates=(
            ("fanan", 0.30),
            ("colon_prompt", 0.15),
            ("starter", 0.02),
            ("dunhao", 2.20),
            ("long_attr", 0.30),
            ("dash", 2.00),
        ),
        budget=1200,
    ),
    # ---------------------------------------------------------------- 体裁特化
    "novel-voice": Preset(
        key="novel-voice",
        name="小说叙事人味",
        dimension="体裁：虚构",
        summary="只清理叙事腔里的「说明文口气」，不碰文学性表达、对话与节奏",
        stage="局部清理（禁碰文学性）",
        triggers=("小说", "章节", "对白", "叙事"),
        trigger_patterns=(r"第[一二三四五六七八九十百零\d]+章|他说|她说|旁白|对白|场景描写",),
        rule_ids=(1, 4, 6, 10, 11, 13),
        include_levels=("A", "B"),
        exclude_note=(
            "不处理冒号（规则 2/12）：对话引语、小标题冒号在小说里是正常写法",
            "不处理顿号（规则 5）：场景铺陈的并列是修辞，不是 AI 痕迹",
            "不处理破折号（规则 8）：人物语气与念头打断常靠破折号",
            "文学性排比、比喻、设问一律保留；对话与口语体本来就是自然表达",
        ),
        norms=(
            "只改「叙述者跳出来解释」的句子，不改人物语言与场景描写",
            "信息守恒：情节事实、人物关系、时间地点不得因改写而变",
            "结构不动：段落顺序与场景切分保持原样，不合并、不拆分",
            "保留作者的比喻与节奏，即使它们与「AI 味」指标重合",
        ),
        self_check=(
            "改动是否只落在叙述句，没碰到对白",
            "删除的对举句是否真的丢了信息（小说里「不是A而是B」可能承担人物心理）",
            "同义重命名是否误伤了刻意的指称变化",
        ),
        gates=(("fanan", 0.80), ("long_attr", 0.40)),
        budget=800,
    ),
    # ---------------------------------------------------------------- 长度特化
    "shortcopy": Preset(
        key="shortcopy",
        name="短文案去 AI 味",
        dimension="长度：<500 汉字",
        summary="脚本门槛外的短文本，只能按机械级规则人工清理",
        stage="手工清理（无脚本统计）",
        triggers=("短文案", "标题", "卖点", "简介", "朋友圈"),
        trigger_patterns=(r"标题|文案|卖点|简介|摘要|朋友圈|海报",),
        rule_ids=(1, 2, 3, 4, 5),
        include_levels=("A", "B"),
        exclude_note=(
            "技能脚本按汉字数判定，**少于 500 汉字会直接退出** —— 短文案不走脚本检测，"
            "也不报密度指标，避免用整篇口径解释一句话",
            "不判语义层四项：样本量不足，同义重命名/衔接连环在短文本上没有统计意义",
            "标题、标语里的对举与冒号可能是刻意修辞，逐条看语境",
        ),
        norms=(
            "逐句人工判断，只改「一眼是模板腔」的地方",
            "字数基本不变，改完朗读一遍，不能出现拗口的书面语",
            "不为了去 AI 味牺牲信息密度：卖点、数字、限定词必须保留",
        ),
        self_check=("每条改动都能说出「原来像模板、现在像人说话」的具体理由",),
        gates=(("fanan", 0.0), ("colon_prompt", 0.0), ("starter", 0.0)),
        budget=520,
    ),
    # ---------------------------------------------------------------- 只验收
    "qc-gate": Preset(
        key="qc-gate",
        name="输出质检闸门",
        dimension="只验收",
        summary="不注入任何规则，只对成稿跑质检并出报告（机器可判 + 待判读清单）",
        stage="交付前验收",
        triggers=("质检", "验收", "检查一下"),
        trigger_patterns=(r"质检|验收|过一遍|检查一下",),
        rule_ids=(),
        include_levels=(),
        exclude_note=(
            "只报告不改稿：任何改动都必须回到对应预设想清楚「改哪、为什么」",
            "语义层四项（同义重命名/衔接连环/结论冒号/同构三连）只列候选，由模型按技能包判据判读，不由脚本下结论",
        ),
        norms=("质检结论必须给出命中位置与次数，不接受「感觉有点 AI 味」",),
        self_check=("blocker 级是否清零", "warn 级是否逐条给了保留理由"),
        # ❗ 必须与 `deai-full` 同口径：质检闸门是"最后一道验收"，
        # 若它比清理预设少判两项，就会出现"清理时要求、验收时不查"的漏网。
        gates=(
            ("fanan", 0.30),
            ("colon_prompt", 0.15),
            ("starter", 0.02),
            ("dunhao", 2.20),
            ("long_attr", 0.30),
            ("dash", 2.00),
        ),
        budget=360,
        auto=False,
    ),
}


# ====================================================================== 匹配


_FICTION_HINT = re.compile(r"[「」“”]|他说|她说|她道|他道|旁白|第[一二三四五六七八九十\d]+章")


def match_preset(text: str, stage: str = "", explicit: str = "") -> Tuple[str, str]:
    """决定该用哪个预设，返回 `(preset_key, 理由)`。

    顺序即优先级（先排除、再定档）：
    1. `explicit` 命中预设 key / 别名 → 直接采用；
    2. `stage == "generate"` → `gen-guard`（生成期不该走成稿清理）；
    3. 汉字 < 500 → `shortcopy`（脚本门槛外）；
    4. 出现叙事特征 → `novel-voice`；
    5. 其余 → `deai-full`。
    """
    if explicit:
        resolved = resolve_preset(explicit)
        if resolved:
            return resolved.key, f"显式指定「{explicit}」"
    if stage == "generate":
        return "gen-guard", "生成阶段：只约束新写内容"
    hanzi = count_hanzi(text)
    if hanzi and hanzi < 500:
        return "shortcopy", f"仅 {hanzi} 汉字，低于脚本统计门槛"
    if text and _FICTION_HINT.search(text):
        return "novel-voice", "检测到叙事/对白特征"
    return "deai-full", "默认成稿清理"


def resolve_preset(name: str) -> Optional[Preset]:
    """按 key / 名称 / 触发词解析预设。"""
    key = str(name or "").strip()
    if not key:
        return None
    if key in PRESETS:
        return PRESETS[key]
    for preset in PRESETS.values():
        if key == preset.name or key in preset.triggers:
            return preset
    return None


#: X 级「永不改」特征的指纹（用于**反向守卫**：改后比改前少 ⇒ 可能误删）。
#:
#: 技能包最核心的安全设计就是这四条「永不改」。但"不注入"只防了模型主动改，
#: 防不住它在改写时顺手删掉 —— 所以这里做**改前/改后计数对比**。
#: 正则只是近似：`空转句引列表` 无法精确判定，命中数下降仅作提示，不作结论。
X_MARKERS: Dict[str, str] = {
    # 行首的「1.」「一、」：用 `^` + re.M，避免依赖换行转义
    "序数词小标题": r"^\s*(?:\d+[.、]|[一二三四五六七八九十]+[、.])\s*\S",
    "「这意味着」复述": r"这意味着",
    "空转句引列表": r"(?:以下\d*[种类个]|如下几[种类个]|我见过(?:的)?[^。]{0,8})[：:]",
}


def x_level_counts(text: str) -> Dict[str, int]:
    """数一遍 X 级特征的出现次数。"""
    return {name: len(re.findall(pattern, text or "", re.M)) for name, pattern in X_MARKERS.items()}


def check_x_level(original: str, revised: str) -> Dict[str, Any]:
    """反向守卫：改后 X 级特征**变少**就是可疑（可能误删了不该动的写法）。"""
    before = x_level_counts(original)
    after = x_level_counts(revised)
    dropped = {name: before[name] - after[name] for name in before if after[name] < before[name]}
    return {"before": before, "after": after, "dropped": dropped, "ok": not dropped}


def structure_metrics(text: str) -> Dict[str, float]:
    """C 级整篇结构指标（**只报告，不设门禁**）。

    技能包把句长/段长方差列为 C 级：它是整篇属性，逐句"制造参差"会把文章改坏
    （配对复测证明人机无差异）。预设声明「C 级只报告」就必须真的报出数字，
    否则那句话是空承诺。

    实现刻意用 `splitlines()` 而不是 `re.split("\n")`：既避开转义坑，
    也让 CRLF / 空行混排的稿子按同一口径切分。
    """
    body = text or ""
    paragraphs: List[str] = []
    buffer: List[str] = []
    for line in body.splitlines():
        if line.strip():
            buffer.append(line.strip())
        elif buffer:
            paragraphs.append("".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append("".join(buffer))

    sentences: List[str] = []
    for line in body.splitlines():
        for piece in re.split(r"[。！？!?]+", line):
            if count_hanzi(piece) >= 2:
                sentences.append(piece)
    lens = [count_hanzi(s) for s in sentences]
    para_lens = [count_hanzi(p) for p in paragraphs]

    def _cv(values: List[int]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        if mean <= 0:
            return 0.0
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return round(var**0.5 / mean, 3)

    return {
        "paragraphs": len(paragraphs),
        "sentences": len(lens),
        "mean_sentence": round(sum(lens) / len(lens), 1) if lens else 0.0,
        "sentence_cv": _cv(lens),
        "paragraph_cv": _cv(para_lens),
    }


# ====================================================================== 质检


@dataclass
class QcFinding:
    """一条质检结果。"""

    detector: str
    label: str
    rule: str
    count: int
    per_ktx: float
    limit: float
    level: str
    human_ref: Optional[float] = None
    gate_class: str = "review"
    samples: List[str] = field(default_factory=list)
    hint: str = ""

    @property
    def passed(self) -> bool:
        return self.count <= self.limit if self.level == "count" else self.per_ktx <= self.limit

    @property
    def blocking(self) -> bool:
        """未达且属于「可清零」项 ⇒ 阻断交付。`review` 项超限只提示复核。"""
        return (not self.passed) and self.gate_class == "blocker"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "detector": self.detector,
            "label": self.label,
            "rule": self.rule,
            "count": self.count,
            "per_ktx": round(self.per_ktx, 3),
            "limit": self.limit,
            "human_ref": self.human_ref,
            "gate_class": self.gate_class,
            "passed": self.passed,
            "blocking": self.blocking,
            "samples": self.samples,
            "hint": self.hint,
        }


def qc_report(
    text: str,
    preset: Preset,
    reference: Optional[str] = None,
    max_samples: int = 3,
) -> Dict[str, Any]:
    """对文本跑该预设的质检门禁。

    Args:
        text: 待检文本（生成结果或改写结果）。
        preset: 用哪套门禁（来自预设的 `gates`）。
        reference: 改写的**原文**。提供时额外做「信息守恒」核对
            （原文的数字与引语必须在改后仍存在）—— 这是技能包里
            「实词都要能指出出处」唯一可机器化的部分。

    Returns:
        `{"ok", "total", "passed", "failed", "blockers", "items", "semantic", "conservation"}`
    """
    hanzi = count_hanzi(text)
    gates = preset.gate_map() or dict(PRESETS["qc-gate"].gates)
    items: List[QcFinding] = []
    hits = detect_text(text)

    for key, limit in gates.items():
        detector = DETECTORS.get(key)
        if detector is None:
            continue
        count = hits.get(key, 0)
        per_ktx = _per_ktx(count, hanzi)
        level = "density" if detector.unit == "density" else "count"
        samples = detector.find(text)[:max_samples] if count else []
        items.append(
            QcFinding(
                detector=key,
                label=detector.label,
                rule=detector.rule,
                count=count,
                per_ktx=per_ktx,
                limit=limit,
                level=level,
                human_ref=detector.human_ref,
                gate_class=detector.gate_class,
                samples=samples,
                hint=detector.note,
            )
        )

    conservation = check_conservation(reference, text) if reference else None
    x_guard = check_x_level(reference, text) if reference else None
    failed = [i for i in items if not i.passed]
    blockers = [i for i in failed if i.blocking]
    return {
        # 数字丢失或 X 级被误删也算不合格（后者是"改了不该改的"）
        "ok": not blockers and (conservation is None or conservation["ok"]) and (x_guard is None or x_guard["ok"]),
        "preset": preset.key,
        "hanzi": hanzi,
        "total": len(items),
        "passed": len(items) - len(failed),
        "failed": len(failed),
        "blockers": len(blockers),
        "reviews": len(failed) - len(blockers),
        "items": [i.as_dict() for i in items],
        "semantic": [{"key": k, "label": label, "hint": hint} for k, label, hint in SEMANTIC_CHECKS],
        "conservation": conservation,
        "x_guard": x_guard,
        "structure": structure_metrics(text),
    }


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_QUOTE_RES = (re.compile(r"「([^」]{1,80})」"), re.compile(r"“([^”]{1,80})”"), re.compile(r'"([^"]{1,80})"'))


def check_conservation(original: str, revised: str) -> Dict[str, Any]:
    """信息守恒核对：原文的数字与引语，改后必须仍然存在。

    只查**可枚举的实词**（数字、成对引号内的短句）。观点与限定词无法机判，
    那部分仍由预设的 `self_check` 约束模型。
    """
    numbers = _NUMBER_RE.findall(original or "")
    quotes: List[str] = []
    for pattern in _QUOTE_RES:
        quotes.extend(pattern.findall(original or ""))

    missing_numbers = [n for n in numbers if n not in (revised or "")]
    missing_quotes = [q for q in quotes if q not in (revised or "")]
    return {
        "numbers_total": len(numbers),
        "quotes_total": len(quotes),
        "missing_numbers": missing_numbers[:10],
        "missing_quotes": missing_quotes[:10],
        # 只有数字缺失才算不合格；引语差异只是待核（见 format_qc 的说明）
        "ok": not missing_numbers,
        "quotes_ok": not missing_quotes,
    }


def format_qc(report: Dict[str, Any], preset_name: str = "") -> str:
    """把质检结果渲染成人读文本（面板与报告共用）。"""
    lines = [
        f"质检预设：{preset_name or report.get('preset', '')}",
        f"篇幅：{report.get('hanzi', 0)} 汉字",
        f"门禁：{report.get('passed', 0)} 通过 / {report.get('failed', 0)} 未达"
        f"（其中阻断 {report.get('blockers', 0)}、需复核 {report.get('reviews', 0)}）",
        "说明：❌ 阻断项必须处理；⚠️ 为脚本粗筛，命中里可能含标题冒号、清单顿号、"
        "作者本人的破折号等合法写法，需逐条复核而非硬改。",
        "",
        "──────── 机器可判（脚本层） ────────",
    ]
    for item in report.get("items", []):
        if item["passed"]:
            mark = "✅"
        elif item.get("blocking"):
            mark = "❌"
        else:
            mark = "⚠️"  # 粗筛项：超限需复核，但技能包认可「误报/指纹保留」
        # 门禁单位统一为「次/千汉字」—— 与技能包报告一致；同时显示次数，
        # 避免短文本里"1 处 = 10/千字"造成的误读。
        metric = f"{item['count']} 次 · {item['per_ktx']:.2f}/千字（上限 {item['limit']:g}）"
        if item.get("human_ref") is not None:
            metric += f"，人类参考 {item['human_ref']:.2f}"
        lines.append(f"{mark} {item['label']}  {metric}")
        if item["samples"]:
            lines.append(f"    例：{' / '.join(item['samples'][:2])}")
    conservation = report.get("conservation")
    if conservation:
        lines.append("")
        lines.append("──────── 信息守恒（与原文比对） ────────")
        if conservation["ok"] and conservation.get("quotes_ok", True):
            lines.append(f"✅ 数字 {conservation['numbers_total']} 个、引语 {conservation['quotes_total']} 处均保留")
        else:
            # 数字是硬约束（技能包验收要求"关键数字仍在"）；
            # 「」也可能是强调而非引文，改写时可以合理改变 ⇒ 只提示核对。
            if conservation["missing_numbers"]:
                lines.append(f"❌ 丢失数字：{conservation['missing_numbers']}（必须补回）")
            if not conservation["ok"]:
                pass  # 上面已列缺失数字
            elif conservation["numbers_total"]:
                lines.append(f"✅ 数字 {conservation['numbers_total']} 个均保留")
            if conservation["missing_quotes"]:
                lines.append(
                    f"⚠️ 这些「」内容改后不同：{conservation['missing_quotes']}（若为强调而非引文可接受，请人工确认）"
                )

    guard = report.get("x_guard")
    if guard:
        lines.append("")
        lines.append("──────── X 级反向守卫（防误删已否决特征） ────────")
        if guard["ok"]:
            lines.append("✅ 序数词小标题、「这意味着」、引列表等 X 级特征数量未减少")
        else:
            for name, lost in guard["dropped"].items():
                lines.append(f"❌ {name} 改后少了 {lost} 处（X 级永不改，请核对是否误删）")

    structure = report.get("structure")
    if structure:
        lines.append("")
        lines.append("──────── C 级结构指标（只报告，不设门禁） ────────")
        lines.append(
            f"段落 {structure['paragraphs']} 段 · 句子 {structure['sentences']} 句 · "
            f"平均句长 {structure['mean_sentence']} 字"
        )
        lines.append(
            f"句长 CV {structure['sentence_cv']} · 段长 CV {structure['paragraph_cv']}"
            "（人机无差异，不为「参差」改句长）"
        )

    lines.append("")
    lines.append("──────── 待判读（语义层，脚本不下结论） ────────")
    for item in report.get("semantic", []):
        lines.append(f"· {item['label']}：{item['hint']}")
    return "\n".join(lines)


# ====================================================================== 管理器


def default_presets_file() -> Path:
    """预设状态文件（唯一来源，别在别处再拼一次）。"""
    return Path.home() / ".ai_novel_writer" / "writing_presets.json"


class PresetManager:
    """预设的启用状态与提示词装配。

    刻意**只管状态与装配**：预设定义是代码常量（`PRESETS`），
    用户改不了一份 JSON 就把规则改坏 —— 技能包的规则更新时预设自动跟上。
    """

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = Path(state_file) if state_file else default_presets_file()
        self._active = ""
        self._auto = True
        self.reload()

    # ------------------------------------------------------------------ 状态

    def reload(self) -> None:
        self._active = ""
        self._auto = True
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"[写作预设] 状态文件无法读取，已忽略：{exc}")
            return
        if not isinstance(data, dict):
            return
        active = str(data.get("active", "") or "")
        if active in PRESETS:
            self._active = active
        self._auto = bool(data.get("auto", True))

    def _save(self) -> bool:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                self.state_file,
                {"active": self._active, "auto": self._auto},
                indent=2,
            )
            return True
        except OSError as exc:
            logger.error(f"[写作预设] 状态保存失败：{exc}")
            return False

    @property
    def active(self) -> str:
        return self._active

    @property
    def auto(self) -> bool:
        return self._auto

    def activate(self, key: str) -> Tuple[bool, str]:
        if key and key not in PRESETS:
            return False, f"预设不存在：{key}"
        self._active = key
        self._save()
        if not key:
            return True, "已关闭写作预设（将回退到技能库原始规则）"
        return True, f"已启用预设「{PRESETS[key].name}」"

    def set_auto(self, enabled: bool) -> Tuple[bool, str]:
        self._auto = bool(enabled)
        self._save()
        return True, "已开启自动选择预设" if self._auto else "已关闭自动选择（只用手动指定的预设）"

    def current(self, text: str = "", stage: str = "") -> Optional[Preset]:
        """当前该用哪个预设：手动指定优先，其次按 `auto` 自动选。"""
        if self._active:
            return PRESETS.get(self._active)
        if not self._auto:
            return None
        key, _reason = match_preset(text, stage=stage)
        return PRESETS.get(key)

    def explain(self, text: str = "", stage: str = "") -> str:
        """给面板看的一句话：现在会用什么、为什么。"""
        if self._active:
            return f"手动指定：{PRESETS[self._active].name}"
        if not self._auto:
            return "自动选择已关闭，且未指定预设 —— 不注入预设"
        key, reason = match_preset(text, stage=stage)
        return f"自动选择：{PRESETS[key].name}（{reason}）"

    # ------------------------------------------------------------------ 装配

    def prompt_context(self, budget: int = 900, text: str = "", stage: str = "") -> str:
        """装配当前生效预设的提示词。

        ❗ 与 `SkillLibrary.prompt_context()` **互斥**：调用方二选一。
        同时注入会把同一批规则说两遍（见模块文档）。
        """
        preset = self.current(text=text, stage=stage)
        if preset is None:
            return ""
        return preset.to_prompt(rules=_library_rules(), budget=min(budget, preset.budget))


_library_cache: Any = None


def _library_rules() -> List[Any]:
    """取技能库里的规则（技能库不可用时返回空 —— 预设仍可用，只是少了细则）。"""
    global _library_cache
    if _library_cache is not None:
        return _library_cache
    try:
        from .skill_library import get_skill_library

        library = get_skill_library()
        if library is None:
            return []
        rules: List[Any] = []
        for skill in library.enabled_skills():
            rules.extend(skill.rules)
        _library_cache = rules
        return rules
    except Exception as exc:  # noqa: BLE001 - 预设是增强项
        logger.debug(f"[写作预设] 读取技能库失败：{exc}")
        return []


def build_preset_context(budget: int = 900, text: str = "", stage: str = "") -> str:
    """模块级便捷入口（`novel_agent` 用它，避免直接依赖管理器单例）。"""
    manager = get_preset_manager()
    return manager.prompt_context(budget=budget, text=text, stage=stage) if manager else ""


# ====================================================================== 单例

_manager: Optional[PresetManager] = None


def get_preset_manager() -> Optional[PresetManager]:
    """预设管理器单例；构造失败返回 `None`（增强项不该让主流程挂掉）。"""
    global _manager
    if _manager is not None:
        return _manager
    try:
        _manager = PresetManager()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[写作预设] 初始化失败：{exc}")
        return None
    return _manager


def reset_preset_manager() -> None:
    """清空单例（测试用）。同时清掉规则缓存。"""
    global _manager, _library_cache
    _manager = None
    _library_cache = None
