#!/bin/bash
# PostgreSQL自动备份脚本
# AI Novel Writer - 数据库备份

set -euo pipefail

# ==================== 配置 ====================
BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-ai_novel}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:?请设置POSTGRES_PASSWORD环境变量}"

# S3备份配置（可选）
S3_BUCKET="${S3_BACKUP_BUCKET:-}"
S3_PREFIX="${S3_BACKUP_PREFIX:-postgres/}"

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
            --data "{\"text\":\"[$status] PostgreSQL备份: $message\"}" \
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

# 执行PostgreSQL备份
backup_postgres() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/${DB_NAME}_${timestamp}.sql.gz"
    local checksum_file="${backup_file}.sha256"
    
    log "开始备份数据库: $DB_NAME"
    
    # 设置密码环境变量
    export PGPASSWORD="$DB_PASSWORD"
    
    # 执行备份并压缩
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom \
        --compress=9 \
        --verbose \
        2>/dev/null | gzip > "$backup_file"; then
        
        # 计算校验和
        sha256sum "$backup_file" > "$checksum_file"
        
        local file_size=$(du -h "$backup_file" | cut -f1)
        log "备份完成: $backup_file ($file_size)"
        notify "备份成功: $backup_file ($file_size)" "success"
        
        return 0
    else
        error "备份失败"
        notify "备份失败" "error"
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
        --metadata "backup-date=$(date -u +%Y-%m-%dT%H:%M:%SZ),database=$DB_NAME"; then
        
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
    done < <(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" -print0)
    
    log "已删除 $deleted_count 个本地备份文件"
    
    # 清理S3备份（如果配置了）
    if [ -n "$S3_BUCKET" ]; then
        local cutoff_date=$(date -d "$RETENTION_DAYS days ago" -u +%Y-%m-%dT%H:%M:%SZ)
        
        aws s3api list-objects-v2 --bucket "$S3_BUCKET" --prefix "$S3_PREFIX" \
            --query "Contents[?LastModified<='$cutoff_date'].Key" --output text | \
        while read -r key; do
            if [ -n "$key" ] && [ "$key" != "None" ]; then
                aws s3 rm "s3://${S3_BUCKET}/${key}"
                log "删除S3备份: $key"
            fi
        done
    fi
}

# 恢复备份
restore_backup() {
    local backup_file="$1"
    
    if [ ! -f "$backup_file" ]; then
        error "备份文件不存在: $backup_file"
        return 1
    fi
    
    log "恢复数据库从备份: $backup_file"
    
    # 验证备份完整性
    if ! verify_backup "$backup_file"; then
        error "备份完整性验证失败，中止恢复"
        return 1
    fi
    
    # 设置密码环境变量
    export PGPASSWORD="$DB_PASSWORD"
    
    # 恢复数据库
    if gunzip -c "$backup_file" | pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --clean --if-exists --verbose 2>/dev/null; then
        
        log "数据库恢复成功"
        return 0
    else
        error "数据库恢复失败"
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
    done < <(find "$BACKUP_DIR" -name "*.sql.gz" -print0 | sort -z)
    
    log "共 $count 个备份文件"
}

# ==================== 主程序 ====================

main() {
    local command="${1:-backup}"
    
    case "$command" in
        backup)
            create_backup_dir
            backup_postgres
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
