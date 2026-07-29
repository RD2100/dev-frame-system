# RD2100 Agent Runtime -- Bootstrap Template

> Version: 1.1 | Requires: PowerShell 5.1+, git
> Target: Any project needing Agent Runtime governance (Claude Code / Codex / Both)

## What This Is

A one-command bootstrap that initializes the RD2100 Agent Runtime governance framework in any project. Copies universal assets (rules, schemas, reviewer docs) and generates project-specific files (AGENTS.md, capability inventory, tool policy) from templates.

## What You Get

| Asset | Type | Scope |
|-------|------|:---:|
| Rules | Copied (universal) | Versioned public rule catalog |
| Schemas | Copied (universal) | 18 JSON Schema files |
| AGENTS.md | Generated | 1 file |
| Capability Inventory | Generated | 10 universal + N project-specific |
| Tool Policy | Generated | 1 file |
| `/go` wrapper | Generated | `tools/devframe-go.ps1` |
| Reviewer Docs | Copied (universal) | 5 files |
| Outcome-First Delivery | Copied (universal) | Milestones, risk profiles, quiet gates |
| Negative Test Fixtures | Copied (universal) | 30 fixtures |

## Quick Start

```powershell
# In project root (auto-detect):
.\templates\runtime-bootstrap\bootstrap.ps1

# Explicit params:
.\bootstrap.ps1 -ProjectName "my-app" -ProjectRoot "D:\my-app" -Platform Both

# Dry-run:
.\bootstrap.ps1 -DryRun
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| -ProjectName | Auto-detected | Project name |
| -ProjectRoot | Current dir | Absolute project root |
| -Platform | Both | Claude / Codex / Both |
| -Phase | 0-5 | Phase designation |
| -DryRun | false | Preview only |
| -Force | false | Overwrite existing |

## Template Files

| Template | Placeholders | Generates |
|----------|-------------|-----------|
| AGENTS.template.md | {{PROJECT_NAME}}, {{PROJECT_ROOT}}, {{CURRENT_DATE}}, {{GIT_REMOTE}}, {{PHASE}}, {{PLATFORM}} | AGENTS.md |
| capability-inventory.template.md | {{PROJECT_NAME}}, {{CURRENT_DATE}}, {{PHASE}} | capability-inventory.md |
| tool-policy.template.md | {{PROJECT_NAME}}, {{PROJECT_ROOT}}, {{PHASE}} | tool-policy.md |
| devframe-go.template.ps1 | {{PROJECT_ROOT}} | tools/devframe-go.ps1 |
| recall-obsidian-working-plan.template.ps1 | {{DEVFRAME_MEMORY_PYTHON_B64}}, {{DEVFRAME_RUNTIME_STATE_B64}}, {{DEVFRAME_OBSIDIAN_VAULT_B64}}, {{DEVFRAME_MEMORY_START_SCRIPT_B64}}, {{DEVFRAME_MEMORY_PORT_B64}} | one global, project-dynamic Codex SessionStart hook |
| checkpoint-obsidian-session.template.ps1 | {{DEVFRAME_MEMORY_PYTHON_B64}}, {{DEVFRAME_RUNTIME_STATE_B64}}, {{DEVFRAME_OBSIDIAN_VAULT_B64}} | one fail-open Codex PreCompact checkpoint hook |

`tools/devframe-go.ps1` defaults to token-safe preview. Use `-Prepare` to create
queued packets without running workers; use `-Execute` only when you are ready
to spend worker tokens. Start optional diagnostics separately with
`devframe dashboard serve --runtime-dir <dir>`.

The Obsidian hook templates are intentionally not installed by `bootstrap.ps1`.
Rendering or registering global Codex hooks is a separate human-gated
activation step. Every `_B64` placeholder must be replaced with the standard
Base64 encoding of the UTF-8 value, including the numeric loopback port. The
hook decodes these values at runtime so PowerShell metacharacters in local
paths cannot become script syntax. SessionStart only recalls bounded guidance and registers the
resolved project; it never writes the Vault. PreCompact may create one bounded,
immutable checkpoint under the agent-owned project subtree. It reads only a
bounded transcript tail, stores high-signal fields rather than raw chat, is
idempotent per session/turn event, suppresses private output, and fails open.
The optional loopback service start is asynchronous, so service startup or
failure cannot hold the SessionStart recall path.
