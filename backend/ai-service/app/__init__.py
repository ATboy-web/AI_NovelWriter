"""
AI模型服务应用包
"""

import os as _os
import sys as _sys

# P2-3: 让服务能定位到共享包 backend/shared（本地开发）或 /app/shared（Docker 镜像）
_APP_DIR = _os.path.dirname(_os.path.abspath(__file__))
_SVC_DIR = _os.path.dirname(_APP_DIR)
for _cand in (
    _os.path.join(_SVC_DIR, "shared"),
    _os.path.join(_os.path.dirname(_SVC_DIR), "shared"),
):
    if _os.path.isdir(_cand):
        if _cand not in _sys.path:
            _sys.path.insert(0, _cand)
        break

__version__ = "1.0.0"
__author__ = "AI Novel Writer Team"

from .main import app

__all__ = ["app"]