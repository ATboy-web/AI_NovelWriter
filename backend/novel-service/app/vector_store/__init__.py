"""
向量数据库模块
"""

from .vector_manager import (
    VectorStoreManager,
    add_chapter_to_vector_store,
    get_chapter_context,
    get_vector_store_manager,
    search_novel_content,
)

__all__ = [
    "VectorStoreManager",
    "get_vector_store_manager",
    "add_chapter_to_vector_store",
    "search_novel_content",
    "get_chapter_context"
]
