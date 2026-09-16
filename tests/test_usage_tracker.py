"""用量追踪测试（v3 §3.5）。

覆盖四组关键行为：

1. **归因** —— `contextvars` 生效、退出必还原、`task_tracker` 装饰器不破坏签名
2. **持久化** —— JSONL 追加 + summary 聚合 + 重启后可重建 + 单行损坏不毁全文件
3. **成本** —— 币种分离、未定价不伪装成 0、估算值带标记
4. **线程** —— 经 `async_runner` 派发的线程能继承归因上下文（这是最容易错的一处）
"""

import json
import sys
import threading
from pathlib import Path

import pytest

from app.async_runner import BackgroundRunner
from app.usage_tracker import (
    SUMMARY_VERSION,
    UsageTracker,
    clear_usage_context,
    current_usage_context,
    new_bucket,
    reset_usage_context,
    set_usage_context,
    task_tracker,
    usage_context,
    usage_tracker,
)

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def tracker():
    """独立实例，避免污染全局单例（全局单例由专门的用例测）。"""
    return UsageTracker()


@pytest.fixture(autouse=True)
def _clean_context():
    """每个用例前后都把上下文清干净 —— 否则用例之间会串归因。"""
    clear_usage_context()
    yield
    clear_usage_context()


# ==================================================================== 归因


class TestUsageContext:
    def test_empty_by_default(self):
        assert current_usage_context() == {}

    def test_set_and_read(self):
        set_usage_context(chapter=7, task="chapter")
        assert current_usage_context()["chapter"] == 7
        assert current_usage_context()["task"] == "chapter"

    def test_none_values_are_ignored(self):
        set_usage_context(chapter=None, task="chapter")
        assert "chapter" not in current_usage_context()

    def test_nested_merge(self):
        with usage_context(chapter=3):
            with usage_context(task="biography"):
                ctx = current_usage_context()
                assert ctx["chapter"] == 3
                assert ctx["task"] == "biography"

    def test_context_restored_on_exit(self):
        with usage_context(chapter=9):
            assert current_usage_context()["chapter"] == 9
        assert "chapter" not in current_usage_context()

    def test_context_restored_on_exception(self):
        with pytest.raises(RuntimeError):
            with usage_context(task="outline"):
                raise RuntimeError("boom")
        assert "task" not in current_usage_context()

    def test_reset_with_stale_token_is_safe(self):
        token = set_usage_context(chapter=1)
        reset_usage_context(token)
        reset_usage_context(token)          # 二次重置不得抛异常

    def test_context_is_copy_not_reference(self):
        set_usage_context(chapter=1)
        snapshot = current_usage_context()
        snapshot["chapter"] = 999
        assert current_usage_context()["chapter"] == 1


class TestTaskTrackerDecorator:
    def test_wraps_and_attributes(self):
        @task_tracker("review", chapter_param="chapter_num")
        def review(chapter_num, content):
            return current_usage_context()

        ctx = review(5, "正文")
        assert ctx["task"] == "review"
        assert ctx["chapter"] == 5

    def test_keyword_chapter(self):
        @task_tracker("chapter", chapter_param="chapter_num")
        def generate(chapter_num=1):
            return current_usage_context()

        assert generate(chapter_num=12)["chapter"] == 12

    def test_missing_chapter_param_is_omitted(self):
        @task_tracker("characters")
        def generate_characters(genre):
            return current_usage_context()

        ctx = generate_characters("玄幻")
        assert ctx["task"] == "characters"
        assert "chapter" not in ctx

    def test_signature_and_metadata_preserved(self):
        """装饰器只加一行、方法体不动，对外可观察面（名字/文档/签名）必须不变。"""
        import inspect

        @task_tracker("outline")
        def generate_outline(self, genre, title, chapter_count, concept=""):
            """原文档字符串"""
            return 1

        assert generate_outline.__name__ == "generate_outline"
        assert generate_outline.__doc__ == "原文档字符串"
        assert list(inspect.signature(generate_outline).parameters) == [
            "self", "genre", "title", "chapter_count", "concept",
        ]

    def test_context_restored_after_call(self):
        @task_tracker("review", chapter_param="chapter_num")
        def review(chapter_num):
            return None

        review(3)
        assert "task" not in current_usage_context()

    def test_does_not_invent_unknown_param(self):
        @task_tracker("review", chapter_param="nope")
        def review(chapter_num):
            return current_usage_context()

        assert "chapter" not in review(4)

    def test_exception_still_resets(self):
        @task_tracker("review", chapter_param="chapter_num")
        def boom(chapter_num):
            raise ValueError("x")

        with pytest.raises(ValueError):
            boom(2)
        assert "task" not in current_usage_context()

    def test_applied_to_novel_agent_methods(self):
        code = _scan.code_only("app/novel_agent.py")
        for marker in ('@task_tracker("chapter"', '@task_tracker("outline")',
                       '@task_tracker("review"', '@task_tracker("characters")'):
            assert marker in code


# ==================================================================== 记录与聚合


class TestRecordAndSummary:
    def test_memory_only_without_novel_dir(self, tracker):
        record = tracker.record(provider="deepseek", model="deepseek-v4-flash",
                                prompt_tokens=100, completion_tokens=50)
        assert record["total_tokens"] == 150
        assert tracker.summary()["totals"]["calls"] == 1

    def test_writes_jsonl_and_summary(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="deepseek", model="deepseek-v4-flash",
                       prompt_tokens=1000, completion_tokens=500)

        detail = tmp_path / "usage" / "usage.jsonl"
        summary = tmp_path / "usage" / "summary.json"
        assert detail.exists() and summary.exists()

        lines = [line for line in detail.read_text(encoding="utf-8").splitlines() if line]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["prompt_tokens"] == 1000
        assert payload["provider"] == "deepseek"

        saved = json.loads(summary.read_text(encoding="utf-8"))
        assert saved["version"] == SUMMARY_VERSION
        assert saved["totals"]["total_tokens"] == 1500

    def test_jsonl_is_append_only(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        for i in range(3):
            tracker.record(provider="glm", model="glm-5.3",
                           prompt_tokens=10, completion_tokens=i)
        detail = tmp_path / "usage" / "usage.jsonl"
        assert len(detail.read_text(encoding="utf-8").strip().splitlines()) == 3

    def test_attribution_from_context(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        with usage_context(chapter=42, task="chapter"):
            record = tracker.record(provider="glm", model="glm-5.3",
                                    prompt_tokens=10, completion_tokens=5)
        assert record["chapter"] == 42
        assert record["task"] == "chapter"
        assert tracker.chapter_rows()[0]["chapter"] == 42

    def test_explicit_args_win_over_context(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        with usage_context(chapter=1, task="chapter"):
            record = tracker.record(provider="glm", model="glm-5.3", chapter=99)
        assert record["chapter"] == 99

    def test_groupings(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        with usage_context(chapter=1, task="chapter"):
            tracker.record(provider="deepseek", model="deepseek-v4-flash",
                           prompt_tokens=100, completion_tokens=50)
        with usage_context(chapter=2, task="outline"):
            tracker.record(provider="glm", model="glm-5.3",
                           prompt_tokens=200, completion_tokens=100)

        summary = tracker.summary()
        assert set(summary["by_chapter"]) == {"1", "2"}
        assert set(summary["by_provider"]) == {"deepseek", "glm"}
        assert set(summary["by_task"]) == {"chapter", "outline"}
        assert summary["totals"]["total_tokens"] == 450

    def test_chapter_tokens_map(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        with usage_context(chapter=3):
            tracker.record(provider="glm", model="glm-5.3",
                           prompt_tokens=10, completion_tokens=20)
        assert tracker.chapter_tokens() == {3: 30}

    def test_chapter_rows_sorted_numerically(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        for chapter in (10, 2, 1):
            with usage_context(chapter=chapter):
                tracker.record(provider="glm", model="glm-5.3", prompt_tokens=1)
        assert [row["chapter"] for row in tracker.chapter_rows()] == [1, 2, 10]

    def test_estimated_calls_counted(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=10,
                       completion_tokens=5, estimated=True)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=10,
                       completion_tokens=5)
        assert tracker.summary()["totals"]["estimated_calls"] == 1

    def test_errors_counted(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=1, ok=False)
        assert tracker.summary()["totals"]["errors"] == 1

    def test_latency_accumulated(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=1, latency_ms=1200)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=1, latency_ms=800)
        assert tracker.summary()["totals"]["latency_ms"] == pytest.approx(2000.0)


class TestPersistence:
    def test_survives_restart_by_rebuild_from_detail(self, tracker, tmp_path):
        """summary.json 丢失时**必须**能从 usage.jsonl 重建，而不是显示空聚合。"""
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="deepseek", model="deepseek-v4-flash",
                       prompt_tokens=100, completion_tokens=100)
        (tmp_path / "usage" / "summary.json").unlink()

        fresh = UsageTracker()
        fresh.set_novel_dir(tmp_path)
        assert fresh.summary()["totals"]["total_tokens"] == 200

    def test_corrupt_summary_triggers_rebuild(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="deepseek", model="deepseek-v4-flash", prompt_tokens=5)
        (tmp_path / "usage" / "summary.json").write_text("{not json", encoding="utf-8")

        fresh = UsageTracker()
        fresh.set_novel_dir(tmp_path)
        assert fresh.summary()["totals"]["calls"] == 1

    def test_unknown_summary_version_triggers_rebuild(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="deepseek", model="deepseek-v4-flash", prompt_tokens=5)
        (tmp_path / "usage" / "summary.json").write_text(
            json.dumps({"version": 0, "totals": new_bucket()}), encoding="utf-8"
        )
        fresh = UsageTracker()
        fresh.set_novel_dir(tmp_path)
        assert fresh.summary()["totals"]["calls"] == 1

    def test_one_corrupt_line_does_not_kill_the_file(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=7)
        detail = tmp_path / "usage" / "usage.jsonl"
        with open(detail, "a", encoding="utf-8") as handle:
            handle.write("{oops not json\n")
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=7)

        records = tracker.read_records()
        assert len(records) == 2

    def test_switching_novel_does_not_mix_aggregates(self, tracker, tmp_path):
        book_a = tmp_path / "a"
        book_b = tmp_path / "b"
        tracker.set_novel_dir(book_a)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=100)
        tracker.set_novel_dir(book_b)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=1)

        assert tracker.summary()["totals"]["total_tokens"] == 1
        assert tracker.summary(book_a)["totals"]["total_tokens"] == 100

    def test_read_records_limit_returns_tail(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        for i in range(5):
            tracker.record(provider="glm", model="glm-5.3", prompt_tokens=i + 1)
        tail = tracker.read_records(limit=2)
        assert [r["prompt_tokens"] for r in tail] == [4, 5]

    def test_export_csv(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="glm", model="glm-5.3", prompt_tokens=10,
                       completion_tokens=5)
        out = tracker.export_csv(tmp_path / "out" / "usage.csv")
        text = out.read_text(encoding="utf-8-sig")
        assert "prompt_tokens" in text.splitlines()[0]
        assert "glm-5.3" in text


class TestCosts:
    def test_currency_separation(self, tracker, tmp_path):
        """CNY 与 USD 绝不相加（§9.9 第 3 条）。"""
        tracker.set_novel_dir(tmp_path)
        tracker.record(provider="deepseek", model="deepseek-v4-flash",
                       prompt_tokens=1_000_000, completion_tokens=0)
        tracker.record(provider="groq", model="openai/gpt-oss-120b",
                       prompt_tokens=1_000_000, completion_tokens=0)
        costs = tracker.summary()["totals"]["costs"]
        assert set(costs) == {"CNY", "USD"}

    def test_known_price_produces_cost(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        record = tracker.record(provider="deepseek", model="deepseek-v4-flash",
                                prompt_tokens=1_000_000, completion_tokens=0)
        assert record["cost_currency"] == "CNY"
        assert record["cost"] == pytest.approx(1.0)

    def test_unknown_model_is_zero_and_unpriced(self, tracker, tmp_path):
        """未定价必须留下 `cost_currency=""` 的空标记，UI 才不会显示成 ¥0。"""
        tracker.set_novel_dir(tmp_path)
        record = tracker.record(provider="nope", model="whatever",
                                prompt_tokens=1000, completion_tokens=1000)
        assert record["cost"] == 0.0
        assert record["cost_currency"] == ""
        assert record["cost_reliable"] is False

    def test_estimated_usage_marks_cost_unreliable(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        record = tracker.record(provider="deepseek", model="deepseek-v4-flash",
                                prompt_tokens=1000, estimated=True)
        assert record["cost_reliable"] is False

    def test_free_local_model_is_zero_but_priced(self, tracker, tmp_path):
        tracker.set_novel_dir(tmp_path)
        record = tracker.record(provider="ollama", model="qwen2.5:14b",
                                prompt_tokens=1000, completion_tokens=1000)
        assert record["cost"] == 0.0
        assert record["cost_currency"] == "CNY"

    def test_pricing_failure_does_not_break_recording(self, tracker, tmp_path, monkeypatch):
        """价目表炸了也必须把用量记下来 —— 用量比成本重要。"""
        import app.providers.pricing as pricing

        def boom(*_a, **_k):
            raise RuntimeError("pricing exploded")

        monkeypatch.setattr(pricing, "estimate_cost", boom)
        tracker.set_novel_dir(tmp_path)
        record = tracker.record(provider="glm", model="glm-5.3", prompt_tokens=10)
        assert record["prompt_tokens"] == 10
        assert record["cost"] == 0.0

    def test_format_costs(self):
        assert UsageTracker.format_costs({}) == "—"
        assert UsageTracker.format_costs({"CNY": 0.5}) == "¥0.5000"
        assert "¥0.5000" in UsageTracker.format_costs({"CNY": 0.5, "USD": 0.1})
        assert "$0.1000" in UsageTracker.format_costs({"CNY": 0.5, "USD": 0.1})


# ==================================================================== 线程


class TestThreadPropagation:
    def test_plain_thread_loses_context(self):
        """先固化"裸线程不继承上下文"这个事实 —— 它是本模块设计的动因。"""
        seen = {}

        def work():
            seen.update(current_usage_context())

        with usage_context(chapter=8):
            thread = threading.Thread(target=work)
            thread.start()
            thread.join()
        assert "chapter" not in seen

    def test_background_runner_preserves_context(self):
        """经 BackgroundRunner 派发的线程**必须**继承归因（§3.5(1) 的关键）。"""
        seen = {}

        def work():
            seen.update(current_usage_context())

        with usage_context(chapter=8, task="chapter"):
            runner = BackgroundRunner()
            thread = runner.submit(work)
            thread.join()
        assert seen["chapter"] == 8
        assert seen["task"] == "chapter"

    def test_report_step(self):
        """真实报告动因：装饰器 + BackgroundRunner 组合能拿到章号。"""
        captured = {}

        @task_tracker("chapter", chapter_param="chapter_num")
        def generate(chapter_num):
            runner = BackgroundRunner()
            runner.submit(lambda: captured.update(current_usage_context())).join()

        generate(15)
        assert captured["chapter"] == 15


class TestGlobalSingleton:
    def test_is_usage_tracker(self):
        assert isinstance(usage_tracker, UsageTracker)

    def test_reset_memory_keeps_disk(self, tmp_path):
        usage_tracker.reset_memory()
        try:
            usage_tracker.set_novel_dir(tmp_path)
            usage_tracker.record(provider="glm", model="glm-5.3", prompt_tokens=3)
            assert (tmp_path / "usage" / "usage.jsonl").exists()
            usage_tracker.reset_memory()
            assert (tmp_path / "usage" / "usage.jsonl").exists()
        finally:
            usage_tracker.set_novel_dir(None)
            usage_tracker.reset_memory()
