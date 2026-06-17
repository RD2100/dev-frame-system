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
governance/
  expected-files.txt
  manifest-ignore.txt
register-hooks.ps1
ci-preflight.ps1
```

#### hooks/pre-commit

```bash
#!/bin/bash
powershell -ExecutionPolicy Bypass -File "$(dirname "$0")/pre-commit.governance.ps1"
exit $?
```

创建后执行 `chmod +x hooks/pre-commit`。

#### hooks/pre-commit.governance.ps1

```powershell
# pre-commit.governance.ps1 — Pre-commit governance gate.
# Exit 0: allow commit. Exit 1: block commit.

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== Pre-Commit Governance Gate ==="

# ---- 1. Manifest auto-regeneration (skip if no Update-GovernanceManifest.ps1) ----
Write-Host "[1/2] Manifest auto-regeneration..."
$updateScript = Join-Path $ProjectRoot "scripts\Update-GovernanceManifest.ps1"
$manifestPath = "hooks\sealed-files-manifest.json"

if (Test-Path $updateScript) {
    Push-Location $ProjectRoot
    try {
        $before = if (Test-Path $manifestPath) { Get-Content $manifestPath -Raw } else { "" }
        & powershell -ExecutionPolicy Bypass -File $updateScript | Out-Null
        $after = if (Test-Path $manifestPath) { Get-Content $manifestPath -Raw } else { "" }
        if ($before -ne $after) {
            git add $manifestPath 2>$null
            Write-Host "[OK] Manifest regenerated and staged."
        } else {
            Write-Host "[OK] Manifest up to date."
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[SKIP] Update-GovernanceManifest.ps1 not found."
}
Write-Host ""

# ---- 2. Compliance checks ----
Write-Host "[2/2] Compliance checks..."

$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot
    try {
        & python $aiGuard staged 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[BLOCKED] ai_guard.py found issues. Fix before commit."
            exit 1
        }
        Write-Host "  ai_guard: PASS"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  ai_guard: not found — SKIP"
}

Write-Host ""
Write-Host "=== Pre-Commit PASS ==="
exit 0
```

#### hooks/pre-push

```bash
#!/bin/bash
powershell -ExecutionPolicy Bypass -File "$(dirname "$0")/pre-push.governance.ps1"
exit $?
```

创建后执行 `chmod +x hooks/pre-push`。

#### hooks/pre-push.governance.ps1

```powershell
# pre-push.governance.ps1 — Pre-push governance gate.
# Exit 0: allow push. Exit 1: block push.

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$errors = 0

Write-Host "=== Pre-Push Governance Gate ==="

# ---- 1. Secret scan ----
Write-Host "[1/3] Secret scan..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot
    try { & python $aiGuard full 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "[BLOCKED] ai_guard failed" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

# ---- 2. Drift check ----
Write-Host "[2/3] Drift check..."
$drift = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path $drift) {
    Push-Location $ProjectRoot
    try { & powershell -ExecutionPolicy Bypass -File $drift 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "[BLOCKED] Drift check failed" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

# ---- 3. Governance gate ----
Write-Host "[3/3] Governance gate..."
$gate = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path $gate) {
    Push-Location $ProjectRoot
    try { & powershell -ExecutionPolicy Bypass -File $gate -Mode blocking 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "[BLOCKED] Gate failed" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

if ($errors -gt 0) {
    Write-Host "=== BLOCKED: $errors check(s) failed ==="
    exit 1
}
Write-Host "=== PASS ==="
exit 0
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
# register-hooks.ps1 — Activate CI preflight hooks. Run once per clone.
$ErrorActionPreference = 'Stop'
$HookDir = "$PSScriptRoot\hooks"
$RepoRoot = (Resolve-Path (Join-Path $HookDir "..")).Path
Write-Host "=== CI Preflight Registration ==="
foreach ($f in @("pre-commit","pre-commit.governance.ps1","pre-push","pre-push.governance.ps1")) {
    if (-not (Test-Path (Join-Path $HookDir $f))) { Write-Error "Missing: hooks/$f"; exit 1 }
}
Push-Location $RepoRoot
try { git config core.hooksPath hooks; Write-Host "[OK] core.hooksPath = hooks" } finally { Pop-Location }
Write-Host "Next: edit governance/expected-files.txt, then verify with ci-preflight.ps1"
```

#### ci-preflight.ps1

```powershell
# ci-preflight.ps1 — Run CI-equivalent checks locally.
$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$errors = 0
Write-Host "=== CI Preflight ==="
Write-Host ""

Write-Host "[1/3] AI Guard..."
$aiGuard = Join-Path $ProjectRoot "tools\ai_guard.py"
if (Test-Path $aiGuard) {
    Push-Location $ProjectRoot; try { & python $aiGuard full 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

Write-Host "[2/3] Drift Check..."
$drift = Join-Path $ProjectRoot "scripts\Test-GovernanceDrift.ps1"
if (Test-Path $drift) {
    Push-Location $ProjectRoot; try { & powershell -ExecutionPolicy Bypass -File $drift 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

Write-Host "[3/3] Governance Gate..."
$gate = Join-Path $ProjectRoot "scripts\Test-Governance.ps1"
if (Test-Path $gate) {
    Push-Location $ProjectRoot; try { & powershell -ExecutionPolicy Bypass -File $gate -Mode blocking 2>&1 } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { $errors++; Write-Host "  FAILED" } else { Write-Host "  PASS" }
} else { Write-Host "  SKIP" }
Write-Host ""

if ($errors -gt 0) { Write-Host "=== $errors check(s) FAILED ==="; exit 1 }
Write-Host "=== All checks PASSED ==="; exit 0
```

### 第四步：激活

```bash
chmod +x hooks/pre-commit hooks/pre-push
powershell -ExecutionPolicy Bypass -File register-hooks.ps1
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
