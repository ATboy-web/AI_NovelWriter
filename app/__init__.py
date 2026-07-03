"""
AI_NovelWriter 应用包
从 novel_app.py 拆分出的独立模块
"""
import importlib
import sys


class _ImportStub:
    """安全导入占位类 - 在实例化时抛出明确的 ImportError"""
    _import_error = ""
    
    def __init__(self, *args, **kwargs):
        raise ImportError(
            f"Module not available (import failed: {self._import_error}). "
            "Please install missing dependencies."
        )


# 安全导入：避免缺失可选依赖时整个包导入失败
def _safe_import(module_name: str, class_name: str):
    """安全导入，失败时返回占位类型（实例化时会报错）"""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        import warnings
        warnings.warn(f"Failed to import {class_name} from {module_name}: {e}")
        # 创建占位类型，实例化时报错而非静默失败
        return type(class_name, (_ImportStub,), {"_import_error": str(e)})

# 核心模块（必须可用）
from .config import AppConfig
from .ai_client import AIClient, token_stats
from .writing_skills import writing_skill_manager

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
    "token_stats",
    "writing_skill_manager",
    "ImageGenerator",
    "SceneDetector",
    "MemoryManager",
    "NoteManager",
    "FullscreenWriter",
    "NovelAgent",
    "ReadingManager",
    "UIStyle",
]
