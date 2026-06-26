package com.ainovelwriter.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ainovelwriter.model.AIConfig
import com.ainovelwriter.service.AIService
import com.ainovelwriter.ui.theme.*
import com.ainovelwriter.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val config = state.aiConfig

    var endpoint by remember(config.endpoint) { mutableStateOf(config.endpoint) }
    var apiKey by remember(config.apiKey) { mutableStateOf(config.apiKey) }
    var model by remember(config.model) { mutableStateOf(config.model) }
    var thinking by remember(config.thinking) { mutableStateOf(config.thinking) }
    var showTestResult by remember { mutableStateOf<String?>(null) }
    var isTesting by remember { mutableStateOf(false) }
    var showApiKey by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    val supportedModels = listOf(
        "deepseek-v4-flash" to "DeepSeek V4 Flash",
        "deepseek-v4" to "DeepSeek V4",
        "deepseek-r1" to "DeepSeek R1",
        "glm-5-flash" to "GLM-5 Flash",
        "glm-5" to "GLM-5",
        "qwen-max" to "Qwen Max",
        "qwen-plus" to "Qwen Plus",
        "kimi-k2.7" to "Kimi K2.7",
        "claude-sonnet-4-20250514" to "Claude Sonnet 4",
        "gpt-4o" to "GPT-4o"
    )

    Column(modifier = Modifier.fillMaxSize().background(Surface1)) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.horizontalGradient(listOf(Primary600, AccentEmerald)))
                .statusBarsPadding()
                .padding(horizontal = 20.dp, vertical = 16.dp)
        ) {
            Text("设置", style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold, color = Color.White))
        }

        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // API Config
            Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(14.dp)) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("API 配置", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))

                    OutlinedTextField(
                        value = endpoint, onValueChange = { endpoint = it },
                        label = { Text("API Endpoint") },
                        modifier = Modifier.fillMaxWidth(), singleLine = true,
                        leadingIcon = { Icon(Icons.Default.Link, null, tint = Primary400) },
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
                    )

                    OutlinedTextField(
                        value = apiKey, onValueChange = { apiKey = it },
                        label = { Text("API Key") },
                        modifier = Modifier.fillMaxWidth(), singleLine = true,
                        leadingIcon = { Icon(Icons.Default.Key, null, tint = Primary400) },
                        visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = {
                            IconButton(onClick = { showApiKey = !showApiKey }) {
                                Icon(if (showApiKey) Icons.Default.VisibilityOff else Icons.Default.Visibility, null, tint = Text4)
                            }
                        },
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
                    )

                    OutlinedTextField(
                        value = model, onValueChange = { model = it },
                        label = { Text("模型名称") },
                        modifier = Modifier.fillMaxWidth(), singleLine = true,
                        leadingIcon = { Icon(Icons.Default.SmartToy, null, tint = Primary400) },
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary400, cursorColor = Primary400)
                    )
                }
            }

            // Thinking mode
            Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(14.dp)) {
                Row(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("深度思考模式", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                        Text("启用后AI会进行更深入的推理", style = MaterialTheme.typography.bodySmall.copy(color = Text4))
                    }
                    Switch(checked = thinking, onCheckedChange = { thinking = it })
                }
            }

            // Action buttons
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = { viewModel.updateAIConfig(AIConfig(endpoint = endpoint, apiKey = apiKey, model = model, thinking = thinking)) },
                    modifier = Modifier.weight(1f), shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Primary500)
                ) {
                    Icon(Icons.Default.Save, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("保存配置")
                }
                OutlinedButton(
                    onClick = {
                        isTesting = true; scope.launch {
                            val success = AIService.testConnection(AIConfig(endpoint = endpoint, apiKey = apiKey, model = model, thinking = thinking))
                            showTestResult = if (success) "连接成功!" else "连接失败，请检查配置"
                            isTesting = false
                        }
                    },
                    modifier = Modifier.weight(1f), enabled = !isTesting, shape = RoundedCornerShape(10.dp)
                ) {
                    if (isTesting) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Primary400)
                    else Icon(Icons.Default.NetworkCheck, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp)); Text("测试连接")
                }
            }

            // Test result
            showTestResult?.let { result ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = if (result.contains("成功")) Success.copy(alpha = 0.1f) else Error.copy(alpha = 0.1f)),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            if (result.contains("成功")) Icons.Default.CheckCircle else Icons.Default.Error, null,
                            tint = if (result.contains("成功")) Success else Error, modifier = Modifier.size(20.dp)
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(result, style = MaterialTheme.typography.bodyMedium.copy(color = if (result.contains("成功")) Success else Error))
                    }
                }
            }

            // Supported models
            Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(14.dp)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("支持的模型", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                    Spacer(Modifier.height(8.dp))
                    supportedModels.forEach { (modelId, modelName) ->
                        Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = model == modelId, onClick = { model = modelId }, colors = RadioButtonDefaults.colors(selectedColor = Primary400))
                            Spacer(Modifier.width(6.dp))
                            Column {
                                Text(modelName, style = MaterialTheme.typography.bodyMedium)
                                Text(modelId, style = MaterialTheme.typography.labelSmall.copy(color = Text4))
                            }
                        }
                    }
                }
            }

            // About
            Card(colors = CardDefaults.cardColors(containerColor = Surface2), shape = RoundedCornerShape(14.dp)) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Default.Info, null, tint = Primary400, modifier = Modifier.size(20.dp))
                        Text("关于", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.SemiBold))
                    }
                    Text("AI自动写小说系统", style = MaterialTheme.typography.bodyMedium)
                    Text("桌面端 + 移动端一体化AI创作工具", style = MaterialTheme.typography.bodySmall.copy(color = Text4))
                    HorizontalDivider(color = Surface4, modifier = Modifier.padding(vertical = 4.dp))
                    Text("开源地址", style = MaterialTheme.typography.labelMedium.copy(color = Text4))
                    Text(
                        "https://github.com/ATboy-web/AI_NovelWriter",
                        style = MaterialTheme.typography.bodySmall.copy(color = Primary400)
                    )
                }
            }
        }
    }
}
