"""面板布局的可配置状态：**分栏** 与 **停靠记忆**。

## 它解决什么

v3.1.0 之前，创作工具页只有"一块内容区 + 一次显示一个面板"这一个形态，
而且**每次启动都回到默认面板**。对实际写作来说这有两个具体的不便：

1. 写正文时要反复在"章节分析"和"记忆可视化"之间来回切 —— 两个面板本可以并排看；
2. 调好/脱出的面板，关掉应用就全忘了，下次要重新摆一遍。

所以本模块只负责**布局这件事本身的数据**：什么模式、哪两个面板、分隔条在哪、
哪些面板已脱出为独立窗口。它**不碰 Tk**（便于单测），也**不写任何业务逻辑**。

## 持久化的两条纪律

1. **损坏不得阻断启动**：布局是"锦上添花"的状态，读不出来就用默认值，
   绝不让用户因为一个坏的 JSON 打不开应用（与 `AppConfig` 的敏感字段不同，
   这里没有任何数据值得为它冒险）。
2. **落地前必须 `sanitize`**：面板 key 会随版本变化（重命名、删除），
   而布局文件是**跨版本**存在的。不校验就会出现"记忆了一个不存在的面板"
   —— 表现为启动后空栏或报错。所以恢复时一律先按当前注册表洗一遍。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "MODE_SINGLE",
    "MODE_SPLIT",
    "PanelLayout",
    "default_path",
    "load",
    "save",
]

MODE_SINGLE = "single"
MODE_SPLIT = "split"
MODES = (MODE_SINGLE, MODE_SPLIT)

#: 分隔条的合法范围 —— 任一侧都不允许被拖到消失（否则用户会以为面板没了）
MIN_RATIO = 0.15
MAX_RATIO = 0.85

#: 侧栏最小宽度（像素）：太窄时面板里的表格会挤成一条
MIN_PANE_WIDTH = 220


def default_path() -> Path:
    """布局文件位置（与 `AppConfig` 同目录，但**独立文件**）。

    为什么独立：配置文件走的是"敏感字段加密 + 多 Profile 迁移"的重逻辑，
    而布局是随时可重建的界面状态。混进去只会让两边都更脆。
    """
    return Path.home() / ".ai_novel_writer" / "panel_layout.json"


@dataclass
class PanelLayout:
    """当前布局（不可变语义，改布局请用 `panel_host` 的方法）。"""

    mode: str = MODE_SINGLE
    #: 主栏面板 key（单栏模式下就是唯一显示的那个）
    primary: str = ""
    #: 副栏面板 key（仅分栏模式有意义）
    secondary: str = ""
    #: 主栏宽度占比
    ratio: float = 0.5
    #: 已脱出为独立窗口的面板 key（"停靠记忆"）
    popped_out: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ 序列化

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "primary": self.primary,
            "secondary": self.secondary,
            "ratio": round(float(self.ratio), 4),
            "popped_out": list(self.popped_out),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "PanelLayout":
        """尽力解析；任何字段缺失/类型不对都退回默认值（**不抛异常**）。"""
        if not isinstance(data, dict):
            return cls()
        layout = cls()
        mode = data.get("mode")
        layout.mode = mode if isinstance(mode, str) and mode in MODES else MODE_SINGLE
        for name in ("primary", "secondary"):
            value = data.get(name)
            setattr(layout, name, value if isinstance(value, str) else "")
        try:
            layout.ratio = float(data.get("ratio", layout.ratio))
        except (TypeError, ValueError):
            layout.ratio = 0.5
        popped = data.get("popped_out")
        if isinstance(popped, list):
            layout.popped_out = [item for item in popped if isinstance(item, str)]
        return layout

    # ------------------------------------------------------------------ 校验

    def sanitize(self, available: Iterable[str]) -> "PanelLayout":
        """按**当前**可用的面板 key 洗一遍，返回新的布局。

        规则（都有明确理由，不是"顺手加的防御"）：

        - 已脱出的面板去重、且必须仍然存在；
        - 副栏面板必须存在、且不能与主栏相同，也不能是已脱出的那个
          （同一面板同时"在右栏"和"在独立窗口"是自相矛盾的状态）；
        - 上述任一不成立 ⇒ **分栏降级为单栏**，而不是硬留一个空栏；
        - `ratio` 夹到 `[MIN_RATIO, MAX_RATIO]`；
        - `primary` 不在可用集合里 ⇒ 交给宿主按默认面板兜底（此处清空）。
        """
        keys = list(dict.fromkeys(available))
        known = set(keys)
        popped = list(dict.fromkeys(item for item in self.popped_out if item in known))

        primary = self.primary if self.primary in known else ""
        secondary = self.secondary
        if secondary not in known or secondary in (primary, *popped) or not secondary:
            secondary = ""

        mode = self.mode
        if mode == MODE_SPLIT and not secondary:
            mode = MODE_SINGLE

        return PanelLayout(
            mode=mode,
            primary=primary,
            secondary=secondary,
            ratio=min(MAX_RATIO, max(MIN_RATIO, float(self.ratio))),
            popped_out=popped,
        )

    def copy(self, **changes: Any) -> "PanelLayout":
        """派生一份改了几个字段的新布局（测试与宿主都用它，避免就地改）。"""
        data = self.to_dict()
        data.update(changes)
        return PanelLayout.from_dict(data)


# ---------------------------------------------------------------------- 读写


def load(path: Path | None = None) -> PanelLayout:
    """读取布局；不存在/损坏/无权限一律返回默认值（**不抛异常**）。"""
    target = path or default_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            return PanelLayout.from_dict(json.load(handle))
    except (OSError, ValueError):
        return PanelLayout()


def save(layout: PanelLayout, path: Path | None = None) -> bool:
    """原子写入布局，返回是否成功。

    ⚠️ 刻意**不抛异常**：保存布局失败（磁盘满、权限）不应该让用户的写作流程中断 ——
    大不了下次启动回到默认布局。
    """
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        from app.storage import atomic_write_json

        atomic_write_json(target, layout.to_dict())
        return True
    except Exception:  # noqa: BLE001 - 布局是"锦上添花"，任何失败都不该影响主流程
        return False
