param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".git\changelog-agent"
$PidPath = Join-Path $StateDir "agent.pid"
$OutLog = Join-Path $StateDir "agent.out.log"
$ErrLog = Join-Path $StateDir "agent.err.log"
$ScriptPath = Join-Path $PSScriptRoot "changelog-agent.ps1"

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

if (Test-Path $PidPath) {
    $ExistingPid = (Get-Content $PidPath -Raw).Trim()
    if ($ExistingPid) {
        $ExistingProcess = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
        if ($ExistingProcess) {
            Write-Output "Changelog agent is already running with PID $ExistingPid."
            Write-Output "Logs: $OutLog"
            exit 0
        }
    }
}

$ArgumentList = @("-ExecutionPolicy", "Bypass", "-File", $ScriptPath)
if ($DryRun) {
    $ArgumentList += "-DryRun"
}

$Process = Start-Process `
    -FilePath "powershell" `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Set-Content -Path $PidPath -Value $Process.Id

Write-Output "Started changelog agent."
Write-Output "PID: $($Process.Id)"
Write-Output "Logs: $OutLog"
