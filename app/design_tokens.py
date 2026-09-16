"""设计系统 - 设计令牌和组件样式

基于UI设计方案v3.0

------------------------------------------------------------------ v3 A3 改造
第二轮审计发现本模块与 `app/ui_style.py: UIStyle` **各有一套同值异名的颜色令牌**，
两套并存必然漂移。但本模块**不能删除** —— `tests/test_design_tokens.py` 直接
import 并有 20 个用例引用它（**测试也是调用方**）。

因此改为**单向派生**：颜色令牌的取值统一从 `UIStyle.COLORS` 取，
`DesignTokens` 只负责提供它那套语义命名（`primary` / `bg_primary` …）。
这样：
- 改主题只需要改 `UIStyle` 一处；
- 本模块的公开 API（`COLORS` / `BUTTON_PRIMARY` / …）完全不变；
- `tests/test_design_design_single_source.py` 断言派生关系，防止有人又写回字面值。

**少数刻意不派生的项**（下方逐条注明原因）：`success_light` / `error_dark`
在 `UIStyle` 里没有对应语义位的独立取值；`SPACING` / `RADIUS` / `FONTS['sizes']`
是另一套刻度（UIStyle 用 4px 基准、本模块用 4/8/12… 的另一套命名），
且被测试逐一断言了具体数值，合并会改变公开契约。
"""

from .ui_style import UIStyle


def _derive_colors() -> dict:
    """把 `UIStyle.COLORS` 的键映射到本模块的语义命名。

    映射关系写死为一张表：新增/改名时这里会 KeyError 立刻暴露，
    而不是悄悄退化成一个"看起来正常但不再同步"的颜色。
    """
    ui = UIStyle.COLORS
    return {
        # 背景色
        "bg_primary": ui["bg_dark"],  # 最深背景
        "bg_secondary": ui["bg_medium"],  # 面板背景
        "bg_card": ui["bg_card"],  # 卡片/输入框
        "bg_hover": ui["bg_hover"],  # 悬停状态
        # 边框色
        "border": ui["border"],  # 分隔线/边框
        "border_light": ui["border_light"],  # 较亮边框
        # 主色调
        "primary": ui["accent"],  # 按钮/高亮
        "primary_hover": ui["accent_hover"],  # 主色悬停
        "primary_light": ui["accent_light"],  # 主色浅色
        # 语义色
        "success": ui["success"],  # 成功
        # UIStyle 无 success_light 语义位 → 保持本模块自有取值（浅一档，用于强调）
        "success_light": "#10b981",
        "error": ui["error"],  # 错误
        # UIStyle.error_bg 是"错误背景"语义，与这里的"错误深色（悬停）"不同位
        "error_dark": "#dc2626",
        "warning": ui["warning"],  # 警告
        "info": ui["info"],  # 信息
        # 文字色
        "text_primary": ui["text_primary"],  # 主要文字
        "text_secondary": ui["text_secondary"],  # 次要文字
        "text_muted": ui["text_muted"],  # 辅助文字
        "text_inverse": ui["text_inverse"],  # 反色文字
    }


class DesignTokens:
    """设计令牌系统

    颜色取值**单一来源于** `app/ui_style.py: UIStyle`（见模块文档）。
    """

    # 颜色系统（派生自 UIStyle.COLORS）
    COLORS = _derive_colors()

    # 间距系统（本模块自有刻度；UIStyle.SPACING 是 4px 基准的另一套命名）
    SPACING = {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 24,
        "2xl": 32,
    }

    # 圆角系统
    RADIUS = {
        "sm": 4,
        "md": 8,
        "lg": 12,
        "xl": 16,
        "full": 9999,
    }

    # 字体系统
    # family / mono 派生自 UIStyle；sizes 是本模块的独立刻度（数值被测试断言）
    FONTS = {
        "family": UIStyle.FONTS["family"],
        "mono": UIStyle.FONTS["family_mono"],
        "sizes": {
            "xs": 10,
            "sm": 11,
            "md": 13,
            "lg": 15,
            "xl": 18,
            "2xl": 24,
        },
    }

    # 组件样式
    BUTTON_PRIMARY = {
        "bg": COLORS["primary"],
        "fg": COLORS["text_inverse"],
        "hover_bg": COLORS["primary_hover"],
        "active_bg": COLORS["primary"],
        "radius": RADIUS["md"],
        "padx": 16,
        "pady": 8,
        "font_size": FONTS["sizes"]["md"],
    }

    BUTTON_SECONDARY = {
        "bg": "#2a2a45",
        "fg": COLORS["text_secondary"],
        "hover_bg": COLORS["bg_hover"],
        "border": COLORS["border_light"],
        "radius": RADIUS["md"],
        "padx": 16,
        "pady": 8,
        "font_size": FONTS["sizes"]["md"],
    }

    BUTTON_DANGER = {
        "bg": COLORS["error"],
        "fg": COLORS["text_inverse"],
        "hover_bg": COLORS["error_dark"],
        "radius": RADIUS["md"],
        "padx": 16,
        "pady": 8,
        "font_size": FONTS["sizes"]["md"],
    }

    CARD = {
        "bg": COLORS["bg_card"],
        "border": COLORS["border"],
        "radius": RADIUS["md"],
        "pad": 12,
    }

    AVATAR = {
        "size": 28,
        "radius": RADIUS["full"],
        "font_size": FONTS["sizes"]["sm"],
        "font_weight": 500,
    }
