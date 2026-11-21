"""本轮修复的行为回归（桌面端）。

覆盖：
- P0-1 云存储客户端缓存：per-call 参数必须真正生效，且不再固化首次参数。
- P0-3 静默降级：降级/失败必须留痕（degradations / last_error），可供 UI 提示。
- P0-3 安全导入：失败必须登记到 IMPORT_FAILURES，占位类报错要带模块名。
- P2-8 切分函数收敛：一份权威实现 + 各调用点原有口径逐一锁死。
- P2-8 分层守卫：核心层不得反向依赖 tkinter / UI 面板。
"""

import ast
import builtins
from pathlib import Path

import pytest

from app import bulk_rewrite, parsing, rework, semantic_candidates
from app.cloud_storage import WebDAVProvider
from app.format_converter import FormatConverter

_APP_DIR = Path(__file__).resolve().parent.parent / "app"


# ------------------------------------------------------------ P0-1 客户端缓存


@pytest.fixture
def provider():
    p = WebDAVProvider({"url": "https://dav.example.com", "username": "u", "password": "p"})
    yield p
    p.close()


def test_per_call_timeout_is_honored(provider):
    c30 = provider._get_client(timeout=30)
    c60 = provider._get_client(timeout=60)
    assert c30 is not c60, "不同 timeout 必须拿到不同客户端，否则参数被静默丢弃"
    assert c30.timeout.read == 30
    assert c60.timeout.read == 60, "后传的 timeout=60 被首次建连参数固化了（旧缺陷）"


def test_same_params_reuse_client(provider):
    a = provider._get_client(timeout=60)
    b = provider._get_client(timeout=60)
    assert a is b, "相同参数应复用连接池，不能每次新建"


def test_bare_call_gets_default_timeout_not_httpx_5s(provider):
    client = provider._get_client()
    assert client.timeout.read == provider.DEFAULT_TIMEOUT
    assert client.timeout.read != 5.0, "裸调用落到 httpx 默认 5s，大文件同步必超时"


def test_base_kwargs_preserved_across_overrides(provider):
    provider._get_client(base_url="https://dav.example.com", timeout=30)
    merged = provider._get_client(timeout=60)
    assert str(merged.base_url) == "https://dav.example.com", "覆盖 timeout 时丢了 base_url"
    assert merged.timeout.read == 60


def test_close_releases_every_bucket(provider):
    c1 = provider._get_client(timeout=30)
    c2 = provider._get_client(timeout=60)
    provider.close()
    assert c1.is_closed and c2.is_closed, "close() 必须关掉全部客户端，不能只关最后一个"
    assert provider.client is None
    assert provider._clients == {}
    provider.close()  # 幂等


def test_injected_client_still_wins_and_gets_timeout():
    """既有契约：外部注入的 client 优先；但显式 timeout 仍要落到它身上。"""

    class Fake:
        timeout = None

        def close(self):
            pass

    p = WebDAVProvider({"url": "https://dav.example.com"})
    fake = Fake()
    p.client = fake
    assert p._get_client() is fake
    assert p._get_client(timeout=60) is fake
    assert fake.timeout == 60


# ------------------------------------------------------------ P0-3 降级留痕


def test_unsupported_format_records_error(tmp_path):
    conv = FormatConverter(tmp_path)
    assert conv.convert("正文", "书名", "mobi") is None
    assert "mobi" in conv.last_error


def test_epub_missing_dependency_degrades_loudly(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ebooklib" or name.startswith("ebooklib."):
            raise ImportError("No module named 'ebooklib'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    conv = FormatConverter(tmp_path)
    out = conv.convert("正文", "书名", "epub")
    assert out is not None and out.endswith(".html"), "缺依赖时应降级产出可读文件"
    assert conv.degradations, "降级必须留痕，否则用户以为拿到的是 EPUB"
    assert "ebooklib" in conv.degradations[0]
    assert "HTML" in conv.degradations[0]


def test_pdf_missing_dependency_degrades_loudly(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fpdf" or name.startswith("fpdf."):
            raise ImportError("No module named 'fpdf'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    conv = FormatConverter(tmp_path)
    out = conv.convert("正文", "书名", "pdf")
    assert out is not None and out.endswith(".txt")
    assert conv.degradations and "TXT" in conv.degradations[0]


def test_state_reset_between_conversions(tmp_path):
    conv = FormatConverter(tmp_path)
    conv.convert("正文", "书名", "mobi")
    assert conv.last_error
    out = conv.convert("正文", "书名", "txt")
    assert out is not None
    assert conv.last_error == "", "上一次失败原因不能被带到下一次成功转换"
    assert conv.degradations == []


def test_conversion_exception_records_error(tmp_path, monkeypatch):
    conv = FormatConverter(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("磁盘写入失败 XYZ")

    monkeypatch.setattr(conv, "_to_txt", boom)
    assert conv.convert("正文", "书名", "txt") is None
    assert "XYZ" in conv.last_error


# ------------------------------------------------------------ P0-3 安全导入


def test_import_failure_registry_exposed():
    import app

    assert isinstance(app.IMPORT_FAILURES, dict)
    assert "IMPORT_FAILURES" in app.__all__


def test_import_stub_error_names_module():
    from app import _safe_import

    stub = _safe_import("app.__definitely_missing_module__", "Ghost")
    assert "app.__definitely_missing_module__" in app_import_failure_text(stub)


def app_import_failure_text(stub) -> str:
    with pytest.raises(ImportError) as ei:
        stub()
    return str(ei.value)


def test_failed_import_is_registered():
    import app

    app._safe_import("app.__another_missing_module__", "Ghost2")
    assert "app.__another_missing_module__" in app.IMPORT_FAILURES


# ------------------------------------------------------------ P2-8 切分收敛

TITLE_TEXT = "# 第一章 起点\n\n第一段第一行\n第一段第二行\n\n第二段"


def test_split_title_two_calibers():
    assert parsing.split_title(TITLE_TEXT)[0] == "# 第一章 起点"
    assert parsing.split_title(TITLE_TEXT, strip_marks=True)[0] == "第一章 起点"


def test_split_title_without_heading():
    assert parsing.split_title("纯正文\n第二行") == ("", "纯正文\n第二行")
    assert parsing.split_title("") == ("", "")


def test_split_paragraphs_two_calibers():
    keep = parsing.split_paragraphs(TITLE_TEXT.split("\n\n", 1)[1])
    assert keep[0] == "第一段第一行\n第一段第二行", "默认口径必须保留段内换行"
    merged = parsing.split_paragraphs(TITLE_TEXT.split("\n\n", 1)[1], merge_lines=True)
    assert merged[0] == "第一段第一行 第一段第二行", "合并口径用空格连接段内各行"


def test_callsite_calibers_unchanged():
    """收敛实现后，各调用点的历史口径必须逐一保持不变。"""
    body = "第一段第一行\n第一段第二行\n\n第二段"
    assert bulk_rewrite.split_title(TITLE_TEXT)[0] == "# 第一章 起点"
    assert rework.split_title(TITLE_TEXT)[0] == "第一章 起点"
    assert bulk_rewrite.split_paragraphs(body) == ["第一段第一行\n第一段第二行", "第二段"]
    assert semantic_candidates.split_paragraphs(body) == ["第一段第一行 第一段第二行", "第二段"]


def test_no_duplicate_split_implementations():
    """守卫：不得在调用点重新写一份切分逻辑。"""
    for mod in (bulk_rewrite, rework, semantic_candidates):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {"split_title", "split_paragraphs"}:
                calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
                assert any(isinstance(c.func, ast.Name) and c.func.id.startswith("_split_") for c in calls), (
                    f"{mod.__name__}.{node.name} 未委托权威实现"
                )


# ------------------------------------------------------------ P2-8 分层守卫

#: 明确属于 UI 层、允许依赖 tkinter 的非 *_ui 模块
_UI_ALLOWLIST = {
    "dialogs",
    "navigation",
    "theme_switch",
    "ui_scroll",
    "ui_style",
    "fullscreen_writer",
    "writing_skills_panel",
}


def _is_ui_layer(path: Path) -> bool:
    rel = path.relative_to(_APP_DIR)
    if rel.parts[0] == "panels":
        return True
    return path.stem.endswith("_ui") or path.stem in _UI_ALLOWLIST


def test_core_layer_is_gui_framework_free():
    """核心/业务层不得 import tkinter —— 否则无法脱离 GUI 复用与测试。

    名字刻意不含 "tk"：`pytest -k "not Tk"` 是**大小写不敏感**的子串匹配，
    叫 ..._tkinter 会被主跑批次误 deselect，只在 Tk 子集里跑。
    """
    offenders = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        if _is_ui_layer(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            if any(m.split(".")[0] == "tkinter" for m in mods):
                offenders.append(f"{path.relative_to(_APP_DIR)}:{node.lineno}")
    assert not offenders, "核心层出现 tkinter 依赖：\n" + "\n".join(offenders)
