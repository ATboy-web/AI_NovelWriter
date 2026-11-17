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
from .text_stats import count_hanzi
from .text_stats import per_ktx as _per_ktx

__all__ = [
    "DETECTORS",
    "PRESETS",
    "Preset",
    "PresetManager",
    "QcFinding",
    "QC_LEVELS",
    "SEMANTIC_CHECKS",
    "build_preset_context",
    "review_criteria",
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

#: 汉字计数与密度换算下沉到 `text_stats`（唯一实现），原因有二：
#: ① `semantic_candidates` 也要用，留在这里会形成潜伏循环；
#: ② 汉字口径必须全仓一致，否则短文案门槛会时灵时不灵且不报错。
#: 顶部已 `from .text_stats import count_hanzi, per_ktx as _per_ktx`。


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
    #: 该检测器针对的**标点**（空 = 不是标点类）。
    #: 风格 DNA 声明「爱用某标点」时，质检据此放行 —— 这是"冲突以风格文档为准"的落点。
    mark: str = ""
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
        mark="——",
        note=">2/千字才优先处理；低于人类参考值的文本不因「缺少」而补写",
    ),
    "semicolon": Detector(
        key="semicolon",
        label="分号",
        rule="F 级指纹",
        patterns=(r"；",),
        mark="；",
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
    #: 人称混用是否算硬伤。**只有虚构叙事预设为 True** ——
    #: 技术文章里"我"与"你"并存是正常写法，用小说标准判会误伤合格稿。
    person_strict: bool = False
    #: 门禁刻意偏离「人类参考 × 系数」的项：`{detector: 理由}`。
    #: 存在理由 = 这个数字**不是**按人体参照算的，而是体裁策略（零容忍 / 放宽）。
    #: 审计时：超界必须有理由；有理由也必须在报告里对人可见 —— 不能默默放宽。
    gate_policy: Tuple[Tuple[str, str], ...] = ()

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
            "person_strict": self.person_strict,
        }

    def to_prompt(
        self,
        rules: Optional[Sequence[Any]] = None,
        budget: int = 900,
        dna: Optional[Any] = None,
    ) -> str:
        """装配成提示词段落。**按规则边界截断**，并说明还有多少条未注入。

        `dna`（`style_dna.StyleDNA`）存在时，紧跟标题插入「作者风格 DNA」段。
        位置很关键：它必须在规则**之前** —— 否则模型先读到"删破折号"，
        再看"破折号是作者特征"，规则已经生效了。
        """
        lines = [
            f"【写作预设：{self.name}】",
            f"阶段：{self.stage} —— {self.summary}",
        ]

        # 风格 DNA 优先于规则：作者特征高于通用判据（"冲突以风格文档为准"）
        dna_block = ""
        if dna is not None:
            from .style_dna import style_prompt

            dna_block = style_prompt(dna)
            if dna_block:
                lines.append(dna_block)

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
        # 起手式删除是零成本（删「说白了」不损失任何信息）⇒ 门禁收到 1.25 倍，
        # 不用"生成期难免"来放水
        gates=(("fanan", 0.50), ("colon_prompt", 0.20), ("starter", 0.01)),
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
        # 小说里人称跳变是硬伤（读者会不知道"谁在看"）
        person_strict=True,
        gate_policy=(
            (
                "fanan",
                "叙事中「不是A而是B」可承担人物心理与转折，比说明文宽容 3.6 倍；"
                "叙事体裁的 human_ref 尚无实测，待按本预设积累稿对后校准",
            ),
            (
                "long_attr",
                "长定语在场景描写里是正常的修饰铺陈，比说明文宽容 4 倍；同上待校准",
            ),
        ),
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
        # 短文案零容忍：一条模板腔就毁掉整句，没有"密度"可言 ⇒ 不用人体参照
        gates=(("fanan", 0.0), ("colon_prompt", 0.0), ("starter", 0.0)),
        gate_policy=(
            ("fanan", "短文案逐句人工判断，出现即改 ⇒ 零容忍，不按密度"),
            ("colon_prompt", "同上：一句话里出现提示语冒号就是模板腔"),
            ("starter", "同上：短文案里「说白了」几乎必然多余"),
        ),
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


#: 门禁相对「人类参考密度」的**合理倍数区间**。
#:
#: 门禁数字不能随手定：它必须能回答"为什么是 0.3 而不是 0.5"。
#: 技能包的做法是"人类参考 × 一个系数"——留出余量容忍正常波动。
#: 区间上下界是**守卫**：越过就说明要么数字拍脑袋了，要么这个检测器的
#: 人类参照需要按体裁重定（而不是直接放宽容差）。
GATE_FACTOR_RANGE: Tuple[float, float] = (1.0, 3.5)


def calibrated_limits(preset: "Preset") -> List[Dict[str, Any]]:
    """把预设门禁换算成「相对人类参考的倍数」，供审计与校准工具使用。

    返回每项：`{detector, label, limit, human_ref, factor, basis}`。
    `factor` 为 `None` 表示该检测器没有人类参照（如分号），只能人工定。
    """
    policy = dict(preset.gate_policy)
    rows: List[Dict[str, Any]] = []
    for key, limit in preset.gates:
        detector = DETECTORS.get(key)
        if detector is None:
            continue
        ref = detector.human_ref
        factor = round(limit / ref, 2) if ref else None
        reason = policy.get(key, "")
        rows.append(
            {
                "detector": key,
                "label": detector.label,
                "limit": limit,
                "human_ref": ref,
                "factor": factor,
                # basis 三档：按人体参照 / 有策略说明 / 无依据
                "basis": "policy" if reason else ("human_ref" if ref else "manual"),
                "policy": reason,
                # 门禁性质随行带回：调用方（校准工具）要据此区分"误判"与"提示噪音"
                "gate_class": detector.gate_class,
            }
        )
    return rows


def gate_factor_issues(preset: "Preset") -> List[str]:
    """返回超出合理倍数的门禁项（空列表 = 全部有据）。

    这不是"报错"，而是**提示该重定人类参照**：某检测器在合格稿上反复超标时，
    正确做法是按体裁重算 `human_ref`，硬放宽 `limit` 会让门禁失去意义。
    """
    low, high = GATE_FACTOR_RANGE
    issues: List[str] = []
    for row in calibrated_limits(preset):
        factor = row["factor"]
        if factor is None:
            continue
        if low <= factor <= high:
            continue
        # 超界但写了策略说明 ⇒ 合规（例如短文案零容忍、小说体裁放宽）
        if row["basis"] == "policy":
            continue
        issues.append(
            f"{preset.key}.{row['detector']}：门禁 {row['limit']:g} 是"
            f"人类参考 {row['human_ref']:g} 的 {factor:g} 倍，"
            f"超出 {low:g}–{high:g} ⇒ 应重定 human_ref，或在 gate_policy 写明理由"
        )
    return issues


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
    #: 被风格 DNA 放行（作者特征）。**保留原始数字**，只是不参与判定 ——
    #: 悄悄把计数改成 0 会让报告撒谎（用户以为这处写法消失了）。
    style_allowed: bool = False
    samples: List[str] = field(default_factory=list)
    hint: str = ""

    @property
    def passed(self) -> bool:
        if self.style_allowed:
            return True
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
            "style_allowed": self.style_allowed,
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
    dna: Optional[Any] = None,
    with_candidates: bool = True,
) -> Dict[str, Any]:
    """对文本跑该预设的质检门禁。

    Args:
        text: 待检文本（生成结果或改写结果）。
        preset: 用哪套门禁（来自预设的 `gates`）。
        reference: 改写的**原文**。提供时额外做「信息守恒」与「X 级反向守卫」
            —— 这是技能包「实词都要能指出出处」「X 级永不改」唯一可机器化的部分。
        with_candidates: 是否附带语义层候选（`semantic_candidates`）。默认开 ——
            "只有清单没有候选"等于让模型凭印象找，这是上一版最弱的一环。
        dna: 风格指纹（`style_dna.StyleDNA`）。提供时：
            ① 作者爱用的标点**从门禁放行**（不再反复提示删破折号）；
            ② 追加人称/句长/禁词比对。

    Returns:
        `{"ok", "total", "passed", "failed", "blockers", "reviews", "items",
           "semantic", "conservation", "x_guard", "structure", "style"}`
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
        # 风格 DNA 放行：作者明确声明爱用这个标点 ⇒ 作者特征高于通用判据
        style_allowed = bool(detector.mark and dna is not None and dna.allows_mark(detector.mark))
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
                style_allowed=style_allowed,
                samples=samples,
                hint=detector.note,
            )
        )

    conservation = check_conservation(reference, text) if reference else None
    x_guard = check_x_level(reference, text) if reference else None

    # 数字丢失 ⇒ **硬阻断**（技能包：「关键数字仍在改稿中」）。
    # 它不是一个"检测器"，但必须出现在 items 里 —— 否则报告显示"全部达标"
    # 却在别处判不合格，用户找不到原因。
    if conservation is not None and not conservation["ok"]:
        missing = conservation["missing_numbers"]
        items.append(
            QcFinding(
                detector="conservation",
                label="信息守恒（数字丢失）",
                rule="技能包最终验收",
                count=len(missing),
                per_ktx=0.0,
                limit=0,
                level="count",
                gate_class="blocker",
                samples=missing[:max_samples],
                hint="原文的数字必须在改后仍存在；丢失即篡改事实",
            )
        )

    drift = None
    if dna is not None:
        from .style_dna import style_drift

        drift = style_drift(text, dna, person_strict=preset.person_strict)

    # 语义层候选：把"要模型判的东西"抽出来，避免它通读全文凭印象挑几处
    candidates = None
    candidate_summary = None
    if with_candidates:
        try:
            from .semantic_candidates import extract_candidates, semantic_summary

            candidates = extract_candidates(text)
            candidate_summary = semantic_summary(candidates)
        except Exception as exc:  # noqa: BLE001 - 候选抽取失败不该让质检失败
            logger.warning(f"[写作预设] 语义候选抽取失败：{exc}")

    failed = [i for i in items if not i.passed]
    blockers = [i for i in failed if i.blocking]
    style_ok = drift is None or drift.ok
    return {
        # 三类不合格：阻断项未清、数字丢失、X 级被误删（含在 items 里）、风格硬偏离
        "ok": not blockers and (x_guard is None or x_guard["ok"]) and style_ok,
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
        "style": drift.as_dict() if drift is not None else None,
        "candidates": candidate_summary,
        "candidate_items": candidates.as_dict()["candidates"] if candidates is not None else None,
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


#: 评审视角的级别划分：哪些**可以扣分**、哪些**不许扣分**、哪些**不判**。
#:
#: 为什么需要这张表：`novel_agent._reviewer_evaluate` 原来内置了一份手写的
#: 「AI 写作痕迹检查」清单（"然而/不过"过渡词要扣分、"在这个世界上"开头要扣分），
#: 与技能库的实测结论**直接冲突** ——
#:
#: | 特征 | Reviewer 旧清单 | 技能库实测 |
#: |---|---|---|
#: | 「这意味着」复述 | 隐含要扣分 | **人类用得更多**（0.027 vs 0.016/千字）⇒ 永不改 |
#: | 序数词小标题 | 未提 | 人类 8.6% vs AI 4.9% ⇒ 永不改 |
#: | 空转句引列表 | 未提 | 人类高一个量级 ⇒ 永不改 |
#:
#: 写和评用两把尺的后果是修订循环互相拉扯：Writer 按预设保留，Reviewer 按清单扣分。
#: 所以评审的判据必须**从同一个规则源派生**（"同一事实写两处必然漂移"，本项目踩过 5 次）。
#:
#: 三档的含义见技能包 `DETECT.md`，这里只做归类，不重复判据原文。
_REVIEW_DEDUCT_LEVELS: tuple[str, ...] = ("A", "B")

#: 规则标题里出现这些词 = 技能包已明确"不再检测 / 永不改"，评审不得拿它扣分。
_RETIRED_MARKERS: tuple[str, ...] = ("降级", "已否决", "不再", "永不改", "已撤销")
_REVIEW_HINT_ONLY: tuple[str, ...] = ("C", "F")
_REVIEW_NEVER: tuple[str, ...] = ("X",)


def review_criteria(rules: Optional[Sequence[Any]] = None, budget: int = 760) -> str:
    """生成**给 Reviewer 智能体**的评审判据段落，与写作预设同源。

    为什么单独一个函数而不是复用 `Preset.to_prompt()`：预设是"怎么写"的约束
    （含最小改动、信息守恒等写作纪律），评审需要的是"怎么判"的口径
    （哪些算错、哪些不算错、哪些不许判）。两者的**级别归类相同、表述目的不同**。

    Args:
        rules: 技能库规则（`SkillRule` 列表）。为 `None` 时从技能库自动取。
        budget: 段落长度上限。

    Returns:
        可直接拼进 system prompt 的文本；技能库不可用时返回**仅含 X 级禁区**的
        最小版本（宁可少判，也不能让评审按旧清单乱扣分）。
    """
    selected = list(rules) if rules is not None else _library_rules()

    deduct: list[str] = []
    hint_only: list[str] = []
    for rule in selected:
        title = str(getattr(rule, "title", "") or "")
        # 只有**带编号的**才是可执行规则；「F 级单模型指纹的处置」这类是章节标题
        if _rule_number(title) is None:
            continue
        # 已降级 / 已否决的条目在技能包里明确"不再检测"，评审也不该拿它扣分
        if _RETIRED_MARKERS and any(marker in title for marker in _RETIRED_MARKERS):
            continue
        level = official_level(title) or str(getattr(rule, "level", "") or "")
        if level in _REVIEW_DEDUCT_LEVELS:
            deduct.append(f"- [{level}] {title}")
        elif level in _REVIEW_HINT_ONLY:
            hint_only.append(f"- [{level}] {title}")

    lines: list[str] = [
        "【评审判据（与写作预设同源，不得另立标准）】",
        "",
        "## 可扣分项（两条规则都有实测依据）",
    ]
    lines.extend(deduct[:12] or ["- （技能库未加载：请勿凭印象判定句式问题）"])

    lines.extend(
        [
            "",
            "## 只提示、不得扣分（配对复测方向反转或人机无差异）",
            "- 序数词小标题（人类 8.6% vs AI 4.9%）",
            "- 「这意味着」式复述（人类 0.027 vs AI 0.016 每千字）",
            "- 空转句引列表（人类高一个量级）",
            "- 概括替代（同段有具体数值也不改）",
            "- 句长/段长方差（两轮复测人机无差异，不为节奏改句长）",
        ]
    )
    if hint_only:
        lines.append("")
        # `item` 已自带 "- [级别] 标题"，别再补前缀
        lines.extend(f"{item}（只报告，不扣分）" for item in hint_only[:5])

    lines.extend(
        [
            "",
            "## 不得判定（模型间共识不足，交人审）",
            "- 比喻贴切度、暗喻、拟人化喻体 —— 模型对贴切度的共识只有 0–40%",
            "",
            "## 使用纪律",
            "- 上述「可扣分项」要指出**具体位置与原句**；指不出位置的扣分无效",
            "- 不在上述清单内的表达，按文学标准正常评价，但不得反推「像 AI」",
            "- 研究语料中显著 ≠ 本篇单次命中显著；不得据此断言作者是 AI",
        ]
    )

    text = "\n".join(lines)
    if len(text) > budget:
        text = text[: max(0, budget - 1)].rstrip() + "…"
    return text


def build_rewrite_instruction(
    report: Dict[str, Any],
    preset: "Preset",
    dna: Optional[Any] = None,
    budget: int = 1800,
) -> str:
    """把质检报告压成一段**可直接交给 Agent 的改写指令**（两段式的第二步）。

    为什么要有这一步：技能包的流程是「先出报告 → 等用户确认 → 再改写」，
    但"等确认"在桌面端靠什么保证？如果只写一句"先报告后改写"在提示词里，
    模型完全可以一步改完（它不会自己停下来）。

    所以把它做成**数据流**：第一步产出一份报告，第二步的指令只能由这份报告生成。
    跳过第一步 ⇒ 没有报告 ⇒ 生成不出指令。约束由此从"提示词里的请求"
    变成"流程里的前置条件"。

    Args:
        report: `qc_report()` 的返回值（必须含指标与候选）。
        preset: 生成该报告时用的预设。
        dna: 风格指纹（有则一并写进指令，避免改写时丢掉作者特征）。
        budget: 指令长度上限。
    """
    lines: List[str] = [
        "请按下面这份**已经完成的检测结论**改写正文。",
        "",
        "## 硬性约束",
        "1. 只改报告中列为「拟改」的项，每处改动必须能对应到规则编号；指不出的改动请撤销。",
        "2. 信息守恒：原文的数字、姓名、日期、引语、限定词（可能/通常/多数）必须保留。",
        "3. 结构不动：标题层级、段落顺序、列表/表格/引用/代码块位置原样保留。",
        "4. **下列特征永不改**（配对复测已推翻，改了反而更不像人）：",
        "   序数词小标题、「这意味着」式复述、空转句引列表、概括替代（同段有数据也不改）。",
        "5. 不制造参差：不为节奏改句长、不拆段落。",
        "6. 输出格式：改写后全文 + 逐处改动清单（原文 → 改后 + 规则编号）。",
        "",
    ]

    # 预设规范（与注入同源，避免"改写时不看规范"）
    preset_part = preset.to_prompt(budget=min(700, budget // 2), dna=dna)
    if preset_part:
        lines.append("## 写作预设（本次改写必须遵守）")
        lines.append(preset_part)
        lines.append("")

    # 机器判定结果
    lines.append("## 检测结果（脚本层，已判定）")
    lines.append(f"篇幅：{report.get('hanzi', 0)} 汉字")
    blockers = [i for i in report.get("items", []) if i.get("blocking")]
    reviews = [i for i in report.get("items", []) if not i["passed"] and not i.get("blocking")]
    allowed = [i for i in report.get("items", []) if i.get("style_allowed")]
    if blockers:
        lines.append("### 必须改（阻断项）")
        for item in blockers:
            samples = "；".join(item.get("samples", [])[:2])
            lines.append(
                f"- {item['label']}（{item['rule']}）：{item['count']} 处，"
                f"{item['per_ktx']:.2f}/千字（上限 {item['limit']:g}）" + (f"；例：{samples}" if samples else "")
            )
    if reviews:
        lines.append("### 需逐条判断（粗筛项，可保留但须给理由）")
        for item in reviews:
            samples = "；".join(item.get("samples", [])[:2])
            lines.append(
                f"- {item['label']}（{item['rule']}）：{item['count']} 处" + (f"；例：{samples}" if samples else "")
            )
    if allowed:
        lines.append("### 已放行（作者风格特征，不得改）")
        for item in allowed:
            lines.append(f"- {item['label']}：{item['count']} 处（风格 DNA 已声明为作者习惯）")

    # 候选清单
    candidates = report.get("candidate_items") or {}
    if candidates:
        lines.append("")
        lines.append("## 待判读候选（请按判据逐条判定 hit / miss / unsure）")
        from .semantic_candidates import JUDGE_LABELS, JUDGE_RULES

        for kind, items in candidates.items():
            if not items:
                continue
            lines.append(f"### {JUDGE_LABELS.get(kind, kind)}：{len(items)} 条")
            for item in items[:12]:
                if kind == "cohesion":
                    lines.append(f"- 第 {item['start']}–{item['end']} 段（{item['length']} 连环）")
                elif kind == "rename":
                    families = "、".join(f"{f['family']}({'/'.join(f['words'])})" for f in item["families"])
                    lines.append(f"- 第 {item['paragraph']} 段：{families}")
                elif kind == "colon_judge":
                    lines.append(f"- 第 {item['paragraph']} 段「{item['prefix']}：…」")
                else:
                    lines.append(f"- 第 {item['paragraph']} 段 {item['length']} 连：{item['sentences'][0]}")
            if len(items) > 12:
                lines.append(f"- （另有 {len(items) - 12} 条，见候选 JSON）")
        lines.append("")
        lines.append("判读纪律：" + "；".join(JUDGE_RULES))

    text = chr(10).join(lines)
    if len(text) > budget:
        text = text[: max(0, budget - 1)].rstrip() + "…"
    return text


def format_qc(report: Dict[str, Any], preset_name: str = "") -> str:
    """把质检结果渲染成人读文本（面板与报告共用）。"""
    lines = [
        f"质检预设：{preset_name or report.get('preset', '')}",
        f"篇幅：{report.get('hanzi', 0)} 汉字",
        f"门禁：{report.get('passed', 0)} 通过 / {report.get('failed', 0)} 未达"
        f"（其中阻断 {report.get('blockers', 0)}、需复核 {report.get('reviews', 0)}）",
        "说明：❌ 阻断项必须处理；⚠️ 为脚本粗筛（可能含标题冒号、清单顿号等合法写法），"
        "需逐条复核而非硬改；🎨 为风格 DNA 声明的作者特征，已放行。",
        "",
        "──────── 机器可判（脚本层） ────────",
    ]
    for item in report.get("items", []):
        if item.get("style_allowed"):
            mark = "🎨"  # 作者特征：风格 DNA 已放行，数字照实显示
        elif item["passed"]:
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

    style = report.get("style")
    if style:
        lines.append("")
        lines.append("──────── 风格 DNA 比对（作者特征优先） ────────")
        person = style.get("person") or {}
        if person.get("detail"):
            lines.append(("✅" if person.get("ok", True) else "❌") + f" 人称：{person['detail']}")
        sentence = style.get("sentence") or {}
        if sentence.get("detail"):
            lines.append(("✅" if sentence.get("ok", True) else "⚠️") + f" 句长：{sentence['detail']}")
        marks = style.get("marks") or {}
        if marks.get("detail"):
            flag = "·" if marks.get("advisory") else "✅"
            lines.append(f"{flag} 爱用标点：{marks['detail']}（作者特征，不算 AI 味）")
        banned = style.get("banned") or {}
        if banned.get("hits"):
            lines.append(f"❌ 禁词：{'、'.join(banned['hits'])}")
        elif banned:
            lines.append("✅ 禁词：无")

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
    candidates = report.get("candidates") or {}
    if candidates:
        basis = "已判读" if candidates.get("basis") == "judged" else "尚未判读（以下为候选数，非命中数）"
        lines.append(
            f"候选 {candidates.get('total', 0)} 条 · {basis} · "
            f"最长连环 {candidates.get('longest_chain', 0)} · "
            f"同构三连 {candidates.get('iso3_count', 0)} · "
            f"重命名 {candidates.get('rename_count', 0)} 次"
        )
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

    def prompt_context(
        self,
        budget: int = 900,
        text: str = "",
        stage: str = "",
        novel_dir: Optional[Any] = None,
    ) -> str:
        """装配当前生效预设的提示词。

        Args:
            novel_dir: 当前作品目录。提供时会读该作品的 `风格DNA.json` 一并注入 ——
                "冲突以风格文档为准"必须真的把文档带进提示词，否则只是句空话。

        ❗ 与 `SkillLibrary.prompt_context()` **互斥**：调用方二选一。
        同时注入会把同一批规则说两遍（见模块文档）。
        """
        preset = self.current(text=text, stage=stage)
        if preset is None:
            return ""
        dna = None
        if novel_dir:
            try:
                from .style_dna import load_style_dna

                dna = load_style_dna(novel_dir)
            except Exception as exc:  # noqa: BLE001 - 风格 DNA 是加分项
                logger.debug(f"[写作预设] 读取风格 DNA 失败：{exc}")
        return preset.to_prompt(rules=_library_rules(), budget=min(budget, preset.budget), dna=dna)


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


def build_preset_context(
    budget: int = 900,
    text: str = "",
    stage: str = "",
    novel_dir: Optional[Any] = None,
) -> str:
    """模块级便捷入口（`novel_agent` 用它，避免直接依赖管理器单例）。"""
    manager = get_preset_manager()
    if manager is None:
        return ""
    return manager.prompt_context(budget=budget, text=text, stage=stage, novel_dir=novel_dir)


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
