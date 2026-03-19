[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"

$TaskName = "Vaani Connect Changelog Agent"
$StopScript = Join-Path $PSScriptRoot "stop-changelog-agent.ps1"

try {
    & schtasks.exe /Query /TN $TaskName 2>$null | Out-Null
    $taskExists = ($LASTEXITCODE -eq 0)
} catch {
    $taskExists = $false
}

if (-not $taskExists) {
    Write-Output "Scheduled task '$TaskName' was not installed."
} else {
    if ($PSCmdlet.ShouldProcess($TaskName, "Remove changelog agent scheduled task")) {
        & schtasks.exe /End /TN $TaskName | Out-Null
        & schtasks.exe /Delete /TN $TaskName /F | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "schtasks.exe failed to remove '$TaskName'."
        }

        Write-Output "Removed scheduled task '$TaskName'."
    }
}

if ($PSCmdlet.ShouldProcess("changelog agent process", "Stop running changelog agent")) {
    & $StopScript
}
