<#
.SYNOPSIS
    Bootstrap the RD2100 Agent Runtime governance framework in any project.
.DESCRIPTION
    Copies universal machine assets and generates one project plan plus the
    minimal agent/runtime entry files.
.PARAMETER ProjectName
    Auto-detected from directory or git remote if omitted.
.PARAMETER ProjectRoot
    Defaults to current directory.
.PARAMETER Platform
    Claude, Codex, or Both. Default: Both.
.PARAMETER Phase
    Phase designation. Default: 0-5.
.PARAMETER DryRun
    Preview without writing files.
.PARAMETER Force
    Overwrite existing files.
.EXAMPLE
    .\bootstrap.ps1
    .\bootstrap.ps1 -ProjectName "my-app" -ProjectRoot "D:\my-app" -DryRun
#>

param(
    [string]$ProjectName = "",
    [string]$ProjectRoot = "",
    [string]$Platform = "Both",
    [string]$Phase = "0-5",
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TemplateDir = $ScriptDir

if (-not $ProjectRoot) { $ProjectRoot = Get-Location | Select-Object -ExpandProperty Path }
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if (-not (Test-Path $ProjectRoot)) {
    if ($DryRun) { Write-Output "[DRY-RUN] Would create: $ProjectRoot" }
    else { New-Item -ItemType Directory -Force -Path $ProjectRoot | Out-Null; Write-Output "[INFO] Created: $ProjectRoot" }
}

if (-not $ProjectName) {
    $ProjectName = Split-Path $ProjectRoot -Leaf
    try { $gitRemote = git -C $ProjectRoot remote get-url origin 2>$null; if ($gitRemote -match '([^/]+?)(\.git)?$') { $ProjectName = $Matches[1] } } catch { }; $global:LASTEXITCODE = 0
}

$GitRemote = "N/A"; try { $GitRemote = git -C $ProjectRoot remote get-url origin 2>$null; if (-not $GitRemote) { $GitRemote = "N/A" } } catch { }; $global:LASTEXITCODE = 0
$CurrentDate = Get-Date -Format "yyyy-MM-dd"

Write-Output "[INFO] Project: $ProjectName | Root: $ProjectRoot | Platform: $Platform | Phase: $Phase"

$Placeholders = @{
    "{{PROJECT_NAME}}" = $ProjectName; "{{PROJECT_ROOT}}" = $ProjectRoot
    "{{CURRENT_DATE}}" = $CurrentDate; "{{GIT_REMOTE}}" = $GitRemote
    "{{PHASE}}" = $Phase; "{{PLATFORM}}" = $Platform
}
# Governance manifest placeholders filled after GEN step
$ManifestPlaceholders = @{}

$SourceRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
if (-not (Test-Path $SourceRoot)) { Write-Error "Source not found: $SourceRoot"; exit 1 }

function Copy-Universal($srcRel, $dstRel, $desc) {
    $src = Join-Path $SourceRoot $srcRel; $dst = Join-Path $ProjectRoot $dstRel
    if ($DryRun) { Write-Output "[DRY-RUN] Copy: $srcRel -> $dstRel ($desc)"; return }
    if (-not (Test-Path $src)) { Write-Error "Source missing: $src"; exit 1 }
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item -Path $src -Destination $dst -Recurse -Force
    Write-Output "[COPY] $srcRel -> $dstRel"
}

function New-FromTemplate($templateFile, $targetRel, $desc) {
    $tpl = Join-Path $TemplateDir $templateFile; $tgt = Join-Path $ProjectRoot $targetRel
    if (-not (Test-Path $tpl)) { Write-Error "Template missing: $tpl"; exit 1 }
    if ((Test-Path $tgt) -and -not $Force) { Write-Output "[SKIP] $targetRel (use -Force)"; return }
    if ($DryRun) { Write-Output "[DRY-RUN] Generate: $templateFile -> $targetRel ($desc)"; return }
    $c = Get-Content $tpl -Raw; foreach ($k in $Placeholders.Keys) { $c = $c.Replace($k, $Placeholders[$k]) }
    foreach ($k in $ManifestPlaceholders.Keys) { $c = $c.Replace($k, $ManifestPlaceholders[$k]) }
    New-Item -ItemType Directory -Force -Path (Split-Path $tgt -Parent) | Out-Null
    Set-Content $tgt $c -NoNewline -Encoding UTF8
    Write-Output "[GEN] $targetRel"
}

function Get-Sha256($path) {
    $stream = [System.IO.File]::OpenRead($path)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace("-", "")
        } finally {
            $sha256.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

Write-Output "`n=== Step 1: Universal Assets ==="
Copy-Universal "rules" "rules" "Public rule catalog"
Copy-Universal "schemas" "schemas" "18 JSON Schema files"
Copy-Universal "packages/agent-acceptance/fixtures/negative-acceptance" "packages/agent-acceptance/fixtures/negative-acceptance" "30 negative fixtures"
# Self-copy templates for re-bootstrap (skip in dry-run)
if (-not $DryRun) {
    $tplDest = Join-Path $ProjectRoot "templates\runtime-bootstrap"
    New-Item -ItemType Directory -Force -Path $tplDest | Out-Null
    Copy-Item -Path "$ScriptDir\*" -Destination $tplDest -Recurse -Force
    Write-Output "[COPY] Bootstrap templates self-copied"
} else {
    Write-Output "[DRY-RUN] Copy: templates/runtime-bootstrap/ -> templates/runtime-bootstrap/"
}

Write-Output "`n=== Step 2: Project-Specific Files ==="
New-FromTemplate "PLAN.template.md" "PLAN.md" "Single project plan"
New-FromTemplate "AGENTS.template.md" "AGENTS.md" "Agent entry point"
New-FromTemplate "capability-inventory.template.md" ".devframe/contracts/capability-inventory.md" "Capability inventory"
New-FromTemplate "tool-policy.template.md" ".devframe/contracts/tool-policy.md" "Tool policy"
New-FromTemplate "devframe-go.template.ps1" "tools/devframe-go.ps1" "/go coding-agent wrapper"

if ($DryRun) {
    Write-Output "[DRY-RUN] Generate: governance-manifest.template.md -> .devframe/contracts/governance-manifest.md (Governance manifest (hash-locked))"
    Write-Output "`n=== Step 3: Verification ==="
    Write-Output "[DRY-RUN] Done."
    exit 0
}

# --- Governance Manifest (hash-locked, generated after all files exist) ---
$p0Hash = Get-Sha256 (Join-Path $ProjectRoot "rules\core.md")
$sadpHash = Get-Sha256 (Join-Path $ProjectRoot "rules\orchestration.md")
$agentsHash = Get-Sha256 (Join-Path $ProjectRoot "AGENTS.md")
$ManifestPlaceholders = @{
    "{{P0_HASH}}" = $p0Hash
    "{{GATE0_HASH}}" = $sadpHash
    "{{VETO_HASH}}" = $sadpHash
    "{{PROTECTED_HASH}}" = $agentsHash
    "{{CUMULATIVE_HASH}}" = $sadpHash
}
New-FromTemplate "governance-manifest.template.md" ".devframe/contracts/governance-manifest.md" "Governance manifest (hash-locked)"

Write-Output "`n=== Step 3: Verification ==="

$unresolved = Select-String -Path (Join-Path $ProjectRoot "AGENTS.md") -Pattern "\{\{" -SimpleMatch 2>$null
if ($unresolved) { Write-Error "FAIL: Unresolved placeholders in AGENTS.md" } else { Write-Output "[OK] AGENTS.md: clean" }

$inv = Join-Path $ProjectRoot ".devframe\contracts\capability-inventory.md"
$n = (Select-String -Path $inv -Pattern "^## \d+\." 2>$null).Count
if ($n -ge 10) { Write-Output "[OK] Capabilities: $n" } else { Write-Error "FAIL: Only $n capabilities" }

Write-Output "`n=== Bootstrap Complete ==="
Write-Output "Next: 1) Complete PLAN.md 2) Register project capabilities (#11+) 3) Reviewer sign-off"
