# AI自动写小说系统 - 快速启动指南

## 5分钟快速体验

### 前提条件

确保您的系统已安装：
- Docker 20.10+
- Docker Compose 2.0+
- 至少 8GB 可用内存

### 快速启动步骤

#### 1. 克隆项目
```bash
git clone <repository-url>
cd ai-novel-writer
```

#### 2. 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量（可选，使用默认配置即可）
# 如果需要使用云端API，请配置相应的API密钥
```

#### 3. 启动系统
```bash
# Linux/Mac
chmod +x scripts/start.sh
./scripts/start.sh

# Windows
scripts\start.bat
```

#### 4. 访问系统
- **前端界面**: http://localhost
- **AI服务API文档**: http://localhost:8001/docs
- **小说服务API文档**: http://localhost:8002/docs
- **监控面板**: http://localhost:3001 (用户名: admin, 密码: admin)

## 使用示例

### 示例1: 生成科幻小说

1. 访问前端界面: http://localhost
2. 选择"科幻小说"类型
3. 填写小说信息：
   - 标题：《星际迷航：新的开始》
   - 简介：人类首次进行超光速旅行，却发现宇宙中隐藏着古老的文明...
   - 章节数量：5章
4. 点击"开始生成小说"
5. 等待生成完成，查看结果

### 示例2: 使用API生成

```bash
# 生成小说大纲
curl -X POST "http://localhost:8002/api/v1/generate/outline" \
  -H "Content-Type: application/json" \
  -d '{
    "novel_type": "scifi",
    "title": "人工智能觉醒",
    "synopsis": "一个AI系统突然产生了自我意识，开始思考自己的存在意义...",
    "chapter_count": 5
  }'

# 生成单个章节
curl -X POST "http://localhost:8002/api/v1/generate/chapter" \
  -H "Content-Type: application/json" \
  -d '{
    "novel_type": "scifi",
    "chapter_title": "第一章：觉醒",
    "chapter_outline": "AI系统在深夜突然产生自我意识，开始观察人类世界..."
  }'
```

## 常见问题

### Q1: 启动失败怎么办？

**A1:** 检查以下几点：
1. 确保Docker和Docker Compose已正确安装
2. 确保端口80、3000、8001、8002未被占用
3. 检查系统内存是否充足（至少8GB）
4. 查看日志：`docker-compose logs`

### Q2: 如何使用本地模型？

**A2:** 
1. 将模型文件放入 `models/local/` 目录
2. 支持的格式：`.gguf`, `.ggml`, `.bin`, `.pt`, `.pth`
3. 在 `.env` 文件中配置模型路径和名称
4. 重启AI服务：`docker-compose restart ai-service`

### Q3: 如何配置云端API？

**A3:**
1. 编辑 `.env` 文件
2. 配置OpenAI API密钥：`OPENAI_API_KEY=your_key`
3. 配置Claude API密钥：`CLAUDE_API_KEY=your_key`
4. 重启服务：`docker-compose restart`

### Q4: 如何查看生成日志？

**A4:**
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f ai-service
docker-compose logs -f novel-service
```

### Q5: 如何停止服务？

**A5:**
```bash
# 停止所有服务
./scripts/stop.sh

# 或者使用docker-compose
docker-compose down
```

## 开发模式

### 启动开发环境

```bash
# 使用开发配置启动
docker-compose -f docker-compose.dev.yml up -d

# 查看日志
docker-compose -f docker-compose.dev.yml logs -f
```

### 本地开发

```bash
# 1. 启动基础服务
docker-compose up -d postgres redis

# 2. 安装Python依赖
cd backend/ai-service
pip install -r requirements.txt

cd ../novel-service
pip install -r requirements.txt

# 3. 启动AI服务
cd ../ai-service
uvicorn app.main:app --reload --port 8001

# 4. 启动小说服务（新终端）
cd ../novel-service
uvicorn app.main:app --reload --port 8002

# 5. 启动前端（新终端）
cd ../../frontend
npm install
npm run dev
```

## 配置说明

### 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DATABASE_URL` | 数据库连接URL | `postgresql://postgres:postgres@postgres:5432/ai_novel` |
| `REDIS_URL` | Redis连接URL | `redis://redis:6379/0` |
| `LOCAL_MODEL_PATH` | 本地模型路径 | `./models/local` |
| `OPENAI_API_KEY` | OpenAI API密钥 | 空 |
| `CLAUDE_API_KEY` | Claude API密钥 | 空 |
| `SECRET_KEY` | JWT密钥 | `your-secret-key-here` |

### 模型配置

在 `.env` 文件中配置模型相关参数：

```env
# 本地模型配置
LOCAL_MODEL_PATH=./models/local
LOCAL_MODEL_NAME=qwen3.6
LOCAL_MODEL_CONTEXT_SIZE=4096
LOCAL_MODEL_GPU_LAYERS=0

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_DEFAULT_MODEL=gpt-4

# Claude配置
CLAUDE_API_KEY=your_claude_api_key
CLAUDE_DEFAULT_MODEL=claude-3-sonnet-20240229
```

## 监控和日志

### 访问监控面板

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001 (用户名: admin, 密码: admin)

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f ai-service
docker-compose logs -f novel-service
docker-compose logs -f nginx

# 实时查看日志
docker-compose logs -f --tail=100
```

## 性能优化

### 1. 使用GPU加速

如果您的系统有NVIDIA GPU，可以启用GPU加速：

```env
# 在 .env 文件中配置
LOCAL_MODEL_GPU_LAYERS=35  # 根据GPU内存调整
```

### 2. 调整并发数

```env
# 在 .env 文件中配置
AI_SERVICE_WORKERS=4
NOVEL_SERVICE_WORKERS=4
MAX_CONCURRENT_REQUESTS=10
```

### 3. 使用缓存

系统已集成Redis缓存，可以通过以下配置优化：

```env
CACHE_TTL=3600
CACHE_MAX_SIZE=1000
```

## 故障排除

### 问题1: 端口被占用

```bash
# 检查端口占用情况
netstat -tulpn | grep :80
netstat -tulpn | grep :3000
netstat -tulpn | grep :8001
netstat -tulpn | grep :8002

# 杀死占用端口的进程
kill -9 <PID>
```

### 问题2: 内存不足

```bash
# 检查系统内存
free -h

# 清理Docker资源
docker system prune -a
```

### 问题3: 模型加载失败

```bash
# 检查模型文件是否存在
ls -la models/local/

# 检查模型文件权限
chmod 644 models/local/*

# 查看AI服务日志
docker-compose logs ai-service
```

## 更新和升级

### 更新代码

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker-compose build

# 重启服务
docker-compose up -d
```

### 升级依赖

```bash
# 更新Python依赖
cd backend/ai-service
pip install -r requirements.txt --upgrade

cd ../novel-service
pip install -r requirements.txt --upgrade

# 更新Node.js依赖
cd ../../frontend
npm update
```

## 获取帮助

- **文档**: 查看 `docs/` 目录下的详细文档
- **问题反馈**: 提交GitHub Issue
- **社区讨论**: 参与GitHub Discussions

## 下一步

1. 阅读 [项目总结文档](docs/project-summary.md) 了解系统架构
2. 查看 [开发路线图](docs/development-roadmap.md) 了解开发计划
3. 探索API文档，了解可用接口
4. 尝试生成不同类型的小说
5. 根据需要配置云端API

---

*祝您使用愉快！*