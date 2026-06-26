package com.ainovelwriter.ui.component

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel
import com.ainovelwriter.viewmodel.Tab

// ==================== Bottom Navigation Bar ====================

data class NavItem(
    val tab: Tab,
    val label: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector,
)

private val navItems = listOf(
    NavItem(Tab.NOVELS, "书架", Icons.Filled.Book, Icons.Outlined.Book),
    NavItem(Tab.CHAPTER, "创作", Icons.Filled.Edit, Icons.Outlined.Edit),
    NavItem(Tab.LOGS, "工具", Icons.Filled.Build, Icons.Outlined.Build),
    NavItem(Tab.WORLD, "日志", Icons.Filled.Assessment, Icons.Outlined.Assessment),
    NavItem(Tab.SETTINGS, "设置", Icons.Filled.Settings, Icons.Outlined.Settings),
)

@Composable
fun BottomNavBar(currentTab: Tab, onTabSelected: (Tab) -> Unit) {
    NavigationBar(
        containerColor = Surface2,
        tonalElevation = 0.dp,
        modifier = Modifier.clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp))
    ) {
        navItems.forEach { item ->
            val selected = currentTab == item.tab
            NavigationBarItem(
                icon = {
                    Icon(
                        imageVector = if (selected) item.selectedIcon else item.unselectedIcon,
                        contentDescription = item.label,
                        modifier = Modifier.size(24.dp)
                    )
                },
                label = {
                    Text(
                        item.label,
                        style = MaterialTheme.typography.labelSmall.copy(
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                            fontSize = 10.sp
                        )
                    )
                },
                selected = selected,
                onClick = { onTabSelected(item.tab) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Primary400,
                    selectedTextColor = Primary300,
                    unselectedIconColor = Text4,
                    unselectedTextColor = Text4,
                    indicatorColor = Primary500.copy(alpha = 0.12f)
                )
            )
        }
    }
}

// ==================== Gradient Header ====================

@Composable
fun GradientHeader(title: String, subtitle: String? = null) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                Brush.horizontalGradient(listOf(Primary600, Primary500, AccentPurple))
            )
            .padding(horizontal = 20.dp, vertical = 16.dp)
    ) {
        Column {
            Text(
                title,
                style = MaterialTheme.typography.headlineSmall.copy(
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
            )
            if (subtitle != null) {
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.labelSmall.copy(
                        color = Color.White.copy(alpha = 0.7f)
                    )
                )
            }
        }
    }
}

// ==================== Status Badge ====================

@Composable
fun StatusBadge(text: String, color: androidx.compose.ui.graphics.Color) {
    Surface(
        color = color.copy(alpha = 0.15f),
        shape = RoundedCornerShape(4.dp)
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall.copy(
                color = color,
                fontSize = 10.sp,
                fontWeight = FontWeight.SemiBold
            ),
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
        )
    }
}

// ==================== Progress Ring ====================

@Composable
fun ProgressRing(
    progress: Float,
    modifier: Modifier = Modifier,
    size: androidx.compose.ui.unit.Dp = 48.dp,
    strokeWidth: androidx.compose.ui.unit.Dp = 4.dp,
) {
    Box(modifier = modifier.size(size), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(
            progress = { progress },
            modifier = Modifier.fillMaxSize(),
            strokeWidth = strokeWidth,
            color = Primary400,
            trackColor = Surface3,
        )
        Text(
            "${(progress * 100).toInt()}%",
            style = MaterialTheme.typography.labelSmall.copy(
                fontWeight = FontWeight.Bold,
                fontSize = 10.sp
            )
        )
    }
}

// ==================== Section Header ====================

@Composable
fun SectionHeader(title: String, action: String? = null, onAction: (() -> Unit)? = null) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            title,
            style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold)
        )
        if (action != null && onAction != null) {
            TextButton(onClick = onAction, contentPadding = PaddingValues(0.dp)) {
                Text(action, style = MaterialTheme.typography.labelMedium.copy(color = Primary400))
            }
        }
    }
}

private val Color = androidx.compose.ui.graphics.Color
