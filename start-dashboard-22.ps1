<#
.SYNOPSIS
    Legacy convenience wrapper defaulting SSH port preference to 22 (auto-falls back to 443).
    All secrets must be provided via backend/.env or environment variables (no hardcoded keys).
    SSH key permission repair and tunnel startup are handled by the shared launcher below.
#>
param(
    [string]$SshHost = "",
    [string]$SshUser = "",
    [int]$SshPort = 22,
    [string]$SshKey = "",
    [switch]$SkipPrompt,
    [switch]$ForceRestart
)

$target = Join-Path $PSScriptRoot "start-dashboard.ps1"
$forwardParams = @{
    SshPort = $SshPort
}
if ($SshHost) { $forwardParams["SshHost"] = $SshHost }
if ($SshUser) { $forwardParams["SshUser"] = $SshUser }
if ($SshKey) { $forwardParams["SshKey"] = $SshKey }
if ($SkipPrompt) { $forwardParams["SkipPrompt"] = $true }
if ($ForceRestart) { $forwardParams["ForceRestart"] = $true }

& $target @forwardParams
