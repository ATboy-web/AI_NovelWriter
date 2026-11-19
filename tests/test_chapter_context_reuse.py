"""上下文构建的单一实现守卫。

## 背景

`_gen_chapter` 与 `_regen_current_chapter` 原先各有一份约 40 行的上下文构建逻辑，
diff 出三处差异，其中一处是真实缺陷：**重新创作章节时漏了 18+/擦边注入**。
已提取为 `_build_chapter_context`，这里钉住：

1. 两个入口都走同一个方法（源码层断言，防再次复制粘贴）；
2. 该方法的输出确实包含应有的各段（含 18+ / 擦边提示）；
3. 边界：没有历史章节、没有大纲、没有世界观时都不崩。
"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _make_agent(tmp_path, *, adult=False, edge=False):
    """造一个只带上下文构建所需依赖的实例。

    `_build_content_hint` 定义在 `OutlineUIMixin` 上（`NovelWriterApp` 通过多重继承
    拿到它），所以这里也用组合类，否则拿不到真实实现。
    """
    from app.generation_ui import GenerationMixin
    from app.outline_ui import OutlineUIMixin

    class _Combo(OutlineUIMixin, GenerationMixin):
        pass

    novel = tmp_path / "novel"
    (novel / "chapters").mkdir(parents=True)
    (novel / "chapters" / "chapter_0001.txt").write_text("# 第1章\n\n前情一。", encoding="utf-8")
    (novel / "chapters" / "chapter_0002.txt").write_text("# 第2章\n\n前情二。", encoding="utf-8")

    obj = _Combo.__new__(_Combo)
    obj.current_novel_dir = novel
    obj.config = {"adult_content": adult, "edge_content": edge}
    obj._get_outlines_context = lambda: "【整体大纲】\n- 第1章 A\n- 第2章 B"
    obj._get_world_context = lambda: "【世界观】\n- 宗门：灵药宗"
    return obj


class TestSingleImplementation:
    def test_both_callers_use_the_shared_method(self):
        """源码守卫：两个入口都必须调用 `_build_chapter_context`。"""
        source = (REPO / "app" / "generation_ui.py").read_text(encoding="utf-8")
        assert source.count("self._build_chapter_context(") >= 2, "有入口又自己拼上下文了"

    def test_no_duplicated_recent_chapter_block(self):
        """同一段"取最近 3 章"的逻辑不应再出现两份。"""
        source = (REPO / "app" / "generation_ui.py").read_text(encoding="utf-8")
        assert source.count("recent_chapters = recent_chapters[-3:]") == 1, "上下文构建出现重复副本"


class TestContextContent:
    def test_includes_recent_chapters(self, tmp_path):
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(3, {"genre": "仙侠"})
        assert "前情一" in ctx and "前情二" in ctx
        assert "必须紧接" in ctx

    def test_includes_outline_and_world(self, tmp_path):
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(3, {"genre": "仙侠"})
        assert "【整体大纲】" in ctx
        assert "【世界观】" in ctx

    def test_includes_coherence_requirements(self, tmp_path):
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(3, {"genre": "仙侠"})
        assert "连贯性核心要求" in ctx

    def test_adult_mode_is_injected(self, tmp_path):
        """核心回归：18+ 模式必须进上下文（原先 regen 入口漏了这一步）。"""
        obj = _make_agent(tmp_path, adult=True)
        ctx = obj._build_chapter_context(3, {"genre": "仙侠"})
        assert "18+" in ctx, "18+ 内容模式没有注入上下文"

    def test_edge_mode_is_injected(self, tmp_path):
        obj = _make_agent(tmp_path, edge=True)
        ctx = obj._build_chapter_context(3, {"genre": "言情"})
        assert "擦边" in ctx

    def test_mode_off_adds_nothing(self, tmp_path):
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(3, {"genre": "仙侠"})
        assert "18+" not in ctx and "擦边内容模式" not in ctx


class TestBoundaries:
    def test_no_history(self, tmp_path):
        """第 1 章：没有任何历史章节，不能崩。"""
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(1, {"genre": "仙侠"})
        assert isinstance(ctx, str)
        assert "连贯性核心要求" in ctx

    def test_empty_outline_and_world(self, tmp_path):
        obj = _make_agent(tmp_path)
        obj._get_outlines_context = lambda: ""
        obj._get_world_context = lambda: ""
        ctx = obj._build_chapter_context(2, {"genre": "仙侠"})
        assert isinstance(ctx, str) and ctx.strip()

    def test_missing_genre(self, tmp_path):
        obj = _make_agent(tmp_path)
        ctx = obj._build_chapter_context(2, {})
        assert isinstance(ctx, str)

    def test_meta_is_optional(self, tmp_path, monkeypatch):
        """不传 meta 时应自行读取，而不是崩在 None.get()。"""
        obj = _make_agent(tmp_path)
        obj._get_meta = lambda: {"genre": "仙侠", "word_count_per_chapter": 3000}
        ctx = obj._build_chapter_context(2)
        assert isinstance(ctx, str) and ctx.strip()
