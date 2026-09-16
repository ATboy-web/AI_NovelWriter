"""线上小说数据的定位与摘要工具（v3 P0 护栏）。

**为什么需要这个模块**：线上数据**不在仓库里**。

`app/character_ui.py` 读的是 `self.current_novel_dir / "memory" / "characters.json"`，
而 `current_novel_dir` 指向 `~/.ai_novel_writer/novels/<书名>_<id>/`。
仓库里那个 `memory/` 目录**不是**线上数据 —— 2026-09-16 的复核中曾因此在仓库内
查找 `characters.json` 而误报「文件不存在」。

因此所有「数据安全断言」都必须通过本模块定位真实数据根目录，
而不是猜仓库路径。
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

__all__ = [
    "novels_root",
    "iter_novel_dirs",
    "find_novel_dir",
    "NovelDataSummary",
    "summarize_novel",
    "characters_sha256",
]


def novels_root() -> Path:
    """线上小说根目录：`~/.ai_novel_writer/novels/`。

    与 `app/config.py: AppConfig.novels_dir` 保持一致（同一实现来源），
    这里不 import AppConfig 以避免实例化时创建目录 / 加载加密配置的副作用。
    """
    return Path.home() / ".ai_novel_writer" / "novels"


def iter_novel_dirs(root: Optional[Path] = None) -> Iterator[Path]:
    """遍历所有小说目录（含 `memory/characters.json` 的目录）。"""
    base = root or novels_root()
    if not base.is_dir():
        return
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "memory" / "characters.json").is_file():
            yield child


def find_novel_dir(root: Optional[Path] = None) -> Optional[Path]:
    """返回「当前线上小说」目录。

    判定顺序：
    1. 角色文件最后修改时间最新的那个（用户实际在用的）；
    2. 都没有时返回 None。

    刻意不按目录名排序 —— 目录名带时间戳后缀，但用户可能倒回旧书继续写。
    """
    best: Optional[Path] = None
    best_mtime = -1.0
    for novel in iter_novel_dirs(root):
        try:
            mtime = (novel / "memory" / "characters.json").stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best, best_mtime = novel, mtime
    return best


def characters_sha256(novel_dir: Path) -> str:
    """计算角色数据的 sha256（十六进制大写）。

    这是项目「角色名不可删除」硬约束的**唯一客观判据**：
    改造前后哈希必须逐位一致。任何一次写操作都会改变它。
    """
    data = (novel_dir / "memory" / "characters.json").read_bytes()
    return hashlib.sha256(data).hexdigest().upper()


def _count_files(directory: Path, pattern: str = "*.json") -> int:
    """统计目录下匹配 `pattern` 的文件数（目录不存在返回 0）。

    章节是 `chapters/chapter_0001.txt`（**txt**），角色文件是 `characters/<名>.json`（json）——
    两者扩展名不同，所以这里必须能传 pattern。
    """
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.glob(pattern) if p.is_file())


@dataclass(frozen=True)
class NovelDataSummary:
    """一次数据快照（用于改造前后比对）。

    ⚠️ 两个容易混淆的计数字段（2026-09-16 修正）：

    - `chapter_count` —— **真正的章节数**：`chapters/chapter_*.txt` 的文件数。
    - `character_file_count` —— `characters/<名>.json` 的文件数。

    修正前 `chapter_count` 统计的是**后者**，于是基线报告里出现
    `character_count: 286 / chapter_count: 286` 这种两个数字相同、
    且"章节数"其实是角色文件数的假象；**真章数（线上 1094）从未被采集**，
    导致 `--verify` 完全无法发现"章节被删"。这里把两者分开并各自诚实命名。
    """

    root: str
    characters_sha256: str
    characters_bytes: int
    character_count: int
    chapter_count: int
    character_file_count: int
    characters_mtime: str

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "characters_sha256": self.characters_sha256,
            "characters_bytes": self.characters_bytes,
            "character_count": self.character_count,
            "chapter_count": self.chapter_count,
            "character_file_count": self.character_file_count,
            "characters_mtime": self.characters_mtime,
        }

    def format_text(self) -> str:
        return (
            f"root         : {self.root}\n"
            f"sha256       : {self.characters_sha256}\n"
            f"bytes        : {self.characters_bytes}\n"
            f"characters   : {self.character_count}\n"
            f"chapters     : {self.chapter_count}\n"
            f"char files   : {self.character_file_count}\n"
            f"mtime        : {self.characters_mtime}\n"
        )


def summarize_novel(novel_dir: Path) -> NovelDataSummary:
    """采集一个小说目录的数据摘要。

    只读：不写入任何文件，也不触碰 `.bak` 轮转。
    """
    char_file = novel_dir / "memory" / "characters.json"
    raw = char_file.read_bytes()

    characters = 0
    try:
        parsed = json.loads(raw.decode("utf-8"))
        if isinstance(parsed, dict):
            # 与 parsing.extract_characters_payload 同一判据：dict 值才算角色
            characters = sum(1 for v in parsed.values() if isinstance(v, dict))
    except (ValueError, UnicodeDecodeError):
        characters = -1  # 解析失败：如实标记，不要伪装成 0

    return NovelDataSummary(
        root=str(novel_dir),
        characters_sha256=hashlib.sha256(raw).hexdigest().upper(),
        characters_bytes=len(raw),
        character_count=characters,
        # 真章数：`chapters/chapter_*.txt`（此前误统计 characters/ 的 JSON，见类文档）
        chapter_count=_count_files(novel_dir / "chapters", "*.txt"),
        character_file_count=_count_files(novel_dir / "characters", "*.json"),
        characters_mtime=_format_mtime(char_file),
    )


def _format_mtime(path: Path) -> str:
    try:
        from datetime import datetime

        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "unknown"
