# Tool Policy -- {{PROJECT_NAME}}

> Bootstrap: {{CURRENT_DATE}} | Phase: {{PHASE}} | Platform: {{PLATFORM}} | Template v1.0

## Permitted Operations

| Operation | Condition |
|-----------|-----------|
| Read files | Within {{PROJECT_ROOT}} |
| List directories | Within {{PROJECT_ROOT}} |
| Git status/log/diff/hash | Read-only |
| Root-accepted local Git commit | Root coordinator only; independent review and required evidence pass, `root_accepted` is recorded, exact accepted paths are staged, cached diff is reconciled, and one local logical commit is created |
| Search (rg, Grep, Select-String) | Read-only |
| JSON validation | Read-only schema audit |
| CodeGraph search/context/explore | Read-only; reindex = human gate |
| Generate files | Only within approved output paths |

## Approved Output Paths

```
docs/agent-runtime/
rules/
schemas/
reports/
hooks/          (audit-only draft; activation = human gate)
templates/
```

## Forbidden (Phase {{PHASE}})

| Category | Forbidden |
|----------|-----------|
| Git slice lifecycle | Worker staging or commit; pre-`root_accepted` commit; commit of failed, blocked, rejected, or unreviewed work; `git add -A`; `git add .`; `git commit -a`; broad restore or checkout; stash; reset; clean |
| Git external effects | Push, pull request creation, merge, release, history rewrite, hook registration, or global Git/agent configuration without an explicit human gate; force-push to `main` or `master` is always forbidden |
| Packages | npm/pip/yarn/pnpm/cargo install |
| MCP | enable, register, modify config |
| Scripts | execute .ps1/.py/.sh without ScriptSafetyRecord + human gate |
| Memory | write, modify, compress, delete |
| Skills | install, execute, auto-load, evolve |
| WorkQueue | consume, modify, reorder |
| External | clone, fetch, pull, install |
| UI | desktop/browser automation (external URLs) |
| Secrets | read .env, .key, .pem, token files |
| User dirs | write to C:\Users, ~/.claude, ~/.codex (except approved config) |

## Capability Use Rules

1. Every capability must be in `docs/agent-runtime/capability-inventory.md` with Status: approved (core-007)
2. Platform field must match executing platform
3. Phase constraints (Access, Human gate, Forbidden) must be respected
4. Missing capability -> stop and propose registration, do not use first

## Evidence Requirements

- File reads: path + section reference
- Commands: command + CWD + result + exit code
- Claims: backed by test result, file listing, or command output
- Unknown/skipped/blocked: report honestly, never mark pass

> Generated from `templates/runtime-bootstrap/tool-policy.template.md`. Run bootstrap.ps1 -Force to regenerate.
