# install.ps1 — Install CI preflight hooks into an existing project.
# Copy this file + the ci-preflight/ template to your machine, then:
#
#   powershell -ExecutionPolicy Bypass -File install.ps1 -TargetProject "D:\my-project"
#
# Or run from within the target project (targets current directory):
#
#   cd D:\my-project
#   powershell -ExecutionPolicy Bypass -File D:\my-project\templates\ci-preflight\install.ps1

param(
    [string]$TargetProject = (Get-Location).Path,
    [string]$TemplateDir = "$PSScriptRoot"
)

$ErrorActionPreference = 'Stop'

Write-Host "=== CI Preflight Install ==="
Write-Host "Target : $TargetProject"
Write-Host "Template: $TemplateDir"
Write-Host ""

# ---- 1. Validate ----
if (-not (Test-Path $TargetProject)) {
    Write-Error "Target project not found: $TargetProject"
    exit 1
}

$required = @(
    "hooks/pre-commit", "hooks/pre-commit.governance.ps1",
    "hooks/pre-push", "hooks/pre-push.governance.ps1",
    "register-hooks.ps1", "ci-preflight.ps1",
    "governance/expected-files.txt", "governance/manifest-ignore.txt"
)
foreach ($f in $required) {
    if (-not (Test-Path (Join-Path $TemplateDir $f))) {
        Write-Error "Template missing: $f"
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

# Merge governance files (don't overwrite if they already exist with custom content)
$govFiles = @("expected-files.txt", "manifest-ignore.txt")
foreach ($gf in $govFiles) {
    $src = Join-Path $TemplateDir "governance/$gf"
    $dst = Join-Path $targetGovernance $gf
    if (-not (Test-Path $dst)) {
        Copy-Item $src $dst -Force
        Write-Host "  Created: governance/$gf"
    } else {
        Write-Host "  Skipped: governance/$gf (already exists — preserved)"
    }
}
Write-Host "  Done."

# ---- 3. Activate hooks ----
Write-Host "[2/4] Activating hooks..."
Push-Location $TargetProject
try {
    git config core.hooksPath hooks
    Write-Host "  core.hooksPath = hooks"
} finally {
    Pop-Location
}

# ---- 4. Detect existing governance tools ----
Write-Host "[3/4] Detecting governance tools..."
$tools = @{
    "tools/ai_guard.py"                        = "ai_guard (secret scan)"
    "scripts/Test-GovernanceDrift.ps1"         = "drift check"
    "scripts/Test-Governance.ps1"              = "governance gate"
    "scripts/Update-GovernanceManifest.ps1"    = "manifest auto-regen"
    "scripts/sadp-audit.ps1"                   = "sadp audit"
}
foreach ($tool in $tools.Keys) {
    $exists = Test-Path (Join-Path $TargetProject $tool)
    $mark = if ($exists) { "[OK]" } else { "[  ]" }
    Write-Host "  $mark $($tools[$tool])"
}

# ---- 5. Verify ----
Write-Host "[4/4] Verifying..."
$hookPath = (git -C $TargetProject config core.hooksPath)
if ($hookPath -ne "hooks") {
    Write-Error "Verification failed: core.hooksPath = '$hookPath' (expected 'hooks')"
    exit 1
}

Write-Host ""
Write-Host "=== Install Complete ==="
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit governance/expected-files.txt — add your project's governance file patterns"
Write-Host "  2. Edit governance/manifest-ignore.txt — add temp/archive directories to exclude"
Write-Host "  3. If you have Update-GovernanceManifest.ps1: generate initial manifest"
Write-Host "  4. Verify: powershell -File ci-preflight.ps1"
Write-Host ""
Write-Host "After setup, git commit and git push will auto-trigger checks."
Write-Host "Agent does not need to remember — git enforces hooks automatically."
exit 0
