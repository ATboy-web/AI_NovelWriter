# AI自动写小说系统 v2.8.0

智能小说创作工坊 - 支持多种类型小说的自动创作

## 功能特性

### 核心功能
- **自动创作**：一键自动生成大纲、角色、章节
- **续写功能**：已完成小说可续写新章
- **章节选择**：下拉选择器跳转任意章节
- **停止创作**：随时停止自动创作
- **多格式导出**：支持TXT、EPUB、PDF、DOCX、Markdown

### 专业创作框架
- **Writer**：五幕法章节结构、感官五维场景构建、叙事节奏控制
- **Reviewer**：六维度评分(结构/角色/节奏/细节/对话/风格)
- **Editor**：编辑裁定标准和原则
- **Character**：角色五维度设计框架
- **Outline**：三幕结构规划框架
- **Synopsis**：四句话简介公式
- **Biography**：六幕法传记写作框架

### 角色管理
- 角色五维度信息展示(属性/武器/技能/性格/背景)
- 角色面板可滚动显示完整详情
- 一键生成角色个人传记(保存到biographies目录)
- 角色桥段库(10种桥段类别、6种桥段基调)

### 文生图提示词系统
- AI自动检测名场面、人物描写、关键时刻
- 自动选择画面比例(1:1, 3:4, 9:16, 16:9)
- 电影级镜头语言(特写/中景/远景/俯仰角)
- 专业摄影构图(三分法/引导线/框架构图)
- 提示词自动保存到scene_prompts目录

### 创作工具
- 事物描写库(10种描写类别、5种描写风格)
- 情景对话推演(多角色对话生成)
- 故事流推演(正向/反向/插值/分支推演)
- 风格转换(7种风格模板)
- 编辑器右键菜单(选中文本跳转创作工具)

### 其他功能
- 侧边栏可滚动
- 多种AI模型支持(Ollama/OpenAI/DeepSeek/Claude)
- 向量检索增强(ChromaDB)
- 一致性审校功能
- 阅读管理器(支持TXT/EPUB/PDF/DOCX/Markdown)

## 下载

[最新版本 v2.8.0](https://github.com/ATboy-web/AI_NovelWriter/releases/tag/v2.8.0)

## 使用方法

1. 下载AI_NovelWriter.exe
2. 运行程序
3. 配置AI API(Ollama/OpenAI等)
4. 新建小说或打开已有小说
5. 点击自动创作或手动创作

## 系统要求

- Windows 10/11
- 至少4GB内存
- 推荐使用GPU加速(可选)

## 项目结构

```
ai-novel-writer/
├── novel_app.py          # 主程序
├── app/
│   ├── ai_client.py      # AI客户端(支持多模型)
│   ├── novel_agent.py    # 小说创作智能体
│   ├── memory_manager.py # 记忆管理
│   ├── scene_detector.py # 名场面检测
│   ├── navigation.py     # 导航菜单
│   └── agent_orchestrator.py # 智能体编排
├── tests/                # 测试文件
└── installer/            # 打包配置
```

## 开发

```bash
# 安装依赖
pip install httpx pytest

# 运行测试
python -m pytest tests/ -v

# 打包
cd installer
pyinstaller novel_app.spec
```

## 许可证

MIT License
