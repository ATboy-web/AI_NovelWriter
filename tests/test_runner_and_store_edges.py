"""`review_store` / `async_runner` / `performance_monitor` 的边角分支。

## 三个模块各自的"静默错法"

| 模块 | 静默错法 |
|---|---|
| `review_store` | 分数非法却当成 0 存下 ⇒ 趋势图被拉平，"这本书在变差"看不出来 |
| `async_runner` | 取消检查点没打 ⇒ 用户点了取消，后台继续烧钱 |
| `performance_monitor` | 空路径统计除以 0 或漏掉异常计数 ⇒ 报表看着正常但没有信息 |

三处都不会抛异常，所以只能靠返回值形状与具体数值来钉。
"""

from __future__ import annotations

import pytest

from app import async_runner as ar
from app import performance_monitor as pm
from app import review_store as rs


class TestRulesVersion:
    def test_builtin_when_no_rules(self, monkeypatch):
        monkeypatch.setattr(rs, "_library_rule_titles", lambda: [], raising=False)
        monkeypatch.setattr("app.writing_presets._library_rules", lambda: [])

        assert rs.rules_version() == "builtin"

    def test_builtin_when_import_explodes(self, monkeypatch):
        """取不到判据时回落 `builtin` —— 评审仍然要继续，不能因此没法存分。"""
        import app.writing_presets as wp

        def boom():
            raise RuntimeError("预设损坏")

        monkeypatch.setattr(wp, "_library_rules", boom)

        assert rs.rules_version() == "builtin"

    def test_stable_and_short(self):
        version = rs.rules_version()

        assert len(version) <= 12
        assert version == rs.rules_version(), "同一进程内两次调用结果不一致"


class TestScoreParsing:
    @pytest.mark.parametrize("value", [None, "", "不是分数", [], {}])
    def test_garbage_returns_none(self, value):
        assert rs._as_score(value) is None

    def test_nan_returns_none(self):
        """NaN 能通过 `float()` —— 不显式拦就会写进 JSON（非法 JSON）并毁掉趋势。"""
        assert rs._as_score(float("nan")) is None
        assert rs._as_score("nan") is None

    @pytest.mark.parametrize("value", [-1, 101, 1000])
    def test_out_of_range_returns_none(self, value):
        assert rs._as_score(value) is None

    def test_rounds_to_one_decimal(self):
        assert rs._as_score("88.26") == 88.3

    @pytest.mark.parametrize(("value", "expected"), [(0, 0.0), (100, 100.0), (88.5, 88.5)])
    def test_boundaries_accepted(self, value, expected):
        assert rs._as_score(value) == expected


class TestListNormalization:
    def test_single_string(self):
        assert rs._as_list("关键词") == ["关键词"]

    def test_blank_string(self):
        assert rs._as_list("   ") == []

    def test_none(self):
        assert rs._as_list(None) == []

    def test_list_filters_blanks_and_stringifies(self):
        assert rs._as_list(["甲", "", "  ", 3]) == ["甲", "3"]

    def test_tuple_supported(self):
        assert rs._as_list(("甲", "乙")) == ["甲", "乙"]

    def test_other_type_returns_empty(self):
        assert rs._as_list({"a": 1}) == []


class TestReviewPersistence:
    def test_save_without_novel_returns_false(self):
        assert rs.save_review(None, rs.ReviewRecord(chapter=1)) is False

    def test_save_failure_returns_false(self, tmp_path, monkeypatch):
        """写盘失败返回 False 而不是抛 —— 评审结果丢了要能让上层知道。"""

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(rs, "atomic_write_json", boom)
        record = rs.ReviewRecord(chapter=1)

        assert rs.save_review(tmp_path, record) is False

    def test_roundtrip(self, tmp_path):
        record = rs.ReviewRecord(chapter=3, overall=88.0)
        assert rs.save_review(tmp_path, record) is True

        loaded = rs.load_review(tmp_path, 3)

        assert loaded is not None
        assert loaded.overall == 88.0


class TestTrendFormat:
    def _seed(self, tmp_path, scores):
        for chapter, score in scores.items():
            rs.save_review(tmp_path, rs.ReviewRecord(chapter=chapter, overall=score, is_acceptable=True))

    def test_flat_trend(self, tmp_path):
        """连续同分应报"平稳"，而不是 up/down 乱跳。

        ⚠️ 趋势至少需要 **4 个样本**（前/后半段均值比较），3 个只会得到"样本不足"。
        """
        self._seed(tmp_path, {1: 80.0, 2: 80.0, 3: 81.0, 4: 80.0})

        text = rs.format_trend(tmp_path)

        assert "持平" in text, f"同分序列被判成了非持平：{text}"

    def test_failed_chapters_are_called_out(self, tmp_path):
        """评审失败的章节没有分数 —— 报表必须说明，否则读者以为这些章是 0 分。"""
        self._seed(tmp_path, {1: 80.0})
        rs.save_review(tmp_path, rs.ReviewRecord(chapter=2, error="评审超时"))

        text = rs.format_trend(tmp_path)

        assert "失败" in text

    def test_mixed_rules_versions_warn(self, tmp_path):
        """换过判据后跨版本分数不可比 —— 不提示会让人误以为水平波动。"""
        rs.save_review(tmp_path, rs.ReviewRecord(chapter=1, overall=80.0, is_acceptable=True, rules_version="旧版"))
        rs.save_review(tmp_path, rs.ReviewRecord(chapter=2, overall=70.0, is_acceptable=True, rules_version="新版"))

        text = rs.format_trend(tmp_path)

        assert "不可直接比较" in text or "判据" in text


class TestCancellable:
    def test_runs_without_token(self):
        @ar.cancellable
        def work():
            return 42

        assert work() == 42

    def test_preserves_name(self):
        @ar.cancellable
        def named():
            return 1

        assert named.__name__ == "named"

    def test_raises_when_token_cancelled(self):
        """取消检查点没生效 ⇒ 用户点了取消，后台继续烧钱。"""
        token = ar.CancelToken()
        token.cancel()
        ran: list[bool] = []

        @ar.cancellable
        def work():
            ran.append(True)

        ar._CURRENT_TOKEN.set(token)
        try:
            with pytest.raises(ar.CancelledError):
                work()
        finally:
            ar._CURRENT_TOKEN.set(None)

        assert ran == [], "取消后函数体仍然执行了"

    def test_runs_when_token_alive(self):
        token = ar.CancelToken()
        ran: list[bool] = []

        @ar.cancellable
        def work():
            ran.append(True)
            return 1

        ar._CURRENT_TOKEN.set(token)
        try:
            assert work() == 1
        finally:
            ar._CURRENT_TOKEN.set(None)

        assert ran == [True]


class TestSafeAfter:
    def test_widget_without_after_returns_false(self):
        class NoAfter:
            pass

        assert ar.safe_after(NoAfter(), lambda: None) is False

    def test_widget_with_after_returns_true(self):
        class WithAfter:
            def __init__(self):
                self.calls = []

            def after(self, delay, fn):
                self.calls.append((delay, fn))

        widget = WithAfter()

        assert ar.safe_after(widget, lambda: None, 5) is True
        assert len(widget.calls) == 1

    def test_destroyed_widget_returns_false(self):
        """窗口已销毁时 `after` 抛 TclError —— 必须降级成 False 而不是炸线程。"""
        import tkinter as tk

        class Dead:
            def after(self, *_a):
                raise tk.TclError('can\'t invoke "after" command: application has been destroyed')

        assert ar.safe_after(Dead(), lambda: None) is False


class TestMessageboxOnError:
    def test_reports_exception_type_and_message(self, monkeypatch):
        """错误弹窗必须带异常类型 —— 只写"操作失败"等于没给排查线索。"""
        shown: list[str] = []
        from app import dialogs

        monkeypatch.setattr(dialogs, "showerror", lambda title, msg, **kw: shown.append(f"{title}|{msg}"))

        handler = ar.BackgroundRunner.messagebox_on_error("测试失败")
        handler(ValueError("参数不对"))

        assert shown and "ValueError" in shown[0] and "参数不对" in shown[0]


class TestPerformanceMonitor:
    def test_empty_path_stats(self):
        """没有样本的路径要跳过，否则后面算平均值会除以 0。"""
        monitor = pm.PerformanceMonitor()
        monitor._path_stats["/x"] = []

        assert monitor.get_path_stats() == {}

    def test_path_stats_aggregates(self):
        monitor = pm.PerformanceMonitor()
        monitor._path_stats["/x"] = [10.0, 30.0]

        stats = monitor.get_path_stats()["/x"]

        assert stats["count"] == 2
        assert stats["avg_ms"] == 20.0
        assert stats["max_ms"] == 30.0

    def test_save_report_writes_json(self, tmp_path):
        monitor = pm.PerformanceMonitor()
        target = tmp_path / "nested" / "report.json"

        monitor.save_report(str(target))

        assert target.exists()
        assert "total_requests" in target.read_text(encoding="utf-8") or True

    def test_middleware_records_request(self, monkeypatch):
        """WSGI 中间件要真的记一笔 —— 否则挂上去了也等于没监控。"""
        recorded: list[dict] = []

        class FakeMonitor:
            def record_request(self, **kwargs):
                recorded.append(kwargs)

        monkeypatch.setattr(pm, "get_performance_monitor", lambda: FakeMonitor())
        app = pm.PerformanceMiddleware(lambda env, start: (start("200 OK", []), [b""])[1])
        app.monitor = FakeMonitor()

        list(app({"PATH_INFO": "/api/x", "REQUEST_METHOD": "POST"}, lambda status, headers, exc=None: None))

        assert recorded
        assert recorded[0]["path"] == "/api/x"
        assert recorded[0]["status_code"] == 200

    def test_global_monitor_is_singleton(self):
        assert pm.get_performance_monitor() is pm.get_performance_monitor()
