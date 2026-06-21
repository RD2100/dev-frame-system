param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)

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
Invoke-Step "public snapshot" "powershell" @(
    "-ExecutionPolicy", "Bypass", "-File", (Join-Path $rootPath "scripts\verify-public-snapshot.ps1")
)
Invoke-Step "control-plane wheel smoke" "powershell" @(
    "-ExecutionPolicy", "Bypass", "-File", (Join-Path $rootPath "scripts\verify-control-plane-wheel.ps1")
)
Invoke-Step "git diff whitespace" "git" @("diff", "--check")

Write-Output "[OK] Release verification passed."
