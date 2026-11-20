package com.ainovelwriter.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.ainovelwriter.model.AIConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

class SettingsRepository(private val context: Context) {

    private object Keys {
        val AI_ENDPOINT = stringPreferencesKey("ai_endpoint")
        val AI_API_KEY = stringPreferencesKey("ai_api_key")
        val AI_MODEL = stringPreferencesKey("ai_model")
        val AI_THINKING = booleanPreferencesKey("ai_thinking")
        val THEME = stringPreferencesKey("theme")
    }

    val aiConfig: Flow<AIConfig> = context.dataStore.data.map { prefs ->
        AIConfig(
            endpoint = prefs[Keys.AI_ENDPOINT] ?: AIConfig().endpoint,
            apiKey = prefs[Keys.AI_API_KEY] ?: "",
            model = prefs[Keys.AI_MODEL] ?: AIConfig().model,
            thinking = prefs[Keys.AI_THINKING] ?: true
        )
    }

    // v3.4：界面主题（与桌面 config.json 的 theme 键同语义；取值见 ThemeTokens.THEME_IDS）
    val themeId: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[Keys.THEME] ?: "cyberpunk"
    }

    suspend fun saveTheme(themeId: String) {
        context.dataStore.edit { prefs -> prefs[Keys.THEME] = themeId }
    }

    suspend fun saveAIConfig(config: AIConfig) {
        context.dataStore.edit { prefs ->
            prefs[Keys.AI_ENDPOINT] = config.endpoint
            prefs[Keys.AI_API_KEY] = config.apiKey
            prefs[Keys.AI_MODEL] = config.model
            prefs[Keys.AI_THINKING] = config.thinking
        }
    }
}
