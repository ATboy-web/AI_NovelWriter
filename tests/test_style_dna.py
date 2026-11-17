"""风格 DNA 测试：解析容错 / 注入 / 漂移比对 / 与门禁的联动。

重点验证三件事（对应本轮建议 2）：

1. **读得进**：坏 JSON、字段类型错、缺字段都不能抛异常，但必须留 warning；
2. **注得进**：没有指纹时不注入任何内容（避免每个作品都多一段废话）；
3. **管得住**：`favorite_marks` 声明的标点必须真的让质检放行 ——
   "冲突以风格文档为准"不能只是提示词里的一句话。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.style_dna import (
    PRONOUN_GROUPS,
    StyleDNA,
    find_dna_file,
    format_drift,
    load_style_dna,
    parse_style_dna,
    save_dna_template,
    style_drift,
    style_prompt,
)

NL = chr(10)


def _dna(**kwargs) -> StyleDNA:
    base = {
        "name": "测试",
        "person": "第三人称限知",
        "tone": "冷静",
        "sentence": {"mean": 20, "cv": 0.4},
        "favorite_marks": ["——"],
        "banned_words": ["赋能"],
    }
    base.update(kwargs)
    return parse_style_dna(base)


# ====================================================================== 解析


class TestParse:
    def test_full_fields(self):
        dna = _dna()
        assert dna.name == "测试"
        assert dna.person == "第三人称限知"
        assert dna.sentence_mean == 20
        assert dna.favorite_marks == ("——",)
        assert dna.banned_words == ("赋能",)
        assert dna.warnings == ()

    def test_chinese_keys(self):
        dna = parse_style_dna({"人称": "第一人称", "语气": "犀利", "禁词": "闭环"})
        assert dna.person == "第一人称"
        assert dna.tone == "犀利"
        assert dna.banned_words == ("闭环",)

    def test_string_list_coercion(self):
        """`"a,b c"` 这种手写串要能拆开，不能整段当一个词。"""
        dna = parse_style_dna({"favorite_marks": "——,…… 、~~~"})
        assert set(dna.favorite_marks) == {"——", "……", "~~~"}

    def test_non_dict_returns_warning(self):
        dna = parse_style_dna([1, 2, 3])
        assert dna.warnings
        assert dna.is_empty

    def test_unknown_person_warns(self):
        dna = parse_style_dna({"person": "第四人称"})
        assert any("不在已知人称分组" in w for w in dna.warnings)

    def test_sentence_as_number_is_tolerated(self):
        dna = parse_style_dna({"sentence": 25})
        assert dna.sentence_mean == 25
        assert dna.warnings

    def test_empty_markers_warn(self):
        dna = parse_style_dna({"favorite_marks": []})
        assert any("favorite_marks" in w for w in dna.warnings)

    def test_is_empty(self):
        assert parse_style_dna({}).is_empty is True
        assert parse_style_dna({"tone": "冷静"}).is_empty is False


class TestLoad:
    def test_missing_returns_none(self, tmp_path: Path):
        assert load_style_dna(tmp_path) is None
        assert load_style_dna(None) is None

    def test_loads_standard_filename(self, tmp_path: Path):
        (tmp_path / "风格DNA.json").write_text(
            json.dumps({"person": "第一人称", "banned_words": ["赋能"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        dna = load_style_dna(tmp_path)
        assert dna is not None and dna.person == "第一人称"
        assert find_dna_file(tmp_path).name == "风格DNA.json"

    def test_broken_json_returns_dna_with_warning(self, tmp_path: Path):
        (tmp_path / "风格DNA.json").write_text("{不是 json", encoding="utf-8")
        dna = load_style_dna(tmp_path)
        assert dna is not None
        assert dna.warnings and "读取失败" in dna.warnings[0]

    def test_prose_only_gives_reference(self, tmp_path: Path):
        """只有散文文档时：不注入规则，但要把"参考它"告诉模型。"""
        (tmp_path / "语言DNA.md").write_text("我的写法……", encoding="utf-8")
        dna = load_style_dna(tmp_path)
        assert dna is not None
        assert dna.prose_reference.endswith("语言DNA.md")
        assert "参考文档" in style_prompt(dna)

    def test_save_template(self, tmp_path: Path):
        ok, message = save_dna_template(tmp_path)
        assert ok and "风格DNA.json" in message
        assert find_dna_file(tmp_path).is_file()
        # 不覆盖既有文件
        ok2, _ = save_dna_template(tmp_path)
        assert ok2 is False

    def test_save_template_without_novel(self):
        ok, message = save_dna_template(None)
        assert ok is False and "没有打开的作品" in message


# ====================================================================== 注入


class TestPrompt:
    def test_empty_dna_gives_nothing(self):
        assert style_prompt(None) == ""
        assert style_prompt(parse_style_dna({})) == ""

    def test_contains_all_fingerprints(self):
        text = style_prompt(_dna())
        assert "作者风格 DNA" in text
        assert "第三人称限知" in text
        assert "冷静" in text
        assert "均值约 20" in text
        assert "——" in text
        assert "赋能" in text

    def test_marks_are_declared_as_author_feature(self):
        """ "不按 AI 指纹规则删改"必须出现在提示词里，否则模型仍会按通用规则删。"""
        assert "不按 AI 指纹规则删改" in style_prompt(_dna())

    def test_budget_truncation(self):
        text = style_prompt(_dna(), budget=60)
        assert len(text) <= 60

    def test_person_warning_not_in_prompt(self):
        """解析警告是给界面看的，不该污染提示词。"""
        dna = parse_style_dna({"person": "第四人称"})
        assert "不在已知人称分组" not in style_prompt(dna)


# ====================================================================== 漂移


class TestDrift:
    def test_none_dna_returns_none(self):
        assert style_drift("任意文本", None) is None
        assert style_drift("任意文本", parse_style_dna({})) is None

    def test_person_mixing_detected(self):
        dna = _dna()
        text = "他走进房间。她坐下。我们都看着。你说呢。" * 3
        drift = style_drift(text, dna, person_strict=True)
        assert drift is not None
        assert drift.person["ok"] is False
        assert drift.ok is False

    def test_person_mixing_is_soft_by_default(self):
        """非叙事体裁：人称混用只提示，不算硬伤。"""
        dna = _dna()
        text = "他走进房间。她坐下。我们都看着。你说呢。" * 3
        drift = style_drift(text, dna)
        assert drift.person["ok"] is False
        assert drift.ok is True
        assert drift.issues == []

    def test_sentence_length_deviation(self):
        dna = _dna(sentence={"mean": 10})
        text = "这是一句特别特别特别长的句子用来拉高平均字数。" * 5
        drift = style_drift(text, dna)
        assert drift is not None
        assert drift.sentence["ok"] is False
        assert "实测" in drift.sentence["detail"]

    def test_sentence_within_band(self):
        dna = _dna(sentence={"mean": 20})
        text = "今天天气不错，我们不如出去走走散散步吧。"  # 20 字，正好落在容许带内
        drift = style_drift(text, dna)
        assert drift.sentence["ok"] is True, drift.sentence

    def test_favorite_mark_counted(self):
        dna = _dna(favorite_marks=["——"])
        drift = style_drift("他停了一下——然后走了。", dna)
        assert drift.marks["counts"]["——"] == 1

    def test_missing_mark_is_advisory_only(self):
        dna = _dna(favorite_marks=["……"])
        drift = style_drift("没有省略号的句子。", dna)
        assert drift.marks["advisory"] is True
        assert drift.marks["ok"] is False
        assert drift.ok is True  # 不因"缺标点"判不合格

    def test_banned_words_hard_fail(self):
        dna = _dna(banned_words=["赋能", "闭环"])
        drift = style_drift("这件事赋能了团队，形成闭环。", dna)
        assert drift.banned["ok"] is False
        assert set(drift.banned["hits"]) == {"赋能", "闭环"}
        assert drift.ok is False
        assert any("禁词" in i for i in drift.issues)

    def test_allows_mark(self):
        dna = _dna(favorite_marks=["——"])
        assert dna.allows_mark("——") is True
        assert dna.allows_mark("……") is False

    def test_format_drift_marks(self):
        dna = _dna()
        text = "他来了。" + "我们都看着。" * 5
        rendered = format_drift(style_drift(text, dna))
        assert "风格 DNA 比对" in rendered
        # 非严格模式下人称问题用 ⚠️ 而非 ❌
        assert "⚠️" in rendered

    def test_format_drift_none(self):
        assert format_drift(None) == ""

    def test_pronoun_groups_long_word_first(self):
        """`我们` 不能被拆成 `我` 计数，否则第一人称永远偏高。"""
        for words in PRONOUN_GROUPS.values():
            lengths = [len(w) for w in words]
            assert lengths == sorted(lengths, reverse=True), words


# ====================================================================== 与门禁联动


class TestGateIntegration:
    def test_dna_releases_dash_gate(self, tmp_path: Path):
        """🔴 核心断言：DNA 声明爱用破折号 ⇒ 质检放行，但**数字照实显示**。"""
        from app.writing_presets import PRESETS, qc_report

        text = ("他停了一下——然后走了。" * 30) + ("正文内容继续说下去。" * 30)
        dna = _dna(favorite_marks=["——"])
        without = qc_report(text, PRESETS["deai-full"], with_candidates=False)
        with_dna = qc_report(text, PRESETS["deai-full"], with_candidates=False, dna=dna)

        dash_without = next(i for i in without["items"] if i["detector"] == "dash")
        dash_with = next(i for i in with_dna["items"] if i["detector"] == "dash")
        assert dash_without["passed"] is False
        assert dash_with["passed"] is True
        assert dash_with["style_allowed"] is True
        # 数字不得被悄悄清零
        assert dash_with["count"] == dash_without["count"] > 0

    def test_no_dna_no_release(self):
        from app.writing_presets import PRESETS, qc_report

        text = ("他停了一下——然后走了。" * 30) + ("正文内容继续说下去。" * 30)
        report = qc_report(text, PRESETS["deai-full"], with_candidates=False)
        dash = next(i for i in report["items"] if i["detector"] == "dash")
        assert dash["style_allowed"] is False

    def test_style_hard_fail_makes_report_fail(self):
        from app.writing_presets import PRESETS, qc_report

        clean = "今天天气不错，我们出去走走吧。" * 40
        dna = _dna(banned_words=["天气"])
        report = qc_report(clean, PRESETS["deai-full"], with_candidates=False, dna=dna)
        assert report["style"]["ok"] is False
        assert report["ok"] is False
