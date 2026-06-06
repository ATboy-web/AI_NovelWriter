"""
长上下文记忆管理模块 - 分层架构，支持5000章小说
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from collections import Counter
from loguru import logger


class MemoryManager:
    """长上下文记忆管理器 - 分层架构，支持5000章小说
    
    分层架构：
    1. 全局摘要 - 整个故事的核心概述 (1个文件)
    2. 卷级摘要 - 每100章为一卷的概述 (50个文件)
    3. 弧线摘要 - 重要剧情弧线的概述 (200个文件)
    4. 章节摘要 - 每章的详细摘要 (5000个文件)
    
    核心机制：
    1. RAG检索 - 倒排索引+关键词匹配，支持百万级检索
    2. 语义去重 - 相似记忆自动合并
    3. 记忆评分 - 根据重要性/新鲜度/引用次数打分
    4. 知识图谱 - 角色关系+事件时间线
    5. 分页加载 - 按需加载，不全部读入内存
    6. 角色活跃度 - 按活跃度加载角色卡片
    """
    
    VOLUME_SIZE = 100  # 每卷100章
    
    def __init__(self, novel_dir: Path):
        self.novel_dir = novel_dir
        self.memory_dir = novel_dir / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        
        # 全局摘要
        self.global_summary_file = self.memory_dir / "global_summary.txt"
        # 章节摘要目录
        self.chapters_dir = self.memory_dir / "chapters"
        self.chapters_dir.mkdir(exist_ok=True)
        # 卷级摘要目录 (新增)
        self.volumes_dir = self.memory_dir / "volumes"
        self.volumes_dir.mkdir(exist_ok=True)
        # 弧线摘要目录 (新增)
        self.arcs_dir = self.memory_dir / "arcs"
        self.arcs_dir.mkdir(exist_ok=True)
        # 角色档案（含关系图）
        self.characters_file = self.memory_dir / "characters.json"
        # 世界观设定
        self.settings_file = self.memory_dir / "settings.json"
        # 事件时间线目录 (改为分页存储)
        self.timeline_dir = self.memory_dir / "timeline"
        self.timeline_dir.mkdir(exist_ok=True)
        # 记忆块分页存储 (改为分页)
        self.chunks_dir = self.memory_dir / "chunks"
        self.chunks_dir.mkdir(exist_ok=True)
        # 倒排索引 (新增，替代全量遍历)
        self.inverted_index_file = self.memory_dir / "inverted_index.json"
        # 关键词索引
        self.index_file = self.memory_dir / "index.json"
        # 记忆评分
        self.scores_file = self.memory_dir / "scores.json"
        # 角色活跃度 (新增)
        self.character_activity_file = self.memory_dir / "character_activity.json"
        
        # 缓存
        self._inverted_index = self._load_inverted_index()
        self._scores = self._load_scores()
        self._character_activity = self._load_character_activity()
        self._current_page = 0  # 当前chunks页
        self._chunks_cache = []  # 当前页的chunks缓存
    
    # ===== 初始化加载方法 =====
    
    def _load_inverted_index(self) -> Dict:
        if self.inverted_index_file.exists():
            try:
                return json.loads(self.inverted_index_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, FileNotFoundError): pass
        return {}
    
    def _save_inverted_index(self):
        self.inverted_index_file.write_text(json.dumps(self._inverted_index, ensure_ascii=False), encoding='utf-8')
    
    def _load_scores(self) -> Dict:
        if self.scores_file.exists():
            try:
                return json.loads(self.scores_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, FileNotFoundError): pass
        return {}
    
    def _save_scores(self):
        self.scores_file.write_text(json.dumps(self._scores, ensure_ascii=False), encoding='utf-8')
    
    def _load_character_activity(self) -> Dict:
        if self.character_activity_file.exists():
            try:
                return json.loads(self.character_activity_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, FileNotFoundError): pass
        return {}
    
    def _save_character_activity(self):
        self.character_activity_file.write_text(json.dumps(self._character_activity, ensure_ascii=False), encoding='utf-8')
    
    # ===== 卷级摘要管理 =====
    
    def _chapter_to_volume(self, chapter_num: int) -> int:
        """章节号转卷号 (每100章一卷)"""
        return (chapter_num - 1) // self.VOLUME_SIZE + 1
    
    def save_volume_summary(self, volume_num: int, summary: str):
        """保存卷级摘要"""
        file = self.volumes_dir / f"volume_{volume_num:03d}.txt"
        file.write_text(summary, encoding='utf-8')
    
    def get_volume_summary(self, volume_num: int) -> str:
        """获取卷级摘要"""
        file = self.volumes_dir / f"volume_{volume_num:03d}.txt"
        if file.exists():
            return file.read_text(encoding='utf-8')
        return ""
    
    def get_current_volume_summary(self, chapter_num: int) -> str:
        """获取当前卷的摘要"""
        vol = self._chapter_to_volume(chapter_num)
        return self.get_volume_summary(vol)
    
    def auto_generate_volume_summary(self, volume_num: int, ai_client=None):
        """自动生成卷级摘要（汇总该卷所有章节摘要）"""
        start_ch = (volume_num - 1) * self.VOLUME_SIZE + 1
        end_ch = volume_num * self.VOLUME_SIZE
        
        summaries = []
        for ch_num in range(start_ch, end_ch + 1):
            ch_sum = self.get_chapter_summary(ch_num)
            if ch_sum:
                summaries.append(f"第{ch_num}章: {ch_sum[:100]}")
        
        if not summaries:
            return ""
        
        # 简单拼接（如果有AI可以进一步压缩）
        summary = f"第{volume_num}卷 (第{start_ch}-{end_ch}章):\n" + "\n".join(summaries)
        self.save_volume_summary(volume_num, summary)
        return summary
    
    # ===== 弧线摘要管理 =====
    
    def save_arc_summary(self, arc_name: str, summary: str, chapters: List[int] = None):
        """保存弧线摘要"""
        safe_name = "".join(c for c in arc_name if c.isalnum() or c in "_ -")[:30]
        file = self.arcs_dir / f"arc_{safe_name}.json"
        data = {
            "name": arc_name,
            "summary": summary,
            "chapters": chapters or [],
            "updated_at": datetime.now().isoformat()
        }
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    def get_arc_summary(self, arc_name: str) -> str:
        """获取弧线摘要"""
        safe_name = "".join(c for c in arc_name if c.isalnum() or c in "_ -")[:30]
        file = self.arcs_dir / f"arc_{safe_name}.json"
        if file.exists():
            data = json.loads(file.read_text(encoding='utf-8'))
            return data.get("summary", "")
        return ""
    
    def get_all_arcs(self) -> List[Dict]:
        """获取所有弧线"""
        arcs = []
        for f in self.arcs_dir.glob("arc_*.json"):
            try:
                arcs.append(json.loads(f.read_text(encoding='utf-8')))
            except (FileNotFoundError, json.JSONDecodeError): pass
        return arcs
    
    # ===== 核心记忆保存 =====
    
    def save_global_summary(self, summary: str):
        with open(self.global_summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
    
    def get_global_summary(self) -> str:
        if self.global_summary_file.exists():
            return self.global_summary_file.read_text(encoding='utf-8')
        return ""
    
    def save_chapter_summary(self, chapter_num: int, summary: str):
        file = self.chapters_dir / f"chapter_{chapter_num:05d}.txt"
        with open(file, 'w', encoding='utf-8') as f:
            f.write(summary)
        # 更新倒排索引
        self._update_inverted_index(f"chapter_{chapter_num:05d}", summary)
        # 更新记忆评分
        self._update_score(f"chapter_{chapter_num:05d}", "summary", importance=8)
        # 检查是否需要自动生成卷级摘要
        if chapter_num % self.VOLUME_SIZE == 0:
            vol = self._chapter_to_volume(chapter_num)
            self.auto_generate_volume_summary(vol)
    
    def get_chapter_summary(self, chapter_num: int) -> str:
        file = self.chapters_dir / f"chapter_{chapter_num:05d}.txt"
        if file.exists():
            return file.read_text(encoding='utf-8')
        return ""
    
    def get_recent_summaries(self, count: int = 5) -> str:
        """获取最近N章的摘要"""
        chapters = sorted(self.chapters_dir.glob("chapter_*.txt"), reverse=True)
        summaries = []
        for ch in chapters[:count]:
            num_str = ch.stem.split("_")[1]
            content = ch.read_text(encoding='utf-8')
            summaries.append(f"第{num_str}章摘要：\n{content}")
            self._increment_reference(f"chapter_{num_str}")
        return "\n\n".join(reversed(summaries))
    
    def get_chapter_range_summary(self, start: int, end: int) -> str:
        """获取章节范围的摘要（分页加载）"""
        summaries = []
        for ch_num in range(start, min(end + 1, start + 50)):  # 最多50章
            ch_sum = self.get_chapter_summary(ch_num)
            if ch_sum:
                summaries.append(f"第{ch_num}章: {ch_sum[:80]}")
        return "\n".join(summaries) if summaries else ""
    
    # ===== 角色活跃度管理 =====
    
    def update_character_activity(self, char_name: str, chapter_num: int):
        """更新角色活跃度"""
        if char_name not in self._character_activity:
            self._character_activity[char_name] = {
                "appearances": [],
                "last_seen": chapter_num,
                "importance": 5
            }
        activity = self._character_activity[char_name]
        if chapter_num not in activity["appearances"]:
            activity["appearances"].append(chapter_num)
            # 只保留最近100次出场
            if len(activity["appearances"]) > 100:
                activity["appearances"] = activity["appearances"][-100:]
        activity["last_seen"] = chapter_num
        self._save_character_activity()
    
    def get_active_characters(self, chapter_num: int, window: int = 50) -> List[str]:
        """获取最近活跃的角色（按活跃度排序）"""
        active = []
        for name, activity in self._character_activity.items():
            last_seen = activity.get("last_seen", 0)
            if chapter_num - last_seen <= window:
                count = len([c for c in activity.get("appearances", []) if c >= chapter_num - window])
                active.append((name, count, last_seen))
        
        # 按出场次数排序
        active.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _, _ in active[:10]]  # 返回前10个活跃角色
    
    # ===== RAG检索 - 倒排索引优化 =====
    
    def _update_inverted_index(self, doc_id: str, content: str):
        """更新倒排索引"""
        keywords = self._extract_keywords(content)
        for kw in keywords:
            if kw not in self._inverted_index:
                self._inverted_index[kw] = []
            if doc_id not in self._inverted_index[kw]:
                self._inverted_index[kw].append(doc_id)
        # 定期保存（每100次更新保存一次）
        if len(self._inverted_index) % 100 == 0:
            self._save_inverted_index()
    
    def retrieve_relevant(self, query: str, top_k: int = 5) -> List[Dict]:
        """RAG检索：使用倒排索引快速查找
        
        使用倒排索引避免遍历所有chunks，支持百万级检索
        """
        query_keywords = set(self._extract_keywords(query))
        if not query_keywords:
            return []
        
        # 使用倒排索引快速找到候选文档
        candidate_ids = set()
        for kw in query_keywords:
            if kw in self._inverted_index:
                candidate_ids.update(self._inverted_index[kw])
        
        # 如果没有索引，降级为遍历章节摘要
        if not candidate_ids:
            return self._fallback_search(query_keywords, top_k)
        
        # 计算候选文档的相关性
        scored = []
        for doc_id in candidate_ids:
            content = self._get_document_content(doc_id)
            if content:
                chunk = {"id": doc_id, "content": content}
                score = self._calculate_relevance(chunk, query_keywords)
                if score > 0:
                    scored.append({**chunk, "relevance": score})
        
        scored.sort(key=lambda x: x["relevance"], reverse=True)
        top = scored[:top_k]
        
        for chunk in top:
            self._increment_reference(chunk.get("id", ""))
        
        return top
    
    def _fallback_search(self, query_keywords: set, top_k: int) -> List[Dict]:
        """降级搜索：遍历最近的章节摘要"""
        scored = []
        chapters = sorted(self.chapters_dir.glob("chapter_*.txt"), reverse=True)
        for ch_file in chapters[:200]:  # 只搜索最近200章
            try:
                content = ch_file.read_text(encoding='utf-8')
                doc_id = ch_file.stem
                chunk = {"id": doc_id, "content": content}
                score = self._calculate_relevance(chunk, query_keywords)
                if score > 0:
                    scored.append({**chunk, "relevance": score})
            except Exception as e:
                logger.debug(f"跳过章节文件 {ch_file.name}: {e}")
        
        scored.sort(key=lambda x: x["relevance"], reverse=True)
        return scored[:top_k]
    
    def _get_document_content(self, doc_id: str) -> str:
        """获取文档内容（支持不同类型的文档）"""
        # 章节摘要
        if doc_id.startswith("chapter_"):
            # 支持 chapter_1 和 chapter_00001 两种格式
            file = self.chapters_dir / f"{doc_id}.txt"
            if not file.exists():
                # 尝试补零格式
                try:
                    num = int(doc_id.split("_", 1)[1])
                    file = self.chapters_dir / f"chapter_{num:05d}.txt"
                except (ValueError, IndexError):
                    pass
            if file.exists():
                return file.read_text(encoding='utf-8')
        # 卷级摘要
        elif doc_id.startswith("volume_"):
            file = self.volumes_dir / f"{doc_id}.txt"
            if file.exists():
                return file.read_text(encoding='utf-8')
        # 弧线摘要
        elif doc_id.startswith("arc_"):
            file = self.arcs_dir / f"{doc_id}.json"
            if file.exists():
                data = json.loads(file.read_text(encoding='utf-8'))
                return data.get("summary", "")
        return ""
    
    def _calculate_relevance(self, chunk: Dict, query_keywords: set) -> float:
        """计算记忆块与查询的相关性分数"""
        content = chunk.get("content", "")
        content_keywords = set(self._extract_keywords(content))
        
        # 关键词匹配得分
        overlap = query_keywords & content_keywords
        keyword_score = len(overlap) / max(len(query_keywords), 1)
        
        # 新鲜度得分（指数衰减，7天半衰期）
        created = chunk.get("created_at", "")
        freshness = self._calc_freshness(created)
        
        # 重要性得分
        importance = chunk.get("importance", 5) / 10.0
        
        # 引用得分
        ref_count = self._scores.get(chunk.get("id", ""), {}).get("references", 0)
        ref_score = min(ref_count / 10.0, 1.0)
        
        # 加权计算
        weights = {"keyword": 0.40, "freshness": 0.20, "importance": 0.30, "ref": 0.10}
        total = (
            keyword_score * weights["keyword"] +
            freshness * weights["freshness"] +
            importance * weights["importance"] +
            ref_score * weights["ref"]
        )
        
        return round(total, 4)
    
    def _calc_freshness(self, created_at: str) -> float:
        """计算新鲜度得分（指数衰减）"""
        if not created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at)
            days_ago = (datetime.now() - created).days
            # 7天半衰期
            return 2 ** (-days_ago / 7)
        except (ValueError, TypeError):
            return 0.5
    
    # ===== 记忆块（Chunks）分页管理 =====
    
    def _get_chunks_page(self, page: int, page_size: int = 100) -> List[Dict]:
        """获取指定页的chunks（分页加载）"""
        page_file = self.chunks_dir / f"page_{page:04d}.json"
        if page_file.exists():
            try:
                return json.loads(page_file.read_text(encoding='utf-8'))
            except (FileNotFoundError, json.JSONDecodeError): pass
        return []
    
    def _save_chunks_page(self, page: int, chunks: List[Dict]):
        """保存指定页的chunks"""
        page_file = self.chunks_dir / f"page_{page:04d}.json"
        page_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding='utf-8')
    
    def _get_total_chunk_count(self) -> int:
        """获取chunks总数"""
        pages = list(self.chunks_dir.glob("page_*.json"))
        if not pages:
            return 0
        last_page = sorted(pages)[-1]
        try:
            chunks = json.loads(last_page.read_text(encoding='utf-8'))
            return (len(pages) - 1) * 100 + len(chunks)
        except (FileNotFoundError, ValueError):
            return 0
    
    def add_chunk(self, chunk_type: str, content: str, importance: int = 5, 
                  tags: List[str] = None, related_to: List[str] = None):
        """添加记忆块（分页存储）"""
        # 去重检查（只检查最近几页）
        existing = self._find_similar_chunk(content)
        if existing:
            self._merge_chunk(existing["id"], content, tags)
            return existing["id"]
        
        chunk = {
            "id": f"{chunk_type}_{int(time.time() * 1000)}",
            "type": chunk_type,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "related_to": related_to or [],
            "created_at": datetime.now().isoformat(),
            "references": 0,
        }
        
        # 找到当前页
        total = self._get_total_chunk_count()
        current_page = total // 100
        page_chunks = self._get_chunks_page(current_page)
        page_chunks.append(chunk)
        self._save_chunks_page(current_page, page_chunks)
        
        # 更新倒排索引
        self._update_inverted_index(chunk["id"], content)
        self._update_score(chunk["id"], chunk_type, importance)
        
        return chunk["id"]
    
    def _find_similar_chunk(self, content: str, threshold: float = 0.7) -> Optional[Dict]:
        """查找相似的记忆块（只检查最近几页）"""
        content_keywords = set(self._extract_keywords(content))
        if not content_keywords:
            return None
        
        # 只检查最近3页（300个chunks）
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max(0, max_page - 2), max_page + 1):
            for chunk in self._get_chunks_page(page):
                chunk_keywords = set(self._extract_keywords(chunk.get("content", "")))
                if not chunk_keywords:
                    continue
                overlap = len(content_keywords & chunk_keywords)
                similarity = overlap / min(len(content_keywords), len(chunk_keywords))
                if similarity > threshold:
                    return chunk
        return None
    
    def _merge_chunk(self, chunk_id: str, new_content: str, new_tags: List[str] = None):
        """合并记忆块"""
        # 查找chunk所在的页
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max_page + 1):
            page_chunks = self._get_chunks_page(page)
            for chunk in page_chunks:
                if chunk["id"] == chunk_id:
                    if new_content not in chunk["content"]:
                        chunk["content"] += f"\n\n[更新]\n{new_content}"
                    if new_tags:
                        chunk["tags"] = list(set(chunk.get("tags", []) + new_tags))
                    chunk["updated_at"] = datetime.now().isoformat()
                    self._save_chunks_page(page, page_chunks)
                    return
        self._save_inverted_index()
    
    def _update_score(self, doc_id: str, doc_type: str, importance: int = 5):
        """更新记忆评分"""
        if doc_id not in self._scores:
            self._scores[doc_id] = {"type": doc_type, "importance": importance, "references": 0, "created": datetime.now().isoformat()}
        else:
            self._scores[doc_id]["importance"] = max(self._scores[doc_id].get("importance", 5), importance)
        self._save_scores()
    
    def _increment_reference(self, doc_id: str):
        """增加引用计数"""
        if doc_id not in self._scores:
            self._scores[doc_id] = {"references": 0}
        self._scores[doc_id]["references"] = self._scores[doc_id].get("references", 0) + 1
    
    # ===== 事件时间线（分页存储）=====
    
    def _get_timeline_page(self, chapter_num: int) -> int:
        """章节号转时间线页码（每100章一页）"""
        return (chapter_num - 1) // 100
    
    def add_event(self, chapter_num: int, event: str, event_type: str = "story", 
                  characters_involved: List[str] = None):
        """添加事件到时间线（分页存储）"""
        page = self._get_timeline_page(chapter_num)
        page_file = self.timeline_dir / f"timeline_{page:03d}.json"
        
        events = []
        if page_file.exists():
            try:
                events = json.loads(page_file.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError): pass
        
        events.append({
            "chapter": chapter_num,
            "event": event,
            "type": event_type,
            "characters": characters_involved or [],
            "timestamp": datetime.now().isoformat(),
        })
        
        page_file.write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding='utf-8')
    
    def get_timeline(self, from_chapter: int = 0, to_chapter: int = None) -> List[Dict]:
        """获取时间线（按范围加载）"""
        if to_chapter is None:
            to_chapter = from_chapter + 200 if from_chapter > 0 else 999999
        
        all_events = []
        start_page = self._get_timeline_page(from_chapter)
        end_page = self._get_timeline_page(to_chapter)
        
        for page in range(start_page, end_page + 1):
            page_file = self.timeline_dir / f"timeline_{page:03d}.json"
            if page_file.exists():
                try:
                    events = json.loads(page_file.read_text(encoding='utf-8'))
                    for e in events:
                        ch = e.get("chapter", 0)
                        if from_chapter <= ch <= to_chapter:
                            all_events.append(e)
                except (FileNotFoundError, json.JSONDecodeError): pass
        
        return sorted(all_events, key=lambda e: (e.get("chapter", 0), e.get("timestamp", "")))
    
    # ===== 角色档案和关系图 =====
    
    def save_characters(self, characters: dict):
        with open(self.characters_file, 'w', encoding='utf-8') as f:
            json.dump(characters, f, indent=2, ensure_ascii=False)
    
    def get_characters(self) -> dict:
        if self.characters_file.exists():
            with open(self.characters_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def update_character(self, name: str, data: dict):
        """更新角色信息，自动检测关系变化"""
        characters = self.get_characters()
        
        old_data = characters.get(name, {})
        
        # 合并更新
        if isinstance(old_data, dict) and isinstance(data, dict):
            old_data.update(data)
            characters[name] = old_data
        else:
            characters[name] = data
        
        self.save_characters(characters)
        
        # 检测关系变化并记录
        if "relationships" in data:
            for rel_name, rel_type in data["relationships"].items():
                self.add_event(
                    chapter_num=0,
                    event=f"角色关系更新: {name} ↔ {rel_name} ({rel_type})",
                    event_type="character",
                    characters_involved=[name, rel_name]
                )
    
    # ===== 记忆评分和衰减 =====
    
    def _update_score(self, item_id: str, item_type: str, importance: int = 5):
        """更新记忆评分"""
        if item_id not in self._scores:
            self._scores[item_id] = {
                "type": item_type,
                "importance": importance,
                "references": 0,
                "created_at": datetime.now().isoformat(),
            }
        self._scores[item_id]["importance"] = max(
            self._scores[item_id].get("importance", 5), importance
        )
        self._save_scores()
    
    def _increment_reference(self, item_id: str):
        """增加引用计数"""
        if item_id not in self._scores:
            self._scores[item_id] = {"type": "unknown", "importance": 5, "references": 0,
                                      "created_at": datetime.now().isoformat()}
        self._scores[item_id]["references"] = self._scores[item_id].get("references", 0) + 1
        self._scores[item_id]["last_referenced"] = datetime.now().isoformat()
        self._save_scores()
    
    def _save_scores(self):
        with open(self.scores_file, 'w', encoding='utf-8') as f:
            json.dump(self._scores, f, indent=2, ensure_ascii=False)
    
    def _load_scores(self) -> dict:
        if self.scores_file.exists():
            with open(self.scores_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    # ===== 记忆健康检查 =====
    
    def health_check(self) -> Dict:
        """检查记忆系统的健康状况
        
        参考Supermemory的质量控制思路：
        1. 检测矛盾信息
        2. 检测衰减严重的记忆
        3. 检测孤立记忆（无关联）
        4. 统计记忆状态
        """
        total_chunks = self._get_total_chunk_count()
        total_chapters = len(list(self.chapters_dir.glob("chapter_*.txt")))
        total_volumes = len(list(self.volumes_dir.glob("volume_*.txt")))
        
        report = {
            "total_chunks": total_chunks,
            "total_chapters": total_chapters,
            "total_volumes": total_volumes,
            "total_characters": len(self.get_characters()),
            "total_arcs": len(list(self.arcs_dir.glob("arc_*.json"))),
            "stale_chunks": [],
            "orphan_chunks": [],
            "recommendations": [],
        }
        
        # 检测衰减（只检查最近几页）
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max(0, max_page - 2), max_page + 1):
            for chunk in self._get_chunks_page(page):
                score = self._scores.get(chunk.get("id", ""), {})
                refs = score.get("references", 0)
                created = score.get("created_at", "")
                freshness = self._calc_freshness(created)
                if freshness < 0.2 and refs < 2:
                    report["stale_chunks"].append({
                        "id": chunk["id"],
                        "type": chunk.get("type", ""),
                        "freshness": round(freshness, 3),
                    })
        
        # 生成建议
        if report["stale_chunks"]:
            report["recommendations"].append(f"有 {len(report['stale_chunks'])} 条记忆已衰减")
        if total_chunks > 5000:
            report["recommendations"].append("记忆块超过5000个，建议归档旧章节记忆")
        if total_chapters > 100 and total_volumes == 0:
            report["recommendations"].append(f"已有{total_chapters}章但无卷级摘要，建议生成卷级摘要")
        
        return report
    
    # ===== 关键词提取和搜索 =====
    
    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """提取关键词（简易分词）"""
        # 中文常见停用词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
                     '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
                     '看', '好', '自己', '这', '他', '她', '它', '们', '那', '被', '把',
                     '可以', '这个', '那个', '什么', '怎么', '因为', '所以', '但是', '然后'}
        
        # 提取2-4字词组
        keywords = []
        cleaned = ''
        for c in text:
            if '\u4e00' <= c <= '\u9fff' or c.isalnum():
                cleaned += c
            else:
                cleaned += ' '
        
        # 提取词组
        for i in range(len(cleaned)):
            for l in [2, 3, 4]:
                if i + l <= len(cleaned):
                    word = cleaned[i:i+l]
                    if word not in stopwords and all('\u4e00' <= c <= '\u9fff' for c in word):
                        keywords.append(word)
        
        # 去重并排序
        counted = Counter(keywords)
        return [word for word, _ in counted.most_common(30)]
    
    def get_settings(self) -> dict:
        if self.settings_file.exists():
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_settings(self, settings: dict):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    
    def update_index(self, chapter_num: int, keywords: List[str]):
        index = self._load_index()
        index[str(chapter_num)] = keywords
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def search_by_keyword(self, keyword: str) -> List[int]:
        index = self._load_index()
        results = []
        for ch_num, keywords in index.items():
            if keyword in keywords:
                results.append(int(ch_num))
        return sorted(results)
    
    def _load_index(self) -> dict:
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    # ===== 智能上下文构建 =====
    
    def build_smart_context(self, chapter_num: int, query: str = "",
                            max_items: int = 10) -> str:
        """智能构建上下文 - 核心RAG方法
        
        优先级排序：
        1. 当前查询相关的记忆块（RAG检索）
        2. 最近章节的事件时间线
        3. 高频引用的角色信息
        4. 世界观设定
        """
        parts = []
        
        # 1. RAG检索相关记忆
        if query:
            relevant = self.retrieve_relevant(query, top_k=5)
            if relevant:
                items = []
                for r in relevant:
                    items.append(f"[{r.get('type', '')}|相关性{r.get('relevance', 0):.2f}] {r.get('content', '')[:200]}")
                parts.append(f"【相关记忆】\n" + "\n\n".join(items))
        
        # 2. 最近时间线事件（使用分页加载）
        recent_events = self.get_timeline(from_chapter=max(1, chapter_num - 5), to_chapter=chapter_num)
        if recent_events:
            event_lines = []
            for e in recent_events[-10:]:
                event_lines.append(f"第{e.get('chapter', 0)}章: {e.get('event', '')}")
            parts.append(f"【故事时间线（最近）】\n" + "\n".join(event_lines))
        
        # 3. 活跃角色（按活跃度排序）
        characters = self.get_characters()
        if characters:
            active_names = self.get_active_characters(chapter_num, window=50)
            char_lines = []
            for name in active_names[:5]:
                if name in characters:
                    info = characters[name]
                    if isinstance(info, dict):
                        char_lines.append(f"- {name}: {info.get('personality', '')[:50]}")
                    else:
                        char_lines.append(f"- {name}: {str(info)[:50]}")
            if not char_lines:
                # 降级到引用次数排序
                for name, info in list(characters.items())[:5]:
                    if isinstance(info, dict):
                        char_lines.append(f"- {name}: {info.get('personality', '')[:50]}")
                    else:
                        char_lines.append(f"- {name}: {str(info)[:50]}")
            if char_lines:
                parts.append(f"【活跃角色】\n" + "\n".join(char_lines))
        
        # 4. 世界观
        settings = self.get_settings()
        if settings:
            settings_text = json.dumps(settings, ensure_ascii=False, indent=2)[:500]
            parts.append(f"【世界观】\n{settings_text}")
        
        return "\n\n---\n\n".join(parts)
