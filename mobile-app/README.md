# AI小说创作工坊 - 移动版

跨平台移动应用，支持iOS和Android。

## 功能特性

### 核心功能
- 小说创作和编辑
- AI辅助写作（续写、扩写、简写、润色、改写、对话）
- Markdown编辑和预览
- 多种小说类型支持

### 创作工具
- 小说元素库
- 角色桥段库
- 事物描写库
- 情景对话推演
- 故事流推演
- 风格转换
- 智能改编

### 书架管理
- 小说列表
- 章节管理
- 进度统计
- 云端同步

## 快速开始

### 环境要求
- Node.js 18+
- Expo CLI
- Android Studio (Android) 或 Xcode (iOS)

### 安装依赖
```bash
cd mobile-app
npm install
```

### 启动开发服务器
```bash
# 启动Expo
npm start

# Android
npm run android

# iOS
npm run ios
```

### 连接后端

1. 确保PC和手机在同一局域网
2. 在设置中配置API地址（如 `http://192.168.1.100:8001`）
3. 启动桌面版的AI服务

## 项目结构

```
mobile-app/
├── App.tsx                 # 主应用入口
├── src/
│   ├── screens/           # 页面组件
│   │   ├── HomeScreen.tsx      # 首页
│   │   ├── EditorScreen.tsx    # 写作编辑器
│   │   ├── LibraryScreen.tsx   # 书架
│   │   ├── ToolsScreen.tsx     # 工具集
│   │   └── SettingsScreen.tsx  # 设置
│   ├── components/        # 公共组件
│   ├── services/          # API服务
│   │   └── api.ts             # 后端通信
│   ├── styles/            # 样式
│   │   └── theme.ts           # 主题配置
│   └── utils/             # 工具函数
├── assets/                # 静态资源
├── app.json              # Expo配置
└── package.json          # 依赖配置
```

## 技术栈

- **框架**: React Native + Expo
- **导航**: React Navigation
- **状态管理**: React Hooks
- **网络**: Axios
- **存储**: AsyncStorage
- **图标**: Expo Vector Icons

## 构建APK

```bash
# Android APK
expo build:android

# iOS IPA
expo build:ios
```

## 开发计划

- [x] 基础框架搭建
- [x] 首页和书架
- [x] 写作编辑器
- [x] AI辅助功能
- [x] 创作工具集
- [ ] 离线支持
- [ ] 云端同步
- [ ] 推送通知
- [ ] 深度链接
