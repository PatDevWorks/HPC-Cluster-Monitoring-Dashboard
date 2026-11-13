
# ============================================================
# SOL PLAATJE A - HPC AIOps DASHBOARD LAUNCHER
# SSH Tunnel + Prometheus + LSTM V8 + FastAPI + React
# ============================================================

$ErrorActionPreference = "Stop"

# PROJECT CONFIGURATION
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$SshKey = "$env:USERPROFILE\Downloads\id_ed25519"
$SshHost = "ubuntu@196.24.241.73"
$SshPort = 443

$PrometheusPort = 9090
$LstmPort = 8102

# ------------------------------------------------------------
# 1. CHECK REQUIREMENTS
# ------------------------------------------------------------

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
    npm install
    Pop-Location
}

# ------------------------------------------------------------
# 2. GET LSTM V8 API KEY
# ------------------------------------------------------------

Write-Host "`nLSTM V8 authentication" -ForegroundColor Cyan

$SecureKey = Read-Host "Enter your existing LSTM V8 API key" -AsSecureString

$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)

try {
    $LstmApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($BSTR)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
}

if ([string]::IsNullOrWhiteSpace($LstmApiKey)) {
    throw "LSTM V8 API key cannot be empty."
}

# ------------------------------------------------------------
# 3. START SSH TUNNEL
# ------------------------------------------------------------

Write-Host "`nChecking SSH tunnel..." -ForegroundColor Cyan

$PromListener = Get-NetTCPConnection -LocalPort 9090 -State Listen -ErrorAction SilentlyContinue
$LstmListener = Get-NetTCPConnection -LocalPort 8102 -State Listen -ErrorAction SilentlyContinue

if ($PromListener -and $LstmListener) {
    Write-Host "Both tunnel ports are already listening. Reusing them." -ForegroundColor Green
}
elseif ($PromListener -or $LstmListener) {
    throw "Only one tunnel port is occupied. Check existing SSH tunnels and free ports 9090 and 8102 before restarting."
}
else {
    Write-Host "Opening SSH tunnel to HPC headnode..." -ForegroundColor Yellow

    $TunnelCommand = "ssh -N -o ExitOnForwardFailure=yes -p $SshPort -i `"$SshKey`" -L 9090:127.0.0.1:9090 -L 8102:127.0.0.1:8102 $SshHost"

    $TunnelProcess = Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        $TunnelCommand
    ) -PassThru

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
        throw "SSH tunnel failed to establish both connections."
    }

    Write-Host "SSH tunnels established." -ForegroundColor Green
}

# ------------------------------------------------------------
# 4. VERIFY PROMETHEUS
# ------------------------------------------------------------

Write-Host "`nChecking Prometheus..." -ForegroundColor Cyan

try {
    $Prometheus = Invoke-WebRequest `
        -Uri "http://127.0.0.1:9090/-/ready" `
        -TimeoutSec 8 `
        -UseBasicParsing

    Write-Host "Prometheus is responding." -ForegroundColor Green
}
catch {
    Write-Host "WARNING: Prometheus readiness check failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ------------------------------------------------------------
# 5. VERIFY LSTM V8
# ------------------------------------------------------------

Write-Host "`nChecking LSTM V8..." -ForegroundColor Cyan

try {
    $Lstm = Invoke-RestMethod `
        -Uri "http://127.0.0.1:8102/ready" `
        -TimeoutSec 8

    Write-Host "LSTM V8 API responded. Models loaded: $($Lstm.loaded)" -ForegroundColor Green
    Write-Host "Model count: $($Lstm.model_count)" -ForegroundColor Green
}
catch {
    Write-Host "WARNING: LSTM V8 readiness check failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ------------------------------------------------------------
# 6. START FASTAPI BACKEND
# ------------------------------------------------------------

Write-Host "`nStarting FastAPI backend..." -ForegroundColor Cyan

$SafeApiKey = $LstmApiKey.Replace("'", "''")

$BackendCommand = "Set-Location '$Root\backend'; `$env:LSTM_V8_API_URL='http://127.0.0.1:8102'; `$env:LSTM_V8_API_KEY='$SafeApiKey'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    $BackendCommand
)

Write-Host "FastAPI backend launched." -ForegroundColor Green

# ------------------------------------------------------------
# 7. START REACT FRONTEND
# ------------------------------------------------------------

Write-Host "`nStarting React frontend..." -ForegroundColor Cyan

$FrontendCommand = "Set-Location '$Root\frontend'; npm run dev"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    $FrontendCommand
)

Write-Host "React frontend launched." -ForegroundColor Green

# ------------------------------------------------------------
# 8. DISPLAY SERVICE INFORMATION
# ------------------------------------------------------------

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host " SOL PLAATJE A - HPC AIOps ENVIRONMENT" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "Prometheus: http://localhost:9090" -ForegroundColor White
Write-Host "LSTM V8:    http://localhost:8102/ready" -ForegroundColor White
Write-Host "FastAPI:    http://localhost:8000" -ForegroundColor White
Write-Host "API Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host "React:      http://localhost:5173" -ForegroundColor White

Write-Host "`nAll launch commands have been issued." -ForegroundColor Green
Write-Host "Keep the SSH tunnel terminal open." -ForegroundColor Yellow

Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"
