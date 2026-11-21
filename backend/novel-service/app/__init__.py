"""
小说生成服务应用包
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
        # 同时加入 shared 自身（兼容 `from middleware import ...` 的旧式导入）
        # 与其父目录（支持 `from shared.api_errors import ...` 的包式导入）。
        # 只加 shared 自身会让包式导入在独立启动服务时失败。
        for _p in (_cand, _os.path.dirname(_cand)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        break

__version__ = "1.0.0"
__author__ = "AI Novel Writer Team"

__all__ = ["app"]
