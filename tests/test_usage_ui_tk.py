"""`usage_ui` 面板构建的测试（真实 Tk）。

## 为什么这里必须用真 Tk

`_build_usage_tab` 是**纯控件构建**：创建 StringVar、五个按钮、一个子 Notebook、
五张表。它的分支（哪张表用哪些列/宽度、按钮用什么颜色）只有真的建出控件才能验。
此前这 30 行一次都没跑过（79.6%）。

## 验什么

- 五个按钮都在、命令都接上了（点了会有反应，不是死按钮）
- 五张表的列定义与宽度与设计一致（列错位比崩溃更难发现）
- 两个 StringVar 的初始文案（"暂无用量记录" / "余额：未查询"）
- 强调色按钮用白字，普通按钮用正文色 —— 这是可读性问题，不是审美

## 关于 CI

本文件的类名含 `Tk`，会被 CI 的 `-k "not Tk"` 排除（CI 无显示环境）。
本地与桌面端仍会执行 —— 与仓库既有 Tk 测试的处理方式一致。
"""

from __future__ import annotations

import tkinter as tk

import _tk_harness
import pytest

from app import usage_ui
from app.usage_ui import UsagePanelMixin

pytestmark = pytest.mark.skipif(not _tk_harness.tk_available(), reason="无显示环境，跳过 Tk 控件测试")


class _Host(UsagePanelMixin):
    """够用的宿主：只提供 `_build_usage_tab` 真正会用到的两样东西。

    `_subscribe_usage_events` / `_refresh_usage_panel` 被替换成空操作 ——
    它们要读真实用量库与事件总线，与本文件要验的"控件摆对了没有"无关。
    """

    def __init__(self, root):
        self.root = root
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)

    def _subscribe_usage_events(self) -> None:  # noqa: D102 - 故意空实现
        self.subscribed = True

    def _refresh_usage_panel(self, *_) -> None:  # noqa: D102 - 故意空实现
        # 用计数器而不是布尔：按钮在构建时就绑定了**绑定方法**，
        # 事后替换实例属性改不动它 —— 只有方法体里的副作用能被观察到。
        self.refresh_count = getattr(self, "refresh_count", 0) + 1


@pytest.fixture
def tab():
    root = _tk_harness.create_root()
    frame = tk.Frame(root)
    frame.pack()
    host = _Host(root)
    try:
        host._build_usage_tab(frame)
        yield host, frame
    finally:
        try:
            root.destroy()
        except tk.TclError:  # pragma: no cover - 已销毁时忽略
            pass


class TestUsagePanelTkBuild:
    def _buttons(self, parent) -> list[tk.Button]:
        found: list[tk.Button] = []
        for child in parent.winfo_children():
            if isinstance(child, tk.Button):
                found.append(child)
            found.extend(self._buttons(child))
        return found

    def test_summary_and_hint_vars_start_with_placeholder(self, tab):
        """空面板不能一片空白 —— 首屏就要说明"还没有记录"。"""
        host, _frame = tab

        assert host.usage_summary_var.get() == "（暂无用量记录）"
        assert host.usage_hint_var.get() == ""

    def test_balance_starts_as_not_queried(self, tab):
        host, _frame = tab

        assert host.usage_balance_var.get() == "余额：未查询"

    def test_five_action_buttons_are_wired(self, tab):
        """五个按钮都要能点（`command` 非空）——死按钮比没有按钮更糟。"""
        host, frame = tab
        buttons = self._buttons(frame)

        labels = [b.cget("text") for b in buttons]
        for expected in ("🔄 刷新", "📤 导出 CSV", "💰 查询余额", "📂 打开目录", "📋 复制概览"):
            assert expected in labels, f"缺少按钮：{expected}"

        for button in buttons:
            assert button.cget("command"), f"按钮「{button.cget('text')}」没有绑定命令"

    def test_emphasis_buttons_use_white_foreground(self, tab):
        """强调色/成功色背景必须配白字 —— 否则对比度不足看不清。"""
        host, frame = tab
        by_label = {b.cget("text"): b for b in self._buttons(frame)}

        assert by_label["🔄 刷新"].cget("fg") in ("white", "#ffffff")
        assert by_label["💰 查询余额"].cget("fg") in ("white", "#ffffff")
        # 普通按钮用正文色（不是白）
        assert by_label["📤 导出 CSV"].cget("fg") != "white"

    def test_button_click_invokes_bound_command(self, tab):
        """点一下要真的调到对应方法 —— 绑定错对象是"看起来正常"的坏。"""
        host, frame = tab
        before = host.refresh_count  # 构建结束时已经刷过一次

        button = next(b for b in self._buttons(frame) if b.cget("text") == "🔄 刷新")
        button.invoke()

        assert host.refresh_count == before + 1, "按钮没有真的调到刷新方法"

    def test_five_sub_tables_exist(self, tab):
        """按章 / 按服务 / 按任务 / 按模型 / 价目表 —— 少一张就少一个视角。"""
        host, _frame = tab

        for attr in (
            "usage_chapter_tree",
            "usage_provider_tree",
            "usage_task_tree",
            "usage_model_tree",
            "usage_price_tree",
        ):
            tree = getattr(host, attr, None)
            assert tree is not None, f"缺少表格：{attr}"
            assert tree["columns"], f"{attr} 没有列定义"

    def test_chapter_table_columns(self, tab):
        """列名与顺序是"这行数字是什么"的唯一说明，错位比缺列更难发现。"""
        host, _frame = tab
        columns = host.usage_chapter_tree["columns"]

        assert tuple(columns) == ("章号", "调用", "输入", "输出", "合计", "实测/估算", "耗时(秒)", "成本")

    def test_price_table_has_confidence_column(self, tab):
        """价目表必须显示置信度与查证日期 —— 价格会变，用户要能自己判断。"""
        host, _frame = tab
        columns = tuple(host.usage_price_tree["columns"])

        assert "置信度" in columns
        assert "查证日期" in columns

    def test_build_subscribes_and_refreshes(self, tab):
        """建完面板要立刻订阅事件并拉一次数据，否则首屏永远是空的。"""
        host, _frame = tab

        assert getattr(host, "subscribed", False) is True
        assert host.refresh_count >= 1, "建完面板没有拉一次数据"


class TestUsageButtonTk:
    def test_button_defaults(self):
        """`_usage_button` 的默认形态：扁平、手型光标、左对齐排列。"""
        root = _tk_harness.create_root()
        frame = tk.Frame(root)
        host = _Host(root)
        try:
            button = host._usage_button(frame, "测试", lambda: None, usage_ui.UIStyle.COLORS["bg_light"])
            assert button.cget("relief") == "flat"
            assert button.cget("cursor") == "hand2"
            assert button.cget("text") == "测试"
        finally:
            root.destroy()
