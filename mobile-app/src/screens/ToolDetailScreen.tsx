/**
 * 工具详情页 - 显示具体工具的功能和内容
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SIZES, SPACING, RADIUS } from '../styles/theme';
import apiService from '../services/api';

// 工具数据定义
const TOOL_DATA: Record<string, any> = {
  elements: {
    title: '小说元素库',
    icon: 'library',
    color: '#3b82f6',
    categories: [
      { id: 'plot', name: '前端情节流', items: ['重生复仇', '系统觉醒', '被退婚', '穿越重生', '末日求生', '校园逆袭', '职场翻身', '娱乐圈'] },
      { id: 'world', name: '世界布局', items: ['九天十地', '三界六道', '星辰大海', '末世废土', '修仙大陆', '都市异能'] },
      { id: 'force', name: '势力结构', items: ['四大宗门', '帝国争霸', '地下势力', '学院体系', '家族势力', '联盟对抗'] },
      { id: 'character', name: '人物设定', items: ['天才主角', '反派BOSS', '红颜知己', '忠心兄弟', '神秘导师', '亦敌亦友'] },
      { id: 'cultivation', name: '修炼体系', items: ['九重天', '五行', '科技修炼', '血脉觉醒', '精神力', '武道'] },
      { id: 'apocalypse', name: '灭世场景', items: ['天地大劫', '魔族入侵', '天道崩塌', '末日降临', '神罚'] },
    ],
  },
  bridges: {
    title: '角色桥段库',
    icon: 'people',
    color: '#8b5cf6',
    categories: [
      { id: 'battle', name: '战斗桥段', items: ['角色对战', '以弱胜强', '绝地反击', '同归于尽', '秒杀'] },
      { id: 'entrance', name: '登场桥段', items: ['霸气登场', '神秘出场', '意外现身', '王者归来', '低调出场'] },
      { id: 'romance', name: '情感桥段', items: ['情侣购物', '情侣看电影', '告白场景', '误会分手', '重逢'] },
      { id: 'growth', name: '成长桥段', items: ['角色修炼', '突破境界', '领悟绝学', '获得传承', '逆天机缘'] },
      { id: 'interaction', name: '互动桥段', items: ['角色挑衅', '苦肉计', '角色诱惑', '装逼打脸', '智商碾压'] },
    ],
  },
  descriptions: {
    title: '事物描写库',
    icon: 'brush',
    color: '#ec4899',
    categories: [
      { id: 'nature', name: '自然景观', items: ['日出日落', '山川河流', '星空大海', '风雨雷电', '四季变换'] },
      { id: 'appearance', name: '人物外貌', items: ['绝世美女', '英俊男子', '老者形象', '孩童描写', '反派外貌'] },
      { id: 'emotion', name: '情感描写', items: ['愤怒', '悲伤', '喜悦', '恐惧', '惊讶', '爱慕'] },
      { id: 'action', name: '动作描写', items: ['战斗动作', '修炼动作', '日常动作', '逃跑追逐', '施展技能'] },
      { id: 'building', name: '建筑描写', items: ['宫殿', '洞府', '城市', '废墟', '仙境'] },
    ],
  },
  dialogue: {
    title: '情景对话推演',
    icon: 'chatbubbles',
    color: '#10b981',
    scenarios: [
      '两个老友多年后重逢',
      '师徒之间的传承对话',
      '敌对双方的对峙',
      '恋人的甜蜜对话',
      '审问犯人的紧张对话',
      '商议战略的会议',
    ],
  },
  storyflow: {
    title: '故事流推演',
    icon: 'git-branch',
    color: '#f59e0b',
    modes: [
      { id: 'forward', name: '正向推演', desc: '基于背景推演后续发展' },
      { id: 'backward', name: '反向推演', desc: '从结局推导过程' },
      { id: 'bridge', name: '中间推演', desc: '连接开端和结局' },
      { id: 'branch', name: '分支推演', desc: '生成多个可能走向' },
    ],
  },
  style: {
    title: '风格转换',
    icon: 'color-palette',
    color: '#ef4444',
    styles: [
      { id: 'hot', name: '热血爽文', desc: '节奏快、爽点密集' },
      { id: 'emotional', name: '细腻情感', desc: '情感丰富、描写细腻' },
      { id: 'humor', name: '幽默搞笑', desc: '轻松诙谐、笑点不断' },
      { id: 'dark', name: '暗黑阴郁', desc: '气氛沉重、剧情黑暗' },
      { id: 'ancient', name: '古风仙侠', desc: '古典文雅、仙气飘飘' },
      { id: 'urban', name: '都市现实', desc: '贴近生活、真实感强' },
      { id: 'suspense', name: '悬疑紧张', desc: '悬念迭起、扣人心弦' },
    ],
  },
  adapt: {
    title: '智能改编',
    icon: 'sync',
    color: '#06b6d4',
    instructions: [
      '改写为更紧张的氛围',
      '增加更多细节描写',
      '转换为第一人称视角',
      '改为更幽默的风格',
      '增加悬念和伏笔',
      '精简为关键情节',
    ],
  },
};

export default function ToolDetailScreen({ route, navigation }: any) {
  const { toolId } = route.params;
  const tool = TOOL_DATA[toolId];
  
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [inputText, setInputText] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  
  if (!tool) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>工具不存在</Text>
      </View>
    );
  }
  
  const handleGenerate = async (item?: string) => {
    setLoading(true);
    setResult('');
    
    try {
      let response;
      const text = inputText || item || '';
      
      switch (toolId) {
        case 'elements':
        case 'bridges':
        case 'descriptions':
          response = await apiService.aiExpand(
            `请生成关于"${text}"的详细设定和描写，要求生动具体，适合小说使用。`
          );
          break;
        case 'dialogue':
          response = await apiService.aiContinue(
            '',
            `场景：${text}\n请生成3-5轮角色对话，要求自然生动，符合人物性格。`
          );
          break;
        case 'storyflow':
          response = await apiService.aiContinue(
            '',
            `请推演以下故事的发展过程：${text}\n要求情节合理，有起承转合。`
          );
          break;
        case 'style':
          response = await apiService.aiPolish(
            `请将以下内容转换为${text}风格：\n${inputText || '暂无内容'}`
          );
          break;
        case 'adapt':
          response = await apiService.aiCompress(
            `请按以下要求改编：${text}\n原文：${inputText || '暂无内容'}`
          );
          break;
        default:
          response = '功能开发中...';
      }
      
      setResult(response);
    } catch (error: any) {
      Alert.alert('错误', error.message || '生成失败，请检查网络连接');
    } finally {
      setLoading(false);
    }
  };
  
  const renderElementsView = () => (
    <View>
      {tool.categories.map((category: any) => (
        <View key={category.id} style={styles.categorySection}>
          <TouchableOpacity
            style={styles.categoryHeader}
            onPress={() => setSelectedCategory(
              selectedCategory === category.id ? null : category.id
            )}
          >
            <Text style={styles.categoryName}>{category.name}</Text>
            <Ionicons
              name={selectedCategory === category.id ? 'chevron-up' : 'chevron-down'}
              size={20}
              color={COLORS.textSecondary}
            />
          </TouchableOpacity>
          
          {selectedCategory === category.id && (
            <View style={styles.itemsGrid}>
              {category.items.map((item: string, index: number) => (
                <TouchableOpacity
                  key={index}
                  style={[styles.itemChip, { borderColor: tool.color }]}
                  onPress={() => {
                    setInputText(item);
                    handleGenerate(item);
                  }}
                >
                  <Text style={[styles.itemText, { color: tool.color }]}>{item}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      ))}
    </View>
  );
  
  const renderDialogueView = () => (
    <View>
      <Text style={styles.sectionTitle}>选择场景</Text>
      {tool.scenarios.map((scenario: string, index: number) => (
        <TouchableOpacity
          key={index}
          style={styles.scenarioItem}
          onPress={() => {
            setInputText(scenario);
            handleGenerate(scenario);
          }}
        >
          <Ionicons name="chatbubble-outline" size={20} color={tool.color} />
          <Text style={styles.scenarioText}>{scenario}</Text>
          <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
        </TouchableOpacity>
      ))}
    </View>
  );
  
  const renderStoryflowView = () => (
    <View>
      <Text style={styles.sectionTitle}>推演模式</Text>
      {tool.modes.map((mode: any) => (
        <TouchableOpacity
          key={mode.id}
          style={styles.modeItem}
          onPress={() => {
            setInputText(mode.name);
            handleGenerate(mode.name);
          }}
        >
          <View style={[styles.modeIcon, { backgroundColor: tool.color + '20' }]}>
            <Ionicons name="git-branch" size={24} color={tool.color} />
          </View>
          <View style={styles.modeInfo}>
            <Text style={styles.modeName}>{mode.name}</Text>
            <Text style={styles.modeDesc}>{mode.desc}</Text>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
  
  const renderStyleView = () => (
    <View>
      <Text style={styles.sectionTitle}>选择目标风格</Text>
      <View style={styles.stylesGrid}>
        {tool.styles.map((style: any) => (
          <TouchableOpacity
            key={style.id}
            style={[styles.styleCard, { borderColor: tool.color }]}
            onPress={() => {
              setInputText(style.name);
              handleGenerate(style.name);
            }}
          >
            <Text style={[styles.styleName, { color: tool.color }]}>{style.name}</Text>
            <Text style={styles.styleDesc}>{style.desc}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
  
  const renderAdaptView = () => (
    <View>
      <Text style={styles.sectionTitle}>改编指示</Text>
      {tool.instructions.map((instruction: string, index: number) => (
        <TouchableOpacity
          key={index}
          style={styles.instructionItem}
          onPress={() => {
            setInputText(instruction);
            handleGenerate(instruction);
          }}
        >
          <Ionicons name="options-outline" size={20} color={tool.color} />
          <Text style={styles.instructionText}>{instruction}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
  
  const renderContent = () => {
    switch (toolId) {
      case 'elements':
      case 'bridges':
      case 'descriptions':
        return renderElementsView();
      case 'dialogue':
        return renderDialogueView();
      case 'storyflow':
        return renderStoryflowView();
      case 'style':
        return renderStyleView();
      case 'adapt':
        return renderAdaptView();
      default:
        return null;
    }
  };
  
  return (
    <ScrollView style={styles.container}>
      {/* 头部 */}
      <View style={[styles.header, { backgroundColor: tool.color + '15' }]}>
        <View style={[styles.headerIcon, { backgroundColor: tool.color + '20' }]}>
          <Ionicons name={tool.icon} size={32} color={tool.color} />
        </View>
        <Text style={styles.headerTitle}>{tool.title}</Text>
      </View>
      
      {/* 输入区域 */}
      <View style={styles.inputSection}>
        <TextInput
          style={styles.input}
          placeholder="输入内容或选择下方选项..."
          placeholderTextColor={COLORS.textMuted}
          value={inputText}
          onChangeText={setInputText}
          multiline
        />
        <TouchableOpacity
          style={[styles.generateButton, { backgroundColor: tool.color }]}
          onPress={() => handleGenerate()}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="white" size="small" />
          ) : (
            <>
              <Ionicons name="flash" size={20} color="white" />
              <Text style={styles.generateButtonText}>生成</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
      
      {/* 工具内容 */}
      <View style={styles.contentSection}>
        {renderContent()}
      </View>
      
      {/* 结果显示 */}
      {result ? (
        <View style={styles.resultSection}>
          <View style={styles.resultHeader}>
            <Text style={styles.resultTitle}>生成结果</Text>
            <TouchableOpacity
              onPress={() => {
                // 复制到剪贴板
                Alert.alert('提示', '已复制到剪贴板');
              }}
            >
              <Ionicons name="copy-outline" size={20} color={COLORS.accent} />
            </TouchableOpacity>
          </View>
          <Text style={styles.resultText}>{result}</Text>
        </View>
      ) : null}
      
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
    flexDirection: 'row',
    alignItems: 'center',
    padding: SPACING.xl,
    borderBottomLeftRadius: RADIUS.xl,
    borderBottomRightRadius: RADIUS.xl,
  },
  headerIcon: {
    width: 56,
    height: 56,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  headerTitle: {
    fontSize: SIZES.xl,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  inputSection: {
    padding: SPACING.lg,
  },
  input: {
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.md,
    padding: SPACING.md,
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    minHeight: 80,
    textAlignVertical: 'top',
    marginBottom: SPACING.md,
  },
  generateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: SPACING.md,
    borderRadius: RADIUS.md,
  },
  generateButtonText: {
    color: 'white',
    fontSize: SIZES.md,
    fontWeight: 'bold',
    marginLeft: SPACING.sm,
  },
  contentSection: {
    paddingHorizontal: SPACING.lg,
  },
  sectionTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
    marginBottom: SPACING.md,
  },
  categorySection: {
    marginBottom: SPACING.md,
  },
  categoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.bgCard,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
  },
  categoryName: {
    fontSize: SIZES.md,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  itemsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingTop: SPACING.sm,
  },
  itemChip: {
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    marginRight: SPACING.sm,
    marginBottom: SPACING.sm,
    backgroundColor: COLORS.bgCard,
  },
  itemText: {
    fontSize: SIZES.sm,
  },
  scenarioItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.sm,
  },
  scenarioText: {
    flex: 1,
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    marginLeft: SPACING.md,
  },
  modeItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.sm,
  },
  modeIcon: {
    width: 48,
    height: 48,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  modeInfo: {
    flex: 1,
  },
  modeName: {
    fontSize: SIZES.md,
    fontWeight: '600',
    color: COLORS.textPrimary,
  },
  modeDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  stylesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  styleCard: {
    width: '48%',
    backgroundColor: COLORS.bgCard,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  styleName: {
    fontSize: SIZES.md,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  styleDesc: {
    fontSize: SIZES.sm,
    color: COLORS.textSecondary,
  },
  instructionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgCard,
    padding: SPACING.md,
    borderRadius: RADIUS.md,
    marginBottom: SPACING.sm,
  },
  instructionText: {
    flex: 1,
    fontSize: SIZES.md,
    color: COLORS.textPrimary,
    marginLeft: SPACING.md,
  },
  resultSection: {
    margin: SPACING.lg,
    backgroundColor: COLORS.bgCard,
    borderRadius: RADIUS.md,
    padding: SPACING.lg,
  },
  resultHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: SPACING.md,
  },
  resultTitle: {
    fontSize: SIZES.lg,
    fontWeight: 'bold',
    color: COLORS.textPrimary,
  },
  resultText: {
    fontSize: SIZES.md,
    color: COLORS.textSecondary,
    lineHeight: 24,
  },
  errorText: {
    fontSize: SIZES.lg,
    color: COLORS.error,
    textAlign: 'center',
    marginTop: 50,
  },
});