"""字体令牌的**棘轮**（P5 第一步）。

## 为什么不一次性替换

实测（2026-09-16）：全仓 **385 处硬编码字体元组、25 个文件**，其中 55 处是计算式
（`font=("Consolas", 8 + x)`）。一次性机械替换有两个问题：

1. **命名必须按角色而非按值**：`("微软雅黑", 9)` 出现在说明文字上是「辅助」、
   出现在按钮上是「按钮文字」—— 按值去重会把 137 处全都叫成同一个名字，
   令牌层就只剩间接、没有语义。逐个判断是设计工作，不是 sed 工作。
2. **回归难以定位**：460 处一起改，视觉出问题时无法判断是哪一处。

因此本文件提供**机制 + 棘轮**：

- `UIStyle.font(role)` 是唯一入口，新代码必须用它；
- 每个文件的硬编码数量记录在 `HARDCODED_FONT_BASELINE`，**只允许减少**；
- 原生面板（P4b 三个）已经是 **0**，作为参考实现；
- 等总数降到 0，就把"原生面板为 0"收紧成"全仓为 0"，与 `ruff format` 门禁同款路径。

## 更新基线的方式

迁移某个文件后，把该文件的数字调小或删掉即可；**绝不要调大**
（`test_baseline_only_shrinks` 会拦住，并告诉你哪个文件涨了）。
"""

import ast
from pathlib import Path

import pytest

from app.ui_style import UIStyle

REPO_ROOT = Path(__file__).parent.parent
APP = REPO_ROOT / "app"
_SKIP_PARTS = {"node_modules", ".git", "dist", "build", "__pycache__"}

#: 2026-09-16 实测：合计 385 处 / 25 个文件。迁移后请**调小**对应数字。
HARDCODED_FONT_BASELINE: dict[str, int] = {
    "app/ai_settings_ui.py": 1,
    "app/character_ui.py": 54,
    "app/editor_ui.py": 5,
    "app/fullscreen_writer.py": 11,
    "app/generation_ui.py": 27,
    "app/lifecycle_ui.py": 63,
    "app/outline_ui.py": 8,
    "app/panels/adapt_panel.py": 2,
    "app/panels/batch_ops_panel.py": 8,
    "app/panels/bridges_panel.py": 2,
    "app/panels/chapter_analysis_panel.py": 15,
    "app/panels/descriptions_panel.py": 2,
    "app/panels/dialogue_panel.py": 2,
    "app/panels/elements_panel.py": 2,
    "app/panels/memory_viz_panel.py": 6,
    "app/panels/story_flow_panel.py": 8,
    "app/panels/style_panel.py": 2,
    "app/panels/summary_mgmt_panel.py": 10,
    "app/panels/websearch_panel.py": 12,
    "app/reader_ui.py": 15,
    "app/shell_ui.py": 69,
    "app/timeline_ui.py": 37,
    "app/toolkit_ui.py": 11,
    "app/usage_ui.py": 4,
    "app/writing_skills_panel.py": 9,
}

#: 已完成令牌化的文件（参考实现，必须保持 0）
MIGRATED_FILES = (
    "app/panels/timeline_panel.py",
    "app/panels/biography_panel.py",
    "app/panels/lineage_panel.py",
    "app/panels/host.py",
)


def _is_literal_tuple(value) -> bool:
    """值是**元组字面量**才算硬编码；`UIStyle.font("label")` 不算。"""
    return isinstance(value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in value.elts)


def _hardcoded_fonts(source: str) -> int:
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "font" and _is_literal_tuple(node.value):
            count += 1
        elif isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "font" and _is_literal_tuple(val):
                    count += 1
    return count


def _current_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(APP.rglob("*.py")):
        if any(part in _SKIP_PARTS for part in path.parts):
            continue
        number = _hardcoded_fonts(path.read_text(encoding="utf-8"))
        if number:
            counts[path.relative_to(REPO_ROOT).as_posix()] = number
    return counts


# ============================================================ 令牌本身


class TestFontRoles:
    def test_every_role_is_a_valid_tk_font_tuple(self):
        """令牌值必须是 Tk 能接受的形态：`(family, size)` 或 `(family, size, style)`。"""
        for role, value in UIStyle.FONT_ROLES.items():
            assert isinstance(value, tuple), f"{role} 不是元组"
            assert 2 <= len(value) <= 3, f"{role} 元素个数应为 2~3，实际 {len(value)}"
            family, size = value[0], value[1]
            assert isinstance(family, str), f"{role} 字体族应为 str"
            assert isinstance(size, int) and size > 0, f"{role} 字号应为正整数"
            if len(value) == 3:
                assert value[2] in ("bold", "italic", "normal"), f"{role} 样式非法：{value[2]}"

    def test_roles_are_immutable(self):
        """元组天然不可变；确保没有角色用了 list（会被 Tk 拒绝）。"""
        assert all(isinstance(v, tuple) for v in UIStyle.FONT_ROLES.values())

    def test_font_returns_the_declared_value(self):
        for role, value in UIStyle.FONT_ROLES.items():
            assert UIStyle.font(role) == value

    def test_unknown_role_falls_back_without_raising(self):
        """未知角色回落 —— 拼错不该让整个面板构建失败。"""
        assert UIStyle.font("不存在的角色") == UIStyle.FONT_ROLES["body"]

    def test_default_role_is_body(self):
        assert UIStyle.font() == UIStyle.FONT_ROLES["body"]

    def test_declared_role_names_cover_the_dominant_literals(self):
        """覆盖率下限：实测用量最大的几种元组必须都能用令牌表达。"""
        for value in (
            ("微软雅黑", 8),
            ("微软雅黑", 9),
            ("微软雅黑", 9, "bold"),
            ("微软雅黑", 10),
            ("微软雅黑", 10, "bold"),
            ("微软雅黑", 11, "bold"),
            ("微软雅黑", 12, "bold"),
            ("", 11, "bold"),
        ):
            assert value in set(UIStyle.FONT_ROLES.values()), f"缺少可用令牌表达：{value}"


class TestRoleNameUsage:
    def test_every_role_used_in_source_is_declared(self):
        """扫全仓 `UIStyle.font("x")` 的字面参数 —— 拼错直接失败（不靠回落掩盖）。

        ⚠️ 必须先 `strip_noise`：`UIStyle.font()` 的 docstring 里为了举例写了
        `UIStyle.font("x")`，裸扫会把说明文字当成真实用法
        （本仓第四次踩这个坑，见 `tests/_source_scan.py` 的模块文档）。
        """
        import re
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        import _source_scan as _scan

        pattern = re.compile(r"""UIStyle\.font\(\s*['"]([^'"]*)['"]""")
        bad: list[str] = []
        used: set[str] = set()
        for path in sorted(APP.rglob("*.py")):
            if any(part in _SKIP_PARTS for part in path.parts):
                continue
            code = _scan.strip_noise(path.read_text(encoding="utf-8"))
            for role in pattern.findall(code):
                used.add(role)
                if role not in UIStyle.FONT_ROLES:
                    bad.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {role!r}")
        assert used, "全仓都还没用上字体令牌？（至少迁移过的 4 个文件应当有）"
        assert bad == [], f"以下角色名未在 FONT_ROLES 中声明：{bad}"


class TestNativePanelsAreMigrated:
    @pytest.mark.parametrize("rel", MIGRATED_FILES)
    def test_migrated_files_have_zero_hardcoded_fonts(self, rel):
        """参考实现：这 4 个文件必须全部走令牌。"""
        assert _hardcoded_fonts((REPO_ROOT / rel).read_text(encoding="utf-8")) == 0, (
            f"{rel} 又出现了硬编码字体元组 —— 请改用 UIStyle.font(<角色>)"
        )

    def test_migrated_files_use_the_token_api(self):
        for rel in MIGRATED_FILES:
            code = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "UIStyle.font(" in code, f"{rel} 应当使用 UIStyle.font(...)"


# ============================================================ 棘轮


class TestFontRatchet:
    def test_baseline_only_shrinks(self):
        """**棘轮**：任何文件的硬编码数量都不得增加。

        增加到说明新代码在写死字体 —— 请改用 `UIStyle.font(<角色>)`；
        若确实需要新角色，先在 `UIStyle.FONT_ROLES` 里声明它。
        """
        current = _current_counts()
        grew = []
        for name, number in current.items():
            allowed = HARDCODED_FONT_BASELINE.get(name, 0)
            if number > allowed:
                grew.append(f"{name}: {allowed} → {number}")
        assert grew == [], "以下文件的硬编码字体数量增加了：\n  " + "\n  ".join(grew)

    def test_baseline_has_no_stale_entries(self):
        """基线里不该留"已经清零"的条目 —— 否则棘轮会松掉。"""
        current = _current_counts()
        stale = [name for name in HARDCODED_FONT_BASELINE if current.get(name, 0) == 0]
        assert stale == [], f"这些文件已无硬编码，请从基线里删掉：{stale}"

    def test_every_file_in_baseline_still_exists(self):
        missing = [name for name in HARDCODED_FONT_BASELINE if not (REPO_ROOT / name).is_file()]
        assert missing == [], f"基线引用了不存在的文件：{missing}"

    def test_total_is_tracked(self):
        """把总数钉成可比较的数字，便于在提交信息里报告进度。"""
        total = sum(_current_counts().values())
        assert total <= sum(HARDCODED_FONT_BASELINE.values())

    def test_app_and_tests_never_use_font_alone_where_a_token_exists(self):
        """新代码的软约束：`app/panels/` 下不得再出现硬编码字体（面板层已全部迁移）。"""
        offenders = {}
        for path in sorted((APP / "panels").rglob("*.py")):
            number = _hardcoded_fonts(path.read_text(encoding="utf-8"))
            if number:
                offenders[path.name] = number
        # v2 迁移面板尚未令牌化，因此在基线里的允许；基线外的直接拦截
        allowed = {Path(name).name: n for name, n in HARDCODED_FONT_BASELINE.items() if "/panels/" in name}
        grew = {k: v for k, v in offenders.items() if v > allowed.get(k, 0)}
        assert grew == {}, f"面板层新增了硬编码字体：{grew}"
