"""技能库测试：解析 / 导入 / 登记 / 启停 / 检索 / 匹配 / 注入 / 安全。

## 为什么要这么细

技能库处理的是**外部文件**（用户从网上下载的 `SKILL.md` 包）。这类输入有两个特点：

1. **形状不可控** —— 少 frontmatter、多一层目录、正文没有标题都会发生；
   解析器必须"退化但不崩"，并把这些情况说出来（`warnings` / `load_failures`）。
2. **带路径与脚本** —— 目录名、key、ZIP 成员名都可能含 `..`。
   凡是**会删文件**或**会写文件**的入口都必须有越界测试。

所以本文件除了功能用例，还有一条底线：**任何外部输入都不该让解析抛异常**。

> 真实技能包（`lieflat-less-ai-tone`）的验收数据见 `docs/SKILL_LIBRARY.md`，
> 不写进测试：仓库不该依赖 `~/Downloads` 下是否存在某个文件。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.skill_library import (
    RULE_LEVELS,
    SkillLibrary,
    classify_level,
    default_registry_file,
    default_skills_dir,
    extract_params,
    extract_rules,
    extract_scenarios,
    extract_sections,
    extract_triggers,
    find_skill_root,
    parse_frontmatter,
    parse_skill,
    sanitize_skill_key,
)

# ====================================================================== 夹具


SKILL_MD = """---
name: demo-tone
description: 三层去 AI 味。适用于写作完成后的成稿清理。用户说「去AI味」「改得自然点」时也用这个技能。
version: 1.2.0
author: 示例作者
---

# 去 AI 味（示例）

## 改写原则（解决「改不好」）

**1. 最小改动。** 一处命中只改解决该问题所必需的部分，不顺便润色。

**2. 信息守恒。** 原文的事实、限定词完整保留。

**3. 结构不动。** 标题层级、段落顺序原样保留。

## 改写规则（按优先级排序）

规则里的数字来自实测。

### 1. 翻案腔

先立一个读者并没有的误解，再推翻它。

改法：直接正面下判断，先给判断再给依据。

> ❌ 真正的壁垒不是技术，而是认知。
> ✅ 真正的壁垒是认知。

### 2. 起手式

「说白了」「说穿了」。删掉直接给判断。

改法：删掉起手式。

### 3. 拟人化喻体（人审区，不自动改）

把工具比作理想化的人。

### 4. 破折号（指纹规则，密度决定优先级）

密度 >2/千字时优先处理。

### 5. 同义重命名（段级）

改法：同义链统一回原名词。

## X 级清单（永不改，防误改）

| 特征 | 依据 | 处置 |
|------|------|------|
| 序数词小标题 | 3.1× | 永不改 |
| 「这意味着」复述 | 翻译腔 | 永不改 |
| 空转句引列表 | 9.4× | 永不改 |

## 只能人审的（skill 明确不碰）

- **比喻贴切度**：机器共识只有 0–40%。
- **暗喻、拟人化喻体**：并入人审区。

## 最终验收

- 每处改动是否都能对应规则编号
- 实词是否都有出处

## 调用方式

```bash
python scripts/detect.py <文件> --max-hits 5 --json-out 结果.json
```
"""


def write_skill(root: Path, text: str = SKILL_MD, *, scripts: bool = True) -> Path:
    """在 `root` 下写一个可解析的技能包。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(text, encoding="utf-8")
    (root / "LICENSE").write_text("示例授权", encoding="utf-8")
    (root / "references").mkdir(exist_ok=True)
    (root / "references" / "semantic.md").write_text("# 判据\n", encoding="utf-8")
    (root / "examples").mkdir(exist_ok=True)
    (root / "examples" / "case.md").write_text("# 案例\n", encoding="utf-8")
    if scripts:
        (root / "scripts").mkdir(exist_ok=True)
        (root / "scripts" / "detect.py").write_text(
            "import argparse\n"
            "ap = argparse.ArgumentParser()\n"
            'ap.add_argument("--max-hits", type=int, default=5, help="每项最多列出的命中数")\n'
            'ap.add_argument("--json-out", default=None, help="把 JSON 写入该路径")\n'
            'ap.add_argument("--candidates", action="store_true", help="只抽候选")\n'
            "args = ap.parse_args()\n",
            encoding="utf-8",
        )
    return root


@pytest.fixture()
def library(tmp_path: Path) -> SkillLibrary:
    """隔离的技能库：技能目录与状态文件都在 tmp 下，绝不碰用户真实目录。"""
    return SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")


@pytest.fixture()
def skill_root(tmp_path: Path) -> Path:
    return write_skill(tmp_path / "src" / "demo-tone")


# ====================================================================== frontmatter


class TestFrontmatter:
    def test_basic(self):
        meta, body, warnings = parse_frontmatter(SKILL_MD)
        assert meta["name"] == "demo-tone"
        assert meta["version"] == "1.2.0"
        assert body.startswith("# 去 AI 味")
        assert warnings == []

    def test_folded_block(self):
        text = "---\nname: x\ndescription: >\n  第一行\n  第二行\n---\n正文"
        meta, body, _warnings = parse_frontmatter(text)
        assert meta["description"] == "第一行\n第二行"
        assert body.strip() == "正文"

    def test_quoted_values_stripped(self):
        meta, _body, _w = parse_frontmatter('---\nname: "quoted"\n---\n正文')
        assert meta["name"] == "quoted"

    def test_missing_frontmatter_is_reported_not_raised(self):
        meta, body, warnings = parse_frontmatter("# 只有正文\n")
        assert meta == {}
        assert body.startswith("# 只有正文")
        assert warnings and "frontmatter" in warnings[0]

    def test_empty_text(self):
        meta, _body, warnings = parse_frontmatter("")
        assert meta == {} and warnings

    def test_bom_tolerated(self):
        meta, _body, _w = parse_frontmatter("\ufeff---\nname: bom\n---\n正文")
        assert meta["name"] == "bom"


# ====================================================================== 章节与规则


class TestRules:
    def test_section_split(self):
        sections = extract_sections(SKILL_MD)
        titles = [s["title"] for s in sections]
        assert "1. 翻案腔" in titles
        assert "X 级清单（永不改，防误改）" in titles
        assert all(s["level"] in (2, 3, 4) for s in sections)

    def test_levels_are_explicit_when_titled(self):
        assert classify_level("X 级清单（永不改，防误改）", "") == ("X", "explicit")
        assert classify_level("7. 拟人化喻体（人审区，不自动改）", "") == ("H", "explicit")
        assert classify_level("8. 破折号（指纹规则）", "") == ("F", "explicit")

    def test_numbered_rules_get_heuristic_level(self):
        level, source = classify_level("1. 翻案腔", "改法：直接下判断")
        assert level in ("A", "B") and source == "heuristic"

    def test_mechanical_wording_marks_a_level(self):
        level, source = classify_level("3. 起手式", "删掉起手式直接给判断")
        assert (level, source) == ("A", "heuristic")

    def test_structural_sections_are_not_graded(self):
        """「改写原则」这类章节不是单条规则，给 A/B 会让统计虚高。"""
        level, source = classify_level("改写原则（解决「改不好」）", "**1. 最小改动。**…")
        assert (level, source) == ("", "default")

    def test_container_sections_are_dropped(self):
        """`## 改写规则（按优先级排序）` 只有一句前言，不该进规则集。"""
        rules, _workflows = extract_rules(SKILL_MD)
        titles = [r.title for r in rules]
        assert "改写规则（按优先级排序）" not in titles
        assert "1. 翻案腔" in titles

    def test_x_and_h_are_not_injectable(self):
        rules, _w = extract_rules(SKILL_MD)
        x_rules = [r for r in rules if r.level == "X"]
        h_rules = [r for r in rules if r.level == "H"]
        assert x_rules and h_rules
        assert all(not r.injectable for r in x_rules + h_rules)

    def test_table_items_extracted_for_x_level(self):
        rules, _w = extract_rules(SKILL_MD)
        x_rule = next(r for r in rules if r.level == "X")
        assert "序数词小标题" in x_rule.items()
        assert "空转句引列表" in x_rule.items()
        # 表头与分隔行不得混进条目
        assert "特征" not in x_rule.items()

    def test_revision_prefers_explicit_fix(self):
        rules, _w = extract_rules(SKILL_MD)
        rule = next(r for r in rules if r.title == "1. 翻案腔")
        assert rule.revision().startswith("改法")

    def test_workflow_sections_detected(self):
        """`### 第一步：…` 归 flow，不进规则。"""
        text = "---\nname: x\n---\n## 工作流\n### 第一步：检测\n详情\n### 第二步：改写\n详情\n"
        rules, workflows = extract_rules(text)
        assert rules == []
        assert [w["title"] for w in workflows] == ["第一步：检测", "第二步：改写"]


# ====================================================================== 场景 / 触发词 / 参数


class TestMetadataExtraction:
    def test_triggers(self):
        triggers = extract_triggers("用户说「去AI味」「改得自然点」时也用这个技能。")
        assert triggers == ["去AI味", "改得自然点"]

    def test_triggers_empty(self):
        assert extract_triggers("") == []
        assert extract_triggers("没有引号的说明") == []

    def test_scenarios(self):
        scenarios = extract_scenarios("三层去AI味。适用于写作完成后的成稿清理。与本技能无关的一句。")
        assert any("适用于" in s for s in scenarios)
        assert all("无关的一句" not in s for s in scenarios)

    def test_params_from_add_argument(self):
        source = 'ap.add_argument("--max-hits", type=int, default=5, help="上限")'
        params = {p.flag: p for p in extract_params(source)}
        assert params["--max-hits"].default == "5"
        assert params["--max-hits"].help == "上限"
        assert params["--max-hits"].takes_value is True

    def test_params_store_true_takes_no_value(self):
        params = extract_params('ap.add_argument("--candidates", action="store_true", help="只抽候选")')
        assert params[0].takes_value is False

    def test_params_from_docs_supplement(self):
        params = {p.flag: p for p in extract_params("运行 `detect.py --json --out x.json`")}
        assert "--json" in params and params["--json"].source == "docs"
        assert "--out" in params

    def test_script_wins_over_docs(self):
        text = 'ap.add_argument("--out", default="a.json", help="脚本里的")\n`--out`'
        params = {p.flag: p for p in extract_params(text)}
        assert params["--out"].source == "script"
        assert params["--out"].default == "a.json"


# ====================================================================== 解析入口


class TestParseSkill:
    def test_full_parse(self, skill_root: Path):
        skill = parse_skill(skill_root)
        assert skill.key == "demo-tone"
        assert skill.name == "demo-tone"
        assert skill.version == "1.2.0"
        assert skill.author == "示例作者"
        assert skill.license == "见 LICENSE 文件"
        assert skill.triggers == ["去AI味", "改得自然点"]
        assert skill.scenarios
        assert skill.rules
        assert {p.flag for p in skill.params} >= {"--max-hits", "--json-out", "--candidates"}
        assert skill.warnings == []

    def test_file_roles(self, skill_root: Path):
        skill = parse_skill(skill_root)
        roles = skill.file_stats()
        assert roles["script"] == 1
        assert roles["reference"] == 1
        assert roles["example"] == 1
        assert roles["doc"] >= 1

    def test_examples_extracted(self, skill_root: Path):
        skill = parse_skill(skill_root)
        pairs = skill.examples()
        assert ("真正的壁垒不是技术，而是认知。", "真正的壁垒是认知。") in pairs

    def test_missing_entry_does_not_raise(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        skill = parse_skill(empty)
        assert skill.entry is None
        assert any("SKILL.md" in w for w in skill.warnings)

    def test_missing_frontmatter_degrades(self, tmp_path: Path):
        root = tmp_path / "nofm"
        root.mkdir()
        (root / "SKILL.md").write_text("# 标题\n\n## 1. 规则\n改法：删掉\n", encoding="utf-8")
        skill = parse_skill(root)
        assert skill.entry is not None
        assert skill.rules  # 正文有编号标题，仍然能解析出规则
        assert any("frontmatter" in w for w in skill.warnings)

    def test_oversized_entry_rejected(self, tmp_path: Path, monkeypatch):
        import app.skill_library as module

        monkeypatch.setattr(module, "MAX_ENTRY_BYTES", 10)
        root = write_skill(tmp_path / "big")
        skill = parse_skill(root)
        assert skill.entry is None
        assert any("过大" in w for w in skill.warnings)

    def test_gbk_bytes_do_not_crash(self, tmp_path: Path):
        root = tmp_path / "gbk"
        root.mkdir()
        (root / "SKILL.md").write_bytes("---\nname: gbk\n---\n中文正文".encode("gbk"))
        skill = parse_skill(root)  # errors="replace" ⇒ 不抛
        assert skill.entry is not None

    def test_find_root_walks_down(self, tmp_path: Path):
        nested = tmp_path / "wrapper" / "inner"
        write_skill(nested)
        assert find_skill_root(tmp_path) == nested

    def test_find_root_gives_up(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        write_skill(deep)
        assert find_skill_root(tmp_path) is None  # 超过 3 层不下探

    def test_skip_dirs_are_not_scanned(self, tmp_path: Path):
        """❗ 黑名单必须在遍历器内部生效。

        曾经的实现把过滤写在使用方，而 `_walk` 在 yield 前已把子目录压栈 ⇒
        过滤落空，`__pycache__` / `node_modules` 照样进文件清单。
        """
        root = write_skill(tmp_path / "s")
        for junk in ("__pycache__", "node_modules", ".git"):
            folder = root / junk
            folder.mkdir()
            (folder / "junk.py").write_text("x = 1", encoding="utf-8")
        skill = parse_skill(root)
        assert not any(junk in f.path for f in skill.files for junk in ("__pycache__", "node_modules", ".git"))


# ====================================================================== 提示词装配


class TestPromptAssembly:
    def test_x_and_h_excluded(self, skill_root: Path):
        skill = parse_skill(skill_root)
        prompt = skill.to_prompt(4000)
        # 标题进不进提示词是判据：X/H 的**正文**绝不出现
        assert "比喻贴切度" not in prompt
        assert "机器共识" not in prompt
        assert "序数词小标题" in prompt  # 但 X 级要作为"禁止改动"被点名
        assert "禁止改动" in prompt

    def test_budget_is_respected(self, skill_root: Path):
        skill = parse_skill(skill_root)
        for budget in (0, 80, 200, 320, 500, 900, 2000):
            assert len(skill.to_prompt(budget)) <= budget, budget

    def test_truncation_is_disclosed(self, skill_root: Path):
        skill = parse_skill(skill_root)
        prompt = skill.to_prompt(200)
        if len(skill.prompt_rules) > 1:
            assert "未注入" in prompt or "…" in prompt

    def test_preview_payload(self, skill_root: Path):
        skill = parse_skill(skill_root)
        data = skill.preview(max_chars=600)
        assert data["rules_total"] > 0
        assert data["chars"] == len(data["prompt"])
        assert data["tokens"] > 0
        assert data["examples"]

    def test_rules_by_level_covers_registry(self, skill_root: Path):
        skill = parse_skill(skill_root)
        grouped = skill.rules_by_level()
        for level in RULE_LEVELS:
            assert level in grouped


# ====================================================================== 管理器


class TestLibraryInstall:
    def test_install_from_directory(self, library: SkillLibrary, skill_root: Path):
        result = library.install(str(skill_root))
        assert result.ok, result.message
        assert result.skill_key == "demo-tone"
        assert (library.skills_dir / "demo-tone" / "SKILL.md").is_file()
        assert "可执行脚本" in result.security_warning  # 有 scripts ⇒ 必须提示

    def test_install_duplicate_rejected(self, library: SkillLibrary, skill_root: Path):
        assert library.install(str(skill_root)).ok
        again = library.install(str(skill_root))
        assert not again.ok and "已有同名" in again.message

    def test_install_rejects_bad_path(self, library: SkillLibrary, tmp_path: Path):
        assert not library.install(str(tmp_path / "nope")).ok
        assert not library.install("").ok
        empty = tmp_path / "empty-dir"
        empty.mkdir()
        assert not library.install(str(empty)).ok

    def test_install_from_zip(self, library: SkillLibrary, skill_root: Path, tmp_path: Path):
        archive = tmp_path / "skill.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in skill_root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(skill_root))
        result = library.install(str(archive))
        assert result.ok, result.message
        assert library.get("demo-tone") is not None

    def test_zip_slip_rejected(self, library: SkillLibrary, tmp_path: Path):
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../../evil.txt", "pwned")
            zf.writestr("SKILL.md", "---\nname: evil\n---\n")
        result = library.install(str(archive))
        assert not result.ok and "解压失败" in result.message
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_register_does_not_copy(self, library: SkillLibrary, skill_root: Path):
        result = library.register(str(skill_root))
        assert result.ok
        assert library.get("demo-tone").mode == "ref"
        assert not (library.skills_dir / "demo-tone").exists()

    def test_register_missing_path(self, library: SkillLibrary, tmp_path: Path):
        assert not library.register(str(tmp_path / "nope")).ok

    def test_register_twice_rejected_without_prior_reload(self, tmp_path: Path, skill_root: Path):
        """❗ 未显式 `reload()` 也必须能去重。

        旧实现直接用 `self._skills`（初始为空）判重 ⇒ 连续登记两次都成功，
        第二次把状态覆盖成新来源，用户看到的是"登记成功"却只有一个条目。
        """
        library = SkillLibrary(skills_dir=tmp_path / "skills", registry_file=tmp_path / "skills.json")
        assert library.register(str(skill_root)).ok
        second = library.register(str(skill_root))
        assert not second.ok and "已存在" in second.message


class TestLibraryState:
    def test_enable_persists_across_instances(self, tmp_path: Path, skill_root: Path):
        kwargs = {"skills_dir": tmp_path / "skills", "registry_file": tmp_path / "skills.json"}
        first = SkillLibrary(**kwargs)
        first.install(str(skill_root))
        assert first.enable("demo-tone").ok

        second = SkillLibrary(**kwargs)
        second.reload()
        assert second.get("demo-tone").enabled is True

    def test_disable(self, library: SkillLibrary, skill_root: Path):
        library.install(str(skill_root))
        library.enable("demo-tone")
        assert library.disable("demo-tone").ok
        library.reload()
        assert library.get("demo-tone").enabled is False

    def test_enable_unknown(self, library: SkillLibrary):
        result = library.enable("nope")
        assert not result.ok and "不存在" in result.message

    def test_corrupt_registry_falls_back_to_empty(self, tmp_path: Path):
        registry = tmp_path / "skills.json"
        registry.write_text("{not json", encoding="utf-8")
        library = SkillLibrary(skills_dir=tmp_path / "skills", registry_file=registry)
        assert library.reload() == []  # 不抛

    def test_missing_ref_source_reported(self, tmp_path: Path, skill_root: Path):
        registry = tmp_path / "skills.json"
        registry.write_text(
            json.dumps({"schema": 1, "skills": {"ghost": {"mode": "ref", "source": str(tmp_path / "gone")}}}),
            encoding="utf-8",
        )
        library = SkillLibrary(skills_dir=tmp_path / "skills", registry_file=registry)
        library.reload()
        assert any("不存在" in why for _name, why in library.load_failures)


class TestLibrarySearchMatch:
    @pytest.fixture()
    def ready(self, library: SkillLibrary, skill_root: Path) -> SkillLibrary:
        library.install(str(skill_root))
        return library

    def test_search_by_rule_text(self, ready: SkillLibrary):
        assert [s.key for s in ready.search("翻案腔")] == ["demo-tone"]

    def test_search_by_trigger(self, ready: SkillLibrary):
        assert [s.key for s in ready.search("去AI味")] == ["demo-tone"]

    def test_search_no_hit(self, ready: SkillLibrary):
        assert ready.search("量子力学") == []

    def test_search_empty_returns_all(self, ready: SkillLibrary):
        assert len(ready.search("")) == 1

    def test_match_scores_trigger_hit(self, ready: SkillLibrary):
        matches = ready.match("这篇读着太像机器人了，帮我改得自然点")
        assert matches and matches[0].key == "demo-tone"
        assert matches[0].score > 0

    def test_match_ignores_unrelated_text(self, ready: SkillLibrary):
        assert ready.match("第一章 雪夜行军 主角拔剑") == []

    def test_match_threshold(self, ready: SkillLibrary):
        assert ready.match("去AI味", threshold=1.1) == []


class TestPromptContext:
    def test_only_enabled_are_injected(self, library: SkillLibrary, skill_root: Path):
        library.install(str(skill_root))
        assert library.prompt_context() == ""
        library.enable("demo-tone")
        assert "【技能：demo-tone】" in library.prompt_context()

    def test_budget_respected(self, library: SkillLibrary, skill_root: Path):
        library.install(str(skill_root))
        library.enable("demo-tone")
        for budget in (120, 300, 900):
            assert len(library.prompt_context(budget=budget)) <= budget

    def test_relevance_ordering(self, library: SkillLibrary, tmp_path: Path, skill_root: Path):
        library.install(str(skill_root))
        other = write_skill(
            tmp_path / "src" / "other",
            SKILL_MD.replace("demo-tone", "other-tone").replace("去AI味", "写打斗"),
        )
        library.install(str(other))
        library.enable("demo-tone")
        library.enable("other-tone")
        text = "帮我写打斗场面，写打斗要狠"
        first = library.prompt_context(budget=3000, text=text).split("【技能：")[1].split("】")[0]
        assert first == "other-tone"


class TestUninstall:
    def test_uninstall_copy_removes_files(self, library: SkillLibrary, skill_root: Path):
        library.install(str(skill_root))
        target = library.skills_dir / "demo-tone"
        assert target.exists()
        assert library.uninstall("demo-tone").ok
        assert not target.exists()

    def test_uninstall_ref_keeps_source(self, library: SkillLibrary, skill_root: Path):
        library.register(str(skill_root))
        assert library.uninstall("demo-tone").ok
        assert (skill_root / "SKILL.md").is_file()

    def test_uninstall_unknown(self, library: SkillLibrary):
        assert not library.uninstall("nope").ok

    def test_uninstall_refuses_escape(self, tmp_path: Path):
        """状态文件可被手改：key 带 `..` 时绝不能删到技能目录外。"""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        registry = tmp_path / "skills.json"
        registry.write_text(
            json.dumps({"schema": 1, "skills": {"../outside": {"mode": "copy", "source": ""}}}),
            encoding="utf-8",
        )
        library = SkillLibrary(skills_dir=tmp_path / "skills", registry_file=registry)
        library.reload()
        result = library.uninstall("../outside")
        assert not result.ok
        assert (outside / "keep.txt").exists()


class TestKeySanitizing:
    def test_chinese_and_spaces(self):
        assert sanitize_skill_key("去 AI 味") == "去-AI-味"

    def test_path_separators_rejected(self):
        assert sanitize_skill_key("../../etc") == "etc"
        assert sanitize_skill_key("..") is None

    def test_empty(self):
        assert sanitize_skill_key("") is None
        assert sanitize_skill_key("   ") is None


# ====================================================================== 默认路径


class TestDefaults:
    def test_paths_are_single_source(self):
        assert default_skills_dir().name == "skills"
        assert default_registry_file().name == "skills.json"
        assert default_skills_dir().parent == default_registry_file().parent


# ====================================================================== 接线守卫

REPO_ROOT = Path(__file__).parent.parent


def _production_sources() -> list[Path]:
    """生产代码（**排除 tests/**，否则测试自己会被当成调用点而假绿）。"""
    return [p for p in sorted((REPO_ROOT / "app").rglob("*.py"))]


class TestWiringGuard:
    """🔴 「注册即遗忘」防线：技能库必须被生产代码真正消费。

    `plugin_system.py` 的教训（曾因全仓零引用被删）在这里同样适用：
    解析得再好，没人读 `prompt_context()` 就等于没有这个功能。
    """

    def test_prompt_context_is_called_in_production(self):
        callers = [
            p.relative_to(REPO_ROOT).as_posix()
            for p in _production_sources()
            if "prompt_context(" in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert "app/novel_agent.py" in callers, "novel_agent 没有消费技能库 —— 启用后不会生效"

    def test_get_skill_library_is_imported_in_production(self):
        sources = [p for p in _production_sources() if p.name != "skill_library.py"]
        importers = [
            p.relative_to(REPO_ROOT).as_posix()
            for p in sources
            if "get_skill_library" in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert "app/novel_agent.py" in importers

    def test_panel_is_registered(self):
        """面板必须出现在三处：注册表 / 面板模块 / 打包清单。"""
        from app.panels import registry

        assert "app.panels.skill_library_panel" in registry.NATIVE_PANEL_MODULES
        registry.load_panels()
        spec = registry.get("skills")
        assert spec is not None and spec.title == "技能库"

    def test_spec_lists_dynamic_imports(self):
        spec = (REPO_ROOT / "installer" / "novel_app.spec").read_text(encoding="utf-8")
        assert "'app.panels.skill_library_panel'" in spec
        assert "'app.skill_library'" in spec

    def test_the_thing_being_called_still_exists(self):
        """**反向断言**：删掉被调方法时，上面的正向守卫不能继续通过。"""
        for name in ("reload", "install", "register", "enable", "disable", "prompt_context", "match", "search"):
            assert hasattr(SkillLibrary, name), f"SkillLibrary.{name} 被删了"
