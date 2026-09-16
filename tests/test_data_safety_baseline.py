"""v3 改造的**数据安全护栏**（P0 交付物）。

背景（硬约束）：**已有角色名不可删除**。线上真实作品为 286 个角色 / 1094 章，
`memory/characters.json` 的 sha256 是判断"有没有弄坏数据"的唯一客观依据。

本文件锁定三件事：

1. `app/live_data.py` 的摘要逻辑正确（哈希、字节数、角色数、章节数），
   且**哈希对写入敏感** —— 否则"哈希未变"就不能作为证据；
2. 线上数据根目录**不在仓库内**（`~/.ai_novel_writer/novels/...`）——
   这是 2026-09-16 复核中实际踩过的坑：在仓库里找 `characters.json` 永远找不到；
3. v3 新增模块**不得出现任何删除角色名的调用面**（源码级断言）。
   项目既有口径（`character_ui.py` 的 `_delete_character` 刻意不接线 +
   `test_character_data_integrity.py` 的源码断言）在这里延伸到新增模块。

⚠️ 本文件的测试**不读写线上数据**：所有断言都在 `tmp_path` 构造的假小说目录上完成。
真实数据只在 `scripts/baseline_check.py` 里做只读采集。
"""

import json
from pathlib import Path

import pytest

from app.live_data import (
    characters_sha256,
    find_novel_dir,
    iter_novel_dirs,
    novels_root,
    summarize_novel,
)

REPO_ROOT = Path(__file__).parent.parent


def _make_novel(root: Path, name: str, character_count: int, chapter_files: int = 3) -> Path:
    """在 root 下构造一个最小可用的小说目录（与线上结构一致）。"""
    novel = root / name
    (novel / "memory").mkdir(parents=True, exist_ok=True)
    (novel / "characters").mkdir(parents=True, exist_ok=True)

    characters = {
        f"角色{i:03d}": {"personality": f"性格{i}", "category": "配角"}
        for i in range(character_count)
    }
    (novel / "memory" / "characters.json").write_text(
        json.dumps(characters, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for i in range(chapter_files):
        (novel / "characters" / f"角色{i:03d}.json").write_text("{}", encoding="utf-8")
    return novel


class TestNovelDataSummary:
    """摘要采集必须准确 —— 它承担"改造前后逐位一致"的举证责任。"""

    def test_counts_and_hash(self, tmp_path):
        novel = _make_novel(tmp_path, "测试书_1", character_count=286, chapter_files=286)
        summary = summarize_novel(novel)

        assert summary.characters_sha256 == characters_sha256(novel)
        assert len(summary.characters_sha256) == 64
        assert summary.characters_bytes == (novel / "memory" / "characters.json").stat().st_size
        assert summary.character_count == 286
        assert summary.chapter_count == 286

    def test_hash_reacts_to_write(self, tmp_path):
        """哈希必须对内容变化敏感，否则"哈希未变"毫无证明力。"""
        novel = _make_novel(tmp_path, "测试书_1", character_count=3)
        before = characters_sha256(novel)

        data = json.loads((novel / "memory" / "characters.json").read_text(encoding="utf-8"))
        data["新角色"] = {"personality": "新增"}
        (novel / "memory" / "characters.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        assert characters_sha256(novel) != before

    def test_hash_reacts_to_byte_level_change_only(self, tmp_path):
        """只有字节变化才改哈希 —— 同内容重写不产生假阳性差异。"""
        novel = _make_novel(tmp_path, "测试书_1", character_count=3)
        before = characters_sha256(novel)
        raw = (novel / "memory" / "characters.json").read_bytes()
        (novel / "memory" / "characters.json").write_bytes(raw)
        assert characters_sha256(novel) == before

    def test_corrupt_file_is_reported_not_silently_zero(self, tmp_path):
        """解析失败必须标记为 -1，不能伪装成"0 个角色"（否则会掩盖数据损坏）。"""
        novel = _make_novel(tmp_path, "测试书_1", character_count=2)
        (novel / "memory" / "characters.json").write_text(
            '{"角色000": {"personality": "截断', encoding="utf-8"
        )
        summary = summarize_novel(novel)
        assert summary.character_count == -1
        assert summary.characters_bytes > 0

    def test_character_count_ignores_non_dict_values(self, tmp_path):
        """与 parsing.extract_characters_payload 同一判据：只有 dict 值才是角色。"""
        novel = _make_novel(tmp_path, "测试书_1", character_count=0)
        (novel / "memory" / "characters.json").write_text(
            json.dumps({"角色甲": {"a": 1}, "备注": "字符串不是角色"}, ensure_ascii=False),
            encoding="utf-8",
        )
        assert summarize_novel(novel).character_count == 1

    def test_as_dict_is_json_serializable(self, tmp_path):
        novel = _make_novel(tmp_path, "测试书_1", character_count=2)
        payload = summarize_novel(novel).as_dict()
        assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


class TestNovelDirDiscovery:
    def test_iter_skips_dirs_without_characters(self, tmp_path):
        _make_novel(tmp_path, "有角色的书_1", character_count=2)
        (tmp_path / "没有角色的书_2" / "memory").mkdir(parents=True)
        (tmp_path / "空目录_3").mkdir()

        found = [p.name for p in iter_novel_dirs(tmp_path)]
        assert found == ["有角色的书_1"]

    def test_iter_on_missing_root_is_empty(self, tmp_path):
        assert list(iter_novel_dirs(tmp_path / "不存在")) == []

    def test_find_returns_newest_by_characters_mtime(self, tmp_path):
        import os
        import time

        old = _make_novel(tmp_path, "旧书_1", character_count=2)
        new = _make_novel(tmp_path, "新书_2", character_count=2)

        past = time.time() - 86400
        os.utime(old / "memory" / "characters.json", (past, past))

        assert find_novel_dir(tmp_path) == new

    def test_find_returns_none_when_no_candidate(self, tmp_path):
        assert find_novel_dir(tmp_path) is None


class TestLiveDataRootIsOutsideRepo:
    """线上数据不在仓库里 —— 这条认知必须固化成断言。"""

    def test_novels_root_is_not_inside_repo(self):
        root = novels_root().resolve()
        assert REPO_ROOT.resolve() not in root.parents
        assert root != REPO_ROOT.resolve()

    def test_real_live_data_if_present_is_outside_repo(self):
        novel = find_novel_dir()
        if novel is None:
            pytest.skip("本机没有线上小说数据，跳过（不视为失败）")

        resolved = novel.resolve()
        assert REPO_ROOT.resolve() not in resolved.parents
        # 仓库里那个 memory/ 不是线上数据
        assert (resolved / "memory" / "characters.json").is_file()


# ---------------------------------------------------------------- 源码级护栏

#: v3 新增/改造的模块。缺失的文件自动跳过，随实施推进自动获得覆盖。
V3_MODULES = (
    "app/live_data.py",
    "app/providers/__init__.py",
    "app/providers/base.py",
    "app/providers/registry.py",
    "app/providers/openai_compat.py",
    "app/providers/anthropic.py",
    "app/providers/ollama.py",
    "app/providers/reasoning.py",
    "app/providers/balance.py",
    "app/providers/pricing.py",
    "app/events/bus.py",
    "app/panels/base.py",
    "app/panels/registry.py",
    "app/panels/legacy.py",
    "app/panels/timeline_panel.py",
    "app/panels/biography_panel.py",
    "app/panels/lineage_panel.py",
    "app/panels/usage_panel.py",
    "app/timeline_store.py",
    "app/lineage.py",
    "app/novel_store.py",
    "app/async_runner.py",
    "app/token_estimator.py",
    "app/usage_tracker.py",
    "app/dialogs.py",
)

#: 硬约束：不得出现"删除角色名"的调用面。
FORBIDDEN_IN_V3 = (
    "_delete_character",
    "delete_character(",
    "remove_character(",
    "characters.pop(",
    "del self.characters",
    "clear_characters(",
)


def _strip_comments_and_docstrings(source: str) -> str:
    """去掉注释与文档字符串后再做负向断言。

    否则"修复说明里提到旧的 `xxx`"会被误判为仍在调用 —— 这是本项目
    源码扫描型断言踩过的坑（第三轮）。
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    doc_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    doc_ranges.append((first.lineno, first.end_lineno))

    lines = source.splitlines()
    for start, end in doc_ranges:
        for idx in range(start - 1, min(end, len(lines))):
            lines[idx] = ""

    cleaned = []
    for line in lines:
        stripped = line.split("#", 1)[0] if "#" in line else line
        cleaned.append(stripped)
    return "\n".join(cleaned)


@pytest.mark.parametrize("rel_path", V3_MODULES)
def test_v3_module_has_no_character_deletion_surface(rel_path):
    """v3 新模块不得提供删除角色名的入口（用户的硬约束）。"""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        pytest.skip(f"{rel_path} 尚未实施")

    body = _strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
    hits = [token for token in FORBIDDEN_IN_V3 if token in body]
    assert not hits, f"{rel_path} 出现删除角色名的调用面: {hits}"


def test_guard_strip_helper_ignores_docstring_mentions(tmp_path):
    """自检：`_strip_comments_and_docstrings` 必须真的能屏蔽注释与文档串。"""
    source = (
        '"""[说明] 旧实现会调用 _delete_character，现已移除。"""\n'
        "# 注释里也提到 remove_character(\n"
        "def f():\n"
        '    """内部说明：曾经 delete_character(x)。"""\n'
        "    return 1\n"
    )
    cleaned = _strip_comments_and_docstrings(source)
    for token in ("_delete_character", "remove_character(", "delete_character("):
        assert token not in cleaned, f"未屏蔽 {token}"


def test_guard_strip_helper_keeps_real_calls(tmp_path):
    """自检：真实调用不能被误屏蔽（否则护栏形同虚设）。"""
    source = "def f(app):\n    app._delete_character('甲')\n"
    assert "_delete_character" in _strip_comments_and_docstrings(source)
