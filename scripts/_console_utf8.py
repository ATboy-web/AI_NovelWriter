"""让脚本的输出在非 UTF-8 控制台上不崩（Windows / cp1252、部分 CI runner）。

## 为什么要单独一个模块

这个坑本项目踩了**两次**，两次都造成真实后果：

1. `fix_release_metadata.py` 里的 `✓` —— 当时只修了那一个脚本；
2. `release_notes.py` 里的 `已写入 …（N 字符）` —— CI 的 Windows runner 控制台是
   **cp1252**，`print` 中文直接抛 `UnicodeEncodeError`，进程以 1 退出
   ⇒ `Create Release` 步骤被跳过、**Release 没能发布**。

第 2 次尤其难查：崩点发生在**文件已经写完之后**，产物其实是好的，
所以"本地手动跑一遍"也可能是好的（取决于本机控制台编码），而 CI 上必然失败。

做成公共模块就是为了让"新增脚本"不必记得这件事 —— 同一类修复写第二遍时，
第二处没被覆盖只是时间问题。
"""

from __future__ import annotations

import sys

__all__ = ["make_stdout_utf8_safe"]


def make_stdout_utf8_safe() -> None:
    """把标准输出/错误切到 UTF-8（无法编码的字符显示为 `?`，不再中断流程）。

    幂等，可重复调用；对已被重定向成非 `TextIOWrapper` 的流自动跳过。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 流已关闭、是只读包装、或本身不支持改编码 —— 都不是致命情况
            continue
