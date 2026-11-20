"""主题系统 —— 三套可切换的极简主义视觉体系（纯数据模块）。

## 设计决策（2026-11-20 UI 改版）

1. **单一来源**：本模块是三套主题取值的唯一权威。桌面端 `UIStyle.COLORS`
   在激活主题时**原地更新**为本模块的调色板（保持字典对象同一性，
   因为全仓大量 `C = UIStyle.COLORS` 的模块级别名必须跟着变）；
   移动端 `ThemeTokens.kt` 由 `scripts/sync_theme_tokens.py` 从本模块生成，
   `tests/test_theme_system.py` 断言两端逐值一致。
2. **不是只换主色**：每套主题完整覆盖背景色阶 / 文字色阶 / 强调色族 /
   语义色文字变体 / 边框 / 悬停 / 组件内边距（`STYLE_PARAMS`）。
   间距刻度（`SPACING_SCALE`）与字体层级三主题**统一**——极简主义要求
   跨主题、跨端同一套栅格与字阶，差异只出现在色彩与组件质感上。
3. **语义填充色跨主题恒定**（success/warning/error/info 的填充值不变）：
   "危险=红、成功=绿"的识别不随主题漂移；随背景变化的是它们的
   `*_text` 文字变体（逐主题调亮，保证 ≥4.5:1，见对比度守卫）。
4. **三主题均为深色底**：现有对比度守卫（`tests/test_panel_ui_quality.py`）
   以深色背景为前提，且 `test_ui_style.py` 断言 `bg_dark < text_primary`。
   废土主题用"暖炭底+锈橙"而非浅色纸面，正是为了守住这条不变量。
5. 本模块**不 import tkinter / ui_style**（与 `genres_data.py` 同例）：
   纯数据才能被打包脚本、同步脚本与测试无副作用地读取。

## 主题一览

| id | 名称 | 视觉语言 |
|---|---|---|
| cyberpunk | 赛博朋克 | 深蓝黑底 + 霓虹青，细边框、紧凑内边距 |
| wasteland | 废土末日 | 暖炭底 + 锈橙琥珀，低饱和、宽松内边距 |
| mechpunk | 机械朋克 |  gunmetal 钢灰底 + 工业琥珀警示色，2px 粗边框、规整内边距 |
"""

from __future__ import annotations

#: 合法主题 id（顺序即设置界面展示顺序）
THEME_IDS = ("cyberpunk", "wasteland", "mechapunk")

#: 默认主题：与改版前的深色观感最接近，老用户零突兀
DEFAULT_THEME = "cyberpunk"

#: 展示元信息（设置界面 / 移动端共用同一份文案）
THEME_META = {
    "cyberpunk": {
        "name_cn": "赛博朋克",
        "description": "深蓝黑 × 霓虹青：细边框、紧凑节奏，夜间控制台气质",
    },
    "wasteland": {
        "name_cn": "废土末日",
        "description": "暖炭 × 锈橙：低饱和大地色、宽松留白，废土手账气质",
    },
    "mechapunk": {
        "name_cn": "机械朋克",
        "description": "钢灰 × 工业琥珀：粗边框、规整栅格，机械仪表气质",
    },
}

#: 统一间距刻度（4px 基准；三主题共用，桌面 px / 移动 dp 同值）。
#: 与 UIStyle.SPACING 同值——UIStyle 侧是既有公开契约，这里声明"主题系统
#: 也覆盖间距"这一事实，守卫测试断言两处一致。
SPACING_SCALE = {"xs": 2, "sm": 4, "md": 8, "lg": 12, "xl": 16, "xxl": 24}

#: 统一字体层级（角色名两端一致；桌面 px 与 UIStyle.FONT_ROLES 同值，
#: 移动 sp 按同一角色序列映射 —— "层级结构统一"而非"像素值相同"，
#: 因为两端 DPI 语义不同）。守卫测试断言 desktop_px 与 FONT_ROLES 一致。
TYPE_SCALE = {
    "caption": {"desktop_px": 8, "mobile_sp": 11},
    "label": {"desktop_px": 9, "mobile_sp": 12},
    "body": {"desktop_px": 10, "mobile_sp": 14},
    "subtitle": {"desktop_px": 11, "mobile_sp": 16},
    "title": {"desktop_px": 12, "mobile_sp": 18},
    "heading": {"desktop_px": 14, "mobile_sp": 20},
    "display": {"desktop_px": 16, "mobile_sp": 24},
}

#: 语义填充色：跨主题恒定（决策 3）。各主题调色板直接引用，避免三处抄写漂移。
_SEMANTIC_FILLS = {
    "success": "#0f6e56",
    "success_bg": "#064e3b",
    "warning": "#f59e0b",
    "warning_bg": "#78350f",
    "error": "#ef4444",
    "error_bg": "#7f1d1d",
    "info": "#3b82f6",
    "info_bg": "#1e3a5f",
}

#: 三套完整调色板。键集必须与 UIStyle.COLORS 完全一致（守卫测试钉住）。
#: 结构别名保持不变：bg_light == bg_card、hover == bg_hover
#: （换肤时的"旧值→新值"映射依赖别名一致，否则同值不同键会产生歧义）。
THEMES: dict[str, dict[str, str]] = {
    "cyberpunk": {
        # 背景色阶 —— 深蓝黑
        "bg_dark": "#0a0e17",
        "bg_medium": "#101725",
        "bg_light": "#162032",
        "bg_card": "#162032",
        "bg_hover": "#1c2940",
        # 强调色族 —— 霓虹青（填充用深青保证白字/金字对比度）
        "accent": "#0c5f75",
        "accent_light": "#22d3ee",
        "accent_hover": "#0e7490",
        "accent_bg": "#0a3a4a",
        # 文字色阶 —— 冷白
        "text_primary": "#e6edf7",
        "text_secondary": "#a8b6cc",
        "text_muted": "#8e9db4",
        "text_inverse": "#ffffff",
        # 边框 —— 细而冷
        "border": "#243350",
        "border_light": "#31456b",
        "border_focus": "#22d3ee",
        # 悬停
        "hover": "#1c2940",
        "hover_light": "#223350",
        # 语义文字变体（逐主题调亮，≥4.5:1）
        "accent_text": "#53c6e8",
        "success_text": "#1cb88e",
        "info_text": "#639cf8",
        "error_text": "#f37777",
        # 刻意与 warning 填充色（#f59e0b）不同值：换肤按"旧值→新值"映射，
        # 同值不同键会产生歧义（守卫 test_palette_swap_map_is_unambiguous）。
        "warning_text": "#f7b32b",
        **_SEMANTIC_FILLS,
    },
    "wasteland": {
        # 背景色阶 —— 暖炭
        "bg_dark": "#14100c",
        "bg_medium": "#1c1712",
        "bg_light": "#241d16",
        "bg_card": "#241d16",
        "bg_hover": "#2c241b",
        # 强调色族 —— 锈橙
        "accent": "#9a3412",
        "accent_light": "#fb923c",
        "accent_hover": "#b45309",
        "accent_bg": "#3a1d0e",
        # 文字色阶 —— 骨白
        "text_primary": "#ede4d3",
        "text_secondary": "#b8a88f",
        "text_muted": "#a2937b",
        "text_inverse": "#ffffff",
        # 边框 —— 风化土色
        "border": "#3a2f22",
        "border_light": "#4d3f2e",
        "border_focus": "#fb923c",
        # 悬停
        "hover": "#2c241b",
        "hover_light": "#352b20",
        # 语义文字变体
        "accent_text": "#f0a868",
        "success_text": "#34c98e",
        "info_text": "#6ba3f5",
        "error_text": "#f07060",
        "warning_text": "#f5a623",
        **_SEMANTIC_FILLS,
    },
    "mechapunk": {
        # 背景色阶 —— 钢灰
        "bg_dark": "#0e1116",
        "bg_medium": "#151a21",
        "bg_light": "#1c232c",
        "bg_card": "#1c232c",
        "bg_hover": "#232c37",
        # 强调色族 —— 钢蓝填充 + 工业琥珀标识
        "accent": "#1d4ed8",
        "accent_light": "#fbbf24",
        "accent_hover": "#2563eb",
        "accent_bg": "#172554",
        # 文字色阶 —— 仪表白
        "text_primary": "#e2e8f0",
        "text_secondary": "#a3b1c2",
        "text_muted": "#92a0b2",
        "text_inverse": "#ffffff",
        # 边框 —— 机械接缝（刻意与 hover_light 不同值，避免换肤映射歧义）
        "border": "#2e3a4a",
        "border_light": "#3a4a5e",
        "border_focus": "#fbbf24",
        # 悬停
        "hover": "#232c37",
        "hover_light": "#2b3644",
        # 语义文字变体
        "accent_text": "#8ab4f8",
        "success_text": "#2fc48d",
        "info_text": "#64a0f6",
        "error_text": "#f37a7a",
        # 刻意与 accent_light/border_focus（#fbbf24）不同值，避免换肤映射歧义
        "warning_text": "#fcd34d",
        **_SEMANTIC_FILLS,
    },
}

#: 每套主题的组件质感参数（ttk 样式用）。间距取值仍落在 4px 栅格上。
#: 这是"不是只换主色"的组件层差异：内边距密度、边框粗细、焦点环颜色。
STYLE_PARAMS = {
    "cyberpunk": {
        "primary_pad": (16, 8),
        "secondary_pad": (12, 6),
        "ghost_pad": (10, 5),
        "tab_pad": (16, 8),
        "entry_pad": (8, 6),
        "borderwidth": 1,
        "tree_row_height": 28,
    },
    "wasteland": {
        "primary_pad": (24, 12),
        "secondary_pad": (20, 10),
        "ghost_pad": (16, 8),
        "tab_pad": (24, 12),
        "entry_pad": (12, 10),
        "borderwidth": 1,
        "tree_row_height": 28,
    },
    "mechapunk": {
        "primary_pad": (20, 10),
        "secondary_pad": (16, 8),
        "ghost_pad": (12, 6),
        "tab_pad": (20, 10),
        "entry_pad": (10, 8),
        "borderwidth": 2,
        "tree_row_height": 28,
    },
}

#: 移动端令牌名 → 本模块调色板键 的映射（sync_theme_tokens.py 生成 Kotlin 用）。
#: 移动端既有命名（Surface0-4 / Text1-4 / Primary 色阶）保持不变，
#: 全部改为从主题取值 —— 屏幕代码零改动即可换肤。
MOBILE_TOKEN_MAP = {
    "Surface0": "bg_dark",
    "Surface1": "bg_dark",
    "Surface2": "bg_card",
    "Surface3": "bg_hover",
    "Surface4": "border_light",
    "Text1": "text_primary",
    "Text2": "text_secondary",
    "Text3": "text_muted",
    "Text4": "text_muted",
    "Primary50": "text_primary",
    "Primary100": "text_primary",
    "Primary200": "accent_light",
    "Primary300": "accent_light",
    "Primary400": "accent_text",
    "Primary500": "accent",
    "Primary600": "accent_hover",
    "Primary700": "accent_bg",
    "Success": "success",
    "Warning": "warning",
    "Error": "error",
    "Info": "info",
}


def normalize_theme(value: object) -> str:
    """把任意历史取值归一为合法主题 id。

    旧配置里的 `theme` 曾是死键（"light" 等遗留值），一律回落默认主题，
    绝不抛异常 —— 启动路径不能因为一个坏配置值打不开程序。
    """
    if isinstance(value, str) and value in THEMES:
        return value
    return DEFAULT_THEME


def palette_swap_map(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """构造"旧调色板值 → 新调色板值"的映射（换肤遍历用）。

    键集必须一致；别名键（bg_light/bg_card、hover/bg_hover）在两套
    调色板里各自同值，因此按值映射无歧义。若出现同值不同映射（数据错误），
    以键序先到先得 —— 守卫测试保证不会走到这一步。
    """
    mapping: dict[str, str] = {}
    for key, old_value in old.items():
        if key in new:
            mapping.setdefault(old_value.lower(), new[key])
    return mapping
