@echo off
cd /d "%~dp0"

echo ========================================
echo   AI NovelWriter - Build Tool
echo ========================================
echo.

set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    pause
    exit /b 1
)

echo [INFO] Cleaning old files...
cd installer
if exist "dist\AI_NovelWriter.exe" del /f /q "dist\AI_NovelWriter.exe" 2>nul

echo [INFO] Building...
"%PYTHON%" -m PyInstaller novel_app.spec --clean --noconfirm

if exist "dist\AI_NovelWriter.exe" (
    echo.
    echo [SUCCESS] Build complete!
    copy /y "dist\AI_NovelWriter.exe" "..\AI_NovelWriter.exe" >nul
    echo [FILE] AI_NovelWriter.exe
) else (
    echo.
    echo [ERROR] Build failed!
)

echo.
pause
