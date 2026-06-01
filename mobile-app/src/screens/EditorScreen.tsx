/**
 * 写作编辑器 - 核心创作页面
 */

import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';
import apiService from '../services/api';

export default function EditorScreen({ route }: any) {
  const [content, setContent] = useState('');
  const [title, setTitle] = useState('未命名章节');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedText, setSelectedText] = useState('');
  const textRef = useRef<TextInput>(null);
  
  // AI功能
  const aiFeatures = [
    { id: 'continue', icon: 'arrow-forward', label: '续写', color: COLORS.accent },
    { id: 'expand', icon: 'expand', label: '扩写', color: '#3b82f6' },
    { id: 'compress', icon: 'contract', label: '简写', color: '#f59e0b' },
    { id: 'polish', icon: 'color-wand', label: '润色', color: '#10b981' },
    { id: 'rewrite', icon: 'swap-horizontal', label: '改写', color: '#ef4444' },
    { id: 'dialogue', icon: 'chatbubbles', label: '对话', color: '#8b5cf6' },
  ];
  
  // Markdown工具
  const mdTools = [
    { id: 'h1', label: 'H1', prefix: '# ' },
    { id: 'h2', label: 'H2', prefix: '## ' },
    { id: 'h3', label: 'H3', prefix: '### ' },
    { id: 'bold', label: 'B', prefix: '**', suffix: '**' },
    { id: 'italic', label: 'I', prefix: '*', suffix: '*' },
    { id: 'quote', label: '>', prefix: '> ' },
    { id: 'list', label: '•', prefix: '- ' },
    { id: 'hr', label: '—', prefix: '\n---\n' },
  ];
  
  // 执行AI功能
  const handleAiFeature = async (featureId: string) => {
    if (!content.trim()) {
      Alert.alert('提示', '请先输入一些内容');
      return;
    }
    
    setIsLoading(true);
    
    try {
      let result = '';
      
      switch (featureId) {
        case 'continue':
          result = await apiService.aiContinue(content);
          break;
        case 'expand':
          result = await apiService.aiExpand(selectedText || content);
          break;
        case 'compress':
          result = await apiService.aiCompress(selectedText || content);
          break;
        case 'polish':
          result = await apiService.aiPolish(selectedText || content);
          break;
        case 'rewrite':
          result = await apiService.aiPolish(selectedText || content); // 复用润色
          break;
        case 'dialogue':
          result = await apiService.aiContinue(content, '生成角色对话');
          break;
      }
      
      if (result) {
        if (featureId === 'continue') {
          setContent(prev => prev + '\n\n' + result);
        } else {
          // 替换选中内容或追加
          if (selectedText) {
            setContent(prev => prev.replace(selectedText, result));
          } else {
            setContent(prev => prev + '\n\n' + result);
          }
        }
      }
    } catch (error) {
      Alert.alert('错误', 'AI处理失败，请检查网络连接');
    } finally {
      setIsLoading(false);
    }
  };
  
  // 插入Markdown
  const insertMarkdown = (prefix: string, suffix?: string) => {
    const selection = textRef.current?.props?.selection;
    if (selection) {
      const before = content.substring(0, selection.start);
      const selected = content.substring(selection.start, selection.end);
      const after = content.substring(selection.end);
      
      setContent(before + prefix + selected + (suffix || '') + after);
    } else {
      setContent(prev => prev + prefix + (suffix || ''));
    }
  };
  
  // 字数统计
  const wordCount = content.length;
  const lineCount = content.split('\n').length;
  
  return (
    <KeyboardAvoidingView 
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* 标题栏 */}
      <View style={styles.header}>
        <TextInput
          style={styles.titleInput}
          value={title}
          onChangeText={setTitle}
          placeholder="章节标题"
          placeholderTextColor={COLORS.textMuted}
        />
        <View style={styles.stats}>
          <Text style={styles.statsText}>{wordCount}字</Text>
          <Text style={styles.statsText}>{lineCount}行</Text>
        </View>
      </View>
      
      {/* AI工具栏 */}
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        style={styles.aiToolbar}
      >
        {aiFeatures.map((feature) => (
          <TouchableOpacity
            key={feature.id}
            style={[styles.aiButton, { backgroundColor: feature.color + '20' }]}
            onPress={() => handleAiFeature(feature.id)}
            disabled={isLoading}
          >
            <Ionicons name={feature.icon as any} size={16} color={feature.color} />
            <Text style={[styles.aiButtonText, { color: feature.color }]}>
              {feature.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      
      {/* Markdown工具栏 */}
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        style={styles.mdToolbar}
      >
        {mdTools.map((tool) => (
          <TouchableOpacity
            key={tool.id}
            style={styles.mdButton}
            onPress={() => insertMarkdown(tool.prefix, tool.suffix)}
          >
            <Text style={styles.mdButtonText}>{tool.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      
      {/* 编辑区域 */}
      <View style={styles.editorContainer}>
        {isLoading && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="large" color={COLORS.accent} />
            <Text style={styles.loadingText}>AI处理中...</Text>
          </View>
        )}
        
        <TextInput
          ref={textRef}
          style={styles.editor}
          value={content}
          onChangeText={setContent}
          placeholder="开始你的创作..."
          placeholderTextColor={COLORS.textMuted}
          multiline
          textAlignVertical="top"
          selectionColor={COLORS.accent}
          onSelectionChange={(e) => {
            const { start, end } = e.nativeEvent.selection;
            if (start !== end) {
              setSelectedText(content.substring(start, end));
            } else {
              setSelectedText('');
            }
          }}
        />
      </View>
      
      {/* 底部工具栏 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity style={styles.bottomButton}>
          <Ionicons name="save-outline" size={20} color={COLORS.textSecondary} />
          <Text style={styles.bottomButtonText}>保存</Text>
        </TouchableOpacity>
        
        <TouchableOpacity style={styles.bottomButton}>
          <Ionicons name="eye-outline" size={20} color={COLORS.textSecondary} />
          <Text style={styles.bottomButtonText}>预览</Text>
        </TouchableOpacity>
        
        <TouchableOpacity style={styles.bottomButton}>
          <Ionicons name="share-outline" size={20} color={COLORS.textSecondary} />
          <Text style={styles.bottomButtonText}>导出</Text>
        </TouchableOpacity>
        
        <TouchableOpacity style={styles.bottomButton}>
          <Ionicons name="settings-outline" size={20} color={COLORS.textSecondary} />
          <Text style={styles.bottomButtonText}>设置</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  titleInput: {
    flex: 1,
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  stats: {
    flexDirection: 'row',
    marginLeft: SPACING.md,
  },
  statsText: {
    fontSize: SIZES.sm,
    color: COLORS.textMuted,
    marginLeft: SPACING.sm,
  },
  aiToolbar: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    maxHeight: 50,
  },
  aiButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: RADIUS.sm,
    marginRight: SPACING.sm,
  },
  aiButtonText: {
    fontSize: SIZES.sm,
    fontWeight: '500',
    marginLeft: 4,
  },
  mdToolbar: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    maxHeight: 40,
    backgroundColor: COLORS.bgMedium,
  },
  mdButton: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: RADIUS.sm,
    marginRight: SPACING.xs,
    backgroundColor: COLORS.bgLight,
  },
  mdButtonText: {
    fontSize: SIZES.sm,
    fontWeight: 'bold',
    color: COLORS.textSecondary,
  },
  editorContainer: {
    flex: 1,
    position: 'relative',
  },
  editor: {
    flex: 1,
    fontSize: SIZES.lg,
    color: COLORS.textPrimary,
    paddingHorizontal: SPACING.xl,
    paddingVertical: SPACING.lg,
    lineHeight: 28,
  },
  loadingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.7)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  loadingText: {
    color: COLORS.textPrimary,
    marginTop: SPACING.md,
    fontSize: SIZES.md,
  },
  bottomBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: SPACING.md,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    backgroundColor: COLORS.bgMedium,
  },
  bottomButton: {
    alignItems: 'center',
  },
  bottomButtonText: {
    fontSize: SIZES.xs,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
});
