$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".git\changelog-agent"
$PidPath = Join-Path $StateDir "agent.pid"

if (-not (Test-Path $PidPath)) {
    Write-Output "No changelog agent PID file found."
    exit 0
}

$PidValue = (Get-Content $PidPath -Raw).Trim()
if (-not $PidValue) {
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    Write-Output "PID file was empty and has been removed."
    exit 0
}

$Process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
if ($Process) {
    Stop-Process -Id $PidValue -Force
    Write-Output "Stopped changelog agent PID $PidValue."
} else {
    Write-Output "Process $PidValue is not running."
}

Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
