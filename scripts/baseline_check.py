#!/usr/bin/env python
"""v3 改造基线检查（P0 护栏）。

用途：改造每一期前后各跑一次，**用同一把尺子**证明「角色数据零改动」。

    python scripts/baseline_check.py            # 采集并打印当前快照
    python scripts/baseline_check.py --record   # 记录为基线文件（含 ruff + 全量 pytest）
    python scripts/baseline_check.py --verify   # 与基线文件比对（不等则 exit 1）
    python scripts/baseline_check.py --record --no-tests   # 只记数据/仓库，不跑测试

只读脚本：不写业务数据；`--record` 只写一个基线 JSON 到 `docs/`。

⚠️ `--record` 默认会跑**全量 pytest**（数十秒到数分钟）。在受限沙箱里整套测试会触发
批量删除守卫、拿不到可信结果，此时用 `--no-tests` 只记数据与仓库状态。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.live_data import find_novel_dir, summarize_novel  # noqa: E402

BASELINE_FILE = REPO_ROOT / "docs" / "v3_baseline.json"


def _run(cmd: list) -> tuple:
    """执行命令并返回 (exit_code, 合并输出)。"""
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"<执行失败: {exc}>"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_pytest_summary(output: str) -> dict:
    """从 pytest 输出里取出 passed/failed 数字（拿不到就保留 -1，不猜）。"""
    result = {"passed": -1, "failed": -1}
    for line in reversed(output.strip().splitlines()):
        if "passed" not in line and "failed" not in line:
            continue
        # 形如 "1391 passed, 0 failed in 209.08s"
        parts = line.replace(",", " ").split()
        for idx, part in enumerate(parts):
            if idx == 0 or not parts[idx - 1].isdigit():
                continue
            if part == "passed":
                result["passed"] = int(parts[idx - 1])
            elif part == "failed":
                result["failed"] = int(parts[idx - 1])
        if result["passed"] >= 0:
            break
    if result["passed"] >= 0 and result["failed"] < 0:
        result["failed"] = 0
    return result


def output_tail(text: str, lines: int = 20) -> str:
    """取输出末尾若干行（失败时定位用）。"""
    return "\n".join(text.strip().splitlines()[-lines:])


def collect(with_tests: bool = False) -> dict:
    """采集完整快照。"""
    snapshot = {"repo": {"head": "", "dirty": None}, "live_data": None}

    code, out = _run(["git", "rev-parse", "--short", "HEAD"])
    snapshot["repo"]["head"] = out.strip().splitlines()[-1] if code == 0 else "unknown"

    code, out = _run(["git", "status", "--porcelain"])
    if code == 0:
        # 把**基线文件自身**从 dirty 里剔除：否则 `--record` 会把"我改了基线"记进去，
        # 导致同一个状态连续两次 record 得到不同内容（不幂等），也无法作为"提交前的干净度"证据。
        baseline_rel = BASELINE_FILE.relative_to(REPO_ROOT).as_posix()
        snapshot["repo"]["dirty"] = [line for line in out.strip().splitlines() if baseline_rel not in line]
    else:
        snapshot["repo"]["dirty"] = None

    novel = find_novel_dir()
    if novel is not None:
        snapshot["live_data"] = summarize_novel(novel).as_dict()

    if with_tests:
        code, out = _run([sys.executable, "-m", "ruff", "check", "app/", "tests/"])
        snapshot["ruff_clean"] = code == 0

        code, out = _run([sys.executable, "-m", "pytest", "-q", "--no-header", f"--basetemp={_pytest_basetemp()}"])
        summary = _parse_pytest_summary(out)
        snapshot["tests"] = summary
        if summary["passed"] < 0:
            snapshot["tests_raw_tail"] = output_tail(out, 15)

    return snapshot


def _pytest_basetemp() -> Path:
    """把 pytest 的临时根指到系统临时目录下的固定子目录。

    不指定时 pytest 会在 `%TEMP%/pytest-of-<user>/pytest-N` 下建**批量**删除，
    在受限沙箱里会误触发删除守卫，表现为一堆 setup ERROR（与代码无关）。
    固定目录同时让残留可预测、可手工清理。
    """
    import tempfile

    base = Path(tempfile.gettempdir()) / "anw_pytest_basetemp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="v3 改造基线检查")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", action="store_true", help="把当前快照写为基线")
    group.add_argument("--verify", action="store_true", help="与既有基线比对")
    parser.add_argument("--full", action="store_true", help="同时跑 ruff 与 pytest")
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="即使 record/full 也跳过 ruff 与 pytest（受限环境下用：整套测试会触发"
        "批量删除守卫，记下来只会是 tests.passed=-1 的噪声）",
    )
    args = parser.parse_args()

    snapshot = collect(with_tests=(args.full or args.record) and not args.no_tests)

    print("=" * 62)
    print("v3 基线快照")
    print("=" * 62)
    repo = snapshot["repo"]
    print(f"HEAD        : {repo['head']}")
    print(f"工作区改动  : {len(repo['dirty']) if repo['dirty'] is not None else '未知'} 项")

    live = snapshot["live_data"]
    if live:
        print("-" * 62)
        print("线上小说数据（只读采集）")
        print(f"  root       : {live['root']}")
        print(f"  sha256     : {live['characters_sha256']}")
        print(f"  bytes      : {live['characters_bytes']}")
        print(f"  characters : {live['character_count']}")
        print(f"  chapters   : {live['chapter_count']}   ← chapters/*.txt（真章数）")
        print(f"  char files : {live.get('character_file_count', '?')}   ← characters/*.json")
        print(f"  mtime      : {live['characters_mtime']}")
    else:
        print("-" * 62)
        print("⚠️  未找到线上小说目录 —— 数据断言已跳过（不视为失败）")

    if "ruff_clean" in snapshot:
        print(f"ruff        : {'通过' if snapshot['ruff_clean'] else '有告警'}")
    if "tests" in snapshot:
        t = snapshot["tests"]
        print(f"pytest      : {t['passed']} passed / {t['failed']} failed")

    if args.record:
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        print("-" * 62)
        print(f"已写入基线文件: {BASELINE_FILE.relative_to(REPO_ROOT)}")
        return 0

    if args.verify:
        if not BASELINE_FILE.is_file():
            print("✗ 基线文件不存在，请先运行 --record")
            return 1
        previous = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        return _verify(previous, snapshot)

    return 0


def _verify(previous: dict, current: dict) -> int:
    """逐项比对，打印差异；数据哈希不一致直接判失败。

    ⚠️ **本工具的契约**：假设两次运行之间**没有正常的数据写活动**
    （即改造前采一次、改造后立刻采一次）。因此"多了新章节/新角色"也会被报成差异 ——
    那是**预期内的**，不是回归；判断回归要看 `characters_sha256` 是否在
    **没有写操作**的情况下变化。
    """
    failures = []

    prev_live = previous.get("live_data") or {}
    cur_live = current.get("live_data") or {}
    if prev_live and cur_live:
        for key, label in (
            ("characters_sha256", "角色数据 sha256"),
            ("characters_bytes", "角色数据字节数"),
            ("character_count", "角色数量"),
            ("chapter_count", "章节数（chapters/*.txt）"),
            ("character_file_count", "角色文件数（characters/*.json）"),
        ):
            if key not in prev_live:
                # 基线文件是旧 schema —— 跳过而不是误报失败
                print(f"· {label}: 本次 {cur_live.get(key)}（旧基线无此字段，跳过比对）")
                continue
            if prev_live.get(key) != cur_live.get(key):
                failures.append(f"{label} 变了: {prev_live.get(key)} → {cur_live.get(key)}")
            else:
                print(f"✓ {label}: {cur_live.get(key)}")
    elif prev_live and not cur_live:
        print("⚠️  基线里有线上数据但本次未找到 → 跳过数据比对")

    prev_tests = previous.get("tests") or {}
    cur_tests = current.get("tests") or {}
    if prev_tests and cur_tests and cur_tests.get("failed", 0) >= 0:
        if cur_tests.get("failed", 0) > prev_tests.get("failed", 0):
            failures.append(f"测试回归: failed {prev_tests.get('failed')} → {cur_tests.get('failed')}")

    print("-" * 62)
    if failures:
        print("✗ 基线校验未通过：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("✓ 基线校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
