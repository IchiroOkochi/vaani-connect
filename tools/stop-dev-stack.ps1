$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".git\dev-stack"
$BackendPidPath = Join-Path $StateDir "backend.wsl.pid"
$SidecarPidPath = Join-Path $StateDir "tts-sidecar.wsl.pid"
$ExpoPidPath = Join-Path $StateDir "expo.pid"

function Get-StoredPid {
    param([string]$PidPath)

    if (-not (Test-Path $PidPath)) {
        return $null
    }

    $raw = (Get-Content $PidPath -Raw).Trim()
    if (-not $raw) {
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $raw
}

function Stop-WslService {
    param(
        [string]$Name,
        [string]$PidPath
    )

    $pidValue = Get-StoredPid -PidPath $PidPath
    if (-not $pidValue) {
        Write-Output "$Name is not tracked."
        return
    }

    & wsl.exe bash -lc "kill $pidValue >/dev/null 2>&1"
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Stopped $Name WSL PID $pidValue."
    } else {
        Write-Output "$Name WSL PID $pidValue was not running."
    }

    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

function Stop-WindowsProcessTree {
    param(
        [string]$Name,
        [string]$PidPath
    )

    $pidValue = Get-StoredPid -PidPath $PidPath
    if (-not $pidValue) {
        Write-Output "$Name is not tracked."
        return
    }

    & taskkill.exe /PID $pidValue /T /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Stopped $Name PID $pidValue."
    } else {
        Write-Output "$Name PID $pidValue was not running."
    }

    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

Stop-WindowsProcessTree -Name "Expo frontend" -PidPath $ExpoPidPath
Stop-WslService -Name "Main backend" -PidPath $BackendPidPath
Stop-WslService -Name "Indic Parler TTS sidecar" -PidPath $SidecarPidPath
