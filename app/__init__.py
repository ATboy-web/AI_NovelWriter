"""
AI_NovelWriter 应用包
从 novel_app.py 拆分出的独立模块
"""
import importlib
from pathlib import Path as _Path

# P3-1: 单一版本源。优先读取已安装包元数据，其次读取 pyproject.toml，
# 冻结(EXE)环境下回退到构建时注入的常量。
_FALLBACK_VERSION = "2.16.0"


def _load_version() -> str:
    try:
        from importlib.metadata import version as _v
        return _v("ai-novel-writer")
    except Exception:
        pass
    try:
        import tomllib
        _pyproject = _Path(__file__).resolve().parent.parent / "pyproject.toml"
        with open(_pyproject, "rb") as _f:
            return tomllib.load(_f)["project"]["version"]
    except Exception:
        pass
    return _FALLBACK_VERSION


__version__ = _load_version()


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
from .ai_client import AIClient, token_stats
from .config import AppConfig
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
    "__version__",
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
