#!/bin/bash
# 备份调度脚本
# AI Novel Writer - 自动备份调度

set -euo pipefail

# ==================== 配置 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_LOG="${BACKUP_LOG:-./logs/backup.log}"
NOTIFICATION_WEBHOOK="${BACKUP_WEBHOOK_URL:-}"

# ==================== 函数 ====================

log() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$message"
    echo "$message" >> "$BACKUP_LOG"
}

error() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo "$message" >&2
    echo "$message" >> "$BACKUP_LOG"
}

notify() {
    local message="$1"
    local status="${2:-info}"
    
    if [ -n "$NOTIFICATION_WEBHOOK" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"[$status] 备份调度: $message\"}" \
            "$NOTIFICATION_WEBHOOK" || true
    fi
}

# 创建日志目录
create_log_dir() {
    local log_dir=$(dirname "$BACKUP_LOG")
    if [ ! -d "$log_dir" ]; then
        mkdir -p "$log_dir"
    fi
}

# 执行备份任务
run_backup() {
    local service="$1"
    local script="${SCRIPT_DIR}/backup-${service}.sh"
    
    if [ ! -f "$script" ]; then
        error "备份脚本不存在: $script"
        return 1
    fi
    
    log "开始备份: $service"
    
    if bash "$script" backup; then
        log "备份完成: $service"
        notify "备份完成: $service" "success"
        return 0
    else
        error "备份失败: $service"
        notify "备份失败: $service" "error"
        return 1
    fi
}

# 全量备份
full_backup() {
    log "==================== 开始全量备份 ===================="
    
    local failed=0
    
    # PostgreSQL备份
    if ! run_backup "postgres"; then
        ((failed++))
    fi
    
    # Redis备份
    if ! run_backup "redis"; then
        ((failed++))
    fi
    
    if [ $failed -eq 0 ]; then
        log "全量备份完成，所有服务备份成功"
        notify "全量备份完成" "success"
    else
        log "全量备份完成，$failed 个服务备份失败"
        notify "全量备份完成，$failed 个服务备份失败" "warning"
    fi
    
    log "==================== 全量备份结束 ===================="
}

# 安装cron任务
install_cron() {
    local cron_schedule="${1:-0 2 * * *}"  # 默认每天凌晨2点
    
    log "安装cron备份任务: $cron_schedule"
    
    # 创建cron任务
    local cron_job="$cron_schedule $(readlink -f "$0") full >> $BACKUP_LOG 2>&1"
    
    # 检查是否已存在
    if crontab -l 2>/dev/null | grep -q "$(readlink -f "$0")"; then
        log "cron任务已存在，更新中..."
        crontab -l 2>/dev/null | grep -v "$(readlink -f "$0")" | { cat; echo "$cron_job"; } | crontab -
    else
        log "添加新的cron任务..."
        (crontab -l 2>/dev/null; echo "$cron_job") | crontab -
    fi
    
    log "cron任务安装完成"
    log "当前cron任务:"
    crontab -l 2>/dev/null | grep "$(readlink -f "$0")" || true
}

# 卸载cron任务
uninstall_cron() {
    log "卸载cron备份任务..."
    
    if crontab -l 2>/dev/null | grep -q "$(readlink -f "$0")"; then
        crontab -l 2>/dev/null | grep -v "$(readlink -f "$0")" | crontab -
        log "cron任务已卸载"
    else
        log "未找到cron任务"
    fi
}

# 显示备份状态
show_status() {
    log "备份状态:"
    
    # 检查PostgreSQL备份
    echo ""
    echo "=== PostgreSQL 备份 ==="
    bash "${SCRIPT_DIR}/backup-postgres.sh" list
    
    # 检查Redis备份
    echo ""
    echo "=== Redis 备份 ==="
    bash "${SCRIPT_DIR}/backup-redis.sh" list
    
    # 检查cron任务
    echo ""
    echo "=== Cron 任务 ==="
    if crontab -l 2>/dev/null | grep -q "$(readlink -f "$0")"; then
        crontab -l 2>/dev/null | grep "$(readlink -f "$0")"
    else
        echo "未安装cron任务"
    fi
}

# 显示帮助
show_help() {
    echo "AI Novel Writer 备份调度脚本"
    echo ""
    echo "用法: $0 <command> [options]"
    echo ""
    echo "命令:"
    echo "  full              执行全量备份（PostgreSQL + Redis）"
    echo "  postgres          备份PostgreSQL"
    echo "  redis             备份Redis"
    echo "  install [schedule] 安装cron任务（默认: 每天凌晨2点）"
    echo "  uninstall         卸载cron任务"
    echo "  status            显示备份状态"
    echo "  help              显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 full                    # 执行全量备份"
    echo "  $0 install '0 2 * * *'     # 安装每天凌晨2点的备份任务"
    echo "  $0 install '0 */6 * * *'   # 安装每6小时的备份任务"
}

# ==================== 主程序 ====================

main() {
    create_log_dir
    
    local command="${1:-help}"
    
    case "$command" in
        full)
            full_backup
            ;;
        postgres)
            run_backup "postgres"
            ;;
        redis)
            run_backup "redis"
            ;;
        install)
            install_cron "${2:-}"
            ;;
        uninstall)
            uninstall_cron
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
