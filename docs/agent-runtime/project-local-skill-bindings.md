# Project-Local Skill Bindings

> Scope: `D:\dev-frame-system`
> Status: active for the current public repository

This file defines how project-local skills and agent conversations must resolve
paths for the current `dev-frame-system` repository.

## Canonical Roots

| ID | Role | Root |
|---|---|---|
| `dev-frame-system` | Current project root | `D:\dev-frame-system` |
| `agents-binding-root` | User-level binding metadata root | `%USERPROFILE%\.agents\bindings\dev-frame-system` |
| `runtime-root` | User-level runtime session/evidence root | `%USERPROFILE%\.devframe-runtime` |

## `/rdinit`

For this project, `/rdinit` must treat `D:\dev-frame-system` as the canonical
project root.

Required paths:

- Project root: `D:\dev-frame-system`
- Bootstrap script: `D:\dev-frame-system\templates\runtime-bootstrap\bootstrap.ps1`
- Runtime template source: resolved from the bootstrap script location, not a
  hard-coded external checkout.

`<legacy-standalone-root>` is a legacy standalone root. Do not use it for this
repository unless the user explicitly asks to operate on that old checkout.

## `/bindChrome`

For this project, `/bindChrome` must bind conversations against the current
project root and the user-level binding store.

Required paths:

- Registry: `%USERPROFILE%\.agents\bindings\dev-frame-system\PROJECT_REGISTRY.json`
- Conversation binding: `%USERPROFILE%\.agents\bindings\dev-frame-system\CONVERSATION_BINDING.json`
- Runtime session record:
  `%USERPROFILE%\.devframe-runtime\web-ai-sessions\chatgpt-<conversation-id>-session.json`
- Browser automation transport: existing Chrome CDP endpoint, not repo-local profile files

Do not write `.agent/` binding state into the public repository. Binding files
must stay under the user-level `.agents` store so a conversation URL change does
not dirty the repo.

## Dispatch Rule

TaskSpecs sent to module agents must use absolute paths from the registry. The
goal agent should not infer roots from old prompts, browser tabs, or legacy
handoff text.

Minimum TaskSpec path fields:

```yaml
project_root: "D:\dev-frame-system"
target_project_id: "dev-frame-system"
target_project_root: "D:\dev-frame-system"
allowed_write_roots:
  - "D:\dev-frame-system"
```

For any governance or review work, the allowed write roots must remain explicit.
An agent may read user-level binding metadata when needed, but it must not write
outside its assigned project roots unless the TaskSpec names that path.
