package com.ainovelwriter.model

data class AIConfig(
    val endpoint: String = "https://api.deepseek.com",
    val apiKey: String = "",
    val model: String = "deepseek-v4-flash",
    val thinking: Boolean = true
)
