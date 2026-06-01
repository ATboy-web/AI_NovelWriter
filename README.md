# AI小说创作工坊

**开源的AI辅助小说创作软件**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0.0-blue.svg)](https://github.com/ATboy-web/AI_NovelWriter/releases)

一个完整的AI小说创作工具，支持桌面端和移动端，帮助创作者高效完成小说创作。

## ✨ 功能特性

### 🤖 AI智能创作
- **AI自动写小说** - 支持Ollama本地模型、OpenAI、DeepSeek、Claude等
- **长上下文记忆** - 自动维护世界观、角色、故事摘要
- **智能体创作** - 自动生成世界观→角色→大纲→章节→审校

### ✍️ AI辅助写作
- **AI续写** - Tab键触发，智能续写20-50字
- **AI扩写** - 将选中文本扩展为详细内容
- **AI简写** - 精简压缩文本
- **AI润色** - 优化语言表达
- **AI改写** - 用不同方式重新表达
- **AI对话生成** - 根据上下文生成角色对话

### 📚 创作工具集
- **小说元素库** - 16类预设元素，组合生成背景设定
- **角色桥段库** - 14种经典桥段模板
- **事物描写库** - 10类描写生成
- **情景对话推演** - 角色互动对话生成
- **故事流推演** - 正向/反向/中间/分支推演
- **风格转换** - 7种风格切换
- **智能改编** - 片段改编、匹配率显示

### 📖 阅读管理
- **多格式支持** - TXT、EPUB、PDF、DOCX、Markdown
- **书签功能** - 添加、删除、跳转
- **阅读主题** - 浅色/深色/护眼模式
- **搜索功能** - 书籍内关键词搜索

### 📱 多平台支持
- **桌面版** - Python + tkinter (Windows/Mac/Linux)
- **移动版** - React Native (Android)

## 🚀 快速开始

### 桌面版

```bash
# 克隆项目
git clone https://github.com/ATboy-web/AI_NovelWriter.git
cd AI_NovelWriter

# 安装依赖
pip install httpx

# 运行
python novel_app.py
```

### Android版

从 [Releases](https://github.com/ATboy-web/AI_NovelWriter/releases) 下载APK安装。

## 🔧 配置AI模型

### Ollama本地模型（推荐）

1. 安装 [Ollama](https://ollama.ai)
2. 下载模型：`ollama pull qwen2.5:14b`
3. 在设置中选择Ollama，点击"检测Ollama"

### 云端API

在设置中配置：
- **OpenAI**: 需要API密钥
- **DeepSeek**: 需要API密钥  
- **Claude**: 需要API密钥

## 📸 界面预览

### 桌面版
- 深色主题界面
- 左侧：小说信息、智能体步骤、大纲
- 右侧：章节内容、日志、审校、笔记、创作工具

### 移动版
- Material Design风格
- 底部导航：首页、书架、写作、工具、我的
- 全屏写作模式

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 桌面版 | Python 3.11+ / tkinter |
| 移动版 | React Native / Expo |
| AI模型 | Ollama / OpenAI API / DeepSeek API |
| 数据存储 | 本地JSON文件 |
| 打包工具 | PyInstaller (桌面) / Gradle (Android) |

## 📁 项目结构

```
AI_NovelWriter/
├── novel_app.py          # 桌面版主程序
├── novel_toolkit.py      # 创作工具集
├── installer/            # 打包配置
├── mobile-app/           # 移动版源码
│   ├── App.tsx           # 主入口
│   └── src/
│       ├── screens/      # 页面组件
│       ├── services/     # API服务
│       └── styles/       # 主题样式
└── backend/              # 后端服务（可选）
```

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork本项目
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -m 'Add xxx feature'`)
4. 推送到分支 (`git push origin feature/xxx`)
5. 创建Pull Request

## 📄 开源许可证

本项目采用 **MIT许可证** 开源，完全免费使用。

```
MIT License

Copyright (c) 2024 AI_NovelWriter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 🔗 相关链接

- [GitHub仓库](https://github.com/ATboy-web/AI_NovelWriter)
- [Releases下载](https://github.com/ATboy-web/AI_NovelWriter/releases)
- [问题反馈](https://github.com/ATboy-web/AI_NovelWriter/issues)

## 💡 致谢

感谢以下开源项目：
- [Ollama](https://ollama.ai) - 本地AI模型运行框架
- [React Native](https://reactnative.dev) - 跨平台移动应用框架
- [Expo](https://expo.dev) - React Native开发工具

---

**⭐ 如果这个项目对你有帮助，请给个Star支持一下！**
