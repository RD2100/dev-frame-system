# CI Preflight 安装提示词

直接复制整段发给智能体。

---

## 任务

为此项目安装 CI 预检门禁系统。完成后 `git commit` 和 `git push` 会自动触发检查，无需 agent 记忆。

## 要求

- 不要修改业务代码
- 不要 push 或创建 PR
- 不要绕过已有 hook
- 完成后运行验证并报告结果

## 执行步骤

### 第一步：检查环境

确认以下命令可用：

```bash
git --version          # 需要 2.9+
powershell -Command "echo ok"
```

如不可用，报告并停止。

### 第二步：确认 hooks 目录不存在

```bash
ls hooks/ 2>/dev/null && echo "hooks/ EXISTS" || echo "hooks/ NOT FOUND"
```

如果 `hooks/` 已存在且包含 `pre-commit` 或 `pre-push`，报告冲突并询问是否覆盖。如果不存在，继续。

### 第三步：创建文件

按以下结构创建文件。每个文件的完整内容在下方代码块中。

```
hooks/
  pre-commit
  pre-commit.governance.ps1
  pre-push
  pre-push.governance.ps1
  python-interpreter.ps1
governance/
  expected-files.txt
  manifest-ignore.txt
register-hooks.ps1
ci-preflight.ps1
```

#### hooks/pre-commit

```bash
#!/bin/bash
# Git pre-commit hook — delegates to governance gate.
# Activated via: git config core.hooksPath hooks
powershell -ExecutionPolicy Bypass -File "$(dirname "$0")/pre-commit.governance.ps1"
exit $?
```

创建后执行 `chmod +x hooks/pre-commit`。

#### hooks/pre-commit.governance.ps1

```powershell
# pre-commit.governance.ps1 - Pre-commit governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: configured-Python attestation -> manifest auto-regen -> compliance checks.
# Exit 0: allow commit. Exit 1: block commit.

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$helper = Join-Path $PSScriptRoot "python-interpreter.ps1"

Write-Host "=== Pre-Commit Governance Gate ==="

if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    Write-Host "[BLOCKED] hooks/python-interpreter.ps1 is missing."
    exit 1
}
. $helper

$interpreter = Get-CiPreflightPython -ProjectRoot $ProjectRoot
$stages = @(
    New-CiPreflightStage `
        -Name "python-interpreter" `
        -ExitCode $interpreter.ExitCode `
        -DurationMs $interpreter.DurationMs
)
if ($interpreter.Status -ne "PASS") {
    try {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-commit" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
    } catch {
        Write-Host "[BLOCKED] Failed to write interpreter receipt: $($_.Exception.Message)"
    }
    Write-Host "[BLOCKED] Configured Python is not healthy ($($interpreter.Health))."
    exit 1
}
Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"

# ---- 1. Manifest auto-regeneration ----
Write-Host "[1/2] Manifest auto-regeneration..."
$updateScript = Join-Path $ProjectRoot "scripts\Update-GovernanceManifest.ps1"
$manifestPath = "hooks\sealed-files-manifest.json"

if (Test-Path -LiteralPath $updateScript -PathType Leaf) {
    $manifestTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $manifestExitCode = 0
    Push-Location $ProjectRoot
    try {
        $before = if (Test-Path -LiteralPath $manifestPath) {
            Get-Content -LiteralPath $manifestPath -Raw
        } else {
            ""
        }
        & powershell -ExecutionPolicy Bypass -File $updateScript | Out-Null
        $manifestExitCode = $LASTEXITCODE
        $after = if (Test-Path -LiteralPath $manifestPath) {
            Get-Content -LiteralPath $manifestPath -Raw
        } else {
            ""
        }
        if ($manifestExitCode -eq 0 -and $before -ne $after) {
            git add -- $manifestPath 2>$null
            Write-Host "[OK] Manifest regenerated and staged."
        } elseif ($manifestExitCode -eq 0) {
            Write-Host "[OK] Manifest up to date."
        } else {
            Write-Host "[BLOCKED] Manifest regeneration failed (exit=$manifestExitCode)."
        }
    } finally {
        Pop-Location
        $manifestTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "manifest-regen" `
        -ExitCode $manifestExitCode `
        -DurationMs $manifestTimer.ElapsedMilliseconds
    if ($manifestExitCode -ne 0) {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-commit" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
        exit 1
    }
} else {
    Write-Host "[SKIP] Update-GovernanceManifest.ps1 not found."
}
Write-Host ""

# ---- 2. Compliance checks ----
Write-Host "[2/2] Compliance checks..."

$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path -LiteralPath $aiGuard -PathType Leaf) {
    $guardTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & $interpreter.Executable $aiGuard staged 2>&1 | Out-Null
        $guardExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $guardTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "ai-guard" `
        -ExitCode $guardExitCode `
        -DurationMs $guardTimer.ElapsedMilliseconds
    if ($guardExitCode -ne 0) {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-commit" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
        Write-Host "[BLOCKED] ai_guard.py found issues. Fix before commit."
        exit 1
    }
    Write-Host "  ai_guard: PASS"
} else {
    Write-Host "  ai_guard: not found - SKIP"
}

# --- Add project-specific checks here ---
# Example: run tests, lint, type-check, etc.

try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "pre-commit" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult "PASS" | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write PASS receipt: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "=== Pre-Commit PASS ==="
exit 0
```

#### hooks/pre-push

```bash
#!/bin/bash
# Git pre-push hook — delegates to governance gate.
# Activated via: git config core.hooksPath hooks
powershell -ExecutionPolicy Bypass -File "$(dirname "$0")/pre-push.governance.ps1"
exit $?
```

创建后执行 `chmod +x hooks/pre-push`。

#### hooks/pre-push.governance.ps1

```powershell
# pre-push.governance.ps1 - Pre-push governance gate (template).
# Copy to hooks/ in your project. Customize the check commands below.
# Runs: configured-Python attestation plus CI-equivalent checks before push.
# Exit 0: allow push. Exit 1: block push.

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$helper = Join-Path $PSScriptRoot "python-interpreter.ps1"
$errors = 0

Write-Host "=== Pre-Push Governance Gate ==="

if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    Write-Host "[BLOCKED] hooks/python-interpreter.ps1 is missing."
    exit 1
}
. $helper

$interpreter = Get-CiPreflightPython -ProjectRoot $ProjectRoot
$stages = @(
    New-CiPreflightStage `
        -Name "python-interpreter" `
        -ExitCode $interpreter.ExitCode `
        -DurationMs $interpreter.DurationMs
)
if ($interpreter.Status -ne "PASS") {
    try {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "pre-push" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
    } catch {
        Write-Host "[BLOCKED] Failed to write interpreter receipt: $($_.Exception.Message)"
    }
    Write-Host "[BLOCKED] Configured Python is not healthy ($($interpreter.Health))."
    exit 1
}
Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"

# ---- 1. Secret scan ----
Write-Host "[1/3] Secret scan..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path -LiteralPath $aiGuard -PathType Leaf) {
    $guardTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & $interpreter.Executable $aiGuard full 2>&1
        $guardExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $guardTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "ai-guard" `
        -ExitCode $guardExitCode `
        -DurationMs $guardTimer.ElapsedMilliseconds
    if ($guardExitCode -ne 0) {
        Write-Host "[BLOCKED] ai_guard.py failed (exit=$guardExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (ai_guard.py not found)"
}
Write-Host ""

# ---- 2. Governance drift check ----
Write-Host "[2/3] Drift check..."
$driftScript = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path -LiteralPath $driftScript -PathType Leaf) {
    $driftTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $driftScript 2>&1
        $driftExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $driftTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "governance-drift" `
        -ExitCode $driftExitCode `
        -DurationMs $driftTimer.ElapsedMilliseconds
    if ($driftExitCode -ne 0) {
        Write-Host "[BLOCKED] Drift check failed (exit=$driftExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (Test-GovernanceDrift.ps1 not found)"
}
Write-Host ""

# ---- 3. Governance gate (repo diff) ----
Write-Host "[3/3] Governance gate..."
$gateScript = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path -LiteralPath $gateScript -PathType Leaf) {
    $gateTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $gateScript -Mode blocking 2>&1
        $gateExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $gateTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "test-governance" `
        -ExitCode $gateExitCode `
        -DurationMs $gateTimer.ElapsedMilliseconds
    if ($gateExitCode -ne 0) {
        Write-Host "[BLOCKED] Gate failed (exit=$gateExitCode)"
        $errors++
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP (Test-Governance.ps1 not found)"
}
Write-Host ""

$overallResult = if ($errors -gt 0) { "BLOCKED" } else { "PASS" }
try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "pre-push" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult $overallResult | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write receipt: $($_.Exception.Message)"
    exit 1
}

if ($errors -gt 0) {
    Write-Host "=== BLOCKED: $errors check(s) failed. Fix before push. ==="
    exit 1
}
Write-Host "=== PASS: All checks passed ==="
exit 0
```

#### hooks/python-interpreter.ps1

```powershell
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
```

#### governance/expected-files.txt

```
# Governance expected files — add your project's governance-critical file patterns.
# Glob patterns resolved via Get-ChildItem -Recurse.
rules/*.md
AGENTS.md
.ai/policy.yaml
hooks/*.ps1
hooks/*.json
.github/workflows/*.yml
scripts/**/*.ps1
scripts/**/*.psm1
governance/*.txt
docs/**/*.md
```

#### governance/manifest-ignore.txt

```
# Only exclude: archive/, future/, test fixtures, temp output.
# NEVER exclude: rules/, hooks/, scripts/, governance/, .github/.
archive/**
**/future/**
scripts/tests/*.tests.ps1
runs/**
reports/**
.backup/**
__pycache__/**
node_modules/**
```

#### register-hooks.ps1

```powershell
# register-hooks.ps1 - Activate CI preflight hooks for this project.
# Run once per clone with an explicit Python executable.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File register-hooks.ps1 -PythonExecutable C:\path\to\python.exe

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$HookDir = Join-Path $PSScriptRoot "hooks"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $HookDir "..")).Path.TrimEnd("\", "/")
$helper = Join-Path $HookDir "python-interpreter.ps1"

Write-Host "=== CI Preflight Registration ==="
Write-Host "Project: $RepoRoot"

$gitTopLevelOutput = @(& git -C $RepoRoot rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or $gitTopLevelOutput.Count -eq 0) {
    Write-Host "[BLOCKED] Target is not a Git working tree."
    exit 1
}
try {
    $gitTopLevel = (
        Resolve-Path -LiteralPath ([string]$gitTopLevelOutput[-1]) -ErrorAction Stop
    ).Path.TrimEnd("\", "/")
} catch {
    Write-Host "[BLOCKED] Git top-level cannot be resolved: $($_.Exception.Message)"
    exit 1
}
if (-not [string]::Equals(
    $RepoRoot,
    $gitTopLevel,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    Write-Host "[BLOCKED] Project must be the canonical Git top-level: $gitTopLevel"
    exit 1
}

$required = @(
    "pre-commit",
    "pre-commit.governance.ps1",
    "pre-push",
    "pre-push.governance.ps1",
    "python-interpreter.ps1"
)
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $HookDir $file) -PathType Leaf)) {
        Write-Host "[BLOCKED] Missing: hooks/$file - ensure ci-preflight template was copied correctly."
        exit 1
    }
}

. $helper
$interpreter = Register-CiPreflightPython `
    -ProjectRoot $RepoRoot `
    -PythonExecutable $PythonExecutable
if ($interpreter.Status -ne "PASS") {
    Write-Host "[BLOCKED] Python registration failed ($($interpreter.Health)): $($interpreter.Diagnostic)"
    exit 1
}

& git -C $RepoRoot config --local core.hooksPath hooks
if ($LASTEXITCODE -ne 0) {
    Write-Host "[BLOCKED] Failed to set repository-local core.hooksPath."
    exit 1
}
$configuredHookPath = @(& git -C $RepoRoot config --local --get core.hooksPath 2>$null)
if ($LASTEXITCODE -ne 0 -or $configuredHookPath.Count -eq 0 -or $configuredHookPath[-1] -ne "hooks") {
    Write-Host "[BLOCKED] core.hooksPath verification failed."
    exit 1
}

Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"
Write-Host "[OK] core.hooksPath = hooks"
Write-Host ""
Write-Host "=== Registration Complete ==="
Write-Host "Active hooks:"
Write-Host "  pre-commit : interpreter attestation + manifest auto-regen + ai_guard"
Write-Host "  pre-push   : interpreter attestation + ai_guard + drift check + governance gate"
Write-Host ""
Write-Host "Customize expected-files.txt and manifest-ignore.txt for this project."
exit 0
```

#### ci-preflight.ps1

```powershell
# ci-preflight.ps1 - Run all CI-equivalent checks locally.
# Use before push to verify CI will pass. Same commands CI runs.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ci-preflight.ps1

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$helper = Join-Path $ProjectRoot "hooks\python-interpreter.ps1"
$errors = 0

Write-Host "=== CI Preflight ==="
Write-Host "Project: $ProjectRoot"
Write-Host ""

if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    Write-Host "[BLOCKED] hooks/python-interpreter.ps1 is missing."
    exit 1
}
. $helper

$interpreter = Get-CiPreflightPython -ProjectRoot $ProjectRoot
$stages = @(
    New-CiPreflightStage `
        -Name "python-interpreter" `
        -ExitCode $interpreter.ExitCode `
        -DurationMs $interpreter.DurationMs
)
if ($interpreter.Status -ne "PASS") {
    try {
        Write-CiPreflightReceipt `
            -ProjectRoot $ProjectRoot `
            -HookName "ci-preflight" `
            -Interpreter $interpreter `
            -Stages $stages `
            -OverallResult "BLOCKED" | Out-Null
    } catch {
        Write-Host "[BLOCKED] Failed to write interpreter receipt: $($_.Exception.Message)"
    }
    Write-Host "[BLOCKED] Configured Python is not healthy ($($interpreter.Health))."
    exit 1
}
Write-Host "[OK] Python $($interpreter.Version): $($interpreter.Executable)"

# 1. AI Guard
Write-Host "[1/3] AI Guard..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path -LiteralPath $aiGuard -PathType Leaf) {
    $guardTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & $interpreter.Executable $aiGuard full 2>&1
        $guardExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $guardTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "ai-guard" `
        -ExitCode $guardExitCode `
        -DurationMs $guardTimer.ElapsedMilliseconds
    if ($guardExitCode -ne 0) {
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

# 2. Drift Check
Write-Host "[2/3] Drift Check..."
$drift = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path -LiteralPath $drift -PathType Leaf) {
    $driftTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $drift 2>&1
        $driftExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $driftTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "governance-drift" `
        -ExitCode $driftExitCode `
        -DurationMs $driftTimer.ElapsedMilliseconds
    if ($driftExitCode -ne 0) {
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

# 3. Governance Gate
Write-Host "[3/3] Governance Gate..."
$gate = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path -LiteralPath $gate -PathType Leaf) {
    $gateTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $ProjectRoot
    try {
        & powershell -ExecutionPolicy Bypass -File $gate -Mode blocking 2>&1
        $gateExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $gateTimer.Stop()
    }
    $stages += New-CiPreflightStage `
        -Name "test-governance" `
        -ExitCode $gateExitCode `
        -DurationMs $gateTimer.ElapsedMilliseconds
    if ($gateExitCode -ne 0) {
        $errors++
        Write-Host "  FAILED"
    } else {
        Write-Host "  PASS"
    }
} else {
    Write-Host "  SKIP"
}
Write-Host ""

$overallResult = if ($errors -gt 0) { "BLOCKED" } else { "PASS" }
try {
    Write-CiPreflightReceipt `
        -ProjectRoot $ProjectRoot `
        -HookName "ci-preflight" `
        -Interpreter $interpreter `
        -Stages $stages `
        -OverallResult $overallResult | Out-Null
} catch {
    Write-Host "[BLOCKED] Failed to write receipt: $($_.Exception.Message)"
    exit 1
}

if ($errors -gt 0) {
    Write-Host "=== $errors check(s) FAILED ==="
    exit 1
}
Write-Host "=== All checks PASSED ==="
exit 0
```

### 第四步：激活

```bash
$PythonExecutable = (Resolve-Path -LiteralPath "<absolute-path-to-healthy-python.exe>").Path
chmod +x hooks/pre-commit hooks/pre-push
powershell -ExecutionPolicy Bypass -File register-hooks.ps1 -PythonExecutable $PythonExecutable
```

### 第五步：检测已有治理工具

列出项目中实际存在的治理工具：

| 工具 | 路径 | 用途 |
|------|------|------|
| ai_guard.py | `tools/ai_guard.py` | 密钥扫描 |
| Test-GovernanceDrift.ps1 | `scripts/Test-GovernanceDrift.ps1` | 漂移检测 |
| Test-Governance.ps1 | `scripts/Test-Governance.ps1` | repo diff gate |
| Update-GovernanceManifest.ps1 | `scripts/Update-GovernanceManifest.ps1` | manifest 自动再生 |

逐项检查文件是否存在，在报告中列出：已有的标记 `[OK]`，没有的标记 `[—]`。

### 第六步：验证

```bash
powershell -ExecutionPolicy Bypass -File ci-preflight.ps1
```

预期：已有的工具对应的检查项 PASS，没有的工具对应的检查项 SKIP。三项不应有 FAILED。

### 第七步：测试 hook 触发

用无害方式验证 hook 真的会触发：

```bash
echo "# ci-preflight test" >> README.md
git add README.md
git commit -m "test: verify CI preflight hooks"
```

观察输出应包含 `=== Pre-Commit Governance Gate ===`。

然后回滚：

```bash
git reset --hard HEAD~1
```

### 第八步：报告

用以下格式输出报告：

```
## CI Preflight 安装报告

**项目**：<项目路径>
**core.hooksPath**：<结果>

**Hook 文件**：
  pre-commit          : created / already exists
  pre-push            : created / already exists

**已检测工具**：
  [OK/—] ai_guard.py
  [OK/—] Test-GovernanceDrift.ps1
  [OK/—] Test-Governance.ps1
  [OK/—] Update-GovernanceManifest.ps1

**验证**：
  ci-preflight.ps1   : PASS / FAILED
  hook 触发测试       : PASS / FAILED

**后续步骤**：
  1. 编辑 governance/expected-files.txt 加入本项目治理文件
  2. 如有 Update-GovernanceManifest.ps1，运行一次生成初始 manifest
  3. 正常使用 git commit / git push，hook 自动生效
```

---

直接复制这整段发给智能体即可。
