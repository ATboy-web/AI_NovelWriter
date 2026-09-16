"""迁移适配器（v3 §2.2）：把 v2 的 `_build_<key>_tool()` 原样包成 `BasePanel`。

## 为什么不是"重写 12 个面板"

12 个 v2 面板合计约 2400 行，功能都验证过。把它们逐个改写成 `BasePanel` 子类，
收益只是"代码好看"，代价是 12 次独立的行为回归风险 —— 不值得。
适配器让它们**一行不改**地进入新框架，行为由测试锁定。

## 适配器必须处理的三件事

1. **容器私有化**：v2 所有面板都往 `self.tool_content_frame` 里画。适配器在 `build()`
   时把该名字指向**本面板自己的 Frame**（`LOCAL_ATTRS` 已声明其不代理给宿主），
   否则 15 个面板会全部画进同一个容器、互相覆盖。

2. **写入仍落在宿主身上**：v2 面板写 `self.elem_result = Text(...)`、
   `self.current_chapter = n`，`self` 就是应用。适配器打开 `proxy_writes`，
   让这些写入与 v2 落在**同一个对象**上，回调（绑定在应用上的方法）才能读到它们。

   ⚠️ 由此带来一条**与 v2 完全一致**的约束：`self.x += 1` 这类"先读后写"要求
   宿主持有 `x`。读取走代理（面板 → 宿主），宿主上也没有就直接 `AttributeError`。
   v2 的 `NovelWriterApp.__init__` 之所以预置了 `dialogue_engine = None`、
   `story_flow_engine = None`、`adapt_engine = None` 等一长串单例属性，
   正是为了让面板能这样读写；迁移后这些预置**不能删**。

3. **切换即重建**：v2 的 `_refresh_toolkit()` 每次选择都销毁全部子控件再重建，
   于是面板的状态是"每次进来都是新的"。适配器把这件事放进 `on_show()`，
   保持既有观感与数据新鲜度。
"""

from __future__ import annotations

import importlib
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

from loguru import logger

from .base import BasePanel
from .registry import register

__all__ = [
    "LEGACY_PANEL_SPECS",
    "LegacyPanelAdapter",
    "LegacyPanelSpec",
    "register_legacy_panels",
]


@dataclass(frozen=True)
class LegacyPanelSpec:
    """一条 v2 面板的迁移登记。"""

    key: str
    title: str
    category: str
    order: int
    module: str
    mixin: str
    build: str
    migration_note: str = ""


#: v2 的 12 个工具面板（原本散落在 `toolkit_ui` 的 elif 链与 `shell_ui` 的 Radiobutton 列表里）
LEGACY_PANEL_SPECS: tuple[LegacyPanelSpec, ...] = (
    # ---- 创作素材（喂给 AI 的"原料"类工具）
    LegacyPanelSpec("elements", "元素库", "创作素材", 10,
                    "app.panels.elements_panel", "ElementsPanelMixin", "_build_elements_tool"),
    LegacyPanelSpec("bridges", "桥段库", "创作素材", 20,
                    "app.panels.bridges_panel", "BridgesPanelMixin", "_build_bridges_tool"),
    LegacyPanelSpec("descriptions", "描写库", "创作素材", 30,
                    "app.panels.descriptions_panel", "DescriptionsPanelMixin", "_build_descriptions_tool"),
    LegacyPanelSpec("dialogue", "对话推演", "创作素材", 40,
                    "app.panels.dialogue_panel", "DialoguePanelMixin", "_build_dialogue_tool"),
    LegacyPanelSpec("style", "风格转换", "创作素材", 50,
                    "app.panels.style_panel", "StylePanelMixin", "_build_style_tool"),
    LegacyPanelSpec("adapt", "智能改编", "创作素材", 60,
                    "app.panels.adapt_panel", "AdaptPanelMixin", "_build_adapt_tool"),
    LegacyPanelSpec("websearch", "热点改编", "创作素材", 70,
                    "app.panels.websearch_panel", "WebSearchPanelMixin", "_build_websearch_tool"),
    # ---- 结构分析（读已有文本做诊断/推演）
    LegacyPanelSpec("story_flow", "故事流", "结构分析", 10,
                    "app.panels.story_flow_panel", "StoryFlowPanelMixin", "_build_story_flow_tool"),
    LegacyPanelSpec("chapters", "章节分析", "结构分析", 20,
                    "app.panels.chapter_analysis_panel", "ChapterAnalysisPanelMixin",
                    "_build_chapter_analysis_tool"),
    # ---- 记忆与摘要
    LegacyPanelSpec("memory_viz", "记忆可视化", "记忆与摘要", 10,
                    "app.panels.memory_viz_panel", "MemoryVizPanelMixin", "_build_memory_viz_tool"),
    LegacyPanelSpec("summary_mgmt", "摘要管理", "记忆与摘要", 20,
                    "app.panels.summary_mgmt_panel", "SummaryMgmtPanelMixin", "_build_summary_mgmt_tool"),
    # ---- 运维
    LegacyPanelSpec("batch_ops", "批量操作", "运维", 10,
                    "app.panels.batch_ops_panel", "BatchOpsPanelMixin", "_build_batch_ops_tool"),
)


class LegacyPanelAdapter(BasePanel):
    """v2 面板的宿主适配器基类。

    本类自身不带 `key`，因此不会被登记；真正的适配器由 `_make_adapter_class()`
    按需生成子类（带 key 的类会自动进入注册表）。
    """

    #: 标记：本面板是迁移来的（`registry.PanelSpec.legacy` 据此判断）
    legacy_migration: ClassVar[bool] = True

    #: ⚠️ 迁移的**核心**：属性写入转发给宿主，见模块文档第 2 条
    proxy_writes: ClassVar[bool] = True

    #: 由动态子类填成"未绑定的 `_build_xxx_tool` 函数"
    _legacy_build_func: ClassVar[Callable[[Any], None] | None] = None

    # ---------------------------------------------------------------- 生命周期

    def build(self, parent: tk.Widget) -> tk.Widget:
        """绑定本面板的私有容器并渲染一次。"""
        # `tool_content_frame` 在 LOCAL_ATTRS 里，故这一行落在面板自己身上（不代理给宿主）
        self.tool_content_frame = parent
        self._render()
        self.mark_built(True)
        return parent

    def on_show(self) -> None:
        """切换回来时重建内容 —— 与 v2「每次选择都销毁重建」的观感一致。"""
        if self.is_built:
            self._render()

    def _render(self) -> None:
        """清空私有容器后重跑 v2 的构建方法。"""
        frame = self.__dict__.get("tool_content_frame")
        func = type(self)._legacy_build_func
        if frame is None or func is None:
            logger.warning(f"迁移面板 {self.key!r} 未就绪（容器或构建方法缺失），跳过渲染")
            return
        for child in frame.winfo_children():
            child.destroy()
        # 关键：以**适配器自身**作为 self 调用 v2 的构建函数。
        # 读取走代理（先查面板、再查宿主），写入按 proxy_writes 落到宿主 —— 与 v2 逐字节等价。
        func(self)


_ADAPTER_CLASSES: dict[str, type[LegacyPanelAdapter]] = {}


def _make_adapter_class(spec: LegacyPanelSpec) -> type[LegacyPanelAdapter]:
    """为一个 v2 面板生成适配器子类（结果缓存，保证注册表条目稳定）。"""
    cached = _ADAPTER_CLASSES.get(spec.key)
    if cached is not None:
        return cached

    module = importlib.import_module(spec.module)
    mixin_cls = getattr(module, spec.mixin)
    build_func = getattr(mixin_cls, spec.build)

    adapter = type(
        f"{spec.mixin.removesuffix('Mixin')}LegacyPanel",
        (LegacyPanelAdapter,),
        {
            "key": spec.key,
            "title": spec.title,
            "category": spec.category,
            "order": spec.order,
            "description": spec.migration_note or f"v2 面板 {spec.mixin}.{spec.build}() 迁移而来",
            # 登记表里显示"这个面板来自哪个文件"（动态类的 __module__ 是本模块，不具信息量）
            "source_module": spec.module,
            "__doc__": f"v2 `{spec.module}.{spec.mixin}` 的适配器（构建方法 `{spec.build}()`）。",
            "_legacy_build_func": staticmethod(build_func),
        },
    )
    _ADAPTER_CLASSES[spec.key] = adapter
    return adapter


def register_legacy_panels() -> list[type[LegacyPanelAdapter]]:
    """装配并登记 12 个 v2 面板。幂等（`load_panels(force=True)` 可安全重复调用）。"""
    registered: list[type[LegacyPanelAdapter]] = []
    for spec in LEGACY_PANEL_SPECS:
        try:
            adapter = _make_adapter_class(spec)
        except (ImportError, AttributeError) as e:
            logger.error(f"迁移面板 {spec.key} 装配失败（该面板本次不可用）: {type(e).__name__}: {e}")
            continue
        # 类创建时 `BasePanel.__init_subclass__` 已自动登记；此处显式调用是为了
        # `reset_registry()` 之后仍能恢复（register 对同一个类是幂等的）。
        register(adapter)
        registered.append(adapter)
    return registered
