[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$DryRun,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$StartScript = Join-Path $PSScriptRoot "start-changelog-agent.ps1"
$PowerShellExe = (Get-Command powershell.exe).Source
$TaskName = "Vaani Connect Changelog Agent"
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$taskCommand = "`"$PowerShellExe`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$StartScript`""
if ($DryRun) {
    $taskCommand += " -DryRun"
}

$createArguments = @(
    "/Create",
    "/TN", $TaskName,
    "/SC", "ONLOGON",
    "/TR", $taskCommand,
    "/RL", "LIMITED",
    "/F",
    "/IT",
    "/RU", $CurrentUser
)

if ($PSCmdlet.ShouldProcess($TaskName, "Install changelog agent scheduled task")) {
    & schtasks.exe @createArguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks.exe failed to install '$TaskName'."
    }

    Write-Output "Installed scheduled task '$TaskName' for user $CurrentUser."
    if ($DryRun) {
        Write-Output "The scheduled task will start the changelog agent in dry-run mode."
    }
}

if ($StartNow -and $PSCmdlet.ShouldProcess($TaskName, "Start changelog agent scheduled task now")) {
    & schtasks.exe /Run /TN $TaskName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks.exe failed to start '$TaskName'."
    }

    Write-Output "Triggered '$TaskName' to run now."
}
