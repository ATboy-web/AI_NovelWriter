"""源码扫描型断言的公共工具。

「某某写法不得再出现」这类负向断言必须先剔除注释与文档字符串 ——
修复说明在 docstring 里提到"旧实现用了 `xxx`"，会让断言被自己的说明文字推翻。
本模块把这段逻辑收成一份，供多个测试文件共用。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# 三引号字符串（=文档字符串）
_DOCSTRING_RE = re.compile(r'("""|\'\'\')(?:(?!\1).)*\1', re.DOTALL)


def read(rel: str) -> str:
    """读取仓库内文件的原始文本。"""
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def strip_noise(src: str) -> str:
    """去掉文档字符串与注释（含行内注释），只留可执行代码。"""
    src = _DOCSTRING_RE.sub("", src)
    lines = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line.split("#", 1)[0])
    return "\n".join(lines)


def code_only(rel: str) -> str:
    """`read` 的「只留代码」版本，用于源码扫描型负向断言。"""
    return strip_noise(read(rel))


def method_body(rel: str, start_marker: str, end_marker: str) -> str:
    """截取两个标记之间的源码片段（断言缩到具体代码块，避免误伤合法用法）。"""
    src = read(rel)
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]
