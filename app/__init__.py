"""
AI_NovelWriter 应用包
从 novel_app.py 拆分出的独立模块
"""

import importlib
from pathlib import Path as _Path

# P3-1: 单一版本源。**顺序即优先级**：`pyproject.toml`（仓库声明的权威源）→
# 已安装分发元数据 → 构建时注入的常量（冻结 EXE 用）。
# ⚠️ 改版本号要同时改 `pyproject.toml`（权威源）与这里；
# `tests/test_version_consistency.py` 会断言两者、README 与 CHANGELOG 相互一致。
_FALLBACK_VERSION = "3.1.0"


def _load_version() -> str:
    """解析版本号。

    ⚠️ **为什么 pyproject 排第一，而不是已安装元数据**（2026-09-17 修正）：

    原实现先查 `importlib.metadata.version("ai-novel-writer")`。这在 CI 上出过事
    ——v3.1.0 的发布流水线里，pip 明明装的是 `ai-novel-writer==3.1.0`，
    `app.__version__` 却解析成 `'1.0.0'`（仓库里 `backend/*/app/__init__.py`
    也把自己标成 `1.0.0`），版本一致性门禁因此红，**发布作业被跳过、Release 没能建出来**。

    根因是这类实现的通病：**把"当前代码是什么版本"交给运行环境回答**。
    环境里只要存在任何一份同名分发元数据，就能覆盖真相；而这类失败完全静默
    （版本号是个字符串，没人会去校验它从哪来）。

    仓库已经把 `pyproject.toml` 定为唯一权威源，所以就该先读它：
    - 开发态 / editable 安装：读得到，且与源码同源；
    - 非 editable 安装：读不到 → 退到已安装元数据（这时它确实是可信来源）；
    - 冻结 EXE：两者都读不到 → 用 `_FALLBACK_VERSION`（构建时注入）。
    """
    try:
        import tomllib

        _pyproject = _Path(__file__).resolve().parent.parent / "pyproject.toml"
        with open(_pyproject, "rb") as _f:
            return tomllib.load(_f)["project"]["version"]
    except Exception:
        pass
    try:
        from importlib.metadata import version as _v

        return _v("ai-novel-writer")
    except Exception:
        pass
    return _FALLBACK_VERSION


__version__ = _load_version()


class _ImportStub:
    """安全导入占位类 - 在实例化时抛出明确的 ImportError"""

    _import_error = ""

    def __init__(self, *args, **kwargs):
        raise ImportError(
            f"Module not available (import failed: {self._import_error}). Please install missing dependencies."
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
