"""分段生成长章节：把"一次写完 6000 字"拆成多段，保证结尾完整。

## 为什么要分段

单次请求给 6000 字，模型常在末尾被 max_tokens 截断 —— 表现是**烂尾**：
话说到一半没了，或者末段草草收场。分段后每段 2000 字，
末段专门要求"事件推进 + 情绪落点"，并检查有没有断在半句。

## 依赖

只依赖 `ai.chat`、`memory.get_meta`（锁定主角名）与 `log`。
截断判定走 `domain.prose.looks_truncated`（纯规则，可穷举测试）。
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.domain.prose import looks_like_planning, looks_truncated

__all__ = ["GenerateLongChapter"]


class GenerateLongChapter:
    """按段生成整章；每一段都带着前一段的结尾做衔接。"""

    def __init__(self, ai: Any, memory: Any, log: Optional[Callable[[str], None]] = None) -> None:
        self.ai = ai
        self.memory = memory
        self.log = log or (lambda _message: None)

    def execute(self, chapter_num, chapter_title, chapter_outline, word_count, context, prev_ending="") -> str:
        """分段生成长章节 - 确保每章结尾完整自然"""
        seg_size = 2000
        part_count = max((word_count + seg_size - 1) // seg_size, 1)
        part_count = min(part_count, 8)

        # 标题处理
        clean_title = chapter_title or ""
        if clean_title.startswith("第") and "章" in clean_title[:6]:
            clean_title = f"第{chapter_num}章"
        else:
            clean_title = f"第{chapter_num}章：{clean_title}"
        title_line = f"# {clean_title}\n\n"

        parts = []
        for i in range(part_count):
            is_last = i == part_count - 1
            self.log(f"[Writer] 第{chapter_num}章 第{i + 1}/{part_count}段...")

            prev_text = "".join(parts)
            if i == 0:
                # 第一段：使用传入的前一章结尾（未被压缩）
                if not prev_ending and context and "【前一章" in str(context):
                    import re as _re

                    m = _re.search(r"【前一章·第\d+章结尾.*?】\n(.+?)(?:\n【|\Z)", str(context), _re.DOTALL)
                    if m:
                        prev_ending = m.group(1).strip()[-800:]
                if prev_ending:
                    part_prompt = f"【前一章结尾 — 必须紧接以下内容】\n{prev_ending}\n\n---\n\n创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文（必须紧接前文）："
                else:
                    part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n请创作约{seg_size}字的小说正文："
            elif is_last:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                # ❗ D15 修复：原提示词只说"给出自然完整的**段落**结尾"。
                # 这会把末段写成"场景收尾"而不是"章节落点" —— 分段生成的章节
                # 于是呈现"每段各自了结、整章没有推进"的观感，也就是读者说的**烂尾**。
                # 末段是本章唯一的定调位置，必须明确要求：本章要有**事件推进**与
                # **情绪落点**，且不得复述前文。
                part_prompt = (
                    f"紧接上文继续写。上文结尾：{last_200}\n"
                    f"这是本章的最后一段（约{seg_size}字）。要求：\n"
                    f"1. 必须**推进实质剧情**（发生一件前面没有的事），不得只是回顾或抒情收束；\n"
                    f"2. 结尾要落在**本章的核心冲突/转折**上，形成章节落点，而不是平淡的场景收尾；\n"
                    f"3. 不要总结全章、不要复述已有情节、不要写「本章完」之类的话；\n"
                    f"4. 直接接续上文文字，不要重复上文任何句子。"
                )
            else:
                last_200 = prev_text[-200:] if len(prev_text) > 200 else prev_text
                part_prompt = f"紧接上文继续写。上文结尾：{last_200}\n要求：继续推进剧情约{seg_size}字，严禁重复。"

            for attempt in range(3):
                try:
                    # 🔒 读取锁定的主角名
                    protagonist = self.memory.get_meta("protagonist", "")
                    protagonist_hint = f"\n【重要】主角名为「{protagonist}」，禁止更换！" if protagonist else ""

                    # 🔴 正文生成**必须关闭思考**：
                    # 开启时 4096 的预算会被 reasoning 吃光，content 为空后
                    # 客户端会退回 reasoning —— 那一整段就会变成"用户希望我…让我想想…"
                    # 的工作笔记写进章节（本次事故的确切成因）。
                    # `allow_reasoning_fallback=False` 是第二道闸：宁可报错重试，
                    # 也不把半成品当成品。
                    response = self.ai.chat(
                        [{"role": "user", "content": part_prompt}],
                        system=f"严密续写，绝不重复。每段给出自然结尾。禁止Markdown格式。{protagonist_hint}\n{context[:1500] if context else ''}",
                        max_tokens=4096,
                        thinking_enabled=False,
                        allow_reasoning_fallback=False,
                    )
                    if response and len(response) > 100:
                        # 第三道闸：即使 provider 忽略了 thinking_enabled，
                        # 规划文字也不能落盘。抛异常走重试，重试仍坏则保留已有段落。
                        if looks_like_planning(response):
                            raise ValueError("返回内容疑似创作规划（内心独白/提纲），不是小说正文")
                        # 去除AI生成的标题
                        lines = response.split("\n", 2)
                        clean = []
                        for line in lines:
                            stripped = line.strip()
                            if (
                                stripped.startswith("#") or (stripped.startswith("第") and "章" in stripped[:10])
                            ) and not clean:
                                continue
                            clean.append(line)
                        response = "\n".join(clean)
                        parts.append(response)
                        break
                except Exception as e:
                    # 认证错误不重试
                    if "401" in str(e) or "Authorization" in str(e) or "API Key" in str(e):
                        raise
                    self.log(f"[Writer] 第{chapter_num}章第{i + 1}段 重试{attempt + 1}: {e}")
                    if attempt == 2:
                        return title_line + ("\n\n".join(parts) if parts else "（生成失败）")

        result = title_line + ("\n\n".join(parts) if parts else "（生成失败）")

        # 末段完整性检查：如果结尾没有句号/感叹号/问号等，AI补全
        #
        # ❗ D18 修复：原实现有三个问题，合起来**主动弄坏了本来完整的结尾**：
        #   1. 判据是"最后一个字符不是终止符"。但 `…` / `—` / `"` 都在白名单里，
        #      于是大量**正常**结尾（以引号或省略号收束的对话）被误判为"不完整"；
        #   2. 判据只看**单字符**，不看语义：`"他走了。"` 以 `"` 收尾会被判不完整，
        #      实际上它比任何补全都完整；
        #   3. 补全文字是**直接 `+=` 追加**的 —— 即使在正确判定的情况下，
        #      追加也必然把"已经说完的话"接上"另一段话"，读起来就是**断裂**，
        #      这正是烂尾观感的一部分。
        #
        # 现在的策略是**保守**：只在"末尾明显断在半句/半词"时才补，
        # 并优先用**句读补全**（几乎不可见），拿不准就**不动** ——
        # "少做"比"把好结尾改坏"安全得多。
        if parts and len(result) > 500:
            last_meaningful = result.rstrip("\n\r \t'\"》）」】…—")
            if last_meaningful:
                last_char = last_meaningful[-1]
                # 只有这些字符能确认"句子说完了"。注意**不含**引号与破折号：
                # 它们既可能收尾也可能收在句中，不足以判断完整性。
                sentence_end = {"。", "！", "？", ".", "!", "?", "；", ";"}
                # 直接以句末标点收尾 ⇒ 完整，**不碰它**
                if last_char in sentence_end:
                    pass
                elif looks_truncated(last_meaningful):
                    self.log(f"[Writer] 第{chapter_num}章末尾疑似断句，尝试补全…")
                    try:
                        last_paragraph = result[-500:]
                        completion = self.ai.chat(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        "以下小说段落在结尾处断了。请只补一个**短语**（10-30字）"
                                        f"把它接成完整句子，不要开启新的情节：\n{last_paragraph}"
                                    ),
                                }
                            ],
                            system="你是文字校对。只输出补全的短语本身，不要重复已有内容，不要换行。",
                            max_tokens=1000,
                            # 补全只有 10–30 字：1000 的预算若被思考吃掉，
                            # 拿回来的是分析过程，会被"与原文重复/过长"判据丢弃，静默失效
                            thinking_enabled=False,
                            allow_reasoning_fallback=False,
                        )
                        completion = (completion or "").strip()
                        # ❗ 与原文重叠的补全一律丢弃（`in` 判据比原来的
                        # `completion[:10] in result[-50:]` 更严：后者只查开头 10 字）
                        if completion and completion not in result and len(completion) <= 60:
                            result += completion
                        elif completion:
                            self.log("[Writer] 补全内容与原文重复或过长，已放弃追加")
                    except Exception as e:
                        self.log(f"[长章节末段补全] 失败: {e}")
                else:
                    # 无法确定是否断句 ⇒ **宁可不动**。静默是最安全的选择。
                    # 措辞要如实：这句原本写"判为完整"，但实际含义是"判不出来所以不动"，
                    # 看日志的人会误以为系统确认了完整性。
                    self.log(f"[Writer] 第{chapter_num}章末尾以「{last_char}」收尾，无法判定是否断句，保持原样不补全")

        return result
