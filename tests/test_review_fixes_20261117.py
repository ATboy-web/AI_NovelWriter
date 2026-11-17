"""审查修复回归（2026-11-17）：插件 / MCP / 解析 / 原子写 / 脱敏 / 启动容错。

与 `test_cloud_storage_*` 两个文件互补。本文件只测**修复的行为边界**，
不重复各模块已有的功能测试。

| 编号 | 修复 | 用例 |
|---|---|---|
| M-9 | 插件安装不再 `rmtree` 既有目录 | `TestPluginInstallNoOverwrite` |
| L-5 | 插件 URL 安装加超时与体积上限 | `TestPluginDownloadLimits` |
| L-1 | MCP 子进程环境变量剥离敏感项 | `TestMcpChildEnv` |
| L-2 | MCP 远程强制 https | `TestMcpHttpScheme` |
| M-10 | 自定义武器/技能原子写 | `TestCustomWeaponAtomicWrite` |
| M-11 | 故事线文件名归一化 | `TestStoryFileNaming` |
| L-7 | 导出文件原子写 | `TestExportAtomicWrite` |
| L-6 | 诊断日志兜底脱敏 | `TestDiagnosticRedaction` |
| M-3 | 云存储不可用时的降级替身 | `TestStartupFallback` |
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.mcp_system as mcp_system
import app.plugin_system as plugin_system
from app.diagnostic_logger import DiagnosticLogger, is_sensitive_key, redact_text
from app.format_converter import FormatConverter
from app.mcp_system import MCPServerSpec, build_child_env, is_sensitive_env_name

REPO_ROOT = Path(__file__).parent.parent


def _code_only(path: Path) -> str:
    """去掉注释与 docstring 后的源码（修复说明里必然提到旧写法）。"""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    body.pop(0)
    return ast.unparse(tree)


# ====================================================================== M-9 插件目录


class TestPluginInstallNoOverwrite:
    """🔴 旧实现在目标目录存在时 `rmtree` —— 可能删掉**另一个**插件。"""

    @pytest.fixture()
    def manager(self, tmp_path: Path) -> plugin_system.PluginManager:
        return plugin_system.PluginManager(
            plugins_dir=tmp_path / "plugins",
            state_file=tmp_path / "state.json",
        )

    def _make_plugin(self, root: Path, name: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "plugin.json").write_text(
            json.dumps({"name": name, "version": "1.0", "type": "tool"}, ensure_ascii=False), encoding="utf-8"
        )
        (root / "main.py").write_text("def get_tools():\n    return []\n", encoding="utf-8")
        return root

    def test_existing_directory_is_not_deleted(self, manager, tmp_path: Path):
        # 已存在目录 foo/，其 plugin.json 里叫 bar（历史上会被误判成"可覆盖"）
        existing = manager.plugins_dir / "foo"
        self._make_plugin(existing, "bar")
        marker = existing / "KEEP.txt"
        marker.write_text("不能被删", encoding="utf-8")

        source = self._make_plugin(tmp_path / "src" / "foo", "foo")
        result = manager.install(str(source))

        assert result.ok is False
        assert "已存在" in result.message
        assert marker.read_text(encoding="utf-8") == "不能被删"
        assert (existing / "plugin.json").is_file()

    def test_fresh_install_still_works(self, manager, tmp_path: Path):
        source = self._make_plugin(tmp_path / "src" / "fresh", "fresh")
        result = manager.install(str(source))
        assert result.ok, result.message
        assert (manager.plugins_dir / "fresh" / "main.py").is_file()
        # 🔴 装完不自动启用
        assert manager.plugins["fresh"].enabled is False


# ====================================================================== L-5 下载限制


class TestPluginDownloadLimits:
    def test_oversized_download_rejected(self, tmp_path: Path, monkeypatch):
        class FakeResponse:
            headers = {"Content-Length": str(plugin_system._MAX_DOWNLOAD_BYTES + 1)}

            def read(self, _n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
        dest = tmp_path / "x.zip"
        with pytest.raises(ValueError, match="文件过大"):
            plugin_system.PluginManager._download_to("https://example.com/x.zip", dest)
        assert not dest.exists() or dest.stat().st_size == 0

    def test_streaming_limit_without_content_length(self, tmp_path: Path, monkeypatch):
        """没有 Content-Length 时，按实际字节数拦截（防分块无限流）。"""
        chunk = b"x" * (64 * 1024)

        class FakeResponse:
            headers = {}

            def __init__(self):
                self.n = 0

            def read(self, _n):
                self.n += 1
                return chunk if self.n < 5000 else b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
        monkeypatch.setattr(plugin_system, "_MAX_DOWNLOAD_BYTES", 200 * 1024)
        with pytest.raises(ValueError, match="超过上限"):
            plugin_system.PluginManager._download_to("https://example.com/x.zip", tmp_path / "x.zip")

    def test_non_http_scheme_rejected(self, tmp_path: Path):
        manager = plugin_system.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "s.json")
        result = manager.install("file:///etc/passwd")
        assert result.ok is False
        assert "协议" in result.message


# ====================================================================== L-1 子进程环境


class TestMcpChildEnv:
    def test_sensitive_names_stripped(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
        monkeypatch.setenv("MY_PASSWORD", "pw")
        monkeypatch.setenv("SAFE_SETTING", "ok")

        env = build_child_env()
        assert "OPENAI_API_KEY" not in env
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert "GITHUB_TOKEN" not in env
        assert "MY_PASSWORD" not in env
        assert env.get("SAFE_SETTING") == "ok"

    def test_explicit_config_env_is_kept(self, monkeypatch):
        """配置里显式写的 env 是配置者主动交出去的，必须保留。"""
        monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
        env = build_child_env({"MY_API_KEY": "intended", "PATH": "x"})
        assert env["MY_API_KEY"] == "intended"
        assert "OPENAI_API_KEY" not in env

    @pytest.mark.parametrize("name", ["api_key", "APIKEY", "access_token", "Cookie", "client_secret"])
    def test_marker_detection(self, name: str):
        assert is_sensitive_env_name(name) is True

    @pytest.mark.parametrize("name", ["PATH", "HOME", "LANG", "PYTHONPATH"])
    def test_normal_names_pass(self, name: str):
        assert is_sensitive_env_name(name) is False

    def test_stdio_uses_builder(self):
        """`_call_stdio` 必须走 `build_child_env`，不能再用 `dict(os.environ)`。"""
        source = _code_only(Path(mcp_system.__file__))
        assert "build_child_env" in source
        assert "dict(os.environ)" not in source


# ====================================================================== L-2 HTTP 传输


class TestMcpHttpScheme:
    @pytest.mark.parametrize(
        "url", ["https://api.example.com/mcp", "http://localhost:8080/mcp", "http://127.0.0.1/mcp"]
    )
    def test_usable_urls(self, url: str):
        spec = MCPServerSpec.from_dict({"name": "x", "transport": "http", "url": url})
        ok, why = spec.is_usable()
        assert ok, why

    @pytest.mark.parametrize("url", ["http://evil.example.com/mcp", "http://192.168.1.9/mcp"])
    def test_remote_http_rejected(self, url: str):
        spec = MCPServerSpec.from_dict({"name": "x", "transport": "http", "url": url})
        ok, why = spec.is_usable()
        assert ok is False
        assert "https" in why

    def test_call_level_guard(self):
        """即使绕过 `is_usable()` 直接 `call()`，也必须被拦。"""
        spec = MCPServerSpec.from_dict({"name": "x", "transport": "http", "url": "http://evil.example.com/mcp"})
        client = mcp_system.MCPClient(spec)
        result = client.call("tools/list")
        assert result.ok is False
        assert "https" in result.message


# ====================================================================== M-10 自定义武器


class TestCustomWeaponAtomicWrite:
    def test_save_produces_valid_json_and_backup(self, tmp_path: Path):
        from app.character_system import CharacterSystem

        custom = tmp_path / "custom.json"
        system = CharacterSystem()
        system.custom_file = custom
        system.custom_weapons = [{"name": "剑"}]
        system.custom_skills = [{"name": "斩"}]

        system._save_custom()
        assert json.loads(custom.read_text(encoding="utf-8"))["weapons"][0]["name"] == "剑"

        system.custom_weapons.append({"name": "刀"})
        system._save_custom()
        assert (custom.parent / (custom.name + ".bak")).exists()

    def test_save_uses_atomic_helper(self):
        """静态兜底：不允许再出现裸 `open(self.custom_file, "w")`。"""
        source = _code_only(REPO_ROOT / "app" / "character_system.py")
        assert "atomic_write_json" in source
        assert 'open(self.custom_file, "w"' not in source


# ====================================================================== M-11 故事线


class TestStoryFileNaming:
    def test_writer_uses_safe_filename(self):
        """写侧必须与 `biography.read_story_arcs` 用同一命名规则。"""
        source = _code_only(REPO_ROOT / "app" / "character_ui.py")
        assert "safe_filename(char_name)" in source
        assert 'f"{char_name}.json"' not in source

    def test_roundtrip_for_unsafe_name(self, tmp_path: Path):
        """带 `/` 的名字：写进去必须能被读取侧读回来。"""
        from app.biography import read_story_arcs
        from app.storage import atomic_write_json, safe_filename

        novel = tmp_path / "novel"
        (novel / "character_stories").mkdir(parents=True)
        name = "a/b"
        atomic_write_json(
            novel / "character_stories" / f"{safe_filename(name)}.json",
            {"name": name, "story_arcs": [], "notes": "OK"},
        )
        assert read_story_arcs(novel, name)["notes"] == "OK"


# ====================================================================== L-7 导出原子写


class TestExportAtomicWrite:
    def test_txt_export_is_valid_and_leaves_no_temp(self, tmp_path: Path):
        converter = FormatConverter(tmp_path)
        out = converter.convert("正文内容", "测试书", "txt")
        assert out
        text = Path(out).read_text(encoding="utf-8")
        assert "正文内容" in text and "测试书" in text
        assert not list((tmp_path / "export").glob(".*tmp*"))

    def test_html_and_markdown(self, tmp_path: Path):
        converter = FormatConverter(tmp_path)
        for fmt in ("html", "markdown"):
            out = converter.convert("正文", "书", fmt)
            assert out and Path(out).is_file()

    def test_commit_failure_preserves_previous_output(self, tmp_path: Path):
        converter = FormatConverter(tmp_path)
        first = converter.convert("第一版", "书", "txt")
        assert first

        def boom(*_a, **_k):
            raise OSError("磁盘满了")

        original = Path(first).read_text(encoding="utf-8")
        converter._commit_output = staticmethod(boom)  # type: ignore[method-assign]
        # `convert()` 把异常转成 None（对外契约），但原文必须完好
        assert converter.convert("第二版", "书", "txt") is None
        assert Path(first).read_text(encoding="utf-8") == original
        # 失败时临时文件必须被清理，不能留在导出目录
        assert not list((tmp_path / "export").glob(".*tmp*"))

    def test_no_double_write(self):
        """静态兜底：导出路径不应再有裸 `open(output_file, "w")`。"""
        source = _code_only(REPO_ROOT / "app" / "format_converter.py")
        assert "open(output_file" not in source


# ====================================================================== L-6 日志脱敏


class TestDiagnosticRedaction:
    @pytest.mark.parametrize(
        "raw,secret",
        [
            ("https://x/y?access_token=abc123&z=1", "abc123"),
            ("Authorization: Bearer eyJhbGciOiJIUzI1Nijunk", "eyJhbGciOiJIUzI1Nijunk"),
            ("key=sk-abcdefghijklmnopqrstuv", "sk-abcdefghijklmnopqrstuv"),
            ("token ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghijklmnopqrstuvwxyz0123"),
        ],
    )
    def test_redacts_inline_secrets(self, raw: str, secret: str):
        assert secret not in redact_text(raw)
        assert "***" in redact_text(raw)

    def test_normal_text_untouched(self):
        assert redact_text("正常文本，没有凭据") == "正常文本，没有凭据"

    def test_dict_keys_are_masked(self, tmp_path: Path):
        logger = DiagnosticLogger(log_dir=tmp_path)
        data = logger._truncate_data({"api_key": "SECRET", "model": "gpt-4o", "nested": {"password": "p"}})
        assert data["api_key"] == "***"
        assert data["model"] == "gpt-4o"
        assert data["nested"]["password"] == "***"

    def test_error_message_is_redacted(self, tmp_path: Path):
        logger = DiagnosticLogger(log_dir=tmp_path)
        message = logger._truncate_data("https://x?access_token=LEAK")
        assert "LEAK" not in message

    @pytest.mark.parametrize("key", ["api_key", "access_token", "password", "cookie", "secret"])
    def test_sensitive_key_marks(self, key: str):
        assert is_sensitive_key(key) is True


# ====================================================================== 启动容错


class TestStartupFallback:
    def test_stub_implements_used_surface(self):
        import novel_app

        stub = novel_app._UnavailableCloudStorage("测试")
        assert stub.get_available_providers() == []
        assert stub.configure_provider("webdav", {}) is False
        assert stub.connect_provider("webdav") is False
        assert stub.upload_novel() is False
        assert stub.download_novel() is False
        assert stub.sync_novel() is False
        stub.close()

    def test_constructor_is_guarded_in_entry(self):
        source = _code_only(REPO_ROOT / "novel_app.py")
        assert "_UnavailableCloudStorage" in source


# ====================================================================== 统计


def test_no_bare_write_in_touched_modules():
    """汇总守卫：本次修复涉及的写盘点都不得是裸 `open(..., "w")`。"""
    targets = {
        "app/cloud_storage.py": ["cloud_config"],
        "app/character_system.py": ["custom_file"],
        "app/format_converter.py": ["output_file"],
    }
    for rel, markers in targets.items():
        source = _code_only(REPO_ROOT / rel)
        for marker in markers:
            assert f'open({marker}, "w"' not in source, f"{rel} 仍有裸写：{marker}"
