param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$controlPlaneRoot = Join-Path $rootPath "packages\control-plane"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("devframe-wheel-smoke-" + [guid]::NewGuid().ToString("N"))
$wheelDir = Join-Path $tempRoot "wheelhouse"
$venvDir = Join-Path $tempRoot "venv"
$projectDir = Join-Path $tempRoot "demo-project"
$runtimeDir = Join-Path $tempRoot "runtime"

function Invoke-Step {
    param(
        [string]$Label,
        [string]$Executable,
        [string[]]$Arguments
    )

    Write-Output "[RUN] $Label"
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Remove-LocalBuildArtifacts {
    $artifactPaths = @(
        "packages\control-plane\build",
        "packages\control-plane\dist",
        "packages\control-plane\devframe_control_plane.egg-info"
    )

    foreach ($relativePath in $artifactPaths) {
        $path = Join-Path $rootPath $relativePath
        if (Test-Path -LiteralPath $path) {
            $resolved = (Resolve-Path $path).Path
            if (-not $resolved.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove outside repository: $resolved"
            }
            Remove-Item -LiteralPath $resolved -Recurse -Force
            Write-Output "[CLEAN] $relativePath"
        }
    }
}

try {
    New-Item -ItemType Directory -Path $wheelDir | Out-Null

    Invoke-Step "build control-plane wheel" "python" @(
        "-m", "pip", "wheel", $controlPlaneRoot, "-w", $wheelDir, "--no-deps"
    )

    $wheel = Get-ChildItem -LiteralPath $wheelDir -Filter "*.whl" | Select-Object -First 1
    if (-not $wheel) {
        throw "Wheel was not produced in $wheelDir"
    }

    Invoke-Step "create smoke venv" "python" @("-m", "venv", $venvDir)
    $python = Join-Path $venvDir "Scripts\python.exe"
    $devframe = Join-Path $venvDir "Scripts\devframe.exe"
    $rdgoal = Join-Path $venvDir "Scripts\rdgoal.exe"

    Invoke-Step "install wheel" $python @("-m", "pip", "install", $wheel.FullName)
    Invoke-Step "devframe doctor" $devframe @("doctor")
    Invoke-Step "devframe init" $devframe @("init", "code_project", $projectDir)
    Invoke-Step "devframe run" $devframe @("run", "--pipeline", (Join-Path $projectDir "PIPELINE.yaml"))
    Invoke-Step "rdgoal" $rdgoal @(
        $projectDir, "Build a working MVP prototype.", "--runtime-dir", $runtimeDir, "--apply-rdinit"
    )

    $outbox = Join-Path $runtimeDir "rdgoal-outbox\demo-project"
    $packet = Get-ChildItem -LiteralPath $outbox -Directory | Select-Object -First 1
    if (-not $packet) {
        throw "rdgoal packet not produced in $outbox"
    }

    Invoke-Step "rdgoal worker" $rdgoal @("worker", $packet.FullName, "--runtime-dir", $runtimeDir)
    Invoke-Step "rdgoal digest" $rdgoal @("digest", "--runtime-dir", $runtimeDir)

    Write-Output "[OK] Control-plane wheel smoke passed."
} finally {
    if (-not $KeepTemp -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
        Write-Output "[CLEAN] temp smoke directory"
    } elseif ($KeepTemp) {
        Write-Output "[KEEP] $tempRoot"
    }

    Remove-LocalBuildArtifacts
}
