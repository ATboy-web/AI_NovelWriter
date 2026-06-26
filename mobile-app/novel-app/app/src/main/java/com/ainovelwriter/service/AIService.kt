package com.ainovelwriter.service

import com.ainovelwriter.model.AIConfig
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

data class TokenStats(
    var totalTokens: Long = 0,
    var promptTokens: Long = 0,
    var completionTokens: Long = 0,
    var requestCount: Int = 0
) {
    fun record(prompt: Int, completion: Int) {
        promptTokens += prompt
        completionTokens += completion
        totalTokens += prompt + completion
        requestCount++
    }
    fun display(): String = when {
        totalTokens >= 1_000_000 -> "%.1fM tokens (%d次)".format(totalTokens / 1_000_000.0, requestCount)
        totalTokens >= 1_000 -> "%.1fK tokens (%d次)".format(totalTokens / 1_000.0, requestCount)
        else -> "$totalTokens tokens (${requestCount}次)"
    }
}

object AIService {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val gson = Gson()
    val tokenStats = TokenStats()
    
    // Auto-detect provider from model name
    fun detectProvider(model: String): String {
        val m = model.lowercase()
        return when {
            m.startsWith("glm") -> "glm"
            m.contains("qwen") || m.contains("qwq") -> "qwen"
            m.contains("kimi") -> "kimi"
            m.contains("deepseek") -> "deepseek"
            m.contains("claude") || m.contains("anthropic") -> "claude"
            else -> "openai"
        }
    }
    
    // Main chat function
    suspend fun chat(config: AIConfig, messages: List<Map<String, String>>, system: String = "", maxTokens: Int = 4096, temperature: Double = 0.8): Result<String> = withContext(Dispatchers.IO) {
        try {
            val provider = detectProvider(config.model)
            val isClaude = provider == "claude"
            
            val fullMessages = if (system.isNotEmpty()) {
                listOf(mapOf("role" to "system", "content" to system)) + messages
            } else messages
            
            // Build payload
            val payload = buildPayload(config.model, provider, fullMessages, maxTokens, temperature, config.thinking)
            
            // Build URL
            val url = config.endpoint.trimEnd('/') + if (isClaude) "/v1/messages" else "/v1/chat/completions"
            
            // Build request
            val body = gson.toJson(payload).toRequestBody("application/json".toMediaType())
            val reqBuilder = Request.Builder().url(url).post(body)
            
            if (config.apiKey.isNotEmpty()) {
                if (isClaude) {
                    reqBuilder.header("x-api-key", config.apiKey)
                    reqBuilder.header("anthropic-version", "2023-06-01")
                } else {
                    reqBuilder.header("Authorization", "Bearer ${config.apiKey}")
                }
            }
            
            val response = client.newCall(reqBuilder.build()).execute()
            val responseBody = response.body?.string() ?: ""
            
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("HTTP ${response.code}: ${responseBody.take(200)}"))
            }
            
            val result = parseResponse(responseBody, provider)
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    private fun buildPayload(model: String, provider: String, messages: List<Map<String, String>>, maxTokens: Int, temperature: Double, thinking: Boolean): Map<String, Any?> {
        val payload = mutableMapOf<String, Any?>(
            "model" to model,
            "messages" to messages,
            "max_tokens" to maxTokens,
            "temperature" to temperature
        )
        
        if (thinking && maxTokens >= 1000) {
            when (provider) {
                "deepseek" -> {
                    payload["thinking"] = mapOf("type" to "enabled")
                    payload["reasoning_effort"] = "high"
                    payload.remove("temperature")
                }
                "glm" -> {
                    payload["thinking"] = mapOf("type" to "enabled")
                    if (model.contains("5.2") || model.contains("5.1")) {
                        payload["reasoning_effort"] = "max"
                    }
                    payload["temperature"] = 1.0
                }
                "qwen" -> {
                    payload["enable_thinking"] = true
                    payload["thinking_budget"] = maxTokens / 2
                }
                "kimi" -> {
                    if (!model.contains("k2.7")) {
                        payload["thinking"] = mapOf("type" to "enabled", "keep" to "all")
                    }
                }
            }
        }
        
        return payload
    }
    
    private fun parseResponse(responseBody: String, provider: String): String {
        if (provider == "claude") {
            val json = JsonParser.parseString(responseBody).asJsonObject
            val content = json.getAsJsonArray("content")?.get(0)?.asJsonObject?.get("text")?.asString ?: ""
            json.getAsJsonObject("usage")?.let { usage ->
                tokenStats.record(
                    usage.get("input_tokens")?.asInt ?: 0,
                    usage.get("output_tokens")?.asInt ?: 0
                )
            }
            return content
        }
        
        val json = JsonParser.parseString(responseBody).asJsonObject
        val choices = json.getAsJsonArray("choices")
        if (choices == null || choices.size() == 0) {
            throw Exception("No choices in response: ${responseBody.take(200)}")
        }
        
        val message = choices[0].asJsonObject.getAsJsonObject("message")
        val content = message?.get("content")?.asString ?: ""
        val reasoning = message?.get("reasoning_content")?.asString ?: ""
        val finishReason = choices[0].asJsonObject.get("finish_reason")?.asString ?: ""
        
        // Record token stats
        json.getAsJsonObject("usage")?.let { usage ->
            tokenStats.record(
                usage.get("prompt_tokens")?.asInt ?: 0,
                usage.get("completion_tokens")?.asInt ?: 0
            )
        }
        
        // Fallback: if content empty but reasoning has content and finish_reason is "length"
        if (content.isEmpty() && reasoning.isNotEmpty() && reasoning.length > 10 && finishReason == "length") {
            return reasoning
        }
        
        return content.ifEmpty { reasoning }
    }
    
    // Test connection
    suspend fun testConnection(config: AIConfig): Boolean {
        return try {
            val result = chat(config, listOf(mapOf("role" to "user", "content" to "你好")), maxTokens = 50)
            result.isSuccess && (result.getOrNull()?.isNotEmpty() == true)
        } catch (e: Exception) {
            false
        }
    }
}