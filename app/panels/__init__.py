"""工具面板混入模块"""
from .elements_panel import ElementsPanelMixin
from .bridges_panel import BridgesPanelMixin
from .descriptions_panel import DescriptionsPanelMixin
from .dialogue_panel import DialoguePanelMixin
from .story_flow_panel import StoryFlowPanelMixin
from .style_panel import StylePanelMixin
from .adapt_panel import AdaptPanelMixin
from .websearch_panel import WebSearchPanelMixin
from .memory_viz_panel import MemoryVizPanelMixin
from .summary_mgmt_panel import SummaryMgmtPanelMixin
from .batch_ops_panel import BatchOpsPanelMixin
from .chapter_analysis_panel import ChapterAnalysisPanelMixin

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
