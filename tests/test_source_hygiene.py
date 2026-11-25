"""源码卫生：禁止不可见控制字符混进 .py 文件。

## 为什么需要

2026-11-25 实测踩到：往测试文件里写正则时，`\\b` 被当成转义写成了**退格符**
（`\\x08`），于是那个正则字面量实际是 `"\\x08\\\\w*writer..."`，永远匹配不到任何行。

排查过程很费劲，因为：
- 编辑器、`sed -n`、`inspect.getsource` **都看不出来**（退格不可见，只表现为光标退一格）
- 代码逻辑看起来完全正确，`re.search` 单测也"应该"匹配
- 只有 `function.__code__.co_consts` 的 `repr` 才暴露 `'\\x08\\\\w*...'`

控制字符进入源码的途径不止手滑：粘贴自网页、命令行 heredoc 转义、脚本生成代码。
一条静态扫描就能挡住整类问题。

## 允许的字符

`\\n`（换行）、`\\t`（缩进）、`\\r`（CRLF 环境的行尾）之外的控制字符一律禁止。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCAN_DIRS = ("app", "tests", "scripts")

#: 允许出现的控制字符
_ALLOWED = {"\n", "\t", "\r"}


def _iter_sources():
    for name in _SCAN_DIRS:
        for path in sorted((_REPO / name).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


class TestNoControlCharacters:
    @pytest.mark.parametrize("path", list(_iter_sources()), ids=lambda p: p.name)
    def test_no_control_chars(self, path: Path):
        text = path.read_text(encoding="utf-8", errors="replace")
        bad: list[tuple[int, int, str]] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for col, ch in enumerate(line):
                if ch < " " and ch not in _ALLOWED:
                    bad.append((lineno, col, hex(ord(ch))))
        assert not bad, (
            f"{path.relative_to(_REPO)} 含不可见控制字符 {bad[:5]}"
            f"（这类字符会让正则/字符串比较静默失效，且编辑器看不见）"
        )

    def test_scan_actually_reads_files(self):
        """反证：确认扫描器读到了文件，否则上面的逐文件用例是空转。"""
        files = list(_iter_sources())
        assert len(files) > 100, f"只扫到 {len(files)} 个文件，疑似扫描失效"
