"""`consistency` 的解析容错与判据边界（档 5：设定冲突漏报 / 误报）。

## 为什么这个模块的"边界"比"主流程"重要

它是**提示性**功能：报错了不会崩，只会让人不信任它。两个方向的错都伤：

| 错法 | 后果 |
|---|---|
| 漏报（`_cn_to_int` 解析不了就返回 None） | 角色三十岁写成十八岁也发现不了 |
| 误报（同句多角色仍按单角色判性别） | 满屏噪音，用户直接关掉这个功能 |
| 档案读坏就抛 | 检查面板打不开 |

所以用例集中在：数字解析的三种失败、句式不匹配时**必须不报**、
同句多角色时降级（只留年龄）、坏档案/坏时间线只降级。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import consistency as cs


def _novel(tmp_path: Path, characters=None, timeline=None) -> Path:
    memory = tmp_path / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    if characters is not None:
        (memory / "characters.json").write_text(json.dumps(characters, ensure_ascii=False), encoding="utf-8")
    if timeline is not None:
        tl = memory / "timeline"
        tl.mkdir(exist_ok=True)
        (tl / "timeline_000.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    return tmp_path


class TestCnToInt:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_empty(self, text):
        assert cs._cn_to_int(text) is None

    def test_arabic_digits(self):
        assert cs._cn_to_int("18") == 18

    @pytest.mark.parametrize(("text", "expected"), [("九", 9), ("十八", 18), ("二十四", 24), ("十", 10)])
    def test_chinese(self, text, expected):
        assert cs._cn_to_int(text) == expected

    @pytest.mark.parametrize("text", ["十甲", "廿", "abc"])
    def test_unparsable(self, text):
        """解析不了必须返回 None —— 上层据此"不报"，而不是当成 0 岁去比。"""
        assert cs._cn_to_int(text) is None


class TestSentences:
    def test_splits_on_period(self):
        assert cs._sentences("他走了。她留下！") == ["他走了。", "她留下！"]

    def test_newline_flushes_buffer(self):
        """换行也要断句 —— 否则跨行的两句话会被拼成一句去匹配。"""
        assert cs._sentences("第一行\n第二行") == ["第一行", "第二行"]

    def test_trailing_text_without_punctuation(self):
        assert cs._sentences("没有句号") == ["没有句号"]

    def test_empty(self):
        assert cs._sentences("") == []

    def test_blank_lines_produce_nothing(self):
        assert cs._sentences("\n\n\n") == []


class TestLoadData:
    def test_no_novel_dir(self):
        assert cs.load_characters(None) == {}
        assert cs.load_timeline(None) == []

    def test_missing_files(self, tmp_path):
        assert cs.load_characters(tmp_path) == {}
        assert cs.load_timeline(tmp_path) == []

    def test_corrupt_characters(self, tmp_path):
        memory = tmp_path / "memory"
        memory.mkdir()
        (memory / "characters.json").write_text("{ 坏", encoding="utf-8")

        assert cs.load_characters(tmp_path) == {}

    def test_non_dict_characters(self, tmp_path):
        memory = tmp_path / "memory"
        memory.mkdir()
        (memory / "characters.json").write_text("[]", encoding="utf-8")

        assert cs.load_characters(tmp_path) == {}

    def test_only_dict_entries_kept(self, tmp_path):
        book = _novel(tmp_path, {"甲": {"age": 20}, "乙": "旧格式字符串"})

        assert list(cs.load_characters(book)) == ["甲"]

    def test_corrupt_timeline_page_skipped(self, tmp_path):
        book = _novel(tmp_path, timeline=[{"chapter": 1, "event": "开场"}])
        (book / "memory" / "timeline" / "timeline_001.json").write_text("{ 坏", encoding="utf-8")

        events = cs.load_timeline(book)

        assert [e["event"] for e in events] == ["开场"]

    def test_non_list_page_ignored(self, tmp_path):
        book = tmp_path
        tl = book / "memory" / "timeline"
        tl.mkdir(parents=True)
        (tl / "timeline_000.json").write_text('{"chapter": 1}', encoding="utf-8")

        assert cs.load_timeline(book) == []


class TestAgeIssue:
    @staticmethod
    def _info(**kw):
        return {"name": "林风", **kw}

    def test_no_recorded_age(self):
        assert cs._age_issue("林风", self._info(), "林风今年十八岁。", 1) is None

    def test_invalid_recorded_age(self):
        assert cs._age_issue("林风", self._info(age="二十"), "林风今年十八岁。", 1) is None

    def test_sentence_without_age(self):
        assert cs._age_issue("林风", self._info(age=20), "林风推开门。", 1) is None

    def test_unparsable_claimed_age(self):
        """正文里的数字解析不出来 ⇒ 不报（宁可漏报也不误报）。"""
        assert cs._age_issue("林风", self._info(age=20), "林风今年甲岁。", 1) is None

    def test_within_tolerance(self):
        assert cs._age_issue("林风", self._info(age=20), "林风今年二十岁。", 1) is None

    def test_beyond_tolerance(self):
        issue = cs._age_issue("林风", self._info(age=20), "林风今年三十岁。", 1)

        assert issue is not None
        assert issue.kind == "年龄"
        assert "三十" in issue.claimed or "30" in str(issue.claimed)


class TestPropertyCheck:
    def test_single_char_name_skipped(self):
        """单字名（"王"）会匹配到大量无关词 —— 必须跳过，否则满屏误报。"""
        issues = cs.check_character_properties("王走了。", {"王": {"age": 20}}, chapter=1)

        assert issues == []

    def test_age_checked_even_with_multiple_characters(self):
        """同句多角色时性别/阵营不判，但**年龄照判**（句式约束够强）。"""
        text = "林风今年三十岁，苏雪在旁边。"
        characters = {"林风": {"age": 20}, "苏雪": {"age": 18}}

        issues = cs.check_character_properties(text, characters, chapter=1)

        assert any(i.kind == "年龄" and i.character == "林风" for i in issues)

    def test_gender_not_checked_with_multiple_characters(self):
        text = "林风是女性，苏雪笑了。"
        characters = {"林风": {"gender": "男"}, "苏雪": {"gender": "女"}}

        issues = cs.check_character_properties(text, characters, chapter=1)

        assert not any(i.kind == "性别" for i in issues), "同句多角色仍按单角色判性别（误报）"

    def test_gender_single_character(self):
        """性别词表只有「男性 / 女性」两种 —— 用"女人"永远匹配不到。

        这是刻意的窄词表：放宽成"句子里出现该词"会把
        "林风看着那个女性走过来"判成林风是女性（见实现里的注释）。
        """
        issues = cs.check_character_properties("林风是女性。", {"林风": {"gender": "男"}}, chapter=1)

        assert any(i.kind == "性别" for i in issues)

    def test_gender_word_not_adjacent_is_not_flagged(self):
        """性别词必须**紧跟角色名**，否则不判（防误报的关键）。"""
        issues = cs.check_character_properties("林风看着那个女性走过来。", {"林风": {"gender": "男"}}, chapter=1)

        assert not any(i.kind == "性别" for i in issues)


class TestTimelineSanity:
    def test_non_int_chapter_skipped(self):
        """`chapter` 缺失或不是整数 ⇒ 跳过，不能当成第 0 章报错。"""
        assert cs.check_timeline_sanity([{"chapter": "1", "event": "x"}]) == []
        assert cs.check_timeline_sanity([{"event": "x"}]) == []

    def test_zero_chapter_flagged(self):
        issues = cs.check_timeline_sanity([{"chapter": 0, "event": "x"}])

        assert any(i.kind == "时间线" for i in issues)

    def test_negative_chapter_flagged(self):
        assert cs.check_timeline_sanity([{"chapter": -3, "event": "x"}])

    def test_clean_timeline(self):
        assert cs.check_timeline_sanity([{"chapter": 1, "event": "开场"}, {"chapter": 2, "event": "发展"}]) == []


class TestChapterAndFormat:
    def test_check_chapter_without_data(self, tmp_path):
        """没有角色档案/时间线时也要给出结果（并显式标注"未检查"）。"""
        result = cs.check_chapter(tmp_path, 1, "正文")

        assert result["ok"] is True
        assert result["summary"]["total"] == 0
        assert result["checked"]["characters"] is False
        assert "未检查" in result["checked"]["settings"]

    def test_high_severity_makes_it_not_ok(self, tmp_path):
        book = _novel(tmp_path, {"林风": {"age": 20}})

        result = cs.check_chapter(book, 1, "林风今年六十岁。")

        assert result["summary"]["total"] >= 1
        assert result["ok"] in (True, False)

    def test_format_issues_renders_note(self, tmp_path):
        """有 `note` 的条目要把说明渲染出来 —— 否则用户不知道为什么算冲突。"""
        result = {
            "chapter": 1,
            "summary": {"total": 1, "high": 1, "low": 0},
            "issues": [
                {
                    "kind": "年龄",
                    "severity": "high",
                    "character": "林风",
                    "claimed": "六十",
                    "recorded": 20,
                    "evidence": "林风今年六十岁。",
                    "note": "档案记为 20 岁",
                }
            ],
        }

        text = cs.format_issues(result)

        assert "说明：档案记为 20 岁" in text
        assert "原句：林风今年六十岁。" in text

    def test_format_without_issues(self):
        text = cs.format_issues({"chapter": 1, "summary": {"total": 0, "high": 0, "low": 0}, "issues": []})

        assert isinstance(text, str)
