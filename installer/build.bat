@echo off
REM AI自动写小说系统 - 打包构建脚本
REM 用法: build.bat [all|services|launcher|installer]

setlocal enabledelayedexpansion

echo ========================================
echo AI自动写小说系统 - 打包构建
echo ========================================
echo.

REM 设置路径
set PROJECT_DIR=%~dp0..
set INSTALLER_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%\dist
set BUILD_DIR=%PROJECT_DIR%\build

REM 创建目录
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

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
if "%TARGET%"=="all" goto build_all
if "%TARGET%"=="services" goto build_services
if "%TARGET%"=="launcher" goto build_launcher
if "%TARGET%"=="installer" goto build_installer
if "%TARGET%"=="clean" goto clean

echo 未知目标: %TARGET%
echo 用法: build.bat [all|services|launcher|installer|clean]
pause
exit /b 1

:build_all
echo [1/4] 打包AI服务...
call :build_ai_service
if errorlevel 1 (
    echo AI服务打包失败
    pause
    exit /b 1
)

echo.
echo [2/4] 打包小说服务...
call :build_novel_service
if errorlevel 1 (
    echo 小说服务打包失败
    pause
    exit /b 1
)

echo.
echo [3/4] 打包启动器...
call :build_launcher
if errorlevel 1 (
    echo 启动器打包失败
    pause
    exit /b 1
)

echo.
echo [4/4] 创建安装程序...
call :build_installer
if errorlevel 1 (
    echo 安装程序创建失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo.
echo 输出文件:
echo   - AI服务: %DIST_DIR%\AI_NovelService.exe
echo   - 小说服务: %DIST_DIR%\NovelGenerator.exe
echo   - 启动器: %DIST_DIR%\AI_NovelWriter.exe
echo   - 安装程序: %INSTALLER_DIR%\AI_NovelWriter_Setup.exe
echo.
pause
exit /b 0

:build_services
echo [1/2] 打包AI服务...
call :build_ai_service
if errorlevel 1 (
    echo AI服务打包失败
    pause
    exit /b 1
)

echo.
echo [2/2] 打包小说服务...
call :build_novel_service
if errorlevel 1 (
    echo 小说服务打包失败
    pause
    exit /b 1
)

echo.
echo 服务打包完成！
pause
exit /b 0

:build_launcher
echo 打包启动器...
call :build_launcher_impl
if errorlevel 1 (
    echo 启动器打包失败
    pause
    exit /b 1
)

echo.
echo 启动器打包完成！
pause
exit /b 0

:build_installer
echo 创建安装程序...
call :build_installer_impl
if errorlevel 1 (
    echo 安装程序创建失败
    pause
    exit /b 1
)

echo.
echo 安装程序创建完成！
pause
exit /b 0

:clean
echo 清理构建文件...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
echo 清理完成！
pause
exit /b 0

REM ========================================
REM 函数定义
REM ========================================

:build_ai_service
echo   正在打包AI服务...
cd /d "%PROJECT_DIR%"

REM 创建运行脚本
echo import sys > "%PROJECT_DIR%\backend\ai-service\run.py"
echo import os >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo. >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo # 添加项目路径 >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))) >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo. >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo from app.main import app >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo import uvicorn >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo. >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo if __name__ == "__main__": >> "%PROJECT_DIR%\backend\ai-service\run.py"
echo     uvicorn.run(app, host="0.0.0.0", port=8001) >> "%PROJECT_DIR%\backend\ai-service\run.py"

REM 安装依赖
pip install -r "%PROJECT_DIR%\backend\ai-service\requirements.txt"

REM 打包
pyinstaller --clean "%INSTALLER_DIR%\ai_service.spec"

if exist "%DIST_DIR%\AI_NovelService.exe" (
    echo   AI服务打包成功
    exit /b 0
) else (
    echo   AI服务打包失败
    exit /b 1
)

:build_novel_service
echo   正在打包小说服务...
cd /d "%PROJECT_DIR%"

REM 创建运行脚本
echo import sys > "%PROJECT_DIR%\backend\novel-service\run.py"
echo import os >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo. >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo # 添加项目路径 >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))) >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo. >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo from app.main import app >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo import uvicorn >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo. >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo if __name__ == "__main__": >> "%PROJECT_DIR%\backend\novel-service\run.py"
echo     uvicorn.run(app, host="0.0.0.0", port=8002) >> "%PROJECT_DIR%\backend\novel-service\run.py"

REM 安装依赖
pip install -r "%PROJECT_DIR%\backend\novel-service\requirements.txt"

REM 打包
pyinstaller --clean "%INSTALLER_DIR%\novel_service.spec"

if exist "%DIST_DIR%\NovelGenerator.exe" (
    echo   小说服务打包成功
    exit /b 0
) else (
    echo   小说服务打包失败
    exit /b 1
)

:build_launcher_impl
echo   正在打包启动器...
cd /d "%INSTALLER_DIR%"

REM 打包
pyinstaller --clean launcher.spec

if exist "%DIST_DIR%\AI_NovelWriter.exe" (
    echo   启动器打包成功
    exit /b 0
) else (
    echo   启动器打包失败
    exit /b 1
)

:build_installer_impl
echo   正在创建安装程序...
cd /d "%INSTALLER_DIR%"

REM 检查NSIS
makensis /VERSION >nul 2>&1
if errorlevel 1 (
    echo   警告: 未找到NSIS，请先安装NSIS
    echo   下载地址: https://nsis.sourceforge.io/Download
    exit /b 1
)

REM 创建安装程序
makensis installer.nsi

if exist "%INSTALLER_DIR%\AI_NovelWriter_Setup.exe" (
    echo   安装程序创建成功
    exit /b 0
) else (
    echo   安装程序创建失败
    exit /b 1
)
