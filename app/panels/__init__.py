"""工具面板混入模块 + v3 面板框架。

v2 的 12 个 `*PanelMixin` 仍在此转出（它们由 `legacy.LegacyPanelAdapter` 适配进新框架，
面板内代码一行未改）。v3 的面板框架四件套也在此转出，调用方不必知道内部布局。
"""

from .adapt_panel import AdaptPanelMixin
from .base import BasePanel
from .batch_ops_panel import BatchOpsPanelMixin
from .biography_panel import BiographyPanel
from .bridges_panel import BridgesPanelMixin
from .chapter_analysis_panel import ChapterAnalysisPanelMixin
from .descriptions_panel import DescriptionsPanelMixin
from .dialogue_panel import DialoguePanelMixin
from .elements_panel import ElementsPanelMixin
from .host import PanelHost
from .legacy import LegacyPanelAdapter, register_legacy_panels
from .lineage_panel import LineagePanel
from .memory_viz_panel import MemoryVizPanelMixin
from .registry import (
    NATIVE_PANEL_MODULES,
    PANEL_REGISTRY,
    PanelSpec,
    all_panels,
    create,
    default_key,
    get,
    grouped,
    load_panels,
    register,
)
from .story_flow_panel import StoryFlowPanelMixin
from .style_panel import StylePanelMixin
from .summary_mgmt_panel import SummaryMgmtPanelMixin
from .timeline_panel import TimelinePanel
from .websearch_panel import WebSearchPanelMixin

__all__ = [
    # ---- v3 面板框架
    "BasePanel",
    "LegacyPanelAdapter",
    "NATIVE_PANEL_MODULES",
    "PANEL_REGISTRY",
    "PanelHost",
    "PanelSpec",
    "all_panels",
    "create",
    "default_key",
    "get",
    "grouped",
    "load_panels",
    "register",
    "register_legacy_panels",
    # ---- v3 原生面板（P4b）
    "BiographyPanel",
    "LineagePanel",
    "TimelinePanel",
    # ---- v2 面板 Mixin（由 legacy 适配器驱动）
    "AdaptPanelMixin",
    "BatchOpsPanelMixin",
    "BridgesPanelMixin",
    "ChapterAnalysisPanelMixin",
    "DescriptionsPanelMixin",
    "DialoguePanelMixin",
    "ElementsPanelMixin",
    "MemoryVizPanelMixin",
    "StoryFlowPanelMixin",
    "StylePanelMixin",
    "SummaryMgmtPanelMixin",
    "WebSearchPanelMixin",
]
