"""
AI_NovelWriter 应用包
从 novel_app.py 拆分出的独立模块
"""
import importlib
import sys

# 安全导入：避免缺失可选依赖时整个包导入失败
def _safe_import(module_name: str, class_name: str):
    """安全导入，失败时返回占位类型"""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        import warnings
        warnings.warn(f"Failed to import {class_name} from {module_name}: {e}")
        # 返回一个占位类型，避免 NameError
        return type(class_name, (), {"__init__": lambda self, *a, **kw: None,
                                       "_import_error": str(e)})

# 核心模块（必须可用）
from .config import AppConfig
from .ai_client import AIClient

# 可选/条件导入的模块
ImageGenerator = _safe_import("app.image_generator", "ImageGenerator")
SceneDetector = _safe_import("app.scene_detector", "SceneDetector")
MemoryManager = _safe_import("app.memory_manager", "MemoryManager")
NoteManager = _safe_import("app.note_manager", "NoteManager")
FullscreenWriter = _safe_import("app.fullscreen_writer", "FullscreenWriter")
NovelAgent = _safe_import("app.novel_agent", "NovelAgent")
ReadingManager = _safe_import("app.reading_manager", "ReadingManager")
UIStyle = _safe_import("app.ui_style", "UIStyle")

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
