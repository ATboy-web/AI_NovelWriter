"""
情景对话推演模块
"""

from .dialogue_manager import (
    DialogueManager,
    DialogueStyle,
    DialogueType,
    get_dialogue_manager,
    generate_dialogue,
    continue_dialogue
)

__all__ = [
    "DialogueManager",
    "DialogueStyle",
    "DialogueType",
    "get_dialogue_manager",
    "generate_dialogue",
    "continue_dialogue"
]