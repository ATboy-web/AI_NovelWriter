"""
设计系统 - 设计令牌和组件样式

基于UI设计方案v3.0
"""


class DesignTokens:
    """设计令牌系统"""
    
    # 颜色系统
    COLORS = {
        # 背景色
        "bg_primary": "#0f0f1a",      # 最深背景
        "bg_secondary": "#16162a",     # 面板背景
        "bg_card": "#1e1e38",          # 卡片/输入框
        "bg_hover": "#252540",         # 悬停状态
        
        # 边框色
        "border": "#2a2a40",           # 分隔线/边框
        "border_light": "#3a3a55",     # 较亮边框
        
        # 主色调
        "primary": "#534ab7",          # 按钮/高亮
        "primary_hover": "#6a62d0",    # 主色悬停
        "primary_light": "#8b84e0",    # 主色浅色
        
        # 语义色
        "success": "#0f6e56",          # 成功
        "success_light": "#10b981",    # 成功浅色
        "error": "#ef4444",            # 错误
        "error_dark": "#dc2626",       # 错误深色
        "warning": "#f59e0b",          # 警告
        "info": "#3b82f6",             # 信息
        
        # 文字色
        "text_primary": "#e0e0f0",     # 主要文字
        "text_secondary": "#a0a0b0",   # 次要文字
        "text_muted": "#606080",       # 辅助文字
        "text_inverse": "#ffffff",     # 反色文字
    }
    
    # 间距系统
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
    FONTS = {
        "family": "微软雅黑, Microsoft YaHei, sans-serif",
        "mono": "Consolas, Monaco, monospace",
        "sizes": {
            "xs": 10,
            "sm": 11,
            "md": 13,
            "lg": 15,
            "xl": 18,
            "2xl": 24,
        }
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
