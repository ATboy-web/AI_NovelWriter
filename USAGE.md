# AI自动写小说系统 - 使用说明

## 快速开始

### 1. 启动系统

```bash
# 进入项目目录
cd ai-novel-writer

# 启动系统（Linux/Mac）
chmod +x scripts/start.sh
./scripts/start.sh

# 启动系统（Windows）
scripts\start.bat
```

### 2. 访问系统

启动完成后，您可以通过以下地址访问系统：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | http://localhost | 主要用户界面 |
| AI服务API | http://localhost:8001 | AI模型服务 |
| 小说服务API | http://localhost:8002 | 小说生成服务 |
| 监控面板 | http://localhost:3001 | Grafana监控 |
| API文档 | http://localhost:8001/docs | AI服务API文档 |
| API文档 | http://localhost:8002/docs | 小说服务API文档 |

## 功能使用指南

### 1. 生成小说

#### 通过Web界面生成

1. 访问 http://localhost
2. 选择小说类型（科幻、悬疑、言情、奇幻、都市）
3. 填写小说标题和简介
4. 选择章节数量和AI模型
5. 点击"开始生成小说"
6. 等待生成完成，查看结果

#### 通过API生成

```bash
# 生成完整小说
curl -X POST "http://localhost:8002/api/v1/generate/novel" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "人工智能觉醒",
    "synopsis": "一个AI系统突然产生了自我意识，开始思考自己的存在意义...",
    "novel_type": "scifi",
    "chapter_count": 5
  }'

# 生成单个章节
curl -X POST "http://localhost:8002/api/v1/generate/chapter" \
  -H "Content-Type: application/json" \
  -d '{
    "novel_type": "scifi",
    "chapter_title": "第一章：觉醒",
    "chapter_outline": "AI系统在深夜突然产生自我意识..."
  }'
```

### 2. 生成人物设定

```bash
# 生成人物设定
curl -X POST "http://localhost:8002/api/v1/generate/character" \
  -H "Content-Type: application/json" \
  -d '{
    "novel_type": "scifi",
    "character_name": "李博士",
    "character_role": "主角",
    "character_traits": ["聪明", "专注", "有责任心"]
  }'
```

### 3. 生成小说大纲

```bash
# 生成小说大纲
curl -X POST "http://localhost:8002/api/v1/generate/outline" \
  -H "Content-Type: application/json" \
  -d '{
    "novel_type": "scifi",
    "title": "人工智能觉醒",
    "synopsis": "一个AI系统突然产生了自我意识...",
    "chapter_count": 10
  }'
```

### 4. 分析文本风格

```bash
# 分析文本风格
curl -X POST "http://localhost:8002/api/v1/analyze/style" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "在未来的地球，人工智能已经深度融入人类社会...",
    "novel_type": "scifi"
  }'
```

## 系统管理

### 查看服务状态

```bash
# 查看所有服务状态
docker-compose ps

# 查看特定服务日志
docker-compose logs -f ai-service
docker-compose logs -f novel-service
```

### 停止系统

```bash
# 停止所有服务
./scripts/stop.sh

# 或者使用docker-compose
docker-compose down
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart ai-service
docker-compose restart novel-service
```

## 配置说明

### 环境变量配置

编辑 `.env` 文件来配置系统：

```env
# 数据库配置
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ai_novel
REDIS_URL=redis://redis:6379/0

# AI模型配置
LOCAL_MODEL_PATH=./models/local
OPENAI_API_KEY=your_openai_key
CLAUDE_API_KEY=your_claude_key

# 安全配置
SECRET_KEY=your_secret_key
```

### 模型配置

#### 使用本地模型

1. 将模型文件放入 `models/local/` 目录
2. 支持的格式：`.gguf`, `.ggml`, `.bin`, `.pt`, `.pth`
3. 在 `.env` 文件中配置模型名称：

```env
LOCAL_MODEL_NAME=qwen3.6
LOCAL_MODEL_CONTEXT_SIZE=4096
LOCAL_MODEL_GPU_LAYERS=0
```

#### 使用云端API

1. 在 `.env` 文件中配置API密钥：

```env
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_DEFAULT_MODEL=gpt-4

# Claude配置
CLAUDE_API_KEY=your_claude_api_key
CLAUDE_DEFAULT_MODEL=claude-3-sonnet-20240229
```

## 开发指南

### 本地开发环境

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

### 运行测试

```bash
# 运行系统测试
python scripts/test.py

# 运行演示脚本
python scripts/demo.py
```

### 查看API文档

- AI服务API文档: http://localhost:8001/docs
- 小说服务API文档: http://localhost:8002/docs

## 故障排除

### 常见问题

#### 1. 端口被占用

```bash
# 检查端口占用
netstat -tulpn | grep :80
netstat -tulpn | grep :3000
netstat -tulpn | grep :8001
netstat -tulpn | grep :8002

# 杀死占用端口的进程
kill -9 <PID>
```

#### 2. 内存不足

```bash
# 检查系统内存
free -h

# 清理Docker资源
docker system prune -a
```

#### 3. 模型加载失败

```bash
# 检查模型文件
ls -la models/local/

# 检查模型文件权限
chmod 644 models/local/*

# 查看AI服务日志
docker-compose logs ai-service
```

#### 4. 服务启动失败

```bash
# 查看所有服务日志
docker-compose logs

# 重新构建镜像
docker-compose build --no-cache

# 重新启动服务
docker-compose up -d
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

# 实时查看日志
docker-compose logs -f --tail=100
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