package com.ainovelwriter.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ainovelwriter.data.NovelRepository
import com.ainovelwriter.data.SettingsRepository
import com.ainovelwriter.model.*
import com.ainovelwriter.service.AIService
import com.ainovelwriter.service.TokenStats
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

enum class Tab { NOVELS, CHAPTER, OUTLINE, CHARACTERS, WORLD, SETTINGS, LOGS }

data class MainUiState(
    val currentTab: Tab = Tab.NOVELS,
    val novelList: List<NovelMeta> = emptyList(),
    val currentNovel: NovelData? = null,
    val userLogs: List<LogEntry> = emptyList(),      // 用户日志：显示当前在做什么
    val devLogs: List<LogEntry> = emptyList(),        // 开发者/AI日志：深层诊断信息
    val isGenerating: Boolean = false,
    val generationProgress: String = "",               // 当前生成步骤描述
    val editingChapter: Chapter? = null,
    val aiConfig: AIConfig = AIConfig()
)

class MainViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "AINovelWriter"
    }

    private val repo = NovelRepository(application)
    private val settingsRepo = SettingsRepository(application)

    private val _state = MutableStateFlow(MainUiState())
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    init {
        loadNovelList()
        viewModelScope.launch {
            settingsRepo.aiConfig.collect { config ->
                _state.value = _state.value.copy(aiConfig = config)
            }
        }
    }

    // region Navigation

    fun setTab(tab: Tab) {
        _state.value = _state.value.copy(currentTab = tab)
    }

    // endregion

    // region Novel CRUD

    fun loadNovelList() {
        _state.value = _state.value.copy(novelList = repo.listNovels())
    }

    fun openNovel(id: String) {
        val novel = repo.getNovel(id)
        _state.value = _state.value.copy(currentNovel = novel, currentTab = Tab.CHAPTER)
    }

    fun closeNovel() {
        _state.value = _state.value.copy(currentNovel = null, currentTab = Tab.NOVELS)
    }

    fun createNovel(title: String, genre: String, concept: String, channel: String = "male", totalChapters: Int = 50, wordCountPerChapter: Int = 3000, is18Plus: Boolean = false, isBorderline: Boolean = false, protagonist: String = "") {
        val meta = NovelMeta(
            title = title,
            genre = genre,
            concept = concept,
            channel = channel,
            totalChapters = totalChapters,
            wordCountPerChapter = wordCountPerChapter,
            is18Plus = is18Plus,
            isBorderline = isBorderline,
            protagonist = protagonist
        )
        val saved = repo.saveNovel(NovelData(meta = meta))
        userLog("📚 创建小说《$title》")
        devLog("创建小说: genre=$genre, chapters=$totalChapters, words=$wordCountPerChapter")
        loadNovelList()
        openNovel(saved.meta.id)
    }

    fun deleteNovel(id: String) {
        repo.deleteNovel(id)
        userLog("🗑️ 删除小说")
        if (_state.value.currentNovel?.meta?.id == id) {
            _state.value = _state.value.copy(currentNovel = null, currentTab = Tab.NOVELS)
        }
        loadNovelList()
    }

    fun updateCurrentNovel(data: NovelData) {
        val saved = repo.saveNovel(data)
        _state.value = _state.value.copy(currentNovel = saved)
        loadNovelList()
    }

    // endregion

    // region Chapter editing

    fun setEditingChapter(chapter: Chapter?) {
        _state.value = _state.value.copy(editingChapter = chapter)
    }

    fun saveChapter(chapter: Chapter) {
        val novel = _state.value.currentNovel ?: return
        repo.saveChapter(novel.meta.id, chapter)
        refreshCurrentNovel()
        userLog("💾 保存第${chapter.chapterNum}章")
    }

    fun deleteChapter(chapterId: String) {
        val novel = _state.value.currentNovel ?: return
        repo.deleteChapter(novel.meta.id, chapterId)
        refreshCurrentNovel()
        userLog("🗑️ 删除章节")
    }

    // endregion

    // region Auto Generate (对齐桌面版 _auto_generate 流程)

    /**
     * 自动创作 - 对齐桌面版完整流程
     * Step 1: 世界观生成
     * Step 2: 角色生成
     * Step 3: 章节大纲生成
     * Step 3.5: 整体大纲 + 故事大纲
     * Step 4: 逐章生成
     */
    fun autoGenerate() {
        val novel = _state.value.currentNovel ?: return
        if (_state.value.isGenerating) {
            userLog("⚠️ 正在生成中，请等待")
            return
        }
        _state.value = _state.value.copy(isGenerating = true)

        viewModelScope.launch {
            try {
                val totalChapters = novel.meta.totalChapters
                val completedChapters = novel.chapters.size
                userLog("🚀 开始自动创作《${novel.meta.title}》")
                userLog("📊 计划${totalChapters}章，已完成${completedChapters}章")
                devLog("自动创作开始: total=$totalChapters, completed=$completedChapters, genre=${novel.meta.genre}")

                var currentNovel = novel

                // Step 1: 世界观生成
                if (currentNovel.worldSettings.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "Step 1/5: 生成世界观")
                    userLog("🌍 Step 1: 生成世界观...")
                    currentNovel = generateWorldInternal(currentNovel)
                } else {
                    userLog("🌍 世界观已存在，跳过")
                    devLog("世界观已存在 (${currentNovel.worldSettings.length}字)")
                }

                // Step 2: 角色生成
                if (currentNovel.characters.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "Step 2/5: 生成角色")
                    userLog("👥 Step 2: 生成角色...")
                    currentNovel = generateCharactersInternal(currentNovel)
                } else {
                    userLog("👥 角色已存在 (${currentNovel.characters.size}个)，跳过")
                }

                // Step 3: 章节大纲生成
                if (currentNovel.outline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "Step 3/5: 生成大纲")
                    userLog("📋 Step 3: 生成章节大纲...")
                    currentNovel = generateOutlineInternal(currentNovel)
                } else {
                    userLog("📋 大纲已存在 (${currentNovel.outline.size}章)，跳过")
                }

                // Step 3.5: 整体大纲 + 故事大纲
                if (currentNovel.overallOutline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "Step 3.5/5: 生成整体大纲")
                    userLog("📝 Step 3.5: 生成整体大纲...")
                    currentNovel = generateOverallOutlineInternal(currentNovel)
                }
                if (currentNovel.storyOutline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "Step 3.5/5: 生成故事大纲")
                    userLog("📖 生成故事大纲...")
                    currentNovel = generateStoryOutlineInternal(currentNovel)
                }

                // Step 4: 逐章生成
                val startChapter = currentNovel.chapters.size + 1
                if (startChapter > totalChapters) {
                    userLog("✅ 所有章节已完成！")
                    _state.value = _state.value.copy(isGenerating = false, generationProgress = "")
                    return@launch
                }

                userLog("✍️ Step 4: 开始逐章生成 (第${startChapter}章 ~ 第${totalChapters}章)")
                var successCount = 0
                var failCount = 0

                for (chNum in startChapter..totalChapters) {
                    // 检查是否已停止
                    if (!_state.value.isGenerating) {
                        userLog("⏹️ 用户停止生成")
                        break
                    }

                    _state.value = _state.value.copy(
                        generationProgress = "Step 4/5: 生成第${chNum}/${totalChapters}章"
                    )

                    try {
                        currentNovel = generateChapterInternal(currentNovel, chNum)
                        successCount++
                    } catch (e: Exception) {
                        failCount++
                        userLog("❌ 第${chNum}章生成失败: ${e.message}")
                        devLog("第${chNum}章异常: ${e.message}\n${e.stackTraceToString().take(500)}")
                        // 重试一次
                        try {
                            kotlinx.coroutines.delay(3000)
                            currentNovel = generateChapterInternal(currentNovel, chNum)
                            successCount++
                            failCount--
                            userLog("✅ 第${chNum}章重试成功")
                        } catch (e2: Exception) {
                            devLog("第${chNum}章重试也失败: ${e2.message}")
                        }
                    }
                }

                userLog("🎉 自动创作完成！成功${successCount}章，失败${failCount}章")
                devLog("自动创作结束: success=$successCount, fail=$failCount")

            } catch (e: Exception) {
                userLog("❌ 自动创作失败: ${e.message}")
                devLog("自动创作异常: ${e.message}\n${e.stackTraceToString().take(500)}")
            } finally {
                _state.value = _state.value.copy(isGenerating = false, generationProgress = "")
            }
        }
    }

    fun stopGeneration() {
        _state.value = _state.value.copy(isGenerating = false, generationProgress = "")
        userLog("⏹️ 已请求停止生成")
    }

    // endregion

    // region Individual Generation Steps (可单独调用)

    fun generateWorld() {
        val novel = _state.value.currentNovel ?: return
        launchAI("构建世界观") {
            val updated = generateWorldInternal(novel)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    fun generateCharacters() {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成角色") {
            val updated = generateCharactersInternal(novel)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    fun generateOutline() {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成大纲") {
            val updated = generateOutlineInternal(novel)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    fun generateOverallOutline() {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成整体大纲") {
            val updated = generateOverallOutlineInternal(novel)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    fun generateStoryOutline() {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成故事大纲") {
            val updated = generateStoryOutlineInternal(novel)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    /** 整合素材：用已有的世界观/角色/概念生成大纲，不强制补全 */
    fun integrateSettings() {
        val novel = _state.value.currentNovel ?: return
        if (_state.value.isGenerating) {
            userLog("⚠️ 正在生成中，请等待")
            return
        }

        // 检查是否有任何素材可用
        val hasWorld = novel.worldSettings.isNotEmpty()
        val hasChars = novel.characters.isNotEmpty()
        val hasConcept = novel.meta.concept.isNotEmpty()

        if (!hasWorld && !hasChars && !hasConcept) {
            userLog("⚠️ 没有可用素材，请先生成世界观、角色或填写概念")
            return
        }

        _state.value = _state.value.copy(isGenerating = true)

        viewModelScope.launch {
            try {
                var currentNovel = novel

                // 报告已有素材
                val parts = mutableListOf<String>()
                if (hasWorld) parts.add("世界观(${currentNovel.worldSettings.length}字)")
                if (hasChars) parts.add("角色(${currentNovel.characters.size}个)")
                if (hasConcept) parts.add("概念")
                userLog("🔗 整合素材: ${parts.joinToString(" + ")}")

                // 生成大纲系列（AI会基于已有素材生成，不需要全部齐全）
                val totalSteps = 3
                var step = 1

                if (currentNovel.outline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "${step}/${totalSteps}: 章节大纲")
                    userLog("📋 生成章节大纲...")
                    currentNovel = generateOutlineInternal(currentNovel)
                    _state.value = _state.value.copy(currentNovel = currentNovel)
                } else {
                    userLog("📋 章节大纲已存在 (${currentNovel.outline.size}章)，跳过")
                }
                step++

                if (currentNovel.overallOutline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "${step}/${totalSteps}: 整体大纲")
                    userLog("📝 生成整体大纲...")
                    currentNovel = generateOverallOutlineInternal(currentNovel)
                    _state.value = _state.value.copy(currentNovel = currentNovel)
                } else {
                    userLog("📝 整体大纲已存在，跳过")
                }
                step++

                if (currentNovel.storyOutline.isEmpty()) {
                    _state.value = _state.value.copy(generationProgress = "${step}/${totalSteps}: 故事大纲")
                    userLog("📖 生成故事大纲...")
                    currentNovel = generateStoryOutlineInternal(currentNovel)
                    _state.value = _state.value.copy(currentNovel = currentNovel)
                } else {
                    userLog("📖 故事大纲已存在，跳过")
                }

                userLog("✅ 整合完成！大纲已就绪，可以开始写作了")
            } catch (e: Exception) {
                userLog("❌ 整合失败: ${e.message}")
                devLog("整合异常: ${e.message}\n${e.stackTraceToString().take(500)}")
            } finally {
                _state.value = _state.value.copy(isGenerating = false, generationProgress = "")
            }
        }
    }

    fun generateChapter(chapterNum: Int) {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成第${chapterNum}章") {
            val updated = generateChapterInternal(novel, chapterNum)
            _state.value = _state.value.copy(currentNovel = updated)
        }
    }

    // endregion

    // region AI Editing Tools

    fun aiContinue() {
        val novel = _state.value.currentNovel ?: return
        val chapter = _state.value.editingChapter ?: return
        launchAI("AI续写") {
            val prompt = buildString {
                appendLine("请继续撰写以下小说内容，保持风格和情节连贯。")
                appendLine("目标续写 ${novel.meta.wordCountPerChapter / 3} 字。")
                appendLine("直接输出续写内容，不要重复已有内容。")
                appendLine()
                appendLine(chapter.content.takeLast(1000))
            }
            val result = chat(prompt, maxTokens = 4000)
            val updated = chapter.copy(
                content = chapter.content + "\n" + result,
                wordCount = chapter.content.length + result.length + 1
            )
            setEditingChapter(updated)
            repo.saveChapter(novel.meta.id, updated)
            refreshCurrentNovel()
            userLog("✅ 续写完成 +${result.length}字")
        }
    }

    fun aiPolish() {
        val novel = _state.value.currentNovel ?: return
        val chapter = _state.value.editingChapter ?: return
        launchAI("AI润色") {
            val prompt = buildString {
                appendLine("请对以下小说内容进行润色优化。")
                appendLine("要求：提升文笔质量，优化句式表达，保持原意不变。")
                appendLine("直接输出润色后的完整内容。")
                appendLine()
                appendLine(chapter.content)
            }
            val result = chat(prompt, maxTokens = 8000)
            val updated = chapter.copy(content = result, wordCount = result.length)
            setEditingChapter(updated)
            repo.saveChapter(novel.meta.id, updated)
            refreshCurrentNovel()
            userLog("✅ 润色完成")
        }
    }

    fun aiExpand() {
        val novel = _state.value.currentNovel ?: return
        val chapter = _state.value.editingChapter ?: return
        launchAI("AI扩写") {
            val prompt = buildString {
                appendLine("请对以下小说内容进行扩写。")
                appendLine("要求：增加细节描写、心理活动、环境氛围，扩充至原来的 1.5-2 倍篇幅。")
                appendLine("直接输出扩写后的完整内容。")
                appendLine()
                appendLine(chapter.content)
            }
            val result = chat(prompt, maxTokens = 10000)
            val updated = chapter.copy(content = result, wordCount = result.length)
            setEditingChapter(updated)
            repo.saveChapter(novel.meta.id, updated)
            refreshCurrentNovel()
            userLog("✅ 扩写完成 ${result.length}字")
        }
    }

    fun aiReview() {
        val chapter = _state.value.editingChapter
            ?: _state.value.currentNovel?.chapters?.maxByOrNull { it.chapterNum }
        if (chapter == null) {
            userLog("⚠️ 没有可审阅的章节")
            return
        }
        launchAI("AI审阅") {
            val prompt = buildString {
                appendLine("请对以下小说内容进行审阅评分。")
                appendLine("从5个维度评分(0-100)：角色一致性、情节逻辑、文笔质量、情感感染力、节奏把控")
                appendLine("输出JSON: {\"score\":总分, \"dimensions\":{...}, \"issues\":[...], \"suggestions\":[...]}")
                appendLine()
                appendLine(chapter.content.take(3000))
            }
            val result = chat(prompt, maxTokens = 2000)
            userLog("🔍 审阅完成:")
            // 显示审阅结果摘要给用户
            result.lines().take(10).forEach { line ->
                if (line.isNotBlank()) userLog("  $line")
            }
            devLog("审阅结果: $result")
        }
    }

    fun antiSlopCheck() {
        // 支持从编辑器或工具面板调用
        val chapter = _state.value.editingChapter
            ?: _state.value.currentNovel?.chapters?.maxByOrNull { it.chapterNum }
        if (chapter == null) {
            userLog("⚠️ 没有可检查的章节")
            return
        }
        // 本地检测（不需要AI调用）
        val forbiddenOpenings = listOf("在这个", "在这个世界上", "随着科技的发展", "众所周知")
        val forbiddenTransitions = listOf("然而", "不过", "尽管如此", "总而言之", "归根结底")
        val forbiddenEndings = listOf("这一切，才刚刚开始", "命运的齿轮", "故事，才刚刚开始")

        val issues = mutableListOf<String>()
        val text = chapter.content

        forbiddenOpenings.forEach { pattern ->
            if (text.contains(pattern)) issues.add("禁止开头: \"$pattern\"")
        }
        forbiddenTransitions.forEach { pattern ->
            val count = text.split(pattern).size - 1
            if (count > 3) issues.add("过渡词过多: \"$pattern\" × $count")
        }
        forbiddenEndings.forEach { pattern ->
            if (text.contains(pattern)) issues.add("禁止结尾: \"$pattern\"")
        }

        if (issues.isEmpty()) {
            userLog("✅ 去AI味检查通过，未发现明显问题")
        } else {
            userLog("⚠️ 发现 ${issues.size} 个AI痕迹:")
            issues.forEach { userLog("  • $it") }
        }
        devLog("AntiSlop检查: ${issues.size} issues in ${text.length}字")
    }

    fun generateSynopsis() {
        val novel = _state.value.currentNovel ?: return
        launchAI("生成简介") {
            val prompt = buildString {
                appendLine("请为小说《${novel.meta.title}》生成500字以内的作品简介。")
                appendLine("类型：${novel.meta.genre}")
                if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
                if (novel.meta.protagonist.isNotEmpty()) appendLine("主角：${novel.meta.protagonist}")
                if (novel.characters.isNotEmpty()) appendLine("主要角色：${novel.characters.keys.joinToString("、")}")
                appendLine()
                appendLine("要求：悬念感强，能吸引目标读者。")
            }
            val result = chat(prompt, maxTokens = 1000)
            val updated = novel.copy(synopsis = result)
            _state.value = _state.value.copy(currentNovel = updated)
            repo.saveNovel(updated)
            userLog("✅ 简介生成完成")
        }
    }

    fun styleTransfer(targetStyle: String) {
        val novel = _state.value.currentNovel ?: return
        val chapter = _state.value.editingChapter
            ?: novel.chapters.maxByOrNull { it.chapterNum }
        if (chapter == null) {
            userLog("⚠️ 没有可转换的章节")
            return
        }
        launchAI("风格转换") {
            val prompt = buildString {
                appendLine("请将以下小说内容转换为「$targetStyle」风格。")
                appendLine("保持情节不变，调整文笔、句式、用词以匹配目标风格。")
                appendLine("直接输出转换后的完整内容。")
                appendLine()
                appendLine(chapter.content.take(2000))
            }
            val result = chat(prompt, maxTokens = 8000)
            val updated = chapter.copy(content = result, wordCount = result.length)
            setEditingChapter(updated)
            repo.saveChapter(novel.meta.id, updated)
            refreshCurrentNovel()
            userLog("✅ 风格转换完成")
        }
    }

    fun generateDialogue(characterName: String, scene: String) {
        val novel = _state.value.currentNovel
        launchAI("生成对话") {
            val prompt = buildString {
                appendLine("请为以下场景生成自然的对话内容（10-15轮）。")
                appendLine("角色：$characterName")
                appendLine("场景：$scene")
                // 注入角色信息
                val char = novel?.characters?.get(characterName)
                if (char != null) {
                    appendLine("角色性格：${char.personality.take(100)}")
                }
                appendLine()
                appendLine("要求：对话要符合角色性格，自然流畅，包含适当的动作描写。")
            }
            val result = chat(prompt, maxTokens = 3000)
            userLog("💬 对话生成完成:")
            result.lines().take(8).forEach { line ->
                if (line.isNotBlank()) userLog("  $line")
            }
            devLog("对话结果: $result")
        }
    }

    // endregion

    // region Export

    fun exportTxt() {
        val novel = _state.value.currentNovel ?: return
        viewModelScope.launch {
            try {
                val content = buildString {
                    appendLine("# ${novel.meta.title}")
                    if (novel.synopsis.isNotEmpty()) {
                        appendLine()
                        appendLine("## 简介")
                        appendLine(novel.synopsis)
                    }
                    appendLine()
                    novel.chapters.sortedBy { it.chapterNum }.forEach { ch ->
                        appendLine("## 第${ch.chapterNum}章 ${ch.title}")
                        appendLine()
                        appendLine(ch.content)
                        appendLine()
                        appendLine("---")
                        appendLine()
                    }
                }
                val dir = getApplication<Application>().getExternalFilesDir(null)
                    ?: getApplication<Application>().filesDir
                val file = java.io.File(dir, "export/${novel.meta.title}.txt")
                file.parentFile?.mkdirs()
                file.writeText(content)
                userLog("📋 导出成功: ${file.name}")
                devLog("导出路径: ${file.absolutePath}, ${content.length}字")
            } catch (e: Exception) {
                userLog("❌ 导出失败: ${e.message}")
            }
        }
    }

    // endregion

    // region Settings

    fun updateAIConfig(config: AIConfig) {
        _state.value = _state.value.copy(aiConfig = config)
        viewModelScope.launch {
            settingsRepo.saveAIConfig(config)
            devLog("AI配置更新: model=${config.model}, endpoint=${config.endpoint}")
        }
    }

    // endregion

    // region Internal Generation (对齐桌面版逻辑)

    /**
     * 世界观生成 - 对齐桌面版 generate_settings
     */
    private suspend fun generateWorldInternal(novel: NovelData): NovelData {
        val prompt = buildString {
            appendLine("小说类型：${novel.meta.genre}")
            appendLine("标题：${novel.meta.title}")
            if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
            if (novel.meta.protagonist.isNotEmpty()) appendLine("主角名：${novel.meta.protagonist}")
            appendLine()
            appendLine("请生成一个灵活、可扩展的世界观设定。")
            appendLine("包含：世界名称、时代背景、力量体系、地理环境、主要势力、核心规则。")
            appendLine("重要原则: 留有扩展空间、灵活多变、层次分明。")
        }
        devLog("[世界观] 开始生成, genre=${novel.meta.genre}")
        val result = chat(prompt, system = "你是一位专业的小说世界观设定师。", maxTokens = 3000)
        val updated = novel.copy(worldSettings = result)
        repo.saveNovel(updated)
        _state.value = _state.value.copy(currentNovel = updated)
        userLog("✅ 世界观生成完成 (${result.length}字)")
        devLog("[世界观] 完成, ${result.length}字")
        return updated
    }

    /**
     * 角色生成 - 对齐桌面版 generate_characters
     */
    private suspend fun generateCharactersInternal(novel: NovelData): NovelData {
        val count = when {
            novel.meta.totalChapters <= 20 -> 3
            novel.meta.totalChapters <= 50 -> 5
            else -> 8
        }
        val worldContext = if (novel.worldSettings.isNotEmpty()) "\n世界观：${novel.worldSettings.take(1000)}" else ""
        val prompt = buildString {
            appendLine("小说类型：${novel.meta.genre}")
            appendLine("标题：${novel.meta.title}")
            if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
            if (novel.meta.protagonist.isNotEmpty()) appendLine("主角名（必须包含为主角）：${novel.meta.protagonist}")
            appendLine(worldContext)
            appendLine()
            appendLine("请创建${count}个角色。")
            appendLine("输出JSON对象，key为角色名，value包含: gender, age, category(主角/女主/配角/反派), faction(阵营), personality(50字以上), background(100字以上), appearance, attributes(力量/敏捷/体质/智力/精神/魅力/幸运，各10-100)。")
            appendLine("严格要求：每个角色必须有独特的人格和背景。直接输出JSON。")
        }
        devLog("[角色] 开始生成, count=$count")
        val result = chat(prompt, system = "你是专业角色设计师。", maxTokens = 6000)
        val characters = parseJsonMap<String, Character>(result)
        val updated = if (characters.isNotEmpty()) {
            novel.copy(characters = characters)
        } else {
            devLog("[角色] JSON解析失败, 尝试提取: ${result.take(300)}")
            novel
        }
        repo.saveNovel(updated)
        _state.value = _state.value.copy(currentNovel = updated)
        userLog("✅ 角色生成完成 (${characters.size}个)")
        devLog("[角色] 完成, ${characters.size}个角色")
        return updated
    }

    /**
     * 章节大纲生成 - 对齐桌面版 generate_outline
     */
    private suspend fun generateOutlineInternal(novel: NovelData): NovelData {
        val system = "你是专业小说大纲师。输出JSON数组，每项包含: chapter(章节号), title(10字内), summary(80-150字)。禁止'待规划'或空摘要。直接输出JSON。"
        val prompt = buildString {
            appendLine("类型：${novel.meta.genre}")
            appendLine("标题：${novel.meta.title}")
            if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
            appendLine("总章数：${novel.meta.totalChapters}")
            appendLine()
            appendLine("请为${novel.meta.totalChapters}章生成详细大纲。")
        }
        devLog("[大纲] 开始生成, ${novel.meta.totalChapters}章")
        val result = chat(prompt, system = system, maxTokens = 4000)
        val outline = parseJsonList<OutlineItem>(result)
        val updated = if (outline.isNotEmpty()) {
            novel.copy(outline = outline)
        } else {
            devLog("[大纲] JSON解析失败, 保存为文本")
            novel.copy(storyOutline = result)
        }
        repo.saveNovel(updated)
        _state.value = _state.value.copy(currentNovel = updated)
        userLog("✅ 大纲生成完成 (${outline.size}章)")
        devLog("[大纲] 完成, ${outline.size}章")
        return updated
    }

    /**
     * 整体大纲 - 对齐桌面版 _generate_overall_outline
     */
    private suspend fun generateOverallOutlineInternal(novel: NovelData): NovelData {
        val system = "你是专业小说大纲规划师。请生成整体大纲，包含：1.故事主线(一句话) 2.主要冲突(2-3个) 3.高潮节点 4.结局走向。输出格式：[{title, description, chapter_range}]"
        val prompt = buildString {
            appendLine("类型：${novel.meta.genre}")
            appendLine("标题：${novel.meta.title}")
            if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
            appendLine("总章数：${novel.meta.totalChapters}")
            if (novel.outline.isNotEmpty()) {
                appendLine("章节标题概要：")
                novel.outline.take(20).forEach { appendLine("第${it.chapter}章 ${it.title}") }
            }
        }
        devLog("[整体大纲] 开始生成")
        val result = chat(prompt, system = system, maxTokens = 4096)
        val updated = novel.copy(overallOutline = result)
        repo.saveNovel(updated)
        _state.value = _state.value.copy(currentNovel = updated)
        userLog("✅ 整体大纲生成完成")
        devLog("[整体大纲] 完成, ${result.length}字")
        return updated
    }

    /**
     * 故事大纲 - 对齐桌面版 _generate_story_outlines
     */
    private suspend fun generateStoryOutlineInternal(novel: NovelData): NovelData {
        val system = "你是专业小说大纲规划师。请生成故事大纲。要求：1.主线故事(3-8个关键事件) 2.副线故事(2-4个关键事件)。输出JSON: {主线: {title, summary, key_events}, 副线: {title, summary, key_events}}"
        val prompt = buildString {
            appendLine("类型：${novel.meta.genre}")
            appendLine("标题：${novel.meta.title}")
            if (novel.meta.concept.isNotEmpty()) appendLine("概念：${novel.meta.concept}")
            appendLine("总章数：${novel.meta.totalChapters}")
        }
        devLog("[故事大纲] 开始生成")
        val result = chat(prompt, system = system, maxTokens = 3000)
        val updated = novel.copy(storyOutline = result)
        repo.saveNovel(updated)
        _state.value = _state.value.copy(currentNovel = updated)
        userLog("✅ 故事大纲生成完成")
        devLog("[故事大纲] 完成, ${result.length}字")
        return updated
    }

    /**
     * 章节生成 - 对齐桌面版 generate_chapter (简化版，无5-Agent协作)
     * 包含：上下文构建 → AI生成 → 保存 → 后处理
     */
    private suspend fun generateChapterInternal(novel: NovelData, chapterNum: Int): NovelData {
        val chapterTitle = novel.outline.find { it.chapter == chapterNum }?.title ?: "第${chapterNum}章"
        val chapterSummary = novel.outline.find { it.chapter == chapterNum }?.summary ?: ""

        // 构建上下文 (对齐桌面版 _build_context)
        val context = buildString {
            // 主角名锁定
            if (novel.meta.protagonist.isNotEmpty()) {
                appendLine("【主角】${novel.meta.protagonist}")
                appendLine()
            }
            // 世界观
            if (novel.worldSettings.isNotEmpty()) {
                appendLine("【世界观】")
                appendLine(novel.worldSettings.take(500))
                appendLine()
            }
            // 整体大纲
            if (novel.overallOutline.isNotEmpty()) {
                appendLine("【整体大纲】")
                appendLine(novel.overallOutline.take(300))
                appendLine()
            }
            // 故事大纲
            if (novel.storyOutline.isNotEmpty()) {
                appendLine("【故事大纲】")
                appendLine(novel.storyOutline.take(300))
                appendLine()
            }
            // 角色信息
            if (novel.characters.isNotEmpty()) {
                appendLine("【主要角色】")
                novel.characters.values.filter { it.category in listOf("主角", "女主") }.forEach { c ->
                    appendLine("${c.name}: ${c.personality.take(50)}")
                }
                appendLine()
            }
            // 前文内容 (对齐桌面版：前一章保留开头600字+结尾1200字)
            val prevChapter = novel.chapters.find { it.chapterNum == chapterNum - 1 }
            if (prevChapter != null) {
                appendLine("【前一章结尾】")
                val prevContent = prevChapter.content
                if (prevContent.length > 1800) {
                    appendLine(prevContent.take(600))
                    appendLine("...")
                    appendLine(prevContent.takeLast(1200))
                } else {
                    appendLine(prevContent)
                }
                appendLine()
            }
            // 更早章节摘要
            val earlierChapters = novel.chapters.filter { it.chapterNum < chapterNum - 1 }.takeLast(3)
            if (earlierChapters.isNotEmpty()) {
                appendLine("【近期章节摘要】")
                earlierChapters.forEach { ch ->
                    appendLine("第${ch.chapterNum}章 ${ch.title}: ${ch.summary.take(100)}")
                }
                appendLine()
            }
            // 完结收束提示
            val remaining = novel.meta.totalChapters - chapterNum
            if (remaining <= 5 && remaining > 0) {
                appendLine("【注意】只剩${remaining}章完结，请开始收束故事线。")
                appendLine()
            }
        }

        val systemPrompt = buildString {
            appendLine("你是专业网络小说作家。直接输出正文，不要Markdown，不要AI式开头结尾。")
            appendLine()
            appendLine(context)
            appendLine("目标字数：${novel.meta.wordCountPerChapter}字")
        }

        val prompt = "创作第${chapterNum}章：${chapterTitle}\n${if (chapterSummary.isNotEmpty()) "大纲：$chapterSummary\n" else ""}直接输出正文："

        devLog("[第${chapterNum}章] 开始生成, title=$chapterTitle")
        val startTime = System.currentTimeMillis()
        val result = chat(prompt, system = systemPrompt, maxTokens = novel.meta.wordCountPerChapter * 2)
        val elapsed = System.currentTimeMillis() - startTime

        val content = result.replace(Regex("^#.*\\n"), "").replace("**", "").trim()
        val chapter = Chapter(
            id = repo.generateId(),
            novelId = novel.meta.id,
            chapterNum = chapterNum,
            title = chapterTitle,
            content = content,
            summary = chapterSummary,
            wordCount = content.length
        )
        repo.saveChapter(novel.meta.id, chapter)
        val updated = repo.getNovel(novel.meta.id) ?: novel
        _state.value = _state.value.copy(currentNovel = updated)

        userLog("✅ 第${chapterNum}章完成 ${content.length}字")
        devLog("[第${chapterNum}章] 完成, ${content.length}字, ${elapsed}ms, ${content.length * 1000 / maxOf(elapsed, 1)}字/秒")

        return updated
    }

    // endregion

    // region Internal Helpers

    private fun launchAI(actionName: String, block: suspend () -> Unit) {
        if (_state.value.isGenerating) {
            userLog("⚠️ 正在生成中，请等待")
            return
        }
        _state.value = _state.value.copy(isGenerating = true, generationProgress = actionName)
        userLog("🔄 $actionName...")
        devLog("[AI] 开始: $actionName")
        viewModelScope.launch {
            try {
                block()
            } catch (e: Exception) {
                userLog("❌ $actionName 失败: ${e.message}")
                devLog("[AI] 异常: $actionName - ${e.message}\n${e.stackTraceToString().take(300)}")
            } finally {
                _state.value = _state.value.copy(isGenerating = false, generationProgress = "")
            }
        }
    }

    private suspend fun chat(prompt: String, system: String = "", maxTokens: Int = 4096): String {
        val config = _state.value.aiConfig
        val messages = listOf(mapOf("role" to "user", "content" to prompt))
        devLog("[API] model=${config.model}, maxTokens=$maxTokens, prompt=${prompt.take(100)}...")
        val startTime = System.currentTimeMillis()
        val result = AIService.chat(config, messages, system = system, maxTokens = maxTokens)
        val elapsed = System.currentTimeMillis() - startTime
        result.onSuccess { content ->
            devLog("[API] 成功 ${elapsed}ms, ${content.length}字, tokens=${AIService.tokenStats.display()}")
        }
        result.onFailure { e ->
            devLog("[API] 失败 ${elapsed}ms: ${e.message}")
        }
        return result.getOrElse { throw it }
    }

    private fun refreshCurrentNovel() {
        val novel = _state.value.currentNovel ?: return
        val refreshed = repo.getNovel(novel.meta.id)
        _state.value = _state.value.copy(currentNovel = refreshed)
        loadNovelList()
    }

    /** 用户日志 - 显示在UI上，告诉用户当前在做什么 */
    private fun userLog(message: String) {
        val entry = LogEntry(type = "user", message = message)
        _state.value = _state.value.copy(
            userLogs = (_state.value.userLogs + entry).takeLast(200)
        )
        Log.i(TAG, "[USER] $message")
    }

    /** 开发者/AI日志 - 深层诊断信息，给AI或开发者看 */
    private fun devLog(message: String) {
        val time = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date())
        val entry = LogEntry(type = "dev", message = "[$time] $message")
        _state.value = _state.value.copy(
            devLogs = (_state.value.devLogs + entry).takeLast(500)
        )
        Log.d(TAG, "[DEV] $message")
    }

    private inline fun <reified T> parseJsonList(json: String): List<T> {
        return try {
            val cleanJson = json.trim().let {
                if (it.startsWith("```")) it.lines().drop(1).dropLast(1).joinToString("\n") else it
            }.let {
                // 提取JSON数组
                val start = it.indexOf('[')
                val end = it.lastIndexOf(']')
                if (start >= 0 && end > start) it.substring(start, end + 1) else it
            }
            val type = com.google.gson.reflect.TypeToken.getParameterized(List::class.java, T::class.java).type
            com.google.gson.Gson().fromJson(cleanJson, type) ?: emptyList()
        } catch (e: Exception) {
            devLog("[JSON] List解析失败: ${e.message}")
            emptyList()
        }
    }

    private inline fun <reified K, reified V> parseJsonMap(json: String): Map<K, V> {
        return try {
            val cleanJson = json.trim().let {
                if (it.startsWith("```")) it.lines().drop(1).dropLast(1).joinToString("\n") else it
            }.let {
                val start = it.indexOf('{')
                val end = it.lastIndexOf('}')
                if (start >= 0 && end > start) it.substring(start, end + 1) else it
            }
            val type = com.google.gson.reflect.TypeToken.getParameterized(Map::class.java, K::class.java, V::class.java).type
            com.google.gson.Gson().fromJson(cleanJson, type) ?: emptyMap()
        } catch (e: Exception) {
            devLog("[JSON] Map解析失败: ${e.message}")
            emptyMap()
        }
    }

    // endregion
}
