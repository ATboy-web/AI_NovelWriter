"""
小说创作智能体模块 - 参考AutoGen多智能体协作架构
"""

import json
import threading
import time
from typing import Dict, List, Any
from datetime import datetime

from .ai_client import AIClient
from .memory_manager import MemoryManager
from .config import AppConfig


class NovelAgent:
    """小说创作智能体 - 参考AutoGen多智能体协作架构
    
    智能体角色：
    - Writer (作家): 负责创作小说内容
    - Reviewer (审校): 负责检查质量和一致性
    - Editor (编辑/质量门): 负责最终裁定是否通过
    
    协作流程（参考AutoGen的GroupChat模式）：
    1. Writer生成内容 → 2. Reviewer审校 → 3. Editor判定
       → 不过关 → Writer修订 → Reviewer再审校 → ...
       → 过关 → 保存定稿
    
    关键机制：
    - 迭代修订循环：质量不达标自动触发修订
    - 质量门控：设定最低通过分数线
    - 反思记忆：记录每次修订的原因，供后续参考
    """
    
    # 质量阈值
    QUALITY_THRESHOLD = 75  # 评分低于此值自动触发修订
    MAX_REVISION_ROUNDS = 3  # 最多修订轮次
    
    def __init__(self, ai_client: AIClient, memory: MemoryManager, log_callback=None, config: AppConfig = None):
        self.ai = ai_client
        self.memory = memory
        self.log = log_callback or print
        self.config = config

        # 智能体会话历史（参考AutoGen的对话记录）
        self._conversation_log: List[Dict] = []

        # 修订记忆（记录每次修订的原因）
        self._revision_memory: List[Dict] = []

        # 线程锁保护共享列表
        self._log_lock = threading.Lock()
    
    def _record_conversation(self, agent: str, action: str, content: str):
        """记录智能体对话（参考AutoGen的消息历史）"""
        with self._log_lock:
            self._conversation_log.append({
                "agent": agent,
                "action": action,
                "content": content[:200],  # 只记录摘要
                "timestamp": datetime.now().isoformat(),
            })
    
    def _build_context(self, chapter_num: int, extra_context: str = "", max_chars: int = None) -> str:
        """构建上下文 - 分层架构，支持5000章小说
        
        上下文结构：
        1. 全局摘要 (10%)
        2. 当前卷摘要 (15%)
        3. 当前弧线摘要 (10%)
        4. 活跃角色 (15%)
        5. 最近章节 (40%)
        6. RAG检索结果 (10%)
        """
        if max_chars is None:
            max_chars = self.config.get("context_window", 32000) // 4 if self.config else 8000
        
        parts = []
        used = 0
        
        # 1. 全局摘要
        gs = self.memory.get_global_summary()
        if gs:
            budget = int(max_chars * 0.10)
            text = self._compress_text(gs, budget, keep_tail=True)
            parts.append(f"【全局摘要】\n{text}")
            used += len(text)
        
        # 2. 当前卷摘要
        vol_summary = self.memory.get_current_volume_summary(chapter_num)
        if vol_summary and used < max_chars:
            budget = int(max_chars * 0.15)
            text = self._compress_text(vol_summary, budget, keep_tail=True)
            parts.append(f"【当前卷】\n{text}")
            used += len(text)
        
        # 3. 活跃角色（按活跃度加载）
        chars = self.memory.get_characters()
        if chars and used < max_chars:
            active_names = self.memory.get_active_characters(chapter_num, window=50)
            budget = int(max_chars * 0.15)
            text = self._compress_active_characters(chars, active_names, budget)
            if text:
                parts.append(f"【活跃角色】\n{text}")
                used += len(text)
        
        # 4. 最近章节摘要（根据小说长度动态调整）
        if used < max_chars:
            # 5000章小说看最近5章，500章看最近3章
            recent_count = 5 if chapter_num > 1000 else 3
            budget = int(max_chars * 0.40)
            recent = self.memory.get_recent_summaries(recent_count)
            if recent:
                text = self._compress_text(recent, budget, keep_tail=True)
                parts.append(f"【近期章节】\n{text}")
                used += len(text)
        
        # 5. RAG检索结果（如果有额外上下文）
        if extra_context and used < max_chars:
            budget = int(max_chars * 0.10)
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                text = self._compress_text(rag_text, budget, keep_tail=False)
                parts.append(f"【相关记忆】\n{text}")
                used += len(text)
        
        # 6. 补充上下文
        if extra_context and used < max_chars:
            parts.append(f"【补充】\n{extra_context[:300]}")
        
        result = "\n\n".join(parts)
        if len(result) > max_chars:
            return result[:max_chars] + "\n...(已压缩)"
        return result
    
    def _compress_active_characters(self, chars: dict, active_names: List[str], budget: int) -> str:
        """压缩活跃角色信息"""
        result = []
        used = 0
        
        # 优先显示活跃角色
        for name in active_names:
            if used >= budget:
                break
            if name in chars:
                info = chars[name]
                if isinstance(info, dict):
                    personality = info.get("personality", "")[:30]
                    line = f"- {name}: {personality}"
                else:
                    line = f"- {name}: {str(info)[:50]}"
                if used + len(line) <= budget:
                    result.append(line)
                    used += len(line)
        
        # 如果还有空间，添加其他重要角色
        if used < budget:
            for name, info in list(chars.items())[:5]:
                if name not in active_names and used < budget:
                    if isinstance(info, dict):
                        personality = info.get("personality", "")[:20]
                        line = f"- {name}: {personality}"
                    else:
                        line = f"- {name}: {str(info)[:30]}"
                    if used + len(line) <= budget:
                        result.append(line)
                        used += len(line)
        
        return "\n".join(result)
    
    # ===== 压缩方法 =====
    
    def _compress_settings(self, settings: dict, budget: int) -> str:
        priority_keys = ["world", "rules", "factions", "technology", "history", "geography", "culture"]
        result = []
        used = 0
        for key in priority_keys:
            if key in settings and used < budget:
                val = str(settings[key])[:budget - used - len(key) - 3]
                result.append(f"{key}: {val}")
                used += len(val) + len(key) + 2
        return "\n".join(result)
    
    def _compress_characters(self, chars: dict, budget: int) -> str:
        core = ["name", "personality", "motivation"]
        result = []
        used = 0
        for name, info in list(chars.items())[:8]:
            if used >= budget: break
            if isinstance(info, dict):
                extra = "; ".join(f"{f}:{str(info.get(f,''))[:50]}" for f in core if f in info)
                line = f"- {name}: {extra}"[:budget - used]
            else:
                line = f"- {name}: {str(info)[:100]}"[:budget - used]
            result.append(line)
            used += len(line) + 1
        return "\n".join(result)
    
    def _compress_text(self, text: str, budget: int, keep_tail: bool = True) -> str:
        if len(text) <= budget: return text
        if budget < 50: return text[:budget] + "..."
        if keep_tail:
            head = int(budget * 0.3)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
        else:
            head = int(budget * 0.7)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
    
    def _compress_recent_chapters(self, recent_text: str, budget: int, chapter_num: int) -> str:
        chapters = recent_text.split("\n\n")
        if len(chapters) <= 1: return self._compress_text(recent_text, budget, True)
        result = []
        used = 0
        latest = chapters[-1] if chapters else ""
        lb = min(int(budget * 0.4), len(latest))
        if latest: result.append(latest[:lb]); used += lb
        for ch in reversed(chapters[:-1]):
            if used >= budget: break
            cb = min(int((budget - used) * 0.3), len(ch))
            if cb > 50: result.insert(0, self._compress_text(ch, cb, True)); used += cb
        return "\n\n".join(result)
    
    # ===== 多智能体协作核心 =====
    
    def generate_with_collaboration(self, chapter_num: int, chapter_title: str,
                                     chapter_outline: str, word_count: int = 3000) -> str:
        """多智能体协作生成章节 - 核心编排方法
        
        参考AutoGen的GroupChat：Writer→Reviewer→Editor 循环
        """
        self._conversation_log = []
        self.log(f"[编排器] 启动多智能体协作：第{chapter_num}章「{chapter_title}」")
        
        # 第1轮：Writer生成初稿
        self.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self._record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        content = self._writer_generate(chapter_num, chapter_title, chapter_outline, word_count)
        
        # 迭代修订循环（参考AutoGen的反馈环）
        for round_num in range(1, self.MAX_REVISION_ROUNDS + 1):
            # Reviewer审校
            self.log(f"[Reviewer] 正在审校第{chapter_num}章（第{round_num}轮）...")
            self._record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            review = self._reviewer_evaluate(chapter_num, content)
            
            # Editor裁定（质量门）
            self.log(f"[Editor] 质量裁定：{review.get('overall_score', 0)}分")
            self._record_conversation("Editor", "judge", 
                f"评分{review.get('overall_score', 0)}，阈值{self.QUALITY_THRESHOLD}")
            
            if review.get("overall_score", 0) >= self.QUALITY_THRESHOLD:
                self.log(f"[Editor] ✅ 通过！质量达标。")
                self._record_conversation("Editor", "approve", "质量达标，通过")
                break
            
            # 不达标，修订
            suggestions = review.get("suggestions", [])
            issues = review.get("issues", [])
            self.log(f"[Editor] ⚠️ 质量不达标（{review.get('overall_score', 0)}/{self.QUALITY_THRESHOLD}），"
                    f"触发第{round_num}轮修订...")
            
            # 记录修订记忆
            with self._log_lock:
                self._revision_memory.append({
                    "chapter": chapter_num,
                    "round": round_num,
                    "issues": issues,
                    "suggestions": suggestions,
                })
            
            # Writer修订
            self.log(f"[Writer] 正在根据审校意见修订...")
            self._record_conversation("Writer", "revise", f"第{round_num}轮修订")
            content = self._writer_revise(chapter_num, content, review, chapter_outline)
        
        self.log(f"[编排器] 第{chapter_num}章协作完成")
        return content
    
    def _writer_generate(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int) -> str:
        """Writer智能体：生成章节内容"""
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent）。
请根据以下上下文信息创作小说章节。

{context}

创作要求：
1. 保持与前文的连贯性
2. 角色行为符合其性格设定
3. 情节推进自然流畅
4. 语言生动，有画面感
5. 目标字数约{word_count}字
6. 直接输出正文内容，不要添加额外说明
7. 注意设置伏笔和悬念"""
        
        prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："
        
        if word_count > 3000:
            return self._generate_long_chapter(chapter_num, chapter_title, chapter_outline, word_count, context)
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response)}")
        return response
    
    def _reviewer_evaluate(self, chapter_num: int, content: str, 
                           previous_feedback: str = "") -> dict:
        """Reviewer智能体：审校章节
        
        参考AutoGen的code_reviewer角色，检查质量和一致性
        """
        context = self._build_context(chapter_num)
        
        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n上次审校反馈（请重点关注）：\n{previous_feedback}"
        
        system = f"""你是一位专业的小说审校编辑（Reviewer Agent）。
请严格检查以下章节内容的各方面质量。

{context}
{feedback_section}

请以JSON格式输出审校结果：
{{
    "character_consistency": 0-100,  // 角色行为一致性
    "plot_logic": 0-100,             // 情节逻辑
    "writing_quality": 0-100,        // 文笔质量
    "emotional_impact": 0-100,       // 情感感染力
    "pacing": 0-100,                 // 节奏把控
    "overall_score": 0-100,          // 综合评分
    "strengths": ["优点1", ...],     // 写得好的地方
    "issues": ["问题1", ...],        // 发现的问题
    "suggestions": ["建议1", ...],   // 修改建议
    "is_acceptable": true/false      // 是否可接受
}}"""
        
        prompt = f"请审校第{chapter_num}章内容：\n\n{content[:4000]}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=2000)
        
        try:
            return self._parse_json_response(response, {"overall_score": 70, "issues": [], "suggestions": []})
        except Exception:
            return {"overall_score": 70, "issues": [], "suggestions": [], "raw": response}
    
    def _writer_revise(self, chapter_num: int, original: str, review: dict, 
                       chapter_outline: str) -> str:
        """Writer智能体：根据审校意见修订章节
        
        参考AutoGen的迭代优化循环
        """
        suggestions = review.get("suggestions", [])
        issues = review.get("issues", [])
        strengths = review.get("strengths", [])
        
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent），正在修订自己的作品。

{context}

修订原则：
1. 根据审校意见进行针对性修改
2. 保留已有的优点和长处
3. 修改时注意不要破坏整体的连贯性
4. 回应每一个具体问题"""
        
        prompt = f"""请修订第{chapter_num}章内容。

审校反馈：
优点（请保持）：{json.dumps(strengths, ensure_ascii=False)}
问题（需修改）：{json.dumps(issues, ensure_ascii=False)}
建议（参考）：{json.dumps(suggestions, ensure_ascii=False)}

原文：
{original[-4000:] if len(original) > 4000 else original}

修订要求：请输出完整的修订后文本，直接输出正文："""
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 修订完成，字数：{len(response)}")
        return response
    
    # ===== 传统方法（兼容旧接口）=====
    
    def generate_chapter(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int = 3000) -> str:
        """生成章节 - 使用多智能体协作"""
        return self.generate_with_collaboration(chapter_num, chapter_title, 
                                                chapter_outline, word_count)
    
    def review_chapter(self, chapter_num: int, content: str) -> dict:
        """审校章节"""
        return self._reviewer_evaluate(chapter_num, content)
    
    def generate_settings(self, genre: str, title: str, concept: str) -> dict:
        """生成世界观"""
        self.log(f"[智能体] 正在生成世界观...")
        system = """你是一位专业的小说世界观设定师。请生成详细的世界观设定。
以JSON格式输出：world/rules/factions/history/technology/geography/culture"""
        prompt = f"小说类型：{genre}\n标题：{title}\n概念：{concept}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)
        settings = self._parse_json_response(response, {"raw": response})
        self.memory.save_settings(settings)
        return settings
    
    def generate_characters(self, genre: str, title: str, count: int = 5) -> dict:
        """生成角色"""
        self.log(f"[智能体] 正在生成{count}个角色...")
        settings = self.memory.get_settings()
        system = f"你是专业角色设计师。世界观：{json.dumps(settings, ensure_ascii=False)[:500]}\n输出JSON：{{'角色名': {{...}}}}"
        prompt = f"小说类型：{genre}\n标题：{title}\n创建{count}个角色"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)
        chars = self._parse_json_response(response, {"raw": response})
        self.memory.save_characters(chars)
        
        # 同时保存到 CharacterSystem 格式（每个角色一个文件）
        characters_dir = self.memory.novel_dir / "characters" if hasattr(self.memory, 'novel_dir') else None
        if characters_dir is None:
            # 尝试从 memory_dir 推断 novel_dir
            characters_dir = self.memory.memory_dir.parent / "characters"
        characters_dir.mkdir(exist_ok=True)
        
        for name, data in chars.items():
            if isinstance(data, dict):
                char_data = {"name": name, **data}
                with open(characters_dir / f"{name}.json", 'w', encoding='utf-8') as f:
                    json.dump(char_data, f, indent=2, ensure_ascii=False)
        
        return chars
    
    def generate_outline(self, genre: str, title: str, chapter_count: int) -> list:
        """生成大纲"""
        self.log(f"[智能体] 正在生成{chapter_count}章大纲...")
        context = self._build_context(0)
        system = f"你是专业小说大纲规划师。\n{context}\n输出JSON数组：[{{'chapter':1,'title':'','summary':'','key_events':[],'characters_involved':[]}}]"
        prompt = f"小说类型：{genre}\n标题：{title}\n章节数：{chapter_count}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        outline = self._parse_json_response(response, [], is_list=True)
        if not outline:
            outline = [{"chapter": i+1, "title": f"第{i+1}章", "summary": "待规划"} for i in range(chapter_count)]
        return outline
    
    def finalize_chapter(self, chapter_num: int, content: str):
        """定稿章节 + 更新记忆"""
        # 章节摘要
        summary = self.ai.chat(
            [{"role": "user", "content": f"请生成摘要（100-200字）：\n{content[:2000]}"}],
            system="你是故事摘要助手。", max_tokens=300
        )
        self.memory.save_chapter_summary(chapter_num, summary)
        
        # 全局摘要
        old = self.memory.get_global_summary()
        new = self.ai.chat(
            [{"role": "user", "content": f"更新全局摘要：\n旧：{old}\n新章节：{summary}"}],
            system="你是故事摘要助手。", max_tokens=500
        )
        self.memory.save_global_summary(new)
        
        # 关键词索引
        kw = self.ai.chat([{"role": "user", "content": f"提取10个关键词，逗号分隔：\n{content[:1000]}"}],
                         system="提取关键词。", max_tokens=200)
        self.memory.update_index(chapter_num, [k.strip() for k in kw.split(",") if k.strip()])
        
        # 添加记忆块
        self.memory.add_chunk("plot", summary, importance=8, 
                             tags=kw.split(",")[:5] if kw else [])
        self.memory.add_event(chapter_num, summary, "story")
        
        self.log(f"[智能体] 第{chapter_num}章定稿完成")
    
    # ===== 工具方法 =====
    
    @staticmethod
    def _parse_json_response(response: str, default: Any, is_list: bool = False) -> Any:
        """解析AI返回的JSON"""
        try:
            marker = "[" if is_list else "{"
            end_marker = "]" if is_list else "}"
            start = response.find(marker)
            end = response.rfind(end_marker) + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return default
    
    def _generate_long_chapter(self, chapter_num, chapter_title, chapter_outline, word_count, context) -> str:
        """分段生成长章节"""
        parts = []
        part_count = max((word_count + 2999) // 3000, 1)
        for i in range(part_count):
            self.log(f"[Writer] 第{chapter_num}章 第{i+1}/{part_count}段...")
            part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n已有：{''.join(parts[-2:]) or '（开头）'}\n请创作约3000字："
            response = self.ai.chat([{"role": "user", "content": part_prompt}],
                                   system=f"专业小说作家。\n{context[:1000]}", max_tokens=4096)
            parts.append(response)
        return "\n\n".join(parts)
