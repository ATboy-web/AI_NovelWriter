#!/usr/bin/env python
"""安装项目自带的 git hooks（目前只有一个：pre-commit 同步依赖图）。

## 为什么用脚本安装而不是直接提交 `.git/hooks/`

`.git/hooks/` **不进版本库** —— 换机器、重新 clone 后钩子就没了。
把钩子内容放在 `scripts/git_hooks/` 里纳入版本管理，再用本脚本装到 `.git/hooks/`，
这样"怎么装"本身也是可追溯的。

## 用法

    python scripts/install_git_hooks.py            # 安装（覆盖同名的既有钩子，先备份）
    python scripts/install_git_hooks.py --uninstall # 卸载
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_DIR = REPO_ROOT / ".git" / "hooks"
HOOKS = ("pre-commit",)


def _write_hook(name: str) -> None:
    src = REPO_ROOT / "scripts" / "git_hooks" / name
    if not src.exists():
        raise SystemExit(f"缺少钩子源文件：{src}")
    HOOK_DIR.mkdir(parents=True, exist_ok=True)
    dst = HOOK_DIR / name
    if dst.exists():
        backup = dst.with_suffix(dst.suffix + ".bak")
        shutil.copy2(dst, backup)
        print(f"  已有钩子已备份：{backup.name}")
    shutil.copy2(src, dst)
    # Windows 上 git 不依赖执行位，但类 Unix 环境需要
    mode = dst.stat().st_mode
    dst.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  已安装：{dst.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装/卸载项目 git hooks")
    parser.add_argument("--uninstall", action="store_true", help="删除已安装的钩子")
    args = parser.parse_args(argv)

    if not HOOK_DIR.parent.exists():
        print(f"这不是 git 仓库（找不到 {HOOK_DIR.parent}）", file=sys.stderr)
        return 2

    for name in HOOKS:
        dst = HOOK_DIR / name
        if args.uninstall:
            if dst.exists():
                dst.unlink()
                print(f"  已卸载：{dst.relative_to(REPO_ROOT)}")
            else:
                print(f"  未安装：{name}")
            continue
        _write_hook(name)

    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
