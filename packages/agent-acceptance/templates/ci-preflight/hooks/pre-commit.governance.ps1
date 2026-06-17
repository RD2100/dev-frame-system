# pre-commit.governance.ps1 — Pre-commit governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: manifest auto-regen → compliance checks.
# Exit 0: allow commit. Exit 1: block commit.

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== Pre-Commit Governance Gate ==="

# ---- 1. Manifest auto-regeneration ----
Write-Host "[1/2] Manifest auto-regeneration..."
$updateScript = Join-Path $ProjectRoot "scripts\Update-GovernanceManifest.ps1"
$manifestPath = "hooks\sealed-files-manifest.json"

if (Test-Path $updateScript) {
    Push-Location $ProjectRoot
    try {
        $before = if (Test-Path $manifestPath) { Get-Content $manifestPath -Raw } else { "" }
        & powershell -ExecutionPolicy Bypass -File $updateScript | Out-Null
        $after = if (Test-Path $manifestPath) { Get-Content $manifestPath -Raw } else { "" }
        if ($before -ne $after) {
            git add $manifestPath 2>$null
            Write-Host "[OK] Manifest regenerated and staged."
        } else {
            Write-Host "[OK] Manifest up to date."
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[SKIP] Update-GovernanceManifest.ps1 not found."
}
Write-Host ""

# ---- 2. Compliance checks ----
Write-Host "[2/2] Compliance checks..."

# --- Core check: ai_guard.py (secret scan) ---
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot
    try {
        & python $aiGuard staged 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[BLOCKED] ai_guard.py found issues. Fix before commit."
            Pop-Location
            exit 1
        }
        Write-Host "  ai_guard: PASS"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  ai_guard: not found — SKIP"
}

# --- Add project-specific checks here ---
# Example: run tests, lint, type-check, etc.
# if (Test-Path "scripts\pre-commit-tests.ps1") {
#     & powershell -File "scripts\pre-commit-tests.ps1"
#     if ($LASTEXITCODE -ne 0) { exit 1 }
# }

Write-Host ""
Write-Host "=== Pre-Commit PASS ==="
exit 0
