#!/usr/bin/env python
"""开发预检：一条命令做完「格式 → 依赖图 → 快速测试」。

## 为什么需要

`tests/test_module_graph.py` 会在依赖图文档过期时报错 —— 但它**只在跑全量时**才会红，
而全量要 8 分钟。实际开发中经常是"改完代码 → 等 8 分钟 → 发现只是忘了重算依赖图"，
白等一轮（本项目已因此白跑过两次全量）。

本脚本把这一步提前到秒级，并提供 `--fix` 自动重算。

## 用法

    python scripts/preflight.py           # 检查 + 自动重算依赖图
    python scripts/preflight.py --no-fix  # 只检查，不改文件（CI 用）
    python scripts/preflight.py --tests   # 额外跑一遍快速测试子集
    python scripts/preflight.py --exe AI_NovelWriter.exe   # 额外跑 EXE 冒烟（30s+）

## 步骤（任一步失败即非 0 退出）

1. `ruff check`          —— 静态检查
2. `ruff format --check` —— 格式
3. `module_graph --check`     —— 存在 hard 循环即失败
4. `module_graph --check-doc` —— 文档过期：`--fix` 时自动重算并暂存
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

#: 快速测试子集：覆盖最容易受结构改动影响的守卫（约 10 秒）
FAST_TESTS = [
    "tests/test_module_graph.py",
    "tests/test_architecture_layers.py",
    "tests/test_layer_packaging.py",
    "tests/test_config_consistency.py",
]


def _run(cmd: list[str], *, capture: bool = True) -> tuple[int, str]:
    """跑一条命令，返回 (退出码, 输出)。不抛异常 —— 失败即返回码。"""
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except OSError as exc:
        return 127, f"无法执行 {cmd[0]}: {exc}"


def _step(name: str, code: int, detail: str = "") -> bool:
    mark = "✓" if code == 0 else "✗"
    print(f"  {mark} {name}")
    if code != 0 and detail.strip():
        for line in detail.strip().splitlines()[-12:]:
            print(f"      {line}")
    return code == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="开发预检（格式 / 依赖图 / 快速测试）")
    parser.add_argument("--no-fix", action="store_true", help="只检查，不自动重算依赖图")
    parser.add_argument("--tests", action="store_true", help="额外跑快速测试子集")
    parser.add_argument(
        "--exe",
        metavar="PATH",
        default=None,
        help="额外跑 EXE 启动冒烟（默认关：一次 30s+ 且需要桌面环境）",
    )
    args = parser.parse_args(argv)

    py = sys.executable
    ok = True

    print("预检：")
    ok &= _step("ruff check", *_run([py, "-m", "ruff", "check", "app", "tests", "backend", "scripts"]))
    ok &= _step(
        "ruff format --check", *_run([py, "-m", "ruff", "format", "--check", "app", "tests", "backend", "scripts"])
    )
    ok &= _step("依赖图：hard 循环", *_run([py, str(SCRIPTS / "module_graph.py"), "--check"]))

    doc_code, doc_out = _run([py, str(SCRIPTS / "module_graph.py"), "--check-doc"])
    if doc_code != 0 and not args.no_fix:
        print("  … 依赖图文档过期，正在重算")
        regen_code, regen_out = _run([py, str(SCRIPTS / "module_graph.py")])
        if not _step("依赖图：重算", regen_code, regen_out):
            ok = False
        else:
            # 重算后必须真的同步，否则说明 render 本身不稳定
            ok &= _step("依赖图：重算后一致", *_run([py, str(SCRIPTS / "module_graph.py"), "--check-doc"]))
            _run(["git", "add", "docs/MODULE_DEPENDENCY_MAP.md"])
    else:
        ok &= _step("依赖图：文档同步", doc_code, doc_out)

    if args.tests:
        ok &= _step(
            "快速测试",
            *_run([py, "-m", "pytest", *FAST_TESTS, "-q", "-p", "no:cacheprovider"]),
        )

    if args.exe:
        ok &= _step(
            "EXE 启动冒烟",
            *_run([py, str(SCRIPTS / "smoke_exe.py"), "--exe", str(args.exe)]),
        )

    print()
    if ok:
        print("✅ 预检通过")
        return 0
    print("❌ 预检未通过")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
