@echo off
title CryptoGraph Analytics Launcher
color 0b

echo ===================================================
echo     Starting CryptoGraph Analytics Environment
echo ===================================================
echo.

echo [*] Handing off to the robust PowerShell installer/runner...
PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"

pause
