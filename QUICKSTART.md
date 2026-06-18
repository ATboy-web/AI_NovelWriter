# AI小说创作工坊 v2.10.0 - 快速启动指南

## 桌面版（推荐）

### 方式1：下载EXE直接运行
1. 下载 [AI_NovelWriter.exe](https://github.com/ATboy-web/AI_NovelWriter/releases/latest)
2. 双击运行

### 方式2：从源码运行
```bash
git clone https://github.com/ATboy-web/AI_NovelWriter.git
cd AI_NovelWriter
pip install -r requirements.txt
python novel_app.py
```

## 配置AI模型

支持以下方式：
- **Ollama** (本地免费): 安装Ollama → `ollama pull qwen2.5` → 在设置中选择Ollama
- **OpenAI**: 在设置中填入API Key
- **DeepSeek**: 在设置中填入API Key

## 快速创作流程

1. **新建小说**: 输入标题 → 选择类型 → 设定章节日字数 → 首次生成章数(建议10章先看效果)
2. **自动创作**: 系统自动生成世界观 → 角色 → 大纲 → 逐章创作
3. **章节回顾(F12)**: 查看最近章节摘要
4. **继续创作**: 点击"自动创作"继续剩余章节

## 功能速览

| 功能 | 快捷键/位置 |
|------|------------|
| 自动创作 | 左侧工具栏 |
| 章节回顾 | F12 或左下按钮 |
| AI辅助写作 | F11 |
| 全屏写作 | F9 |
| 大纲跳转 | 左侧大纲列表点击 |
| 角色面板 | 左侧角色卡片 |
| 角色成长日志 | 角色详情底部 |
| 名场面提示词 | scene_prompts/ 目录 |

## 项目结构

```
ai-novel-writer/
├── AI_NovelWriter.exe    # Windows可执行文件
├── novel_app.py           # 主程序
├── app/                   # 核心模块
│   ├── ai_client.py       # AI模型客户端
│   ├── novel_agent.py     # 智能体编排
│   └── memory_manager.py  # 记忆系统
├── character_system.py    # 角色系统
├── novel_toolkit.py       # 创作工具集
├── installer/             # 打包脚本
└── tests/                 # 单元测试(40个)
```
