$ErrorActionPreference = "Stop"

$maxInputChars = 65536
$jobTimeoutSeconds = 8
$job = $null
$runtimePython = $null
$runtimeState = $null
$vaultRoot = $null

function Write-Continue {
    [Console]::Out.WriteLine('{"continue":true,"suppressOutput":true}')
}

function ConvertFrom-TemplateBase64([string]$encoded, [string]$name) {
    if ([string]::IsNullOrWhiteSpace($encoded) -or $encoded.Contains("{{")) {
        throw "Unresolved template value: $name"
    }
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    return $strictUtf8.GetString([Convert]::FromBase64String($encoded))
}

try {
    $runtimePython = ConvertFrom-TemplateBase64 "{{DEVFRAME_MEMORY_PYTHON_B64}}" "runtime python"
    $runtimeState = ConvertFrom-TemplateBase64 "{{DEVFRAME_RUNTIME_STATE_B64}}" "runtime state"
    $vaultRoot = ConvertFrom-TemplateBase64 "{{DEVFRAME_OBSIDIAN_VAULT_B64}}" "vault root"

    $inputBuilder = New-Object System.Text.StringBuilder
    $buffer = New-Object char[] 4096
    while (($read = [Console]::In.Read($buffer, 0, $buffer.Length)) -gt 0) {
        if ($inputBuilder.Length + $read -gt $maxInputChars) {
            Write-Continue
            exit 0
        }
        [void]$inputBuilder.Append($buffer, 0, $read)
    }
    $rawInput = $inputBuilder.ToString()
    if ([string]::IsNullOrWhiteSpace($rawInput)) {
        Write-Continue
        exit 0
    }
    $payload = $rawInput | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $payload -or $payload -is [System.Array]) {
        Write-Continue
        exit 0
    }
    if ([string]$payload.hook_event_name -ne "PreCompact") {
        Write-Continue
        exit 0
    }
    $cwd = [string]$payload.cwd
    $sessionId = [string]$payload.session_id
    $turnId = [string]$payload.turn_id
    $transcriptPath = [string]$payload.transcript_path
    $trigger = [string]$payload.trigger
    if ([string]::IsNullOrWhiteSpace($trigger)) {
        $trigger = "auto"
    }
    if (
        [string]::IsNullOrWhiteSpace($cwd) -or
        [string]::IsNullOrWhiteSpace($sessionId) -or
        [string]::IsNullOrWhiteSpace($turnId) -or
        [string]::IsNullOrWhiteSpace($transcriptPath) -or
        -not (Test-Path -LiteralPath $runtimePython -PathType Leaf)
    ) {
        Write-Continue
        exit 0
    }

    $arguments = @(
        "-I", "-B", "-m", "control_plane.cli", "memory",
        "checkpoint", "capture-from-transcript",
        "--cwd", $cwd,
        "--transcript-path", $transcriptPath,
        "--session-id", $sessionId,
        "--turn-id", $turnId,
        "--trigger", $trigger,
        "--runtime-dir", $runtimeState,
        "--vault-root", $vaultRoot,
        "--format", "json"
    )
    $argumentJson = ConvertTo-Json -Compress -InputObject $arguments
    $job = Start-Job -ScriptBlock {
        param([string]$executable, [string]$serializedArguments)
        $cliArguments = ConvertFrom-Json -InputObject $serializedArguments
        $null = & $executable @cliArguments 2>$null
        return [int]$LASTEXITCODE
    } -ArgumentList @($runtimePython, $argumentJson)
    $completed = Wait-Job -Job $job -Timeout $jobTimeoutSeconds
    if ($null -ne $completed) {
        $null = Receive-Job -Job $job -ErrorAction SilentlyContinue
    }
} catch {
    Write-Debug "Bounded Obsidian checkpoint capture was unavailable."
} finally {
    if ($null -ne $job) {
        if ($job.State -eq "Running") {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
        }
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

Write-Continue
exit 0
