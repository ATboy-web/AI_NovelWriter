"""语义层候选抽取测试（对应建议 4：补齐技能包的 `--candidates` 等价能力）。

抽取本身是**启发式**，所以测试分两类：

- **必须命中**：构造明确的样例，证明各类候选真的能被抽出来（否则等于没实现）；
- **必须不命中**：构造容易误报的样例，证明判据没有放宽到"见词就算"。

后者比前者重要 —— 候选误报会让用户去改本来正确的文字。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.semantic_candidates import (
    COHESION_THRESHOLD,
    JUDGE_LABELS,
    JUDGE_LABELS_VALUES,
    JUDGE_RULES,
    extract_candidates,
    format_candidates,
    load_candidates,
    semantic_summary,
    split_paragraphs,
    split_sentences,
    write_candidates,
)

NL = chr(10)


def _paras(*items: str) -> str:
    return (NL + NL).join(items)


# ====================================================================== 切分


class TestSplit:
    def test_paragraphs_by_blank_line(self):
        text = _paras("第一段。", "第二段。", "第三段。")
        assert split_paragraphs(text) == ["第一段。", "第二段。", "第三段。"]

    def test_single_newline_is_same_paragraph(self):
        text = "第一行" + NL + "第二行" + NL + NL + "新段"
        assert split_paragraphs(text) == ["第一行 第二行", "新段"]

    def test_blank_text(self):
        assert split_paragraphs("") == []
        assert split_paragraphs(None) == []

    def test_sentences(self):
        assert split_sentences("他说。她走了！为什么？") == ["他说", "她走了", "为什么"]

    def test_short_fragment_dropped(self):
        """过短的碎片（如"好。"）不算句子，避免把签名统计带偏。"""
        assert split_sentences("好。这句话足够长了。") == ["这句话足够长了"]


# ====================================================================== 同义重命名


class TestRename:
    def test_same_family_multiword_is_hit(self):
        text = "这个方案能提升效率、提高产出，并增强稳定性。"
        found = extract_candidates(text).get("rename")
        assert found, "同族三词并存必须抽出来"
        families = {f["family"] for f in found[0]["families"]}
        assert "提升" in families

    def test_cross_family_single_word_is_miss(self):
        """🔴 曾经的误报：`方案` 与 `问题` 各一次被当成重命名。

        它们是两个不同概念，读者不需要做「X 就是 Y」的连接 —— 必须不命中。
        """
        text = "这个方案有问题，问题在于成本太高，方案还得改。"
        assert extract_candidates(text).get("rename") == []

    def test_single_family_single_word_is_miss(self):
        text = "我们要提升效率。"
        assert extract_candidates(text).get("rename") == []

    def test_two_families_each_multiword_is_hit(self):
        text = "先优化流程、改进方法，再提升效率、提高产出。"
        found = extract_candidates(text).get("rename")
        assert found
        families = {f["family"] for f in found[0]["families"]}
        assert {"优化", "提升"} <= families

    def test_carries_paragraph_index(self):
        text = _paras("第一段无关内容。", "这个方案能提升效率、提高产出、增强稳定性。")
        found = extract_candidates(text).get("rename")
        assert found[0]["paragraph"] == 2


# ====================================================================== 衔接连环


class TestCohesion:
    def test_long_chain_is_hit(self):
        ops = ["这也解释了为什么", "这也意味着", "这正是", "从这个角度", "换句话说", "也就是说", "因此", "所以"]
        paras = ["开头独立内容。"] + [f"{op}第{i}点需要展开说明，因为前面交代过背景。" for i, op in enumerate(ops, 1)]
        found = extract_candidates(_paras(*paras)).get("cohesion")
        assert found
        assert found[0]["length"] >= COHESION_THRESHOLD

    def test_short_chain_is_miss(self):
        paras = ["开头。", "因此第一点成立。", "所以第二点也成立。", "独立的新话题。"]
        assert extract_candidates(_paras(*paras)).get("cohesion") == []

    def test_all_streaks_recorded_for_summary(self):
        """分布要收**全部**连环：只数 ≥6 的候选会让"最长连环"永远显示 0。"""
        paras = ["开头。", "因此第一点。", "所以第二点。", "独立段。"]
        candidates = extract_candidates(_paras(*paras))
        assert candidates.extra["max_chain"] == 2
        assert candidates.get("cohesion") == []

    def test_meaning_this_means_detected(self):
        """实测漏过：`这意味着` 不在旧表里，导致 AI 文最典型的承接被判漏。"""
        paras = ["开头。"] + [f"这意味着第{i}点要重排优先级，因为前提变了。" for i in range(1, 8)]
        candidates = extract_candidates(_paras(*paras))
        assert candidates.extra["max_chain"] >= COHESION_THRESHOLD


# ====================================================================== 结论冒号


class TestColon:
    def test_short_prefix_is_candidate(self):
        text = "一句话总结：先做小的。"
        found = extract_candidates(text).get("colon_judge")
        assert found and found[0]["prefix"] == "一句话总结"

    def test_long_prefix_is_miss(self):
        """冒号前太长就不像"提示语"，是正常长句里的冒号。"""
        text = "当他走进那个堆满旧书和灰尘的房间并环顾四周的时候，他注意到一件事：桌上有一封信。"
        assert extract_candidates(text).get("colon_judge") == []

    def test_quote_colon_is_still_candidate_for_model(self):
        """引语冒号也进候选 —— 但要不要改由模型按判据判，脚本不预设。"""
        text = "她留下的最后一句话是：就这样吧。"
        found = extract_candidates(text).get("colon_judge")
        assert found
        assert found[0]["label"] == ""  # 留给模型判


# ====================================================================== 句法同构


class TestIsomorphic:
    def test_triple_is_hit(self):
        text = "叫什么名字？承载什么功能？嵌入哪个生态？"
        candidates = extract_candidates(text)
        assert candidates.get("iso3"), "连续三句同骨架必须抽出三连"

    def test_pair_without_triple(self):
        text = "服务网络能不能覆盖到老家？车的残值经不经得起检验？" + "然后是一段完全不同长度而且带逗号，说明别的事情。"
        candidates = extract_candidates(text)
        assert candidates.get("iso_pair")
        assert candidates.get("iso3") == []

    def test_different_lengths_are_miss(self):
        """长度差得多就不是"高度同构"，宽口径排比没有区分力。"""
        text = "短句问？这是一个明显长得多而且结构完全不同的句子吗？"
        assert extract_candidates(text).get("iso_pair") == []


# ====================================================================== 汇总与读写


class TestSummary:
    def test_basis_is_candidates_before_judging(self):
        candidates = extract_candidates("一句话总结：先做小的。")
        summary = semantic_summary(candidates)
        assert summary["basis"] == "candidates"
        assert summary["judged"] == 0

    def test_basis_is_judged_after_labeling(self):
        candidates = extract_candidates("一句话总结：先做小的。")
        for item in candidates.get("colon_judge"):
            item["label"] = "hit"
        summary = semantic_summary(candidates)
        assert summary["basis"] == "judged"
        assert summary["colon_hits"] == 1

    def test_miss_does_not_count_as_hit(self):
        candidates = extract_candidates("一句话总结：先做小的。")
        for item in candidates.get("colon_judge"):
            item["label"] = "miss"
            item["reason"] = "这是标题不是结论提示"
        summary = semantic_summary(candidates)
        assert summary["colon_hits"] == 0
        # 阴性判读也要被记录（用于对账原始候选 → 有效命中）
        assert candidates.judged == 1

    def test_rename_per_paragraph(self):
        text = _paras("这个方案能提升效率、提高产出。", "第二段。", "第三段。")
        summary = semantic_summary(extract_candidates(text))
        assert summary["rename_count"] == 1
        assert summary["rename_per_paragraph"] == pytest.approx(1 / 3, rel=0.05)


class TestIO:
    def test_roundtrip(self, tmp_path: Path):
        candidates = extract_candidates("一句话总结：先做小的。" + NL + NL + "第二段也这样。")
        for item in candidates.get("colon_judge"):
            item["label"] = "hit"
            item["reason"] = "结论提示"
        path = tmp_path / "cand.json"
        ok, _ = write_candidates(candidates, path)
        assert ok

        loaded = load_candidates(path)
        assert loaded is not None
        assert loaded.total == candidates.total
        assert loaded.judged == candidates.judged

    def test_json_has_judge_rules(self, tmp_path: Path):
        candidates = extract_candidates("一句话总结：先做小的。")
        path = tmp_path / "cand.json"
        write_candidates(candidates, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # 判读纪律必须随候选一起交付，否则"判据"只存在于技能包的 md 里
        assert data["judge_rules"] == list(JUDGE_RULES)
        assert data["allowed_labels"] == list(JUDGE_LABELS_VALUES)

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_candidates(tmp_path / "nope.json") is None

    def test_load_broken_returns_none(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{oops", encoding="utf-8")
        assert load_candidates(path) is None


class TestFormat:
    def test_lists_all_kinds(self):
        text = _paras(
            "这个方案能提升效率、提高产出。",
            "一句话总结：先做小的。",
        )
        rendered = format_candidates(extract_candidates(text))
        for label in JUDGE_LABELS.values():
            assert label in rendered

    def test_states_basis_explicitly(self):
        rendered = format_candidates(extract_candidates("一句话总结：先做小的。"))
        assert "尚未判读" in rendered

    def test_mentions_discipline(self):
        rendered = format_candidates(extract_candidates("一句话总结：先做小的。"))
        assert "禁止自造标签" in rendered


# ====================================================================== 边界


class TestEdgeCases:
    def test_empty_text(self):
        candidates = extract_candidates("")
        assert candidates.total == 0
        assert candidates.paragraphs == 0

    def test_no_crash_on_weird_input(self):
        assert extract_candidates("。。。、、、！！！").total == 0

    def test_judge_labels_closed_set(self):
        assert set(JUDGE_LABELS_VALUES) == {"hit", "miss", "unsure"}

    def test_max_per_kind_applied(self):
        from app.semantic_candidates import MAX_PER_KIND

        text = NL * 2
        text = (NL + NL).join(["一句话总结：先做小的。"] * (MAX_PER_KIND + 20))
        candidates = extract_candidates(text)
        assert len(candidates.get("colon_judge")) <= MAX_PER_KIND

    def test_candidates_have_empty_label_slots(self):
        candidates = extract_candidates("一句话总结：先做小的。")
        for items in candidates.items.values():
            for item in items:
                assert "label" in item and item["label"] == ""
                assert "reason" in item


# ====================================================================== 与预设接线


class TestPresetWiring:
    def test_qc_report_carries_candidates(self):
        from app.writing_presets import PRESETS, qc_report

        text = ("一句话总结：先做小的。" + "正文内容继续写下去。" * 20) * 3
        report = qc_report(text, PRESETS["deai-full"])
        assert report["candidates"] is not None
        assert report["candidate_items"] is not None
        assert report["candidates"]["total"] >= 1

    def test_can_disable_candidates(self):
        from app.writing_presets import PRESETS, qc_report

        text = ("一句话总结：先做小的。" + "正文内容继续写下去。" * 20) * 3
        report = qc_report(text, PRESETS["deai-full"], with_candidates=False)
        assert report["candidates"] is None

    def test_rewrite_instruction_includes_candidates(self):
        from app.writing_presets import PRESETS, build_rewrite_instruction, qc_report

        text = ("一句话总结：先做小的。" + "正文内容继续写下去。" * 20) * 3
        report = qc_report(text, PRESETS["deai-full"])
        instruction = build_rewrite_instruction(report, PRESETS["deai-full"])
        assert "待判读候选" in instruction
        assert "hit / miss / unsure" in instruction
        assert "永不改" in instruction
