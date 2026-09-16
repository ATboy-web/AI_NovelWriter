"""字体令牌的**棘轮** —— P5 已完成，本文件现在是**零容忍门禁**。

## 历程（值得留档的方法论）

2026-09-16 实测：全仓 **385 处硬编码字体元组、25 个文件**（其中 55 处是计算式
`font=("Consolas", 8 + x)`）。当时**没有**一次性机械替换，理由是：

1. **命名必须按角色而非按值**：`("微软雅黑", 9)` 出现在说明文字上是「辅助」、
   出现在按钮上是「按钮文字」—— 按值去重会把 137 处全都叫成同一个名字；
2. **回归难以定位**：385 处一起改，视觉出问题时无法判断是哪一处。

于是先落"机制 + 棘轮"：`UIStyle.font(role)` 是唯一入口、每个文件的硬编码数量记进
`HARDCODED_FONT_BASELINE` 只许减少。

**2026-09-17 收尾**：枚举后发现 385 处**只对应 21 种取值**，其中 15 种已有令牌
（覆盖 375 处），只差 6 种取值 / 10 处。补齐令牌后，剩余替换全部是**等值替换**
（令牌值 == 原字面量，逐条断言），因此可以机械完成且**视觉零变化可证**。
棘轮基线随之清空，本文件收紧为"全仓不得有硬编码字体元组"。

⚠️ 迁移脚本翻过的车（判据必须自检）：`ast` 的 `col_offset` 是 **UTF-8 字节偏移**，
按字符切片会在含中文的行上错位，第一版把 25 个文件全写坏了。现在脚本内置换算 +
**写盘前 `ast.parse` 自检** + "替换前后字体取值多重集必须一致"。
"""

import ast
from pathlib import Path

import pytest

from app.ui_style import UIStyle

REPO_ROOT = Path(__file__).parent.parent
APP = REPO_ROOT / "app"
_SKIP_PARTS = {"node_modules", ".git", "dist", "build", "__pycache__"}

#: **已清零**（2026-09-17）。此后只允许保持空：
#: 若某文件出现硬编码字体元组，`test_no_hardcoded_fonts_anywhere` 会直接失败。
HARDCODED_FONT_BASELINE: dict[str, int] = {}

#: 参考实现（最早完成令牌化的文件），保持 0
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
    def test_no_hardcoded_fonts_anywhere(self):
        """**收紧后的零容忍门禁**（P5 已收尾）：全仓不得再出现字体字面量。

        新代码一律 `UIStyle.font(<角色>)`；确需新字号时，先在 `UIStyle.FONT_ROLES`
        声明角色（这样"字号"这件事始终只有一个定义处）。
        """
        current = _current_counts()
        assert current == {}, "以下文件出现了硬编码字体元组，请改用 UIStyle.font(<角色>)：\n  " + "\n  ".join(
            f"{name}: {number} 处" for name, number in sorted(current.items())
        )

    def test_baseline_is_empty(self):
        """基线必须保持为空 —— 留着旧数字会让棘轮松掉。"""
        assert HARDCODED_FONT_BASELINE == {}

    def test_baseline_only_shrinks(self):
        """（保留原判据，基线为空时退化为"任何文件都不得有"）"""
        current = _current_counts()
        grew = [
            f"{name}: {HARDCODED_FONT_BASELINE.get(name, 0)} → {number}"
            for name, number in current.items()
            if number > HARDCODED_FONT_BASELINE.get(name, 0)
        ]
        assert grew == [], "以下文件的硬编码字体数量增加了：\n  " + "\n  ".join(grew)

    def test_total_is_tracked(self):
        """把总数钉成可比较的数字，便于在提交信息里报告进度（现应为 0）。"""
        total = sum(_current_counts().values())
        assert total == 0

    def test_baseline_has_no_stale_entries(self):
        """基线里不该留"已经清零"的条目 —— 否则棘轮会松掉。"""
        current = _current_counts()
        stale = [name for name in HARDCODED_FONT_BASELINE if current.get(name, 0) == 0]
        assert stale == [], f"这些文件已无硬编码，请从基线里删掉：{stale}"

    def test_every_file_in_baseline_still_exists(self):
        missing = [name for name in HARDCODED_FONT_BASELINE if not (REPO_ROOT / name).is_file()]
        assert missing == [], f"基线引用了不存在的文件：{missing}"

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
