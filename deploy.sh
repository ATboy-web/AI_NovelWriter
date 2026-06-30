#!/bin/bash
# AI_NovelWriter 生产环境部署脚本
# 使用方法: chmod +x deploy.sh && ./deploy.sh

set -e

echo "=========================================="
echo "  AI_NovelWriter 生产环境部署"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查依赖
check_dependencies() {
    echo -e "${YELLOW}检查依赖...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}错误: 未安装 Docker${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}错误: 未安装 Docker Compose${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}依赖检查通过${NC}"
}

# 检查环境变量
check_env() {
    echo -e "${YELLOW}检查环境变量...${NC}"
    
    if [ ! -f .env ]; then
        echo -e "${RED}错误: 未找到 .env 文件${NC}"
        echo "请复制 .env.example 为 .env 并填入实际值"
        exit 1
    fi
    
    source .env
    
    if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "your_secure_db_password_here" ]; then
        echo -e "${RED}错误: 请设置 DB_PASSWORD${NC}"
        exit 1
    fi
    
    if [ -z "$JWT_SECRET" ] || [ "$JWT_SECRET" = "your_jwt_secret_key_here_at_least_32_chars" ]; then
        echo -e "${RED}错误: 请设置 JWT_SECRET${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}环境变量检查通过${NC}"
}

# 创建必要目录
create_dirs() {
    echo -e "${YELLOW}创建必要目录...${NC}"
    
    mkdir -p nginx/ssl
    mkdir -p nginx/logs
    mkdir -p monitoring/grafana/dashboards
    mkdir -p monitoring/grafana/datasources
    mkdir -p scripts
    mkdir -p logs
    
    echo -e "${GREEN}目录创建完成${NC}"
}

# 生成 SSL 证书（Let's Encrypt）
setup_ssl() {
    echo -e "${YELLOW}检查 SSL 证书...${NC}"
    
    if [ ! -f nginx/ssl/fullchain.pem ]; then
        echo -e "${YELLOW}SSL 证书不存在，将使用自签名证书（仅用于测试）${NC}"
        
        # 生成自签名证书
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/privkey.pem \
            -out nginx/ssl/fullchain.pem \
            -subj "/C=CN/ST=State/L=City/O=Organization/CN=localhost"
        
        echo -e "${GREEN}自签名证书已生成${NC}"
        echo -e "${YELLOW}注意: 生产环境请使用 Let's Encrypt 证书${NC}"
    else
        echo -e "${GREEN}SSL 证书已存在${NC}"
    fi
}

# 初始化数据库
init_database() {
    echo -e "${YELLOW}初始化数据库...${NC}"
    
    cat > scripts/init.sql << 'EOF'
-- AI_NovelWriter 数据库初始化脚本

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 小说表
CREATE TABLE IF NOT EXISTS novels (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    genre VARCHAR(50),
    description TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 章节表
CREATE TABLE IF NOT EXISTS chapters (
    id SERIAL PRIMARY KEY,
    novel_id INTEGER REFERENCES novels(id),
    chapter_number INTEGER NOT NULL,
    title VARCHAR(200),
    content TEXT,
    word_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(novel_id, chapter_number)
);

-- 订阅表
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_novels_user_id ON novels(user_id);
CREATE INDEX IF NOT EXISTS idx_chapters_novel_id ON chapters(novel_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
EOF
    
    echo -e "${GREEN}数据库初始化脚本已创建${NC}"
}

# 构建并启动服务
deploy() {
    echo -e "${YELLOW}构建并启动服务...${NC}"
    
    # 拉取最新镜像
    docker-compose -f docker-compose.prod.yml pull
    
    # 构建自定义镜像
    docker-compose -f docker-compose.prod.yml build --no-cache
    
    # 停止旧容器
    docker-compose -f docker-compose.prod.yml down
    
    # 启动新容器
    docker-compose -f docker-compose.prod.yml up -d
    
    echo -e "${GREEN}服务启动完成${NC}"
}

# 健康检查
health_check() {
    echo -e "${YELLOW}执行健康检查...${NC}"
    
    sleep 10
    
    # 检查各个服务
    services=("nginx:80" "ai-service:8001" "novel-service:8002")
    
    for service in "${services[@]}"; do
        name="${service%%:*}"
        port="${service##*:}"
        
        if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ ${name} 服务正常${NC}"
        else
            echo -e "${RED}✗ ${name} 服务异常${NC}"
        fi
    done
}

# 显示部署信息
show_info() {
    echo ""
    echo "=========================================="
    echo "  部署完成！"
    echo "=========================================="
    echo ""
    echo "访问地址:"
    echo "  HTTP:  http://localhost"
    echo "  HTTPS: https://localhost"
    echo ""
    echo "监控地址:"
    echo "  Grafana: http://localhost:3001"
    echo "  Prometheus: http://localhost:9090"
    echo ""
    echo "常用命令:"
    echo "  查看日志: docker-compose -f docker-compose.prod.yml logs -f"
    echo "  停止服务: docker-compose -f docker-compose.prod.yml down"
    echo "  重启服务: docker-compose -f docker-compose.prod.yml restart"
    echo ""
}

# 主流程
main() {
    check_dependencies
    check_env
    create_dirs
    setup_ssl
    init_database
    deploy
    health_check
    show_info
}

# 执行主流程
main
