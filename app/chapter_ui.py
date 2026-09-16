"""章节层：章节显示/保存/切换/导出/选择器

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from app.events import TOPIC_CHAPTER_SAVED


class ChapterUIMixin:
    """章节层：章节显示/保存/切换/导出/选择器"""

    def _announce_chapter_saved(self, chapter_num: int, content: str):
        """广播 `chapter.saved`（v3 §2.3）。

        这一个事件同时驱动四件事：时间线抽事件、用量面板更新该章 token、
        角色面板刷新"出现章"、记忆可视化刷新。发布方不需要知道有谁在听 ——
        将来加第 5 个消费者时，这里一行都不用改。
        """
        self._publish_event(
            TOPIC_CHAPTER_SAVED,
            {
                "novel_dir": str(self.current_novel_dir or ""),
                "chapter": chapter_num,
                "words": len(content or ""),
            },
        )

    def _display_chapter(self, num, title, content):
        """显示章节内容（线程安全）"""
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", content)
        self.chapter_title_var.set(f"第{num}章: {title}")
        self.word_count_var.set(f"字数: {len(content)}")
        meta = self._get_meta()
        total = meta.get("total_chapters", meta.get("chapter_count", "?"))
        self.chapter_var.set(f"{self.current_chapter}/{total}")

        # 后台线程保存摘要（避免UI线程I/O）
        if hasattr(self, "current_novel_dir") and self.current_novel_dir:
            threading.Thread(target=self._save_chapter_summary, args=(num, title, content), daemon=True).start()

    def _save_chapter_summary(self, chapter_num: int, title: str, content: str):
        """保存章节摘要到文件"""
        if not self.current_novel_dir:
            return

        try:
            # 创建摘要目录
            summary_dir = self.current_novel_dir / "summaries"
            summary_dir.mkdir(exist_ok=True)

            # 提取前500字作为摘要
            summary_text = content[:500]
            if len(content) > 500:
                summary_text += "..."

            # 保存摘要文件
            summary_file = summary_dir / f"chapter_{chapter_num:04d}_summary.txt"
            summary_content = f"章节: 第{chapter_num}章 {title}\n字数: {len(content)}\n\n摘要:\n{summary_text}"
            summary_file.write_text(summary_content, encoding="utf-8")

            self._log(f"[摘要] 已保存第{chapter_num}章摘要")
        except Exception as e:
            self._log(f"[摘要] 保存失败: {e}")

    def _save_chapter(self):
        """保存当前章节"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return

        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可保存的内容")
            return

        chapters_dir = self.current_novel_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        # 🛡️ 原子写入
        chapter_file = chapters_dir / f"chapter_{self.current_chapter:04d}.txt"
        self._atomic_write(chapter_file, content)

        self._announce_chapter_saved(self.current_chapter, content)
        self._log(f"第{self.current_chapter}章已保存")
        messagebox.showinfo("成功", "章节已保存")

    def _prev_chapter(self):
        """加载上一章"""
        if not self.outline or not self.current_novel_dir:
            return
        if self.current_chapter <= 1:
            self._log("已经是第一章")
            return

        # 保存当前章节
        self._save_chapter_silent()

        # 切换到上一章
        self.current_chapter -= 1
        self._load_chapter_by_number(self.current_chapter)

    def _next_chapter(self):
        """加载下一章"""
        if not self.outline or not self.current_novel_dir:
            return
        if self.current_chapter >= len(self.outline):
            self._log("已经是最后一章")
            return

        # 保存当前章节
        self._save_chapter_silent()

        # 切换到下一章
        self.current_chapter += 1
        self._load_chapter_by_number(self.current_chapter)

    def _save_chapter_silent(self):
        """静默保存当前章节（不弹窗）"""
        if not self.current_novel_dir:
            return
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            return
        chapters_dir = self.current_novel_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        with open(chapters_dir / f"chapter_{self.current_chapter:04d}.txt", "w", encoding="utf-8") as f:
            f.write(content)
        self._announce_chapter_saved(self.current_chapter, content)
        self._log(f"第{self.current_chapter}章已自动保存")

    def _load_chapter_by_number(self, ch_num):
        """根据章节号加载内容"""
        if not self.outline or ch_num < 1 or ch_num > len(self.outline):
            return

        chapter_info = self.outline[ch_num - 1]
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_file = chapters_dir / f"chapter_{ch_num:04d}.txt"

        if chapter_file.exists():
            content = chapter_file.read_text(encoding="utf-8")
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", content)
            self.chapter_title_var.set(f"第{ch_num}章: {chapter_info.get('title', '')}")
            self.word_count_var.set(f"字数: {len(content)}")
            self._log(f"已加载第{ch_num}章")
        else:
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", f"章节大纲：\n{chapter_info.get('summary', '无')}\n\n在此处编写内容...")
            self.chapter_title_var.set(f"第{ch_num}章: {chapter_info.get('title', '')} (未生成)")
            self.word_count_var.set("字数: 0")
            self._log(f"第{ch_num}章尚未生成，可手动编写")

        # 更新进度显示
        self.chapter_var.set(f"{ch_num}/{len(self.outline)}")

    def _update_chapter_selector(self):
        """更新章节选择器"""
        if not self.outline:
            self.chapter_select["values"] = []
            return

        chapters = [f"第{i + 1}章" for i in range(len(self.outline))]
        self.chapter_select["values"] = chapters

        # 设置当前章节
        if self.current_chapter > 0 and self.current_chapter <= len(chapters):
            self.chapter_select_var.set(chapters[self.current_chapter - 1])
        elif chapters:
            self.chapter_select_var.set(chapters[0])

    def _on_chapter_select(self, event):
        """章节选择器回调 - 跳转到指定章节"""
        selection = self.chapter_select_var.get()
        if not selection:
            return
        try:
            ch_num = int(selection.replace("第", "").replace("章", "").strip())
        except ValueError:
            return

        self._save_chapter_silent()
        self.current_chapter = ch_num
        self._load_chapter_by_number(ch_num)

        # 更新大纲列表选中状态
        self.outline_list.selection_clear(0, tk.END)
        self.outline_list.selection_set(ch_num - 1)
        self.outline_list.see(ch_num - 1)

    def _export_txt(self):
        """导出全文TXT"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return

        meta = self._get_meta()
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt")], initialfile=f"{meta.get('title', '小说')}.txt"
        )

        if not save_path:
            return

        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))

        with open(save_path, "w", encoding="utf-8") as out:
            out.write(f"《{meta.get('title', '小说')}》\n\n")
            for cf in chapter_files:
                content = cf.read_text(encoding="utf-8")
                out.write(content + "\n\n")

        self._log(f"全文已导出到: {save_path}")
        messagebox.showinfo("成功", f"全文已导出到:\n{save_path}")
