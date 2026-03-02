@echo off
echo.
echo ================================
echo Launching Share File Server
echo ================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Checking for required files...
if not exist fileserver.py (
    echo Error: fileserver.py not found in this directory.
    pause
    exit /b 1
)

python fileserver.py %*
if errorlevel 1 (
    echo Error: Failed to start the file server.
    pause
    exit /b 1
)
echo File server started successfully.

echo.
echo Server process ended.
pause
