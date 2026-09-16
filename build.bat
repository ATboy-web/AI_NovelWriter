@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   AI NovelWriter - Build Tool
echo ========================================
echo.

rem ---------------------------------------------------------------
rem [1/3] Resolve a Python interpreter that actually has the build
rem       dependencies (PyInstaller + tkinter).
rem
rem       History: this script used to hardcode
rem         C:\...\.workbuddy\binaries\python\versions\3.13.12\python.exe
rem       which is an *empty* managed env (no PyInstaller, no tkinter),
rem       so a double-click always failed. Now we probe candidates.
rem
rem       Override with:  set ANW_PYTHON=C:\path\to\python.exe
rem ---------------------------------------------------------------
set "PYTHON="

if defined ANW_PYTHON call :TryPython "%ANW_PYTHON%"

call :TryLauncher 3.11
call :TryLauncher 3.12
call :TryLauncher 3.13
call :TryLauncher 3.10

call :TryPython "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
call :TryPython "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
call :TryPython "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
call :TryPython "C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
call :TryPython "python"

if not defined PYTHON (
    echo [ERROR] No usable Python found.
    echo         Need an interpreter with BOTH PyInstaller and tkinter.
    echo.
    echo         Install them with:
    echo             python -m pip install pyinstaller
    echo         Or point at one explicitly:
    echo             set ANW_PYTHON=C:\path\to\python.exe
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON%
echo.

rem ---------------------------------------------------------------
rem [2/3] Build
rem ---------------------------------------------------------------
echo [INFO] Cleaning old files...
cd installer
if exist "dist\AI_NovelWriter.exe" del /f /q "dist\AI_NovelWriter.exe" 2>nul

echo [INFO] Building...
"%PYTHON%" -m PyInstaller novel_app.spec --clean --noconfirm
set "BUILD_RC=%ERRORLEVEL%"
cd ..

if not exist "installer\dist\AI_NovelWriter.exe" (
    echo.
    echo [ERROR] Build failed! PyInstaller exit code = %BUILD_RC%
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Build complete!

rem ---------------------------------------------------------------
rem [3/3] Distribute the artifact
rem       - repo root : .\AI_NovelWriter.exe   (source of truth)
rem       - desktop   : %USERPROFILE%\Desktop\ (hand-off copy)
rem ---------------------------------------------------------------
copy /y "installer\dist\AI_NovelWriter.exe" "AI_NovelWriter.exe" >nul
echo [FILE] %CD%\AI_NovelWriter.exe

set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%\" set "DESKTOP=C:\Users\Administrator\Desktop"

if exist "%DESKTOP%\" (
    copy /y "installer\dist\AI_NovelWriter.exe" "%DESKTOP%\AI_NovelWriter.exe" >nul
    if exist "%DESKTOP%\AI_NovelWriter.exe" (
        echo [FILE] %DESKTOP%\AI_NovelWriter.exe
    ) else (
        echo [WARN] Could not copy to Desktop: %DESKTOP%
    )
) else (
    echo [WARN] Desktop folder not found: %DESKTOP%
)

echo.
pause
exit /b 0

rem ---------------------------------------------------------------
rem :TryLauncher <version>
rem   Resolve via the Windows "py" launcher, then delegate to :TryPython.
rem   Silently does nothing if that version is not installed.
rem ---------------------------------------------------------------
:TryLauncher
if defined PYTHON exit /b 0
set "LPATH="
for /f "delims=" %%P in ('py -%~1 -c "import sys;print(sys.executable)" 2^>nul') do set "LPATH=%%P"
if defined LPATH call :TryPython "%LPATH%"
exit /b 0

rem ---------------------------------------------------------------
rem :TryPython <path>
rem   Sets PYTHON if the candidate runs and can import PyInstaller+tkinter.
rem ---------------------------------------------------------------
:TryPython
if defined PYTHON exit /b 0
set "CAND=%~1"
if "%CAND%"=="" exit /b 0

if exist "%CAND%" goto :TryPythonProbe
where "%~1" >nul 2>nul || exit /b 0

:TryPythonProbe
"%~1" -c "import PyInstaller, tkinter" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=%~1"
    echo [OK]   probe passed: %~1
    exit /b 0
)
echo [SKIP] %~1  ^(no PyInstaller or no tkinter^)
exit /b 0
