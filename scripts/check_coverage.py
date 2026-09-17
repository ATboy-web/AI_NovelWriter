#!/usr/bin/env python3
"""覆盖率门禁：把「阈值判定」从 CI 的 shell 里搬进可测试的 Python 脚本。

## 为什么要单独一个脚本，而不是 `pyproject.toml` 里写 `fail_under`

本项目已经踩过三次「同一事实写两处必然漂移」。若阈值同时写在
`pyproject.toml`（给本地 `coverage report` 用）和 `.github/workflows/ci.yml`
（给 CI 用），两处迟早会不一致 —— 而覆盖率门禁一旦不一致，最坏情况是
**CI 说通过、本地说失败**，或反过来让门禁形同虚设。

因此：**`pyproject.toml` 的 `[tool.coverage.report] fail_under` 是唯一权威**，
本脚本与 CI 都从那里读，不各自硬编码。

## 为什么不用 `coverage report --fail-under=N`

两个原因，都是实测踩到的：

1. `coverage report`（7.16.1）**没有 `-q` 选项**。误加 `-q` 会得到
   `no such option: -q` 且退出码为 1 —— 看起来像"门禁失败"，
   实际是"命令根本没跑"。这种假信号比没有门禁更危险。
2. 光靠一个退出码，失败时看不到「差了多少、哪个文件拖累」。

本脚本改为：读 JSON 报告 → 与阈值比较 → 打印差值 → 明确 exit 1/0。

## 阈值是双向的

- **低于 `fail_under` ⇒ 失败**（防覆盖率下滑）；
- **高于 `fail_under + RATCHET_MARGIN` ⇒ 也失败**，提示上调阈值
  （防"真实覆盖率涨了但阈值没跟上"，那样门禁会慢慢变成橡皮图章）。
  可用 `--no-ratchet` 关闭，或 `--update` 直接把阈值写回 `pyproject.toml`。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console_utf8 import make_stdout_utf8_safe  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# 阈值上调的提示余量：真实值高出阈值超过这个数（百分点）就提醒收紧。
RATCHET_MARGIN = 2.0

# 这两个源文件是**故意留低**的：它们是 Tkinter 粘合层，但没被
# `[tool.coverage.run] omit` 排除（体积小、逻辑薄）。单独看它们会误判成"退步"。
# 这里不做特殊处理，只在下滑分析里作为参考信息打印。
_LOW_COVERAGE_HINTS = {"app/usage_ui.py", "app/panels/*"}


def read_threshold() -> float | None:
    """从 `pyproject.toml` 读 `[tool.coverage.report] fail_under`。

    用正则而不是 `tomllib`：本脚本要能在 **Python 3.11+ 任意小版本** 上跑，
    且不想因为 TOML 里出现本项目用不到的新语法就整体失败。
    读不到就返回 None（由调用方决定是警告还是失败）。
    """
    if not PYPROJECT.is_file():
        return None
    text = PYPROJECT.read_text(encoding="utf-8")
    # 定位到 [tool.coverage.report] 段落，避免误取别处的 fail_under
    section = re.search(
        r"^\[tool\.coverage\.report\](.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return None
    m = re.search(r"^\s*fail_under\s*=\s*([0-9.]+)", section.group(1), re.MULTILINE)
    return float(m.group(1)) if m else None


def write_threshold(value: float) -> bool:
    """把阈值写回 `pyproject.toml`（`--update` 用）。找不到段落则返回 False。"""
    text = PYPROJECT.read_text(encoding="utf-8")
    section = re.search(
        r"(^\[tool\.coverage\.report\](?:.*?)(?=^\[|\Z))",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return False
    body = section.group(1)
    if re.search(r"^\s*fail_under\s*=", body, re.MULTILINE):
        new_body = re.sub(
            r"^(\s*fail_under\s*=\s*)[0-9.]+",
            lambda m: f"{m.group(1)}{value:g}",
            body,
            flags=re.MULTILINE,
        )
    else:
        new_body = body.rstrip("\n") + f"\nfail_under = {value:g}\n"
    PYPROJECT.write_text(text.replace(body, new_body), encoding="utf-8")
    return True


def load_json_report(path: Path) -> dict:
    """读覆盖率 JSON 报告并返回 totals。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    totals = data.get("totals")
    if not totals:
        raise SystemExit(f"[coverage-gate] 报告缺少 totals 字段：{path}")
    return data


def format_low_files(data: dict, limit: int = 8) -> list[str]:
    """按「未覆盖语句数」降序，给出拖累总量的文件（最有行动价值）。"""
    rows: list[tuple[int, float, str]] = []
    for name, info in data.get("files", {}).items():
        summary = info.get("summary", {})
        missing = summary.get("missing_lines", 0)
        pct = summary.get("percent_covered", 100.0)
        if missing > 0:
            rows.append((missing, pct, name))
    rows.sort(reverse=True)
    return [f"    {missing:>5} 行未覆盖  {pct:5.1f}%  {name}" for missing, pct, name in rows[:limit]]


def main(argv: list[str] | None = None) -> int:
    make_stdout_utf8_safe()

    parser = argparse.ArgumentParser(description="覆盖率阈值门禁（阈值唯一来源：pyproject.toml）")
    parser.add_argument("--report", default="coverage.json", help="覆盖率 JSON 报告路径（默认 coverage.json）")
    parser.add_argument("--no-ratchet", action="store_true", help="关闭「覆盖率涨了要收紧阈值」的提醒")
    parser.add_argument("--update", action="store_true", help="把当前真实覆盖率写回 pyproject.toml 作为新阈值")
    parser.add_argument("--quiet", action="store_true", help="只在失败时输出")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    if not report_path.is_file():
        print(f"[coverage-gate] 找不到覆盖率报告：{report_path}", file=sys.stderr)
        print("[coverage-gate] 请先用 --cov-report=json 生成报告。", file=sys.stderr)
        return 2

    threshold = read_threshold()
    if threshold is None:
        print(
            "[coverage-gate] pyproject.toml 的 [tool.coverage.report] 里没有 fail_under，门禁无法判定。",
            file=sys.stderr,
        )
        return 2

    data = load_json_report(report_path)
    actual = float(data["totals"]["percent_covered"])
    stmt = data["totals"]["num_statements"]
    missing = data["totals"]["missing_lines"]

    if args.update:
        if write_threshold(round(actual, 1)):
            print(f"[coverage-gate] 已把 fail_under 更新为 {round(actual, 1):g}（原 {threshold:g}）")
            return 0
        print("[coverage-gate] 写回失败：pyproject.toml 里找不到 [tool.coverage.report] 段落", file=sys.stderr)
        return 2

    ok = True
    if actual < threshold:
        ok = False
    elif not args.no_ratchet and actual > threshold + RATCHET_MARGIN:
        ok = False  # 过高同样失败：提示收紧阈值，否则门禁会退化成橡皮图章

    if not args.quiet or not ok:
        print(f"[coverage-gate] 阈值 {threshold:g}%  实测 {actual:.2f}%  语句 {stmt}  未覆盖 {missing}")
        if actual < threshold:
            print(f"[coverage-gate] ✗ 覆盖率低于阈值 {threshold - actual:.2f} 个百分点")
            print("[coverage-gate] 未覆盖语句最多的文件：")
            for line in format_low_files(data):
                print(line)
        elif not args.no_ratchet and actual > threshold + RATCHET_MARGIN:
            suggest = round(actual - 1.0, 1)  # 留 1 个百分点缓冲，避免正常波动就红
            print(
                f"[coverage-gate] ✗ 覆盖率已高于阈值 {actual - threshold:.2f} 个百分点"
                f" ⇒ 阈值该收紧了（建议 fail_under = {suggest:g}）"
            )
            print("[coverage-gate]   收紧方式：编辑 pyproject.toml，或运行本脚本加 --update")
        else:
            print(f"[coverage-gate] ✓ 覆盖率达标（余量 {actual - threshold:.2f} 个百分点）")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
