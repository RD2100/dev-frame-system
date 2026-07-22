param(
    [string]$Root = (Get-Location).Path,
    [switch]$FailOnTrackedForbidden
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$sensitiveConfigPath = "opencode.config.json"

if (Test-Path -LiteralPath (Join-Path $rootPath ".git")) {
    $trackedSensitiveConfig = @(
        & git -C $rootPath ls-files -- $sensitiveConfigPath 2>$null
    )
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata"
        exit 1
    }
    if ($trackedSensitiveConfig.Count -gt 0) {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] tracked sensitive config: $sensitiveConfigPath"
        exit 1
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

$requiredPaths = @(
    "README.md",
    "README.zh-CN.md",
    "AGENTS.md",
    ".github\workflows\release-verify.yml",
    "docs\agent-runtime",
    "docs\assets\devframe-system-banner.svg",
    "docs\module-sources.md",
    "docs\status\release-readiness.md",
    "docs\status\reviewer-index.md",
    "packages\agent-acceptance",
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
    ".codegraph",
    ".devframe-runtime",
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

    Get-ChildItem -LiteralPath $Path -Force | ForEach-Object {
        if (-not ($_ -is [System.IO.FileSystemInfo]) -or [string]::IsNullOrWhiteSpace($_.FullName)) {
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
}

$missing = New-Object System.Collections.Generic.List[string]
foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $rootPath $path))) {
        $missing.Add($path)
    }
}

if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Output "[MISSING] $_" }
    exit 1
}

$requiredTextChecks = @(
    @{
        Path = "AGENTS.md"
        Text = "rules/recon.md"
    },
    @{
        Path = "rules\README.md"
        Text = "recon.md"
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
        Path = "docs\agent-runtime\negative-test-fixtures\NEG-031-missing-recon-receipt.json"
        Text = "Missing Recon Receipt"
    }
)

$textFailures = New-Object System.Collections.Generic.List[string]
foreach ($check in $requiredTextChecks) {
    $path = Join-Path $rootPath $check.Path
    if (-not (Test-Path -LiteralPath $path)) {
        $textFailures.Add("$($check.Path): file missing")
        continue
    }
    $content = Get-Content -LiteralPath $path -Raw
    if (-not $content.Contains($check.Text)) {
        $textFailures.Add("$($check.Path): missing '$($check.Text)'")
    }
}

if ($textFailures.Count -gt 0) {
    $textFailures | ForEach-Object { Write-Output "[TEXT-FAIL] $_" }
    exit 1
}

if ($FailOnTrackedForbidden -and (Test-Path -LiteralPath (Join-Path $rootPath ".git"))) {
    $trackedFailures = New-Object System.Collections.Generic.List[string]
    $trackedForbidden = & git -C $rootPath ls-files -- `
        "chatgpt-review-reply.txt" `
        "review-bundle-*" `
        "products/*" 2>$null

    foreach ($path in $trackedForbidden) {
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            if ($path -like "products/*") {
                $trackedFailures.Add("tracked bundled product: $path")
            } else {
                $trackedFailures.Add("tracked forbidden review artifact: $path")
            }
        }
    }

    if ($trackedFailures.Count -gt 0) {
        $trackedFailures | ForEach-Object {
            Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_"
        }
        exit 1
    }
}

$violations = New-Object System.Collections.Generic.List[string]
Get-PublicSnapshotItems -Path $rootPath -RootPath $rootPath | ForEach-Object {
    if ($_.FullName -like (Join-Path $rootPath ".git*")) {
        return
    }

    $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $_.FullName

    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $_.FullName) {
        return
    }

    $relativeParts = $relative -split '[\\/]'
    if ($relativeParts.Count -eq 1) {
        if ($forbiddenRootNames -contains $_.Name) {
            $violations.Add("forbidden root review artifact: $relative")
        }

        foreach ($pattern in $forbiddenRootNamePatterns) {
            if ($_.Name -like $pattern) {
                $violations.Add("forbidden root review artifact: $relative")
                break
            }
        }
    }

    if ($forbiddenNames -contains $_.Name) {
        $violations.Add("forbidden name: $relative")
    }

    if (-not $_.PSIsContainer -and ($forbiddenExtensions -contains $_.Extension)) {
        $violations.Add("forbidden extension: $relative")
    }

    if (-not $_.PSIsContainer -and $_.Length -gt 5MB) {
        $violations.Add("file exceeds 5MB: $relative")
    }
}

if ($violations.Count -gt 0) {
    $violations | ForEach-Object { Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_" }
    exit 1
}

$privateTextFailures = New-Object System.Collections.Generic.List[string]
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
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

    try {
        $content = [System.IO.File]::ReadAllText($_.FullName, $utf8)
    } catch {
        return
    }

    foreach ($pattern in $forbiddenTextPatterns) {
        if ($content -match $pattern.Pattern) {
            $privateTextFailures.Add("${relative}: contains $($pattern.Name)")
        }
    }
}

if ($privateTextFailures.Count -gt 0) {
    $privateTextFailures | ForEach-Object {
        Write-Output "[PUBLIC-SNAPSHOT-FAIL] $_"
    }
    exit 1
}

$jsonFailures = New-Object System.Collections.Generic.List[string]
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
        $jsonFailures.Add("${relative}: $($_.Exception.Message)")
    }
}

if ($jsonFailures.Count -gt 0) {
    $jsonFailures | ForEach-Object { Write-Output "[JSON-FAIL] $_" }
    exit 1
}

Write-Output "[OK] Public snapshot required paths are present."
Write-Output "[OK] Governance rule references are present."
Write-Output "[OK] No submodules, local agent state, evidence archives, generated packages, oversized files, or private text markers found."
Write-Output "[OK] JSON files parse as UTF-8."
