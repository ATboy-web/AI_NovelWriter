#!/bin/bash
# Redis自动备份脚本
# AI Novel Writer - Redis备份

set -euo pipefail

# ==================== 配置 ====================
BACKUP_DIR="${BACKUP_DIR:-./backups/redis}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"

# S3备份配置（可选）
S3_BUCKET="${S3_BACKUP_BUCKET:-}"
S3_PREFIX="${S3_BACKUP_PREFIX:-redis/}"

# 通知配置（可选）
NOTIFICATION_WEBHOOK="${BACKUP_WEBHOOK_URL:-}"

# ==================== 函数 ====================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

notify() {
    local message="$1"
    local status="${2:-info}"
    
    if [ -n "$NOTIFICATION_WEBHOOK" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"[$status] Redis备份: $message\"}" \
            "$NOTIFICATION_WEBHOOK" || true
    fi
}

# 创建备份目录
create_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log "创建备份目录: $BACKUP_DIR"
    fi
}

# 执行Redis备份
backup_redis() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/redis_${timestamp}.rdb"
    
    log "开始备份Redis"
    
    # 构建redis-cli命令
    local redis_cmd="redis-cli -h $REDIS_HOST -p $REDIS_PORT"
    if [ -n "$REDIS_PASSWORD" ]; then
        redis_cmd="$redis_cmd -a $REDIS_PASSWORD"
    fi
    
    # 触发BGSAVE
    log "触发Redis BGSAVE..."
    if ! $redis_cmd BGSAVE; then
        error "触发BGSAVE失败"
        notify "触发BGSAVE失败" "error"
        return 1
    fi
    
    # 等待BGSAVE完成
    log "等待BGSAVE完成..."
    local max_wait=60
    local waited=0
    
    while [ $waited -lt $max_wait ]; do
        local last_save=$($redis_cmd LASTSAVE)
        sleep 2
        local current_save=$($redis_cmd LASTSAVE)
        
        if [ "$current_save" != "$last_save" ]; then
            log "BGSAVE完成"
            break
        fi
        
        ((waited+=2))
    done
    
    if [ $waited -ge $max_wait ]; then
        error "BGSAVE超时"
        notify "BGSAVE超时" "error"
        return 1
    fi
    
    # 复制RDB文件
    local rdb_path=$($redis_cmd CONFIG GET dir | tail -1)/dump.rdb
    
    if [ -f "$rdb_path" ]; then
        cp "$rdb_path" "$backup_file"
        
        # 压缩备份
        gzip "$backup_file"
        backup_file="${backup_file}.gz"
        
        # 计算校验和
        sha256sum "$backup_file" > "${backup_file}.sha256"
        
        local file_size=$(du -h "$backup_file" | cut -f1)
        log "备份完成: $backup_file ($file_size)"
        notify "备份成功: $backup_file ($file_size)" "success"
        
        return 0
    else
        error "RDB文件不存在: $rdb_path"
        notify "RDB文件不存在" "error"
        return 1
    fi
}

# 验证备份完整性
verify_backup() {
    local backup_file="$1"
    local checksum_file="${backup_file}.sha256"
    
    log "验证备份完整性: $backup_file"
    
    if [ ! -f "$checksum_file" ]; then
        error "校验和文件不存在: $checksum_file"
        return 1
    fi
    
    if sha256sum -c "$checksum_file" > /dev/null 2>&1; then
        log "备份完整性验证通过"
        return 0
    else
        error "备份完整性验证失败"
        return 1
    fi
}

# 上传到S3
upload_to_s3() {
    local backup_file="$1"
    
    if [ -z "$S3_BUCKET" ]; then
        log "未配置S3备份，跳过上传"
        return 0
    fi
    
    local s3_path="s3://${S3_BUCKET}/${S3_PREFIX}$(basename "$backup_file")"
    
    log "上传备份到S3: $s3_path"
    
    if aws s3 cp "$backup_file" "$s3_path" \
        --storage-class STANDARD_IA \
        --metadata "backup-date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
        
        # 上传校验和
        aws s3 cp "${backup_file}.sha256" "${s3_path}.sha256"
        
        log "S3上传完成"
        return 0
    else
        error "S3上传失败"
        return 1
    fi
}

# 清理旧备份
cleanup_old_backups() {
    log "清理${RETENTION_DAYS}天前的备份"
    
    local deleted_count=0
    
    # 清理本地备份
    while IFS= read -r -d '' file; do
        rm -f "$file" "${file}.sha256"
        ((deleted_count++))
    done < <(find "$BACKUP_DIR" -name "*.rdb.gz" -mtime +"$RETENTION_DAYS" -print0)
    
    log "已删除 $deleted_count 个本地备份文件"
}

# 恢复备份
restore_backup() {
    local backup_file="$1"
    
    if [ ! -f "$backup_file" ]; then
        error "备份文件不存在: $backup_file"
        return 1
    fi
    
    log "恢复Redis从备份: $backup_file"
    
    # 验证备份完整性
    if ! verify_backup "$backup_file"; then
        error "备份完整性验证失败，中止恢复"
        return 1
    fi
    
    # 构建redis-cli命令
    local redis_cmd="redis-cli -h $REDIS_HOST -p $REDIS_PORT"
    if [ -n "$REDIS_PASSWORD" ]; then
        redis_cmd="$redis_cmd -a $REDIS_PASSWORD"
    fi
    
    # 停止Redis写入
    log "停止Redis写入..."
    $redis_cmd DEBUG SLEEP 1
    
    # 获取Redis数据目录
    local redis_dir=$($redis_cmd CONFIG GET dir | tail -1)
    local rdb_file="${redis_dir}/dump.rdb"
    
    # 备份当前RDB文件
    if [ -f "$rdb_file" ]; then
        cp "$rdb_file" "${rdb_file}.bak.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # 解压并恢复备份
    if gunzip -c "$backup_file" > "$rdb_file"; then
        log "备份文件已恢复到: $rdb_file"
        
        # 重启Redis以加载恢复的数据
        log "请手动重启Redis以加载恢复的数据"
        log "命令: docker-compose restart redis"
        
        return 0
    else
        error "备份恢复失败"
        return 1
    fi
}

# 显示备份列表
list_backups() {
    log "备份列表:"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log "备份目录不存在: $BACKUP_DIR"
        return 0
    fi
    
    local count=0
    while IFS= read -r -d '' file; do
        local size=$(du -h "$file" | cut -f1)
        local date=$(stat -c %y "$file" 2>/dev/null || stat -f %Sm "$file" 2>/dev/null)
        echo "  $file ($size) - $date"
        ((count++))
    done < <(find "$BACKUP_DIR" -name "*.rdb.gz" -print0 | sort -z)
    
    log "共 $count 个备份文件"
}

# ==================== 主程序 ====================

main() {
    local command="${1:-backup}"
    
    case "$command" in
        backup)
            create_backup_dir
            backup_redis
            cleanup_old_backups
            ;;
        restore)
            if [ -z "${2:-}" ]; then
                error "请指定备份文件路径"
                echo "用法: $0 restore <backup_file>"
                exit 1
            fi
            restore_backup "$2"
            ;;
        list)
            list_backups
            ;;
        verify)
            if [ -z "${2:-}" ]; then
                error "请指定备份文件路径"
                echo "用法: $0 verify <backup_file>"
                exit 1
            fi
            verify_backup "$2"
            ;;
        *)
            echo "用法: $0 {backup|restore|list|verify}"
            exit 1
            ;;
    esac
}

main "$@"
