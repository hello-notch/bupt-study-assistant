@echo off
setlocal
where node.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Install Node.js and pnpm first.
    pause
    exit /b 1
)
node.exe "%~dp0scripts\start-client.cjs"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
