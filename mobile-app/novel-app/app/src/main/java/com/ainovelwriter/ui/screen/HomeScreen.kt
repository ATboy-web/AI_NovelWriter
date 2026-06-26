package com.ainovelwriter.ui.screen

import androidx.compose.animation.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.model.NovelMeta
import com.ainovelwriter.ui.component.StatusBadge
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel
import com.ainovelwriter.viewmodel.Tab

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var novelToDelete by remember { mutableStateOf<NovelMeta?>(null) }

    Scaffold(
        topBar = {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Brush.horizontalGradient(listOf(Primary600, Primary500, AccentPurple)))
                    .statusBarsPadding()
                    .padding(horizontal = 20.dp, vertical = 16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            "我的书架",
                            style = MaterialTheme.typography.headlineSmall.copy(
                                fontWeight = FontWeight.Bold,
                                color = androidx.compose.ui.graphics.Color.White
                            )
                        )
                        Text(
                            "${state.novelList.size} 本小说",
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.7f)
                            )
                        )
                    }
                    FilledIconButton(
                        onClick = { viewModel.setTab(Tab.CHAPTER) },
                        colors = IconButtonDefaults.filledIconButtonColors(
                            containerColor = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.2f),
                            contentColor = androidx.compose.ui.graphics.Color.White
                        ),
                        modifier = Modifier.size(40.dp)
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "新建", modifier = Modifier.size(20.dp))
                    }
                }
            }
        }
    ) { padding ->
        if (state.novelList.isEmpty()) {
            EmptyBookshelf(
                onStartCreate = { viewModel.setTab(Tab.CHAPTER) },
                modifier = Modifier.padding(padding)
            )
        } else {
            LazyColumn(
                modifier = Modifier.padding(padding).fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(state.novelList, key = { it.id }) { novel ->
                    NovelCard(
                        novel = novel,
                        onClick = { viewModel.openNovel(novel.id) },
                        onLongClick = { novelToDelete = novel }
                    )
                }
                // 底部间距
                item { Spacer(modifier = Modifier.height(8.dp)) }
            }
        }
    }

    novelToDelete?.let { novel ->
        AlertDialog(
            onDismissRequest = { novelToDelete = null },
            icon = { Icon(Icons.Default.DeleteForever, contentDescription = null, tint = Error) },
            title = { Text("删除小说") },
            text = { Text("确定要删除「${novel.title}」吗？\n此操作不可恢复。") },
            confirmButton = {
                TextButton(
                    onClick = { viewModel.deleteNovel(novel.id); novelToDelete = null },
                    colors = ButtonDefaults.textButtonColors(contentColor = Error)
                ) { Text("删除") }
            },
            dismissButton = {
                TextButton(onClick = { novelToDelete = null }) { Text("取消") }
            }
        )
    }
}

@Composable
private fun EmptyBookshelf(onStartCreate: () -> Unit, modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(32.dp)) {
            Box(
                modifier = Modifier
                    .size(96.dp)
                    .clip(CircleShape)
                    .background(Surface3),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Outlined.MenuBook,
                    contentDescription = null,
                    modifier = Modifier.size(48.dp),
                    tint = Text4
                )
            }
            Spacer(modifier = Modifier.height(20.dp))
            Text(
                "书架空空如也",
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.SemiBold),
                color = Text2
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                "创建你的第一部小说\n让AI帮你构建精彩故事",
                style = MaterialTheme.typography.bodyMedium,
                color = Text4,
                lineHeight = 22.sp
            )
            Spacer(modifier = Modifier.height(28.dp))
            Button(
                onClick = onStartCreate,
                colors = ButtonDefaults.buttonColors(containerColor = Primary500),
                shape = RoundedCornerShape(12.dp),
                contentPadding = PaddingValues(horizontal = 28.dp, vertical = 14.dp)
            ) {
                Icon(Icons.Default.AutoAwesome, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("开始创作", style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun NovelCard(novel: NovelMeta, onClick: () -> Unit, onLongClick: () -> Unit) {
    val progress = if (novel.totalChapters > 0) novel.chapterCount.toFloat() / novel.totalChapters else 0f
    val genreColor = GenreColors.get(novel.genre)
    val genreIcon = GenreIcons.get(novel.genre)

    Card(
        modifier = Modifier.fillMaxWidth().animateContentSize(),
        onClick = onClick,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface2),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            // Genre icon
            Box(
                modifier = Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(genreColor.container),
                contentAlignment = Alignment.Center
            ) {
                Text(genreIcon, fontSize = 24.sp)
            }

            Spacer(modifier = Modifier.width(14.dp))

            // Info
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    novel.title,
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    StatusBadge(novel.genre.substringBefore("-").ifEmpty { "未分类" }, genreColor.primary)
                    StatusBadge(
                        if (novel.channel == "male") "男频" else "女频",
                        if (novel.channel == "male") Info else AccentPink
                    )
                    if (novel.is18Plus) StatusBadge("18+", Error)
                    if (novel.isBorderline) StatusBadge("擦边", Warning)
                }
                Spacer(modifier = Modifier.height(10.dp))
                // Progress bar
                LinearProgressIndicator(
                    progress = { progress },
                    modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)),
                    color = genreColor.primary,
                    trackColor = Surface3,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(
                        "${novel.chapterCount}/${novel.totalChapters}章",
                        style = MaterialTheme.typography.labelSmall.copy(color = Text4)
                    )
                    Text(
                        "${(progress * 100).toInt()}%",
                        style = MaterialTheme.typography.labelSmall.copy(
                            color = genreColor.primary,
                            fontWeight = FontWeight.SemiBold
                        )
                    )
                }
            }
        }
    }
}
