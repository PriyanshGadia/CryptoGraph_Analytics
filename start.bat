@echo off
title CryptoGraph Analytics Launcher
color 0b

echo ===================================================
echo     Starting CryptoGraph Analytics Environment
echo ===================================================
echo.

:: Start Backend
echo [*] Initializing Backend Server (FastAPI)...
start "CryptoGraph Backend" cmd /c "cd /d "%~dp0backend" && set PYTHONPATH=%~dp0backend;%~dp0 && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: Start Frontend
echo [*] Initializing Frontend Server (Next.js)...
start "CryptoGraph Frontend" cmd /c "cd /d "%~dp0frontend" && npm run dev"

:: Wait for frontend to compile and servers to start
echo [*] Waiting for servers to initialize...
timeout /t 5 /nobreak >nul

:: Launch browser
echo [*] Launching Browser...
start http://localhost:3000

echo.
echo ===================================================
echo   All systems running! 
echo   (Backend and Frontend are running in separate 
echo    terminal windows)
echo ===================================================
pause
