# -*- coding: utf-8 -*-
"""image_generator 配置读取 / 后端探测 / 生成路径补测（monkeypatch httpx，无真实网络）。

覆盖 base_url / model_name / _headers / _dimension 的防御性分支，check_backend 与
list_models 的全部结果分流，以及 generate_result / generate_to_novel 的成败路径。
"""

import base64

import httpx
import pytest

from app.image_generator import DISABLED_PROVIDER, ImageGenerator


class FakeConfig:
    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)


class FakeResp:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data
        self.content = content

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


def _gen(values=None):
    return ImageGenerator(FakeConfig(values))


class TestConfigReads:
    def test_provider_default_and_disabled(self):
        assert _gen().provider() == "comfyui"
        assert _gen({"img_provider": ""}).provider() == DISABLED_PROVIDER
        assert _gen({"img_provider": "sdapi"}).is_configured() is True
        assert _gen({"img_provider": "disabled"}).is_configured() is False

    def test_base_url_configured_overrides_default(self):
        assert _gen({"img_api_base": "http://x:9000/"}).base_url() == "http://x:9000"
        assert _gen().base_url() == "http://127.0.0.1:8188"

    def test_model_name_default_and_configured(self):
        assert _gen().model_name() == "sd_xl_base_1.0.safetensors"
        assert _gen({"img_model": "custom.safetensors"}).model_name() == "custom.safetensors"
        assert _gen({"img_provider": "sdapi"}).model_name() == ""

    def test_headers_with_and_without_key(self):
        assert _gen()._headers() == {}
        assert _gen({"img_api_key": "secret"})._headers() == {"Authorization": "Bearer secret"}

    @pytest.mark.parametrize(
        "explicit,config_value,expected",
        [
            (512, None, 512),
            (None, "768", 768),
            (None, "bad", 1024),
            (None, None, 1024),
            (0, None, 1024),
            (-5, None, 1024),
            ("abc", None, 1024),
            (None, 0, 1024),
        ],
    )
    def test_dimension_defensive(self, explicit, config_value, expected):
        values = {} if config_value is None else {"img_width": config_value}
        assert _gen(values)._dimension(explicit, "img_width") == expected


class TestCheckBackend:
    def test_not_configured(self):
        result = _gen({"img_provider": "disabled"}).check_backend()
        assert result.ok is False
        assert "未启用" in result.message

    def test_unknown_backend(self):
        result = _gen({"img_provider": "nope"}).check_backend()
        assert result.ok is False
        assert "未知后端" in result.message

    def test_connection_error(self, monkeypatch):
        def _raise(*a, **k):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("app.image_generator.httpx.get", _raise)
        result = _gen().check_backend()
        assert result.ok is False
        assert "连不上" in result.message

    def test_non_200_with_auth_hint(self, monkeypatch):
        monkeypatch.setattr("app.image_generator.httpx.get", lambda *a, **k: FakeResp(401))
        result = _gen().check_backend()
        assert result.ok is False
        assert "API Key" in result.message

    def test_sdapi_ok_counts_models(self, monkeypatch):
        payload = [{"model_name": "m1"}, {"title": "m2"}]
        monkeypatch.setattr("app.image_generator.httpx.get", lambda *a, **k: FakeResp(200, payload))
        result = _gen({"img_provider": "sdapi"}).check_backend()
        assert result.ok is True
        assert "2 个模型" in result.message

    def test_comfyui_ok_without_models(self, monkeypatch):
        monkeypatch.setattr("app.image_generator.httpx.get", lambda *a, **k: FakeResp(200, {}))
        result = _gen().check_backend()
        assert result.ok is True


class TestListModels:
    def test_unknown_backend_empty(self):
        assert _gen({"img_provider": "nope"}).list_models() == []

    def test_non_200_empty(self, monkeypatch):
        monkeypatch.setattr("app.image_generator.httpx.get", lambda *a, **k: FakeResp(500))
        assert _gen({"img_provider": "sdapi"}).list_models() == []

    def test_exception_empty(self, monkeypatch):
        def _raise(*a, **k):
            raise httpx.ConnectError("x")

        monkeypatch.setattr("app.image_generator.httpx.get", _raise)
        assert _gen({"img_provider": "sdapi"}).list_models() == []

    def test_success(self, monkeypatch):
        monkeypatch.setattr("app.image_generator.httpx.get", lambda *a, **k: FakeResp(200, [{"model_name": "m"}]))
        assert _gen({"img_provider": "sdapi"}).list_models() == ["m"]


class TestGenerate:
    def test_empty_prompt_fails(self):
        result = _gen().generate_result("   ")
        assert result.ok is False
        assert "提示词为空" in result.message

    def test_disabled_fails(self):
        result = _gen({"img_provider": "disabled"}).generate_result("a cat")
        assert result.ok is False
        assert "未启用" in result.message

    def test_unknown_backend_fails(self):
        result = _gen({"img_provider": "nope"}).generate_result("a cat")
        assert result.ok is False
        assert "未知的图片后端" in result.message

    def test_sdapi_success(self, monkeypatch):
        png = base64.b64encode(b"fake-png-bytes").decode()
        monkeypatch.setattr("app.image_generator.httpx.post", lambda *a, **k: FakeResp(200, {"images": [png]}))
        gen = _gen({"img_provider": "sdapi"})
        result = gen.generate_result("a cat", width=64, height=64)
        assert result.ok is True
        assert result.data == b"fake-png-bytes"
        assert gen.generate("a cat") == b"fake-png-bytes"

    def test_sdapi_no_images_field(self, monkeypatch):
        monkeypatch.setattr("app.image_generator.httpx.post", lambda *a, **k: FakeResp(200, {}))
        result = _gen({"img_provider": "sdapi"}).generate_result("a cat")
        assert result.ok is False
        assert "images" in result.error

    def test_comfyui_no_base_fails(self, monkeypatch):
        gen = _gen({"img_provider": "comfyui", "img_model": "m.safetensors"})
        monkeypatch.setattr(gen, "base_url", lambda: "")
        result = gen.generate_result("a cat")
        assert result.ok is False
        assert "未配置后端地址" in result.error


class TestSaveAndNovel:
    def test_save_image(self, tmp_path):
        path = _gen().save_image(b"data", tmp_path, "cover")
        assert path == tmp_path / "images" / "cover.png"
        assert path.read_bytes() == b"data"

    def test_generate_to_novel_success(self, tmp_path, monkeypatch):
        png = base64.b64encode(b"img").decode()
        monkeypatch.setattr("app.image_generator.httpx.post", lambda *a, **k: FakeResp(200, {"images": [png]}))
        result = _gen({"img_provider": "sdapi"}).generate_to_novel("a cat", tmp_path, "cover")
        assert result.ok is True
        assert result.path == tmp_path / "images" / "cover.png"
        assert "已保存到" in result.message

    def test_generate_to_novel_save_failure(self, tmp_path, monkeypatch):
        png = base64.b64encode(b"img").decode()
        monkeypatch.setattr("app.image_generator.httpx.post", lambda *a, **k: FakeResp(200, {"images": [png]}))
        gen = _gen({"img_provider": "sdapi"})

        def _boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(gen, "save_image", _boom)
        result = gen.generate_to_novel("a cat", tmp_path, "cover")
        assert result.ok is False
        assert "保存失败" in result.message

    def test_generate_to_novel_propagates_generation_failure(self, tmp_path):
        result = _gen({"img_provider": "disabled"}).generate_to_novel("a cat", tmp_path, "cover")
        assert result.ok is False
        assert not (tmp_path / "images").exists()
