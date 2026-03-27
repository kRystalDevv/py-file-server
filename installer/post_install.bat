@echo off
setlocal EnableExtensions
:: Streamlined cloudflared installer for use during Inno Setup post-install.
:: Usage: post_install.bat [TOOLS_DIR]
::   TOOLS_DIR - where to place cloudflared.exe (defaults to script directory)

set "TOOLS_DIR=%~1"
if "%TOOLS_DIR%"=="" set "TOOLS_DIR=%~dp0"

echo [INFO] Checking for cloudflared...

:: Check if already available on PATH
where cloudflared >nul 2>&1
if not errorlevel 1 (
    echo [OK] cloudflared is already available on PATH.
    exit /b 0
)

:: Check if already in tools dir
if exist "%TOOLS_DIR%\cloudflared.exe" (
    echo [OK] cloudflared found in tools directory.
    exit /b 0
)

echo [INFO] cloudflared not found. Attempting download...

:: Detect architecture
set "CF_ASSET=cloudflared-windows-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "CF_ASSET=cloudflared-windows-arm64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" set "CF_ASSET=cloudflared-windows-386.exe"

set "CF_URL=https://github.com/cloudflare/cloudflared/releases/latest/download/%CF_ASSET%"
set "CF_EXE=%TOOLS_DIR%\cloudflared.exe"

:: Ensure tools directory exists
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" >nul 2>&1

:: Try winget first
where winget >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Trying winget install...
    winget install -e --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements --silent --disable-interactivity >nul 2>&1
    if not errorlevel 1 (
        echo [OK] cloudflared installed via winget.
        exit /b 0
    )
)

:: Direct download as fallback
echo [INFO] Downloading cloudflared from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%CF_URL%' -OutFile '%CF_EXE%' -UseBasicParsing -TimeoutSec 180; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }" 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to download cloudflared.
    exit /b 1
)

if not exist "%CF_EXE%" (
    echo [ERROR] Download completed but file not found.
    exit /b 1
)

echo [OK] cloudflared downloaded to: %CF_EXE%
exit /b 0
