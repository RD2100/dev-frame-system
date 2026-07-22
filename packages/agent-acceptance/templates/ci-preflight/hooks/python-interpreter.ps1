# python-interpreter.ps1 - Shared configured-Python attestation and receipt helpers.

$script:CiPreflightHookVersion = "1.1.0"
$script:CiPreflightPythonConfigPath = "devframe/ci-preflight-python.json"

function Test-CiPreflightSamePath {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    $leftFull = [System.IO.Path]::GetFullPath($Left).TrimEnd("\", "/")
    $rightFull = [System.IO.Path]::GetFullPath($Right).TrimEnd("\", "/")
    return [string]::Equals(
        $leftFull,
        $rightFull,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Get-CiPreflightSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function New-CiPreflightPythonResult {
    param(
        [AllowNull()]$Executable,
        [AllowNull()]$Version,
        [Parameter(Mandatory = $true)][string]$SelectionSource,
        [Parameter(Mandatory = $true)][string]$Health,
        [AllowNull()]$ExitCode,
        [Parameter(Mandatory = $true)][ValidateSet("PASS", "BLOCKED")][string]$Status,
        [Parameter(Mandatory = $true)][long]$DurationMs,
        [AllowNull()]$Diagnostic
    )

    return [pscustomobject][ordered]@{
        Executable      = $Executable
        Version         = $Version
        SelectionSource = $SelectionSource
        Health          = $Health
        ExitCode        = $ExitCode
        Status          = $Status
        DurationMs      = [Math]::Max(0, $DurationMs)
        Diagnostic      = $Diagnostic
    }
}

function Get-CiPreflightPythonConfigFile {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $root = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
    $gitPathOutput = @(
        & git -C $root rev-parse --git-path $script:CiPreflightPythonConfigPath 2>$null
    )
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0 -or $gitPathOutput.Count -eq 0) {
        throw "Unable to resolve repository-local Python configuration path."
    }

    $gitPath = [string]$gitPathOutput[-1]
    if ([string]::IsNullOrWhiteSpace($gitPath)) {
        throw "Git returned an empty repository-local Python configuration path."
    }
    if (-not [System.IO.Path]::IsPathRooted($gitPath)) {
        $gitPath = Join-Path $root $gitPath
    }
    return [System.IO.Path]::GetFullPath($gitPath)
}

function Invoke-CiPreflightPythonProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$SelectionSource
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $probeCode = "import json, os, sys; print(json.dumps({'executable': os.path.realpath(sys.executable), 'version': '.'.join(map(str, sys.version_info[:3]))}, separators=(',', ':')))"
    $probeOutput = @()
    $probeExitCode = $null
    try {
        $probeOutput = @(& $Executable -I -c $probeCode 2>&1)
        $probeExitCode = $LASTEXITCODE
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $Executable `
            -Version $null `
            -SelectionSource $SelectionSource `
            -Health "probe_failed" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }
    $stopwatch.Stop()

    if ($probeExitCode -ne 0) {
        return (New-CiPreflightPythonResult `
            -Executable $Executable `
            -Version $null `
            -SelectionSource $SelectionSource `
            -Health "probe_failed" `
            -ExitCode $probeExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Configured executable failed the Python health probe.")
    }

    $probe = $null
    for ($index = $probeOutput.Count - 1; $index -ge 0; $index--) {
        try {
            $candidate = [string]$probeOutput[$index]
            if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                $parsed = $candidate | ConvertFrom-Json -ErrorAction Stop
                if ($parsed.executable -is [string] -and $parsed.version -is [string]) {
                    $probe = $parsed
                    break
                }
            }
        } catch {
            continue
        }
    }
    if ($null -eq $probe) {
        return (New-CiPreflightPythonResult `
            -Executable $Executable `
            -Version $null `
            -SelectionSource $SelectionSource `
            -Health "probe_failed" `
            -ExitCode $probeExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Configured executable returned no valid Python probe document.")
    }

    $reportedExecutable = $null
    try {
        $reportedExecutable = (Resolve-Path -LiteralPath $probe.executable -ErrorAction Stop).Path
    } catch {
        return (New-CiPreflightPythonResult `
            -Executable $Executable `
            -Version ([string]$probe.version) `
            -SelectionSource $SelectionSource `
            -Health "path_drift" `
            -ExitCode $probeExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Python reported an executable path that cannot be resolved.")
    }

    return (New-CiPreflightPythonResult `
        -Executable $reportedExecutable `
        -Version ([string]$probe.version) `
        -SelectionSource $SelectionSource `
        -Health "healthy" `
        -ExitCode $probeExitCode `
        -Status "PASS" `
        -DurationMs $stopwatch.ElapsedMilliseconds `
        -Diagnostic $null)
}

function Register-CiPreflightPython {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$PythonExecutable
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $resolvedExecutable = $null
    try {
        $resolvedExecutable = (Resolve-Path -LiteralPath $PythonExecutable -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $resolvedExecutable -PathType Leaf)) {
            throw "Configured Python path is not a file."
        }
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $null `
            -Version $null `
            -SelectionSource "explicit_parameter" `
            -Health "missing_executable" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }

    try {
        $beforeProbeHash = Get-CiPreflightSha256 -Path $resolvedExecutable
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $null `
            -SelectionSource "explicit_parameter" `
            -Health "probe_failed" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }

    $probe = Invoke-CiPreflightPythonProbe `
        -Executable $resolvedExecutable `
        -SelectionSource "explicit_parameter"
    if ($probe.Status -ne "PASS") {
        return $probe
    }
    if (-not (Test-CiPreflightSamePath -Left $resolvedExecutable -Right $probe.Executable)) {
        return (New-CiPreflightPythonResult `
            -Executable $probe.Executable `
            -Version $probe.Version `
            -SelectionSource "explicit_parameter" `
            -Health "path_drift" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $probe.DurationMs `
            -Diagnostic "Python reported a different executable than the explicit path.")
    }

    try {
        $afterProbeHash = Get-CiPreflightSha256 -Path $resolvedExecutable
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $probe.Version `
            -SelectionSource "explicit_parameter" `
            -Health "probe_failed" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }
    if ($beforeProbeHash -ne $afterProbeHash) {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $probe.Version `
            -SelectionSource "explicit_parameter" `
            -Health "binary_drift" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Python executable changed during registration.")
    }

    try {
        $configPath = Get-CiPreflightPythonConfigFile -ProjectRoot $ProjectRoot
        $configDirectory = Split-Path -Parent $configPath
        [System.IO.Directory]::CreateDirectory($configDirectory) | Out-Null
        $config = [ordered]@{
            schema_version   = "1.0.0"
            executable       = $resolvedExecutable
            version          = $probe.Version
            sha256           = $afterProbeHash
            selection_source = "explicit_parameter"
        }
        $temporaryPath = "$configPath.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText(
            $temporaryPath,
            (($config | ConvertTo-Json -Depth 4) + [Environment]::NewLine),
            $utf8
        )
        Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force -ErrorAction Stop
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $probe.Version `
            -SelectionSource "explicit_parameter" `
            -Health "invalid_config" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }

    $stopwatch.Stop()
    return (New-CiPreflightPythonResult `
        -Executable $resolvedExecutable `
        -Version $probe.Version `
        -SelectionSource "explicit_parameter" `
        -Health "healthy" `
        -ExitCode $probe.ExitCode `
        -Status "PASS" `
        -DurationMs $stopwatch.ElapsedMilliseconds `
        -Diagnostic $null)
}

function Get-CiPreflightPython {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $configPath = Get-CiPreflightPythonConfigFile -ProjectRoot $ProjectRoot
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $null `
            -Version $null `
            -SelectionSource "repo_local_config" `
            -Health "invalid_config" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $null `
            -Version $null `
            -SelectionSource "repo_local_config" `
            -Health "missing_config" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Repository-local Python configuration is missing.")
    }

    try {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 -ErrorAction Stop |
            ConvertFrom-Json -ErrorAction Stop
        if (
            $config.schema_version -ne "1.0.0" -or
            -not ($config.executable -is [string]) -or
            -not [System.IO.Path]::IsPathRooted($config.executable) -or
            -not ($config.version -is [string]) -or
            $config.version -notmatch '^\d+\.\d+\.\d+$' -or
            -not ($config.sha256 -is [string]) -or
            $config.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
            $config.selection_source -ne "explicit_parameter"
        ) {
            throw "Repository-local Python configuration has an invalid shape."
        }
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $null `
            -Version $null `
            -SelectionSource "repo_local_config" `
            -Health "invalid_config" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }

    $configuredExecutable = [System.IO.Path]::GetFullPath([string]$config.executable)
    $resolvedExecutable = $null
    try {
        $resolvedExecutable = (Resolve-Path -LiteralPath $configuredExecutable -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $resolvedExecutable -PathType Leaf)) {
            throw "Configured Python path is not a file."
        }
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $configuredExecutable `
            -Version $null `
            -SelectionSource ([string]$config.selection_source) `
            -Health "missing_executable" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }
    if (-not (Test-CiPreflightSamePath -Left $configuredExecutable -Right $resolvedExecutable)) {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $null `
            -SelectionSource ([string]$config.selection_source) `
            -Health "path_drift" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Configured Python path no longer resolves to the registered path.")
    }

    try {
        $currentHash = Get-CiPreflightSha256 -Path $resolvedExecutable
    } catch {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $null `
            -SelectionSource ([string]$config.selection_source) `
            -Health "probe_failed" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic $_.Exception.Message)
    }
    if ($currentHash -ne ([string]$config.sha256).ToLowerInvariant()) {
        $stopwatch.Stop()
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $null `
            -SelectionSource ([string]$config.selection_source) `
            -Health "binary_drift" `
            -ExitCode $null `
            -Status "BLOCKED" `
            -DurationMs $stopwatch.ElapsedMilliseconds `
            -Diagnostic "Configured Python executable hash differs from registration.")
    }

    $probe = Invoke-CiPreflightPythonProbe `
        -Executable $resolvedExecutable `
        -SelectionSource ([string]$config.selection_source)
    if ($probe.Status -ne "PASS") {
        return $probe
    }
    try {
        $afterProbeHash = Get-CiPreflightSha256 -Path $resolvedExecutable
    } catch {
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $probe.Version `
            -SelectionSource ([string]$config.selection_source) `
            -Health "probe_failed" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $probe.DurationMs `
            -Diagnostic $_.Exception.Message)
    }
    if ($afterProbeHash -ne ([string]$config.sha256).ToLowerInvariant()) {
        return (New-CiPreflightPythonResult `
            -Executable $resolvedExecutable `
            -Version $probe.Version `
            -SelectionSource ([string]$config.selection_source) `
            -Health "binary_drift" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $probe.DurationMs `
            -Diagnostic "Configured Python executable changed during its health probe.")
    }
    if (-not (Test-CiPreflightSamePath -Left $resolvedExecutable -Right $probe.Executable)) {
        return (New-CiPreflightPythonResult `
            -Executable $probe.Executable `
            -Version $probe.Version `
            -SelectionSource ([string]$config.selection_source) `
            -Health "path_drift" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $probe.DurationMs `
            -Diagnostic "Python now reports a different executable path.")
    }
    if ($probe.Version -ne [string]$config.version) {
        return (New-CiPreflightPythonResult `
            -Executable $probe.Executable `
            -Version $probe.Version `
            -SelectionSource ([string]$config.selection_source) `
            -Health "version_drift" `
            -ExitCode $probe.ExitCode `
            -Status "BLOCKED" `
            -DurationMs $probe.DurationMs `
            -Diagnostic "Python version differs from registration.")
    }

    return $probe
}

function New-CiPreflightStage {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()]$ExitCode,
        [Parameter(Mandatory = $true)][long]$DurationMs,
        [AllowNull()]$OutputFile = $null
    )

    return [pscustomobject][ordered]@{
        name        = $Name
        exit_code   = $ExitCode
        output_file = $OutputFile
        duration_ms = [Math]::Max(0, $DurationMs)
    }
}

function Write-CiPreflightReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][ValidateSet("pre-commit", "pre-push", "ci-preflight")][string]$HookName,
        [Parameter(Mandatory = $true)]$Interpreter,
        [Parameter(Mandatory = $true)][object[]]$Stages,
        [Parameter(Mandatory = $true)][ValidateSet("PASS", "BLOCKED")][string]$OverallResult
    )

    if ($Stages.Count -lt 1) {
        throw "At least one receipt stage is required."
    }
    $root = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path

    $branchOutput = @(& git -C $root symbolic-ref --quiet --short HEAD 2>$null)
    $branch = if ($LASTEXITCODE -eq 0 -and $branchOutput.Count -gt 0) {
        [string]$branchOutput[-1]
    } else {
        "HEAD"
    }

    $commitOutput = @(& git -C $root rev-list --count HEAD 2>$null)
    $commitCount = 0
    if ($LASTEXITCODE -eq 0 -and $commitOutput.Count -gt 0) {
        [void][int]::TryParse([string]$commitOutput[-1], [ref]$commitCount)
    }

    $stagedOutput = @(& git -C $root diff --cached --name-only 2>$null)
    $stagedCount = if ($LASTEXITCODE -eq 0) {
        @($stagedOutput | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count
    } else {
        0
    }

    $receipt = [ordered]@{
        timestamp          = [DateTimeOffset]::UtcNow.ToString("o")
        hook_name          = $HookName
        hook_version       = $script:CiPreflightHookVersion
        python_interpreter = [ordered]@{
            executable       = $Interpreter.Executable
            version          = $Interpreter.Version
            selection_source = $Interpreter.SelectionSource
            health            = $Interpreter.Health
            exit_code          = $Interpreter.ExitCode
            status             = $Interpreter.Status
        }
        stages             = @($Stages)
        git_context        = [ordered]@{
            branch            = $branch
            commit_count      = $commitCount
            staged_file_count = $stagedCount
        }
        overall_result     = $OverallResult
    }

    $receiptDirectory = Join-Path $root "_evidence\hook-output"
    [System.IO.Directory]::CreateDirectory($receiptDirectory) | Out-Null
    $receiptPath = Join-Path $receiptDirectory "latest.json"
    $temporaryPath = "$receiptPath.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        (($receipt | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        $utf8
    )
    Move-Item -LiteralPath $temporaryPath -Destination $receiptPath -Force -ErrorAction Stop
    return $receiptPath
}
