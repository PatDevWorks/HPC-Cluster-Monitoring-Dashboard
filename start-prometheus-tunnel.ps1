<#
.SYNOPSIS
    Opens a standalone SSH port forward for Prometheus only.
.DESCRIPTION
    Keeps the tunnel running in this window until Ctrl+C. Reads SSH settings from parameters,
    environment variables, backend/.env, then saved dashboard settings.
.EXAMPLE
    .\start-prometheus-tunnel.ps1
.EXAMPLE
    .\start-prometheus-tunnel.ps1 -SshHost 196.24.241.73 -SshUser ubuntu -SshPort 22 -SshKey "$HOME\Downloads\id_ed25519"
#>
param(
    [string]$SshHost = "",
    [string]$SshUser = "",
    [int]$SshPort = 0,
    [string]$SshKey = "",
    [int]$LocalPort = 9090,
    [string]$RemoteHost = "127.0.0.1",
    [int]$RemotePort = 9090,
    [switch]$SkipPrompt
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$EnvFile = Join-Path $RepoRoot "backend\.env"
$DbFile = Join-Path $RepoRoot "backend\hpc_aiops.db"
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"

function Load-DotEnv([string]$Path) {
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    foreach ($rawLine in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $map[$key] = $value
    }
    return $map
}

function Get-ConfigValue([string]$ParamValue, [string]$EnvName, [hashtable]$DotEnv, [string]$DefaultValue = "") {
    if ($ParamValue -and $ParamValue.Trim()) { return $ParamValue.Trim() }
    $envValue = [Environment]::GetEnvironmentVariable($EnvName, "Process")
    if (-not $envValue) { $envValue = [Environment]::GetEnvironmentVariable($EnvName, "User") }
    if ($envValue -and $envValue.Trim()) { return $envValue.Trim() }
    if ($DotEnv.ContainsKey($EnvName) -and $DotEnv[$EnvName]) { return [string]$DotEnv[$EnvName] }
    return $DefaultValue
}

function Get-SavedSshSettings([string]$PythonExe, [string]$DatabasePath) {
    if (-not (Test-Path -LiteralPath $PythonExe) -or -not (Test-Path -LiteralPath $DatabasePath)) { return @{} }
    try {
        $query = "import json,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); r=c.execute('SELECT key,value_json FROM app_settings').fetchall(); print(json.dumps({x[0]:json.loads(x[1]) for x in r}))"
        $raw = & $PythonExe -c $query $DatabasePath 2>$null
        if ($LASTEXITCODE -eq 0 -and $raw) {
            $saved = $raw | ConvertFrom-Json
            $result = @{}
            foreach ($name in @("ssh_host", "ssh_user", "ssh_port")) {
                if ($saved.$name) { $result[$name] = [string]$saved.$name }
            }
            return $result
        }
    } catch {}
    return @{}
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 1500) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect($HostName, $Port, $null, $null)
        if ($pending.AsyncWaitHandle.WaitOne($TimeoutMs, $false) -and $client.Connected) {
            $client.EndConnect($pending)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PrometheusReady([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/-/ready" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Repair-SshPrivateKeyAcl([string]$KeyPath) {
    if (-not $KeyPath -or -not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { return $false }
    try {
        $resolvedPath = (Resolve-Path -LiteralPath $KeyPath).Path
        $currentAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = Get-Acl -LiteralPath $resolvedPath
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleAll($rule) }
        $account = [System.Security.Principal.NTAccount]::new($currentAccount)
        $readRule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $account,
            [System.Security.AccessControl.FileSystemRights]::Read,
            [System.Security.AccessControl.AccessControlType]::Allow
        )
        $acl.AddAccessRule($readRule)
        Set-Acl -LiteralPath $resolvedPath -AclObject $acl
        Write-Host "[OK] SSH key permissions restricted to $currentAccount." -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[WARN] Could not repair SSH key permissions: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

function ConvertTo-ProcessArgument([string]$Value) {
    if ($Value -match '\s|"') { return '"' + $Value.Replace('"', '\"') + '"' }
    return $Value
}

function Stop-ProcessTree([int]$ProcessId) {
    try { & taskkill /PID $ProcessId /T /F 2>$null | Out-Null }
    catch { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }
}

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  HPC AI Operations Dashboard - Prometheus Tunnel" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

if ($LocalPort -lt 1 -or $LocalPort -gt 65535 -or $RemotePort -lt 1 -or $RemotePort -gt 65535) {
    throw "LocalPort and RemotePort must be between 1 and 65535."
}

$dotEnv = Load-DotEnv $EnvFile
$dbSettings = Get-SavedSshSettings $VenvPython $DbFile
$ResolvedSshHost = Get-ConfigValue $SshHost "HPC_SSH_HOST" $dotEnv ""
if (-not $ResolvedSshHost -and $dbSettings.ContainsKey("ssh_host")) { $ResolvedSshHost = $dbSettings["ssh_host"] }
if (-not $ResolvedSshHost -and -not $SkipPrompt) {
    $enteredHost = Read-Host "Headnode SSH Host/IP"
    if ($enteredHost) { $ResolvedSshHost = $enteredHost.Trim() }
}
if (-not $ResolvedSshHost) { throw "No SSH host configured. Set HPC_SSH_HOST in backend/.env or pass -SshHost." }

$ResolvedSshUser = Get-ConfigValue $SshUser "HPC_SSH_USER" $dotEnv ""
if (-not $ResolvedSshUser -and $dbSettings.ContainsKey("ssh_user")) { $ResolvedSshUser = $dbSettings["ssh_user"] }
if (-not $ResolvedSshUser) { $ResolvedSshUser = "ubuntu" }

$ResolvedSshPort = $SshPort
if ($ResolvedSshPort -le 0) {
    $portText = Get-ConfigValue "" "HPC_SSH_PORT" $dotEnv ""
    if (-not $portText -and $dbSettings.ContainsKey("ssh_port")) { $portText = $dbSettings["ssh_port"] }
    if ($portText -match '^\d+$') { $ResolvedSshPort = [int]$portText }
}
if ($ResolvedSshPort -le 0) {
    foreach ($candidatePort in @(443, 22)) {
        if (Test-TcpPort $ResolvedSshHost $candidatePort) { $ResolvedSshPort = $candidatePort; break }
    }
    if ($ResolvedSshPort -le 0) { throw "SSH is unreachable on ports 443 and 22 at $ResolvedSshHost." }
} elseif (-not (Test-TcpPort $ResolvedSshHost $ResolvedSshPort)) {
    $fallbackFound = $false
    foreach ($candidatePort in @(443, 22)) {
        if ($candidatePort -ne $ResolvedSshPort -and (Test-TcpPort $ResolvedSshHost $candidatePort)) {
            Write-Host "[WARN] Port $ResolvedSshPort is unreachable; using open SSH port $candidatePort." -ForegroundColor Yellow
            $ResolvedSshPort = $candidatePort
            $fallbackFound = $true
            break
        }
    }
    if (-not $fallbackFound) { throw "SSH is unreachable on configured port and fallback ports 443/22 at $ResolvedSshHost." }
}

$ResolvedSshKey = Get-ConfigValue $SshKey "HPC_SSH_KEY_PATH" $dotEnv ""
if (-not $ResolvedSshKey) {
    foreach ($candidateKey in @(
        (Join-Path $HOME ".ssh\id_ed25519"),
        (Join-Path $HOME ".ssh\id_rsa"),
        (Join-Path $HOME "Downloads\id_ed25519"),
        (Join-Path $HOME "Downloads\id_rsa")
    )) {
        if (Test-Path -LiteralPath $candidateKey -PathType Leaf) { $ResolvedSshKey = $candidateKey; break }
    }
}
if ($ResolvedSshKey) {
    if (-not (Test-Path -LiteralPath $ResolvedSshKey -PathType Leaf)) { throw "SSH key file not found: $ResolvedSshKey" }
    $ResolvedSshKey = (Resolve-Path -LiteralPath $ResolvedSshKey).Path
    [void](Repair-SshPrivateKeyAcl $ResolvedSshKey)
}

if (Test-PrometheusReady $LocalPort) {
    Write-Host "[OK] Prometheus is already reachable at http://127.0.0.1:$LocalPort." -ForegroundColor Green
    Write-Host "Stop the process currently serving this port before creating another tunnel." -ForegroundColor Gray
    exit 0
}

$sshArgs = @(
    "-N", "-T",
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ConnectTimeout=8",
    "-p", [string]$ResolvedSshPort,
    "-L", "127.0.0.1:${LocalPort}:${RemoteHost}:${RemotePort}"
)
if ($ResolvedSshKey) { $sshArgs += @("-o", "IdentitiesOnly=yes", "-i", $ResolvedSshKey) }
$logFile = Join-Path $env:TEMP ("hpc-prometheus-tunnel-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$sshArgs += @("-E", $logFile)
$sshArgs += "${ResolvedSshUser}@${ResolvedSshHost}"
$process = $null

try {
    Write-Host "Opening http://127.0.0.1:$LocalPort -> ${ResolvedSshUser}@${ResolvedSshHost}:${ResolvedSshPort}:${RemoteHost}:${RemotePort}" -ForegroundColor Cyan
    $quotedArgs = @($sshArgs | ForEach-Object { ConvertTo-ProcessArgument ([string]$_) }) -join ' '
    $process = Start-Process -FilePath "ssh" -ArgumentList $quotedArgs -WindowStyle Hidden -PassThru

    $ready = $false
    $deadline = (Get-Date).AddSeconds(12)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) { break }
        if (Test-PrometheusReady $LocalPort) { $ready = $true; break }
        Start-Sleep -Milliseconds 400
    }
    if ($process.HasExited) {
        $details = ""
        if (Test-Path -LiteralPath $logFile) { $details = (Get-Content -LiteralPath $logFile -Tail 8) -join "`n" }
        throw "SSH tunnel exited (code $($process.ExitCode)). $details"
    }
    if ($ready) {
        Write-Host "[OK] Prometheus tunnel is ready at http://127.0.0.1:$LocalPort" -ForegroundColor Green
    } else {
        Write-Host "[OK] SSH tunnel is running on local port $LocalPort. Prometheus readiness has not responded yet." -ForegroundColor Yellow
    }
    Write-Host "Keep this window open. Press Ctrl+C to stop the tunnel." -ForegroundColor Gray
    while (-not $process.HasExited) { Start-Sleep -Seconds 1 }
    throw "SSH tunnel stopped (code $($process.ExitCode)). See $logFile"
} finally {
    if ($process -and -not $process.HasExited) { Stop-ProcessTree $process.Id }
}
