package com.ainovelwriter.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.service.AIService
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel

data class ToolItem(
    val title: String,
    val icon: ImageVector,
    val description: String,
    val color: Color,
    val requiresAPI: Boolean = true,
    val action: (MainViewModel) -> Unit
)

private val tools = listOf(
    ToolItem("自动创作", Icons.Default.AutoAwesome, "一键完成全部流程", AccentPurple) { vm -> vm.autoGenerate() },
    ToolItem("生成世界观", Icons.Default.Public, "AI构建世界观", AccentCyan) { vm -> vm.generateWorld() },
    ToolItem("生成角色", Icons.Default.Person, "自动生成角色", AccentPink) { vm -> vm.generateCharacters() },
    ToolItem("生成大纲", Icons.Default.List, "章节大纲", Info) { vm -> vm.generateOutline() },
    ToolItem("整体大纲", Icons.Default.AccountTree, "全书规划", AccentAmber) { vm -> vm.generateOverallOutline() },
    ToolItem("故事大纲", Icons.Default.MenuBook, "主线/副线", AccentEmerald) { vm -> vm.generateStoryOutline() },
    ToolItem("去AI味", Icons.Default.FindInPage, "检查AI痕迹", Warning) { vm -> vm.antiSlopCheck() },
    ToolItem("风格转换", Icons.Default.Palette, "转换文风", AccentPurple) { vm -> vm.styleTransfer("古风") },
    ToolItem("整合素材", Icons.Default.Hub, "已有素材→生成大纲", AccentAmber) { vm -> vm.integrateSettings() },
    ToolItem("情景对话", Icons.Default.Forum, "多角色对话", AccentCyan) { vm -> vm.generateDialogue("主角", "日常") },
    ToolItem("书籍简介", Icons.Default.AutoStories, "生成简介", AccentPink) { vm -> vm.generateSynopsis() },
    ToolItem("导出TXT", Icons.Default.FileDownload, "导出小说", AccentEmerald) { vm -> vm.exportTxt() },
    ToolItem("Token用量", Icons.Default.DataUsage, "API统计", Text3, requiresAPI = false) { }
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ToolsScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showTokenDialog by remember { mutableStateOf(false) }
    var showStyleDialog by remember { mutableStateOf(false) }
    var showDialogueDialog by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(Primary600, AccentCyan)))
                .statusBarsPadding()
                .padding(horizontal = 20.dp, vertical = 16.dp)
        ) {
            Column {
                Text("工具箱", style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold, color = Color.White))
                if (state.currentNovel != null) {
                    Text("当前: ${state.currentNovel!!.meta.title}", style = MaterialTheme.typography.labelSmall.copy(color = Color.White.copy(alpha = 0.7f)))
                }
            }
        }

        // API status hint
        val hasAPI = state.aiConfig.apiKey.isNotEmpty()
        if (!hasAPI) {
            Card(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                colors = CardDefaults.cardColors(containerColor = Warning.copy(alpha = 0.1f)),
                shape = RoundedCornerShape(10.dp)
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(Icons.Default.Warning, null, tint = Warning, modifier = Modifier.size(18.dp))
                    Column {
                        Text("需要配置API", style = MaterialTheme.typography.labelMedium.copy(color = Warning, fontWeight = FontWeight.SemiBold))
                        Text("请到「设置」页面填写API Key并保存", style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                    }
                }
            }
        }

        // Progress
        if (state.isGenerating) {
            Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(2.dp)), color = Primary400, trackColor = Surface3)
                if (state.generationProgress.isNotEmpty()) {
                    Text(state.generationProgress, style = MaterialTheme.typography.labelSmall.copy(color = Primary300), modifier = Modifier.padding(top = 4.dp))
                }
            }
        }

        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            contentPadding = PaddingValues(12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            items(tools) { tool ->
                val hasAPI = state.aiConfig.apiKey.isNotEmpty()
                val enabled = (!tool.requiresAPI || hasAPI) && !state.isGenerating
                ToolCard(
                    tool = tool,
                    enabled = enabled,
                    onClick = {
                        when (tool.title) {
                            "Token用量" -> showTokenDialog = true
                            "风格转换" -> showStyleDialog = true
                            "情景对话" -> showDialogueDialog = true
                            else -> tool.action(viewModel)
                        }
                    }
                )
            }
        }
    }

    // Token dialog
    if (showTokenDialog) {
        AlertDialog(
            onDismissRequest = { showTokenDialog = false },
            icon = { Icon(Icons.Default.DataUsage, null, tint = Primary400) },
            title = { Text("Token用量") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(AIService.tokenStats.display(), style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold))
                    HorizontalDivider(color = Surface4)
                    Text("Prompt: ${AIService.tokenStats.promptTokens}", style = MaterialTheme.typography.bodyMedium)
                    Text("Completion: ${AIService.tokenStats.completionTokens}", style = MaterialTheme.typography.bodyMedium)
                    Text("请求次数: ${AIService.tokenStats.requestCount}", style = MaterialTheme.typography.bodyMedium)
                }
            },
            confirmButton = { TextButton(onClick = { showTokenDialog = false }) { Text("关闭") } }
        )
    }

    // Style dialog
    if (showStyleDialog) {
        var targetStyle by remember { mutableStateOf("") }
        val styles = listOf("热血爽文", "文艺清新", "悬疑惊悚", "轻松幽默", "史诗宏大", "古风典雅", "现代都市", "科幻硬核")
        AlertDialog(
            onDismissRequest = { showStyleDialog = false },
            title = { Text("选择目标风格") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    styles.forEach { style ->
                        FilterChip(selected = targetStyle == style, onClick = { targetStyle = style }, label = { Text(style) }, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(8.dp))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { if (targetStyle.isNotEmpty()) viewModel.styleTransfer(targetStyle); showStyleDialog = false }, enabled = targetStyle.isNotEmpty()) { Text("转换") } },
            dismissButton = { TextButton(onClick = { showStyleDialog = false }) { Text("取消") } }
        )
    }

    // Dialogue dialog
    if (showDialogueDialog) {
        var characterName by remember { mutableStateOf("") }
        var scene by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { showDialogueDialog = false },
            title = { Text("生成情景对话") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(value = characterName, onValueChange = { characterName = it }, label = { Text("角色名") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(10.dp))
                    OutlinedTextField(value = scene, onValueChange = { scene = it }, label = { Text("场景描述") }, modifier = Modifier.fillMaxWidth(), maxLines = 3, shape = RoundedCornerShape(10.dp))
                }
            },
            confirmButton = { TextButton(onClick = { if (characterName.isNotBlank()) viewModel.generateDialogue(characterName, scene); showDialogueDialog = false }, enabled = characterName.isNotBlank()) { Text("生成") } },
            dismissButton = { TextButton(onClick = { showDialogueDialog = false }) { Text("取消") } }
        )
    }
}

@Composable
private fun ToolCard(tool: ToolItem, enabled: Boolean, onClick: () -> Unit) {
    Card(
        onClick = onClick, enabled = enabled, shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = Surface2, disabledContainerColor = Surface2.copy(alpha = 0.5f))
    ) {
        Column(
            modifier = Modifier.padding(14.dp).fillMaxWidth().height(100.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(
                modifier = Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(tool.color.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(tool.icon, null, tint = if (enabled) tool.color else Text4, modifier = Modifier.size(22.dp))
            }
            Spacer(Modifier.height(8.dp))
            Text(tool.title, style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold), textAlign = TextAlign.Center, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(tool.description, style = MaterialTheme.typography.labelSmall.copy(color = Text4), textAlign = Alignment.CenterVertically.let { TextAlign.Center }, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}
