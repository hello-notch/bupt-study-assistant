@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "VITE_CMD=%PROJECT_ROOT%web\node_modules\.bin\vite.cmd"

if not exist "%VITE_CMD%" (
    echo [ERROR] Server dependencies are missing.
    echo Run: cd /d "%PROJECT_ROOT%web" ^&^& pnpm install
    pause
    exit /b 1
)

echo.
echo YouXueBan server is starting on:
echo   This computer: http://[::1]:8787/
echo   IPv6 clients:  http://[2001:da8:215:8f02:7f5b:8f99:8107:90c3]:8787/
echo This entry provides authentication, portal, activity, academic,
echo electricity and AI proxy APIs. Press Ctrl+C to stop.
echo.
cd /d "%PROJECT_ROOT%web"
call "%VITE_CMD%" --host :: --port 8787 --strictPort
exit /b %ERRORLEVEL%
