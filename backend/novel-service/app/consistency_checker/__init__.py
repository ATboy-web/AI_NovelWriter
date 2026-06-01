"""
一致性审校模块
"""

from .consistency_checker import (
    ConsistencyChecker,
    ConflictType,
    ConflictSeverity,
    get_consistency_checker,
    check_chapter_consistency
)

__all__ = [
    "ConsistencyChecker",
    "ConflictType",
    "ConflictSeverity",
    "get_consistency_checker",
    "check_chapter_consistency"
]