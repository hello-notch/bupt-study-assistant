@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "WEB_ROOT=%PROJECT_ROOT%web"
set "VITE_SCRIPT=%WEB_ROOT%\node_modules\vite\bin\vite.js"
set "PORT=5173"

if not "%~1"=="" set "PORT=%~1"

where node.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Install Node.js 20 or newer.
    pause
    exit /b 1
)

if not exist "%VITE_SCRIPT%" (
    echo [ERROR] Frontend dependencies are missing.
    echo Open a terminal in "%WEB_ROOT%" and run: pnpm install
    pause
    exit /b 1
)

echo.
echo YouXueBan frontend is starting...
echo URL: http://127.0.0.1:%PORT%/
echo Press Ctrl+C to stop.
echo.

cd /d "%WEB_ROOT%"
node.exe "%VITE_SCRIPT%" --host 127.0.0.1 --port "%PORT%" --strictPort
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="-1073741510" exit /b 0
if "%EXIT_CODE%"=="-1" exit /b 0
if "%EXIT_CODE%"=="130" exit /b 0

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Frontend exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
