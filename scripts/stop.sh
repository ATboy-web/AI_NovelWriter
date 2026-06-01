#!/bin/bash

# AI自动写小说系统停止脚本

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

# 停止服务
stop_services() {
    print_message "停止所有服务..." "$BLUE"
    
    docker-compose down
    
    print_message "所有服务已停止" "$GREEN"
}

# 清理资源（可选）
cleanup() {
    if [ "$1" = "--clean" ]; then
        print_message "清理Docker资源..." "$YELLOW"
        
        # 删除未使用的镜像
        docker image prune -f
        
        # 删除未使用的卷
        docker volume prune -f
        
        print_message "资源清理完成" "$GREEN"
    fi
}

# 显示停止信息
show_stop_info() {
    echo ""
    print_message "========================================" "$BLUE"
    print_message "AI自动写小说系统已停止" "$GREEN"
    print_message "========================================" "$BLUE"
    echo ""
    print_message "提示:" "$YELLOW"
    print_message "  使用 ./scripts/start.sh 重新启动系统" "$NC"
    print_message "  使用 ./scripts/stop.sh --clean 清理Docker资源" "$NC"
    echo ""
}

# 主函数
main() {
    print_message "停止AI自动写小说系统..." "$BLUE"
    
    # 停止服务
    stop_services
    
    # 清理资源
    cleanup "$1"
    
    # 显示停止信息
    show_stop_info
}

# 捕获中断信号
trap 'print_message "停止被中断" "$RED"; exit 1' INT TERM

# 执行主函数
main "$@"