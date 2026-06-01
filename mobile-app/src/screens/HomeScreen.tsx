/**
 * 首页 - 快速开始创作
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ImageBackground,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';
import apiService from '../services/api';

export default function HomeScreen({ navigation }: any) {
  const novelTypes = apiService.getNovelTypes();
  
  return (
    <ScrollView style={styles.container}>
      {/* 欢迎区域 */}
      <View style={styles.welcomeSection}>
        <Text style={styles.welcomeTitle}>AI小说创作工坊</Text>
        <Text style={styles.welcomeSubtitle}>
          让AI助你创作精彩小说
        </Text>
      </View>
      
      {/* 快速开始 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>快速开始</Text>
        <TouchableOpacity 
          style={styles.quickStartCard}
          onPress={() => navigation.navigate('写作')}
        >
          <View style={styles.quickStartIcon}>
            <Ionicons name="create" size={32} color={COLORS.accent} />
          </View>
          <View style={styles.quickStartContent}>
            <Text style={styles.quickStartTitle}>开始创作</Text>
            <Text style={styles.quickStartDesc}>
              选择小说类型，开始你的创作之旅
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={24} color={COLORS.textMuted} />
        </TouchableOpacity>
      </View>
      
      {/* 小说类型 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>小说类型</Text>
        <View style={styles.typeGrid}>
          {novelTypes.map((type) => (
            <TouchableOpacity
              key={type.id}
              style={[styles.typeCard, { borderLeftColor: type.color }]}
              onPress={() => navigation.navigate('写作', { novelType: type.id })}
            >
              <Ionicons 
                name={type.icon as any} 
                size={28} 
                color={type.color} 
              />
              <Text style={styles.typeName}>{type.name}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      
      {/* AI功能 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>AI辅助功能</Text>
        <View style={styles.featureList}>
          {[
            { icon: 'flash', title: 'AI续写', desc: '根据已有内容继续创作' },
            { icon: 'expand', title: 'AI扩写', desc: '将简短内容扩展为详细描写' },
            { icon: 'contract', title: 'AI简写', desc: '精简压缩冗长内容' },
            { icon: 'color-wand', title: 'AI润色', desc: '优化语言表达' },
            { icon: 'swap-horizontal', title: 'AI改写', desc: '用不同方式重新表达' },
            { icon: 'chatbubbles', title: 'AI对话', desc: '生成角色对话' },
          ].map((feature, index) => (
            <TouchableOpacity key={index} style={styles.featureItem}>
              <View style={styles.featureIcon}>
                <Ionicons name={feature.icon as any} size={20} color={COLORS.accent} />
              </View>
              <View style={styles.featureContent}>
                <Text style={styles.featureTitle}>{feature.title}</Text>
                <Text style={styles.featureDesc}>{feature.desc}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      
      {/* 创作工具 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>创作工具</Text>
        <View style={styles.toolGrid}>
          {[
            { icon: 'library', title: '元素库', color: '#3b82f6' },
            { icon: 'people', title: '桥段库', color: '#8b5cf6' },
            { icon: 'brush', title: '描写库', color: '#ec4899' },
            { icon: 'chatbubbles', title: '对话推演', color: '#10b981' },
            { icon: 'git-branch', title: '故事流', color: '#f59e0b' },
            { icon: 'color-palette', title: '风格转换', color: '#ef4444' },
          ].map((tool, index) => (
            <TouchableOpacity 
              key={index} 
              style={styles.toolItem}
              onPress={() => navigation.navigate('工具', { tool: tool.title })}
            >
              <View style={[styles.toolIcon, { backgroundColor: tool.color + '20' }]}>
                <Ionicons name={tool.icon as any} size={24} color={tool.color} />
              </View>
              <Text style={styles.toolTitle}>{tool.title}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      
      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  welcomeSection: {
    padding: SPACING.xl,
    paddingTop: SPACING.lg,
  },
  welcomeTitle: {
    fontSize: SIZES.title,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: SPACING.sm,
  },
  welcomeSubtitle: {
    fontSize: SIZES.lg,
    color: COLORS.textSecondary,
  },
  section: {
    paddingHorizontal: SPACING.xl,
    marginBottom: SPACING.xl,
  },
  sectionTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: SPACING.md,
  },
  quickStartCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
  },
  quickStartIcon: {
    width: 56,
    height: 56,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.accent + '20',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  quickStartContent: {
    flex: 1,
  },
  quickStartTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: 4,
  },
  quickStartDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
  },
  typeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  typeCard: {
    width: '48%',
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderLeftWidth: 3,
    flexDirection: 'row',
    alignItems: 'center',
  },
  typeName: {
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    marginLeft: SPACING.sm,
    fontWeight: '500',
  },
  featureList: {
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.lg,
    overflow: 'hidden',
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: SPACING.md,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  featureIcon: {
    width: 40,
    height: 40,
    borderRadius: RADIUS.sm,
    backgroundColor: COLORS.accent + '20',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  featureContent: {
    flex: 1,
  },
  featureTitle: {
    fontSize: SIZES.md,
    fontWeight: '600',
    color: COLORS.textPrimary,
    marginBottom: 2,
  },
  featureDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
  },
  toolGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  toolItem: {
    width: '31%',
    alignItems: 'center',
    marginBottom: SPACING.lg,
  },
  toolIcon: {
    width: 56,
    height: 56,
    borderRadius: RADIUS.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: SPACING.sm,
  },
  toolTitle: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
    textAlign: 'center',
  },
});
