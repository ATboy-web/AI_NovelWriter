"""插件系统测试（v3.2 重新启用 + 改良）。

## 分层

1. **纯逻辑** —— 名称消毒、Zip Slip、静态体检、能力汇总。不碰网络、不碰 Tk。
2. **真实安装流程** —— 用 `tmp_path` 造真插件目录 / 真 ZIP，走完整 `install`
   → `enable` → 消费端读到 → `disable` → `uninstall` 闭环。
3. **🔴 接线守卫（本文件最重要的一层）** ——
   插件系统曾经因为"全仓零引用"被当死代码删除（`34ce8b1`）。
   所以必须有一个测试**钉住"读它的人存在"**，否则同样的删除会再次发生。
   守卫用 AST 找真实调用，**排除 tests/**（"测试也算调用方"是误判，见仓内教训）。

## 为什么守卫必须双向

只断言"`plugin_skill_context` 被调用"是不够的：如果哪天有人把
`get_writing_skills()` 从 `Plugin` 上删掉，调用点还在、测试仍绿 —— 除非
同时断言"**被调用的那个东西必须仍然存在**"。所以本文件两条都测。
"""

from __future__ import annotations

import ast
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402

from app import plugin_system as ps  # noqa: E402
from app.panels import registry  # noqa: E402
from app.panels.plugin_panel import PluginPanel, plugin_detail_lines, plugin_rows  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """每个用例一套**独立**的插件目录与状态文件（绝不碰用户的真实插件目录）。"""
    monkeypatch.setattr(ps, "_manager", None)
    return ps.PluginManager(
        plugins_dir=tmp_path / "plugins",
        state_file=tmp_path / "plugins.json",
    )


def _write_plugin(root: Path, name: str, *, config_extra: dict | None = None, main_src: str = "") -> Path:
    """在 `root` 下造一个插件目录，返回其路径。"""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    config = {"name": name, "version": "1.0.0", "entry": "main.py", "type": "writing_skill"}
    config.update(config_extra or {})
    (d / "plugin.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    (d / "main.py").write_text(main_src or DEFAULT_MAIN, encoding="utf-8")
    return d


#: 一个"写作技能包"型插件的最小实现 —— 刻意只提供这一种能力，
#: 用来验证"能力汇总"不会把别的类型也算进来。
DEFAULT_MAIN = """
def get_writing_skills():
    return [{
        "name": "去油文风",
        "description": "降低 AI 腔",
        "prompt": "避免'总而言之'、避免排比三连；多用具体动作替代抽象形容。",
        "rules": ["总而言之", "不禁感叹"],
    }]
"""


# ====================================================================== 1. 纯逻辑


class TestSanitizeName:
    @pytest.mark.parametrize("good", ["插件A", "my-plugin", "my_plugin", "v1.0", "abc123"])
    def test_accepts_legal_names(self, good):
        assert ps.sanitize_plugin_name(good) == good

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "../evil",
            "..",
            "a/b",
            "a\\b",
            ".hidden",
            "a..b",
            "C:",
            "x" * 65,
            "a b",  # 空格不在白名单
            "a$b",
        ],
    )
    def test_rejects_illegal_names(self, bad):
        assert ps.sanitize_plugin_name(bad) is None


class TestZipSlip:
    def test_rejects_traversal_member(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("../../escaped.txt", "pwned")
        dest = tmp_path / "dest"
        dest.mkdir()
        with zipfile.ZipFile(zip_path) as z:
            with pytest.raises(ValueError, match="不安全的 ZIP 路径"):
                ps.safe_extract(z, dest)
        # 反证：确实**没有**在目标目录外写出文件（防止"报了错但文件已落盘"）
        assert not (tmp_path / "escaped.txt").exists()
        assert not (tmp_path.parent / "escaped.txt").exists()

    def test_rejects_prefix_sibling(self, tmp_path):
        """`is_relative_to` 而非字符串 startswith —— 前缀相同但并非子目录要拒绝。"""
        dest = tmp_path / "dest"
        dest.mkdir()
        zip_path = tmp_path / "sib.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("../dest_evil/x.txt", "pwned")
        with zipfile.ZipFile(zip_path) as z:
            with pytest.raises(ValueError):
                ps.safe_extract(z, dest)

    def test_accepts_normal_member(self, tmp_path):
        zip_path = tmp_path / "ok.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("plug/plugin.json", "{}")
            z.writestr("plug/main.py", "x = 1")
        dest = tmp_path / "dest"
        dest.mkdir()
        with zipfile.ZipFile(zip_path) as z:
            ps.safe_extract(z, dest)
        assert (dest / "plug" / "main.py").exists()


class TestAudit:
    def test_clean_plugin_is_safe(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text(DEFAULT_MAIN, encoding="utf-8")
        audit = ps.audit_plugin(f)
        assert audit.risk_level == "safe"
        assert "未发现高危调用" in audit.summary()

    @pytest.mark.parametrize(
        ("src", "symbol"),
        [
            ("import os\nos.system('dir')\n", "os.system"),
            ("import subprocess\nsubprocess.run(['ls'])\n", "subprocess"),
            ("eval('1+1')\n", "eval"),
            ("import socket\n", "socket"),
            ("import shutil\nshutil.rmtree('/')\n", "shutil.rmtree"),
        ],
    )
    def test_flags_dangerous_symbols(self, tmp_path, src, symbol):
        f = tmp_path / "main.py"
        f.write_text(src, encoding="utf-8")
        audit = ps.audit_plugin(f)
        assert audit.risk_level == "high"
        assert any(name == symbol for name, _ in audit.dangerous), audit.dangerous
        assert symbol in audit.summary()

    def test_syntax_error_is_high_risk(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("def broken(:\n", encoding="utf-8")
        audit = ps.audit_plugin(f)
        assert audit.risk_level == "high"
        assert audit.syntax_error

    def test_records_imports(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("import json\nfrom pathlib import Path\n", encoding="utf-8")
        audit = ps.audit_plugin(f)
        assert "json" in audit.imports
        assert "pathlib" in audit.imports

    def test_oversized_entry_is_rejected(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("#" * (ps._MAX_ENTRY_BYTES + 10), encoding="utf-8")
        audit = ps.audit_plugin(f)
        assert audit.risk_level == "high"
        assert "过大" in audit.syntax_error


# ====================================================================== 2. 安装流程


class TestInstallFlow:
    def test_install_from_directory_then_enable_disable_uninstall(self, tmp_path, manager):
        src = _write_plugin(tmp_path / "src", "去油插件")
        result = manager.install(str(src))
        assert result.ok, result.message
        assert result.plugin_name == "去油插件"
        assert "尚未启用" in result.message
        assert result.security_warning  # 必须给出风险告知

        # 🔴 装完**默认不启用**（危险默认值已修）
        plugin = manager.get("去油插件")
        assert plugin is not None
        assert plugin.enabled is False
        assert manager.all_writing_skills() == []

        # 启用后消费端立刻能读到
        en = manager.enable("去油插件")
        assert en.ok
        skills = manager.all_writing_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "去油文风"
        assert skills[0]["plugin"] == "去油插件"
        assert "总而言之" in skills[0]["rules"]

        # 停用后消费端读到空
        assert manager.disable("去油插件").ok
        assert manager.all_writing_skills() == []

        # 卸载
        assert manager.uninstall("去油插件").ok
        assert manager.get("去油插件") is None
        assert not (manager.plugins_dir / "去油插件").exists()

    def test_enable_state_persists_across_manager_instances(self, tmp_path):
        """启用状态必须写盘 —— 否则重启应用就"忘了"，等于半个死功能。"""
        src = _write_plugin(tmp_path / "src", "持久插件")
        mgr1 = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "plugins.json")
        assert mgr1.install(str(src)).ok
        assert mgr1.enable("持久插件").ok

        mgr2 = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "plugins.json")
        assert mgr2.get("持久插件").enabled is True

    def test_install_from_zip(self, tmp_path, manager):
        # 造一个"含一层顶层目录"的 ZIP（GitHub 归档的典型形态）
        zip_path = tmp_path / "plug.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("my-plugin-main/plugin.json", json.dumps({"name": "压缩包插件", "type": "writing_skill"}))
            z.writestr("my-plugin-main/main.py", DEFAULT_MAIN)
        result = manager.install(str(zip_path))
        assert result.ok, result.message
        assert result.plugin_name == "压缩包插件"
        assert manager.get("压缩包插件") is not None

    def test_zip_with_traversal_is_refused_and_leaves_nothing(self, tmp_path, manager):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("plugin.json", json.dumps({"name": "坏人"}))
            z.writestr("../../pwned.txt", "x")
        result = manager.install(str(zip_path))
        assert not result.ok
        assert "不安全" in result.message
        # 反证：插件目录为空（没有留半成品）
        assert list(manager.plugins_dir.iterdir()) == []

    def test_illegal_name_refused(self, tmp_path, manager):
        src = _write_plugin(tmp_path / "src", "ok", config_extra={"name": "../逃逸"})
        result = manager.install(str(src))
        assert not result.ok
        assert "非法" in result.message
        assert list(manager.plugins_dir.iterdir()) == []

    def test_duplicate_install_refused(self, tmp_path, manager):
        src = _write_plugin(tmp_path / "src", "重名插件")
        assert manager.install(str(src)).ok
        again = manager.install(str(src))
        assert not again.ok
        assert "已存在" in again.message

    def test_broken_plugin_install_rolls_back(self, tmp_path, manager):
        """入口有语法错的插件：安装必须**回滚**，不能在插件目录里留一个启不起来的目录。"""
        src = _write_plugin(tmp_path / "src", "坏插件", main_src="def broken(:\n")
        result = manager.install(str(src))
        assert not result.ok
        assert "回滚" in result.message
        assert not (manager.plugins_dir / "坏插件").exists()

    def test_install_into_own_store_refused(self, tmp_path, manager):
        """把插件根目录自己当源目录安装 —— 会造成递归复制，必须拒绝。"""
        result = manager.install(str(manager.plugins_dir))
        assert not result.ok

    def test_nonexistent_source(self, tmp_path, manager):
        result = manager.install(str(tmp_path / "nope"))
        assert not result.ok
        assert "不存在" in result.message

    def test_empty_source(self, manager):
        assert not manager.install("").ok

    def test_uninstall_outside_root_refused(self, tmp_path, monkeypatch):
        """即便配置被人改成插件根目录之外，卸载也必须拒绝删除。"""
        mgr = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "plugins.json")
        outside = _write_plugin(tmp_path / "outside", "外部插件")
        plugin = ps.Plugin(outside)
        mgr.plugins["外部插件"] = plugin
        result = mgr.uninstall("外部插件")
        assert not result.ok
        assert "拒绝删除" in result.message
        assert outside.exists()  # 反证：目录还在


class TestCapabilityAggregation:
    def test_only_enabled_plugins_contribute(self, tmp_path, manager):
        src1 = _write_plugin(tmp_path / "s1", "甲")
        src2 = _write_plugin(tmp_path / "s2", "乙")
        manager.install(str(src1))
        manager.install(str(src2))
        assert manager.all_writing_skills() == []
        manager.enable("甲")
        names = [s["plugin"] for s in manager.all_writing_skills()]
        assert names == ["甲"]

    def test_all_capability_kinds(self, tmp_path, manager):
        main = """
def get_writing_skills():
    return [{"name": "S", "prompt": "p", "rules": []}]
def get_library():
    return {"type": "elements", "category": "C", "items": [{"name": "n"}]}
def get_exporters():
    return [{"name": "E", "ext": ".e"}]
def get_ai_providers():
    return [{"name": "P", "base_url": "http://x"}]
def get_tools():
    return [{"name": "T", "desc": "d"}]
"""
        src = _write_plugin(tmp_path / "src", "全能插件", main_src=main)
        manager.install(str(src))
        manager.enable("全能插件")
        assert len(manager.all_writing_skills()) == 1
        assert "elements" in manager.all_libraries()
        assert len(manager.all_exporters()) == 1
        assert len(manager.all_ai_providers()) == 1
        assert len(manager.all_tools()) == 1

    def test_failing_capability_does_not_crash_aggregation(self, tmp_path, manager):
        """插件内部抛异常时，汇总要能继续 —— 一个坏插件不该让面板炸掉。"""
        ok_src = _write_plugin(tmp_path / "ok1", "好插件")
        bad_src = _write_plugin(
            tmp_path / "bad",
            "抛错插件",
            main_src="def get_writing_skills():\n    raise RuntimeError('boom')\n",
        )
        manager.install(str(ok_src))
        manager.install(str(bad_src))
        manager.enable("好插件")
        manager.enable("抛错插件")
        skills = manager.all_writing_skills()
        assert [s["plugin"] for s in skills] == ["好插件"]

    def test_disabled_and_broken_plugins_are_not_enabled_plugins(self, tmp_path, manager):
        src = _write_plugin(tmp_path / "src", "半坏插件")
        # 先正常装上并启用
        manager.install(str(src))
        manager.enable("半坏插件")
        # 再破坏入口文件后 reload —— 加载失败，即使状态说"启用"也不能算 enabled
        (manager.plugins_dir / "半坏插件" / "main.py").write_text("def (:\n", encoding="utf-8")
        manager.reload()
        plugin = manager.get("半坏插件")
        assert plugin is not None
        assert plugin.enabled is True  # 状态没被抹掉
        assert plugin.module is None  # 但加载失败
        assert manager.enabled_plugins() == []  # ⇒ 不参与汇总
        assert manager.all_writing_skills() == []
        # 且禁止启用（明确报错，而不是静默）
        assert not manager.enable("半坏插件").ok


class TestWritingSkillsConsumption:
    """插件写作技能包 → `WritingSkillManager` 的真实消费（"读它的人"存在性验证）。"""

    def test_context_contains_plugin_prompt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ps, "_manager", None)
        mgr = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "s.json")
        src = _write_plugin(tmp_path / "src", "风格插件")
        mgr.install(str(src))
        mgr.enable("风格插件")
        monkeypatch.setattr(ps, "_manager", mgr)

        from app.writing_skills import WritingSkillManager

        wsm = WritingSkillManager()
        ctx = wsm.plugin_skill_context()
        assert "【插件技能·去油文风】" in ctx
        assert "多用具体动作替代抽象形容" in ctx
        assert wsm.plugin_ban_rules() == ["总而言之", "不禁感叹"]

    def test_context_empty_without_plugins(self, monkeypatch):
        monkeypatch.setattr(ps, "_manager", None)
        from app.writing_skills import WritingSkillManager

        wsm = WritingSkillManager()
        assert wsm.plugin_skill_context() == ""
        assert wsm.plugin_ban_rules() == []

    def test_plugin_rules_hit_anti_slop_check(self, tmp_path, monkeypatch):
        """插件禁用词必须在**文字层**生效（而不是只出现在提示词里）。"""
        monkeypatch.setattr(ps, "_manager", None)
        mgr = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "s.json")
        src = _write_plugin(tmp_path / "src", "风格插件")
        mgr.install(str(src))
        mgr.enable("风格插件")
        monkeypatch.setattr(ps, "_manager", mgr)

        from app.writing_skills import AntiSlopProcessor, WritingSkillManager

        wsm = WritingSkillManager()
        issues = wsm.anti_slop.check_text("他叹了口气，总而言之，事情就是这样。", extra_banned=wsm.plugin_ban_rules())
        assert issues["plugin_banned"], issues
        assert any("总而言之" in x for x in issues["plugin_banned"])
        # 反证：不传插件规则时，这一项必须是空的（证明是插件规则起的作用）
        assert AntiSlopProcessor().check_text("总而言之")["plugin_banned"] == []

    def test_plugin_failure_never_breaks_generation_context(self, monkeypatch):
        """插件系统不可用时返回空串 —— 增强项绝不能把主流程弄挂。"""
        import app.plugin_system as mod

        monkeypatch.setattr(mod, "get_plugin_manager", lambda: None)
        from app.writing_skills import WritingSkillManager

        wsm = WritingSkillManager()
        assert wsm.plugin_skill_context() == ""
        assert wsm.plugin_ban_rules() == []

    def test_exception_in_manager_is_swallowed(self, monkeypatch):
        import app.plugin_system as mod

        class Boom:
            def all_writing_skills(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(mod, "get_plugin_manager", lambda: Boom())
        from app.writing_skills import WritingSkillManager

        wsm = WritingSkillManager()
        assert wsm.plugin_skill_context() == ""  # 不抛，返回空
        assert wsm.plugin_ban_rules() == []


class TestGlobalManager:
    def test_get_plugin_manager_is_lazy_and_swallows_failure(self, monkeypatch):
        monkeypatch.setattr(ps, "_manager", None)

        def boom():
            raise OSError("disk gone")

        monkeypatch.setattr(ps, "PluginManager", boom)
        assert ps.get_plugin_manager() is None
        ps.reset_plugin_manager()
        assert ps._manager is None


class TestNameAllowsChinesePunctuation:
    """❗ 回归测试：中文插件名里的间隔号曾导致**合法插件装不上**。

    起初白名单是 `[\\w\\u4e00-\\u9fff.\\-]`，`\\w` **不匹配** `·`(U+00B7)，
    于是「示例插件·去油文风」被判定为非法名 —— 而这是再正常不过的中文命名。
    安全判据应该是"拦真正危险的字符"，不是"尽量少放行"。
    """

    @pytest.mark.parametrize(
        "name",
        [
            "示例插件·去油文风",
            "作者·插件",
            "插件（增强版）",
            "《我的插件》",
            "插件：续",
            "a•b",
            "插件、附注",
        ],
    )
    def test_chinese_punctuation_is_accepted(self, name):
        assert ps.sanitize_plugin_name(name) == name

    @pytest.mark.parametrize("name", ["a/b", "a\\b", "a\x00b", "..", ".x", "a..b", "", "  "])
    def test_real_path_risks_still_rejected(self, name):
        assert ps.sanitize_plugin_name(name) is None


class TestBundledExamplePlugin:
    """仓库自带的示例插件必须**真的可装、可启用、可被消费**。

    为什么要有这一组：全新安装时 `~/.ai_novel_writer/plugins/` 是空的，
    "插件功能已启用"这件事**无法被验证**。示例插件是唯一的开箱证据。
    如果示例插件本身坏了，用户看到的就是"插件功能是坏的"。
    """

    def _example_dir(self) -> Path:
        return REPO_ROOT / "examples" / "plugins" / "demo_writing_skill"

    def test_example_files_exist_and_are_valid_json(self):
        d = self._example_dir()
        assert (d / "plugin.json").exists() and (d / "main.py").exists()
        cfg = json.loads((d / "plugin.json").read_text(encoding="utf-8"))
        assert cfg["type"] in ps.PLUGIN_TYPES
        assert ps.sanitize_plugin_name(cfg["name"]) == cfg["name"], "示例插件的名字自己就非法"

    def test_example_installs_enables_and_is_consumed(self, manager):
        d = self._example_dir()
        assert d.exists(), "示例插件目录不见了"
        installed = manager.install(str(d))
        assert installed.ok, installed.message
        name = json.loads((d / "plugin.json").read_text(encoding="utf-8"))["name"]
        assert manager.enable(name).ok
        # 关键：**消费端**真的读到了 —— 这才叫"生效"
        skills = manager.all_writing_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "去油文风"
        assert skills[0]["rules"] == ["总而言之", "不禁感叹"]
        assert skills[0]["plugin"] == name
        libs = manager.all_libraries()
        assert sum(len(v) for v in libs.values()) >= 1

    def test_example_passes_own_audit(self):
        """示例插件不能自己就是个"高危"示例。"""
        d = self._example_dir()
        audit = ps.audit_plugin(d / "main.py")
        assert audit.risk_level in ("safe", "notice"), f"示例插件被判为高危：{audit.summary()}"


# ====================================================================== 3. 面板层


class TestPanelPure:
    def test_registered(self):
        registry.load_panels()
        spec = registry.get("plugins")
        assert spec is not None
        assert spec.panel_cls is PluginPanel
        assert spec.title == "插件中心"
        assert spec.category == "运维"

    def test_module_listed_in_registry(self):
        assert "app.panels.plugin_panel" in registry.NATIVE_PANEL_MODULES

    def test_listed_in_packaging_spec(self):
        """按字符串导入的面板必须同时出现在 spec 的 hiddenimports —— 否则打包后少一块。"""
        spec = _scan.read("installer/novel_app.spec")
        assert "app.panels.plugin_panel" in spec
        assert "app.plugin_system" in spec

    def test_plugin_rows_shape(self):
        rows = plugin_rows(
            [
                {
                    "name": "A",
                    "version": "1.0",
                    "type": "writing_skill",
                    "type_label": "写作技能包",
                    "enabled": True,
                    "risk_level": "high",
                },
                {"name": "B", "version": "2.0", "type": "tool", "enabled": False, "load_error": "boom"},
            ]
        )
        iid, values = rows[0]
        assert iid == "A"
        assert values == ("A", "1.0", "写作技能包", "已启用", "高")
        iid2, values2 = rows[1]
        assert values2[3] == "加载失败"  # load_error 优先于 enabled 显示

    def test_plugin_detail_lines_empty(self):
        assert plugin_detail_lines({}) == []

    def test_plugin_detail_lines_includes_risk_and_error(self):
        lines = dict(
            plugin_detail_lines(
                {
                    "name": "A",
                    "version": "1",
                    "type_label": "写作技能包",
                    "capabilities": ["writing_skill"],
                    "enabled": False,
                    "risk_level": "high",
                    "risk_summary": "触及：os.system（执行系统命令）",
                    "load_error": "boom",
                    "plugin_dir": "/x",
                }
            )
        )
        assert "高" in lines["风险"]
        assert lines["加载错误"] == "boom"
        assert "写作技能包" in lines["提供能力"]


# ====================================================================== 4. 接线守卫


def _production_call_sites(name: str) -> list[str]:
    """在整个 `app/` 里找 `name` 的真实**方法调用**（AST，排除注释/docstring）。

    只认 `xxx.name(...)` 形式 —— 属性读取（`p.name`）不算"被使用"，
    因为它不产生任何效果（本仓「注册即遗忘」的典型形态就是"定义了但没人调"）。
    """
    hits: list[str] = []
    for py in sorted((REPO_ROOT / "app").rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name:
                hits.append(py.relative_to(REPO_ROOT).as_posix())
    return hits


class TestWiringGuard:
    """🔴 本文件最重要的一层：钉住插件系统**确实被生产代码使用**。

    背景：`plugin_system.py` 曾因"全仓零引用"被删（`34ce8b1`）。
    只把它恢复成文件是不够的 —— 必须证明消费端存在。
    """

    def test_writing_skill_context_is_called_in_production(self):
        hits = _production_call_sites("plugin_skill_context")
        # 调用点必须存在，且必须来自**生产代码**（novel_agent 那条注入链）
        assert hits, "plugin_skill_context 在生产代码里零调用 —— 插件技能包等于没接上"
        assert "app/novel_agent.py" in hits or "app/writing_skills.py" in hits

    def test_plugin_ban_rules_is_called_in_production(self):
        hits = _production_call_sites("plugin_ban_rules")
        assert hits, "plugin_ban_rules 零调用 —— 插件禁用词不会在文字层生效"

    def test_all_writing_skills_is_called_in_production(self):
        hits = _production_call_sites("all_writing_skills")
        assert hits, "PluginManager.all_writing_skills 零调用"

    def test_the_thing_being_called_still_exists(self):
        """**反向断言**：被调用的方法必须仍然存在。

        没有这条，删掉 `Plugin.get_writing_skills`（或把 `all_writing_skills`
        改成返回空）时，上面几条守卫仍会通过 —— 那就是恒真的假守卫。
        """
        for method in (
            "get_writing_skills",
            "get_library",
            "get_exporters",
            "get_ai_providers",
            "get_tools",
        ):
            assert hasattr(ps.Plugin, method), f"Plugin.{method} 被删了"
        for method in ("all_writing_skills", "all_libraries", "all_exporters", "all_tools"):
            assert hasattr(ps.PluginManager, method), f"PluginManager.{method} 被删了"
        assert hasattr(ps, "get_plugin_manager")

    def test_plugin_system_module_is_not_orphan(self):
        """插件模块必须被生产代码 import（否则又回到"死模块"状态）。"""
        importers = []
        for py in sorted((REPO_ROOT / "app").rglob("*.py")):
            if py.name == "plugin_system.py":
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except OSError:  # pragma: no cover
                continue
            if "plugin_system" in src:
                importers.append(py.relative_to(REPO_ROOT).as_posix())
        assert importers, "app/plugin_system.py 没有任何生产代码 import —— 它又变成死模块了"
        assert "app/writing_skills.py" in importers  # 消费端
        assert "app/panels/plugin_panel.py" in importers  # 界面端

    def test_no_plugin_literal_outside_owner(self):
        """插件根目录路径只允许在 `plugin_system.py` 里拼接（防"同一事实写两处"）。"""
        offenders = []
        needle = ".ai_novel_writer"
        for py in sorted((REPO_ROOT / "app").rglob("*.py")):
            if py.name in ("plugin_system.py", "diagnostic_logger.py"):
                continue
            code = _scan.strip_noise(py.read_text(encoding="utf-8"))
            if needle in code and "plugins" in code:
                offenders.append(str(py.relative_to(REPO_ROOT)))
        assert offenders == [], f"这些文件自己拼了插件目录：{offenders}"


# ====================================================================== 5. 真 Tk（可选）


def _tk_available() -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _tk_available(), reason="无显示环境")
class TestPanelTk:
    def test_build_marks_built_and_shows_empty_state(self, tmp_path, monkeypatch):
        import tkinter as tk

        monkeypatch.setattr(ps, "_manager", None)
        mgr = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "s.json")
        monkeypatch.setattr(ps, "_manager", mgr)

        root = tk.Tk()
        root.withdraw()
        try:
            panel = PluginPanel(app=None)
            frame = panel.build(root)
            assert frame is not None
            assert panel.is_built is True  # ❗ 不标记会被宿主反复重建
            assert "尚未安装任何插件" in panel._detail.get("1.0", tk.END)
        finally:
            root.destroy()

    def test_panel_lists_installed_plugin(self, tmp_path, monkeypatch):
        import tkinter as tk

        monkeypatch.setattr(ps, "_manager", None)
        mgr = ps.PluginManager(plugins_dir=tmp_path / "plugins", state_file=tmp_path / "s.json")
        src = _write_plugin(tmp_path / "src", "面板插件")
        mgr.install(str(src))
        monkeypatch.setattr(ps, "_manager", mgr)

        root = tk.Tk()
        root.withdraw()
        try:
            panel = PluginPanel(app=None)
            panel.build(root)
            rows = panel._tree.get_children()
            assert len(rows) == 1
            assert rows[0] == "面板插件"
        finally:
            root.destroy()

    def test_panel_reports_unavailable_manager(self, tmp_path, monkeypatch):
        """插件系统不可用时，面板必须显示"不可用"而不是崩溃或空白。"""
        import tkinter as tk

        import app.panels.plugin_panel as panel_mod

        monkeypatch.setattr(panel_mod, "get_plugin_manager", lambda: None)
        root = tk.Tk()
        root.withdraw()
        try:
            panel = PluginPanel(app=None)
            panel.build(root)
            assert panel.is_built is True
            assert "不可用" in panel._detail.get("1.0", tk.END)
        finally:
            root.destroy()
