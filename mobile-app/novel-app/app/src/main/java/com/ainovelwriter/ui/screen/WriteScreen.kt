package com.ainovelwriter.ui.screen

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.model.*
import com.ainovelwriter.ui.component.ProgressRing
import com.ainovelwriter.ui.component.SectionHeader
import com.ainovelwriter.ui.component.StatusBadge
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel
import com.ainovelwriter.viewmodel.Tab

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WriteScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    if (state.currentNovel == null) NovelCreationScreen(viewModel)
    else NovelDetailScreen(viewModel, state)
}

// ==================== Creation Form ====================

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NovelCreationScreen(viewModel: MainViewModel) {
    var title by remember { mutableStateOf("") }
    var genre by remember { mutableStateOf("") }
    var concept by remember { mutableStateOf("") }
    var channel by remember { mutableStateOf("male") }
    var totalChapters by remember { mutableStateOf("50") }
    var wordCountPerChapter by remember { mutableStateOf("3000") }
    var is18Plus by remember { mutableStateOf(false) }
    var isBorderline by remember { mutableStateOf(false) }
    var protagonist by remember { mutableStateOf("") }
    var genreExpanded by remember { mutableStateOf(false) }

    val maleGenres = listOf(
        "玄幻-东方玄幻", "玄幻-异世大陆", "仙侠-古典仙侠", "仙侠-修真文明",
        "都市-都市异能", "都市-商战职场", "历史-架空历史", "历史-秦汉三国",
        "科幻-星际文明", "科幻-时空穿梭", "悬疑-推理侦探", "悬疑-探险生存",
        "游戏-虚拟网游", "游戏-电子竞技", "武侠-传统武侠", "武侠-浪子异侠",
        "军事-战争幻想", "体育-足球运动", "穿越-架空历史", "穿越-都市重生",
        "系统流", "末日-末世危机"
    )
    val femaleGenres = listOf(
        "古代言情-宫廷侯爵", "古代言情-穿越奇情", "现代言情-豪门总裁", "现代言情-都市情缘",
        "幻想言情-仙侣奇缘", "幻想言情-魔法幻情", "纯爱", "百合", "耽美",
        "科幻-未来世界", "悬疑-推理侦探"
    )
    val genres = if (channel == "male") maleGenres else femaleGenres

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(Primary600, AccentPurple)))
                .statusBarsPadding()
                .padding(horizontal = 20.dp, vertical = 16.dp)
        ) {
            Text(
                "创建新小说",
                style = MaterialTheme.typography.headlineSmall.copy(
                    fontWeight = FontWeight.Bold, color = Color.White
                )
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // Title
            OutlinedTextField(
                value = title, onValueChange = { title = it },
                label = { Text("书名") },
                placeholder = { Text("给你的小说起个名字") },
                modifier = Modifier.fillMaxWidth(), singleLine = true,
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
            )

            // Channel
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                listOf("male" to "男频", "female" to "女频").forEach { (value, label) ->
                    val selected = channel == value
                    FilterChip(
                        selected = selected,
                        onClick = { channel = value; genre = "" },
                        label = { Text(label) },
                        leadingIcon = if (selected) {{ Icon(Icons.Default.Check, null, Modifier.size(16.dp)) }} else null,
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = Primary500.copy(alpha = 0.2f),
                            selectedLabelColor = Primary300
                        ),
                        shape = RoundedCornerShape(10.dp)
                    )
                }
            }

            // Genre
            ExposedDropdownMenuBox(expanded = genreExpanded, onExpandedChange = { genreExpanded = it }) {
                OutlinedTextField(
                    value = genre, onValueChange = {}, readOnly = true,
                    label = { Text("类型") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(genreExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400)
                )
                ExposedDropdownMenu(expanded = genreExpanded, onDismissRequest = { genreExpanded = false }) {
                    genres.forEach { g ->
                        DropdownMenuItem(
                            text = { Text(g) },
                            onClick = { genre = g; genreExpanded = false },
                            leadingIcon = { Text(GenreIcons.get(g)) }
                        )
                    }
                }
            }

            // Protagonist
            OutlinedTextField(
                value = protagonist, onValueChange = { protagonist = it },
                label = { Text("主角名（可选）") },
                placeholder = { Text("锁定主角名，AI会自动使用") },
                modifier = Modifier.fillMaxWidth(), singleLine = true,
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
            )

            // Concept
            OutlinedTextField(
                value = concept, onValueChange = { concept = it },
                label = { Text("故事概念") },
                placeholder = { Text("简单描述你的故事想法") },
                modifier = Modifier.fillMaxWidth().height(100.dp),
                maxLines = 4,
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
            )

            // Chapters & Words
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = totalChapters,
                    onValueChange = { totalChapters = it.filter { c -> c.isDigit() } },
                    label = { Text("总章数") },
                    modifier = Modifier.weight(1f), singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
                )
                OutlinedTextField(
                    value = wordCountPerChapter,
                    onValueChange = { wordCountPerChapter = it.filter { c -> c.isDigit() } },
                    label = { Text("每章字数") },
                    modifier = Modifier.weight(1f), singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
                )
            }

            // Toggles
            Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("18+ 成人内容", style = MaterialTheme.typography.bodyMedium)
                            Text("包含成人向情节", style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                        }
                        Switch(checked = is18Plus, onCheckedChange = { is18Plus = it })
                    }
                    HorizontalDivider(color = Surface4, modifier = Modifier.padding(vertical = 4.dp))
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("擦边内容", style = MaterialTheme.typography.bodyMedium)
                            Text("包含擦边球情节", style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                        }
                        Switch(checked = isBorderline, onCheckedChange = { isBorderline = it })
                    }
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Create button
            Button(
                onClick = {
                    viewModel.createNovel(
                        title = title, genre = genre, concept = concept,
                        channel = channel,
                        totalChapters = totalChapters.toIntOrNull() ?: 50,
                        wordCountPerChapter = wordCountPerChapter.toIntOrNull() ?: 3000,
                        is18Plus = is18Plus, isBorderline = isBorderline,
                        protagonist = protagonist
                    )
                },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                enabled = title.isNotBlank() && genre.isNotBlank(),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Primary500)
            ) {
                Icon(Icons.Default.AutoAwesome, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("创建小说", style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

// ==================== Detail View ====================

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NovelDetailScreen(viewModel: MainViewModel, state: com.ainovelwriter.viewmodel.MainUiState) {
    val novel = state.currentNovel ?: return
    var selectedSubTab by remember { mutableStateOf("概览") }
    val subTabs = listOf("概览", "大纲", "角色", "世界观", "笔记")
    val progress = if (novel.meta.totalChapters > 0) novel.chapters.size.toFloat() / novel.meta.totalChapters else 0f
    val genreColor = GenreColors.get(novel.meta.genre)

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header with gradient
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(genreColor.primary, genreColor.primary.copy(alpha = 0.7f))))
                .statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { viewModel.closeNovel() }) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = Color.White)
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        novel.meta.title,
                        style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold, color = Color.White),
                        maxLines = 1
                    )
                    Text(
                        "${novel.meta.genre} · ${novel.chapters.size}/${novel.meta.totalChapters}章 · ${(progress * 100).toInt()}%",
                        style = MaterialTheme.typography.labelSmall.copy(color = Color.White.copy(alpha = 0.8f))
                    )
                }
                ProgressRing(progress = progress, size = 44.dp, strokeWidth = 3.dp)
            }
        }

        // Sub-tabs
        ScrollableTabRow(
            selectedTabIndex = subTabs.indexOf(selectedSubTab),
            containerColor = Surface2,
            contentColor = Primary400,
            edgePadding = 12.dp,
            divider = {}
        ) {
            subTabs.forEach { tab ->
                Tab(
                    selected = selectedSubTab == tab,
                    onClick = { selectedSubTab = tab },
                    text = {
                        Text(
                            tab,
                            style = MaterialTheme.typography.labelLarge.copy(
                                fontWeight = if (selectedSubTab == tab) FontWeight.Bold else FontWeight.Normal,
                                color = if (selectedSubTab == tab) Primary300 else Text4
                            )
                        )
                    }
                )
            }
        }

        // Content
        when (selectedSubTab) {
            "概览" -> OverviewTab(viewModel, novel, state, progress)
            "大纲" -> OutlineTab(viewModel, novel, state)
            "角色" -> CharactersTab(viewModel, novel, state)
            "世界观" -> WorldTab(viewModel, novel, state)
            "笔记" -> NotesTab(viewModel, novel)
        }
    }
}

// ==================== 概览 Tab ====================

@Composable
private fun OverviewTab(viewModel: MainViewModel, novel: NovelData, state: com.ainovelwriter.viewmodel.MainUiState, progress: Float) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Action buttons
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = { viewModel.generateChapter(novel.chapters.size + 1) },
                    enabled = !state.isGenerating,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Primary500)
                ) {
                    if (state.isGenerating) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Color.White)
                    else Icon(Icons.Default.AutoAwesome, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("开始创作")
                }
                Button(
                    onClick = { viewModel.autoGenerate() },
                    enabled = !state.isGenerating,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Success)
                ) {
                    Icon(Icons.Default.PlaylistAdd, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("自动创作")
                }
            }
        }

        // Generating progress
        if (state.isGenerating) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Primary500.copy(alpha = 0.1f)), shape = RoundedCornerShape(12.dp)) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = Primary400)
                            Spacer(Modifier.width(10.dp))
                            Text(state.generationProgress.ifEmpty { "生成中..." }, style = MaterialTheme.typography.bodySmall.copy(color = Primary300))
                        }
                        Spacer(Modifier.height(8.dp))
                        Button(
                            onClick = { viewModel.stopGeneration() },
                            colors = ButtonDefaults.buttonColors(containerColor = Error),
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 6.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.Stop, null, Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("停止生成", style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
            }
        }

        // Chapter list
        item {
            SectionHeader("章节列表", if (novel.chapters.isNotEmpty()) "${novel.chapters.size}章" else null)
        }

        if (novel.chapters.isEmpty()) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                    Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("📝", fontSize = 32.sp)
                            Spacer(Modifier.height(8.dp))
                            Text("暂无章节", style = MaterialTheme.typography.bodyMedium.copy(color = Text4))
                            Text("点击「开始创作」生成第一章", style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                        }
                    }
                }
            }
        } else {
            items(novel.chapters.sortedByDescending { it.chapterNum }) { chapter ->
                Card(
                    onClick = { viewModel.setEditingChapter(chapter); viewModel.setTab(Tab.OUTLINE) },
                    colors = CardDefaults.cardColors(containerColor = Surface2),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Row(modifier = Modifier.padding(14.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).background(Surface3),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("${chapter.chapterNum}", style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold, color = Primary400))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                chapter.title.ifEmpty { "第${chapter.chapterNum}章" },
                                style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Medium),
                                maxLines = 1
                            )
                            Text("${chapter.wordCount}字", style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                        }
                        Icon(Icons.Default.ChevronRight, null, tint = Text4, modifier = Modifier.size(20.dp))
                    }
                }
            }
        }
    }
}

// ==================== 大纲 Tab ====================

@Composable
private fun OutlineTab(viewModel: MainViewModel, novel: NovelData, state: com.ainovelwriter.viewmodel.MainUiState) {
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { viewModel.generateOutline() }, enabled = !state.isGenerating, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                    Text("章节大纲")
                }
                OutlinedButton(onClick = { viewModel.generateOverallOutline() }, enabled = !state.isGenerating, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                    Text("整体大纲")
                }
            }
            OutlinedButton(onClick = { viewModel.generateStoryOutline() }, enabled = !state.isGenerating, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text("故事大纲")
            }
        }

        if (novel.outline.isNotEmpty()) {
            item { SectionHeader("章节大纲", "${novel.outline.size}章") }
            items(novel.outline) { item ->
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(10.dp)) {
                    Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
                        Box(modifier = Modifier.size(28.dp).clip(RoundedCornerShape(6.dp)).background(Primary500.copy(alpha = 0.15f)), contentAlignment = Alignment.Center) {
                            Text("${item.chapter}", style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, color = Primary400))
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(item.title, style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Medium))
                            if (item.summary.isNotEmpty()) Text(item.summary, style = MaterialTheme.typography.bodySmall.copy(color = Text3), maxLines = 3)
                        }
                    }
                }
            }
        }

        if (novel.overallOutline.isNotEmpty()) {
            item { SectionHeader("整体大纲") }
            item { Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(10.dp)) { Text(novel.overallOutline, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(14.dp)) } }
        }
        if (novel.storyOutline.isNotEmpty()) {
            item { SectionHeader("故事大纲") }
            item { Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(10.dp)) { Text(novel.storyOutline, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(14.dp)) } }
        }
    }
}

// ==================== 角色 Tab ====================

@Composable
private fun CharactersTab(viewModel: MainViewModel, novel: NovelData, state: com.ainovelwriter.viewmodel.MainUiState) {
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Button(onClick = { viewModel.generateCharacters() }, enabled = !state.isGenerating, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Default.PersonAdd, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("AI生成角色")
            }
        }
        if (novel.characters.isNotEmpty()) {
            item { SectionHeader("角色列表", "${novel.characters.size}个") }
            items(novel.characters.entries.toList()) { (name, char) ->
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(modifier = Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(Primary500.copy(alpha = 0.15f)), contentAlignment = Alignment.Center) {
                                Text(name.take(1), style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold, color = Primary400))
                            }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(name, style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                                if (char.category.isNotEmpty()) StatusBadge(char.category, AccentPurple)
                            }
                        }
                        if (char.personality.isNotEmpty()) {
                            Spacer(Modifier.height(8.dp))
                            Text("性格: ${char.personality}", style = MaterialTheme.typography.bodySmall.copy(color = Text3), maxLines = 2)
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                            char.attributes.forEach { (attr, value) ->
                                Surface(color = Surface3, shape = RoundedCornerShape(6.dp)) {
                                    Text(
                                        "$attr $value",
                                        style = MaterialTheme.typography.labelSmall.copy(color = Text3),
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        } else {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                    Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("👤", fontSize = 32.sp)
                            Spacer(Modifier.height(8.dp))
                            Text("暂无角色", style = MaterialTheme.typography.bodyMedium.copy(color = Text4))
                        }
                    }
                }
            }
        }
    }
}

// ==================== 世界观 Tab ====================

@Composable
private fun WorldTab(viewModel: MainViewModel, novel: NovelData, state: com.ainovelwriter.viewmodel.MainUiState) {
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Button(onClick = { viewModel.generateWorld() }, enabled = !state.isGenerating, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Default.Public, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("生成世界观")
            }
        }
        if (novel.worldSettings.isNotEmpty()) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text("世界观设定", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                        Spacer(Modifier.height(8.dp))
                        Text(novel.worldSettings, style = MaterialTheme.typography.bodySmall.copy(lineHeight = 22.sp))
                    }
                }
            }
        } else {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(12.dp)) {
                    Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("🌍", fontSize = 32.sp)
                            Spacer(Modifier.height(8.dp))
                            Text("暂未生成世界观", style = MaterialTheme.typography.bodyMedium.copy(color = Text4))
                        }
                    }
                }
            }
        }
    }
}

// ==================== 笔记 Tab ====================

@Composable
private fun NotesTab(viewModel: MainViewModel, novel: NovelData) {
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            OutlinedButton(
                onClick = {
                    val updated = novel.copy(notes = novel.notes + Note(
                        id = java.util.UUID.randomUUID().toString(),
                        title = "新笔记", content = "",
                        createdAt = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.getDefault()).format(java.util.Date())
                    ))
                    viewModel.updateCurrentNovel(updated)
                },
                shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.Add, null); Spacer(Modifier.width(8.dp)); Text("添加笔记")
            }
        }
        if (novel.notes.isNotEmpty()) {
            items(novel.notes) { note ->
                Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(10.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text(note.title, style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Medium))
                        if (note.content.isNotEmpty()) {
                            Spacer(Modifier.height(4.dp))
                            Text(note.content, style = MaterialTheme.typography.bodySmall.copy(color = Text3), maxLines = 3)
                        }
                    }
                }
            }
        }
    }
}
