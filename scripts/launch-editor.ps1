# Launch the DevFrame T3 editor (the integrated T3 Code desktop client).
#
# This is the real product surface: the T3 Code native desktop client wired to
# DevFrame's read model. `devframe client t3desktop` installs the bridge bundle
# into the local T3 checkout, serves the DevFrame bridge on port 8788, then runs
# the T3 desktop launcher (Electron). The T3 window is the editor; today it reads
# DevFrame projects/threads/sessions read-only (write-back is a future gate).
#
# By default this runs the PRODUCTION build (--prod): the prebuilt renderer is
# loaded with no Vite dev server and no file watchers, so startup is fast and
# memory use is low. The first production launch (or any launch after deleting
# the build) runs `pnpm build:desktop` once, which can take a few minutes; later
# launches are quick. Pass -Dev to use the slower Vite dev server instead (only
# needed while actively editing the RD-Code fork source). Pass -Rebuild to force
# a fresh production build before starting.
#
# Prerequisites (already verified by `devframe client doctor`): a local T3 Code
# checkout under .devframe-runtime/external/t3code with node_modules installed,
# Node 24+, and pnpm.

param(
    [switch]$Dev,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pkg = Join-Path $repoRoot "packages\control-plane"
$t3 = Join-Path $repoRoot ".devframe-runtime\external\t3code"
$port = 8788

if (-not (Test-Path (Join-Path $t3 "devframe.t3desktop.mjs"))) {
    Write-Error "T3 editor checkout not found at $t3. Run: devframe client bridge --t3-root <T3 checkout>"
    exit 1
}

$modeLabel = if ($Dev) { "dev (Vite dev server)" } else { "production build (fast, low memory)" }

Write-Host "DevFrame T3 editor"
Write-Host "Bridge server : http://127.0.0.1:$port  (loopback only)"
Write-Host "T3 client     : $t3 (Electron desktop)"
Write-Host "Launch mode   : $modeLabel"
if (-not $Dev) {
    Write-Host "First production launch builds the UI once (a few minutes); later launches are fast. Close this window to stop."
} else {
    Write-Host "Dev mode rebuilds the UI on launch and keeps a dev server resident (slower, higher memory). Close this window to stop."
}
Write-Host ""

# Give the desktop client a fresh Windows AppUserModelID under the RD-Code brand.
# Windows caches the taskbar icon per AppUserModelID; the upstream default
# ("com.t3tools.t3code") keeps resurrecting the old T3 taskbar icon from cache
# even after the icon assets are replaced. A distinct RD-Code identity makes
# Windows use the current window icon (apps/desktop/resources/icon.ico).
$previousLocation = Get-Location
$previousAppUserModelId = $env:T3CODE_DESKTOP_APP_USER_MODEL_ID
$previousForceBuild = $env:DEVFRAME_T3_FORCE_BUILD
try {
    $env:T3CODE_DESKTOP_APP_USER_MODEL_ID = "com.rdcode.client"
    if ($Rebuild -and -not $Dev) {
        $env:DEVFRAME_T3_FORCE_BUILD = "1"
    }

    Set-Location $pkg
    if ($Dev) {
        python -m control_plane.cli client t3desktop --t3-root "$t3" --port $port --overwrite-bridge
    } else {
        python -m control_plane.cli client t3desktop --t3-root "$t3" --port $port --overwrite-bridge --prod
    }
} finally {
    Set-Location $previousLocation
    if ($null -eq $previousAppUserModelId) {
        Remove-Item Env:T3CODE_DESKTOP_APP_USER_MODEL_ID -ErrorAction SilentlyContinue
    } else {
        $env:T3CODE_DESKTOP_APP_USER_MODEL_ID = $previousAppUserModelId
    }
    if ($null -eq $previousForceBuild) {
        Remove-Item Env:DEVFRAME_T3_FORCE_BUILD -ErrorAction SilentlyContinue
    } else {
        $env:DEVFRAME_T3_FORCE_BUILD = $previousForceBuild
    }
}
