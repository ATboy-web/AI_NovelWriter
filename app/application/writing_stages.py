"""四个写作阶段的用例实现（PlotDesigner / Writer / Reviewer / Editor）。

## 为什么从 `novel_agent.py` 搬出来

`novel_agent.py` 有 2800+ 行，其中"每个 Agent 怎么拼提示词、怎么校验返回"
是**可以直接被测试的纯编排逻辑**，却和历史悠久的 `NovelAgent` 混在一起：
想验"评审失败时分数必须是 None"，必须先造一个能动起来的 Agent。

搬出来之后，每个阶段是一个只有 `execute()` 的类，依赖通过 `StageDeps` 注入。

## 为什么依赖是 callable 而不是接口

`build_context`（动态上下文工程）与 `long_chapter`（分段续写）本身还有依赖
（memory 的 6 个读取方法、config 的上下文窗口）。把它们一起搬等于顺手重写
核心算法 —— 那是另一件事。这里只注入"能调用"的形态，等它们准备好了再搬。

## 契约由 `tests/test_novel_agent_five_stage_contract.py` 钉住（74 条）

那个文件在搬迁前后**一条都没改**，是这次结构改动的安全网：
- 评审失败 ⇒ `overall_score is None`（不许回落成 70 分）
- 评审抛异常 ⇒ 正文保留
- 修订稿不足原文一半 ⇒ 返回原文
- 正文/修订 `allow_reasoning_fallback=False`
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict

from app.domain.plot import normalize_plot_analysis
from app.parsing import parse_json_response

__all__ = [
    "AnalyzePlot",
    "BuildWorldScene",
    "EvaluateReview",
    "GenerateDraft",
    "ReviseDraft",
    "StageDeps",
]


@dataclass
class StageDeps:
    """阶段共享依赖。

    `log` 刻意是普通 callable（不是 logging 对象）—— 上层传进来的就是
    `NovelAgent.log`，它有自己的一套"往面板推一行"的语义。
    """

    ai: Any
    memory: Any
    log: Callable[[str], None]
    build_context: Callable[..., str]
    writing_style: Callable[[], str]
    long_chapter: Callable[..., str] | None = None
    #: 写进评审记录，用于"这条分数是哪个模型给的"
    model_name: str = ""


class BuildWorldScene:
    def __init__(self, deps: StageDeps) -> None:
        self.deps = deps

    def execute(self, chapter_num: int, plot_analysis: Dict) -> str:
        """WorldBuilder：从作品设置里取出已知区域，拼成场景提示。"""
        settings = self.deps.memory.get_settings()
        if settings and isinstance(settings, dict):
            world = settings.get("world", {})
            if isinstance(world, dict):
                known = world.get("已知区域", [])
                # settings.json 是用户可编辑的，形状不可信：
                # - 写成字符串 ⇒ 当单个区域（否则 `join` 会把字逐字拆开）
                # - 写成 dict/数字 ⇒ 直接视为无（切片会抛 TypeError）
                if isinstance(known, str):
                    known = [known]
                if isinstance(known, (list, tuple)):
                    cleaned = [str(item).strip() for item in known[:3] if str(item).strip()]
                    if cleaned:
                        return f"世界观场景: {', '.join(cleaned)}"
        return ""


class AnalyzePlot:
    def __init__(self, deps: StageDeps) -> None:
        self.deps = deps

    def execute(self, chapter_num: int, title: str, outline: str) -> Dict:
        """PlotDesigner: 分析情节类型、节奏、伏笔"""
        if not outline or len(outline) < 10:
            if chapter_num <= 3:
                plot_type = "opening"
            elif chapter_num % 10 == 0:
                plot_type = "ending"
            else:
                plot_type = "writing"
            return {"type": plot_type, "pace": "medium", "foreshadowing": []}

        system = '你是专业情节设计师。分析章节大纲，输出JSON: {"type": "opening/writing/action/dialogue/ending", "pace": "slow/medium/fast", "foreshadowing": []}'
        prompt = f"第{chapter_num}章: {title}\n大纲: {outline[:500]}"
        try:
            response = self.deps.ai.chat(
                [{"role": "user", "content": prompt}], system=system, max_tokens=1000, thinking_enabled=False
            )
            # P2-7 收敛：此前这里是手写的「括号深度追踪 + 正则兜底」两段解析
            # （约 30 行，含 `import re`、两处 `re.sub` 尾逗号修复）。
            # 改为走全仓唯一实现 `parse_json_response`：其 Strategy 1（截取 `{…}`）/
            # Strategy 2（去 markdown 后截取）/ Strategy 3（字符串感知 + 朴素两种修复）
            # 是本处逻辑的**严格超集**，且额外覆盖单引号、弯引号、
            # 截断补全（Strategy 4）。原来的「括号深度追踪」在此场景没有额外收益：
            # 期望结果是 dict，`parse_json_response` 的 Strategy 1 已按
            # `text.find("{")` + `text.rfind("}")` 取同一区间。
            parsed = parse_json_response(response, None)
            if isinstance(parsed, dict):
                return normalize_plot_analysis(parsed)
        except Exception as e:
            self.deps.log(f"[PlotDesigner] 分析失败: {e}")
        return {"type": "writing", "pace": "medium", "foreshadowing": []}


class GenerateDraft:
    def __init__(self, deps: StageDeps) -> None:
        self.deps = deps

    def execute(
        self,
        chapter_num: int,
        chapter_title: str,
        chapter_outline: str,
        word_count: int,
        context: str = None,
        prev_ending: str = "",
    ) -> str:
        """Writer智能体：生成章节内容"""
        if context is None:
            context = self.deps.build_context(chapter_num)

        # === 缓存优化策略 ===
        # 将"固定写作指南"放在 system prompt 最前面，作为 DeepSeek 缓存前缀
        # 将"每章动态上下文"放在最后面，这样不同章节的 system prompt 前缀相同
        # 缓存命中率可以从 13.7% 提升到 60%+

        # 🔒 读取锁定的主角名
        protagonist = self.deps.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f'\n\n【重要·主角锁定】本小说主角名为「{protagonist}」。所有章节必须以「{protagonist}」为主视角，禁止更换主角名！如果大纲中写"主角"，实际就是「{protagonist}」。'

        # --- 缓存前缀部分（固定，所有章节共用）---
        cache_prefix = f"""你是一位专业的小说作家（Writer Agent）。

【写作风格要求】
{self.deps.writing_style()}

【正向要求 - 你必须做到】
1. 【最重要】必须紧接前一章结尾继续，保持时间、地点、情节的绝对连贯！
2. 角色行为符合其性格设定，保持人物形象一致
3. 情节推进自然流畅，有起承转合
4. 语言生动形象，有画面感和代入感
5. 直接输出正文内容，不要添加额外说明
6. 巧妙设置伏笔和悬念，吸引读者继续阅读
7. 对话要符合角色性格，有个性化特征
8. 场景描写要有细节，调动五感（视觉、听觉、嗅觉、触觉、味觉）
9. 适当运用修辞手法（比喻、拟人、排比等）增强文采
10. 目标字数约{word_count}字，必须写够字数

【负面禁止 - 绝对不能做】
1. 禁止使用Markdown格式（禁止**加粗**、*斜体*、#标题等标记），使用纯文本
2. 禁止出现重复内容、凑字数的废话
3. 禁止角色行为前后矛盾（如性格突变、能力突变）
4. 禁止情节逻辑漏洞（如时间线混乱、因果关系错误）
5. 禁止使用现代网络用语（如"666"、"yyds"等），保持文风统一
6. 禁止在正文中出现作者旁白、元叙述（如"接下来会发生什么"）
7. 禁止突然跳出故事视角（如"读者可能会想"）
8. 禁止使用过多的"的"、"了"、"着"等助词堆砌
9. 禁止对话过于书面化，要口语化、自然
10. 禁止场景转换生硬，要有过渡
11. 【重要】禁止无故引入新角色！必须使用【当前剧情线角色】中已有的角色
12. 【重要】如果必须引入新角色，必须给出明确的出场原因和后续作用

【AI写作痕迹禁止 - 必须避免】
1. 禁止以"在这个世界上"、"在这个时代"等开头
2. 禁止过度使用"然而"、"不过"、"尽管如此"等过渡词
3. 禁止以"故事才刚刚开始"、"命运的齿轮开始转动"等结尾
4. 禁止形容词堆砌（如"美丽动人可爱"）
5. 要用具体动作和细节展示，不要直接告诉读者"""

        # --- 动态上下文部分（每章不同，放在缓存前缀后面）---
        dynamic_context = f"""{context}
{protagonist_hint}
请根据以上上下文信息创作小说章节。"""

        system = cache_prefix + "\n\n" + dynamic_context

        # 直接使用传入的前一章结尾（从generate_with_collaboration提取，未被压缩）
        if not prev_ending and "【前一章" in str(context):
            import re as _re

            m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)", str(context), _re.DOTALL)
            if m:
                prev_ending = m.group(1).strip()[-800:]

        if prev_ending:
            prompt = f"【前一章结尾 — 你必须紧接以下内容继续创作】\n{prev_ending}\n\n---\n\n请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文（必须紧接前文）："
        else:
            prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："

        if word_count > 3000 and self.deps.long_chapter is not None:
            return self.deps.long_chapter(chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending)

        # 动态计算max_tokens：中文约2 tokens/字，预留足够空间
        max_tokens = max(word_count * 2, 8192)
        # 同分段生成：正文不要思考，也不要 reasoning 兜底
        response = self.deps.ai.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=max_tokens,
            thinking_enabled=False,
            allow_reasoning_fallback=False,
        )
        self.deps.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response) if response else 0}")
        return response or ""


class EvaluateReview:
    def __init__(self, deps: StageDeps) -> None:
        self.deps = deps

    def execute(self, chapter_num: int, content: str, previous_feedback: str = "") -> dict:
        """Reviewer智能体：审校章节

        参考AutoGen的code_reviewer角色，检查质量和一致性
        """
        context = self.deps.build_context(chapter_num)

        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n上次审校反馈（请重点关注）：\n{previous_feedback}"

        # === 缓存优化策略（与Writer相同）===
        # 固定评审规则在前（缓存前缀），动态内容在后

        cache_prefix = """你是一位专业的小说审校编辑（Reviewer Agent）。

【正向检查 - 重点关注优点】
1. 角色塑造是否立体、有成长弧线
2. 情节是否有张力、有悬念
3. 文笔是否生动、有画面感
4. 情感表达是否真挚、有感染力
5. 节奏把控是否得当、有起伏
6. 伏笔设置是否巧妙、有回收
7. 世界观设定是否一致、有深度
8. 对话是否自然、符合角色性格
9. 场景描写是否有细节、氛围感
10. 章节结尾是否有悬念、吸引继续阅读

【负面检查 - 重点发现问题】
1. 角色行为是否前后矛盾（如性格突变、能力突变）
2. 情节是否有逻辑漏洞（如时间线混乱、因果错误）
3. 是否有重复内容或凑字数的情况
4. 文风是否突然变化（如从古风突变现代）
5. 关键设定是否与前文冲突
6. 场景转换是否生硬、缺乏过渡
7. 是否有明显的错别字或语病
8. 是否有过于冗长、拖沓的段落

【AI写作痕迹检查】

⚠️ 这一项**不再使用手写清单**，判据由技能库统一提供（见下方注入的「评审判据」）。

原清单（"在这个世界上"开头、"然而/不过"过渡词、"故事才刚刚开始"结尾）
已废弃，原因：它与技能库的实测结论冲突 ——
「这意味着」式复述、序数词小标题等在 270 对同题同事实配对复测中
**人类用得比 AI 更多**，据此扣分等于惩罚人类写法。
"然而/不过"只在与技能库「句首连接词」规则同时命中时才处理。

【原创技巧类提示（不是扣分项，只在 suggestions 里提一句）】
1. 是否以"在这个世界上"、"在这个时代"这类空泛时空壳开头
2. 是否以"故事才刚刚开始"、"命运的齿轮开始转动"结尾
3. 是否有形容词堆砌（如"美丽动人可爱"）
4. 是否有 AI 式元叙述（如"读者可能会想"）
这四条**没有实测依据**，属经验性套路；只当写作建议，不得计入六维度评分。"""

        dynamic_context = f"""{context}
{feedback_section}
请根据以上上下文严格检查以下章节内容的各方面质量。

请以JSON格式输出审校结果：
{{
    "character_consistency": 0-100,
    "plot_logic": 0-100,
    "writing_quality": 0-100,
    "emotional_impact": 0-100,
    "pacing": 0-100,
    "overall_score": 0-100,
    "strengths": ["优点1", ...],
    "issues": ["问题1", ...],
    "suggestions": ["建议1", ...],
    "is_acceptable": true/false
}}"""

        # 评审判据从技能库派生 —— 与写作预设同源，避免「写」和「评」用两把尺
        try:
            from app.writing_presets import review_criteria

            criteria = review_criteria()
        except Exception as exc:  # noqa: BLE001 - 判据取不到不该中断评审
            self.deps.log(f"[评审] 取技能库判据失败，使用最小判据: {exc}")
            criteria = ""
        if criteria:
            cache_prefix = cache_prefix + "\n\n" + criteria

        system = cache_prefix + "\n\n" + dynamic_context

        # 采样：开头2000 + 中间1000 + 结尾1000，覆盖全文
        sample_parts = []
        if len(content) > 4000:
            sample_parts.append(content[:2000])
            mid = len(content) // 2
            sample_parts.append(content[mid - 500 : mid + 500])
            sample_parts.append(content[-1000:])
            sample = "\n...（中间省略）...\n".join(sample_parts)
        else:
            sample = content

        prompt = f"请审校第{chapter_num}章内容：\n\n{sample}"
        # 评审要的是 JSON：先想几千字再输出 JSON，既慢又容易把预算耗在思考上
        # （本次两章评审全部失败的成因）。关掉思考，并要求"拿不到成品就报错"。
        response = self.deps.ai.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=4000,
            thinking_enabled=False,
            allow_reasoning_fallback=False,
        )

        # 🔴 失败不伪装：解析不出来就给 None + error，**不再回落成 70 分**。
        # 旧实现 `{"overall_score": 70}` 让"评审失败"看起来像"70 分"，
        # 而 70 分通常就在及格线附近 ⇒ 失败被记成通过。
        from app.review_store import normalize_review, save_review

        try:
            raw = parse_json_response(response or "{}", {})
        except Exception as exc:  # noqa: BLE001 - 解析失败是预期分支
            raw = {"error": f"评审结果解析失败：{exc}"}
        # 解析器在"期望 dict 但 AI 返回顶层数组"时会给出 list。
        # `normalize_review` 内部也检查类型，但**调用点自证**才能被
        # `tests/test_parse_type_contract.py` 的静态守卫识别 —— 那道守卫专门
        # 用来防"新增调用点忘了判类型"，绕过去等于让它失效。
        if not isinstance(raw, dict):
            raw = {"error": f"评审结果类型异常（{type(raw).__name__}），需人工确认"}

        record = normalize_review(raw, chapter_num, model=self.deps.model_name)
        save_review(getattr(self.deps.memory, "novel_dir", None), record)
        if not record.ok:
            self.deps.log(f"[Reviewer] ⚠️ 评审未完成（{record.error}），本章无可用分数")
        return record.as_dict()


class ReviseDraft:
    def __init__(self, deps: StageDeps) -> None:
        self.deps = deps

    def execute(
        self,
        chapter_num: int,
        original: str,
        review: dict,
        chapter_outline: str,
        context: str = None,
        prev_ending: str = "",
    ) -> str:
        """Writer智能体：根据审校意见修订章节

        参考AutoGen的迭代优化循环
        """
        suggestions = review.get("suggestions", [])
        issues = review.get("issues", [])
        strengths = review.get("strengths", [])

        if context is None:
            context = self.deps.build_context(chapter_num)

        # 🔒 读取锁定的主角名
        protagonist = self.deps.memory.get_meta("protagonist", "")
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n\n【重要·主角锁定】主角名为「{protagonist}」，修订时不得更换主角名！"

        # 前一章结尾提示
        ending_hint = ""
        if prev_ending:
            ending_hint = f"\n\n【前一章结尾 — 修订后仍需紧接此情节】\n{prev_ending[-600:]}"

        system = f"""你是一位专业的小说作家（Writer Agent），正在修订自己的作品。
{context}
{protagonist_hint}
{ending_hint}

修订原则：
1. 根据审校意见进行针对性修改
2. 保留已有的优点和长处
3. 修改时注意不要破坏整体的连贯性
4. 回应每一个具体问题"""

        # 计算需要的token数（中文约2 tokens/字，需要输出完整章节）
        original_len = len(original)
        # 修订需要输出完整章节，所以max_tokens要足够大
        needed_tokens = max(8192, int(original_len * 2.5))

        # 采样策略：开头2000 + 中间1000 + 结尾2000，让AI了解全文结构
        if original_len > 5000:
            mid = original_len // 2
            original_sample = (
                original[:2000]
                + "\n...(中间省略)...\n"
                + original[mid - 500 : mid + 500]
                + "\n...(省略)...\n"
                + original[-2000:]
            )
        else:
            original_sample = original

        prompt = f"""请修订第{chapter_num}章内容。

审校反馈：
优点（请保持）：{json.dumps(strengths, ensure_ascii=False)}
问题（需修改）：{json.dumps(issues, ensure_ascii=False)}
建议（参考）：{json.dumps(suggestions, ensure_ascii=False)}

原文（共{original_len}字）：
{original_sample}

修订要求：
1. 输出完整的修订后文本（不少于{original_len}字）
2. 针对审校反馈的问题进行修改
3. 保持原文的优点和情节连贯性
4. 直接输出正文，不要输出分析过程："""

        # 修订稿会**覆盖**正文：必须不思考、不兜底。
        # 否则「用户希望我…让我想想…」会被当成修订结果写进书里，
        # 而字数还能通过"不少于原文"的检查（推理往往比正文长），
        # 反而更容易骗过闸门。
        response = self.deps.ai.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=needed_tokens,
            thinking_enabled=False,
            allow_reasoning_fallback=False,
        )

        # 如果修订后字数明显变短，可能是AI截断了，返回原文
        if response and len(response) < original_len * 0.5:
            self.deps.log(f"[Writer] 修订后字数({len(response)})过短，保留原文({original_len}字)")
            return original

        self.deps.log(f"[Writer] 修订完成，字数：{len(response) if response else 0}")
        return response or original
