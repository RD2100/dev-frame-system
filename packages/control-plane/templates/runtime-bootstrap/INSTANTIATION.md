# Runtime Bootstrap - Instantiation Guide

## Step 1: Run Bootstrap

From a source checkout of `RD2100/dev-frame-system`:

```powershell
cd D:\your-project
powershell -ExecutionPolicy Bypass -File <repo-root>\templates\runtime-bootstrap\bootstrap.ps1
```

Auto-detects project name from directory or git remote. Override:

```powershell
.\bootstrap.ps1 -ProjectName "my-app" -ProjectRoot "D:\my-app" -Platform Both
```

## Step 2: Verify

```powershell
cat AGENTS.md | Select-String "{{"   # Must return nothing
dir rules\
dir schemas\
cat docs\agent-runtime\capability-inventory.md | Select-String "^## \d+\."  # >= 10
```

## Step 2b: Verify Governance Integrity

After bootstrap, check that protected governance sections match the manifest:

```powershell
Get-FileHash rules/core.md, AGENTS.md -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash)  $([System.IO.Path]::GetFileName($_.Path))" }
```

Compare hashes against `docs/agent-runtime/governance-manifest.md`. If any protected section hash differs, treat it as governance drift and escalate to human review.

## Step 3: Register Project Resources

1. Open `docs/agent-runtime/capability-inventory.md`.
2. Add entries for project-specific resources.
3. Set `Status: proposed`, submit to reviewer, then change to `Status: approved` after sign-off.

## Step 4: Configure Platform Assets

Claude Code: add project-specific hooks or sealed-file manifests only after review. Codex: enable plugins as needed and compare tool availability against the capability inventory.

## Step 5: Submit For Review

```markdown
# Bootstrap Report -- PROJECT_NAME
- Bootstrap v1.0
- Assets: rules, schemas, AGENTS.md, capability inventory, tool policy, reviewer docs, negative fixtures
- Pending: register project capabilities, configure platform assets, reviewer sign-off
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `{{PROJECT_NAME}}` in AGENTS.md | Re-run with `-Force` |
| Rules not copied | Ensure bootstrap is run from a source checkout with root `rules/`, `schemas/`, and `docs/` |
| File exists errors | Use `-Force` |
