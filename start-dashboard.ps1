# Launch Sol Plaatje A — Predictive HPC Cluster AIOps Backend (:8000) & React Frontend (:5173)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$Root\backend\.venv\Scripts\python.exe")) {
    Write-Host "Creating Python virtual environment and installing backend packages..." -ForegroundColor Yellow
    python -m venv "$Root\backend\.venv"
    & "$Root\backend\.venv\Scripts\pip.exe" install -r "$Root\backend\requirements.txt"
}

if (-not (Test-Path "$Root\frontend\node_modules")) {
    Write-Host "Installing React frontend npm packages (first-time setup)..." -ForegroundColor Yellow
    Push-Location "$Root\frontend"
    npm install
    Pop-Location
}

Write-Host "Starting FastAPI Real-Time HPC Pipeline on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Write-Host "Starting React Vite Dashboard on http://localhost:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev"

Write-Host "Both servers launching! Open http://localhost:5173 in your browser." -ForegroundColor Yellow
