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
  
  // 获取小说类型
  getNovelTypes() {
    return [
      { id: 'scifi', name: '科幻小说', icon: 'rocket', color: '#3b82f6' },
      { id: 'mystery', name: '悬疑推理', icon: 'search', color: '#8b5cf6' },
      { id: 'romance', name: '言情小说', icon: 'heart', color: '#ec4899' },
      { id: 'fantasy', name: '奇幻小说', icon: 'star', color: '#f59e0b' },
      { id: 'urban', name: '都市小说', icon: 'business', color: '#10b981' },
    ];
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
