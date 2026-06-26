package com.ainovelwriter.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.model.Chapter
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditorScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val chapter = state.editingChapter

    if (chapter == null) {
        Box(modifier = Modifier.fillMaxSize().background(Surface1), contentAlignment = Alignment.Center) {
            Text("请先选择一个章节进行编辑", color = Text4)
        }
        return
    }

    var content by remember(chapter.id) { mutableStateOf(chapter.content) }
    var showStyleDialog by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(Primary600, Primary500)))
                .statusBarsPadding()
                .padding(horizontal = 12.dp, vertical = 10.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { viewModel.setEditingChapter(null) }) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = Color.White)
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "第${chapter.chapterNum}章 ${chapter.title}",
                        style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold, color = Color.White),
                        maxLines = 1
                    )
                    Text(
                        "${content.length}字",
                        style = MaterialTheme.typography.labelSmall.copy(color = Color.White.copy(alpha = 0.7f))
                    )
                }
                // Save button
                FilledTonalButton(
                    onClick = { viewModel.saveChapter(chapter.copy(content = content, wordCount = content.length)) },
                    colors = ButtonDefaults.filledTonalButtonColors(containerColor = Color.White.copy(alpha = 0.2f), contentColor = Color.White),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.Save, null, Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("保存", style = MaterialTheme.typography.labelMedium)
                }
            }
        }

        // Chapter summary
        if (chapter.summary.isNotEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                colors = CardDefaults.cardColors(containerColor = Primary500.copy(alpha = 0.08f)),
                shape = RoundedCornerShape(10.dp)
            ) {
                Text(
                    "摘要: ${chapter.summary}",
                    style = MaterialTheme.typography.bodySmall.copy(color = Text3),
                    modifier = Modifier.padding(10.dp)
                )
            }
        }

        // Editor
        BasicTextField(
            value = content,
            onValueChange = { content = it },
            modifier = Modifier
                .fillMaxSize()
                .weight(1f)
                .padding(horizontal = 16.dp, vertical = 8.dp),
            textStyle = TextStyle(color = Text1, fontSize = 16.sp, lineHeight = 28.sp),
            cursorBrush = SolidColor(Primary400)
        )

        // Bottom toolbar
        Surface(color = Surface2, shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp)) {
            Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp).navigationBarsPadding()) {
                // Row 1: Primary actions
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    EditorToolButton("AI续写", Icons.Default.Edit, Primary500, !state.isGenerating) { viewModel.aiContinue() }
                    EditorToolButton("AI润色", Icons.Default.AutoFixHigh, AccentCyan, !state.isGenerating) { viewModel.aiPolish() }
                    EditorToolButton("AI扩写", Icons.Default.OpenInFull, AccentAmber, !state.isGenerating) { viewModel.aiExpand() }
                    EditorToolButton("AI审校", Icons.Default.RateReview, AccentEmerald, !state.isGenerating) { viewModel.aiReview() }
                }
                Spacer(Modifier.height(6.dp))
                // Row 2: Extra tools
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    EditorToolButton("去AI味", Icons.Default.FindInPage, Warning, !state.isGenerating) { viewModel.antiSlopCheck() }
                    EditorToolButton("风格转换", Icons.Default.Palette, AccentPurple, !state.isGenerating) { showStyleDialog = true }
                }
            }
        }
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
                        FilterChip(
                            selected = targetStyle == style,
                            onClick = { targetStyle = style },
                            label = { Text(style) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp)
                        )
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { if (targetStyle.isNotEmpty()) viewModel.styleTransfer(targetStyle); showStyleDialog = false }, enabled = targetStyle.isNotEmpty()) { Text("转换") }
            },
            dismissButton = { TextButton(onClick = { showStyleDialog = false }) { Text("取消") } }
        )
    }
}

@Composable
private fun RowScope.EditorToolButton(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, color: androidx.compose.ui.graphics.Color, enabled: Boolean, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.weight(1f),
        enabled = enabled,
        shape = RoundedCornerShape(8.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = color),
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp)
    ) {
        Icon(icon, null, Modifier.size(14.dp))
        Spacer(Modifier.width(3.dp))
        Text(label, style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp))
    }
}
