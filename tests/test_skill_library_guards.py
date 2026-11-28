"""`skill_library` 的解析容错与安装守卫（档 2：技能规则不注入）。

## 这个模块的"静默错法"

| 故障 | 用户看到 |
|---|---|
| 一个坏技能包把整库拖垮 | 所有技能消失，只剩"加载失败" |
| `SKILL.md` 过大/编码坏却硬解析 | 卡住或读进垃圾 |
| 技能名没消毒 | `../x` 被当目录名，装到技能库外面 |
| 卸载不校验归属 | 配置被改成 `..` 就删掉上层目录 |
| `prompt_context` 注入了 X 级规则 | **模型被指示"可以改动禁止项"** |

最后一条最要紧：X/H 级永不注入。

## 真实 API（第一版全按记忆写，错了一片）

- `SkillLibrary(skills_dir, registry_file)`
- `install/uninstall/set_enabled` 返回 `SkillResult(ok, message, ...)`，**不是元组**
- `skill.key` 是**消毒后的名字**（`去 AI 味` → `去-AI-味`），不是目录名
- `prompt_context(budget=900, text="")`
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app import skill_library as sl

# ❗ 规则必须在 `## 改写规则`（或含"规则/原则/清单"的标题）之下，
# 且**三级标题 + 列表正文**才会被 `extract_rules` 认成规则：
#   - 二级标题含"规则" ⇒ 容器（`_is_container` 判 True），本身不注入；
#   - 三级标题含"规则/原则/清单…" 且正文 ≥3 行或含列表 ⇒ 真规则。
# 第一版用 `## A 级：必须遵守` + 单行正文，结果一条规则都没解析出来 ——
# 症状是提示词里出现"（该技能没有可注入的规则）"。
SKILL_MD = """---
name: 去 AI 味
description: 让文本更像人写的
version: 1.0.0
author: tester
---

## 改写规则

### 规则一：不要用空词
- 避免"显然"这类空词
- 避免"众所周知"
- 避免"不难看出"

### 规则二（X 级）：禁止改动定稿段落
- 不得修改作者已定稿的段落
- 保留作者原句
- 不得重写已发表章节
"""


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "_library", None)
    return sl.SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")


def _make_skill(root: Path, name: str = "demo", body: str = SKILL_MD) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


def _only_key(lib) -> str:
    skills = lib.all_skills()
    assert skills, "技能库是空的"
    return skills[0].key


class TestPathSafety:
    def test_find_root_at_top(self, tmp_path):
        d = _make_skill(tmp_path, "root-skill")

        assert sl.find_skill_root(d) == d

    def test_find_root_one_level_down(self, tmp_path):
        d = _make_skill(tmp_path / "wrapper", "inner")

        assert sl.find_skill_root(tmp_path) == d

    def test_find_root_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")

        assert sl.find_skill_root(f) is None

    def test_find_root_skips_skip_dirs(self, tmp_path):
        """`.git` 里的 SKILL.md 不该被当成技能根。"""
        _make_skill(tmp_path / ".git", "x")

        assert sl.find_skill_root(tmp_path) is None

    def test_find_root_returns_none_when_nothing(self, tmp_path):
        (tmp_path / "empty").mkdir()

        assert sl.find_skill_root(tmp_path) is None

    @pytest.mark.parametrize("name", ["", "   ", "..", ".", "///"])
    def test_sanitize_rejects_empty_and_dots(self, name):
        assert sl.sanitize_skill_key(name) is None

    def test_sanitize_keeps_chinese(self):
        """中文**不构成路径风险**，不能因为是"非 ASCII"就拒绝。"""
        assert sl.sanitize_skill_key("去 AI 味") == "去-AI-味"

    def test_sanitize_strips_path_separators(self):
        key = sl.sanitize_skill_key("../../逃逸")

        assert key is not None
        assert "/" not in key and ".." not in key

    def test_sanitize_truncates_long_names(self):
        assert len(sl.sanitize_skill_key("技" * 200)) <= 64


class TestScanFiles:
    def test_classifies_by_directory(self, tmp_path):
        root = _make_skill(tmp_path)
        (root / "scripts").mkdir()
        (root / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
        (root / "references").mkdir()
        (root / "references" / "doc.md").write_text("x", encoding="utf-8")

        roles = {f.path: f.role for f in sl._scan_files(root, [])}

        assert roles["scripts/run.py"] == "script"
        assert roles["references/doc.md"] == "reference"

    def test_file_limit_warns(self, tmp_path, monkeypatch):
        """超限要**记警告** —— 用户得知道这个技能没被完整收录。"""
        monkeypatch.setattr(sl, "MAX_SKILL_FILES", 2)
        root = _make_skill(tmp_path)
        for i in range(5):
            (root / f"f{i}.txt").write_text("x", encoding="utf-8")

        warnings: list[str] = []
        files = sl._scan_files(root, warnings)

        assert len(files) == 2
        assert any("文件数超过" in w for w in warnings)


class TestParseSkill:
    """解析器**永不抛异常** —— 一个坏包不该拖垮整库。"""

    def test_missing_entry_returns_empty_skill(self, tmp_path):
        d = tmp_path / "空技能"
        d.mkdir()

        skill = sl.parse_skill(d)

        assert skill.entry is None
        assert any("未找到" in w for w in skill.warnings)

    def test_oversized_entry_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sl, "MAX_ENTRY_BYTES", 10)
        d = _make_skill(tmp_path)

        assert any("过大" in w for w in sl.parse_skill(d).warnings)

    def test_parses_frontmatter_fields(self, tmp_path):
        skill = sl.parse_skill(_make_skill(tmp_path))

        assert skill.name == "去 AI 味"
        assert skill.description.startswith("让文本")
        assert skill.version == "1.0.0"
        assert skill.entry is not None

    def test_license_from_file(self, tmp_path):
        """授权写在 LICENSE 里时只**指出存在**，不猜条款。"""
        d = _make_skill(tmp_path)
        (d / "LICENSE").write_text("MIT", encoding="utf-8")

        assert sl.parse_skill(d).license == "见 LICENSE 文件"

    def test_key_is_sanitized_name(self, tmp_path):
        assert sl.parse_skill(_make_skill(tmp_path)).key == "去-AI-味"

    def test_broken_frontmatter_still_parses(self, tmp_path):
        """frontmatter 坏了也不能整包失败 —— 正文规则还有价值。"""
        d = _make_skill(tmp_path, body="---\nname: x\n（没有收尾）\n\n# 规则\n- 甲\n")

        skill = sl.parse_skill(d)

        assert skill.entry is not None
        assert isinstance(skill.rules, list)


class TestPromptContext:
    """注入是"技能真的生效"的唯一通道。"""

    def test_enabled_skill_is_injected(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        lib.set_enabled(_only_key(lib), True)

        text = lib.prompt_context(text="写一段对话")

        assert text, "启用了技能但 prompt_context 是空的"
        assert "不要用空词" in text

    def test_disabled_skill_is_not_injected(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        lib.set_enabled(_only_key(lib), False)

        assert "不要用空词" not in lib.prompt_context(text="写一段对话")

    def test_x_level_rules_never_injected_as_tasks(self, lib):
        """🔴 X 级**不作为可执行规则**注入 —— 但必须作为"禁止改动"被点名。

        这两件事别混：
        - 注入成 `- [X] 规则二：…` ⇒ 模型会照着去做（就是规则明令禁止的事）；
        - 列进「禁止改动（已否决特征…）」⇒ 模型知道**这些不能碰**，才是防误改。
        所以判据是"不出现在可执行行里 + 出现在警示行里"，不是"整段文本不出现"。
        """
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        skill = lib.all_skills()[0]
        lib.set_enabled(skill.key, True)

        text = lib.prompt_context(text="写一段对话")

        assert all(r.level != "X" for r in skill.prompt_rules), "X 级混进了可注入规则"
        assert not any(line.startswith("- [X]") for line in text.splitlines()), "X 级被当成可执行规则注入了"
        assert "禁止改动" in text, "X 级完全没有提示，模型可能去改禁改的东西"

    def test_tiny_budget_does_not_explode(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        lib.set_enabled(_only_key(lib), True)

        text = lib.prompt_context(budget=10, text="写一段对话")

        assert isinstance(text, str)


class TestInstallGuards:
    def test_install_missing_source(self, lib, tmp_path):
        result = lib.install(str(tmp_path / "没有这个"))

        assert result.ok is False
        assert result.message

    def test_install_directory_without_skill_md(self, lib, tmp_path):
        src = tmp_path / "无技能"
        src.mkdir()

        assert lib.install(str(src)).ok is False

    def test_install_directory(self, lib, tmp_path):
        src = _make_skill(tmp_path / "src", "新技能")

        result = lib.install(str(src))

        assert result.ok is True, result.message
        assert lib.skills_dir.is_dir() and list(lib.skills_dir.iterdir())

    def test_install_sanitizes_name(self, lib, tmp_path):
        """技能名来自 `SKILL.md`，是不可信输入。"""
        d = tmp_path / "src" / "占位"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: ../../逃逸\n---\n\n# 规则\n", encoding="utf-8")

        lib.install(str(d))

        installed = [p.name for p in lib.skills_dir.iterdir()] if lib.skills_dir.exists() else []
        assert all(".." not in n for n in installed)

    def test_install_zip(self, lib, tmp_path):
        src = _make_skill(tmp_path / "src", "压缩技能")
        archive = tmp_path / "s.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in src.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(src.parent))

        assert lib.install(str(archive)).ok is True

    def test_install_zip_slip_rejected(self, lib, tmp_path):
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../逃逸/SKILL.md", SKILL_MD)

        lib.install(str(archive))

        assert not (tmp_path / "逃逸").exists(), "Zip Slip 把文件写到了库外"


class TestUninstallGuards:
    def test_uninstall_unknown_key_is_refused(self, lib):
        """`key` 来自状态文件（用户可手改）—— 不存在的 key 必须被拒。

        ⚠️ 路径守卫（`target.is_relative_to(skills_dir)`）只在 `mode == "copy"`
        且 key 真实存在时才执行；而 `key` 在入库时已消毒，正常路径下走不到。
        真要覆盖它得伪造状态文件 + 同名目录，收益低于成本，这里只验可达到的入口。
        """
        result = lib.uninstall("../../逃逸")

        assert result.ok is False
        assert "不存在" in result.message

    def test_uninstall_removes_directory(self, lib, tmp_path):
        src = _make_skill(tmp_path / "src", "待删")
        lib.install(str(src))
        lib.reload()
        key = _only_key(lib)

        result = lib.uninstall(key)

        assert result.ok is True, result.message
        assert not (lib.skills_dir / key).exists()


class TestRegistryAndReload:
    def test_corrupt_registry_does_not_break_reload(self, lib):
        """登记文件坏掉 ⇒ 读成空状态继续，而不是让整库打不开。"""
        _make_skill(lib.skills_dir, "demo")
        lib.registry_file.parent.mkdir(parents=True, exist_ok=True)
        lib.registry_file.write_text("{ 坏", encoding="utf-8")

        lib.reload()

        assert lib.all_skills(), "登记文件坏了导致技能全丢"
        assert lib.all_skills()[0].enabled is False

    def test_enable_persists(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        key = _only_key(lib)
        lib.set_enabled(key, True)

        fresh = sl.SkillLibrary(skills_dir=lib.skills_dir, registry_file=lib.registry_file)
        fresh.reload()

        assert fresh.get(key) is not None
        assert fresh.get(key).enabled is True

    def test_reload_tolerates_broken_skill(self, lib):
        """一个坏包不能拖垮整库 —— 其它技能仍要能用。"""
        _make_skill(lib.skills_dir, "好的")
        broken = lib.skills_dir / "坏的"
        broken.mkdir(parents=True)  # 没有 SKILL.md ⇒ 解析不出入口

        lib.reload()

        assert lib.all_skills(), "坏技能把好技能也带没了"
        assert lib.load_failures, "坏技能没有任何记录（用户不知道它为什么没生效）"

    def test_duplicate_key_is_reported(self, lib):
        """两个目录给同一个技能名 ⇒ 报重复而不是静默覆盖。"""
        _make_skill(lib.skills_dir, "a")
        _make_skill(lib.skills_dir, "b")

        lib.reload()

        assert len(lib.all_skills()) == 1
        assert lib.load_failures, "重复 key 既没合并也没报错"


class TestSingleton:
    """单例是"增强项不该拖垮主流程"的落点。"""

    def test_returns_none_when_init_fails(self, monkeypatch):
        monkeypatch.setattr(sl, "_library", None)

        def boom(*_a, **_kw):
            raise OSError("技能目录不可写")

        monkeypatch.setattr(sl, "SkillLibrary", boom)

        assert sl.get_skill_library() is None

    def test_caches_instance(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sl, "_library", None)
        monkeypatch.setattr(sl, "default_skills_dir", lambda: tmp_path / "skills")
        monkeypatch.setattr(sl, "default_registry_file", lambda: tmp_path / "skills.json")

        first = sl.get_skill_library()
        second = sl.get_skill_library()

        assert first is second

    def test_reset_clears_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sl, "_library", None)
        monkeypatch.setattr(sl, "default_skills_dir", lambda: tmp_path / "skills")
        monkeypatch.setattr(sl, "default_registry_file", lambda: tmp_path / "skills.json")
        first = sl.get_skill_library()

        sl.reset_skill_library()

        assert sl.get_skill_library() is not first


class TestInstallInternals:
    def test_duplicate_install_refused(self, lib, tmp_path):
        """同名技能已存在 ⇒ 拒绝，不覆盖（覆盖会丢用户的启用状态）。"""
        src = _make_skill(tmp_path / "src", "重名")
        assert lib.install(str(src)).ok is True

        again = lib.install(str(src))

        assert again.ok is False
        assert "已有同名" in again.message

    def test_install_copy_failure_reported(self, lib, tmp_path, monkeypatch):
        src = _make_skill(tmp_path / "src", "复制失败")

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(sl.shutil, "copytree", boom)

        result = lib.install(str(src))

        assert result.ok is False
        assert "复制" in result.message

    def test_install_zip_without_skill(self, lib, tmp_path):
        archive = tmp_path / "空.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", "hi")

        result = lib.install(str(archive))

        assert result.ok is False

    def test_install_script_warns_about_execution(self, lib, tmp_path):
        """含脚本的技能要**明确说明不执行** —— 否则用户以为软件跑了别人的代码。"""
        src = _make_skill(tmp_path / "src", "带脚本")
        (src / "scripts").mkdir()
        (src / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")

        result = lib.install(str(src))

        assert result.ok is True
        assert result.security_warning, "含脚本却没给任何提示"
        assert "不会执行" in result.security_warning

    def test_install_state_save_failure(self, lib, tmp_path, monkeypatch):
        src = _make_skill(tmp_path / "src", "状态失败")

        def boom(*_a, **_kw):
            raise OSError("只读")

        monkeypatch.setattr(lib, "_write_state", boom)

        result = lib.install(str(src))

        assert result.ok is False
        assert "状态" in result.message


class TestPreviewAndMatch:
    def test_preview_reports_levels(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()

        data = lib.preview(_only_key(lib))

        assert isinstance(data, dict)
        assert "prompt" in data or "levels" in data

    def test_match_returns_scores(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()
        skill = lib.all_skills()[0]

        result = sl.match_skill(skill, "我想让这段文字不那么 AI 味")

        assert result.key == skill.key
        assert 0.0 <= result.score

    def test_match_on_unrelated_text(self, lib):
        _make_skill(lib.skills_dir, "demo")
        lib.reload()

        result = sl.match_skill(lib.all_skills()[0], "今天天气不错")

        assert isinstance(result.score, float)
