package com.ainovelwriter.ui.theme

import androidx.compose.ui.graphics.Color

// ==================== Genre Color System ====================
// 为每种小说类型分配独特的颜色，增强视觉辨识度

object GenreColors {
    data class GenreColor(val primary: Color, val container: Color)

    private val colorMap = mapOf(
        // 男频
        "玄幻" to GenreColor(Color(0xFF8B5CF6), Color(0xFF2E1065)),
        "仙侠" to GenreColor(Color(0xFF06B6D4), Color(0xFF083344)),
        "都市" to GenreColor(Color(0xFF3B82F6), Color(0xFF1E3A5F)),
        "历史" to GenreColor(Color(0xFFF59E0B), Color(0xFF451A03)),
        "科幻" to GenreColor(Color(0xFF10B981), Color(0xFF022C22)),
        "悬疑" to GenreColor(Color(0xFF6366F1), Color(0xFF1E1B4B)),
        "游戏" to GenreColor(Color(0xFF14B8A6), Color(0xFF042F2E)),
        "武侠" to GenreColor(Color(0xFFEF4444), Color(0xFF450A0A)),
        "军事" to GenreColor(Color(0xFF64748B), Color(0xFF1E293B)),
        "体育" to GenreColor(Color(0xFFF97316), Color(0xFF431407)),
        "穿越" to GenreColor(Color(0xFFEC4899), Color(0xFF500724)),
        "系统" to GenreColor(Color(0xFFA855F7), Color(0xFF3B0764)),
        "末日" to GenreColor(Color(0xFF78716C), Color(0xFF292524)),
        // 女频
        "言情" to GenreColor(Color(0xFFF472B6), Color(0xFF500724)),
        "纯爱" to GenreColor(Color(0xFFFB923C), Color(0xFF431407)),
        "百合" to GenreColor(Color(0xFFFBBF24), Color(0xFF451A03)),
        "耽美" to GenreColor(Color(0xFF818CF8), Color(0xFF1E1B4B)),
        "幻想" to GenreColor(Color(0xFFC084FC), Color(0xFF3B0764)),
    )

    fun get(genre: String): GenreColor {
        for ((key, value) in colorMap) {
            if (genre.contains(key)) return value
        }
        return GenreColor(Color(0xFF6366F1), Color(0xFF1E1B4B))
    }
}

// ==================== Icon Emoji System ====================
object GenreIcons {
    fun get(genre: String): String = when {
        genre.contains("玄幻") -> "⚡"
        genre.contains("仙侠") -> "⚔️"
        genre.contains("都市") -> "🏙️"
        genre.contains("历史") -> "🏛️"
        genre.contains("科幻") -> "🚀"
        genre.contains("悬疑") -> "🔍"
        genre.contains("游戏") -> "🎮"
        genre.contains("武侠") -> "🥋"
        genre.contains("军事") -> "🎖️"
        genre.contains("体育") -> "⚽"
        genre.contains("穿越") -> "🌀"
        genre.contains("系统") -> "💻"
        genre.contains("末日") -> "☢️"
        genre.contains("言情") -> "💕"
        genre.contains("纯爱") -> "🧡"
        genre.contains("百合") -> "🌸"
        genre.contains("耽美") -> "💎"
        genre.contains("幻想") -> "✨"
        else -> "📖"
    }
}
