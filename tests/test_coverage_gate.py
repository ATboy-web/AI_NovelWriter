"""覆盖率阈值门禁的自检测试。

## 为什么门禁本身也要测

一个"永远不会失败"的门禁比没有门禁更糟：它制造了"覆盖率有保障"的错觉。
本项目已确立的做法是 **反证法** —— 故意把判据推到会失败的区间，确认它真的红，
再恢复。这些测试就是那条反证过程的固化版本。

## 阈值只在 pyproject.toml 定义一处

`tests/` 里**不得**再写一遍数字，否则「同一事实写两处必然漂移」会在此重现。
本测试验证的是：脚本能从 pyproject 读到阈值，并且**读到的值和 CI 用的是同一个**。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_coverage.py"


def _load_gate_module():
    """按路径加载 `scripts/check_coverage.py`（它不是包的一部分）。"""
    spec = importlib.util.spec_from_file_location("_check_coverage_for_test", SCRIPT)
    assert spec and spec.loader, "无法加载 scripts/check_coverage.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_coverage_for_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gate():
    return _load_gate_module()


def _write_report(tmp_path: Path, percent: float) -> Path:
    """造一份最小可用的覆盖率 JSON 报告（字段与 coverage json 一致）。"""
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "percent_covered": percent,
                    "num_statements": 100,
                    "missing_lines": int(100 - percent),
                    "covered_lines": int(percent),
                    "has_errors": False,
                },
                "files": {
                    "app/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 30}},
                },
            }
        ),
        encoding="utf-8",
    )
    return report


# --------------------------------------------------------------------------
# 1. 配置本身
# --------------------------------------------------------------------------


def test_pyproject_declares_a_threshold(gate):
    """`[tool.coverage.report] fail_under` 必须存在 —— 否则门禁无法判定。"""
    threshold = gate.read_threshold()
    assert threshold is not None, "pyproject.toml 里没有 fail_under，覆盖率门禁形同虚设"
    assert 0 < threshold < 100


def test_threshold_is_not_a_rubber_stamp(gate):
    """阈值不能低到毫无意义。

    低于 50% 时，本项目大量"核心模块覆盖率都在 80%+"的事实说明
    这个门禁放行了真实的严重退步。
    """
    assert gate.read_threshold() >= 50, "覆盖率阈值过低，几乎不可能拦截任何退步"


def test_ci_reads_threshold_from_pyproject_not_hardcoded():
    """CI 不得自己写一个数字 —— 必须调用本脚本（阈值唯一来源原则）。

    这条守卫的意义：一旦有人在 workflow 里塞回 `--cov-fail-under=NN`，
    阈值就有了两个真相源，必然漂移（本项目已踩过三次）。
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/check_coverage.py" in ci, "CI 没有调用覆盖率门禁脚本"

    # `--cov-fail-under` 会绕过 pyproject，制造第二个真相源
    assert "--cov-fail-under" not in ci, (
        "CI 使用 --cov-fail-under 会绕过 pyproject.toml 的 fail_under，"
        "导致阈值有两个来源（必然漂移）。请改用 scripts/check_coverage.py。"
    )


def test_ci_generates_the_json_report(gate):
    """门禁读的是 JSON 报告 —— CI 必须真的生成它，否则门禁必然报错退出。"""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--cov-report=json" in ci, "CI 没有生成 JSON 覆盖率报告，check_coverage.py 会因找不到文件而失败"


# --------------------------------------------------------------------------
# 2. 判定逻辑（正反两个方向）
# --------------------------------------------------------------------------


def test_passes_when_above_threshold_within_margin(gate, tmp_path, monkeypatch):
    """实测略高于阈值（在 ratchet 余量内）⇒ 通过。"""
    threshold = gate.read_threshold()
    monkeypatch.setattr(gate, "read_threshold", lambda: threshold)
    rc = gate.main(["--report", str(_write_report(tmp_path, threshold + 0.5))])
    assert rc == 0


def test_fails_when_below_threshold(gate, tmp_path, monkeypatch):
    """反证：实测低于阈值 ⇒ 必须 exit 1。"""
    threshold = gate.read_threshold()
    monkeypatch.setattr(gate, "read_threshold", lambda: threshold)
    rc = gate.main(["--report", str(_write_report(tmp_path, threshold - 0.1))])
    assert rc == 1, "覆盖率低于阈值却没有失败 —— 这就是一个橡皮图章门禁"


def test_fails_when_far_above_threshold_ratchet(gate, tmp_path, monkeypatch):
    """反证（反向）：实测远超阈值 ⇒ 也必须 exit 1，提示收紧。

    这条是本轮的设计要点：门禁必须**双向**。只防下滑的门禁，
    在覆盖率真实上涨后会永久失效（阈值不动 = 放行任意退步）。
    """
    threshold = gate.read_threshold()
    monkeypatch.setattr(gate, "read_threshold", lambda: threshold)
    rc = gate.main(["--report", str(_write_report(tmp_path, threshold + gate.RATCHET_MARGIN + 5))])
    assert rc == 1, "覆盖率大涨但阈值没跟上，门禁已退化成橡皮图章，应当失败并提示收紧"


def test_no_ratchet_flag_relaxes_the_upper_bound(gate, tmp_path, monkeypatch):
    """`--no-ratchet` 只关掉"涨了要收紧"，不关掉"跌了要拦"。"""
    threshold = gate.read_threshold()
    monkeypatch.setattr(gate, "read_threshold", lambda: threshold)

    # 远超阈值 + --no-ratchet ⇒ 放行
    rc_high = gate.main(
        ["--report", str(_write_report(tmp_path, 99.0)), "--no-ratchet"],
    )
    assert rc_high == 0

    # 低于阈值 + --no-ratchet ⇒ 仍然拦
    rc_low = gate.main(
        ["--report", str(_write_report(tmp_path, 1.0)), "--no-ratchet"],
    )
    assert rc_low == 1, "--no-ratchet 不应关掉下限判定"


# --------------------------------------------------------------------------
# 3. 异常路径（缺失/损坏输入必须明确报错，不能静默通过）
# --------------------------------------------------------------------------


def test_missing_report_is_an_error_not_a_pass(gate, tmp_path, monkeypatch):
    """报告文件不存在 ⇒ exit 2（配置/环境错误），**绝不能是 0**。"""
    monkeypatch.setattr(gate, "read_threshold", lambda: 50.0)
    rc = gate.main(["--report", str(tmp_path / "nope.json")])
    assert rc == 2, "报告缺失却返回 0 —— 门禁会在 CI 无声失效"


def test_missing_threshold_is_an_error(gate, tmp_path, monkeypatch):
    """pyproject 里没有 fail_under ⇒ exit 2，而不是默默放行。"""
    monkeypatch.setattr(gate, "read_threshold", lambda: None)
    rc = gate.main(["--report", str(_write_report(tmp_path, 80.0))])
    assert rc == 2


def test_empty_totals_is_an_error(gate, tmp_path, monkeypatch):
    """报告缺 totals 字段 ⇒ 明确失败（SystemExit），不得当成 0% 或 100%。"""
    monkeypatch.setattr(gate, "read_threshold", lambda: 50.0)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"files": {}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        gate.main(["--report", str(bad)])


# --------------------------------------------------------------------------
# 4. `--update` 写回（阈值收紧的自动化路径）
# --------------------------------------------------------------------------


def test_update_writes_back_and_restores(gate, tmp_path, monkeypatch):
    """`--update` 能把值写回 pyproject.toml，且我们随后能还原。

    ⚠️ 这条测试**会真的改 pyproject.toml**，因此必须保证还原，
    并且断言还原成功 —— 否则测试跑一半失败会留下脏文件。
    """
    original_text = gate.PYPROJECT.read_text(encoding="utf-8")
    try:
        monkeypatch.setattr(gate, "read_threshold", lambda: 50.0)
        rc = gate.main(["--report", str(_write_report(tmp_path, 61.5)), "--update"])
        assert rc == 0
        # 写回后重新读（走真实解析路径，不用 monkeypatch）
        monkeypatch.undo()
        assert gate.read_threshold() == 61.5
    finally:
        gate.PYPROJECT.write_text(original_text, encoding="utf-8")

    assert gate.read_threshold() is not None, "还原失败：pyproject.toml 已损坏"
