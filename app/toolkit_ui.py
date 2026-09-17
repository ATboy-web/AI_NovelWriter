"""工具层：工具面板刷新、格式转换、插图/封面、云同步

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from loguru import logger

from app import SceneDetector, UIStyle, dialogs
from app.format_converter import FormatConverter, ImageManager
from app.panels import PanelHost
from app.panels import layout as panel_layout
from app.panels import registry as panel_registry


class ToolkitUIMixin:
    """工具层：工具面板刷新、格式转换、插图/封面、云同步"""

    def _init_panel_host(self, selector_parent):
        """建立面板宿主：加载注册表 → 渲染分组选择器 → **恢复上次布局**（v3 §2.2）。

        这一段替代了 v2 的两处硬编码：`shell_ui` 里手写的 12 个 Radiobutton，
        以及本文件里手写的 12 路 `if/elif`。两者表达的是同一份"有哪些面板"的信息，
        写在两个文件里必然漂移；现在都由 `app/panels/registry.py` 渲染。

        布局（单栏/分栏、两个栏各放谁、分隔条比例、哪些面板脱出为独立窗口）
        由 `app/panels/layout.py` 记忆到 `~/.ai_novel_writer/panel_layout.json`。
        宿主本身**不碰文件**，只通过 `on_layout_changed` 回调把状态交出来。
        """
        panel_registry.load_panels()
        self.panel_host = PanelHost(
            self,
            container=self.tool_content_frame,
            select_var=self.tool_type_var,
            selector_parent=selector_parent,
            bus=getattr(self, "event_bus", None),
            on_layout_changed=self._save_panel_layout,
        )
        self.panel_host.build_selector()
        # 先恢复记忆的布局；`apply_layout` 内部会按当前注册表洗一遍，
        # 因此面板改名/删除后不会出现"记忆了一个不存在的面板"。
        remembered = panel_layout.load()
        self.panel_host.apply_layout(remembered)
        self._log(
            f"面板注册表已加载：{len(panel_registry.PANEL_REGISTRY)} 个面板"
            f"（{len(panel_registry.categories())} 个分组）"
            f"；布局={'分栏' if self.panel_host.is_split() else '单栏'}"
        )
        self._record_panel_registry()

    def _save_panel_layout(self, layout) -> None:
        """把布局记忆到磁盘（由宿主在布局变化时回调）。

        ⚠️ 失败**不上报给用户**：布局是"锦上添花"的状态，写不进去也不该打断写作。
        """
        if not panel_layout.save(layout):
            logger.debug("面板布局未能落盘（不影响本次使用）")

    def _record_panel_registry(self):
        """把面板注册结果**同时写进磁盘诊断日志**。

        为什么需要它：`load_panels()` 对单个面板模块的导入失败是"记日志后跳过"，
        而打包成 windowed EXE 后**没有控制台**，那条日志就永远看不到 ——
        面板少了几块却毫无痕迹。落到 `~/.ai_novel_writer/diagnostic_logs/*.jsonl`
        之后，无论界面怎么显示，"这次到底注册了哪些面板"都能事后核对。
        """
        try:
            from app.diagnostic_logger import get_logger

            specs = panel_registry.all_panels()
            get_logger().log(
                "SYSTEM",
                "panel_registry",
                {
                    "total": len(specs),
                    "by_category": {
                        category: [spec.key for spec in group] for category, group in panel_registry.grouped()
                    },
                    "native": [spec.key for spec in specs if not spec.legacy],
                    "legacy": [spec.key for spec in specs if spec.legacy],
                    # 导入失败的模块（正常应为空）——这才是"面板少了几块"的可查证据
                    "load_failures": list(panel_registry.LOAD_FAILURES),
                },
            )
        except Exception as e:  # noqa: BLE001 - 诊断记录失败绝不能影响启动
            logger.debug(f"[toolkit_ui] 面板注册结果落日志失败（忽略）: {e}")

    def _refresh_toolkit(self):
        """重建当前工具面板。

        v3 P4：改由注册表 + `PanelHost` 驱动，原来的 12 路 `if/elif` 分发链已删除。
        保留此方法名是因为它被 `shell_ui` 与若干面板当作"刷新当前工具页"的入口。
        """
        host = getattr(self, "panel_host", None)
        if host is None:
            return
        host.refresh()

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
            dialogs.showwarning("提示", "请先打开小说")
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
            content_sample += cf.read_text(encoding="utf-8")[:500] + "\n"

        def run():
            try:
                self._log("[封面] 正在生成封面提示词...")
                prompt = self.ai_client.chat(
                    [
                        {
                            "role": "user",
                            "content": f"书名：{title}\n类型：{genre}\n概念：{concept}\n内容片段：{content_sample[:1000]}\n\n请为这本小说生成一个精美的封面AI绘图提示词(英文，适合Midjourney/Stable Diffusion)，包含风格描述、画面构图、色彩方案、氛围。",
                        }
                    ],
                    system="你是专业封面设计师。生成AI绘图提示词。只输出英文提示词。",
                    max_tokens=1500,
                )

                # 保存封面提示词
                cover_dir = self.current_novel_dir / "cover"
                cover_dir.mkdir(exist_ok=True)
                cover_file = cover_dir / "cover_prompt.txt"
                cover_content = f"书名: {title}\n类型: {genre}\n\n封面AI提示词:\n{prompt}"
                cover_file.write_text(cover_content, encoding="utf-8")

                # 生成简单HTML封面预览
                html = self._build_cover_html(title, genre, meta.get("tags", []), concept)
                (cover_dir / "cover_preview.html").write_text(html, encoding="utf-8")

                self._log("[封面] 已保存到 cover/ 目录")
                self.root.after(
                    0,
                    lambda: dialogs.showinfo(
                        "完成",
                        "封面已生成:\n- 提示词: cover/cover_prompt.txt\n- 预览: cover/cover_preview.html\n\n将提示词复制到Midjourney/SD即可生成封面图",
                    ),
                )
            except Exception as e:
                self._log(f"[封面] 失败: {e}")
                self.root.after(0, lambda _exc=e: dialogs.showerror("失败", str(_exc)))

        threading.Thread(target=run, daemon=True).start()

    def _build_cover_html(self, title, genre, tags, concept):
        """生成简单封面HTML预览"""
        colors = {
            "玄幻": ("#1a1a2e", "#e94560"),
            "都市": ("#2d3436", "#00b894"),
            "科幻": ("#0a0a23", "#00d2ff"),
            "悬疑": ("#1a1a1a", "#c0392b"),
            "言情": ("#2d1810", "#e74c3c"),
            "历史": ("#3e2723", "#ffb300"),
            "游戏": ("#1b2838", "#66c0f4"),
        }
        bg, accent = colors.get(genre, ("#1a1a2e", "#e94560"))
        tag_str = " · ".join(tags[:3]) if tags else genre
        concept_str = concept[:100] if concept else "AI智能创造的故事"

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>
<style>\nbody{{margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:{bg}}}
.cover{{width:300px;height:450px;background:linear-gradient(135deg,{bg},{accent}33);border:2px solid {accent};border-radius:12px;text-align:center;padding:40px 20px;color:white;font-family:sans-serif;}}
h1{{font-size:24px;margin:20px 0;color:{accent};}}p{{font-size:12px;opacity:0.7;margin:5px 0;}}
.line{{width:80px;height:2px;background:{accent};margin:20px auto;}}</style></head><body>
<div class=cover><div class=line></div><h1>{title}</h1><p>{tag_str}</p><div class=line></div><p>{concept_str}</p><p style=margin-top:30px;font-size:10px>AI NovelWriter</p></div></body></html>"""

    def _show_format_converter(self):
        """显示格式转换对话框"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先新建或打开小说")
            return

        if not self.format_converter:
            self.format_converter = FormatConverter(self.current_novel_dir)

        dialog = tk.Toplevel(self.root)
        dialog.title("格式转换")
        dialog.geometry("450x400")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="选择导出格式:", font=UIStyle.font("title"), bg=C["bg_dark"], fg=C["text_primary"]).pack(
            pady=(15, 10)
        )

        # 格式列表
        formats = self.format_converter.get_formats()
        format_var = tk.StringVar(value="html")

        for fmt_key, fmt_info in formats.items():
            frame = tk.Frame(dialog, bg=C["bg_dark"])
            frame.pack(fill=tk.X, padx=20, pady=3)

            tk.Radiobutton(
                frame,
                text=f"{fmt_info['name']} ({fmt_info['ext']})",
                variable=format_var,
                value=fmt_key,
                font=UIStyle.font("body"),
                bg=C["bg_dark"],
                fg=C["text_primary"],
                selectcolor=C["accent"],
            ).pack(side=tk.LEFT)
            tk.Label(
                frame, text=fmt_info["desc"], font=UIStyle.font("caption"), bg=C["bg_dark"], fg=C["text_muted"]
            ).pack(side=tk.RIGHT)

        # 包含图片选项
        include_images_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            dialog,
            text="包含插图（如有）",
            variable=include_images_var,
            font=UIStyle.font("body"),
            bg=C["bg_dark"],
            fg=C["text_primary"],
            selectcolor=C["accent"],
        ).pack(pady=10)

        def do_convert():
            fmt = format_var.get()

            # 收集所有章节
            chapters_dir = self.current_novel_dir / "chapters"
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            chapters = []

            for cf in chapter_files:
                num = int(cf.stem.split("_")[1])
                content = cf.read_text(encoding="utf-8")
                # 从大纲获取标题
                title = f"第{num}章"
                if self.outline and num <= len(self.outline):
                    title = self.outline[num - 1].get("title", title)
                chapters.append({"num": num, "title": title, "content": content})

            if not chapters:
                # 如果没有章节文件，使用编辑区内容
                content = self.content_text.get("1.0", tk.END).strip()
                if not content:
                    dialogs.showwarning("提示", "没有可导出的内容")
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
                if dialogs.askyesno("成功", f"已导出为{formats[fmt]['name']}格式\n\n{result}\n\n是否打开文件？"):
                    # 使用 os.startfile 安全打开文件（不经过 shell，避免命令注入）
                    import os

                    try:
                        os.startfile(result)
                    except Exception as e:
                        self._log(f"打开文件失败: {e}")
                        dialogs.showinfo("提示", f"文件已保存到：\n{result}")
            else:
                dialogs.showerror("错误", "格式转换失败")

        tk.Button(
            dialog,
            text="开始转换",
            font=UIStyle.font("subtitle_bold"),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            command=do_convert,
        ).pack(pady=15)

    def _insert_image(self):
        """插入图片到编辑区"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先新建或打开小说")
            return

        if not self.image_manager:
            self.image_manager = ImageManager(self.current_novel_dir)

        # 选择图片文件
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("所有文件", "*.*"),
            ],
        )

        if not file_path:
            return

        # 导入图片
        img_path = self.image_manager.import_image(file_path)
        if not img_path:
            dialogs.showerror("错误", "导入图片失败")
            return

        # 在编辑区插入图片标记
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
            if not hasattr(self, "_photo_refs"):
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
            "battle": "战斗场面",
            "beauty": "人物特写",
            "emotion": "情感场景",
            "epic_scene": "震撼场面",
            "character_closeup": "角色特写",
            "landscape": "风景全景",
            "confrontation": "对峙场面",
            "sacrifice": "牺牲时刻",
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

            prompt_file = img_dir / f"ch{chapter_num:04d}_{scene['type']}_{i + 1}_prompt.txt"
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
            prompt_file.write_text(prompt_content, encoding="utf-8")
            self._log(f"[提示词] 已保存: {prompt_file.name}")

    def _cloud_sync(self):
        """云端同步对话框"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先新建或打开小说")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("云端同步")
        dialog.geometry("400x300")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="云端同步", font=UIStyle.font("title"), bg=C["bg_dark"], fg=C["text_primary"]).pack(
            pady=(15, 10)
        )

        # 获取可用的云存储
        providers = self.cloud_storage.get_available_providers()
        configured = [p for p in providers if p.get("configured")]

        if not configured:
            tk.Label(
                dialog,
                text="未配置云存储\n\n请在 设置 → 云端存储 中配置",
                font=UIStyle.font("body"),
                bg=C["bg_dark"],
                fg=C["text_muted"],
            ).pack(pady=20)
        else:
            provider_var = tk.StringVar(value=configured[0]["name"])
            for p in configured:
                tk.Radiobutton(
                    dialog,
                    text=p["name"],
                    variable=provider_var,
                    value=p["name"],
                    font=UIStyle.font("body"),
                    bg=C["bg_dark"],
                    fg=C["text_primary"],
                    selectcolor=C["accent"],
                ).pack(anchor=tk.W, padx=30, pady=3)

            def do_upload():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:

                    def run():
                        try:
                            self._log(f"开始上传到 {provider_name}...")
                            success = self.cloud_storage.upload_novel(self.current_novel_dir, provider_id)
                            if success:
                                self._log("上传成功！")
                                self.root.after(0, lambda: dialogs.showinfo("成功", f"小说已上传到 {provider_name}"))
                            else:
                                self._log("上传失败")
                                self.root.after(0, lambda: dialogs.showerror("失败", "上传失败，请检查网络和配置"))
                        except Exception as e:
                            self.root.after(0, lambda _exc=e: dialogs.showerror("错误", str(_exc)))

                    threading.Thread(target=run, daemon=True).start()

            def do_download():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:

                    def run():
                        try:
                            self._log(f"开始从 {provider_name} 下载...")
                            success = self.cloud_storage.download_novel(
                                "/AI_NovelWriter", self.current_novel_dir, provider_id
                            )
                            if success:
                                self._log("下载成功！")
                                self.root.after(0, lambda: dialogs.showinfo("成功", f"小说已从 {provider_name} 下载"))
                            else:
                                self._log("下载失败")
                                self.root.after(0, lambda: dialogs.showerror("失败", "下载失败"))
                        except Exception as e:
                            self.root.after(0, lambda _exc=e: dialogs.showerror("错误", str(_exc)))

                    threading.Thread(target=run, daemon=True).start()

            btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
            btn_frame.pack(fill=tk.X, padx=30, pady=15)

            tk.Button(
                btn_frame,
                text="上传到云端",
                font=UIStyle.font("body"),
                bg=C["accent"],
                fg="white",
                relief=tk.FLAT,
                padx=15,
                command=do_upload,
            ).pack(side=tk.LEFT, padx=5)
            tk.Button(
                btn_frame,
                text="从云端下载",
                font=UIStyle.font("body"),
                bg=C["success"],
                fg="white",
                relief=tk.FLAT,
                padx=15,
                command=do_download,
            ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            dialog,
            text="关闭",
            font=UIStyle.font("body"),
            bg=C["bg_light"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=15,
            command=dialog.destroy,
        ).pack(pady=10)
