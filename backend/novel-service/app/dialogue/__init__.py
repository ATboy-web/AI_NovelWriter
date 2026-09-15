"""
情景对话推演模块
"""

from .dialogue_manager import (
    DialogueManager,
    DialogueStyle,
    DialogueType,
    continue_dialogue,
    generate_dialogue,
    get_dialogue_manager,
)

__all__ = [
    "DialogueManager",
    "DialogueStyle",
    "DialogueType",
    "get_dialogue_manager",
    "generate_dialogue",
    "continue_dialogue"
]
