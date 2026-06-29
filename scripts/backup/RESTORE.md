# 数据恢复手册

本文档描述了 AI Novel Writer 系统的数据恢复流程。

## 目录

- [恢复前准备](#恢复前准备)
- [PostgreSQL恢复](#postgresql恢复)
- [Redis恢复](#redis恢复)
- [完整系统恢复](#完整系统恢复)
- [常见问题](#常见问题)

---

## 恢复前准备

### 1. 确认备份文件

```bash
# 列出所有备份
./scripts/backup/backup-scheduler.sh status

# 验证备份完整性
./scripts/backup/backup-postgres.sh verify /path/to/backup.sql.gz
./scripts/backup/backup-redis.sh verify /path/to/backup.rdb.gz
```

### 2. 停止相关服务

```bash
# 停止所有服务
docker-compose down

# 或只停止特定服务
docker-compose stop ai-service novel-service
```

### 3. 确认磁盘空间

```bash
# 检查磁盘空间
df -h

# 确保有足够的空间用于恢复
# 建议至少有备份文件大小的3倍空间
```

---

## PostgreSQL恢复

### 方法1: 使用备份脚本恢复

```bash
# 恢复指定备份
./scripts/backup/backup-postgres.sh restore /path/to/backup.sql.gz
```

### 方法2: 手动恢复

```bash
# 1. 启动PostgreSQL服务
docker-compose up -d postgres

# 2. 等待服务就绪
docker-compose exec postgres pg_isready

# 3. 恢复数据库
gunzip -c /path/to/backup.sql.gz | \
    docker-compose exec -T postgres pg_restore \
    -U postgres -d ai_novel \
    --clean --if-exists

# 4. 验证恢复
docker-compose exec postgres psql -U postgres -d ai_novel -c "\dt"
```

### 方法3: 从S3恢复

```bash
# 1. 从S3下载备份
aws s3 cp s3://your-bucket/postgres/backup.sql.gz /tmp/backup.sql.gz

# 2. 验证备份
./scripts/backup/backup-postgres.sh verify /tmp/backup.sql.gz

# 3. 恢复备份
./scripts/backup/backup-postgres.sh restore /tmp/backup.sql.gz
```

### 恢复特定表

```bash
# 只恢复特定表
gunzip -c /path/to/backup.sql.gz | \
    docker-compose exec -T postgres pg_restore \
    -U postgres -d ai_novel \
    --clean --if-exists \
    -t table_name
```

### 恢复到特定时间点 (PITR)

如果配置了WAL归档，可以恢复到特定时间点：

```bash
# 1. 停止PostgreSQL
docker-compose stop postgres

# 2. 恢复基础备份
gunzip -c /path/to/base-backup.sql.gz | \
    docker-compose exec -T postgres pg_restore \
    -U postgres -d ai_novel

# 3. 配置恢复
docker-compose exec postgres bash -c "
echo 'restore_command = '\''cp /archive/%f %p'\''' >> /var/lib/postgresql/data/postgresql.conf
echo 'recovery_target_time = '\''2026-06-29 12:00:00'\''' >> /var/lib/postgresql/data/postgresql.conf
"

# 4. 启动PostgreSQL
docker-compose start postgres
```

---

## Redis恢复

### 方法1: 使用备份脚本恢复

```bash
# 恢复指定备份
./scripts/backup/backup-redis.sh restore /path/to/backup.rdb.gz
```

### 方法2: 手动恢复

```bash
# 1. 停止Redis
docker-compose stop redis

# 2. 获取Redis数据目录
REDIS_DIR=$(docker-compose exec redis redis-cli CONFIG GET dir | tail -1)

# 3. 备份当前RDB文件
docker-compose exec redis cp ${REDIS_DIR}/dump.rdb ${REDIS_DIR}/dump.rdb.bak

# 4. 恢复备份文件
gunzip -c /path/to/backup.rdb.gz > /tmp/dump.rdb
docker cp /tmp/dump.rdb ai-novel-redis:${REDIS_DIR}/dump.rdb

# 5. 重启Redis
docker-compose restart redis

# 6. 验证恢复
docker-compose exec redis redis-cli DBSIZE
```

### 方法3: 从S3恢复

```bash
# 1. 从S3下载备份
aws s3 cp s3://your-bucket/redis/backup.rdb.gz /tmp/backup.rdb.gz

# 2. 验证备份
./scripts/backup/backup-redis.sh verify /tmp/backup.rdb.gz

# 3. 恢复备份
./scripts/backup/backup-redis.sh restore /tmp/backup.rdb.gz
```

---

## 完整系统恢复

### 步骤1: 准备环境

```bash
# 1. 克隆代码（如果是新环境）
git clone https://github.com/ATboy-web/AI_NovelWriter.git
cd AI_NovelWriter

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库密码等
```

### 步骤2: 恢复数据库

```bash
# 1. 启动数据库服务
docker-compose up -d postgres redis

# 2. 等待服务就绪
docker-compose exec postgres pg_isready
docker-compose exec redis redis-cli ping

# 3. 恢复PostgreSQL
./scripts/backup/backup-postgres.sh restore /path/to/postgres-backup.sql.gz

# 4. 恢复Redis
./scripts/backup/backup-redis.sh restore /path/to/redis-backup.rdb.gz
```

### 步骤3: 恢复应用数据

```bash
# 1. 恢复模型文件（如果有备份）
# 模型文件通常在 models/ 目录

# 2. 恢复配置文件
# 确保 .env 文件配置正确

# 3. 恢复日志（可选）
# 日志通常不需要恢复
```

### 步骤4: 启动服务

```bash
# 1. 启动所有服务
docker-compose up -d

# 2. 检查服务状态
docker-compose ps

# 3. 检查日志
docker-compose logs -f

# 4. 验证服务
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:3000
```

### 步骤5: 验证恢复

```bash
# 1. 检查数据库
docker-compose exec postgres psql -U postgres -d ai_novel -c "SELECT COUNT(*) FROM novels;"

# 2. 检查Redis缓存
docker-compose exec redis redis-cli DBSIZE

# 3. 测试API
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"test"}]}'

# 4. 检查监控
curl http://localhost:9090/-/healthy
curl http://localhost:3001/api/health
```

---

## 常见问题

### Q1: 恢复后数据库连接失败

**原因**: 可能是密码不匹配

**解决方案**:
```bash
# 检查PostgreSQL日志
docker-compose logs postgres

# 重置密码
docker-compose exec postgres psql -U postgres -c "ALTER USER postgres PASSWORD 'new_password';"

# 更新.env文件
sed -i 's/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=new_password/' .env

# 重启服务
docker-compose restart
```

### Q2: Redis恢复后数据为空

**原因**: Redis可能没有正确加载RDB文件

**解决方案**:
```bash
# 检查Redis日志
docker-compose logs redis

# 确认RDB文件存在
docker-compose exec redis ls -la /data/dump.rdb

# 强制加载RDB
docker-compose exec redis redis-cli DEBUG LOAD-SCHEDULE
```

### Q3: 恢复后服务启动失败

**原因**: 可能是数据库schema不匹配

**解决方案**:
```bash
# 检查应用日志
docker-compose logs ai-service
docker-compose logs novel-service

# 运行数据库迁移（如果有）
docker-compose exec ai-service python -m alembic upgrade head

# 或重新初始化数据库
docker-compose exec postgres psql -U postgres -d ai_novel -f /docker-entrypoint-initdb.d/init.sql
```

### Q4: 备份文件损坏

**原因**: 传输错误或存储问题

**解决方案**:
```bash
# 验证备份完整性
./scripts/backup/backup-postgres.sh verify /path/to/backup.sql.gz

# 如果损坏，尝试从S3恢复更早的备份
aws s3 ls s3://your-bucket/postgres/ --recursive | sort | tail -10

# 选择一个更早的备份
./scripts/backup/backup-postgres.sh restore /path/to/earlier-backup.sql.gz
```

### Q5: 磁盘空间不足

**原因**: 备份文件太大或磁盘空间太小

**解决方案**:
```bash
# 检查磁盘空间
df -h

# 清理旧备份
./scripts/backup/backup-scheduler.sh full

# 清理Docker缓存
docker system prune -a

# 扩展磁盘空间（如果可能）
```

---

## 恢复检查清单

恢复完成后，请检查以下项目：

- [ ] PostgreSQL服务正常运行
- [ ] Redis服务正常运行
- [ ] 数据库表结构完整
- [ ] 数据库数据完整
- [ ] Redis缓存数据正常
- [ ] AI服务可以正常启动
- [ ] 小说服务可以正常启动
- [ ] 前端可以正常访问
- [ ] API接口响应正常
- [ ] 监控系统正常工作
- [ ] 日志收集正常工作
- [ ] 备份任务正常执行

---

## 联系支持

如果恢复过程中遇到问题，请联系：

- GitHub Issues: https://github.com/ATboy-web/AI_NovelWriter/issues
- 邮箱: [待定]
