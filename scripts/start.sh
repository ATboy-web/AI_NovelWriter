#!/bin/bash

# AI自动写小说系统启动脚本
# 优化版本：使用健康检查替代sleep

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-120}
HEALTH_CHECK_INTERVAL=${HEALTH_CHECK_INTERVAL:-5}

# 打印带颜色的消息
print_message() {
    echo -e "${2}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# 等待服务就绪
wait_for_service() {
    local service_name="$1"
    local health_url="$2"
    local timeout="${3:-$HEALTH_CHECK_TIMEOUT}"
    local interval="${4:-$HEALTH_CHECK_INTERVAL}"
    
    print_message "等待 $service_name 就绪..." "$YELLOW"
    
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if curl -s -f "$health_url" > /dev/null 2>&1; then
            print_message "$service_name 已就绪 (${elapsed}s)" "$GREEN"
            return 0
        fi
        
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    
    echo ""
    print_message "错误: $service_name 启动超时 (${timeout}s)" "$RED"
    return 1
}

# 等待Docker容器健康
wait_for_container() {
    local container_name="$1"
    local timeout="${2:-$HEALTH_CHECK_TIMEOUT}"
    local interval="${3:-$HEALTH_CHECK_INTERVAL}"
    
    print_message "等待容器 $container_name 健康..." "$YELLOW"
    
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "unknown")
        
        if [ "$health_status" = "healthy" ]; then
            print_message "容器 $container_name 已健康 (${elapsed}s)" "$GREEN"
            return 0
        elif [ "$health_status" = "unknown" ]; then
            # 容器可能没有健康检查，检查是否运行中
            local running=$(docker inspect --format='{{.State.Running}}' "$container_name" 2>/dev/null || echo "false")
            if [ "$running" = "true" ]; then
                print_message "容器 $container_name 已运行 (${elapsed}s)" "$GREEN"
                return 0
            fi
        fi
        
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    
    echo ""
    print_message "错误: 容器 $container_name 启动超时 (${timeout}s)" "$RED"
    return 1
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
    
    # 检查Docker守护进程是否运行
    if ! docker info > /dev/null 2>&1; then
        print_message "错误: Docker守护进程未运行，请启动Docker" "$RED"
        exit 1
    fi
    
    print_message "Docker环境检查通过" "$GREEN"
}

# 检查环境变量
check_env() {
    if [ ! -f .env ]; then
        print_message "警告: .env文件不存在，将使用默认配置" "$YELLOW"
        if [ -f .env.example ]; then
            cp .env.example .env
            print_message "已从.env.example创建.env文件" "$YELLOW"
            print_message "请编辑.env文件配置数据库密码等敏感信息" "$YELLOW"
        fi
    fi
    
    # 检查必要的环境变量
    if [ -f .env ]; then
        source .env
        
        if [ -z "$POSTGRES_PASSWORD" ]; then
            print_message "警告: POSTGRES_PASSWORD未设置" "$YELLOW"
        fi
        
        if [ -z "$GRAFANA_ADMIN_PASSWORD" ]; then
            print_message "警告: GRAFANA_ADMIN_PASSWORD未设置" "$YELLOW"
        fi
    fi
    
    print_message "环境配置检查完成" "$GREEN"
}

# 创建必要的目录
create_directories() {
    mkdir -p logs/{ai-service,novel-service,nginx}
    mkdir -p models/local
    mkdir -p nginx/ssl
    mkdir -p monitoring/grafana/provisioning/{datasources,dashboards}
    mkdir -p monitoring/grafana/dashboards
    mkdir -p backups/{postgres,redis}
    
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
    
    # 等待基础服务就绪（使用健康检查）
    wait_for_container "ai-novel-postgres" 60
    wait_for_container "ai-novel-redis" 60
    
    # 启动应用服务
    docker-compose up -d ai-service novel-service
    
    # 等待应用服务就绪
    wait_for_service "AI服务" "http://localhost:8001/api/v1/health" 90
    wait_for_service "小说服务" "http://localhost:8002/api/v1/health" 90
    
    # 启动前端和代理服务
    docker-compose up -d frontend nginx
    
    # 等待前端服务就绪
    wait_for_service "前端服务" "http://localhost:3000" 60
    
    # 启动监控服务
    docker-compose up -d prometheus grafana alertmanager node-exporter postgres-exporter redis-exporter
    
    # 启动日志服务
    docker-compose up -d loki promtail
    
    print_message "所有服务启动完成" "$GREEN"
}

# 检查服务状态
check_services() {
    print_message "检查服务状态..." "$BLUE"
    
    docker-compose ps
    
    echo ""
    print_message "服务健康状态:" "$YELLOW"
    
    # 检查各服务
    local services=(
        "AI服务|http://localhost:8001/api/v1/health"
        "小说服务|http://localhost:8002/api/v1/health"
        "前端服务|http://localhost:3000"
        "Nginx代理|http://localhost:80"
        "Prometheus|http://localhost:9090/-/healthy"
        "Grafana|http://localhost:3001/api/health"
    )
    
    local all_healthy=true
    
    for service in "${services[@]}"; do
        IFS='|' read -r name url <<< "$service"
        
        if curl -s -f "$url" > /dev/null 2>&1; then
            print_message "  ✓ $name: 正常" "$GREEN"
        else
            print_message "  ✗ $name: 异常" "$RED"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        print_message "所有服务运行正常" "$GREEN"
    else
        print_message "部分服务异常，请检查日志" "$YELLOW"
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
    echo ""
    print_message "API文档:" "$YELLOW"
    print_message "  AI服务: http://localhost:8001/docs" "$NC"
    print_message "  小说服务: http://localhost:8002/docs" "$NC"
    echo ""
    print_message "监控信息:" "$YELLOW"
    print_message "  Prometheus: http://localhost:9090" "$NC"
    print_message "  Grafana: http://localhost:3001" "$NC"
    print_message "  Alertmanager: http://localhost:9093" "$NC"
    echo ""
    print_message "常用命令:" "$YELLOW"
    print_message "  查看日志: make docker-logs" "$NC"
    print_message "  停止服务: make docker-down" "$NC"
    print_message "  备份数据: make backup" "$NC"
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
    
    # 构建镜像（如果需要）
    if [ "${1:-}" = "--build" ] || [ "${1:-}" = "-b" ]; then
        build_images
    fi
    
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
