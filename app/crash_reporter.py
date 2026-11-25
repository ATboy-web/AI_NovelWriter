"""崩溃报告：把未捕获异常与原生崩溃落成**可反馈的结构化文件**。

## 为什么需要这一层

此前用户机器上的崩溃只表现为"窗口突然消失"：

- Tk 主线程的未捕获异常只打到 `stderr`，而 PyInstaller 的窗口模式没有控制台
  ⇒ 用户看不到、也复制不出来；
- 子线程里的异常同理（`threading.excepthook` 未接管时只有一行默认输出）；
- 段错误、递归过深、死锁这类**原生崩溃**不经过 Python 异常机制
  ⇒ 必须靠 `faulthandler` 才能留下调用栈；
- 没有任何落盘文件 ⇒ 想反馈也只能说"它崩了"。

本模块把这三类崩溃统一写进 `~/.ai_novel_writer/crashes/` 下的 JSON 文件，
字段固定、可直接附在反馈里。

## 设计约束

| 约束 | 做法 |
|---|---|
| **绝不改变原有功能** | 只挂钩子，不替换任何业务逻辑；钩子内二次异常一律吞掉 |
| **自身绝不能崩** | 写报告全程 `try/except`，失败只记一行日志 |
| **可重复安装** | 用模块级哨兵标记，重复调用直接返回 |
| **不无限增长** | 只保留最近 `_MAX_REPORTS` 份，其余按文件名（含时间戳）删除 |
| **可测试** | 落点由参数注入，测试用 `tmp_path`，不污染真实目录 |

## 文件形态

`crashes/crash-YYYYmmdd-HHMMSS-<pid>-<kind>.json`

```json
{
  "kind": "uncaught" | "thread" | "fatal",
  "timestamp": "2026-11-25T15:04:05",
  "app_version": "3.4.1",
  "python": "3.11.9 (CPython)",
  "platform": "Windows-10-...",
  "executable": "...\\AI_NovelWriter.exe",
  "frozen": true,
  "exception": {"type": "KeyError", "message": "'x'"},
  "traceback": ["File \"...\", line 12, in ...", "..."],
  "recent_logs": ["最后 N 行诊断日志"]
}
```
"""

from __future__ import annotations

import faulthandler
import os
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Optional

from loguru import logger

from app.diagnostic_logger import resolve_log_dir
from app.storage import atomic_write_json

__all__ = ["install_crash_hooks", "write_crash_report", "resolve_crash_dir"]

#: 崩溃文件保留份数（防止长期运行把磁盘写满）
_MAX_REPORTS = 20
#: 报告里附带的最近诊断日志行数
_RECENT_LOG_LINES = 50
#: 安装标记：重复调用直接返回，避免把钩子层层套娃
_INSTALLED = False


def resolve_crash_dir(explicit: Optional[Path] = None) -> Path:
    """崩溃报告目录：显式参数 > 与诊断日志同根（`~/.ai_novel_writer/crashes`）。

    与 `diagnostic_logger.resolve_log_dir` 保持同一根目录 —— 用户反馈时
    打包一个 `.ai_novel_writer` 目录即可，不必在两处找文件。
    """
    if explicit is not None:
        return Path(explicit)
    return resolve_log_dir().parent / "crashes"


def _app_version() -> str:
    try:
        from app import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001 - 版本读不到不该影响崩溃报告本身
        return "unknown"


def _recent_logs(log_dir: Path) -> list[str]:
    """取最近一份按日分片的诊断日志的末尾若干行（读不到就返回空）。"""
    try:
        shards = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.name, reverse=True)
        if not shards:
            return []
        lines = shards[0].read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-_RECENT_LOG_LINES:]
    except Exception:  # noqa: BLE001
        return []


def _prune(crash_dir: Path) -> None:
    """只保留最近 `_MAX_REPORTS` 份；文件名含时间戳，按名排序即按时间排序。"""
    try:
        reports = sorted(crash_dir.glob("crash-*.json"), key=lambda p: p.name, reverse=True)
        for old in reports[_MAX_REPORTS:]:
            old.unlink(missing_ok=True)
    except OSError:  # 清理失败只可能是文件系统问题，不影响主流程
        pass


def write_crash_report(
    kind: str,
    exc_type: Optional[type[BaseException]] = None,
    exc: Optional[BaseException] = None,
    tb: Optional[TracebackType] = None,
    *,
    crash_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> Optional[Path]:
    """写一份崩溃报告，返回文件路径；任何环节失败都返回 `None`，**绝不抛异常**。

    `kind` 取 `uncaught`（主线程）/ `thread`（子线程）/ `fatal`（原生）。
    """
    try:
        target_dir = resolve_crash_dir(crash_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = target_dir / f"crash-{stamp}-{os.getpid()}-{kind}.json"

        payload: dict[str, Any] = {
            "kind": kind,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "app_version": _app_version(),
            "python": f"{platform.python_version()} ({platform.python_implementation()})",
            "platform": platform.platform(),
            "executable": sys.executable,
            # PyInstaller 打包后为 True —— 用户反馈时用它区分"源码运行"与"EXE 运行"
            "frozen": bool(getattr(sys, "frozen", False)),
            "exception": {
                "type": exc_type.__name__ if exc_type else "",
                "message": str(exc) if exc is not None else "",
            },
            "traceback": [],
            "recent_logs": _recent_logs(Path(log_dir) if log_dir else resolve_log_dir()),
        }

        if exc is not None and tb is not None:
            payload["traceback"] = traceback.format_exception(exc_type, exc, tb)
        elif tb is not None:
            payload["traceback"] = traceback.format_tb(tb)

        # 走统一原子写（tmp + os.replace）：崩溃场景磁盘本就不稳定，
        # 半写的 JSON 会变成"看起来有报告、其实解析不了"的假现场。
        atomic_write_json(path, payload, indent=2)
        _prune(target_dir)
        return path
    except Exception as exc_write:  # noqa: BLE001 - 报告失败绝不能掩盖原始崩溃
        try:
            logger.debug(f"[crash] 崩溃报告写入失败：{exc_write}")
        except Exception as exc_log:  # noqa: BLE001 - 连日志都写不了时只剩 stderr
            print(f"[crash] 报告与日志均不可用：{exc_log}", file=sys.stderr)
        return None


def install_crash_hooks(
    *,
    crash_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
    enable_faulthandler: bool = True,
) -> bool:
    """接管三类崩溃出口，返回是否本次真正安装（重复调用返回 `False`）。

    - `sys.excepthook`：主线程未捕获异常
    - `threading.excepthook`：子线程未捕获异常（Python 3.8+）
    - `faulthandler`：原生崩溃（段错误 / 递归溢出 / 死锁超时）

    原有的 `excepthook` 会被**链式调用**：本仓只负责落盘，不吞掉原行为
    （例如某些环境下 `tkinter` 或调试器依赖默认输出）。
    """
    global _INSTALLED
    if _INSTALLED:
        return False

    target_dir = resolve_crash_dir(crash_dir)
    resolved_log_dir = Path(log_dir) if log_dir else resolve_log_dir()

    prev_hook = sys.excepthook

    def _hook(exc_type, exc, tb) -> None:
        write_crash_report("uncaught", exc_type, exc, tb, crash_dir=target_dir, log_dir=resolved_log_dir)
        try:
            prev_hook(exc_type, exc, tb)
        except Exception as exc_chain:  # noqa: BLE001 - 原 hook 可能是调试器/IDE 的，抛错不能掩盖原始崩溃
            logger.debug(f"[crash] 原 excepthook 调用失败（已忽略）：{exc_chain}")

    sys.excepthook = _hook

    # 子线程：Python 3.8+，`args.exc_type/exc_value/exc_traceback` 可能为 None（解释器退出期）
    if hasattr(threading, "excepthook"):
        prev_thread_hook = threading.excepthook

        def _thread_hook(args) -> None:
            if args.exc_type is not None:
                write_crash_report(
                    "thread",
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                    crash_dir=target_dir,
                    log_dir=resolved_log_dir,
                )
            try:
                prev_thread_hook(args)
            except Exception as exc_chain:  # noqa: BLE001 - 原 hook 抛错不能掩盖子线程崩溃
                logger.debug(f"[crash] 原 threading.excepthook 调用失败（已忽略）：{exc_chain}")

        threading.excepthook = _thread_hook

    # 原生崩溃：写进独立文件（faulthandler 只吃文件对象，不能进 JSON）
    if enable_faulthandler:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            fatal_path = target_dir / "faulthandler.log"
            # 追加而非覆盖：同一次会话多次异常都要留痕；文件句柄必须长期存活
            fatal_file = open(fatal_path, "a", encoding="utf-8")  # noqa: SIM115 - 生命周期即进程
            faulthandler.enable(file=fatal_file, all_threads=True)
        except Exception as exc_fh:  # noqa: BLE001 - 无写权限时降级为不启用
            logger.debug(f"[crash] faulthandler 未启用：{exc_fh}")

    _INSTALLED = True
    logger.debug(f"[crash] 崩溃报告已启用，落点 {target_dir}")
    return True
