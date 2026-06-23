<#
.SYNOPSIS
    CryptoGraph Analytics Windows Installer & Runner
.DESCRIPTION
    Automatically installs dependencies (Python, Node.js) via Winget if missing.
    Sets up the Python virtual environment, installs Node modules, and runs the servers.
#>

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    CryptoGraph Analytics Windows Setup & Run"
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

function Check-Command {
    param ([string]$Command)
    $path = Get-Command $Command -ErrorAction SilentlyContinue
    return $null -ne $path
}

# 1. Check & Install Python
if (-not (Check-Command "python")) {
    Write-Host "[!] Python not found. Installing via Winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.11 --exact --source winget --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "[*] Python is installed." -ForegroundColor Green
}

# 2. Check & Install Node.js
if (-not (Check-Command "node")) {
    Write-Host "[!] Node.js not found. Installing via Winget..." -ForegroundColor Yellow
    winget install --id OpenJS.NodeJS -e --source winget --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "[*] Node.js is installed." -ForegroundColor Green
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Get-PythonExecutable {
    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) { return "py -3" }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python -and $python.Length -gt 0) {
        $test = & python --version 2>&1
        if ($LASTEXITCODE -eq 0) { return "python" }
    }

    $wingetPath = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    if (Test-Path $wingetPath) { return "& `"$wingetPath`"" }

    $wingetPath2 = "$env:PROGRAMFILES\Python311\python.exe"
    if (Test-Path $wingetPath2) { return "& `"$wingetPath2`"" }

    return $null
}

# 3. Setup Python Backend
Write-Host "[*] Setting up Backend Environment..." -ForegroundColor Cyan
Set-Location "$ScriptDir\backend"

$pyCmd = Get-PythonExecutable
if (-not $pyCmd) {
    Write-Host "[!] Could not find a valid Python executable. If you just installed Python, please restart this terminal and run the script again." -ForegroundColor Red
    Pause
    exit 1
}

$venvValid = $false
if (Test-Path "venv\Scripts\python.exe") {
    $testVenv = & .\venv\Scripts\python.exe --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $venvValid = $true
    }
}

if (-not $venvValid) {
    if (Test-Path "venv") {
        Write-Host "    Found broken virtual environment, recreating..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force "venv"
    }
    Write-Host "    Creating virtual environment using $pyCmd..."
    Invoke-Expression "$pyCmd -m venv venv"
}
Write-Host "    Installing Python requirements (this may take a while)..."
.\venv\Scripts\python.exe -m pip install --upgrade pip > $null
.\venv\Scripts\python.exe -m pip install -r requirements.txt > $null

# 4. Setup Node Frontend
Write-Host "[*] Setting up Frontend Environment..." -ForegroundColor Cyan
Set-Location "$ScriptDir\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "    Installing NPM packages..."
    npm install
}

# 5. Run Everything
Write-Host ""
Write-Host "[*] Launching Servers..." -ForegroundColor Green

# Launch backend in a new window using the venv python
$env:PYTHONPATH = "$ScriptDir\backend;$ScriptDir"
Start-Process cmd -ArgumentList "/k `"cd /d `"$ScriptDir\backend`" && .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`"" -WindowStyle Normal

# Launch frontend in a new window
Start-Process cmd -ArgumentList "/k `"cd /d `"$ScriptDir\frontend`" && npm run dev`"" -WindowStyle Normal

Start-Sleep -Seconds 8

# Launch browser
Start-Process "http://localhost:3000"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  All systems running! "
Write-Host "  (Check the newly opened terminal windows for logs)"
Write-Host "===================================================" -ForegroundColor Cyan
Pause
