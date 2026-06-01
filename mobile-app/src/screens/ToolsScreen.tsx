/**
 * 工具页 - 创作工具集
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';

const TOOLS = [
  {
    id: 'elements',
    title: '小说元素库',
    desc: '预设大量小说元素，组合生成背景设定',
    icon: 'library',
    color: '#3b82f6',
    items: ['前端情节流', '世界布局', '势力结构', '人物设定', '修炼体系', '灭世场景'],
  },
  {
    id: 'bridges',
    title: '角色桥段库',
    desc: '经典网文桥段模板',
    icon: 'people',
    color: '#8b5cf6',
    items: ['角色对战', '角色登场', '情侣互动', '角色修炼', '情感场景'],
  },
  {
    id: 'descriptions',
    title: '事物描写库',
    desc: '管理和生成各类描写',
    icon: 'brush',
    color: '#ec4899',
    items: ['自然景观', '人物外貌', '情感描写', '动作描写', '天气描写'],
  },
  {
    id: 'dialogue',
    title: '情景对话推演',
    desc: '角色之间互动的对话场景',
    icon: 'chatbubbles',
    color: '#10b981',
    items: ['对话生成', '继续推演', '风格调整', '导出文本'],
  },
  {
    id: 'storyflow',
    title: '故事流推演',
    desc: '基于背景推演故事发展',
    icon: 'git-branch',
    color: '#f59e0b',
    items: ['正向推演', '反向推演', '分支推演', '冲突升级'],
  },
  {
    id: 'style',
    title: '风格转换',
    desc: '仿写、改写、风格调整',
    icon: 'color-palette',
    color: '#ef4444',
    items: ['风格转换', '作家模仿', '类型改编', '风格分析'],
  },
  {
    id: 'adapt',
    title: '智能改编',
    desc: '圈定截取改编，匹配率显示',
    icon: 'sync',
    color: '#06b6d4',
    items: ['片段改编', '批量改编', '随机改编', '替换原文'],
  },
];

export default function ToolsScreen({ navigation }: any) {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>创作工具集</Text>
        <Text style={styles.subtitle}>丰富的工具助你创作</Text>
      </View>
      
      {TOOLS.map((tool) => (
        <TouchableOpacity 
          key={tool.id} 
          style={styles.toolCard}
          onPress={() => navigation.navigate('ToolDetail', { toolId: tool.id })}
        >
          <View style={[styles.toolIcon, { backgroundColor: tool.color + '20' }]}>
            <Ionicons name={tool.icon as any} size={28} color={tool.color} />
          </View>
          
          <View style={styles.toolContent}>
            <Text style={styles.toolTitle}>{tool.title}</Text>
            <Text style={styles.toolDesc}>{tool.desc}</Text>
            
            <View style={styles.tagContainer}>
              {tool.items.slice(0, 3).map((item, index) => (
                <View key={index} style={[styles.tag, { backgroundColor: tool.color + '15' }]}>
                  <Text style={[styles.tagText, { color: tool.color }]}>{item}</Text>
                </View>
              ))}
              {tool.items.length > 3 && (
                <Text style={styles.moreTag}>+{tool.items.length - 3}</Text>
              )}
            </View>
          </View>
          
          <Ionicons name="chevron-forward" size={20} color={COLORS.textMuted} />
        </TouchableOpacity>
      ))}
      
      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  header: {
    padding: SPACING.xl,
    paddingBottom: SPACING.lg,
  },
  title: {
    fontSize: SIZES.xxl,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: SIZES.md,
    color: COLORS.textSecondary,
  },
  toolCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    marginHorizontal: SPACING.lg,
    marginBottom: SPACING.md,
    padding: SPACING.lg,
    borderRadius: RADIUS.lg,
  },
  toolIcon: {
    width: 56,
    height: 56,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  toolContent: {
    flex: 1,
  },
  toolTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: 4,
  },
  toolDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
    marginBottom: SPACING.sm,
  },
  tagContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  tag: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.sm,
    marginRight: 6,
    marginBottom: 4,
  },
  tagText: {
    fontSize: SIZES.xs,
    fontWeight: '500',
  },
  moreTag: {
    fontSize: SIZES.xs,
    color: COLORS.textMuted,
  },
});
