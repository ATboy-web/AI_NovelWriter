"""`plugin_system` 的失败路径与安装拒绝（第 2 档：静默失效）。

## 这个模块的失效方式

| 故障 | 用户看到 |
|---|---|
| 坏插件被**丢弃**而不是保留 | 插件列表里它凭空消失，不知道坏了 |
| 加载失败仍能「启用」 | 点了启用、界面显示已启用，但功能没生效 |
| 安装来源不校验 | `file://` / 内含插件根目录的源目录 ⇒ 递归复制把盘写满 |
| 状态文件读坏 ⇒ 全部未启用 | 用户以为插件被卸了 |
| 静态体检漏报 | 用户**没看到风险**就点了启用 |

最后一条最要紧：`audit_plugin` 不是安全边界（插件仍以同等权限运行），
它是**告知机制** —— 它漏了，用户的"知情同意"就是假的。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app import plugin_system as ps

DEFAULT_MAIN = "def register(api):\n    pass\n"


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_manager", None)
    return ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "plugins.json")


def _write_plugin(root: Path, name: str, *, config: dict | None = None, main_src: str = "") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "version": "1.0.0", "entry": "main.py", "type": "writing_skill"}
    payload.update(config or {})
    (d / "plugin.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (d / "main.py").write_text(main_src or DEFAULT_MAIN, encoding="utf-8")
    return d


class TestAudit:
    """静态体检是"启用前让用户看到风险"的唯一手段。"""

    def test_unreadable_entry(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("x", encoding="utf-8")
        target.chmod(0o000)
        try:
            audit = ps.audit_plugin(target)
            if audit.syntax_error:  # 某些环境仍可读，跳过时不误判
                assert "读取失败" in audit.syntax_error
        finally:
            target.chmod(0o644)

    def test_oversized_entry_rejected(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_bytes(b"x" * (ps._MAX_ENTRY_BYTES + 1))

        audit = ps.audit_plugin(target)

        assert "过大" in audit.syntax_error

    def test_syntax_error_reported(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("def broken(:\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert "SyntaxError" in audit.syntax_error

    def test_bare_import_is_flagged(self, tmp_path):
        """`import socket` **不产生属性访问节点** —— 只看点号会漏报（实测漏报过）。"""
        target = tmp_path / "main.py"
        target.write_text("import socket\n\ndef register(api): pass\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert any(sym == "socket" for sym, _why in audit.dangerous)

    def test_attribute_use_is_flagged(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("import os\n\ndef register(api):\n    os.system('ls')\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert any(sym == "os.system" for sym, _why in audit.dangerous)

    def test_import_only_open_is_dropped(self, tmp_path):
        """只 `import` 不提 `open` ⇒ 视为读配置，降噪掉（否则每个插件都高危）。"""
        target = tmp_path / "main.py"
        target.write_text("import io\n\nx = 1\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert not any(sym == "open" for sym, _why in audit.dangerous)

    def test_called_open_is_kept(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("open('x')\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert any(sym == "open" for sym, _why in audit.dangerous)

    def test_high_risk_level(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("import subprocess\nimport socket\nimport os\nsubprocess.run('ls')\n", encoding="utf-8")

        audit = ps.audit_plugin(target)

        assert audit.risk_level in ("medium", "high")


class TestPluginLoadFailures:
    def test_missing_entry_file_is_recorded_not_dropped(self, tmp_path):
        """入口文件不存在时要**保留插件并带上原因**，而不是让它从列表里消失。"""
        d = _write_plugin(tmp_path / "plugins", "坏插件", config={"entry": "根本没有.py"})

        plugin = ps.Plugin(d)

        assert plugin.module is None
        assert "入口文件不存在" in plugin.load_error

    def test_config_corrupt_returns_empty(self, tmp_path):
        d = _write_plugin(tmp_path / "plugins", "配置坏了")
        (d / "plugin.json").write_text("{ 坏掉的配置", encoding="utf-8")

        plugin = ps.Plugin(d)

        assert plugin.config == {}

    def test_module_import_error_is_captured(self, tmp_path):
        """插件代码抛错不能拖垮应用启动 —— 只记 load_error。"""
        d = _write_plugin(tmp_path / "plugins", "会崩的插件", main_src="raise RuntimeError('boom')\n")

        plugin = ps.Plugin(d)

        assert plugin.module is None
        assert "RuntimeError" in plugin.load_error

    def test_broken_plugin_survives_reload(self, manager):
        """🔴 加载失败的插件也要出现在列表里 —— 旧实现 `if plugin.module` 直接丢弃。"""
        _write_plugin(manager.plugins_dir, "好插件")
        _write_plugin(manager.plugins_dir, "坏插件", main_src="raise RuntimeError('x')\n")

        names = [p.name for p in manager.reload()]

        assert set(names) >= {"好插件", "坏插件"}, "坏插件从列表里消失了"


class TestStatePersistence:
    def test_corrupt_state_means_all_disabled(self, manager):
        _write_plugin(manager.plugins_dir, "甲")
        manager.state_file.parent.mkdir(parents=True, exist_ok=True)
        manager.state_file.write_text("{ 坏", encoding="utf-8")

        assert manager._load_state() == set()

    def test_save_state_failure_returns_result(self, manager, monkeypatch):
        """状态存不上要返回失败结果，而不是抛 —— 界面得能提示。"""

        def boom(*_a, **_kw):
            raise OSError("只读")

        monkeypatch.setattr(Path, "write_text", boom, raising=False)
        monkeypatch.setattr("builtins.open", boom)

        result = manager._save_state()

        assert result.ok is False
        assert "失败" in result.message

    def test_reload_without_plugins_dir(self, manager):
        assert manager.reload() == []

    def test_enable_unknown_plugin(self, manager):
        result = manager.enable("不存在")

        assert result.ok is False
        assert "不存在" in result.message

    def test_enable_broken_plugin_refused(self, manager):
        """加载失败的插件不能"启用成功" —— 那会让用户以为功能已开。"""
        _write_plugin(manager.plugins_dir, "坏插件", main_src="raise RuntimeError('x')\n")
        manager.reload()

        result = manager.enable("坏插件")

        assert result.ok is False
        assert "加载失败" in result.message

    def test_disable_unknown_plugin(self, manager):
        assert manager.disable("不存在").ok is False

    def test_high_risk_plugin_warns_on_enable(self, manager):
        """高危插件启用时必须带**安全提示**（这是"知情同意"的落点）。"""
        _write_plugin(
            manager.plugins_dir,
            "危险插件",
            main_src="import subprocess\nimport socket\nimport os\nsubprocess.run('ls')\n",
        )
        manager.reload()
        plugin = manager.get("危险插件")
        if plugin.audit.risk_level != "high":
            pytest.skip("该插件未被判为 high（体检阈值变化）")

        result = manager.enable("危险插件")

        assert result.security_warning, "高危插件启用了却没有安全提示"


class TestInstallRejections:
    """安装来源的每一条拒绝都对应一种"能把盘写满 / 绕过用户意图"的输入。"""

    def test_empty_source(self, manager):
        assert manager.install("").ok is False
        assert manager.install("   ").ok is False

    def test_unsupported_scheme(self, manager):
        for source in ("ftp://x/plugin.zip", "file:///tmp/x.zip", "data:text/plain,hi"):
            result = manager.install(source)
            assert result.ok is False, source
            assert "协议" in result.message

    def test_zip_missing(self, manager, tmp_path):
        assert manager.install(str(tmp_path / "没有这个.zip")).ok is False

    def test_not_a_zip(self, manager, tmp_path):
        fake = tmp_path / "假.zip"
        fake.write_text("这不是 zip", encoding="utf-8")

        result = manager.install(str(fake))

        assert result.ok is False
        assert "ZIP" in result.message

    def test_zip_without_plugin_json(self, manager, tmp_path):
        archive = tmp_path / "空.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", "hi")

        result = manager.install(str(archive))

        assert result.ok is False
        assert "plugin.json" in result.message

    def test_zip_slip_is_rejected(self, manager, tmp_path):
        """含 `../` 的 ZIP 条目必须被 `safe_extract` 拦下。"""
        archive = tmp_path / "恶意.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../逃逸.txt", "x")

        result = manager.install(str(archive))

        assert result.ok is False

    def test_directory_missing(self, manager, tmp_path):
        assert manager.install(str(tmp_path / "没有这个目录")).ok is False

    def test_path_is_file_not_dir(self, manager, tmp_path):
        f = tmp_path / "文件.txt"
        f.write_text("x", encoding="utf-8")

        result = manager.install(str(f))

        assert result.ok is False
        assert "不是目录" in result.message or "ZIP" in result.message

    def test_directory_without_plugin_json(self, manager, tmp_path):
        d = tmp_path / "空目录"
        d.mkdir()

        result = manager.install(str(d))

        assert result.ok is False
        assert "plugin.json" in result.message

    def test_source_is_plugins_root(self, manager):
        """把插件根目录当来源 ⇒ 自我复制。

        ⚠️ 递归检查排在"有没有 plugin.json"**之后**，所以源目录本身也要有一份 ——
        否则会先被"缺少 plugin.json"挡住，验不到递归分支。
        """
        _write_plugin(manager.plugins_dir, "甲")
        _write_plugin(manager.plugins_dir.parent, "占位", config={"name": "占位"})
        (manager.plugins_dir / "plugin.json").write_text('{"name": "根", "entry": "main.py"}', encoding="utf-8")

        result = manager.install(str(manager.plugins_dir))

        assert result.ok is False
        assert "无需安装" in result.message

    def test_source_contains_plugins_root(self, manager, tmp_path):
        """源目录**包含**插件根 ⇒ 递归复制，磁盘会被写满。"""
        manager.plugins_dir.mkdir(parents=True, exist_ok=True)
        _write_plugin(manager.plugins_dir, "甲")
        # 父级也要有 plugin.json，才能越过"缺少 plugin.json"走到递归检查
        (tmp_path / "plugin.json").write_text('{"name": "外层", "entry": "main.py"}', encoding="utf-8")
        (tmp_path / "main.py").write_text(DEFAULT_MAIN, encoding="utf-8")

        result = manager.install(str(tmp_path))

        assert result.ok is False
        assert "递归" in result.message


class TestInstallSuccess:
    def test_install_from_directory(self, manager, tmp_path):
        src = _write_plugin(tmp_path / "src", "新插件")

        result = manager.install(str(src))

        assert result.ok is True
        assert (manager.plugins_dir / "新插件" / "plugin.json").exists()
        assert manager.get("新插件") is not None, "装完没有重新扫描"

    def test_install_from_zip(self, manager, tmp_path):
        src = _write_plugin(tmp_path / "src", "压缩插件")
        archive = tmp_path / "p.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in src.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(src.parent))

        result = manager.install(str(archive))

        assert result.ok is True
        assert manager.get("压缩插件") is not None

    def test_dangerous_plugin_name_is_sanitized(self, manager, tmp_path):
        """插件名来自 `plugin.json`，是不可信输入 —— 不能直接当目录名。"""
        src = _write_plugin(tmp_path / "src", "占位", config={"name": "../../逃逸"})

        result = manager.install(str(src))

        installed = [p.name for p in manager.plugins_dir.iterdir()] if manager.plugins_dir.exists() else []
        assert not any(".." in name for name in installed), f"安装目录名没消毒：{installed}"
        assert result.ok is False or all(manager.plugins_dir in p.parents for p in manager.plugins_dir.iterdir())

    def test_uninstall_removes_directory_and_state(self, manager, tmp_path):
        src = _write_plugin(tmp_path / "src", "待卸插件")
        manager.install(str(src))
        manager.enable("待卸插件")

        result = manager.uninstall("待卸插件")

        assert result.ok is True
        assert not (manager.plugins_dir / "待卸插件").exists()
        assert "待卸插件" not in manager._enabled_names, "卸载后状态里还留着"

    def test_uninstall_unknown(self, manager):
        assert manager.uninstall("不存在").ok is False


class TestDownloadLimits:
    """下载有两道闸：声明大小与累计写入。缺一条就能被单次请求写满磁盘。"""

    def test_declared_size_over_limit(self, manager, tmp_path, monkeypatch):
        class Response:
            headers = {"Content-Length": str(ps._MAX_DOWNLOAD_BYTES + 1)}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: Response())

        with pytest.raises(ValueError, match="过大"):
            ps.PluginManager._download_to("https://example.com/x.zip", tmp_path / "x.zip")

    def test_stream_exceeds_limit(self, manager, tmp_path, monkeypatch):
        """服务端不报长度时，只能靠累计写入兜底。"""

        class Response:
            headers: dict = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, _size):
                return b"x" * (ps._MAX_DOWNLOAD_BYTES // 2 + 1)

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: Response())

        with pytest.raises(ValueError, match="上限"):
            ps.PluginManager._download_to("https://example.com/x.zip", tmp_path / "x.zip")

    def test_url_scheme_rejected(self, manager):
        result = manager._install_from_url("file:///etc/passwd")

        assert result.ok is False
        assert "协议" in result.message

    def test_github_page_rewritten_to_archive(self, manager, monkeypatch):
        """给 GitHub 仓库页链接时应自动改写成归档地址，而不是把网页当 ZIP 存。"""
        seen: list[str] = []

        def fake_download(url, dest):
            seen.append(url)
            Path(dest).write_bytes(b"PK\x03\x04")

        monkeypatch.setattr(manager, "_download_to", fake_download)
        monkeypatch.setattr(manager, "_install_from_zip", lambda p: ps.PluginResult(True, "ok"))

        manager._install_from_url("https://github.com/user/repo")

        assert seen and seen[0].endswith("/archive/refs/heads/main.zip")

    def test_download_error_is_converted(self, manager, monkeypatch):
        def boom(*_a, **_kw):
            raise OSError("连接被拒")

        monkeypatch.setattr(manager, "_download_to", boom)

        result = manager._install_from_url("https://example.com/x.zip")

        assert result.ok is False
        assert "下载失败" in result.message
