"""`plugin_system` 的第二批：ZIP 体积闸、名称解析、卸载守卫、结果结构。

## 为什么这些也要测

- **ZIP 三道体积闸**（成员数 / 单文件 / 总量）缺一条就能做压缩炸弹；
- **路径判据用 `is_relative_to` 而非 `startswith`** —— `/tmp/plugin_evil`
  与前缀相同的 `/tmp/plugin` 不是子目录，`startswith` 会放过它；
- **卸载前必须校验目标在插件根之内** —— 配置被改成 `..` 就能删掉整个作品目录。
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


class TestZipLimits:
    def test_too_many_members_rejected(self, tmp_path):
        archive = tmp_path / "many.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for i in range(ps._MAX_EXTRACT_MEMBERS + 1):
                zf.writestr(f"f{i}.txt", "x")

        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="成员过多"):
            ps.safe_extract(zf, tmp_path / "out")

    def test_single_file_too_large_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ps, "_MAX_EXTRACT_MEMBER_BYTES", 10)
        archive = tmp_path / "big.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("big.txt", "x" * 100)

        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="单个文件过大"):
            ps.safe_extract(zf, tmp_path / "out")

    def test_total_size_over_limit_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ps, "_MAX_EXTRACT_BYTES", 50)
        archive = tmp_path / "total.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for i in range(3):
                zf.writestr(f"f{i}.txt", "x" * 30)

        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="上限"):
            ps.safe_extract(zf, tmp_path / "out")

    def test_prefix_lookalike_path_rejected(self, tmp_path):
        """前缀相同但不是子目录 —— 字符串 `startswith` 会放过这种路径。"""
        archive = tmp_path / "look.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../plugin_evil/x.txt", "x")

        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError, match="不安全"):
            ps.safe_extract(zf, tmp_path / "plugin")


class TestNameResolution:
    def test_read_name_falls_back_to_dir_name(self, tmp_path):
        d = tmp_path / "我的插件"
        d.mkdir()
        (d / "plugin.json").write_text("{ 坏", encoding="utf-8")

        assert ps.PluginManager._read_plugin_name(d) == "我的插件"

    def test_read_name_uses_config(self, tmp_path):
        d = _write_plugin(tmp_path, "目录名", config={"name": "配置里的名字"})

        assert ps.PluginManager._read_plugin_name(d) == "配置里的名字"

    def test_find_plugin_dir_one_level_down(self, tmp_path):
        """GitHub 归档会多套一层 `repo-main/`，`plugin.json` 在那一层里。

        ⚠️ 只钻**一层** —— 所以要放 `tmp_path/repo-main/plugin.json`，
        而不是 `tmp_path/repo-main/插件名/plugin.json`（后者不在支持范围内）。
        """
        wrapper = tmp_path / "repo-main"
        wrapper.mkdir()
        (wrapper / "plugin.json").write_text('{"name": "嵌套插件", "entry": "main.py"}', encoding="utf-8")
        (wrapper / "main.py").write_text(DEFAULT_MAIN, encoding="utf-8")

        assert ps.PluginManager._find_plugin_dir(tmp_path) == wrapper

    def test_install_zip_with_wrapper_dir(self, manager, tmp_path):
        """整条链路：ZIP 里套一层 `repo-main/` 也要装得上。"""
        wrapper = tmp_path / "repo-main"
        wrapper.mkdir()
        (wrapper / "plugin.json").write_text('{"name": "嵌套插件", "entry": "main.py"}', encoding="utf-8")
        (wrapper / "main.py").write_text(DEFAULT_MAIN, encoding="utf-8")
        archive = tmp_path / "n.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in wrapper.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(tmp_path))

        result = manager.install(str(archive))

        assert result.ok is True, result.message
        assert manager.get("嵌套插件") is not None


class TestUninstallGuards:
    def test_path_outside_plugins_dir_refused(self, manager, tmp_path):
        """插件目录被改成根目录之外时必须拒绝删除。"""
        _write_plugin(manager.plugins_dir, "正常插件")
        manager.reload()
        manager.get("正常插件").plugin_dir = tmp_path

        result = manager.uninstall("正常插件")

        assert result.ok is False
        assert "拒绝删除" in result.message

    def test_rmtree_failure_reported(self, manager, monkeypatch):
        _write_plugin(manager.plugins_dir, "删不掉的插件")
        manager.reload()

        def boom(*_a, **_kw):
            raise OSError("文件被占用")

        monkeypatch.setattr(ps.shutil, "rmtree", boom)

        result = manager.uninstall("删不掉的插件")

        assert result.ok is False
        assert "失败" in result.message


class TestResultAndAuditShapes:
    def test_result_as_dict_includes_detail(self):
        result = ps.PluginResult(True, "好了", "插件甲", detail={"x": 1})

        assert result.as_dict()["x"] == 1
        assert result.as_dict()["plugin_name"] == "插件甲"

    def test_audit_summary_for_syntax_error(self):
        audit = ps.PluginAudit(syntax_error="SyntaxError: bad")

        assert "无法解析" in audit.summary()

    def test_audit_summary_for_clean_plugin(self):
        assert ps.PluginAudit().summary() == "未发现高危调用"

    def test_audit_as_dict(self, tmp_path):
        target = tmp_path / "main.py"
        target.write_text("import socket\n", encoding="utf-8")

        data = ps.audit_plugin(target).as_dict()

        assert "socket" in data["imports"]
        assert data["risk_level"] in ("low", "medium", "high")
        assert isinstance(data["dangerous"], list)
