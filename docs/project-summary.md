# AI自动写小说系统 - 项目总结

## 项目概述

本项目是一个完整的AI小说生成产品，采用微服务架构，支持多种小说类型（科幻、悬疑、言情、奇幻、都市），集成本地模型和云端API，包含用户系统、付费功能、多角色管理等完整产品特性。

## 系统架构

### 分层架构

```
┌─────────────────────────────────────┐
│         前端用户界面层              │
│    (React/Vue + TypeScript)         │
├─────────────────────────────────────┤
│         API网关层                   │
│    (Node.js + Express)              │
├─────────────────────────────────────┤
│         业务逻辑层                  │
│    (Python + FastAPI)               │
├─────────────────────────────────────┤
│         AI模型层                    │
│    (本地模型 + 云端API)            │
├─────────────────────────────────────┤
│         数据存储层                  │
│    (PostgreSQL + Redis)             │
└─────────────────────────────────────┘
```

### 核心服务

1. **AI模型服务** (端口: 8001)
   - 负责AI模型的加载、管理和推理
   - 支持本地模型（llama.cpp）和云端API（GPT/Claude）
   - 提供统一的推理接口

2. **小说生成服务** (端口: 8002)
   - 负责小说生成的核心业务逻辑
   - 支持多种小说类型的生成
   - 提供大纲、章节、人物等生成功能

3. **前端服务** (端口: 3000)
   - 提供用户界面
   - 支持小说生成、编辑、导出等功能
   - 响应式设计，支持多端访问

4. **Nginx反向代理** (端口: 80)
   - 统一入口，路由分发
   - 负载均衡，SSL终端
   - 静态资源缓存

## 功能特性

### 1. 多类型小说生成

| 类型 | 特点 | 适用场景 |
|------|------|----------|
| 科幻小说 | 未来科技、太空探索、人工智能 | 科幻爱好者 |
| 悬疑推理 | 犯罪谜题、逻辑推理、悬疑氛围 | 推理爱好者 |
| 言情小说 | 爱情故事、情感纠葛、人物成长 | 言情爱好者 |
| 奇幻小说 | 魔法系统、异世界、史诗冒险 | 奇幻爱好者 |
| 都市小说 | 现实生活、职场故事、社会现象 | 都市爱好者 |

### 2. 智能生成引擎

- **大纲生成**: 自动生成小说大纲，包含章节结构、情节发展
- **章节生成**: 根据大纲自动生成章节内容
- **人物生成**: 自动创建人物设定，包括性格、背景、关系
- **风格分析**: 分析文本风格，提供写作建议

### 3. 质量控制系统

- **连贯性检查**: 检查情节、人物、时间线的连贯性
- **逻辑验证**: 验证故事逻辑的合理性
- **风格一致性**: 确保写作风格的一致性
- **内容优化**: 优化语言表达、情节设计

### 4. 用户系统

- **角色管理**: 普通用户、VIP用户、管理员
- **权限控制**: 功能权限、数据权限
- **个人中心**: 作品管理、个人设置
- **订阅管理**: 免费版、基础版、专业版

### 5. 付费系统

- **订阅模式**: 按月/按年订阅
- **支付集成**: 支付宝、微信支付
- **发票管理**: 电子发票生成
- **营销活动**: 优惠券、促销活动

## 技术栈

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.13 | 主要后端语言 |
| FastAPI | 0.104.1 | Web框架 |
| Node.js | 22 | 前端服务和API网关 |
| Express | 4.18.2 | Node.js Web框架 |
| PostgreSQL | 15 | 主数据库 |
| Redis | 7 | 缓存和会话存储 |

### AI模型技术

| 技术 | 用途 |
|------|------|
| llama.cpp | 本地模型推理 |
| Qwen3.6 | 本地部署的大语言模型 |
| OpenAI GPT-4 | 云端AI模型 |
| Claude API | 云端AI模型 |

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | 前端框架 |
| TypeScript | 5.0 | 类型安全 |
| Tailwind CSS | 3.0 | 样式框架 |
| Vite | 5.0 | 构建工具 |

### 部署技术

| 技术 | 用途 |
|------|------|
| Docker | 容器化 |
| Docker Compose | 容器编排 |
| Nginx | 反向代理 |
| Prometheus | 监控 |
| Grafana | 监控面板 |

## 项目结构

```
ai-novel-writer/
├── frontend/                    # 前端服务
│   ├── src/                    # 源代码
│   ├── public/                 # 静态资源
│   ├── package.json           # 依赖配置
│   └── Dockerfile             # Docker配置
├── backend/                     # 后端服务
│   ├── ai-service/            # AI模型服务
│   ├── novel-service/         # 小说生成服务
│   ├── auth-service/          # 用户认证服务
│   └── payment-service/       # 支付服务
├── shared/                      # 共享库
├── models/                      # AI模型存储
├── docs/                        # 项目文档
├── scripts/                     # 部署脚本
├── nginx/                       # Nginx配置
├── monitoring/                  # 监控配置
├── docker-compose.yml          # Docker编排
└── README.md                   # 项目说明
```

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 8GB 内存
- 至少 20GB 磁盘空间

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ai-novel-writer
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

3. **启动系统**
```bash
# Linux/Mac
chmod +x scripts/start.sh
./scripts/start.sh

# Windows
scripts\start.bat
```

4. **访问系统**
- 前端界面: http://localhost
- AI服务API: http://localhost:8001
- 小说服务API: http://localhost:8002
- 监控面板: http://localhost:3001

### 开发模式

```bash
# 启动开发环境
docker-compose -f docker-compose.dev.yml up -d

# 查看日志
docker-compose logs -f

# 停止服务
./scripts/stop.sh
```

## API接口

### AI模型服务 (端口: 8001)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate/chapter` | POST | 生成章节内容 |
| `/api/v1/generate/outline` | POST | 生成小说大纲 |
| `/api/v1/generate/character` | POST | 生成人物设定 |
| `/api/v1/analyze/style` | POST | 分析文本风格 |
| `/api/v1/models` | GET | 获取可用模型 |
| `/api/v1/health` | GET | 健康检查 |

### 小说生成服务 (端口: 8002)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate/novel` | POST | 生成完整小说 |
| `/api/v1/generate/chapter` | POST | 生成单个章节 |
| `/api/v1/generate/outline` | POST | 生成小说大纲 |
| `/api/v1/generate/character` | POST | 生成人物设定 |
| `/api/v1/novel-types` | GET | 获取支持的小说类型 |
| `/api/v1/health` | GET | 健康检查 |

## 配置说明

### 环境变量配置

```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/ai_novel
REDIS_URL=redis://localhost:6379/0

# AI模型配置
LOCAL_MODEL_PATH=./models/local
OPENAI_API_KEY=your_openai_key
CLAUDE_API_KEY=your_claude_key

# 安全配置
SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256

# 支付配置
ALIPAY_APP_ID=your_alipay_appid
WECHAT_PAY_APPID=your_wechat_appid
```

### 模型配置

```yaml
# 本地模型配置
local_model:
  path: ./models/local
  name: qwen3.6
  context_size: 4096
  gpu_layers: 0

# 云端模型配置
cloud_models:
  openai:
    api_key: ${OPENAI_API_KEY}
    default_model: gpt-4
    max_tokens: 4096
  claude:
    api_key: ${CLAUDE_API_KEY}
    default_model: claude-3-sonnet-20240229
    max_tokens: 4096
```

## 部署指南

### 生产环境部署

1. **服务器要求**
   - CPU: 8核以上
   - 内存: 32GB以上
   - 磁盘: 100GB以上 SSD
   - 网络: 稳定的公网IP

2. **域名和SSL**
```bash
# 配置域名解析
# 申请SSL证书
# 配置Nginx SSL
```

3. **部署步骤**
```bash
# 1. 克隆代码
git clone <repository-url>
cd ai-novel-writer

# 2. 配置环境变量
cp .env.example .env
vim .env

# 3. 启动服务
docker-compose -f docker-compose.prod.yml up -d

# 4. 配置反向代理
# 编辑 nginx/nginx.conf

# 5. 启动监控
docker-compose up -d prometheus grafana
```

### 监控和告警

- **Prometheus**: 指标收集和存储
- **Grafana**: 可视化监控面板
- **告警规则**: 服务可用性、性能指标、错误率

## 开发指南

### 开发环境搭建

```bash
# 1. 安装依赖
cd backend/ai-service
pip install -r requirements.txt

cd ../novel-service
pip install -r requirements.txt

cd ../../frontend
npm install

# 2. 启动开发服务
# AI服务
cd ../backend/ai-service
uvicorn app.main:app --reload --port 8001

# 小说服务
cd ../novel-service
uvicorn app.main:app --reload --port 8002

# 前端
cd ../../frontend
npm run dev
```

### 代码规范

- **Python**: PEP8, Black格式化
- **JavaScript/TypeScript**: ESLint, Prettier
- **Git**: Conventional Commits

### 测试

```bash
# Python测试
cd backend/ai-service
pytest

# 前端测试
cd frontend
npm test
# AI自动写小说系统 - 项目总结

## 项目概述

本项目是一个完整的AI小说生成产品，采用微服务架构，支持多种小说类型（科幻、悬疑、言情、奇幻、都市），集成本地模型和云端API，包含用户系统、付费功能、多角色管理等完整产品特性。

## 系统架构

### 分层架构

```
┌─────────────────────────────────────┐
│         前端用户界面层              │
│    (React/Vue + TypeScript)         │
├─────────────────────────────────────┤
│         API网关层                   │
│    (Node.js + Express)              │
├─────────────────────────────────────┤
│         业务逻辑层                  │
│    (Python + FastAPI)               │
├─────────────────────────────────────┤
│         AI模型层                    │
│    (本地模型 + 云端API)            │
├─────────────────────────────────────┤
│         数据存储层                  │
│    (PostgreSQL + Redis)             │
└─────────────────────────────────────┘
```

### 核心服务

1. **AI模型服务** (端口: 8001)
   - 负责AI模型的加载、管理和推理
   - 支持本地模型（llama.cpp）和云端API（GPT/Claude）
   - 提供统一的推理接口

2. **小说生成服务** (端口: 8002)
   - 负责小说生成的核心业务逻辑
   - 支持多种小说类型的生成
   - 提供大纲、章节、人物等生成功能

3. **前端服务** (端口: 3000)
   - 提供用户界面
   - 支持小说生成、编辑、导出等功能
   - 响应式设计，支持多端访问

4. **Nginx反向代理** (端口: 80)
   - 统一入口，路由分发
   - 负载均衡，SSL终端
   - 静态资源缓存

## 功能特性

### 1. 多类型小说生成

| 类型 | 特点 | 适用场景 |
|------|------|----------|
| 科幻小说 | 未来科技、太空探索、人工智能 | 科幻爱好者 |
| 悬疑推理 | 犯罪谜题、逻辑推理、悬疑氛围 | 推理爱好者 |
| 言情小说 | 爱情故事、情感纠葛、人物成长 | 言情爱好者 |
| 奇幻小说 | 魔法系统、异世界、史诗冒险 | 奇幻爱好者 |
| 都市小说 | 现实生活、职场故事、社会现象 | 都市爱好者 |

### 2. 智能生成引擎

- **大纲生成**: 自动生成小说大纲，包含章节结构、情节发展
- **章节生成**: 根据大纲自动生成章节内容
- **人物生成**: 自动创建人物设定，包括性格、背景、关系
- **风格分析**: 分析文本风格，提供写作建议

### 3. 质量控制系统

- **连贯性检查**: 检查情节、人物、时间线的连贯性
- **逻辑验证**: 验证故事逻辑的合理性
- **风格一致性**: 确保写作风格的一致性
- **内容优化**: 优化语言表达、情节设计

### 4. 用户系统

- **角色管理**: 普通用户、VIP用户、管理员
- **权限控制**: 功能权限、数据权限
- **个人中心**: 作品管理、个人设置
- **订阅管理**: 免费版、基础版、专业版

### 5. 付费系统

- **订阅模式**: 按月/按年订阅
- **支付集成**: 支付宝、微信支付
- **发票管理**: 电子发票生成
- **营销活动**: 优惠券、促销活动

## 技术栈

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.13 | 主要后端语言 |
| FastAPI | 0.104.1 | Web框架 |
| Node.js | 22 | 前端服务和API网关 |
| Express | 4.18.2 | Node.js Web框架 |
| PostgreSQL | 15 | 主数据库 |
| Redis | 7 | 缓存和会话存储 |

### AI模型技术

| 技术 | 用途 |
|------|------|
| llama.cpp | 本地模型推理 |
| Qwen3.6 | 本地部署的大语言模型 |
| OpenAI GPT-4 | 云端AI模型 |
| Claude API | 云端AI模型 |

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | 前端框架 |
| TypeScript | 5.0 | 类型安全 |
| Tailwind CSS | 3.0 | 样式框架 |
| Vite | 5.0 | 构建工具 |

### 部署技术

| 技术 | 用途 |
|------|------|
| Docker | 容器化 |
| Docker Compose | 容器编排 |
| Nginx | 反向代理 |
| Prometheus | 监控 |
| Grafana | 监控面板 |

## 项目结构

```
ai-novel-writer/
├── frontend/                    # 前端服务
│   ├── src/                    # 源代码
│   ├── public/                 # 静态资源
│   ├── package.json           # 依赖配置
│   └── Dockerfile             # Docker配置
├── backend/                     # 后端服务
│   ├── ai-service/            # AI模型服务
│   ├── novel-service/         # 小说生成服务
│   ├── auth-service/          # 用户认证服务
│   └── payment-service/       # 支付服务
├── shared/                      # 共享库
├── models/                      # AI模型存储
├── docs/                        # 项目文档
├── scripts/                     # 部署脚本
├── nginx/                       # Nginx配置
├── monitoring/                  # 监控配置
├── docker-compose.yml          # Docker编排
└── README.md                   # 项目说明
```

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 8GB 内存
- 至少 20GB 磁盘空间

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ai-novel-writer
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

3. **启动系统**
```bash
# Linux/Mac
chmod +x scripts/start.sh
./scripts/start.sh

# Windows
scripts\start.bat
```

4. **访问系统**
- 前端界面: http://localhost
- AI服务API: http://localhost:8001
- 小说服务API: http://localhost:8002
- 监控面板: http://localhost:3001

### 开发模式

```bash
# 启动开发环境
docker-compose -f docker-compose.dev.yml up -d

# 查看日志
docker-compose logs -f

# 停止服务
./scripts/stop.sh
```

## API接口

### AI模型服务 (端口: 8001)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate/chapter` | POST | 生成章节内容 |
| `/api/v1/generate/outline` | POST | 生成小说大纲 |
| `/api/v1/generate/character` | POST | 生成人物设定 |
| `/api/v1/analyze/style` | POST | 分析文本风格 |
| `/api/v1/models` | GET | 获取可用模型 |
| `/api/v1/health` | GET | 健康检查 |

### 小说生成服务 (端口: 8002)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate/novel` | POST | 生成完整小说 |
| `/api/v1/generate/chapter` | POST | 生成单个章节 |
| `/api/v1/generate/outline` | POST | 生成小说大纲 |
| `/api/v1/generate/character` | POST | 生成人物设定 |
| `/api/v1/novel-types` | GET | 获取支持的小说类型 |
| `/api/v1/health` | GET | 健康检查 |

## 配置说明

### 环境变量配置

```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/ai_novel
REDIS_URL=redis://localhost:6379/0

# AI模型配置
LOCAL_MODEL_PATH=./models/local
OPENAI_API_KEY=your_openai_key
CLAUDE_API_KEY=your_claude_key

# 安全配置
SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256

# 支付配置
ALIPAY_APP_ID=your_alipay_appid
WECHAT_PAY_APPID=your_wechat_appid
```

### 模型配置

```yaml
# 本地模型配置
local_model:
  path: ./models/local
  name: qwen3.6
  context_size: 4096
  gpu_layers: 0

# 云端模型配置
cloud_models:
  openai:
    api_key: ${OPENAI_API_KEY}
    default_model: gpt-4
    max_tokens: 4096
  claude:
    api_key: ${CLAUDE_API_KEY}
    default_model: claude-3-sonnet-20240229
    max_tokens: 4096
```

## 部署指南

### 生产环境部署

1. **服务器要求**
   - CPU: 8核以上
   - 内存: 32GB以上
   - 磁盘: 100GB以上 SSD
   - 网络: 稳定的公网IP

2. **域名和SSL**
```bash
# 配置域名解析
# 申请SSL证书
# 配置Nginx SSL
```

3. **部署步骤**
```bash
# 1. 克隆代码
git clone <repository-url>
cd ai-novel-writer

# 2. 配置环境变量
cp .env.example .env
vim .env

# 3. 启动服务
docker-compose -f docker-compose.prod.yml up -d

# 4. 配置反向代理
# 编辑 nginx/nginx.conf

# 5. 启动监控
docker-compose up -d prometheus grafana
```

### 监控和告警

- **Prometheus**: 指标收集和存储
- **Grafana**: 可视化监控面板
- **告警规则**: 服务可用性、性能指标、错误率

## 开发指南

### 开发环境搭建

```bash
# 1. 安装依赖
cd backend/ai-service
pip install -r requirements.txt

cd ../novel-service
pip install -r requirements.txt

cd ../../frontend
npm install

# 2. 启动开发服务
# AI服务
cd ../backend/ai-service
uvicorn app.main:app --reload --port 8001

# 小说服务
cd ../novel-service
uvicorn app.main:app --reload --port 8002

# 前端
cd ../../frontend
npm run dev
```

### 代码规范

- **Python**: PEP8, Black格式化
- **JavaScript/TypeScript**: ESLint, Prettier
- **Git**: Conventional Commits

### 测试

```bash
# Python测试
cd backend/ai-service
pytest

# 前端测试
cd frontend
npm test
```

## 常见问题

### Q1: 如何添加新的小说类型？

A1: 在 `backend/novel-service/app/generators/novel_generator.py` 中添加新的生成器类，然后在工厂类中注册。

### Q2: 如何切换AI模型？

A2: 在生成请求中指定 `model_type` 参数，支持 `local`、`openai`、`claude`。

### Q3: 如何优化生成质量？

A3: 调整以下参数：
- `temperature`: 控制生成随机性（0.1-1.0）
- `top_p`: 控制采样范围（0.1-1.0）
- `max_tokens`: 控制生成长度

### Q4: 如何扩展用户系统？

A4: 在 `backend/auth-service` 中添加新的用户功能，如社交登录、多因素认证等。

## 性能优化

### 数据库优化

- 添加适当的索引
- 使用连接池
- 定期清理过期数据

### 缓存策略

- Redis缓存热点数据
- 本地缓存模型结果
- CDN加速静态资源

### 并发处理

- 异步处理生成任务
- 消息队列削峰
- 负载均衡分发请求

## 安全考虑

### 数据安全

- 用户密码加密存储
- 敏感数据加密传输
- 定期备份数据

### API安全

- JWT令牌认证
- 请求频率限制
- 输入参数验证

### 系统安全

- 定期更新依赖
- 安全漏洞扫描
- 访问日志审计

## 扩展计划

### 短期扩展

- [ ] 添加更多小说类型
- [ ] 优化生成质量
- [ ] 完善用户系统
- [ ] 添加移动端支持

### 中期扩展

- [ ] 支持多语言
- [ ] 添加协作功能
- [ ] 集成更多AI模型
- [ ] 开发API开放平台

### 长期扩展

- [ ] 建立创作者生态
- [ ] 开发元宇宙应用
- [ ] 实现AI辅助创作
- [ ] 探索商业化模式

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 许可证

本项目采用MIT许可证。

## 联系方式

- 项目维护者: [待定]
- 邮箱: [待定]
- 项目链接: [GitHub Repository]

## 致谢

感谢所有为这个项目做出贡献的开发者和研究人员。