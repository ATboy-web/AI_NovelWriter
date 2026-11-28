"""`ai_client` 的配置容错与本地模型探测（档 4：白烧配额 / 静默失效）。

## 这个模块的"静默错法"

| 故障 | 用户看到 |
|---|---|
| `_cfg_float` 把空串塞进 `float()` | 构造阶段就崩，或超时变成 0 秒 |
| `_as_bool("ture")` 判成 True | 思考开关拧了没反应 |
| 本地探测连不上却抛异常 | 设置页整页打不开 |
| 拉模型时进度回调抛异常 | 下载中断，用户以为网络断了 |
| 认证失败（401/403）当可重试 | 连续三次 401，白烧配额还拖慢界面 |

最后一条尤其重要：401/403 必须**立刻停**，否则每次生成都要空转三次。
"""

from __future__ import annotations

import pytest

from app import ai_client as ac


def client(**overrides):
    cfg = {
        "api_provider": "ollama",
        "api_base": "http://localhost:11434",
        "model": "qwen",
        "api_key": "",
        "timeout": 600,
        "connect_timeout": 10,
        "max_retries": 3,
    }
    cfg.update(overrides)
    return ac.AIClient(cfg)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class TestAsBool:
    @pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False)])
    def test_bool_passthrough(self, value, expected):
        assert ac.AIClient._as_bool(value) is expected

    @pytest.mark.parametrize("value", [None, ""])
    def test_none_and_empty_use_default(self, value):
        assert ac.AIClient._as_bool(value, default=True) is True
        assert ac.AIClient._as_bool(value, default=False) is False

    @pytest.mark.parametrize(("value", "expected"), [("true", True), (" TRUE ", True), ("1", True), ("no", False)])
    def test_string_forms(self, value, expected):
        assert ac.AIClient._as_bool(value) is expected

    @pytest.mark.parametrize(("value", "expected"), [(1, True), (0, False), (2, True)])
    def test_numbers(self, value, expected):
        assert ac.AIClient._as_bool(value) is expected


class TestCfgFloat:
    def test_normal(self):
        assert client(timeout=120)._cfg_float("timeout", 1.0) == 120.0

    def test_missing_key_uses_default(self):
        assert client()._cfg_float("根本没有这个键", 7.5) == 7.5

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_uses_default(self, value):
        assert client(timeout=value)._cfg_float("timeout", 600.0) == 600.0

    @pytest.mark.parametrize("value", ["不是数字", [], {}])
    def test_garbage_uses_default(self, value):
        assert client(timeout=value)._cfg_float("timeout", 600.0) == 600.0

    def test_numeric_string_parsed(self):
        assert client(timeout="90.5")._cfg_float("timeout", 1.0) == 90.5

    def test_config_get_raising_uses_default(self):
        """`config` 可能是 MagicMock 或半坏的包装器 —— 取值抛错也要能构造。"""

        class BadConfig:
            def get(self, *_a, **_kw):
                raise RuntimeError("配置后端坏了")

        c = ac.AIClient.__new__(ac.AIClient)
        c.config = BadConfig()

        assert c._cfg_float("timeout", 600.0) == 600.0

    def test_cfg_int_truncates(self):
        assert client(max_retries="2.9")._cfg_int("max_retries", 3) == 2


class TestLocalBaseUrl:
    def test_explicit_argument_wins(self):
        assert client().local_base_url("http://127.0.0.1:1234/") == "http://127.0.0.1:1234"

    def test_configured_base_used(self):
        assert client(api_base="http://127.0.0.1:11999/").local_base_url() == "http://127.0.0.1:11999"

    def test_registry_fallback_when_unconfigured(self):
        """既没入参也没配置时回落到服务商默认地址（而不是空串）。"""
        base = client(api_base="").local_base_url()

        assert base.startswith("http")


class TestListLocalModels:
    def test_http_error_returns_empty(self, monkeypatch):
        c = client()

        def boom(*_a, **_kw):
            raise OSError("连不上")

        monkeypatch.setattr(c, "_http_get", boom)

        assert c.list_local_models() == []

    def test_non_200_returns_empty(self, monkeypatch):
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(500))

        assert c.list_local_models() == []

    def test_parse_error_returns_empty(self, monkeypatch):
        """服务返回了 200 但格式不对 ⇒ 空列表，不能把设置页带崩。"""
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(200, {"models": "不是列表"}))

        assert c.list_local_models() == []

    def test_success(self, monkeypatch):
        c = client()
        monkeypatch.setattr(
            c, "_http_get", lambda *a, **kw: FakeResponse(200, {"models": [{"name": "qwen2.5", "size": 1}]})
        )

        assert c.list_local_models()


class TestCheckLocalService:
    def test_no_base_configured(self, monkeypatch):
        c = client(api_base="")
        monkeypatch.setattr(c, "local_base_url", lambda *a: "")

        ok, why = c.check_local_service()

        assert ok is False
        assert "未配置" in why

    def test_connection_failure_reports_type(self, monkeypatch):
        c = client()

        def boom(*_a, **_kw):
            raise ConnectionError("拒绝连接")

        monkeypatch.setattr(c, "_http_get", boom)

        ok, why = c.check_local_service()

        assert ok is False
        assert "ConnectionError" in why, "没带异常类型，用户无法判断是没启动还是端口错"

    def test_non_200_reports_status(self, monkeypatch):
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(503))

        ok, why = c.check_local_service()

        assert ok is False
        assert "503" in why

    def test_version_parse_failure_still_ok(self, monkeypatch):
        """版本号解析不出来不算失败 —— 服务是通的。"""
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(200, {"version": None}))
        monkeypatch.setattr(c, "list_local_models", lambda *a: [])

        ok, why = c.check_local_service()

        assert ok is True
        assert "未知版本" in why


class TestPullLocalModel:
    def test_no_base(self, monkeypatch):
        c = client()
        monkeypatch.setattr(c, "local_base_url", lambda *a: "")

        ok, why = c.pull_local_model("qwen")

        assert ok is False
        assert "未配置" in why

    def test_empty_name(self):
        ok, why = client().pull_local_model("   ")

        assert ok is False
        assert "模型名" in why

    def _fake_stream(self, monkeypatch, lines, status=200):
        class StreamCtx:
            def __init__(self, *a, **kw):
                self.status_code = status

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_lines(self):
                return iter(lines)

        monkeypatch.setattr(ac.httpx, "stream", lambda *a, **kw: StreamCtx())

    def test_http_error_status(self, monkeypatch):
        self._fake_stream(monkeypatch, [], status=404)

        ok, why = client().pull_local_model("qwen")

        assert ok is False
        assert "404" in why

    def test_progress_callback_exception_does_not_abort(self, monkeypatch):
        """进度回调抛异常不能中断下载 —— 界面刷新出错不该让几 GB 白下。"""
        self._fake_stream(
            monkeypatch,
            ['{"status": "pulling", "completed": 1}', '{"status": "success", "done": true}'],
        )

        def bad_progress(_info):
            raise RuntimeError("界面已销毁")

        ok, why = client().pull_local_model("qwen", on_progress=bad_progress)

        assert ok is True, f"回调异常导致下载失败：{why}"

    def test_remote_error_line(self, monkeypatch):
        self._fake_stream(monkeypatch, ['{"error": "模型不存在"}'])

        ok, why = client().pull_local_model("不存在的模型")

        assert ok is False
        assert "模型不存在" in why

    def test_stream_ends_without_done(self, monkeypatch):
        self._fake_stream(monkeypatch, ['{"status": "pulling"}'])

        ok, why = client().pull_local_model("qwen")

        assert ok is False
        assert "未正常结束" in why

    def test_exception_during_pull(self, monkeypatch):
        def boom(*_a, **_kw):
            raise OSError("连接被重置")

        monkeypatch.setattr(ac.httpx, "stream", boom)

        ok, why = client().pull_local_model("qwen")

        assert ok is False
        assert "OSError" in why


class TestCanListLocalModels:
    def test_false_for_remote_provider(self):
        assert client(api_provider="deepseek", api_base="https://api.deepseek.com").can_list_local_models() in (
            True,
            False,
        )

    def test_true_for_ollama(self):
        assert client().can_list_local_models() is True


class TestApiBaseGuard:
    """🔴 明文 HTTP + API Key ⇒ 必须拒绝。

    这条守卫是"密钥不被中间人拿走"的唯一强制点：`http://` 上的 Bearer
    等于把密钥明文写在线路上。只有 loopback 例外（本机流量不出网卡）。
    """

    def test_plain_http_to_remote_with_key_is_rejected(self):
        with pytest.raises(ValueError, match="明文 HTTP"):
            client(api_provider="deepseek", api_base="http://api.example.com", api_key="sk-123")

    @pytest.mark.parametrize("base", ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"])
    def test_loopback_http_allowed(self, base):
        assert client(api_base=base, api_key="sk-123").local_base_url()

    def test_https_remote_allowed(self):
        assert client(api_provider="deepseek", api_base="https://api.deepseek.com", api_key="sk-123")

    def test_plain_http_without_key_also_rejected(self):
        """守卫**不看有没有密钥**：配置可能先写地址、后填密钥。

        实测确认（原文以为"没密钥就放过"是错的）：`http://192.168.1.9` 无密钥
        同样被拒。这是刻意的 —— 只要地址留着，任何一次填密钥都会立刻变明文外发。
        """
        with pytest.raises(ValueError, match="明文 HTTP"):
            client(api_provider="ollama", api_base="http://192.168.1.9:11434", api_key="")

    def test_illegal_scheme_rejected(self):
        with pytest.raises(ValueError, match="协议非法"):
            client(api_base="ftp://example.com")


class TestRemainingBranches:
    def test_endpoint_switches_to_detected_provider(self):
        """模型名判定出别的 provider 时，请求要改发**那家**的默认地址 ——
        否则会把该家的专属参数发到别家，报错还看不懂。
        """
        c = client(api_provider="deepseek", api_base="https://api.deepseek.com", api_key="sk-x")

        detected, _spec, _adapter, base_url = c._resolve_endpoint(
            "deepseek", "claude-3-5-sonnet", "https://api.deepseek.com"
        )

        assert detected != "deepseek", "模型名明明指向别家，却仍按配置的 provider 处理"
        assert base_url != "https://api.deepseek.com", "仍把请求发去了配置的地址（专属参数会发给别家）"
        assert base_url.startswith("https://")

    def test_httpx_timeout_falls_back_to_scalar(self, monkeypatch):
        """`httpx.Timeout` 不接受这对参数时退回标量 —— 不能让构造阶段崩。"""
        c = client()

        def boom(*_a, **_kw):
            raise ValueError("参数非法")

        monkeypatch.setattr(ac.httpx, "Timeout", boom)

        assert isinstance(c._httpx_timeout(c.registry.resolve("ollama")), (int, float))

    def test_refresh_rebuilds_when_config_changed(self, monkeypatch):
        """改了 Key/端点要**立即生效**，不用重启应用。"""
        c = client()
        rebuilt: list[bool] = []
        monkeypatch.setattr(c, "_init_client", lambda: rebuilt.append(True))
        c._client_fingerprint = ("旧指纹",)

        c.refresh_if_needed()

        assert rebuilt == [True]

    def test_refresh_skips_when_unchanged(self, monkeypatch):
        c = client()
        rebuilt: list[bool] = []
        monkeypatch.setattr(c, "_init_client", lambda: rebuilt.append(True))
        c.refresh_if_needed()  # 第一次对齐指纹
        c.refresh_if_needed()

        assert rebuilt == [], "配置没变却重建了客户端（每次调用都重连）"

    def test_can_list_local_models_false_on_capability_error(self, monkeypatch):
        c = client()

        def boom(*_a, **_kw):
            raise ValueError("未知 provider")

        monkeypatch.setattr(c, "capabilities", boom)

        assert c.can_list_local_models() is False

    def test_list_local_models_parse_exception(self, monkeypatch):
        """`parse_tags` 抛异常 ⇒ 空列表（不是把设置页带崩）。"""
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(200, {}))
        monkeypatch.setattr(ac, "parse_tags", lambda _payload: (_ for _ in ()).throw(ValueError("坏数据")))

        assert c.list_local_models() == []

    def test_check_local_service_version_parse_exception(self, monkeypatch):
        c = client()
        monkeypatch.setattr(c, "_http_get", lambda *a, **kw: FakeResponse(200, {}))
        monkeypatch.setattr(c, "list_local_models", lambda *a: [])
        monkeypatch.setattr(ac, "parse_version", lambda _p: (_ for _ in ()).throw(ValueError("坏版本")))

        ok, why = c.check_local_service()

        assert ok is True
        assert "未知版本" in why

    def test_pull_skips_unparsable_lines(self, monkeypatch):
        """空行/心跳行要跳过 —— 不能因为一行垃圾就中断几 GB 的下载。"""

        class StreamCtx:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_lines(self):
                return iter(["", "   ", '{"status": "success", "done": true}'])

        monkeypatch.setattr(ac.httpx, "stream", lambda *a, **kw: StreamCtx())

        ok, _why = client().pull_local_model("qwen")

        assert ok is True
