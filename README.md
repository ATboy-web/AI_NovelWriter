# AI小说创作工坊

**开源的AI辅助小说创作软件** | **免费 · 无需注册 · 无需付费**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.1.0-blue.svg)](https://github.com/ATboy-web/AI_NovelWriter/releases/tag/v2.1.0)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)

一个完整的AI小说创作工具，支持桌面端和移动端，帮助创作者高效完成小说创作。

---

## ✨ 功能特性（v2.1.0）

### 🤖 AI智能创作（参考AutoGen多智能体架构）
- **多智能体协作** - Writer（作家）/ Reviewer（审校）/ Editor（质量门）三角色分工
- **迭代修订循环** - 质量不达标自动触发修订，最多3轮
- **质量门控** - 综合评分≥75分才通过，不达标退回重写
- **AI自动写小说** - 支持Ollama本地模型、OpenAI、DeepSeek、Claude等
- **长上下文记忆（参考Supermemory）** - RAG语义检索、记忆评分、事件时间线、记忆衰减模型

### ✍️ AI辅助写作
- **AI续写** - Tab键触发，智能续写20-50字
- **AI扩写** - 将选中文本扩展为详细内容
- **AI简写** - 精简压缩文本
- **AI润色** - 优化语言表达
- **AI改写** - 用不同方式重新表达
- **AI对话生成** - 根据上下文生成角色对话
- **全屏沉浸式写作** - 支持打字机模式、字体缩放、纸张位置、背景主题
- **Markdown编辑** - 语法高亮、实时预览、快捷键工具栏

### 📚 创作工具集（500+内容模板）
- **小说元素库** - 22类 160+元素，支持自定义添加
- **角色桥段库** - 18类 80+模板（对战/登场/情侣/修炼/装逼打脸等）
- **事物描写库** - 18类 150+关键词
- **情景对话推演** - 多轮对话生成，可截断继续
- **故事流推演** - 4种模式（正向/反向/分支/冲突升级）
- **风格转换** - 10种风格（热血/细腻/幽默/暗黑/古风/甜宠/虐恋等）
- **智能改编** - 片段改编、批量改编、匹配率显示
- **热点改编** - 联网热点梗库 + AI搜索改编 + 用户自定义添加

### 👫 男女频标签体系
- **男生频道** - 12大类（玄幻/仙侠/都市/历史/科幻/悬疑/游戏/军事/武侠/体育/轻小说/二次元）
- **女生频道** - 9大类（古代言情/现代言情/幻想言情/纯爱/浪漫青春/仙侠奇缘/悬疑灵异/游戏竞技/短篇）
- **附加标签** - 角色设定/情节元素/世界观/爽点标签

### 📖 阅读管理
- **多格式支持** - TXT、EPUB、PDF、DOCX、Markdown
- **书签功能** - 添加、删除、跳转
- **阅读主题** - 浅色/深色/护眼模式
- **搜索功能** - 书籍内关键词搜索

### 📝 笔记系统
- **文档笔记** - 当前章节专属
- **工程笔记** - 整个小说工程共享
- **便笺本** - 全局共享，可跨工程发送

### 📱 多平台支持
- **桌面版** - Python + tkinter (Windows)
- **移动版** - React Native (Android APK)

---

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

---

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
- **自定义API**: 兼容OpenAI格式

---

## 📋 版本历史

### v2.1.0 (2026-06-01)

**新功能：**
- ✅ 参考AutoGen架构重构智能体（Writer/Reviewer/Editor多角色协作+迭代修订）
- ✅ 参考Supermemory优化记忆系统（RAG检索/语义去重/记忆评分/事件时间线）
- ✅ 男女频完整标签体系（男生12类/女生9类 + 附加标签）
- ✅ 联网搜索热点改编（内置20+热点梗 + AI搜索 + 用户自定义）
- ✅ 大幅扩充创作工具（元素库160+/桥段库80+/描写库150+）
- ✅ 笔记系统（文档笔记/工程笔记/便笺本）
- ✅ 阅读管理器（TXT/EPUB/PDF/DOCX/MD）
- ✅ 用户自定义热点/梗/笑话功能
- ✅ 全屏写作模式（打字机/Markdown/字体缩放/背景主题）
- ✅ Android APK（React Native）

**Bug修复：**
- ✅ 修复MemoryManager缺少get_settings/save_settings
- ✅ 修复FullscreenWriter._toggle_ai引用未定义self.ai_var
- ✅ 修复EPUB read_book缩进错误
- ✅ 修复_adapt_random访问不存在的字典键
- ✅ 修复delete_custom_meme索引错误
- ✅ 修复模板{n-1}格式错误
- ✅ 修复tkinter线程安全问题（6处）
- ✅ 修复KeyRelease绑定冲突
- ✅ 修复PDF PageObject比较错误
- ✅ 修复新建小说时genre_combo未定义错误

### v2.0.0 (2026-05-30)
- 初始版本发布

---

## ⚠️ 已知问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **tkinter界面偶尔冻结** | 中 | 部分复杂操作（如自动创作全流程）可能出现短暂卡顿，等待即可 |
| **Ollama连接超时** | 中 | 本地Ollama服务未启动时，检测Ollama可能超时较长（约30秒） |
| **EPUB大文件加载慢** | 低 | 超过10MB的EPUB文件解析较慢，建议分章节导入 |
| **PDF中文乱码** | 低 | 部分扫描版PDF无法正确提取文字，建议使用TXT或DOCX |
| **Android版功能不完整** | 中 | 移动版暂不支持全屏写作、文生图、阅读管理器等桌面版功能 |
| **热点改编内容有限** | 低 | 内置热点梗库约20条，用户可自行添加更多 |

---

## 🗺️ 开发路线图

### 近期计划
- [ ] 优化AI续写的响应速度
- [ ] 添加更多热点梗内容（定期更新）
- [ ] 支持导出EPUB/PDF格式
- [ ] 添加暗色/亮色主题切换（桌面版）
- [ ] 修复PDF中文提取问题

### 中期计划
- [ ] 添加文生图集成（ComfyUI/SD WebUI）
- [ ] 支持多人协作（云端同步）
- [ ] 添加iOS版本
- [ ] 集成更多AI模型（GPT-4o、Claude 3.5等）
- [ ] 添加插件系统

### 长期计划
- [ ] 建立创作者社区
- [ ] 支持多语言
- [ ] 添加语音输入
- [ ] AI绘图自动生成插图
- [ ] 建立创作者生态

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 桌面版 | Python 3.11+ / tkinter |
| 移动版 | React Native / Expo |
| AI模型 | Ollama / OpenAI API / DeepSeek API |
| 智能体 | 参考AutoGen多智能体协作架构 |
| 记忆系统 | 参考Supermemory RAG检索架构 |
| 数据存储 | 本地JSON文件 |
| 打包工具 | PyInstaller (桌面) / Gradle (Android) |
| 版本管理 | Git |

---

## 📁 项目结构

```
AI_NovelWriter/
├── novel_app.py          # 桌面版主程序 (4900+行)
├── novel_toolkit.py      # 创作工具集 (580+行)
├── installer/            # PyInstaller打包配置
│   ├── dist/             # 打包输出 (exe)
│   └── novel_app.spec    # 打包规范
├── mobile-app/           # React Native移动版
│   ├── App.tsx           # 主入口
│   ├── src/screens/      # 页面组件
│   ├── src/services/     # API服务
│   ├── src/styles/       # 主题样式
│   └── android/          # Android构建配置
├── backend/              # 后端服务（可选）
│   ├── ai-service/       # AI模型服务
│   └── novel-service/    # 小说生成服务
└── LICENSE               # MIT许可证
```

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork本项目
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -m 'Add xxx feature'`)
4. 推送到分支 (`git push origin feature/xxx`)
5. 创建Pull Request

### 贡献方向

- 🐛 Bug修复
- 📚 扩充创作工具内容（元素/桥段/描写/热点梗）
- 🌐 多语言支持
- 📱 移动版功能完善
- 📖 文档完善
- 🎨 UI/UX优化

---

## 📄 开源许可证

本项目采用 **MIT许可证** 开源，完全免费使用，无需注册，无需付费。

详见 [LICENSE](LICENSE) 文件。

---

## 🔗 相关链接

- [GitHub仓库](https://github.com/ATboy-web/AI_NovelWriter)
- [Releases下载](https://github.com/ATboy-web/AI_NovelWriter/releases)
- [问题反馈](https://github.com/ATboy-web/AI_NovelWriter/issues)
- [Ollama官网](https://ollama.ai)

---

## 💡 致谢

感谢以下开源项目和参考：
- [Ollama](https://ollama.ai) - 本地AI模型运行框架
- [AutoGen](https://github.com/microsoft/autogen) - 多智能体协作架构参考
- [Supermemory](https://github.com/supermemoryai/supermemory) - 记忆系统架构参考
- [React Native](https://reactnative.dev) - 跨平台移动应用框架
- [Expo](https://expo.dev) - React Native开发工具

---

**⭐ 如果这个项目对你有帮助，请给个Star支持一下！**
