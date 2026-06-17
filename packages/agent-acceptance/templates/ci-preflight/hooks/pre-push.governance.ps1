# pre-push.governance.ps1 — Pre-push governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: CI-equivalent checks before push.
# Exit 0: allow push. Exit 1: block push.

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$errors = 0

Write-Host "=== Pre-Push Governance Gate ==="

# ---- 1. Secret scan ----
Write-Host "[1/3] Secret scan..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot
    try {
        & python $aiGuard full 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[BLOCKED] ai_guard.py failed (exit=$LASTEXITCODE)"
            $errors++
        } else {
            Write-Host "  PASS"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  SKIP (ai_guard.py not found)"
}
Write-Host ""

# ---- 2. Governance drift check ----
Write-Host "[2/3] Drift check..."
$driftScript = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path $driftScript) {
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $driftScript 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[BLOCKED] Drift check failed (exit=$LASTEXITCODE)"
            $errors++
        } else {
            Write-Host "  PASS"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  SKIP (Test-GovernanceDrift.ps1 not found)"
}
Write-Host ""

# ---- 3. Governance gate (repo diff) ----
Write-Host "[3/3] Governance gate..."
$gateScript = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path $gateScript) {
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $gateScript -Mode blocking 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[BLOCKED] Gate failed (exit=$LASTEXITCODE)"
            $errors++
        } else {
            Write-Host "  PASS"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  SKIP (Test-Governance.ps1 not found)"
}
Write-Host ""

# ---- 4. Add project-specific checks here ----
# Example:
# $testScript = Join-Path $ProjectRoot "scripts\Run-Tests.ps1"
# if (Test-Path $testScript) {
#     & powershell -File $testScript
#     if ($LASTEXITCODE -ne 0) { $errors++ }
# }

if ($errors -gt 0) {
    Write-Host "=== BLOCKED: $errors check(s) failed. Fix before push. ==="
    exit 1
}
Write-Host "=== PASS: All checks passed ==="
exit 0
