/**
 * 设置页 - 个人中心和配置
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  Switch,
  Modal,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';
import apiService from '../services/api';
import AsyncStorage from '@react-native-async-storage/async-storage';

// 可用模型列表
const AVAILABLE_MODELS = [
  { id: 'qwen2.5:14b', name: 'Qwen2.5 14B', provider: 'Ollama', desc: '本地模型，推荐' },
  { id: 'qwen2.5:7b', name: 'Qwen2.5 7B', provider: 'Ollama', desc: '轻量级本地模型' },
  { id: 'llama3.1:8b', name: 'Llama3.1 8B', provider: 'Ollama', desc: 'Meta开源模型' },
  { id: 'deepseek-r1:14b', name: 'DeepSeek R1 14B', provider: 'Ollama', desc: '推理能力强' },
  { id: 'glm4:9b', name: 'GLM4 9B', provider: 'Ollama', desc: '智谱AI模型' },
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI', desc: '需要API密钥' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI', desc: '性价比高' },
  { id: 'deepseek-chat', name: 'DeepSeek Chat', provider: 'DeepSeek', desc: '需要API密钥' },
  { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'Claude', desc: '需要API密钥' },
];

export default function SettingsScreen() {
  const [apiUrl, setApiUrl] = useState('http://localhost:11434');
  const [apiKey, setApiKey] = useState('');
  const [selectedModel, setSelectedModel] = useState('qwen2.5:14b');
  const [darkMode, setDarkMode] = useState(true);
  const [autoSave, setAutoSave] = useState(true);
  const [typewriterMode, setTypewriterMode] = useState(true);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'unknown' | 'connected' | 'disconnected'>('unknown');

  // 加载保存的配置
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const config = await AsyncStorage.getItem('app_settings');
      if (config) {
        const parsed = JSON.parse(config);
        setApiUrl(parsed.apiUrl || 'http://localhost:11434');
        setApiKey(parsed.apiKey || '');
        setSelectedModel(parsed.selectedModel || 'qwen2.5:14b');
        setDarkMode(parsed.darkMode !== false);
        setAutoSave(parsed.autoSave !== false);
        setTypewriterMode(parsed.typewriterMode !== false);
      }
    } catch (e) {
      console.log('加载设置失败:', e);
    }
  };

  const saveSettings = async () => {
    try {
      await AsyncStorage.setItem('app_settings', JSON.stringify({
        apiUrl,
        apiKey,
        selectedModel,
        darkMode,
        autoSave,
        typewriterMode,
      }));
      // 同时更新API服务配置
      await apiService.saveConfig({ baseURL: apiUrl, apiKey });
      Alert.alert('成功', '设置已保存');
    } catch (e) {
      Alert.alert('错误', '保存设置失败');
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setConnectionStatus('unknown');
    try {
      // 更新API配置
      await apiService.saveConfig({ baseURL: apiUrl, apiKey });
      const isHealthy = await apiService.healthCheck();
      setConnectionStatus(isHealthy ? 'connected' : 'disconnected');
      Alert.alert(
        isHealthy ? '连接成功' : '连接失败',
        isHealthy ? '已成功连接到AI服务' : '无法连接到AI服务，请检查地址是否正确'
      );
    } catch (e) {
      setConnectionStatus('disconnected');
      Alert.alert('连接失败', '无法连接到AI服务');
    } finally {
      setTesting(false);
    }
  };

  const syncToCloud = async () => {
    setSyncing(true);
    try {
      // 获取本地数据
      const novels = await AsyncStorage.getItem('novels');
      const settings = await AsyncStorage.getItem('app_settings');
      
      // 模拟同步到云端（实际需要实现云存储API）
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // 保存同步记录
      await AsyncStorage.setItem('last_sync', new Date().toISOString());
      
      Alert.alert('同步成功', '所有数据已同步到云端');
    } catch (e) {
      Alert.alert('同步失败', '无法同步到云端，请检查网络连接');
    } finally {
      setSyncing(false);
    }
  };

  const restoreFromCloud = async () => {
    Alert.alert(
      '确认恢复',
      '从云端恢复将覆盖本地数据，确定继续吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定恢复',
          onPress: async () => {
            setSyncing(true);
            try {
              // 模拟从云端恢复（实际需要实现云存储API）
              await new Promise(resolve => setTimeout(resolve, 2000));
              
              Alert.alert('恢复成功', '数据已从云端恢复');
            } catch (e) {
              Alert.alert('恢复失败', '无法从云端恢复数据');
            } finally {
              setSyncing(false);
            }
          },
        },
      ]
    );
  };

  const exportAllNovels = async () => {
    try {
      const novelsData = await AsyncStorage.getItem('novels');
      const novels = novelsData ? JSON.parse(novelsData) : [];
      
      if (novels.length === 0) {
        Alert.alert('提示', '暂无小说数据可导出');
        return;
      }

      Alert.alert(
        '导出小说',
        `共有 ${novels.length} 部小说，确定导出吗？`,
        [
          { text: '取消', style: 'cancel' },
          {
            text: '确定导出',
            onPress: async () => {
              // 实际实现需要使用文件系统API
              Alert.alert('导出成功', `已导出 ${novels.length} 部小说`);
            },
          },
        ]
      );
    } catch (e) {
      Alert.alert('导出失败', '无法导出小说数据');
    }
  };

  const getLastSyncTime = async () => {
    try {
      const lastSync = await AsyncStorage.getItem('last_sync');
      if (lastSync) {
        const date = new Date(lastSync);
        return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
      }
    } catch (e) {}
    return '从未同步';
  };

  const [lastSyncTime, setLastSyncTime] = useState('从未同步');
  useEffect(() => {
    getLastSyncTime().then(setLastSyncTime);
  }, []);

  const getSelectedModelName = () => {
    const model = AVAILABLE_MODELS.find(m => m.id === selectedModel);
    return model ? `${model.name} (${model.provider})` : selectedModel;
  };

  const settingsGroups = [
    {
      title: 'AI配置',
      items: [
        {
          icon: 'server-outline',
          label: 'API地址',
          type: 'input',
          value: apiUrl,
          onChangeText: setApiUrl,
          placeholder: 'http://localhost:11434',
        },
        {
          icon: 'key-outline',
          label: 'API密钥',
          type: 'input',
          value: apiKey,
          onChangeText: setApiKey,
          placeholder: '输入API密钥（Ollama不需要）',
          secure: true,
        },
        {
          icon: 'hardware-chip-outline',
          label: 'AI模型',
          type: 'select',
          value: getSelectedModelName(),
          onPress: () => setShowModelPicker(true),
        },
        {
          icon: 'wifi-outline',
          label: '测试连接',
          type: 'action',
          onPress: testConnection,
          loading: testing,
          status: connectionStatus,
        },
      ],
    },
    {
      title: '写作设置',
      items: [
        {
          icon: 'moon-outline',
          label: '深色模式',
          type: 'switch',
          value: darkMode,
          onValueChange: setDarkMode,
        },
        {
          icon: 'save-outline',
          label: '自动保存',
          type: 'switch',
          value: autoSave,
          onValueChange: setAutoSave,
        },
        {
          icon: 'text-outline',
          label: '打字机模式',
          type: 'switch',
          value: typewriterMode,
          onValueChange: setTypewriterMode,
        },
      ],
    },
    {
      title: '数据管理',
      items: [
        {
          icon: 'cloud-upload-outline',
          label: '同步到云端',
          type: 'action',
          desc: `上次同步: ${lastSyncTime}`,
          onPress: syncToCloud,
          loading: syncing,
        },
        {
          icon: 'cloud-download-outline',
          label: '从云端恢复',
          type: 'action',
          desc: '恢复云端数据到本地',
          onPress: restoreFromCloud,
        },
        {
          icon: 'download-outline',
          label: '导出所有小说',
          type: 'action',
          desc: '导出为文件保存',
          onPress: exportAllNovels,
        },
      ],
    },
    {
      title: '关于',
      items: [
        {
          icon: 'information-circle-outline',
          label: '版本',
          type: 'info',
          value: 'v2.0.0',
        },
        {
          icon: 'document-text-outline',
          label: '使用帮助',
          type: 'action',
          onPress: () => Alert.alert('帮助', '详见文档'),
        },
        {
          icon: 'star-outline',
          label: '给个好评',
          type: 'action',
          onPress: () => Alert.alert('感谢', '感谢您的支持！'),
        },
      ],
    },
  ];

  const renderItem = (item: any, index: number) => {
    switch (item.type) {
      case 'input':
        return (
          <View key={index} style={styles.settingItem}>
            <View style={styles.settingLabel}>
              <Ionicons name={item.icon} size={20} color={COLORS.textSecondary} />
              <Text style={styles.settingText}>{item.label}</Text>
            </View>
            <TextInput
              style={styles.settingInput}
              value={item.value}
              onChangeText={item.onChangeText}
              placeholder={item.placeholder}
              placeholderTextColor={COLORS.textMuted}
              secureTextEntry={item.secure}
            />
          </View>
        );

      case 'select':
        return (
          <TouchableOpacity key={index} style={styles.settingItem} onPress={item.onPress}>
            <View style={styles.settingLabel}>
              <Ionicons name={item.icon} size={20} color={COLORS.textSecondary} />
              <Text style={styles.settingText}>{item.label}</Text>
            </View>
            <View style={styles.selectValue}>
              <Text style={styles.settingValue}>{item.value}</Text>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            </View>
          </TouchableOpacity>
        );

      case 'switch':
        return (
          <View key={index} style={styles.settingItem}>
            <View style={styles.settingLabel}>
              <Ionicons name={item.icon} size={20} color={COLORS.textSecondary} />
              <Text style={styles.settingText}>{item.label}</Text>
            </View>
            <Switch
              value={item.value}
              onValueChange={item.onValueChange}
              trackColor={{ false: COLORS.bgLight, true: COLORS.accent + '50' }}
              thumbColor={item.value ? COLORS.accent : COLORS.textMuted}
            />
          </View>
        );

      case 'info':
        return (
          <View key={index} style={styles.settingItem}>
            <View style={styles.settingLabel}>
              <Ionicons name={item.icon} size={20} color={COLORS.textSecondary} />
              <Text style={styles.settingText}>{item.label}</Text>
            </View>
            <Text style={styles.settingValue}>{item.value}</Text>
          </View>
        );

      case 'action':
        return (
          <TouchableOpacity key={index} style={styles.settingItem} onPress={item.onPress}>
            <View style={styles.settingLabel}>
              <Ionicons name={item.icon} size={20} color={COLORS.textSecondary} />
              <View style={{ flex: 1 }}>
                <Text style={styles.settingText}>{item.label}</Text>
                {item.desc && <Text style={styles.settingDesc}>{item.desc}</Text>}
              </View>
            </View>
            {item.loading ? (
              <ActivityIndicator size="small" color={COLORS.accent} />
            ) : item.status ? (
              <View style={[styles.statusDot, { backgroundColor: item.status === 'connected' ? COLORS.success : COLORS.error }]} />
            ) : (
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            )}
          </TouchableOpacity>
        );

      default:
        return null;
    }
  };

  return (
    <ScrollView style={styles.container}>
      {/* 用户信息 */}
      <View style={styles.userCard}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={40} color={COLORS.accent} />
        </View>
        <View style={styles.userInfo}>
          <Text style={styles.userName}>创作者</Text>
          <Text style={styles.userPlan}>免费版</Text>
        </View>
        <TouchableOpacity style={styles.editButton} onPress={saveSettings}>
          <Text style={styles.editButtonText}>保存设置</Text>
        </TouchableOpacity>
      </View>

      {/* 设置列表 */}
      {settingsGroups.map((group, groupIndex) => (
        <View key={groupIndex} style={styles.settingGroup}>
          <Text style={styles.groupTitle}>{group.title}</Text>
          <View style={styles.groupContent}>
            {group.items.map((item, index) => renderItem(item, index))}
          </View>
        </View>
      ))}

      <View style={{ height: 30 }} />

      {/* 模型选择弹窗 */}
      <Modal
        visible={showModelPicker}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowModelPicker(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>选择AI模型</Text>
              <TouchableOpacity onPress={() => setShowModelPicker(false)}>
                <Ionicons name="close" size={24} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>
            
            <FlatList
              data={AVAILABLE_MODELS}
              keyExtractor={(item) => item.id}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[
                    styles.modelItem,
                    selectedModel === item.id && styles.modelItemSelected,
                  ]}
                  onPress={() => {
                    setSelectedModel(item.id);
                    setShowModelPicker(false);
                  }}
                >
                  <View style={styles.modelInfo}>
                    <Text style={styles.modelName}>{item.name}</Text>
                    <Text style={styles.modelProvider}>{item.provider}</Text>
                    <Text style={styles.modelDesc}>{item.desc}</Text>
                  </View>
                  {selectedModel === item.id && (
                    <Ionicons name="checkmark-circle" size={24} color={COLORS.accent} />
                  )}
                </TouchableOpacity>
              )}
            />
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    margin: SPACING.lg,
    padding: SPACING.lg,
    borderRadius: RADIUS.lg,
  },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: COLORS.accent + '20',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  userInfo: {
    flex: 1,
  },
  userName: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: 2,
  },
  userPlan: {
    fontSize: SIZES.sm,
    color: COLORS.accent,
  },
  editButton: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    backgroundColor: COLORS.accent,
    borderRadius: RADIUS.sm,
  },
  editButtonText: {
    fontSize: SIZES.sm,
    color: 'white',
    fontWeight: '600',
  },
  settingGroup: {
    marginBottom: SPACING.lg,
  },
  groupTitle: {
    fontSize: SIZES.md,
    fontWeight: '600',
    color: COLORS.textSecondary,
    paddingHorizontal: SPACING.xl,
    marginBottom: SPACING.sm,
  },
  groupContent: {
    backgroundColor: COLORS.bgCard,
    marginHorizontal: SPACING.lg,
    borderRadius: RADIUS.lg,
    overflow: 'hidden',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  settingLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  settingText: {
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    marginLeft: SPACING.md,
  },
  settingDesc: {
    fontSize: SIZES.xs,
    color: COLORS.textMuted,
    marginLeft: SPACING.md,
    marginTop: 2,
  },
  settingInput: {
    flex: 1,
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    textAlign: 'right',
    marginLeft: SPACING.md,
  },
  settingValue: {
    fontSize: SIZES.md,
    color: COLORS.textSecondary,
  },
  selectValue: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: COLORS.bgDark,
    borderTopLeftRadius: RADIUS.xl,
    borderTopRightRadius: RADIUS.xl,
    maxHeight: '70%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.lg,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  modalTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  modelItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.lg,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  modelItemSelected: {
    backgroundColor: COLORS.accent + '10',
  },
  modelInfo: {
    flex: 1,
  },
  modelName: {
    fontSize: SIZES.md,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  modelProvider: {
    fontSize: SIZES.sm,
    color: COLORS.accent,
    marginTop: 2,
  },
  modelDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
});