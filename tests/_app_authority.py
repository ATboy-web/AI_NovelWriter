"""保证"仓库根目录的 `app` 包"是测试进程里的那一个。

## 为什么需要这个模块

本仓库有 **三个名为 `app` 的包**：

| 路径 | 用途 | `__version__` |
|---|---|---|
| `app/` | 桌面端主程序 | 与 `pyproject.toml` 一致 |
| `backend/ai-service/app/` | AI 服务 | 硬编码 `"1.0.0"` |
| `backend/novel-service/app/` | 小说生成服务 | 硬编码 `"1.0.0"` |

`import app` 取哪一个**完全由 `sys.path` 顺序决定**，而测试代码会往 `sys.path` 插目录。
2026-09-17 的发布事故就是这么来的：`backend/tests/test_generators.py` 为了导入
novel-service 的生成器，把 `backend/novel-service` 插到 `sys.path[0]`，
于是**整个测试进程的 `import app` 都指向了后端那个包**，
`tests/test_version_consistency.py` 读到 `app.__version__ == '1.0.0'`：

- 本地永远复现不了（本地没有走同一条路径）；
- 失败信息只有一句"版本不一致"，看不出是**读错了包**；
- 后果是 `Tests` 三个作业全红 ⇒ `Build EXE & Release` 被跳过 ⇒ **Release 没建出来**。

这种失败模式（"同名包被静默替换"）会污染的不只是版本断言 —— 任何 `import app`
的用例都可能在实际测试后端代码。所以这里把它收束成一条可断言的不变量，
而不是在每个用例里各写一段 `sys.path` 防御。
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = [
    "ROOT",
    "app_conflicts",
    "describe_app_authority",
    "restore_root_app_authority",
]

#: 仓库根目录（本文件在 `tests/` 下）
ROOT = Path(__file__).resolve().parent.parent

#: 与仓库根下的 `app` 同名的其它包所在目录（相对仓库根）
SHADOWING_DIRS = ("backend/ai-service", "backend/novel-service")


def _is_root_app(module: object) -> bool:
    """该模块对象是不是仓库根下的 `app`。"""
    file = getattr(module, "__file__", None)
    if not file:
        return False
    try:
        return Path(file).resolve() == (ROOT / "app" / "__init__.py").resolve()
    except OSError:  # pragma: no cover - 路径异常时保守判否
        return False


def app_conflicts() -> list[str]:
    """排在仓库根**之前**、会劫持 `import app` 的 `sys.path` 条目。

    "存在于 `sys.path`"本身不算问题：`backend/tests/test_generators.py` 确实需要
    把 `backend/novel-service` 放上去才能导入它的生成器。
    真正致命的是**顺序** —— 它一旦排到仓库根前面，`import app` 就指向后端包，
    于是 `tests/` 里的用例会在不知情的情况下测后端代码。
    """
    resolved_root = ROOT.resolve()
    shadow_dirs = [ROOT / name for name in SHADOWING_DIRS]
    usable = [d for d in shadow_dirs if (d / "app" / "__init__.py").is_file()]

    positions = [index for index, entry in enumerate(sys.path) if Path(entry or ".").resolve() == resolved_root]
    if not positions:
        # 仓库根不在 sys.path 上：所有影子目录都算冲突
        return [str(d) for d in usable]

    root_index = positions[0]
    found: list[str] = []
    for entry in sys.path[:root_index]:
        candidate = Path(entry or ".").resolve()
        for shadow in usable:
            if candidate == shadow.resolve():
                found.append(str(shadow))
    return found


def describe_app_authority() -> str:
    """当前 `app` 解析状态的可读描述（断言失败时用）。"""
    module = sys.modules.get("app")
    resolved = getattr(module, "__file__", None) or "(尚未导入)"
    return (
        f"sys.modules['app'] = {resolved}\n"
        f"sys.path[0] = {sys.path[0] if sys.path else '(空)'}\n"
        f"sys.path 里会劫持 app 的条目 = {app_conflicts() or '无'}"
    )


def restore_root_app_authority() -> list[str]:
    """把"仓库根的 `app` 优先"恢复成不变量，返回本次修好的项（便于诊断/测试）。

    做三件事：

    1. 仓库根回到 `sys.path[0]`（它被后端测试的 `insert(0, ...)` 挤到了后面）；
    2. 若 `sys.modules['app']` 已被后端同名包占用，丢弃它及其子模块 ——
       下一次 `import app` 才会按新顺序重新解析（已在别处持有的引用不受影响）；
    3. 若 `app` 尚未导入，则主动导入一次并校验，让问题在**此处**暴露而不是
       在某个不相关的用例里以奇怪数字出现。
    """
    fixed: list[str] = []
    root = str(ROOT)

    if not sys.path or sys.path[0] != root:
        if root in sys.path:
            sys.path.remove(root)
        sys.path.insert(0, root)
        fixed.append("sys.path 顺序")

    module = sys.modules.get("app")
    if module is not None and not _is_root_app(module):
        hijacked = getattr(module, "__file__", "?")
        for name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
            sys.modules.pop(name, None)
        fixed.append(f"sys.modules['app'] 曾被劫持为 {hijacked}")

    import app as imported  # noqa: PLC0415 - 必须在修正顺序之后才能导入

    if not _is_root_app(imported):
        raise RuntimeError("`import app` 仍解析到仓库根之外的包，测试结果不可信。\n" + describe_app_authority())
    return fixed
