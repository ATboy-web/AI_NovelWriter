"""文生图 + 本地模型：接口补全的门禁。

## 背景

2026-09-17 的一致性审计发现两个功能"有配置、有实现，但**没有入口**"：

| 功能 | 当时的状况 |
|---|---|
| 文生图 | `ImageGenerator.generate()` **全仓零调用**（实例只用来拼状态栏文案），整组 `img_*` 配置喂给没人调用的对象；`img_api_key` 被声明为敏感字段却从未被读取；失败只写 logger、界面拿不到原因 |
| 本地模型 | `AIClient.get_ollama_models()` 只有**测试**调用，界面从未使用 ⇒ 用户只能手打模型名；没有健康探测、没有模型拉取 |

本文件按"**接口存在 + 参数被读 + 调用链可达**"三层来钉，
而不是只断言"类里有这个方法"—— 那正是当初漏掉的地方。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import httpx
import pytest
import respx

from app.image_generator import (
    IMAGE_BACKENDS,
    ImageGenerator,
    ImageGenResult,
    parse_comfyui_models,
    parse_sdapi_models,
)
from app.providers import (
    OLLAMA_PATHS,
    LocalModel,
    parse_pull_progress,
    parse_tags,
    parse_version,
)
from app.providers.registry import default_registry

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_config(**overrides):
    """构造一个只认这些键的假配置（键缺失时返回 default）。"""

    class _Cfg:
        def __init__(self, values):
            self._v = values

        def get(self, key, default=None):
            return self._v.get(key, default)

    return _Cfg(overrides)


# ═══════════════════════════════════ 文生图 ═══════════════════════════════════


class TestImageBackendRegistry:
    """后端注册表：新增后端只改一处。"""

    def test_registry_is_not_empty_and_has_expected_keys(self):
        assert set(IMAGE_BACKENDS) >= {"comfyui", "sdapi"}

    def test_every_backend_is_self_consistent(self):
        for key, b in IMAGE_BACKENDS.items():
            assert b.key == key, f"{key} 的 key 与字典键不一致"
            assert b.label, f"{key} 缺 label"
            assert b.default_base.startswith("http"), f"{key} 的默认地址不像 URL"
            assert b.health_path.startswith("/"), f"{key} 的健康探测路径必须是绝对路径"

    def test_backends_with_model_list_have_parser(self):
        for key, b in IMAGE_BACKENDS.items():
            if b.models_path:
                assert b.models_parser is not None, f"{key} 声明了 models_path 却没有解析函数"

    def test_disabled_is_not_a_backend(self):
        """`disabled` 是"关闭"的意思，不能悄悄变成某个后端。"""
        assert "disabled" not in IMAGE_BACKENDS


class TestImageParsers:
    """解析器必须对**真实响应形状**有效，而不是对理想形状有效。"""

    def test_parse_comfyui_models_real_shape(self):
        # 形状取自 ComfyUI 的 /object_info/CheckpointLoaderSimple
        data = {
            "CheckpointLoaderSimple": {
                "input": {"required": {"ckpt_name": [["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"], {}]}}
            }
        }
        assert parse_comfyui_models(data) == ["sd_xl_base_1.0.safetensors", "dreamshaper_8.safetensors"]

    @pytest.mark.parametrize(
        "bad",
        [
            {},
            {"CheckpointLoaderSimple": {}},
            {"CheckpointLoaderSimple": {"input": {}}},
            {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": []}}}},
            None,
            [],
            "x",
        ],
    )
    def test_parse_comfyui_models_is_defensive(self, bad):
        """层级很深的接口一旦改版就会缺字段 —— 必须返回空列表而不是抛异常。"""
        assert parse_comfyui_models(bad) == []

    def test_parse_sdapi_models_prefers_model_name(self):
        """`model_name` 才是 txt2img 实际接受的值；`title` 带 hash 后缀。"""
        data = [
            {"title": "sd_xl_base_1.0 [a1b2c3]", "model_name": "sd_xl_base_1.0", "filename": "x.safetensors"},
            {"title": "only_title"},
        ]
        assert parse_sdapi_models(data) == ["sd_xl_base_1.0", "only_title"]

    @pytest.mark.parametrize("bad", [{}, None, "x", [1, 2], [{}]])
    def test_parse_sdapi_models_is_defensive(self, bad):
        assert parse_sdapi_models(bad) == []


class TestImageResultIsStructured:
    """失败必须有**可读原因**，这是旧实现最大的问题（只写 logger 后返回 None）。"""

    def test_disabled_gives_actionable_message(self):
        gen = ImageGenerator(_make_config(img_provider="disabled"))
        r = gen.generate_result("prompt")
        assert not r.ok and r.data is None
        assert "未启用" in r.message and "设置" in r.message, f"提示不够可操作：{r.message}"

    def test_unknown_backend_names_the_backend(self):
        gen = ImageGenerator(_make_config(img_provider="nope"))
        r = gen.generate_result("prompt")
        assert not r.ok
        assert "nope" in r.message

    def test_empty_prompt_is_rejected(self):
        gen = ImageGenerator(_make_config(img_provider="comfyui"))
        assert not gen.generate_result("   ").ok

    def test_generate_keeps_old_contract(self):
        """`generate()` 仍返回 bytes/None —— 旧调用方不能被打断。"""
        gen = ImageGenerator(_make_config(img_provider="disabled"))
        assert gen.generate("prompt") is None
        assert gen.last_error, "失败后 last_error 应当有内容供调用方读取"

    def test_provider_unreachable_explains_connection(self):
        gen = ImageGenerator(_make_config(img_provider="comfyui", img_api_base="http://127.0.0.1:9"))
        r = gen.check_backend(timeout=0.5)
        assert not r.ok
        assert "连不上" in r.message and "服务已启动" in r.message

    def test_result_round_trips_through_dict(self):
        r = ImageGenResult(ok=True, provider="comfyui", data=b"x", width=512, height=512)
        d = r.as_dict()
        assert d["ok"] and d["provider"] == "comfyui" and d["bytes"] == 1


class TestImageApiKeyIsNowRead:
    """`img_api_key` 曾被声明为敏感字段却零读取 —— 需要鉴权的端点因此完全不可用。"""

    def test_key_becomes_bearer_header(self):
        gen = ImageGenerator(_make_config(img_provider="comfyui", img_api_key="sk-img"))
        assert gen._headers() == {"Authorization": "Bearer sk-img"}

    def test_no_key_means_no_header(self):
        """本地直连是默认场景，不能凭空加一个头。"""
        for value in ("", None, "   "):
            gen = ImageGenerator(_make_config(img_provider="comfyui", img_api_key=value))
            assert gen._headers() == {}

    def test_key_is_actually_sent_on_request(self):
        """参数被读 ≠ 被用上：这里真的发一次请求，确认头里带了 key。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"sd-models": []})

        gen = ImageGenerator(_make_config(img_provider="sdapi", img_api_base="http://img.local", img_api_key="sk-img"))
        with respx.mock:
            respx.get("http://img.local/sdapi/v1/sd-models").mock(side_effect=handler)
            gen.list_models()
        assert seen.get("auth") == "Bearer sk-img"


class TestImageDimensionsFromConfig:
    def test_config_drives_dimensions(self):
        gen = ImageGenerator(_make_config(img_provider="comfyui", img_width="768", img_height="432"))
        assert gen._dimension(None, "img_width") == 768
        assert gen._dimension(None, "img_height") == 432

    def test_explicit_argument_wins(self):
        gen = ImageGenerator(_make_config(img_provider="comfyui", img_width=768))
        assert gen._dimension(512, "img_width") == 512

    @pytest.mark.parametrize("bad", ["abc", "", None, 0, -8])
    def test_bad_value_falls_back_without_raising(self, bad):
        gen = ImageGenerator(_make_config(img_provider="comfyui", img_width=bad))
        assert gen._dimension(None, "img_width") == 1024


class TestImageHasARealEntryPoint:
    """**这一条是本轮的核心**：当初的问题不是"接口不好"，而是"根本没有调用方"。"""

    def test_illustration_panel_exists_and_is_registered(self):
        from app.panels import registry

        registry.load_panels()
        keys = {s.key for s in registry.all_panels()}
        assert "illustration" in keys, "插图面板没有登记 —— 文生图又变回不可达"
        assert not registry.LOAD_FAILURES, f"面板加载失败：{registry.LOAD_FAILURES}"

    def test_panel_actually_calls_the_generator(self):
        """源码级确认面板真的调了生成（而不是又建一个没人用的对象）。"""
        src = (_REPO_ROOT / "app" / "panels" / "illustration_panel.py").read_text(encoding="utf-8")
        assert "generate_to_novel" in src, "面板没有调用生成入口"
        assert "check_backend" in src, "面板没有后端检测入口"

    def test_panel_does_not_require_pil(self):
        """打包 EXE 有意排除 PIL，面板必须能不带它工作。"""
        src = (_REPO_ROOT / "app" / "panels" / "illustration_panel.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # 找所有 ImportFrom("PIL")，确认都被 try/except ImportError 包着
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    if isinstance(child, ast.ImportFrom) and (child.module or "").startswith("PIL"):
                        assert any(
                            isinstance(h.type, ast.Name) and h.type.id == "ImportError" for h in node.handlers
                        ), "PIL 的导入没有 `except ImportError` 兜底"
                        return
        pytest.skip("面板里没有 PIL 导入（也符合预期）")

    def test_panel_is_declared_for_packaging(self):
        """原生面板是按字符串动态导入的，spec 不列就会在打包后少一块。"""
        spec = (_REPO_ROOT / "installer" / "novel_app.spec").read_text(encoding="utf-8")
        assert "app.panels.illustration_panel" in spec, "spec 的 hiddenimports 没列插图面板"

    def test_panel_runs_generation_off_the_ui_thread(self):
        """SD 一张图几十秒，同步跑会让界面假死。"""
        src = (_REPO_ROOT / "app" / "panels" / "illustration_panel.py").read_text(encoding="utf-8")
        assert "BackgroundRunner" in src, "生成没有走后台线程"


# ═══════════════════════════════════ 本地模型 ═══════════════════════════════════


class TestOllamaPathConstants:
    def test_paths_are_single_source(self):
        spec = default_registry().get("ollama")
        assert spec.chat_path == OLLAMA_PATHS["chat"], (
            "registry 的 chat_path 与 OLLAMA_PATHS 不一致 —— 同一路径写两处会漂移"
        )

    def test_expected_paths_present(self):
        for key in ("chat", "tags", "version", "pull"):
            assert OLLAMA_PATHS.get(key), f"缺少 {key} 路径"


class TestLocalModelParsers:
    def test_parse_tags_real_shape(self):
        data = {
            "models": [
                {
                    "name": "qwen3:8b",
                    "size": 5 * 1024**3,
                    "modified_at": "2026-09-01T00:00:00Z",
                    "details": {"parameter_size": "8.2B", "quantization_level": "Q4_K_M", "family": "qwen3"},
                }
            ]
        }
        models = parse_tags(data)
        assert len(models) == 1
        m = models[0]
        assert m.name == "qwen3:8b" and m.parameter_size == "8.2B" and m.quantization == "Q4_K_M"
        assert m.size_gb == 5.0
        assert "qwen3:8b" in m.label()

    @pytest.mark.parametrize("bad", [{}, None, [], {"models": "x"}, {"models": [1, {}, {"no_name": 1}]}])
    def test_parse_tags_is_defensive(self, bad):
        assert parse_tags(bad) == []

    def test_parse_version(self):
        assert parse_version({"version": "0.3.12"}) == "0.3.12"
        assert parse_version({}) == ""
        assert parse_version(None) == ""

    def test_parse_pull_progress_computes_percent(self):
        info = parse_pull_progress('{"status": "downloading", "completed": 30, "total": 120}')
        assert info["percent"] == 25.0 and not info["done"]

    def test_parse_pull_progress_detects_done(self):
        assert parse_pull_progress('{"status": "success"}')["done"] is True

    def test_parse_pull_progress_surfaces_error(self):
        assert parse_pull_progress('{"error": "model not found"}')["error"] == "model not found"

    @pytest.mark.parametrize("bad", ["", "  ", "not json", "[]", "123"])
    def test_parse_pull_progress_rejects_junk(self, bad):
        assert parse_pull_progress(bad) is None

    def test_local_model_dict_round_trip(self):
        m = LocalModel(name="a", size=1024, parameter_size="7B")
        assert (
            LocalModel(**{k: v for k, v in m.as_dict().items() if k in {"name", "size", "parameter_size"}}).name == "a"
        )


class TestLocalModelClientApi:
    """`AIClient` 上的三个新接口必须真的打对地址、并正确解析。"""

    def _client(self, base="http://localhost:11434"):
        from app.ai_client import AIClient

        cfg = _make_config(api_provider="ollama", api_base=base, api_key="")
        return AIClient(cfg)

    @respx.mock
    def test_list_local_models_hits_tags(self):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(
                200,
                json={"models": [{"name": "qwen3:8b", "size": 100, "details": {"parameter_size": "8B"}}]},
            )
        )
        models = self._client().list_local_models()
        assert [m.name for m in models] == ["qwen3:8b"]
        assert models[0].parameter_size == "8B"

    @respx.mock
    def test_list_local_models_empty_when_service_down(self):
        respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        assert self._client().list_local_models() == []

    @respx.mock
    def test_list_local_models_empty_on_error_status(self):
        respx.get("http://localhost:11434/api/tags").mock(return_value=httpx.Response(500))
        assert self._client().list_local_models() == []

    @respx.mock
    def test_check_local_service_ok(self):
        respx.get("http://localhost:11434/api/version").mock(
            return_value=httpx.Response(200, json={"version": "0.3.12"})
        )
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": "a"}]})
        )
        ok, message = self._client().check_local_service()
        assert ok and "0.3.12" in message and "1" in message

    @respx.mock
    def test_check_local_service_failure_is_explained(self):
        respx.get("http://localhost:11434/api/version").mock(side_effect=httpx.ConnectError("refused"))
        ok, message = self._client().check_local_service()
        assert not ok and "连不上" in message

    @respx.mock
    def test_pull_reports_progress_and_completion(self):
        lines = "\n".join(
            [
                '{"status": "pulling manifest"}',
                '{"status": "downloading", "completed": 5, "total": 10}',
                '{"status": "success"}',
            ]
        )
        respx.post("http://localhost:11434/api/pull").mock(return_value=httpx.Response(200, text=lines))
        seen = []
        ok, message = self._client().pull_local_model("qwen3:8b", on_progress=seen.append)
        assert ok, message
        assert any(p.get("percent") == 50.0 for p in seen), f"进度回调没收到百分比：{seen}"

    def test_pull_rejects_empty_name(self):
        ok, message = self._client().pull_local_model("   ")
        assert not ok and "模型名" in message

    @respx.mock
    def test_pull_surfaces_server_error(self):
        respx.post("http://localhost:11434/api/pull").mock(
            return_value=httpx.Response(200, text='{"error": "model not found"}')
        )
        ok, message = self._client().pull_local_model("nope")
        assert not ok and "model not found" in message


class TestLocalModelUiIsWired:
    """接口存在 ≠ 界面用得上 —— 当初 `get_ollama_models` 就是只被测试调用。"""

    def test_settings_page_uses_the_new_api(self):
        src = (_REPO_ROOT / "app" / "ai_settings_ui.py").read_text(encoding="utf-8")
        assert "list_local_models" in src, "设置页没有使用模型列表接口"
        assert "check_local_service" in src, "设置页没有使用服务检测接口"

    def test_visibility_is_capability_driven(self):
        """显隐必须看能力位 `local`，而不是 `provider == "ollama"`。"""
        src = (_REPO_ROOT / "app" / "ai_settings_ui.py").read_text(encoding="utf-8")
        assert "can_list_local_models" in src

    def test_capability_helper_uses_local_flag(self):
        from app.ai_client import AIClient

        client = AIClient.__new__(AIClient)
        client.config = _make_config(api_provider="ollama")
        client.registry = default_registry()
        assert client.can_list_local_models("ollama") is True
        assert client.can_list_local_models("deepseek") is False

    def test_get_ollama_models_delegates_to_single_source(self):
        """旧名字必须委托给新实现，而不是自己再解析一遍。"""
        src = inspect.getsource(__import__("app.ai_client", fromlist=["AIClient"]).AIClient.get_ollama_models)
        assert "list_local_models" in src, "get_ollama_models 又自己解析了一遍（两处实现会漂移）"


# ═══════════════════════════════ 真实 Tk 构建（可跳过） ═══════════════════════════════


@pytest.fixture(scope="module")
def tk_root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as exc:  # noqa: BLE001 - 无显示环境则跳过
        pytest.skip(f"无可用 Tk 环境：{exc}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


class _FakeApp:
    """最小宿主：只提供插图面板真正会读的东西。"""

    def __init__(self, novel_dir, generator=None):
        self.current_novel_dir = novel_dir
        self.current_chapter = 1
        self.logs = []
        self.image_gen = generator
        self.root = None

    def _log(self, message):
        self.logs.append(message)


def _novel_with_prompts(tmp_path: Path) -> Path:
    novel = tmp_path / "试作"
    d = novel / "scene_prompts"
    d.mkdir(parents=True)
    (d / "ch0001_epic_scene_1_prompt.txt").write_text(
        "章节: 第1章\n类型: 震撼场面\n场景: 主角立于山巅\nAI提示词:\nhero on a cliff, epic, (cinematic)\n",
        encoding="utf-8",
    )
    return novel


class TestIllustrationPanelRealTk:
    """面板必须**真的能建起来**。

    前面的测试只验证了"源码里有调用"，那不能排除运行时报错
    （例如把 `pretty_tree` 的返回值当成 Treeview 用 —— 本轮真踩过：
    它返回的是 dict，且返回的 Frame 还需要自行 pack）。
    """

    def test_builds_and_lists_prompts(self, tk_root, tmp_path):
        import tkinter as tk

        from app.panels.illustration_panel import IllustrationPanel

        novel = _novel_with_prompts(tmp_path)
        app = _FakeApp(novel)
        frame = tk.Frame(tk_root)
        panel = IllustrationPanel(app)
        panel.build(frame)

        assert panel.is_built is True
        assert frame.winfo_children(), "面板必须真的画出内容"
        assert panel._prompts, "没有列出 scene_prompts 下的提示词"
        assert panel._tree.get_children(""), "表格里没有任何行"
        panel.detach()

    def test_build_without_novel_is_graceful(self, tk_root):
        import tkinter as tk

        from app.panels.illustration_panel import IllustrationPanel

        frame = tk.Frame(tk_root)
        panel = IllustrationPanel(_FakeApp(None))
        panel.build(frame)  # 不应抛异常
        assert panel._prompts == []
        panel.detach()

    def test_events_do_not_crash(self, tk_root, tmp_path):
        import tkinter as tk

        from app.events import TOPIC_CHAPTER_SAVED, TOPIC_NOVEL_OPENED
        from app.panels.illustration_panel import IllustrationPanel

        frame = tk.Frame(tk_root)
        panel = IllustrationPanel(_FakeApp(_novel_with_prompts(tmp_path)))
        panel.build(frame)
        panel.on_event(TOPIC_NOVEL_OPENED, {})
        panel.on_event(TOPIC_CHAPTER_SAVED, {"chapter": 1})
        panel.on_event("无关主题", {})
        panel.on_show()
        panel.detach()

    def test_prompt_body_extraction_prefers_ai_prompt(self, tmp_path):
        from app.panels.illustration_panel import IllustrationPanel

        p = _novel_with_prompts(tmp_path) / "scene_prompts" / "ch0001_epic_scene_1_prompt.txt"
        body = IllustrationPanel._read_prompt_body(p)
        assert body == "hero on a cliff, epic, (cinematic)"

    def test_prompt_body_falls_back_to_scene_line(self, tmp_path):
        """没有 `AI提示词:` 标记时退回 `场景:` 行（手动生成的提示词可能没有该标记）。"""
        from app.panels.illustration_panel import IllustrationPanel

        p = tmp_path / "x.txt"
        p.write_text("章节: 第1章\n场景: 只有场景行\n", encoding="utf-8")
        assert IllustrationPanel._read_prompt_body(p) == "只有场景行"

    def test_generate_requires_selection(self, tk_root, tmp_path):
        """未选中提示词时点生成 —— 应给出提示而不是抛异常。"""
        import tkinter as tk

        from app.panels.illustration_panel import IllustrationPanel

        frame = tk.Frame(tk_root)
        panel = IllustrationPanel(
            _FakeApp(_novel_with_prompts(tmp_path), generator=ImageGenerator(_make_config(img_provider="comfyui")))
        )
        panel.build(frame)
        panel._current = None
        panel._on_generate()
        assert "选中" in panel._hint.cget("text")
        panel.detach()

    def test_generate_runs_without_blocking_and_reports(self, tk_root, tmp_path, monkeypatch):
        """端到端：选中提示词 → 生成（打桩的后端）→ 结果回主线程显示。

        用打桩的 `generate_to_novel` 替代真实网络，只验证**调用链通**：
        面板 → ImageGenerator → 回调更新界面。
        """
        import tkinter as tk

        from app.panels.illustration_panel import IllustrationPanel

        gen = ImageGenerator(_make_config(img_provider="comfyui"))
        called = {}

        def fake_generate_to_novel(prompt, novel_dir, name, **kw):
            called["prompt"] = prompt
            called["name"] = name
            return ImageGenResult(ok=True, provider="comfyui", data=b"png", width=0, message="生成成功")

        monkeypatch.setattr(gen, "generate_to_novel", fake_generate_to_novel, raising=False)

        frame = tk.Frame(tk_root)
        app = _FakeApp(_novel_with_prompts(tmp_path), generator=gen)
        panel = IllustrationPanel(app)
        panel.build(frame)
        panel._current = panel._prompts[0]
        panel._on_generate()
        # `_runner` 的 ui 是 app.root（此处为 None）⇒ 回调同步执行，无需等待
        assert called.get("prompt") == "hero on a cliff, epic, (cinematic)"
        assert called.get("name") == "ch0001_epic_scene_1_prompt"
        assert panel._hint.cget("text")
        panel.detach()
