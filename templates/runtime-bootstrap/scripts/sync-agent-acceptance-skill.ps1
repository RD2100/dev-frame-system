$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $scriptDir "..\SKILL.md"
if (-not (Test-Path $source)) {
    Write-Host "SKIPPED source not found: $source"
    exit 0
}

$roots = @(
    "$HOME\.codex\skills",
    "$HOME\.claude\skills",
    "$HOME\.agents\skills"
)

foreach ($root in $roots) {
    if (-not (Test-Path $root)) {
        Write-Host "SKIPPED $root (skill root missing)"
        continue
    }
    $targetDir = Join-Path $root "agent-acceptance"
    $target = Join-Path $targetDir "SKILL.md"
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Copy-Item -Path $source -Destination $target -Force
    Write-Host "COPIED $target"
}
