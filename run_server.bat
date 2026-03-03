@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SERVER_CMD=python fileserver.py"
set "MODE="
set "PORT="
set "SHARE_DIR="
set "EXTRA_ARGS="
set "USE_NO_BROWSER=0"

call :print_header
call :check_prerequisites || goto :fatal

if not "%~1"=="" (
    echo [INFO] Advanced mode detected. Starting with arguments you provided.
    echo [INFO] Command: python fileserver.py %*
    echo.
    python fileserver.py %*
    goto :after_run
)

:menu
echo Choose how you want to run your file server:
echo.
echo   [1] Local only (safest) - only this PC can open the server
echo   [2] LAN sharing - devices on your Wi-Fi/LAN can open the server
echo   [3] Public internet - creates a Cloudflare public link
echo   [4] Custom setup (choose mode, port, folder, browser behavior)
echo   [5] Show simple examples
echo   [0] Exit
echo.
set /p "MENU_CHOICE=Enter your choice (0-5): "

if "%MENU_CHOICE%"=="1" (
    set "MODE=local"
    goto :launch_selected
)
if "%MENU_CHOICE%"=="2" (
    set "MODE=lan"
    goto :launch_selected
)
if "%MENU_CHOICE%"=="3" (
    set "MODE=public"
    goto :launch_selected
)
if "%MENU_CHOICE%"=="4" (
    goto :custom_setup
)
if "%MENU_CHOICE%"=="5" (
    call :show_examples
    goto :menu
)
if "%MENU_CHOICE%"=="0" (
    echo.
    echo Exiting launcher.
    exit /b 0
)

echo.
echo [WARN] Invalid choice. Please type 0, 1, 2, 3, 4, or 5.
echo.
goto :menu

:custom_setup
echo.
echo ================================
echo Custom setup wizard
echo ================================
echo.
set "MODE="
echo Pick mode:
echo   [1] local
echo   [2] lan
echo   [3] public
set /p "CUSTOM_MODE_CHOICE=Mode (1-3, default 2): "
if "%CUSTOM_MODE_CHOICE%"=="" set "CUSTOM_MODE_CHOICE=2"

if "%CUSTOM_MODE_CHOICE%"=="1" set "MODE=local"
if "%CUSTOM_MODE_CHOICE%"=="2" set "MODE=lan"
if "%CUSTOM_MODE_CHOICE%"=="3" set "MODE=public"
if not defined MODE (
    echo [WARN] Invalid mode choice. Returning to main menu.
    echo.
    goto :menu
)

set "PORT="
set /p "PORT=Port (press Enter for default): "
if defined PORT (
    for /f "delims=0123456789" %%A in ("%PORT%") do set "PORT_INVALID=1"
    if defined PORT_INVALID (
        set "PORT_INVALID="
        set "PORT="
        echo [WARN] Port must contain only numbers. Using default.
    )
)

set "SHARE_DIR="
set /p "SHARE_DIR=Folder to share (press Enter for current folder): "
if defined SHARE_DIR (
    if not exist "%SHARE_DIR%" (
        echo [WARN] Folder does not exist: "%SHARE_DIR%"
        echo [WARN] Using current folder instead.
        set "SHARE_DIR="
    )
)

set "USE_NO_BROWSER=0"
set /p "NO_BROWSER_CHOICE=Do not open browser automatically? (y/N): "
if /i "%NO_BROWSER_CHOICE%"=="y" set "USE_NO_BROWSER=1"

goto :launch_selected

:launch_selected
echo.
echo ================================
echo Starting file server
echo ================================
echo Mode: %MODE%
if defined PORT echo Port: %PORT%
if not defined PORT echo Port: default
if defined SHARE_DIR (
    echo Shared folder: "%SHARE_DIR%"
) else (
    echo Shared folder: current folder
)
if "%USE_NO_BROWSER%"=="1" (
    echo Browser auto-open: disabled
) else (
    echo Browser auto-open: enabled
)
if /i "%MODE%"=="public" (
    where cloudflared >nul 2>&1
    if errorlevel 1 (
        echo [WARN] cloudflared is not currently available in PATH.
        echo [WARN] Public mode may fail until cloudflared is installed.
    )
)
echo.

set "EXTRA_ARGS=--mode %MODE%"
if defined PORT set "EXTRA_ARGS=%EXTRA_ARGS% --port %PORT%"
if defined SHARE_DIR set "EXTRA_ARGS=%EXTRA_ARGS% --directory ""%SHARE_DIR%"""
if "%USE_NO_BROWSER%"=="1" set "EXTRA_ARGS=%EXTRA_ARGS% --no-browser"

echo [INFO] Command: %SERVER_CMD% %EXTRA_ARGS%
echo.
call %SERVER_CMD% %EXTRA_ARGS%

:after_run
if errorlevel 1 (
    echo.
    echo [ERROR] The server stopped with an error.
    echo [TIP] Run setup.bat first if dependencies are missing.
    goto :fatal
)

echo.
echo ================================
echo Server process ended normally.
echo ================================
pause
exit /b 0

:check_prerequisites
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not available in PATH.
    echo [ACTION] Run setup.bat, then try again.
    exit /b 1
)

if not exist fileserver.py (
    echo [ERROR] fileserver.py was not found in:
    echo         %CD%
    echo [ACTION] Open this script from the project folder.
    exit /b 1
)
exit /b 0

:print_header
echo.
echo =========================================================
echo 63xky File Server Launcher
echo Easy start menu for Local, LAN, or Public sharing
echo =========================================================
echo.
exit /b 0

:show_examples
echo.
echo Simple command examples:
echo   python fileserver.py --mode local
echo   python fileserver.py --mode lan --port 8080
echo   python fileserver.py --mode public --directory ".\files"
echo.
exit /b 0

:fatal
echo.
echo Launcher finished with errors.
pause
exit /b 1
