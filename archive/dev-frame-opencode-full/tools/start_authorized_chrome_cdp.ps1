param(
  [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$authPath = Join-Path $PSScriptRoot 'AUTHORIZED_GPT_CONVERSATION.json'
$profileDir = Join-Path $repoRoot '.chrome-cdp-profile'
$port = 9222

if (-not (Test-Path -LiteralPath $authPath)) {
  throw "AUTHORIZED_GPT_CONVERSATION.json not found: $authPath"
}

$auth = Get-Content -LiteralPath $authPath -Encoding UTF8 -Raw | ConvertFrom-Json
$authorizedUrl = [string]$auth.authorized_conversation_url
if ([string]::IsNullOrWhiteSpace($authorizedUrl) -or $authorizedUrl -notmatch '^https://chatgpt\.com/c/') {
  throw "authorized_conversation_url is missing or not a ChatGPT conversation URL"
}
if ($auth.allow_new_conversation -eq $true -or $auth.no_base_url_fallback -ne $true -or $auth.no_auto_new_conversation -ne $true) {
  throw "authorization guard flags are not fail-closed"
}

$chromeCandidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $chromeCandidates) {
  throw "chrome.exe not found in standard install paths"
}

$chromeExe = $chromeCandidates[0]
New-Item -ItemType Directory -Path $profileDir -Force | Out-Null

$existing = Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" |
  Where-Object { $_.CommandLine -match "--remote-debugging-port=$port" }

if ($existing) {
  $dedicated = @($existing | Where-Object { $_.CommandLine -like "*$profileDir*" })
  if (-not $dedicated) {
    [pscustomobject]@{
      status = "not_launched"
      reason = "port_9222_already_used_by_non_dedicated_chrome"
      required_action = "close/relaunch that Chrome with --remote-allow-origins=* or free port 9222"
      profile_dir = $profileDir
      authorized_conversation_url = $authorizedUrl
    } | ConvertTo-Json -Depth 3
    exit 2
  }
}

if (-not $NoLaunch) {
  $args = @(
    "--remote-debugging-port=$port",
    "--remote-allow-origins=*",
    "--user-data-dir=$profileDir",
    "--no-first-run",
    "--no-default-browser-check",
    $authorizedUrl
  )
  Start-Process -FilePath $chromeExe -ArgumentList $args -WindowStyle Hidden | Out-Null
  Start-Sleep -Seconds 3
}

[pscustomobject]@{
  status = "launched_or_already_running"
  chrome = $chromeExe
  remote_debugging_port = $port
  remote_allow_origins = "*"
  user_data_dir = $profileDir
  authorized_conversation_url = $authorizedUrl
} | ConvertTo-Json -Depth 3
