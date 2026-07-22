# pre-push.governance.ps1 - Pre-push governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: configured-Python attestation plus CI-equivalent checks before push.
# Exit 0: allow push. Exit 1: block push.

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$helper = Join-Path $PSScriptRoot "python-interpreter.ps1"
$errors = 0

Write-Host "=== Pre-Push Governance Gate ==="

if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    Write-Host "[BLOCKED] hooks/python-interpreter.ps1 is missing."
    exit 1
}
. $helper

$interpreter = Get-CiPreflightPython -ProjectRoot $ProjectRoot
$stages = @(
    New-CiPreflightStage `
        -Name "python-interpreter" `
        -ExitCode $interpreter.ExitCode `
        -DurationMs $interpreter.DurationMs
)
if ($interpreter.Status -ne "PASS") {
    try {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-push" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
    } catch {
        Write-Host "[BLOCKED] Failed to write interpreter receipt: $($_.Exception.Message)"
    }
    Write-Host "[BLOCKED] Configured Python is not healthy ($($interpreter.Health))."
    exit 1
}
Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"

# ---- 1. Secret scan ----
Write-Host "[1/3] Secret scan..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path -LiteralPath $aiGuard -PathType Leaf) {
    $guardTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & $interpreter.Executable $aiGuard full 2>&1
        $guardExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $guardTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "ai-guard" `
        -ExitCode $guardExitCode `
        -DurationMs $guardTimer.ElapsedMilliseconds
    if ($guardExitCode -ne 0) {
        Write-Host "[BLOCKED] ai_guard.py failed (exit=$guardExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (ai_guard.py not found)"
}
Write-Host ""

# ---- 2. Governance drift check ----
Write-Host "[2/3] Drift check..."
$driftScript = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path -LiteralPath $driftScript -PathType Leaf) {
    $driftTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $driftScript 2>&1
        $driftExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $driftTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "governance-drift" `
        -ExitCode $driftExitCode `
        -DurationMs $driftTimer.ElapsedMilliseconds
    if ($driftExitCode -ne 0) {
        Write-Host "[BLOCKED] Drift check failed (exit=$driftExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (Test-GovernanceDrift.ps1 not found)"
}
Write-Host ""

# ---- 3. Governance gate (repo diff) ----
Write-Host "[3/3] Governance gate..."
$gateScript = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path -LiteralPath $gateScript -PathType Leaf) {
    $gateTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $gateScript -Mode blocking 2>&1
        $gateExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $gateTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "test-governance" `
        -ExitCode $gateExitCode `
        -DurationMs $gateTimer.ElapsedMilliseconds
    if ($gateExitCode -ne 0) {
        Write-Host "[BLOCKED] Gate failed (exit=$gateExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (Test-Governance.ps1 not found)"
}
Write-Host ""

$overallResult = if ($errors -gt 0) { "BLOCKED" } else { "PASS" }
try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "pre-push" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult $overallResult | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write receipt: $($_.Exception.Message)"
    exit 1
}

if ($errors -gt 0) {
    Write-Host "=== BLOCKED: $errors check(s) failed. Fix before push. ==="
    exit 1
}
Write-Host "=== PASS: All checks passed ==="
exit 0
