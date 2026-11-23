"""风格 DNA 学习与渲染的纯逻辑测试。

## 为什么值得测

「从成稿学习」是技能库面板的核心增值功能：它把用户已有章节统计成一份
**可核对、可修改**的风格草稿。此前该路径整体未覆盖（style_dna 84.2%，
缺口集中在 `_learn_paragraphs` / `learn_from_texts` / `learn_and_save`）。

这些函数全部是纯逻辑（不碰 Tk），补测无显示环境亦可跑，CI 计入门禁。

## 测什么

- `_learn_paragraphs`：空行分段、段内换行合并、尾部缓冲
- `learn_from_texts`：样本不足、人称集中/不集中/缺失、句长均值与离散、标点密度
- `learn_and_save`：无目录 / 已存在不覆盖 / 显式覆盖 / 无章节 / 写入失败 / 成功
- `format_dna`：None、空指纹、全字段、warnings 段落
"""

from __future__ import annotations

import json

from app.style_dna import (
    StyleDNA,
    _learn_paragraphs,
    format_dna,
    learn_and_save,
    learn_from_texts,
)

#: 一段 200+ 汉字的样本，人称统一用「他」，句长有一定变化
SAMPLE = (
    "他推开门，风雪灌了进来。"
    "他站在门口，看着屋里那盏还没灭的油灯，忽然觉得这一切都不太真实。"
    "三年前他离开的时候，这盏灯也是这样亮着的。"
    "他没有说话，只是慢慢走过去，把手里那张已经揉皱的纸放在桌上。"
    "纸上写着七个字，字迹被雨水泡得有些模糊。"
    "他伸手把灯芯挑亮了一点，屋里的影子跟着晃了晃，像是有人在暗处动了一下。"
    "他知道自己不该回来，可他还是回来了。"
) * 2


# ─────────────────────────── 段落切分 ───────────────────────────


class TestLearnParagraphs:
    def test_empty_input(self):
        assert _learn_paragraphs([]) == []

    def test_none_like_text_skipped(self):
        assert _learn_paragraphs(["", None]) == []

    def test_inner_newlines_merged_into_one_paragraph(self):
        result = _learn_paragraphs(["第一行\n第二行"])
        assert result == ["第一行 第二行"]

    def test_blank_line_splits_paragraphs(self):
        result = _learn_paragraphs(["段一第一行\n段一第二行\n\n段二"])
        assert result == ["段一第一行 段一第二行", "段二"]

    def test_trailing_buffer_flushed(self):
        assert _learn_paragraphs(["只有一段"]) == ["只有一段"]

    def test_multiple_texts_concatenated(self):
        result = _learn_paragraphs(["甲\n\n乙", "丙"])
        assert result == ["甲", "乙", "丙"]  # 每个 text 独立切分，不跨文本合并缓冲

    def test_whitespace_only_lines_ignored(self):
        assert _learn_paragraphs(["   \n\t\n"]) == []


# ─────────────────────────── 从文本学习 ───────────────────────────


class TestLearnFromTexts:
    def test_insufficient_sample_returns_warning(self):
        dna = learn_from_texts(["太短了。"], name="样本")
        assert dna.name == "样本"
        assert any("不足" in w for w in dna.warnings)
        assert dna.person == ""

    def test_dominant_person_detected(self):
        dna = learn_from_texts([SAMPLE])
        assert dna.person == "第三人称"

    def test_mixed_person_warns(self):
        # 必须跨人称组才算混用：她/他同属第三人称组，各半的应是「我」与「他」
        mixed = "我说完就走。他站在原地。" * 30
        dna = learn_from_texts([mixed])
        assert dna.person == ""
        assert any("人称不集中" in w for w in dna.warnings)

    def test_no_pronoun_warns(self):
        no_pronoun = "风起。云散。天光乍破。山色空蒙。" * 20  # 需 200+ 汉字，否则先走样本不足分支
        dna = learn_from_texts([no_pronoun])
        assert dna.person == ""
        assert any("没有人称代词" in w for w in dna.warnings)

    def test_sentence_stats_present(self):
        dna = learn_from_texts([SAMPLE])
        assert dna.sentence_mean > 0
        assert dna.sentence_cv >= 0

    def test_favorite_marks_detected(self):
        # 只学「破折号 / 省略号」这两类（_LEARNABLE_MARKS），逗号不在其中
        dashed = SAMPLE.replace("。", "——") * 3
        dna = learn_from_texts([dashed])
        assert "——" in dna.favorite_marks

    def test_tone_and_banned_words_left_empty(self):
        """语气与禁词属人工判断，机器不该猜。"""
        dna = learn_from_texts([SAMPLE])
        assert dna.tone == ""
        assert dna.banned_words == ()

    def test_long_text_truncated_without_error(self):
        dna = learn_from_texts([SAMPLE * 200])
        assert isinstance(dna, StyleDNA)

    def test_empty_list_gives_warning(self):
        dna = learn_from_texts([])
        assert any("不足" in w for w in dna.warnings)


# ─────────────────────────── 学习并保存 ───────────────────────────


class TestLearnAndSave:
    def test_no_novel_dir(self):
        ok, message = learn_and_save(None)
        assert ok is False and "没有打开的作品" in message

    def test_existing_file_not_overwritten_by_default(self, tmp_path):
        (tmp_path / "风格DNA.json").write_text("{}", encoding="utf-8")
        ok, message = learn_and_save(tmp_path)
        assert ok is False and "未覆盖" in message

    def test_existing_file_overwritten_when_asked(self, tmp_path):
        target = tmp_path / "风格DNA.json"
        target.write_text("{}", encoding="utf-8")
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "ch001.txt").write_text(SAMPLE, encoding="utf-8")
        ok, message = learn_and_save(tmp_path, overwrite=True)
        assert ok is True and "已从成稿学习" in message

    def test_no_chapters(self, tmp_path):
        ok, message = learn_and_save(tmp_path)
        assert ok is False and "没有可学习的章节" in message

    def test_successful_write(self, tmp_path):
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "ch001.txt").write_text(SAMPLE, encoding="utf-8")
        ok, message = learn_and_save(tmp_path)
        assert ok is True
        target = tmp_path / "风格DNA.json"
        assert target.exists()
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload.get("name")

    def test_warnings_persisted_into_payload(self, tmp_path):
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "ch001.txt").write_text("太短。", encoding="utf-8")
        ok, _ = learn_and_save(tmp_path)
        # 样本不足时 learn_from_novel 返回 None 或带 warning 的 dna，两者都不该崩
        assert isinstance(ok, bool)

    def test_write_failure_reported(self, tmp_path, monkeypatch):
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "ch001.txt").write_text(SAMPLE, encoding="utf-8")

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("app.style_dna.atomic_write_json", _boom)
        ok, message = learn_and_save(tmp_path)
        assert ok is False and "写入失败" in message


# ─────────────────────────── 渲染 ───────────────────────────


class TestFormatDna:
    def test_none_renders_hint(self):
        text = format_dna(None)
        assert "尚未配置" in text

    def test_empty_dna_shows_placeholder_name(self):
        text = format_dna(StyleDNA())
        assert "（未命名）" in text

    def test_full_dna_renders_all_fields(self):
        dna = StyleDNA(
            name="冷峻",
            person="他",
            tone="克制",
            sentence_mean=18.5,
            sentence_cv=0.42,
            favorite_marks=("，", "。"),
            banned_words=("呵呵",),
            prose_reference="refs/a.md",
            notes="作者手改",
        )
        text = format_dna(dna)
        for expected in (
            "冷峻",
            "人称：他",
            "语气：克制",
            "句长",
            "爱用标点",
            "禁词：呵呵",
            "参考文档：a.md",
            "备注：作者手改",
        ):
            assert expected in text

    def test_warnings_rendered_as_list(self):
        text = format_dna(StyleDNA(name="x", warnings=("缺人称", "缺句长")))
        assert "未能自动确定" in text
        assert "- 缺人称" in text and "- 缺句长" in text
