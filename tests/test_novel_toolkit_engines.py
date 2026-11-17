"""创作工具库测试：元素/桥段/描写库、引擎类、热梗改编。

## 覆盖思路

`novel_toolkit.py` 里有三类东西，测试策略各不相同：

| 类型 | 例子 | 怎么测 |
|---|---|---|
| **数据 + 增删查** | `ElementLibrary` / `BridgeLibrary` / `DescriptionLibrary` | 真读写临时目录，验证自定义项落盘与回读 |
| **AI 驱动的引擎** | `DialogueEngine` / `StoryFlowEngine` / `StyleTransferEngine` / `AdaptEngine` | 假 AI 记录 prompt，断言"该传的参数真的传了" |
| **模板填充** | `WebSearchAdaptEngine` | 用固定模板断言占位符被替换、且只替换一次 |

对引擎类，**断言 prompt 内容而不是返回值**：这些方法的返回值就是 AI 原样返回，
断言它等于"断言假 AI 自己"；而 prompt 里是否带上了用户输入，才是真正的逻辑。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_toolkit import (
    AdaptEngine,
    BridgeLibrary,
    DescriptionLibrary,
    DialogueEngine,
    ElementLibrary,
    StoryFlowEngine,
    StyleTransferEngine,
    WebSearchAdaptEngine,
)

# ====================================================================== 假 AI


class FakeAI:
    """记录每次调用的假 AI。返回值可指定。"""

    def __init__(self, reply: str = "AI 生成结果"):
        self.reply = reply
        self.calls: list[dict] = []

    def chat(self, messages, system: str = "", max_tokens: int = 0, temperature: float = 0.7):
        self.calls.append(
            {"messages": messages, "system": system, "max_tokens": max_tokens, "temperature": temperature}
        )
        return self.reply

    @property
    def last_prompt(self) -> str:
        return self.calls[-1]["messages"][0]["content"]


# ====================================================================== 元素库


class TestElementLibrary:
    def test_categories_have_counts(self, tmp_path: Path):
        library = ElementLibrary(novel_dir=tmp_path)
        categories = library.get_categories()
        assert categories
        for row in categories:
            assert {"name", "desc", "count"} <= set(row)
            assert row["count"] >= 0

    def test_items_of_known_category(self, tmp_path: Path):
        library = ElementLibrary(novel_dir=tmp_path)
        name = library.get_categories()[0]["name"]
        assert library.get_items(name)

    def test_unknown_category_returns_empty(self, tmp_path: Path):
        assert ElementLibrary(novel_dir=tmp_path).get_items("不存在的类") == []

    def test_add_custom_item_persists(self, tmp_path: Path):
        library = ElementLibrary(novel_dir=tmp_path)
        library.add_custom_item("自定义类", {"name": "新元素", "template": "模板"})
        assert any(row["name"] == "自定义类" for row in library.get_categories())
        assert library.get_items("自定义类")[0]["name"] == "新元素"

    def test_add_custom_item_without_dir_is_noop(self):
        """没有作品目录时静默跳过 —— 不能因为"没打开书"就抛异常。"""
        ElementLibrary(novel_dir=None).add_custom_item("x", {"name": "y"})

    def test_custom_items_append(self, tmp_path: Path):
        library = ElementLibrary(novel_dir=tmp_path)
        library.add_custom_item("类", {"name": "一"})
        library.add_custom_item("类", {"name": "二"})
        assert [i["name"] for i in library.get_items("类")] == ["一", "二"]

    def test_generate_background_uses_selected_elements(self, tmp_path: Path):
        library = ElementLibrary(novel_dir=tmp_path)
        ai = FakeAI("背景设定")
        result = library.generate_background(
            ai,
            selected_elements=[{"name": "宗门", "template": "九大宗门"}],
            novel_type="玄幻",
            title="测试书",
        )
        assert result == "背景设定"
        prompt = ai.last_prompt
        assert "玄幻" in prompt and "测试书" in prompt and "九大宗门" in prompt


# ====================================================================== 桥段库


class TestBridgeLibrary:
    """注意：`BridgeLibrary` **没有 `__init__`**，不收 `novel_dir`（纯内存类常量）。"""

    def test_categories(self):
        assert BridgeLibrary().get_categories()

    def test_templates_of_category(self):
        library = BridgeLibrary()
        category = library.get_categories()[0]["name"]
        assert library.get_templates(category)

    def test_unknown_category_returns_empty(self):
        assert BridgeLibrary().get_templates("不存在的桥段") == []

    def test_add_custom_template(self):
        library = BridgeLibrary()
        library.add_custom_item("自定义桥段", "{a}看着{b}，什么也没说。", "沉默对峙")
        assert library.get_templates("自定义桥段")

    def test_generate_bridge_prompt(self):
        library = BridgeLibrary()
        ai = FakeAI("桥段文本")
        result = library.generate_bridge(
            ai,
            category="角色对战",
            characters={"a": "林默", "b": "秦风"},
            setting="苍云城",
        )
        assert result == "桥段文本"
        prompt = ai.last_prompt
        assert "林默" in prompt or "苍云城" in prompt


# ====================================================================== 描写库


class TestDescriptionLibrary:
    """`get_categories()` 返回的是**类别名列表**（`List[str]`），不是 dict 列表。"""

    def test_categories_are_names(self):
        categories = DescriptionLibrary().get_categories()
        assert categories
        assert all(isinstance(c, str) for c in categories)

    def test_add_custom_item(self):
        library = DescriptionLibrary()
        library.add_custom_item("自定义描写", "月光像一层薄霜铺在青石板上。")
        assert "自定义描写" in library.get_categories()

    def test_add_duplicate_is_ignored(self):
        library = DescriptionLibrary()
        library.add_custom_item("去重类", "同一条")
        library.add_custom_item("去重类", "同一条")
        assert library.CATEGORIES["去重类"].count("同一条") == 1

    def test_instances_are_isolated(self):
        """🔴 回归守卫：原先没有 `__init__`，新增项会写进**类属性**，
        导致一本书的描写出现在另一本书（甚至另一个会话）。"""
        first, second = DescriptionLibrary(), DescriptionLibrary()
        first.add_custom_item("隔离测试", "只在第一个实例")
        assert "隔离测试" not in second.get_categories()
        assert "隔离测试" not in DescriptionLibrary.CATEGORIES, "类属性被污染了"

    def test_generate_description_prompt(self):
        library = DescriptionLibrary()
        ai = FakeAI("描写文本")
        result = library.generate_description(ai, subject="破旧的老宅", category="环境")
        assert result == "描写文本"
        assert "破旧的老宅" in ai.last_prompt


# ====================================================================== 对话引擎


class TestDialogueEngine:
    def test_start_records_history(self):
        ai = FakeAI("对话内容")
        engine = DialogueEngine(ai)
        engine.start_dialogue("雨夜相遇", [{"name": "林默", "personality": "冷淡"}])
        assert engine.history
        assert "雨夜相遇" in ai.last_prompt
        assert "林默" in ai.last_prompt

    def test_continue_without_history(self):
        """没开始就继续 ⇒ 给出提示，不能 IndexError。"""
        engine = DialogueEngine(FakeAI())
        assert "请先开始" in engine.continue_dialogue()

    def test_continue_appends(self):
        ai = FakeAI("第一段")
        engine = DialogueEngine(ai)
        engine.start_dialogue("场景", [{"name": "甲"}])
        ai.reply = "第二段"
        engine.continue_dialogue("加紧张")
        assert len(engine.history) == 2
        assert "加紧张" in ai.last_prompt

    def test_continue_uses_tail_of_previous(self):
        """续写只带上一段末尾 500 字（避免 prompt 无限增长）。"""
        ai = FakeAI("长" * 800)
        engine = DialogueEngine(ai)
        engine.start_dialogue("场景", [{"name": "甲"}])
        engine.continue_dialogue()
        prompt = ai.last_prompt
        assert "长" * 500 in prompt
        assert "长" * 800 not in prompt

    def test_export_text_joins(self):
        ai = FakeAI("第一段")
        engine = DialogueEngine(ai)
        engine.start_dialogue("场景", [{"name": "甲"}])
        ai.reply = "第二段"
        engine.continue_dialogue()
        text = engine.export_text()
        assert "第一段" in text and "第二段" in text

    def test_export_empty(self):
        assert DialogueEngine(FakeAI()).export_text() == ""


# ====================================================================== 故事流引擎


class TestStoryFlowEngine:
    @pytest.mark.parametrize(
        "method,args,expected_fragments",
        [
            ("mode1_forward", ("剑与魔法", "林默", "宗门大比"), ["剑与魔法", "林默", "宗门大比"]),
            ("mode2_bridge", ("主角被逐出师门", "主角登临巅峰"), ["被逐出师门", "登临巅峰"]),
            ("mode3_branch", ("主角发现身世",), ["主角发现身世"]),
            ("mode4_conflict_escalation", ("两方对峙",), ["两方对峙"]),
        ],
    )
    def test_prompts_carry_inputs(self, method, args, expected_fragments):
        ai = FakeAI("推演结果")
        engine = StoryFlowEngine(ai)
        getattr(engine, method)(*args)
        for fragment in expected_fragments:
            assert fragment in ai.last_prompt, f"{method} 的 prompt 丢了「{fragment}」"

    def test_branch_count_is_passed(self):
        ai = FakeAI()
        StoryFlowEngine(ai).mode3_branch("故事", branch_count=5)
        assert "5" in ai.last_prompt


# ====================================================================== 风格转换


class TestStyleTransferEngine:
    def test_styles_registry(self):
        styles = StyleTransferEngine(FakeAI()).get_styles()
        assert len(styles) >= 10
        for name, info in styles.items():
            assert {"desc", "temp", "system"} <= set(info), name
            assert 0 < info["temp"] <= 1.5

    def test_convert_known_style(self):
        ai = FakeAI()
        StyleTransferEngine(ai).convert_style("原文内容", "热血爽文")
        assert ai.calls[-1]["system"] == StyleTransferEngine.STYLES["热血爽文"]["system"]
        assert ai.calls[-1]["temperature"] == StyleTransferEngine.STYLES["热血爽文"]["temp"]
        assert "原文内容" in ai.last_prompt

    def test_convert_unknown_style_falls_back(self):
        """未知风格名 ⇒ 用默认 system 与温度，不能 KeyError。"""
        ai = FakeAI()
        StyleTransferEngine(ai).convert_style("原文", "不存在的风格")
        assert ai.calls[-1]["system"] == "你是小说作家。"
        assert ai.calls[-1]["temperature"] == 0.8

    def test_long_text_is_truncated(self):
        """超长文本要截到 3000 字，否则会超出上下文。"""
        ai = FakeAI()
        StyleTransferEngine(ai).convert_style("字" * 5000, "热血爽文")
        assert "字" * 3000 in ai.last_prompt
        assert "字" * 3001 not in ai.last_prompt


# ====================================================================== 智能改编


class TestAdaptEngine:
    def test_adapt_segment_returns_structured(self):
        ai = FakeAI("改编后的内容")
        result = AdaptEngine(ai).adapt_segment("原始内容", "改得更紧张")
        assert {"original", "adapted", "match_rate"} <= set(result)
        assert result["adapted"] == "改编后的内容"
        assert "改得更紧张" in ai.last_prompt

    def test_match_rate_within_bounds(self):
        """匹配率必须落在 30–95 —— 它是给用户看的百分比，越界会显示成负数或 >100%。"""
        for reply in ("短", "中等长度的内容", "很长" * 500):
            result = AdaptEngine(FakeAI(reply)).adapt_segment("原始内容", "指令")
            assert 30 <= result["match_rate"] <= 95, result["match_rate"]

    def test_original_is_truncated(self):
        result = AdaptEngine(FakeAI("x")).adapt_segment("原" * 900, "指令")
        assert len(result["original"]) <= 500

    def test_random_adapt_count(self):
        results = AdaptEngine(FakeAI("x")).random_adapt("原文", count=3)
        assert len(results) == 3

    def test_random_adapt_capped_by_instruction_pool(self):
        """请求数超过可用指令数时，不能重复使用同一条指令造成空跑。"""
        results = AdaptEngine(FakeAI("x")).random_adapt("原文", count=99)
        assert len(results) < 99
        instructions = [r for r in results]
        assert instructions  # 至少有一条

    def test_random_adapt_uses_different_instructions(self):
        ai = FakeAI("x")
        AdaptEngine(ai).random_adapt("原文", count=3)
        prompts = [call["messages"][0]["content"] for call in ai.calls]
        assert len(set(prompts)) == len(prompts), "每条改编指令应当不同"


# ====================================================================== 热梗改编


class TestWebSearchAdaptEngine:
    def test_categories_loaded(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert engine.get_categories()

    def test_items_of_default_category(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert engine.get_items()

    def test_add_custom_meme_persists(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        item = engine.add_custom_meme("自定义梗", "测试梗", "描述", "{name}在{place}遇到{num}个人")
        assert item["custom"] is True
        assert any(i.get("name") == "测试梗" for i in engine.get_items("自定义梗"))
        # 落盘：新实例能读回
        reloaded = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert any(i.get("name") == "测试梗" for i in reloaded.get_items("自定义梗"))

    def test_delete_custom_meme(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        engine.add_custom_meme("自定义梗", "待删", "", "{name}")
        items = engine.get_items("自定义梗")
        index = next(i for i, row in enumerate(items) if row.get("name") == "待删")
        engine.delete_custom_meme("自定义梗", index)
        assert not any(row.get("name") == "待删" for row in engine.get_items("自定义梗"))

    def test_delete_builtin_is_rejected(self, tmp_path: Path):
        """内置梗没有 custom 标记 ⇒ 不能被删（否则用户误操作会丢内置库）。"""
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        category = engine.get_categories()[0]
        before = len(engine.get_items(category))
        engine.delete_custom_meme(category, 0)
        assert len(engine.get_items(category)) == before

    def test_delete_out_of_range_is_safe(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        engine.delete_custom_meme("不存在", 99)

    def test_fill_template_replaces_placeholders(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        result = engine._fill_template("{name}在{place}遇见了{num}个人")
        assert "{" not in result, f"占位符未替换完：{result}"

    def test_fill_template_replaces_only_first_occurrence(self, tmp_path: Path):
        """同名占位符只替换一次是既定行为 —— 记下来，免得被当 bug 改坏。"""
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        result = engine._fill_template("{name}-{name}")
        assert result.count("{name}") == 1

    def test_search_with_query_uses_ai(self, tmp_path: Path):
        ai = FakeAI("改编结果")
        engine = WebSearchAdaptEngine(ai, novel_dir=tmp_path)
        result = engine.search_and_adapt(query="某个热点", category="热梗改编")
        assert result == "改编结果"
        assert "某个热点" in ai.last_prompt

    def test_search_without_query_fills_template(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        result = engine.search_and_adapt(query="", category=engine.get_categories()[0])
        assert result and result != "暂无内容"

    def test_search_unknown_category(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert engine.search_and_adapt(query="", category="不存在的类") == "暂无内容"

    def test_ai_adapt_prompt_has_character_name(self, tmp_path: Path):
        """`_ai_adapt` 曾因引用未定义的 `name` 抛 NameError，这里钉住修复。"""
        ai = FakeAI()
        engine = WebSearchAdaptEngine(ai, novel_dir=tmp_path)
        engine.search_and_adapt(query="素材", category="热梗改编")
        assert "有角色" in ai.last_prompt

    def test_random_meme(self, tmp_path: Path):
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert engine.random_meme()

    def test_corrupt_custom_file_is_tolerated(self, tmp_path: Path):
        """自定义梗文件损坏 ⇒ 忽略，不能拖垮整个引擎。"""
        custom_dir = tmp_path / "websearch_custom"
        custom_dir.mkdir()
        (custom_dir / "custom_hot_memes.json").write_text("{坏 json", encoding="utf-8")
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        assert engine.get_categories()

    def test_class_library_not_mutated(self, tmp_path: Path):
        """实例加梗不能污染类变量（否则换本书还能看到上一本的梗）。"""
        before = {k: len(v) for k, v in WebSearchAdaptEngine.HOT_MEMES.items()}
        engine = WebSearchAdaptEngine(FakeAI(), novel_dir=tmp_path)
        engine.add_custom_meme("隔离测试", "只有这一本", "", "{name}")
        after = {k: len(v) for k, v in WebSearchAdaptEngine.HOT_MEMES.items()}
        assert before == after


# ====================================================================== 自定义项落盘格式


class TestPersistenceFormat:
    def test_custom_items_file_is_utf8_json(self, tmp_path: Path):
        """自定义项必须存成可读 UTF-8 JSON —— 中文不能被转义成 \\uXXXX。"""
        library = ElementLibrary(novel_dir=tmp_path)
        library.add_custom_item("中文类", {"name": "中文项"})
        target = tmp_path / "custom_elements" / "中文类.json"
        if not target.exists():  # 目录名可能是别的，找一下
            candidates = list(tmp_path.glob("*/中文类.json"))
            assert candidates, "自定义项没有落盘"
            target = candidates[0]
        raw = target.read_text(encoding="utf-8")
        assert "中文项" in raw, "中文被转义了（ensure_ascii 没关）"
        assert json.loads(raw)["items"][0]["name"] == "中文项"
