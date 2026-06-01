# AI自动写小说系统

一个完整的AI小说生成产品，支持多种小说类型、本地模型和云端API集成。

## 系统架构

采用微服务架构，分为5个核心服务：

1. **前端服务** (Node.js + Express)
   - 用户界面（Web/移动端）
   - API路由和负载均衡
   - 静态资源服务

2. **用户认证服务** (Python + FastAPI)
   - 用户注册/登录
   - JWT令牌管理
   - 权限控制

3. **小说生成服务** (Python + FastAPI)
   - 多类型小说生成（科幻、悬疑、言情等）
   - 章节管理和编辑
   - 内容质量评估

4. **AI模型服务** (Python + FastAPI)
   - 本地模型集成（llama.cpp）
   - 云端API调用（GPT/Claude）
   - 模型负载均衡

5. **支付服务** (Python + FastAPI)
   - 用户订阅管理
   - 付费功能控制
   - 支付集成

## 技术栈

### 后端
- **Python 3.13** + FastAPI
- **Node.js 22** + Express
- **PostgreSQL** - 主数据库
- **Redis** - 缓存和会话存储
- **Docker** - 容器化部署

### AI模型
- **本地模型**: llama.cpp + Qwen3.6
- **云端API**: OpenAI GPT-4, Claude API
- **模型管理**: 自定义模型路由和负载均衡

### 前端
- **React/Vue.js** - 现代前端框架
- **TypeScript** - 类型安全
- **Tailwind CSS** - 样式框架

## 项目结构

```
ai-novel-writer/
├── frontend/                    # 前端服务
│   ├── src/
│   │   ├── components/         # UI组件
│   │   ├── pages/              # 页面组件
│   │   ├── services/           # API调用服务
│   │   ├── store/              # 状态管理
│   │   └── utils/              # 工具函数
│   ├── public/                 # 静态资源
│   ├── package.json
│   └── Dockerfile
├── backend/                     # 后端服务
│   ├── auth-service/           # 用户认证服务
│   │   ├── app/
│   │   │   ├── api/            # API路由
│   │   │   ├── core/           # 核心配置
│   │   │   ├── models/         # 数据模型
│   │   │   └── services/       # 业务逻辑
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── novel-service/          # 小说生成服务
│   │   ├── app/
│   │   │   ├── api/            # API路由
│   │   │   ├── generators/     # 小说生成器
│   │   │   ├── models/         # 数据模型
│   │   │   └── services/       # 业务逻辑
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── ai-service/             # AI模型服务
│   │   ├── app/
│   │   │   ├── api/            # API路由
│   │   │   ├── models/         # 模型管理
│   │   │   ├── inference/      # 推理引擎
│   │   │   └── services/       # 业务逻辑
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── payment-service/        # 支付服务
│       ├── app/
│       │   ├── api/            # API路由
│       │   ├── models/         # 数据模型
│       │   └── services/       # 业务逻辑
│       ├── requirements.txt
│       └── Dockerfile
├── shared/                      # 共享库
│   ├── python/                 # Python共享模块
│   │   ├── config/             # 配置管理
│   │   ├── utils/              # 工具函数
│   │   └── exceptions/         # 自定义异常
│   └── types/                  # 类型定义
├── models/                      # AI模型存储
│   ├── local/                  # 本地模型
│   └── configs/                # 模型配置
├── docs/                        # 项目文档
├── scripts/                     # 部署脚本
├── docker-compose.yml          # Docker编排
└── README.md
```

## 核心功能模块

### 1. 小说生成引擎
- **类型支持**: 科幻、悬疑、言情、奇幻、都市等
- **生成模式**: 
  - 全自动生成（大纲→章节→全文）
  - 半自动生成（用户干预关键情节）
  - 模板生成（基于预设模板）
- **质量控制**: 
  - 情节连贯性检查
  - 人物一致性维护
  - 逻辑合理性验证

### 2. 用户系统
- **角色管理**: 
  - 普通用户（免费额度）
  - VIP用户（付费功能）
  - 管理员（系统管理）
- **权限控制**: 
  - 功能权限（生成、编辑、导出）
  - 数据权限（个人作品、共享模板）

### 3. 付费系统
- **订阅模式**: 
  - 免费版（基础功能）
  - 基础版（更多生成次数）
  - 专业版（高级功能）
- **支付集成**: 
  - 支付宝/微信支付
  - 订阅管理
  - 发票系统

### 4. 内容管理
- **作品管理**: 
  - 创建、编辑、删除
  - 版本控制
  - 协作编辑
- **导出功能**: 
  - 多格式导出（TXT、PDF、EPUB）
  - 打印排版
  - 分享链接

## 开发路线图

### 阶段1: MVP原型 (4-6周)
- [x] 基础架构搭建
- [ ] 简单小说生成（单类型）
- [ ] 基础用户系统
- [ ] 命令行界面

### 阶段2: 功能扩展 (6-8周)
- [ ] 多类型小说支持
- [ ] Web界面开发
- [ ] 本地模型集成
- [ ] 基础付费功能

### 阶段3: 产品完善 (8-10周)
- [ ] 完整用户系统
- [ ] 高级生成功能
- [ ] 支付系统集成
- [ ] 性能优化

### 阶段4: 生产部署 (4-6周)
- [ ] Docker容器化
- [ ] CI/CD流水线
- [ ] 监控和日志
- [ ] 安全加固

## 快速开始

### 环境要求
- Python 3.13+
- Node.js 22+
- PostgreSQL 15+
- Redis 7+
- Docker (可选)

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ai-novel-writer
```

2. **安装依赖**
```bash
# Python依赖
cd backend
pip install -r requirements.txt

# Node.js依赖
cd ../frontend
npm install
```

3. **配置环境**
```bash
# 复制配置文件
cp .env.example .env

# 编辑配置
vim .env
```

4. **启动服务**
```bash
# 开发模式
docker-compose up -d

# 或手动启动
cd backend && python -m uvicorn app.main:app --reload
cd ../frontend && npm run dev
```

## 配置说明

### 环境变量
```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/ai_novel
REDIS_URL=redis://localhost:6379/0

# AI模型配置
LOCAL_MODEL_PATH=./models/local
OPENAI_API_KEY=your_openai_key
CLAUDE_API_KEY=your_claude_key

# 支付配置
ALIPAY_APP_ID=your_alipay_appid
WECHAT_PAY_APPID=your_wechat_appid

# 安全配置
SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256
```

## 部署指南

### Docker部署
```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 生产部署
```bash
# 使用Nginx反向代理
# 配置SSL证书
# 设置监控告警
```

## 贡献指南

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 联系方式

- 项目维护者: [Your Name]
- 邮箱: [your-email@example.com]
- 项目链接: [GitHub Repository]

## 致谢

- 感谢所有贡献者
- 感谢开源社区的支持
- 特别感谢AI模型开发者