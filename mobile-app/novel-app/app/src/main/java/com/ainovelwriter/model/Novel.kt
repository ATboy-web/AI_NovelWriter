package com.ainovelwriter.model

data class NovelMeta(
    val id: String = "",
    val title: String = "",
    val genre: String = "",
    val concept: String = "",
    val channel: String = "male",
    val chapterCount: Int = 0,
    val totalChapters: Int = 50,
    val wordCountPerChapter: Int = 3000,
    val is18Plus: Boolean = false,
    val isBorderline: Boolean = false,  // 擦边开关
    val protagonist: String = "",        // 主角名锁定
    val createdAt: String = "",
    val updatedAt: String = ""
)

data class Chapter(
    val id: String = "",
    val novelId: String = "",
    val chapterNum: Int = 0,
    val title: String = "",
    val content: String = "",
    val summary: String = "",
    val wordCount: Int = 0,
    val createdAt: String = ""
)

data class OutlineItem(
    val chapter: Int = 0,
    val title: String = "",
    val summary: String = ""
)

data class Character(
    val name: String = "",
    val gender: String = "",
    val age: Int = 25,
    val category: String = "",
    val faction: String = "中立",
    val personality: String = "",
    val background: String = "",
    val appearance: String = "",
    val attributes: Map<String, Int> = mapOf(
        "力量" to 50,
        "敏捷" to 50,
        "体质" to 50,
        "智力" to 50,
        "精神" to 50,
        "魅力" to 50,
        "幸运" to 50
    )
)

data class NovelData(
    val meta: NovelMeta = NovelMeta(),
    val chapters: List<Chapter> = emptyList(),
    val characters: Map<String, Character> = emptyMap(),
    val outline: List<OutlineItem> = emptyList(),
    val worldSettings: String = "",
    val storyOutline: String = "",
    val overallOutline: String = "",
    val synopsis: String = "",
    val notes: List<Note> = emptyList()
)

data class Note(
    val id: String = "",
    val title: String = "",
    val content: String = "",
    val createdAt: String = ""
)

data class LogEntry(
    val time: Long = System.currentTimeMillis(),
    val type: String = "info",
    val message: String = ""
)
