package com.ainovelwriter.ui.screen

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showDevLog by remember { mutableStateOf(false) }
    val context = LocalContext.current

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(Primary600, AccentAmber)))
                .statusBarsPadding()
                .padding(horizontal = 20.dp, vertical = 12.dp)
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("日志", style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold, color = Color.White))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    IconButton(onClick = { exportLogs(context, state.userLogs, state.devLogs) }) {
                        Icon(Icons.Default.Share, "导出", tint = Color.White, modifier = Modifier.size(22.dp))
                    }
                    IconButton(onClick = { copyLogs(context, state.userLogs, state.devLogs) }) {
                        Icon(Icons.Default.ContentCopy, "复制", tint = Color.White, modifier = Modifier.size(22.dp))
                    }
                }
            }
        }

        // Tab toggle
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = !showDevLog, onClick = { showDevLog = false },
                label = { Text("用户日志") },
                leadingIcon = if (!showDevLog) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null,
                shape = RoundedCornerShape(8.dp),
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Primary500.copy(alpha = 0.2f), selectedLabelColor = Primary300)
            )
            FilterChip(
                selected = showDevLog, onClick = { showDevLog = true },
                label = { Text("开发者日志") },
                leadingIcon = if (showDevLog) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null,
                shape = RoundedCornerShape(8.dp),
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Warning.copy(alpha = 0.2f), selectedLabelColor = Warning)
            )
            Spacer(Modifier.weight(1f))
            Text(
                "${if (showDevLog) state.devLogs.size else state.userLogs.size}条",
                style = MaterialTheme.typography.labelSmall.copy(color = Text4),
                modifier = Modifier.align(Alignment.CenterVertically)
            )
        }

        // Progress
        if (state.isGenerating) {
            Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(2.dp)), color = Primary400, trackColor = Surface3)
                if (state.generationProgress.isNotEmpty()) {
                    Text(state.generationProgress, style = MaterialTheme.typography.labelSmall.copy(color = Primary300), modifier = Modifier.padding(top = 4.dp))
                }
            }
        }

        // Log content
        val logs = if (showDevLog) state.devLogs else state.userLogs
        val listState = rememberLazyListState()

        if (logs.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("📋", fontSize = 36.sp)
                    Spacer(Modifier.height(12.dp))
                    Text(if (showDevLog) "暂无开发者日志" else "暂无用户日志", style = MaterialTheme.typography.bodyMedium.copy(color = Text3))
                    Text(
                        if (showDevLog) "AI调用详情、Token统计、错误堆栈" else "操作状态和进度信息",
                        style = MaterialTheme.typography.labelSmall.copy(color = Text4)
                    )
                }
            }
        } else {
            LazyColumn(state = listState, modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                items(logs.reversed()) { log ->
                    val color = when {
                        log.message.contains("✅") || log.message.contains("完成") -> Success
                        log.message.contains("❌") || log.message.contains("失败") -> Error
                        log.message.contains("⚠️") || log.message.contains("警告") -> Warning
                        log.message.contains("[API]") || log.message.contains("[JSON]") -> AccentAmber
                        else -> Text3
                    }
                    Text(
                        log.message,
                        style = if (showDevLog) MaterialTheme.typography.labelSmall.copy(fontSize = 11.sp, fontFamily = FontFamily.Monospace, lineHeight = 16.sp)
                        else MaterialTheme.typography.bodySmall.copy(lineHeight = 18.sp),
                        color = color,
                        maxLines = if (showDevLog) 3 else 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp, horizontal = 4.dp)
                    )
                }
            }
            LaunchedEffect(logs.size) { if (logs.isNotEmpty()) listState.animateScrollToItem(0) }
        }
    }
}

private fun exportLogs(context: Context, userLogs: List<com.ainovelwriter.model.LogEntry>, devLogs: List<com.ainovelwriter.model.LogEntry>) {
    val time = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
    val content = buildString {
        appendLine("═══════════════════════════════════════")
        appendLine("  AI小说创作工坊 - 诊断日志")
        appendLine("  导出时间: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())}")
        appendLine("═══════════════════════════════════════")
        appendLine()
        appendLine("━━━ 用户日志 (${userLogs.size}条) ━━━")
        userLogs.forEach { log -> appendLine("[${SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(log.time))}] ${log.message}") }
        appendLine()
        appendLine("━━━ 开发者日志 (${devLogs.size}条) ━━━")
        devLogs.forEach { log -> appendLine(log.message) }
    }
    try {
        val dir = File(context.getExternalFilesDir(null), "logs"); dir.mkdirs()
        val file = File(dir, "AI_NovelWriter_日志_$time.txt"); file.writeText(content)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"; putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, "AI小说工坊诊断日志")
            putExtra(Intent.EXTRA_TEXT, "共${userLogs.size + devLogs.size}条记录")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }, "发送日志到..."))
    } catch (e: Exception) { copyLogs(context, userLogs, devLogs) }
}

private fun copyLogs(context: Context, userLogs: List<com.ainovelwriter.model.LogEntry>, devLogs: List<com.ainovelwriter.model.LogEntry>) {
    val content = buildString {
        appendLine("=== 用户日志 ===")
        userLogs.forEach { log -> appendLine("[${SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(log.time))}] ${log.message}") }
        appendLine(); appendLine("=== 开发者日志 ===")
        devLogs.forEach { log -> appendLine(log.message) }
    }
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("novel_logs", content))
}
