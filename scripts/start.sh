#!/bin/bash

# AI自动写小说系统启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    echo -e "${2}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_message "错误: Docker未安装，请先安装Docker" "$RED"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_message "错误: Docker Compose未安装，请先安装Docker Compose" "$RED"
        exit 1
    fi
    
    print_message "Docker环境检查通过" "$GREEN"
}

# 检查环境变量
check_env() {
    if [ ! -f .env ]; then
        print_message "警告: .env文件不存在，将使用默认配置" "$YELLOW"
        cp .env.example .env 2>/dev/null || true
    fi
    
    print_message "环境配置检查完成" "$GREEN"
}

# 创建必要的目录
create_directories() {
    mkdir -p logs/{ai-service,novel-service,nginx}
    mkdir -p models/local
    mkdir -p nginx/ssl
    mkdir -p monitoring/grafana
    
    print_message "目录结构创建完成" "$GREEN"
}

# 构建Docker镜像
build_images() {
    print_message "开始构建Docker镜像..." "$BLUE"
    
    docker-compose build --no-cache
    
    print_message "Docker镜像构建完成" "$GREEN"
}

# 启动服务
start_services() {
    print_message "启动服务..." "$BLUE"
    
    # 启动基础服务
    docker-compose up -d postgres redis
    
    # 等待基础服务就绪
    print_message "等待数据库和缓存服务就绪..." "$YELLOW"
    sleep 10
    
    # 启动应用服务
    docker-compose up -d ai-service novel-service
    
    # 等待应用服务就绪
    print_message "等待应用服务就绪..." "$YELLOW"
    sleep 15
    
    # 启动前端和代理服务
    docker-compose up -d frontend nginx
    
    # 启动监控服务
    docker-compose up -d prometheus grafana
    
    print_message "所有服务启动完成" "$GREEN"
}

# 检查服务状态
check_services() {
    print_message "检查服务状态..." "$BLUE"
    
    docker-compose ps
    
    # 检查健康状态
    print_message "检查服务健康状态..." "$YELLOW"
    
    # 检查AI服务
    if curl -s http://localhost:8001/health > /dev/null; then
        print_message "AI服务: 正常" "$GREEN"
    else
        print_message "AI服务: 异常" "$RED"
    fi
    
    # 检查小说服务
    if curl -s http://localhost:8002/health > /dev/null; then
        print_message "小说服务: 正常" "$GREEN"
    else
        print_message "小说服务: 异常" "$RED"
    fi
    
    # 检查前端服务
    if curl -s http://localhost:3000 > /dev/null; then
        print_message "前端服务: 正常" "$GREEN"
    else
        print_message "前端服务: 异常" "$RED"
    fi
    
    # 检查Nginx
    if curl -s http://localhost:80 > /dev/null; then
        print_message "Nginx代理: 正常" "$GREEN"
    else
        print_message "Nginx代理: 异常" "$RED"
    fi
}

# 显示访问信息
show_access_info() {
    echo ""
    print_message "========================================" "$BLUE"
    print_message "AI自动写小说系统启动成功！" "$GREEN"
    print_message "========================================" "$BLUE"
    echo ""
    print_message "访问地址:" "$YELLOW"
    print_message "  前端界面: http://localhost" "$NC"
    print_message "  AI服务API: http://localhost:8001" "$NC"
    print_message "  小说服务API: http://localhost:8002" "$NC"
    print_message "  监控面板: http://localhost:3001" "$NC"
    echo ""
    print_message "API文档:" "$YELLOW"
    print_message "  AI服务: http://localhost:8001/docs" "$NC"
    print_message "  小说服务: http://localhost:8002/docs" "$NC"
    echo ""
    print_message "监控信息:" "$YELLOW"
    print_message "  Prometheus: http://localhost:9090" "$NC"
    print_message "  Grafana: http://localhost:3001 (admin/admin)" "$NC"
    echo ""
    print_message "========================================" "$BLUE"
}

# 主函数
main() {
    print_message "启动AI自动写小说系统..." "$BLUE"
    
    # 检查环境
    check_docker
    check_env
    
    # 创建目录
    create_directories
    
    # 构建镜像
    build_images
    
    # 启动服务
    start_services
    
    # 检查服务状态
    check_services
    
    # 显示访问信息
    show_access_info
}

# 捕获中断信号
trap 'print_message "启动被中断" "$RED"; exit 1' INT TERM

# 执行主函数
main "$@"