"""面板注册表（v3 §2.2）。

## 它替代了什么

v2 新增一个面板要改 **5 处**：新建文件 + `panels/__init__.py` + `novel_app.py`（import + 继承列表）
+ `shell_ui.py:577` 的 Radiobutton 列表 + `toolkit_ui.py:26` 的 `elif` 链。
其中 3 处是"同一份信息的重复登记"，漏改一处的后果是**静默失灵**
（面板能建出来，但选择器上没有它；或选了没反应）。

v3 之后新增面板只有 **1 处改动**：新建面板文件 + 在 `NATIVE_PANEL_MODULES` 加一行。
分发层（`toolkit_ui` / `shell_ui`）只读注册表，不再硬编码任何面板键。

## 注册动作有两个入口，但都汇聚到同一个幂等的 `register()`

1. `BasePanel.__init_subclass__` —— 类定义时自动登记（面板文件被导入即生效）
2. `load_panels()` 的显式扫描 —— 保证 `force=True` 重载与"类已存在但注册表被清空"
   （测试里的 `reset_registry()`）两种情况都能恢复
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from .base import BasePanel

__all__ = [
    "CATEGORY_ORDER",
    "DEFAULT_CATEGORY",
    "NATIVE_PANEL_MODULES",
    "PANEL_REGISTRY",
    "PanelSpec",
    "all_panels",
    "categories",
    "create",
    "default_key",
    "get",
    "grouped",
    "load_panels",
    "register",
    "reset_registry",
]

#: 分组显示顺序。未列入的分组排在最后（按首次出现顺序）。
CATEGORY_ORDER: tuple[str, ...] = (
    "创作素材",
    "结构分析",
    "记忆与摘要",
    "世界与世代",
    "运维",
)

#: 面板未声明分组时的归属
DEFAULT_CATEGORY = "运维"

#: v3 原生面板（`BasePanel` 子类）所在模块。
#: 🚧 新增面板只需在这里加一行 —— 这是 v3「新增面板只需 1 处改动」的兑现点。
NATIVE_PANEL_MODULES: tuple[str, ...] = (
    # P4b 将在此追加：世界线与时间线 / 角色传记 / 世代传承
)


@dataclass(frozen=True)
class PanelSpec:
    """一条面板登记项（不可变，可安全共享/缓存）。"""

    key: str
    title: str
    category: str
    order: int
    panel_cls: type
    description: str = ""
    source: str = field(default="", compare=False)

    @property
    def legacy(self) -> bool:
        """是否为 v2 迁移面板（迁移面板的 on_show 会重建内容，见 legacy.py）。"""
        return bool(getattr(self.panel_cls, "legacy_migration", False))


#: key -> PanelSpec。顺序不承载语义（排序由 `all_panels()` 负责）
PANEL_REGISTRY: dict[str, PanelSpec] = {}

_LOADED = False


# ---------------------------------------------------------------------- 注册


def register(panel_cls: type) -> PanelSpec:
    """登记一个面板类。**幂等**：同一个类重复登记是安全的（返回既有 spec）。

    同一个 `key` 被**两个不同类**占用则直接抛错 —— 与其让选择器出现两个同名项
    或后注册者静默顶掉前注册者，不如在启动时就响亮失败。
    """
    key = getattr(panel_cls, "key", "")
    if not key:
        raise ValueError(f"{panel_cls.__name__} 缺少 key，无法登记为面板")

    existing = PANEL_REGISTRY.get(key)
    if existing is not None:
        if existing.panel_cls is panel_cls:
            return existing
        raise ValueError(
            f"面板 key '{key}' 重复：{existing.panel_cls.__module__}.{existing.panel_cls.__name__} "
            f"与 {panel_cls.__module__}.{panel_cls.__name__} 冲突"
        )

    spec = PanelSpec(
        key=key,
        title=getattr(panel_cls, "title", "") or key,
        category=getattr(panel_cls, "category", "") or DEFAULT_CATEGORY,
        order=int(getattr(panel_cls, "order", 100)),
        panel_cls=panel_cls,
        description=getattr(panel_cls, "description", "") or "",
        # 迁移适配器是动态生成的类，其 `__module__` 是 legacy 模块本身；
        # `source_module` 才是"这个面板真正来自哪个文件"的可诊断信息。
        source=getattr(panel_cls, "source_module", "") or getattr(panel_cls, "__module__", ""),
    )
    PANEL_REGISTRY[key] = spec
    return spec


def _register_module_panels(module: Any) -> int:
    """把某个模块内定义的 `BasePanel` 子类全部登记（`load_panels` 用）。"""
    from .base import BasePanel

    count = 0
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, BasePanel)
            and getattr(obj, "key", "")
            and obj.__module__ == module.__name__
        ):
            register(obj)
            count += 1
    return count


def load_panels(force: bool = False) -> list[PanelSpec]:
    """导入并登记全部面板。返回排序后的面板列表。

    面板模块导入失败**不阻断**应用启动（只记 error 并跳过该面板）——
    一个坏面板不该让整个创作工坊起不来；但测试会断言面板数量，坏模块跑不过 CI。
    """
    global _LOADED
    if _LOADED and not force:
        return all_panels()

    from . import legacy

    legacy.register_legacy_panels()

    for module_name in NATIVE_PANEL_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception as e:  # noqa: BLE001 - 单个面板坏掉不应拖垮应用
            logger.error(f"面板模块 {module_name} 导入失败，该面板本次不可用: {type(e).__name__}: {e}")
            continue
        _register_module_panels(module)

    _LOADED = True
    return all_panels()


def reset_registry() -> None:
    """清空注册表（仅供测试）。"""
    global _LOADED
    PANEL_REGISTRY.clear()
    _LOADED = False


# ---------------------------------------------------------------------- 查询


def get(key: str) -> PanelSpec | None:
    return PANEL_REGISTRY.get(key)


def all_panels() -> list[PanelSpec]:
    """按「分组顺序 → order → 标题」排序后的全部面板。"""
    order_index = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    return sorted(
        PANEL_REGISTRY.values(),
        key=lambda s: (order_index.get(s.category, len(CATEGORY_ORDER)), s.order, s.title),
    )


def categories() -> list[str]:
    """当前有面板的分组（已按 `CATEGORY_ORDER` 排序）。"""
    seen: list[str] = []
    for spec in all_panels():
        if spec.category not in seen:
            seen.append(spec.category)
    return seen


def grouped() -> list[tuple[str, list[PanelSpec]]]:
    """`[(分组名, [面板...]), ...]`，供选择器渲染分组小标题。"""
    buckets: dict[str, list[PanelSpec]] = {}
    for spec in all_panels():
        buckets.setdefault(spec.category, []).append(spec)
    return [(name, buckets[name]) for name in categories()]


def default_key() -> str:
    """默认激活的面板键（排序后的第一个）。注册表为空时返回 `""`。"""
    panels = all_panels()
    return panels[0].key if panels else ""


def create(key: str, app: Any) -> BasePanel:
    """按 key 实例化面板。未知 key 抛 `KeyError`（调用方应先 `get()` 判断）。"""
    spec = PANEL_REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"未登记的面板 key: {key!r}（已登记: {sorted(PANEL_REGISTRY)}）")
    return spec.panel_cls(app)
