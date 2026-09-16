"""版本与文档一致性门禁。

**为什么需要这个文件**：版本号曾散落在 5 处（`pyproject.toml` / `app/__init__.py` /
README 标题 / README 下载表 / CHANGELOG），任何一处漏改都会让"仓库对外信息"互相矛盾 ——
而这类不一致**没有任何运行时症状**，只能靠人眼发现（历史上确实发生过：
README 的下载表指向旧版本、关于对话框写死 v2.0）。

因此把「改版本号时必须一起改哪些地方」变成断言，让遗漏在 CI 阶段就红。

⚠️ 本文件**只断言"当前版本"相关的一致性**，不追溯历史：
`docs/` 下的报告、`ROADMAP_V3` 的版本基线等是**当时的事实记录**，不应随版本递增而改写。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?$")

#: 根目录允许存在的 Markdown 文档集合（与 `docs/README.md` 的说明保持一致）。
#: 新增根级文档时必须同步改这里与 `docs/README.md` —— 两条信息表达同一件事，
#: 分开维护必然漂移（`README_CN.md` 曾经就变成与 `README.md` 重复且陈旧的第二份入口）。
EXPECTED_ROOT_DOCS = {
    "README.md",
    "README_EN.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "QUICKSTART.md",
    "USAGE.md",
}


def _pyproject_version() -> str:
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


@pytest.fixture(scope="module")
def version() -> str:
    return _pyproject_version()


def test_pyproject_version_is_semver(version):
    assert SEMVER_RE.match(version), f"版本号不符合语义化版本格式: {version!r}"


def test_single_source_of_truth(version):
    """`pyproject.toml` 是权威源，`app.__version__` 必须与之一致。"""
    from app import __version__

    assert __version__ == version, (
        f"app.__version__={__version__!r} 与 pyproject.toml 的 {version!r} 不一致；改版本号时两者都要改"
    )


def test_frozen_fallback_matches(version):
    """冻结（EXE）环境读不到 pyproject，会退回 `_FALLBACK_VERSION` —— 它也必须是当前版本。"""
    import app

    fallback = getattr(app, "_FALLBACK_VERSION", None)
    assert fallback is not None, "app 包应定义 _FALLBACK_VERSION 供冻结环境回退"
    assert fallback == version, (
        f"_FALLBACK_VERSION={fallback!r} 与 pyproject.toml 的 {version!r} 不一致；打包出的 EXE 会显示错误版本"
    )


def test_readme_shows_current_version(version):
    """README 标题与下载表都要体现当前版本（历史上下载表曾长期指向旧版本）。"""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    heading = text.splitlines()[0]
    assert version in heading, f"README 标题未体现当前版本：{heading!r}"

    download_rows = [line for line in text.splitlines() if line.startswith("|") and "AI_NovelWriter" in line]
    assert download_rows, "README 缺少下载表"
    assert any(version in row for row in download_rows), f"README 下载表未体现当前版本 {version}"


def test_readme_en_shows_current_version(version):
    text = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")
    assert version in text.splitlines()[0], "README_EN 标题未体现当前版本"


def test_changelog_has_entry_for_version(version):
    """CHANGELOG 必须有当前版本的条目（发布前写日志是既定流程）。"""
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^##\s+v?{re.escape(version)}\b", text, re.MULTILINE), f"CHANGELOG.md 缺少 {version} 的条目"


def test_root_document_set_is_consistent():
    """根目录 Markdown 文档集合必须与文档索引所声明的集合一致。

    这条守卫的直接依据：`docs/README.md` 声明的根级文档清单曾与实际不符
    （多出一份陈旧的 `README_CN.md`）—— 同一事实写在两处就会漂移。
    """
    actual = {path.name for path in REPO_ROOT.glob("*.md")}
    assert actual == EXPECTED_ROOT_DOCS, (
        "根目录文档集合与预期不一致：\n"
        f"  多出: {sorted(actual - EXPECTED_ROOT_DOCS)}\n"
        f"  缺少: {sorted(EXPECTED_ROOT_DOCS - actual)}\n"
        "请同步修改 tests/test_version_consistency.py 与 docs/README.md"
    )

    index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for name in sorted(EXPECTED_ROOT_DOCS):
        assert name in index, f"docs/README.md 的根级文档清单缺少 {name}"


def test_binaries_are_not_versioned_by_gitignore():
    """二进制通过 Releases 分发，不入库（`.gitignore` 必须挡住）。"""
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.exe", "*.apk"):
        assert pattern in ignored, f".gitignore 缺少 {pattern} 排除规则"
