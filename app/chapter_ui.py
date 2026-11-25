"""章节层：章节显示/保存/切换/导出/选择器

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from app import dialogs
from app.application import SaveChapter
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

        # ⛔ 这里曾启动一个后台线程写 `summaries/chapter_%04d_summary.txt`，
        # 内容是 `content[:500]`（正文前 500 字）冒充"摘要"。已删除，理由三条：
        #   1. **它不是摘要** —— 只是正文截断，"摘要:"这个标签是错的；
        #   2. **没有任何读取方** —— 全仓只有 `generation_ui.py:1964` 读 `summaries/`，
        #      而它读的是 **05d** 命名；`04d` 那份**只写不读**（死写入）；
        #   3. **制造重复与漂移** —— 与 `memory_manager.save_chapter_summary`（05d）
        #      写同一逻辑内容却不同文件名，于是同一章在 `summaries/` 下有两个文件
        #      （实测《快速统治》第 1 章同时存在 `chapter_0001_summary.txt` 1789 字符的
        #      思维链与 `chapter_0001_summary.txt` 535 字符的正文截断）。
        # 权威摘要只有一个来源：`MemoryManager.save_chapter_summary`（`memory_manager.py:371`）。

    def _save_chapter(self):
        """保存当前章节"""
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先创建或打开小说")
            return

        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            dialogs.showwarning("提示", "没有可保存的内容")
            return

        # 落盘规则（文件名、目录、原子写、空内容拒绝）在 `application.SaveChapter`
        # —— 那里可以被端到端测试覆盖，面板只剩"取内容 + 调用例 + 弹窗"。
        result = SaveChapter().execute(self.current_novel_dir, self.current_chapter, content)
        if not result.ok:
            dialogs.showwarning("提示", result.reason)
            return

        self._announce_chapter_saved(self.current_chapter, content)
        self._log(f"第{self.current_chapter}章已保存")
        dialogs.showinfo("成功", "章节已保存")

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
        """静默保存当前章节（不弹窗）。

        ❗ 本轮改为**原子写**。这里是"自动保存"，触发频率最高，
        而原先用的是裸 `open(..., "w")` —— 一旦在写入过程中进程被杀
        （任务管理器结束 / 断电 / 崩溃），磁盘上留下的是**被截断的半章**，
        而原文已经没了。章节是用户最不可再生的数据，这条必须原子。
        """
        if not self.current_novel_dir:
            return
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            return
        # 与 `_save_chapter` 共用**同一条落盘路径**（`application.SaveChapter`）——
        # 自动保存与手动保存写法不同，是历史上"两个写入方"事故的根源。
        SaveChapter().execute(self.current_novel_dir, self.current_chapter, content)
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
        """导出全文 TXT（走 `format_converter` 的统一实现）。

        为什么改：此前这里是**手写的一套导出**（裸 `open("w")` + 只支持 TXT），
        而 `format_converter` 早已支持六种格式（TXT/HTML/Markdown/EPUB/PDF/DOCX）。
        同一件"导出"的事两套代码，后果是：格式细节两边不一致、修一处忘另一处。
        现在统一走 converter —— 想导其他格式，用工具栏「格式转换」即可。

        行为变化（有意）：TXT 里每章前会多出分隔线与章名（converter 的规范格式），
        不再包含正文首行的 markdown `#` 标记。
        """
        if not self.current_novel_dir:
            dialogs.showwarning("提示", "请先创建或打开小说")
            return

        meta = self._get_meta()
        title = meta.get("title", "小说")
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt")], initialfile=f"{title}.txt"
        )
        if not save_path:
            return

        chapters: list[dict] = []
        for path in sorted((self.current_novel_dir / "chapters").glob("chapter_*.txt")):
            raw = path.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            heading = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else ""
            body = "\n".join(lines[1:]).strip() if heading else raw.strip()
            match = re.search(r"(\d+)", path.stem)
            chapters.append({"num": int(match.group(1)) if match else 0, "title": heading, "content": body})

        try:
            from app.format_converter import FormatConverter

            converter = FormatConverter(self.current_novel_dir)
            result = converter.convert("", title, "txt", chapters=chapters, output_file=Path(save_path))
            if not result:
                reason = converter.last_error or "请检查导出目录权限。"
                dialogs.showerror("导出失败", f"格式转换未返回结果：{reason}")
                return
        except Exception as exc:  # noqa: BLE001 - 导出失败要能看见原因
            self._log(f"导出失败: {exc}")
            dialogs.showerror("导出失败", str(exc))
            return

        self._log(f"全文已导出到: {result}")
        dialogs.showinfo("成功", f"全文已导出到:\n{result}")
