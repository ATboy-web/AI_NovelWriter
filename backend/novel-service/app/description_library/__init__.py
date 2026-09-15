"""
事物描写库模块
"""

from .description_manager import (
    DescriptionCategory,
    DescriptionManager,
    DescriptionStyle,
    enhance_description,
    generate_description,
    generate_scene_description,
    get_description_manager,
    search_descriptions,
)

__all__ = [
    "DescriptionManager",
    "DescriptionCategory",
    "DescriptionStyle",
    "get_description_manager",
    "generate_description",
    "generate_scene_description",
    "enhance_description",
    "search_descriptions"
]
