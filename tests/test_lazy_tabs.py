"""页签懒加载的契约。

## 为什么

`_build_reader_ui` 本身约 43ms，但它在启动时就构建 —— 而用户打开软件
几乎总是先看"章节内容"。改为首次切换时构建。

真正要防的回归是三条：
1. **不切换就不构建**（否则懒加载白做）；
2. **切过去要构建**（否则页签空白，功能消失）；
3. **重复切换不重建**（否则每次切页都卡一下，还泄漏控件）；
4. 构建抛异常时**不能把界面带崩**，也不能无限重试。
"""

from __future__ import annotations


class _FakeNotebook:
    """只实现 `select()`，够被测逻辑用。"""

    def __init__(self, current: str):
        self._current = current

    def select(self):
        return self._current


class _FakeFrame:
    def __init__(self, name: str):
        self._name = name

    def __str__(self):
        return self._name


def _make_shell(current: str, builder):
    """造一个只带懒加载所需字段的实例。"""
    from app.shell_ui import ShellMixin

    obj = ShellMixin.__new__(ShellMixin)
    obj.notebook = _FakeNotebook(current)
    obj._lazy_tabs = {"reader": [_FakeFrame("frameA"), builder, False]}
    return obj


class TestLazyTabLoading:
    def test_not_built_while_other_tab_active(self):
        calls = []
        shell = _make_shell("frameB", lambda parent: calls.append(parent))
        shell._on_tab_changed_lazy()
        assert calls == [], "没切过去就构建了，懒加载没意义"

    def test_built_when_switched_to(self):
        calls = []
        shell = _make_shell("frameA", lambda parent: calls.append(parent))
        shell._on_tab_changed_lazy()
        assert len(calls) == 1
        assert shell._lazy_tabs["reader"][2] is True, "构建后必须置位，否则会重复构建"

    def test_not_rebuilt_on_repeat(self):
        calls = []
        shell = _make_shell("frameA", lambda parent: calls.append(parent))
        for _ in range(3):
            shell._on_tab_changed_lazy()
        assert len(calls) == 1, f"重复构建了 {len(calls)} 次"

    def test_builder_exception_does_not_propagate(self):
        def boom(parent):
            raise RuntimeError("构建炸了")

        shell = _make_shell("frameA", boom)
        shell._on_tab_changed_lazy()  # 不抛即通过
        assert shell._lazy_tabs["reader"][2] is True, "失败也要置位，否则每次切页都撞同一个异常"

    def test_missing_state_is_noop(self):
        """未注册懒加载页签时（例如旧实例）不应该崩。"""
        from app.shell_ui import ShellMixin

        obj = ShellMixin.__new__(ShellMixin)
        obj.notebook = _FakeNotebook("x")
        obj._on_tab_changed_lazy()  # 无 _lazy_tabs，直接返回

    def test_select_failure_is_swallowed(self):
        class _Broken:
            def select(self):
                raise RuntimeError("notebook 已销毁")

        from app.shell_ui import ShellMixin

        obj = ShellMixin.__new__(ShellMixin)
        obj.notebook = _Broken()
        obj._lazy_tabs = {"reader": [_FakeFrame("a"), lambda p: None, False]}
        obj._on_tab_changed_lazy()  # 不抛
