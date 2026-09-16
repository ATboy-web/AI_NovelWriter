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
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))  # 同目录的测试辅助模块（_app_authority）
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


def test_app_resolves_to_the_repository_package():
    """**先定位"版本的来源"，再比较版本值**。

    这条守卫是 2026-09-17 发布事故的直接产物：CI 上 `app.__version__` 解析成 `'1.0.0'`
    （pip 装的明明是 `ai-novel-writer==3.1.0`），失败信息只有一句版本不一致，
    完全看不出是"版本读错了"还是"读错了包"。

    本仓库存在**三个名为 `app` 的包**（根目录 `app/` 与 `backend/ai-service/app`、
    `backend/novel-service/app`，后两者自带 `__version__ = "1.0.0"`），
    而 `backend/tests/conftest.py` 会往 `sys.path` 插目录。一旦解析到后端那个，
    版本断言就会以一个毫无线索的数字差异出现。所以这里先钉死"必须是仓库根下的 app"。
    """
    import app

    resolved = Path(app.__file__).resolve()
    assert resolved.is_relative_to(REPO_ROOT.resolve()), (
        f"import app 解析到了仓库之外：{resolved}\n"
        f"（仓库根为 {REPO_ROOT}；backend/*/app 里另有同名包，其 __version__ 是 1.0.0）"
    )
    assert resolved == (REPO_ROOT / "app" / "__init__.py").resolve(), f"import app 解析到了非预期的文件：{resolved}"


def test_version_ignores_installed_distribution_metadata(version, monkeypatch):
    """**回归**：已安装分发元数据不得覆盖 `pyproject.toml`。

    复刻 CI 的失败条件 —— 环境里有一份声称别的版本的同名分发元数据。
    原实现先查 `importlib.metadata.version("ai-novel-writer")`，于是被它带偏：
    版本一致性门禁变红 ⇒ `Build EXE & Release` 跳过 ⇒ **v3.1.0 的 Release 没建出来**，
    而本地（没有该元数据）永远复现不了。

    `pyproject.toml` 是仓库声明的唯一权威源，就应当先读它。
    """
    import importlib.metadata

    import app

    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "1.0.0")
    assert app._load_version() == version, "环境里的分发元数据覆盖了 pyproject.toml 的版本"


def test_version_falls_back_when_pyproject_is_unreadable(monkeypatch):
    """读不到 `pyproject.toml` 时才退到分发元数据 / 常量（冻结 EXE 走这条）。"""
    import importlib.metadata
    import tomllib

    import app

    real_load = tomllib.load

    def _fail(handle):
        if str(getattr(handle, "name", "")).endswith("pyproject.toml"):
            raise OSError("模拟冻结环境：没有 pyproject.toml")
        return real_load(handle)

    monkeypatch.setattr(tomllib, "load", _fail)
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "9.9.9")
    assert app._load_version() == "9.9.9", "pyproject 不可读时应退到已安装元数据"

    # 两者都不可用 → 构建时注入的常量
    monkeypatch.setattr(
        importlib.metadata, "version", lambda _name: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError)
    )
    assert app._load_version() == app._FALLBACK_VERSION


def test_root_app_wins_when_a_shadowing_app_package_is_ahead_on_sys_path(tmp_path):
    """**复刻 v3.1.0 发布事故**：同名 `app` 包排在 `sys.path` 前面时，`app` 必须仍是仓库根那个。

    CI 上真实的肇事者见 `backend/tests/test_generators.py`（把 `backend/novel-service`
    插到 `sys.path[0]`，那里也有 `app/`）。这里用临时目录造一个等价影子包，
    以便在**任何机器上都能复现**，而不是只在 CI 复现。
    """
    import _app_authority as authority

    shadow = tmp_path / "novel-service" / "app"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    saved_path = list(sys.path)
    saved_modules = {name: mod for name, mod in sys.modules.items() if name == "app" or name.startswith("app.")}
    try:
        sys.path.insert(0, str(tmp_path / "novel-service"))
        for name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
            sys.modules.pop(name, None)

        import app as hijacked

        assert hijacked.__version__ == "1.0.0", "影子包没生效，这条复刻无效"
        assert authority._is_root_app(hijacked) is False

        fixed = authority.restore_root_app_authority()

        assert fixed, "应报告修正了哪些项"
        import app as restored

        assert authority._is_root_app(restored), authority.describe_app_authority()
        assert restored.__version__ == _pyproject_version()
    finally:
        for name in [name for name in list(sys.modules) if name == "app" or name.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def test_backend_service_packages_are_not_ahead_of_the_repo_root():
    """`backend/*/app` 不得排在仓库根**前面**（那会劫持 `app` 这个名字）。

    注意：它们**在** `sys.path` 上是合理的（`backend/tests` 需要），
    错误的是顺序 —— `restore_root_app_authority()` 之后必须没有更靠前的影子目录。
    """
    import _app_authority as authority

    authority.restore_root_app_authority()
    assert authority.app_conflicts() == [], (
        f"这些目录排在仓库根之前，会让 import app 指向后端：{authority.app_conflicts()}\n"
        + authority.describe_app_authority()
    )


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


# ====================================================================== 发布说明派生


def _load_release_notes_module():
    """加载 `scripts/release_notes.py`（它不是包，用文件路径加载）。"""
    import importlib.util

    path = REPO_ROOT / "scripts" / "release_notes.py"
    assert path.is_file(), f"缺少发布说明生成脚本：{path}"
    spec = importlib.util.spec_from_file_location("anw_release_notes", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_notes_are_derived_from_changelog(version):
    """**CI 打标签时用这个脚本生成发布说明** —— 生成不出来，发布页就等于没有说明
    （此前用 `generate_release_notes` 自动生成，对直推仓库只有 88 字符）。"""
    module = _load_release_notes_module()
    notes = module.build_release_notes(version, date="2026-01-01")

    assert f"v{version}" in notes, "发布说明未体现版本号"
    for key in ("下载", "系统要求", "校验"):
        assert key in notes, f"发布说明缺少「{key}」小节"

    section = module.changelog_section(version)
    assert section in notes, "发布说明的正文应当来自 CHANGELOG 对应条目"
    assert len(section) > 200, f"{version} 的 CHANGELOG 条目过短（{len(section)} 字符），发布说明会很空"
    assert "###" in section, "CHANGELOG 条目应至少带一个小节标题"


def test_release_notes_report_unknown_version():
    """未知版本必须显式失败，而不是静默产出空的发布说明。"""
    module = _load_release_notes_module()
    with pytest.raises(KeyError):
        module.changelog_section("999.999.999")


def test_release_notes_cli_writes_file(tmp_path, version):
    """CLI 路径也要能用（CI 里走的是 `--out`）。"""
    module = _load_release_notes_module()
    out = tmp_path / "notes.md"
    assert module.main([version, "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("**发布日期**")
    assert module.main(["999.999.999", "--out", str(out)]) == 1, "未知版本应返回非零退出码"
