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
    }

    val aiConfig: Flow<AIConfig> = context.dataStore.data.map { prefs ->
        AIConfig(
            endpoint = prefs[Keys.AI_ENDPOINT] ?: AIConfig().endpoint,
            apiKey = prefs[Keys.AI_API_KEY] ?: "",
            model = prefs[Keys.AI_MODEL] ?: AIConfig().model,
            thinking = prefs[Keys.AI_THINKING] ?: true
        )
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
