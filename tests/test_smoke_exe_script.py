"""`scripts/smoke_exe.py` 自身的守卫（**不启动任何 EXE**）。

## 为什么要测一个测试脚本

冒烟脚本的价值全在判据上。如果判据写错，它会给出"全绿"的假结论 ——
比没有冒烟更危险（会让人以为验证过了）。

所以这里只测**判据函数**与**探针的失败模式**，绝不依赖真实产物：

- 有 EXE 时：跑一次真冒烟（`pytest -m exe` 手动触发，不进默认全量；
  一次要 30s+ 且依赖桌面环境，放进每次全量会让 CI 又慢又不稳）
- 无 EXE 时：跳过，但判据单测照跑

## 几条反证（缺了它们，本文件就是空转）

- `windows_of_pid` 对一个不存在的 pid 必须返回空 —— 否则"读到标题"毫无意义
- `check_title` 必须拒绝没有版本号的标题 —— 否则版本号忘了同步也发现不了
- `read_panel_registry_event` 对空目录必须返回 None 且**不卡死**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import smoke_exe  # noqa: E402


class TestExpectedFromSource:
    def test_returns_positive_numbers(self):
        panels, categories = smoke_exe.expected_from_source()
        assert panels > 0 and categories > 0

    def test_matches_registry_directly(self):
        """与直接查询注册表必须一致 —— 防止本函数自己算错。"""
        from app.panels.registry import PANEL_REGISTRY, load_panels
        from app.panels.registry import categories as _categories

        load_panels()
        panels, categories = smoke_exe.expected_from_source()
        assert panels == len(PANEL_REGISTRY)
        assert categories == len(_categories())

    def test_is_not_hardcoded(self):
        """源码里的期望值不能是写死的常量。

        如果哪天有人把 `expected_from_source` 改成 `return 20, 5`，
        那它就不再能发现"面板少了一个" —— 这条用例就是防这个的。
        """
        source = (_REPO / "scripts" / "smoke_exe.py").read_text(encoding="utf-8")
        body = source.split("def expected_from_source", 1)[1].split("\ndef ", 1)[0]
        assert "PANEL_REGISTRY" in body, "期望值不是从注册表现算的"


class TestWindowProbe:
    def test_nonexistent_pid_returns_empty(self):
        """反证：探针读不到东西时必须返回空，而不是返回任意窗口。"""
        assert smoke_exe.windows_of_pid(999_999_999) == []

    def test_returns_list_type(self):
        assert isinstance(smoke_exe.windows_of_pid(0), list)


class TestCheckTitle:
    def test_rejects_empty(self):
        result = smoke_exe.check_title([])
        assert result.ok is False
        assert "没有读到" in result.detail

    def test_rejects_unrelated_window(self):
        result = smoke_exe.check_title(["记事本", "计算器"])
        assert result.ok is False
        assert "AI小说创作工坊" in result.detail

    def test_accepts_title_with_version(self):
        result = smoke_exe.check_title(["AI小说创作工坊 v3.2.5"])
        assert result.ok is True
        assert "v3.2.5" in result.detail

    def test_rejects_title_without_version(self):
        """版本号忘了同步时，标题里就没有 `vX.Y` —— 必须报出来。"""
        result = smoke_exe.check_title(["AI小说创作工坊"])
        assert result.ok is False
        assert "版本号" in result.detail

    def test_picks_the_product_window_among_others(self):
        result = smoke_exe.check_title(["某个对话框", "AI小说创作工坊 v3.0.0", "工具提示"])
        assert result.ok is True


class TestCheckPanels:
    def _event(self, total=20, cats=5, failures=None):
        return {
            "total": total,
            "by_category": {f"分组{i}": [] for i in range(cats)},
            "native": ["a"] * total,
            "legacy": [],
            "load_failures": failures or [],
        }

    def test_all_good(self):
        checks = smoke_exe.check_panels(self._event(), 20, 5)
        assert all(c.ok for c in checks)

    def test_missing_event_fails(self):
        checks = smoke_exe.check_panels(None, 20, 5)
        assert len(checks) == 1 and checks[0].ok is False

    def test_panel_count_mismatch_detected(self):
        checks = smoke_exe.check_panels(self._event(total=19), 20, 5)
        failed = [c for c in checks if not c.ok]
        assert failed and "19" in failed[0].detail

    def test_category_mismatch_detected(self):
        checks = smoke_exe.check_panels(self._event(cats=4), 20, 5)
        failed = [c for c in checks if not c.ok]
        assert failed and "分组" in failed[0].name

    def test_load_failures_detected(self):
        """`load_failures` 非空 = 有面板模块导不进来（界面少了几块）。"""
        checks = smoke_exe.check_panels(self._event(failures=["app.panels.outline_panel"]), 20, 5)
        failed = [c for c in checks if not c.ok]
        assert failed and "导入失败" in failed[0].name
        assert "outline_panel" in failed[0].detail


class TestReadPanelRegistryEvent:
    def test_empty_dir_returns_none_without_hanging(self, tmp_path):
        """空目录必须返回 None，且不能把等待时间耗光（默认 10s 会拖慢测试）。"""
        import time

        start = time.time()
        assert smoke_exe.read_panel_registry_event(tmp_path, timeout=0.5) is None
        assert time.time() - start < 3, "空目录等待过久 —— 超时参数没生效"

    def test_reads_last_event(self, tmp_path):
        log = tmp_path / "diag.jsonl"
        log.write_text(
            '{"topic":"SYSTEM","event":"panel_registry","data":{"total":19}}\n'
            '{"topic":"SYSTEM","event":"panel_registry","data":{"total":20}}\n',
            encoding="utf-8",
        )
        event = smoke_exe.read_panel_registry_event(tmp_path, timeout=1)
        assert event == {"total": 20}, "应当取**最后**一条（重启后旧记录还留在文件里）"

    def test_ignores_unrelated_lines(self, tmp_path):
        log = tmp_path / "diag.jsonl"
        log.write_text(
            '{"topic":"AI","event":"chat","data":{"total":1}}\n'
            "这行不是 JSON\n"
            '{"topic":"SYSTEM","event":"panel_registry","data":{"total":20}}\n',
            encoding="utf-8",
        )
        assert smoke_exe.read_panel_registry_event(tmp_path, timeout=1) == {"total": 20}


class TestMainExitCodes:
    def test_missing_exe_returns_2(self, tmp_path):
        code = smoke_exe.main(["--exe", str(tmp_path / "不存在.exe")])
        assert code == 2


@pytest.mark.skipif(
    not (_REPO / "AI_NovelWriter.exe").exists(),
    reason="没有打包产物，跳过真冒烟（只在有 EXE 的机器上跑）",
)
class TestRealSmoke:
    """有产物时跑一次真冒烟。`-m exe` 可单独触发。"""

    @pytest.mark.exe
    def test_smoke_passes(self):
        code = smoke_exe.main([])
        assert code == 0, "冒烟未通过 —— 看上面的逐条判据"


class TestConfirmDialogProbe:
    """退出确认框探针（`shell_ui._on_close` → `askyesno("确认", ...)`）。

    这三个函数是给"自动点掉防误关确认框"用的。它们的失败模式是
    **静默返回空/False**（拿不到句柄就什么也不做），所以必须有反证。
    """

    def test_nonexistent_pids_yield_no_dialogs(self):
        assert smoke_exe.confirm_dialog_handles([999_999_999]) == []

    def test_empty_pid_list(self):
        assert smoke_exe.confirm_dialog_handles([]) == []

    def test_child_buttons_of_bogus_handle_is_empty(self):
        assert smoke_exe._child_buttons(0) == []

    def test_click_yes_on_bogus_handle_returns_false(self):
        """拿不到按钮时必须返回 False，不能假装点成功了。"""
        assert smoke_exe.click_yes(0) is False

    def test_markers_cover_chinese_and_english(self):
        """中文系统按钮是「是(Y)」，英文是「&Yes」—— 两边都要认。"""
        assert any("是" in m for m in smoke_exe.YES_BUTTON_MARKERS)
        assert any("Yes" in m for m in smoke_exe.YES_BUTTON_MARKERS)

    def test_confirm_markers_match_the_real_dialog_title(self):
        """对话框标题必须能被识别 —— 它来自 `dialogs.askyesno("确认", ...)`。"""
        source = (_REPO / "app" / "shell_ui.py").read_text(encoding="utf-8")
        assert 'askyesno("确认"' in source, "退出确认框的标题变了，探针会认不出来"
        assert "确认" in smoke_exe.CONFIRM_DIALOG_MARKERS


class TestReportNotes:
    def test_notes_do_not_affect_ok(self):
        """观察项不能影响结论 —— 否则"没发请求所以没有性能报告"会误判失败。"""
        report = smoke_exe.SmokeReport()
        report.add("某判据", True)
        report.note("某观察项")
        assert report.ok is True

    def test_empty_report_is_not_ok(self):
        """一条判据都没跑 = 不该判通过（防止"什么都没检查就绿"）。"""
        assert smoke_exe.SmokeReport().ok is False
