package com.ainovelwriter

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.ainovelwriter.ui.component.BottomNavBar
import com.ainovelwriter.ui.screen.*
import com.ainovelwriter.ui.theme.AINovelWriterTheme
import com.ainovelwriter.viewmodel.MainViewModel
import com.ainovelwriter.viewmodel.Tab

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AINovelWriterTheme {
                MainApp()
            }
        }
    }
}

@Composable
fun MainApp(viewModel: MainViewModel = viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        bottomBar = {
            BottomNavBar(
                currentTab = state.currentTab,
                onTabSelected = { viewModel.setTab(it) }
            )
        }
    ) { innerPadding ->
        when (state.currentTab) {
            Tab.NOVELS -> HomeScreen(viewModel)
            Tab.CHAPTER -> WriteScreen(viewModel)
            Tab.OUTLINE -> {
                if (state.editingChapter != null) {
                    EditorScreen(viewModel)
                } else {
                    WriteScreen(viewModel)
                }
            }
            Tab.LOGS -> ToolsScreen(viewModel)
            Tab.WORLD -> LogScreen(viewModel)     // 日志页
            Tab.SETTINGS -> SettingsScreen(viewModel)
            Tab.CHARACTERS -> WriteScreen(viewModel)
        }
    }
}
