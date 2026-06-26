package com.ainovelwriter.data

import android.content.Context
import com.ainovelwriter.model.*
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.File

class NovelRepository(private val context: Context) {

    private val gson = Gson()
    private val novelsDir: File
        get() = File(context.getExternalFilesDir(null) ?: context.filesDir, "novels").also { it.mkdirs() }

    fun generateId(): String =
        System.currentTimeMillis().toString(36) + (Math.random() * 1000).toInt()

    private fun novelDir(meta: NovelMeta): File =
        File(novelsDir, sanitizeDirName("${meta.id}_${meta.title}"))

    private fun novelDirById(id: String): File? =
        novelsDir.listFiles()?.find { it.isDirectory && it.name.startsWith("${id}_") }

    private fun sanitizeDirName(name: String): String =
        name.replace(Regex("[\\\\/:*?\"<>|]"), "_")

    // region CRUD

    fun listNovels(): List<NovelMeta> {
        val dirs = novelsDir.listFiles()?.filter { it.isDirectory } ?: return emptyList()
        return dirs.mapNotNull { dir ->
            val metaFile = File(dir, "meta.json")
            if (metaFile.exists()) {
                try {
                    gson.fromJson(metaFile.readText(), NovelMeta::class.java)
                } catch (_: Exception) {
                    null
                }
            } else null
        }.sortedByDescending { it.updatedAt }
    }

    fun getNovel(id: String): NovelData? {
        val dir = novelDirById(id) ?: return null

        val meta = readJson<NovelMeta>(File(dir, "meta.json")) ?: return null
        val chapters = readJsonList<Chapter>(File(dir, "chapters.json"))
        val characters = readJsonMap<String, Character>(File(dir, "characters.json"))
        val outline = readJsonList<OutlineItem>(File(dir, "outline.json"))
        val notes = readJsonList<Note>(File(dir, "notes.json"))
        val worldSettings = readText(File(dir, "world_settings.txt"))
        val storyOutline = readText(File(dir, "story_outline.txt"))
        val overallOutline = readText(File(dir, "overall_outline.txt"))
        val synopsis = readText(File(dir, "synopsis.txt"))

        return NovelData(
            meta = meta,
            chapters = chapters,
            characters = characters,
            outline = outline,
            worldSettings = worldSettings,
            storyOutline = storyOutline,
            overallOutline = overallOutline,
            synopsis = synopsis,
            notes = notes
        )
    }

    fun saveNovel(data: NovelData): NovelData {
        val now = System.currentTimeMillis().toString()
        val meta = if (data.meta.id.isEmpty()) {
            data.meta.copy(id = generateId(), createdAt = now, updatedAt = now)
        } else {
            data.meta.copy(updatedAt = now)
        }
        val updated = data.copy(meta = meta)

        val dir = novelDir(meta)
        dir.mkdirs()

        writeJson(File(dir, "meta.json"), updated.meta)
        writeJson(File(dir, "chapters.json"), updated.chapters)
        writeJson(File(dir, "characters.json"), updated.characters)
        writeJson(File(dir, "outline.json"), updated.outline)
        writeJson(File(dir, "notes.json"), updated.notes)
        File(dir, "world_settings.txt").writeText(updated.worldSettings)
        File(dir, "story_outline.txt").writeText(updated.storyOutline)
        File(dir, "overall_outline.txt").writeText(updated.overallOutline)
        File(dir, "synopsis.txt").writeText(updated.synopsis)

        return updated
    }

    fun deleteNovel(id: String): Boolean {
        val dir = novelDirById(id) ?: return false
        return dir.deleteRecursively()
    }

    // endregion

    // region Single-chapter helpers

    fun saveChapter(novelId: String, chapter: Chapter) {
        val novel = getNovel(novelId) ?: return
        val updatedChapters = novel.chapters.filter { it.id != chapter.id } + chapter
        val updated = novel.copy(
            chapters = updatedChapters,
            meta = novel.meta.copy(chapterCount = updatedChapters.size)
        )
        saveNovel(updated)
    }

    fun deleteChapter(novelId: String, chapterId: String) {
        val novel = getNovel(novelId) ?: return
        val updatedChapters = novel.chapters.filter { it.id != chapterId }
        val updated = novel.copy(
            chapters = updatedChapters,
            meta = novel.meta.copy(chapterCount = updatedChapters.size)
        )
        saveNovel(updated)
    }

    // endregion

    // region IO helpers

    private fun writeJson(file: File, obj: Any) {
        file.writeText(gson.toJson(obj))
    }

    private inline fun <reified T> readJson(file: File): T? {
        if (!file.exists()) return null
        return try {
            gson.fromJson(file.readText(), T::class.java)
        } catch (_: Exception) {
            null
        }
    }

    private inline fun <reified T> readJsonList(file: File): List<T> {
        if (!file.exists()) return emptyList()
        return try {
            val type = TypeToken.getParameterized(List::class.java, T::class.java).type
            gson.fromJson(file.readText(), type) ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }

    private inline fun <reified K, reified V> readJsonMap(file: File): Map<K, V> {
        if (!file.exists()) return emptyMap()
        return try {
            val type = TypeToken.getParameterized(Map::class.java, K::class.java, V::class.java).type
            gson.fromJson(file.readText(), type) ?: emptyMap()
        } catch (_: Exception) {
            emptyMap()
        }
    }

    private fun readText(file: File): String =
        if (file.exists()) file.readText() else ""

    // endregion
}
