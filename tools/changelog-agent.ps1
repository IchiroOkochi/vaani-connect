param(
    [switch]$Once,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ChangelogPath = Join-Path $RepoRoot "CHANGELOG.md"
$PromptPath = Join-Path $PSScriptRoot "changelog-agent.prompt.md"
$StateDir = Join-Path $RepoRoot ".git\changelog-agent"
$StatePath = Join-Path $StateDir "state.json"
$LockPath = Join-Path $StateDir "update.lock"
$LastMessagePath = Join-Path $StateDir "last-message.txt"
$DebounceMilliseconds = 2500
$IgnoredSegments = @(
    ".git",
    ".expo",
    ".next",
    ".turbo",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "web-build",
    "htmlcov",
    "tmp",
    "vaani_connect_audio"
)

$script:LastAppliedSignature = ""
$script:PendingReason = "startup"
$script:PendingAt = Get-Date
$script:UpdateQueued = $true
$script:UpdateInFlight = $false

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

if (Test-Path -LiteralPath $StatePath) {
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($state.lastAppliedSignature) {
            $script:LastAppliedSignature = [string]$state.lastAppliedSignature
        }
    } catch {
    }
}

function Write-Log {
    param([string]$Message)
    Write-Output "[changelog-agent $(Get-Date -Format o)] $Message"
}

function Normalize-GitPath {
    param([string]$Value)
    return ($Value -replace "\\", "/") -replace "^\./+", ""
}

function Should-IgnoreGitPath {
    param([string]$GitPath)

    if (-not $GitPath) {
        return $true
    }

    $normalized = Normalize-GitPath $GitPath
    $segments = $normalized -split "/"
    foreach ($segment in $segments) {
        if ($IgnoredSegments -contains $segment) {
            return $true
        }
    }

    if ($normalized -eq "CHANGELOG.md" -or $normalized.EndsWith("/CHANGELOG.md")) {
        return $true
    }

    if ($normalized -like "bakcend/benchmark/results/*") {
        return $true
    }

    return $false
}

function Should-IgnoreWatchPath {
    param([string]$RelativePath)
    return (Should-IgnoreGitPath $RelativePath)
}

function Get-FileFingerprint {
    param([string]$GitPath)

    $absolutePath = Join-Path $RepoRoot ($GitPath -replace "/", "\")
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        return "${GitPath}:missing"
    }

    $item = Get-Item -LiteralPath $absolutePath
    $hash = (Get-FileHash -Algorithm SHA1 -LiteralPath $absolutePath).Hash.ToLowerInvariant()
    return "${GitPath}:$($item.Length):$hash"
}

function Get-Sha1String {
    param([string]$Value)

    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $sha1.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha1.Dispose()
    }
}

function Get-RelativeRepoPath {
    param([string]$FullPath)

    $repoUri = New-Object System.Uri(($RepoRoot.TrimEnd("\") + "\"))
    $fileUri = New-Object System.Uri($FullPath)
    $relativeUri = $repoUri.MakeRelativeUri($fileUri)
    return Normalize-GitPath ([System.Uri]::UnescapeDataString($relativeUri.ToString()))
}

function Get-ChangeSnapshot {
    $statusLines = & git status --porcelain=v1 --untracked-files=all -- .
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed"
    }

    $entries = @()
    foreach ($line in $statusLines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $status = $line.Substring(0, 2).Trim()
        if (-not $status) {
            $status = "??"
        }

        $rawPath = $line.Substring(3).Trim()
        if (-not $rawPath) {
            continue
        }

        $paths = @($rawPath -split " -> " | ForEach-Object { Normalize-GitPath $_ })
        $actionablePaths = @($paths | Where-Object { -not (Should-IgnoreGitPath $_) })
        if ($actionablePaths.Count -eq 0) {
            continue
        }

        $displayPath = if ($paths.Count -gt 1) {
            "$($paths[0]) -> $($paths[-1])"
        } else {
            $paths[0]
        }

        $fingerprints = @($paths | ForEach-Object { Get-FileFingerprint $_ })

        $entries += [pscustomobject]@{
            Status      = $status
            Paths       = $paths
            DisplayPath = $displayPath
            Fingerprint = ($fingerprints -join "|")
        }
    }

    if ($entries.Count -eq 0) {
        return [pscustomobject]@{
            Entries    = @()
            Signature  = ""
        }
    }

    $signatureText = ($entries | ForEach-Object {
        "$($_.Status)|$($_.DisplayPath)|$($_.Fingerprint)"
    }) -join "`n"

    return [pscustomobject]@{
        Entries    = $entries
        Signature  = (Get-Sha1String $signatureText)
    }
}

function Save-State {
    param([string]$Signature)

    $payload = [pscustomobject]@{
        lastAppliedSignature = $Signature
        updatedAt            = (Get-Date).ToString("o")
    }

    $payload | ConvertTo-Json | Set-Content -LiteralPath $StatePath
}

function Try-AcquireLock {
    if (Test-Path -LiteralPath $LockPath) {
        return $false
    }

    Set-Content -LiteralPath $LockPath -Value (Get-Date).ToString("o")
    return $true
}

function Release-Lock {
    Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
}

function Invoke-CodexUpdate {
    param($Snapshot)

    $promptTemplate = Get-Content -LiteralPath $PromptPath -Raw
    $changedFiles = ($Snapshot.Entries | ForEach-Object { "- $($_.Status) $($_.DisplayPath)" }) -join "`n"
    $prompt = "$($promptTemplate.Trim())`n`nChanged files right now:`n$changedFiles`n"

    $prompt | & codex exec --full-auto -C $RepoRoot -o $LastMessagePath -
    return ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $ChangelogPath))
}

function Invoke-Update {
    param([string]$Reason)

    if ($script:UpdateInFlight) {
        $script:UpdateQueued = $true
        $script:PendingReason = $Reason
        $script:PendingAt = Get-Date
        return
    }

    $script:UpdateInFlight = $true
    try {
        $snapshot = Get-ChangeSnapshot
        if (-not $snapshot.Signature) {
            Write-Log "No actionable repo changes after $Reason."
            return
        }

        if ($snapshot.Signature -eq $script:LastAppliedSignature) {
            Write-Log "Changes already logged; skipping after $Reason."
            return
        }

        if (-not (Try-AcquireLock)) {
            Write-Log "Another changelog update is already running; waiting for the next change."
            return
        }

        try {
            if ($DryRun) {
                Write-Log "Dry run: would invoke Codex with these changed files:"
                foreach ($entry in $snapshot.Entries) {
                    Write-Log "  $($entry.Status) $($entry.DisplayPath)"
                }
                return
            }

            Write-Log "Updating changelog after $Reason."
            if (Invoke-CodexUpdate $snapshot) {
                $script:LastAppliedSignature = $snapshot.Signature
                Save-State $script:LastAppliedSignature
                Write-Log "CHANGELOG.md updated."
            } else {
                Write-Log "Codex update failed; will retry on the next file change."
            }
        } finally {
            Release-Lock
        }
    } catch {
        Write-Log $_.Exception.Message
    } finally {
        $script:UpdateInFlight = $false
    }
}

if ($Once) {
    Write-Log "Checking $RepoRoot"
    Invoke-Update "startup"
    exit 0
}

Write-Log "Watching $RepoRoot"

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $RepoRoot
$watcher.Filter = "*"
$watcher.IncludeSubdirectories = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]"FileName, LastWrite, CreationTime, DirectoryName, Size"
$watcher.EnableRaisingEvents = $true

$subscriptions = @(
    (Register-ObjectEvent -InputObject $watcher -EventName Changed -SourceIdentifier "changelog-agent.changed"),
    (Register-ObjectEvent -InputObject $watcher -EventName Created -SourceIdentifier "changelog-agent.created"),
    (Register-ObjectEvent -InputObject $watcher -EventName Deleted -SourceIdentifier "changelog-agent.deleted"),
    (Register-ObjectEvent -InputObject $watcher -EventName Renamed -SourceIdentifier "changelog-agent.renamed")
)

try {
    while ($true) {
        $event = Wait-Event -Timeout 1
        if ($event) {
            $sourceArgs = $event.SourceEventArgs
            $fullPath = if ($sourceArgs.FullPath) { $sourceArgs.FullPath } else { $null }
            if ($fullPath) {
                $relativePath = Get-RelativeRepoPath $fullPath
                if (-not (Should-IgnoreWatchPath $relativePath)) {
                    $script:PendingReason = $relativePath
                    $script:PendingAt = Get-Date
                    $script:UpdateQueued = $true
                }
            }

            Remove-Event -EventIdentifier $event.EventIdentifier
            continue
        }

        if ($script:UpdateQueued -and ((Get-Date) - $script:PendingAt).TotalMilliseconds -ge $DebounceMilliseconds) {
            $script:UpdateQueued = $false
            Invoke-Update $script:PendingReason
        }
    }
} finally {
    foreach ($subscription in $subscriptions) {
        Unregister-Event -SubscriptionId $subscription.Id -ErrorAction SilentlyContinue
    }

    $watcher.Dispose()
}
