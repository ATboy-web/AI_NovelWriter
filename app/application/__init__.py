"""应用层：用例编排。只依赖 `domain` 与 `ports`，不认识文件系统细节。

## 这一层做什么

以「列出作品的分支子项目」为例，用例只负责**串联**：
从端口取 `(目录名, meta)` → 交给领域函数判定 → 组装成 `BranchRow`。

它不做的事（也是它脆弱性的来源）：
- 不遍历目录（适配器做）
- 不判断"能不能打开"（领域做）
- 不拼界面需要的键（兼容层做）
"""

from __future__ import annotations

from .build_context import BuildContext
from .generation_tree import BuildGenerationTree
from .list_branches import BranchRow, ListBranches
from .long_chapter import GenerateLongChapter
from .save_chapter import SaveChapter, SaveChapterResult
from .writing_stages import AnalyzePlot, EvaluateReview, GenerateDraft, ReviseDraft, StageDeps

__all__ = [
    "AnalyzePlot",
    "BranchRow",
    "BuildContext",
    "BuildGenerationTree",
    "EvaluateReview",
    "GenerateDraft",
    "GenerateLongChapter",
    "ListBranches",
    "ReviseDraft",
    "SaveChapter",
    "SaveChapterResult",
    "StageDeps",
]
