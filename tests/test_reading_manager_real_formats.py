# -*- coding: utf-8 -*-
"""reading_manager 真实格式覆盖（R3 补测）。

既有 test_reading_manager_formats.py 大量 mock 掉了 read_book 本身，
epub/pdf/docx 的提取与读取分支实际从未执行。本文件用**真实夹具**
（ebooklib 生成 EPUB、手工最小 PDF、python-docx 生成 DOCX）覆盖：

- 三种格式的元数据提取与正文读取（含 PDF 逐页异常吞掉分支）
- 可选依赖缺失时的导入回落（loguru / ebooklib / pypdf / docx）
- import_book 的路径安全分支与"源文件已在书库内"的同文件保护
- read_book 的异常回落（损坏编码 → None）
"""

import importlib
import logging
import sys
from pathlib import Path

import pytest

import app.reading_manager as rm_mod
from app.reading_manager import ReadingManager


def _make_config(tmp_path):
    return type("Config", (), {"config_dir": tmp_path})()


def _pdf_string(value: str) -> str:
    """PDF 字面量：ASCII 用圆括号，中文用 UTF-16BE 带 BOM 的十六进制串。"""
    try:
        value.encode("latin-1")
        return f"({value})"
    except UnicodeEncodeError:
        return "<FEFF" + value.encode("utf-16-be").hex().upper() + ">"


def _make_pdf(path: Path, text: str = "Hello PDF", title: str = "PDF书名", author: str = "PDF作者"):
    """手工构造带文本与 Info 字典的最小合法 PDF（不依赖 reportlab）。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        f"<< /Title {_pdf_string(title)} /Author {_pdf_string(author)} >>".encode("ascii"),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))


def _make_epub(path: Path):
    epub = pytest.importorskip("ebooklib.epub")
    book = epub.EpubBook()
    book.set_identifier("anw-test-001")
    book.set_title("EPUB书名")
    book.set_language("zh")
    book.add_author("EPUB作者")
    chapter = epub.EpubHtml(title="第一章", file_name="c1.xhtml", lang="zh")
    chapter.content = "<h1>第一章</h1><p>这是正文内容。</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)


def _make_docx(path: Path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("第一段正文")
    doc.add_paragraph("第二段正文")
    doc.save(str(path))


class TestRealEpub:
    def test_metadata_and_read(self, tmp_path):
        pytest.importorskip("ebooklib")
        rm = ReadingManager(_make_config(tmp_path))
        src = tmp_path / "book.epub"
        _make_epub(src)
        meta = rm.import_book(str(src))
        assert meta is not None
        assert meta["title"] == "EPUB书名"
        assert meta["author"] == "EPUB作者"
        assert meta["chapters"], "应提取到章节文件名"
        content = rm.read_book(meta["file_path"])
        assert content and "这是正文内容" in content
        assert "<" not in content, "HTML 标签应被剥离"


class TestRealPdf:
    def test_metadata_and_read(self, tmp_path):
        pytest.importorskip("pypdf")
        rm = ReadingManager(_make_config(tmp_path))
        src = tmp_path / "book.pdf"
        _make_pdf(src)
        meta = rm.import_book(str(src))
        assert meta is not None
        assert meta["pages"] == 1
        assert meta["title"] == "PDF书名"
        assert meta["author"] == "PDF作者"
        content = rm.read_book(meta["file_path"])
        assert content and "Hello PDF" in content

    def test_page_extract_error_is_swallowed(self, tmp_path, monkeypatch):
        pytest.importorskip("pypdf")
        rm = ReadingManager(_make_config(tmp_path))
        src = tmp_path / "book.pdf"
        _make_pdf(src, text="Good page")

        import pypdf

        original = pypdf.PdfReader

        class FlakyReader(original):
            @property
            def pages(self):
                pages = super().pages

                class BadPage:
                    def extract_text(self):
                        raise RuntimeError("页损坏")

                return [BadPage(), pages[0]]

        monkeypatch.setattr(rm_mod, "_pdf_lib", type("Lib", (), {"PdfReader": FlakyReader}))
        content = rm.read_book(str(src))
        assert content and "Good page" in content, "坏页应被跳过而非整体失败"


class TestRealDocx:
    def test_metadata_and_read(self, tmp_path):
        pytest.importorskip("docx")
        rm = ReadingManager(_make_config(tmp_path))
        src = tmp_path / "book.docx"
        _make_docx(src)
        meta = rm.import_book(str(src))
        assert meta is not None
        assert meta["pages"] == 0  # 2 段落 // 50
        content = rm.read_book(meta["file_path"])
        assert content == "第一段正文\n\n第二段正文"


class TestImportSafety:
    def test_file_already_in_library_no_crash(self, tmp_path):
        """源文件本就在书库内：不得触发 SameFileError（v3.4.1 修复）。"""
        rm = ReadingManager(_make_config(tmp_path))
        src = rm.books_dir / "inside.txt"
        src.write_text("已在书库\n正文", encoding="utf-8")
        meta = rm.import_book(str(src))
        assert meta is not None
        assert Path(meta["file_path"]) == src
        assert src.read_text(encoding="utf-8") == "已在书库\n正文"

    def test_resolve_failure_falls_back_to_plain_name(self, tmp_path, monkeypatch):
        rm = ReadingManager(_make_config(tmp_path))
        src = tmp_path / "外部书.txt"
        src.write_text("标题行\n正文", encoding="utf-8")

        def boom(self):
            raise OSError("resolve 失败")

        monkeypatch.setattr(Path, "resolve", boom)
        meta = rm.import_book(str(src))
        assert meta is not None
        assert Path(meta["file_path"]).name == "外部书.txt"

    def test_read_bad_encoding_returns_none(self, tmp_path):
        rm = ReadingManager(_make_config(tmp_path))
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\xff\xfe\x00 invalid-utf8")
        assert rm.read_book(str(bad)) is None


@pytest.fixture
def rm_reloader():
    """临时把某依赖标记为不可导入并 reload 模块；teardown 恢复原模块。"""
    saved = {}

    def reload_blocking(*names):
        for name in names:
            saved[name] = sys.modules.get(name)
            sys.modules[name] = None  # None ⇒ import 抛 ImportError
        return importlib.reload(rm_mod)

    yield reload_blocking
    for name, value in saved.items():
        if value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = value
    importlib.reload(rm_mod)


class TestOptionalImportFallbacks:
    def test_loguru_missing_uses_logging(self, rm_reloader):
        mod = rm_reloader("loguru")
        assert isinstance(mod.logger, logging.Logger)

    def test_ebooklib_missing_disables_epub(self, rm_reloader):
        mod = rm_reloader("ebooklib")
        assert mod.EPUB_SUPPORT is False

    def test_both_pdf_libs_missing_disables_pdf(self, rm_reloader):
        mod = rm_reloader("pypdf", "PyPDF2")
        assert mod.PDF_SUPPORT is False
        assert mod._pdf_lib is None

    def test_docx_missing_disables_docx(self, rm_reloader):
        mod = rm_reloader("docx")
        assert mod.DOCX_SUPPORT is False
