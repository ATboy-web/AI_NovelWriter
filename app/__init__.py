"""
AI_NovelWriter 应用包
从 novel_app.py 拆分出的独立模块
"""

from .config import AppConfig
from .ai_client import AIClient
from .image_generator import ImageGenerator
from .scene_detector import SceneDetector
from .memory_manager import MemoryManager
from .note_manager import NoteManager
from .fullscreen_writer import FullscreenWriter
from .novel_agent import NovelAgent
from .reading_manager import ReadingManager
from .ui_style import UIStyle

__all__ = [
    "AppConfig",
    "AIClient", 
    "ImageGenerator",
    "SceneDetector",
    "MemoryManager",
    "NoteManager",
    "FullscreenWriter",
    "NovelAgent",
    "ReadingManager",
    "UIStyle",
]
