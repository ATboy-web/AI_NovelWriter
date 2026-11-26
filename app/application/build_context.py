"""动态上下文工程：按写作阶段分配上下文预算。

## 为什么在 application 层

这是纯编排：从 memory 读 6 类数据 → 按 `CONTEXT_RATIOS` 分配字数预算 →
压缩 → 拼成给 Writer/Reviewer 的上下文。它不写盘、不发网络请求，
但会决定"模型能看到哪些前情" —— 属于应用层的组装职责。

## 一个容易搞错的点

预算单位是**字符**，不是 token。换算入口在 `app.token_estimator`，
调用方（`NovelAgent._build_context`）负责把上下文窗口换成字符预算。
本类只负责"在给定预算内怎么分"。
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from app.domain.plot import CONTEXT_RATIOS
from app.token_estimator import chars_for_context_window

__all__ = ["BuildContext"]


class BuildContext:
    """组装一章的写作上下文。

    `context_window` 是模型的上下文窗口（token）。调用方负责从配置里取，
    本类不碰配置对象 —— 那样会把"配置怎么存"耦合进用例。
    """

    def __init__(
        self,
        memory: Any,
        log: Optional[Callable[[str], None]] = None,
        context_window: int = 30000,
    ) -> None:
        self.memory = memory
        self.log = log or (lambda _message: None)
        self.context_window = context_window

    def execute(
        self, chapter_num: int, extra_context: str = "", max_chars: int = None, writing_phase: str = "writing"
    ) -> str:
        """动态上下文工程 - 根据写作阶段智能分配比例 (Hello-Agents参考)

        写作阶段:
        - opening: 开头阶段，需要更多世界/角色描述
        - writing: 常规写作，平衡分配
        - action: 动作场景，需要近章上下文
        - dialogue: 对话场景，需要角色信息
        - ending: 结尾阶段，需要全局摘要
        """
        if max_chars is None:
            # v3 §3.5(3)：换算口径收敛到 token_estimator，与 v2 的
            # `context_window // 3` **等效**（32000 → 10666，无配置 → 10000）。
            # 有意保留这个保守除数：窗口里还要装提示词模板、指令与输出预算。
            window = self.context_window
            max_chars = chars_for_context_window(window)

        # 动态比例分配 — extra_context(前文内容)是连贯性关键，必须占大比例。
        # 表在模块级（`CONTEXT_RATIOS`）：`PLOT_TYPES` 由它的键派生，
        # 不必在两处同步维护"有哪些情节类型"。
        ratio = CONTEXT_RATIOS.get(writing_phase, CONTEXT_RATIOS["writing"])

        parts = []
        used = 0

        gs = self.memory.get_global_summary()
        if gs:
            text = self._compress_text(gs, int(max_chars * ratio["global"]), keep_tail=True)
            section = f"【全局摘要】\n{text}"
            parts.append(section)
            used += len(section)

        vol = self.memory.get_current_volume_summary(chapter_num)
        if vol:
            text = self._compress_text(vol, int(max_chars * ratio["volume"]), keep_tail=True)
            section = f"【当前卷】\n{text}"
            parts.append(section)
            used += len(section)

        chars = self.memory.get_characters()
        if chars:
            active_names = self.memory.get_active_characters(chapter_num, window=50)
            # 过滤：只保留最近活跃的角色，排除"无名小卒"中已不活跃的
            important_chars = {}
            for name in active_names:
                if name in chars:
                    info = chars[name]
                    if isinstance(info, dict):
                        category = info.get("category", "")
                        # "无名小卒"只有活跃时才显示，不活跃则跳过
                        if category == "无名小卒" and name not in active_names:
                            continue
                    important_chars[name] = info
            # 合并：活跃角色 + 主角/关键人物
            for name, info in chars.items():
                if name not in important_chars and isinstance(info, dict):
                    if info.get("category") in ("主角", "女主角", "男主角", "关键人物"):
                        important_chars[name] = info

            text = self._compress_active_characters(important_chars, active_names, int(max_chars * ratio["chars"]))
            if text:
                section = f"【当前剧情线角色】（共{len(important_chars)}人，请勿无故引入新角色）\n{text}"
                parts.append(section)
                used += len(section)

        recent_count = 5 if chapter_num > 1000 else 3
        recent = self.memory.get_recent_summaries(recent_count)
        if recent:
            text = self._compress_text(recent, int(max_chars * ratio["recent"]), keep_tail=True)
            section = f"【近期章节】\n{text}"
            parts.append(section)
            used += len(section)

        if extra_context:
            # 直接注入外部上下文（世界观、大纲等关键信息）
            ec_budget = int(max_chars * ratio["extra"])
            # keep_tail=True: 保留结尾（前一章结尾是连贯性关键）
            ec_text = self._compress_text(extra_context, ec_budget, keep_tail=True)
            ec_section = f"【创作指引】\n{ec_text}"
            parts.append(ec_section)
            used += len(ec_section)  # P2-7: 计入段标题，避免预算失真

            # 同时做RAG检索补充
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                # P2-7: 预算下限钳位到 0，防止 max_chars-used 为负
                rag_budget = max(0, min(int(max_chars * ratio["rag"]), max_chars - used))
                text = self._compress_text(rag_text, rag_budget, keep_tail=False)
                if text and len(text) > 20:
                    rag_section = f"【相关记忆】\n{text}"
                    parts.append(rag_section)
                    used += len(rag_section)

        # 写作技能上下文（知识图谱、写作技巧）
        try:
            from .writing_skills import writing_skill_manager

            # P-04b：传入 `chapter_num`，让学习到的经验按"距今章节数"检索。
            # 旧实现不传 ⇒ `get_writing_context` 的 `chapter` 形参恒为默认 0
            # ⇒ 第 87 章写下的成功模式在第 120 章读不到。
            skills_context = writing_skill_manager.get_writing_context(chapter=chapter_num)
            if skills_context and len(skills_context) > 20:
                skill_budget = max(0, min(500, max_chars - used))
                text = self._compress_text(skills_context, skill_budget, keep_tail=False)
                if text:
                    skill_section = f"【写作参考】\n{text}"
                    parts.append(skill_section)
                    used += len(skill_section)
        except Exception as e:
            self.log(f"[写作技能] 获取上下文失败: {e}")

        # 插件写作技能包（v3.2）：插件贡献的提示词片段**单独占一段预算**。
        # 为什么不并进上面的【写作参考】：那段只有 500 字且会被 `_compress_text` 压缩，
        # 插件技能包（可能有多条、每条都较长）塞进去会被压没 —— 等于装上了但不起作用。
        # ⚠️ 这里必须**直接**调用（而不是只依赖 `get_writing_context` 内部已包含），
        # 因为 `tests/test_plugin_system.py::TestWiringGuard` 要求存在显式生产调用点，
        # 否则插件系统会重蹈"定义完整但零引用 ⇒ 被当死代码删除"的覆辙。
        try:
            from .writing_skills import writing_skill_manager

            plugin_ctx = writing_skill_manager.plugin_skill_context()
            if plugin_ctx:
                plugin_budget = max(0, min(800, max_chars - used))
                text = self._compress_text(plugin_ctx, plugin_budget, keep_tail=False)
                if text:
                    section = f"【插件写作技能】\n{text}"
                    parts.append(section)
                    used += len(section)
        except Exception as e:
            self.log(f"[插件技能] 获取上下文失败: {e}")

        # 写作预设（v3.3）：把技能库规则按「阶段 / 体裁 / 长度」装配成的可复用能力单元。
        # ⚠️ 与下面的技能库注入**互斥**：预设本身已包含规则子集，两者同时注入
        # 会把同一批规则说两遍（既浪费预算，又让模型以为这是两组不同要求）。
        # 生成阶段传 `stage="generate"` ⇒ 自动选「生成期防 AI 腔」，而不是成稿清理。
        preset_ctx = ""
        try:
            from .writing_presets import get_preset_manager

            manager = get_preset_manager()
            if manager is not None:
                # 1200 是实测得出的下界：900 只能装下 5 条规则（规范与边界要占 600），
                # 会漏掉翻译腔/语义层四条；1200 可装 9–11 条且不足上下文的 12%。
                preset_budget = max(0, min(1200, max_chars - used))
                # 传作品目录：预设会把该作品的「风格DNA.json」一并注入，
                # 让"冲突以风格文档为准"在生成期就生效，而不是等成稿后才发现跑偏
                preset_ctx = manager.prompt_context(
                    budget=preset_budget,
                    stage="generate",
                    novel_dir=getattr(self.memory, "novel_dir", None),
                )
                if preset_ctx:
                    section = f"【写作预设】\n{preset_ctx}"
                    parts.append(section)
                    used += len(section)
        except Exception as e:
            self.log(f"[写作预设] 获取约束失败: {e}")

        # 技能库（v3.3）：**仅在没有预设时兜底**。规则文本较长，塞进 500 字的
        # 【写作参考】里会被 `_compress_text` 压成一句废话，所以独立占预算。
        if not preset_ctx:
            try:
                from .skill_library import get_skill_library

                library = get_skill_library()
                skill_budget = max(0, min(900, max_chars - used))
                skill_ctx = library.prompt_context(budget=skill_budget) if library is not None else ""
                if skill_ctx:
                    section = f"【技能库规则】\n{skill_ctx}"
                    parts.append(section)
                    used += len(section)
            except Exception as e:
                self.log(f"[技能库] 获取规则失败: {e}")

        # === 伏笔追踪 ===
        unresolved = self._get_unresolved_plots()
        if unresolved and used + len(unresolved) < max_chars:
            parts.insert(1, unresolved)  # 插入到全局摘要后面，确保AI看到
            used += len(unresolved)

        # 🔧 修复: ContextOptimizer.optimize 接口不匹配导致上下文被静默丢弃
        # 原代码: ContextOptimizer.optimize({"内容": ...}) 只接受 "内容" 键
        # 但 optimize 迭代 COMPRESSION_RATIOS 键 (global_summary, volume_summary, ...)
        # 导致全部内容被跳过 → 返回空字符串 → Writer/Reviewer 无上下文
        # 修复: 直接拼接 parts 并用简单截断
        result = "\n\n".join(parts)
        if len(result) > max_chars:
            marker = "\n...(截断)...\n"
            head = int(max_chars * 0.3)
            tail = max_chars - head - len(marker)
            result = result[:head] + marker + result[-tail:]
        return result

    @staticmethod
    def _compress_text(text: str, budget: int, keep_tail: bool = True) -> str:
        if len(text) <= budget:
            return text
        if budget < 50:
            return text[:budget] + "..."
        if keep_tail:
            head = int(budget * 0.3)
            return text[:head] + "...\n\n" + text[-(budget - head - 5) :]
        else:
            head = int(budget * 0.7)
            return text[:head] + "...\n\n" + text[-(budget - head - 5) :]

    @staticmethod
    def _compress_active_characters(chars: dict, active_names: List[str], budget: int) -> str:
        """压缩活跃角色信息 - 按等级优先显示"""
        result = []
        used = 0

        # 角色等级优先级
        PRIORITY_RANKS = {"主角": 0, "女主角": 0, "男主角": 0, "关键人物": 1, "配角": 2, "无名小卒": 3}

        # 按优先级排序
        def char_priority(name):
            if name not in chars:
                return 99
            info = chars.get(name, {})
            if isinstance(info, dict):
                return PRIORITY_RANKS.get(info.get("category", "无名小卒"), 3)
            return 3

        # 优先显示活跃角色（按等级排序）
        sorted_active = sorted(active_names, key=char_priority)
        for name in sorted_active:
            if used >= budget:
                break
            if name in chars:
                info = chars[name]
                if isinstance(info, dict):
                    category = info.get("category", "未知")
                    line = BuildContext._format_character_line(name, info, category, compact=False)
                    # 超预算就退回精简格式，**绝不因此丢掉这个角色**：
                    # 角色从上下文消失比"信息少"危害大得多（模型会当他没出现过）。
                    if used + len(line) > budget:
                        line = BuildContext._format_character_line(name, info, category, compact=True)
                else:
                    line = f"- {name}: {str(info)[:50]}"
                if used + len(line) <= budget:
                    result.append(line)
                    used += len(line)

        # 如果空间够，添加主角/关键人物（即使不活跃）
        if used < budget:
            for name, info in chars.items():
                if used >= budget or name in active_names:
                    continue
                if isinstance(info, dict):
                    category = info.get("category", "")
                    if category in ("主角", "女主角", "男主角", "关键人物"):
                        line = BuildContext._format_character_line(name, info, category, compact=False)
                        if used + len(line) > budget:
                            line = BuildContext._format_character_line(name, info, category, compact=True)
                        if used + len(line) <= budget:
                            result.append(line)
                            used += len(line)

        return "\n".join(result) if result else ""

    @staticmethod
    def _format_character_line(name: str, info: dict, category: str, *, compact: bool) -> str:
        """渲染一行角色摘要。

        `compact=True` 是**超预算时的降级格式**（只保留性格），
        保证"角色不因字多而被整条丢弃"。
        """
        personality = info.get("personality", "")[: 20 if compact else 30]
        faction = info.get("faction", "")
        line = f"- [{category}] {name}: {personality}"
        if faction:
            line += f" (阵营:{faction})"
        if compact:
            return line
        # 只有核心角色才值得占篇幅写背景/目标；无名小卒写了也挤掉别人
        if category in ("主角", "女主角", "男主角", "关键人物"):
            backstory = str(info.get("backstory") or info.get("background") or "").strip()[:60]
            goal = str(info.get("goal") or "").strip()[:20]
            relationship = str(info.get("relationship_to_main") or "").strip()[:25]
            if backstory:
                line += f"｜背景:{backstory}"
            if goal:
                line += f"｜目标:{goal}"
            if relationship:
                line += f"｜与主角:{relationship}"
        return line

    def _get_unresolved_plots(self) -> str:
        """获取未回收的伏笔/剧情线索"""
        try:
            gs = self.memory.get_global_summary()
            if not gs:
                return ""

            # 从全局摘要中提取伏笔关键词
            foreshadow_keywords = [
                "伏笔",
                "悬念",
                "暗示",
                "预示",
                "未解之谜",
                "神秘",
                "秘密",
                "阴谋",
                "真相",
                "预言",
                "轮回",
                "宿命",
                "传承",
                "使命",
            ]

            unresolved = []
            for keyword in foreshadow_keywords:
                if keyword in gs:
                    # 找到包含关键词的句子
                    sentences = gs.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
                    for s in sentences:
                        if keyword in s and len(s) > 10:
                            unresolved.append(s.strip())
                            if len(unresolved) >= 8:
                                break
                if len(unresolved) >= 8:
                    break

            if unresolved:
                return "【未回收伏笔/悬念】\n" + "\n".join(unresolved[:8])
            return ""
        except Exception:
            return ""
