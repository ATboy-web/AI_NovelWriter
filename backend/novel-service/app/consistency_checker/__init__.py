"""
一致性审校模块
"""

from .consistency_checker import (
    ConflictSeverity,
    ConflictType,
    ConsistencyChecker,
    check_chapter_consistency,
    get_consistency_checker,
)

__all__ = [
    "ConsistencyChecker",
    "ConflictType",
    "ConflictSeverity",
    "get_consistency_checker",
    "check_chapter_consistency"
]
