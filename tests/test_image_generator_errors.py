"""`image_generator` 的后端探测与错误呈现（档 4：白等 / 白烧）。

## 这个模块的"静默错法"

| 错法 | 用户看到 |
|---|---|
| 没配地址却发出请求 | 一个 `httpx` 原始异常糊在界面上 |
| ComfyUI 轮询永不退出 | 界面卡 4 分钟没任何反馈 |
| 响应缺字段直接抛 KeyError | 用户看到 traceback 而不是"工作流不兼容" |

第三条尤其典型：`KeyError: 'images'` 对用户毫无意义，
而"工作流节点不兼容"能让他去换工作流。
"""

from __future__ import annotations

from typing import Any

from app import image_generator as ig


class FakeConfig:
    def __init__(self, values: dict[str, Any] | None = None):
        self._values = values or {}

    def get(self, key, default=None):
        return self._values.get(key, default)


def _gen(**values):
    return ig.ImageGenerator(config=FakeConfig(values))


class FakeResp:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content

    def json(self):
        return self._payload


class TestBackendResolution:
    def test_unknown_backend(self):
        gen = _gen(img_provider="不存在")

        result = gen.check_backend()

        assert result.ok is False
        assert "未知后端" in result.message

    def test_known_backend(self):
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188")

        assert gen.backend() is not None


class TestTestConnection:
    def test_not_enabled(self):
        """没启用文生图时**不发请求** —— 回一句"未启用"，与"连不上"要能分辨。"""
        gen = _gen(img_provider="")

        result = gen.check_backend()

        assert result.ok is False
        assert "未启用" in result.message

    def test_missing_base_url(self, monkeypatch):
        """后端存在但地址为空 ⇒ 明确说"未配置"，不发请求。"""
        gen = _gen(img_provider="comfyui", img_base="")
        monkeypatch.setattr(gen, "base_url", lambda: "")

        result = gen.check_backend()

        assert result.ok is False
        assert "未配置" in result.message

    def test_connection_error_is_presented(self, monkeypatch):
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188")

        def boom(*_a, **_kw):
            raise ConnectionError("拒绝连接")

        monkeypatch.setattr(ig.httpx, "get", boom)

        result = gen.check_backend()

        assert result.ok is False
        # 面向用户的是 `message`（"连不上 X，请确认服务已启动"），
        # 异常类型放在 `error` —— 这两层分工别混
        assert "连不上" in result.message
        assert "ConnectionError" in result.error

    def test_non_200_reported(self, monkeypatch):
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188")
        monkeypatch.setattr(ig.httpx, "get", lambda *a, **kw: FakeResp(500))

        result = gen.check_backend()

        assert result.ok is False

    def test_model_parse_failure_still_ok(self, monkeypatch):
        """SD WebUI 一个接口兼作探测与模型列表：解析失败不算后端不可用。"""
        gen = _gen(img_provider="sdapi", img_base="http://127.0.0.1:7860")
        monkeypatch.setattr(ig.httpx, "get", lambda *a, **kw: FakeResp(200, {"models": "不是列表"}))

        result = gen.check_backend()

        assert result.ok is True, result.message


class TestListModels:
    def test_backend_without_models_api(self):
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188")

        assert isinstance(gen.list_models(), list)

    def test_missing_base_url(self):
        gen = _gen(img_provider="sdapi", img_base="")

        assert gen.list_models() == []

    def test_non_200_returns_empty(self, monkeypatch):
        gen = _gen(img_provider="sdapi", img_base="http://127.0.0.1:7860")
        monkeypatch.setattr(ig.httpx, "get", lambda *a, **kw: FakeResp(500))

        assert gen.list_models() == []


class TestGenerate:
    def test_missing_base_url(self, monkeypatch):
        gen = _gen(img_provider="comfyui", img_base="", img_model="sd_xl.ckpt")
        monkeypatch.setattr(gen, "base_url", lambda: "")

        data, error = gen._generate_comfyui("一只猫", "", 512, 512)

        assert data is None
        assert "未配置" in error

    def test_missing_model_name(self, monkeypatch):
        """ComfyUI 必须指定 Checkpoint 文件名 —— 空着要明确说，不能发个空 workflow。

        ⚠️ `model_name()` 对 comfyui 有默认值（`sd_xl_base_1.0.safetensors`），
        所以"空模型名"只能靠替换得到；这条守的是**下游对空值的处理**。
        """
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188", img_model="")
        monkeypatch.setattr(gen, "model_name", lambda: "")

        data, error = gen._generate_comfyui("一只猫", "", 512, 512)

        assert data is None
        assert "模型" in error

    def test_sdapi_missing_base(self, monkeypatch):
        gen = _gen(img_provider="sdapi", img_base="")
        monkeypatch.setattr(gen, "base_url", lambda: "")

        data, error = gen._generate_sdapi("猫", "", 512, 512)

        assert data is None
        assert "未配置" in error

    def test_comfyui_missing_field_is_explained(self, monkeypatch):
        """响应缺字段时要给"工作流节点不兼容"，而不是裸 `KeyError`。"""
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188", img_model="sd_xl.ckpt")

        def fake_post(*_a, **_kw):
            raise KeyError("prompt_id")

        monkeypatch.setattr(ig.httpx, "post", fake_post)

        data, error = gen._generate_comfyui("猫", "", 512, 512)

        assert data is None
        assert "兼容" in error or "缺少字段" in error

    def test_comfyui_other_exception_presented(self, monkeypatch):
        gen = _gen(img_provider="comfyui", img_base="http://127.0.0.1:8188", img_model="sd_xl.ckpt")

        def fake_post(*_a, **_kw):
            raise RuntimeError("队列满了")

        monkeypatch.setattr(ig.httpx, "post", fake_post)

        data, error = gen._generate_comfyui("猫", "", 512, 512)

        assert data is None
        assert "RuntimeError" in error
