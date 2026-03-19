param(
    [ValidateSet("web", "start", "android", "ios")]
    [string]$FrontendTarget = "web",
    [switch]$NoSidecar
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RepoRoot ".git\dev-stack"
$BackendPidPath = Join-Path $StateDir "backend.wsl.pid"
$SidecarPidPath = Join-Path $StateDir "tts-sidecar.wsl.pid"
$ExpoPidPath = Join-Path $StateDir "expo.pid"
$BackendOutLog = Join-Path $StateDir "backend.out.log"
$BackendErrLog = Join-Path $StateDir "backend.err.log"
$SidecarOutLog = Join-Path $StateDir "tts-sidecar.out.log"
$SidecarErrLog = Join-Path $StateDir "tts-sidecar.err.log"
$ExpoOutLog = Join-Path $StateDir "expo.out.log"
$ExpoErrLog = Join-Path $StateDir "expo.err.log"

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

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

function Convert-ToWslPath {
    param([string]$WindowsPath)

    $resolved = [System.IO.Path]::GetFullPath($WindowsPath)
    $driveLetter = $resolved.Substring(0, 1).ToLowerInvariant()
    $rest = $resolved.Substring(2).Replace("\", "/")
    return "/mnt/$driveLetter$rest"
}

function Quote-Bash {
    param([string]$Value)

    $escaped = $Value.Replace("\", "\\").Replace('"', '\"').Replace('$', '\$').Replace('`', '\`')
    return '"' + $escaped + '"'
}

function Test-WindowsProcessRunning {
    param([string]$PidPath)

    $pidValue = Get-StoredPid -PidPath $PidPath
    if (-not $pidValue) {
        return $false
    }

    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($process) {
        return $true
    }

    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    return $false
}

function Test-WslProcessRunning {
    param([string]$PidPath)

    $pidValue = Get-StoredPid -PidPath $PidPath
    if (-not $pidValue) {
        return $false
    }

    & wsl.exe bash -lc "kill -0 $pidValue >/dev/null 2>&1"
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    return $false
}

function Build-WslExports {
    param([hashtable]$Variables)

    $exports = @()
    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        $exports += "export $key=$(Quote-Bash -Value $value)"
    }

    return ($exports -join "; ")
}

function Start-WslService {
    param(
        [string]$Name,
        [string]$PidPath,
        [string]$WorkingDirectory,
        [string]$ActivatePath,
        [string]$Command,
        [string]$OutLog,
        [string]$ErrLog,
        [hashtable]$EnvironmentVariables
    )

    if (Test-WslProcessRunning -PidPath $PidPath) {
        $existingPid = Get-StoredPid -PidPath $PidPath
        Write-Output "$Name is already running in WSL with PID $existingPid."
        return
    }

    $wslWorkingDirectory = Convert-ToWslPath -WindowsPath $WorkingDirectory
    $wslActivatePath = Convert-ToWslPath -WindowsPath $ActivatePath
    $wslOutLog = Convert-ToWslPath -WindowsPath $OutLog
    $wslErrLog = Convert-ToWslPath -WindowsPath $ErrLog
    $exports = Build-WslExports -Variables $EnvironmentVariables

    $bashCommand = @(
        "set -e"
        "cd $(Quote-Bash -Value $wslWorkingDirectory)"
        "if [ ! -f $(Quote-Bash -Value $wslActivatePath) ]; then echo __MISSING_VENV__; exit 21; fi"
        "source $(Quote-Bash -Value $wslActivatePath)"
    )

    if ($exports) {
        $bashCommand += $exports
    }

    $bashCommand += "nohup $Command > $(Quote-Bash -Value $wslOutLog) 2> $(Quote-Bash -Value $wslErrLog) < /dev/null & echo `$!"

    $result = & wsl.exe bash -lc ($bashCommand -join "; ")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start $Name in WSL."
    }

    $pidValue = (($result | Select-Object -Last 1) -as [string]).Trim()
    if ($pidValue -eq "__MISSING_VENV__") {
        throw "$Name virtual environment was not found at $ActivatePath"
    }
    if (-not $pidValue) {
        throw "$Name did not return a PID."
    }

    Set-Content -Path $PidPath -Value $pidValue
    Write-Output "Started $Name in WSL with PID $pidValue."
    Write-Output "Logs: $OutLog"
}

function Start-ExpoService {
    param(
        [string]$PidPath,
        [string]$WorkingDirectory,
        [string]$FrontendTarget,
        [string]$OutLog,
        [string]$ErrLog
    )

    if (Test-WindowsProcessRunning -PidPath $PidPath) {
        $existingPid = Get-StoredPid -PidPath $PidPath
        Write-Output "Expo frontend is already running with PID $existingPid."
        return
    }

    $npmCommand = switch ($FrontendTarget) {
        "web" { "npm run web" }
        "android" { "npm run android" }
        "ios" { "npm run ios" }
        default { "npm run start" }
    }

    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/c", $npmCommand `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru

    Set-Content -Path $PidPath -Value $process.Id
    Write-Output "Started Expo frontend with PID $($process.Id) using target '$FrontendTarget'."
    Write-Output "Logs: $OutLog"
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe is not available. Install WSL first or use the manual startup flow."
}

$backendWorkingDirectory = Join-Path $RepoRoot "backend"
$backendActivatePath = Join-Path $backendWorkingDirectory ".venv\bin\activate"
$sidecarWorkingDirectory = Join-Path $backendWorkingDirectory "tts_sidecar"
$sidecarActivatePath = Join-Path $sidecarWorkingDirectory ".venv\bin\activate"
$expoWorkingDirectory = Join-Path $RepoRoot "Expo"

if (-not (Test-Path $backendActivatePath)) {
    throw "Backend virtual environment not found at $backendActivatePath"
}

$useSidecar = $false
if (-not $NoSidecar -and (Test-Path $sidecarActivatePath)) {
    $useSidecar = $true
}

if (-not $NoSidecar -and -not $useSidecar) {
    Write-Output "TTS sidecar virtual environment was not found at $sidecarActivatePath."
    Write-Output "Continuing with backend TTS provider fallback instead of the sidecar."
}

$sharedToken = $env:HF_TOKEN
if (-not $sharedToken) {
    $sharedToken = $env:HUGGINGFACE_HUB_TOKEN
}

if ($useSidecar) {
    Start-WslService `
        -Name "Indic Parler TTS sidecar" `
        -PidPath $SidecarPidPath `
        -WorkingDirectory $sidecarWorkingDirectory `
        -ActivatePath $sidecarActivatePath `
        -Command "uvicorn app:app --host 0.0.0.0 --port 8010" `
        -OutLog $SidecarOutLog `
        -ErrLog $SidecarErrLog `
        -EnvironmentVariables @{
            HF_TOKEN = $sharedToken
            HUGGINGFACE_HUB_TOKEN = $sharedToken
        }
}

$backendEnvironment = @{
    HF_TOKEN = $sharedToken
    HUGGINGFACE_HUB_TOKEN = $sharedToken
}

if ($useSidecar) {
    $backendEnvironment["VAANI_TTS_PROVIDER"] = "parler_sidecar"
    $backendEnvironment["VAANI_TTS_SIDECAR_URL"] = "http://127.0.0.1:8010"
}

Start-WslService `
    -Name "Main backend" `
    -PidPath $BackendPidPath `
    -WorkingDirectory $backendWorkingDirectory `
    -ActivatePath $backendActivatePath `
    -Command "uvicorn app.server:app --host 0.0.0.0 --port 8000 --log-level info" `
    -OutLog $BackendOutLog `
    -ErrLog $BackendErrLog `
    -EnvironmentVariables $backendEnvironment

Start-ExpoService `
    -PidPath $ExpoPidPath `
    -WorkingDirectory $expoWorkingDirectory `
    -FrontendTarget $FrontendTarget `
    -OutLog $ExpoOutLog `
    -ErrLog $ExpoErrLog

Write-Output ""
Write-Output "Dev stack start complete."
Write-Output "Main backend: http://localhost:8000/health"
if ($useSidecar) {
    Write-Output "TTS sidecar: http://localhost:8010/health"
}
Write-Output "Expo target: $FrontendTarget"
Write-Output "State directory: $StateDir"
