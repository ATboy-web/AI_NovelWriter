"""覆盖率**全口径可见性**报告（P0-2）。

## 为什么需要这个脚本

`pyproject.toml` 的 `[tool.coverage.run] omit` 排除了 40+ 个 UI 模块。
门禁读到的 `86.x%` 是**计入口径**的覆盖率，而不是整个 `app/` 的覆盖率。
两者差距很大（被排除的语句约占 app 的三分之一），但过去 CI 日志里
只看得到前者 —— 于是"覆盖率 86%"很容易被读成"整个桌面端测到了 86%"。

历史教训：上一轮两个真实 `TypeError` 都落在被 omit 的 `generation_ui.py`，
门禁全绿也没能拦住。可见性不能替代测试，但**看不见就永远补不上**。

## 这个脚本做什么

只读报告、不改门禁：
- 口径 A（计入）：直接取 `coverage.json` 的 totals；
- 口径 B（全 app）：把未计入文件的语句数补进分母（这些文件按 0 覆盖计）；
- 明确列出被排除的文件数、语句数与占比。

语句数用 `coverage` 自己的 `Coverage.analysis2()` 统计，与计入口径**同一定义**，
不是 AST 近似值 —— 否则两个数字不可比。

用法：
    python scripts/coverage_visibility.py --report coverage.json
    python scripts/coverage_visibility.py --report coverage.json --json-out coverage_visibility.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def collect(report_path: Path) -> dict:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    totals = data["totals"]
    measured_files = {_norm(k) for k in data.get("files", {})}

    app_dir = REPO / "app"
    all_files = {_norm(str(p.relative_to(REPO))) for p in app_dir.rglob("*.py")}
    unmeasured = sorted(all_files - measured_files)

    import coverage

    cov = coverage.Coverage(config_file=False, source=["app"])
    omitted_statements = 0
    per_file = []
    for rel in unmeasured:
        try:
            _, statements, _, _, _ = cov.analysis2(str(REPO / rel))
        except Exception as exc:  # noqa: BLE001 - 解析失败要显式暴露，不能静默按 0 计
            print(f"[warn] 无法统计 {rel}：{type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        omitted_statements += len(statements)
        per_file.append({"file": rel, "statements": len(statements)})

    measured_statements = int(totals["num_statements"])
    covered = int(totals["covered_lines"])
    full_statements = measured_statements + omitted_statements
    return {
        "measured": {
            "files": len(measured_files),
            "statements": measured_statements,
            "covered": covered,
            "percent": round(covered * 100.0 / measured_statements, 2) if measured_statements else 0.0,
        },
        "omitted": {
            "files": len(per_file),
            "statements": omitted_statements,
            "share_of_app": round(omitted_statements * 100.0 / full_statements, 2) if full_statements else 0.0,
            "top": sorted(per_file, key=lambda d: -d["statements"])[:15],
        },
        "full_app": {
            "files": len(measured_files) + len(per_file),
            "statements": full_statements,
            "covered": covered,
            "percent": round(covered * 100.0 / full_statements, 2) if full_statements else 0.0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="覆盖率全口径可见性报告（只读，不改门禁）")
    parser.add_argument("--report", default="coverage.json", help="pytest-cov 产出的 JSON 报告")
    parser.add_argument("--json-out", default="", help="可选：把本报告也写成 JSON")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO / report_path
    if not report_path.exists():
        print(f"[error] 找不到覆盖率报告：{report_path}", file=sys.stderr)
        return 2

    result = collect(report_path)
    m, o, fa = result["measured"], result["omitted"], result["full_app"]

    print("=" * 72)
    print("覆盖率双口径（门禁只看口径 A；口径 B 用于看清真实风险面）")
    print("=" * 72)
    print(f"口径A 计入范围 : {m['files']:>3} 文件 / {m['statements']:>6} 语句 / {m['percent']:>6.2f}%")
    print(f"口径B 全 app   : {fa['files']:>3} 文件 / {fa['statements']:>6} 语句 / {fa['percent']:>6.2f}%")
    print(f"被 omit 排除   : {o['files']:>3} 文件 / {o['statements']:>6} 语句（占 app 语句 {o['share_of_app']:.2f}%）")
    print("-" * 72)
    print("排除语句最多的文件（补测优先级参考）：")
    for item in o["top"]:
        print(f"  {item['statements']:>5}  {item['file']}")
    print("=" * 72)

    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = REPO / out
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
