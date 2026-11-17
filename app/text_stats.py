"""文本度量 —— 汉字计数与密度换算的**唯一实现**。

## 为什么要单独一个模块

`count_hanzi` 原本在 `writing_presets.py` 里。但 `semantic_candidates.py` 也要用它，
于是两个模块互相延迟导入，形成潜伏循环（`python scripts/module_graph.py` 会报出来）。

更根本的问题是：**汉字计数口径必须全仓一致**。技能包的脚本按汉字数判定
（"少于 500 汉字直接退出"），如果某处按 `len()` 算、另一处按汉字算，
短文案门槛就会时灵时不灵 —— 而且不会报错。

所以把它下沉到最底层（不依赖任何 app 模块），谁都能用，且只有一份。
"""

from __future__ import annotations

import re

__all__ = ["HANZI_RE", "count_hanzi", "per_ktx"]

#: 汉字（CJK 统一表意文字基本区）。刻意**不含**标点、数字、英文 ——
#: 技能包的口径就是"汉字数"，中英混排时按汉字折算才不会把英文段落算成正文。
HANZI_RE = re.compile(r"[\u4e00-\u9fff]")


def count_hanzi(text: str) -> int:
    """汉字个数。`None` / 非字符串按空处理（调用方不必先判空）。"""
    if not text:
        return 0
    return len(HANZI_RE.findall(str(text)))


def per_ktx(count: int, hanzi: int) -> float:
    """每千汉字密度。`hanzi <= 0` 返回 0（短文本不参与密度判定）。"""
    if hanzi <= 0:
        return 0.0
    return count * 1000.0 / hanzi
