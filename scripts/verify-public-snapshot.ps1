param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$FailOnTrackedForbidden
)

$ErrorActionPreference = "Stop"
$MaxPublicSnapshotFailureRecords = 64
$MaxGitOutputRecords = $MaxPublicSnapshotFailureRecords + 1
$MaxGitOutputLineCharacters = 4096

function Stop-PublicSnapshot {
    param(
        [string]$Message
    )

    Write-Output "[PUBLIC-SNAPSHOT-FAIL] $Message"
    exit 1
}

function Add-PublicSnapshotFailure {
    param(
        [System.Collections.Generic.List[string]]$Failures,
        [ref]$Overflow,
        [string]$Message
    )

    if ($Failures.Count -lt $MaxPublicSnapshotFailureRecords) {
        $Failures.Add($Message)
        return
    }
    $Overflow.Value = $true
}

function Test-IsRemoteOrDevicePath {
    param(
        [string]$Path
    )

    return ($Path.StartsWith('\\') -or $Path.StartsWith('//'))
}

function Test-IsReparsePoint {
    param(
        [System.IO.FileSystemInfo]$Item
    )

    return (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Get-SnapshotRootPath {
    param(
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or (Test-IsRemoteOrDevicePath -Path $Path)) {
        Stop-PublicSnapshot -Message "invalid root"
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    } catch {
        Stop-PublicSnapshot -Message "invalid root"
    }

    if (Test-IsRemoteOrDevicePath -Path $fullPath) {
        Stop-PublicSnapshot -Message "invalid root"
    }

    $pathRoot = [System.IO.Path]::GetPathRoot($fullPath)
    if ([string]::IsNullOrWhiteSpace($pathRoot)) {
        Stop-PublicSnapshot -Message "invalid root"
    }

    $currentPath = $pathRoot
    $currentItem = $null
    $parts = $fullPath.Substring($pathRoot.Length) -split '[\\/]' | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    }
    foreach ($part in $parts) {
        $currentPath = Join-Path $currentPath $part
        try {
            $currentItem = Get-Item -LiteralPath $currentPath -Force -ErrorAction Stop
        } catch {
            Stop-PublicSnapshot -Message "invalid root"
        }
        if (Test-IsReparsePoint -Item $currentItem) {
            Stop-PublicSnapshot -Message "root contains reparse point"
        }
    }

    if ($null -eq $currentItem) {
        try {
            $currentItem = Get-Item -LiteralPath $currentPath -Force -ErrorAction Stop
        } catch {
            Stop-PublicSnapshot -Message "invalid root"
        }
    }
    if (-not $currentItem.PSIsContainer) {
        Stop-PublicSnapshot -Message "invalid root"
    }

    return $fullPath
}

function Test-ContainedSnapshotPath {
    param(
        [string]$RootPath,
        [string]$RelativePath
    )

    $currentPath = $RootPath
    $visitedParts = New-Object System.Collections.Generic.List[string]
    foreach ($part in ($RelativePath -split '[\\/]')) {
        if ([string]::IsNullOrWhiteSpace($part)) {
            continue
        }
        $visitedParts.Add($part)
        $currentPath = Join-Path $currentPath $part
        try {
            $item = Get-Item -LiteralPath $currentPath -Force -ErrorAction Stop
        } catch {
            return $false
        }
        if (Test-IsReparsePoint -Item $item) {
            $displayPath = [string]::Join('\', $visitedParts)
            Stop-PublicSnapshot -Message "reparse point: $displayPath"
        }
    }

    return $true
}

function Invoke-GitLsFiles {
    param(
        [string]$RootPath,
        [string[]]$Pathspecs
    )

    $output = New-Object System.Collections.Generic.List[string]
    $captureState = [PSCustomObject]@{
        HasAnyOutput = $false
        OutputValid = $true
    }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Stop"
        & git -C $RootPath ls-files -- @Pathspecs 2>$null | ForEach-Object {
            $captureState.HasAnyOutput = $true
            $line = [string]$_
            if ($line.Length -gt $MaxGitOutputLineCharacters) {
                $captureState.OutputValid = $false
                return
            }
            if (
                -not [string]::IsNullOrWhiteSpace($line) -and
                $output.Count -lt $MaxGitOutputRecords
            ) {
                $output.Add($line)
            }
        }
        $exitCode = $LASTEXITCODE
    } catch {
        $captureState.OutputValid = $false
        $exitCode = 1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($null -eq $exitCode) {
        $exitCode = 1
    }
    if ($exitCode -ne 0 -or -not $captureState.OutputValid) {
        $output.Clear()
    }
    return [PSCustomObject]@{
        Output = @($output)
        ExitCode = $exitCode
        HasAnyOutput = $captureState.HasAnyOutput
        OutputValid = $captureState.OutputValid
    }
}

$rootPath = Get-SnapshotRootPath -Path $Root
$sensitiveConfigPath = "opencode.config.json"

$gitMetadataPresent = Test-ContainedSnapshotPath -RootPath $rootPath -RelativePath ".git"
if ($gitMetadataPresent) {
    $gitResult = Invoke-GitLsFiles -RootPath $rootPath -Pathspecs @(
        $sensitiveConfigPath,
        ".claude/*",
        ".aiworkflow/*",
        ".hypothesis/*"
    )
    if ($gitResult.ExitCode -ne 0 -or -not $gitResult.OutputValid) {
        Stop-PublicSnapshot -Message "unable to verify tracked sensitive config metadata"
    }
    $trackedLocalAgentState = @(
        $gitResult.Output | Where-Object { $_ -like ".claude/*" }
    )
    if ($trackedLocalAgentState.Count -gt 0) {
        Stop-PublicSnapshot -Message "tracked local agent state: .claude"
    }
    $trackedGeneratedState = @(
        $gitResult.Output | Where-Object {
            $_ -like ".aiworkflow/*" -or $_ -like ".hypothesis/*"
        }
    )
    if ($trackedGeneratedState.Count -gt 0) {
        Stop-PublicSnapshot -Message "tracked local generated state"
    }
    if ($gitResult.HasAnyOutput) {
        Stop-PublicSnapshot -Message "tracked sensitive config: $sensitiveConfigPath"
    }
}

function Get-RelativeSnapshotPath {
    param(
        [string]$BasePath,
        [string]$TargetPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)

    if ($targetFull.StartsWith($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $targetFull.Substring($baseFull.Length)
    }

    return $targetFull
}

function Get-SafeSnapshotDisplayPath {
    param(
        [string]$RelativePath
    )

    if (
        [string]::IsNullOrWhiteSpace($RelativePath) -or
        [System.IO.Path]::IsPathRooted($RelativePath) -or
        (($RelativePath -split '[\\/]') -contains '..')
    ) {
        return "<unavailable>"
    }
    $displayPath = [regex]::Replace($RelativePath, '[\p{C}\p{Zl}\p{Zp}]', '?')
    if ($displayPath.Length -gt 240) {
        return $displayPath.Substring(0, 240)
    }
    return $displayPath
}

$requiredPaths = @(
    "PLAN.md",
    "AGENTS.md",
    ".github\workflows\release-verify.yml",
    "packages\agent-acceptance",
    "packages\agent-acceptance\fixtures\negative-acceptance\NEG-031-missing-recon-receipt.json",
    "packages\ai-workflow-hub",
    "packages\control-plane",
    "packages\test-frame",
    "rules",
    "rules\recon.md",
    "schemas",
    "scripts\verify-control-plane-wheel.ps1",
    "scripts\verify-public-snapshot.ps1",
    "scripts\verify-release.ps1",
    "templates\runtime-bootstrap"
)

$forbiddenNames = @(
    ".gitmodules",
    ".agent",
    ".ai",
    ".ai-bridge",
    ".agents",
    ".claude",
    ".codex",
    ".gsd",
    ".opencode",
    "_archive",
    "_evidence",
    "_reports",
    "artifacts",
    "build",
    "dist",
    "evidence",
    "reports",
    "runs"
)

$forbiddenExtensions = @(
    ".zip",
    ".7z",
    ".rar",
    ".docx",
    ".pyc",
    ".pyo",
    ".bak"
)

$forbiddenRootNames = @(
    "chatgpt-review-reply.txt"
)

$forbiddenRootNamePatterns = @(
    "review-bundle-*"
)

$forbiddenTextPatterns = @(
    @{
        Name = "private dev-frame-system checkout path"
        Pattern = "D:\\dev-frame-system|D:/dev-frame-system|D:\\devframe-system|D:/devframe-system"
    },
    @{
        Name = "private adjacent devframe root path"
        Pattern = "D:\\dev-frame\\|D:/dev-frame/|D:\\test-frame|D:/test-frame|D:\\agent-acceptance|D:/agent-acceptance"
    },
    @{
        Name = "private RD user home path"
        Pattern = "C:\\Users\\RD|C:/Users/RD"
    },
    @{
        Name = "concrete ChatGPT conversation URL"
        Pattern = "chatgpt\.com/c/[0-9a-fA-F-]{8,}"
    },
    @{
        Name = "mojibake replacement marker"
        Pattern = "\u951F\u65A4\u62F7|\uFFFD|\u9225\?|\u922B\?|\u922E\?|\u95BF\u719F\u67BB\u93B7"
    }
)

$textScanExtensions = @(
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".txt",
    ".yaml",
    ".yml"
)

$textScanAllowlist = @(
    "packages\control-plane\tests\test_public_snapshot.py",
    "scripts\verify-public-snapshot.ps1"
)

$ignoredGeneratedDirs = @(
    "__pycache__",
    ".aiworkflow",
    ".claude",
    ".codegraph",
    ".devframe-runtime",
    ".hypothesis",
    ".kiro",
    ".vscode",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "products",
    "node_modules"
)

function Test-IsUnderIgnoredGeneratedDir {
    param(
        [string]$BasePath,
        [string]$TargetPath
    )

    $relative = Get-RelativeSnapshotPath -BasePath $BasePath -TargetPath $TargetPath
    $parts = $relative -split '[\\/]'
    foreach ($part in $parts) {
        if ($ignoredGeneratedDirs -contains $part) {
            return $true
        }
    }
    return $false
}

function Get-PublicSnapshotItems {
    param(
        [string]$Path,
        [string]$RootPath
    )

    $enumerationErrors = @()
    Get-ChildItem -LiteralPath $Path -Force `
        -ErrorAction SilentlyContinue -ErrorVariable +enumerationErrors | ForEach-Object {
            if (-not ($_ -is [System.IO.FileSystemInfo]) -or [string]::IsNullOrWhiteSpace($_.FullName)) {
                return
            }
            if (Test-IsReparsePoint -Item $_) {
                $_
                return
            }

            if ($_.PSIsContainer) {
                $relative = Get-RelativeSnapshotPath -BasePath $RootPath -TargetPath $_.FullName

                if ($relative -like ".git*") {
                    return
                }

                $parts = $relative -split '[\\/]'
                $isIgnored = $false
                foreach ($part in $parts) {
                    if ($ignoredGeneratedDirs -contains $part) {
                        $isIgnored = $true
                        break
                    }
                }
                if (-not $isIgnored) {
                    $_
                    Get-PublicSnapshotItems -Path $_.FullName -RootPath $RootPath
                }
            } else {
                $relative = Get-RelativeSnapshotPath -BasePath $RootPath -TargetPath $_.FullName
                if ($relative -ne $sensitiveConfigPath) {
                    $_
                }
            }
    }
    if ($enumerationErrors.Count -gt 0) {
        $relativePath = Get-RelativeSnapshotPath -BasePath $RootPath -TargetPath $Path
        $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $relativePath
        throw [System.InvalidOperationException]::new(
            "DEVFRAME_PUBLIC_SNAPSHOT_ENUMERATION:$displayPath"
        )
    }
}

function Stop-PublicSnapshotEnumerationFailure {
    param(
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    $prefix = "DEVFRAME_PUBLIC_SNAPSHOT_ENUMERATION:"
    $message = $ErrorRecord.Exception.Message
    if ([string]::IsNullOrWhiteSpace($message) -or -not $message.StartsWith($prefix)) {
        throw $ErrorRecord
    }
    $displayPath = $message.Substring($prefix.Length)
    Stop-PublicSnapshot -Message "unable to enumerate snapshot path: $displayPath"
}

$missing = New-Object System.Collections.Generic.List[string]
foreach ($path in $requiredPaths) {
    if (-not (Test-ContainedSnapshotPath -RootPath $rootPath -RelativePath $path)) {
        $missing.Add($path)
    }
}

if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Output "[MISSING] $_" }
    exit 1
}

$requiredTextChecks = @(
    @{
        Path = "PLAN.md"
        Text = "Current verdict:"
    },
    @{
        Path = "PLAN.md"
        Text = "## 15. Documentation Policy"
    },
    @{
        Path = "AGENTS.md"
        Text = "PLAN.md"
    },
    @{
        Path = "AGENTS.md"
        Text = "rules/recon.md"
    },
    @{
        Path = "rules\open-source-reuse.md"
        Text = "rules/recon.md"
    },
    @{
        Path = "rules\recon.md"
        Text = "RULE recon-001: Recon Gate Before Write-Capable Work"
    },
    @{
        Path = "packages\agent-acceptance\fixtures\negative-acceptance\NEG-031-missing-recon-receipt.json"
        Text = "Missing Recon Receipt"
    }
)

$textFailures = New-Object System.Collections.Generic.List[string]
foreach ($check in $requiredTextChecks) {
    $path = Join-Path $rootPath $check.Path
    if (-not (Test-ContainedSnapshotPath -RootPath $rootPath -RelativePath $check.Path)) {
        $textFailures.Add("$($check.Path): file missing")
        continue
    }
    try {
        $content = Get-Content -LiteralPath $path -Raw -ErrorAction Stop
    } catch {
        $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $check.Path
        Write-Output "[TEXT-FAIL] ${displayPath}: unable to inspect required text"
        exit 1
    }
    if ($null -eq $content -or -not $content.Contains($check.Text)) {
        $textFailures.Add("$($check.Path): missing '$($check.Text)'")
    }
}

if ($textFailures.Count -gt 0) {
    $textFailures | ForEach-Object { Write-Output "[TEXT-FAIL] $_" }
    exit 1
}

if ($FailOnTrackedForbidden -and $gitMetadataPresent) {
    $trackedFailures = New-Object System.Collections.Generic.List[string]
    $trackedFailuresOverflow = $false
    $gitResult = Invoke-GitLsFiles -RootPath $rootPath -Pathspecs @(
        "chatgpt-review-reply.txt",
        "review-bundle-*",
        "products/*"
    )
    if ($gitResult.ExitCode -ne 0 -or -not $gitResult.OutputValid) {
        Stop-PublicSnapshot -Message "unable to verify tracked sensitive config metadata"
    }
    $trackedForbidden = @($gitResult.Output)

    foreach ($path in $trackedForbidden) {
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $path
            if ($path -like "products/*") {
                Add-PublicSnapshotFailure `
                    -Failures $trackedFailures `
                    -Overflow ([ref]$trackedFailuresOverflow) `
                    -Message "tracked bundled product: $displayPath"
            } else {
                Add-PublicSnapshotFailure `
                    -Failures $trackedFailures `
                    -Overflow ([ref]$trackedFailuresOverflow) `
                    -Message "tracked forbidden review artifact: $displayPath"
            }
        }
    }

    if ($trackedFailures.Count -gt 0) {
        $trackedFailures | ForEach-Object {
            Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_"
        }
        if ($trackedFailuresOverflow) {
            Write-Output "[PUBLIC-SNAPSHOT-FAIL] additional tracked path failures omitted"
        }
        exit 1
    }
}

$violations = New-Object System.Collections.Generic.List[string]
$violationsOverflow = $false
try {
    Get-PublicSnapshotItems -Path $rootPath -RootPath $rootPath | ForEach-Object {
    if ($_.FullName -like (Join-Path $rootPath ".git*")) {
        return
    }

    $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $_.FullName
    $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $relative

    if (Test-IsReparsePoint -Item $_) {
        Add-PublicSnapshotFailure `
            -Failures $violations `
            -Overflow ([ref]$violationsOverflow) `
            -Message "reparse point: $displayPath"
        return
    }

    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $_.FullName) {
        return
    }

    $relativeParts = $relative -split '[\\/]'
    if ($relativeParts.Count -eq 1) {
        if ($forbiddenRootNames -contains $_.Name) {
            Add-PublicSnapshotFailure `
                -Failures $violations `
                -Overflow ([ref]$violationsOverflow) `
                -Message "forbidden root review artifact: $displayPath"
        }

        foreach ($pattern in $forbiddenRootNamePatterns) {
            if ($_.Name -like $pattern) {
                Add-PublicSnapshotFailure `
                    -Failures $violations `
                    -Overflow ([ref]$violationsOverflow) `
                    -Message "forbidden root review artifact: $displayPath"
                break
            }
        }
    }

    if ($forbiddenNames -contains $_.Name) {
        Add-PublicSnapshotFailure `
            -Failures $violations `
            -Overflow ([ref]$violationsOverflow) `
            -Message "forbidden name: $displayPath"
    }

    if (-not $_.PSIsContainer -and ($forbiddenExtensions -contains $_.Extension)) {
        Add-PublicSnapshotFailure `
            -Failures $violations `
            -Overflow ([ref]$violationsOverflow) `
            -Message "forbidden extension: $displayPath"
    }

    if (-not $_.PSIsContainer -and $_.Length -gt 5MB) {
        Add-PublicSnapshotFailure `
            -Failures $violations `
            -Overflow ([ref]$violationsOverflow) `
            -Message "file exceeds 5MB: $displayPath"
    }
    }
} catch {
    Stop-PublicSnapshotEnumerationFailure -ErrorRecord $_
}

if ($violations.Count -gt 0) {
    $violations | ForEach-Object { Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_" }
    if ($violationsOverflow) {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] additional snapshot violations omitted"
    }
    exit 1
}

$privateTextFailures = New-Object System.Collections.Generic.List[string]
$privateTextFailuresOverflow = $false
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
try {
    Get-PublicSnapshotItems -Path $rootPath -RootPath $rootPath | Where-Object {
    $_ -is [System.IO.FileSystemInfo] -and -not $_.PSIsContainer -and
        -not [string]::IsNullOrWhiteSpace($_.FullName) -and
        ($textScanExtensions -contains $_.Extension)
} | ForEach-Object {
    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $_.FullName) {
        return
    }

    $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $_.FullName
    if ($textScanAllowlist -contains $relative) {
        return
    }
    $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $relative

    try {
        $content = [System.IO.File]::ReadAllText($_.FullName, $utf8)
    } catch {
        Stop-PublicSnapshot -Message "unable to inspect text: $displayPath"
    }

    foreach ($pattern in $forbiddenTextPatterns) {
        if ($content -match $pattern.Pattern) {
            Add-PublicSnapshotFailure `
                -Failures $privateTextFailures `
                -Overflow ([ref]$privateTextFailuresOverflow) `
                -Message "${displayPath}: contains $($pattern.Name)"
        }
    }
    }
} catch {
    Stop-PublicSnapshotEnumerationFailure -ErrorRecord $_
}

if ($privateTextFailures.Count -gt 0) {
    $privateTextFailures | ForEach-Object {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_"
    }
    if ($privateTextFailuresOverflow) {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] additional private text failures omitted"
    }
    exit 1
}

try {
    Get-PublicSnapshotItems -Path $rootPath -RootPath $rootPath | Where-Object {
    $_ -is [System.IO.FileSystemInfo] -and -not $_.PSIsContainer -and
        -not [string]::IsNullOrWhiteSpace($_.FullName) -and $_.Extension -eq ".json"
} | ForEach-Object {
    $jsonFile = $_
    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $jsonFile.FullName) {
        return
    }

    $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $jsonFile.FullName

    try {
        $jsonText = [System.IO.File]::ReadAllText($jsonFile.FullName, $utf8)
        if ($jsonText.Length -gt 0 -and $jsonText[0] -eq [char]0xFEFF) {
            $jsonText = $jsonText.Substring(1)
        }
        $jsonText | ConvertFrom-Json | Out-Null
    } catch {
        $displayPath = Get-SafeSnapshotDisplayPath -RelativePath $relative
        Write-Output "[JSON-FAIL] ${displayPath}: unable to parse JSON"
        exit 1
    }
    }
} catch {
    Stop-PublicSnapshotEnumerationFailure -ErrorRecord $_
}

Write-Output "[OK] Public snapshot required paths are present."
Write-Output "[OK] Governance rule references are present."
Write-Output "[OK] Ignored local runtime caches were excluded; scanned public files contain no forbidden state, archives, oversized files, or private text markers."
Write-Output "[OK] JSON files parse as UTF-8."
