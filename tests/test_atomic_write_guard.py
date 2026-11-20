"""原子写守卫：状态/配置类写入必须走 `atomic_write*`，不得裸写。

## 为什么需要这道守卫

裸 `open(path, "w")` 在写入中途被杀（用户强退、断电、任务管理器结束进程）会留下
**截断文件**。对用户导出（TXT/PDF）无所谓 —— 重新导一次就行；但对**状态/配置**
是灾难：

| 文件 | 裸写坏掉的后果 |
|---|---|
| `chapters/chapter_NNNN.txt` | 章节只有半截，而摘要/索引/记忆已按"这章存在"更新 |
| `outline.json` | 读不回来 → 当成"没有大纲"重新生成 → 覆盖用户改过的部分 |
| `rewrite_log.json` | 断点续跑失效 → 已重写的章全部重做（**真金白银**） |
| `style_config.json` | 回默认值，用户调过的旋钮悄悄失效 |
| `writer_settings.json` | 字号/纸张/打字机模式全部回默认 |
| `knowledge_graph.json` | 实体/关系/事件全丢 |

## 守卫是**双向**的

- 出现清单之外的新裸写 ⇒ 失败（提醒考虑原子写，或显式登记理由）
- 清单里的条目消失 ⇒ 也失败（清单该删了，否则它会变成一份没人看的谎话）

这条纪律源自本项目踩过的坑：单向守卫会让清单腐烂，最后没人相信它。
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"

#: 允许保留的裸写：(文件, 行内容特征, 理由)。
#:
#: 只登记**确实是导出/一次性生成**的场景。任何"读回来还要用"的文件都不该出现在这里。
ALLOWED_RAW_WRITES: tuple[tuple[str, str, str], ...] = (
    # ---- 用户主动导出：失败可重做，不涉及应用状态
    ("editor_ui.py", "f.write_text(", "导出场景提示词，用户重导即可"),
    ("reader_ui.py", "open(file_path,", "导出书内内容"),
    ("shell_ui.py", "filepath.write_text(", "导出用户内容"),
    ("toolkit_ui.py", "cover_file.write_text(", "生成封面 HTML"),
    ("toolkit_ui.py", "cover_preview.html", "生成封面预览"),
    ("toolkit_ui.py", "prompt_file.write_text(", "导出提示词"),
    ("skill_library_panel.py", "target.write_text(", "导出改写指令给用户"),
    ("chapter_analysis_panel.py", "open(dest,", "导出章节分析报告"),
    ("batch_ops_panel.py", "dest.write_text(", "批量复制章节到新作品（目标是新文件）"),
    ("usage_tracker.py", "open(path,", "导出用量 CSV"),
    ("semantic_candidates.py", "target.write_text(", "导出候选清单"),
    # ---- 临时文件 / 已经自带原子语义
    ("format_converter.py", "open(tmp,", "先写 tmp 再 rename，本身是原子模式"),
    ("format_converter.py", "open(img_file,", "写出二进制图片"),
    ("image_generator.py", "open(filepath,", "写出生成的图片"),
    ("plugin_system.py", "open(dest,", "解压/复制插件文件"),
    ("cloud_storage.py", "open(tmp,", "下载先落 tmp"),
    ("mcp_system.py", "tmp.write_text(", "写临时配置文件后 rename"),
    # ---- 低价值状态：坏了重新开始的代价可接受，暂不动
    ("reading_manager.py", "bookmarks_file", "书签/阅读历史，重建成本低"),
    ("reading_manager.py", "reading_history_file", "同上"),
    ("reading_manager.py", "open(file_path,", "导入书籍时写入"),
    ("note_manager.py", "open(self.sticky_file", "便签，单行文本"),
    ("note_manager.py", "open(self.project_note_file", "工程笔记"),
    ("note_manager.py", "open(note_file", "文档笔记"),
    ("plugin_system.py", "open(self.state_file", "插件启用状态"),
    ("performance_monitor.py", "open(filepath,", "性能采样落盘"),
    ("timeline_ui.py", "(branch_dir /", "分支小说的 meta/outline（新建产物）"),
    ("timeline_ui.py", "ch_file.write_text(", "分支小说章节（新建产物）"),
    ("timeline_ui.py", "main_file.write_text(", "初始化空世界线（仅文件不存在时）"),
    ("mcp_panel.py", "path.write_text(", "创建示例配置文件"),
)

#: 扫描时跳过的行：注释 / docstring 里提到裸写是在**解释为什么不用它**。
SKIP_MARKERS = ("#", '"""', "为什么", "旧实现", "原先", "用 `open(")


def _is_comment_or_doc(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    # 文档里**引用代码**也是在解释为什么不用它：这一行含反引号包裹的调用，
    # 不可能是真实写盘语句（真实语句不会带 markdown 反引号）。
    if "`open(" in stripped or "`write_text(" in stripped:
        return True
    return any(marker in stripped for marker in ("为什么", "旧实现", "原先", "裸 `open"))


def scan() -> list[tuple[str, int, str]]:
    """返回所有裸写位置 `[(相对路径, 行号, 行内容)]`。"""
    rows: list[tuple[str, int, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in str(path) or path.name == "storage.py":
            # storage.py 是原子写本身的实现，它当然要裸写
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _is_comment_or_doc(line):
                continue
            if "atomic_write" in line:
                continue
            if ".write_text(" in line or re.search(r"open\([^)]*['\"]w", line):
                rows.append((path.relative_to(ROOT).as_posix(), number, line.strip()))
    return rows


def _allowed(rel: str, line: str) -> bool:
    for file_name, marker, _why in ALLOWED_RAW_WRITES:
        if rel.endswith(file_name) and marker in line:
            return True
    return False


class TestAtomicWriteGuard:
    def test_no_unregistered_raw_writes(self):
        offenders = [f"{rel}:{number} {line[:80]}" for rel, number, line in scan() if not _allowed(rel, line)]
        assert not offenders, (
            "以下位置是裸写且未登记理由。若确实是一次性导出，请加入 ALLOWED_RAW_WRITES 并写明原因；"
            "若是状态/配置，请改用 atomic_write_text / atomic_write_json：\n  " + "\n  ".join(offenders)
        )

    def test_allowlist_entries_still_exist(self):
        """双向：清单里的条目若已消失，说明清单过期，必须同步删除。"""
        rows = scan()
        stale = [
            f"{file_name} :: {marker}（{why}）"
            for file_name, marker, why in ALLOWED_RAW_WRITES
            if not any(rel.endswith(file_name) and marker in line for rel, _n, line in rows)
        ]
        assert not stale, "以下登记项已不存在，请从 ALLOWED_RAW_WRITES 删除：\n  " + "\n  ".join(stale)

    def test_core_state_files_are_atomic(self):
        """核心状态文件必须走原子写 —— 抽查几个最要紧的。"""
        checks = [
            ("writing_skills.py", "style_config.json"),
            ("writing_skills.py", "knowledge_graph.json"),
            ("writing_skills.py", "time_memory.json"),
            ("fullscreen_writer.py", "writer_settings.json"),
            ("bulk_rewrite.py", "REWRITE_LOG"),
        ]
        for file_name, marker in checks:
            source = (ROOT / file_name).read_text(encoding="utf-8")
            assert marker in source, f"{file_name} 里找不到 {marker}"
            assert "atomic_write" in source, f"{file_name} 应使用 atomic_write*，但源码里没有"
