package com.ainovelwriter.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ==================== 主题状态（v3.4 三主题可切换） ====================
//
// 令牌取值唯一权威在桌面仓 app/theme_system.py，经 scripts/sync_theme_tokens.py
// 生成为 ThemeTokens.kt（DO NOT EDIT）。本文件把令牌暴露为**状态驱动的 getter**：
// 屏幕代码继续写 Surface1 / Primary400 / Text3（零改动），读取发生在组合期，
// applyThemeTokens 更新快照状态后所有读过令牌的组合自动重组 —— 即时换肤。

object ThemeState {
    var themeId by mutableStateOf(ThemeTokens.DEFAULT_THEME)
        internal set

    internal var palette by mutableStateOf(ThemeTokens.COLORS.getValue(ThemeTokens.DEFAULT_THEME))
}

/** 激活主题（非法 id 回落默认，与桌面 normalize_theme 同语义）。 */
fun applyThemeTokens(themeId: String) {
    val tid = if (themeId in ThemeTokens.THEME_IDS) themeId else ThemeTokens.DEFAULT_THEME
    ThemeState.themeId = tid
    ThemeState.palette = ThemeTokens.COLORS.getValue(tid)
}

private fun token(name: String): Color = Color(ThemeState.palette.getValue(name))

// ==================== Color Tokens（状态驱动，名称与旧版完全一致） ====================

// Surface - 主题背景色阶
val Surface0: Color get() = token("Surface0")    // 最深背景
val Surface1: Color get() = token("Surface1")    // 主背景
val Surface2: Color get() = token("Surface2")    // 卡片/面板
val Surface3: Color get() = token("Surface3")    // 悬浮/高亮
val Surface4: Color get() = token("Surface4")    // 边框/分割线

// Text - 主题文字色阶
val Text1: Color get() = token("Text1")          // 主文字
val Text2: Color get() = token("Text2")          // 次文字
val Text3: Color get() = token("Text3")          // 辅助文字
val Text4: Color get() = token("Text4")          // 禁用/占位

// Primary - 主题强调色族
val Primary50: Color get() = token("Primary50")
val Primary100: Color get() = token("Primary100")
val Primary200: Color get() = token("Primary200")
val Primary300: Color get() = token("Primary300")
val Primary400: Color get() = token("Primary400")
val Primary500: Color get() = token("Primary500")
val Primary600: Color get() = token("Primary600")
val Primary700: Color get() = token("Primary700")

// Semantic - 语义填充色跨主题恒定（与桌面同一决策：危险=红、成功=绿不随主题漂移）
val Success: Color get() = token("Success")
val Warning: Color get() = token("Warning")
val Error: Color get() = token("Error")
val Info: Color get() = token("Info")

// Accent Colors for genre tags —— 题材识别色属**内容语义**，不随界面主题变化
val AccentPurple = Color(0xFF8B5CF6)
val AccentPink = Color(0xFFEC4899)
val AccentCyan = Color(0xFF06B6D4)
val AccentAmber = Color(0xFFF59E0B)
val AccentEmerald = Color(0xFF10B981)

// ==================== 统一间距与字体层级（与桌面同一套令牌） ====================

object AppSpacing {
    val xs = ThemeTokens.SPACING.getValue("xs").dp
    val sm = ThemeTokens.SPACING.getValue("sm").dp
    val md = ThemeTokens.SPACING.getValue("md").dp
    val lg = ThemeTokens.SPACING.getValue("lg").dp
    val xl = ThemeTokens.SPACING.getValue("xl").dp
    val xxl = ThemeTokens.SPACING.getValue("xxl").dp
}

private fun roleSp(role: String) = ThemeTokens.TYPE_SCALE.getValue(role).sp

val AppTypography = Typography(
    displayLarge = TextStyle(fontSize = roleSp("display"), fontWeight = FontWeight.Bold, lineHeight = 32.sp, letterSpacing = (-0.5).sp),
    displayMedium = TextStyle(fontSize = roleSp("display"), fontWeight = FontWeight.Bold, lineHeight = 32.sp),
    headlineLarge = TextStyle(fontSize = roleSp("display"), fontWeight = FontWeight.Bold, lineHeight = 32.sp),
    headlineMedium = TextStyle(fontSize = roleSp("heading"), fontWeight = FontWeight.SemiBold, lineHeight = 28.sp),
    headlineSmall = TextStyle(fontSize = roleSp("title"), fontWeight = FontWeight.SemiBold, lineHeight = 24.sp),
    titleLarge = TextStyle(fontSize = roleSp("title"), fontWeight = FontWeight.Medium, lineHeight = 24.sp),
    titleMedium = TextStyle(fontSize = roleSp("subtitle"), fontWeight = FontWeight.Medium, lineHeight = 22.sp),
    titleSmall = TextStyle(fontSize = roleSp("body"), fontWeight = FontWeight.Medium, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontSize = roleSp("subtitle"), fontWeight = FontWeight.Normal, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontSize = roleSp("body"), fontWeight = FontWeight.Normal, lineHeight = 20.sp),
    bodySmall = TextStyle(fontSize = roleSp("label"), fontWeight = FontWeight.Normal, lineHeight = 16.sp),
    labelLarge = TextStyle(fontSize = roleSp("body"), fontWeight = FontWeight.Medium, lineHeight = 20.sp),
    labelMedium = TextStyle(fontSize = roleSp("label"), fontWeight = FontWeight.Medium, lineHeight = 16.sp),
    labelSmall = TextStyle(fontSize = roleSp("caption"), fontWeight = FontWeight.Medium, lineHeight = 14.sp),
)

// ==================== Color Scheme（每主题一套，Material 组件状态色自动派生） ====================

private fun schemeFor(tid: String): ColorScheme {
    val p = ThemeTokens.COLORS.getValue(tid)
    fun c(name: String) = Color(p.getValue(name))
    return darkColorScheme(
        primary = c("Primary500"),
        onPrimary = Color.White,
        primaryContainer = c("Primary700"),
        onPrimaryContainer = c("Primary200"),
        secondary = c("Primary400"),
        onSecondary = Color.White,
        secondaryContainer = c("Primary700"),
        onSecondaryContainer = c("Primary200"),
        tertiary = c("Primary300"),
        onTertiary = Color.White,
        tertiaryContainer = c("Primary700"),
        onTertiaryContainer = c("Primary200"),
        background = c("Surface1"),
        onBackground = c("Text1"),
        surface = c("Surface2"),
        onSurface = c("Text1"),
        surfaceVariant = c("Surface3"),
        onSurfaceVariant = c("Text3"),
        error = c("Error"),
        onError = Color.White,
        errorContainer = Color(0xFF7F1D1D),
        onErrorContainer = Color(0xFFFEE2E2),
        outline = c("Surface4"),
        outlineVariant = c("Surface3"),
        inverseSurface = c("Text1"),
        inverseOnSurface = c("Surface1"),
    )
}

// ==================== Theme ====================

@Composable
fun AINovelWriterTheme(themeId: String = ThemeTokens.DEFAULT_THEME, content: @Composable () -> Unit) {
    // themeId 变化时同步令牌状态（首帧即正确，无闪烁）
    remember(themeId) { applyThemeTokens(themeId) }
    MaterialTheme(
        colorScheme = schemeFor(ThemeState.themeId),
        typography = AppTypography,
        content = content
    )
}