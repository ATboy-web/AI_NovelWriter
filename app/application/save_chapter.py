"""用例：把一章正文落盘。

## 为什么单独有个用例

这段逻辑原先只存在于 `chapter_ui._save_chapter`（Tk 面板方法）里：
拼 `chapters/chapter_%04d.txt`、建目录、原子写、广播 `chapter.saved`。

后果是**它无法被端到端测试覆盖** —— 想验证"Agent 生成的正文能正确落进作品目录"，
必须先造一个 Tk 面板。而"生成 → 落盘 → 重启后读得到"正是本项目最该被钉住的链路
（面板里其他按钮都可以重写，这条链路断了作品就丢了）。

抽出来之后：
- 面板只负责"取文本框内容 + 调用例 + 弹窗"
- 测试可以直接跑"生成 → 保存 → 重开验证"，不需要 Tk

## 职责边界（刻意不做的事）

- **不发事件**：只返回该广播的载荷。事件总线属于上层装配，用例不该知道它存在。
- **不写摘要**：`summaries/` 的唯一权威是 `MemoryManager.save_chapter_summary`
  （见 `chapter_ui.py` 顶部注释里记录的教训：曾有两个写入方，同一章出现两份摘要）。
- **不改大纲/元数据**：本章写完不代表章节数变了。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.storage import atomic_write_text

__all__ = ["SaveChapter", "SaveChapterResult"]

#: 章节文件命名（全仓唯一来源，别再各处拼 `chapter_{n:04d}.txt`）
CHAPTER_FILE_FMT = "chapter_{:04d}.txt"


@dataclass
class SaveChapterResult:
    """保存结果。`ok=False` 时 `reason` 可直接展示给用户。"""

    ok: bool
    chapter: int
    path: Path | None = None
    words: int = 0
    reason: str = ""

    def event_payload(self, novel_dir: str) -> dict[str, Any]:
        """`chapter.saved` 的事件载荷。

        这一个事件同时驱动四件事：时间线抽事件、用量面板更新 token、
        角色面板刷新"出现章"、记忆可视化刷新。
        """
        return {
            "novel_dir": str(novel_dir or ""),
            "chapter": int(self.chapter),
            "words": int(self.words),
        }


class SaveChapter:
    """把正文写到 `<作品>/chapters/chapter_%04d.txt`（原子写）。"""

    def execute(self, novel_dir: Any, chapter_num: int, content: str) -> SaveChapterResult:
        chapter = int(chapter_num)
        if chapter < 1:
            return SaveChapterResult(ok=False, chapter=chapter, reason=f"章节号非法：{chapter_num}")
        if not novel_dir:
            return SaveChapterResult(ok=False, chapter=chapter, reason="请先创建或打开小说")

        text = (content or "").strip()
        if not text:
            # 空内容绝不落盘：写一个空文件等于把这章的正文删了（重启后无法区分
            # "还没写" 与 "被清空"），而用户在面板上点"保存"显然不是这个意思。
            return SaveChapterResult(ok=False, chapter=chapter, reason="没有可保存的内容")

        target = Path(novel_dir) / "chapters" / CHAPTER_FILE_FMT.format(chapter)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, text)

        return SaveChapterResult(
            ok=True,
            chapter=chapter,
            path=target,
            words=len(text),
        )
