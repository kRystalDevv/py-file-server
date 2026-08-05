@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo =========================================================
echo 63xky FileServer - Build Script
echo Builds PyInstaller executable and Inno Setup installer
echo =========================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    exit /b 1
)

:: Check PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)

:: Install dependencies
echo [INFO] Installing dependencies...
python -m pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    exit /b 1
)

:: Build with PyInstaller
echo.
echo [INFO] Building with PyInstaller...
python -m PyInstaller fileserver.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

echo [OK] PyInstaller build complete: dist\FileServer\

:: Check for Inno Setup
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo.
    echo [WARN] Inno Setup 6 not found. Skipping installer compilation.
    echo [INFO] Install from: https://jrsoftware.org/isdl.php
    echo [INFO] PyInstaller output is ready in dist\FileServer\
    goto :done
)

:: Read version from __init__.py
for /f "tokens=3 delims== " %%V in ('findstr /C:"__version__" fileshare_app\__init__.py') do set "APP_VERSION=%%~V"
if "%APP_VERSION%"=="" set "APP_VERSION=1.4.0"
echo [INFO] Building installer for version %APP_VERSION%

:: Compile installer
echo.
echo [INFO] Compiling Inno Setup installer...
"%ISCC%" /DMyAppVersion=%APP_VERSION% installer\fileserver.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed.
    exit /b 1
)

echo.
echo [OK] Installer built: installer\Output\FileServerSetup-%APP_VERSION%.exe

:done
echo.
echo =========================================================
echo Build complete!
echo =========================================================
pause
exit /b 0
