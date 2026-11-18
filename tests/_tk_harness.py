"""全仓**唯一**的 Tk 根窗口创建入口（测试侧）。

## 为什么要有这个文件

仓库里原先有 **6 个文件各自写了一遍** `tk.Tk()` + `except: pytest.skip("无显示环境")`：

| 文件 | 位置 |
|---|---|
| `test_panel_controls_mounted.py` | `_make_root()` + `_tk_ok()` |
| `test_panel_layout.py` | fixture 内联 |
| `test_panel_popout.py` | fixture 内联 |
| `test_p4b_panels.py` | fixture 内联 |
| `test_genres.py` | `_tk_available()` + 类内创建 |
| `test_mcp_system.py` | `_tk_available()` + 类内创建 |
| `test_image_and_local_model.py` | fixture 内联 |

六份重复带来三个后果：

1. **同一故障六种表现**：`test_panel_controls_mounted` 会 skip，`test_panel_layout` 会 skip，
   但 `test_panel_layout` 里"窗口未映射"的断言比较实在 —— 它一 skip，**面板布局回归就没人守了**；
2. **谁也不记录失败现场**：`except Exception: skip` 把异常上下文直接丢掉，导致
   "Tk 偶发初始化失败"这个现象长期无法定因（本次排查就是为此）；
3. **判据不一致**：有的捕获 `Exception`，有的只捕 `tk.TclError`，有的连重试都没有。

## 这里的契约

- `create_root()`：建一个已 `withdraw()` 的根窗口；**失败时先重试**（带递增间隔），
  仍失败则把完整现场写入 `%TEMP%/anw_tk_failure.jsonl` 再抛 `TkUnavailable`。
- `require_tk()`：给 `skipif` 用，只回答"能不能建"，不建多次。
- `TkUnavailable`：**专门区分"环境起不来"与"面板有缺陷"** ——
  调用方只允许对前者 skip；后者必须让测试真的失败。
"""

from __future__ import annotations

import atexit
import json
import os
import pathlib
import tempfile
import threading
import time
import tkinter as tk
from functools import lru_cache

#: 失败现场落盘位置（排查用；不存在说明从未失败过）
FAILURE_LOG = pathlib.Path(tempfile.gettempdir()) / "anw_tk_failure.jsonl"

#: 本进程创建过多少个 Tcl 解释器 —— 这是"暴露面"的度量。
#:
#: 每次 `tk.Tk()` 都会新建一个 Tcl 解释器，并**重新从磁盘读取 init.tcl**
#: （一次约 25 KB）。全量套件因此会做上百次这种读操作，任何一次瞬时读失败
#: 都会让当次 Tk 初始化失败。把次数记下来，才能判断"减少暴露面"值不值得做。
_CREATE_COUNT = 0
_CREATE_COUNT_LOG = pathlib.Path(tempfile.gettempdir()) / "anw_tk_create_count.txt"


def _flush_create_count() -> None:
    try:
        _CREATE_COUNT_LOG.write_text(
            f"creations={_CREATE_COUNT} final_handles={_handle_count()}", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


atexit.register(_flush_create_count)


class TkUnavailable(RuntimeError):
    """Tk 解释器无法初始化 —— 这是**环境**问题，与"面板有没有挂载控件"无关。"""


def _readable_init_tcl() -> dict:
    """用**纯 Python** 直接读一次 init.tcl，判断"文件此刻是否真的读不到"。

    这一步是定因的关键分叉：
    - Python 也读不到 ⇒ 文件/句柄/杀软层面的问题；
    - Python 读得到，只有 Tcl 读不到 ⇒ Tcl 解释器初始化路径的问题。

    ⚠️ 定位库目录**不能靠 `tk.__file__`**：诊断可能跑在"被替身替换过的 tk"下
    （测试自身就会这么做），那时它没有 `__file__`，诊断就只剩一条 error。
    改用解释器前缀（`sys.base_prefix`/`sys.prefix`），任何情况下都能定位。
    """
    import sys

    info: dict = {}
    try:
        roots = []
        for prefix in (getattr(sys, "base_prefix", ""), getattr(sys, "prefix", "")):
            if prefix:
                roots.append(pathlib.Path(prefix) / "tcl")
        tk_file = getattr(tk, "__file__", "") or ""
        if tk_file:
            roots.append(pathlib.Path(tk_file).resolve().parent.parent / "tcl")

        candidates: list[pathlib.Path] = []
        for root in roots:
            if root.is_dir():
                candidates.extend(sorted(root.glob("tcl8.*/init.tcl")))
        info["init_tcl_candidates"] = [str(c) for c in candidates]
        if candidates:
            target = candidates[0]
            info["init_tcl_size"] = target.stat().st_size
            info["init_tcl_read_ok"] = len(target.read_bytes()) > 0
        else:
            info["init_tcl_read_ok"] = False
            info["init_tcl_read_error"] = "未找到任何 init.tcl（Tcl 库目录不存在）"
    except Exception as exc:  # noqa: BLE001 - 诊断本身不能抛
        info.setdefault("init_tcl_read_ok", False)
        info["init_tcl_read_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _handle_count() -> int | None:
    """进程句柄数（Windows）；其它平台返回 None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetProcessHandleCount.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        count = ctypes.c_ulong()
        if kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(count)):
            return int(count.value)
    except Exception:  # noqa: BLE001
        return None
    return None


def _memory_mb() -> dict:
    """进程内存（Windows）：PrivateUsage / WorkingSet。

    为什么记这个：失败发生在**运行 7 分钟、第 110 次创建解释器**之后，
    而同一瞬间 Python 读 init.tcl 是成功的 —— 说明不是文件系统问题，
    更要看"进程自身状态"。内存是最直接的一项。
    """
    if os.name != "nt":
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        # ❗  返回伪句柄 -1，若不定 argtypes，ctypes 会按 c_int 传参
        # 并抛 OverflowError（伪句柄是 64 位的 0xFFFFFFFFFFFFFFFF）。实测踩过。
        get_info = kernel32.K32GetProcessMemoryInfo
        get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        ok = get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        if ok:
            mb = 1024 * 1024
            return {
                "working_set_mb": round(counters.WorkingSetSize / mb, 1),
                "peak_working_set_mb": round(counters.PeakWorkingSetSize / mb, 1),
                "private_mb": round(counters.PrivateUsage / mb, 1),
                "pagefile_mb": round(counters.PagefileUsage / mb, 1),
            }
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _record_failure(exc: BaseException, attempts: list[dict]) -> None:
    """把失败现场追加到 `FAILURE_LOG`（每次失败一行 JSON）。"""
    try:
        info = {
            "error": f"{type(exc).__name__}: {exc}",
            "current_test": os.environ.get("PYTEST_CURRENT_TEST", ""),
            "argv": list(__import__("sys").argv),
            "cwd": os.getcwd(),
            "executable": __import__("sys").executable,
            "threads": [t.name for t in threading.enumerate()],
            "handles": _handle_count(),
            "tcl_library_env": os.environ.get("TCL_LIBRARY"),
            "tk_library_env": os.environ.get("TK_LIBRARY"),
            "default_root": repr(getattr(tk, "_default_root", None)),
            "attempts": attempts,
            **_readable_init_tcl(),
        }
        with open(FAILURE_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(info, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - 诊断失败不得改变用例结论
        pass


#: 重试成功的记录（证明"偶发失败"确实发生过、以及恢复所需次数）
RETRY_LOG = pathlib.Path(tempfile.gettempdir()) / "anw_tk_retry.jsonl"


def _record_retry(trace: list[dict]) -> None:
    try:
        info = {
            "current_test": os.environ.get("PYTEST_CURRENT_TEST", ""),
            "failed_attempts": len(trace),
            "trace": trace,
            "handles": _handle_count(),
            # 决定性判据：失败**当下**，纯 Python 能否读到 init.tcl？
            # 读得到 ⇒ Tcl 侧问题（解释器初始化路径/通道）；读不到 ⇒ 文件/驱动层面。
            "init_tcl_at_failure": _readable_init_tcl(),
            "create_count_so_far": _CREATE_COUNT,
            "memory": _memory_mb(),
        }
        with open(RETRY_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(info, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def create_root(*, attempts: int = 3, retry_delay: float = 0.15) -> tk.Tk:
    """建一个隐藏的 Tk 根窗口；失败重试，仍失败则记录现场并抛 `TkUnavailable`。

    `attempts` 默认 3 次、间隔递增（0.15s / 0.30s）：观测到的失败是**短暂窗口**内的
    连续失败（原先紧挨着的 2 次都失败），给小间隔让 OS 有机会恢复是必要的；
    但**重试不是方案本身** —— 真正的修复在调用方（见 `tests/test_tk_harness.py`
    记录的成因与判据）。
    """
    trace: list[dict] = []
    last: BaseException | None = None
    for index in range(attempts):
        started = time.perf_counter()
        global _CREATE_COUNT
        try:
            root = tk.Tk()
            _CREATE_COUNT += 1
            root.withdraw()
            if index > 0:
                # 重试成功了：这正是"偶发失败确实存在"的证据，必须留痕，
                # 否则我们会误以为问题已经消失（静默恢复 = 又一次静默掩盖）。
                _record_retry(trace)
            return root
        except Exception as exc:  # noqa: BLE001 - Tcl 异常类型跨版本不统一
            last = exc
            trace.append(
                {
                    "attempt": index + 1,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "handles": _handle_count(),
                }
            )
            if index < attempts - 1:
                time.sleep(retry_delay * (index + 1))
    assert last is not None
    _record_failure(last, trace)
    raise TkUnavailable(f"Tk 初始化失败（{attempts} 次尝试）：{last}") from last


def optional_root():
    """给"无显示环境可接受"的 fixture 用：建不出窗口就 **skip 并告警**。

    与 `create_root()` 的分工：

    | 入口 | 无窗口时 | 用在哪 |
    |---|---|---|
    | `create_root()` | 抛 `TkUnavailable`（测试**失败**） | 断言"控件是否真的挂载/可见"的守卫类测试 —— 它不能假装通过 |
    | `optional_root()` | `pytest.skip` + 告警 | 布局/弹出面板等"没有显示就没法验证"的测试 |

    ⚠️ `optional_root` 的跳过**必须留痕**：`pytest.skip` 会把用例标成 skipped，
    若不告警，一次环境故障就会让面板布局回归永久静默。
    """
    import warnings

    import pytest

    try:
        return create_root()
    except TkUnavailable as exc:
        warnings.warn(
            f"[tk-harness] Tk 不可用，跳过本用例（{exc}）。"
            f"现场记录见 {FAILURE_LOG}；若本机本应有显示环境请据此排查。",
            stacklevel=2,
        )
        pytest.skip(f"无可用 Tk 环境（已重试仍失败）：{exc}")


@lru_cache(maxsize=1)
def tk_available() -> bool:
    """能否建出 Tk 根窗口（供 `skipif` 使用）。

    ❗ 结果**缓存**：每次探测都要新建一个 Tcl 解释器（重新读 init.tcl），
    而 `skipif` 在每个模块/类上都会求值一次。缓存后全进程只探测一次 ——
    既减少暴露面，也避免探测本身成为一次额外风险。
    """
    try:
        root = create_root()
    except TkUnavailable as exc:
        # 返回 False 会让整个"Tk 面板测试类"被 skipif 跳过。
        # 那是一种**合法的**无显示环境处理，但绝不能静默 ——
        # 否则面板挂载/布局回归会在无人察觉的情况下失去守护。
        import warnings

        warnings.warn(
            f"[tk-harness] Tk 不可用，相关面板测试将被跳过（原因：{exc}）。"
            "若本机本应有显示环境，请查 %TEMP%/anw_tk_failure.jsonl 的现场记录。",
            stacklevel=2,
        )
        return False
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass
    return True
