$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "     Starting CryptoGraph Analytics Environment    " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Start Backend
Write-Host "[*] Initializing Backend Server (FastAPI)..." -ForegroundColor Yellow
$venvPython = "$PSScriptRoot\backend\venv\Scripts\python.exe"
$venvValid = $false
if (Test-Path $venvPython) {
    $testVenv = & $venvPython --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $venvValid = $true
    }
}

if (-not $venvValid) {
    Write-Host "[!] Virtual environment is missing or broken. Please run install_windows.ps1 first." -ForegroundColor Red
    Pause
    exit 1
}
$env:PYTHONPATH = "$PSScriptRoot\backend;$PSScriptRoot"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"cd /d `"$PSScriptRoot\backend`" && set API_KEY=dev_default_key_123 && .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-use-colors`"" -WindowStyle Normal

# Wait briefly
Start-Sleep -Seconds 2

# Start Frontend
Write-Host "[*] Initializing Frontend Server (Next.js)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"cd /d `"$PSScriptRoot\frontend`" && set NEXT_PUBLIC_API_KEY=dev_default_key_123 && set API_KEY=dev_default_key_123 && npm run dev`"" -WindowStyle Normal

# Wait for frontend to compile
Write-Host "[*] Waiting for servers to initialize (5s)..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Launch Browser
Write-Host "[*] Launching Browser..." -ForegroundColor Green
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "   All systems running!                            " -ForegroundColor Cyan
Write-Host "   (Backend and Frontend are running in separate   " -ForegroundColor Cyan
Write-Host "    terminal windows)                              " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
