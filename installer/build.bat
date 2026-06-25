@echo off
REM AI自动写小说系统 - 打包构建脚本
REM 用法: build.bat [app|clean]

setlocal enabledelayedexpansion

echo ========================================
echo AI自动写小说系统 - 打包构建
echo ========================================
echo.

REM 设置路径
set PROJECT_DIR=%~dp0..
set INSTALLER_DIR=%~dp0
set DIST_DIR=%INSTALLER_DIR%\dist

REM 创建目录
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.9+
    pause
    exit /b 1
)

REM 检查图标文件
if not exist "%PROJECT_DIR%\icon.ico" (
    echo 警告: 未找到icon.ico图标文件
    echo 请将图标文件放在项目根目录
)

REM 检查PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装PyInstaller...
    pip install pyinstaller
)

REM 解析参数
set TARGET=%1
if "%TARGET%"=="" set TARGET=all

echo 目标: %TARGET%
echo.

REM 执行打包
if "%TARGET%"=="app" goto build_app
if "%TARGET%"=="all" goto build_app
if "%TARGET%"=="clean" goto clean

echo 未知目标: %TARGET%
echo 用法: build.bat [app|clean]
pause
exit /b 1

:build_app
echo 正在打包桌面应用...
cd /d "%INSTALLER_DIR%"

REM 打包
python -m PyInstaller novel_app.spec --clean --noconfirm

if exist "%INSTALLER_DIR%\dist\AI_NovelWriter.exe" (
    echo.
    echo ========================================
    echo 打包完成！
    echo ========================================
    echo.
    echo 输出文件: %INSTALLER_DIR%\dist\AI_NovelWriter.exe
    echo.
    echo 请将AI_NovelWriter.exe复制到项目根目录或桌面使用
) else (
    echo.
    echo 打包失败！请检查错误信息
)
pause
exit /b 0

:clean
echo 清理构建文件...
if exist "%INSTALLER_DIR%\build" rmdir /s /q "%INSTALLER_DIR%\build"
if exist "%INSTALLER_DIR%\dist" rmdir /s /q "%INSTALLER_DIR%\dist"
if exist "%INSTALLER_DIR%\__pycache__" rmdir /s /q "%INSTALLER_DIR%\__pycache__"
echo 清理完成！
pause
exit /b 0
