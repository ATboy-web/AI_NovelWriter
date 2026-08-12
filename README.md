

# AI小说创作工坊 v2.14.2

[![CI](https://github.com/ATboy-web/AI_NovelWriter/actions/workflows/ci.yml/badge.svg)](https://github.com/ATboy-web/AI_NovelWriter/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT%20Modified-green.svg)](LICENSE)

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
│   ├── secure_config.py      # 安全配置（API密钥加密存储）
│   ├── config.py             # 配置管理
│   └── ...                   # 更多模块
├── backend/                  # 后端服务 (FastAPI)
│   ├── ai-service/           # AI模型服务
│   └── novel-service/        # 小说生成服务
├── frontend-react/           # 前端界面 (React + Vite)
├── mobile-app/               # 移动端 (Kotlin原生)
├── monitoring/               # 监控配置
│   ├── prometheus.yml        # Prometheus配置
│   ├── alertmanager.yml      # 告警管理配置
│   ├── promtail.yml          # 日志收集配置
│   └── grafana/              # Grafana仪表板
├── scripts/                  # 运维脚本
│   └── backup/               # 备份脚本
├── tests/                    # 测试用例
├── docs/                     # 文档
│   └── API.md                # API文档
├── docker-compose.yml        # Docker编排
├── .github/workflows/        # CI/CD流水线
├── CONTRIBUTING.md           # 贡献指南
└── LICENSE                   # MIT Modified许可证
```

## 开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行桌面版
python novel_app.py

# 运行测试
python -m pytest tests/ -v

# 代码质量检查
ruff check app/ tests/
```

## Docker 部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置数据库密码等

# 2. 启动服务
docker-compose up -d

# 3. 查看服务状态
docker-compose ps

# 4. 访问服务
# - 前端: http://localhost:3000
# - AI服务: http://localhost:8001
# - 小说服务: http://localhost:8002
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3001
```

## 基础设施

### 监控系统
- **Prometheus**: 指标采集和存储
- **Grafana**: 可视化仪表板
- **Alertmanager**: 告警通知
- **Loki + Promtail**: 日志聚合

### 备份系统
```bash
# 执行全量备份
./scripts/backup/backup-scheduler.sh full

# 安装定时备份（每天凌晨2点）
./scripts/backup/backup-scheduler.sh install '0 2 * * *'

# 查看备份状态
./scripts/backup/backup-scheduler.sh status
```

### 测试
```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行带覆盖率的测试
python -m pytest tests/ --cov=app --cov-report=html
```

## 贡献

欢迎贡献！请阅读 [贡献指南](CONTRIBUTING.md) 了解如何参与项目开发。

## 许可证

MIT Modified License - 详见 [LICENSE](LICENSE)

**商用需注明来源**：任何商业使用请注明项目名称和 GitHub 链接。
