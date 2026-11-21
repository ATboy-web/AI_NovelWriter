"""服务共用的 API 错误助手。

此前 ai-service / novel-service 的 5 个模块各自抄了同一份 `_internal_error`：
实现完全一致，却分散在 5 处 —— 任何一次"改错误文案/改日志口径"都要改 5 遍，
漏改就会让不同端点的行为悄悄分叉。此处收敛为唯一实现，各服务按已有的
`backend/shared` 路径引导（见各服务 app/__init__.py）导入。
"""

import logging

from fastapi import HTTPException

__all__ = ["internal_error"]


def internal_error(e: Exception) -> HTTPException:
    """通用内部错误处理：记录详细错误到日志，仅返回通用提示给客户端。"""
    logging.getLogger(__name__).error(f"请求处理失败: {e}", exc_info=True)
    return HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
