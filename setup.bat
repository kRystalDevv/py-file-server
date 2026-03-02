@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD=python"
set "REQUIREMENTS_OK=0"

call :print_header

call :is_admin
if errorlevel 1 (
    echo [INFO] Administrator privileges are required for reliable setup.
    call :relaunch_elevated
    if errorlevel 1 goto :fatal
    echo [INFO] Elevated installer launched. Closing this window.
    exit /b 0
)

call :refresh_path

call :ensure_cloudflared || goto :fatal
call :ensure_python || goto :fatal
call :install_requirements || goto :fatal
call :final_validation || goto :fatal

echo.
echo ================================
echo Setup completed successfully.
echo Environment is ready.
echo ================================
pause
exit /b 0

:fatal
echo.
echo ================================
echo Setup failed. See errors above.
echo ================================
pause
exit /b 1

:print_header
echo.
echo ================================
echo Robust environment installer
echo ================================
echo.
exit /b 0

:is_admin
net session >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:relaunch_elevated
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c ""%~f0""' -Verb RunAs" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] UAC elevation request was denied or failed.
    exit /b 1
)
exit /b 0

:refresh_path
set "MACHINE_PATH="
set "USER_PATH="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetEnvironmentVariable('Path','Machine')"`) do set "MACHINE_PATH=%%A"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "USER_PATH=%%A"
if defined MACHINE_PATH (
    if defined USER_PATH (
        set "PATH=%MACHINE_PATH%;%USER_PATH%"
    ) else (
        set "PATH=%MACHINE_PATH%"
    )
)
exit /b 0

:ensure_cloudflared
echo.
echo ================================
echo Ensuring cloudflared is installed
echo ================================

call :is_cloudflared_available
if not errorlevel 1 (
    echo [INFO] cloudflared is already available.
    exit /b 0
)

echo [INFO] cloudflared not detected. Trying method 1/3: winget.
call :install_cloudflared_winget
if not errorlevel 1 exit /b 0

echo [WARN] Method 1 failed. Trying method 2/3: Chocolatey.
call :install_cloudflared_choco
if not errorlevel 1 exit /b 0

echo [WARN] Method 2 failed. Trying method 3/3: direct download.
call :install_cloudflared_direct
if not errorlevel 1 exit /b 0

echo [ERROR] All cloudflared installation methods failed.
exit /b 1

:is_cloudflared_available
where cloudflared >nul 2>&1 || exit /b 1
cloudflared --version >nul 2>&1 || exit /b 1
exit /b 0

:install_cloudflared_winget
where winget >nul 2>&1 || exit /b 1
winget install -e --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements --silent --disable-interactivity >nul 2>&1
if errorlevel 1 exit /b 1
call :refresh_path
call :is_cloudflared_available
exit /b %errorlevel%

:install_cloudflared_choco
where choco >nul 2>&1 || exit /b 1
choco install cloudflared -y --no-progress >nul 2>&1
if errorlevel 1 exit /b 1
call :refresh_path
call :is_cloudflared_available
exit /b %errorlevel%

:install_cloudflared_direct
set "CF_ASSET=cloudflared-windows-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "CF_ASSET=cloudflared-windows-arm64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" set "CF_ASSET=cloudflared-windows-386.exe"

set "CF_DIR=%ProgramFiles%\cloudflared"
set "CF_EXE=%CF_DIR%\cloudflared.exe"
if not exist "%CF_DIR%" mkdir "%CF_DIR%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/%CF_ASSET%' -OutFile '%CF_EXE%' -UseBasicParsing -TimeoutSec 180; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 exit /b 1
if not exist "%CF_EXE%" exit /b 1

call :add_machine_path "%CF_DIR%"
if errorlevel 1 exit /b 1

call :refresh_path
call :is_cloudflared_available
exit /b %errorlevel%

:ensure_python
echo.
echo ================================
echo Ensuring Python and pip are installed
echo ================================

call :is_python_available
if not errorlevel 1 (
    echo [INFO] Python is already available.
    set "PYTHON_CMD=python"
    call :ensure_pip
    exit /b %errorlevel%
)

echo [INFO] Python not detected. Trying method 1/3: winget.
call :install_python_winget
if not errorlevel 1 (
    call :ensure_pip
    exit /b %errorlevel%
)

echo [WARN] Method 1 failed. Trying method 2/3: Chocolatey.
call :install_python_choco
if not errorlevel 1 (
    call :ensure_pip
    exit /b %errorlevel%
)

echo [WARN] Method 2 failed. Trying method 3/3: official installer.
call :install_python_direct
if not errorlevel 1 (
    call :ensure_pip
    exit /b %errorlevel%
)

echo [ERROR] All Python installation methods failed.
exit /b 1

:is_python_available
python -c "import sys; print(sys.version)" >nul 2>&1 || exit /b 1
exit /b 0

:install_python_winget
where winget >nul 2>&1 || exit /b 1
winget install -e --id Python.Python.3.12 --scope machine --accept-source-agreements --accept-package-agreements --silent --disable-interactivity >nul 2>&1
if errorlevel 1 exit /b 1
call :refresh_path
call :repair_python_path_if_needed
call :is_python_available
exit /b %errorlevel%

:install_python_choco
where choco >nul 2>&1 || exit /b 1
choco install python -y --no-progress >nul 2>&1
if errorlevel 1 exit /b 1
call :refresh_path
call :repair_python_path_if_needed
call :is_python_available
exit /b %errorlevel%

:install_python_direct
set "PY_VERSION=3.12.8"
set "PY_ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" set "PY_ARCH="
set "PY_INSTALLER=%TEMP%\python-%PY_VERSION%-%PY_ARCH%.exe"
if "%PY_ARCH%"=="" set "PY_INSTALLER=%TEMP%\python-%PY_VERSION%.exe"

set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-%PY_ARCH%.exe"
if "%PY_ARCH%"=="" set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing -TimeoutSec 240; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 exit /b 1
if not exist "%PY_INSTALLER%" exit /b 1

"%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0 Shortcuts=0 >nul 2>&1
if errorlevel 1 exit /b 1

call :refresh_path
call :repair_python_path_if_needed
call :is_python_available
exit /b %errorlevel%

:repair_python_path_if_needed
call :is_python_available
if not errorlevel 1 exit /b 0

for %%P in (
    "%ProgramFiles%\Python312"
    "%ProgramFiles%\Python311"
    "%ProgramFiles%\Python310"
    "%LocalAppData%\Programs\Python\Python312"
    "%LocalAppData%\Programs\Python\Python311"
    "%LocalAppData%\Programs\Python\Python310"
) do (
    if exist "%%~P\python.exe" (
        call :add_machine_path "%%~P"
        call :add_machine_path "%%~P\Scripts"
    )
)

call :refresh_path
call :is_python_available
if not errorlevel 1 exit /b 0

where py >nul 2>&1 || exit /b 1
for /f "usebackq delims=" %%X in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PY_FROM_LAUNCHER=%%X"
if not defined PY_FROM_LAUNCHER exit /b 1
for %%D in ("%PY_FROM_LAUNCHER%") do set "PY_DIR=%%~dpD"
if not exist "%PY_FROM_LAUNCHER%" exit /b 1

call :add_machine_path "%PY_DIR%"
call :add_machine_path "%PY_DIR%Scripts"
call :refresh_path
call :is_python_available
exit /b %errorlevel%

:ensure_pip
python -m pip --version >nul 2>&1
if not errorlevel 1 exit /b 0

python -m ensurepip --upgrade >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is unavailable and ensurepip failed.
    exit /b 1
)

python -m pip --version >nul 2>&1 || exit /b 1
exit /b 0

:add_machine_path
set "TARGET_PATH=%~1"
if "%TARGET_PATH%"=="" exit /b 1
if not exist "%TARGET_PATH%" exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$d='%TARGET_PATH%'; $p=[Environment]::GetEnvironmentVariable('Path','Machine'); if([string]::IsNullOrWhiteSpace($p)){ $p=$d } else { $exists=$p.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ieq $d }; if(-not $exists){ $p=($p.TrimEnd(';') + ';' + $d) } }; [Environment]::SetEnvironmentVariable('Path',$p,'Machine')" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:install_requirements
echo.
echo ================================
echo Installing Python requirements
echo ================================

if not exist requirements.txt (
    echo [ERROR] requirements.txt not found in: %CD%
    exit /b 1
)

set "TRY=1"
:retry_pip_upgrade
python -m pip install --upgrade pip >nul 2>&1
if not errorlevel 1 goto pip_upgrade_ok
if %TRY% GEQ 3 (
    echo [ERROR] Failed to upgrade pip after 3 attempts.
    exit /b 1
)
set /a TRY+=1
echo [WARN] pip upgrade failed. Retrying (%TRY%/3)...
timeout /t 3 /nobreak >nul
goto retry_pip_upgrade

:pip_upgrade_ok
set "TRY=1"
:retry_requirements
python -m pip install -r requirements.txt >nul 2>&1
if not errorlevel 1 goto requirements_ok
if %TRY% GEQ 3 (
    echo [ERROR] Failed to install requirements after 3 attempts.
    exit /b 1
)
set /a TRY+=1
echo [WARN] requirements install failed. Retrying (%TRY%/3)...
timeout /t 3 /nobreak >nul
goto retry_requirements

:requirements_ok
set "REQUIREMENTS_OK=1"
exit /b 0

:final_validation
echo.
echo ================================
echo Final validation
echo ================================

set "VALIDATION_FAILED=0"

call :is_cloudflared_available
if errorlevel 1 (
    echo [ERROR] cloudflared is not callable.
    set "VALIDATION_FAILED=1"
) else (
    echo [OK] cloudflared is callable.
)

call :is_python_available
if errorlevel 1 (
    echo [ERROR] python is not callable.
    set "VALIDATION_FAILED=1"
) else (
    echo [OK] python is callable.
)

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available.
    set "VALIDATION_FAILED=1"
) else (
    echo [OK] pip is available.
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python is not visible on PATH.
    set "VALIDATION_FAILED=1"
) else (
    echo [OK] python is visible on PATH.
)

if "%REQUIREMENTS_OK%"=="1" (
    echo [OK] requirements.txt dependencies installed.
) else (
    echo [ERROR] requirements.txt dependencies were not confirmed as installed.
    set "VALIDATION_FAILED=1"
)

if "%VALIDATION_FAILED%"=="1" (
    echo [ERROR] Environment validation failed.
    exit /b 1
)

echo [OK] Environment validation passed.
exit /b 0
