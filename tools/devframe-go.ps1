<#
.SYNOPSIS
    Project-local /go wrapper for DevFrame coding-agent fan-out.
.DESCRIPTION
    Previews or launches a DevFrame coding session from the project root. The
    default mode is token-safe preview: it shows shard targets and worker
    command templates without creating rdgoal packets or running workers.
.EXAMPLE
    .\tools\devframe-go.ps1 -Goal "Fix the failing tests"
    .\tools\devframe-go.ps1 -Goal "Fix the failing tests" -Changed -Prepare
    .\tools\devframe-go.ps1 -Goal "Fix the failing tests" -Changed -Execute
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Goal,

    [string]$ProjectRoot = "",
    [string[]]$Target = @(),
    [string]$Agents = "auto",
    [int]$MaxAgents = 4,
    [string]$RuntimeDir = "",
    [ValidateSet("opencode", "codex", "claude")]
    [string]$Worker = "opencode",
    [string]$Model = "",
    [string]$OpencodeAgent = "build",
    [switch]$Changed,
    [switch]$Prepare,
    [switch]$Execute,
    [string[]]$Command = @()
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
}

if ($Prepare -and $Execute) {
    [Console]::Error.WriteLine("Use either -Prepare or -Execute, not both.")
    exit 2
}

if (-not (Get-Command devframe -ErrorAction SilentlyContinue)) {
    Write-Error "devframe CLI not found. Install devframe-control-plane before using this wrapper."
    exit 1
}

$argsList = @(
    "code",
    $Goal,
    "--project",
    $ProjectRoot,
    "--agents",
    $Agents,
    "--max-agents",
    [string]$MaxAgents,
    "--worker",
    $Worker,
    "--opencode-agent",
    $OpencodeAgent
)

foreach ($item in $Target) {
    $argsList += @("--target", $item)
}

if ($Changed) {
    $argsList += "--changed"
}

if ($RuntimeDir) {
    $argsList += @("--runtime-dir", $RuntimeDir)
}

if ($Model) {
    $argsList += @("--model", $Model)
}

if ($Execute) {
    $argsList += "--execute"
} elseif (-not $Prepare) {
    $argsList += "--preview"
}

if ($Command.Count -gt 0) {
    $argsList += "--command"
    $argsList += $Command
}

& devframe @argsList
exit $LASTEXITCODE
