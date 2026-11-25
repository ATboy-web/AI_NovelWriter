"""风格指纹的领域规则（命名等纯逻辑）。

`style_dna.learn_from_novel` 的统计部分早已在 `learn_from_texts`（纯函数）里，
剩下的纯逻辑只有"从目录名推导显示名"这一小段 —— 但它是**有边界的分支**
（时间戳后缀、超长截断、空名回落），值得单独测。
"""

from __future__ import annotations

import re

__all__ = ["derive_display_name"]

#: 作品目录名尾部的下单时间戳，如 `书名_1781862528`
_TIMESTAMP_SUFFIX = re.compile(r"_\d{6,}$")

#: 显示名最大长度（超出用省略号；再长在面板上会挤掉其他信息）
MAX_DISPLAY_NAME = 24


def derive_display_name(dir_name: str, fallback: str = "本书") -> str:
    """从作品目录名推导一个可用于展示的名字。

    三种处理：
    - 去掉尾部时间戳（`重生之岛_1781862528` → `重生之岛`）
    - 超长截断到 24 字并加省略号
    - 全空回落 `fallback`（目录名可能只有时间戳）
    """
    raw = _TIMESTAMP_SUFFIX.sub("", (dir_name or "").strip())
    if not raw:
        return fallback
    if len(raw) > MAX_DISPLAY_NAME:
        return raw[:MAX_DISPLAY_NAME] + "…"
    return raw
