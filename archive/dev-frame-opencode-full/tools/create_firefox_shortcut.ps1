$WshShell = New-Object -ComObject WScript.Shell
$StartMenu = [Environment]::GetFolderPath('Programs')
$ShortcutPath = Join-Path $StartMenu 'Mozilla Firefox.lnk'
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'D:\Program Files\Mozilla Firefox\firefox.exe'
$Shortcut.Save()
Write-Host "Created: $ShortcutPath"
