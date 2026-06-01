"""
定稿管理模块
"""

from .finalization_manager import (
    FinalizationManager,
    ChapterStatus,
    get_finalization_manager,
    finalize_chapter
)

__all__ = [
    "FinalizationManager",
    "ChapterStatus",
    "get_finalization_manager",
    "finalize_chapter"
]