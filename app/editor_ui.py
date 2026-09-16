"""编辑器层：正文编辑、右键菜单、AI 改写/润色/全屏写作

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import threading
import time
import tkinter as tk
from tkinter import messagebox

from app import FullscreenWriter, SceneDetector, UIStyle


class EditorUIMixin:
    """编辑器层：正文编辑、右键菜单、AI 改写/润色/全屏写作"""

    def _on_text_change(self, event=None):
        """文本变化事件 - 更新字数统计"""
        try:
            content = self.content_text.get("1.0", tk.END).strip()
            self.word_count_var.set(str(len(content)))
            self.is_modified = True
        except tk.TclError:
            pass  # 窗口关闭中的事件忽略

    def _show_editor_context_menu(self, event):
        """编辑器右键菜单 - 用选中文字跳转到创作工具"""
        menu = tk.Menu(self.root, tearoff=0, bg=UIStyle.COLORS["bg_card"], fg=UIStyle.COLORS["text_primary"])

        try:
            selected = self.content_text.selection_get()
        except tk.TclError:
            selected = ""

        if not selected.strip():
            selected = self.content_text.get("1.0", tk.END).strip()[:500]
            menu.add_command(label="使用全文内容", state=tk.DISABLED)
        else:
            menu.add_command(label=f"已选中 {len(selected)} 字", state=tk.DISABLED)

        menu.add_separator()
        menu.add_command(label="事物描写库", command=lambda: self._open_tool_with_text("description", selected))
        menu.add_command(label="角色桥段库", command=lambda: self._open_tool_with_text("bridge", selected))
        menu.add_command(label="情景对话推演", command=lambda: self._open_tool_with_text("dialogue", selected))
        menu.add_command(label="用选中内容仿写", command=lambda: self._style_imitation_with_text(selected))
        menu.add_command(label="生成图片提示词", command=lambda: self._gen_prompt_from_text(selected))

        menu.post(event.x_root, event.y_root)

    def _open_tool_with_text(self, tool_type: str, text: str):
        """用选中文字跳转到创作工具"""
        self._selected_context_text = text
        tab_mapping = {"description": " 创作工具 ", "bridge": " 创作工具 ", "dialogue": " 创作工具 "}
        tab_name = tab_mapping.get(tool_type, " 创作工具 ")

        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == tab_name:
                self.notebook.select(i)
                break

        self._log(f"已跳转到 {tab_name.strip()}，选中 {len(text)} 字作为上下文")
        messagebox.showinfo("已跳转", f"已选中 {len(text)} 字内容\n请在「创作工具」标签页使用对应功能")

    def _style_imitation_with_text(self, text: str):
        """用选中文字进行仿写"""
        self._selected_context_text = text
        self._log(f"已获取选中内容作为仿写参考 ({len(text)}字)")
        self._style_imitation()

    def _gen_prompt_from_text(self, text: str):
        """从选中文字生成图片提示词"""
        if not self.current_novel_dir:
            messagebox.showinfo("提示", "请先打开小说")
            return
        scenes = SceneDetector.detect(text)
        if not scenes:
            messagebox.showinfo("提示", "未检测到适合生成图片的场景")
            return
        img_dir = self.current_novel_dir / "scene_prompts"
        img_dir.mkdir(exist_ok=True)
        ts = int(time.time())
        for i, scene in enumerate(scenes):
            f = img_dir / f"manual_{ts}_{i + 1}_prompt.txt"
            f.write_text(f"场景: {scene.get('text', '')[:200]}\n\n提示词:\n{scene.get('prompt', '')}", encoding="utf-8")
        self._log(f"已保存 {len(scenes)} 个手动提示词到 scene_prompts/")
        messagebox.showinfo("成功", f"已生成 {len(scenes)} 个提示词\n保存到 scene_prompts/")

    def _display_optimized(self, content):
        """显示优化后的内容"""
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", content)
        self.word_count_var.set(f"字数: {len(content)}")
        self._log("优化内容已加载到编辑器，请审阅后保存")

    def _display_generated(self, content):
        """显示生成的内容"""
        dialog = tk.Toplevel(self.root)
        dialog.title("仿写结果")
        dialog.geometry("700x500")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="仿写结果", font=("微软雅黑", 12, "bold"), bg=C["bg_dark"], fg=C["accent_light"]).pack(
            pady=(10, 5)
        )

        result_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 11), bg=C["bg_card"], fg=C["text_primary"], padx=15, pady=15
        )
        result_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        result_text.insert("1.0", content)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def insert_to_editor():
            self.content_text.insert(tk.INSERT, "\n\n" + content)
            dialog.destroy()
            self._log("仿写内容已插入编辑器")

        def replace_editor():
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", content)
            self.word_count_var.set(f"字数: {len(content)}")
            dialog.destroy()
            self._log("仿写内容已替换编辑器内容")

        tk.Button(
            btn_frame,
            text="插入到编辑器",
            command=insert_to_editor,
            bg=C["accent"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="替换编辑器内容",
            command=replace_editor,
            bg=C["warning"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="关闭",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)

    def _open_fullscreen_writer(self):
        """打开全屏写作模式 - 与自动写作共享上下文"""
        # 获取当前章节内容
        current_text = self.content_text.get("1.0", tk.END).strip()

        # 构建共享上下文（世界观、角色、大纲等）
        shared_context = ""
        if self.memory:
            settings = self.memory.get_settings()
            if settings:
                shared_context += f"世界观: {json.dumps(settings, ensure_ascii=False)[:500]}\n"
            characters = self.memory.get_characters()
            if characters:
                shared_context += f"角色: {json.dumps(characters, ensure_ascii=False)[:500]}\n"
            global_summary = self.memory.get_global_summary()
            if global_summary:
                shared_context += f"故事进展: {global_summary[:300]}\n"

        # 如果有大纲，添加当前章节大纲
        if self.outline and self.current_chapter > 0 and self.current_chapter <= len(self.outline):
            ch_info = self.outline[self.current_chapter - 1]
            shared_context += f"当前章节大纲: {ch_info.get('summary', '')}\n"

        # 注入整体大纲和故事大纲
        outlines_ctx = self._get_outlines_context()
        if outlines_ctx:
            shared_context += f"\n{outlines_ctx}\n"

        # 注入世界观设定
        world_ctx = self._get_world_context()
        if world_ctx:
            shared_context += f"\n{world_ctx}\n"

        # 🔒 注入主角名锁定
        if self.current_novel_dir:
            meta_file = self.current_novel_dir / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        _meta = json.load(f)
                    _protagonist = _meta.get("protagonist", "")
                    if _protagonist:
                        shared_context += f"\n【重要·主角锁定】本小说主角名为「{_protagonist}」。所有创作必须以「{_protagonist}」为主角，禁止更换！"
                except Exception:
                    pass

        def save_callback(content):
            # 保存到当前章节
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", content)
            self.word_count_var.set(str(len(content)))
            self._save_chapter()

            # 自动更新记忆
            if self.memory and self.agent:
                with self._state_lock:
                    ch_num = self.current_chapter
                threading.Thread(target=lambda: self.agent.finalize_chapter(ch_num, content), daemon=True).start()
                self._log("[联动] 全屏写作内容已保存并更新记忆")

            # 角色EXP奖励（异步分析，不阻塞UI）
            with self._state_lock:
                ch_num = self.current_chapter
            threading.Thread(target=lambda: self._award_chapter_exp(ch_num, content), daemon=True).start()

        FullscreenWriter(
            parent=self.root,
            ai_client=self.ai_client,
            config=self.config,
            initial_text=current_text,
            save_callback=save_callback,
            shared_context=shared_context,  # 传递共享上下文
        )
