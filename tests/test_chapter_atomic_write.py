"""章节落盘必须原子 —— 数据安全守卫（v3.2 / 任务四）。

## 为什么这条值得单独一个文件

章节是**用户最不可再生的数据**，而且它的产生成本极高
（一章 6000 字可能要几十分钟的串行 API 往返）。

裸写 `open(path, "w")` 有两种破坏方式：

1. **写一半被杀**（任务管理器结束进程 / 断电 / 崩溃 / 取消）
   ⇒ 磁盘上留下**被截断的半章**，而完整原文已经不存在了；
2. 并发写（自动保存 + 生成完成同时落盘）⇒ 两次 `write` 交错。

`app.storage.atomic_write_text` 用「唯一临时名 + `os.replace`」解决这两点：
要么完整的旧内容、要么完整的新内容，**不存在中间态**。

这个缺陷不会报错、不会崩溃、测试也全绿 —— 只在**真出事那天**才暴露。
所以只能用"扫描写盘点"的方式守住，这正是本文件存在的理由。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import _source_scan as _scan  # noqa: E402

#: 章节文件的文件名形态。
#: ❗ 表达式里**有点**是常态（`self.current_chapter`、`self.current_ch`），
#: 用 `[A-Za-z0-9_]*` 那种字符类会漏掉它 —— 负向对照时就是这么被骗过去的
#: （把原子写改回裸 `open` 仍然全绿）。所以这里放开为"任意非 `}` 字符"。
_CHAPTER_PATH_PATTERN = re.compile(r"chapter_\{[^}]*:0?4d\}\.txt")

#: 允许出现"非原子写"的文件白名单（附理由，避免无脑放行）。
#: 每条都必须写明**为什么这里可以不是原子写**。
_ATOMIC_EXEMPT: dict[str, str] = {}


def _chapter_write_sites() -> list[tuple[str, int, str]]:
    """找出所有"把章节文件用裸文本模式打开写入"的位置。

    返回 `[(相对路径, 行号, 该行内容)]`。
    """
    hits: list[tuple[str, int, str]] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _ATOMIC_EXEMPT:
            continue
        # ❗ 用 code_only 剔注释与 docstring：本仓的说明性注释里**故意**
        # 提到旧的写法来解释为什么改掉它（例如 "原先用的是裸 open(..., 'w')"），
        # 那是说明而非实现，不能被判为违规。
        code = _scan.code_only(rel)
        for lineno, line in enumerate(code.splitlines(), start=1):
            if _CHAPTER_PATH_PATTERN.search(line) and re.search(r"\bopen\s*\(", line) and '"w"' in line:
                hits.append((rel, lineno, line.strip()))
    return hits


class TestChapterWritesAreAtomic:
    def test_no_bare_open_for_writing_chapters(self):
        """所有章节落盘必须走原子写。

        若这条变红：说明有人新增了（或回退了）一处裸 `open(..., "w")` 写章节。
        正确改法是改成 `self._atomic_write(path, content)`
        （它委托 `app.storage.atomic_write_text`）。
        """
        hits = _chapter_write_sites()
        assert not hits, "发现非原子的章节写盘：\n" + "\n".join(f"  {rel}:{ln}  {src}" for rel, ln, src in hits)

    def test_chapter_files_are_actually_written_somewhere(self):
        """反向断言：不能靠"把写盘代码删光"来让上面那条通过。"""
        code = _scan.code_only("app/generation_ui.py") + _scan.code_only("app/chapter_ui.py")
        assert code.count("_atomic_write(") >= 2, "章节写盘点不见了（不是原子化，而是被删了）"

    def test_atomic_write_delegates_to_shared_helper(self):
        """`_atomic_write` 必须委托统一实现，不能自己再写一份。

        本仓曾把原子写重复实现 4 次，其中一处用 `with_suffix('.tmp')`
        导致 `settings.json` 与 `settings.md` 争用同一个 `settings.tmp`。
        """
        code = _scan.code_only("app/persistence_ui.py")
        assert "atomic_write_text" in code, "_atomic_write 没有委托 app.storage"

    def test_storage_helper_uses_os_replace(self):
        code = _scan.code_only("app/storage.py")
        assert "os.replace" in code, "原子替换机制不见了"

    def test_storage_helper_uses_unique_temp_names(self):
        """临时名必须唯一 —— 否则同目录并发写会互相破坏。"""
        code = _scan.code_only("app/storage.py")
        assert "uuid" in code, "临时名不再唯一（并发写会互相覆盖）"


class TestOtherImportantDataIsAtomic:
    """章节之外，这些文件同样是"崩一次就没了" —— 也必须原子写。

    本轮（v3.2）补的几处，以及为什么它们各自重要：

    | 数据 | 非原子写的后果 |
    |---|---|
    | `meta.json` | 小说元信息（标题/主角/世代）损坏 ⇒ **作品直接打不开** |
    | `scores.json` | 检索评分表清零 ⇒ 表现为"记忆突然变笨了" |
    | `index.json` | 关键词索引损坏 ⇒ `search_by_keyword` 全面失效 |
    | `*_concept.txt` | 续集/同人设定丢失 ⇒ 新作失去创作依据 |

    判据是"这些路径的写入必须走 `atomic_write_*`"，用**源码扫描**钉住 ——
    因为它们分散在 UI 回调里，行为测试要起 Tk 才能覆盖。
    """

    #: (相对路径, 必须出现的原子写调用, 说明)
    _SITES = [
        ("app/lifecycle_ui.py", 'atomic_write_json(novel_dir / "meta.json"', "作品元信息"),
        ("app/lifecycle_ui.py", 'atomic_write_text(novel_dir / "sequel_concept.txt"', "续集设定"),
        ("app/lifecycle_ui.py", 'atomic_write_text(novel_dir / "spinoff_concept.txt"', "同人设定"),
        ("app/memory_manager.py", "atomic_write_json(self.scores_file", "检索评分表"),
        ("app/memory_manager.py", "atomic_write_json(self.index_file", "关键词索引"),
        ("app/timeline_ui.py", "atomic_write_text(", "分支摘要"),
    ]

    @pytest.mark.parametrize(
        ("rel", "needle", "what"),
        _SITES,
        ids=[f"{s[2]}" for s in _SITES],
    )
    def test_site_uses_atomic_write(self, rel, needle, what):
        """❗ 必须用 `count_normalized`（忽略空白差异），不能裸 `in`。

        `ruff format` 会把长调用拆行：
            atomic_write_text(
                novel_dir / "sequel_concept.txt",
                ...,
            )
        此时单行 needle 匹配不上 —— 代码行为完全没变，只是换了个括号内换行。
        本仓踩过这个坑，`_source_scan.count_normalized` 就是为此存在的。
        """
        code = _scan.code_only(rel)
        assert _scan.count_normalized(code, needle) >= 1, f"{rel} 的「{what}」写入没走原子写"

    def test_meta_json_has_no_bare_open_anymore(self):
        """`meta.json` 曾经在 3 处被裸 `open(..., "w")` 写 —— 全部收口。

        同样用 `count_normalized`：否则 `ruff format` 把 `open(` 拆行后，
        这条会**静默通过**（漏报比假红更危险）。
        """
        code = _scan.code_only("app/lifecycle_ui.py")
        for shape in (
            'open(novel_dir / "meta.json", "w"',
            'open(novel_dir/"meta.json", "w"',  # 归一化后的等价写法
        ):
            assert _scan.count_normalized(code, shape) == 0, "meta.json 又出现了裸写"

    def test_memory_manager_has_no_bare_json_writes(self):
        """❗ 只拦**写**：`open(path, "r")` 是读，本来就不该原子化。

        （第一版判据写成"出现 `open(self.scores_file,`"就报错，
        结果命中了一处合法的读取 —— 判据比要拦的东西宽，就是假阳性。）
        """
        code = _scan.code_only("app/memory_manager.py")
        offenders = []
        for name in ("self.scores_file", "self.index_file", "self.inverted_index_file"):
            # 归一化后匹配"写模式"，避开 `"r"`（读）与 `"a"`（追加，另有其语义）
            for mode in ('"w"', '"w"'):
                shape = f"open({name},{mode}"
                if _scan.count_normalized(code, shape) > 0:
                    offenders.append(f"{name} 仍以 {mode} 裸写")
        assert not offenders, "又出现了裸 open 写入：\n" + "\n".join(offenders)


class TestAtomicWriteBehaviour:
    """行为验证：真的做到"要么旧的、要么新的"，且失败不破坏原文件。"""

    def test_write_creates_file(self, tmp_path):
        from app.storage import atomic_write_text

        target = tmp_path / "chapter_0001.txt"
        atomic_write_text(target, "第一章内容")
        assert target.read_text(encoding="utf-8") == "第一章内容"

    def test_overwrite_is_complete(self, tmp_path):
        from app.storage import atomic_write_text

        target = tmp_path / "chapter_0001.txt"
        atomic_write_text(target, "旧内容" * 100)
        atomic_write_text(target, "新内容")
        # 若实现是"先清空再写"，失败时会看到旧内容的前缀残留；这里断言完全替换
        assert target.read_text(encoding="utf-8") == "新内容"

    def test_no_temp_file_left_behind(self, tmp_path):
        from app.storage import atomic_write_text

        target = tmp_path / "chapter_0001.txt"
        atomic_write_text(target, "内容")
        leftover = [p.name for p in tmp_path.iterdir() if p.name != target.name]
        assert leftover == [], f"写完后残留了临时文件：{leftover}"

    def test_original_survives_when_write_fails(self, tmp_path, monkeypatch):
        """❗ 最关键的一条：写失败时**原文件必须完好**。

        这正是"原子"的意义 —— 不做原子写的话，`open(..., "w")` 会先把文件
        截断为 0，再写入失败，于是**旧内容也一起丢了**。
        """
        from app import storage

        target = tmp_path / "chapter_0001.txt"
        storage.atomic_write_text(target, "原来的完整内容")

        def _boom(*_a, **_k):
            raise OSError("磁盘满了")

        monkeypatch.setattr(storage.os, "replace", _boom)
        with pytest.raises(OSError):
            storage.atomic_write_text(target, "新内容")

        assert target.read_text(encoding="utf-8") == "原来的完整内容", "写失败把原文也弄丢了"
