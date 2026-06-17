# register-hooks.ps1 — Activate CI preflight hooks for this project.
# Run once per clone. No dependencies beyond Git 2.9+ and PowerShell.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File register-hooks.ps1

$ErrorActionPreference = 'Stop'
$HookDir = "$PSScriptRoot\hooks"
$RepoRoot = (Resolve-Path (Join-Path $HookDir "..")).Path

Write-Host "=== CI Preflight Registration ==="
Write-Host "Project: $RepoRoot"

# Verify hook files exist
$required = @("pre-commit", "pre-commit.governance.ps1", "pre-push", "pre-push.governance.ps1")
foreach ($f in $required) {
    if (-not (Test-Path (Join-Path $HookDir $f))) {
        Write-Error "Missing: hooks/$f — ensure ci-preflight template was copied correctly."
        exit 1
    }
}

# Set git hooks path
Push-Location $RepoRoot
try {
    git config core.hooksPath hooks
    Write-Host "[OK] core.hooksPath = hooks"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Registration Complete ==="
Write-Host "Active hooks:"
Write-Host "  pre-commit : manifest auto-regen + ai_guard"
Write-Host "  pre-push   : ai_guard + drift check + governance gate"
Write-Host ""
Write-Host "Customize expected-files.txt and manifest-ignore.txt for this project."
exit 0
