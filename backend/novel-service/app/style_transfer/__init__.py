"""
风格转换模块
"""

from .style_transfer_manager import (
    StyleTransferManager,
    StyleType,
    TransferMode,
    get_style_transfer_manager,
    analyze_style,
    transfer_style,
    imitate_author_style,
    adapt_to_genre
)

__all__ = [
    "StyleTransferManager",
    "StyleType",
    "TransferMode",
    "get_style_transfer_manager",
    "analyze_style",
    "transfer_style",
    "imitate_author_style",
    "adapt_to_genre"
]