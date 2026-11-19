"""UI 布局健康守卫：防止"控件被压扁"和"滚轮失灵"复发。

## 为什么需要

这两个缺陷都不是"代码写错"，而是**布局模型用错**导致的行为：
- `pack(side=LEFT)` 空间不足时**不换行**，直接把最后一个控件压到接近 0
  （实测「详情」按钮 `w=8 / req=43`，文字完全不可见、点不中）；
- Tk 的 `<MouseWheel>` **不冒泡**，只绑容器时鼠标停在内容上就滚不动
  （实测 0.000 → 0.000）。

两者都"能跑、不报错、测试全绿"，只有真渲染出来才看得见。
所以这里用真 Tk 渲染 + 源码结构守卫两条腿。
"""

from __future__ import annotations

import pathlib

import _tk_harness
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


# ====================================================================== 滚轮必须冒泡到子树


@pytest.mark.skipif(not _tk_harness.tk_available(), reason="无可用 Tk 环境")
class TestWheelBindsToWholeTree:
    @pytest.fixture()
    def root(self):
        root = _tk_harness.create_root()
        yield root
        try:
            root.destroy()
        except Exception:
            pass

    def test_binds_descendants_not_just_container(self, root):
        """只绑容器 = 鼠标停在按钮上滚不动（本次真实事故）。"""
        import tkinter as tk

        from app.ui_scroll import bind_wheel_to_tree

        container = tk.Frame(root)
        container.pack()
        buttons = [tk.Button(container, text=f"b{i}") for i in range(3)]
        for btn in buttons:
            btn.pack()

        calls: list = []

        def handler(event):
            calls.append(event)

        bound = bind_wheel_to_tree(container, handler)
        assert bound >= 4, f"应绑定容器 + 3 个子件，实际 {bound}"

        # 判据用"绑定脚本存在"而不是 event_generate：
        # 未映射窗口上的合成事件不会投递（实测 calls 恒为空，与被测行为无关）。
        assert container.bind("<MouseWheel>"), "容器本身没绑上"
        for index, btn in enumerate(buttons):
            assert btn.bind("<MouseWheel>"), f"第 {index} 个按钮没绑上（鼠标停在它上面就滚不动）"

    def test_survives_widget_without_bind(self):
        """个别控件 bind 受限不该中断整棵子树。"""
        import tkinter as tk

        from app.ui_scroll import bind_wheel_to_tree

        root = _tk_harness.create_root()
        try:
            frame = tk.Frame(root)
            tk.Label(frame, text="x").pack()
            count = bind_wheel_to_tree(frame, lambda e: None)
            assert count >= 2
        finally:
            root.destroy()

    def test_returns_count_for_diagnostics(self, root):
        """返回值用于"绑了多少个"的自检（本次靠它发现只绑了空壳）。"""
        import tkinter as tk

        from app.ui_scroll import bind_wheel_to_tree

        empty = tk.Frame(root)
        empty.pack()
        assert bind_wheel_to_tree(empty, lambda e: None) == 1, "空容器应只绑定自己"


# ====================================================================== 布局结构守卫


class TestSidebarButtonLayout:
    """角色按钮条必须用 grid 等分，不能回退到 pack 平铺。

    pack 在 223px 里排 5 个按钮时，最后一个会被压成 8px —— 这是回归的精确条件。
    """

    @staticmethod
    def _source() -> str:
        return (REPO / "app" / "shell_ui.py").read_text(encoding="utf-8")

    def test_character_buttons_use_grid_with_weight(self):
        source = self._source()
        start = source.index("# 角色操作按钮")
        end = source.index("# ===== 右侧主内容区 =====")
        block = source[start:end]

        assert ").grid(row=" in block, "角色按钮条又用回 pack 平铺了（最后一个会被压扁）"
        assert "columnconfigure(_col, weight=1)" in block, "缺少列权重，容器变窄时不会等比缩小"

    def test_no_pack_side_left_in_that_block(self):
        source = self._source()
        start = source.index("# 角色操作按钮")
        end = source.index("# ===== 右侧主内容区 =====")
        block = source[start:end]
        assert "pack(side=tk.LEFT" not in block, "同一行平铺多个按钮会重现 8px 问题"

    def test_all_five_entries_still_present(self):
        """改布局不能把入口弄丢。"""
        source = self._source()
        start = source.index("# 角色操作按钮")
        end = source.index("# ===== 右侧主内容区 =====")
        block = source[start:end]
        for label in ("新建", "AI生成", "传记", "补全人设", "详情"):
            assert label in block, f"按钮「{label}」不见了"


class TestLeftSidebarWheelWiring:
    """左栏必须用递归绑定，且必须在内容构建**之后**调用。

    第一次修的时候绑在了左栏刚创建时（内容还没建），实际一个后代都没绑上 ——
    静态看代码"调用了"，跑起来仍然是 0.000 → 0.000。
    """

    @staticmethod
    def _create_widgets_source() -> str:
        import ast

        source = (REPO / "app" / "shell_ui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_create_widgets":
                return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
        raise AssertionError("找不到 _create_widgets")

    def test_uses_tree_binding(self):
        body = self._create_widgets_source()
        assert "bind_wheel_to_tree(left_panel" in body, "左栏滚轮又只绑容器了"

    def test_binding_happens_after_content(self):
        body = self._create_widgets_source()
        bind_at = body.index("bind_wheel_to_tree(left_panel")
        content_at = body.index("# 角色操作按钮")
        assert bind_at > content_at, "递归绑定必须放在左栏内容构建之后，否则绑的是空壳"
