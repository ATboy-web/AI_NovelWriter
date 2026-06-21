# AI小说创作工坊 v2.14.2

基于AI的智能小说创作系统 — 支持15种小说类型的全自动创作，5Agent协作架构，世界线分支系统

## 功能特性

### 核心创作
- **一键自动生成**: 大纲 → 角色 → 章节全自动创作
- **5Agent协作架构**: PlotDesigner → WorldBuilder → Writer → Reviewer → Editor
- **多轮迭代修订**: AI审校反馈 → 自动修订，质量阈值自动判定
- **15种小说类型**: 科幻、悬疑、言情、奇幻、都市、历史、武侠、仙侠、恐怖、军事、游戏、体育、穿越、系统流、末日
- **续写功能**: 已完成小说可续写新章，上下文无缝衔接

### 世界线分支系统
- 决策点每章自动检测，主线完结后生成分支
- 分支线拥有完整系统（独立大纲/角色/摘要）
- 世界线面板直接浏览决策点

### 角色系统
- 角色五维度信息（属性/武器/技能/性格/背景）
- 自动生成角色传记
- 角色桥段库（10种桥段类别、6种桥段基调）
- 自动创建新角色，角色成长追踪

### 创作工具
- 事物描写库（10种类别、5种风格）
- 情景对话推演（多角色对话生成）
- 故事流推演（正向/反向/插值/分支推演）
- 风格转换（7种风格模板）
- AI封面生成器（提示词 + HTML预览）

### 导出与阅读
- 多格式导出: TXT、EPUB、PDF、DOCX、Markdown
- 阅读管理器: 支持多种电子书格式
- 文生图提示词系统（电影级镜头语言）

## 下载

| 平台 | 版本 | 大小 | 链接 |
|------|------|------|------|
| Windows | v2.14.2 | ~97MB | [AI_NovelWriter.exe](https://github.com/ATboy-web/AI_NovelWriter/releases/latest) |
| Android | v2.12.3 | ~2.4MB | [AI_NovelWriter.apk](https://github.com/ATboy-web/AI_NovelWriter/releases/tag/v2.12.3) |

## 快速开始

1. 下载 `AI_NovelWriter.exe`
2. 运行程序（首次运行需配置AI服务）
3. 点击 **设置** 配置AI API（支持 Ollama / OpenAI / DeepSeek / Claude 等）
4. 点击 **新建小说** 输入标题、类型、概念
5. 点击 **自动创作** 开始生成

## 系统要求

- Windows 10/11 64位
- 至少4GB内存
- 推荐：本地 Ollama + 14B+ 模型，或 OpenAI/Claude API密钥

## 项目结构

```
ai-novel-writer/
├── novel_app.py              # 主程序 (Tkinter GUI)
├── app/
│   ├── ai_client.py          # AI客户端 (Ollama/OpenAI/DeepSeek/Claude)
│   ├── novel_agent.py        # 5Agent协作智能体
│   ├── agent_orchestrator.py # 智能体编排器
│   ├── memory_manager.py     # 记忆管理系统
│   ├── config.py             # 配置管理
│   ├── scene_detector.py     # 名场面检测
│   ├── note_manager.py       # 笔记管理
│   ├── reading_manager.py    # 阅读管理器
│   ├── fullscreen_writer.py  # 全屏写作模式
│   └── ...                   # 更多模块
├── backend/                  # 后端服务 (FastAPI)
├── mobile-app/               # 移动端 (WebView)
├── installer/                # 打包配置
├── CHANGELOG.md              # 更新日志
├── CONTRIBUTING.md           # 贡献指南
└── LICENSE                   # MIT 许可证
```

## 开发

```bash
# 安装依赖
pip install httpx loguru python-docx pypdf ebooklib markdown beautifulsoup4 Pillow chromadb

# 运行
python novel_app.py

# 打包 EXE
pip install pyinstaller
pyinstaller --onefile --windowed --name AI_NovelWriter \
  --add-data "app;app" --add-data "backend;backend" \
  novel_app.py

# 运行测试
python -m pytest tests/ -v
```

## 许可证

MIT License - 详见 [LICENSE](LICENSE)
