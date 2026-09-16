"""用量面板测试（v3 §3.5(5)）。

面板本身是 Tk 控件，但**逻辑部分**（概览文本、成本单元格、各子页的行渲染、
余额能力文案）都是纯函数或只依赖 `Treeview` 的两三个方法，因此本文件用
一个假 Tree 覆盖它们 —— 不创建真实 Tk 根窗口（CI 无显示环境）。

同时固化两条"诚实原则"的源码级断言：
- 未定价必须显示「无价目」，不能显示成 ¥0.0000（会被读成免费）
- provider 没有余额接口时要说清原因，不能报错或留空
"""

import sys
import tkinter as tk
from pathlib import Path

import pytest

from app.providers.balance import BALANCE_PROBES, capability_text
from app.usage_tracker import UsageTracker, usage_context
from app.usage_ui import (
    TASK_LABELS,
    UsagePanelMixin,
    format_cost_cell,
    summarize_rows,
)

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


class FakeTree:
    """只实现面板用到的三个方法（`get_children` / `delete` / `insert`）。"""

    def __init__(self):
        self.rows = []

    def get_children(self):
        return list(range(len(self.rows)))

    def delete(self, *_items):
        self.rows.clear()

    def insert(self, _parent, _index, values=None, **_kw):
        self.rows.append(tuple(values))
        return f"item-{len(self.rows)}"

    # --- 断言辅助
    def column(self, index):
        return [row[index] for row in self.rows]

    def find_row(self, index, value):
        for row in self.rows:
            if row[index] == value:
                return row
        return None


class DummyPanel(UsagePanelMixin):
    """不带 Tk 的面板宿主：只提供面板逻辑需要的最小上下文。"""

    def __init__(self):
        self.logs = []

    def _log(self, message):
        self.logs.append(message)


@pytest.fixture
def panel():
    return DummyPanel()


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    """把全局单例临时指向 tmp_path，避免碰到真实用户数据。"""
    from app import usage_tracker as module

    fresh = UsageTracker()
    fresh.set_novel_dir(tmp_path)
    monkeypatch.setattr(module, "usage_tracker", fresh)
    monkeypatch.setattr("app.usage_ui.usage_tracker", fresh)
    return fresh


# ==================================================================== 纯函数


class TestSummarizeRows:
    def test_empty_summary(self):
        text = summarize_rows({"totals": {}})
        assert "0" in text

    def test_measured_and_estimated_split(self):
        summary = {"totals": {
            "calls": 3, "total_tokens": 1200, "estimated_calls": 1,
            "errors": 0, "costs": {"CNY": 0.5},
        }}
        text = summarize_rows(summary)
        assert "1.2K" in text
        assert "实测 2 次 / 估算 1 次" in text
        assert "¥0.5000" in text

    def test_errors_shown(self):
        summary = {"totals": {"calls": 2, "total_tokens": 10, "errors": 1}}
        assert "失败 1 次" in summarize_rows(summary)

    def test_without_estimation_shows_call_count(self):
        summary = {"totals": {"calls": 4, "total_tokens": 10, "estimated_calls": 0}}
        assert "4 次调用" in summarize_rows(summary)


class TestFormatCostCell:
    def test_unpriced_is_named_not_zero(self):
        """未定价绝不能显示 ¥0.0000 —— 那会被读成"免费"。"""
        assert format_cost_cell({}) == "无价目"
        assert format_cost_cell({"costs": {}}) == "无价目"

    def test_priced_zero_is_shown_as_zero(self):
        """真·免费（本地模型）与"没有价目"是两回事，必须能分开。"""
        assert format_cost_cell({"costs": {"CNY": 0.0}}) == "¥0.0000"

    def test_priced_value(self):
        assert format_cost_cell({"costs": {"CNY": 0.0123}}) == "¥0.0123"

    def test_multiple_currencies(self):
        text = format_cost_cell({"costs": {"CNY": 0.5, "USD": 0.25}})
        assert "¥0.5000" in text and "$0.2500" in text


class TestBalanceCapabilityText:
    def test_supported(self):
        assert "支持余额查询" in capability_text("deepseek")

    def test_known_unsupported_explains_why(self):
        text = capability_text("openai")
        assert text.startswith("❌")
        assert "session key" in text

    def test_unknown_provider_is_question_not_error(self):
        text = capability_text("some-new-provider")
        assert text.startswith("❓")

    def test_local_model(self):
        assert "无计费" in capability_text("ollama")

    def test_probe_table_only_lists_verified(self):
        """只收录已核实的：kimi 端点未逐字确认，故必须标为未配置。"""
        assert BALANCE_PROBES["deepseek"].configured is True
        assert BALANCE_PROBES["kimi"].configured is False


# ==================================================================== 行渲染


class TestChapterRows:
    def test_renders_estimated_split(self, panel, tracker):
        with usage_context(chapter=1):
            tracker.record(provider="deepseek", model="deepseek-v4-flash",
                           prompt_tokens=1000, completion_tokens=500, latency_ms=2000)
        with usage_context(chapter=1):
            tracker.record(provider="deepseek", model="deepseek-v4-flash",
                           prompt_tokens=10, completion_tokens=5,
                           estimated=True, latency_ms=1000)

        tree = FakeTree()
        panel._fill_chapters(tree, tracker.chapter_rows())
        row = tree.rows[0]
        assert row[0] == 1
        assert row[1] == 2                        # 调用数
        assert row[5] == "1 / 1 ≈"                # 实测/估算
        assert row[6] == "3.0"                    # 耗时秒
        assert row[7].startswith("¥")

    def test_empty(self, panel):
        tree = FakeTree()
        panel._fill_chapters(tree, [])
        assert tree.rows == []


class TestProviderRows:
    def test_includes_balance_capability(self, panel, tracker):
        tracker.record(provider="deepseek", model="deepseek-v4-flash", prompt_tokens=10)
        tracker.record(provider="openai", model="gpt-4o", prompt_tokens=10)

        tree = FakeTree()
        panel._fill_provider(tree, tracker.summary()["by_provider"])
        deepseek = tree.find_row(0, "deepseek")
        openai = tree.find_row(0, "openai")
        assert "支持余额查询" in deepseek[6]
        assert openai[6].startswith("❌")

    def test_sorted_by_name(self, panel, tracker):
        for provider in ("glm", "deepseek", "openai"):
            tracker.record(provider=provider, model="x", prompt_tokens=1)
        tree = FakeTree()
        panel._fill_provider(tree, tracker.summary()["by_provider"])
        assert tree.column(0) == ["deepseek", "glm", "openai"]


class TestTaskRows:
    def test_uses_chinese_labels_and_share(self, panel, tracker):
        with usage_context(task="chapter"):
            tracker.record(provider="glm", model="glm-5.3", prompt_tokens=300)
        with usage_context(task="outline"):
            tracker.record(provider="glm", model="glm-5.3", prompt_tokens=100)

        summary = tracker.summary()
        tree = FakeTree()
        panel._fill_task(tree, summary["by_task"], summary["totals"]["total_tokens"])

        assert tree.column(0)[0] == TASK_LABELS["chapter"] == "正文"
        assert tree.column(3)[0] == "75.0%"
        assert tree.column(3)[1] == "25.0%"

    def test_largest_first(self, panel, tracker):
        with usage_context(task="chapter"):
            tracker.record(provider="glm", model="glm-5.3", prompt_tokens=10)
        with usage_context(task="review"):
            tracker.record(provider="glm", model="glm-5.3", prompt_tokens=999)
        summary = tracker.summary()
        tree = FakeTree()
        panel._fill_task(tree, summary["by_task"], 1009)
        assert tree.column(0)[0] == "审校"

    def test_zero_total_does_not_divide_by_zero(self, panel, tracker):
        with usage_context(task="chapter"):
            tracker.record(provider="glm", model="glm-5.3")
        summary = tracker.summary()
        tree = FakeTree()
        panel._fill_task(tree, summary["by_task"], 0)
        assert tree.rows[0][3] == "—"


class TestModelAndPriceRows:
    def test_model_rows(self, panel, tracker):
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=100,
                       completion_tokens=100, latency_ms=500)
        tree = FakeTree()
        panel._fill_model(tree, tracker.summary()["by_model"])
        assert tree.rows[0][0] == "glm-5.3"
        assert tree.rows[0][2] == "200"
        assert tree.rows[0][3] == "0.5"

    def test_price_table_shows_provenance(self, panel):
        """价目表必须带来源/置信度/查证日期 —— 价格会变，用户要能自己判断。"""
        tree = FakeTree()
        panel._fill_prices(tree)
        headers = ("deepseek", "glm", "qwen", "claude", "ollama")
        assert any(row[0] in headers for row in tree.rows)
        seen_providers = {row[0] for row in tree.rows}
        assert {"deepseek", "claude", "qwen"} <= seen_providers
        # 置信度列必须有值，且低置信度会被标出来
        assert all(row[7] for row in tree.rows)
        assert any(row[7] != "official" for row in tree.rows)

    def test_tiered_price_is_annotated(self, panel):
        tree = FakeTree()
        panel._fill_prices(tree)
        qwen_rows = [row for row in tree.rows if row[0] == "qwen"]
        assert any("阶梯" in row[1] for row in qwen_rows)


# ==================================================================== 联动与源码守卫


class TestChapterTokenBadge:
    """章节列表里的 token 徽标（`outline_ui._token_badge`）。"""

    def test_no_record_renders_nothing(self):
        from app.outline_ui import _token_badge

        assert _token_badge(None) == ""
        assert _token_badge(0) == ""
        assert _token_badge("bad") == ""

    def test_record_renders_compact_form(self):
        from app.outline_ui import _token_badge

        assert _token_badge(1500) == "  · 1.5K"
        assert _token_badge(2_500_000) == "  · 2.5M"

    def test_badge_does_not_pollute_chapter_combobox(self):
        """徽标只能进列表项，不能进章号下拉框（否则跳章逻辑会被污染）。"""
        code = _scan.read("app/outline_ui.py")
        assert "chapters.append(f\"第{ch}章\")" in code


class TestIntegrationPoints:
    def test_bind_usage_novel_sets_tracker(self, panel, tmp_path):
        panel._bind_usage_novel(tmp_path)
        from app.usage_tracker import usage_tracker

        try:
            assert usage_tracker.novel_dir == tmp_path
        finally:
            usage_tracker.set_novel_dir(None)
            usage_tracker.reset_memory()

    def test_bind_usage_novel_swallows_errors(self, panel, monkeypatch):
        """统计目录切不过去也不能影响"打开小说"这条主流程。"""
        def boom(_dir):
            raise OSError("disk gone")

        monkeypatch.setattr("app.usage_ui.usage_tracker.set_novel_dir", boom)
        panel._bind_usage_novel("whatever")
        assert panel.logs and "失败" in panel.logs[0]

    def test_chapter_token_badges_returns_map(self, panel, tmp_path, monkeypatch):
        fresh = UsageTracker()
        fresh.set_novel_dir(tmp_path)
        with usage_context(chapter=7):
            fresh.record(provider="glm", model="glm-5.3", prompt_tokens=100)
        # 必须打到 `app.usage_ui` 里的引用（它 `from ... import usage_tracker`
        # 拿的是对象引用，改 `app.usage_tracker.usage_tracker` 影响不到它）
        monkeypatch.setattr("app.usage_ui.usage_tracker", fresh)
        assert panel._chapter_token_badges() == {7: 100}

    def test_status_text_is_short(self, panel, tmp_path, monkeypatch):
        fresh = UsageTracker()
        fresh.set_novel_dir(tmp_path)
        fresh.record(provider="glm", model="glm-5.3", prompt_tokens=100)
        monkeypatch.setattr("app.usage_ui.usage_tracker", fresh)
        assert "tokens" in panel._usage_status_text()

    def test_lifecycle_calls_bind_at_every_switch(self):
        """4 处 `current_novel_dir = ...` 之后都必须同步用量目录。"""
        code = _scan.read("app/lifecycle_ui.py")
        assignments = code.count("self.current_novel_dir = novel_dir")
        binds = code.count("self._bind_usage_novel(novel_dir)")
        assert assignments == 4
        assert binds == assignments

    def test_shell_registers_tab(self):
        code = _scan.read("app/shell_ui.py")
        assert "self._build_usage_tab(usage_frame)" in code
        assert 'text=" 用量统计 "' in code

    def test_status_bar_includes_usage(self):
        code = _scan.read("app/shell_ui.py")
        assert "_usage_status_text()" in code

    def test_outline_list_shows_badge(self):
        code = _scan.read("app/outline_ui.py")
        assert "def _token_badge" in code
        assert 'getattr(self, "_chapter_token_badges", None)' in code
        assert "_token_badge(badges.get(ch))" in code

    def test_app_inherits_mixin(self):
        code = _scan.read("novel_app.py")
        assert "from app.usage_ui import UsagePanelMixin" in code
        assert "UsagePanelMixin," in code

    def test_panel_has_no_character_delete_entry(self):
        """项目硬约束：任何新面板都不得提供删除角色名的入口。"""
        code = _scan.code_only("app/usage_ui.py")
        for forbidden in ("delete_character", "remove_character", "unlink"):
            assert forbidden not in code


class TestTabStructure:
    def test_five_sub_tabs_and_column_headers(self):
        """面板必须覆盖 §3.5(5) 要求的维度，且列头不能被改动到丢信息。"""
        source = _scan.read("app/usage_ui.py")
        for header in ('"章号"', '"调用"', '"输入"', '"输出"', '"合计"',
                       '"实测/估算"', '"耗时(秒)"', '"成本"', '"余额能力"',
                       '"置信度"', '"查证日期"'):
            assert header in source

    def test_estimated_marker_documented(self):
        code = _scan.read("app/usage_ui.py")
        assert "≈" in code

    def test_export_uses_utf8_bom_for_excel(self):
        from app.usage_tracker import UsageTracker as Tracker

        source = _scan.read("app/usage_tracker.py")
        assert "utf-8-sig" in source
        assert Tracker.CSV_FIELDS[0] == "time"

    def test_tk_end_used_without_root(self):
        """`tk.END` 只是常量字符串，不创建 Tk 根 —— 保证无 GUI 环境也能导入。"""
        assert tk.END == "end"
