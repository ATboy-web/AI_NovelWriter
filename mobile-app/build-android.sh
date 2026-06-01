#!/bin/bash
# Android APK 构建脚本

set -e

echo "========================================"
echo "AI小说创作工坊 - Android构建"
echo "========================================"

# 检查Node.js
if ! command -v node &> /dev/null; then
    echo "错误: 未安装Node.js"
    exit 1
fi

# 检查Java
if ! command -v java &> /dev/null; then
    echo "错误: 未安装Java JDK"
    echo "请安装JDK 17: https://adoptium.net/"
    exit 1
fi

# 检查Android SDK
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    echo "警告: 未设置ANDROID_HOME或ANDROID_SDK_ROOT"
    echo "请安装Android Studio: https://developer.android.com/studio"
fi

echo ""
echo "步骤1: 安装依赖..."
npm install

echo ""
echo "步骤2: 安装EAS CLI..."
npm install -g eas-cli

echo ""
echo "步骤3: 登录Expo账号..."
echo "如果没有账号，请先注册: https://expo.dev/signup"
eas login

echo ""
echo "步骤4: 构建APK..."
echo "选择 'preview' 配置生成APK文件"
eas build --platform android --profile preview

echo ""
echo "========================================"
echo "构建完成！"
echo "========================================"
echo ""
echo "APK文件将通过邮件发送，或在Expo控制台下载"
echo "下载地址: https://expo.dev/accounts/[username]/projects/ai-novel-writer/builds"
