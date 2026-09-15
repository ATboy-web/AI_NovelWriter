"""业务生成层：设定/角色/大纲/章节生成、审校、风格、EXP、批量创作、扩写

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from loguru import logger

from app import UIStyle
from app.diagnostic_logger import get_logger
from app.parsing import parse_exp_json, parse_json_response

_diag = get_logger()


class GenerationMixin:
    """业务生成层：设定/角色/大纲/章节生成、审校、风格、EXP、批量创作、扩写"""


    def _gen_settings(self):
        """生成世界观"""
        if not self._check_ready():
            return
        if hasattr(self, '_gen_running') and self._gen_running:
            self._log("生成任务正在进行中，请勿重复点击")
            return
        
        self._gen_running = True
        
        def run():
            try:
                meta = self._get_meta()
                self.agent.generate_settings(meta["genre"], meta["title"], meta.get("concept", ""))
                self._log("世界观设定已保存到 memory/settings.json")
            except Exception as e:
                self._log(f"生成失败: {e}")
            finally:
                self._gen_running = False
        
        threading.Thread(target=run, daemon=True).start()
    def _gen_characters(self):
        """生成角色"""
        if not self._check_ready():
            return
        if hasattr(self, '_gen_running') and self._gen_running:
            self._log("生成任务正在进行中，请勿重复点击")
            return
        
        self._gen_running = True
        
        def run():
            try:
                meta = self._get_meta()
                self.agent.generate_characters(meta["genre"], meta["title"])
                self._log("角色档案已保存")
                
                # 同步到 charsystem 和 characters/ 目录
                self._sync_memory_chars_to_dir()
            except Exception as e:
                self._log(f"生成失败: {e}")
            finally:
                self._gen_running = False
        
        threading.Thread(target=run, daemon=True).start()
    def _gen_outline(self):
        """生成大纲 - 根据当前选择的类型"""
        if not self._check_ready():
            return
        if hasattr(self, '_gen_running') and self._gen_running:
            self._log("生成任务正在进行中，请勿重复点击")
            return
        
        outline_type = self.outline_type_var.get()
        self._gen_running = True
        
        def run():
            try:
                meta = self._get_meta()
                
                if outline_type == "章节大纲":
                    # 生成章节大纲 — 使用 total_chapters（用户设定的总章数）
                    real_total = meta.get("total_chapters", meta.get("chapter_count"))
                    # 大题纲分批生成，超过50章先打前站
                    outline_count = min(real_total, 50) if real_total > 10 else real_total
                    new_outline = self.agent.generate_outline(
                        meta["genre"], meta["title"], outline_count,
                        concept=meta.get("concept", ""),
                        total_chapters=real_total  # 真实总章数，防止阶段计算偏差
                    )
                    with self._state_lock:
                        self.outline = new_outline
                    with open(self.current_novel_dir / "outline.json", 'w', encoding='utf-8') as f:
                        json.dump(new_outline, f, indent=2, ensure_ascii=False)
                    self._log("章节大纲已保存到 outline.json")
                    
                elif outline_type == "整体大纲":
                    # 生成整体大纲
                    self._log("正在生成整体大纲...")
                    concept = meta.get("concept", "")
                    overall = self._generate_overall_outline(meta, concept, self.outline)
                    self._save_overall_outline(overall)
                    self._log("整体大纲已保存到 outlines/overall.json")
                    
                elif outline_type == "故事大纲":
                    # 生成故事大纲
                    self._log("正在生成故事大纲...")
                    concept = meta.get("concept", "")
                    stories = self._generate_story_outlines(meta, concept, self.outline)
                    self._save_story_outlines(stories)
                    self._log("故事大纲已保存到 outlines/stories.json")
                
                # GUI操作在主线程
                self.root.after(0, self._refresh_outline_list)
            except Exception as e:
                self._log(f"生成失败: {e}")
            finally:
                self._gen_running = False
        
        threading.Thread(target=run, daemon=True).start()
    def _generate_overall_outline(self, meta: dict, concept: str = "", chapter_outline: list = None) -> list:
        """生成整体大纲 — 带概念上下文和重试"""
        real_total = meta.get("total_chapters", meta.get("chapter_count", 100))
        protagonist = meta.get("protagonist", "")
        
        context_lines = [f"小说类型：{meta['genre']}", f"标题：{meta['title']}", f"全书总章数：{real_total}章", f"当前批次大纲：{meta.get('chapter_count', len(chapter_outline) if chapter_outline else '?')}章"]
        if protagonist:
            context_lines.insert(0, f"主角名：{protagonist}")
        if concept:
            context_lines.insert(0, f"核心概念（用户想法）：{concept}")
        if chapter_outline:
            titles = [c.get('title', f"第{i+1}章") for i, c in enumerate(chapter_outline[:10])]
            context_lines.append(f"已有章节标题：{' → '.join(titles)}")
        prompt = "\n".join(context_lines)
        
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n【重要】本小说主角名为「{protagonist}」，所有描述必须围绕「{protagonist}」展开！"
        
        system = f"""你是专业小说大纲规划师。请根据小说的核心概念和章节标题，生成整体大纲，包含：
1. 故事主线（一句话概括）
2. 主要冲突（2-3个）
3. 高潮节点（2-3个关键转折点）
4. 结局走向
{protagonist_hint}

严格输出合法JSON数组，不要添加任何额外文字。注意：所有字符串值必须用双引号；每个对象的最后一个键值对后不能有逗号。
输出格式：[{{"title": "故事主线", "description": "详细描述", "chapter_range": "第1-5000章"}}, ...]"""
        
        last_error = None
        for attempt in range(3):
            try:
                response = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
                if not response or len(response.strip()) < 20:
                    # 打印调试信息帮助诊断
                    resp_len = len(response) if response else 0
                    self._log(f"[整体大纲] AI响应异常 (长度={resp_len})，等待重试({attempt+1}/3)...")
                    if resp_len > 0:
                        self._log(f"[整体大纲] 响应预览: {response.strip()[:200]}")
                    time.sleep(5)
                    continue
                result = self._parse_json_response(response, [])
                # 标准化：确保返回列表
                if isinstance(result, dict) and "title" in result:
                    result = [result]
                if result and isinstance(result, list) and len(result) > 0:
                    self._log(f"整体大纲生成成功 ({len(result)}项)")
                    return result
                else:
                    self._log(f"[整体大纲] 解析结果为空，等待重试({attempt+1}/3)...")
                    time.sleep(5)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    self._log(f"整体大纲生成重试 {attempt+2}/3...")
                    time.sleep(5)
        
        # 降级：从章节大纲提取有意义的信息
        self._log(f"整体大纲AI生成失败，使用降级方案: {last_error}")
        # 从章节大纲提取关键事件
        key_events = []
        if chapter_outline:
            for item in chapter_outline[:5]:
                title = item.get('title', '')
                if title:
                    key_events.append(title)
        events_text = '、'.join(key_events) if key_events else '主角面临核心困境与挑战'
        
        fallback = [
            {"title": "故事主线", "description": f"小说《{meta['title']}》：{meta.get('concept', '')[:200]}。主角{protagonist}在阴阳交界处重生，逐步揭开岛屿秘密。", "chapter_range": f"第1-{real_total}章"},
            {"title": "主要冲突", "description": f"{protagonist}被阳人和阴人双重排斥，需在夹缝中求生并证明自己。关键事件：{events_text}", "chapter_range": f"第1-{real_total*2//3}章"},
            {"title": "高潮节点", "description": f"{protagonist}掌握阴阳之力后，面对岛屿最大秘密的揭示，引发阴阳两域的终极对决", "chapter_range": f"第{real_total*4//5-10}-{real_total*4//5+10}章"},
            {"title": "结局走向", "description": f"{protagonist}打破阴阳隔阂，重塑岛屿秩序，或选择离开这个不属于他的世界", "chapter_range": f"最后20章"}
        ]
        return fallback
    def _generate_story_outlines(self, meta: dict, concept: str = "", chapter_outline: list = None) -> dict:
        """生成故事大纲 — 带概念上下文和重试"""
        real_total = meta.get("total_chapters", meta.get("chapter_count", 100))
        protagonist = meta.get("protagonist", "")
        
        context_lines = [f"小说类型：{meta['genre']}", f"标题：{meta['title']}", f"全书总章数：{real_total}章", f"当前批次大纲：{meta.get('chapter_count', len(chapter_outline) if chapter_outline else '?')}章"]
        if protagonist:
            context_lines.insert(0, f"主角名：{protagonist}")
        if concept:
            context_lines.insert(0, f"核心概念（用户想法）：{concept}")
        if chapter_outline:
            titles = [c.get('title', f"第{i+1}章") for i, c in enumerate(chapter_outline[:10])]
            context_lines.append(f"已有章节标题：{' → '.join(titles)}")
        prompt = "\n".join(context_lines)
        
        protagonist_hint = ""
        if protagonist:
            protagonist_hint = f"\n【重要】本小说主角名为「{protagonist}」，所有故事线必须围绕「{protagonist}」展开！"
        
        system = f"""你是专业小说大纲规划师。请根据小说的核心概念和章节标题，生成简洁有力的故事大纲。

要求：
1. 主线故事：核心情节推进线（3-8个关键事件）
2. 副线故事：次要线索或隐藏真相线（2-4个关键事件）
{protagonist_hint}

📌 输出格式（仅JSON，无其他文字）：
{{"主线": {{"title": "短标题", "summary": "1-2句话概要", "key_events": ["事件1","事件2","事件3"]}}, "副线": {{"title": "短标题", "summary": "1-2句话概要", "key_events": ["事件1","事件2"]}}}}

⚠️ JSON语法：所有字符串用双引号，冒号后无多余空格，最后一项后不加逗号。"""
        
        last_error = None
        for attempt in range(3):
            try:
                response = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
                if not response or len(response.strip()) < 20:
                    last_error = f"empty_response_attempt_{attempt+1}"
                    self._log(f"[故事大纲] AI响应为空，等待重试({attempt+1}/3)...")
                    time.sleep(5)
                    continue
                result = self._parse_json_response(response, {})
                if result and isinstance(result, dict) and len(result) > 0:
                    self._log(f"故事大纲生成成功 ({len(result)}条故事线)")
                    return result
                else:
                    last_error = f"parse_failed_attempt_{attempt+1}"
                    self._log(f"[故事大纲] 解析结果为空，等待重试({attempt+1}/3)...")
                    time.sleep(5)
            except Exception as e:
                last_error = str(e)[:200]
                if attempt < 2:
                    self._log(f"故事大纲生成重试 {attempt+2}/3...")
                    time.sleep(5)
        
        # 降级：从章节大纲和概念提取有意义的故事线
        self._log(f"故事大纲AI生成失败，使用智能降级方案: {last_error}")
        # 从章节大纲提取关键事件
        key_events = []
        if chapter_outline:
            for item in chapter_outline[:12]:
                title = item.get('title', '')
                if title and len(title) > 1:
                    key_events.append(title)
        if not key_events:
            key_events = ["开端", "发展", "转折", "高潮", "结局"]
        
        # 从概念中提取世界观描述
        world_desc = ""
        if concept:
            world_desc = concept[:80] + ("..." if len(concept) > 80 else "")
        else:
            world_desc = f"{meta.get('genre','玄幻')}世界"
        
        protagonist_name = protagonist or "主角"
        fallback = {
            "主线": {
                "title": f"《{meta['title']}》— {protagonist_name}的征程",
                "summary": f"在{world_desc}中，{protagonist_name}踏上冒险之路，经历重重考验，最终成长为独当一面的存在。",
                "key_events": key_events[:8]
            },
            "副线": {
                "title": "隐藏的真相",
                "summary": f"在{protagonist_name}的旅途背后，一个更深的秘密正在浮现。古老的力量、失落的传承、敌友难辨的关系交织在一起。",
                "key_events": key_events[4:8] if len(key_events) >= 8 else ["揭示第一个秘密", "发现核心线索", "真相大白"]
            }
        }
        return fallback
    def _parse_json_response(self, response: str, default):
        """解析JSON响应 — 多层修复（与novel_agent一致的健壮版本）

        P2-6: 纯逻辑已抽取至 app.parsing.parse_json_response（可独立单测）。
        """
        return parse_json_response(response, default)
    def _gen_chapter(self):
        """生成下一章"""
        if not self._check_ready():
            return
        with self._state_lock:
            if not self.outline:
                messagebox.showwarning("提示", "请先生成大纲")
                return
            
            self.current_chapter += 1
            if self.current_chapter > len(self.outline):
                messagebox.showinfo("提示", "所有章节已生成完毕")
                self.current_chapter = len(self.outline)
                return
            
            chapter_info = self.outline[self.current_chapter - 1]

        def run():
            try:
                ch_num = self.current_chapter  # 捕获当前值，避免竞态
                meta = self._get_meta()
                
                # 构建上下文（前几章完整内容 + 整体大纲 + 故事大纲）
                prev_context = ""
                chapters_dir = self.current_novel_dir / "chapters"
                if chapters_dir.exists():
                    # 🔧 修复：获取所有章节文件，取最近3章（而非只匹配1个文件）
                    all_chapters = sorted(chapters_dir.glob("chapter_*.txt"))
                    recent_chapters = [f for f in all_chapters if f.stem < f"chapter_{ch_num:04d}"]
                    recent_chapters = recent_chapters[-3:]
                    if recent_chapters:
                        recent = []
                        for pf in recent_chapters:
                            text = pf.read_text(encoding='utf-8')
                            # 最近一章：开头回顾+完整结尾（连贯性关键）
                            if pf == recent_chapters[-1]:
                                ch_start = text[:800] if len(text) > 800 else text
                                ch_end = text[-1500:] if len(text) > 2000 else text
                                recent.append(f"【前一章·{pf.stem}开头回顾】\n{ch_start}")
                                recent.append(f"【前一章·{pf.stem}结尾 — 必须紧接】\n{ch_end}")
                            else:
                                ch_sample = text[:600] if len(text) > 600 else text
                                ch_tail = text[-400:] if len(text) > 1000 else ""
                                recent.append(f"【{pf.stem}节选】\n{ch_sample}\n...(结尾) {ch_tail}")
                        prev_context = "\n\n---\n\n".join(recent)
                
                outlines_ctx = self._get_outlines_context()
                if outlines_ctx:
                    prev_context = outlines_ctx + "\n\n---\n\n" + prev_context
                
                world_ctx = self._get_world_context()
                if world_ctx:
                    prev_context = world_ctx + "\n\n---\n\n" + prev_context
                
                # 添加强制连贯指令
                coherence_hint = "\n\n【⚠️ 连贯性核心要求】\n1. 本章必须紧接前一章结尾的情节继续\n2. 不得更换世界观设定、场景类型、故事基调\n3. 保持与前几章一致的叙事风格和语言风格\n4. 所有已出现角色保持性格、关系、状态一致"
                prev_context = prev_context + coherence_hint if prev_context else coherence_hint
                
                # 🔥 18+/擦边内容注入
                adult_content = self.config.get("adult_content", False)
                edge_content = self.config.get("edge_content", False)
                if adult_content or edge_content:
                    content_hint = self._build_content_hint(adult_content, edge_content, meta.get("genre", ""))
                    if content_hint:
                        prev_context = prev_context + "\n\n" + content_hint
                
                content = self.agent.generate_chapter(
                    ch_num,
                    chapter_info.get("title", f"第{ch_num}章"),
                    chapter_info.get("summary", ""),
                    word_count=meta.get("word_count_per_chapter", 3000),
                    prev_context=prev_context
                )
                
                # 保存章节
                chapters_dir = self.current_novel_dir / "chapters"
                chapters_dir.mkdir(exist_ok=True)
                with open(chapters_dir / f"chapter_{ch_num:04d}.txt", 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # GUI操作必须在主线程
                self.root.after(0, lambda: self._display_chapter(
                    ch_num, chapter_info.get("title", ""), content))
                
                # 自动定稿
                self.agent.finalize_chapter(ch_num, content)
                
                # 角色EXP奖励
                self._award_chapter_exp(ch_num, content)
                
                # 名场面检测
                if self.config.get("auto_detect_scene", True):
                    self._detect_and_prompt_image(content, ch_num)
                
                self._log(f"第{ch_num}章已保存并定稿")
            except Exception as e:
                self._log(f"生成失败: {e}")
                self.root.after(0, lambda _exc=e: messagebox.showerror("错误", str(_exc)))
        
        threading.Thread(target=run, daemon=True).start()
    def _review_chapter(self):
        """审校当前章节"""
        if not self._check_ready():
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可审校的内容")
            return
        
        with self._state_lock:
            ch_num = self.current_chapter

        def run():
            try:
                review = self.agent.review_chapter(ch_num, content)
                review_json = json.dumps(review, indent=2, ensure_ascii=False)
                self.root.after(0, lambda: self._display_review(review_json))
                self._log(f"审校完成，评分：{review.get('overall_score', 'N/A')}")
            except Exception as e:
                self._log(f"审校失败: {e}")
                self.root.after(0, lambda _exc=e: messagebox.showerror("错误", str(_exc)))
        
        threading.Thread(target=run, daemon=True).start()
    def _style_optimize(self):
        """风格优化当前章节"""
        if not self._check_ready():
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可优化的内容")
            return
        
        def run():
            try:
                self._log("正在进行风格优化...")
                
                settings = self.memory.get_settings() if self.memory else {}
                meta = self._get_meta()
                
                system = f"""你是专业小说风格优化师。小说类型：{meta.get('genre', '未知')}
世界观：{json.dumps(settings, ensure_ascii=False)[:300] if settings else '未知'}

优化要求：
1. 保持原文情节和结构
2. 增强文学性和可读性
3. 优化句式和用词
4. 增加细节描写（适当）
5. 确保风格一致
6. 直接输出优化后的内容"""
                
                prompt = f"请优化以下章节内容：\n\n{content[:3000]}"
                
                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
                
                self.root.after(0, lambda: self._display_optimized(result))
                self._log("风格优化完成")
                
            except Exception as e:
                self._log(f"风格优化失败: {e}")
        
        threading.Thread(target=run, daemon=True).start()
    def _style_imitation(self):
        """仿写风格 - 从文件夹导入多个作者的作品进行风格模仿"""
        if not self._check_ready():
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("仿写风格 - 模仿作者写作风格")
        dialog.geometry("750x650")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="仿写风格", font=('微软雅黑', 14, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(pady=(15, 10))
        
        # 已导入的作者风格列表
        style_frame = tk.LabelFrame(dialog, text=" 已导入的作者风格 ", bg=C['bg_dark'], fg=C['accent_light'],
                                    font=('微软雅黑', 10))
        style_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        style_list = tk.Listbox(style_frame, bg=C['bg_card'], fg=C['text_primary'],
                               font=('微软雅黑', 10), height=6, selectmode=tk.EXTENDED)
        style_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 存储风格数据
        self._imported_styles = getattr(self, '_imported_styles', [])
        for style in self._imported_styles:
            style_list.insert(tk.END, f"{style.get('author', '未知')} - {style.get('unique_features', '')[:30]}...")
        
        # 操作按钮
        btn_frame = tk.Frame(style_frame, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        def import_author_folder():
            """导入作者作品文件夹"""
            folder = filedialog.askdirectory(title="选择包含作者作品的文件夹")
            if not folder:
                return
            
            folder = Path(folder)
            texts = []
            
            # 读取文件夹中的所有文本文件
            for f in folder.glob("*"):
                if f.suffix.lower() in ['.txt', '.md']:
                    try:
                        texts.append((f.stem, f.read_text(encoding='utf-8')))
                    except Exception as e:
                        logger.debug(f"读取文件失败 {f.name}: {e}")
                elif f.suffix.lower() == '.docx':
                    try:
                        from docx import Document
                        doc = Document(str(f))
                        text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                        texts.append((f.stem, text))
                    except ImportError:
                        messagebox.showwarning("提示", "需要安装 python-docx 才能读取 Word 文档")
                        return
            
            if not texts:
                messagebox.showwarning("提示", "文件夹中没有找到可读取的文本文件")
                return
            
            # 分析每个文件的风格
            def analyze_all():
                for name, text in texts:
                    if len(text) > 100:  # 至少100字才分析
                        style = self.agent.analyze_style(text[:3000], name)
                        self._imported_styles.append(style)
                        self.root.after(0, lambda s=style: style_list.insert(tk.END, 
                            f"{s.get('author', '未知')} - {s.get('unique_features', '')[:30]}..."))
                
                self.root.after(0, lambda: messagebox.showinfo("完成", f"已导入 {len(texts)} 个作者的风格"))
                self._log(f"已导入 {len(texts)} 个作者的风格特征")
            
            self._log("正在分析作者风格...")
            threading.Thread(target=analyze_all, daemon=True).start()
        
        def import_single_file():
            """导入单个文件分析风格"""
            file_path = filedialog.askopenfilename(
                title="选择作者作品",
                filetypes=[("文本文件", "*.txt *.md"), ("Word文档", "*.docx"), ("所有文件", "*.*")]
            )
            if not file_path:
                return
            
            file_path = Path(file_path)
            text = ""
            
            try:
                if file_path.suffix.lower() in ['.txt', '.md']:
                    text = file_path.read_text(encoding='utf-8')
                elif file_path.suffix.lower() == '.docx':
                    from docx import Document
                    doc = Document(str(file_path))
                    text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {e}")
                return
            
            if len(text) < 100:
                messagebox.showwarning("提示", "文本内容太少，无法准确分析风格")
                return
            
            author_name = tk.simpledialog.askstring("作者名称", "请输入作者名称:", initialvalue=file_path.stem)
            if not author_name:
                return
            
            def analyze():
                style = self.agent.analyze_style(text[:3000], author_name)
                self._imported_styles.append(style)
                self.root.after(0, lambda: style_list.insert(tk.END, 
                    f"{style.get('author', '未知')} - {style.get('unique_features', '')[:30]}..."))
                self.root.after(0, lambda: messagebox.showinfo("完成", f"已分析 {author_name} 的风格"))
                self._log(f"已分析 {author_name} 的写作风格")
            
            self._log(f"正在分析 {author_name} 的风格...")
            threading.Thread(target=analyze, daemon=True).start()
        
        def remove_selected():
            """移除选中的风格"""
            selected = style_list.curselection()
            for idx in reversed(selected):
                style_list.delete(idx)
                if idx < len(self._imported_styles):
                    self._imported_styles.pop(idx)
        
        tk.Button(btn_frame, text="导入文件夹", command=import_author_folder,
                 bg=C['accent'], fg='white', font=('微软雅黑', 9), padx=10).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="导入单个文件", command=import_single_file,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 9), padx=10).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="移除选中", command=remove_selected,
                 bg=C['error'], fg='white', font=('微软雅黑', 9), padx=10).pack(side=tk.RIGHT, padx=3)
        
        # 创作设置
        write_frame = tk.LabelFrame(dialog, text=" 仿写创作 ", bg=C['bg_dark'], fg=C['accent_light'],
                                   font=('微软雅黑', 10))
        write_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # 创作提示
        tk.Label(write_frame, text="创作提示:", bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=10, pady=(5, 3))
        prompt_text = tk.Text(write_frame, wrap=tk.WORD, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'], height=3)
        prompt_text.pack(fill=tk.X, padx=10, pady=3)
        prompt_text.insert("1.0", "请用模仿的风格写一段关于...")
        
        # 字数设置
        params_frame = tk.Frame(write_frame, bg=C['bg_dark'])
        params_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(params_frame, text="字数:", bg=C['bg_dark'], fg=C['text_primary']).pack(side=tk.LEFT)
        word_count_var = tk.StringVar(value="3000")
        ttk.Combobox(params_frame, textvariable=word_count_var, 
                    values=["500", "1000", "2000", "3000", "5000"], width=8).pack(side=tk.LEFT, padx=5)
        
        # 模式选择
        mode_var = tk.StringVar(value="single")
        tk.Radiobutton(params_frame, text="单一风格", variable=mode_var, value="single",
                       bg=C['bg_dark'], fg=C['text_primary'], selectcolor=C['bg_dark']).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(params_frame, text="融合风格", variable=mode_var, value="blend",
                       bg=C['bg_dark'], fg=C['text_primary'], selectcolor=C['bg_dark']).pack(side=tk.LEFT, padx=10)
        
        def start_imitation():
            """开始仿写"""
            if not self._imported_styles:
                messagebox.showwarning("提示", "请先导入至少一个作者的风格")
                return
            
            prompt = prompt_text.get("1.0", tk.END).strip()
            if not prompt:
                messagebox.showwarning("提示", "请输入创作提示")
                return
            
            word_count = int(word_count_var.get())
            mode = mode_var.get()
            selected = style_list.curselection()
            
            if mode == "single":
                if not selected:
                    messagebox.showwarning("提示", "请选择一个作者风格")
                    return
                style = self._imported_styles[selected[0]]
                
                def generate():
                    try:
                        self._log(f"正在使用 {style.get('author', '')} 的风格创作...")
                        result = self.agent.generate_with_style(prompt, style, word_count)
                        self.root.after(0, lambda: self._display_generated(result))
                        self._log("仿写完成")
                    except Exception as e:
                        self._log(f"仿写失败: {e}")
                
                threading.Thread(target=generate, daemon=True).start()
            else:
                # 融合模式
                if len(selected) < 2:
                    messagebox.showwarning("提示", "融合模式需要选择至少2个风格")
                    return
                styles = [self._imported_styles[i] for i in selected]
                
                def generate():
                    try:
                        self._log("正在融合多个风格创作...")
                        result = self.agent.blend_styles(styles, prompt, word_count)
                        self.root.after(0, lambda: self._display_generated(result))
                        self._log("风格融合创作完成")
                    except Exception as e:
                        self._log(f"风格融合失败: {e}")
                
                threading.Thread(target=generate, daemon=True).start()
        
        def apply_to_chapter():
            """将仿写结果应用到当前章节"""
            if not self._imported_styles:
                messagebox.showwarning("提示", "请先导入风格")
                return
            
            selected = style_list.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择一个风格")
                return
            
            style = self._imported_styles[selected[0]]
            current_content = self.content_text.get("1.0", tk.END).strip()
            
            if not current_content:
                messagebox.showwarning("提示", "当前章节没有内容")
                return
            
            def rewrite():
                try:
                    self._log(f"正在用 {style.get('author', '')} 的风格重写当前章节...")
                    prompt = f"请用以下风格重写这段内容：\n\n{current_content[:2000]}"
                    result = self.agent.generate_with_style(prompt, style, len(current_content))
                    self.root.after(0, lambda: self._display_generated(result))
                    self._log("风格重写完成")
                except Exception as e:
                    self._log(f"风格重写失败: {e}")
            
            threading.Thread(target=rewrite, daemon=True).start()
        
        action_frame = tk.Frame(write_frame, bg=C['bg_dark'])
        action_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(action_frame, text="开始仿写", command=start_imitation,
                 bg=C['success'], fg='white', font=('微软雅黑', 11, 'bold'), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        tk.Button(action_frame, text="用选中风格重写当前章节", command=apply_to_chapter,
                 bg=C['warning'], fg='white', font=('微软雅黑', 10), padx=15).pack(side=tk.LEFT, padx=5)
    def _stop_generate(self):
        """停止自动创作"""
        self._auto_running = False
        self._stop_flag = True
        self._log("已请求停止自动创作，正在完成当前章节...")
    def _auto_detect_decisions(self, chapter_num: int, content: str):
        """自动检测决策点，记录到主世界线（不生成分支）"""
        try:
            # 只在有实质内容的章节检测
            if len(content) < 500:
                return
            
            timeline_dir = self.current_novel_dir / "timelines"
            timeline_dir.mkdir(exist_ok=True)
            main_file = timeline_dir / "main.json"
            
            # 读取或创建主世界线
            if main_file.exists():
                main_data = json.loads(main_file.read_text(encoding='utf-8'))
            else:
                main_data = {"name": "主线", "events": [], "chapters": [], "branches": []}
            
            # 只检测新章节，已检测过的不重复
            if chapter_num in main_data.get("chapters", []):
                return
            
            system = """你是专业故事分析师。提取本章的关键决策点，输出JSON:
{"decisions": [{"desc": "当时的情况", "chosen": "主角选择了什么", "alternative": "可能的另一种选择"}]}
如果没有明显的决策点，输出[]。只检测真正影响故事走向的选择。"""
            
            response = self.ai_client.chat(
                [{"role": "user", "content": f"第{chapter_num}章:\n{content[:2000]}"}],
                system=system, max_tokens=1500
            )
            if not response:
                return
            
            # 多策略JSON解析
            data = None
            
            # Strategy 1: 括号深度追踪
            start = response.find('{')
            if start >= 0:
                depth = 0
                end_idx = -1
                for i in range(start, len(response)):
                    if response[i] == '{': depth += 1
                    elif response[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx > start:
                    json_str = response[start:end_idx]
                    # 修复常见JSON问题
                    json_str = re.sub(r',\s*}', '}', json_str)
                    json_str = re.sub(r',\s*]', ']', json_str)
                    # 修复未转义的引号
                    json_str = json_str.replace('\n', '\\n').replace('\r', '\\r')
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
            
            # Strategy 2: 清理markdown后重试
            if not data:
                cleaned = response.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                match = re.search(r'\{[\s\S]*\}', cleaned.strip())
                if match:
                    try:
                        data = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass
            
            # Strategy 3: 正则提取decisions数组
            if not data:
                match = re.search(r'"decisions"\s*:\s*\[([\s\S]*?)\]', response)
                if match:
                    try:
                        decisions_str = '[{' + match.group(1) + '}]'
                        decisions_str = re.sub(r',\s*}', '}', decisions_str)
                        decisions_str = re.sub(r',\s*]', ']', decisions_str)
                        data = {"decisions": json.loads(decisions_str)}
                    except json.JSONDecodeError:
                        pass
            
            if not data:
                return
            
            decisions = data.get("decisions", [])
            if not decisions:
                return
            
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                desc = d.get('desc', d.get('description', ''))
                chosen = d.get('chosen', d.get('choice', ''))
                alternative = d.get('alternative', d.get('other', ''))
                if not desc or not chosen:
                    continue
                main_data["events"].append(
                    f"第{chapter_num}章: {desc[:80]} → 选择了「{chosen[:30]}」"
                )
                main_data.setdefault("branches", []).append({
                    "chapter": chapter_num,
                    "decision": desc[:100],
                    "chosen": chosen[:50],
                    "alternative": alternative[:50],
                    "story": "",  # 分支故事，初始为空
                })
            
            main_data.setdefault("chapters", []).append(chapter_num)
            main_file.write_text(json.dumps(main_data, indent=2, ensure_ascii=False), encoding='utf-8')
            self._log(f"[世界线] 第{chapter_num}章 记录{len(decisions)}个决策点")
            
        except Exception as e:
            self._log(f"[世界线] 决策检测异常: {type(e).__name__}: {e}")
    def _edit_decision(self, dialog, all_branches, selected_idx, timelines, tl_name, main_file, refresh_callback):
        """编辑选中的决策点"""
        idx = selected_idx[0]
        if idx < 0 or idx >= len(all_branches):
            messagebox.showwarning("提示", "请先在左侧点击选择一个决策点")
            return
        
        br = all_branches[idx]
        
        edit_dlg = tk.Toplevel(dialog)
        edit_dlg.title("编辑决策点")
        edit_dlg.geometry("500x450")
        edit_dlg.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(edit_dlg, text="编辑决策点", font=('微软雅黑', 11, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=8)
        
        fields = [
            ("决策情境 (decision)", "decision", 60),
            ("选择方案 (chosen)", "chosen", 40),
            ("另一可能 (alternative)", "alternative", 40),
            ("分支故事 (story)", "story", 200),
        ]
        
        entries = {}
        for label, key, height in fields:
            tk.Label(edit_dlg, text=label, font=('微软雅黑', 9),
                    bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=15, pady=(8, 1))
            
            if height > 80:
                entry = tk.Text(edit_dlg, height=5, font=('微软雅黑', 9),
                               bg=C['bg_medium'], fg=C['text_primary'], relief=tk.FLAT, padx=8, pady=5)
            else:
                entry = tk.Entry(edit_dlg, font=('微软雅黑', 9),
                                bg=C['bg_medium'], fg=C['text_primary'], relief=tk.FLAT)
            entry.pack(fill=tk.X, padx=15)
            entries[key] = entry
        
        # 填充当前值
        for key, entry in entries.items():
            val = br.get(key, "")
            if isinstance(entry, tk.Text):
                entry.insert("1.0", val)
            else:
                entry.insert(0, val)
        
        def save_edit():
            for key, entry in entries.items():
                val = entry.get("1.0", tk.END).strip() if isinstance(entry, tk.Text) else entry.get().strip()
                br[key] = val
            
            # 回写文件
            target = next((t for t in timelines if t.get("name") == tl_name), None)
            if target:
                target_file = self.current_novel_dir / "timelines" / target["_file"]
                target_file.write_text(json.dumps(target, indent=2, ensure_ascii=False), encoding='utf-8')
                self._log(f"[世界线] 决策点已编辑保存")
            
            edit_dlg.destroy()
            refresh_callback()
        
        tk.Button(edit_dlg, text="💾 保存", font=('微软雅黑', 10), padx=20,
                 bg=C['accent'], fg='white', relief=tk.FLAT,
                 command=save_edit).pack(pady=10)
    def _award_chapter_exp(self, chapter_num: int, content: str):
        """章节完成后，AI分析角色行为自动给予EXP（基于角色做了什么）"""
        # 防止同一章节重复发放EXP
        with self._state_lock:
            if chapter_num in self._exp_awarded_chapters:
                return
            self._exp_awarded_chapters.add(chapter_num)
        
        try:
            if not self.character_system or not self.ai_client:
                self._log(f"[角色EXP] 跳过: character_system={self.character_system is not None}, ai_client={self.ai_client is not None}")
                return
            if not self.ai_client.is_configured():
                self._log(f"[角色EXP] 跳过: AI未配置")
                return
            
            # 获取当前活跃角色和配角列表
            all_chars = self.character_system.get_character_names()
            if not all_chars:
                return
            
            _diag.chapter_event(chapter_num, "EXP_ANALYSIS_START", {
                "characters": all_chars[:8], "content_len": len(content)
            })
            
            # 对活跃角色进行行为分析（最多分析8个）
            chars_to_analyze = all_chars[:8]
            chars_str = "、".join(chars_to_analyze)
            
            # AI分析提示：提取角色在章节中的行为（支持正向和负向）
            system_prompt = f"""你是小说角色行为分析专家。
分析以下章节内容中，下列角色分别做了什么事情。
人生有得有失，故事中的角色也会经历成功和挫折。根据行为给予正向或负向的经验值。

可分析的角色: {chars_str}

正向行为（+EXP）：
- 重大战斗胜利/对决: 60-150
- 突破领悟/觉醒: 60-120
- 技能学习/修炼成功: 30-80
- 关键决策正确: 25-60
- 探索发现/奇遇: 20-50
- 社交结盟/帮助他人: 10-40
- 日常积极行为: 5-20

负向行为（-EXP，体现成长的代价）：
- 战斗失败/被击败: -30 to -100
- 决策失误/判断错误: -20 to -60
- 遭受背叛/被暗算: -10 to -40
- 技能使用失败/走火入魔: -20 to -80
- 失去重要物品/资源: -10 to -30
- 违背承诺/道德瑕疵: -5 to -20
- 遭遇挫折/低谷期: -5 to -15

未出场/无行动: 0

输出格式（严格JSON，键为角色名，值为action/exp/detail）：
{{"角色名": {{"action": "行为类别(+/-)", "exp": 经验值(正数或负数), "detail": "行为简述(15字内)"}}}}
示例: {{"主角名": {{"action": "战斗失败", "exp": -50, "detail": "被强敌击败重伤"}}}}

重要：只输出JSON，不要任何其他文字！"""

            # 采样策略：开头+中间+结尾，覆盖全文角色行为
            if len(content) > 3000:
                mid = len(content) // 2
                sample = content[:1500] + "\n...\n" + content[mid-500:mid+500] + "\n...\n" + content[-1000:]
            else:
                sample = content
            
            # 重试机制（增加到3次）
            response = None
            for attempt in range(3):
                try:
                    # 简化prompt，明确要求只输出JSON
                    simple_prompt = f"""分析第{chapter_num}章中角色行为，输出JSON。

角色列表: {chars_str}

章节内容:
{sample}

输出格式（只输出JSON，不要分析过程）:
{{"角色名": {{"action": "行为", "exp": 数值, "detail": "简述"}}}}"""
                    
                    self._log(f"[角色EXP] 第{attempt+1}次调用AI...")
                    response = self.ai_client.chat(
                        [{"role": "user", "content": simple_prompt}],
                        system=system_prompt, max_tokens=3000  # 增大token以容纳思考+JSON
                    )
                    
                    # 详细日志
                    self._log(f"[角色EXP] 第{attempt+1}次响应: type={type(response).__name__}, len={len(response) if response else 0}")
                    
                    # 检查响应是否有效
                    if response and len(response.strip()) > 10:
                        self._log(f"[角色EXP] 第{attempt+1}次调用成功，响应长度: {len(response)}")
                        break
                    else:
                        self._log(f"[角色EXP] 第{attempt+1}次响应为空或过短: {repr(response)[:100]}")
                        response = None
                        
                except Exception as e:
                    self._log(f"[角色EXP] 第{attempt+1}次调用异常: {type(e).__name__}: {e}")
                    response = None
                
                if attempt < 2:
                    self._log(f"[角色EXP] 重试{attempt+2}/3...")
                    time.sleep(3)
            
            if not response:
                self._log(f"[角色EXP] 3次调用均失败，跳过本次EXP发放")
                _diag.chapter_event(chapter_num, "EXP_NO_RESPONSE", {"chars": chars_str, "attempts": 3})
                return
            
            _diag.chapter_event(chapter_num, "EXP_AI_RESPONSE", {
                "response_len": len(response), "response_preview": response[:200]
            })
            
            # 解析JSON（增强容错）
            behaviors = self._parse_exp_json(response)
            if not behaviors:
                self._log(f"[角色EXP] JSON解析失败: {response[:100]}")
                _diag.chapter_event(chapter_num, "EXP_JSON_PARSE_FAILED", {"response": response[:200]})
                return
            
            # 发放EXP（支持正向和负向，含模糊角色名匹配）
            total_exp = 0
            logs = []
            for char_name, behavior in behaviors.items():
                if not isinstance(behavior, dict):
                    continue
                try:
                    exp = int(behavior.get("exp", 0))
                    exp = max(-200, min(200, exp))  # 钳位EXP范围
                except (ValueError, TypeError):
                    continue
                if exp == 0:
                    continue  # 跳过无行动
                action = behavior.get("action", "行为")
                detail = behavior.get("detail", "")
                
                # 查找角色（精确匹配 → 前缀匹配）
                char = self.character_system.get_character(char_name)
                if not char:
                    # 优先精确匹配，其次前缀匹配
                    best_match = None
                    best_score = 0
                    for real_name in all_chars:
                        if real_name == char_name:
                            best_match = real_name
                            best_score = 100
                            break
                        # 前缀匹配（如"林风"匹配"林"）
                        if real_name.startswith(char_name) or char_name.startswith(real_name):
                            score = len(real_name)  # 更长的匹配更精确
                            if score > best_score:
                                best_match = real_name
                                best_score = score
                    if best_match:
                        char = self.character_system.get_character(best_match)
                        char_name = best_match
                if not char:
                    continue
                
                try:
                    result = char.add_exp(exp)
                    self.character_system.save_character(char_name)
                    total_exp += exp
                except Exception as e:
                    self._log(f"[角色EXP] {char_name} add_exp失败: {e}")
                    continue
                
                # 正向: 升级提示
                if exp > 0 and result.get("leveled_up"):
                    logs.append(f"{char_name}({action}) +{exp}EXP → 升级 Lv.{result['current_level']}")
                elif exp < 0 and result.get("leveled_down"):
                    logs.append(f"{char_name}({action}) {exp}EXP → 降级 Lv.{result['current_level']}")
                elif exp < 0:
                    logs.append(f"{char_name}({action}) {exp}EXP | {detail}")
                else:
                    logs.append(f"{char_name}({action}) +{exp}EXP | {detail}")
            
            if logs:
                self._log(f"[角色EXP] 第{chapter_num}章 共{total_exp}EXP | " + " | ".join(logs[:5]))
                _diag.chapter_event(chapter_num, "EXP_AWARDED", {
                    "total_exp": total_exp, "characters_awarded": len(logs),
                    "details": logs[:5]
                })
                self.root.after(0, self._update_char_display)
            else:
                self._log(f"[角色EXP] 第{chapter_num}章 未检测到角色有效行为")
                _diag.chapter_event(chapter_num, "EXP_NO_ACTION", {"behaviors_sample": str(behaviors)[:200]})
                
        except Exception as e:
            self._log(f"[角色EXP] 分析失败: {e}")
            _diag.log("ERROR", "award_chapter_exp", {"chapter": chapter_num}, error=e)
            import traceback
            self._log(traceback.format_exc())
    def _parse_exp_json(self, response: str) -> dict:
        """解析EXP分析的JSON响应（增强容错）

        P2-6: 纯逻辑已抽取至 app.parsing.parse_exp_json（可独立单测）。
        """
        return parse_exp_json(response)
    def _regen_current_chapter(self):
        """重新创作当前章节"""
        if not self._check_ready(silent=True):
            return
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        # 获取当前章节
        current_ch = self.current_chapter
        if current_ch <= 0:
            messagebox.showwarning("提示", "没有当前章节")
            return
        
        result = messagebox.askyesno("重新创作", 
            f"确定要重新创作第{current_ch}章吗？\n当前内容将被覆盖。")
        if not result:
            return
        
        self._log(f"正在重新创作第{current_ch}章...")
        
        def run():
            try:
                meta = self._get_meta()
                chapter_info = {}
                if self.outline and current_ch <= len(self.outline):
                    chapter_info = self.outline[current_ch - 1]
                
                # 构建上下文（前几章完整内容 + 整体大纲 + 故事大纲）
                prev_context = ""
                chapters_dir = self.current_novel_dir / "chapters"
                if chapters_dir.exists():
                    # 🔧 修复：获取所有章节文件，取最近3章（而非只匹配1个文件）
                    all_chapters = sorted(chapters_dir.glob("chapter_*.txt"))
                    recent_chapters = [f for f in all_chapters if f.stem < f"chapter_{current_ch:04d}"]
                    recent_chapters = recent_chapters[-3:]
                    if recent_chapters:
                        recent = []
                        for pf in recent_chapters:
                            text = pf.read_text(encoding='utf-8')
                            if pf == recent_chapters[-1]:
                                ch_start = text[:800] if len(text) > 800 else text
                                ch_end = text[-1500:] if len(text) > 2000 else text
                                recent.append(f"【前一章·{pf.stem}开头回顾】\n{ch_start}")
                                recent.append(f"【前一章·{pf.stem}结尾 — 必须紧接】\n{ch_end}")
                            else:
                                ch_sample = text[:600] if len(text) > 600 else text
                                ch_tail = text[-400:] if len(text) > 1000 else ""
                                recent.append(f"【{pf.stem}节选】\n{ch_sample}\n...(结尾) {ch_tail}")
                        prev_context = "\n\n---\n\n".join(recent)
                
                outlines_ctx = self._get_outlines_context()
                if outlines_ctx:
                    prev_context = outlines_ctx + "\n\n---\n\n" + prev_context
                
                world_ctx = self._get_world_context()
                if world_ctx:
                    prev_context = world_ctx + "\n\n---\n\n" + prev_context
                
                # 添加强制连贯指令
                coherence_hint = "\n\n【⚠️ 连贯性核心要求】\n1. 本章必须紧接前一章结尾的情节继续\n2. 不得更换世界观设定、场景类型、故事基调\n3. 保持与前几章一致的叙事风格和语言风格\n4. 所有已出现角色保持性格、关系、状态一致"
                prev_context = prev_context + coherence_hint if prev_context else coherence_hint
                
                content = self.agent.generate_chapter(
                    current_ch,
                    chapter_info.get("title", f"第{current_ch}章"),
                    chapter_info.get("summary", ""),
                    word_count=meta.get("word_count_per_chapter", 10000),
                    prev_context=prev_context
                )
                
                # 保存
                chapters_dir = self.current_novel_dir / "chapters"
                chapters_dir.mkdir(exist_ok=True)
                with open(chapters_dir / f"chapter_{current_ch:04d}.txt", 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # 更新显示
                self.root.after(0, lambda c=content, n=current_ch, t=chapter_info.get("title", ""): 
                               self._display_chapter(n, t, c))
                self._log(f"第{current_ch}章重新创作完成")
                
            except Exception as e:
                self._log(f"重新创作失败: {e}")
        
        threading.Thread(target=run, daemon=True).start()
    def _regen_all_chapters(self):
        """全部重新创作 — 让用户选择是否重创世界观/角色/大纲"""
        if not self._check_ready(silent=True):
            return
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        # 构建选择对话框
        dlg = tk.Toplevel(self.root)
        dlg.title("全部重新创作")
        dlg.geometry("480x340")
        dlg.configure(bg=UIStyle.COLORS['bg_dark'])
        dlg.resizable(False, False)
        C = UIStyle.COLORS
        
        tk.Label(dlg, text="⚠️ 全部重新创作", font=('微软雅黑', 13, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=(12, 3))
        tk.Label(dlg, text="选择需要重新生成的内容：", font=('微软雅黑', 9),
                bg=C['bg_dark'], fg=C['text_secondary']).pack(pady=(0, 8))
        
        # 勾选框
        var_world = tk.BooleanVar(value=False)
        var_chars = tk.BooleanVar(value=False)
        var_outline = tk.BooleanVar(value=True)
        var_chapters = tk.BooleanVar(value=True)
        
        options_frame = tk.Frame(dlg, bg=C['bg_dark'])
        options_frame.pack(fill=tk.X, padx=20, pady=3)
        
        def make_cb(parent, text, var, enabled=True):
            cb = tk.Checkbutton(parent, text=text, variable=var,
                               font=('微软雅黑', 9),
                               bg=C['bg_dark'], fg=C['text_primary'],
                               selectcolor=C['bg_card'], activebackground=C['bg_dark'],
                               activeforeground=C['text_primary'],
                               wraplength=420, justify=tk.LEFT)
            cb.pack(anchor=tk.W, pady=3)
            if not enabled:
                cb.config(state=tk.DISABLED)
            return cb
        
        make_cb(options_frame, "重新生成世界观 (世界设定/背景)", var_world)
        make_cb(options_frame, "重新生成角色 (主角/配角/反派)", var_chars)
        make_cb(options_frame, "重新生成大纲 (全部: 章节/整体/故事)", var_outline)
        make_cb(options_frame, "重新生成所有章节 (正文内容)", var_chapters, enabled=False)
        
        # 提示
        tk.Label(dlg, text="未勾选的项目将保留现有内容",
                font=('微软雅黑', 9), bg=C['bg_dark'],
                fg=C['text_secondary']).pack(pady=(10, 5))
        
        result = {'confirmed': False}
        
        def on_confirm():
            result['confirmed'] = True
            result['world'] = var_world.get()
            result['chars'] = var_chars.get()
            result['outline'] = var_outline.get()
            dlg.destroy()
        
        def on_cancel():
            dlg.destroy()
        
        btn_frame = tk.Frame(dlg, bg=C['bg_dark'])
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="开始重新创作", command=on_confirm,
                 bg=C['error'], fg='white', font=('微软雅黑', 10, 'bold'),
                 padx=20, pady=6).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=on_cancel,
                 bg=C['bg_light'], fg=C['text_primary'],
                 font=('微软雅黑', 10), padx=20, pady=6).pack(side=tk.LEFT, padx=5)
        
        dlg.transient(self.root)
        dlg.grab_set()
        self.root.wait_window(dlg)
        
        if not result['confirmed']:
            return
        
        # 🛡️ 自动备份（在删除前）
        self._backup_novel("before_regen")
        
        # 删除勾选的内容
        if result['world']:
            sf = self.current_novel_dir / "memory" / "settings.json"
            if sf.exists():
                sf.unlink()
            self._log("已清除世界观")
        
        if result['chars']:
            cd = self.current_novel_dir / "characters"
            if cd.exists():
                for f in cd.glob("*.json"):
                    f.unlink()
            self._log("已清除所有角色")
        
        if result['outline']:
            of = self.current_novel_dir / "outline.json"
            if of.exists():
                of.unlink()
            # 清除整体大纲和故事大纲
            for fn in ["overall.json", "stories.json"]:
                fpath = self.current_novel_dir / "outlines" / fn
                if fpath.exists():
                    fpath.unlink()
            self.outline = []
            self._log("已清除所有大纲")
        
        # 删除旧章节
        chapters_dir = self.current_novel_dir / "chapters"
        if chapters_dir.exists():
            for f in chapters_dir.glob("chapter_*.txt"):
                f.unlink()
            self._log("已清除所有旧章节")
        
        # 重置EXP发放记录（旧章节已删除，新章节需要重新发放）
        self._exp_awarded_chapters.clear()
        
        # 清除旧的记忆数据（防止上一轮生成的污染）
        mem_dir = self.current_novel_dir / "memory"
        if mem_dir.exists():
            for sub in ["chapters", "chunks", "timeline"]:
                sd = mem_dir / sub
                if sd.exists():
                    for f in sd.glob("*"):
                        f.unlink()
            for fn in ["global_summary.txt", "inverted_index.json", "scores.json"]:
                fp = mem_dir / fn
                if fp.exists():
                    fp.unlink()
        # 清除摘要和场景提示
        for sd_name in ["summaries", "scene_prompts"]:
            sd = self.current_novel_dir / sd_name
            if sd.exists():
                for f in sd.glob("*"):
                    f.unlink()
        
        # 重置进度
        self.current_chapter = 0
        meta = self._get_meta()
        total = meta.get('total_chapters', meta.get('chapter_count', '?'))
        self.chapter_var.set(f"0/{total}")
        self.content_text.delete("1.0", tk.END)
        
        summary = []
        if result['world']: summary.append("世界观")
        if result['chars']: summary.append("角色")
        if result['outline']: summary.append("大纲")
        summary.append("所有章节")
        self._log(f"开始全部重新创作: {', '.join(summary)}")
        
        # 启动自动创作
        self._auto_generate()
    def _auto_generate(self):
        """自动创作全流程 - 优化版本，支持大量章节"""
        # 防重复点击
        if hasattr(self, '_auto_running') and self._auto_running:
            self._log("自动创作正在进行中，请勿重复点击")
            return
        
        if not self._check_ready():
            return
        
        self._auto_running = True
        self.auto_btn.config(state=tk.DISABLED, text="创作中...")
        
        meta = self._get_meta()
        
        # 🔥 18+/擦边内容注入到概念中（影响世界观、角色、大纲生成）
        adult_content = self.config.get("adult_content", False)
        edge_content = self.config.get("edge_content", False)
        if adult_content or edge_content:
            content_hint = self._build_content_hint(adult_content, edge_content, meta.get("genre", ""))
            if content_hint:
                original_concept = meta.get("concept", "")
                meta["concept"] = original_concept + "\n\n" + content_hint if original_concept else content_hint
                self._log(f"[内容模式] 18+:{'开' if adult_content else '关'} 擦边:{'开' if edge_content else '关'}")
        
        def run():
            try:
                self._log("=== 开始自动创作 ===")
                self._log(f"[优化] 已启用内存优化模式，每10章自动清理缓存")
                
                # 1. 生成世界观（如果不存在）
                settings_file = self.current_novel_dir / "memory" / "settings.json"
                if not settings_file.exists():
                    try:
                        concept = meta.get("concept", "")
                        self.agent.generate_settings(meta["genre"], meta["title"], concept)
                        if concept:
                            self._log(f"[世界观] 已基于用户想法生成世界观")
                    except Exception as e:
                        self._log(f"世界观生成失败，跳过: {e}")
                else:
                    self._log("世界观已存在，跳过生成")

                # 2. 生成角色（如果不存在）
                characters_dir = self.current_novel_dir / "characters"
                if not characters_dir.exists() or not list(characters_dir.glob("*.json")):
                    try:
                        chars = self.agent.generate_characters(meta["genre"], meta["title"])
                        # 验证：检查characters/目录是否有文件生成
                        char_files = list(characters_dir.glob("*.json"))
                        if not char_files:
                            self._log("[错误] 角色生成后 characters/ 目录仍为空！")
                            # 尝试从 memory 恢复
                            self._sync_characters_from_memory()
                            char_files = list(characters_dir.glob("*.json"))
                        if char_files:
                            self._log(f"角色生成完成 ({len(char_files)}个角色)")
                            # 🔒 提取主角名并保存到meta.json
                            protagonist = ""
                            for name, info in (chars or {}).items():
                                if isinstance(info, dict) and info.get("category") == "主角":
                                    protagonist = name
                                    break
                            if not protagonist and chars:
                                # 如果没有标记为主角，取第一个角色
                                protagonist = next(iter(chars.keys()), "")
                            if protagonist:
                                meta["protagonist"] = protagonist
                                with open(self.current_novel_dir / "meta.json", 'w', encoding='utf-8') as f:
                                    json.dump(meta, f, indent=2, ensure_ascii=False)
                                self.memory.save_meta("protagonist", protagonist)
                                self._log(f"[角色] 主角已锁定: {protagonist}")
                        else:
                            self._log("[错误] 角色生成完全失败，无法恢复")
                    except Exception as e:
                        self._log(f"角色生成失败: {e}")
                        import traceback
                        self._log(traceback.format_exc())
                else:
                    self._log("角色已存在，跳过生成")

                # 3. 生成大纲（如果不存在）
                outline_file = self.current_novel_dir / "outline.json"
                if not outline_file.exists() or not self.outline:
                    try:
                        concept = meta.get("concept", "")
                        real_total = meta.get("total_chapters", meta.get("chapter_count"))
                        # 大题纲分批生成，超过50章先打前站
                        outline_count = min(real_total, 50) if real_total > 10 else real_total
                        with self._state_lock:
                            self.outline = self.agent.generate_outline(
                                meta["genre"], meta["title"], outline_count, concept,
                                total_chapters=real_total)
                        with open(outline_file, 'w', encoding='utf-8') as f:
                            with self._state_lock:
                                json.dump(self.outline, f, indent=2, ensure_ascii=False)
                        # 更新meta中的章节数，保持total_chapters不变
                        meta["chapter_count"] = outline_count
                        with open(self.current_novel_dir / "meta.json", 'w', encoding='utf-8') as f:
                            json.dump(meta, f, indent=2, ensure_ascii=False)
                        self.root.after(0, self._refresh_outline_list)
                        self._log(f"大纲已生成: {len(self.outline)}章 (总计划{real_total}章)")
                    except Exception as e:
                        self._log(f"大纲生成失败: {e}")
                        self._auto_running = False
                        self.root.after(0, lambda: self.auto_btn.config(state=tk.NORMAL, text="自动创作"))
                        return
                else:
                    self._log(f"大纲已存在: {len(self.outline)}章，跳过生成")
                
                # 3.5 自动生成整体大纲和故事大纲（如果缺失）
                outlines_dir = self.current_novel_dir / "outlines"
                outlines_dir.mkdir(exist_ok=True)
                overall_file = outlines_dir / "overall.json"
                stories_file = outlines_dir / "stories.json"
                
                if not overall_file.exists() or not stories_file.exists():
                    self._log("自动生成整体大纲和故事大纲...")
                    concept = meta.get("concept", "")
                    chapter_outline = self.outline  # 已生成的章节大纲作为上下文
                    
                    # 生成整体大纲
                    if not overall_file.exists():
                        try:
                            overall = self._generate_overall_outline(meta, concept, chapter_outline)
                            self._save_overall_outline(overall)
                            self._log(f"整体大纲已生成 ({len(overall)}项)")
                        except Exception as e:
                            self._log(f"整体大纲生成失败: {e}")
                    
                    # 生成故事大纲
                    if not stories_file.exists():
                        try:
                            stories = self._generate_story_outlines(meta, concept, chapter_outline)
                            self._save_story_outlines(stories)
                            self._log(f"故事大纲已生成 ({len(stories)}条线)")
                        except Exception as e:
                            self._log(f"故事大纲生成失败: {e}")

                # 4. 逐章生成（从已完成的下一章开始）
                chapters_dir = self.current_novel_dir / "chapters"
                chapters_dir.mkdir(exist_ok=True)
                existing_chapters = set()
                for f in chapters_dir.glob("chapter_*.txt"):
                    try:
                        num = int(f.stem.split('_')[-1])
                        existing_chapters.add(num)
                    except ValueError:
                        pass
                
                with self._state_lock:
                    outline_snapshot = list(self.outline)
                
                total = len(outline_snapshot)
                display_total = meta.get("total_chapters", total)  # 真实总章数用于进度显示
                skipped = 0
                generated = 0
                failed = 0
                batch_count = 0
                
                for i, chapter_info in enumerate(outline_snapshot):
                    ch_num = i + 1
                    
                    # 检查是否请求停止
                    if not self._auto_running:
                        self._log("自动创作已停止")
                        break
                    
                    # 跳过已完成的章节
                    if ch_num in existing_chapters:
                        skipped += 1
                        continue
                    
                    with self._state_lock:
                        self.current_chapter = ch_num
                    
                    # 🛡️ 保存检查点（断电恢复用）
                    self._save_checkpoint(ch_num, "generating")
                    
                    try:
                        # 构建前几章上下文（内容+摘要）
                        recent_context = []
                        ch_count = min(ch_num - 1, 3)  # 最多前3章
                        for offset in range(ch_count, 0, -1):
                            prev_ch = ch_num - offset
                            pf = chapters_dir / f"chapter_{prev_ch:04d}.txt"
                            if pf.exists():
                                text = pf.read_text(encoding='utf-8')
                                if offset == 1:
                                    # 最近一章：保留开头+完整结尾（连贯性关键）
                                    content_sample = text[:600] if len(text) > 600 else text
                                    ending_sample = text[-1200:] if len(text) > 1800 else text
                                    recent_context.append(f"【前一章·第{prev_ch}章开头】\n{content_sample}")
                                    recent_context.append(f"【前一章·第{prev_ch}章结尾 — 必须紧接此情节继续】\n{ending_sample}")
                                else:
                                    # 更早的章节：只保留摘要
                                    content_sample = text[:400] if len(text) > 400 else text
                                    recent_context.append(f"【第{prev_ch}章概要】\n{content_sample}")
                        
                        prev_context = "\n---\n".join(recent_context)
                        
                        # 完结收束：根据小说真实总章数判断是否接近结局
                        # 使用 meta 中的 total_chapters（用户设定的总章数），而非当前批次大纲长度
                        real_total = meta.get("total_chapters", meta.get("chapter_count", len(outline_snapshot)))
                        remaining = real_total - ch_num
                        if real_total > 100 and ch_num <= 10:
                            pass  # 长篇开头不提示完结
                        elif remaining <= 3:
                            prev_context += f"\n\n【重要】只剩{remaining+1}章完结。本章必须推进至最终结局。"
                        elif remaining <= 10:
                            prev_context += f"\n\n【提示】还有{remaining+1}章。请为结局做铺垫，收束支线。"
                        
                        # 注入整体大纲和故事大纲到生成上下文
                        outlines_ctx = self._get_outlines_context()
                        if outlines_ctx:
                            prev_context = outlines_ctx + "\n\n---\n\n" + prev_context
                        
                        # 注入世界观设定到生成上下文
                        world_ctx = self._get_world_context()
                        if world_ctx:
                            prev_context = world_ctx + "\n\n---\n\n" + prev_context
                        
                        # 如果大纲是"待规划"或为空，批量生成后续大纲
                        chapter_summary = chapter_info.get("summary", "")
                        chapter_title = chapter_info.get("title", f"第{ch_num}章")
                        if not chapter_summary or chapter_summary == "待规划":
                            # 批量生成后10章大纲（含当前章）
                            batch_end = min(ch_num + 9, len(outline_snapshot))
                            self._log(f"大纲不足，动态生成第{ch_num}-{batch_end}章大纲...")
                            try:
                                real_total = meta.get("total_chapters", meta.get("chapter_count", len(outline_snapshot)))
                                remaining = real_total - ch_num + 1
                                is_ending = (ch_num > real_total * 0.85)
                                ending_hint = "这是结尾阶段，请规划收束。每条摘要需推进结局。" if is_ending else ""
                                
                                # 获取世界观和概念上下文
                                world_context = self._get_world_context() or ""
                                concept_hint = f"\n\n【世界观/概念】\n{world_context[:600]}\n" if world_context else ""
                                
                                protagonist = meta.get("protagonist", "")
                                protagonist_hint = f"\n【重要】主角名为「{protagonist}」，所有章节必须以此角色为主角！" if protagonist else ""
                                
                                gen_system = f"""你是故事大纲师。基于前文和世界观生成{batch_end-ch_num+1}章大纲。{ending_hint}{protagonist_hint}
输出JSON数组: [{{"chapter":{ch_num},"title":"章节标题(10字)","summary":"具体情节(80字)"}}]
禁止"待规划"。每章必须有具体事件，标题必须反映本章核心内容。"""
                                
                                gen_prompt = f"前文: {prev_context[:800]}\n类型: {meta['genre']}\n标题: {meta.get('title','')[:30]}\n概念: {meta.get('concept','')[:200]}\n还剩余{remaining}章完结。{concept_hint}"
                                resp = self.ai_client.chat(
                                    [{"role": "user", "content": gen_prompt}],
                                    system=gen_system, max_tokens=2000
                                )
                                if resp:
                                    m = re.search(r'\[[\s\S]*\]', resp)
                                    if m:
                                        try:
                                            # 修复常见JSON问题
                                            json_str = m.group()
                                            json_str = re.sub(r',\s*}', '}', json_str)
                                            json_str = re.sub(r',\s*]', ']', json_str)
                                            new_batch = json.loads(json_str)
                                        except json.JSONDecodeError:
                                            self._log(f"[大纲] JSON解析失败，跳过批量更新")
                                            new_batch = []
                                        
                                        if new_batch:
                                            with self._state_lock:
                                                for item in new_batch:
                                                    if not isinstance(item, dict) or "chapter" not in item:
                                                        continue
                                                    idx = item["chapter"] - 1
                                                    if idx < len(self.outline):
                                                        self.outline[idx]["title"] = item.get("title", f"第{item['chapter']}章")
                                                        self.outline[idx]["summary"] = item.get("summary", f"第{item['chapter']}章情节")
                                            # 保存已更新的 outline.json
                                            outline_file = self.current_novel_dir / "outline.json"
                                            with open(outline_file, 'w', encoding='utf-8') as f:
                                                json.dump(self.outline, f, indent=2, ensure_ascii=False)
                                        # 用新生成的大纲
                                        cur_item = next((x for x in new_batch if x["chapter"] == ch_num), None)
                                        if cur_item:
                                            chapter_title = cur_item.get("title", chapter_title)
                                            chapter_summary = cur_item.get("summary", chapter_summary)
                                            self._log(f"大纲已批量生成: 第{ch_num}章 {chapter_title}")
                                
                                if not chapter_summary or chapter_summary == "待规划":
                                    # 注入世界观和概念到大纲，让 AI 有明确创作方向
                                    concept_text = meta.get("concept", "")
                                    genre_text = meta.get("genre", "")
                                    chapter_summary = f"【{genre_text}】{concept_text[:150]}。第{ch_num}章：请基于世界观设定创作该章情节，保持风格一致。"
                            except Exception:
                                chapter_summary = f"第{ch_num}章，故事继续发展"
                        
                        # 超时重试3次
                        for attempt in range(3):
                            try:
                                content = self.agent.generate_chapter(
                                    ch_num,
                                    chapter_title,
                                    chapter_summary,
                                    word_count=meta.get("word_count_per_chapter", 6000),
                                    prev_context=prev_context
                                )
                                break
                            except Exception as te:
                                err_msg = str(te).lower()
                                # 认证错误不重试，立即抛出
                                if "401" in err_msg or "authorization" in err_msg:
                                    self._log(f"[错误] API认证失败 (401)，请检查API Key!")
                                    raise
                                # 超时判断（只匹配明确的超时错误）
                                is_timeout = any(kw in err_msg for kw in [
                                    "timeout", "timed out", "deadline exceeded",
                                    "request timed out", "connection timed out"
                                ])
                                if is_timeout and attempt < 2:
                                    wait_time = (attempt + 1) * 5  # 指数退避: 5s, 10s
                                    self._log(f"第{ch_num}章超时，重试{attempt+1}/3（等待{wait_time}秒）...")
                                    time.sleep(wait_time)
                                else:
                                    raise

                        # 🛡️ 原子写入章节（防止断电损坏）
                        chapter_file = chapters_dir / f"chapter_{ch_num:04d}.txt"
                        self._atomic_write(chapter_file, content)
                        
                        # 章节写入成功即为成功
                        generated += 1
                        batch_count += 1
                        
                        # 更新UI（第一章立即显示，之后每5章显示）
                        if generated == 1 or batch_count % 5 == 0 or ch_num == total:
                            self.root.after(0, lambda c=content, n=ch_num, t=chapter_info.get("title", ""): self._display_chapter(n, t, c))
                            self._log(f"第{ch_num}章创作完成 (进度: {generated}/{total-skipped}, 全书: {ch_num}/{display_total})")
                        else:
                            self._log(f"第{ch_num}章创作完成")
                        
                        # 后处理（单独try-except，不影响成功计数）
                        try:
                            # 定稿
                            self.agent.finalize_chapter(ch_num, content)
                            
                            # 自动检测决策点
                            self._auto_detect_decisions(ch_num, content)
                            
                            # 自动检测新角色
                            self._auto_detect_characters(ch_num, content)
                            
                            # 角色EXP奖励
                            self._award_chapter_exp(ch_num, content)
                            
                            # 名场面检测
                            if self.config.get("auto_detect_scene", True):
                                self._detect_and_prompt_image(content, ch_num)
                        except Exception as post_err:
                            self._log(f"[后处理] 第{ch_num}章部分后处理失败: {post_err}")
                        
                        # 每10章释放一次内存 + 保存快照
                        if generated % 10 == 0:
                            import gc
                            gc.collect()
                            # 🛡️ 定期保存内存快照（防止累积数据丢失）
                            self._save_checkpoint(ch_num, "snapshot")
                            self._log(f"[内存] 已释放内存+保存快照 (已完成{generated}章)")
                            
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        self._log(f"第{ch_num}章创作失败: {e}")
                        self._log(f"[DEBUG] Traceback:\n{tb[:500]}")
                        failed += 1
                        
                        # 认证错误立即停止整个批次
                        if "401" in str(e) or "Authorization" in str(e):
                            self._log(f"[错误] API认证失败，停止所有创作。请检查API Key设置。")
                            self._log(f"当前API配置: provider={self.config.get('api_provider')}, "
                                     f"base_url={self.config.get('api_base')}")
                            break
                        
                        continue
                
                # 更新进度显示 — 使用真实总章数
                completed = len(existing_chapters) + generated
                self.root.after(0, lambda c=completed, dt=display_total: self.chapter_var.set(f"{c}/{dt}"))
                
                summary = f"=== 自动创作完成 ===\n"
                summary += f"全书计划: {display_total} 章\n"
                summary += f"本次批次: {total} 章\n"
                if skipped > 0:
                    summary += f"跳过已完成: {skipped} 章\n"
                summary += f"本次生成: {generated} 章\n"
                if failed > 0:
                    summary += f"失败: {failed} 章\n"
                self._log(summary)
                
                # 🛡️ 清除检查点（生成完成）
                self._clear_checkpoint()
                
                if generated > 0:
                    self.root.after(0, lambda: messagebox.showinfo("完成", f"《{meta['title']}》创作完成！\n本次生成 {generated} 章"))
                elif skipped > 0:
                    self.root.after(0, lambda: messagebox.showinfo("提示", "所有章节已完成，无需继续创作"))
                    
            except Exception as e:
                self._log(f"自动创作失败: {e}")
            finally:
                self._auto_running = False
                self.root.after(0, lambda: self.auto_btn.config(state=tk.NORMAL, text="自动创作"))
        
        threading.Thread(target=run, daemon=True).start()
    def _chapter_review(self):
        """章节回顾 - AI生成最近章节摘要"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        meta = self._get_meta()
        total = meta.get('total_chapters', meta.get("chapter_count", 0)) or len(self.outline)
        if total == 0:
            messagebox.showwarning("提示", "还没有章节")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("章节回顾")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(700, sw - 60), int(sh * 0.7)
        x, y = (sw - w) // 2, (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text=f"📖《{meta.get('title', '小说')}》章节回顾",
                font=('微软雅黑', 12, 'bold'), bg=C['bg_dark'], fg=C['accent']).pack(pady=10)
        
        review_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                                                bg=C['bg_card'], fg=C['text_primary'],
                                                relief=tk.FLAT, padx=15, pady=15)
        review_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        # 读取最近5章摘要
        summaries = []
        for n in range(max(1, total - 4), total + 1):
            summary_file = self.current_novel_dir / "summaries" / f"chapter_{n:05d}_summary.txt"
            if summary_file.exists():
                summaries.append(summary_file.read_text(encoding='utf-8'))
        
        if summaries:
            review_text.insert("1.0", "\n\n---\n\n".join(summaries))
        else:
            review_text.insert("1.0", "暂无章节摘要，请先使用自动创作生成内容。")
        
        review_text.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="关闭", font=('微软雅黑', 10), padx=20,
                 bg=C['bg_light'], fg=C['text_primary'], command=dialog.destroy).pack(pady=10)
    def _extend_novel(self):
        """续写已完结的小说"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        existing = sorted([int(f.stem.split("_")[-1]) for f in chapters_dir.glob("chapter_*.txt")])
        if not existing:
            messagebox.showwarning("提示", "没有已生成的章节")
            return
        
        last_ch = existing[-1]
        meta = self._get_meta()
        
        ask = tk.Toplevel(self.root)
        ask.title("续写小说")
        ask.geometry("400x250")
        C = UIStyle.COLORS
        ask.configure(bg=C['bg_dark'])
        
        tk.Label(ask, text=f"从第{last_ch}章后续写", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=15)
        
        tk.Label(ask, text="新增章节数:", bg=C['bg_dark'], fg=C['text_primary']).pack()
        add_count = tk.StringVar(value="10")
        tk.Spinbox(ask, from_=1, to=500, textvariable=add_count, width=8,
                  font=('微软雅黑', 10), bg=C['bg_card']).pack(pady=5)
        
        def start():
            n = int(add_count.get())
            ask.destroy()
            
            def run():
                try:
                    self._auto_running = True
                    self._stop_flag = False
                    
                    # 读最后5章内容作为上下文
                    context_parts = []
                    for ch in existing[-5:]:
                        chf = chapters_dir / f"chapter_{ch:04d}.txt"
                        if chf.exists():
                            text = chf.read_text(encoding='utf-8')
                            context_parts.append(f"第{ch}章内容摘录: {text[:500]}")
                    context_text = "\n".join(context_parts)
                    
                    # 生成新的延续大纲
                    self._log(f"[续写] 基于第{last_ch}章结尾生成{n}章大纲...")
                    new_outline = self.agent.generate_outline_continuation(
                        meta.get("genre", "玄幻"), meta.get("title", ""), n,
                        context_text, current_count=last_ch
                    )
                    
                    # 更新总章数
                    total = last_ch + n
                    meta["chapter_count"] = total
                    meta["total_chapters"] = total  # 同步更新 total_chapters
                    with open(self.current_novel_dir / "meta.json", 'w', encoding='utf-8') as f:
                        json.dump(meta, f, indent=2, ensure_ascii=False)
                    
                    # 合并大纲
                    existing_outline = list(self.outline) if self.outline else []
                    # 修复新大纲的chapter编号
                    for i, o in enumerate(new_outline):
                        o["chapter"] = last_ch + i + 1
                    
                    # 写入 outline.json
                    full_outline = existing_outline + new_outline
                    with open(self.current_novel_dir / "outline.json", 'w', encoding='utf-8') as f:
                        json.dump(full_outline, f, indent=2, ensure_ascii=False)
                    self.outline = full_outline
                    self._refresh_outline_list()
                    
                    # 逐章生成
                    self._log(f"[续写] 开始创作{n}章...")
                    word_count = meta.get("word_count_per_chapter", 6000)
                    
                    for i, ch_info in enumerate(new_outline):
                        if self._stop_flag:
                            break
                        ch_num = last_ch + i + 1
                        
                        # 读前几章
                        prev_parts = []
                        for off in [1, 2, 3]:
                            pf = chapters_dir / f"chapter_{ch_num - off:04d}.txt"
                            if pf.exists():
                                t = pf.read_text(encoding='utf-8')
                                prev_parts.append(f"第{ch_num-off}章: {t[:600]}..." if len(t)>600 else t)
                        prev_ctx = "\n---\n".join(prev_parts)
                        
                        # 结尾收束：根据小说真实总章数判断
                        real_total = meta.get("total_chapters", meta.get("chapter_count", last_ch + len(new_outline)))
                        rem = real_total - last_ch - i - 1
                        if real_total > 100 and last_ch + i <= 10:
                            pass  # 长篇开头不提示完结
                        elif rem <= 3:
                            prev_ctx += f"\n\n【重要】只剩{rem+1}章完结。请收束故事。"
                        
                        # 注入整体大纲和故事大纲
                        outlines_ctx = self._get_outlines_context()
                        if outlines_ctx:
                            prev_ctx = outlines_ctx + "\n\n---\n\n" + prev_ctx
                        
                        # 注入世界观设定
                        world_ctx = self._get_world_context()
                        if world_ctx:
                            prev_ctx = world_ctx + "\n\n---\n\n" + prev_ctx
                        
                        content = self.agent.generate_chapter(
                            ch_num, ch_info.get("title", f"第{ch_num}章"),
                            ch_info.get("summary", ""), word_count, prev_context=prev_ctx
                        )
                        
                        ch_file = chapters_dir / f"chapter_{ch_num:04d}.txt"
                        ch_file.write_text(content, encoding='utf-8')
                        self.agent.finalize_chapter(ch_num, content)
                        self._auto_detect_characters(ch_num, content)
                        self._auto_detect_decisions(ch_num, content)
                        
                        # 角色EXP奖励
                        self._award_chapter_exp(ch_num, content)
                        
                        with self._state_lock:
                            self.current_chapter = ch_num
                        self.root.after(0, lambda c=content, n=ch_num, t=ch_info.get("title",""): 
                                       self._display_chapter(n, t, c))
                        self._log(f"[续写] 第{ch_num}章完成 ({len(content)}字)")
                    
                    self._log(f"[续写] 完成！共新增{len(new_outline)}章")
                    self.root.after(0, lambda: messagebox.showinfo("完成", f"续写完成！新增{len(new_outline)}章"))
                except Exception as e:
                    self._log(f"[续写] 失败: {e}")
                    self.root.after(0, lambda _exc=e: messagebox.showerror("失败", str(_exc)))
                finally:
                    self._auto_running = False
            
            threading.Thread(target=run, daemon=True).start()
        
        tk.Button(ask, text="开始续写", font=('微软雅黑', 10), padx=20,
                 bg=C['accent'], fg='white', command=start).pack(pady=10)
