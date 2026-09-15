"""backend/shared/middleware 单元测试

覆盖 JWT 认证、动态限流、请求日志三个中间件。

本文件的存在价值之一：锁死「认证中间件必须真的拦截请求」这一行为。
历史缺陷（2026-09 发现）：AuthMiddleware._is_public_path() 用 PUBLIC_PATHS
（其中包含 "/"）做前缀匹配，任何路径都以 "/" 开头 ⇒ 恒为 True，
中间件对所有请求直接放行，ENABLE_AUTH=true 形同虚设。
"""

import importlib
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from shared.middleware import auth as auth_module  # noqa: E402
from shared.middleware.auth import (  # noqa: E402
    AuthDependencies,
    AuthMiddleware,
    JWTConfig,
    JWTManager,
    _load_api_keys,
)
from shared.middleware.logging import (  # noqa: E402
    PerformanceMonitor,
    RequestLogger,
    RequestLoggerConfig,
)
from shared.middleware.rate_limiter import (  # noqa: E402
    DynamicRateLimiter,
    RateLimitStore,
)

TEST_SECRET = "unit-test-secret-key-0123456789abcdef"


async def _echo_app(scope, receive, send):
    """最小 ASGI 应用：固定返回 200 ok。"""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


async def _call(middleware, path="/api/v1/generate", headers=None, method="GET"):
    """通过 ASGI 直接调用中间件，返回响应。"""
    transport = httpx.ASGITransport(app=middleware)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers or {})


# --------------------------------------------------------------------------
# JWTConfig：密钥解析
# --------------------------------------------------------------------------


class TestJWTConfigSecretResolution:
    def test_explicit_secret_key_wins(self):
        cfg = JWTConfig(secret_key="explicit-key")
        assert cfg.SECRET_KEY == "explicit-key"

    def test_secret_key_env_preferred_over_jwt_secret(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "from-secret-key")
        monkeypatch.setenv("JWT_SECRET", "from-jwt-secret")
        importlib.reload(auth_module)
        try:
            assert auth_module.JWTConfig.SECRET_KEY == "from-secret-key"
        finally:
            monkeypatch.undo()
            importlib.reload(auth_module)

    def test_jwt_secret_used_as_alias(self, monkeypatch):
        """.env.example / docker-compose.prod.yml / deploy.sh 使用的名字是 JWT_SECRET。

        若只认 SECRET_KEY，运维按文档配置的密钥会被静默忽略。
        """
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("JWT_SECRET", "only-jwt-secret")
        importlib.reload(auth_module)
        try:
            assert auth_module.JWTConfig.SECRET_KEY == "only-jwt-secret"
        finally:
            monkeypatch.undo()
            importlib.reload(auth_module)


# --------------------------------------------------------------------------
# 公开路径判定（认证绕过的回归测试）
# --------------------------------------------------------------------------


class TestIsPublicPath:
    @pytest.fixture
    def mw(self):
        return AuthMiddleware(_echo_app, config=JWTConfig(secret_key=TEST_SECRET))

    @pytest.mark.parametrize(
        "path",
        ["/", "/health", "/docs", "/redoc", "/openapi.json", "/api/v1/health"],
    )
    def test_public_paths_allowed(self, mw, path):
        assert mw._is_public_path(path) is True

    def test_docs_static_subresource_allowed(self, mw):
        assert mw._is_public_path("/docs/oauth2-redirect") is True

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/generate",
            "/api/v1/models",
            "/api/v1/admin/secret",
            "/api/v1/novels",
            "/anything/protected",
        ],
    )
    def test_business_paths_are_not_public(self, mw, path):
        """回归：这些路径历史上被判为公开，导致鉴权完全失效。"""
        assert mw._is_public_path(path) is False

    def test_prefix_does_not_overmatch(self, mw):
        """前缀 /docs 不应匹配 /docsomething。"""
        assert mw._is_public_path("/docsomething") is False

    def test_public_path_prefixes_never_contains_root(self):
        """硬约束：前缀列表中出现 "/" 会让所有路径变成公开。"""
        assert "/" not in JWTConfig.PUBLIC_PATH_PREFIXES


# --------------------------------------------------------------------------
# JWTManager
# --------------------------------------------------------------------------


class TestJWTManager:
    @pytest.fixture
    def manager(self):
        return JWTManager(JWTConfig(secret_key=TEST_SECRET))

    def test_access_token_round_trip(self, manager):
        token = manager.create_access_token({"sub": "u1", "username": "alice"})
        payload = manager.verify_token(token)
        assert payload["sub"] == "u1"
        assert payload["username"] == "alice"
        assert payload["type"] == "access"

    def test_refresh_token_round_trip(self, manager):
        token = manager.create_refresh_token({"sub": "u1"})
        payload = manager.verify_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "u1"

    def test_expired_token_returns_none(self, manager):
        token = manager.create_access_token(
            {"sub": "u1"}, expires_delta=timedelta(seconds=-10)
        )
        assert manager.verify_token(token) is None

    def test_tampered_token_returns_none(self, manager):
        token = manager.create_access_token({"sub": "u1"})
        assert manager.verify_token(token + "x") is None

    def test_token_signed_with_other_key_rejected(self, manager):
        other = JWTManager(
            JWTConfig(secret_key="another-secret-key-0123456789abcdefghij")
        )
        token = other.create_access_token({"sub": "u1"})
        assert manager.verify_token(token) is None

    def test_missing_secret_raises_on_sign(self):
        cfg = JWTConfig()
        cfg.SECRET_KEY = ""
        with pytest.raises(RuntimeError):
            JWTManager(cfg).create_access_token({"sub": "u1"})

    def test_missing_secret_verify_returns_none(self):
        cfg = JWTConfig()
        cfg.SECRET_KEY = ""
        assert JWTManager(cfg).verify_token("whatever") is None


# --------------------------------------------------------------------------
# 凭据提取
# --------------------------------------------------------------------------


def _make_request(headers=None, query="", cookies=None):
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    if cookies:
        raw_headers.append(
            (b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode())
        )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/generate",
        "query_string": query.encode(),
        "headers": raw_headers,
        "client": ("1.2.3.4", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


class TestCredentialExtraction:
    @pytest.fixture
    def mw(self):
        return AuthMiddleware(_echo_app, config=JWTConfig(secret_key=TEST_SECRET))

    def test_extract_token_from_bearer_header(self, mw):
        req = _make_request(headers={"Authorization": "Bearer abc123"})
        assert mw._extract_token(req) == "abc123"

    def test_extract_token_from_query(self, mw):
        assert mw._extract_token(_make_request(query="token=q1")) == "q1"

    def test_extract_token_from_cookie(self, mw):
        req = _make_request(cookies={"access_token": "c1"})
        assert mw._extract_token(req) == "c1"

    def test_extract_token_absent(self, mw):
        assert mw._extract_token(_make_request()) is None

    def test_non_bearer_header_ignored(self, mw):
        req = _make_request(headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert mw._extract_token(req) is None

    def test_extract_api_key_from_header(self, mw):
        req = _make_request(headers={"X-API-Key": "k1"})
        assert mw._extract_api_key(req) == "k1"

    def test_extract_api_key_from_query(self, mw):
        assert mw._extract_api_key(_make_request(query="api_key=k2")) == "k2"

    def test_extract_api_key_absent(self, mw):
        assert mw._extract_api_key(_make_request()) is None


class TestApiKeyLoading:
    def test_empty_env_yields_no_keys(self, monkeypatch):
        monkeypatch.delenv("API_KEYS", raising=False)
        assert _load_api_keys() == {}

    def test_bare_key_defaults_to_basic(self, monkeypatch):
        monkeypatch.setenv("API_KEYS", "sk-abc")
        keys = _load_api_keys()
        assert keys["sk-abc"]["level"] == "basic"
        assert keys["sk-abc"]["user_id"] == "apikey-sk-abc"

    def test_key_with_level(self, monkeypatch):
        monkeypatch.setenv("API_KEYS", "sk-a:premium, sk-b ")
        keys = _load_api_keys()
        assert keys["sk-a"]["level"] == "premium"
        assert keys["sk-b"]["level"] == "basic"

    def test_blank_entries_ignored(self, monkeypatch):
        monkeypatch.setenv("API_KEYS", " , ,")
        assert _load_api_keys() == {}


# --------------------------------------------------------------------------
# AuthMiddleware.dispatch（端到端）
# --------------------------------------------------------------------------


class TestAuthMiddlewareDispatch:
    @pytest.fixture
    def mw(self, monkeypatch):
        monkeypatch.setenv("API_KEYS", "good-key:premium")
        return AuthMiddleware(_echo_app, config=JWTConfig(secret_key=TEST_SECRET))

    @pytest.mark.asyncio
    async def test_public_path_passes(self, mw):
        resp = await _call(mw, "/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_path_without_credentials_is_401(self, mw):
        resp = await _call(mw, "/api/v1/generate")
        assert resp.status_code == 401
        assert resp.json()["error"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_protected_path_with_invalid_api_key_is_401(self, mw):
        resp = await _call(mw, "/api/v1/generate", headers={"X-API-Key": "bad"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_grants_access(self, mw):
        resp = await _call(mw, "/api/v1/generate", headers={"X-API-Key": "good-key"})
        assert resp.status_code == 200
        assert resp.headers["X-User-Id"] == "apikey-good-key"

    @pytest.mark.asyncio
    async def test_valid_jwt_grants_access(self, mw):
        token = mw.jwt_manager.create_access_token(
            {"sub": "u9", "username": "bob", "role": "admin", "level": "premium"}
        )
        resp = await _call(
            mw, "/api/v1/generate", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.headers["X-User-Id"] == "u9"

    @pytest.mark.asyncio
    async def test_docs_subresource_passes(self, mw):
        resp = await _call(mw, "/docs/oauth2-redirect")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_credential_source_returns_503(self, monkeypatch):
        """启用鉴权却没有任何凭据来源 → 显式失败，绝不静默放行。"""
        monkeypatch.delenv("API_KEYS", raising=False)
        cfg = JWTConfig()
        cfg.SECRET_KEY = ""
        mw = AuthMiddleware(_echo_app, config=cfg)
        resp = await _call(mw, "/api/v1/generate")
        assert resp.status_code == 503
        assert resp.json()["error"] == "Auth Misconfigured"

    @pytest.mark.asyncio
    async def test_public_path_still_works_without_credentials(self, monkeypatch):
        monkeypatch.delenv("API_KEYS", raising=False)
        cfg = JWTConfig()
        cfg.SECRET_KEY = ""
        mw = AuthMiddleware(_echo_app, config=cfg)
        resp = await _call(mw, "/health")
        assert resp.status_code == 200


# --------------------------------------------------------------------------
# AuthDependencies
# --------------------------------------------------------------------------


class TestAuthDependencies:
    def _request_with_user(self, user=None):
        req = _make_request()
        if user is not None:
            req.scope["state"] = {"user": user}
        return req

    def test_get_current_user_raises_without_user(self):
        from fastapi import HTTPException

        deps = AuthDependencies()
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(_make_request())
        assert exc.value.status_code == 401

    def test_get_current_user_returns_user(self):
        deps = AuthDependencies()
        user = {"user_id": "u1", "role": "user", "level": "free"}
        assert deps.get_current_user(self._request_with_user(user)) == user

    def test_require_role_allows_matching_role(self):
        from starlette.requests import Request

        deps = AuthDependencies()
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "headers": [],
                "client": ("1.2.3.4", 1),
                "server": ("test", 80),
                "scheme": "http",
            }
        )
        req.state.user = {"user_id": "u1", "role": "admin", "level": "premium"}
        assert deps.require_role(["admin"])(req)["user_id"] == "u1"

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            deps.require_role(["superuser"])(req)
        assert exc.value.status_code == 403

    def test_require_level_rejects_insufficient_level(self):
        from fastapi import HTTPException
        from starlette.requests import Request

        deps = AuthDependencies()
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "headers": [],
                "client": ("1.2.3.4", 1),
                "server": ("test", 80),
                "scheme": "http",
            }
        )
        req.state.user = {"user_id": "u1", "role": "user", "level": "free"}
        with pytest.raises(HTTPException) as exc:
            deps.require_level(["premium"])(req)
        assert exc.value.status_code == 403
        assert deps.require_level(["free", "basic"])(req)["level"] == "free"


# --------------------------------------------------------------------------
# 动态限流
# --------------------------------------------------------------------------


class TestRateLimiterHelpers:
    @pytest.fixture
    def limiter(self):
        return DynamicRateLimiter(_echo_app)

    @pytest.mark.parametrize(
        "path,method,expected",
        [
            ("/health", "GET", "health"),
            ("/api/v1/health", "GET", "health"),
            ("/api/v1/generate", "POST", "generate"),
            ("/api/v1/models", "POST", "model_manage"),
            ("/api/v1/models", "DELETE", "model_manage"),
            ("/api/v1/models", "GET", "default"),
            ("/api/v1/novels", "GET", "default"),
        ],
    )
    def test_endpoint_category(self, limiter, path, method, expected):
        assert limiter._get_endpoint_category(path, method) == expected

    def test_estimate_chapter_length_empty(self, limiter):
        assert limiter._estimate_chapter_length(None) == 0
        assert limiter._estimate_chapter_length({}) == 0

    def test_estimate_chapter_length_from_max_tokens(self, limiter):
        assert limiter._estimate_chapter_length({"max_tokens": 1500}) == 1000

    def test_very_long_chapter_is_throttled_hardest(self, limiter):
        assert limiter._get_dynamic_limits("generate", 12000) == (3, 60)

    def test_long_chapter_throttled(self, limiter):
        assert limiter._get_dynamic_limits("generate", 6000) == (5, 60)

    def test_default_category_uses_default_rules(self, limiter):
        assert limiter._get_dynamic_limits("default", 0) == (10000, 60)

    def test_client_id_uses_authenticated_user(self, limiter):
        req = _make_request()
        req.state.user = {"user_id": "u1"}
        assert limiter._get_client_id(req) == "user:u1"

    def test_client_id_ignores_spoofable_headers(self, limiter):
        """X-Forwarded-For / X-User-Id 由客户端可控，不得作为限流标识。"""
        req = _make_request(
            headers={"X-Forwarded-For": "9.9.9.9", "X-User-Id": "admin"}
        )
        assert limiter._get_client_id(req) == "ip:1.2.3.4"

    def test_user_level_from_state_not_header(self, limiter):
        req = _make_request(headers={"X-User-Level": "unlimited"})
        assert limiter._get_user_level(req) == "free"
        req.state.user = {"level": "premium"}
        assert limiter._get_user_level(req) == "premium"


class TestRateLimitStore:
    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        store = RateLimitStore()
        allowed, remaining, _ = await store.check_rate_limit("k", 3, 60)
        assert allowed is True
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self):
        store = RateLimitStore()
        for _ in range(3):
            await store.check_rate_limit("k", 3, 60)
        allowed, remaining, reset = await store.check_rate_limit("k", 3, 60)
        assert allowed is False
        assert remaining == 0
        assert reset >= 0

    @pytest.mark.asyncio
    async def test_expired_entries_are_evicted(self):
        store = RateLimitStore()
        for _ in range(3):
            await store.check_rate_limit("k", 3, 1)
        store._store["k"] = [t - 5 for t in store._store["k"]]
        allowed, _, _ = await store.check_rate_limit("k", 3, 1)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_usage_counting(self):
        store = RateLimitStore()
        await store.check_rate_limit("k", 5, 60)
        await store.check_rate_limit("k", 5, 60)
        assert await store.get_usage("k", 60) == 2

    @pytest.mark.asyncio
    async def test_keys_are_isolated(self):
        store = RateLimitStore()
        await store.check_rate_limit("a", 1, 60)
        allowed, _, _ = await store.check_rate_limit("b", 1, 60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_disabled_limiter_passes_through(self):
        limiter = DynamicRateLimiter(_echo_app)
        assert limiter.config.ENABLED is False
        resp = await _call(limiter, "/api/v1/generate")
        assert resp.status_code == 200


# --------------------------------------------------------------------------
# 请求日志 / 性能监控
# --------------------------------------------------------------------------


class TestRequestLogger:
    @pytest.fixture
    def logger_mw(self):
        return RequestLogger(_echo_app, config=RequestLoggerConfig())

    def test_excluded_paths_not_logged(self, logger_mw):
        for path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            assert logger_mw._should_log(path) is False

    def test_business_paths_logged(self, logger_mw):
        assert logger_mw._should_log("/api/v1/generate") is True

    def test_sanitize_masks_sensitive_fields(self, logger_mw):
        body = {
            "username": "alice",
            "password": "hunter2",
            "API_KEY": "sk-secret",
            "Authorization": "Bearer x",
        }
        out = logger_mw._sanitize_body(body)
        assert out["username"] == "alice"
        assert out["password"] == "***"
        assert out["API_KEY"] == "***"
        assert out["Authorization"] == "***"

    def test_sanitize_recurses_into_nested_dicts(self, logger_mw):
        body = {"outer": {"token": "t", "keep": 1}}
        out = logger_mw._sanitize_body(body)
        assert out["outer"]["token"] == "***"
        assert out["outer"]["keep"] == 1

    @pytest.mark.asyncio
    async def test_logged_request_passes_through(self, logger_mw):
        resp = await _call(logger_mw, "/api/v1/generate")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_request_short_circuits(self, logger_mw):
        resp = await _call(logger_mw, "/health")
        assert resp.status_code == 200


class TestPerformanceMonitor:
    def test_records_and_aggregates(self):
        pm = PerformanceMonitor()
        pm.record_request("/a", "GET", 200, 10.0)
        pm.record_request("/a", "GET", 500, 30.0)
        metrics = pm.get_metrics()
        assert metrics["total_requests"] == 2
        assert metrics["successful_requests"] == 1
        assert metrics["failed_requests"] == 1
        assert metrics["avg_duration_ms"] == 20.0
        assert metrics["success_rate"] == 50.0
        assert metrics["max_duration_ms"] == 30.0
        assert metrics["min_duration_ms"] == 10.0
        assert metrics["endpoints"]["GET:/a"]["count"] == 2
        assert metrics["endpoints"]["GET:/a"]["error_rate"] == 50.0

    def test_empty_metrics_do_not_divide_by_zero(self):
        metrics = PerformanceMonitor().get_metrics()
        assert metrics["avg_duration_ms"] == 0
        assert metrics["success_rate"] == 0

    def test_reset_clears_state(self):
        pm = PerformanceMonitor()
        pm.record_request("/a", "GET", 200, 5.0)
        pm.reset()
        assert pm.get_metrics()["total_requests"] == 0
        assert pm.get_metrics()["endpoints"] == {}
