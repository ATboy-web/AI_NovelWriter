"""继承编排的领域层测试（假 writer，**不碰磁盘**）。

## 这组用例在守什么

`inherit_into_child` 最关键的行为不是"复制成功"，而是**失败时怎么办**：

- 计划里标了 missing ⇒ 不该去尝试复制（省无谓 IO，也避免误报）
- 复制抛 `ValueError`（护栏拒绝）⇒ 记 missing 并**继续下一个**，绝不绕过护栏重试
- 单个维度失败不能中断整批（否则用户点了"创建续集"只会得到半套数据）

这些以前只能靠"造父代目录 + 权限异常"来间接验证，现在用假 writer 直接喂。
"""

from __future__ import annotations

import pytest

from app.domain.lineage import (
    DIMENSION_SOURCES,
    InheritancePlan,
    build_inheritance,
    render_plot_report,
)


class FakeWriter:
    """记录调用；可指定"复制失败"或"护栏拒绝"的路径。"""

    def __init__(self, *, failing: set[str] | None = None, rejecting: set[str] | None = None):
        self.failing = set(failing or ())
        self.rejecting = set(rejecting or ())
        self.copies: list[str] = []
        self.writes: list[tuple[str, str]] = []

    def copy(self, parent_dir: str, child_dir: str, relative: str) -> bool:
        self.copies.append(relative)
        if relative in self.rejecting:
            raise ValueError(f"护栏拒绝：{relative}")
        return relative not in self.failing

    def write_text(self, child_dir: str, relative: str, content: str) -> bool:
        self.writes.append((relative, content))
        return True


def _plan(
    *,
    dimensions: dict[str, bool] | None = None,
    copies: dict[str, list[str]] | None = None,
    missing: dict[str, list[str]] | None = None,
) -> InheritancePlan:
    """造一个计划：默认全维度勾选、全部可复制。"""
    inherited = {dim: True for dim in DIMENSION_SOURCES}
    if dimensions:
        inherited.update(dimensions)
    plan = InheritancePlan(parent_dir="/p", inherited=inherited)
    for dim in DIMENSION_SOURCES:
        plan.items[dim] = {
            "copy": list((copies or {}).get(dim, DIMENSION_SOURCES[dim])),
            "missing": list((missing or {}).get(dim, [])),
            "skipped": not inherited[dim],
        }
    return plan


class TestBuildInheritance:
    def test_all_sources_copied(self):
        writer = FakeWriter()
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c")
        assert result["missing"] == []
        expected = {rel for rels in DIMENSION_SOURCES.values() for rel in rels}
        assert set(result["copied"]) == expected

    def test_copy_returning_false_lands_in_missing(self):
        target = DIMENSION_SOURCES["outline"][0]
        writer = FakeWriter(failing={target})
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c")
        assert target in result["missing"]
        assert target not in result["copied"]

    def test_guard_rejection_is_recorded_not_retried(self):
        """护栏拒绝 ⇒ 记 missing，且**只尝试一次**（不许绕过护栏重试）。"""
        target = DIMENSION_SOURCES["characters"][0]
        writer = FakeWriter(rejecting={target})
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c")
        assert target in result["missing"]
        assert writer.copies.count(target) == 1, "护栏拒绝后出现了重试 —— 绝不允许"

    def test_one_failure_does_not_abort_the_batch(self):
        failing = DIMENSION_SOURCES["outline"][0]
        writer = FakeWriter(failing={failing})
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c")
        assert len(result["copied"]) > 1, "单个维度失败就中断了整批"
        assert failing in result["missing"]

    def test_planned_missing_is_not_attempted(self):
        target = DIMENSION_SOURCES["settings"][0]
        plan = _plan(copies={"settings": []}, missing={"settings": [target]})
        writer = FakeWriter()
        result = build_inheritance(plan, writer, parent_dir="/p", child_dir="/c")
        assert target in result["missing"]
        assert target not in writer.copies, "计划里已判定缺失，不该再去试"

    def test_skipped_dimension_not_touched(self):
        plan = _plan(dimensions={"timeline": False})
        writer = FakeWriter()
        build_inheritance(plan, writer, parent_dir="/p", child_dir="/c")
        for rel in DIMENSION_SOURCES["timeline"]:
            assert rel not in writer.copies, "未勾选的维度被复制了"

    def test_duplicates_deduped_keeping_order(self):
        """`memory` 与 `plots` 都含 `memory/global_summary.txt`。"""
        result = build_inheritance(_plan(), FakeWriter(), parent_dir="/p", child_dir="/c")
        assert result["copied"] == list(dict.fromkeys(result["copied"]))

    def test_plots_written_when_enabled(self):
        writer = FakeWriter()
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c", plots_content="- [ ] 伏笔A\n")
        assert result["plots_file"] == "inherited_plots.md"
        assert writer.writes and "伏笔A" in writer.writes[0][1]

    def test_plots_skipped_when_content_empty(self):
        writer = FakeWriter()
        result = build_inheritance(_plan(), writer, parent_dir="/p", child_dir="/c", plots_content="")
        assert result["plots_file"] is None
        assert writer.writes == []

    def test_plots_skipped_when_dimension_unchecked(self):
        writer = FakeWriter()
        result = build_inheritance(
            _plan(dimensions={"plots": False}),
            writer,
            parent_dir="/p",
            child_dir="/c",
            plots_content="- [ ] x\n",
        )
        assert result["plots_file"] is None

    def test_plots_write_failure_does_not_raise(self):
        class BadWriter(FakeWriter):
            def write_text(self, child_dir, relative, content):
                raise OSError("disk full")

        result = build_inheritance(_plan(), BadWriter(), parent_dir="/p", child_dir="/c", plots_content="- [ ] x\n")
        assert result["plots_file"] is None
        assert result["copied"], "伏笔写失败不该影响其他维度的复制结果"

    def test_custom_plots_filename(self):
        result = build_inheritance(
            _plan(),
            FakeWriter(),
            parent_dir="/p",
            child_dir="/c",
            plots_content="- [ ] x\n",
            plots_filename="todo.md",
        )
        assert result["plots_file"] == "todo.md"


class TestRenderPlotReport:
    def test_empty_items(self):
        assert render_plot_report([]) == ""

    def test_renders_markdown_checklist(self):
        text = render_plot_report(["伏笔A", "伏笔B"])
        assert text.startswith("# 前代未回收伏笔")
        assert "- [ ] 伏笔A" in text and "- [ ] 伏笔B" in text
        assert text.endswith("\n")

    def test_generator_input(self):
        assert "- [ ] x" in render_plot_report(item for item in ["x"])

    @pytest.mark.parametrize("items", [[""], ["  "], ["a", ""]])
    def test_blank_items_are_not_dropped_silently(self, items):
        """空项也照样输出 —— 上游 `extract_unresolved_plots` 已过滤，这里不二次判断。"""
        text = render_plot_report(items)
        assert text.count("- [ ]") == len(items)
