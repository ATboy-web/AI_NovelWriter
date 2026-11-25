"""领域层：作品、角色、记忆、世界线、规则 —— **不依赖任何其它 app 模块**。

## 这一层的边界（重要）

允许：标准库、`dataclasses`、`typing`。
禁止：`app.storage` / `app.ai_client` / `app.panels.*` / `tkinter` / 任何 Provider SDK。

理由见 `tests/test_architecture_layers.py`：那里有一条断言在**扫源码**，
一旦有人在本层 import 了上层模块，测试立刻变红。这条约束比文档可靠 ——
文档会过期，断言不会。

## 当前状态

这是**渐进式迁移的样板**，尚未全量搬迁。已迁入的只有 `branch`（分支子项目的领域视图）。
其余领域逻辑（代际继承、角色状态推进、伏笔等）仍在 `app/lineage.py` 等旧模块里，
按「先跑通一个用例、再逐个搬迁」的节奏推进。
"""

from __future__ import annotations

from .branch import BranchInfo, describe_branch

__all__ = ["BranchInfo", "describe_branch"]
