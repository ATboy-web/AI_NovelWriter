"""发布工具脚本的行为测试。

`scripts/` 下的两个脚本都被**发布流程**直接依赖（CI 打标签时跑 `release_notes.py`
生成发布说明、维护时跑 `fix_release_metadata.py` 清理历史乱码）。它们出问题的表现是
"发布页上没有说明/说明被重复叠加" —— 都是线上才看得见的，所以在这里先钉住。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    assert path.is_file(), f"缺少脚本 {path}"
    spec = importlib.util.spec_from_file_location(f"anw_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fixer():
    return _load("fix_release_metadata")


def test_garbled_detection(fixer):
    assert fixer.is_garbled("v2.14.1 - ??????")
    assert fixer.is_garbled("## ????\n- ??API????")
    assert not fixer.is_garbled("v3.0.0 - 面板化工作台")
    assert not fixer.is_garbled("")
    assert not fixer.is_garbled(None)


def test_backfilled_body_is_not_flagged_again(fixer):
    """**幂等性**：补记后的正文里保留了原始乱码（在 `<details>` 内），
    若只看"含 ??"就再补一次，会层层叠加（实测踩到，v2.14.0 被套了两层）。"""
    original = "## ????\n- ??API????"
    assert fixer.needs_body_fix(original) is True

    once = fixer.build_body("2.12.3", original)
    assert fixer.needs_body_fix(once) is False, "已补记的正文不应再次被判为待修复"

    # 重复补记的正文应能被收敛回一层
    twice = fixer.build_body("2.12.3", once)
    assert twice.count(fixer.MARKER) == 2, "构造前提：确实叠了两层"
    repaired = fixer.build_body("2.12.3", fixer.extract_original(twice))
    assert repaired.count(fixer.MARKER) == 1
    assert original.splitlines()[-1] in repaired, "收敛后仍应保留原始文本"


def test_extract_original_returns_none_when_clean(fixer):
    assert fixer.extract_original("正常正文，没有乱码") is None


def test_extract_original_recovers_through_backfilled_body(fixer):
    """**回归**：补记会把正文里的围栏转义成 `'''`，因此重复补记的正文里
    只有一个围栏对，其内容是"上一轮补记过的整篇正文"（仍含补记标记）。
    只按"含 `??` 且不含标记"过滤会把原文丢光 —— 实测把 v2.14.0 的原文丢了。
    正确行为是递归往里取。"""
    original = "## ????\n- ??API????\n- 第三行 ??"
    once = fixer.build_body("2.13.0", original)
    twice = fixer.build_body("2.13.0", once)

    assert fixer.extract_original(once) == original
    assert fixer.extract_original(twice) == original, "应能递归穿透补记层取回原文"


def test_extract_original_never_returns_a_backfilled_body(fixer):
    """取回的必须是**原文**，而不是上一轮的补记正文（否则会自我叠加）。"""
    original = "## ????\n- ??API????"
    twice = fixer.build_body("2.13.0", fixer.build_body("2.13.0", original))
    recovered = fixer.extract_original(twice)
    assert recovered is not None
    assert fixer.MARKER not in recovered and fixer.MARKER_NO_ORIGINAL not in recovered


def test_marker_admits_when_original_is_lost(fixer):
    """原文取不回时，标记**不得**声称"原始文本保留在下方折叠块中"。"""
    body = fixer.build_body("2.14.0", None)
    assert fixer.MARKER_NO_ORIGINAL in body
    assert fixer.MARKER not in body


def test_build_body_includes_changelog_section(fixer):
    """能取到 CHANGELOG 条目时，补记正文必须带上它（那是项目的权威记录）。"""
    body = fixer.build_body("2.12.2", "## ????\n- ???")
    section = fixer.changelog_section("2.12.2")
    assert section and section in body
    assert fixer.MARKER in body


def test_build_body_without_changelog_keeps_only_the_original(fixer):
    """CHANGELOG 没有该版本时**不得编造**：只保留标记 + 原文折叠块。

    用一个"确定不存在"的版本号，避免测试依赖"当前哪些版本缺条目"这一会变的事实
    （v2.12.1 原本缺条目，补记后就变了 —— 上一版测试正是因此失效）。
    """
    body = fixer.build_body("9.9.9", "## ????\n- ???")
    assert fixer.changelog_section("9.9.9") is None
    assert "本版本内容" not in body, "没有 CHANGELOG 条目时不得凭空生成正文"
    assert "???" in body, "原始文本必须保留在折叠块中"
    assert fixer.MARKER in body


def test_build_body_uses_factual_note_when_available(fixer):
    """有预设的**可核实**说明时必须带上（例如"该版本是 APK 发布"这一事实）。"""
    body = fixer.build_body("v2.12.1", "## ????\n- ???")
    assert fixer.FALLBACK_NOTE["v2.12.1"] in body


def test_release_notes_script_handles_unknown_version():
    notes_mod = _load("release_notes")
    with pytest.raises(KeyError):
        notes_mod.changelog_section("999.999.999")
