"""格式导出与图片管理测试（`format_converter` 覆盖率主力）。

## 测什么

`FormatConverter` 有 6 种输出格式，此前只有 txt/html/markdown 被零星覆盖，
EPUB / PDF / DOCX 三条链路（约 200 行）**从未执行过**。它们的共同风险是：

1. **依赖缺失时静默产出错误文件** —— 三者都写了"ImportError 就降级"，
   但没人验证降级真的产出可用文件；
2. **标题进路径** —— `re.sub` 净化了非法字符，但没人验证 `../../x` 之类真的被挡住；
3. **章节/元信息/插图三个可选参数** —— 不传、只传部分、全传，行为可能不同。

本文件按"每条格式 × 三种入参组合"覆盖，并对降级分支做**显式**测试
（用 `monkeypatch` 把模块标记为不可导入）。

## 不断言字节内容

EPUB/PDF/DOCX 的二进制格式细节由第三方库决定，断言"第 3 字节是什么"只会
在库升级时假红。这里断言的是**外部可观察的结果**：文件存在、非空、
能被对应库重新读回、且包含标题文字。
"""

from __future__ import annotations

import builtins
import os
import sys
from pathlib import Path

import pytest

from app.format_converter import CJK_FONT_CANDIDATES, FormatConverter, ImageManager

CHAPTERS = [
    {"num": 1, "title": "第一章 起", "content": "第一段正文。\n\n第二段正文。"},
    {"num": 2, "title": "第二章 承", "content": "第二章的内容在这里。"},
]
METADATA = {"author": "测试作者", "genre": "玄幻"}


@pytest.fixture()
def converter(tmp_path: Path) -> FormatConverter:
    return FormatConverter(novel_dir=tmp_path)


def _hide_module(monkeypatch, name: str) -> None:
    """让 `import name` 抛 ImportError（模拟依赖缺失的降级分支）。

    ❗ 直接 `sys.modules[name] = None` 不够：`from x import Y` 走的是
    import 机制，会先查 `meta_path`。用 `builtins.__import__` 拦截最可靠。
    """
    real_import = builtins.__import__

    def fake_import(module_name, *args, **kwargs):
        if module_name == name or module_name.startswith(f"{name}."):
            raise ImportError(f"模拟缺失：{name}")
        return real_import(module_name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for key in list(sys.modules):
        if key == name or key.startswith(f"{name}."):
            monkeypatch.delitem(sys.modules, key, raising=False)


# ====================================================================== 注册表与分发


class TestFormats:
    def test_all_six_formats_registered(self):
        assert set(FormatConverter.SUPPORTED_FORMATS) == {"txt", "html", "markdown", "epub", "pdf", "docx"}

    def test_each_format_has_required_keys(self):
        for name, info in FormatConverter.SUPPORTED_FORMATS.items():
            assert {"name", "ext", "desc"} <= set(info), name
            assert info["ext"].startswith("."), name

    def test_unknown_format_returns_none(self, converter: FormatConverter):
        assert converter.convert("正文", "标题", "rtf") is None

    def test_output_goes_to_export_dir(self, converter: FormatConverter, tmp_path: Path):
        out = converter.convert("正文", "书", "txt")
        assert out and Path(out).parent == tmp_path / "export"

    def test_without_novel_dir_uses_cwd_export(self, tmp_path: Path, monkeypatch):
        """`novel_dir=None` 时退回当前目录下的 `export/`（不能崩）。"""
        monkeypatch.chdir(tmp_path)
        converter = FormatConverter()
        out = converter.convert("正文", "无目录", "txt")
        assert out and (tmp_path / "export").is_dir()


class TestTitleSafety:
    """标题会拼进文件名 —— 这是唯一会碰路径的输入。"""

    @pytest.mark.parametrize(
        "title",
        ["a/b", "a\\b", "a:b", "a*b", "a?b", "a<b>c", 'a"b', "a|b", "../../etc/passwd"],
    )
    def test_illegal_chars_are_stripped(self, converter: FormatConverter, tmp_path: Path, title: str):
        out = converter.convert("正文", title, "txt")
        assert out
        target = Path(out)
        # 必须仍然落在 export/ 之内，且文件名不含路径分隔符
        assert target.parent == tmp_path / "export"
        assert "/" not in target.name and "\\" not in target.name

    def test_traversal_does_not_escape(self, converter: FormatConverter, tmp_path: Path):
        converter.convert("正文", "../../victim", "txt")
        assert not (tmp_path.parent / "victim.txt").exists()


# ====================================================================== 文本类


class TestTextFormats:
    def test_txt_with_chapters(self, converter: FormatConverter):
        out = converter.convert("总正文", "书", "txt", chapters=CHAPTERS)
        text = Path(out).read_text(encoding="utf-8")
        assert "第一章 起" in text
        assert "第二章 承" in text
        assert "第一段正文" in text

    def test_txt_without_chapters(self, converter: FormatConverter):
        out = converter.convert("只有正文", "书", "txt")
        assert "只有正文" in Path(out).read_text(encoding="utf-8")

    def test_markdown_has_heading(self, converter: FormatConverter):
        out = converter.convert("正文", "书名", "markdown", chapters=CHAPTERS)
        text = Path(out).read_text(encoding="utf-8")
        assert text.lstrip().startswith("#") or "书名" in text

    def test_html_contains_title_and_meta(self, converter: FormatConverter):
        out = converter.convert("正文", "书名", "html", chapters=CHAPTERS, metadata=METADATA)
        html = Path(out).read_text(encoding="utf-8")
        assert "<html" in html.lower()
        assert "书名" in html
        assert "测试作者" in html

    def test_html_without_metadata(self, converter: FormatConverter):
        """不传 metadata 时用默认作者，不能抛。"""
        out = converter.convert("正文", "书名", "html")
        assert Path(out).is_file()


class TestImageInHtml:
    def _png(self, path: Path) -> Path:
        # 1×1 透明 PNG（最小合法图片）
        data = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
        )
        path.write_bytes(data)
        return path

    def test_image_marker_rendered(self, converter: FormatConverter, tmp_path: Path):
        """**独占一段**的 `![alt](name)` 要变成 `<img>`，并把二进制写到 img_dir。

        ❗ 标记必须独占一行：实现用 `re.match`（从段首匹配），
        行内标记（"看图：![说明](pic.png)"）不会被转换 —— 见下一条用例。
        """
        output = tmp_path / "images_store"
        output.mkdir()
        html = converter._content_to_html("![说明](pic.png)", images={"pic.png": b"data"}, img_dir=output)
        assert "<img" in html
        assert "说明" in html
        assert (output / "0.png").exists()

    def test_inline_marker_is_left_alone(self, converter: FormatConverter):
        """行内图片标记保持原文 —— 记下这个约束，避免有人误以为"没渲染是 bug"。"""
        html = converter._content_to_html("看图：![说明](pic.png)")
        assert "<img" not in html
        assert "![说明](pic.png)" in html

    def test_image_marker_without_data(self, converter: FormatConverter):
        """只有标记没有图片数据时，保留原路径（不能崩）。"""
        html = converter._content_to_html("![说明](missing.png)")
        assert "<img" in html
        assert "missing.png" in html

    def test_plain_paragraphs(self, converter: FormatConverter):
        html = converter._content_to_html("第一段\n\n第二段")
        assert html.count("<p>") == 2


# ====================================================================== EPUB


class TestEpub:
    def test_produces_valid_epub(self, converter: FormatConverter):
        out = converter.convert("正文", "书", "epub", chapters=CHAPTERS, metadata=METADATA)
        assert out and Path(out).suffix == ".epub"
        assert Path(out).stat().st_size > 0

    def test_epub_can_be_read_back(self, converter: FormatConverter):
        """用 epub 库自己读回来 —— 这是"文件真的是 EPUB"的最强证据。"""
        epub = pytest.importorskip("ebooklib.epub")
        out = converter.convert("正文", "可读性", "epub", chapters=CHAPTERS)
        book = epub.read_epub(out)
        assert book.get_metadata("DC", "title")[0][0] == "可读性"

    def test_without_chapters(self, converter: FormatConverter):
        out = converter.convert("只有正文", "书", "epub")
        assert Path(out).is_file()

    def test_falls_back_to_html(self, converter: FormatConverter, monkeypatch):
        """缺 ebooklib ⇒ 产出 HTML，而不是失败。"""
        _hide_module(monkeypatch, "ebooklib")
        out = converter.convert("正文", "降级", "epub")
        assert out and out.endswith(".html"), f"应降级为 .html，实际 {out}"
        assert Path(out).is_file()


# ====================================================================== PDF


class TestPdf:
    #: 当前环境是否有可用的中文字体 —— 决定了"能真的出 PDF"还是"必须降级为 TXT"。
    #: 直接引用产品代码里的候选列表（单一事实来源）：代码加路径、这里自动跟上。
    _HAS_CJK_FONT = any(os.path.exists(p) for p in CJK_FONT_CANDIDATES)

    def test_produces_pdf(self, converter: FormatConverter):
        out = converter.convert("正文内容。", "书", "pdf", chapters=CHAPTERS)
        assert out, "导出没有返回路径"
        if self._HAS_CJK_FONT:
            assert Path(out).suffix == ".pdf"
            # PDF 必须以 %PDF- 开头
            assert Path(out).read_bytes().startswith(b"%PDF")
        else:
            # 无中文字体时必须**降级为 TXT**而不是崩：原实现回落到 Helvetica 渲染中文，
            # fpdf2 会抛 TypeError（Linux CI 实测），用户什么都拿不到。
            assert out.endswith(".txt"), "无中文字体时应降级 TXT，不能硬出 PDF"

    def test_without_chapters(self, converter: FormatConverter):
        out = converter.convert("正文", "书", "pdf")
        if self._HAS_CJK_FONT:
            assert Path(out).read_bytes().startswith(b"%PDF")
        else:
            assert out.endswith(".txt")

    def test_with_metadata(self, converter: FormatConverter):
        out = converter.convert("正文", "书", "pdf", metadata=METADATA)
        assert Path(out).is_file()
        if not self._HAS_CJK_FONT:
            assert out.endswith(".txt")

    def test_falls_back_to_txt(self, converter: FormatConverter, monkeypatch):
        _hide_module(monkeypatch, "fpdf")
        out = converter.convert("正文", "降级", "pdf")
        assert out and out.endswith(".txt")


# ====================================================================== DOCX


class TestDocx:
    def test_produces_docx(self, converter: FormatConverter):
        out = converter.convert("正文内容。", "书", "docx", chapters=CHAPTERS, metadata=METADATA)
        assert out and Path(out).suffix == ".docx"
        assert Path(out).stat().st_size > 0

    def test_docx_can_be_read_back(self, converter: FormatConverter):
        docx = pytest.importorskip("docx")
        out = converter.convert("正文内容。", "可读性", "docx", chapters=CHAPTERS)
        document = docx.Document(out)
        texts = "\n".join(p.text for p in document.paragraphs)
        assert "可读性" in texts
        assert "第一章 起" in texts

    def test_without_optional_args(self, converter: FormatConverter):
        out = converter.convert("正文", "书", "docx")
        assert Path(out).is_file()

    def test_falls_back_to_txt(self, converter: FormatConverter, monkeypatch):
        _hide_module(monkeypatch, "docx")
        out = converter.convert("正文", "降级", "docx")
        assert out and out.endswith(".txt")


# ====================================================================== 原子写


class TestAtomicExport:
    def test_failed_conversion_leaves_no_temp(self, converter: FormatConverter, tmp_path: Path):
        """转换抛异常时，临时文件必须被清掉（否则 export/ 会积垃圾）。"""
        converter._commit_output = staticmethod(lambda *a: (_ for _ in ()).throw(OSError("磁盘满")))  # type: ignore[method-assign]
        assert converter.convert("正文", "书", "txt") is None
        assert not list((tmp_path / "export").glob(".*tmp*"))

    def test_existing_output_survives_failure(self, converter: FormatConverter):
        first = converter.convert("第一版", "书", "txt")
        original = Path(first).read_text(encoding="utf-8")
        converter._commit_output = staticmethod(lambda *a: (_ for _ in ()).throw(OSError("磁盘满")))  # type: ignore[method-assign]
        converter.convert("第二版", "书", "txt")
        assert Path(first).read_text(encoding="utf-8") == original, "失败的转换不能破坏上一次的成品"


# ====================================================================== 图片管理


class TestImageManager:
    def _png(self, path: Path) -> Path:
        data = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
        )
        path.write_bytes(data)
        return path

    def test_import_image(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        source = self._png(tmp_path / "src.png")
        dest = manager.import_image(str(source), name="cover.png")
        assert dest and Path(dest).is_file()
        assert (tmp_path / "images" / "cover.png").is_file()

    def test_import_missing_source(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        assert manager.import_image(str(tmp_path / "不存在.png")) is None

    def test_import_without_novel_dir(self, tmp_path: Path):
        manager = ImageManager()
        assert manager.import_image(str(self._png(tmp_path / "a.png"))) is None

    def test_auto_name_generated(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        dest = manager.import_image(str(self._png(tmp_path / "x.png")))
        assert dest and "x.png" in Path(dest).name

    def test_get_image_path(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        manager.import_image(str(self._png(tmp_path / "a.png")), name="a.png")
        assert manager.get_image_path("a.png")
        assert manager.get_image_path("不存在") is None

    def test_list_images_filters_non_images(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        manager.import_image(str(self._png(tmp_path / "a.png")), name="a.png")
        (tmp_path / "images" / "note.txt").write_text("x", encoding="utf-8")
        names = [row["name"] for row in manager.list_images()]
        assert names == ["a.png"]
        assert "size_str" in manager.list_images()[0]

    def test_list_images_without_dir(self):
        assert ImageManager().list_images() == []

    def test_get_images_data(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        manager.import_image(str(self._png(tmp_path / "a.png")), name="a.png")
        data = manager.get_images_data()
        assert data["a.png"].startswith(b"\x89PNG")

    def test_get_images_data_without_dir(self):
        assert ImageManager().get_images_data() == {}

    def test_insert_marker_at_position(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        text = manager.insert_image_marker("前面后面", 2, "a.png", alt_text="插图")
        assert text == "前面![插图](a.png)后面"

    def test_insert_marker_at_start_and_end(self, tmp_path: Path):
        manager = ImageManager(novel_dir=tmp_path)
        assert manager.insert_image_marker("正文", 0, "a.png").startswith("![")
        assert manager.insert_image_marker("正文", 2, "a.png").endswith("(a.png)")
