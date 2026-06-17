# ci-preflight.ps1 — Run all CI-equivalent checks locally.
# Use before push to verify CI will pass. Same commands CI runs.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ci-preflight.ps1

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$errors = 0

Write-Host "=== CI Preflight ==="
Write-Host "Project: $ProjectRoot"
Write-Host ""

# 1. AI Guard
Write-Host "[1/3] AI Guard..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot
    try { & python $aiGuard full 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

# 2. Drift Check
Write-Host "[2/3] Drift Check..."
$drift = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path $drift) {
    Push-Location $ProjectRoot
    try { & powershell -ExecutionPolicy Bypass -File $drift 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

# 3. Governance Gate
Write-Host "[3/3] Governance Gate..."
$gate = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path $gate) {
    Push-Location $ProjectRoot
    try { & powershell -ExecutionPolicy Bypass -File $gate -Mode blocking 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

if ($errors -gt 0) {
    Write-Host "=== $errors check(s) FAILED ==="
    exit 1
}
Write-Host "=== All checks PASSED ==="
exit 0
