"""后端韧性回归：统一错误助手 + 限流存储内存治理。

对应本轮修复：
- P2-8：5 处逐字相同的 `_internal_error` 收敛到 `shared.api_errors.internal_error`。
- P1-7：`RateLimitStore` 的 key 无界增长（TTL 淘汰 + 容量上限 + 只读 get_usage）。

这些用例锁死的是"行为契约"，不是实现细节：错误文案/状态码一旦分叉、
或内存治理被回退成 defaultdict 读一次就建 key，都会在这里立刻变红。
"""

import ast
import sys
import time
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import HTTPException  # noqa: E402
from shared.api_errors import internal_error  # noqa: E402
from shared.middleware.rate_limiter import RateLimitStore  # noqa: E402

# ---------------------------------------------------------------- 统一错误助手


def test_internal_error_returns_generic_500():
    exc = internal_error(RuntimeError("数据库连接串 leaked"))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 500
    assert exc.detail == "服务器内部错误，请稍后重试"
    # 内部细节不得回传客户端
    assert "leaked" not in exc.detail


def test_internal_error_logs_detail(caplog):
    import logging

    with caplog.at_level(logging.ERROR):
        internal_error(ValueError("内部细节 XYZ"))
    assert any("内部细节 XYZ" in r.message for r in caplog.records), "详细错误必须落日志，否则线上无法定位"


#: 曾经各自抄一份 _internal_error 的 5 个模块
_DEDUP_TARGETS = [
    "ai-service/app/main.py",
    "ai-service/app/api/routes.py",
    "novel-service/app/main.py",
    "novel-service/app/api/routes.py",
    "novel-service/app/api/new_features_routes.py",
]


@pytest.mark.parametrize("rel", _DEDUP_TARGETS)
def test_no_local_internal_error_reimplementation(rel):
    """守卫：不得再在服务内重新定义 _internal_error，必须复用 shared 实现。"""
    src = (_BACKEND_DIR / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_internal_error" not in defined, f"{rel} 又出现了本地重复实现"
    assert "from shared.api_errors import internal_error as _internal_error" in src, (
        f"{rel} 必须从 shared.api_errors 导入统一实现"
    )


# ---------------------------------------------------------------- 限流存储治理


@pytest.mark.asyncio
async def test_get_usage_does_not_create_key():
    store = RateLimitStore()
    assert store.key_count() == 0
    assert await store.get_usage("从未出现过的客户端", 60) == 0
    assert store.key_count() == 0, "只读查询不得凭空建 key（旧 defaultdict 实现会）"


@pytest.mark.asyncio
async def test_basic_limit_still_enforced():
    store = RateLimitStore()
    for i in range(3):
        allowed, remaining, _ = await store.check_rate_limit("k", 3, 60)
        assert allowed is True
        assert remaining == 3 - i - 1
    allowed, remaining, reset = await store.check_rate_limit("k", 3, 60)
    assert allowed is False
    assert remaining == 0
    assert reset >= 0
    assert await store.get_usage("k", 60) == 3


@pytest.mark.asyncio
async def test_expired_keys_are_evicted():
    store = RateLimitStore()
    await store.check_rate_limit("fresh", 10, 60)
    # 手工塞一个早已过期的 key，模拟长期运行后遗留的冷 key
    store._store["stale"] = [time.time() - 3600]
    assert store.key_count() == 2
    await store.check_rate_limit("another", 10, 60)
    assert "stale" not in store._store, "过期 key 必须被 TTL 淘汰"
    assert "fresh" in store._store


@pytest.mark.asyncio
async def test_long_window_key_survives_short_window_call():
    """淘汰按见过的最长窗口判定，短窗口请求不得误删长窗口计数。"""
    store = RateLimitStore()
    await store.check_rate_limit("hourly", 100, 3600)
    store._store["hourly"] = [time.time() - 600]  # 10 分钟前，对小时窗口仍有效
    await store.check_rate_limit("per_minute", 10, 60)
    assert "hourly" in store._store, "长窗口 key 被短窗口调用误删了"


@pytest.mark.asyncio
async def test_capacity_cap_evicts_coldest():
    store = RateLimitStore(max_keys=3)
    now = time.time()
    await store.check_rate_limit("a", 100, 3600)
    await store.check_rate_limit("b", 100, 3600)
    await store.check_rate_limit("c", 100, 3600)
    store._store["a"] = [now - 100]  # a 最久未活跃
    await store.check_rate_limit("d", 100, 3600)
    assert store.key_count() <= 3, "容量上限必须兜底，key 不能无界增长"
    assert "a" not in store._store, "应淘汰最久未活跃的 key"
    assert "d" in store._store
