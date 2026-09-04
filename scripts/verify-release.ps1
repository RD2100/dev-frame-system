param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$powerShellExecutable = if ($PSVersionTable.PSEdition -eq "Core") {
    Join-Path $PSHOME "pwsh.exe"
} else {
    Join-Path $PSHOME "powershell.exe"
}
if (-not (Test-Path -LiteralPath $powerShellExecutable -PathType Leaf)) {
    throw "Current PowerShell host could not be resolved: $powerShellExecutable"
}

function Invoke-Step {
    param(
        [string]$Label,
        [string]$Executable,
        [string[]]$Arguments
    )

    Write-Output "[RUN] $Label"
    Push-Location $rootPath
    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Label failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Invoke-Step "pytest" "python" @("-m", "pytest", "-q")
Invoke-Step "public snapshot" $powerShellExecutable @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $rootPath "scripts\verify-public-snapshot.ps1"),
    "-FailOnTrackedForbidden"
)
$wheelSmokeArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
    (Join-Path $rootPath "scripts\verify-control-plane-wheel.ps1")
)
if ($Offline) {
    $wheelSmokeArguments += "-Offline"
}
Invoke-Step "control-plane wheel smoke" $powerShellExecutable $wheelSmokeArguments
Invoke-Step "git diff whitespace" "git" @("diff", "--check")

Write-Output "[OK] Release verification passed."
