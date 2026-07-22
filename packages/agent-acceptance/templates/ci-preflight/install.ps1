# install.ps1 - Install CI preflight hooks into an existing project.
# Copy this file plus the ci-preflight template to your machine, then run:
#
#   powershell -ExecutionPolicy Bypass -File install.ps1 -TargetProject C:\project -PythonExecutable C:\Python\python.exe

[CmdletBinding()]
param(
    [string]$TargetProject = (Get-Location).Path,
    [string]$TemplateDir,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TemplateDir)) {
    $TemplateDir = $PSScriptRoot
}

Write-Host "=== CI Preflight Install ==="
Write-Host "Target : $TargetProject"
Write-Host "Template: $TemplateDir"
Write-Host ""

# ---- 1. Validate ----
if (-not (Test-Path -LiteralPath $TargetProject -PathType Container)) {
    Write-Host "[BLOCKED] Target project not found: $TargetProject"
    exit 1
}
try {
    $TargetProject = (Resolve-Path -LiteralPath $TargetProject -ErrorAction Stop).Path.TrimEnd("\", "/")
} catch {
    Write-Host "[BLOCKED] Target project cannot be resolved: $($_.Exception.Message)"
    exit 1
}
$gitTopLevelOutput = @(& git -C $TargetProject rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or $gitTopLevelOutput.Count -eq 0) {
    Write-Host "[BLOCKED] Target is not a Git working tree."
    exit 1
}
try {
    $gitTopLevel = (
        Resolve-Path -LiteralPath ([string]$gitTopLevelOutput[-1]) -ErrorAction Stop
    ).Path.TrimEnd("\", "/")
} catch {
    Write-Host "[BLOCKED] Git top-level cannot be resolved: $($_.Exception.Message)"
    exit 1
}
if (-not [string]::Equals(
    $TargetProject,
    $gitTopLevel,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    Write-Host "[BLOCKED] Target project must be the canonical Git top-level: $gitTopLevel"
    exit 1
}

$required = @(
    "hooks/pre-commit",
    "hooks/pre-commit.governance.ps1",
    "hooks/pre-push",
    "hooks/pre-push.governance.ps1",
    "hooks/python-interpreter.ps1",
    "register-hooks.ps1",
    "ci-preflight.ps1",
    "governance/expected-files.txt",
    "governance/manifest-ignore.txt"
)
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $TemplateDir $file) -PathType Leaf)) {
        Write-Host "[BLOCKED] Template missing: $file"
        exit 1
    }
}

# ---- 2. Copy hooks ----
Write-Host "[1/4] Copying hook files..."
$targetHooks = Join-Path $TargetProject "hooks"
$targetGovernance = Join-Path $TargetProject "governance"
New-Item -ItemType Directory -Force -Path $targetHooks | Out-Null
New-Item -ItemType Directory -Force -Path $targetGovernance | Out-Null

Copy-Item (Join-Path $TemplateDir "hooks/*") $targetHooks -Force
Copy-Item (Join-Path $TemplateDir "ci-preflight.ps1") $TargetProject -Force
Copy-Item (Join-Path $TemplateDir "register-hooks.ps1") $TargetProject -Force

$governanceFiles = @("expected-files.txt", "manifest-ignore.txt")
foreach ($governanceFile in $governanceFiles) {
    $source = Join-Path $TemplateDir "governance/$governanceFile"
    $destination = Join-Path $targetGovernance $governanceFile
    if (-not (Test-Path -LiteralPath $destination)) {
        Copy-Item $source $destination -Force
        Write-Host "  Created: governance/$governanceFile"
    } else {
        Write-Host "  Skipped: governance/$governanceFile (already exists - preserved)"
    }
}
Write-Host "  Done."

# ---- 3. Explicitly register copied hooks and Python ----
Write-Host "[2/4] Registering hooks with configured Python..."
$registrationScript = Join-Path $TargetProject "register-hooks.ps1"
& powershell `
    -NoProfile `
    -NonInteractive `
    -ExecutionPolicy Bypass `
    -File $registrationScript `
    -PythonExecutable $PythonExecutable
if ($LASTEXITCODE -ne 0) {
    Write-Host "[BLOCKED] Hook registration failed (exit=$LASTEXITCODE)."
    exit 1
}

# ---- 4. Detect existing governance tools ----
Write-Host "[3/4] Detecting governance tools..."
$tools = @{
    "tools/ai_guard.py"                     = "ai_guard (secret scan)"
    "scripts/Test-GovernanceDrift.ps1"      = "drift check"
    "scripts/Test-Governance.ps1"           = "governance gate"
    "scripts/Update-GovernanceManifest.ps1" = "manifest auto-regen"
    "scripts/sadp-audit.ps1"                = "sadp audit"
}
foreach ($tool in $tools.Keys) {
    $exists = Test-Path -LiteralPath (Join-Path $TargetProject $tool)
    $mark = if ($exists) { "[OK]" } else { "[  ]" }
    Write-Host "  $mark $($tools[$tool])"
}

# ---- 5. Verify ----
Write-Host "[4/4] Verifying..."
$hookPath = @(& git -C $TargetProject config --local --get core.hooksPath 2>$null)
if ($LASTEXITCODE -ne 0 -or $hookPath.Count -eq 0 -or $hookPath[-1] -ne "hooks") {
    Write-Host "[BLOCKED] Verification failed: core.hooksPath is not hooks."
    exit 1
}

Write-Host ""
Write-Host "=== Install Complete ==="
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit governance/expected-files.txt - add your project's governance file patterns"
Write-Host "  2. Edit governance/manifest-ignore.txt - add temp/archive directories to exclude"
Write-Host "  3. If you have Update-GovernanceManifest.ps1: generate initial manifest"
Write-Host "  4. Verify: powershell -File ci-preflight.ps1"
Write-Host ""
Write-Host "After setup, git commit and git push will auto-trigger checks."
Write-Host "Agent does not need to remember - git enforces hooks automatically."
exit 0
