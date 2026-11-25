"""技能包解析的领域规则。

## 抽出来的原因

`skill_library.parse_skill` 本身已经是"读一次 + 纯解析"（`parse_frontmatter` 早就是纯函数），
但**"按优先级找入口文件"这段逻辑重复了三处**（`parse_skill`、扫子目录、`discover`）：

    for name in _ENTRY_NAMES:
        if (root / name).is_file():
            ...

三份拷贝意味着"优先级顺序"有三个定义点 —— 哪天想把 `SKILL.MD` 提到最前面，
得记住改三处。收敛成一个函数，顺序只在一处。
"""

from __future__ import annotations

from typing import Callable, Sequence

__all__ = ["first_entry_name"]

#: 入口文件的候选名，**按优先级**排列（大写优先，兼容社区包的写法）
ENTRY_NAMES: tuple[str, ...] = ("SKILL.md", "skill.md", "Skill.md", "SKILL.MD")


def first_entry_name(candidates: Sequence[str], is_file: Callable[[str], bool]) -> str | None:
    """按优先级返回第一个存在的入口文件名；都不存在返回 `None`。

    `is_file` 注入而不是直接 `Path.is_file()`：调用方各自有基准目录，
    传入 `lambda n: (base / n).is_file()` 即可；这样本函数保持纯，可穷举测试。
    """
    for name in candidates:
        if is_file(name):
            return name
    return None
