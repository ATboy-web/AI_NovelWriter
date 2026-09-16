"""设计系统单一源断言（v3 A3）。

`app/design_tokens.py` 与 `app/ui_style.py` 曾各有一套同值异名的颜色令牌。
现在 `DesignTokens.COLORS` **派生自** `UIStyle.COLORS`。

本文件的作用是防止这次收敛被回退：只要有人在 `design_tokens.py` 里把某个
颜色写回字面值，或改了 `UIStyle` 而没同步映射表，这里就会失败。

⚠️ 刻意不派生的项也在下面显式列出 —— 写清楚"哪些是例外"，
比留一个模糊的"大部分应该一致"更有约束力。
"""

from app.design_tokens import DesignTokens, _derive_colors
from app.ui_style import UIStyle

#: DesignTokens 的语义名 → UIStyle 的令牌名（单一源的映射关系）
DERIVED_COLOR_MAP = {
    "bg_primary": "bg_dark",
    "bg_secondary": "bg_medium",
    "bg_card": "bg_card",
    "bg_hover": "bg_hover",
    "border": "border",
    "border_light": "border_light",
    "primary": "accent",
    "primary_hover": "accent_hover",
    "primary_light": "accent_light",
    "success": "success",
    "error": "error",
    "warning": "warning",
    "info": "info",
    "text_primary": "text_primary",
    "text_secondary": "text_secondary",
    "text_muted": "text_muted",
    "text_inverse": "text_inverse",
}

#: 有意保留本模块自有取值（UIStyle 无对应语义位），修改需走 review
INTENTIONALLY_INDEPENDENT_COLORS = {"success_light", "error_dark"}


class TestColorsAreDerived:
    def test_every_mapped_key_matches_ui_style(self):
        for token_name, ui_name in DERIVED_COLOR_MAP.items():
            assert DesignTokens.COLORS[token_name] == UIStyle.COLORS[ui_name], (
                f"{token_name} 应与 UIStyle.COLORS[{ui_name!r}] 一致（单一定义在 ui_style）"
            )

    def test_no_color_key_is_left_behind(self):
        """每个 COLORS 键要么在映射表里，要么在例外清单里 —— 不允许"新增的漏网之鱼"。"""
        known = set(DERIVED_COLOR_MAP) | INTENTIONALLY_INDEPENDENT_COLORS
        assert set(DesignTokens.COLORS) == known

    def test_derive_is_idempotent(self):
        assert _derive_colors() == DesignTokens.COLORS

    def test_changing_ui_style_propagates(self, monkeypatch):
        """真正的证明：改 UIStyle 后 DesignTokens 必须跟着变。"""
        patched = dict(UIStyle.COLORS)
        patched["accent"] = "#123456"
        monkeypatch.setattr(UIStyle, "COLORS", patched)
        assert _derive_colors()["primary"] == "#123456"

    def test_missing_token_fails_loudly(self, monkeypatch):
        """UIStyle 少了令牌时必须直接报错，而不是静默退化。"""
        patched = {k: v for k, v in UIStyle.COLORS.items() if k != "accent"}
        monkeypatch.setattr(UIStyle, "COLORS", patched)
        try:
            _derive_colors()
        except KeyError:
            return
        raise AssertionError("UIStyle 缺少 accent 时应抛 KeyError")


class TestFontsAndComponentStyles:
    def test_font_family_is_derived(self):
        assert DesignTokens.FONTS["family"] == UIStyle.FONTS["family"]
        assert DesignTokens.FONTS["mono"] == UIStyle.FONTS["family_mono"]

    def test_component_styles_still_reference_colors(self):
        """组件样式必须继续引用 COLORS（而不是自己写死颜色）。"""
        assert DesignTokens.BUTTON_PRIMARY["bg"] == DesignTokens.COLORS["primary"]
        assert DesignTokens.BUTTON_PRIMARY["hover_bg"] == DesignTokens.COLORS["primary_hover"]
        assert DesignTokens.BUTTON_DANGER["bg"] == DesignTokens.COLORS["error"]
        assert DesignTokens.CARD["bg"] == DesignTokens.COLORS["bg_card"]

    def test_public_api_surface_unchanged(self):
        """公开 API 必须保持不变 —— 测试与文档都在用它。"""
        for attr in (
            "COLORS",
            "SPACING",
            "RADIUS",
            "FONTS",
            "BUTTON_PRIMARY",
            "BUTTON_SECONDARY",
            "BUTTON_DANGER",
            "CARD",
            "AVATAR",
        ):
            assert hasattr(DesignTokens, attr), f"缺少公开属性 {attr}"
