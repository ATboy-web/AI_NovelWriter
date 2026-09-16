"""导入健康度守卫。

## 为什么需要它

`app/__init__.py` 对可选模块用 `_safe_import`：导入失败**不抛异常**，而是返回一个
`_ImportStub` 子类 —— 目的是"缺可选依赖时整个包还能起来"。代价是**失败被静默降级**：
类还在、名字还在，只有真正实例化时才炸。

本轮就真实踩到：给 `app/fullscreen_writer.py` 加模块级 `from app import UIStyle` 造成
循环引用（`app/__init__` 在定义 UIStyle 之前就导入它），`FullscreenWriter` 当场变成桩 ——
**测试全绿，只有一条 warning**。若不是那条 warning，这个"全屏写作窗口无法打开"的
回归会一直留在发布版里。

因此本文件把"不允许静默降级"变成断言。
"""

from __future__ import annotations

import importlib
import pkgutil
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "app"

#: 子模块导入失败时，这些名字会被替换成桩 —— 必须逐个验证是真身
GUARDED_EXPORTS = (
    "ImageGenerator",
    "SceneDetector",
    "MemoryManager",
    "NoteManager",
    "FullscreenWriter",
    "NovelAgent",
    "ReadingManager",
    "UIStyle",
)


def test_no_guarded_export_is_an_import_stub():
    """任何一个被 `_safe_import` 兜住的导出都不得是桩。"""
    import app

    degraded = []
    for name in GUARDED_EXPORTS:
        obj = getattr(app, name, None)
        assert obj is not None, f"app.{name} 不存在"
        if issubclass(obj, app._ImportStub):
            degraded.append(f"{name}: {obj._import_error}")
    assert degraded == [], "以下模块导入失败并被静默降级为占位符：\n  " + "\n  ".join(degraded)


def test_importing_app_emits_no_degradation_warning():
    """导入 `app` 的过程不得出现"Failed to import"告警（即不得发生降级）。"""
    import app  # noqa: F401  - 确保已在 sys.modules 里

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(app)
    offenders = [str(w.message) for w in caught if "Failed to import" in str(w.message)]
    assert offenders == [], "导入 app 时发生降级：\n  " + "\n  ".join(offenders)


def _app_submodules() -> list[str]:
    names = []
    for info in pkgutil.walk_packages([str(APP)], prefix="app."):
        if info.name.endswith(".__main__"):
            continue
        names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", _app_submodules())
def test_each_app_submodule_imports(module_name):
    """每个子模块都必须能独立导入（循环引用会在这里暴露）。"""
    importlib.import_module(module_name)
