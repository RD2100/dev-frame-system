# ci-preflight.ps1 - Run all CI-equivalent checks locally.
# Use before push to verify CI will pass. Same commands CI runs.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ci-preflight.ps1

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$helper = Join-Path $ProjectRoot "hooks\python-interpreter.ps1"
$errors = 0

Write-Host "=== CI Preflight ==="
Write-Host "Project: $ProjectRoot"
Write-Host ""

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
            -HookName "ci-preflight" `
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

# 1. AI Guard
Write-Host "[1/3] AI Guard..."
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
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

# 2. Drift Check
Write-Host "[2/3] Drift Check..."
$drift = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path -LiteralPath $drift -PathType Leaf) {
    $driftTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $drift 2>&1
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
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

# 3. Governance Gate
Write-Host "[3/3] Governance Gate..."
$gate = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path -LiteralPath $gate -PathType Leaf) {
    $gateTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $gate -Mode blocking 2>&1
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
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

$overallResult = if ($errors -gt 0) { "BLOCKED" } else { "PASS" }
try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "ci-preflight" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult $overallResult | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write receipt: $($_.Exception.Message)"
    exit 1
}

if ($errors -gt 0) {
    Write-Host "=== $errors check(s) FAILED ==="
    exit 1
}
Write-Host "=== All checks PASSED ==="
exit 0
