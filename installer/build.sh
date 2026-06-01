#!/bin/bash
# AI自动写小说系统 - 打包构建脚本 (Linux/Mac)
# 用法: ./build.sh [all|services|launcher]

set -e

echo "========================================"
echo "AI自动写小说系统 - 打包构建"
echo "========================================"
echo

# 设置路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
BUILD_DIR="$PROJECT_DIR/build"

# 创建目录
mkdir -p "$DIST_DIR"
mkdir -p "$BUILD_DIR"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python 3.9+"
    exit 1
fi

# 检查图标文件
if [ ! -f "$PROJECT_DIR/icon.ico" ]; then
    echo "警告: 未找到icon.ico图标文件"
    echo "请将图标文件放在项目根目录"
fi

# 检查PyInstaller
if ! pip3 show pyinstaller &> /dev/null; then
    echo "正在安装PyInstaller..."
    pip3 install pyinstaller
fi

# 解析参数
TARGET="${1:-all}"

echo "目标: $TARGET"
echo

# 执行打包
case "$TARGET" in
    all)
        echo "[1/3] 打包AI服务..."
        build_ai_service
        
        echo
        echo "[2/3] 打包小说服务..."
        build_novel_service
        
        echo
        echo "[3/3] 打包启动器..."
        build_launcher
        
        echo
        echo "========================================"
        echo "打包完成！"
        echo "========================================"
        echo
        echo "输出文件:"
        echo "  - AI服务: $DIST_DIR/AI_NovelService"
        echo "  - 小说服务: $DIST_DIR/NovelGenerator"
        echo "  - 启动器: $DIST_DIR/AI_NovelWriter"
        ;;
    services)
        echo "[1/2] 打包AI服务..."
        build_ai_service
        
        echo
        echo "[2/2] 打包小说服务..."
        build_novel_service
        
        echo
        echo "服务打包完成！"
        ;;
    launcher)
        echo "打包启动器..."
        build_launcher
        
        echo
        echo "启动器打包完成！"
        ;;
    clean)
        echo "清理构建文件..."
        rm -rf "$BUILD_DIR" "$DIST_DIR"
        echo "清理完成！"
        ;;
    *)
        echo "未知目标: $TARGET"
        echo "用法: ./build.sh [all|services|launcher|clean]"
        exit 1
        ;;
esac

# 函数定义
build_ai_service() {
    echo "  正在打包AI服务..."
    cd "$PROJECT_DIR"
    
    # 创建运行脚本
    cat > "$PROJECT_DIR/backend/ai-service/run.py" << 'EOF'
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
EOF
    
    # 安装依赖
    pip3 install -r "$PROJECT_DIR/backend/ai-service/requirements.txt"
    
    # 打包
    pyinstaller --clean "$SCRIPT_DIR/ai_service.spec"
    
    if [ -f "$DIST_DIR/AI_NovelService" ]; then
        echo "  AI服务打包成功"
    else
        echo "  AI服务打包失败"
        exit 1
    fi
}

build_novel_service() {
    echo "  正在打包小说服务..."
    cd "$PROJECT_DIR"
    
    # 创建运行脚本
    cat > "$PROJECT_DIR/backend/novel-service/run.py" << 'EOF'
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
EOF
    
    # 安装依赖
    pip3 install -r "$PROJECT_DIR/backend/novel-service/requirements.txt"
    
    # 打包
    pyinstaller --clean "$SCRIPT_DIR/novel_service.spec"
    
    if [ -f "$DIST_DIR/NovelGenerator" ]; then
        echo "  小说服务打包成功"
    else
        echo "  小说服务打包失败"
        exit 1
    fi
}

build_launcher() {
    echo "  正在打包启动器..."
    cd "$SCRIPT_DIR"
    
    # 打包
    pyinstaller --clean launcher.spec
    
    if [ -f "$DIST_DIR/AI_NovelWriter" ]; then
        echo "  启动器打包成功"
    else
        echo "  启动器打包失败"
        exit 1
    fi
}
