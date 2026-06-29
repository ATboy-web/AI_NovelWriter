# AI Novel Writer - Makefile
# 统一任务运行入口

.PHONY: help install dev test lint build run stop clean backup restore docker-up docker-down docker-build

# 默认目标
help: ## 显示帮助信息
	@echo "AI Novel Writer - 可用命令:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ==================== 开发环境 ====================

install: ## 安装Python依赖
	pip install -e ".[dev]"

dev: ## 启动开发环境
	python novel_app.py

test: ## 运行测试
	python -m pytest tests/ -v

test-cov: ## 运行测试（带覆盖率）
	python -m pytest tests/ --cov=app --cov-report=html --cov-report=term

lint: ## 代码质量检查
	ruff check app/ tests/
	ruff format --check app/ tests/

format: ## 代码格式化
	ruff format app/ tests/

type-check: ## 类型检查
	mypy app/ --ignore-missing-imports

# ==================== Docker环境 ====================

docker-build: ## 构建Docker镜像
	docker-compose build

docker-up: ## 启动Docker服务
	docker-compose up -d

docker-down: ## 停止Docker服务
	docker-compose down

docker-up-prod: ## 启动生产环境
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-down-prod: ## 停止生产环境
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

docker-logs: ## 查看Docker日志
	docker-compose logs -f

docker-ps: ## 查看运行中的容器
	docker-compose ps

docker-restart: ## 重启所有服务
	docker-compose restart

docker-clean: ## 清理Docker资源
	docker system prune -f
	docker volume prune -f

# ==================== 备份恢复 ====================

backup: ## 执行全量备份
	./scripts/backup/backup-scheduler.sh full

backup-postgres: ## 备份PostgreSQL
	./scripts/backup/backup-postgres.sh backup

backup-redis: ## 备份Redis
	./scripts/backup/backup-redis.sh backup

backup-install: ## 安装备份定时任务
	./scripts/backup/backup-scheduler.sh install '0 2 * * *'

backup-uninstall: ## 卸载备份定时任务
	./scripts/backup/backup-scheduler.sh uninstall

backup-status: ## 查看备份状态
	./scripts/backup/backup-scheduler.sh status

restore-postgres: ## 恢复PostgreSQL（需要指定备份文件）
	@echo "用法: ./scripts/backup/backup-postgres.sh restore <backup_file>"

restore-redis: ## 恢复Redis（需要指定备份文件）
	@echo "用法: ./scripts/backup/backup-redis.sh restore <backup_file>"

# ==================== 打包部署 ====================

build-exe: ## 打包Windows EXE
	pyinstaller --onefile --windowed --name AI_NovelWriter \
		--add-data "app;app" --add-data "backend;backend" \
		novel_app.py

build-apk: ## 构建Android APK
	cd mobile-app/novel-app && ./gradlew assembleRelease

# ==================== 监控 ====================

monitoring-up: ## 启动监控服务
	docker-compose up -d prometheus grafana alertmanager loki promtail

monitoring-down: ## 停止监控服务
	docker-compose down prometheus grafana alertmanager loki promtail

prometheus-check: ## 检查Prometheus配置
	docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml

# ==================== 数据库 ====================

db-shell: ## 进入PostgreSQL shell
	docker-compose exec postgres psql -U postgres -d ai_novel

db-migrate: ## 运行数据库迁移
	docker-compose exec ai-service python -m alembic upgrade head

db-backup: ## 备份数据库
	./scripts/backup/backup-postgres.sh backup

db-restore: ## 恢复数据库（需要指定备份文件）
	@echo "用法: ./scripts/backup/backup-postgres.sh restore <backup_file>"

# ==================== Redis ====================

redis-shell: ## 进入Redis shell
	docker-compose exec redis redis-cli

redis-monitor: ## 监控Redis
	docker-compose exec redis redis-cli monitor

# ==================== 日志 ====================

logs-ai: ## 查看AI服务日志
	docker-compose logs -f ai-service

logs-novel: ## 查看小说服务日志
	docker-compose logs -f novel-service

logs-nginx: ## 查看Nginx日志
	docker-compose logs -f nginx

logs-postgres: ## 查看PostgreSQL日志
	docker-compose logs -f postgres

logs-redis: ## 查看Redis日志
	docker-compose logs -f redis

# ==================== 清理 ====================

clean: ## 清理构建产物
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-all: ## 清理所有（包括Docker）
	clean
	docker-clean
