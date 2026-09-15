"""工具层：工具面板刷新、格式转换、插图/封面、云同步

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from app import SceneDetector, UIStyle
from format_converter import FormatConverter, ImageManager


class ToolkitUIMixin:
    """工具层：工具面板刷新、格式转换、插图/封面、云同步"""


    def _refresh_toolkit(self):
        """刷新工具集界面"""
        for w in self.tool_content_frame.winfo_children():
            w.destroy()
        
        tool_type = self.tool_type_var.get()
        
        if tool_type == "elements":
            self._build_elements_tool()
        elif tool_type == "bridges":
            self._build_bridges_tool()
        elif tool_type == "descriptions":
            self._build_descriptions_tool()
        elif tool_type == "dialogue":
            self._build_dialogue_tool()
        elif tool_type == "story_flow":
            self._build_story_flow_tool()
        elif tool_type == "style":
            self._build_style_tool()
        elif tool_type == "adapt":
            self._build_adapt_tool()
        elif tool_type == "websearch":
            self._build_websearch_tool()
        elif tool_type == "chapters":
            self._build_chapter_analysis_tool()
        elif tool_type == "memory_viz":
            self._build_memory_viz_tool()
        elif tool_type == "summary_mgmt":
            self._build_summary_mgmt_tool()
        elif tool_type == "batch_ops":
            self._build_batch_ops_tool()
    def _show_tool_result(self, widget, text):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
    def _insert_to_chapter(self, text_widget):
        """将工具结果智能插入到当前章节（AI润色衔接）"""
        content = text_widget.get("1.0", tk.END).strip()
        if not content:
            return
        
        # 获取当前章节内容作为上下文
        current_text = self.content_text.get("1.0", tk.END).strip()
        
        if not self.ai_client.is_configured():
            # 无AI配置时直接插入
            self.content_text.insert(tk.INSERT, "\n\n" + content)
            self._log("内容已直接插入（未配置AI润色）")
            return
        
        # 使用AI润色使内容衔接更自然
        def run():
            try:
                self._log("正在AI润色插入内容...")
                
                # 获取当前章节上下文（取最后500字作为衔接参考）
                context = current_text[-500:] if len(current_text) > 500 else current_text
                
                system = """你是专业小说编辑。任务是将新内容自然地融入现有文章中。
要求：
1. 保持原文风格和语气
2. 添加自然的过渡语句
3. 确保上下文逻辑连贯
4. 不要重复已有内容
5. 直接输出修改后的内容，不要添加解释"""
                
                prompt = f"""现有文章（末尾部分）：
---
{context}
---

需要插入的新内容：
---
{content}
---

请将新内容自然地融入到现有文章末尾，确保衔接流畅。"""
                
                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=2000)
                
                # 在主线程中插入润色后的内容
                self.root.after(0, lambda: self._insert_polished_content(result))
                self._log("AI润色完成，内容已插入")
                
            except Exception as e:
                # 润色失败时直接插入原内容
                self.root.after(0, lambda: self.content_text.insert(tk.INSERT, "\n\n" + content))
                self._log(f"AI润色失败，直接插入原内容: {e}")
        
        threading.Thread(target=run, daemon=True).start()
    def _insert_polished_content(self, content):
        """插入润色后的内容"""
        self.content_text.insert(tk.INSERT, "\n\n" + content)
        # 更新字数统计
        full_text = self.content_text.get("1.0", tk.END).strip()
        self.word_count_var.set(f"字数: {len(full_text)}")
    def _display_review(self, review_json: str):
        """显示审校结果（主线程调用）"""
        self.review_text.delete("1.0", tk.END)
        self.review_text.insert("1.0", review_json)
        self.notebook.select(2)
    def _generate_cover(self):
        """AI生成小说封面"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        meta = self._get_meta()
        title = meta.get("title", "未命名")
        genre = meta.get("genre", "玄幻")
        concept = meta.get("concept", "")
        
        # 读取一些章节内容获取风格参考
        content_sample = ""
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))[:3]
        for cf in chapter_files:
            content_sample += cf.read_text(encoding='utf-8')[:500] + "\n"
        
        def run():
            try:
                self._log("[封面] 正在生成封面提示词...")
                prompt = self.ai_client.chat(
                    [{"role": "user", "content": f"书名：{title}\n类型：{genre}\n概念：{concept}\n内容片段：{content_sample[:1000]}\n\n请为这本小说生成一个精美的封面AI绘图提示词(英文，适合Midjourney/Stable Diffusion)，包含风格描述、画面构图、色彩方案、氛围。"}],
                    system="你是专业封面设计师。生成AI绘图提示词。只输出英文提示词。",
                    max_tokens=1500
                )
                
                # 保存封面提示词
                cover_dir = self.current_novel_dir / "cover"
                cover_dir.mkdir(exist_ok=True)
                cover_file = cover_dir / "cover_prompt.txt"
                cover_content = f"书名: {title}\n类型: {genre}\n\n封面AI提示词:\n{prompt}"
                cover_file.write_text(cover_content, encoding='utf-8')
                
                # 生成简单HTML封面预览
                html = self._build_cover_html(title, genre, meta.get("tags", []), concept)
                (cover_dir / "cover_preview.html").write_text(html, encoding='utf-8')
                
                self._log(f"[封面] 已保存到 cover/ 目录")
                self.root.after(0, lambda: messagebox.showinfo("完成", 
                    f"封面已生成:\n- 提示词: cover/cover_prompt.txt\n- 预览: cover/cover_preview.html\n\n将提示词复制到Midjourney/SD即可生成封面图"))
            except Exception as e:
                self._log(f"[封面] 失败: {e}")
                self.root.after(0, lambda _exc=e: messagebox.showerror("失败", str(_exc)))
        
        threading.Thread(target=run, daemon=True).start()
    def _build_cover_html(self, title, genre, tags, concept):
        """生成简单封面HTML预览"""
        colors = {"玄幻": ("#1a1a2e", "#e94560"), "都市": ("#2d3436", "#00b894"),
                  "科幻": ("#0a0a23", "#00d2ff"), "悬疑": ("#1a1a1a", "#c0392b"),
                  "言情": ("#2d1810", "#e74c3c"), "历史": ("#3e2723", "#ffb300"),
                  "游戏": ("#1b2838", "#66c0f4")}
        bg, accent = colors.get(genre, ("#1a1a2e", "#e94560"))
        tag_str = " · ".join(tags[:3]) if tags else genre
        concept_str = concept[:100] if concept else "AI智能创造的故事"
        
        return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>
<style>\nbody{{margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:{bg}}}
.cover{{width:300px;height:450px;background:linear-gradient(135deg,{bg},{accent}33);border:2px solid {accent};border-radius:12px;text-align:center;padding:40px 20px;color:white;font-family:sans-serif;}}
h1{{font-size:24px;margin:20px 0;color:{accent};}}p{{font-size:12px;opacity:0.7;margin:5px 0;}}
.line{{width:80px;height:2px;background:{accent};margin:20px auto;}}</style></head><body>
<div class=cover><div class=line></div><h1>{title}</h1><p>{tag_str}</p><div class=line></div><p>{concept_str}</p><p style=margin-top:30px;font-size:10px>AI NovelWriter</p></div></body></html>'''
    def _show_format_converter(self):
        """显示格式转换对话框"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        if not self.format_converter:
            self.format_converter = FormatConverter(self.current_novel_dir)
        
        dialog = tk.Toplevel(self.root)
        dialog.title("格式转换")
        dialog.geometry("450x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择导出格式:", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))
        
        # 格式列表
        formats = self.format_converter.get_formats()
        format_var = tk.StringVar(value="html")
        
        for fmt_key, fmt_info in formats.items():
            frame = tk.Frame(dialog, bg=C['bg_dark'])
            frame.pack(fill=tk.X, padx=20, pady=3)
            
            tk.Radiobutton(frame, text=f"{fmt_info['name']} ({fmt_info['ext']})", 
                          variable=format_var, value=fmt_key,
                          font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                          selectcolor=C['accent']).pack(side=tk.LEFT)
            tk.Label(frame, text=fmt_info['desc'], font=('微软雅黑', 8),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(side=tk.RIGHT)
        
        # 包含图片选项
        include_images_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dialog, text="包含插图（如有）", variable=include_images_var,
                      font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                      selectcolor=C['accent']).pack(pady=10)
        
        def do_convert():
            fmt = format_var.get()
            
            # 收集所有章节
            chapters_dir = self.current_novel_dir / "chapters"
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            chapters = []
            
            for cf in chapter_files:
                num = int(cf.stem.split("_")[1])
                content = cf.read_text(encoding='utf-8')
                # 从大纲获取标题
                title = f"第{num}章"
                if self.outline and num <= len(self.outline):
                    title = self.outline[num-1].get("title", title)
                chapters.append({"num": num, "title": title, "content": content})
            
            if not chapters:
                # 如果没有章节文件，使用编辑区内容
                content = self.content_text.get("1.0", tk.END).strip()
                if not content:
                    messagebox.showwarning("提示", "没有可导出的内容")
                    return
            else:
                content = "\n\n".join(ch["content"] for ch in chapters)
            
            meta = self._get_meta() if self.current_novel_dir else {}
            
            # 获取图片数据
            images = None
            if include_images_var.get() and self.image_manager:
                images = self.image_manager.get_images_data()
            
            # 转换
            result = self.format_converter.convert(
                content=content,
                title=meta.get("title", "小说"),
                format_type=fmt,
                chapters=chapters if chapters else None,
                metadata=meta,
                images=images,
            )
            
            if result:
                self._log(f"格式转换完成: {result}")
                dialog.destroy()
                
                # 询问是否打开
                if messagebox.askyesno("成功", f"已导出为{formats[fmt]['name']}格式\n\n{result}\n\n是否打开文件？"):
                    # 使用 os.startfile 安全打开文件（不经过 shell，避免命令注入）
                    import os
                    try:
                        os.startfile(result)
                    except Exception as e:
                        self._log(f"打开文件失败: {e}")
                        messagebox.showinfo("提示", f"文件已保存到：\n{result}")
            else:
                messagebox.showerror("错误", "格式转换失败")
        
        tk.Button(dialog, text="开始转换", font=('微软雅黑', 11, 'bold'),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=20, pady=8,
                 command=do_convert).pack(pady=15)
    def _insert_image(self):
        """插入图片到编辑区"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        if not self.image_manager:
            self.image_manager = ImageManager(self.current_novel_dir)
        
        # 选择图片文件
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("所有文件", "*.*"),
            ]
        )
        
        if not file_path:
            return
        
        # 导入图片
        img_path = self.image_manager.import_image(file_path)
        if not img_path:
            messagebox.showerror("错误", "导入图片失败")
            return
        
        # 在编辑区插入图片标记
        cursor_pos = self.content_text.index(tk.INSERT)
        img_name = Path(img_path).name
        
        # 插入Markdown格式的图片标记
        marker = f"\n![插图]({img_name})\n"
        self.content_text.insert(tk.INSERT, marker)
        
        # 尝试在Text widget中显示图片预览
        try:
            from PIL import Image, ImageTk
            img = Image.open(img_path)
            # 缩放图片
            max_width = 400
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            
            # 转换为Tkinter可用的格式
            photo = ImageTk.PhotoImage(img)
            
            # 先获取当前内容（不含标记）
            current = self.content_text.get("1.0", tk.END)
            current = current.replace(f"\n![插图]({img_name})\n", "")
            
            # 清空并重新插入内容
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", current)
            
            # 在Text widget中插入图片预览
            self.content_text.image_create(tk.INSERT, image=photo)
            self.content_text.insert(tk.INSERT, "\n")
            
            # 保持引用防止被垃圾回收
            if not hasattr(self, '_photo_refs'):
                self._photo_refs = []
            self._photo_refs.append(photo)
            
        except ImportError:
            # 如果没有PIL，只保留文本标记（已插入）
            pass
        except Exception as e:
            self._log(f"图片预览加载失败: {e}")
        
        self._log(f"已插入图片: {img_name}")
        
        # 更新字数
        content = self.content_text.get("1.0", tk.END).strip()
        self.word_count_var.set(str(len(content)))
    def _detect_and_prompt_image(self, content: str, chapter_num: int):
        """检测名场面 - 只保留质量最高的2个"""
        all_scenes = SceneDetector.detect(content)
        if not all_scenes:
            return
        
        # 只取质量最高的前2个名场面，减少垃圾
        scored_scenes = []
        for s in all_scenes:
            text_len = len(s.get("text", ""))
            prompt_len = len(s.get("prompt", ""))
            # 评分：场景描述越长>越具体；提示词越长>越详细
            score = (text_len * 0.3 + prompt_len * 0.7) if prompt_len > 50 else 0
            scored_scenes.append((score, s))
        
        scored_scenes.sort(key=lambda x: x[0], reverse=True)
        scenes = [s for score, s in scored_scenes[:2] if score > 30]  # 质量阈值
        
        if not scenes:
            return
        
        self._log(f"[名场面] 第{chapter_num}章 检测到{len(scenes)}个高质量场景")
        
        img_dir = self.current_novel_dir / "scene_prompts"
        img_dir.mkdir(exist_ok=True)
        
        scene_type_cn = {
            "battle": "战斗场面", "beauty": "人物特写", "emotion": "情感场景",
            "epic_scene": "震撼场面", "character_closeup": "角色特写",
            "landscape": "风景全景", "confrontation": "对峙场面", "sacrifice": "牺牲时刻"
        }
        
        for i, scene in enumerate(scenes):
            type_name = scene_type_cn.get(scene["type"], "名场面")
            prompt_text = scene.get("prompt", "")
            scene_text = scene.get("text", "")[:300]
            aspect_ratio = scene.get("aspect_ratio", "16:9")
            size = scene.get("size", "1024x576")
            shot_type = scene.get("shot_type", "")
            composition = scene.get("composition", "")
            style = scene.get("style", "")
            characters_in = scene.get("characters", [])
            
            # 包含人物描写
            char_desc = ""
            if characters_in:
                char_desc = "人物: " + ", ".join(str(c) for c in characters_in[:5])
            
            prompt_file = img_dir / f"ch{chapter_num:04d}_{scene['type']}_{i+1}_prompt.txt"
            prompt_content = (
                f"章节: 第{chapter_num}章\n"
                f"类型: {type_name}\n"
                f"场景: {scene_text}\n"
                f"{char_desc}\n\n"
                f"画面比例: {aspect_ratio} ({size})\n"
                f"镜头: {shot_type}\n"
                f"构图: {composition}\n"
                f"质感: {style}\n\n"
                f"AI提示词:\n{prompt_text}"
            )
            prompt_file.write_text(prompt_content, encoding='utf-8')
            self._log(f"[提示词] 已保存: {prompt_file.name}")
            
            purpose_text = {
                "battle": "增强战斗场面的视觉冲击力",
                "beauty": "展现角色外形特征和精神面貌",
                "emotion": "捕捉情感高潮，增强读者代入",
                "epic_scene": "渲染宏大世界观和场景氛围",
                "character_closeup": "刻画角色细节表情",
                "landscape": "展示世界观和环境氛围",
                "confrontation": "表现角色对峙的张力",
                "sacrifice": "定格感动人心的瞬间",
            }.get(scene["type"], "可视化关键场景")
            
            # 保存提示词
            safe_type = scene["type"]
            prompt_file = img_dir / f"ch{chapter_num:04d}_{safe_type}_{i+1}_prompt.txt"
            prompt_content = (
                f"章节: 第{chapter_num}章\n"
                f"类型: {type_name}\n"
                f"场景: {scene_text}\n\n"
                f"画面比例: {aspect_ratio} ({size})\n"
                f"镜头: {shot_type}\n"
                f"构图: {composition}\n"
                f"质感: {style}\n\n"
                f"AI提示词:\n{prompt_text}"
            )
            prompt_file.write_text(prompt_content, encoding='utf-8')
            self._log(f"[提示词] 已保存: {prompt_file.name}")
    def _show_image_prompt_dialog(self, chapter_num, idx, type_name, scene_text, prompt_text, purpose_text, scene, img_dir):
        """显示电影级图片生成提醒对话框"""
        C = UIStyle.COLORS
        dialog = tk.Toplevel(self.root)
        dialog.title(f"名场面插图 - 第{chapter_num}章")
        dialog.geometry("650x550")
        dialog.configure(bg=C['bg_dark'])
        dialog.grab_set()
        
        tk.Label(dialog, text=f"第{chapter_num}章 检测到【{type_name}】", font=('微软雅黑', 14, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(pady=(15, 5))
        
        # 电影级参数
        aspect_ratio = scene.get("aspect_ratio", "16:9")
        size = scene.get("size", "1024x576")
        shot_type = scene.get("shot_type", "")
        composition = scene.get("composition", "")
        style = scene.get("style", "")
        
        cinematic_frame = tk.Frame(dialog, bg=C['bg_card'])
        cinematic_frame.pack(fill=tk.X, padx=20, pady=5)
        
        cinematic_info = (
            f"画面比例: {aspect_ratio} ({size})  |  "
            f"镜头: {shot_type[:30]}...\n"
            f"构图: {composition[:30]}...  |  "
            f"质感: {style[:30]}..."
        )
        tk.Label(cinematic_frame, text=cinematic_info, font=('微软雅黑', 9),
                bg=C['bg_card'], fg=C['accent_light'], wraplength=600, justify=tk.LEFT).pack(padx=10, pady=5)
        
        info_frame = tk.Frame(dialog, bg=C['bg_card'])
        info_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(info_frame, text=f"场景: {scene_text}", font=('微软雅黑', 10),
                bg=C['bg_card'], fg=C['text_primary'], wraplength=600, justify=tk.LEFT).pack(padx=10, pady=5)
        
        # 说明为什么要生成图片
        tk.Label(dialog, text=f"推荐理由: {purpose_text}", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['warning'], wraplength=600).pack(padx=20, pady=5)
        
        # 倒计时 - 10秒
        timer_var = tk.StringVar(value="10秒后自动生成AI提示词")
        timer_label = tk.Label(dialog, textvariable=timer_var, font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['error'])
        timer_label.pack(pady=5)
        
        prompt_file = img_dir / f"ch{chapter_num:04d}_{scene['type']}_{idx+1}_prompt.txt"
        
        def start_countdown(remaining=10):
            """避免递归的倒计时"""
            def tick():
                nonlocal remaining
                if not dialog.winfo_exists():
                    return
                if remaining <= 0:
                    do_save_prompt()
                    return
                timer_var.set(f"{remaining}秒后自动生成AI提示词")
                remaining -= 1
                dialog.after(1000, tick)
            tick()
        
        def do_save_prompt():
            """保存AI提示词"""
            dialog.destroy()
            # 保存提示词到文件
            prompt_content = f"章节: 第{chapter_num}章\n类型: {type_name}\n场景: {scene_text}\n\nAI提示词:\n{prompt_text}"
            prompt_file.write_text(prompt_content, encoding='utf-8')
            self._log(f"[提示词] 已保存: {prompt_file.name}")
            self.root.after(0, lambda: messagebox.showinfo("已保存", f"AI提示词已保存到:\n{img_dir.name}/{prompt_file.name}"))
        
        def do_generate():
            """生成图片"""
            dialog.destroy()
            # 先保存提示词
            prompt_content = f"章节: 第{chapter_num}章\n类型: {type_name}\n场景: {scene_text}\n\nAI提示词:\n{prompt_text}"
            prompt_file.write_text(prompt_content, encoding='utf-8')
            self._log(f"[提示词] 已保存: {prompt_file.name}")
            
            def gen_img():
                self._log(f"[文生图] 正在生成: {type_name}...")
                img_data = self.image_gen.generate(
                    prompt=prompt_text,
                    negative_prompt="low quality, blurry, deformed, ugly",
                    width=self.config.get("img_width", 1024),
                    height=self.config.get("img_height", 1024),
                )
                if img_data:
                    filepath = self.image_gen.save_image(img_data, self.current_novel_dir,
                        f"chapter_{chapter_num:04d}_scene_{idx+1}")
                    self._log(f"插图已保存: {filepath}")
                    self.root.after(0, lambda: messagebox.showinfo("成功", f"插图已保存:\n{filepath}"))
            threading.Thread(target=gen_img, daemon=True).start()
        
        def do_skip():
            """跳过 - 仍然保存提示词"""
            do_save_prompt()
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(pady=15)
        
        # 如果有API才显示生成图片按钮
        if self.image_gen.is_configured():
            tk.Button(btn_frame, text="生成插图", command=do_generate,
                     bg=C['success'], fg='white', font=('微软雅黑', 10, 'bold'), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="仅保存提示词", command=do_save_prompt,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="跳过", command=do_skip,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 10), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        start_countdown()
    def _cloud_sync(self):
        """云端同步对话框"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("云端同步")
        dialog.geometry("400x300")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="云端同步", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))
        
        # 获取可用的云存储
        providers = self.cloud_storage.get_available_providers()
        configured = [p for p in providers if p.get("configured")]
        
        if not configured:
            tk.Label(dialog, text="未配置云存储\n\n请在 设置 → 云端存储 中配置",
                    font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
        else:
            provider_var = tk.StringVar(value=configured[0]["name"])
            for p in configured:
                tk.Radiobutton(dialog, text=p["name"], variable=provider_var, value=p["name"],
                              font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                              selectcolor=C['accent']).pack(anchor=tk.W, padx=30, pady=3)
            
            def do_upload():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:
                    def run():
                        try:
                            self._log(f"开始上传到 {provider_name}...")
                            success = self.cloud_storage.upload_novel(self.current_novel_dir, provider_id)
                            if success:
                                self._log(f"上传成功！")
                                self.root.after(0, lambda: messagebox.showinfo("成功", f"小说已上传到 {provider_name}"))
                            else:
                                self._log(f"上传失败")
                                self.root.after(0, lambda: messagebox.showerror("失败", f"上传失败，请检查网络和配置"))
                        except Exception as e:
                            self.root.after(0, lambda _exc=e: messagebox.showerror("错误", str(_exc)))
                    threading.Thread(target=run, daemon=True).start()
            
            def do_download():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:
                    def run():
                        try:
                            self._log(f"开始从 {provider_name} 下载...")
                            success = self.cloud_storage.download_novel("/AI_NovelWriter", self.current_novel_dir, provider_id)
                            if success:
                                self._log(f"下载成功！")
                                self.root.after(0, lambda: messagebox.showinfo("成功", f"小说已从 {provider_name} 下载"))
                            else:
                                self._log(f"下载失败")
                                self.root.after(0, lambda: messagebox.showerror("失败", f"下载失败"))
                        except Exception as e:
                            self.root.after(0, lambda _exc=e: messagebox.showerror("错误", str(_exc)))
                    threading.Thread(target=run, daemon=True).start()
            
            btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
            btn_frame.pack(fill=tk.X, padx=30, pady=15)
            
            tk.Button(btn_frame, text="上传到云端", font=('微软雅黑', 10),
                     bg=C['accent'], fg='white', relief=tk.FLAT, padx=15,
                     command=do_upload).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="从云端下载", font=('微软雅黑', 10),
                     bg=C['success'], fg='white', relief=tk.FLAT, padx=15,
                     command=do_download).pack(side=tk.LEFT, padx=5)
        
        tk.Button(dialog, text="关闭", font=('微软雅黑', 10),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=15,
                 command=dialog.destroy).pack(pady=10)
