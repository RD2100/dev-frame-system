# Create a Desktop shortcut that opens the DevFrame editor (read-only visual
# control plane) via scripts/launch-editor.ps1.
#
# The shortcut itself is written to the user's Desktop (outside this repo) and is
# not committed. Re-run any time to recreate it.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repoRoot "scripts\launch-editor.ps1"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "DevFrame T3 Editor.lnk"

# Remove the earlier mislabeled shortcut if present (it pointed at the read-only
# diagnostic dashboard, not the T3 editor).
$oldLnk = Join-Path $desktop "DevFrame Editor.lnk"
if (Test-Path $oldLnk) { Remove-Item $oldLnk -Force }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.IconLocation = "shell32.dll,13"
$shortcut.Description = "Launch the DevFrame T3 desktop editor (read-only, wired to the DevFrame bridge)"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host "Created shortcut: $lnkPath"
Write-Host "Target: powershell -File $launcher"
