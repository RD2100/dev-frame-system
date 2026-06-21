param(
    [string]$Root = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)

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

$ignoredGeneratedDirs = @(
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache"
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

$violations = New-Object System.Collections.Generic.List[string]
Get-ChildItem -LiteralPath $rootPath -Recurse -Force | ForEach-Object {
    if ($_.FullName -like (Join-Path $rootPath ".git*")) {
        return
    }

    $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $_.FullName

    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $_.FullName) {
        return
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

$jsonFailures = New-Object System.Collections.Generic.List[string]
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
Get-ChildItem -LiteralPath $rootPath -Recurse -Filter "*.json" -File | ForEach-Object {
    if (Test-IsUnderIgnoredGeneratedDir -BasePath $rootPath -TargetPath $_.FullName) {
        return
    }

    try {
        $jsonText = [System.IO.File]::ReadAllText($_.FullName, $utf8)
        if ($jsonText.Length -gt 0 -and $jsonText[0] -eq [char]0xFEFF) {
            $jsonText = $jsonText.Substring(1)
        }
        $jsonText | ConvertFrom-Json | Out-Null
    } catch {
        $relative = Get-RelativeSnapshotPath -BasePath $rootPath -TargetPath $_.FullName
        $jsonFailures.Add("${relative}: $($_.Exception.Message)")
    }
}

if ($jsonFailures.Count -gt 0) {
    $jsonFailures | ForEach-Object { Write-Output "[JSON-FAIL] $_" }
    exit 1
}

Write-Output "[OK] Public snapshot required paths are present."
Write-Output "[OK] No submodules, local agent state, evidence archives, generated packages, or oversized files found."
Write-Output "[OK] JSON files parse as UTF-8."
