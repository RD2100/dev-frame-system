# pre-commit.governance.ps1 - Pre-commit governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: configured-Python attestation -> manifest auto-regen -> compliance checks.
# Exit 0: allow commit. Exit 1: block commit.

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$helper = Join-Path $PSScriptRoot "python-interpreter.ps1"

Write-Host "=== Pre-Commit Governance Gate ==="

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
            -HookName "pre-commit" `
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

# ---- 1. Manifest auto-regeneration ----
Write-Host "[1/2] Manifest auto-regeneration..."
$updateScript = Join-Path $ProjectRoot "scripts\Update-GovernanceManifest.ps1"
$manifestPath = "hooks\sealed-files-manifest.json"

if (Test-Path -LiteralPath $updateScript -PathType Leaf) {
    $manifestTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $manifestExitCode = 0
    Push-Location $ProjectRoot
    try {
        $before = if (Test-Path -LiteralPath $manifestPath) {
            Get-Content -LiteralPath $manifestPath -Raw
        } else {
            ""
        }
        & powershell -ExecutionPolicy Bypass -File $updateScript | Out-Null
        $manifestExitCode = $LASTEXITCODE
        $after = if (Test-Path -LiteralPath $manifestPath) {
            Get-Content -LiteralPath $manifestPath -Raw
        } else {
            ""
        }
        if ($manifestExitCode -eq 0 -and $before -ne $after) {
            git add -- $manifestPath 2>$null
            Write-Host "[OK] Manifest regenerated and staged."
        } elseif ($manifestExitCode -eq 0) {
            Write-Host "[OK] Manifest up to date."
        } else {
            Write-Host "[BLOCKED] Manifest regeneration failed (exit=$manifestExitCode)."
        }
    } finally {
        Pop-Location
        $manifestTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "manifest-regen" `
        -ExitCode $manifestExitCode `
        -DurationMs $manifestTimer.ElapsedMilliseconds
    if ($manifestExitCode -ne 0) {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-commit" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
        exit 1
    }
} else {
    Write-Host "[SKIP] Update-GovernanceManifest.ps1 not found."
}
Write-Host ""

# ---- 2. Compliance checks ----
Write-Host "[2/2] Compliance checks..."

$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path -LiteralPath $aiGuard -PathType Leaf) {
    $guardTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & $interpreter.Executable $aiGuard staged 2>&1 | Out-Null
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
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-commit" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
        Write-Host "[BLOCKED] ai_guard.py found issues. Fix before commit."
        exit 1
    }
    Write-Host "  ai_guard: PASS"
} else {
    Write-Host "  ai_guard: not found - SKIP"
}

# --- Add project-specific checks here ---
# Example: run tests, lint, type-check, etc.

try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "pre-commit" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult "PASS" | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write PASS receipt: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "=== Pre-Commit PASS ==="
exit 0
