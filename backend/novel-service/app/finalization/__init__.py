"""
定稿管理模块
"""

from .finalization_manager import ChapterStatus, FinalizationManager, finalize_chapter, get_finalization_manager

__all__ = [
    "FinalizationManager",
    "ChapterStatus",
    "get_finalization_manager",
    "finalize_chapter"
]
