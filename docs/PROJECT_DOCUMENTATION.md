# AI_NovelWriter 项目完整文档

## 项目概述

**项目名称**: AI自动写小说系统 (AI_NovelWriter)  
**项目版本**: v2.14.4 (EXE) / v2.12.5 (APK)  
**GitHub**: https://github.com/ATboy-web/AI_NovelWriter  
**许可证**: MIT Modified (商用需注明来源)

## 核心功能

### 1. 多类型小说生成
支持15种小说类型：
- 科幻、悬疑、言情、奇幻、都市
- 历史、武侠、仙侠、恐怖、军事
- 游戏、体育、穿越、系统流、末日

### 2. 5-Agent协作架构
- **PlotDesigner**: 情节设计师 - 大纲分解、伏笔管理
- **WorldBuilder**: 世界构建师 - 世界观一致性
- **Writer**: 作家 - 创作小说内容
- **Reviewer**: 审校 - 检查质量和一致性
- **Editor**: 编辑 - 质量门裁定

### 3. 记忆管理系统
- 全局摘要（1个文件）
- 卷级摘要（每100章）
- 弧线摘要（重要剧情线）
- 章节摘要（5000章支持）
- 倒排索引RAG检索
- 角色活跃度追踪

### 4. 写作技能系统
- 去AI味处理器（AntiSlopProcessor）
- 知识图谱（角色关系、事件追踪）
- 时间感知记忆
- 风格分析和转换

### 5. 阅读管理器
- 多格式支持：TXT、EPUB、PDF、DOCX、Markdown
- 书签管理
- 阅读进度跟踪
- 关键词搜索

## 技术架构

### 技术栈
- **后端**: Python + FastAPI
- **前端**: Node.js + Express
- **数据库**: PostgreSQL + Redis
- **AI模型**: 本地模型(llama.cpp) + 云端API(OpenAI/Claude/DeepSeek)
- **容器化**: Docker + docker-compose

### 服务划分
1. **AI模型服务** (端口: 8001) - 模型管理和推理
2. **小说生成服务** (端口: 8002) - 核心业务逻辑
3. **前端服务** (端口: 3000) - 用户界面
4. **Nginx代理** (端口: 80) - 反向代理

### 核心模块
```
app/
├── novel_agent.py      # 核心智能体（5-Agent协作）
├── ai_client.py        # AI客户端（多模型支持）
├── memory_manager.py   # 记忆管理系统
├── writing_skills.py   # 写作技能系统
├── scene_detector.py   # 场景检测器
├── diagnostic_logger.py # 诊断日志
├── reading_manager.py  # 阅读管理器
├── secure_config.py    # 安全配置
├── config.py           # 应用配置
└── panels/             # UI面板（12个）
```

## 代码质量

### 测试覆盖
- **总测试数**: 1073个
- **总体覆盖率**: 87.2%（排除UI代码后）
- **测试框架**: pytest + pytest-cov

### 各模块覆盖率
| 模块 | 覆盖率 |
|------|--------|
| config.py | 100% |
| scene_detector.py | 100% |
| note_manager.py | 100% |
| agent_orchestrator.py | 97.3% |
| writing_skills.py | 96.4% |
| performance_monitor.py | 90.5% |
| diagnostic_logger.py | 88.8% |
| secure_config.py | 89.0% |
| memory_manager.py | 85.1% |
| novel_agent.py | 84.7% |
| reading_manager.py | 74.5% |
| image_generator.py | 72.7% |
| ai_client.py | 72.5% |

### 代码审查结果
已完成全面代码审查，发现并修复了5个阻塞问题：
1. ✅ novel_agent.py: _diag未定义导致运行时崩溃
2. ✅ memory_manager.py: 添加线程安全保护
3. ✅ reading_manager.py: 修复路径遍历漏洞
4. ✅ secure_config.py: 修复解密回退泄露明文
5. ✅ config.py: 统一配置系统

## 部署方式

### Docker部署
```bash
docker-compose up -d
```

### 桌面版
- 支持Windows打包（PyInstaller + NSIS安装程序）
- 图形界面启动器

### 移动版
- Android APK（React + TypeScript）
- 支持DeepSeek API集成

## 配置说明

### AI模型配置
```json
{
  "api_provider": "deepseek",
  "api_key": "your-api-key",
  "api_base": "https://api.deepseek.com",
  "model": "deepseek-v4-flash"
}
```

### 支持的AI提供商
- Ollama（本地）
- OpenAI
- DeepSeek
- Claude
- 小米MiMo
- Kimi
- 自定义API

## 开发指南

### 环境要求
- Python >= 3.11
- Node.js >= 18
- Docker（可选）

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行测试
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

### 代码规范
- 使用ruff进行代码检查
- 使用mypy进行类型检查
- 行长度限制：120字符

## 更新日志

### v2.14.4 (最新)
- 修复DeepSeek API连接问题
- 优化EXP系统（基于故事内容事件/行为）
- 建立双日志系统
- 自动化打包流程

### v2.14.0
- 桌面端+手机版全面修复
- 代码审查和安全修复
- 测试覆盖率提升到87.2%

### v2.13.1
- React + TypeScript重构手机版
- 修复白屏问题
- 优化UI交互

## 联系方式

- **GitHub**: https://github.com/ATboy-web/AI_NovelWriter
- **Issues**: https://github.com/ATboy-web/AI_NovelWriter/issues

---

*文档生成时间: 2026-06-30*
