# p23 三级任务离线验收 runner：纯离线，不启动 dsh，不联网，不读仓库其他文件。
# 用法（在 worktree 根目录）：pwsh -File .agents\devframe\p23\run-offline-acceptance.ps1

# 真实模型运行段门禁：无 key 只提示，不影响离线段。
if (-not $env:DEEPSEEK_API_KEY) { Write-Host '真实模型运行段被阻塞（缺 DEEPSEEK_API_KEY）——离线段不受影响' }

$base = Split-Path $PSCommandPath
$script:failed = $false

function Ok([string]$msg) { Write-Host "[ok] $msg" }
function Fail([string]$msg) { Write-Host "[FAIL] $msg"; $script:failed = $true }

# --- 四件套存在性：brief / manifest / runner（自身）/ evidence（允许检查时已存在；未生成不算缺口，本 runner 跑完后写入）---
$briefPath = Join-Path $base 'three-level-task-brief.md'
$manifestPath = Join-Path $base 'journey-manifest.json'
$evidencePath = Join-Path $base 'offline-acceptance-evidence.md'
foreach ($f in @($briefPath, $manifestPath, $PSCommandPath)) {
    if (Test-Path $f) { Ok "存在 $(Split-Path -Leaf $f)" } else { Fail "缺文件 $(Split-Path -Leaf $f)" }
}
if (Test-Path $evidencePath) { Ok '存在 offline-acceptance-evidence.md（检查时已存在，允许）' }
else { Ok 'offline-acceptance-evidence.md 未生成（允许：本 runner 跑完后写入，不算缺口）' }

# --- brief 内容检查 ---
if (Test-Path $briefPath) {
    $patterns = @('派单', 'Worker 执行', '组长验收', '总控合并', '账本登记', '铁律', '缺 DEEPSEEK_API_KEY 阻塞')
    foreach ($p in $patterns) {
        if (Select-String -Path $briefPath -SimpleMatch $p -Quiet) { Ok "brief 含 '$p'" }
        else { Fail "brief 缺 '$p'" }
    }
}

# --- manifest 检查 ---
$manifest = $null
if (Test-Path $manifestPath) {
    try {
        $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Ok 'manifest ConvertFrom-Json 成功'
    } catch {
        Fail "manifest JSON 解析失败：$($_.Exception.Message)"
    }
}

$requiredFields = @('sessionId', 'worktree', 'branch', 'commitSha', 'gateCounts')
if ($manifest) {
    $steps = @($manifest.steps) | Where-Object { $null -ne $_ }
    if ($steps.Count -eq 5) { Ok 'manifest steps.Count = 5' } else { Fail "manifest steps.Count = $($steps.Count)（应 5）" }
    foreach ($s in $steps) {
        $stepName = [string]$s.step
        $fields = @($s.persistence_fields) | Where-Object { $null -ne $_ }
        $missing = @($requiredFields | Where-Object { $fields -notcontains $_ })
        if ($missing.Count -eq 0) { Ok "step '$stepName' persistence_fields 覆盖 sessionId/worktree/branch/commitSha/gateCounts" }
        else { Fail "step '$stepName' persistence_fields 缺：$($missing -join '/')" }
        if ($stepName) {
            if (Select-String -Path $briefPath -SimpleMatch $stepName -Quiet) { Ok "brief 命中 step '$stepName'" }
            else { Fail "brief 未命中 step '$stepName'" }
        } else {
            Fail 'step 缺 step 名，无法与 brief 交叉核对'
        }
    }
}

# --- 结算 ---
if ($script:failed) { Write-Host '缺口：见上方 [FAIL] 行'; exit 1 }
Write-Host 'OFFLINE ACCEPTANCE: ALL GREEN'
exit 0
