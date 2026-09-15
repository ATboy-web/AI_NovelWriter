"""
角色桥段库模块
"""

from .bridge_manager import (
    BridgeCategory,
    BridgeManager,
    BridgeTone,
    combine_bridges,
    generate_bridge,
    generate_bridge_with_variation,
    get_bridge_manager,
    search_bridges,
)

__all__ = [
    "BridgeManager",
    "BridgeCategory",
    "BridgeTone",
    "get_bridge_manager",
    "generate_bridge",
    "combine_bridges",
    "generate_bridge_with_variation",
    "search_bridges"
]
