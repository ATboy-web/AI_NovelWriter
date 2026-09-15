"""工具面板混入模块"""
from .adapt_panel import AdaptPanelMixin
from .batch_ops_panel import BatchOpsPanelMixin
from .bridges_panel import BridgesPanelMixin
from .chapter_analysis_panel import ChapterAnalysisPanelMixin
from .descriptions_panel import DescriptionsPanelMixin
from .dialogue_panel import DialoguePanelMixin
from .elements_panel import ElementsPanelMixin
from .memory_viz_panel import MemoryVizPanelMixin
from .story_flow_panel import StoryFlowPanelMixin
from .style_panel import StylePanelMixin
from .summary_mgmt_panel import SummaryMgmtPanelMixin
from .websearch_panel import WebSearchPanelMixin

__all__ = [
    "ElementsPanelMixin",
    "BridgesPanelMixin",
    "DescriptionsPanelMixin",
    "DialoguePanelMixin",
    "StoryFlowPanelMixin",
    "StylePanelMixin",
    "AdaptPanelMixin",
    "WebSearchPanelMixin",
    "MemoryVizPanelMixin",
    "SummaryMgmtPanelMixin",
    "BatchOpsPanelMixin",
    "ChapterAnalysisPanelMixin",
]
