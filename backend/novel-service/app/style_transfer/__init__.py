"""
风格转换模块
"""

from .style_transfer_manager import (
    StyleTransferManager,
    StyleType,
    TransferMode,
    adapt_to_genre,
    analyze_style,
    get_style_transfer_manager,
    imitate_author_style,
    transfer_style,
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
