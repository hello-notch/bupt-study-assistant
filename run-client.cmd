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

set "YOUXUEBAN_CLIENT_URL=http://127.0.0.1:8787"
echo.
echo Starting YouXueBan client...
echo Make sure run-server.cmd is already running.
echo.
cd /d "%PROJECT_ROOT%client"
call "%ELECTRON_CMD%" "."
exit /b %ERRORLEVEL%
