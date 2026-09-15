"""大纲层：整体大纲/故事大纲读写、上下文注入、世界观、大纲条目增删改

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import tkinter as tk
from tkinter import messagebox

from app import UIStyle


class OutlineUIMixin:
    """大纲层：整体大纲/故事大纲读写、上下文注入、世界观、大纲条目增删改"""


    def _refresh_outline_list(self):
        """刷新大纲列表"""
        self.outline_list.delete(0, tk.END)
        outline_type = self.outline_type_var.get()

        if outline_type == "章节大纲":
            chapters = []
            for item in self.outline:
                ch = item.get("chapter", "?")
                title = item.get("title", "未命名")
                self.outline_list.insert(tk.END, f"第{ch}章: {title}")
                chapters.append(f"第{ch}章")

            # 更新章节选择器
            if hasattr(self, 'chapter_select'):
                self.chapter_select['values'] = chapters
                if chapters:
                    current = f"第{self.current_chapter}章" if self.current_chapter > 0 else chapters[0]
                    self.chapter_select_var.set(current)
        elif outline_type == "整体大纲":
            overall = self._get_overall_outline()
            if isinstance(overall, dict):
                # 单对象格式 → 显示为一项
                self.outline_list.insert(tk.END, f"1. {overall.get('title', '未命名')}")
            elif isinstance(overall, list):
                for i, item in enumerate(overall):
                    self.outline_list.insert(tk.END, f"{i+1}. {item.get('title', '未命名')}")
        elif outline_type == "故事大纲":
            stories = self._get_story_outlines()
            for name, story in stories.items():
                self.outline_list.insert(tk.END, f"📖 {name}")
    def _on_outline_type_change(self, event=None):
        """大纲类型切换"""
        self._refresh_outline_list()
    def _get_overall_outline(self) -> list:
        """获取整体大纲 — 自动标准化为列表"""
        if not self.current_novel_dir:
            return []
        outline_dir = self.current_novel_dir / "outlines"
        overall_file = outline_dir / "overall.json"
        if overall_file.exists():
            with open(overall_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 兼容单个对象的旧格式
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
        return []
    def _save_overall_outline(self, data):
        """保存整体大纲 — 自动标准化为列表格式"""
        if not self.current_novel_dir:
            return
        outline_dir = self.current_novel_dir / "outlines"
        outline_dir.mkdir(exist_ok=True)
        # 兼容：如果AI返回单个对象，包装为列表
        if isinstance(data, dict) and "title" in data:
            data = [data]
        with open(outline_dir / "overall.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    def _get_story_outlines(self) -> dict:
        """获取所有故事大纲"""
        if not self.current_novel_dir:
            return {}
        outline_dir = self.current_novel_dir / "outlines"
        stories_file = outline_dir / "stories.json"
        if stories_file.exists():
            with open(stories_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    def _save_story_outlines(self, data: dict):
        """保存故事大纲"""
        if not self.current_novel_dir:
            return
        outline_dir = self.current_novel_dir / "outlines"
        outline_dir.mkdir(exist_ok=True)
        with open(outline_dir / "stories.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    def _get_outlines_context(self) -> str:
        """获取整体大纲和故事大纲的上下文，用于注入章节生成"""
        parts = []
        overall = self._get_overall_outline()
        if overall:
            lines = []
            # 兼容dict和list两种格式
            if isinstance(overall, dict):
                # 单个对象 → 取title和description
                title = overall.get("title", "")
                desc = overall.get("description", overall.get("content", ""))[:120]
                lines.append(f"1. {title}：{desc}")
            elif isinstance(overall, list):
                for i, item in enumerate(overall[:15]):
                    title = item.get("title", "")
                    desc = item.get("description", item.get("content", ""))[:120]
                    lines.append(f"{i+1}. {title}：{desc}")
            if lines:
                parts.append("【整体大纲 - 全局创作指南】\n" + "\n".join(lines))

        stories = self._get_story_outlines()
        if stories:
            lines = []
            for name, story in list(stories.items())[:8]:
                summary = story.get("summary", story.get("content", ""))[:150]
                lines.append(f"故事线「{name}」：{summary}")
            if lines:
                parts.append("【故事大纲 - 多条故事线】\n" + "\n".join(lines))

        return "\n\n".join(parts) if parts else ""
    def _build_content_hint(self, adult: bool, edge: bool, genre: str) -> str:
        """构建18+/擦边内容提示词"""
        hints = []

        if adult:
            hints.append("""【🔞 18+成人内容模式 - 已启用】
本作品包含成人内容，请大胆创作：
- 亲密场景：可详细描写角色之间的亲密接触、情感交融、肌肤之亲、床戏
- 暴力战斗：战斗场景要残酷真实，可描写血腥、伤痛、生死搏杀
- 心理阴暗面：角色可以有复杂的道德灰度，展现人性的阴暗面
- 禁忌题材：可涉及禁忌关系、道德边缘、灰色地带
- 情感深度：情感描写要深入骨髓，展现欲望、执念、痴迷
- 残酷现实：可描写社会阴暗面、人性丑恶、生存挣扎
【重要】不要回避成人内容，这是创作需求，大胆发挥！""")

        if edge:
            hints.append("""【💋 擦边内容模式 - 已启用】
本作品允许擦边内容，在尺度边缘游走：
- 暧昧描写：角色之间的暧昧互动、暗示性对话、若有若无的身体接触
- 性感描写：可描写角色的性感魅力、身材曲线、诱人姿态
- 暗示性场景：可通过暗示、隐喻手法描写亲密场景，不直接描写但让读者遐想
- 情色张力：在情节中制造情色张力，让读者产生遐想
- 浴室/更衣等私密场景：可适当描写私密场景
- 醉酒/意外等擦边情节：可设计擦边桥段
【重要】擦边要擦到位，不要过于保守，让读者有想象空间！""")

        # 根据类型增强相关提示
        genre_lower = genre.lower() if genre else ""
        if any(kw in genre_lower for kw in ["言情", "romance", "恋爱", "婚恋", "总裁"]):
            hints.append("【类型增强】本作品为言情类型，情感线和亲密互动是核心卖点，请着重描写角色之间的情感纠葛和身体吸引力。")
        elif any(kw in genre_lower for kw in ["武侠", "仙侠", "玄幻", "修真"]):
            hints.append("【类型增强】本作品为武侠/仙侠类型，战斗场景要热血激烈，可描写修炼的痛苦与突破的快感。")
        elif any(kw in genre_lower for kw in ["悬疑", "恐怖", "灵异", "推理"]):
            hints.append("【类型增强】本作品为悬疑/恐怖类型，要营造紧张压抑的氛围，可描写血腥恐怖的场景。")
        elif any(kw in genre_lower for kw in ["末日", "apocalypse", "废土"]):
            hints.append("【类型增强】本作品为末日类型，要展现末世的残酷和人性的挣扎，可描写生存的艰难和道德的崩塌。")

        return "\n\n".join(hints) if hints else ""
    def _get_world_context(self) -> str:
        """获取世界观设定上下文，用于注入章节生成"""
        if not self.current_novel_dir:
            return ""
        settings_file = self.current_novel_dir / "memory" / "settings.json"
        if not settings_file.exists():
            return ""
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw = data.get("raw", json.dumps(data, ensure_ascii=False))
            # 清理markdown标记
            raw = raw.replace("```json", "").replace("```", "").strip()
            return f"【世界观设定 — 必须严格遵守以下设定进行创作】\n{raw[:3000]}"
        except Exception as e:
            self._log(f"读取世界观失败: {e}")
            return ""
    def _add_outline_item(self):
        """添加大纲项"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return

        outline_type = self.outline_type_var.get()

        dialog = tk.Toplevel(self.root)
        dialog.title(f"添加{outline_type}")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS

        tk.Label(dialog, text=f"添加{outline_type}", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))

        # 标题输入
        title_frame = tk.Frame(dialog, bg=C['bg_dark'])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="标题:", bg=C['bg_dark'], fg=C['text_primary']).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'])
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 内容输入
        tk.Label(dialog, text="内容:", bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(10, 3))
        content_text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                              bg=C['bg_card'], fg=C['text_primary'], height=12)
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        def confirm():
            title = title_entry.get().strip()
            content = content_text.get("1.0", tk.END).strip()
            if not title:
                messagebox.showwarning("提示", "请输入标题")
                return

            if outline_type == "整体大纲":
                overall = self._get_overall_outline()
                overall.append({"title": title, "content": content})
                self._save_overall_outline(overall)
            elif outline_type == "故事大纲":
                stories = self._get_story_outlines()
                stories[title] = {"title": title, "content": content, "chapters": []}
                self._save_story_outlines(stories)
            elif outline_type == "章节大纲":
                ch_num = len(self.outline) + 1
                self.outline.append({"chapter": ch_num, "title": title, "summary": content})
                outline_file = self.current_novel_dir / "outline.json"
                with open(outline_file, 'w', encoding='utf-8') as f:
                    json.dump(self.outline, f, indent=2, ensure_ascii=False)

            self._refresh_outline_list()
            dialog.destroy()
            self._log(f"已添加{outline_type}: {title}")

        tk.Button(dialog, text="确认添加", command=confirm, bg=C['accent'], fg='white',
                 font=('微软雅黑', 10), padx=20, pady=5).pack(pady=10)
    def _edit_outline_item(self):
        """编辑大纲项"""
        selection = self.outline_list.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要编辑的大纲项")
            return

        idx = selection[0]
        outline_type = self.outline_type_var.get()

        # 获取当前内容
        if outline_type == "章节大纲":
            if idx < len(self.outline):
                item = self.outline[idx]
                title = item.get("title", "")
                content = item.get("summary", "")
            else:
                return
        elif outline_type == "整体大纲":
            overall = self._get_overall_outline()
            if idx < len(overall):
                item = overall[idx]
                title = item.get("title", "")
                content = item.get("description", item.get("content", ""))
            else:
                return
        elif outline_type == "故事大纲":
            stories = self._get_story_outlines()
            names = list(stories.keys())
            if idx < len(names):
                item = stories[names[idx]]
                title = item.get("title", "")
                content = item.get("summary", item.get("content", ""))
            else:
                return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑{outline_type}")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS

        tk.Label(dialog, text=f"编辑{outline_type}", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))

        # 标题输入
        title_frame = tk.Frame(dialog, bg=C['bg_dark'])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="标题:", bg=C['bg_dark'], fg=C['text_primary']).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'])
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        title_entry.insert(0, title)

        # 内容输入
        tk.Label(dialog, text="内容:", bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(10, 3))
        content_text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                              bg=C['bg_card'], fg=C['text_primary'], height=12)
        content_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        content_text.insert("1.0", content)

        def confirm():
            new_title = title_entry.get().strip()
            new_content = content_text.get("1.0", tk.END).strip()
            if not new_title:
                messagebox.showwarning("提示", "请输入标题")
                return

            if outline_type == "章节大纲":
                self.outline[idx]["title"] = new_title
                self.outline[idx]["summary"] = new_content
                outline_file = self.current_novel_dir / "outline.json"
                with open(outline_file, 'w', encoding='utf-8') as f:
                    json.dump(self.outline, f, indent=2, ensure_ascii=False)
            elif outline_type == "整体大纲":
                overall = self._get_overall_outline()
                overall[idx] = {"title": new_title, "description": new_content, "chapter_range": overall[idx].get("chapter_range", "")}
                self._save_overall_outline(overall)
            elif outline_type == "故事大纲":
                stories = self._get_story_outlines()
                names = list(stories.keys())
                old_name = names[idx]
                old_story = stories.get(old_name, {})
                del stories[old_name]
                stories[new_title] = {
                    "title": new_title,
                    "summary": new_content,
                    "key_events": old_story.get("key_events", [])
                }
                self._save_story_outlines(stories)

            self._refresh_outline_list()
            dialog.destroy()
            self._log(f"已更新{outline_type}: {new_title}")

        tk.Button(dialog, text="确认修改", command=confirm, bg=C['accent'], fg='white',
                 font=('微软雅黑', 10), padx=20, pady=5).pack(pady=10)
    def _delete_outline_item(self):
        """删除大纲项"""
        selection = self.outline_list.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的大纲项")
            return

        idx = selection[0]
        outline_type = self.outline_type_var.get()

        if not messagebox.askyesno("确认", f"确定要删除这个{outline_type}吗？"):
            return

        if outline_type == "章节大纲":
            if idx < len(self.outline):
                removed = self.outline.pop(idx)
                # 重新编号
                for i, item in enumerate(self.outline):
                    item["chapter"] = i + 1
                outline_file = self.current_novel_dir / "outline.json"
                with open(outline_file, 'w', encoding='utf-8') as f:
                    json.dump(self.outline, f, indent=2, ensure_ascii=False)
                self._log(f"已删除: {removed.get('title', '')}")
        elif outline_type == "整体大纲":
            overall = self._get_overall_outline()
            if idx < len(overall):
                removed = overall.pop(idx)
                self._save_overall_outline(overall)
                self._log(f"已删除: {removed.get('title', '')}")
        elif outline_type == "故事大纲":
            stories = self._get_story_outlines()
            names = list(stories.keys())
            if idx < len(names):
                removed_name = names[idx]
                del stories[removed_name]
                self._save_story_outlines(stories)
                self._log(f"已删除: {removed_name}")

        self._refresh_outline_list()
    def _on_outline_select(self, event):
        """大纲选中事件"""
        if not self.current_novel_dir:
            return

        selection = self.outline_list.curselection()
        if not selection:
            return

        idx = selection[0]
        outline_type = self.outline_type_var.get() if hasattr(self, 'outline_type_var') else "章节大纲"

        if outline_type == "整体大纲":
            overall = self._get_overall_outline()
            items = [overall] if isinstance(overall, dict) else overall
            if 0 <= idx < len(items):
                item = items[idx]
                self.content_text.delete("1.0", tk.END)
                lines = [
                    f"标题: {item.get('title', '未命名')}",
                    f"描述: {item.get('description', item.get('content', '暂无'))}",
                    f"章节范围: {item.get('chapter_range', '全文')}",
                ]
                self.content_text.insert("1.0", "\n\n".join(lines))
                self.chapter_title_var.set(f"整体大纲: {item.get('title', '')}")
        elif outline_type == "故事大纲":
            stories = self._get_story_outlines()
            story_list = list(stories.items())
            if 0 <= idx < len(story_list):
                name, story = story_list[idx]
                self.content_text.delete("1.0", tk.END)
                events = story.get("key_events", [])
                lines = [
                    f"故事线: {name}",
                    f"标题: {story.get('title', '未知')}",
                    f"概要: {story.get('summary', story.get('content', '暂无'))}",
                    f"关键事件: {', '.join(events) if events else '暂无'}",
                ]
                self.content_text.insert("1.0", "\n\n".join(lines))
                self.chapter_title_var.set(f"故事大纲: {name}")
        elif self.outline:
            # 章节大纲
            if idx < len(self.outline):
                chapter_info = self.outline[idx]
                self.current_chapter = idx + 1

                chapters_dir = self.current_novel_dir / "chapters"
                chapter_file = chapters_dir / f"chapter_{self.current_chapter:04d}.txt"

                if chapter_file.exists():
                    content = chapter_file.read_text(encoding='utf-8')
                    self.content_text.delete("1.0", tk.END)
                    self.content_text.insert("1.0", content)
                    self.chapter_title_var.set(f"第{self.current_chapter}章: {chapter_info.get('title', '')}")
                    self.word_count_var.set(f"字数: {len(content)}")
                    self._log(f"已加载第{self.current_chapter}章，可编辑后按 Ctrl+S 保存")
                else:
                    self.chapter_title_var.set(f"第{self.current_chapter}章: {chapter_info.get('title', '')} (未生成)")
                    self.content_text.delete("1.0", tk.END)
                    self.content_text.insert("1.0", f"章节大纲：\n{chapter_info.get('summary', '无')}\n\n在此处编写内容...")

                total = len(self.outline)
                display_total = self._get_meta().get("total_chapters", total)
                self.chapter_var.set(f"{self.current_chapter}/{display_total}")
