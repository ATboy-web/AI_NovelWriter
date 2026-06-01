/**
 * 书架 - 小说管理
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';

// 模拟数据
const MOCK_NOVELS = [
  {
    id: '1',
    title: '星际迷航：新的开始',
    genre: 'scifi',
    chapters: 12,
    words: 45000,
    lastEdit: '2小时前',
    cover: null,
  },
  {
    id: '2',
    title: '暗夜追踪者',
    genre: 'mystery',
    chapters: 8,
    words: 32000,
    lastEdit: '昨天',
    cover: null,
  },
  {
    id: '3',
    title: '时光倒流的爱情',
    genre: 'romance',
    chapters: 15,
    words: 58000,
    lastEdit: '3天前',
    cover: null,
  },
];

const GENRE_COLORS: Record<string, string> = {
  scifi: '#3b82f6',
  mystery: '#8b5cf6',
  romance: '#ec4899',
  fantasy: '#f59e0b',
  urban: '#10b981',
};

const GENRE_NAMES: Record<string, string> = {
  scifi: '科幻',
  mystery: '悬疑',
  romance: '言情',
  fantasy: '奇幻',
  urban: '都市',
};

export default function LibraryScreen({ navigation }: any) {
  const [novels, setNovels] = useState(MOCK_NOVELS);
  
  const renderNovelCard = ({ item }: { item: typeof MOCK_NOVELS[0] }) => (
    <TouchableOpacity
      style={styles.novelCard}
      onPress={() => navigation.navigate('NovelDetail', { novel: item })}
    >
      <View style={[styles.cover, { backgroundColor: GENRE_COLORS[item.genre] + '30' }]}>
        <Ionicons 
          name="book" 
          size={32} 
          color={GENRE_COLORS[item.genre]} 
        />
        <View style={[styles.genreBadge, { backgroundColor: GENRE_COLORS[item.genre] }]}>
          <Text style={styles.genreText}>{GENRE_NAMES[item.genre]}</Text>
        </View>
      </View>
      
      <View style={styles.novelInfo}>
        <Text style={styles.novelTitle} numberOfLines={2}>
          {item.title}
        </Text>
        
        <View style={styles.novelMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="document-text-outline" size={14} color={COLORS.textMuted} />
            <Text style={styles.metaText}>{item.chapters}章</Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="text-outline" size={14} color={COLORS.textMuted} />
            <Text style={styles.metaText}>{(item.words / 10000).toFixed(1)}万字</Text>
          </View>
        </View>
        
        <Text style={styles.lastEdit}>最后编辑: {item.lastEdit}</Text>
      </View>
    </TouchableOpacity>
  );
  
  return (
    <View style={styles.container}>
      {/* 头部统计 */}
      <View style={styles.statsHeader}>
        <View style={styles.statItem}>
          <Text style={styles.statNumber}>{novels.length}</Text>
          <Text style={styles.statLabel}>作品</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statNumber}>
            {novels.reduce((sum, n) => sum + n.chapters, 0)}
          </Text>
          <Text style={styles.statLabel}>章节</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={styles.statNumber}>
            {(novels.reduce((sum, n) => sum + n.words, 0) / 10000).toFixed(1)}
          </Text>
          <Text style={styles.statLabel}>万字</Text>
        </View>
      </View>
      
      {/* 小说列表 */}
      <FlatList
        data={novels}
        renderItem={renderNovelCard}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
      />
      
      {/* 新建按钮 */}
      <TouchableOpacity 
        style={styles.fab}
        onPress={() => navigation.navigate('写作')}
      >
        <Ionicons name="add" size={28} color="white" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  statsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: SPACING.xl,
    backgroundColor: COLORS.bgCard,
    marginBottom: SPACING.md,
  },
  statItem: {
    alignItems: 'center',
  },
  statNumber: {
    fontSize: SIZES.xxl,
    fontWeight: 'bold',
    color: COLORS.accent,
  },
  statLabel: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
    marginTop: 4,
  },
  listContent: {
    padding: SPACING.lg,
  },
  novelCard: {
    flexDirection: 'row',
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.lg,
    marginBottom: SPACING.md,
    overflow: 'hidden',
  },
  cover: {
    width: 100,
    height: 140,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  genreBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.sm,
  },
  genreText: {
    fontSize: SIZES.xs,
    color: 'white',
    fontWeight: 'bold',
  },
  novelInfo: {
    flex: 1,
    padding: SPACING.md,
    justifyContent: 'space-between',
  },
  novelTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: SPACING.sm,
  },
  novelMeta: {
    flexDirection: 'row',
    marginBottom: SPACING.sm,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: SPACING.md,
  },
  metaText: {
    fontSize: SIZES.sm,
    color: COLORS.textMuted,
    marginLeft: 4,
  },
  lastEdit: {
    fontSize: SIZES.xs,
    color: COLORS.textMuted,
  },
  fab: {
    position: 'absolute',
    right: SPACING.xl,
    bottom: SPACING.xl,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: COLORS.accent,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
});
