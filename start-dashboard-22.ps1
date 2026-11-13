
# ============================================================
# SOL PLAATJE A - HPC AIOps DASHBOARD LAUNCHER
# SSH PORT 22
#
# SSH Tunnel + Prometheus + LSTM V8 + FastAPI + React
# ============================================================

$ErrorActionPreference = "Stop"

# ---------------- PROJECT CONFIGURATION ----------------

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$SshKey = "$env:USERPROFILE\Downloads\id_ed25519"
$SshHost = "ubuntu@196.24.241.73"
$SshPort = 22

$PrometheusPort = 9090
$LstmPort = 8102
$BackendPort = 8000
$FrontendPort = 5173

# ---------------- CHECK REQUIREMENTS ----------------

Write-Host "`nChecking project requirements..." -ForegroundColor Cyan

if (-not (Test-Path $SshKey)) {
    throw "SSH key not found: $SshKey"
}

if (-not (Test-Path "$Root\backend\.venv\Scripts\python.exe")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow

    python -m venv "$Root\backend\.venv"

    & "$Root\backend\.venv\Scripts\pip.exe" install -r "$Root\backend\requirements.txt"
}

if (-not (Test-Path "$Root\frontend\node_modules")) {
    Write-Host "Installing frontend packages..." -ForegroundColor Yellow

    Push-Location "$Root\frontend"
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

# ---------------- GET LSTM V8 API KEY ----------------

# ---------------- LSTM V8 API CONFIGURATION ----------------

$LstmApiKey = "0350e2e004e0aa23817ffa4a8ba2b4bb583eb477dc13a1c267dbc4e5dc7a27a2"

if ([string]::IsNullOrWhiteSpace($LstmApiKey) -or
    $LstmApiKey -eq "PASTE_YOUR_EXISTING_LSTM_V8_API_KEY_HERE") {
    throw "Configure your LSTM V8 API key in this script first."
}
# ---------------- CHECK EXISTING TUNNELS ----------------

Write-Host "`nChecking tunnel ports..." -ForegroundColor Cyan

$PromListener = Get-NetTCPConnection -LocalPort $PrometheusPort -State Listen -ErrorAction SilentlyContinue
$LstmListener = Get-NetTCPConnection -LocalPort $LstmPort -State Listen -ErrorAction SilentlyContinue

if ($PromListener -and $LstmListener) {
    Write-Host "Both tunnel ports are already listening. Reusing them." -ForegroundColor Green
}
elseif ($PromListener -or $LstmListener) {
    throw "Only one tunnel port is occupied. Check existing tunnels and free ports 9090 and 8102."
}
else {

    # ---------------- START SSH TUNNEL ----------------

    Write-Host "`nStarting SSH tunnel on port 22..." -ForegroundColor Cyan

    $TunnelCommand = "ssh -N -o ExitOnForwardFailure=yes -p 22 -i `"$SshKey`" -L 9090:127.0.0.1:9090 -L 8102:127.0.0.1:8102 $SshHost"

    $TunnelProcess = Start-Process powershell.exe `
        -ArgumentList @("-NoExit", "-Command", $TunnelCommand) `
        -PassThru

    $TunnelReady = $false

    for ($i = 0; $i -lt 30; $i++) {

        Start-Sleep -Seconds 1

        $PromListener = Get-NetTCPConnection -LocalPort 9090 -State Listen -ErrorAction SilentlyContinue
        $LstmListener = Get-NetTCPConnection -LocalPort 8102 -State Listen -ErrorAction SilentlyContinue

        if ($PromListener -and $LstmListener) {
            $TunnelReady = $true
            break
        }

        if ($TunnelProcess.HasExited) {
            throw "SSH tunnel process exited. Check the SSH terminal."
        }
    }

    if (-not $TunnelReady) {
        throw "SSH tunnel failed to establish both connections on port 22."
    }

    Write-Host "SSH tunnel established." -ForegroundColor Green
}

# ---------------- VERIFY PROMETHEUS ----------------

Write-Host "`nChecking Prometheus..." -ForegroundColor Cyan

try {
    Invoke-WebRequest `
        -Uri "http://127.0.0.1:9090/-/ready" `
        -TimeoutSec 8 `
        -UseBasicParsing | Out-Null

    Write-Host "Prometheus is ready." -ForegroundColor Green
}
catch {
    Write-Host "WARNING: Prometheus check failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ---------------- VERIFY LSTM V8 ----------------

Write-Host "`nChecking LSTM V8..." -ForegroundColor Cyan

try {
    $Lstm = Invoke-RestMethod `
        -Uri "http://127.0.0.1:8102/ready" `
        -TimeoutSec 8

    Write-Host "LSTM V8 responded. Models loaded: $($Lstm.loaded)" -ForegroundColor Green
    Write-Host "Model count: $($Lstm.model_count)" -ForegroundColor Green
}
catch {
    Write-Host "WARNING: LSTM V8 check failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ---------------- START FASTAPI ----------------

# ---------------- START FASTAPI ----------------

Write-Host "`nStarting FastAPI backend..." -ForegroundColor Cyan

# Set environment variables in the launcher process.
# The child PowerShell process inherits them.

$env:LSTM_V8_API_URL = "http://127.0.0.1:8102"
$env:LSTM_V8_API_KEY = $LstmApiKey
$env:HPC_SSH_HOST = "196.24.241.73"
$env:HPC_SSH_USER = "ubuntu"
$env:HPC_SSH_PORT = "22"
$env:HPC_SSH_KEY_PATH = "$env:USERPROFILE\Downloads\id_ed25519"
$BackendCommand = "Set-Location '$Root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    $BackendCommand
)

Write-Host "FastAPI backend launched." -ForegroundColor Green

# ---------------- START REACT ----------------

Write-Host "`nStarting React frontend..." -ForegroundColor Cyan

$FrontendCommand = "Set-Location '$Root\frontend'; npm run dev"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    $FrontendCommand
)

Write-Host "React frontend launched." -ForegroundColor Green

# ---------------- DISPLAY STATUS ----------------

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host " SOL PLAATJE A - HPC AIOps ENVIRONMENT" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "SSH:        Port 22" -ForegroundColor White
Write-Host "Prometheus: http://localhost:9090" -ForegroundColor White
Write-Host "LSTM V8:    http://localhost:8102/ready" -ForegroundColor White
Write-Host "FastAPI:    http://localhost:8000" -ForegroundColor White
Write-Host "API Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host "React:      http://localhost:5173" -ForegroundColor White

Write-Host "`nKeep the SSH tunnel terminal open." -ForegroundColor Yellow

Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"
