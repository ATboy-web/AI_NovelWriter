package com.ainovelwriter.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ==================== Color Tokens ====================

// Primary - Indigo
val Primary50 = Color(0xFFEEF2FF)
val Primary100 = Color(0xFFE0E7FF)
val Primary200 = Color(0xFFC7D2FE)
val Primary300 = Color(0xFFA5B4FC)
val Primary400 = Color(0xFF818CF8)
val Primary500 = Color(0xFF6366F1)
val Primary600 = Color(0xFF4F46E5)
val Primary700 = Color(0xFF4338CA)

// Surface - Slate Dark
val Surface0 = Color(0xFF0B0F1A)    // 最深背景
val Surface1 = Color(0xFF0F172A)    // 主背景
val Surface2 = Color(0xFF1E293B)    // 卡片/面板
val Surface3 = Color(0xFF293548)    // 悬浮/高亮
val Surface4 = Color(0xFF334155)    // 边框/分割线

// Text
val Text1 = Color(0xFFF1F5F9)       // 主文字
val Text2 = Color(0xFFCBD5E1)       // 次文字
val Text3 = Color(0xFF94A3B8)       // 辅助文字
val Text4 = Color(0xFF64748B)       // 禁用/占位

// Semantic
val Success = Color(0xFF10B981)
val Warning = Color(0xFFF59E0B)
val Error = Color(0xFFEF4444)
val Info = Color(0xFF3B82F6)

// Accent Colors for genre tags
val AccentPurple = Color(0xFF8B5CF6)
val AccentPink = Color(0xFFEC4899)
val AccentCyan = Color(0xFF06B6D4)
val AccentAmber = Color(0xFFF59E0B)
val AccentEmerald = Color(0xFF10B981)

// ==================== Typography ====================

val AppTypography = Typography(
    displayLarge = TextStyle(fontSize = 32.sp, fontWeight = FontWeight.Bold, lineHeight = 40.sp, letterSpacing = (-0.5).sp),
    displayMedium = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp),
    headlineLarge = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.Bold, lineHeight = 32.sp),
    headlineMedium = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, lineHeight = 28.sp),
    headlineSmall = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold, lineHeight = 24.sp),
    titleLarge = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Medium, lineHeight = 24.sp),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium, lineHeight = 22.sp),
    titleSmall = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Normal, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Normal, lineHeight = 20.sp),
    bodySmall = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Normal, lineHeight = 18.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium, lineHeight = 20.sp),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium, lineHeight = 16.sp),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, lineHeight = 14.sp),
)

// ==================== Color Scheme ====================

private val DarkColorScheme = darkColorScheme(
    primary = Primary500,
    onPrimary = Color.White,
    primaryContainer = Primary700,
    onPrimaryContainer = Primary100,
    secondary = Primary400,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFF312E81),
    onSecondaryContainer = Primary200,
    tertiary = AccentCyan,
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFF164E63),
    onTertiaryContainer = Color(0xFFCFFAFE),
    background = Surface1,
    onBackground = Text1,
    surface = Surface2,
    onSurface = Text1,
    surfaceVariant = Surface3,
    onSurfaceVariant = Text3,
    error = Error,
    onError = Color.White,
    errorContainer = Color(0xFF7F1D1D),
    onErrorContainer = Color(0xFFFEE2E2),
    outline = Surface4,
    outlineVariant = Surface3,
    inverseSurface = Text1,
    inverseOnSurface = Surface1,
)

// ==================== Theme ====================

@Composable
fun AINovelWriterTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = AppTypography,
        content = content
    )
}
