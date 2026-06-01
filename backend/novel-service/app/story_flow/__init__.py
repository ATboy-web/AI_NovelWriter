"""
故事流推演模块
"""

from .story_flow_manager import (
    StoryFlowManager,
    FlowType,
    EventType,
    get_story_flow_manager,
    generate_story_flow,
    generate_branching_scenarios,
    generate_conflict_escalation
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