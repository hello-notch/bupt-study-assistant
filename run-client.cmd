@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "ELECTRON_CMD=%PROJECT_ROOT%client\node_modules\.bin\electron.cmd"

if not exist "%ELECTRON_CMD%" (
    echo [ERROR] Client dependencies are missing.
    echo Run: cd /d "%PROJECT_ROOT%client" ^&^& pnpm install
    pause
    exit /b 1
)

echo.
echo Starting YouXueBan client...
echo Campus accounts and model settings stay on this device.
echo.
cd /d "%PROJECT_ROOT%client"
call "%ELECTRON_CMD%" "."
exit /b %ERRORLEVEL%
