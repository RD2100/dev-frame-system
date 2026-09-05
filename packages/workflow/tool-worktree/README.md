---
description: "The model-facing worktree tools: create, list, status, remove, and prune (reconcile) over the calling session's own workspace, for users and maintainers choosing or configuring the worktree consumer."
kind: "package-reference"
---

# @deepseek-ai/dsh-tool-worktree

English | [中文](README.zh.md)

## Summary

`dsh-tool-worktree` gives the model five `worktree_*` tools over `ctx.worktreeRegistry`: create, list, status, remove, and prune (reconcile). Every tool is bound to the calling session's own workspace — the workspace comes from the immutable session header cwd, never from a model-supplied id — so the model can only manage the second checkouts of the directory it runs in. The registry package owns the git mechanics, the durable rows, and the refusal classification; this plugin owns the schemas, the authorization door, and the model-facing renderings. Results ride the ordinary tool call/result session events, so no new session event is owed.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

The five tools are the only model-visible surface of the worktree seam. A session running inside a registered workspace can create clean checkouts for builds, experiments, or parallel tasks, observe them, remove them, and reconcile the registry with what git actually reports. A session whose directory is not a registered workspace receives the same authorization rejection from every tool.

### The tools

| Tool | Purpose | Key behavior |
|---|---|---|
| `worktree_create` | Add a linked worktree and register it durably | `path` is required; absolute paths stand, relative paths resolve against the workspace directory. `branch` names a NEW branch. |
| `worktree_list` | List this workspace's registrations | Durable rows only; worktrees created outside the product are invisible until adopted. |
| `worktree_status` | Observe one worktree by id | A missing directory reports `directoryExists: false` — an observation, not an error. |
| `worktree_remove` | Delete one worktree through git | Dirty trees refuse unless `force: true`; the registration drops only after git succeeded. |
| `worktree_prune` | Reconcile rows with `git worktree list` | Report-only by default; `pruneDangling: true` drops stale rows, `adoptUnregistered: true` registers outside-created worktrees. |

### Authorization

Each call resolves the caller from `exec.agent`'s session header cwd, canonicalized and matched against `ctx.workspaceRegistry`. A call without a calling agent, a header without a cwd, or a directory that is not a registered workspace all reject with the reason stated. A worktree id registered under a different workspace is reported exactly like an unknown id — the rejection message says `is not registered for this workspace` either way, so the model cannot probe other workspaces' registrations through error differences.

### Refusals and retry semantics

The registry classifies git's four refusal dialects — occupied path, branch conflict, dirty tree, oversized path — and the typed error text carries the concrete fix, so the model can retry with a corrected argument without host help. The classification table and the retry semantics for each kind live in the [worktree-registry README](../worktree-registry/README.md#failure-kinds-retry-semantics-and-link-shells); `worktree_create` refusals name the kind in their reason text (`path-exists`, `branch-conflict`, `path-length`).

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the authorization door and the renderings; observable behavior is fully covered in [Use this package](#use-this-package).

### Design concept

The plugin is a thin Consumer: it declares no config, registers the guidance section, and adds five tools whose execute bodies validate arguments and delegate to `ctx.worktreeRegistry` (and `ctx.workspaceRegistry` for the caller resolution). The git mechanics, durable rows, and refusal classification are the registry package's contract, not re-implementations.

### Authorization order

`resolveCaller` runs first in every execute body: it rejects a missing agent or cwd, canonicalizes the header cwd with `fs.realpath`, and matches it against registered workspace paths (case-folded on Windows). Only then do the tools resolve ids through `authorizedWorktree`, which rejects ids that have no row for the caller's workspace. Argument validation (`path`, `id` non-empty) happens before any registry call.

### Render intent

The pending call is a `generic` card titled from the call's arguments (for example `worktree: create '<path>'`), and the result keeps a plain generic card. Status and prune results add rendering hints: a missing directory points at `worktree_prune`, and a prune report lists the dangling registrations and unregistered worktrees with the applied action counts.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Plugin entry: guidance section, five tool schemas, renderings, delegation to the registry |
| [`src/authorization.ts`](src/authorization.ts) | Caller resolution from the session header and workspace-authorized id checks |
| — | No runtime invariant companion is published; this consumer owns no independent event stream or divergent observation — the registry validates its own operations, and tool results ride the ordinary call/result events. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

Read these pages when the tool-level contract is not enough.

- [Worktree registry subsystem](../../../docs/subsystems/worktree-registry.md) — the seam contract behind the tools.
- [Worktree registry package](../worktree-registry/README.md) — the operations, durable rows, refusal classification, and reconcile report.
- [Generated tool catalog](../../../docs/tool-catalog.md#deepseek-aidsh-tool-worktree) — the exact schemas the model receives.
- [Worktree tools Agent Note](../../../.agents/notes/implemented/feature/2026-09-05-worktree-tools-and-reconcile.md) — the authorization design and its decisions.

-----

<a id="model-experience"></a>
## Model Experience

### System prompt

#### What the model sees

Every parent request in this plugin's registration scope receives the fixed routing guidance below.

##### Worktree guidance

```markdown
The worktree_* tools manage second checkouts (git worktrees) of the calling session's own workspace: they authorize against the session's working directory and cannot touch another workspace's registrations. Get ids with worktree_list before worktree_status or worktree_remove; create with worktree_create for clean builds, experiments, or parallel tasks. A worktree whose directory was deleted outside the product is recovered with worktree_prune (pruneDangling: true), and outside-created checkouts become manageable after worktree_prune (adoptUnregistered: true).
```

#### Token effect

Small fixed guidance cost per request while the plugin is active.

#### KV Cache effect

Prefix-stable while the plugin scope and guidance text are unchanged. Activation or disposal may invalidate reuse from this prompt section.

### Tool schema

#### What the model sees

The generated [`worktree_*` schemas](../../../docs/tool-catalog.md#deepseek-aidsh-tool-worktree) expose five tools. `worktree_create` takes a required `path` string and an optional `branch` string; `worktree_list` takes no parameters; `worktree_status` and `worktree_remove` take a required worktree `id` (plus an optional `force` boolean on remove); `worktree_prune` takes the two optional action booleans. Provider-side details — durable rows, subprocess calls, refusal classification — are absent from the call schemas.

#### Token effect

Small fixed schema cost on each request where the tools are visible.

#### KV Cache effect

Prefix-stable while the definitions and visibility are unchanged.

### Tool results

#### What the model sees

Create returns `{ id, path, branch }`; list returns the workspace's registrations with id, canonical path, branch, and creation time; status returns `{ id, directoryExists, branch?, clean? }` with optional fields absent when the directory is gone; remove and prune return the applied outcome with per-item render text. Errors return isError results whose text states the cause and the concrete fix.

#### Token effect

Proportional to the workspace's worktree count for list and prune; single-item results for the other tools.

#### KV Cache effect

Each result appends after the reusable request prefix; no prefix invalidation comes from this package.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>


These limits define what the tools do not yet support. They are current constraints, not a task backlog.

- **One workspace per call** — the authorization anchors every tool to the calling session's workspace; a model cannot manage another workspace's worktrees even when that workspace is registered.
- **No move, rename, or re-branch tool** — the registry's create/remove vocabulary is exposed as-is; mutating an existing worktree's location or branch is deferred.
- **Adoption trusts git's list** — `adoptUnregistered` registers whatever `git worktree list` reports outside the known rows, without human confirmation.
- **Presentation stays generic** — every card is the `generic` card; dedicated worktree card renderers are deferred.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

This Dev Note is working context for maintainers: open directions that are not decided. It is explicitly non-authoritative — shipped behavior, limits, and accepted rationale live in the sections above, the package code, and the linked Agent Notes.

Open directions: dedicated card renderers for status and prune; a move/re-branch operation pair; and per-tool permission hooks if deployments want to gate removal separately from observation.

</details>
