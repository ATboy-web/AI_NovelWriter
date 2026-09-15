"""
故事流推演模块
"""

from .story_flow_manager import (
    EventType,
    FlowType,
    StoryFlowManager,
    generate_branching_scenarios,
    generate_conflict_escalation,
    generate_story_flow,
    get_story_flow_manager,
)

__all__ = [
    "StoryFlowManager",
    "FlowType",
    "EventType",
    "get_story_flow_manager",
    "generate_story_flow",
    "generate_branching_scenarios",
    "generate_conflict_escalation"
]
