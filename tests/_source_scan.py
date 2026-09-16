"""源码扫描型断言的公共工具。

本模块处理源码扫描断言的**三类已知脆弱点**，每一类都被真实事故踩过：

1. **注释/文档字符串**：修复说明在 docstring 里提到"旧实现用了 `xxx`"，
   会让断言被自己的说明文字推翻 → `strip_noise` / `code_only`。
2. **文档字符串里的示例代码**：说明"调用时机"时原样引用了一行赋值，
   被数成"第 5 处入口" → 同上（这也是 `code_only` 存在的理由）。
3. **格式化换行**（2026-09-16 新增）：`ruff format` 会把长调用拆成多行，
   于是 `code.count("self._publish_event(TOPIC_CONFIG_CHANGED")` 从 1 变 0 ——
   **行为没变，断言却红了** → `count_normalized` / `squash`。
4. **字符串里的 `#`**（2026-09-16 加固）：朴素的 `line.split("#", 1)` 会把
   `bg="#101020", fg=C["typo_key"])` **整行截断**，于是 `fg=C["typo_key"]` 从扫描结果里
   彻底消失 —— 颜色令牌守卫会**静默漏检**。现改用 `tokenize` 去注释（字符串原样保留），
   并保留旧实现作为极端输入下的兜底。
   （实测：当前仓库两种实现找到的键完全一致，即该洞尚未被触发，但必须堵上。）

写新的源码扫描断言时：**先 `code_only`，再 `count_normalized`**，不要裸用 `str.count`。
"""

import io
import re
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# 三引号字符串（=文档字符串）
_DOCSTRING_RE = re.compile(r'("""|\'\'\')(?:(?!\1).)*\1', re.DOTALL)

# 连续空白（含换行）
_WS_RE = re.compile(r"\s+")


def read(rel: str) -> str:
    """读取仓库内文件的原始文本。"""
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def squash(src: str) -> str:
    """把连续空白压成单个空格。

    用途见 `count_normalized`。也可用于"标记跨行"的定位：
    `squash(src).index("def foo( self, x )")`。
    """
    return _WS_RE.sub(" ", src)


def count_normalized(src: str, needle: str) -> int:
    """**忽略一切空白差异**地统计 `needle` 出现次数。

    为什么需要它：`ruff format` 会把长调用拆行，
    `src.count("self._publish_event(TOPIC_CONFIG_CHANGED")` 这类断言会**假红** ——
    代码行为完全没变，只是换了个括号内换行。

    实现：把两边所有空白都删掉再数。因此 `needle` 可以写成任意换行/缩进形式，
    但不能依赖空白作为分隔（例如不要用 `"a b"` 去区分 `ab`）。
    """
    return _WS_RE.sub("", src).count(_WS_RE.sub("", needle))


def _strip_comments(src: str) -> str:
    """用 `tokenize` 去掉注释：**字符串里的 `#` 不再被误当注释**。

    朴素写法 `line.split("#", 1)[0]` 会把 `bg="#101020", fg=C["typo"])` 整行截断，
    使截断点之后的内容从扫描结果里消失 —— 那会让"守卫型断言"静默漏检
    （例如 `TestPanelColorTokensExist` 就扫不到 `C["typo"]`）。

    极端输入（token 流不完整等）下退回旧行为：**断言工具本身不应抛错**。
    """
    if "#" not in src:
        return src
    try:
        kept = [tok for tok in tokenize.generate_tokens(io.StringIO(src).readline) if tok.type != tokenize.COMMENT]
        return tokenize.untokenize(kept)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def strip_noise(src: str) -> str:
    """**先去注释**（`tokenize`，保留字符串）**再抹文档字符串**（正则）。

    顺序很关键：正则会把 `x = \"\"\"…\"\"\"` 变成 `x = ` 从而不再是合法 Python，
    所以必须先在**原始源码**上做 tokenize。

    行结构保持不变（只把内容清空，不删行）—— 调用方会用 `code.index(...)` 做切片，
    行数稳定更利于定位。
    """
    return _DOCSTRING_RE.sub("", _strip_comments(src))


def code_only(rel: str) -> str:
    """`read` 的「只留代码」版本，用于源码扫描型负向断言。"""
    return strip_noise(read(rel))


def code_only_normalized(rel: str) -> str:
    """`code_only` + 去掉全部空白 —— 写"包含某调用"的断言时最省心。"""
    return _WS_RE.sub("", strip_noise(read(rel)))


def method_body(rel: str, start_marker: str, end_marker: str) -> str:
    """截取两个标记之间的源码片段（断言缩到具体代码块，避免误伤合法用法）。"""
    src = read(rel)
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]
