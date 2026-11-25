#!/usr/bin/env python
"""EXE 启动冒烟：把「打包后到底能不能用」变成可复现的检查。

## 为什么需要它

`check_bundle.py` 只看**静态清单**（TOC 里有没有某个包）。它能回答"依赖打全了吗"，
但回答不了"启动起来是不是活的"：

- onefile 引导进程可能崩在解包阶段，而 EXE 文件本身完全正常；
- 某个面板模块导入失败会被 `load_panels()` **记日志后跳过** ——
  界面照常出现，只是少了几块（`app/__init__` 的 `_ImportStub` 降级同理）；
- 版本号忘了同步时，标题里会显示旧版本，但没人会注意。

所以真实的冒烟判据是四条：**窗口标题非空且含版本号、双进程结构、面板注册完整、
`load_failures` 为空**。这四条以前靠手工看，本脚本把它们变成一条命令。

## 判据来源（不要凭记忆改）

- 面板总数/分组数取自 `app/panels/registry.py`（唯一权威），
  本脚本用 `--expect-panels` / `--expect-categories` 显式传入，
  **默认值从源码现算**，避免"文档写了 20、实际变成 19"这种漂移。
- `panel_registry` 事件由 `toolkit_ui._record_panel_registry` 写入，
  字段：`log_dir` / `total` / `by_category` / `native` / `legacy` / `load_failures`。

## 用法

    python scripts/smoke_exe.py                      # 用仓库根的 AI_NovelWriter.exe
    python scripts/smoke_exe.py --exe 桌面/x.exe     # 指定产物
    python scripts/smoke_exe.py --timeout 90         # 慢机器放宽等待
    python scripts/smoke_exe.py --keep-logs          # 保留隔离出来的诊断目录

退出码：0 全通过 / 1 任一条不通过 / 2 找不到 EXE。

## 两个已踩过的坑

1. **必须隔离 `AI_NOVEL_DIAGNOSTIC_DIR`**：否则读到的是用户真实使用中的日志，
   "面板 20 个"可能是上一次运行留下的。本脚本每次都建临时目录。
2. **不要用 `Start-Process` 拉起 GUI**（沙箱约束下会失败）；
   `subprocess.Popen` + `EnumWindows` 实测可用。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: 等待窗口出现的最长时间（onefile 首次运行要解包，冷机可能要 20s+）
DEFAULT_TIMEOUT = 60.0

#: 窗口标题必须包含的前缀（版本号在它后面）
TITLE_PREFIX = "AI小说创作工坊"


# ══════════════════════════════════════════════════════════════ 期望值


def expected_from_source() -> tuple[int, int]:
    """从面板注册表现算「应有几个面板 / 几个分组」。

    为什么不写死数字：`docs/` 里的数字会和代码漂移（本项目已经因此错过一次）。
    直接 import 源码是唯一不会漂的来源。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.panels.registry import PANEL_REGISTRY, load_panels
    from app.panels.registry import categories as _categories

    load_panels()
    return len(PANEL_REGISTRY), len(_categories())


# ══════════════════════════════════════════════════════════════ 窗口探针


def windows_of_pid(pid: int) -> list[str]:
    """返回该进程的可见窗口标题（只在本平台有意义；其他平台返回空）。"""
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    found: list[str] = []
    proc_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):
        wpid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value:
                    found.append(buf.value)
        return True

    user32.EnumWindows(proc_type(_cb), 0)
    return found


def windows_of_pids(pids: list[int]) -> list[str]:
    """返回这批进程的可见窗口标题（onefile 下窗口不在 `Popen.pid` 上）。"""
    seen: list[str] = []
    for pid in pids:
        for title in windows_of_pid(pid):
            if title not in seen:
                seen.append(title)
    return seen


def live_processes(exe_path: Path) -> list[int]:
    """查找正在运行的该 EXE 的进程（onefile 应有引导 + 应用两个）。

    用 `CreateToolhelp32Snapshot` 而不是 `tasklist` 文本解析：后者在中文
    系统上列名会截断，且输出格式随版本变。
    """
    if sys.platform != "win32":
        return []
    target = str(exe_path).lower()
    pids: list[int] = []
    kernel32 = ctypes.windll.kernel32
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return []
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.decode("mbcs", errors="replace").lower()
            if name and name in target:
                pids.append(int(entry.th32ProcessID))
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return pids


#: 确认框标题里会出现的字样（`shell_ui._on_close` 用 `askyesno("确认", ...)`）
CONFIRM_DIALOG_MARKERS = ("确认", "Confirm")

#: 按钮文本：中文系统是「是(Y)」，英文是「&Yes」/「Yes」
YES_BUTTON_MARKERS = ("是", "Yes", "&Yes", "确定", "OK")


def _child_buttons(hwnd: int) -> list[tuple[int, str]]:
    """列出某窗口的直接子按钮 `[(hwnd, 文本)]`。

    ❗ 必须先 `IsWindow` 校验：`EnumChildWindows(0, ...)` 会把**桌面所有窗口**
    当成子窗口枚举出来（0 表示桌面），于是无效句柄会得到一大堆无关句柄。
    """
    if sys.platform != "win32" or not hwnd:
        return []
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return []
    out: list[tuple[int, str]] = []
    proc_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(child, _lparam):
        length = user32.GetWindowTextLengthW(child)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(child, buf, length + 1)
            out.append((int(child), buf.value))
        return True

    user32.EnumChildWindows(hwnd, proc_type(_cb), 0)
    return out


def confirm_dialog_handles(pids: list[int]) -> list[int]:
    """找这批进程里的「确认」类对话框窗口句柄。"""
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    found: list[int] = []
    proc_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):
        wpid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value not in pids or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if any(marker in buf.value for marker in CONFIRM_DIALOG_MARKERS):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proc_type(_cb), 0)
    return found


def click_yes(dialog_hwnd: int) -> bool:
    """点掉确认框的「是」按钮。成功发出点击返回 True。"""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5
    for hwnd, text in _child_buttons(dialog_hwnd):
        if any(marker in text for marker in YES_BUTTON_MARKERS):
            user32.SendMessageW(hwnd, BM_CLICK, 0, 0)
            return True
    return False


def request_close(pid: int) -> bool:
    """向该进程的窗口发 `WM_CLOSE`；成功发出返回 True（不代表进程已退）。"""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    sent = False
    proc_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):
        nonlocal sent
        wpid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            sent = True
        return True

    user32.EnumWindows(proc_type(_cb), 0)
    return sent


# ══════════════════════════════════════════════════════════════ 判据


@dataclass
class CheckResult:
    """一条判据的结果。`detail` 在不通过时要能直接拿去报错。"""

    name: str
    ok: bool
    detail: str = ""


@dataclass
class SmokeReport:
    checks: list[CheckResult] = field(default_factory=list)
    #: 观察项：记录事实但不影响结论（例如"没发过请求所以没有性能报告"）
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))

    def note(self, text: str) -> None:
        self.notes.append(text)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks) and bool(self.checks)

    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok]


def read_panel_registry_event(log_dir: Path, timeout: float = 10.0) -> dict | None:
    """从隔离目录的 `*.jsonl` 里找最后一条 `panel_registry` 事件。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for path in sorted(log_dir.rglob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                if "panel_registry" not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                data = record.get("data") or record.get("payload") or {}
                if isinstance(data, dict) and "total" in data:
                    return data
        time.sleep(0.3)
    return None


def check_title(titles: list[str]) -> CheckResult:
    """标题必须非空、含产品名、且带版本号（`vX.Y.Z`）。"""
    if not titles:
        return CheckResult("窗口标题", False, "没有读到任何可见窗口标题（进程可能崩在启动阶段）")

    titled = [t for t in titles if TITLE_PREFIX in t]
    if not titled:
        return CheckResult("窗口标题", False, f"标题里没有「{TITLE_PREFIX}」：{titles}")

    title = titled[0]
    has_version = " v" in title and any(ch.isdigit() for ch in title.split(" v", 1)[1][:3])
    if not has_version:
        return CheckResult("窗口标题", False, f"标题缺少版本号（忘同步 `_FALLBACK_VERSION`？）：{title}")
    return CheckResult("窗口标题", True, title)


def check_panels(event: dict | None, want_total: int, want_categories: int) -> list[CheckResult]:
    """面板注册的三条：总数、分组数、导入失败列表为空。"""
    if event is None:
        return [CheckResult("面板注册事件", False, "诊断日志里没有 panel_registry 事件（启动没走完？）")]

    by_cat = event.get("by_category") or {}
    total = event.get("total")
    failures = event.get("load_failures") or []

    return [
        CheckResult(
            "面板总数",
            total == want_total,
            f"期望 {want_total}，实际 {total}",
        ),
        CheckResult(
            "面板分组数",
            len(by_cat) == want_categories,
            f"期望 {want_categories}，实际 {len(by_cat)}：{sorted(by_cat)}",
        ),
        CheckResult(
            "面板导入失败",
            not failures,
            f"有 {len(failures)} 个模块导入失败：{failures}",
        ),
    ]


# ══════════════════════════════════════════════════════════════ 主流程


def run_smoke(
    exe: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    keep_logs: bool = False,
    want_panels: int | None = None,
    want_categories: int | None = None,
) -> SmokeReport:
    report = SmokeReport()
    if not exe.exists():
        report.add("产物存在", False, f"找不到 {exe}")
        return report

    if want_panels is None or want_categories is None:
        src_panels, src_cats = expected_from_source()
        want_panels = want_panels if want_panels is not None else src_panels
        want_categories = want_categories if want_categories is not None else src_cats

    log_dir = Path(tempfile.mkdtemp(prefix="nw_smoke_logs_"))
    env = dict(os.environ)
    # 隔离：否则读到的是用户真实使用中的日志，判据全部失去意义
    env["AI_NOVEL_DIAGNOSTIC_DIR"] = str(log_dir)
    env.pop("PYTHONPATH", None)  # 防止误用源码而不是 EXE 内的代码

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent))
        report.add("进程已启动", True, f"pid={proc.pid}")

        # ---- 等窗口 ----
        # ⚠️ 不能只查 `proc.pid`：onefile 下那是引导进程，窗口在解包后的子进程里。
        # 真机验证时因此对**正常产物**报过"窗口没出现"（面板日志却全对）。
        titles: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                report.add("进程存活", False, f"启动后立即退出，退出码 {proc.returncode}")
                break
            related = live_processes(exe) or [proc.pid]
            titles = windows_of_pids(related)
            if titles:
                break
            time.sleep(0.4)
        else:
            report.add("窗口出现", False, f"{timeout:.0f}s 内没有等到窗口")

        report.add(check_title(titles).name, check_title(titles).ok, check_title(titles).detail)

        # ---- 双进程结构（onefile：引导 + 应用）----
        pids = live_processes(exe)
        report.add(
            "onefile 双进程",
            len(pids) >= 2,
            f"找到 {len(pids)} 个该 EXE 的进程：{pids}（onefile 应有引导 + 应用）",
        )

        # ---- 面板注册 ----
        event = read_panel_registry_event(log_dir)
        for check in check_panels(event, want_panels, want_categories):
            report.add(check.name, check.ok, check.detail)
        if event is not None:
            report.add("产物内面板清单", True, f"native={len(event.get('native') or [])}")

        # ---- 优雅关闭（三段式：请求 → 确认框 → 真的退出）----
        # 同理发给**窗口所在**的进程（onefile 下是子进程）
        related = live_processes(exe) or [proc.pid]
        closed = False
        for pid in related:
            closed = request_close(pid) or closed
        report.add("关闭请求已送达", closed, "" if closed else "没有找到可关闭的窗口")

        # 程序有防误关确认框（`shell_ui._on_close` → `askyesno("确认", ...)`）。
        # 它是**正确设计**，但自动化要能点掉它才能验完退出链路。
        confirmed = False
        confirm_deadline = time.time() + 10
        while time.time() < confirm_deadline and proc.poll() is None:
            handles = confirm_dialog_handles(live_processes(exe) or related)
            if handles:
                confirmed = click_yes(handles[0])
                if confirmed:
                    break
            time.sleep(0.3)
        report.add(
            "退出确认框",
            confirmed or proc.poll() is not None,
            "已点「是」"
            if confirmed
            else ("进程直接退出，无确认框" if proc.poll() is not None else "没等到确认框或没找到「是」按钮"),
        )

        try:
            proc.wait(timeout=20)
            report.add("进程已退出", True, f"退出码 {proc.returncode}")
        except subprocess.TimeoutExpired:
            report.add("进程已退出", False, "点掉确认框后 20s 仍未退出")

        # 观察项（**不是判据**）：`_on_close` 会调 `_flush_performance_report()`，
        # 但它内部有 `if not summary.get("total_requests"): return` ——
        # 本次冒烟没发过任何 AI 请求，所以本来就不该落盘。
        # 把它当判据会对每个正常产物报错（真机踩过）。
        perf_files = list(log_dir.rglob("performance-*.json"))
        report.note(
            f"性能报告：{'有 ' + str(len(perf_files)) + ' 个' if perf_files else '无（本次未发请求，符合预期）'}"
        )
        jsonl_files = list(log_dir.rglob("*.jsonl"))
        report.note(f"诊断日志：{len(jsonl_files)} 个 .jsonl")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        if keep_logs:
            print(f"[smoke] 诊断日志保留在：{log_dir}")
        else:
            shutil.rmtree(log_dir, ignore_errors=True)

    return report


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="EXE 启动冒烟")
    parser.add_argument("--exe", default=str(REPO_ROOT / "AI_NovelWriter.exe"), help="产物路径")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="等待窗口的秒数")
    parser.add_argument("--keep-logs", action="store_true", help="保留隔离的诊断目录")
    parser.add_argument("--expect-panels", type=int, default=None, help="期望面板数（默认从源码算）")
    parser.add_argument("--expect-categories", type=int, default=None, help="期望分组数（默认从源码算）")
    args = parser.parse_args(argv)

    exe = Path(args.exe)
    if not exe.is_absolute():
        exe = (REPO_ROOT / exe).resolve()

    print(f"冒烟目标：{exe}")
    if not exe.exists():
        print(f"❗ 找不到产物：{exe}")
        return 2

    report = run_smoke(
        exe,
        timeout=args.timeout,
        keep_logs=args.keep_logs,
        want_panels=args.expect_panels,
        want_categories=args.expect_categories,
    )

    for check in report.checks:
        mark = "✓" if check.ok else "✗"
        line = f"  {mark} {check.name}"
        if check.detail:
            line += f" —— {check.detail}"
        print(line)

    for note in report.notes:
        print(f"  · {note}")

    print()
    if report.ok:
        print("✅ 冒烟通过")
        return 0
    print(f"❌ 冒烟失败（{len(report.failures())} 条）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
