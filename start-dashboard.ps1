param(
    [string]$SshHost = "",
    [string]$SshUser = "",
    [int]$SshPort = 0,
    [string]$SshKey = "",
    [string]$V7ApiKey = "",
    [string]$LstmApiKey = "",
    [switch]$SkipPrompt,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$EnvFile = Join-Path $BackendDir ".env"
$DbFile = Join-Path $BackendDir "hpc_aiops.db"

function Load-DotEnv([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    foreach ($rawLine in (Get-Content -Path $Path -Encoding UTF8)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { continue }
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        $map[$k] = $v
    }
    return $map
}

function Get-ConfigValue([string]$ParamVal, [string]$EnvName, [hashtable]$DotEnvMap, [string]$DefaultVal = "") {
    if ($ParamVal -and $ParamVal.Trim()) { return $ParamVal.Trim() }
    $envVal = [Environment]::GetEnvironmentVariable($EnvName, "Process")
    if (-not $envVal) { $envVal = [Environment]::GetEnvironmentVariable($EnvName, "User") }
    if ($envVal -and $envVal.Trim()) { return $envVal.Trim() }
    if ($DotEnvMap.ContainsKey($EnvName) -and $DotEnvMap[$EnvName]) { return [string]$DotEnvMap[$EnvName] }
    return $DefaultVal
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 1500) {
    if (-not $HostName -or $Port -le 0) { return $false }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($ok -and $client.Connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-HttpReady([string]$Url, [int]$TimeoutSec = 2) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Get-ListenPids([int]$Port) {
    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        return @()
    }
}

function Resolve-SavedSshSettingsFromDb([string]$PythonExe, [string]$DbPath) {
    if (-not (Test-Path $PythonExe) -or -not (Test-Path $DbPath)) { return @{} }
    try {
        $py = "import json, sqlite3, sys; conn=sqlite3.connect(sys.argv[1]); rows=conn.execute('SELECT key, value_json FROM app_settings').fetchall(); print(json.dumps({r[0]: json.loads(r[1]) for r in rows}))"
        $raw = & $PythonExe -c $py $DbPath 2>$null
        if ($LASTEXITCODE -eq 0 -and $raw) {
            $obj = $raw | ConvertFrom-Json
            $res = @{}
            if ($obj.ssh_host) { $res["ssh_host"] = [string]$obj.ssh_host }
            if ($obj.ssh_user) { $res["ssh_user"] = [string]$obj.ssh_user }
            if ($obj.ssh_port) { $res["ssh_port"] = [string]$obj.ssh_port }
            return $res
        }
    } catch {}
    return @{}
}

function Stop-ProcessIfOwnedBySsh([int]$ProcessId) {
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "^ssh(\.exe)?$") {
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 300
            return $true
        }
    } catch {}
    return $false
}

function Stop-ProcessTree([int]$ProcessId) {
    try {
        & taskkill /PID $ProcessId /T /F 2>$null | Out-Null
    } catch {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  HPC AI Operations Dashboard - Unified Launcher" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

if (-not (Test-Path $VenvPython)) {
    throw "Backend virtualenv Python not found at $VenvPython. Create backend/.venv and install requirements first."
}
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    throw "Frontend dependencies missing in $FrontendDir\node_modules. Run 'npm install' in frontend first."
}

$dotEnv = Load-DotEnv $EnvFile
$dbSettings = Resolve-SavedSshSettingsFromDb $VenvPython $DbFile

# Resolve Head Node SSH Configuration
$ResolvedSshHost = Get-ConfigValue $SshHost "HPC_SSH_HOST" $dotEnv ""
if (-not $ResolvedSshHost -and $dbSettings.ContainsKey("ssh_host")) {
    $ResolvedSshHost = $dbSettings["ssh_host"]
}
if (-not $ResolvedSshHost -and -not $SkipPrompt) {
    $enteredHost = Read-Host "Headnode SSH Host/IP (leave blank if Prometheus/Slurm are local)"
    if ($enteredHost) { $ResolvedSshHost = $enteredHost.Trim() }
}

$ResolvedSshUser = Get-ConfigValue $SshUser "HPC_SSH_USER" $dotEnv ""
if (-not $ResolvedSshUser -and $dbSettings.ContainsKey("ssh_user")) {
    $ResolvedSshUser = $dbSettings["ssh_user"]
}
if (-not $ResolvedSshUser) { $ResolvedSshUser = "ubuntu" }

$ResolvedSshPort = $SshPort
if ($ResolvedSshPort -le 0) {
    $envPortStr = Get-ConfigValue "" "HPC_SSH_PORT" $dotEnv ""
    if (-not $envPortStr -and $dbSettings.ContainsKey("ssh_port")) { $envPortStr = $dbSettings["ssh_port"] }
    if ($envPortStr -match "^\d+$") { $ResolvedSshPort = [int]$envPortStr }
}
if ($ResolvedSshHost -and $ResolvedSshPort -le 0) {
    foreach ($candPort in @(443, 22)) {
        if (Test-TcpPort $ResolvedSshHost $candPort 1500) {
            $ResolvedSshPort = $candPort
            break
        }
    }
    if ($ResolvedSshPort -le 0) { $ResolvedSshPort = 443 }
} elseif ($ResolvedSshHost -and $ResolvedSshPort -gt 0 -and -not (Test-TcpPort $ResolvedSshHost $ResolvedSshPort 1500)) {
    foreach ($altPort in @(443, 22)) {
        if ($altPort -ne $ResolvedSshPort -and (Test-TcpPort $ResolvedSshHost $altPort 1500)) {
            Write-Host "[WARN] Port $ResolvedSshPort unreachable on $ResolvedSshHost; using open SSH port $altPort." -ForegroundColor Yellow
            $ResolvedSshPort = $altPort
            break
        }
    }
}
if ($ResolvedSshPort -le 0) { $ResolvedSshPort = 443 }

$ResolvedSshKey = Get-ConfigValue $SshKey "HPC_SSH_KEY_PATH" $dotEnv ""
if (-not $ResolvedSshKey) {
    $keyCandidates = @(
        (Join-Path $HOME ".ssh\id_ed25519"),
        (Join-Path $HOME ".ssh\id_rsa"),
        (Join-Path $HOME "Downloads\id_ed25519"),
        (Join-Path $HOME "Downloads\id_rsa")
    ) | Where-Object { Test-Path $_ }
    if ($ResolvedSshHost -and $keyCandidates.Count -gt 1) {
        foreach ($cand in $keyCandidates) {
            & ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 -p $ResolvedSshPort -i $cand "${ResolvedSshUser}@${ResolvedSshHost}" "true" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $ResolvedSshKey = $cand
                break
            }
        }
    }
    if (-not $ResolvedSshKey -and $keyCandidates.Count -gt 0) {
        $ResolvedSshKey = $keyCandidates[0]
    }
}

$TunnelProc = $null
$BackendProc = $null
$FrontendProc = $null

try {
    # 1. Verify / start Prometheus on Headnode and auto-establish SSH port-forwards (9090, 8101, 8102)
    $ForwardPorts = @()
    if ($ResolvedSshHost) {
        Write-Host "[1/4] Checking cluster services on ${ResolvedSshUser}@${ResolvedSshHost}:${ResolvedSshPort}..." -ForegroundColor Cyan
        $sshCmdArgs = @(
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=6",
            "-p", "$ResolvedSshPort"
        )
        if ($ResolvedSshKey) { $sshCmdArgs += @("-i", $ResolvedSshKey) }
        $sshTarget = "${ResolvedSshUser}@${ResolvedSshHost}"

        $remoteProbeScript = @'
if ! curl -sf http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
  systemctl is-active --quiet prometheus 2>/dev/null || sudo -n systemctl start prometheus 2>/dev/null || true
  command -v docker >/dev/null 2>&1 && docker start prometheus >/dev/null 2>&1 || true
  sleep 2
fi
PROM=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9090/-/ready || echo 000)
V7=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8101/ready || echo 000)
LSTM=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8102/ready || echo 000)
SLURM=$(sinfo -h -o '%a' >/dev/null 2>&1 && echo up || echo down)
echo "PROM=$PROM V7=$V7 LSTM=$LSTM SLURM=$SLURM"
'@ -replace "`r`n", "`n"

        $probeLine = ""
        try {
            $probeRaw = & ssh @sshCmdArgs $sshTarget $remoteProbeScript 2>&1
            $matchObj = $probeRaw | Select-String -Pattern "PROM=" | Select-Object -Last 1
            if ($matchObj) {
                $probeLine = $matchObj.Line
                Write-Host "      Cluster telemetry probe: $probeLine" -ForegroundColor Gray
            } else {
                Write-Host "      [WARN] Could not parse SSH cluster probe output: $probeRaw" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "      [WARN] SSH cluster probe error: $($_.Exception.Message)" -ForegroundColor Yellow
        }

        $serviceChecks = @(
            @{ Port = 9090; Url = "http://127.0.0.1:9090/-/ready"; Name = "Prometheus"; AlwaysForward = $true },
            @{ Port = 8101; Url = "http://127.0.0.1:8101/ready"; Name = "V7 Isolation Forest"; AlwaysForward = ($probeLine -match "V7=200") },
            @{ Port = 8102; Url = "http://127.0.0.1:8102/ready"; Name = "LSTM V8"; AlwaysForward = ($probeLine -match "LSTM=200") }
        )

        foreach ($svc in $serviceChecks) {
            $p = $svc.Port
            $isHealthy = Test-HttpReady $svc.Url 2
            if ($isHealthy -and -not $ForceRestart) {
                Write-Host "      [OK] $($svc.Name) already responding on localhost:$p" -ForegroundColor Green
                continue
            }
            $existingPids = Get-ListenPids $p
            if ($existingPids.Count -gt 0) {
                $freed = $false
                foreach ($epid in $existingPids) {
                    if (Stop-ProcessIfOwnedBySsh $epid) {
                        $freed = $true
                        Write-Host "      Cleaned stale SSH tunnel PID $epid on port $p" -ForegroundColor Yellow
                    }
                }
                if (-not $freed -and (Get-ListenPids $p).Count -gt 0) {
                    Write-Host "      [WARN] Port $p in use by non-SSH PID $($existingPids -join ','); skipping tunnel for $p" -ForegroundColor Yellow
                    continue
                }
            }
            if ($svc.AlwaysForward -or -not $probeLine) {
                $ForwardPorts += $p
            }
        }

        if ($ForwardPorts.Count -gt 0) {
            $tunnelArgs = @(
                "-N", "-T",
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-p", "$ResolvedSshPort"
            )
            if ($ResolvedSshKey) { $tunnelArgs += @("-i", $ResolvedSshKey) }
            foreach ($fp in $ForwardPorts) {
                $tunnelArgs += @("-L", "${fp}:127.0.0.1:${fp}")
            }
            $tunnelArgs += $sshTarget

            Write-Host "      Starting unified SSH tunnel for ports: $($ForwardPorts -join ', ')..." -ForegroundColor Cyan
            $TunnelProc = Start-Process -FilePath "ssh" -ArgumentList $tunnelArgs -WindowStyle Hidden -PassThru

            $deadline = (Get-Date).AddSeconds(10)
            while ((Get-Date) -lt $deadline) {
                if ($TunnelProc.HasExited) {
                    Write-Host "      [WARN] SSH tunnel exited early (code $($TunnelProc.ExitCode))." -ForegroundColor Yellow
                    break
                }
                if (Test-HttpReady "http://127.0.0.1:9090/-/ready" 1) { break }
                Start-Sleep -Milliseconds 400
            }
        }
    } else {
        Write-Host "[1/4] No SSH gateway host configured; checking local Prometheus/ML services..." -ForegroundColor Yellow
    }

    # 2. Export Live Cluster & Model Environment Variables for FastAPI Backend
    Write-Host "[2/4] Configuring backend environment variables..." -ForegroundColor Cyan
    $PromUrl = Get-ConfigValue "" "PROMETHEUS_URL" $dotEnv "http://localhost:9090"
    $env:PROMETHEUS_URL = $PromUrl
    if ($ResolvedSshHost) {
        $env:HPC_SSH_HOST = $ResolvedSshHost
        $env:HPC_SSH_USER = $ResolvedSshUser
        $env:HPC_SSH_PORT = [string]$ResolvedSshPort
        if ($ResolvedSshKey) { $env:HPC_SSH_KEY_PATH = $ResolvedSshKey }
    }

    if (Test-HttpReady "http://127.0.0.1:9090/-/ready" 2) {
        Write-Host "      [OK] Prometheus live at $PromUrl" -ForegroundColor Green
    } else {
        Write-Host "      [WARN] Prometheus not responding at $PromUrl yet (backend will auto-switch once live)." -ForegroundColor Yellow
    }

    $ResolvedV7Url = Get-ConfigValue "" "V7_API_URL" $dotEnv ""
    if (-not $ResolvedV7Url -and (Test-HttpReady "http://127.0.0.1:8101/ready" 2)) {
        $ResolvedV7Url = "http://localhost:8101"
    }
    if ($ResolvedV7Url) {
        $env:V7_API_URL = $ResolvedV7Url
        $ResolvedV7Key = Get-ConfigValue $V7ApiKey "V7_API_KEY" $dotEnv ""
        if ($ResolvedV7Key) { $env:V7_API_KEY = $ResolvedV7Key }
        Write-Host "      [OK] V7 Isolation Forest API configured: $ResolvedV7Url" -ForegroundColor Green
    }

    $ResolvedLstmUrl = Get-ConfigValue "" "LSTM_V8_API_URL" $dotEnv ""
    if (-not $ResolvedLstmUrl -and (Test-HttpReady "http://127.0.0.1:8102/ready" 2)) {
        $ResolvedLstmUrl = "http://localhost:8102"
    }
    if ($ResolvedLstmUrl) {
        $env:LSTM_V8_API_URL = $ResolvedLstmUrl
        $ResolvedLstmKey = Get-ConfigValue $LstmApiKey "LSTM_V8_API_KEY" $dotEnv ""
        if (-not $ResolvedLstmKey -and -not $SkipPrompt) {
            $optKey = Read-Host "Optional LSTM V8 API key (press Enter to skip or store in backend/.env)"
            if ($optKey) { $ResolvedLstmKey = $optKey.Trim() }
        }
        if ($ResolvedLstmKey) { $env:LSTM_V8_API_KEY = $ResolvedLstmKey }
        Write-Host "      [OK] LSTM V8 API configured: $ResolvedLstmUrl" -ForegroundColor Green
    }

    # 3. Clean stale dashboard servers on 8000 / 5173 when requested or start fresh
    foreach ($svcPort in @(8000, 5173)) {
        $listenPids = Get-ListenPids $svcPort
        if ($listenPids.Count -gt 0) {
            if ($ForceRestart) {
                foreach ($pId in $listenPids) {
                    Stop-ProcessTree $pId
                }
                Start-Sleep -Milliseconds 500
            } else {
                throw "Port $svcPort is already in use by PID $($listenPids -join ','). Stop it or pass -ForceRestart."
            }
        }
    }

    Write-Host "[3/4] Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Cyan
    $BackendProc = Start-Process -FilePath $VenvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $BackendDir `
        -PassThru

    $apiDeadline = (Get-Date).AddSeconds(20)
    $apiReady = $false
    while ((Get-Date) -lt $apiDeadline) {
        if ($BackendProc.HasExited) {
            throw "Backend server exited unexpectedly (code $($BackendProc.ExitCode))."
        }
        if (Test-HttpReady "http://127.0.0.1:8000/api/health" 2) {
            $apiReady = $true
            break
        }
        Start-Sleep -Milliseconds 400
    }
    if (-not $apiReady) {
        throw "Backend did not become healthy on http://127.0.0.1:8000/api/health within 20 seconds."
    }

    Write-Host "[4/4] Starting React UI (Vite) on http://localhost:5173..." -ForegroundColor Cyan
    $FrontendProc = Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
        -WorkingDirectory $FrontendDir `
        -PassThru

    Write-Host ""
    Write-Host "=====================================================" -ForegroundColor Green
    Write-Host "  Dashboard Running!" -ForegroundColor Green
    Write-Host "  UI:         http://localhost:5173" -ForegroundColor White
    Write-Host "  API Health: http://127.0.0.1:8000/api/health" -ForegroundColor White
    Write-Host "  Press Ctrl+C in this window to stop all services." -ForegroundColor Gray
    Write-Host "=====================================================" -ForegroundColor Green

    while (-not $BackendProc.HasExited -and -not $FrontendProc.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nStopping launched services..." -ForegroundColor Yellow
    foreach ($proc in @($FrontendProc, $BackendProc, $TunnelProc)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-ProcessTree $proc.Id
        }
    }
}
