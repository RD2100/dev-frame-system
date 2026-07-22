# register-hooks.ps1 - Activate CI preflight hooks for this project.
# Run once per clone with an explicit Python executable.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File register-hooks.ps1 -PythonExecutable C:\path\to\python.exe

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$HookDir = Join-Path $PSScriptRoot "hooks"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $HookDir "..")).Path.TrimEnd("\", "/")
$helper = Join-Path $HookDir "python-interpreter.ps1"

Write-Host "=== CI Preflight Registration ==="
Write-Host "Project: $RepoRoot"

$gitTopLevelOutput = @(& git -C $RepoRoot rev-parse --show-toplevel 2>$null)
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
    $RepoRoot,
    $gitTopLevel,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    Write-Host "[BLOCKED] Project must be the canonical Git top-level: $gitTopLevel"
    exit 1
}

$required = @(
    "pre-commit",
    "pre-commit.governance.ps1",
    "pre-push",
    "pre-push.governance.ps1",
    "python-interpreter.ps1"
)
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $HookDir $file) -PathType Leaf)) {
        Write-Host "[BLOCKED] Missing: hooks/$file - ensure ci-preflight template was copied correctly."
        exit 1
    }
}

. $helper
$interpreter = Register-CiPreflightPython `
    -ProjectRoot $RepoRoot `
    -PythonExecutable $PythonExecutable
if ($interpreter.Status -ne "PASS") {
    Write-Host "[BLOCKED] Python registration failed ($($interpreter.Health)): $($interpreter.Diagnostic)"
    exit 1
}

& git -C $RepoRoot config --local core.hooksPath hooks
if ($LASTEXITCODE -ne 0) {
    Write-Host "[BLOCKED] Failed to set repository-local core.hooksPath."
    exit 1
}
$configuredHookPath = @(& git -C $RepoRoot config --local --get core.hooksPath 2>$null)
if ($LASTEXITCODE -ne 0 -or $configuredHookPath.Count -eq 0 -or $configuredHookPath[-1] -ne "hooks") {
    Write-Host "[BLOCKED] core.hooksPath verification failed."
    exit 1
}

Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"
Write-Host "[OK] core.hooksPath = hooks"
Write-Host ""
Write-Host "=== Registration Complete ==="
Write-Host "Active hooks:"
Write-Host "  pre-commit : interpreter attestation + manifest auto-regen + ai_guard"
Write-Host "  pre-push   : interpreter attestation + ai_guard + drift check + governance gate"
Write-Host ""
Write-Host "Customize expected-files.txt and manifest-ignore.txt for this project."
exit 0
