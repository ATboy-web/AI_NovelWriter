/**
 * API服务 - 与后端通信
 */

import axios, { AxiosInstance } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// API配置
const API_CONFIG = {
  // 默认连接本地服务（同一局域网）
  baseURL: 'http://192.168.1.100:8001',
  timeout: 30000,
};

class ApiService {
  private client: AxiosInstance;
  private apiKey: string = '';
  
  constructor() {
    this.client = axios.create({
      baseURL: API_CONFIG.baseURL,
      timeout: API_CONFIG.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    this.loadConfig();
  }
  
  // 加载配置
  async loadConfig() {
    try {
      const config = await AsyncStorage.getItem('api_config');
      if (config) {
        const parsed = JSON.parse(config);
        this.client.defaults.baseURL = parsed.baseURL || API_CONFIG.baseURL;
        this.apiKey = parsed.apiKey || '';
      }
    } catch (e) {
      console.log('加载配置失败:', e);
    }
  }
  
  // 保存配置
  async saveConfig(config: { baseURL?: string; apiKey?: string }) {
    try {
      if (config.baseURL) {
        this.client.defaults.baseURL = config.baseURL;
      }
      if (config.apiKey) {
        this.apiKey = config.apiKey;
      }
      await AsyncStorage.setItem('api_config', JSON.stringify({
        baseURL: this.client.defaults.baseURL,
        apiKey: this.apiKey,
      }));
    } catch (e) {
      console.log('保存配置失败:', e);
    }
  }
  
  // 健康检查
  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health');
      return response.data?.status === 'healthy';
    } catch {
      return false;
    }
  }
  
  // 生成小说章节
  async generateChapter(params: {
    novelType: string;
    chapterTitle: string;
    chapterOutline: string;
    previousContent?: string;
    maxTokens?: number;
  }): Promise<any> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: params.novelType,
      chapter_title: params.chapterTitle,
      chapter_outline: params.chapterOutline,
      previous_content: params.previousContent || '',
      max_tokens: params.maxTokens || 2000,
      temperature: 0.8,
    });
    return response.data;
  }
  
  // 生成大纲
  async generateOutline(params: {
    novelType: string;
    title: string;
    synopsis: string;
    chapterCount: number;
  }): Promise<any> {
    const response = await this.client.post('/api/v1/generate/outline', {
      novel_type: params.novelType,
      title: params.title,
      synopsis: params.synopsis,
      chapter_count: params.chapterCount,
    });
    return response.data;
  }
  
  // 生成人物
  async generateCharacter(params: {
    novelType: string;
    characterName: string;
    characterRole: string;
    characterTraits: string[];
  }): Promise<any> {
    const response = await this.client.post('/api/v1/generate/character', {
      novel_type: params.novelType,
      character_name: params.characterName,
      character_role: params.characterRole,
      character_traits: params.characterTraits,
    });
    return response.data;
  }
  
  // AI续写
  async aiContinue(text: string, context?: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '续写',
      chapter_outline: `请续写以下内容：\n\n${text}`,
      previous_content: context || '',
      max_tokens: 200,
      temperature: 0.8,
    });
    return response.data?.content || '';
  }
  
  // AI扩写
  async aiExpand(text: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '扩写',
      chapter_outline: `请将以下内容扩写为更详细生动的版本：\n\n${text}`,
      max_tokens: 1000,
      temperature: 0.7,
    });
    return response.data?.content || '';
  }
  
  // AI简写
  async aiCompress(text: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '简写',
      chapter_outline: `请精简以下内容，保留核心情节：\n\n${text}`,
      max_tokens: 500,
      temperature: 0.5,
    });
    return response.data?.content || '';
  }
  
  // AI润色
  async aiPolish(text: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '润色',
      chapter_outline: `请润色以下内容，优化语言表达：\n\n${text}`,
      max_tokens: 800,
      temperature: 0.7,
    });
    return response.data?.content || '';
  }
  
  // 获取小说类型 - 男女频完整标签体系
  getNovelTypes() {
    return {
      male: [
        { id: 'xuanhuan', name: '玄幻', icon: 'flame', color: '#ef4444', 
          sub: ['东方玄幻', '异世大陆', '高武世界'],
          tags: ['废材崛起', '扮猪吃虎', '杀伐果断', '系统流', '穿越大军', '重生复仇', '无敌流', '升级流', '异界大陆', '灵气复苏'] },
        { id: 'xianxia', name: '仙侠', icon: 'leaf', color: '#8b5cf6',
          sub: ['古典仙侠', '现代修真', '洪荒封神'],
          tags: ['修仙问道', '法宝灵器', '渡劫飞升', '宗门林立', '天道轮回'] },
        { id: 'dushi', name: '都市', icon: 'business', color: '#3b82f6',
          sub: ['都市生活', '都市异能', '青春校园'],
          tags: ['扮猪吃虎', '杀伐果断', '智商在线', '低调男主', '逆天改命'] },
        { id: 'lishi', name: '历史', icon: 'time', color: '#f59e0b',
          sub: ['架空历史', '两宋元明', '三国争霸'],
          tags: ['王朝争霸', '穿越重生', '谋士军师', '权谋斗争'] },
        { id: 'kehuan', name: '科幻', icon: 'rocket', color: '#06b6d4',
          sub: ['星际文明', '末世危机', '时空穿梭'],
          tags: ['末世废土', '星空宇宙', '赛博朋克', '求生冒险', '星际战争'] },
        { id: 'xuanyi', name: '悬疑', icon: 'search', color: '#6366f1',
          sub: ['灵异恐怖', '侦探推理', '探险揭秘'],
          tags: ['诡异复苏', '悬疑推理', '恐怖灵异', '真相揭秘'] },
        { id: 'youxi', name: '游戏', icon: 'game-controller', color: '#10b981',
          sub: ['电子竞技', '虚拟网游', '游戏异界'],
          tags: ['数据化', '职业选手', '游戏异界', '电竞巅峰'] },
        { id: 'junshi', name: '军事', icon: 'shield', color: '#6b7280',
          sub: ['抗战烽火', '谍战特工', '战争幻想'],
          tags: ['铁血军魂', '军事科技', '战争史诗'] },
        { id: 'wuxia', name: '武侠', icon: 'sword', color: '#dc2626',
          sub: ['传统武侠', '国术古武', '武侠幻想'],
          tags: ['江湖恩怨', '绝世武功', '侠之大者', '一代宗师'] },
        { id: 'tiyu', name: '体育', icon: 'football', color: '#84cc16',
          sub: ['篮球风云', '足球天下', '综合竞技'],
          tags: ['热血竞技', '逆袭夺冠', '体育精神'] },
        { id: 'qingshuo', name: '轻小说', icon: 'book', color: '#ec4899',
          sub: ['原生幻想', '搞笑吐槽', '恋爱日常'],
          tags: ['轻松欢脱', '二次元', '日常向'] },
      ],
      female: [
        { id: 'guyan', name: '古代言情', icon: 'rose', color: '#ec4899',
          sub: ['女尊王朝', '宫闱宅斗', '穿越奇情'],
          tags: ['穿越重生', '宅斗宫斗', '甜宠', '虐恋情深', '先婚后爱'] },
        { id: 'xianyan', name: '现代言情', icon: 'heart', color: '#f43f5e',
          sub: ['豪门总裁', '都市婚恋', '职场丽人'],
          tags: ['霸总老公', '追妻火葬场', '契约婚姻', '欢喜冤家', '隐婚密爱', '替身前妻'] },
        { id: 'huanqing', name: '幻想言情', icon: 'sparkles', color: '#a855f7',
          sub: ['异世恋歌', '快穿攻略', '魔法幻情'],
          tags: ['快穿攻略', '系统空间', '神仙爱情', '异世界'] },
        { id: 'chunai', name: '纯爱', icon: 'moon', color: '#6366f1',
          sub: ['古代纯爱', '现代纯爱', '幻想纯爱'],
          tags: ['双向奔赴', '暗恋成真', '温馨治愈'] },
        { id: 'qingchun', name: '浪漫青春', icon: 'school', color: '#22c55e',
          sub: ['青春校园', '疼痛成长', '纯爱唯美'],
          tags: ['校园恋爱', '青梅竹马', '暗恋', '酸甜初恋'] },
        { id: 'xianqing', name: '仙侠奇缘', icon: 'flower', color: '#f59e0b',
          sub: ['古典仙缘', '修仙情劫', '洪荒情缘'],
          tags: ['前世今生', '师徒恋', '仙魔恋'] },
        { id: 'nvxuan', name: '悬疑灵异', icon: 'eye', color: '#6b7280',
          sub: ['推理侦探', '恐怖惊悚', '灵异鬼怪'],
          tags: ['悬疑推理', '灵异事件'] },
        { id: 'nvyou', name: '游戏竞技', icon: 'trophy', color: '#10b981',
          sub: ['电子竞技', '全息网游', '电竞爱情'],
          tags: ['电竞女神', '游戏情缘'] },
        { id: 'duanpian', name: '短篇', icon: 'clipboard', color: '#94a3b8',
          sub: ['短篇言情', '微小说', '轻小说'],
          tags: ['短篇', '精悍'] },
      ],
    };
  }
  
  // AI改写
  async aiRewrite(text: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '改写',
      chapter_outline: `请用不同的表达方式重新改写以下内容，保持相同的情节和含义：\n\n${text}`,
      max_tokens: 800,
      temperature: 0.7,
    });
    return response.data?.content || '';
  }
  
  // AI生成对话
  async aiDialogue(scenario: string, characters?: string[]): Promise<string> {
    const charInfo = characters ? `角色：${characters.join('、')}` : '';
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '对话生成',
      chapter_outline: `场景：${scenario}\n${charInfo}\n请生成3-5轮角色对话，要求自然生动，符合人物性格。`,
      max_tokens: 600,
      temperature: 0.8,
    });
    return response.data?.content || '';
  }
  
  // AI故事流推演
  async aiStoryFlow(params: {
    mode: 'forward' | 'backward' | 'bridge' | 'branch';
    background?: string;
    beginning?: string;
    ending?: string;
    events?: string[];
  }): Promise<string> {
    let prompt = '';
    switch (params.mode) {
      case 'forward':
        prompt = `背景：${params.background}\n事件：${params.events?.join('、')}\n请推演故事的后续发展。`;
        break;
      case 'backward':
        prompt = `结局：${params.ending}\n请推演导致这个结局的过程。`;
        break;
      case 'bridge':
        prompt = `开端：${params.beginning}\n结局：${params.ending}\n请推演连接开端和结局的中间过程。`;
        break;
      case 'branch':
        prompt = `背景：${params.background}\n请生成3个不同的故事走向分支。`;
        break;
    }
    
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'fantasy',
      chapter_title: '故事流推演',
      chapter_outline: prompt,
      max_tokens: 1500,
      temperature: 0.8,
    });
    return response.data?.content || '';
  }
  
  // AI风格转换
  async aiStyleTransfer(text: string, targetStyle: string): Promise<string> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '风格转换',
      chapter_outline: `请将以下内容转换为${targetStyle}风格：\n\n${text}`,
      max_tokens: 1000,
      temperature: 0.7,
    });
    return response.data?.content || '';
  }
  
  // AI智能改编
  async aiAdapt(text: string, instruction: string): Promise<{ adapted: string; matchRate: number }> {
    const response = await this.client.post('/api/v1/generate/chapter', {
      novel_type: 'urban',
      chapter_title: '智能改编',
      chapter_outline: `请按以下要求改编：${instruction}\n原文：${text}`,
      max_tokens: 1000,
      temperature: 0.7,
    });
    
    // 计算匹配率（简化版本）
    const adapted = response.data?.content || '';
    const matchRate = Math.max(0, Math.min(100, 100 - (adapted.length - text.length) / text.length * 50));
    
    return { adapted, matchRate: Math.round(matchRate) };
  }
  
  // 获取Ollama模型列表
  async getOllamaModels(): Promise<string[]> {
    try {
      const response = await this.client.get('/api/tags');
      return response.data?.models?.map((m: any) => m.name) || [];
    } catch {
      return [];
    }
  }
}

// 导出单例
export const apiService = new ApiService();
export default apiService;
