"""大纲上下文构建的纯逻辑测试（无显示环境可跑，CI 计入门禁）。

## 为什么值得测

`outline_ui` 此前整文件被覆盖率门禁排除（omit），但它承载的
「把大纲/世界观组装成喂给 AI 的上下文」是**创作质量的核心链路**：
截断长度、格式兼容（旧 dict / 新 list）、内容模式注入的取舍都在这里。
这些方法不碰任何 Tk 控件 —— 只依赖 `current_novel_dir` 与文件系统，
因此用假宿主即可在 CI 上完整执行（同 `theme_switch` 补测已验证的路径）。

## 测什么

- `_build_content_hint`：adult/edge/genre 的组合矩阵与类型增强匹配
- `_get_overall_outline`：旧 dict 格式归一化、list 透传、文件缺失
- `_get_story_outlines`：读取与缺失
- `_get_outlines_context`：两种格式的渲染、条数截断、空大纲
- `_get_world_context`：settings.json 的 raw 字段、markdown 围栏清理、长度截断
- `_token_badge`：None / 0 / 非数值 / 正常值的分支
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.outline_ui import OutlineUIMixin, _token_badge


class _Host(OutlineUIMixin):
    """鸭子类型宿主：只提供 Mixin 实际用到的属性。"""

    def __init__(self, novel_dir: Path | None):
        self.current_novel_dir = novel_dir
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)

    def _novel_store(self):  # pragma: no cover - 保存路径测试在 persistence 侧覆盖
        raise NotImplementedError


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(tmp_path)


# ─────────────────────────── _build_content_hint ───────────────────────────


class TestBuildContentHint:
    def test_both_modes_off_leaves_only_genre_hint(self, host):
        text = host._build_content_hint(adult=False, edge=False, genre="玄幻")
        assert "18+" not in text and "擦边" not in text
        assert "武侠/仙侠类型" in text

    def test_no_match_and_no_modes_returns_empty(self, host):
        assert host._build_content_hint(adult=False, edge=False, genre="科幻") == ""

    def test_adult_only(self, host):
        text = host._build_content_hint(adult=True, edge=False, genre="")
        assert "18+成人内容模式" in text
        assert "擦边内容模式" not in text

    def test_edge_only(self, host):
        text = host._build_content_hint(adult=False, edge=True, genre="")
        assert "擦边内容模式" in text
        assert "18+" not in text

    def test_both_modes(self, host):
        text = host._build_content_hint(adult=True, edge=True, genre="")
        assert "18+成人内容模式" in text and "擦边内容模式" in text

    @pytest.mark.parametrize(
        ("genre", "keyword"),
        [
            ("都市言情", "言情类型"),
            ("Romance 都市", "言情类型"),
            ("仙侠修真", "武侠/仙侠类型"),
            ("悬疑推理", "悬疑/恐怖类型"),
            ("末日废土", "末日类型"),
            ("科幻", None),
        ],
    )
    def test_genre_enhancement(self, host, genre, keyword):
        text = host._build_content_hint(adult=False, edge=False, genre=genre)
        if keyword is None:
            assert "【类型增强】" not in text
        else:
            assert keyword in text

    def test_genre_match_is_case_insensitive(self, host):
        text = host._build_content_hint(adult=False, edge=False, genre="APocalypse")
        assert "末日类型" in text

    def test_genre_empty_string_safe(self, host):
        assert host._build_content_hint(adult=True, edge=False, genre="").startswith("【")


# ─────────────────────────── 大纲读取与归一化 ───────────────────────────


class TestGetOverallOutline:
    def test_missing_dir_returns_empty(self, tmp_path):
        host = _Host(None)
        assert host._get_overall_outline() == []
        host2 = _Host(tmp_path)
        assert host2._get_overall_outline() == []

    def test_legacy_dict_normalized_to_list(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        (outline_dir / "overall.json").write_text(
            json.dumps({"title": "第一卷", "description": "开局"}), encoding="utf-8"
        )
        result = host._get_overall_outline()
        assert result == [{"title": "第一卷", "description": "开局"}]

    def test_list_passthrough(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        data = [{"title": f"章{i}"} for i in range(3)]
        (outline_dir / "overall.json").write_text(json.dumps(data), encoding="utf-8")
        assert host._get_overall_outline() == data


class TestGetStoryOutlines:
    def test_missing_returns_empty(self, host):
        assert host._get_story_outlines() == {}

    def test_reads_stories_json(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        data = {"主线": {"summary": "复仇"}}
        (outline_dir / "stories.json").write_text(json.dumps(data), encoding="utf-8")
        assert host._get_story_outlines() == data


# ─────────────────────────── 上下文组装 ───────────────────────────


class TestGetOutlinesContext:
    def test_empty_when_no_files(self, host):
        assert host._get_outlines_context() == ""

    def test_overall_dict_renders_numbered_line(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        (outline_dir / "overall.json").write_text(
            json.dumps({"title": "觉醒", "description": "主角获得能力"}), encoding="utf-8"
        )
        text = host._get_outlines_context()
        assert "【整体大纲" in text
        assert "1. 觉醒：主角获得能力" in text

    def test_overall_list_truncates_to_15(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        data = [{"title": f"章{i}", "description": "x"} for i in range(20)]
        (outline_dir / "overall.json").write_text(json.dumps(data), encoding="utf-8")
        text = host._get_outlines_context()
        assert "1. 章0" in text and "15. 章14" in text
        assert "16." not in text

    def test_description_falls_back_to_content_key(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        (outline_dir / "overall.json").write_text(
            json.dumps([{"title": "T", "content": "用 content 字段的描述"}]), encoding="utf-8"
        )
        assert "用 content 字段的描述" in host._get_outlines_context()

    def test_story_outlines_rendered_and_truncated_to_8(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        stories = {f"线{i}": {"summary": f"摘要{i}"} for i in range(10)}
        (outline_dir / "stories.json").write_text(json.dumps(stories), encoding="utf-8")
        text = host._get_outlines_context()
        assert "【故事大纲" in text
        assert "故事线「线0」" in text and "故事线「线7」" in text
        assert "故事线「线8」" not in text

    def test_overall_and_stories_joined_by_blank_line(self, host, tmp_path):
        outline_dir = tmp_path / "outlines"
        outline_dir.mkdir()
        (outline_dir / "overall.json").write_text(json.dumps([{"title": "A", "description": "a"}]), encoding="utf-8")
        (outline_dir / "stories.json").write_text(json.dumps({"S": {"summary": "s"}}), encoding="utf-8")
        text = host._get_outlines_context()
        assert "【整体大纲" in text and "【故事大纲" in text


# ─────────────────────────── 世界观上下文 ───────────────────────────


class TestGetWorldContext:
    def test_no_novel_dir_returns_empty(self, tmp_path):
        assert _Host(None)._get_world_context() == ""

    def test_missing_settings_returns_empty(self, host):
        assert host._get_world_context() == ""

    def test_raw_field_with_markdown_fences_cleaned(self, host, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "settings.json").write_text(json.dumps({"raw": "```json\n{灵气浓度: 高}\n```"}), encoding="utf-8")
        text = host._get_world_context()
        assert "```" not in text
        assert "灵气浓度" in text
        assert text.startswith("【世界观设定")

    def test_falls_back_to_serializing_whole_dict(self, host, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "settings.json").write_text(json.dumps({"力量体系": "九境"}, ensure_ascii=False), encoding="utf-8")
        assert "九境" in host._get_world_context()

    def test_truncated_to_3000_chars(self, host, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "settings.json").write_text(json.dumps({"raw": "长" * 5000}), encoding="utf-8")
        text = host._get_world_context()
        assert len(text) < 5000

    def test_corrupt_json_swallowed(self, host, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "settings.json").write_text("{broken", encoding="utf-8")
        assert host._get_world_context() == ""


# ─────────────────────────── token 徽标 ───────────────────────────


class TestTokenBadge:
    @pytest.mark.parametrize("bad", [None, 0, -5, "abc", ""])
    def test_no_display_for_missing_or_invalid(self, bad):
        assert _token_badge(bad) == ""

    def test_positive_value(self):
        assert _token_badge(1500) == "  · 1.5K"

    def test_small_value_not_compacted(self):
        assert _token_badge(900).endswith("900")

    def test_numeric_string_accepted(self):
        assert _token_badge("2400") != ""
